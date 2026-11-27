# tests/test_geometry_build.py
import pytest
from shapely.geometry import LineString, Polygon

from odu_cfd.geometry.build import build_building
from odu_cfd.geometry.mesh import bounds
from odu_cfd.geometry.plan2d import Plan2D
from odu_cfd.ingest.odu_detect import OduInstance
from odu_cfd.schema import BuildingConfig, GeometryConfig


def _plan():
    return Plan2D(
        envelope=Polygon([(0, 0), (30, 0), (30, 20), (0, 20)]),
        balconies=(
            Polygon([(5, 0), (9, 0), (9, 2), (5, 2)]),
            Polygon([(20, 0), (24, 0), (24, 2), (20, 2)]),
        ),
        rails=(LineString([(5, 0), (9, 0)]), LineString([(20, 0), (24, 0)])),
        columns=(),
    )


def _odu(i, x, y):
    return OduInstance(f"ODU-{i:02d}", "B", "M-EQPM", (x, y), (0.98, 0.47), 0.0)


ODUS = [_odu(1, 5.99, 1.0), _odu(2, 7.49, 1.0), _odu(3, 20.99, 1.0)]


def _build(odus=ODUS, floors=3):
    return build_building(_plan(), BuildingConfig(floors, 3.3), GeometryConfig(), odus)


def test_building_volume_and_bounds():
    m = _build()
    (name, mesh), = m.groups["building"].items()
    from odu_cfd.geometry.mesh import volume

    assert volume(mesh) == pytest.approx((600 - 16) * 9.9)
    assert bounds(mesh)[2] == pytest.approx(0.0) and bounds(mesh)[5] == pytest.approx(9.9)


def test_slabs_and_rails_per_floor():
    from odu_cfd.geometry.mesh import volume

    m = _build()
    assert volume(m.groups["balcony"]["balcony_slabs"]) == pytest.approx(16 * 0.15 * 3)
    assert volume(m.groups["rail"]["rails"]) == pytest.approx(2 * 4 * 0.05 * 1.1 * 3)


def test_odu_regions_per_floor_and_height():
    m = _build()
    names = sorted(m.groups["odu"])
    assert len(names) == 9 and names[0] == "ODU-01_f00" and names[-1] == "ODU-03_f02"
    b = bounds(m.groups["odu"]["ODU-01_f00"])
    assert (b[2], b[5]) == pytest.approx((0.15, 1.15))
    b2 = bounds(m.groups["odu"]["ODU-01_f02"])
    assert (b2[2], b2[5]) == pytest.approx((0.15 + 6.6, 1.15 + 6.6))


def test_odu_height_override():
    m = build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), ODUS, odu_height_m=0.8)
    b = bounds(m.groups["odu"]["ODU-01_f00"])
    assert b[5] - b[2] == pytest.approx(0.8)


def test_summary_and_all_closed():
    s = _build().summary()
    assert s["num_floors"] == 3 and s["height_m"] == pytest.approx(9.9)
    assert s["envelope_area_m2"] == pytest.approx(600.0)
    assert all(p["closed"] for p in s["parts"].values())
    assert s["parts"]["odu"]["regions"] == 9
    assert s["warnings"] == []


def test_odu_outside_balcony_is_warned():
    s = _build(odus=[_odu(1, 15.0, 10.0)]).summary()
    assert any("ODU-01" in w and "ngoài ban công" in w for w in s["warnings"])


# ---- trường hợp biên ----
from shapely.geometry import MultiPolygon

from odu_cfd.geometry.mesh import is_closed, volume


def _plan_with(balconies, envelope=None, rails=()):
    env = envelope or Polygon([(0, 0), (30, 0), (30, 20), (0, 20)])
    return Plan2D(env, tuple(balconies), tuple(rails), ())


def test_protruding_balcony_is_not_subtracted_beyond_envelope():
    # ban công nhô ra ngoài: y từ -2 đến 2, chỉ phần y>=0 nằm trong đường bao
    plan = _plan_with([Polygon([(5, -2), (9, -2), (9, 2), (5, 2)])])
    m = build_building(plan, BuildingConfig(1, 3.3), GeometryConfig(), [])
    assert volume(m.groups["building"]["building"]) == pytest.approx((600 - 8) * 3.3)
    assert volume(m.groups["balcony"]["balcony_slabs"]) == pytest.approx(16 * 0.15)
    assert all(p["closed"] for p in m.summary()["parts"].values())


def test_balcony_outside_envelope_leaves_building_intact():
    plan = _plan_with([Polygon([(50, 50), (54, 50), (54, 52), (50, 52)])])
    m = build_building(plan, BuildingConfig(2, 3.0), GeometryConfig(), [])
    assert volume(m.groups["building"]["building"]) == pytest.approx(600 * 6.0)
    assert m.summary()["warnings"] == []


