import shutil

import pytest

from odu_cfd.cli import main
from odu_cfd.errors import IngestError
from odu_cfd.ingest.config import read_ingest_config
from odu_cfd.ingest.pipeline import confirm_ingest, run_ingest


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "du-an"
    assert main(["init", str(p)]) == 0
    return p


def test_run_ingest_proposes(project, tower_dxf):
    cfg = run_ingest(project, tower_dxf)
    assert cfg.status == "proposed" and cfg.view_id == "V1" and cfg.units == "mm"
    assert cfg.layers["A-WALL"] == "wall_ext" and cfg.layers["M-EQPM"] == "odu"
    assert "A-ANNO" not in cfg.layers
    assert len(cfg.odus) == 4
    assert (project / "input" / "tower.dxf").is_file()
    assert (project / "input" / "overlay.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert read_ingest_config(project / "input" / "ingest.yaml") == cfg


def test_second_view_can_be_chosen_and_unknown_view_lists_options(project, tower_dxf):
    assert run_ingest(project, tower_dxf, view_id="V2").view_bbox[0] > 400
    with pytest.raises(IngestError, match="V1"):
        run_ingest(project, tower_dxf, view_id="V9")


def test_unknown_extension(project, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF")
    with pytest.raises(IngestError, match=r"\.dwg|\.dxf"):
        run_ingest(project, f)


def test_dwg_goes_through_converter(project, tower_dxf, tmp_path, monkeypatch):
    dwg_file = tmp_path / "tower.dwg"
    dwg_file.write_bytes(b"AC1032" + b"\0" * 64)

    (project / "input" / "tower.dxf").write_text("DXF của người dùng")

    def fake_convert(dwg, out, exe=None):
        assert out.name == "tower.converted.dxf"
        shutil.copy(tower_dxf, out)
        return out

    monkeypatch.setattr("odu_cfd.ingest.pipeline.convert_dwg_to_dxf", fake_convert)
    cfg = run_ingest(project, dwg_file)
    assert cfg.original_file == "input/tower.dwg" and cfg.source_file == "input/tower.converted.dxf"


    assert (project / "input" / "tower.dxf").read_text() == "DXF của người dùng"


def test_confirm_requires_envelope_and_units(project, tower_dxf):
    run_ingest(project, tower_dxf)
    assert confirm_ingest(project).status == "confirmed"


def test_confirm_without_odus_succeeds_with_warning(project, tower_dxf, capsys):
    # giai đoạn 2c: không có dàn nóng vẫn xác nhận được (cần wall_ext hoặc slab); chỉ cảnh báo, hướng dẫn `layout`
    run_ingest(project, tower_dxf)
    ingest_yaml = project / "input" / "ingest.yaml"
    cfg = read_ingest_config(ingest_yaml)
    cfg.odus = []
    from odu_cfd.ingest.config import write_ingest_config

    write_ingest_config(ingest_yaml, cfg)
    capsys.readouterr()
    assert confirm_ingest(project).status == "confirmed"
    err = capsys.readouterr().err
    assert "Cảnh báo" in err and "dàn nóng" in err and "layout" in err


def test_confirm_without_envelope_still_fails(project, tower_dxf):
    run_ingest(project, tower_dxf)
    ingest_yaml = project / "input" / "ingest.yaml"
    cfg = read_ingest_config(ingest_yaml)
    cfg.layers = {k: v for k, v in cfg.layers.items() if v not in ("wall_ext", "slab")}
    from odu_cfd.ingest.config import write_ingest_config

    write_ingest_config(ingest_yaml, cfg)
    with pytest.raises(IngestError, match="wall_ext"):
        confirm_ingest(project)


def test_confirm_with_odus_has_no_warning(project, tower_dxf, capsys):
    run_ingest(project, tower_dxf)
    capsys.readouterr()
    confirm_ingest(project)
    assert capsys.readouterr().err == ""


def test_cli_flow(project, tower_dxf, capsys):
    assert main(["ingest", str(project), str(tower_dxf)]) == 0
    out = capsys.readouterr().out
    assert "overlay.png" in out and "--confirm" in out
    assert main(["ingest", str(project), "--confirm"]) == 0
    assert read_ingest_config(project / "input" / "ingest.yaml").status == "confirmed"


def test_cli_needs_source_or_confirm(project, capsys):
    assert main(["ingest", str(project)]) == 2
    assert "Lỗi" in capsys.readouterr().err


def _confirmed(project, tower_dxf):
    run_ingest(project, tower_dxf)
    confirm_ingest(project)
    return project / "input" / "ingest.yaml"


def test_rerun_refuses_to_overwrite_confirmed_config(project, tower_dxf):
    yaml_path = _confirmed(project, tower_dxf)
    before = yaml_path.read_bytes()
    with pytest.raises(IngestError, match="--force"):
        run_ingest(project, tower_dxf)
    assert yaml_path.read_bytes() == before


def test_force_overwrites_and_keeps_backup(project, tower_dxf):
    yaml_path = _confirmed(project, tower_dxf)
    old = yaml_path.read_bytes()
    cfg = run_ingest(project, tower_dxf, force=True)
    assert cfg.status == "proposed"
    assert (project / "input" / "ingest.yaml.bak").read_bytes() == old


def test_rerun_over_proposed_config_is_allowed(project, tower_dxf):
    run_ingest(project, tower_dxf)
    assert run_ingest(project, tower_dxf).status == "proposed"


def test_cli_force_flag(project, tower_dxf, capsys):
    assert main(["ingest", str(project), str(tower_dxf)]) == 0
    assert main(["ingest", str(project), "--confirm"]) == 0
    capsys.readouterr()
    assert main(["ingest", str(project), str(tower_dxf)]) == 2
    assert "--force" in capsys.readouterr().err
    assert main(["ingest", str(project), str(tower_dxf), "--force"]) == 0
    assert read_ingest_config(project / "input" / "ingest.yaml").status == "proposed"


def _with_degenerate_cluster(tower_dxf):
    import ezdxf

    doc = ezdxf.readfile(tower_dxf)
    msp = doc.modelspace()
    for i in range(60):  # 60 đoạn thẳng nằm trên một đường: nhiều đối tượng nhất nhưng bbox cao 0
        msp.add_line((-900000 + i * 500, 0), (-900000 + i * 500 + 400, 0), dxfattribs={"layer": "A-WALL"})
    doc.saveas(tower_dxf)


def test_degenerate_view_is_never_chosen_automatically(project, tower_dxf):
    _with_degenerate_cluster(tower_dxf)
    cfg = run_ingest(project, tower_dxf)
    assert cfg.view_id == "V1" and cfg.view_bbox[2] - cfg.view_bbox[0] > 10


def test_explicit_degenerate_view_is_reported(project, tower_dxf):
    _with_degenerate_cluster(tower_dxf)
    with pytest.raises(IngestError, match="suy biến"):
        run_ingest(project, tower_dxf, view_id="V3")


def test_empty_dxf_is_reported_as_empty_not_units(project, tmp_path):
    f = tmp_path / "empty.dxf"
    f.write_bytes(b"")
    with pytest.raises(IngestError, match="rỗng hoặc hỏng"):
        run_ingest(project, f)


def test_overlay_box_rotates_counter_clockwise_like_odu_rotation():
    import math

    from odu_cfd.ingest.odu_detect import OduInstance
    from odu_cfd.ingest.overlay import _box_corners

    odu = OduInstance("ODU-01", "B", "L", (10.0, 20.0), (2.0, 1.0), 30.0)
    c = _box_corners(odu)
    ex = (c[1][0] - c[0][0], c[1][1] - c[0][1])  # cạnh W (trục x của hộp) sau khi xoay
    assert ex == pytest.approx((2 * math.cos(math.radians(30)), 2 * math.sin(math.radians(30))))
    assert (sum(p[0] for p in c) / 4, sum(p[1] for p in c) / 4) == pytest.approx((10.0, 20.0))
