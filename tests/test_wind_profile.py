import pytest

from odu_cfd.climate.profile import TERRAIN_ALPHA, wind_speed_at


def test_speed_at_reference_height_equals_reference_speed():
    assert wind_speed_at(10.0, 2.6, 10.0, "III") == pytest.approx(2.6)


def test_power_law_above_reference():
    expected = 2.6 * (40.0 / 10.0) ** TERRAIN_ALPHA["III"]
    assert wind_speed_at(40.0, 2.6, 10.0, "III") == pytest.approx(expected)


def test_rougher_terrain_has_steeper_profile():
    smooth = wind_speed_at(60.0, 2.0, 10.0, "I")
    rough = wind_speed_at(60.0, 2.0, 10.0, "V")
    assert rough > smooth


def test_speed_increases_with_height():
    assert wind_speed_at(60.0, 2.0, 10.0, "III") > wind_speed_at(20.0, 2.0, 10.0, "III")


def test_calm_stays_calm():
    assert wind_speed_at(60.0, 0.0, 10.0, "III") == 0.0


@pytest.mark.parametrize("z", [0.0, -5.0])
def test_non_positive_height_rejected(z):
    with pytest.raises(ValueError):
        wind_speed_at(z, 2.0, 10.0, "III")


def test_unknown_category_rejected():
    with pytest.raises(ValueError):
        wind_speed_at(10.0, 2.0, 10.0, "IX")


@pytest.mark.parametrize("args", [
    (float("nan"), 2.0, 10.0), (float("inf"), 2.0, 10.0),
    (10.0, float("nan"), 10.0), (10.0, float("inf"), 10.0),
    (10.0, 2.0, float("nan")), (10.0, 2.0, float("inf")),
])
def test_non_finite_inputs_rejected(args):
    with pytest.raises(ValueError):
        wind_speed_at(*args, "III")
