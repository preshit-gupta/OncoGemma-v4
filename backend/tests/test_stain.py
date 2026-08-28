import os
import numpy as np
from PIL import Image
import pytest

from pipeline.stain import fit_macenko_stain, PureNumpyMacenkoNormalizer

def test_macenko_normalizer_fit_transform():
    """Verify MacenkoNormalizer fit and transform operations on synthetic patch."""
    ref_patch = np.full((256, 256, 3), (180, 50, 150), dtype=np.uint8) # Synthetic H&E
    src_patch = np.full((256, 256, 3), (200, 70, 180), dtype=np.uint8)

    normalizer = PureNumpyMacenkoNormalizer()
    normalizer.fit(ref_patch)

    assert normalizer.stain_matrix is not None
    assert normalizer.max_concentrations is not None

    transformed = normalizer.transform(src_patch)
    assert transformed.shape == src_patch.shape
    assert transformed.dtype == np.uint8

def test_stain_fit_determinism(tmp_path):
    """Verify deterministic stain params for identical checksums."""
    ref_path = tmp_path / "stain_ref.png"
    ref_img = Image.new("RGB", (256, 256), color=(180, 50, 150))
    ref_img.save(ref_path)

    synthetic_slide = Image.new("RGB", (1024, 1024), color=(200, 80, 160))

    norm1, params1, mask1 = fit_macenko_stain(
        synthetic_slide,
        checksum_sha256="abc123def456",
        ref_image_path=str(ref_path)
    )

    norm2, params2, mask2 = fit_macenko_stain(
        synthetic_slide,
        checksum_sha256="abc123def456",
        ref_image_path=str(ref_path)
    )

    assert params1["stain_matrix"] == params2["stain_matrix"]
    assert params1["max_concentrations"] == params2["max_concentrations"]
    assert np.array_equal(mask1, mask2)
