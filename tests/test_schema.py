import pytest
import yaml

from odu_cfd.errors import ConfigError
from odu_cfd.schema import load_project, parse_project


def test_parse_valid_project(valid_dict):
    p = parse_project(valid_dict)
    assert p.name == "demo"
    assert p.climate.design_temp_c == 36.8
    assert p.climate.wind.speeds_ms == (0.0, 2.6)
    assert p.climate.wind.directions_deg == (0.0, 90.0, 180.0, 270.0)
    assert p.climate.wind.terrain_category == "III"
    assert p.building.num_floors == 19
    assert p.odu.model_id == "test-odu"
    assert p.odu.simultaneity_fraction == 0.8
    assert p.compute.backend == "local"
    assert p.compute.confidence == "screening"


def test_load_project_from_file(tmp_path, valid_dict):
    f = tmp_path / "project.yaml"
    f.write_text(yaml.safe_dump(valid_dict, allow_unicode=True), encoding="utf-8")
    assert load_project(f).name == "demo"


def test_load_project_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="không tìm thấy"):
        load_project(tmp_path / "nope.yaml")


def test_load_project_bad_yaml(tmp_path):
    f = tmp_path / "project.yaml"
    f.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_project(f)


def _set(d, path, value):
    for key in path[:-1]:
        d = d[key]
    d[path[-1]] = value


def _del(d, path):
    for key in path[:-1]:
        d = d[key]
    del d[path[-1]]


@pytest.mark.parametrize(
    "path,value,fragment",
    [
        (("climate", "design_temp_c"), 90, "climate.design_temp_c"),
        (("climate", "design_temp_c"), "nóng", "climate.design_temp_c"),
        (("climate", "wind", "speeds_ms"), [], "climate.wind.speeds_ms"),
        (("climate", "wind", "speeds_ms"), [-1], "climate.wind.speeds_ms"),
        (("climate", "wind", "directions_deg"), [360], "climate.wind.directions_deg"),
        (("climate", "wind", "terrain_category"), "IX", "climate.wind.terrain_category"),
        (("building", "num_floors"), 0, "building.num_floors"),
        (("building", "num_floors"), 2.5, "building.num_floors"),
        (("building", "floor_height_m"), 10, "building.floor_height_m"),
        (("odu", "load_fraction"), 0, "odu.load_fraction"),
        (("odu", "simultaneity_fraction"), 1.2, "odu.simultaneity_fraction"),
        (("odu", "louver_open_fraction"), True, "odu.louver_open_fraction"),
        (("compute", "backend"), "gpu", "compute.backend"),
        (("compute", "cores"), 0, "compute.cores"),
        (("compute", "confidence"), "maybe", "compute.confidence"),
    ],
)
def test_invalid_value_names_the_field(valid_dict, path, value, fragment):
    _set(valid_dict, path, value)
    with pytest.raises(ConfigError, match=fragment):
        parse_project(valid_dict)


@pytest.mark.parametrize(
    "path",
    [
        ("project", "name"),
        ("climate", "design_temp_c"),
        ("climate", "wind", "terrain_category"),
        ("building", "floor_height_m"),
        ("odu", "model_id"),
        ("compute", "backend"),
    ],
)
def test_missing_field_is_reported(valid_dict, path):
    _del(valid_dict, path)
    with pytest.raises(ConfigError, match="thiếu") as exc:
        parse_project(valid_dict)
    assert ".".join(path) in str(exc.value)


def test_top_level_must_be_mapping():
    with pytest.raises(ConfigError, match="thiếu"):
        parse_project([1, 2, 3])


# ---- review fixes ----
def _mut(valid_dict, path, value):
    d = valid_dict
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value
    return valid_dict


@pytest.mark.parametrize("path,value", [
    (("climate", "design_temp_c"), float("nan")),
    (("climate", "design_temp_c"), float("inf")),
    (("odu", "load_fraction"), float("nan")),
    (("climate", "wind", "ref_height_m"), float("inf")),
    (("climate", "wind", "speeds_ms"), [float("nan")]),
    (("climate", "wind", "speeds_ms"), [float("inf")]),
])
def test_non_finite_rejected(valid_dict, path, value):
    with pytest.raises(ConfigError):
        parse_project(_mut(valid_dict, path, value))


def test_non_finite_from_yaml(tmp_path, valid_dict):
    f = tmp_path / "project.yaml"
    text = yaml.safe_dump(valid_dict, allow_unicode=True).replace("design_temp_c: 36.8", "design_temp_c: .nan")
    f.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="design_temp_c"):
        load_project(f)


@pytest.mark.parametrize("speeds", [[2.6, 2.60], [0, 0.0], [-0.0, 0], [1, 2, 1]])
def test_duplicate_speeds_rejected(valid_dict, speeds):
    with pytest.raises(ConfigError, match="speeds_ms"):
        parse_project(_mut(valid_dict, ("climate", "wind", "speeds_ms"), speeds))


def test_duplicate_directions_rejected(valid_dict):
    with pytest.raises(ConfigError, match="directions_deg"):
        parse_project(_mut(valid_dict, ("climate", "wind", "directions_deg"), [90, 90]))


def test_fractional_direction_rejected(valid_dict):
    with pytest.raises(ConfigError, match="directions_deg"):
        parse_project(_mut(valid_dict, ("climate", "wind", "directions_deg"), [0, 0.5]))


def test_whole_float_direction_accepted(valid_dict):
    p = parse_project(_mut(valid_dict, ("climate", "wind", "directions_deg"), [0, 90.0]))
    assert p.climate.wind.directions_deg == (0.0, 90.0)


@pytest.mark.parametrize("desc", [None, ""])
def test_null_or_empty_description_becomes_empty(valid_dict, desc):
    valid_dict["project"]["description"] = desc
    assert parse_project(valid_dict).description == ""


def test_non_utf8_project_file(tmp_path):
    f = tmp_path / "project.yaml"
    f.write_bytes("project:\n  name: Đà\n".encode("cp1258"))
    with pytest.raises(ConfigError, match="UTF-8"):
        load_project(f)
