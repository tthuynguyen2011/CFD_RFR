import json

import pytest
import yaml

from odu_cfd.cli import main


def test_init_creates_project_structure(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    assert main(["init", str(target)]) == 0
    assert (target / "project.yaml").is_file()
    for sub in ("input", "cases", "results", "report"):
        assert (target / sub).is_dir()
    assert 'name: "du_an_a"' in (target / "project.yaml").read_text(encoding="utf-8")


def test_init_refuses_to_overwrite(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    assert main(["init", str(target)]) == 0
    assert main(["init", str(target)]) == 2
    assert "đã tồn tại" in capsys.readouterr().err


def test_validate_accepts_template_project(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    assert main(["validate", str(target)]) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "du_an_a" in out


def test_validate_reports_bad_field(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    data = yaml.safe_load((target / "project.yaml").read_text(encoding="utf-8"))
    data["compute"]["backend"] = "gpu"
    (target / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert main(["validate", str(target)]) == 2
    assert "compute.backend" in capsys.readouterr().err


def test_validate_with_library_checks_model(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": []}), encoding="utf-8")
    assert main(["validate", str(target), "--library", str(lib)]) == 2
    assert "TÊN-MODEL-TRONG-THƯ-VIỆN" in capsys.readouterr().err


def test_validate_with_library_accepts_known_model(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    data = yaml.safe_load((target / "project.yaml").read_text(encoding="utf-8"))
    data["odu"]["model_id"] = "test-odu"
    (target / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    lib = tmp_path / "lib"
    lib.mkdir()
    entry = {
        "model_id": "test-odu", "vendor": "TestCo", "width_m": 0.9, "depth_m": 0.35,
        "height_m": 0.8, "airflow_m3_h": 6000, "cooling_kw": 10, "compressor_kw": 3,
        "intake_limit_c": 46, "source": "dữ liệu thử",
    }
    (lib / "a.yaml").write_text(yaml.safe_dump({"models": [entry]}, allow_unicode=True), encoding="utf-8")
    assert main(["validate", str(target), "--library", str(lib)]) == 0


def test_scenarios_writes_json(tmp_path, capsys):
    target = tmp_path / "du_an_a"
    main(["init", str(target)])
    assert main(["scenarios", str(target)]) == 0
    items = json.loads((target / "scenarios.json").read_text(encoding="utf-8"))
    # speeds [0, 2.6] x 4 hướng: 1 calm + 4
    assert [i["scenario_id"] for i in items][0] == "calm"
    assert len(items) == 5
    assert set(items[0]) == {"scenario_id", "wind_speed_ms", "wind_from_deg", "transient"}


def test_missing_project_dir(tmp_path, capsys):
    assert main(["validate", str(tmp_path / "khong_co")]) == 2
    assert "không tìm thấy" in capsys.readouterr().err


def test_command_is_required():
    with pytest.raises(SystemExit):
        main([])


def test_vietnamese_output_survives_cp1252_stdout(tmp_path):
    """Khi stdout là cp1252 (pipe trên Windows), CLI không được sập và phải xuất UTF-8."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONPATH=str(src))
    result = subprocess.run(
        [sys.executable, "-m", "odu_cfd", "init", str(tmp_path / "du_an_b")],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "Đã tạo dự án" in result.stdout.decode("utf-8")


@pytest.mark.parametrize("name", ["2024", "yes", "null", "toa #1"])
def test_init_name_roundtrips_for_tricky_folder_names(tmp_path, name):
    from odu_cfd.schema import load_project
    target = tmp_path / name
    assert main(["init", str(target)]) == 0
    assert main(["validate", str(target)]) == 0
    assert load_project(target / "project.yaml").name == name


def test_init_dot_uses_cwd_name(tmp_path, monkeypatch):
    from odu_cfd.schema import load_project
    d = tmp_path / "du_an_dot"
    d.mkdir()
    monkeypatch.chdir(d)
    assert main(["init", "."]) == 0
    assert load_project(d / "project.yaml").name == "du_an_dot"


def test_init_under_a_file_reports_error(tmp_path, capsys):
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
    assert main(["init", str(f / "proj")]) == 2
    assert "Lỗi:" in capsys.readouterr().err
