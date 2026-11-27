import json
import re

import pytest

from odu_cfd.cli import main


@pytest.fixture
def project(tmp_path, tower_dxf):
    p = tmp_path / "du-an"
    assert main(["init", str(p)]) == 0
    assert main(["ingest", str(p), str(tower_dxf)]) == 0
    return p


def test_geometry_refuses_unconfirmed(project, capsys):
    assert main(["geometry", str(project)]) == 2
    err = capsys.readouterr().err
    assert "chưa xác nhận" in err and "--confirm" in err


def test_end_to_end(project, capsys):
    assert main(["ingest", str(project), "--confirm"]) == 0
    assert main(["geometry", str(project)]) == 0
    g = project / "input" / "geometry"
    for name in ("building.stl", "balcony.stl", "rail.stl", "odu.stl", "scene.glb", "geometry.json", "viewer.html",
                 "plan.json", "base.glb"):
        assert (g / name).is_file(), name
    assert (project / "balconies.yaml").is_file()
    info = json.loads((g / "geometry.json").read_text(encoding="utf-8"))
    assert info["num_floors"] == 19
    assert info["parts"]["odu"]["regions"] == 4 * 19
    assert info["parts"]["building"]["volume_m3"] == pytest.approx((600 - 16) * 19 * 3.3)
    assert all(p["closed"] for p in info["parts"].values())
    assert info["warnings"] == []
    names = re.findall(r"^solid (\S+)", (g / "odu.stl").read_text(encoding="ascii"), re.M)
    assert "ODU-01_f00" in names and "ODU-04_f18" in names and len(names) == 76


def test_view_prints_path_without_opening(project, capsys):
    main(["ingest", str(project), "--confirm"])
    main(["geometry", str(project)])
    capsys.readouterr()
    assert main(["view", str(project), "--no-open"]) == 0
    assert "viewer.html" in capsys.readouterr().out


def test_view_before_geometry_is_an_error(project, capsys):
    assert main(["view", str(project), "--no-open"]) == 2
    assert "geometry" in capsys.readouterr().err


# ---- I2/I6/I1/m4 ở mức pipeline ----
import yaml


def _confirm(project):
    assert main(["ingest", str(project), "--confirm"]) == 0


def _edit_yaml(project, fn):
    y = project / "input" / "ingest.yaml"
    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    fn(data)
    y.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _library(tmp_path, project, height=0.8, w=0.9, d=0.35):
    data = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    data["odu"]["model_id"] = "test-odu"
    (project / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    entry = {
        "model_id": "test-odu", "vendor": "TestCo", "width_m": w, "depth_m": d, "height_m": height,
        "airflow_m3_h": 6000, "cooling_kw": 10, "compressor_kw": 3, "intake_limit_c": 46,
        "source": "dữ liệu thử",
    }
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": [entry]}, allow_unicode=True), encoding="utf-8")
    return lib


def test_geometry_json_has_size_source_origin_and_note(project):
    _confirm(project)
    assert main(["geometry", str(project)]) == 0
    info = json.loads((project / "input/geometry/geometry.json").read_text(encoding="utf-8"))
    assert all(o["size_source"] == "drawing" for o in info["odus"])
    assert info["origin_xy_m"] == pytest.approx([15.0, 10.0])
    assert "coordinate_note" in info


def test_library_overrides_odu_footprint(tmp_path, project):
    _confirm(project)
    lib = _library(tmp_path, project, w=0.9, d=0.35)
    assert main(["geometry", str(project), "--library", str(lib)]) == 0
    info = json.loads((project / "input/geometry/geometry.json").read_text(encoding="utf-8"))
    assert all(o["size_source"] == "library" and o["size"] == [0.9, 0.35] for o in info["odus"])
    assert all(o["size_drawing"] for o in info["odus"])


def test_library_height_too_tall_is_error(tmp_path, project, capsys):
    _confirm(project)
    lib = _library(tmp_path, project, height=3.4)
    assert main(["geometry", str(project), "--library", str(lib)]) == 2
    assert "tầng" in capsys.readouterr().err
    assert not (project / "input/geometry/odu.stl").exists()


def test_geometry_without_odus_warns_and_writes_empty_odu(project, capsys):
    # giai đoạn 2c: ingest.yaml không còn bắt buộc có dàn nóng; geometry cảnh báo và hướng dẫn tạo phương án
    _confirm(project)
    _edit_yaml(project, lambda d: d.update(odus=[]))
    capsys.readouterr()
    assert main(["geometry", str(project)]) == 0
    err = capsys.readouterr().err
    assert "chưa có dàn nóng" in err and "layout" in err
    info = json.loads((project / "input/geometry/geometry.json").read_text(encoding="utf-8"))
    assert info["parts"]["odu"]["regions"] == 0
    assert (project / "input/geometry/odu.stl").is_file()
    assert (project / "input/geometry/plan.json").is_file()


def test_geometry_rejects_missing_envelope_role(project, capsys):
    _confirm(project)
    _edit_yaml(project, lambda d: d.update(layers={k: v for k, v in d["layers"].items() if v not in ("wall_ext", "slab")}))
    assert main(["geometry", str(project)]) == 2
    assert "wall_ext" in capsys.readouterr().err


def test_geometry_rejects_duplicate_ids(project, capsys):
    _confirm(project)

    def dup(d):
        for o in d["odus"]:
            o["id"] = "ODU-01"

    _edit_yaml(project, dup)
    assert main(["geometry", str(project)]) == 2
    assert "trùng" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["../outside.dxf", "C:/outside.dxf"])
def test_geometry_rejects_source_outside_input(project, capsys, bad):
    _confirm(project)
    _edit_yaml(project, lambda d: d.update(source_file=bad))
    assert main(["geometry", str(project)]) == 2
    assert "source_file" in capsys.readouterr().err


def test_geometry_rejects_huge_odu(project, capsys):
    _confirm(project)

    def big(d):
        d["odus"][0]["size"] = [500.0, 0.5]

    _edit_yaml(project, big)
    assert main(["geometry", str(project)]) == 2
    assert "size" in capsys.readouterr().err


def test_unclosed_mesh_writes_no_stl(project, capsys, monkeypatch):
    import odu_cfd.geometry.build as bld

    _confirm(project)
    monkeypatch.setattr(bld, "is_closed", lambda mesh: False)
    assert main(["geometry", str(project)]) == 2
    assert "không kín" in capsys.readouterr().err
    assert not (project / "input/geometry/building.stl").exists()


def test_colliding_stl_region_names_are_error(tmp_path):
    from odu_cfd.errors import IngestError
    from odu_cfd.geometry.export import write_stl
    from odu_cfd.geometry.mesh import box

    m = box(0, 0, 1, 1, 0, 0, 1)
    with pytest.raises(IngestError, match="trùng"):
        write_stl(tmp_path / "a.stl", {"ODU 01": m, "ODU_01": m})
