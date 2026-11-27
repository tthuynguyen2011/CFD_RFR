import os

import pytest
import yaml

from odu_cfd.errors import ConfigError
from odu_cfd.layout.io import layout_path, layouts_dir, list_layouts, read_layout, write_layout
from odu_cfd.layout.model import Layout, OduPlacement


def _lay(name="KT-v1"):
    return Layout(
        name,
        "Phương án kiến trúc đề xuất",
        "architect",
        (4, 5, 6, 9),
        (
            OduPlacement("ODU-01", 6.46, 1.615, 180.0, model_id="M1", size=(0.98, 0.37), floors=(4, 5)),
            OduPlacement("ODU-02", 7.54, 1.615, -90.5),
        ),
    )


def _write_raw(proj, name, text):
    d = layouts_dir(proj)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_layouts_dir(tmp_path):
    assert layouts_dir(tmp_path) == tmp_path / "layouts"


@pytest.mark.parametrize("bad", ["../x", "a/b", "a\\b", "", "x" * 65, "a b", "..", "a\nb", "ODU\n", "tên"])
def test_layout_path_rejects(tmp_path, bad):
    with pytest.raises(ConfigError):
        layout_path(tmp_path, bad)


def test_layout_path_rejects_non_str(tmp_path):
    with pytest.raises(ConfigError):
        layout_path(tmp_path, None)


def test_layout_path_ok_and_contained(tmp_path):
    p = layout_path(tmp_path, "KT-v1.2")
    assert p == tmp_path / "layouts" / "KT-v1.2.yaml"
    assert (tmp_path / "layouts").resolve() in p.resolve().parents
    assert layout_path(tmp_path, "x" * 64).name == "x" * 64 + ".yaml"


