import math

import pytest
from shapely.geometry import Point, Polygon

from odu_cfd.layout.balconies import BalconyInfo
from odu_cfd.layout.model import Layout, OduPlacement
from odu_cfd.layout.validate import Problem, odu_footprint, validate_layout

B = [
    BalconyInfo("B01", Polygon([(5, 0), (9, 0), (9, 2), (5, 2)]), True),
    BalconyInfo("B02", Polygon([(20, 0), (24, 0), (24, 2), (20, 2)]), False),
]
SIZE = (0.98, 0.37)


def _layout(odus, floors=(4, 5)):
    return Layout("t", "", "manual", floors, tuple(odus))


def _errors(problems):
    return [p for p in problems if p.level == "error"]


def test_valid_layout_has_no_problems():
    lay = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0), OduPlacement("ODU-02", 7.5, 1.0, 0.0)])
    assert validate_layout(lay, B, 40, {"ODU-01": SIZE, "ODU-02": SIZE}) == []


def test_outside_balcony_is_error():
    lay = _layout([OduPlacement("ODU-01", 15.0, 10.0, 0.0)])
    errs = _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE}))
    assert len(errs) == 1 and errs[0].odu_id == "ODU-01" and "ngoài ban công" in errs[0].message


def test_partly_outside_is_error():
    lay = _layout([OduPlacement("ODU-01", 5.2, 1.0, 0.0)])  # nhô ra khỏi mép trái x=5
    assert _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE}))


def test_rotation_matters_for_fit():
    ok = _layout([OduPlacement("ODU-01", 8.4, 1.0, 0.0)])
    bad = _layout([OduPlacement("ODU-01", 8.9, 1.0, 90.0)])
    assert not _errors(validate_layout(ok, B, 40, {"ODU-01": SIZE}))
    assert _errors(validate_layout(bad, B, 40, {"ODU-01": SIZE}))


def test_denied_balcony_is_error():
    lay = _layout([OduPlacement("ODU-01", 22.0, 1.0, 0.0)])
    errs = _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE}))
    assert len(errs) == 1 and "B02" in errs[0].message and "không cho phép" in errs[0].message


def test_overlap_is_error_only_on_shared_floors():
    a = OduPlacement("ODU-01", 6.0, 1.0, 0.0, floors=(4,))
    b = OduPlacement("ODU-02", 6.3, 1.0, 0.0, floors=(5,))
    assert not _errors(validate_layout(_layout([a, b]), B, 40, {"ODU-01": SIZE, "ODU-02": SIZE}))
    c = OduPlacement("ODU-03", 6.3, 1.0, 0.0, floors=(4, 5))
    errs = _errors(validate_layout(_layout([a, c]), B, 40, {"ODU-01": SIZE, "ODU-03": SIZE}))
    assert len(errs) == 1 and "chồng" in errs[0].message


def test_floors_out_of_range_and_empty():
    lay = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0)], floors=(4, 41))
    assert any("tầng" in p.message for p in _errors(validate_layout(lay, B, 40, {"ODU-01": SIZE})))
    lay2 = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0, floors=(99,))])
    assert _errors(validate_layout(lay2, B, 40, {"ODU-01": SIZE}))


def test_footprint_matches_mesh_box():
    from odu_cfd.geometry.mesh import box_polygon

    p = OduPlacement("O", 10.0, 5.0, 33.0)
    assert odu_footprint(p, SIZE).equals_exact(box_polygon(10.0, 5.0, SIZE[0], SIZE[1], 33.0), 1e-9)


def test_missing_size_is_error():
    lay = _layout([OduPlacement("ODU-01", 6.0, 1.0, 0.0)])
    assert _errors(validate_layout(lay, B, 40, {}))


# ---- bổ sung ----------------------------------------------------------------


def test_footprint_rotation_direction_is_counter_clockwise_independent_check():
    # chân đế 2 x 1 xoay +30 độ ngược chiều kim đồng hồ: đỉnh (1, 0.5) -> (0.616, 0.933)
    fp = odu_footprint(OduPlacement("O", 0.0, 0.0, 30.0), (2.0, 1.0))
    assert fp.contains(Point(0.60, 0.90))
    assert not fp.contains(Point(0.60, -0.90))
    c = math.cos(math.radians(30)), math.sin(math.radians(30))
    corner = (1 * c[0] - 0.5 * c[1], 1 * c[1] + 0.5 * c[0])
    assert any(math.dist(corner, q) < 1e-9 for q in fp.exterior.coords)


def test_footprint_is_translated_to_center():
    fp = odu_footprint(OduPlacement("O", 10.0, 5.0, 0.0), (2.0, 1.0))
    assert fp.bounds == pytest.approx((9.0, 4.5, 11.0, 5.5))


def test_containment_tolerance_is_one_millimetre():
    # chân đế rộng 0.98: tâm x = 5.49 là sát mép trái x=5
    ok = _layout([OduPlacement("O", 5.49 - 0.0005, 1.0, 0.0)])  # nhô 0.5 mm: chấp nhận
    bad = _layout([OduPlacement("O", 5.49 - 0.002, 1.0, 0.0)])  # nhô 2 mm: lỗi
    flush = _layout([OduPlacement("O", 5.49, 1.0, 0.0)])
    assert not _errors(validate_layout(ok, B, 40, {"O": SIZE}))
    assert not _errors(validate_layout(flush, B, 40, {"O": SIZE}))
    assert _errors(validate_layout(bad, B, 40, {"O": SIZE}))


