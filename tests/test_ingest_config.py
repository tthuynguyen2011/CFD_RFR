import pytest

from odu_cfd.errors import IngestError
from odu_cfd.ingest.config import IngestConfig, read_ingest_config, write_ingest_config
from odu_cfd.ingest.odu_detect import OduInstance


def _cfg():
    return IngestConfig(
        status="proposed",
        source_file="input/tower.dxf",
        original_file="input/tower.dwg",
        units="mm",
        view_id="V1",
        view_bbox=(0.0, 0.0, 30.0, 20.0),
        layers={"A-WALL": "wall_ext", "A-BALC": "balcony"},
        odu_area_range_m2=(0.2, 3.0),
        odus=[OduInstance("ODU-01", "ODU_TEST", "M-EQPM", (5.99, 1.035), (0.98, 0.47), 0.0)],
    )


def test_roundtrip(tmp_path):
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, _cfg())
    assert read_ingest_config(p) == _cfg()


def test_vietnamese_text_survives(tmp_path):
    cfg = _cfg()
    cfg.layers = {"A-TƯỜNG": "wall_ext"}
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, cfg)
    assert read_ingest_config(p).layers == {"A-TƯỜNG": "wall_ext"}


@pytest.mark.parametrize(
    "old,new,field",
    [
        ("status: proposed", "status: maybe", "status"),
        ("A-BALC: balcony", "A-BALC: roof", "layers"),
        ("units: mm", "units: furlong", "units"),
    ],
)
def test_invalid_values_name_the_field(tmp_path, old, new, field):
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, _cfg())
    p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    with pytest.raises(IngestError, match=field):
        read_ingest_config(p)


def test_bad_bbox_is_rejected(tmp_path):
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, _cfg())
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace("30.0", "-5.0"), encoding="utf-8")
    with pytest.raises(IngestError, match="view_bbox"):
        read_ingest_config(p)


def test_missing_file_is_ingest_error(tmp_path):
    with pytest.raises(IngestError, match="ingest.yaml"):
        read_ingest_config(tmp_path / "ingest.yaml")


# ---- I2: kiểm tra đầu vào chặt hơn ----
import dataclasses

from odu_cfd.ingest.config import validate_for_geometry


def _read_modified(tmp_path, mutate):
    cfg = _cfg()
    mutate(cfg)
    p = tmp_path / "ingest.yaml"
    write_ingest_config(p, cfg)
    return read_ingest_config(p)


def _odu(i, **kw):
    base = dict(odu_id=f"ODU-{i:02d}", block="B", layer="M", center=(1.0, 1.0), size=(0.9, 0.4), rotation_deg=0.0)
    base.update(kw)
    return OduInstance(**base)


@pytest.mark.parametrize("bad", ["ODU 01", "ODU/01", "../x", "ô", "a;b"])
def test_bad_odu_id_is_rejected(tmp_path, bad):
    with pytest.raises(IngestError, match=r"odus\[0\]\.id"):
        _read_modified(tmp_path, lambda c: setattr(c, "odus", [_odu(1, odu_id=bad)]))


def test_duplicate_odu_id_is_rejected(tmp_path):
    with pytest.raises(IngestError, match="trùng"):
        _read_modified(tmp_path, lambda c: setattr(c, "odus", [_odu(1), _odu(2, odu_id="ODU-01")]))


@pytest.mark.parametrize(
    "bad",
    [
        "../outside.dxf",
        "/etc/x.dxf",
        "C:\\x\\a.dxf",
        "C:/x/a.dxf",
        "input/../../a.dxf",
        "other/a.dxf",
        "a.dxf",
        "input",
        "\\\\srv\\share\\a.dxf",
    ],
)
@pytest.mark.parametrize("field", ["source_file", "original_file"])
def test_paths_must_be_relative_inside_input(tmp_path, bad, field):
    with pytest.raises(IngestError, match=field):
        _read_modified(tmp_path, lambda c: setattr(c, field, bad))


