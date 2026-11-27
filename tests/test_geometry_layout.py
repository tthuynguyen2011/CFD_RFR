"""Dựng 3D theo phương án bố trí (giai đoạn 2c, Task 6) trên bản vẽ tổng hợp."""

import json
import re
import struct

import pytest
import yaml

from odu_cfd.cli import main
from odu_cfd.layout.io import layout_path, write_layout
from odu_cfd.layout.model import Layout, OduPlacement

ODUS = (
    OduPlacement("ODU-01", 6.0, 1.0, 180.0),
    OduPlacement("ODU-02", 7.5, 1.0, 180.0),
    OduPlacement("ODU-03", 21.0, 1.0, 180.0),
    OduPlacement("ODU-04", 22.5, 1.0, 180.0),
)


@pytest.fixture
def project(tmp_path, tower_dxf):
    p = tmp_path / "du-an"
    assert main(["init", str(p)]) == 0
    assert main(["ingest", str(p), str(tower_dxf)]) == 0
    assert main(["ingest", str(p), "--confirm"]) == 0
    assert main(["geometry", str(p)]) == 0
    return p


def _save(project, name, odus=ODUS, floors=(4, 5, 6), source="manual", description="thử"):
    write_layout(layout_path(project, name), Layout(name, description, source, floors, tuple(odus)))


def _out(project, name):
    return project / "input" / "geometry" / "layouts" / name


def _names(path):
    return re.findall(r"^solid (\S+)", path.read_text(encoding="ascii"), re.M)


def _glb_json(path):
    data = path.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + n].decode("utf-8"))


def _library(tmp_path, project, models):
    data = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    data["odu"]["model_id"] = models[0]["model_id"]
    (project / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    entries = []
    for m in models:
        entries.append(
            {"vendor": "T", "airflow_m3_h": 6000, "cooling_kw": 10, "compressor_kw": 3, "intake_limit_c": 46,
             "source": "thử", **m}
        )
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": entries}, allow_unicode=True), encoding="utf-8")
    return lib


def test_geometry_with_layout_writes_self_contained_folder(project, capsys):
    _save(project, "KT1")
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    out = _out(project, "KT1")
    for f in ("building.stl", "balcony.stl", "rail.stl", "odu.stl", "scene.glb", "geometry.json", "viewer.html"):
        assert (out / f).is_file(), f
    names = _names(out / "odu.stl")
    assert len(names) == 4 * 3
    assert "ODU-01_f03" in names and "ODU-04_f05" in names and "ODU-01_f00" not in names
    info = json.loads((out / "geometry.json").read_text(encoding="utf-8"))
    assert all(p["closed"] for p in info["parts"].values())
    assert info["parts"]["odu"]["regions"] == 12
    lay = info["layout"]
    assert lay["name"] == "KT1" and lay["source"] == "manual" and lay["description"] == "thử"
    assert lay["floors"] == "4-6"
    assert [o["id"] for o in lay["odus"]] == ["ODU-01", "ODU-02", "ODU-03", "ODU-04"]
    o = lay["odus"][0]
    assert o["x"] == 6.0 and o["y"] == 1.0 and o["rotation_deg"] == 180.0
    assert o["front_angle_deg"] == pytest.approx(270.0)
    assert o["size"] == [1.0, 0.4] and o["size_source"] == "default"
    assert o["floors"] == [4, 5, 6] and o["model_id"] is None
    # kết quả phẳng của lần `geometry` không phương án vẫn nguyên (4 dàn x 19 tầng)
    assert len(_names(project / "input/geometry/odu.stl")) == 4 * 19


def test_layout_odu_z_uses_floor_level_minus_one(project):
    _save(project, "KT1", odus=[ODUS[0]], floors=(2,))
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    path = _out(project, "KT1") / "odu.stl"
    assert _names(path) == ["ODU-01_f01"]
    zs = sorted({float(m) for m in re.findall(r"vertex \S+ \S+ (\S+)", path.read_text(encoding="ascii"))})
    assert zs == pytest.approx([3.3 + 0.15, 3.3 + 0.15 + 1.0])


def test_per_odu_floors_override(project):
    odus = [OduPlacement("ODU-01", 6.0, 1.0, 180.0, floors=(1, 19)), ODUS[1]]
    _save(project, "KT1", odus=odus, floors=(5,))
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    names = _names(_out(project, "KT1") / "odu.stl")
    assert sorted(names) == ["ODU-01_f00", "ODU-01_f18", "ODU-02_f04"]


def test_invalid_layout_exit_2_and_nothing_written(project, capsys):
    bad = ODUS + (OduPlacement("ODU-09", 15.0, 10.0, 0.0),)
    _save(project, "XAU", odus=bad)
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "XAU"]) == 2
    err = capsys.readouterr().err
    assert "ODU-09" in err and "ngoài ban công" in err
    assert not _out(project, "XAU").exists()
    assert not (project / "input/geometry/layouts").exists()


