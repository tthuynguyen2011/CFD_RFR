import pytest

from odu_cfd.errors import ConfigError, IngestError
from odu_cfd.schema import parse_project


def test_ingest_error_is_config_error():
    assert issubclass(IngestError, ConfigError)


def test_geometry_section_is_optional_with_defaults(valid_dict):
    g = parse_project(valid_dict).geometry
    assert (g.slab_thickness_m, g.rail_height_m, g.rail_thickness_m, g.odu_default_height_m) == (
        0.15,
        1.1,
        0.05,
        1.0,
    )


def test_geometry_overrides_only_given_keys(valid_dict):
    valid_dict["geometry"] = {"rail_height_m": 1.2}
    g = parse_project(valid_dict).geometry
    assert g.rail_height_m == 1.2
    assert g.slab_thickness_m == 0.15


@pytest.mark.parametrize(
    "key,val",
    [
        ("slab_thickness_m", 0),
        ("rail_height_m", -1),
        ("rail_thickness_m", "x"),
        ("odu_default_height_m", float("nan")),
    ],
)
def test_geometry_rejects_bad_values(valid_dict, key, val):
    valid_dict["geometry"] = {key: val}
    with pytest.raises(ConfigError, match=f"geometry.{key}"):
        parse_project(valid_dict)


@pytest.mark.parametrize(
    "key,val",
    [
        ("slab_thickness_m", 1.5),
        ("rail_height_m", 3.5),
        ("rail_thickness_m", 0.6),
        ("odu_default_height_m", 6.0),
    ],
)
def test_geometry_rejects_values_above_upper_bound(valid_dict, key, val):
    valid_dict["geometry"] = {key: val}
    with pytest.raises(ConfigError, match=f"geometry.{key}"):
        parse_project(valid_dict)


@pytest.mark.parametrize(
    "key,val",
    [("slab_thickness_m", 1), ("rail_height_m", 3), ("rail_thickness_m", 0.5), ("odu_default_height_m", 5)],
)
def test_geometry_accepts_upper_bound_itself(valid_dict, key, val):
    valid_dict["geometry"] = {key: val}
    assert getattr(parse_project(valid_dict).geometry, key) == val


def test_odu_default_size_defaults(valid_dict):
    g = parse_project(valid_dict).geometry
    assert (g.odu_default_width_m, g.odu_default_depth_m) == (1.0, 0.4)


def test_odu_default_size_override(valid_dict):
    valid_dict["geometry"] = {"odu_default_width_m": 0.98, "odu_default_depth_m": 0.37}
    g = parse_project(valid_dict).geometry
    assert (g.odu_default_width_m, g.odu_default_depth_m) == (0.98, 0.37)


@pytest.mark.parametrize("key", ["odu_default_width_m", "odu_default_depth_m"])
@pytest.mark.parametrize("val", [0, -1, float("nan"), 6, "x", True])
def test_odu_default_size_rejects_bad(valid_dict, key, val):
    valid_dict["geometry"] = {key: val}
    with pytest.raises(ConfigError, match=f"geometry.{key}"):
        parse_project(valid_dict)


@pytest.mark.parametrize("key", ["odu_default_width_m", "odu_default_depth_m"])
def test_odu_default_size_accepts_upper_bound(valid_dict, key):
    valid_dict["geometry"] = {key: 5}
    assert getattr(parse_project(valid_dict).geometry, key) == 5