def test_roundtrip(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    lay = _lay()
    write_layout(p, lay)
    assert read_layout(p) == lay


def test_roundtrip_vietnamese_utf8_on_disk(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    assert "Phương án kiến trúc" in p.read_bytes().decode("utf-8")


def test_roundtrip_empty_odus(tmp_path):
    p = layout_path(tmp_path, "e")
    lay = Layout("e", "", "manual", (1,), ())
    write_layout(p, lay)
    assert read_layout(p) == lay


def test_int_coordinates_become_float(tmp_path):
    p = _write_raw(
        tmp_path, "n", "name: n\nfloors: '1'\nsource: manual\nodus:\n  - {id: A, x: 1, y: 2, rotation_deg: 0}\n"
    )
    o = read_layout(p).odus[0]
    assert isinstance(o.x, float) and o.size is None and o.floors is None and o.model_id is None


def test_second_write_makes_bak_with_old_content(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    first = p.read_bytes()
    write_layout(p, Layout("KT-v1", "mới", "manual", (1,), ()))
    bak = p.with_name(p.name + ".bak")
    assert bak.read_bytes() == first
    assert read_layout(p).description == "mới"


def test_no_backup_flag(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    write_layout(p, _lay(), backup=False)
    assert not p.with_name(p.name + ".bak").exists()


def test_no_temp_files_left(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    write_layout(p, _lay())
    assert sorted(f.name for f in p.parent.iterdir()) == ["KT-v1.yaml", "KT-v1.yaml.bak"]


def test_failed_replace_keeps_old_file_and_no_temp(tmp_path, monkeypatch):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    before = p.read_bytes()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_layout(p, Layout("KT-v1", "hỏng", "manual", (1,), ()), backup=False)
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert sorted(f.name for f in p.parent.iterdir()) == ["KT-v1.yaml"]


def test_failed_serialization_keeps_old_file(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    before = p.read_bytes()
    bad = Layout("KT-v1", "x", "manual", (1,), (OduPlacement("A", object(), 0, 0),))
    with pytest.raises(Exception):
        write_layout(p, bad)
    assert p.read_bytes() == before
    assert "KT-v1.yaml" in [f.name for f in p.parent.iterdir()]
    assert not [f for f in p.parent.iterdir() if f.suffix == ".tmp" or f.name.startswith(".")]


def test_write_rejects_invalid_layout(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    with pytest.raises(ConfigError):
        write_layout(p, Layout("KT-v1", "", "lạ", (1,), ()))
    assert not p.exists()


def test_write_creates_layouts_dir(tmp_path):
    p = layout_path(tmp_path, "a")
    assert not p.parent.exists()
    write_layout(p, Layout("a", "", "manual", (1,), ()))
    assert p.exists()


_BASE = "name: t\nsource: manual\nfloors: '1-2'\nodus:\n"
_ODU = "  - {id: A, x: 1.0, y: 2.0, rotation_deg: 0}\n"
_HEAD = "  - {id: A, x: 1, y: 2, rotation_deg: 0, "


@pytest.mark.parametrize(
    "text,field",
    [
        ("source: manual\nfloors: '1'\nodus: []\n", "name"),
        ("name: t\nsource: manual\nfloors: '1'\n", "odus"),
        ("name: t\nsource: manual\nodus: []\n", "floors"),
        ("name: t\nsource: manual\nfloors: '1'\nodus: {}\n", "odus"),
        ("name: t\nsource: manual\nfloors: '1'\nodus: 5\n", "odus"),
        ("name: t\nsource: lạ\nfloors: '1'\nodus: []\n", "source"),
        ("name: t\nsource: manual\nfloors: 'x'\nodus: []\n", "floors"),
        ("name: t\nsource: manual\nfloors: 4\nodus: []\n", "floors"),
        ("name: t\nsource: manual\nfloors: ''\nodus: []\n", "floors"),
        ("name: t\nsource: manual\nfloors: '1'\ndescription: 5\nodus: []\n", "description"),
        (_BASE + "  - {id: 'A B', x: 1, y: 2, rotation_deg: 0}\n", "odus[0].id"),
        (_BASE + "  - {id: 5, x: 1, y: 2, rotation_deg: 0}\n", "odus[0].id"),
        (_BASE + "  - {x: 1, y: 2, rotation_deg: 0}\n", "odus[0].id"),
        (_BASE + _ODU + "  - {id: A, x: 3, y: 2, rotation_deg: 0}\n", "odus[1].id"),
        (_BASE + "  - {id: A, x: .nan, y: 2, rotation_deg: 0}\n", "odus[0].x"),
        (_BASE + "  - {id: A, x: 1, y: .inf, rotation_deg: 0}\n", "odus[0].y"),
        (_BASE + "  - {id: A, x: 1, y: 2, rotation_deg: -.inf}\n", "odus[0].rotation_deg"),
        (_BASE + "  - {id: A, x: true, y: 2, rotation_deg: 0}\n", "odus[0].x"),
        (_BASE + "  - {id: A, x: 1, y: 2, rotation_deg: false}\n", "odus[0].rotation_deg"),
        (_BASE + "  - {id: A, x: '1', y: 2, rotation_deg: 0}\n", "odus[0].x"),
        (_BASE + "  - {id: A, x: 1, y: 2}\n", "odus[0].rotation_deg"),
        (_BASE + _HEAD + "size: [1]}\n", "odus[0].size"),
        (_BASE + _HEAD + "size: [1, 0]}\n", "odus[0].size"),
        (_BASE + _HEAD + "size: [1, 5.5]}\n", "odus[0].size"),
        (_BASE + _HEAD + "size: [1, true]}\n", "odus[0].size"),
        (_BASE + _HEAD + "size: [1, .nan]}\n", "odus[0].size"),
        (_BASE + _HEAD + "size: 1}\n", "odus[0].size"),
        (_BASE + _HEAD + "floors: '3-1'}\n", "odus[0].floors"),
        (_BASE + _HEAD + "floors: 3}\n", "odus[0].floors"),
        (_BASE + _HEAD + "model_id: 5}\n", "odus[0].model_id"),
        (_BASE + "  - 5\n", "odus[0]"),
    ],
)
def test_read_rejects_naming_field(tmp_path, text, field):
    p = _write_raw(tmp_path, "t", text)
    with pytest.raises(ConfigError) as ei:
        read_layout(p)
    assert field in str(ei.value)


def test_size_exactly_five_ok(tmp_path):
    p = _write_raw(tmp_path, "t", _BASE + _HEAD + "size: [5, 5]}\n")
    assert read_layout(p).odus[0].size == (5.0, 5.0)


def test_read_rejects_name_mismatch(tmp_path):
    p = _write_raw(tmp_path, "other", _BASE)
    with pytest.raises(ConfigError, match="name"):
        read_layout(p)


def test_read_rejects_broken_yaml(tmp_path):
    p = _write_raw(tmp_path, "t", "name: [oops\n")
    with pytest.raises(ConfigError, match="YAML"):
        read_layout(p)


def test_read_rejects_non_mapping_root(tmp_path):
    p = _write_raw(tmp_path, "t", "- a\n- b\n")
    with pytest.raises(ConfigError):
        read_layout(p)


def test_read_rejects_non_utf8(tmp_path):
    d = layouts_dir(tmp_path)
    d.mkdir()
    p = d / "t.yaml"
    p.write_bytes(b"name: t\ndescription: \xff\xfe\n")
    with pytest.raises(ConfigError, match="UTF-8"):
        read_layout(p)


def test_read_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="t.yaml"):
        read_layout(layouts_dir(tmp_path) / "t.yaml")


def test_read_rejects_python_object_tags(tmp_path):
    p = _write_raw(
        tmp_path, "t", "name: !!python/object/apply:os.getcwd []\nsource: manual\nfloors: '1'\nodus: []\n"
    )
    with pytest.raises(ConfigError):
        read_layout(p)


def test_read_limits_odus_to_5000(tmp_path):
    rows = "".join(f"  - {{id: A{i}, x: 1, y: 2, rotation_deg: 0}}\n" for i in range(5001))
    p = _write_raw(tmp_path, "t", _BASE + rows)
    with pytest.raises(ConfigError, match="5000"):
        read_layout(p)
    rows = "".join(f"  - {{id: A{i}, x: 1, y: 2, rotation_deg: 0}}\n" for i in range(5000))
    p = _write_raw(tmp_path, "t", _BASE + rows)
    assert len(read_layout(p).odus) == 5000


def test_list_layouts(tmp_path):
    assert list_layouts(tmp_path) == []
    d = layouts_dir(tmp_path)
    d.mkdir()
    for n in ["b.yaml", "a.yaml", "a.yaml.bak", "bad name.yaml", "x.txt", "tên.yaml", "KT-v1.2.yaml"]:
        (d / n).write_text("x", encoding="utf-8")
    (d / "sub.yaml").mkdir()
    assert list_layouts(tmp_path) == ["KT-v1.2", "a", "b"]


def test_written_yaml_is_plain_safe_data(tmp_path):
    p = layout_path(tmp_path, "KT-v1")
    write_layout(p, _lay())
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["floors"] == "4-6,9" and data["odus"][0]["size"] == [0.98, 0.37]
