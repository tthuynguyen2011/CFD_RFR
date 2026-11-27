"""Lệnh CLI cho ban công và phương án bố trí (giai đoạn 2c, Task 7) trên bản vẽ tổng hợp."""

import sys
import types

import pytest

from odu_cfd.cli import PROJECT_SUBDIRS, main
from odu_cfd.layout.io import layout_path, list_layouts, read_layout, write_layout
from odu_cfd.layout.model import Layout, OduPlacement


@pytest.fixture
def raw_project(tmp_path, tower_dxf):
    p = tmp_path / "du-an"
    assert main(["init", str(p)]) == 0
    assert main(["ingest", str(p), str(tower_dxf)]) == 0
    assert main(["ingest", str(p), "--confirm"]) == 0
    return p


@pytest.fixture
def project(raw_project):
    assert main(["geometry", str(raw_project)]) == 0
    return raw_project


def _run(capsys, *argv):
    capsys.readouterr()
    code = main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_init_creates_layouts_dir(tmp_path):
    assert "layouts" in PROJECT_SUBDIRS
    assert main(["init", str(tmp_path / "x")]) == 0
    assert (tmp_path / "x" / "layouts").is_dir()


# ---- layout balconies ----
def test_balconies_lists_table(project, capsys):
    code, out, _ = _run(capsys, "layout", "balconies", project)
    assert code == 0
    assert "B01" in out and "B02" in out and "8.0" in out and "true" in out.lower()


def test_balconies_deny_and_allow(project, capsys):
    code, out, _ = _run(capsys, "layout", "balconies", project, "--deny", "B01")
    assert code == 0
    line = next(l for l in out.splitlines() if l.strip().startswith("B01"))
    assert "false" in line.lower()
    code, out, _ = _run(capsys, "layout", "balconies", project, "--allow", "B01", "--deny", "B02")
    line1 = next(l for l in out.splitlines() if l.strip().startswith("B01"))
    line2 = next(l for l in out.splitlines() if l.strip().startswith("B02"))
    assert "true" in line1.lower() and "false" in line2.lower()
    code, out, _ = _run(capsys, "layout", "balconies", project, "--allow-all")
    assert "false" not in out.lower()


def test_balconies_unknown_id(project, capsys):
    code, _, err = _run(capsys, "layout", "balconies", project, "--allow", "B99")
    assert code == 2 and "B99" in err and "B01" in err


def test_balconies_accepts_comma_list(project, capsys):
    code, out, _ = _run(capsys, "layout", "balconies", project, "--deny", "B01,B02")
    assert code == 0 and out.lower().count("false") == 2


def test_commands_before_geometry_tell_to_run_geometry(raw_project, capsys):
    for argv in (
        ["layout", "balconies", raw_project],
        ["layout", "auto", raw_project, "--name", "a", "--floors", "4"],
        ["layout", "validate", raw_project, "a"],
        ["layout", "new", raw_project, "--name", "a", "--floors", "4"],
    ):
        code, _, err = _run(capsys, *argv)
        assert code == 2 and "odu-cfd geometry" in err, argv


# ---- layout auto ----
def test_auto_writes_layout_and_builds(project, capsys):
    code, out, err = _run(capsys, "layout", "auto", project, "--name", "TD", "--floors", "4-6", "--count", "2",
                          "--description", "Tự động")
    assert code == 0, err
    lay = read_layout(layout_path(project, "TD"))
    assert lay.source == "rule" and lay.floors == (4, 5, 6) and lay.description == "Tự động"
    assert [o.odu_id for o in lay.odus] == ["ODU-01", "ODU-02", "ODU-03", "ODU-04"]
    assert all(o.size is None for o in lay.odus)  # không --size: kích thước theo thư viện/mặc định lúc dựng
    assert "4" in out and "TD" in out
    assert main(["geometry", str(project), "--layout", "TD"]) == 0


def test_auto_grid_and_options(project, capsys):
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "G", "--floors", "4", "--count", "4",
                        "--pattern", "grid", "--size", "0.98,0.37", "--balconies", "B01", "--wall-gap", "0.2",
                        "--spacing", "0.1", "--min-area", "1", "--facing", "0")
    assert code == 0, err
    lay = read_layout(layout_path(project, "G"))
    assert len(lay.odus) == 4 and all(o.size == (0.98, 0.37) for o in lay.odus)
    assert all(o.x < 10 for o in lay.odus)  # chỉ B01
    assert all(o.rotation_deg == pytest.approx(-90.0) for o in lay.odus)


