import math

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from odu_cfd.errors import ConfigError
from odu_cfd.layout.auto import auto_layout
from odu_cfd.layout.balconies import BalconyInfo
from odu_cfd.layout.validate import odu_footprint, validate_layout

ENV = Polygon([(0, 0), (30, 0), (30, 20), (0, 20)])
BALS = [
    BalconyInfo("B01", Polygon([(5, 0), (9, 0), (9, 2), (5, 2)]), True),
    BalconyInfo("B02", Polygon([(20, 0), (24, 0), (24, 2), (20, 2)]), True),
]
BODY = ENV.difference(unary_union([b.polygon for b in BALS]))
SIZE = (0.98, 0.37)
KW = dict(name="r", floors=(4, 5), size=SIZE)


def test_row_of_two_back_to_wall_facing_out():
    lay, warns = auto_layout(BALS, BODY, count=2, **KW)
    assert warns == [] and [o.odu_id for o in lay.odus] == ["ODU-01", "ODU-02", "ODU-03", "ODU-04"]
    a, b = lay.odus[0], lay.odus[1]
    assert (a.x, a.y) == pytest.approx((6.46, 1.615)) and (b.x, b.y) == pytest.approx((7.54, 1.615))
    assert (a.rotation_deg % 360) == pytest.approx(180.0)  # mặt thổi (rotation+90) = 270 = hướng -y = ra ngoài
    assert lay.source == "rule" and a.size is None and lay.floors == (4, 5)
    assert not [p for p in validate_layout(lay, BALS, 40, {o.odu_id: SIZE for o in lay.odus}) if p.level == "error"]


def test_second_balcony_hand_computed():
    lay, _ = auto_layout(BALS, BODY, count=2, **KW)
    c, d = lay.odus[2], lay.odus[3]
    assert (c.x, c.y) == pytest.approx((21.46, 1.615)) and (d.x, d.y) == pytest.approx((22.54, 1.615))


def test_too_many_for_row_is_reduced_with_warning():
    lay, warns = auto_layout(BALS[:1], BODY, count=6, **KW)
    assert len(lay.odus) == 3 and any("B01" in w and "3/6" in w for w in warns)


def test_grid_fills_rows_from_wall_outwards():
    lay, _ = auto_layout(BALS[:1], BODY, count=4, pattern="grid", **KW)
    assert len(lay.odus) == 4
    rows = {}
    for o in lay.odus:
        rows.setdefault(round(o.y, 3), []).append(o)
    assert sorted(rows) == pytest.approx([1.145, 1.615]) and len(rows[1.615]) == 3 and len(rows[1.145]) == 1
    for o in lay.odus:
        assert BALS[0].polygon.buffer(1e-3).contains(odu_footprint(o, SIZE))


def test_grid_capacity_is_limited_with_warning():
    lay, warns = auto_layout(BALS[:1], BODY, count=100, pattern="grid", **KW)
    assert len(lay.odus) == 12 and any("12/100" in w for w in warns)  # 3 cột x 4 hàng
    errs = [p for p in validate_layout(lay, BALS, 40, {o.odu_id: SIZE for o in lay.odus}) if p.level == "error"]
    assert errs == []


def test_denied_and_small_balconies_are_skipped():
    bals = [BalconyInfo("B01", BALS[0].polygon, False), BALS[1]]
    lay, warns = auto_layout(bals, BODY, count=1, **KW)
    assert [round(o.x, 1) for o in lay.odus] == [22.0] and warns == []
    lay2, _ = auto_layout(BALS, BODY, count=1, min_area_m2=9.0, **KW)
    assert lay2.odus == ()


def test_only_ids_filter():
    lay, _ = auto_layout(BALS, BODY, count=1, only_ids=["B02"], **KW)
    assert len(lay.odus) == 1 and lay.odus[0].x > 20


def test_only_ids_naming_denied_balcony_warns_and_skips():
    bals = [BalconyInfo("B01", BALS[0].polygon, False), BALS[1]]
    lay, warns = auto_layout(bals, BODY, count=1, only_ids=["B01"], **KW)
    assert lay.odus == () and any("B01" in w and "không cho phép" in w for w in warns)


def test_only_ids_unknown_warns():
    lay, warns = auto_layout(BALS, BODY, count=1, only_ids=["B99", "B01"], **KW)
    assert len(lay.odus) == 1 and any("B99" in w for w in warns)


def test_numeric_facing_changes_rotation_only():
    lay, _ = auto_layout(BALS[:1], BODY, count=1, facing=0.0, **KW)  # thổi theo +x
    assert lay.odus[0].rotation_deg == pytest.approx(-90.0)
    assert lay.odus[0].y == pytest.approx(2.0 - 0.2 - 0.49)  # dựa lưng tường (y=2), nửa bề sâu theo y là w/2=0.49
    fp = odu_footprint(lay.odus[0], SIZE)
    assert BALS[0].polygon.buffer(1e-3).contains(fp)


def test_numeric_facing_hand_computed_row_of_three():
    # xoay -90: chiếm 0.37 (x) x 0.98 (y); ht = 0.185, cột cách 2*0.185+0.1 = 0.47; tâm t_mid = 7
    lay, warns = auto_layout(BALS[:1], BODY, count=3, facing=0.0, **KW)
    assert warns == []
    assert [o.x for o in lay.odus] == pytest.approx([6.53, 7.0, 7.47])
    assert all(o.y == pytest.approx(1.31) for o in lay.odus)


