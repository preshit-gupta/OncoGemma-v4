import pytest
from pipeline.coords import um_to_px, px_to_um, level_downsample_for_mpp

def test_um_to_px_roundtrip():
    mpp_values = [0.25, 0.50, 1.0]
    test_ums = [0.0, 100.0, 256.5, 1024.0, 50000.0]

    for mpp in mpp_values:
        for um in test_ums:
            px = um_to_px(um, mpp, downsample=1.0)
            recovered_um = px_to_um(px, mpp, downsample=1.0)
            # Within 1 pixel accuracy tolerance (mpp / 2)
            assert abs(recovered_um - um) <= (mpp / 2.0) + 1e-5

def test_downsample_scaling():
    # Level 0 @ 0.25 um/px -> Level 2 @ 1.0 um/px (4x downsample)
    mpp_native = 0.25
    mpp_target = 1.0
    ds = level_downsample_for_mpp(mpp_target, mpp_native)
    assert ds == 4.0

    um = 100.0
    px_level0 = um_to_px(um, mpp_native, downsample=1.0) # 400 px
    px_level2 = um_to_px(um, mpp_native, downsample=ds)   # 100 px

    assert px_level0 == 400
    assert px_level2 == 100

def test_invalid_arguments():
    with pytest.raises(ValueError):
        um_to_px(100.0, mpp=0.0)
    with pytest.raises(ValueError):
        px_to_um(100, mpp=-0.5)