def test_auto_refuses_overwrite_without_force(project, capsys):
    base = ["layout", "auto", project, "--name", "TD", "--floors", "4", "--count", "1"]
    assert _run(capsys, *base)[0] == 0
    first = layout_path(project, "TD").read_bytes()
    code, _, err = _run(capsys, *base, "--count", "2")
    assert code == 2 and "--force" in err
    assert layout_path(project, "TD").read_bytes() == first
    code, _, _ = _run(capsys, *base, "--count", "2", "--force")
    assert code == 0 and len(read_layout(layout_path(project, "TD")).odus) == 4
    assert layout_path(project, "TD").with_name("TD.yaml.bak").is_file()


def test_auto_warnings_are_printed(project, capsys):
    code, out, err = _run(capsys, "layout", "auto", project, "--name", "W", "--floors", "4", "--count", "9")
    assert code == 0
    assert "Cảnh báo" in err and "B01" in err


def test_auto_uses_library_size(tmp_path, project, capsys):
    import yaml

    data = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    data["odu"]["model_id"] = "m1"
    (project / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    lib = tmp_path / "lib"
    lib.mkdir()
    entry = {"model_id": "m1", "vendor": "T", "width_m": 0.9, "depth_m": 0.35, "height_m": 0.8, "airflow_m3_h": 6000,
             "cooling_kw": 10, "compressor_kw": 3, "intake_limit_c": 46, "source": "thử"}
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": [entry]}, allow_unicode=True), encoding="utf-8")
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "L", "--floors", "4", "--library", lib)
    assert code == 0, err
    assert read_layout(layout_path(project, "L")).odus[0].size is None  # chỉ dùng thư viện để xếp chỗ
    out_dir_ok = _run(capsys, "geometry", project, "--layout", "L", "--library", lib)[0]
    assert out_dir_ok == 0
    import json

    info = json.loads((project / "input" / "geometry" / "layouts" / "L" / "geometry.json").read_text(encoding="utf-8"))
    assert info["layout"]["odus"][0]["size"] == [0.9, 0.35] and info["layout"]["odus"][0]["size_source"] == "library"


@pytest.mark.parametrize(
    "extra",
    [
        ["--floors", "0"],
        ["--floors", "a"],
        ["--floors", "18-25"],  # vượt 19 tầng
        ["--floors", "4", "--size", "abc"],
        ["--floors", "4", "--size", "1"],
        ["--floors", "4", "--size", "0,1"],
        ["--floors", "4", "--facing", "huong"],
        ["--floors", "4", "--pattern", "hex"],
        ["--floors", "4", "--balconies", "B99"],
    ],
)
def test_auto_bad_arguments(project, capsys, extra):
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "X", *extra)
    assert code == 2 and "Lỗi" in err
    assert not layout_path(project, "X").exists()


def test_auto_bad_name(project, capsys):
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "a b", "--floors", "4")
    assert code == 2 and "không hợp lệ" in err


# ---- layout from-ingest ----
def test_from_ingest(project, capsys):
    code, out, err = _run(capsys, "layout", "from-ingest", project, "--name", "BV", "--floors", "4-19")
    assert code == 0, err
    lay = read_layout(layout_path(project, "BV"))
    assert lay.source == "drawing" and len(lay.odus) == 4 and lay.floors == tuple(range(4, 20))
    assert err == "" or "Cảnh báo" not in err
    assert main(["geometry", str(project), "--layout", "BV"]) == 0


def test_from_ingest_force_and_overwrite(project, capsys):
    base = ["layout", "from-ingest", project, "--name", "BV", "--floors", "4"]
    assert _run(capsys, *base)[0] == 0
    code, _, err = _run(capsys, *base)
    assert code == 2 and "--force" in err
    assert _run(capsys, *base, "--force")[0] == 0


def test_from_ingest_warns_for_denied_balcony(project, capsys):
    assert main(["layout", "balconies", str(project), "--deny", "B01"]) == 0
    code, _, err = _run(capsys, "layout", "from-ingest", project, "--name", "BV", "--floors", "4")
    assert code == 0 and "Cảnh báo" in err and "không cho phép" in err


def test_from_ingest_without_odus_gives_empty_layout_with_warning(project, capsys):
    import yaml

    y = project / "input" / "ingest.yaml"
    data = yaml.safe_load(y.read_text(encoding="utf-8"))
    data["odus"] = []
    y.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, out, err = _run(capsys, "layout", "from-ingest", project, "--name", "BV", "--floors", "4")
    assert code == 0
    assert read_layout(layout_path(project, "BV")).odus == ()


