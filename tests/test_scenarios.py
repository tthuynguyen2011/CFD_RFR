from odu_cfd.climate import build_scenarios
from odu_cfd.schema import WindConfig


def _wind(speeds, dirs):
    return WindConfig(
        ref_height_m=10.0,
        speeds_ms=tuple(float(s) for s in speeds),
        directions_deg=tuple(float(d) for d in dirs),
        terrain_category="III",
    )


def test_calm_is_a_single_transient_scenario():
    scenarios = build_scenarios(_wind([0, 2.6], [0, 90]))
    calm = [s for s in scenarios if s.wind_speed_ms == 0]
    assert len(calm) == 1
    assert calm[0].scenario_id == "calm"
    assert calm[0].transient is True


def test_wind_scenarios_cover_every_direction_and_are_steady():
    scenarios = build_scenarios(_wind([0, 2.6], [0, 90]))
    ids = [s.scenario_id for s in scenarios]
    assert ids == ["calm", "w2.6_d000", "w2.6_d090"]
    assert all(not s.transient for s in scenarios if s.wind_speed_ms > 0)


def test_count_is_calm_plus_speeds_times_directions():
    scenarios = build_scenarios(_wind([0, 1, 2.6], [0, 90, 180, 270]))
    assert len(scenarios) == 1 + 2 * 4


def test_without_calm_speed_no_calm_scenario():
    scenarios = build_scenarios(_wind([1.8], [45]))
    assert [s.scenario_id for s in scenarios] == ["w1.8_d045"]


def test_ids_are_unique():
    scenarios = build_scenarios(_wind([0, 1, 2], [0, 45, 90, 135]))
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids))


def test_colliding_ids_raise_config_error():
    import pytest
    from odu_cfd.errors import ConfigError
    with pytest.raises(ConfigError):
        build_scenarios(_wind([1.0000001, 1.0000002], [0]))