def test_balcony_splitting_building_gives_valid_multipolygon():
    # dải ban công cắt đôi đường bao
    plan = _plan_with([Polygon([(14, -1), (16, -1), (16, 21), (14, 21)])])
    m = build_building(plan, BuildingConfig(1, 3.0), GeometryConfig(), [])
    assert volume(m.groups["building"]["building"]) == pytest.approx((600 - 40) * 3.0)
    assert m.summary()["parts"]["building"]["closed"]


def test_envelope_multipolygon_and_hole_survive():
    env = MultiPolygon(
        [
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(4, 4), (6, 4), (6, 6), (4, 6)]]),
            Polygon([(20, 0), (30, 0), (30, 10), (20, 10)]),
        ]
    )
    m = build_building(_plan_with([], envelope=env), BuildingConfig(1, 3.0), GeometryConfig(), [])
    assert volume(m.groups["building"]["building"]) == pytest.approx((96 + 100) * 3.0)
    assert is_closed(m.groups["building"]["building"])


def test_tiny_envelope_is_warned():
    plan = _plan_with([], envelope=Polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)]))
    m = build_building(plan, BuildingConfig(1, 3.0), GeometryConfig(), [])
    assert any("đường bao" in w for w in m.summary()["warnings"])


def test_no_balconies_no_rails_groups_empty():
    m = build_building(_plan_with([]), BuildingConfig(1, 3.0), GeometryConfig(), [])
    s = m.summary()
    assert s["parts"]["balcony"]["regions"] == 0 and s["parts"]["rail"]["regions"] == 0


# ---- I7, I6, m3, m6, I8 ----
import math

from odu_cfd.errors import IngestError
from odu_cfd.geometry.mesh import box
from odu_cfd.geometry.mesh import bounds as _bounds


def test_rails_start_at_slab_top():
    m = _build(floors=2)
    b = _bounds(m.groups["rail"]["rails"])
    assert b[2] == pytest.approx(0.15)
    assert b[5] == pytest.approx(3.3 + 0.15 + 1.1)


def test_box_rotation_direction_is_ccw():
    m = box(10.0, 10.0, 2.0, 1.0, 30.0, 0.0, 1.0)
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    expected = (10 + (-1) * c - (-0.5) * s, 10 + (-1) * s + (-0.5) * c)  # góc (-w/2, -d/2)
    top = m.vertices[m.vertices[:, 2] == 1.0][:, :2]
    assert any(abs(p[0] - expected[0]) < 1e-6 and abs(p[1] - expected[1]) < 1e-6 for p in top)


def test_rail_is_trimmed_by_building_body():
    from odu_cfd.geometry.mesh import volume

    # lan can nằm trên mép ban công: nửa dày nằm trong khối nhà (y>=2 ban công kết thúc), nửa trong ban công
    plan = _plan_with(
        [Polygon([(5, 0), (9, 0), (9, 2), (5, 2)])],
        rails=[LineString([(5, 2), (9, 2)])],
    )
    m = build_building(plan, BuildingConfig(1, 3.3), GeometryConfig(), [])
    # chỉ nửa phía ban công (y từ 1.975 đến 2) còn lại
    assert volume(m.groups["rail"]["rails"]) == pytest.approx(4 * 0.025 * 1.1)
    # khối nhà và lan can không chồng thể tích
    assert volume(m.groups["building"]["building"]) == pytest.approx((600 - 8) * 3.3)


def test_rail_inside_building_is_warned_when_lost():
    plan = _plan_with([], rails=[LineString([(5, 10), (9, 10)])])
    m = build_building(plan, BuildingConfig(1, 3.3), GeometryConfig(), [])
    assert any("lan can" in w for w in m.warnings)


def test_odu_overlapping_building_is_warned():
    odu = OduInstance("ODU-09", "B", "M", (10.0, 10.0), (1.0, 1.0), 0.0)
    m = build_building(_plan_with([]), BuildingConfig(1, 3.3), GeometryConfig(), [odu])
    assert any("ODU-09" in w and "khối nhà" in w for w in m.warnings)


def test_odu_overlapping_rail_is_warned():
    plan = _plan_with(
        [Polygon([(5, 0), (9, 0), (9, 2), (5, 2)])], rails=[LineString([(5, 1.0), (9, 1.0)])]
    )
    odu = OduInstance("ODU-07", "B", "M", (7.0, 1.0), (1.0, 0.5), 0.0)
    m = build_building(plan, BuildingConfig(1, 3.3), GeometryConfig(), [odu])
    assert any("ODU-07" in w and "lan can" in w for w in m.warnings)


