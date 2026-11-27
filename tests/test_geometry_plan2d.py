# tests/test_geometry_plan2d.py
import pytest

from odu_cfd.errors import IngestError
from odu_cfd.geometry.plan2d import extract_plan
from odu_cfd.ingest.config import IngestConfig
from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.ingest.layers import classify_layers


def _cfg(drawing, view=(-1.0, -1.0, 40.0, 30.0), drop=()):
    roles = {k: v for k, v in classify_layers(drawing.layers).items() if v and k not in drop}
    return IngestConfig("confirmed", "x.dxf", None, "mm", "V1", view, roles, (0.2, 3.0), [])


def test_envelope_balconies_rails(tower_dxf):
    d = load_drawing(tower_dxf)
    plan = extract_plan(d, _cfg(d))
    assert plan.envelope.area == pytest.approx(600.0)
    assert sorted(round(b.area, 3) for b in plan.balconies) == [8.0, 8.0]
    assert sorted(round(r.length, 3) for r in plan.rails) == [4.0, 4.0]
    assert plan.columns == ()


def test_far_cluster_is_outside_the_view(tower_dxf):
    d = load_drawing(tower_dxf)
    plan = extract_plan(d, _cfg(d))
    assert plan.envelope.bounds[2] < 40


def test_second_view_gives_its_own_envelope(tower_dxf):
    d = load_drawing(tower_dxf)
    plan = extract_plan(d, _cfg(d, view=(499.0, -1.0, 511.0, 13.0)))
    assert plan.envelope.area == pytest.approx(100.0)
    assert len(plan.balconies) == 0


def test_no_envelope_layer_is_an_error(tower_dxf):
    d = load_drawing(tower_dxf)
    with pytest.raises(IngestError, match="đường bao"):
        extract_plan(d, _cfg(d, drop=("A-WALL",)))


# ---- trường hợp biên (bản vẽ dựng tay) ----
from odu_cfd.ingest.drawing import Drawing, Primitive


def _rect(layer, x0, y0, x1, y1, closed=True):
    return Primitive("path", layer, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), closed)


def _drawing(prims):
    layers = tuple(sorted({p.layer for p in prims}))
    return Drawing(tuple(prims), (), layers, "m", 1.0, {})


def _hcfg(layers=None, view=(-50.0, -50.0, 100.0, 100.0)):
    layers = layers or {"W": "wall_ext", "B": "balcony", "R": "rail", "C": "column"}
    return IngestConfig("confirmed", "x.dxf", None, "m", "V1", view, layers, (0.2, 3.0), [])


def test_courtyard_hole_is_filled():
    d = _drawing([_rect("W", 0, 0, 30, 20), _rect("W", 10, 5, 20, 15)])
    plan = extract_plan(d, _hcfg())
    assert plan.envelope.area == pytest.approx(600.0)
    assert len(plan.envelope.interiors) == 0


def test_double_line_wall_gives_outer_outline():
    d = _drawing([_rect("W", 0, 0, 30, 20), _rect("W", 0.3, 0.3, 29.7, 19.7)])
    plan = extract_plan(d, _hcfg())
    assert plan.envelope.area == pytest.approx(600.0)


def test_small_fragments_are_dropped():
    d = _drawing([_rect("W", 0, 0, 30, 20), _rect("W", 40, 0, 40.5, 0.5)])
    plan = extract_plan(d, _hcfg())
    assert plan.envelope.area == pytest.approx(600.0)


def test_envelope_multipolygon_for_two_blocks():
    d = _drawing([_rect("W", 0, 0, 10, 10), _rect("W", 20, 0, 30, 10)])
    plan = extract_plan(d, _hcfg())
    assert plan.envelope.geom_type == "MultiPolygon"
    assert plan.envelope.area == pytest.approx(200.0)


def test_columns_and_closed_rail_and_bowtie_balcony():
    bow = Primitive("path", "B", ((0, 0), (4, 2), (4, 0), (0, 2)), True)  # nơ: không hợp lệ
    d = _drawing(
        [
            _rect("W", 0, 0, 30, 20),
            bow,
            _rect("C", 1, 1, 1.5, 1.5),
            _rect("R", 5, 5, 6, 6),
        ]
    )
    plan = extract_plan(d, _hcfg())
    assert len(plan.columns) == 1 and plan.columns[0].area == pytest.approx(0.25)
    assert len(plan.rails) == 1 and plan.rails[0].length == pytest.approx(4.0)
    assert plan.balconies and all(b.is_valid for b in plan.balconies)


def test_view_uses_bbox_center_only():
    # đường bao vắt qua biên view nhưng tâm nằm trong -> được lấy một lần
    d = _drawing([_rect("W", 0, 0, 30, 20)])
    plan = extract_plan(d, _hcfg(view=(10.0, 5.0, 16.0, 15.0)))
    assert plan.envelope.area == pytest.approx(600.0)
    with pytest.raises(IngestError):
        extract_plan(d, _hcfg(view=(40.0, 40.0, 50.0, 50.0)))


def test_filled_holes_area_is_recorded():
    prims = [
        _rect("W", 0, 0, 20, 20),
        _rect("W", 5, 5, 5.6, 5.6),  # lỗ nhỏ 0,36 m2 (mặt bị loại vì < MIN_PIECE_AREA_M2)
    ]
    d = _drawing(prims)
    plan = extract_plan(d, _hcfg())
    assert plan.envelope.area == pytest.approx(400.0)  # lỗ bị lấp
    assert plan.envelope.geom_type == "Polygon" and not list(plan.envelope.interiors)
    assert plan.filled_holes_m2 == pytest.approx(0.36)


def test_no_hole_means_zero_filled():
    plan = extract_plan(_drawing([_rect("W", 0, 0, 20, 20)]), _hcfg())
    assert plan.filled_holes_m2 == 0.0