# ---- layout validate ----
def _save(project, name, odus, floors=(4, 5)):
    write_layout(layout_path(project, name), Layout(name, "", "manual", floors, tuple(odus)))


def test_validate_clean_returns_0(project, capsys):
    _save(project, "OK", [OduPlacement("ODU-01", 6.0, 1.0, 180.0)])
    code, out, _ = _run(capsys, "layout", "validate", project, "OK")
    assert code == 0 and "OK" in out


def test_validate_error_returns_2_and_lists_all(project, capsys):
    _save(project, "XAU", [OduPlacement("ODU-01", 15.0, 10.0, 0.0), OduPlacement("ODU-02", 6.0, 1.0, 0.0),
                           OduPlacement("ODU-03", 6.2, 1.0, 0.0)])
    code, out, err = _run(capsys, "layout", "validate", project, "XAU")
    text = out + err
    assert code == 2
    assert "ODU-01" in text and "ngoài ban công" in text and "chồng" in text


def test_validate_denied_balcony(project, capsys):
    main(["layout", "balconies", str(project), "--deny", "B02"])
    _save(project, "D", [OduPlacement("ODU-01", 21.0, 1.0, 180.0)])
    code, out, err = _run(capsys, "layout", "validate", project, "D")
    assert code == 2 and "không cho phép" in out + err


def test_validate_uses_library_size(tmp_path, project, capsys):
    # size riêng 1.9 x 0.4 đặt sát mép phải ban công B01 (x tới 9): hỏng khi dài hơn
    _save(project, "S", [OduPlacement("ODU-01", 8.6, 1.0, 0.0, size=(1.9, 0.4))])
    code, _, _ = _run(capsys, "layout", "validate", project, "S")
    assert code == 2


def test_validate_missing_layout_lists_existing(project, capsys):
    _save(project, "A1", [])
    code, _, err = _run(capsys, "layout", "validate", project, "ZZ")
    assert code == 2 and "ZZ" in err and "A1" in err


def test_validate_bad_name_cannot_escape(project, capsys):
    code, _, err = _run(capsys, "layout", "validate", project, "../x")
    assert code == 2 and "không hợp lệ" in err


# ---- layout list / new ----
def test_list_empty_and_filled(project, capsys):
    code, out, _ = _run(capsys, "layout", "list", project)
    assert code == 0 and "chưa có" in out.lower()
    _save(project, "B", [OduPlacement("ODU-01", 6.0, 1.0, 180.0)], floors=(4, 5, 6, 9))
    _save(project, "A", [])
    code, out, _ = _run(capsys, "layout", "list", project)
    lines = [l for l in out.splitlines() if l.strip()]
    assert code == 0
    ia = next(i for i, l in enumerate(lines) if l.split()[0] == "A")
    ib = next(i for i, l in enumerate(lines) if l.split()[0] == "B")
    assert ia < ib
    assert "manual" in lines[ib] and "1" in lines[ib] and "4-6,9" in lines[ib]


def test_list_reports_broken_layout_without_failing(project, capsys):
    _save(project, "A", [])
    layout_path(project, "BAD").write_text("name: BAD\n", encoding="utf-8")
    code, out, err = _run(capsys, "layout", "list", project)
    assert code == 0 and "BAD" in out + err and "A" in out


def test_new_creates_empty_manual_layout(project, capsys):
    code, out, err = _run(capsys, "layout", "new", project, "--name", "T1", "--floors", "4-19",
                          "--description", "Phương án trống")
    assert code == 0, err
    lay = read_layout(layout_path(project, "T1"))
    assert lay.source == "manual" and lay.odus == () and lay.description == "Phương án trống"
    assert lay.floors == tuple(range(4, 20))  # 22 > 19 tầng: phải bị chặn, xem test riêng


def test_new_floors_and_refuse_overwrite(project, capsys):
    assert _run(capsys, "layout", "new", project, "--name", "T1", "--floors", "4-6")[0] == 0
    lay = read_layout(layout_path(project, "T1"))
    assert lay.source == "manual" and lay.odus == () and lay.floors == (4, 5, 6)
    code, _, err = _run(capsys, "layout", "new", project, "--name", "T1", "--floors", "4")
    assert code == 2 and "--force" in err
    assert read_layout(layout_path(project, "T1")).floors == (4, 5, 6)


def test_new_floors_beyond_building_is_error(project, capsys):
    code, _, err = _run(capsys, "layout", "new", project, "--name", "T1", "--floors", "18-30")
    assert code == 2 and "19" in err and not layout_path(project, "T1").exists()