def test_odu_touching_only_is_not_warned():
    odu = OduInstance("ODU-08", "B", "M", (7.0, 1.0), (1.0, 0.5), 0.0)  # trong ban công, không chạm
    m = build_building(_plan_with([Polygon([(5, 0), (9, 0), (9, 2), (5, 2)])]), BuildingConfig(1, 3.3), GeometryConfig(), [odu])
    assert m.warnings == ()


def test_odu_through_upper_slab_is_error():
    odu = OduInstance("ODU-01", "B", "M", (7.0, 1.0), (1.0, 0.5), 0.0)
    plan = _plan_with([Polygon([(5, 0), (9, 0), (9, 2), (5, 2)])])
    with pytest.raises(IngestError, match="tầng"):
        build_building(plan, BuildingConfig(2, 3.0), GeometryConfig(), [odu], odu_height_m=3.2)


def test_rail_taller_than_floor_is_error():
    plan = _plan_with([Polygon([(5, 0), (9, 0), (9, 2), (5, 2)])], rails=[LineString([(5, 0), (9, 0)])])
    with pytest.raises(IngestError, match="lan can"):
        build_building(plan, BuildingConfig(2, 1.2), GeometryConfig(), [])


def test_odu_size_override_keeps_center_and_rotation():
    odu = OduInstance("ODU-01", "B", "M", (6.0, 1.0), (0.98, 1.02), 90.0)
    m = build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), [odu], odu_size_override=(1.0, 0.4))
    b = _bounds(m.groups["odu"]["ODU-01_f00"])
    assert (b[3] - b[0], b[4] - b[1]) == pytest.approx((0.4, 1.0))  # xoay 90 độ
    assert ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2) == pytest.approx((6.0, 1.0))
    assert m.odu_sizes["ODU-01"] == {"size": (1.0, 0.4), "size_source": "library"}


def test_odu_size_source_drawing_by_default():
    m = _build()
    assert m.odu_sizes["ODU-01"] == {"size": (0.98, 0.47), "size_source": "drawing"}


def test_filled_hole_is_warned_and_summary_has_origin():
    plan = Plan2D(
        Polygon([(0, 0), (30, 0), (30, 20), (0, 20)]), (), (), (), filled_holes_m2=36.0
    )
    m = build_building(plan, BuildingConfig(1, 3.3), GeometryConfig(), [])
    assert any("lấp" in w and "36" in w for w in m.warnings)
    s = m.summary()
    assert s["origin_xy_m"] == pytest.approx([15.0, 10.0])
    assert "coordinate_note" in s


def test_small_filled_hole_not_warned():
    plan = Plan2D(Polygon([(0, 0), (30, 0), (30, 20), (0, 20)]), (), (), (), filled_holes_m2=2.0)
    assert build_building(plan, BuildingConfig(1, 3.3), GeometryConfig(), []).warnings == ()


def test_unclosed_region_is_error(monkeypatch):
    import odu_cfd.geometry.build as bld

    monkeypatch.setattr(bld, "is_closed", lambda mesh: False)
    with pytest.raises(IngestError, match="không kín"):
        build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), [])


# ---- Giai đoạn 2c: dựng theo phương án (tầng, chiều cao, nguồn kích thước theo từng dàn) ----
def test_odu_floors_limit_regions_and_z():
    odus = [_odu(1, 6.0, 1.0)]
    m = build_building(
        _plan(), BuildingConfig(6, 3.3), GeometryConfig(), odus, odu_floors={"ODU-01": (3, 4)}
    )
    assert sorted(m.groups["odu"]) == ["ODU-01_f03", "ODU-01_f04"]
    b = bounds(m.groups["odu"]["ODU-01_f03"])
    assert b[2] == pytest.approx(3 * 3.3 + 0.15)


def test_odu_floors_none_means_all_floors_and_missing_id_means_all():
    m = build_building(_plan(), BuildingConfig(2, 3.3), GeometryConfig(), [_odu(1, 6.0, 1.0), _odu(2, 7.5, 1.0)],
                       odu_floors={"ODU-01": (1,)})
    assert sorted(m.groups["odu"]) == ["ODU-01_f01", "ODU-02_f00", "ODU-02_f01"]


@pytest.mark.parametrize("bad", [(2,), (-1,), (0, 5)])
def test_odu_floors_out_of_range_is_error(bad):
    with pytest.raises(IngestError, match="tầng"):
        build_building(_plan(), BuildingConfig(2, 3.3), GeometryConfig(), [_odu(1, 6.0, 1.0)],
                       odu_floors={"ODU-01": bad})


