import io
import numpy as np
from PIL import Image, ImageCms

# Global cache for built ImageCms ICC transforms
_CMS_TRANSFORM_CACHE = {}

def get_icc_transform(icc_bytes: bytes):
    """Build and cache PIL ImageCms transform from embedded raw ICC profile bytes to sRGB."""
    if not icc_bytes:
        return None
    cache_key = hash(icc_bytes)
    if cache_key in _CMS_TRANSFORM_CACHE:
        return _CMS_TRANSFORM_CACHE[cache_key]

    try:
        in_profile = ImageCms.getOpenProfile(io.BytesIO(icc_bytes))
        srgb_profile = ImageCms.createProfile("sRGB")
        transform = ImageCms.buildTransform(in_profile, srgb_profile, "RGB", "RGB")
        _CMS_TRANSFORM_CACHE[cache_key] = transform
        return transform
    except Exception as e:
        print(f"[ICC Profile Warning] Failed to parse ICC profile transform: {e}")
        _CMS_TRANSFORM_CACHE[cache_key] = None
        return None

def check_icc_profile(slide) -> tuple[bytes | None, bool]:
    """Inspect slide object or properties for embedded ICC color profile."""
    icc_bytes = None
    
    # 1. OpenSlide properties
    if hasattr(slide, "properties"):
        icc_bytes = slide.properties.get("openslide.color-profile")
        if isinstance(icc_bytes, str):
            icc_bytes = icc_bytes.encode("utf-8")

    # 2. PIL Image info fallback
    if not icc_bytes and hasattr(slide, "info"):
        icc_bytes = slide.info.get("icc_profile")

    has_icc = bool(icc_bytes and len(icc_bytes) > 0)
    return (icc_bytes if has_icc else None), has_icc

def read_region_srgb(
    slide,
    x_um: float,
    y_um: float,
    w_um: float,
    h_um: float,
    out_px: int | tuple[int, int],
    mpp_x: float = 0.25,
    mpp_y: float = 0.25
) -> tuple[np.ndarray, bool]:
    """
    Authoritative single entry point for reading slide tile regions in sRGB color space.
    
    :param slide: OpenSlide object or PIL Image object.
    :param x_um: Top-left X coordinate in micrometers (base level 0).
    :param y_um: Top-left Y coordinate in micrometers (base level 0).
    :param w_um: Width of region in micrometers.
    :param h_um: Height of region in micrometers.
    :param out_px: Target pixel dimension (int or (width, height) tuple).
    :param mpp_x: Micrometers per pixel X at level 0.
    :param mpp_y: Micrometers per pixel Y at level 0.
    :return: (RGB uint8 numpy array of shape (H, W, 3), icc_applied boolean)
    """
    if isinstance(out_px, int):
        target_w_px, target_h_px = out_px, out_px
    else:
        target_w_px, target_h_px = out_px

    x_px_0 = int(round(x_um / mpp_x))
    y_px_0 = int(round(y_um / mpp_y))
    w_px_0 = int(round(w_um / mpp_x))
    h_px_0 = int(round(h_um / mpp_y))

    icc_bytes, has_icc = check_icc_profile(slide)
    icc_applied = False

    # 1. OpenSlide Slide object
    if hasattr(slide, "read_region"):
        best_level = 0
        if hasattr(slide, "get_best_level_for_downsample"):
            target_downsample = w_px_0 / max(1, target_w_px)
            best_level = slide.get_best_level_for_downsample(target_downsample)

        level_ds = slide.level_downsamples[best_level] if hasattr(slide, "level_downsamples") else 1.0
        w_px_lvl = max(1, int(round(w_px_0 / level_ds)))
        h_px_lvl = max(1, int(round(h_px_0 / level_ds)))

        pil_tile = slide.read_region((x_px_0, y_px_0), best_level, (w_px_lvl, h_px_lvl))
        if pil_tile.mode != "RGB":
            pil_tile = pil_tile.convert("RGB")

    # 2. PIL Image object fallback
    elif hasattr(slide, "crop"):
        img_w, img_h = slide.size
        box_x1 = max(0, min(img_w, x_px_0))
        box_y1 = max(0, min(img_h, y_px_0))
        box_x2 = max(box_x1, min(img_w, x_px_0 + w_px_0))
        box_y2 = max(box_y1, min(img_h, y_px_0 + h_px_0))

        if box_x2 > box_x1 and box_y2 > box_y1:
            pil_tile = slide.crop((box_x1, box_y1, box_x2, box_y2))
        else:
            pil_tile = Image.new("RGB", (max(1, target_w_px), max(1, target_h_px)), color=(240, 235, 240))

        if pil_tile.mode != "RGB":
            pil_tile = pil_tile.convert("RGB")

    else:
        raise TypeError(f"Unsupported slide object type: {type(slide)}")

    # Apply ICC transform if embedded profile exists
    if has_icc and icc_bytes:
        transform = get_icc_transform(icc_bytes)
        if transform:
            try:
                pil_tile = ImageCms.applyTransform(pil_tile, transform)
                icc_applied = True
            except Exception as pe:
                print(f"[ICC Transform Note] {pe}")

    # Ensure tile has valid dimensions
    if pil_tile.width == 0 or pil_tile.height == 0:
        pil_tile = Image.new("RGB", (max(1, target_w_px), max(1, target_h_px)), color=(240, 235, 240))

    # Resize to exact target output dimensions if needed
    if pil_tile.size != (target_w_px, target_h_px):
        pil_tile = pil_tile.resize((max(1, target_w_px), max(1, target_h_px)), Image.Resampling.BILINEAR)

    tile_arr = np.array(pil_tile, dtype=np.uint8)
    return tile_arr, icc_applied
