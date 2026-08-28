"""
Pure coordinate conversion functions between base-level micrometers (um)
and level-N pixel coordinates.

Rule (from PRD §5.1):
All persisted geometry is in base-level micrometers, origin top-left of level 0.
"""

def um_to_px(um: float, mpp: float, downsample: float = 1.0) -> int:
    """
    Convert micrometer coordinate to pixel index at a given downsample factor.

    :param um: Coordinate in micrometers from origin (0, 0)
    :param mpp: Micrometers per pixel at native level 0 (e.g., 0.25 um/px)
    :param downsample: Downsample ratio relative to level 0 (1.0 = level 0, 4.0 = level 2, etc.)
    :return: Pixel index (rounded int)
    """
    if mpp <= 0:
        raise ValueError(f"MPP must be positive, got {mpp}")
    if downsample <= 0:
        raise ValueError(f"Downsample must be positive, got {downsample}")
    
    px_level0 = um / mpp
    px_level_n = px_level0 / downsample
    return int(round(px_level_n))


def px_to_um(px: int | float, mpp: float, downsample: float = 1.0) -> float:
    """
    Convert pixel coordinate at a given downsample factor to micrometer coordinate at level 0.

    :param px: Pixel coordinate at level N
    :param mpp: Micrometers per pixel at native level 0
    :param downsample: Downsample ratio relative to level 0
    :return: Micrometer coordinate (float)
    """
    if mpp <= 0:
        raise ValueError(f"MPP must be positive, got {mpp}")
    if downsample <= 0:
        raise ValueError(f"Downsample must be positive, got {downsample}")
    
    px_level0 = px * downsample
    return px_level0 * mpp


def level_downsample_for_mpp(target_mpp: float, native_mpp: float) -> float:
    """
    Calculate downsample factor required to achieve target MPP from native MPP.
    """
    if native_mpp <= 0 or target_mpp <= 0:
        raise ValueError("MPP values must be positive")
    return target_mpp / native_mpp
