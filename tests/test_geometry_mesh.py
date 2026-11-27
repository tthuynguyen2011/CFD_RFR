import numpy as np
import pytest
from shapely.geometry import Polygon

from odu_cfd.geometry.mesh import box, bounds, extrude_polygon, is_closed, merge, volume


def test_square_prism():
    m = extrude_polygon(Polygon([(0, 0), (3, 0), (3, 2), (0, 2)]), 1.0, 3.0)
    assert is_closed(m)
    assert volume(m) == pytest.approx(12.0)
    assert bounds(m) == pytest.approx((0, 0, 1, 3, 2, 3))


def test_polygon_with_hole():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(4, 4), (4, 6), (6, 6), (6, 4)]
    m = extrude_polygon(Polygon(outer, [hole]), 0.0, 2.0)
    assert is_closed(m)
    assert volume(m) == pytest.approx((100 - 4) * 2.0)


def test_concave_l_shape():
    m = extrude_polygon(Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]), 0.0, 1.0)
    assert is_closed(m) and volume(m) == pytest.approx(6.0)


def test_clockwise_input_is_reoriented():
    m = extrude_polygon(Polygon([(0, 0), (0, 2), (2, 2), (2, 0)]), 0.0, 1.0)
    assert volume(m) == pytest.approx(4.0)


def test_multipolygon():
    from shapely.geometry import MultiPolygon

    mp = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(5, 5), (7, 5), (7, 6), (5, 6)])])
    m = extrude_polygon(mp, 0.0, 1.0)
    assert is_closed(m) and volume(m) == pytest.approx(3.0)


def test_bad_height():
    with pytest.raises(ValueError):
        extrude_polygon(Polygon([(0, 0), (1, 0), (1, 1)]), 2.0, 2.0)


def test_box_rotation():
    m = box(10.0, 5.0, 0.98, 0.47, 90.0, 0.0, 1.0)
    lo, hi = bounds(m)[:3], bounds(m)[3:]
    assert (hi[0] - lo[0], hi[1] - lo[1]) == pytest.approx((0.47, 0.98))
    assert ((hi[0] + lo[0]) / 2, (hi[1] + lo[1]) / 2) == pytest.approx((10.0, 5.0))
    assert volume(m) == pytest.approx(0.98 * 0.47)


def test_open_mesh_is_detected():
    m = box(0, 0, 1, 1, 0, 0, 1)
    open_mesh = type(m)(m.vertices, m.faces[:-1])
    assert not is_closed(open_mesh)


def test_merge_keeps_both():
    a, b = box(0, 0, 1, 1, 0, 0, 1), box(5, 5, 1, 1, 0, 0, 2)
    m = merge([a, b])
    assert is_closed(m) and volume(m) == pytest.approx(3.0)
    assert m.faces.max() < len(m.vertices)


def _normals(m):
    t = m.vertices[m.faces]
    return np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])


def test_normals_point_outward():
    m = extrude_polygon(Polygon([(0, 0), (3, 0), (3, 2), (0, 2)]), 0.0, 1.0)
    n = _normals(m)
    c = m.vertices[m.faces].mean(axis=1) - np.array([1.5, 1.0, 0.5])
    assert (np.einsum("ij,ij->i", n, c) > 0).all()
    # bottom faces point down, top faces point up
    zc = m.vertices[m.faces][:, :, 2]
    assert (n[(zc == 0).all(axis=1)][:, 2] < 0).all()
    assert (n[(zc == 1).all(axis=1)][:, 2] > 0).all()


def test_no_degenerate_faces():
    m = extrude_polygon(Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]), 0.0, 1.0)
    assert (np.linalg.norm(_normals(m), axis=1) > 1e-12).all()


def test_box_closed_for_any_rotation():
    m = box(1, 2, 1.0, 0.5, 33.0, 0.0, 1.0)
    assert is_closed(m) and volume(m) > 0


# ---- I1: tường bên theo cạnh biên của CDT ----
def test_two_squares_touching_at_a_vertex_are_closed():
    from shapely.geometry import MultiPolygon

    mp = MultiPolygon(
        [Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]), Polygon([(2, 2), (4, 2), (4, 4), (2, 4)])]
    )
    m = extrude_polygon(mp, 0.0, 1.0)
    assert is_closed(m) and volume(m) == pytest.approx(8.0)


def test_hole_touching_outer_boundary_is_closed():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(0, 4), (3, 4), (3, 6), (0, 6)]  # lỗ chạm biên ngoài theo một đoạn
    p = Polygon(outer, [hole])
    m = extrude_polygon(p, 0.0, 2.0)
    assert is_closed(m)
    assert volume(m) == pytest.approx(p.area * 2.0)


def test_hole_touching_outer_at_a_point_is_closed():
    p = Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)], [[(0, 5), (3, 3), (3, 7)]]
    )
    m = extrude_polygon(p, 0.0, 2.0)
    assert is_closed(m)
    assert volume(m) == pytest.approx(p.area * 2.0)


def test_balcony_touching_facade_at_one_vertex_is_closed():
    from shapely.geometry import MultiPolygon

    mp = MultiPolygon(
        [Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), Polygon([(10, 10), (12, 10), (12, 12), (10, 12)])]
    )
    m = extrude_polygon(mp, 0.0, 3.0)
    assert is_closed(m) and volume(m) == pytest.approx(104 * 3.0)


def test_duplicated_faces_are_not_closed():
    m = extrude_polygon(Polygon([(0, 0), (3, 0), (3, 2), (0, 2)]), 0.0, 1.0)
    assert not is_closed(merge([m, m]))


def test_near_duplicate_vertices_still_close():
    # hồi quy từ bản vẽ thật: lan can sau phép hợp đa giác có đỉnh cách nhau ~1e-14 m
    poly = Polygon([(0, 0), (2, 0), (2, 1e-14), (2, 1), (1e-14, 1), (0, 1)], [[(0.5, 0.4), (0.5 + 1e-13, 0.4), (0.5, 0.6), (0.7, 0.6), (0.7, 0.4)]])
    m = extrude_polygon(poly, 0.0, 1.1)
    assert is_closed(m) and volume(m) > 0