def test_new_requires_floors_and_name(project, capsys):
    with pytest.raises(SystemExit):
        main(["layout", "new", str(project), "--name", "T1"])
    capsys.readouterr()


# ---- edit ----
@pytest.fixture
def fake_server(monkeypatch):
    calls = []
    mod = types.ModuleType("odu_cfd.layout.server")

    def run_editor(project_dir, layout_name, library_dir=None, port=0, open_browser=True):
        calls.append(
            {"project": str(project_dir), "layout": layout_name, "library": library_dir, "port": port,
             "open": open_browser}
        )
        return 0

    mod.run_editor = run_editor
    monkeypatch.setitem(sys.modules, "odu_cfd.layout.server", mod)
    import odu_cfd.layout as pkg

    monkeypatch.setattr(pkg, "server", mod, raising=False)
    return calls


def test_edit_existing_layout(project, capsys, fake_server):
    _save(project, "KT1", [])
    code, _, err = _run(capsys, "edit", project, "--layout", "KT1", "--port", "8123", "--no-open", "--library", "LIB")
    assert code == 0, err
    assert fake_server == [{"project": str(project), "layout": "KT1", "library": "LIB", "port": 8123, "open": False}]


def test_edit_defaults(project, capsys, fake_server):
    _save(project, "KT1", [])
    assert _run(capsys, "edit", project, "--layout", "KT1")[0] == 0
    assert fake_server[0]["port"] == 0 and fake_server[0]["open"] is True and fake_server[0]["library"] is None


def test_edit_creates_missing_layout_with_floors(project, capsys, fake_server):
    code, _, err = _run(capsys, "edit", project, "--layout", "MOI", "--floors", "4-6", "--no-open")
    assert code == 0, err
    lay = read_layout(layout_path(project, "MOI"))
    assert lay.source == "manual" and lay.odus == () and lay.floors == (4, 5, 6)
    assert fake_server[0]["layout"] == "MOI"


def test_edit_missing_layout_without_floors_is_error(project, capsys, fake_server):
    code, _, err = _run(capsys, "edit", project, "--layout", "MOI", "--no-open")
    assert code == 2 and "--floors" in err
    assert not layout_path(project, "MOI").exists() and fake_server == []


def test_edit_without_layout_name_uses_first_existing(project, capsys, fake_server):
    _save(project, "B", [])
    _save(project, "A", [])
    assert _run(capsys, "edit", project, "--no-open")[0] == 0
    assert fake_server[0]["layout"] == "A"


def test_edit_without_layout_and_none_exist_needs_floors(project, capsys, fake_server):
    code, _, err = _run(capsys, "edit", project, "--no-open")
    assert code == 2 and "--floors" in err
    assert _run(capsys, "edit", project, "--floors", "4", "--no-open")[0] == 0
    assert fake_server[0]["layout"] == "layout-1" and list_layouts(project) == ["layout-1"]


def test_edit_before_geometry_is_error(raw_project, capsys, fake_server):
    code, _, err = _run(capsys, "edit", raw_project, "--layout", "KT1", "--floors", "4", "--no-open")
    assert code == 2 and "odu-cfd geometry" in err and fake_server == []


def test_edit_bad_layout_name(project, capsys, fake_server):
    code, _, err = _run(capsys, "edit", project, "--layout", "../x", "--floors", "4")
    assert code == 2 and "không hợp lệ" in err and fake_server == []


def test_edit_returns_server_exit_code(project, capsys, fake_server, monkeypatch):
    _save(project, "KT1", [])
    sys.modules["odu_cfd.layout.server"].run_editor = lambda *a, **k: 7
    assert _run(capsys, "edit", project, "--layout", "KT1", "--no-open")[0] == 7


def test_cli_import_does_not_pull_layout_cycle():
    import os
    import subprocess
    from pathlib import Path

    import odu_cfd

    env = dict(os.environ, PYTHONPATH=str(Path(odu_cfd.__file__).parent.parent))
    for order in (
        "import odu_cfd.layout.validate, odu_cfd.geometry.pipeline, odu_cfd.cli",
        "import odu_cfd.geometry.pipeline, odu_cfd.layout.validate, odu_cfd.cli",
        "import odu_cfd.cli, odu_cfd.geometry.pipeline, odu_cfd.layout.validate",
    ):
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", order], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr


