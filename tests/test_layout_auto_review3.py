"""Hồi quy review chéo 3 cho auto_layout: hướng thổi từ cạnh hở (C1), trượt (I2), size_explicit (I3), làm tròn."""

import pytest
from shapely.geometry import Polygon

from odu_cfd.layout.auto import _out_direction, auto_layout
from odu_cfd.layout.balconies import BalconyInfo
from odu_cfd.layout.validate import odu_footprint

SIZE = (0.98, 0.37)
KW = dict(name="r", floors=(4,), size=SIZE)


def rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def blow(o):
    return (o.rotation_deg + 90.0) % 360.0


def inside(bal, o, size=SIZE):
    return bal.polygon.buffer(1e-3).contains(odu_footprint(o, size))


# ---- C1 ----
def test_c1_thin_outer_sliver_does_not_flip_direction():
    # đường bao rộng hơn ban công 5 mm: sau khi trừ ban công còn dải mỏng y in [-0.005, 0]
    bal = BalconyInfo("B01", rect(5, 0, 9, 2), True)
    body = rect(0, -0.005, 30, 20).difference(bal.polygon)
    lay, warns = auto_layout([bal], body, count=1, **KW)
    assert blow(lay.odus[0]) == pytest.approx(270.0)
    assert warns == []  # không rơi vào dự phòng: dải mỏng 5 mm đã bị mở bỏ, cạnh ngoài vẫn được coi là hở


def test_c1_deep_narrow_loggia_blows_along_long_axis():
    # loggia 1,6 (x) x 3 (y): hở ở y=0, lưng ở y=3, vách bên gần tâm hơn tường lưng
    bal = BalconyInfo("B01", rect(5, 0, 6.6, 3), True)
    body = rect(0, 0, 30, 20).difference(bal.polygon)
    lay, warns = auto_layout([bal], body, count=1, **KW)
    assert warns == [] and blow(lay.odus[0]) == pytest.approx(270.0)
    assert lay.odus[0].y == pytest.approx(3.0 - 0.2 - 0.185)  # dựa lưng y=3


def test_c1_deep_loggia_opening_towards_minus_x():
    bal = BalconyInfo("B01", rect(0, 5, 3, 6.6), True)
    body = rect(0, 0, 30, 20).difference(bal.polygon)
    lay, _ = auto_layout([bal], body, count=1, **KW)
    assert blow(lay.odus[0]) == pytest.approx(180.0)


def test_c1_projecting_balcony_outside_envelope():
    bal = BalconyInfo("B01", rect(5, -1.5, 9, 0), True)
    lay, _ = auto_layout([bal], rect(0, 0, 30, 20), count=1, **KW)
    assert blow(lay.odus[0]) == pytest.approx(270.0)
    assert lay.odus[0].y == pytest.approx(-0.2 - 0.185)


def test_c1_open_on_three_sides_blows_along_net_vector():
    bal = BalconyInfo("B01", rect(5, 0, 9, 2), True)
    body = rect(0, 2, 30, 20)  # chỉ giáp tường ở mép trên
    lay, _ = auto_layout([bal], body, count=1, **KW)
    assert blow(lay.odus[0]) == pytest.approx(270.0)


def test_c1_open_on_two_opposite_sides_uses_longest_open_edge():
    # dải 1 x 3 hở hai bên đối nhau (trái 3 m / phải 2 m không giáp) -> tổng khác 0 chứ không triệt tiêu hẳn;
    # dùng ca đối xứng hoàn toàn: cạnh trái và phải đều hở 3 m, đáy giáp tường, đỉnh giáp tường
    bal = BalconyInfo("B01", rect(5, 0, 6, 3), True)
    body = rect(0, 3, 30, 20).union(rect(0, -5, 30, 0))
    n, warn = _out_direction(bal, body)
    assert warn is None
    assert abs(n[0]) == pytest.approx(1.0) and abs(n[1]) == pytest.approx(0.0, abs=1e-9)
    assert _out_direction(bal, body)[0] == n  # tất định


def test_c1_length_weighting_matters():
    # bậc thang: 1 cạnh hở dài 3 m hướng -y và 4 cạnh hở ngắn (~0,4-0,5 m) xen kẽ +x / -y;
    # trung bình có trọng số chiều dài nghiêng hẳn về -y (ny < -0.93); không trọng số chỉ ~ -0.83
    bal = BalconyInfo(
        "B01", Polygon([(0, 0), (3, 0), (3, 0.5), (3.4, 0.5), (3.4, 1), (3.8, 1), (3.8, 3), (0, 3)]), True
    )
    body = rect(-5, 3, 30, 20).union(rect(-5, -5, 0, 3)).union(rect(3.8, 1, 30, 3))
    (nx, ny), warn = _out_direction(bal, body)
    assert warn is None and ny < -0.93 and nx > 0


