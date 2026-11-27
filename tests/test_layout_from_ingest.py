import pytest
from shapely.geometry import Polygon

from odu_cfd.errors import ConfigError
from odu_cfd.ingest.odu_detect import OduInstance
from odu_cfd.layout.balconies import BalconyInfo
from odu_cfd.layout.from_ingest import layout_from_ingest

BALS = [
    BalconyInfo("B01", Polygon([(5, 0), (9, 0), (9, 2), (5, 2)]), True),
    BalconyInfo("B02", Polygon([(20, 0), (24, 0), (24, 2), (20, 2)]), True),
]


def _inst(i, x, y, rot=180.0, size=(0.98, 0.37)):
    return OduInstance(i, "BLK", "LYR", (x, y), size, rot)


FOUR = [
    _inst("ODU-01", 5.99, 1.035),
    _inst("ODU-02", 7.49, 1.035),
    _inst("ODU-03", 20.99, 1.035),
    _inst("ODU-04", 22.49, 1.035, 90.0),
]


def test_normal_case_no_warnings():
    lay, warns = layout_from_ingest(FOUR, BALS, name="bv", floors=(4, 5), description="từ bản vẽ")
    assert warns == []
    assert lay.source == "drawing" and lay.name == "bv" and lay.floors == (4, 5) and lay.description == "từ bản vẽ"
    assert [(o.odu_id, o.x, o.y, o.rotation_deg) for o in lay.odus] == [
        ("ODU-01", 5.99, 1.035, 180.0),
        ("ODU-02", 7.49, 1.035, 180.0),
        ("ODU-03", 20.99, 1.035, 180.0),
        ("ODU-04", 22.49, 1.035, 90.0),
    ]
    assert all(o.size is None and o.model_id is None and o.floors is None for o in lay.odus)


def test_outside_balcony_kept_with_warning():
    odus = FOUR + [_inst("ODU-05", 15.0, 10.0)]
    lay, warns = layout_from_ingest(odus, BALS, name="bv", floors=(1,))
    assert len(lay.odus) == 5 and lay.odus[4].odu_id == "ODU-05"
    assert warns == ["ODU-05 không rơi vào ban công nào"]


def test_in_denied_balcony_warns():
    bals = [BalconyInfo("B01", BALS[0].polygon, False), BALS[1]]
    lay, warns = layout_from_ingest(FOUR, bals, name="bv", floors=(1,))
    assert len(lay.odus) == 4 and len(warns) == 2 and all("B01" in w and "không cho phép" in w for w in warns)


def test_empty_gives_empty_layout():
    lay, warns = layout_from_ingest([], BALS, name="bv", floors=(1,))
    assert lay.odus == () and warns == []


def test_bad_or_duplicate_ids_are_sanitised_uniquely():
    odus = [_inst("odu 1", 6.0, 1.0), _inst("ODU-01", 7.0, 1.0), _inst("ODU-01", 8.0, 1.0), _inst("", 21.0, 1.0)]
    lay, _ = layout_from_ingest(odus, BALS, name="bv", floors=(1,))
    ids = [o.odu_id for o in lay.odus]
    assert len(set(ids)) == 4 and "ODU-01" in ids
    import re

    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+", i) for i in ids)


def test_does_not_use_drawing_size():
    lay, _ = layout_from_ingest([_inst("ODU-01", 6.0, 1.0, size=(3.0, 3.0))], BALS, name="bv", floors=(1,))
    assert lay.odus[0].size is None


def test_roundtrips_through_io_and_floors_validation(tmp_path):
    from odu_cfd.layout.io import layout_path, read_layout, write_layout

    lay, _ = layout_from_ingest(FOUR, BALS, name="bv", floors=(4, 5, 6))
    p = layout_path(tmp_path, "bv")
    write_layout(p, lay)
    assert read_layout(p) == lay


def test_bad_floors_raise():
    with pytest.raises(ConfigError):
        layout_from_ingest(FOUR, BALS, name="bv", floors=())