def test_all_errors_are_listed(project, capsys):
    bad = (OduPlacement("ODU-01", 15.0, 10.0, 0.0), OduPlacement("ODU-02", 16.0, 10.0, 0.0))
    _save(project, "XAU", odus=bad)
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "XAU"]) == 2
    err = capsys.readouterr().err
    assert "ODU-01" in err and "ODU-02" in err


def test_floors_beyond_building_block_build(project, capsys):
    _save(project, "KT1", floors=(18, 19, 20))
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "KT1"]) == 2
    assert "tầng 20" in capsys.readouterr().err
    assert not _out(project, "KT1").exists()


def test_denied_balcony_blocks_build(project, capsys):
    assert main(["layout", "balconies", str(project), "--deny", "B01"]) == 0
    _save(project, "KT1")
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "KT1"]) == 2
    assert "không cho phép" in capsys.readouterr().err


def test_unknown_layout_lists_existing(project, capsys):
    _save(project, "KT1")
    _save(project, "KT2")
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "KT9"]) == 2
    err = capsys.readouterr().err
    assert "KT9" in err and "KT1" in err and "KT2" in err


def test_bad_layout_name_is_error(project, capsys):
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "../x"]) == 2
    assert "không hợp lệ" in capsys.readouterr().err


def test_two_layouts_make_two_folders_with_different_stl(project):
    _save(project, "KT1")
    _save(project, "KT2", odus=ODUS[:2], floors=(4,))
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    assert main(["geometry", str(project), "--layout", "KT2"]) == 0
    a = (_out(project, "KT1") / "odu.stl").read_bytes()
    b = (_out(project, "KT2") / "odu.stl").read_bytes()
    assert a != b
    assert len(_names(_out(project, "KT1") / "odu.stl")) == 12
    assert len(_names(_out(project, "KT2") / "odu.stl")) == 2
    assert (_out(project, "KT1") / "building.stl").read_bytes() == (_out(project, "KT2") / "building.stl").read_bytes()


def test_empty_layout_builds_empty_odu(project):
    _save(project, "TRONG", odus=[])
    assert main(["geometry", str(project), "--layout", "TRONG"]) == 0
    info = json.loads((_out(project, "TRONG") / "geometry.json").read_text(encoding="utf-8"))
    assert info["parts"]["odu"]["regions"] == 0 and info["layout"]["odus"] == []


def test_library_size_and_height_per_model(tmp_path, project):
    lib = _library(
        tmp_path,
        project,
        [
            {"model_id": "nho", "width_m": 0.9, "depth_m": 0.35, "height_m": 0.8},
            {"model_id": "lon", "width_m": 1.2, "depth_m": 0.5, "height_m": 1.5},
        ],
    )
    odus = [
        OduPlacement("ODU-01", 6.0, 1.0, 180.0),  # model của dự án = nho
        OduPlacement("ODU-02", 7.8, 1.0, 180.0, model_id="lon"),
        OduPlacement("ODU-03", 21.0, 1.0, 180.0, size=(0.6, 0.3)),  # size riêng, chiều cao theo model dự án
        OduPlacement("ODU-04", 23.0, 1.0, 180.0, model_id="khong-co"),  # thiếu trong thư viện: mặc định + cảnh báo
    ]
    _save(project, "KT1", odus=odus, floors=(1,))
    assert main(["geometry", str(project), "--layout", "KT1", "--library", str(lib)]) == 0
    info = json.loads((_out(project, "KT1") / "geometry.json").read_text(encoding="utf-8"))
    by = {o["id"]: o for o in info["layout"]["odus"]}
    assert by["ODU-01"]["size"] == [0.9, 0.35] and by["ODU-01"]["size_source"] == "library"
    assert by["ODU-02"]["size"] == [1.2, 0.5] and by["ODU-02"]["model_id"] == "lon"
    assert by["ODU-03"]["size"] == [0.6, 0.3] and by["ODU-03"]["size_source"] == "layout"
    assert by["ODU-04"]["size"] == [1.0, 0.4] and by["ODU-04"]["size_source"] == "default"
    assert any("khong-co" in w for w in info["warnings"])
    text = (_out(project, "KT1") / "odu.stl").read_text(encoding="ascii")
    blocks = dict(re.findall(r"solid (\S+)\n(.*?)endsolid", text, re.S))

    def top(name):
        return max(float(m) for m in re.findall(r"vertex \S+ \S+ (\S+)", blocks[name]))

    assert top("ODU-01_f00") == pytest.approx(0.15 + 0.8)
    assert top("ODU-02_f00") == pytest.approx(0.15 + 1.5)
    assert top("ODU-03_f00") == pytest.approx(0.15 + 0.8)
    assert top("ODU-04_f00") == pytest.approx(0.15 + 1.0)


def test_library_height_too_tall_blocks_layout(tmp_path, project, capsys):
    lib = _library(tmp_path, project, [{"model_id": "cao", "width_m": 0.9, "depth_m": 0.35, "height_m": 3.4}])
    _save(project, "KT1")
    capsys.readouterr()
    assert main(["geometry", str(project), "--layout", "KT1", "--library", str(lib)]) == 2
    assert "tầng" in capsys.readouterr().err
    assert not _out(project, "KT1").exists()