def test_overlap_area_threshold():
    # hai hộp 0.98 x 0.37 giao nhau 0.37 * dx; ngưỡng 1e-4 m2 -> dx ~ 0.00027
    a = OduPlacement("A", 6.0, 1.0, 0.0)
    just_touch = OduPlacement("B", 6.98 - 0.0001, 1.0, 0.0)  # giao 3.7e-5 < 1e-4
    over = OduPlacement("C", 6.98 - 0.0004, 1.0, 0.0)  # giao 1.48e-4 > 1e-4
    s = {"A": SIZE, "B": SIZE, "C": SIZE}
    assert not _errors(validate_layout(_layout([a, just_touch]), B, 40, s))
    assert len(_errors(validate_layout(_layout([a, over]), B, 40, s))) == 1


def test_touching_edges_do_not_overlap():
    a = OduPlacement("A", 6.0, 1.0, 0.0)
    b = OduPlacement("B", 6.98, 1.0, 0.0)  # cạnh chung
    assert validate_layout(_layout([a, b]), B, 40, {"A": SIZE, "B": SIZE}) == []


def test_floors_equal_to_num_floors_ok_and_zero_bad():
    o = OduPlacement("O", 6.0, 1.0, 0.0)
    assert not _errors(validate_layout(_layout([o], floors=(39, 40)), B, 40, {"O": SIZE}))
    assert _errors(validate_layout(_layout([o], floors=(0, 1)), B, 40, {"O": SIZE}))
    assert _errors(validate_layout(_layout([o], floors=()), B, 40, {"O": SIZE}))


def test_odu_with_empty_own_floors_is_error():
    o = OduPlacement("O", 6.0, 1.0, 0.0, floors=())
    errs = _errors(validate_layout(_layout([o]), B, 40, {"O": SIZE}))
    assert errs and errs[0].odu_id == "O"


def test_duplicate_and_bad_ids_are_errors():
    a = OduPlacement("A", 6.0, 1.0, 0.0)
    a2 = OduPlacement("A", 8.0, 1.0, 0.0)
    assert any("trùng" in p.message for p in _errors(validate_layout(_layout([a, a2]), B, 40, {"A": SIZE})))
    bad = OduPlacement("A B", 6.0, 1.0, 0.0)
    assert _errors(validate_layout(_layout([bad]), B, 40, {"A B": SIZE}))


@pytest.mark.parametrize("x,y,r", [(math.nan, 1.0, 0.0), (6.0, math.inf, 0.0), (6.0, 1.0, math.nan)])
def test_non_finite_coordinates_are_errors(x, y, r):
    lay = _layout([OduPlacement("O", x, y, r)])
    errs = _errors(validate_layout(lay, B, 40, {"O": SIZE}))
    assert len(errs) == 1 and errs[0].odu_id == "O"


@pytest.mark.parametrize("size", [(0, 0.4), (1.0, -1), (math.nan, 0.4), (1.0,)])
def test_bad_size_is_error(size):
    lay = _layout([OduPlacement("O", 6.0, 1.0, 0.0)])
    assert _errors(validate_layout(lay, B, 40, {"O": size}))


def test_touching_balconies_pick_the_containing_one():
    # hai ban công chạm nhau tại x=9; dàn nằm trọn trong ban công thứ hai (cho phép)
    bals = [
        BalconyInfo("B01", Polygon([(5, 0), (9, 0), (9, 2), (5, 2)]), False),
        BalconyInfo("B02", Polygon([(9, 0), (13, 0), (13, 2), (9, 2)]), True),
    ]
    inside_b2 = _layout([OduPlacement("O", 10.0, 1.0, 0.0)])
    assert validate_layout(inside_b2, bals, 40, {"O": SIZE}) == []
    inside_b1 = _layout([OduPlacement("O", 7.0, 1.0, 0.0)])
    errs = _errors(validate_layout(inside_b1, bals, 40, {"O": SIZE}))
    assert len(errs) == 1 and "B01" in errs[0].message
    straddle = _layout([OduPlacement("O", 9.0, 1.0, 0.0)])  # nằm vắt qua hai ban công: không ban công nào chứa trọn
    assert "ngoài ban công" in _errors(validate_layout(straddle, bals, 40, {"O": SIZE}))[0].message


def test_empty_layout_has_no_problems():
    assert validate_layout(_layout([]), B, 40, {}) == []


def test_problem_levels_are_error_or_warning_and_messages_are_vietnamese_with_id():
    lay = _layout([OduPlacement("ODU-09", 15.0, 10.0, 0.0)])
    p = validate_layout(lay, B, 40, {"ODU-09": SIZE})[0]
    assert isinstance(p, Problem) and p.level in ("error", "warning") and "ODU-09" in p.message


def test_many_odus_scale():
    odus = [OduPlacement(f"O{i}", 5.5 + (i % 3) * 1.1, 0.5 + (i // 3) * 0.0, 0.0, floors=(i + 1,)) for i in range(30)]
    lay = Layout("t", "", "manual", (1,), tuple(odus))
    assert not _errors(validate_layout(lay, B, 40, {o.odu_id: SIZE for o in odus}))