def test_nested_path_inside_input_is_ok(tmp_path):
    cfg = _read_modified(tmp_path, lambda c: setattr(c, "source_file", "input/thư mục/tầng 1.dxf"))
    assert cfg.source_file == "input/thư mục/tầng 1.dxf"


@pytest.mark.parametrize("size", [(500.0, 0.4), (0.9, 5.01), (5.0001, 5.0)])
def test_odu_size_upper_bound(tmp_path, size):
    with pytest.raises(IngestError, match=r"odus\[0\]\.size"):
        _read_modified(tmp_path, lambda c: setattr(c, "odus", [_odu(1, size=size)]))


def test_odu_size_exactly_five_is_ok(tmp_path):
    _read_modified(tmp_path, lambda c: setattr(c, "odus", [_odu(1, size=(5.0, 5.0))]))


@pytest.mark.parametrize("center", [(float("nan"), 1.0), (1.0, float("inf"))])
def test_odu_center_must_be_finite(tmp_path, center):
    with pytest.raises(IngestError, match=r"odus\[0\]\.center"):
        _read_modified(tmp_path, lambda c: setattr(c, "odus", [_odu(1, center=center)]))


@pytest.mark.parametrize(
    "bbox",
    [(-1e9, -1e9, 1e9, 1e9), (0.0, 0.0, 2e5, 10.0), (0.0, 0.0, 10.0, 2e5), (1e12, 0.0, 1e12 + 5, 5.0)],
)
def test_view_bbox_must_be_sane(tmp_path, bbox):
    with pytest.raises(IngestError, match="view_bbox"):
        _read_modified(tmp_path, lambda c: setattr(c, "view_bbox", bbox))


def test_view_bbox_of_100km_is_ok(tmp_path):
    _read_modified(tmp_path, lambda c: setattr(c, "view_bbox", (0.0, 0.0, 1e5, 1e5)))


def test_too_many_odus_is_rejected(tmp_path):
    odus = [_odu(i, center=(float(i), 1.0)) for i in range(5001)]
    with pytest.raises(IngestError, match="odus"):
        _read_modified(tmp_path, lambda c: setattr(c, "odus", odus))


def test_validate_for_geometry_ok():
    validate_for_geometry(_cfg())


def test_validate_for_geometry_needs_envelope_layer():
    cfg = _cfg()
    cfg.layers = {"A-BALC": "balcony"}
    with pytest.raises(IngestError, match="wall_ext"):
        validate_for_geometry(cfg)


def test_validate_for_geometry_accepts_slab_only():
    cfg = _cfg()
    cfg.layers = {"A-SLAB": "slab"}
    validate_for_geometry(cfg)


def test_validate_for_geometry_odus_optional_by_default():
    # giai đoạn 2c: dàn nóng là biến thiết kế (phương án bố trí), không còn bắt buộc trong ingest.yaml
    validate_for_geometry(dataclasses.replace(_cfg(), odus=[]))


def test_validate_for_geometry_can_still_require_odus():
    cfg = dataclasses.replace(_cfg(), odus=[])
    with pytest.raises(IngestError, match="dàn nóng"):
        validate_for_geometry(cfg, require_odus=True)


def test_validate_for_geometry_lists_all_problems():
    cfg = dataclasses.replace(_cfg(), odus=[], layers={})
    with pytest.raises(IngestError) as e:
        validate_for_geometry(cfg, require_odus=True)
    assert "wall_ext" in str(e.value) and "dàn nóng" in str(e.value)


def test_overlay_box_corners_rotate_counter_clockwise():
    from odu_cfd.ingest.overlay import _box_corners

    o = OduInstance("ODU-01", "B", "M", (10.0, 10.0), (2.0, 1.0), 30.0)
    c = _box_corners(o)[0]  # góc (-w/2, -d/2) sau khi xoay +30 độ ngược chiều kim đồng hồ
    assert c == pytest.approx((10 - 0.8660254 + 0.25, 10 - 0.5 - 0.4330127), abs=1e-6)
