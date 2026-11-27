import ezdxf
import pytest
from dxf_factory import ODU_D, ODU_W, make_tower_dxf

from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.ingest.layers import classify_layers
from odu_cfd.ingest.odu_detect import detect_odus

VIEW = (-1.0, -1.0, 40.0, 30.0)


def _detect(path, view=VIEW, **kw):
    d = load_drawing(path)
    return detect_odus(d, view, classify_layers(d.layers), **kw)


def test_finds_four_units_and_excludes_enclosure(tower_dxf):
    odus, excluded = _detect(tower_dxf)
    assert [o.odu_id for o in odus] == ["ODU-01", "ODU-02", "ODU-03", "ODU-04"]
    assert odus[0].center == pytest.approx((5.99, 1.035))
    assert odus[3].center == pytest.approx((22.49, 1.035))
    assert odus[0].size == pytest.approx((ODU_W, ODU_D))
    assert [e.block for e in excluded] == ["ENCLOSURE"]
    assert excluded[0].odu_id == "X-01"


def test_units_outside_view_are_ignored(tower_dxf):
    odus, _ = _detect(tower_dxf, view=(-1.0, -1.0, 10.0, 30.0))
    assert [o.odu_id for o in odus] == ["ODU-01", "ODU-02"]


def _add(path, mutate):
    doc = ezdxf.readfile(path)
    mutate(doc, doc.modelspace())
    doc.saveas(path)


def test_duplicate_blocks_are_merged(tower_dxf):
    _add(tower_dxf, lambda doc, msp: msp.add_blockref(
        "ODU_TEST", (5500, 800), dxfattribs={"layer": "M-EQPM"}))
    odus, _ = _detect(tower_dxf)
    assert len(odus) == 4


def test_block_name_alone_is_enough(tower_dxf):
    def mutate(doc, msp):
        blk = doc.blocks.new("VRF mini")
        for a, b in [((0, 0), (980, 0)), ((980, 0), (980, 470)), ((980, 470), (0, 470)), ((0, 470), (0, 0))]:
            blk.add_line(a, b)
        msp.add_blockref("VRF mini", (10000, 10000), dxfattribs={"layer": "A-ANNO"})

    _add(tower_dxf, mutate)
    odus, _ = _detect(tower_dxf)
    assert len(odus) == 5
    assert any(o.block == "VRF mini" for o in odus)


def test_rotation_is_kept_and_size_is_unrotated(tower_dxf):
    _add(tower_dxf, lambda doc, msp: msp.add_blockref(
        "ODU_TEST", (30000, 15000), dxfattribs={"layer": "M-EQPM", "rotation": 90}))
    odus, _ = _detect(tower_dxf, view=(-1.0, -1.0, 40.0, 30.0))
    rot = [o for o in odus if o.rotation_deg == pytest.approx(90)]
    assert len(rot) == 1 and rot[0].size == pytest.approx((ODU_W, ODU_D))


def test_area_range_is_configurable(tower_dxf):
    odus, excluded = _detect(tower_dxf, area_range_m2=(0.2, 20.0))
    assert len(odus) == 5 and excluded == []


# ---- I6 ----


def test_rotation_comes_from_transformed_corners_for_mirrored_insert(tower_dxf):
    # extrusion (0,0,-1) lật trục X của OCS; góc thật trong WCS = 180 - 30 = 150, không phải dxf.rotation = 30
    _add(tower_dxf, lambda doc, msp: msp.add_blockref(
        "ODU_TEST", (30000, 15000),  # điểm chèn tính theo OCS
        dxfattribs={"layer": "M-EQPM", "rotation": 30, "extrusion": (0, 0, -1)}))
    odus, _ = _detect(tower_dxf, view=(-40.0, -1.0, 40.0, 30.0))
    got = [o for o in odus if o.center[0] < -20]
    assert len(got) == 1
    assert got[0].rotation_deg == pytest.approx(150.0, abs=1e-3)


def test_odu_nested_in_group_block_is_found(tower_dxf):
    def mutate(doc, msp):
        grp = doc.blocks.new("GROUP_A")
        grp.add_blockref("ODU_TEST", (0, 0), dxfattribs={"layer": "0"})
        grp.add_blockref("ODU_TEST", (2000, 0), dxfattribs={"layer": "0"})
        msp.add_blockref("GROUP_A", (30000, 10000), dxfattribs={"layer": "A-ANNO", "rotation": 90})

    _add(tower_dxf, mutate)
    odus, _ = _detect(tower_dxf)
    nested = [o for o in odus if o.center[1] > 9.0 and o.center[0] > 25.0]
    assert len(nested) == 2
    assert all(o.rotation_deg == pytest.approx(90.0, abs=1e-3) for o in nested)
    assert nested[0].size == pytest.approx((ODU_W, ODU_D))


def test_minsert_gives_every_copy(tower_dxf):
    _add(tower_dxf, lambda doc, msp: msp.add_blockref(
        "ODU_TEST", (10000, 12000),
        dxfattribs={"layer": "M-EQPM", "row_count": 2, "column_count": 3,
                    "row_spacing": 1500, "column_spacing": 2000}))
    odus, _ = _detect(tower_dxf)
    assert len(odus) == 4 + 6


def test_text_and_dimensions_do_not_inflate_footprint(tower_dxf):
    def mutate(doc, msp):
        blk = doc.blocks.new("ODU LABELED")
        for a, b in [((0, 0), (980, 0)), ((980, 0), (980, 370)), ((980, 370), (0, 370)), ((0, 370), (0, 0))]:
            blk.add_line(a, b)
        blk.add_text("ODU VRF MINI 990x980x370", dxfattribs={"insert": (0, 600), "height": 200})
        blk.add_point((3000, 3000))
        msp.add_blockref("ODU LABELED", (15000, 15000), dxfattribs={"layer": "M-EQPM"})

    _add(tower_dxf, mutate)
    odus, _ = _detect(tower_dxf)
    got = [o for o in odus if o.block == "ODU LABELED"]
    assert len(got) == 1 and got[0].size == pytest.approx((0.98, 0.37))
