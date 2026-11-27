import math

import ezdxf
import pytest
from dxf_factory import ODU_D, ODU_W, make_tower_dxf

from odu_cfd.errors import IngestError
from odu_cfd.ingest.drawing import load_drawing


def _extent(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_units_and_metre_coordinates(tower_dxf):
    d = load_drawing(tower_dxf)
    assert (d.units, d.scale_to_m) == ("mm", 0.001)
    walls = [p for p in d.primitives if p.layer == "A-WALL"]
    xs = [x for p in walls for x, _ in p.points]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(510.0)
    assert "A-WALL" in d.layers and "M-EQPM" in d.layers


def test_unitless_drawing_requires_override(tmp_path):
    p = tmp_path / "u.dxf"
    make_tower_dxf(p, unit_code=0)
    with pytest.raises(IngestError, match="đơn vị"):
        load_drawing(p)
    d = load_drawing(p, units_override="m")
    assert d.scale_to_m == 1.0
    assert max(x for q in d.primitives if q.layer == "A-WALL" for x, _ in q.points) == pytest.approx(510.0)


def test_bad_units_override(tower_dxf):
    with pytest.raises(IngestError, match="furlong"):
        load_drawing(tower_dxf, units_override="furlong")


def test_insert_footprint_in_metres(tower_dxf):
    d = load_drawing(tower_dxf)
    ins = [p for p in d.primitives if p.kind == "insert" and p.name == "ODU_TEST"]
    assert len(ins) == 4
    assert ins[0].layer == "M-EQPM" and len(ins[0].points) == 4
    assert _extent(ins[0].points) == pytest.approx((ODU_W, ODU_D))


def test_rotated_insert_swaps_extents(tmp_path):
    p = tmp_path / "r.dxf"
    make_tower_dxf(p)
    doc = ezdxf.readfile(p)
    doc.modelspace().add_blockref(
        "ODU_TEST", (40000, 40000), dxfattribs={"layer": "M-EQPM", "rotation": 90}
    )
    doc.saveas(p)
    d = load_drawing(p)
    rot = [q for q in d.primitives if q.kind == "insert" and q.rotation_deg == pytest.approx(90)]
    assert len(rot) == 1
    assert _extent(rot[0].points) == pytest.approx((ODU_D, ODU_W))


def test_bulge_polyline_is_flattened(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    doc.modelspace().add_lwpolyline([(0, 0, 1), (1000, 0, 0)], format="xyb")
    p = tmp_path / "b.dxf"
    doc.saveas(p)
    pts = load_drawing(p).primitives[0].points
    assert len(pts) > 8
    assert all(abs(math.hypot(x - 0.5, y) - 0.5) < 0.006 for x, y in pts)


def test_texts_are_collected(tower_dxf):
    d = load_drawing(tower_dxf)
    t = [t for t in d.texts if t.text == "A-101"]
    assert len(t) == 1 and (t[0].x, t[0].y) == pytest.approx((1.0, 1.0))


def test_unsupported_entities_are_counted_not_fatal(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))
    h = msp.add_hatch()
    h.paths.add_polyline_path([(0, 0), (10, 0), (10, 10)], is_closed=True)
    p = tmp_path / "h.dxf"
    doc.saveas(p)
    d = load_drawing(p)
    assert len(d.primitives) == 1 and d.skipped.get("HATCH") == 1


# ---- C1: bung INSERT trên layer kết cấu ----


def _new_doc():
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6  # mét
    return doc


def _save(doc, tmp_path, name="s.dxf"):
    p = tmp_path / name
    doc.saveas(p)
    return p


def _paths(d, layer):
    return [p for p in d.primitives if p.kind == "path" and p.layer == layer]


def test_structural_insert_is_expanded_into_paths(tmp_path):
    doc = _new_doc()
    blk = doc.blocks.new("WALLBLK")
    blk.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True, dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("WALLBLK", (10, 20), dxfattribs={"layer": "A-WALL"})
    d = load_drawing(_save(doc, tmp_path))
    got = _paths(d, "A-WALL")  # layer "0" trong block thừa hưởng layer của INSERT
    assert len(got) == 1 and got[0].closed
    assert sorted(got[0].points) == [(10, 20), (10, 23), (14, 20), (14, 23)]
    assert not [p for p in d.primitives if p.kind == "insert"]


def test_expansion_honours_negative_scale_mirror_and_rotation(tmp_path):
    doc = _new_doc()
    blk = doc.blocks.new("L")
    blk.add_line((0, 0), (2, 0), dxfattribs={"layer": "0"})
    msp = doc.modelspace()
    msp.add_blockref("L", (10, 0), dxfattribs={"layer": "A-WALL", "xscale": -1.0})
    msp.add_blockref("L", (0, 10), dxfattribs={"layer": "A-WALL", "rotation": 90})
    msp.add_blockref("L", (0, 20), dxfattribs={"layer": "A-WALL", "extrusion": (0, 0, -1)})
    got = [sorted(p.points) for p in _paths(load_drawing(_save(doc, tmp_path)), "A-WALL")]
    assert [(8, 0), (10, 0)] in got
    assert [(0, 10), pytest.approx((0, 12), abs=1e-9)] in got
    assert [(-2, 20), (0, 20)] in got  # OCS bị lật quanh trục Y


def test_nested_blocks_inherit_layer_and_compose_transforms(tmp_path):
    doc = _new_doc()
    inner = doc.blocks.new("INNER")
    inner.add_line((0, 0), (1, 0), dxfattribs={"layer": "0"})
    mid = doc.blocks.new("MID")
    mid.add_blockref("INNER", (5, 0), dxfattribs={"layer": "0", "xscale": 2.0})
    mid.add_blockref("INNER", (0, 7), dxfattribs={"layer": "A-DETAIL"})
    doc.modelspace().add_blockref("MID", (100, 100), dxfattribs={"layer": "A-HANDRAIL", "rotation": 90})
    d = load_drawing(_save(doc, tmp_path))
    rail = _paths(d, "A-HANDRAIL")
    assert len(rail) == 1  # (5,0)-(7,0) xoay 90 độ quanh gốc rồi dời (100,100)
    assert sorted(rail[0].points) == pytest.approx([(100, 105), (100, 107)])
    assert len(_paths(d, "A-DETAIL")) == 1  # layer riêng của entity lồng được giữ


def test_minsert_on_structural_layer_expands_every_copy(tmp_path):
    doc = _new_doc()
    blk = doc.blocks.new("POST")
    blk.add_line((0, 0), (0, 1), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref(
        "POST", (0, 0), dxfattribs={"layer": "A-BALCONY", "row_count": 2, "column_count": 3,
                                    "row_spacing": 5, "column_spacing": 10}
    )
    d = load_drawing(_save(doc, tmp_path))
    starts = sorted(min(p.points) for p in _paths(d, "A-BALCONY"))
    assert starts == [(0, 0), (0, 5), (10, 0), (10, 5), (20, 0), (20, 5)]


def test_non_structural_insert_keeps_bounding_box(tmp_path):
    doc = _new_doc()
    blk = doc.blocks.new("STAIRBLK")
    for i in range(50):
        blk.add_line((i, 0), (i, 3), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("STAIRBLK", (0, 0), dxfattribs={"layer": "A-STAIR"})
    d = load_drawing(_save(doc, tmp_path))
    assert [p.kind for p in d.primitives] == ["insert"]
    assert _extent(d.primitives[0].points) == pytest.approx((49, 3))


def test_layer_roles_argument_overrides_auto_classification(tmp_path):
    doc = _new_doc()
    blk = doc.blocks.new("B")
    blk.add_line((0, 0), (3, 0), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("B", (0, 0), dxfattribs={"layer": "A-WALL"})
    doc.modelspace().add_blockref("B", (0, 5), dxfattribs={"layer": "CUSTOM"})
    p = _save(doc, tmp_path)
    auto = load_drawing(p)
    assert len(_paths(auto, "A-WALL")) == 1 and not _paths(auto, "CUSTOM")
    mine = load_drawing(p, layer_roles={"CUSTOM": "wall_ext", "A-WALL": None})
    assert len(_paths(mine, "CUSTOM")) == 1 and not _paths(mine, "A-WALL")


def test_self_referencing_block_terminates(tmp_path):
    doc = _new_doc()
    blk = doc.blocks.new("LOOP")
    blk.add_line((0, 0), (1, 0), dxfattribs={"layer": "0"})
    blk.add_blockref("LOOP", (1, 0), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("LOOP", (0, 0), dxfattribs={"layer": "A-WALL"})
    d = load_drawing(_save(doc, tmp_path))
    assert 1 <= len(_paths(d, "A-WALL")) <= 20


def test_expansion_is_capped(tmp_path, monkeypatch):
    from odu_cfd.ingest import drawing as drawing_mod

    doc = _new_doc()
    blk = doc.blocks.new("B")
    blk.add_line((0, 0), (1, 0), dxfattribs={"layer": "0"})
    for i in range(50):
        doc.modelspace().add_blockref("B", (0, i), dxfattribs={"layer": "A-WALL"})
    monkeypatch.setattr(drawing_mod, "MAX_EXPANDED_PATHS", 10)
    d = load_drawing(_save(doc, tmp_path))
    assert 10 <= len(_paths(d, "A-WALL")) < 50
    assert d.skipped.get("INSERT-limit")


def test_empty_dxf_reports_empty_or_broken(tmp_path):
    p = tmp_path / "empty.dxf"
    ezdxf.new("R2018").saveas(p)
    with pytest.raises(IngestError, match="rỗng hoặc hỏng"):
        load_drawing(p)
    z = tmp_path / "zero.dxf"
    z.write_bytes(b"")
    with pytest.raises(IngestError, match="rỗng hoặc hỏng"):
        load_drawing(z)
