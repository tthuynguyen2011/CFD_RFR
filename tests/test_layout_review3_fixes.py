"""Hồi quy review chéo 3: cảnh báo mất cờ ban công (I1), tên phương án (M2/M3), check_layout (M4)."""

import pytest
import yaml
from shapely.geometry import Polygon

from odu_cfd.errors import ConfigError
from odu_cfd.layout.balconies import read_balconies, set_allowed, write_balconies
from odu_cfd.layout.io import check_layout, layout_path, list_layouts, layouts_dir, write_layout
from odu_cfd.layout.model import Layout, OduPlacement


def rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# ---- I1 ----
def test_lost_denied_flag_warns(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1), rect(10, 0, 12, 1)])
    set_allowed(tmp_path, denied_ids=["B02"])
    w = []
    out = write_balconies(tmp_path, [rect(0, 0, 2, 1), rect(11, 0, 13, 1)], warnings=w)  # tâm lệch 1 m
    assert [b.allowed for b in out] == [True, True]
    assert len(w) == 1 and "B02" in w[0] and "11.000" in w[0] and "bị mất cờ không cho phép/ghi chú" in w[0]


def test_lost_note_warns_and_kept_flag_does_not(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1), rect(10, 0, 12, 1)])
    p = tmp_path / "balconies.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["balconies"][0]["note"] = "giữ"
    d["balconies"][1]["note"] = "mất"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    w = []
    write_balconies(tmp_path, [rect(0.1, 0, 2.1, 1), rect(20, 0, 22, 1)], warnings=w)
    assert len(w) == 1 and "B02" in w[0] and "mất" in w[0]


def test_default_flags_lost_do_not_warn_and_signature_kept(tmp_path):
    write_balconies(tmp_path, [rect(0, 0, 2, 1)])
    w = []
    out = write_balconies(tmp_path, [rect(50, 0, 52, 1)], warnings=w)
    assert w == [] and len(out) == 1
    assert len(read_balconies(tmp_path)) == 1
    write_balconies(tmp_path, [rect(50, 0, 52, 1)])  # không truyền warnings vẫn chạy


# ---- M2/M3 ----
@pytest.mark.parametrize(
    "bad",
    ["CON", "con", "Prn", "AUX", "nul", "COM1", "com9", "LPT1", "lpt9", "con.txt", "NUL.v1", "aux.x.y", "abc.", "-rf", "-", "x..", "a-b."],
)
def test_bad_names_rejected(tmp_path, bad):
    with pytest.raises(ConfigError) as e:
        layout_path(tmp_path, bad)
    assert "tên phương án" in str(e.value)


@pytest.mark.parametrize("good", ["KT-v1", "KT-v1.2", "console", "com10", "COM0", "lpt", "a-b", "A_1", "x.con"])
def test_good_names_accepted(tmp_path, good):
    assert layout_path(tmp_path, good).name == f"{good}.yaml"


def test_parse_layout_rejects_reserved_name_in_content():
    from odu_cfd.layout.io import _parse_layout

    with pytest.raises(ConfigError):
        _parse_layout({"name": "CON", "source": "manual", "floors": "1", "odus": []}, None)


def test_list_layouts_skips_reserved_stems(tmp_path):
    d = layouts_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "ok.yaml").write_text("x", encoding="utf-8")
    (d / "console.yaml").write_text("x", encoding="utf-8")
    assert list_layouts(tmp_path) == ["console", "ok"]


def test_write_layout_rejects_reserved_name(tmp_path):
    with pytest.raises(ConfigError):
        write_layout(tmp_path / "layouts" / "NUL.yaml", Layout("NUL", "", "manual", (1,), ()))


# ---- M4 ----
def _lay(**kw):
    base = dict(name="t", description="", source="manual", floors=(1,), odus=(OduPlacement("A", 1.0, 2.0, 0.0),))
    base.update(kw)
    return Layout(**base)


def test_check_layout_accepts_valid():
    check_layout(_lay())


@pytest.mark.parametrize(
    "lay",
    [
        _lay(source="lạ"),
        _lay(odus=(OduPlacement("A", 1, 2, 0, size=(0.0, 0.4)),)),
        _lay(odus=(OduPlacement("A", 1, 2, 0, size=(6.0, 0.4)),)),
        _lay(odus=(OduPlacement("A", 1, 2, 0, size=(-1.0, 0.4)),)),
        _lay(odus=(OduPlacement("A", 1, 2, 0), OduPlacement("A", 3, 2, 0))),
        _lay(odus=(OduPlacement("a b", 1, 2, 0),)),
        _lay(floors=()),
        _lay(name="CON"),
        _lay(odus=tuple(OduPlacement(f"U{i}", 0, 0, 0) for i in range(5001))),
        _lay(odus=(OduPlacement("A", float("nan"), 2, 0),)),
    ],
)
def test_check_layout_rejects_like_read_layout(lay):
    with pytest.raises(ConfigError):
        check_layout(lay)