def test_odu_heights_per_odu():
    odus = [_odu(1, 6.0, 1.0), _odu(2, 7.5, 1.0)]
    m = build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), odus, odu_heights={"ODU-01": 0.8, "ODU-02": 1.5})
    assert bounds(m.groups["odu"]["ODU-01_f00"])[5] == pytest.approx(0.15 + 0.8)
    assert bounds(m.groups["odu"]["ODU-02_f00"])[5] == pytest.approx(0.15 + 1.5)


def test_odu_heights_missing_id_uses_default():
    m = build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), [_odu(1, 6.0, 1.0)], odu_heights={})
    assert bounds(m.groups["odu"]["ODU-01_f00"])[5] == pytest.approx(0.15 + GeometryConfig().odu_default_height_m)


def test_odu_heights_one_too_tall_is_error():
    odus = [_odu(1, 6.0, 1.0), _odu(2, 7.5, 1.0)]
    with pytest.raises(IngestError, match="tầng"):
        build_building(_plan(), BuildingConfig(2, 3.3), GeometryConfig(), odus, odu_heights={"ODU-02": 3.3})


def test_odu_size_sources_are_recorded():
    odus = [_odu(1, 6.0, 1.0), _odu(2, 7.5, 1.0)]
    m = build_building(_plan(), BuildingConfig(1, 3.3), GeometryConfig(), odus,
                       odu_size_sources={"ODU-01": "layout", "ODU-02": "default"})
    assert m.odu_sizes["ODU-01"]["size_source"] == "layout"
    assert m.odu_sizes["ODU-02"]["size_source"] == "default"


def test_three_digit_odu_ids_make_unique_region_names():
    from odu_cfd.geometry.export import check_region_names

    odus = [OduInstance(f"ODU-{i:03d}", "B", "L", (5.5 + 0.01 * i, 1.0), (0.01, 0.01), 0.0) for i in (1, 2, 100)]
    m = build_building(_plan(), BuildingConfig(2, 3.3), GeometryConfig(), odus)
    check_region_names(m.groups["odu"])
    assert "ODU-100_f01" in m.groups["odu"] and "ODU-001_f00" in m.groups["odu"]


def test_sliver_walls_are_removed_and_warned(tmp_path):
    from odu_cfd.geometry.export import write_stl
    from odu_cfd.geometry.mesh import volume

    plan = Plan2D(
        envelope=Polygon([(0, 0), (30, 0), (30, 20), (0, 20)]),
        balconies=(Polygon([(0.005, 5), (4, 5), (4, 9), (0.005, 9)]),),  # thụt vào 5 mm so với mép trái
        rails=(),
        columns=(),
    )
    m = build_building(plan, BuildingConfig(2, 3.0), GeometryConfig(), [])
    mesh = m.groups["building"]["building"]
    assert volume(mesh) == pytest.approx((600 - 16) * 6.0, rel=1e-6)
    # không còn tam giác nào nằm trọn trong mặt phẳng x = 0 (vách mỏng dọc mép trái ban công)
    for f in mesh.faces:
        xs = [mesh.vertices[i][0] for i in f]
        assert not (max(xs) - min(xs) < 1e-9 and abs(xs[0]) < 1e-9 and
                    min(mesh.vertices[i][1] for i in f) > 4.9 and max(mesh.vertices[i][1] for i in f) < 9.1)
    assert any("mảnh tường mỏng" in w and "12 cm" in w for w in m.warnings)


def test_sliver_removal_keeps_convex_corners_sharp():
    from odu_cfd.geometry.mesh import bounds

    m = _build()
    b = m.groups["building"]["building"]
    xs = {round(float(v[0]), 9) for v in b.vertices}
    ys = {round(float(v[1]), 9) for v in b.vertices}
    assert {0.0, 30.0} <= xs and {0.0, 20.0} <= ys
    assert bounds(b)[:2] == pytest.approx((0.0, 0.0)) and bounds(b)[3:5] == pytest.approx((30.0, 20.0))
    assert not any("mảnh tường mỏng" in w for w in m.warnings)


def test_open_body_helper_reports_dropped_area():
    from odu_cfd.geometry.build import open_body

    env = Polygon([(0, 0), (30, 0), (30, 20), (0, 20)])
    bal = Polygon([(10, 0.005), (14, 0.005), (14, 2), (10, 2)])
    body, dropped, n = open_body(env, bal)
    assert body.area == pytest.approx(600 - 4 * 2, abs=1e-6)
    assert dropped == pytest.approx(4 * 0.005, rel=1e-3) and n == 1