def test_c1_enclosed_balcony_falls_back_with_warning():
    bal = BalconyInfo("B01", rect(5, 5, 9, 7), True)
    lay, warns = auto_layout([bal], rect(0, 0, 30, 20), count=1, **KW)
    assert any("B01" in w for w in warns)


# ---- I2 ----
def test_i2_l_shaped_balcony_places_by_sliding():
    # L: cánh ngang 4 x 1 (y 0..1) và cánh đứng x 0..1, y 1..3; tâm bbox rơi vào chỗ lõm
    bal = BalconyInfo("B01", Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]), True)
    body = rect(1, 1, 30, 20).union(rect(-5, 1, 0, 20)).union(rect(0, 3, 1, 20))
    lay, warns = auto_layout([bal], body, count=1, wall_gap_m=0.0, **KW)
    assert len(lay.odus) == 1
    assert inside(bal, lay.odus[0])
    assert not [w for w in warns if "không đặt được dàn nóng nào" in w]


def test_i2_l_shape_two_units_no_overlap():
    # dàn thứ hai không chồng dàn thứ nhất: dịch ra ngoài theo n khi hàng sát lưng không vừa
    bal = BalconyInfo("B01", Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]), True)
    body = rect(1, 1, 30, 20).union(rect(-5, 1, 0, 20)).union(rect(0, 3, 1, 20))
    lay, warns = auto_layout([bal], body, count=2, wall_gap_m=0.0, **KW)
    assert len(lay.odus) == 2 and all(inside(bal, o) for o in lay.odus) and warns == []
    f = [odu_footprint(o, SIZE) for o in lay.odus]
    assert f[0].intersection(f[1]).area < 1e-9


def test_i2_u_shaped_balcony_places():
    bal = BalconyInfo("B01", Polygon([(0, 0), (5, 0), (5, 2), (4, 2), (4, 1), (1, 1), (1, 2), (0, 2)]), True)
    body = rect(-5, 2, 30, 20).union(rect(1, 1, 4, 2))
    lay, _ = auto_layout([bal], body, count=1, wall_gap_m=0.0, **KW)
    assert len(lay.odus) == 1 and inside(bal, lay.odus[0])


def test_i2_deterministic():
    bal = BalconyInfo("B01", Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]), True)
    body = rect(1, 1, 30, 20).union(rect(-5, 1, 0, 20)).union(rect(0, 3, 1, 20))
    a = auto_layout([bal], body, count=3, pattern="grid", wall_gap_m=0.0, **KW)
    b = auto_layout([bal], body, count=3, pattern="grid", wall_gap_m=0.0, **KW)
    assert a == b


def test_i2_empty_layout_has_prominent_warning():
    bal = BalconyInfo("B01", rect(5, 0, 9, 2), True)
    lay, warns = auto_layout([bal], rect(0, 2, 30, 20), count=1, name="r", floors=(4,), size=(5.0, 3.0))
    assert lay.odus == () and any("không đặt được dàn nóng nào" in w for w in warns)


# ---- I3 ----
def test_i3_size_only_written_when_explicit():
    bal = BalconyInfo("B01", rect(5, 0, 9, 2), True)
    body = rect(0, 2, 30, 20)
    a, _ = auto_layout([bal], body, count=1, **KW)
    b, _ = auto_layout([bal], body, count=1, size_explicit=True, **KW)
    assert all(o.size is None for o in a.odus) and all(o.size == SIZE for o in b.odus)
    assert [(o.x, o.y) for o in a.odus] == [(o.x, o.y) for o in b.odus]


# ---- làm tròn ----
def test_values_rounded_to_6_decimals():
    bal = BalconyInfo("B01", rect(5, 0, 9, 2), True)
    body = rect(0, 2, 30, 20)
    lay, _ = auto_layout([bal], body, count=2, facing=240.00000000504428, **KW)
    for o in lay.odus:
        for v in (o.x, o.y, o.rotation_deg):
            assert round(v, 6) == v
        assert -180.0 < o.rotation_deg <= 180.0
    assert lay.odus[0].rotation_deg == 150.0


@pytest.mark.parametrize("facing", [-90.0, 270.0, -90.0 + 1e-9, 270.0 - 1e-9, 630.0])
def test_rotation_never_minus_180(facing):
    bal = BalconyInfo("B01", rect(5, 0, 9, 2), True)
    lay, _ = auto_layout([bal], rect(0, 2, 30, 20), count=1, facing=facing, **KW)
    assert -180.0 < lay.odus[0].rotation_deg <= 180.0