@pytest.mark.parametrize("facing,rot", [(270.0, 180.0), (90.0, 0.0), (180.0, 90.0), (360.0, -90.0), (-90.0, 180.0)])
def test_facing_to_rotation_normalised(facing, rot):
    lay, _ = auto_layout(BALS[:1], BODY, count=1, facing=facing, **KW)
    assert lay.odus[0].rotation_deg == pytest.approx(rot)
    assert -180 < lay.odus[0].rotation_deg <= 180


def test_oblique_facing_stays_inside_balcony():
    lay, warns = auto_layout(BALS[:1], BODY, count=2, facing=225.0, **KW)
    assert len(lay.odus) == 2
    for o in lay.odus:
        assert BALS[0].polygon.buffer(1e-3).contains(odu_footprint(o, SIZE))


def test_oversize_unit_is_dropped_with_warning():
    lay, warns = auto_layout(BALS[:1], BODY, count=1, name="r", floors=(4,), size=(5.0, 3.0))
    assert lay.odus == () and warns


def test_deterministic():
    a, _ = auto_layout(BALS, BODY, count=2, **KW)
    b, _ = auto_layout(list(reversed(BALS)), BODY, count=2, **KW)
    assert a == b


def test_works_when_balcony_projects_outside_the_envelope():
    proj = [BalconyInfo("B01", Polygon([(5, -2), (9, -2), (9, 0), (5, 0)]), True)]
    body = ENV  # ban công nhô ra phía y<0, tường tại y=0
    lay, warns = auto_layout(proj, body, count=1, **KW)
    o = lay.odus[0]
    assert o.y == pytest.approx(-0.2 - 0.185) and (o.rotation_deg % 360) == pytest.approx(180.0)


def test_empty_body_falls_back_to_short_axis_with_warning():
    lay, warns = auto_layout(BALS[:1], None, count=1, **KW)
    o = lay.odus[0]
    assert (o.x, o.y) == pytest.approx((7.0, 0.385)) and o.rotation_deg == pytest.approx(0.0)
    assert any("B01" in w for w in warns)
    lay2, warns2 = auto_layout(BALS[:1], Polygon(), count=1, **KW)
    assert lay2 == lay and warns2


def test_body_covering_centroid_falls_back_away_from_body_centre():
    lay, warns = auto_layout(BALS[:1], ENV, count=1, **KW)  # tâm ban công nằm trong body: vector 0
    o = lay.odus[0]
    assert (o.x, o.y) == pytest.approx((7.0, 1.615)) and (o.rotation_deg % 360) == pytest.approx(180.0)
    assert warns


def test_per_odu_floors_none_and_layout_floors_set():
    lay, _ = auto_layout(BALS, BODY, count=1, name="r", floors=[2, 3], size=SIZE, description="mô tả")
    assert lay.floors == (2, 3) and lay.description == "mô tả" and all(o.floors is None for o in lay.odus)


def test_unique_sequential_ids_across_balconies():
    lay, _ = auto_layout(BALS, BODY, count=3, **KW)
    assert [o.odu_id for o in lay.odus] == [f"ODU-{i:02d}" for i in range(1, 7)]


def test_ids_use_three_digits_when_over_99():
    many = [
        BalconyInfo(f"B{i:03d}", Polygon([(i * 10, 0), (i * 10 + 4, 0), (i * 10 + 4, 2), (i * 10, 2)]), True)
        for i in range(1, 101)
    ]
    body = ENV.difference(unary_union([b.polygon for b in many]))
    lay, _ = auto_layout(many, body, count=1, **KW)
    ids = [o.odu_id for o in lay.odus]
    assert len(ids) == 100 and ids[0] == "ODU-001" and ids[-1] == "ODU-100"


@pytest.mark.parametrize(
    "kw",
    [
        dict(count=0),
        dict(count=-1),
        dict(count=1.5),
        dict(pattern="spiral"),
        dict(facing="inward"),
        dict(facing=float("nan")),
        dict(wall_gap_m=-0.1),
        dict(spacing_m=float("inf")),
        dict(size=(0, 0.4)),
        dict(size=(1.0,)),
        dict(size=(float("nan"), 0.4)),
        dict(floors=()),
    ],
)
def test_bad_parameters_raise_config_error(kw):
    args = dict(KW, count=1)
    args.update(kw)
    with pytest.raises(ConfigError):
        auto_layout(BALS, BODY, **args)


def test_zero_spacing_and_wall_gap_flush_to_wall():
    lay, warns = auto_layout(BALS[:1], BODY, count=4, spacing_m=0.0, wall_gap_m=0.0, **KW)
    assert len(lay.odus) == 4 and warns == []
    assert lay.odus[0].y == pytest.approx(2.0 - 0.185)
    assert [o.x for o in lay.odus] == pytest.approx([5.53, 6.51, 7.49, 8.47])
    for o in lay.odus:
        assert BALS[0].polygon.buffer(1e-3).contains(odu_footprint(o, SIZE))


def test_nothing_placed_when_no_balconies():
    lay, warns = auto_layout([], BODY, count=1, **KW)
    assert lay.odus == () and any("không đặt được dàn nóng nào" in w for w in warns)