def test_plan_json_schema_and_balcony_ids_match_yaml(project):
    g = project / "input" / "geometry"
    plan = json.loads((g / "plan.json").read_text(encoding="utf-8"))
    assert plan["version"] == 1 and plan["units"] == "m"
    assert plan["num_floors"] == 19 and plan["floor_height_m"] == 3.3
    assert plan["slab_thickness_m"] == 0.15 and plan["rail_height_m"] == 1.1
    assert plan["origin_xy_m"] == pytest.approx([15.0, 10.0])
    assert len(plan["envelope"]) == 1
    ext = plan["envelope"][0]["exterior"]
    assert ext[0] != ext[-1] and len(ext) == 4 and plan["envelope"][0]["holes"] == []
    assert len(plan["balconies"]) == 2
    ids = [b["id"] for b in plan["balconies"]]
    assert ids == ["B01", "B02"]
    for b in plan["balconies"]:
        assert b["polygon"][0] != b["polygon"][-1]
        assert b["area_m2"] == pytest.approx(8.0) and b["allowed"] is True
    assert len(plan["rails"]) == 2 and all(len(r) >= 2 for r in plan["rails"])
    ydoc = yaml.safe_load((project / "balconies.yaml").read_text(encoding="utf-8"))
    assert [b["id"] for b in ydoc["balconies"]] == ids


def test_plan_json_follows_allowed_flag_and_rerun_keeps_it(project):
    assert main(["layout", "balconies", str(project), "--deny", "B02"]) == 0
    assert main(["geometry", str(project)]) == 0
    plan = json.loads((project / "input/geometry/plan.json").read_text(encoding="utf-8"))
    assert {b["id"]: b["allowed"] for b in plan["balconies"]} == {"B01": True, "B02": False}


def test_base_glb_has_no_odu_nodes(project):
    gl = _glb_json(project / "input/geometry/base.glb")
    assert {n["extras"]["group"] for n in gl["nodes"]} == {"building", "balcony", "rail"}
    full = _glb_json(project / "input/geometry/scene.glb")
    assert "odu" in {n["extras"]["group"] for n in full["nodes"]}


def test_base_glb_has_no_odu_even_after_layout_build(project):
    _save(project, "KT1")
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    gl = _glb_json(project / "input/geometry/base.glb")
    assert "odu" not in {n["extras"]["group"] for n in gl["nodes"]}
    sc = _glb_json(_out(project, "KT1") / "scene.glb")
    assert sum(1 for n in sc["nodes"] if n["extras"]["group"] == "odu") == 12


def test_plan_to_dict_handles_holes_and_multipolygon():
    from shapely.geometry import LineString, MultiPolygon, Polygon

    from odu_cfd.geometry.pipeline import plan_to_dict
    from odu_cfd.geometry.plan2d import Plan2D
    from odu_cfd.layout.balconies import BalconyInfo
    from odu_cfd.schema import BuildingConfig, GeometryConfig

    a = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(2, 2), (4, 2), (4, 4), (2, 4)]])
    b = Polygon([(20, 0), (25, 0), (25, 5), (20, 5)])
    plan = Plan2D(MultiPolygon([a, b]), (), (LineString([(0, 0), (1, 0), (1, 1)]),), ())
    infos = [BalconyInfo("B1", Polygon([(0, 0), (1, 0), (1, 1)]), False)]
    d = plan_to_dict(plan, BuildingConfig(3, 3.0), GeometryConfig(), infos)
    assert len(d["envelope"]) == 2
    first = next(e for e in d["envelope"] if e["holes"])
    assert len(first["holes"]) == 1 and len(first["holes"][0]) == 4
    assert all(p[0] != p[-1] for e in d["envelope"] for p in [e["exterior"], *e["holes"]])
    assert d["rails"] == [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]]
    assert d["balconies"][0]["allowed"] is False and d["balconies"][0]["id"] == "B1"
    json.dumps(d)


def test_view_with_layout(project, capsys):
    _save(project, "KT1")
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    capsys.readouterr()
    assert main(["view", str(project), "--layout", "KT1", "--no-open"]) == 0
    out = capsys.readouterr().out
    assert "KT1" in out and "viewer.html" in out


def test_view_missing_layout_message_names_command(project, capsys):
    _save(project, "KT1")
    capsys.readouterr()
    assert main(["view", str(project), "--layout", "KT1", "--no-open"]) == 2
    err = capsys.readouterr().err
    assert "geometry" in err and "--layout KT1" in err


def test_layout_run_rewrites_balconies_and_plan(project):
    _save(project, "KT1")
    (project / "balconies.yaml").unlink()
    (project / "input/geometry/plan.json").unlink()
    assert main(["geometry", str(project), "--layout", "KT1"]) == 0
    assert (project / "balconies.yaml").is_file()
    assert (project / "input/geometry/plan.json").is_file()