# ---- vòng 4: geometry --layout không ghi gì khi phương án lỗi (M6) ----
def test_geometry_layout_error_leaves_balconies_yaml_untouched(project, capsys):
    from odu_cfd.layout.balconies import FILE_NAME

    path = project / FILE_NAME
    path.write_bytes(path.read_bytes() + b"# dau vet nguoi dung\n")
    before = path.read_bytes()
    plan_before = (project / "input" / "geometry" / "plan.json").read_bytes()
    _save(project, "BAD", [OduPlacement("ODU-01", 15.0, 10.0, 0.0)])
    code, _, err = _run(capsys, "geometry", project, "--layout", "BAD")
    assert code == 2 and "ODU-01" in err
    assert path.read_bytes() == before
    assert (project / "input" / "geometry" / "plan.json").read_bytes() == plan_before


def test_geometry_layout_error_does_not_create_balconies_yaml(project, capsys):
    from odu_cfd.layout.balconies import FILE_NAME

    (project / FILE_NAME).unlink()
    _save(project, "BAD", [OduPlacement("ODU-01", 15.0, 10.0, 0.0)])
    code, _, _ = _run(capsys, "geometry", project, "--layout", "BAD")
    assert code == 2 and not (project / FILE_NAME).exists()


def test_geometry_layout_success_writes_balconies_yaml(project, capsys):
    from odu_cfd.layout.balconies import FILE_NAME

    (project / FILE_NAME).unlink()
    _save(project, "GOOD", [OduPlacement("ODU-01", 6.0, 1.0, 180.0)])
    assert _run(capsys, "geometry", project, "--layout", "GOOD")[0] == 0
    assert (project / FILE_NAME).is_file()


def test_geometry_prints_carry_over_warning(project, capsys):
    import inspect

    from odu_cfd.layout.balconies import write_balconies

    if "warnings" not in inspect.signature(write_balconies).parameters:
        pytest.skip("write_balconies chưa có tham số warnings (F1)")
    assert main(["layout", "balconies", str(project), "--deny", "B01"]) == 0
    import yaml

    from odu_cfd.layout.balconies import FILE_NAME

    path = project / FILE_NAME
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for it in data["balconies"]:
        if it["id"] == "B01":
            it["polygon"] = [[x + 50.0, y + 50.0] for x, y in it["polygon"]]
            it["centroid"] = [it["centroid"][0] + 50.0, it["centroid"][1] + 50.0]
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    code, _, err = _run(capsys, "geometry", project)
    assert code == 0 and "Cảnh báo" in err and "allowed" in err


# ---- layout auto: rỗng và size_explicit (I2) ----
def test_auto_empty_result_exits_2_without_writing(project, capsys):
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "E", "--floors", "4", "--min-area", "9999")
    assert code == 2 and "--allow-empty" in err
    assert not layout_path(project, "E").exists()


def test_auto_allow_empty_writes_empty_layout(project, capsys):
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "E", "--floors", "4", "--min-area", "9999",
                        "--allow-empty")
    assert code == 0 and read_layout(layout_path(project, "E")).odus == ()


@pytest.mark.parametrize("extra,expected", [([], False), (["--size", "1,0.4"], True)])
def test_auto_passes_size_explicit_only_with_size_flag(project, capsys, monkeypatch, extra, expected):
    import odu_cfd.layout.auto as auto_mod

    seen = {}
    real = auto_mod.auto_layout

    def spy(*a, **kw):
        seen["size_explicit"] = kw.get("size_explicit")
        return real(*a, **kw)

    monkeypatch.setattr(auto_mod, "auto_layout", spy)
    code, _, err = _run(capsys, "layout", "auto", project, "--name", "X", "--floors", "4", *extra)
    assert code == 0, err
    assert seen["size_explicit"] is expected


# ---- layout validate --verbose (M1) ----
def test_validate_verbose_lists_empty_allowed_balconies_and_counts(project, capsys):
    _save(project, "V", [OduPlacement("ODU-01", 6.0, 1.0, 180.0), OduPlacement("ODU-02", 7.4, 1.0, 180.0)])
    assert main(["layout", "balconies", str(project), "--deny", "B02"]) == 0
    code, out, _ = _run(capsys, "layout", "validate", project, "V", "--verbose")
    assert code == 0
    assert "B01: 2 dàn nóng" in out
    code2, out2, _ = _run(capsys, "layout", "validate", project, "V")
    assert "B01: 2 dàn nóng" not in out2


def test_validate_verbose_reports_allowed_balcony_without_odu(project, capsys):
    _save(project, "V", [OduPlacement("ODU-01", 6.0, 1.0, 180.0)])
    code, out, _ = _run(capsys, "layout", "validate", project, "V", "--verbose")
    assert code == 0 and "B02" in out and "không có dàn nóng" in out
