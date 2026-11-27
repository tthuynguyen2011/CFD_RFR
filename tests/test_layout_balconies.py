import os
import random

import pytest
import yaml
from shapely.geometry import Polygon

from odu_cfd.errors import ConfigError
from odu_cfd.layout.balconies import (
    BalconyInfo,
    number_balconies,
    read_balconies,
    set_allowed,
    write_balconies,
)


def rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_number_orders_by_y_then_x():
    polys = [rect(10, 5, 12, 6), rect(0, 5, 2, 6), rect(50, 0, 52, 1)]
    out = number_balconies(polys)
    assert [i for i, _ in out] == ["B01", "B02", "B03"]
    assert out[0][1].equals(polys[2])  # y thấp nhất
    assert out[1][1].equals(polys[1])  # cùng y, x nhỏ trước
    assert out[2][1].equals(polys[0])


def test_number_is_stable_under_input_order():
    rnd = random.Random(1)
    polys = [rect(x, y, x + 2, y + 1) for x in range(0, 30, 5) for y in range(0, 20, 4)]
    ref = [(i, p.wkt) for i, p in number_balconies(polys)]
    for _ in range(5):
        rnd.shuffle(polys)
        assert [(i, p.wkt) for i, p in number_balconies(polys)] == ref


def test_number_digit_width():
    assert number_balconies([rect(i * 3, 0, i * 3 + 1, 1) for i in range(5)])[0][0] == "B01"
    ids = [i for i, _ in number_balconies([rect(i * 3, 0, i * 3 + 1, 1) for i in range(100)])]
    assert ids[0] == "B001" and ids[-1] == "B100"
    ids = [i for i, _ in number_balconies([rect(i * 3, 0, i * 3 + 1, 1) for i in range(99)])]
    assert ids[0] == "B01" and ids[-1] == "B99"
    assert number_balconies([]) == []


def test_write_read_roundtrip(tmp_path):
    polys = [rect(5.123456789, 0.1, 9.987654321, 2.2), rect(20, 0, 24, 2)]
    infos = write_balconies(tmp_path, polys)
    back = read_balconies(tmp_path)
    assert [b.balcony_id for b in back] == ["B01", "B02"] == [b.balcony_id for b in infos]
    for a, b in zip(infos, back):
        assert a.polygon.equals_exact(b.polygon, 1e-9)
        assert b.allowed is True and b.note == ""
    src = polys[0]  # B02 (y=0.1 cao hơn y=0)
    assert back[1].polygon.area == pytest.approx(src.area, abs=1e-9)
    assert back[1].polygon.centroid.x == pytest.approx(src.centroid.x, abs=1e-9)
    assert max(abs(a - b) for a, b in zip(back[1].polygon.bounds, src.bounds)) < 1e-9


def test_file_has_header_comment_and_data(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 4, 2)])
    text = (tmp_path / "balconies.yaml").read_text(encoding="utf-8")
    assert text.lstrip().startswith("#") and "allowed" in text.split("balconies:")[0]
    data = yaml.safe_load(text)["balconies"][0]
    assert data["id"] == "B01" and data["area_m2"] == pytest.approx(8.0)
    assert data["centroid"] == pytest.approx([2.0, 1.0]) and data["allowed"] is True


def test_rewrite_keeps_flags_by_centroid_even_if_ids_shift(tmp_path):
    a, b, c = rect(0, 0, 2, 1), rect(10, 0, 12, 1), rect(20, 0, 22, 1)
    write_balconies(tmp_path, [a, b, c])
    set_allowed(tmp_path, denied_ids=["B02"])
    p = tmp_path / "balconies.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["balconies"][1]["note"] = "ghi chú"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    # thêm ban công mới ở giữa (x=5) và nhích ban công cũ 0.3 m; B02 cũ thành B03
    new = rect(5, 0, 7, 1)
    b_moved = rect(10.3, 0, 12.3, 1)
    out = write_balconies(tmp_path, [a, new, b_moved, c])
    by_id = {x.balcony_id: x for x in out}
    assert by_id["B03"].allowed is False and by_id["B03"].note == "ghi chú"
    assert by_id["B02"].allowed is True and by_id["B02"].note == ""
    assert by_id["B01"].allowed and by_id["B04"].allowed
    assert [x.allowed for x in read_balconies(tmp_path)] == [True, True, False, True]


