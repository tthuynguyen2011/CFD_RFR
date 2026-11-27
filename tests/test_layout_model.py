import pytest

from odu_cfd.errors import ConfigError
from odu_cfd.layout.model import (
    ID_RE,
    NAME_RE,
    SOURCES,
    Layout,
    OduPlacement,
    format_floors,
    front_angle_deg,
    parse_floors,
)


def test_parse_floors_basic():
    assert parse_floors("4-19,22-23") == tuple(range(4, 20)) + (22, 23)


def test_parse_floors_tolerates_spaces():
    assert parse_floors(" 1 , 3-4 ") == (1, 3, 4)


@pytest.mark.parametrize("bad", ["3-1", "0", "a", "", "2,2", "1.5", "1,,2", "1-", "-3", "2-3,3-4", "  "])
def test_parse_floors_rejects(bad):
    with pytest.raises(ConfigError):
        parse_floors(bad)


def test_parse_floors_error_names_segment():
    with pytest.raises(ConfigError, match="3-1"):
        parse_floors("1,3-1")


def test_parse_floors_rejects_non_string():
    with pytest.raises(ConfigError):
        parse_floors(None)
    with pytest.raises(ConfigError):
        parse_floors(5)


def test_parse_floors_rejects_huge_range():
    with pytest.raises(ConfigError):
        parse_floors("1-99999999")


def test_format_floors():
    assert format_floors((1, 2, 3, 7)) == "1-3,7"
    assert format_floors((5,)) == "5"
    assert format_floors((4, 5, 6, 9)) == "4-6,9"
    assert format_floors((1, 3, 5)) == "1,3,5"
    assert format_floors((1, 2)) == "1-2"


def test_floors_roundtrip():
    for fl in [(1, 2, 3, 7), (4,), (1, 3, 5, 6, 7, 20)]:
        assert parse_floors(format_floors(fl)) == fl


@pytest.mark.parametrize("rot,exp", [(0, 90), (180, 270), (-90, 0), (270, 0), (360, 90), (-180, 270)])
def test_front_angle(rot, exp):
    assert front_angle_deg(OduPlacement("O", 0, 0, rot)) == pytest.approx(exp)


def test_front_angle_in_range():
    for rot in (-1e-12, 269.9999, -720.5, 1000):
        a = front_angle_deg(OduPlacement("O", 0, 0, rot))
        assert 0 <= a < 360


def test_floors_of():
    a = OduPlacement("A", 0, 0, 0)
    b = OduPlacement("B", 0, 0, 0, floors=(2,))
    lay = Layout("t", "", "manual", (1, 2, 3), (a, b))
    assert lay.floors_of(a) == (1, 2, 3)
    assert lay.floors_of(b) == (2,)


def test_constants():
    assert SOURCES == ("architect", "rule", "drawing", "manual")
    import re

    assert re.match(NAME_RE, "KT-v1.2") and not re.match(NAME_RE, "a b")
    assert re.match(ID_RE, "ODU-01") and not re.match(ID_RE, "ODU 01")


def test_frozen():
    p = OduPlacement("A", 0, 0, 0)
    with pytest.raises(Exception):
        p.x = 1