def test_rewrite_far_balcony_does_not_inherit(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    set_allowed(tmp_path, denied_ids=["B01"])
    out = write_balconies(tmp_path, [rect(0.6, 0, 2.6, 1)])  # tâm lệch 0.6 >= 0.5
    assert out[0].allowed is True


def test_rewrite_one_old_flag_not_reused_twice(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    set_allowed(tmp_path, denied_ids=["B01"])
    out = write_balconies(tmp_path, [rect(0.0, 0, 2, 1), rect(0.2, 2, 2.2, 3)])
    assert [x.allowed for x in out] == [False, True]


def test_rewrite_disappeared_old_balcony_is_dropped(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1), rect(10, 0, 12, 1)])
    set_allowed(tmp_path, denied_ids=["B02"])
    out = write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    assert len(out) == 1 and len(read_balconies(tmp_path)) == 1


def test_set_allowed_basic(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1), rect(10, 0, 12, 1), rect(20, 0, 22, 1)])
    out = set_allowed(tmp_path, denied_ids=["B01", "B03"])
    assert [b.allowed for b in out] == [False, True, False]
    out = set_allowed(tmp_path, allowed_ids=["B03"])
    assert [b.allowed for b in out] == [False, True, True]
    assert [b.allowed for b in read_balconies(tmp_path)] == [False, True, True]
    out = set_allowed(tmp_path, all_allowed=True)
    assert all(b.allowed for b in out)
    out = set_allowed(tmp_path, all_allowed=True, denied_ids=["B02"])
    assert [b.allowed for b in out] == [True, False, True]


def test_set_allowed_unknown_id_lists_valid_ids_and_changes_nothing(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1), rect(10, 0, 12, 1)])
    before = (tmp_path / "balconies.yaml").read_bytes()
    with pytest.raises(ConfigError) as ei:
        set_allowed(tmp_path, allowed_ids=["B01"], denied_ids=["B99"])
    assert "B99" in str(ei.value) and "B01" in str(ei.value) and "B02" in str(ei.value)
    assert (tmp_path / "balconies.yaml").read_bytes() == before


def test_set_allowed_same_id_both_lists_rejected(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    with pytest.raises(ConfigError):
        set_allowed(tmp_path, allowed_ids=["B01"], denied_ids=["B01"])


def test_read_missing_file_points_to_geometry(tmp_path):
    with pytest.raises(ConfigError, match="odu-cfd geometry"):
        read_balconies(tmp_path)
    with pytest.raises(ConfigError, match="odu-cfd geometry"):
        set_allowed(tmp_path, all_allowed=True)


@pytest.mark.parametrize(
    "body",
    [
        "balconies: 5\n",
        "balconies: [{id: B01, polygon: [[0,0],[1,0]], allowed: true}]\n",
        "balconies: [{id: 'x y', polygon: [[0,0],[1,0],[1,1]], allowed: true}]\n",
        "balconies: [{id: B01, polygon: [[0,0],[1,0],[1,1]], allowed: 'yes'}]\n",
        "balconies: [{id: B01, polygon: [[0,0],[1,0],[.nan,1]], allowed: true}]\n",
        "balconies: [{id: B01, polygon: [[0,0],[1,0],[1,1]]}, {id: B01, polygon: [[0,0],[1,0],[1,1]]}]\n",
        "balconies: [{id: B01, polygon: [[0,0],[1,1],[1,0],[0,1]], allowed: true}]\n",
        "not: [valid",
    ],
)
def test_read_rejects_bad_file(tmp_path, body):
    (tmp_path / "balconies.yaml").write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError):
        read_balconies(tmp_path)


def test_write_leaves_no_temp_files_and_keeps_utf8_note(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    p = tmp_path / "balconies.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["balconies"][0]["note"] = "Ban công kiến trúc không cho phép"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    assert read_balconies(tmp_path)[0].note == "Ban công kiến trúc không cho phép"
    assert sorted(os.listdir(tmp_path)) == ["balconies.yaml"]


def test_write_rejects_empty_polygon(tmp_path):
    with pytest.raises(ConfigError):
        write_balconies(tmp_path, [Polygon()])
    assert not (tmp_path / "balconies.yaml").exists()


def test_write_empty_list(tmp_path):
    assert write_balconies(tmp_path, []) == []
    assert read_balconies(tmp_path) == []


def test_balconyinfo_defaults():
    b = BalconyInfo("B01", rect(0, 0, 1, 1))
    assert b.allowed is True and b.note == ""
