import json
import re
import struct

import numpy as np
import pytest

from odu_cfd.geometry.export import write_glb, write_stl
from odu_cfd.geometry.mesh import box, volume


def _read_stl(path):
    text = path.read_text(encoding="ascii")
    regions = {}
    for name, body in re.findall(r"solid (\S+)\n(.*?)endsolid \1", text, re.S):
        v = np.array(
            [[float(t) for t in m] for m in re.findall(r"vertex (\S+) (\S+) (\S+)", body)]
        ).reshape(-1, 3, 3)
        regions[name] = v
    return regions


def _signed_volume(tris):
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def test_stl_regions_roundtrip(tmp_path):
    a, b = box(0, 0, 1, 2, 0, 0, 3), box(5, 5, 1, 1, 45, 0, 1)
    write_stl(tmp_path / "x.stl", {"ODU-01_f00": a, "b region": b})
    r = _read_stl(tmp_path / "x.stl")
    assert set(r) == {"ODU-01_f00", "b_region"}
    assert _signed_volume(r["ODU-01_f00"]) == pytest.approx(volume(a))
    assert _signed_volume(r["b_region"]) == pytest.approx(volume(b))
    assert len(r["ODU-01_f00"]) == len(a.faces)


def test_stl_facet_normals_match_winding(tmp_path):
    a = box(0, 0, 1, 2, 0, 0, 3)
    write_stl(tmp_path / "x.stl", {"a": a})
    text = (tmp_path / "x.stl").read_text(encoding="ascii")
    normals = np.array([[float(t) for t in m] for m in re.findall(r"facet normal (\S+) (\S+) (\S+)", text)])
    tris = _read_stl(tmp_path / "x.stl")["a"]
    expect = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    expect /= np.linalg.norm(expect, axis=1)[:, None]
    assert np.allclose(normals, expect, atol=1e-6)


def _read_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert (magic, version, length) == (b"glTF", 2, len(data))
    jlen, jtype = struct.unpack_from("<II", data, 12)
    assert jtype == 0x4E4F534A and jlen % 4 == 0
    gltf = json.loads(data[20 : 20 + jlen])
    boff = 20 + jlen
    blen, btype = struct.unpack_from("<II", data, boff)
    assert btype == 0x004E4942 and blen % 4 == 0 and boff + 8 + blen == len(data)
    return gltf, data[boff + 8 :]


def test_glb_structure(tmp_path):
    a = box(0, 0, 1, 1, 0, 0, 2)
    write_glb(tmp_path / "s.glb", {"building": {"building": a}, "odu": {"ODU-01_f00": a, "ODU-02_f00": a}})
    gltf, binary = _read_glb(tmp_path / "s.glb")
    assert gltf["asset"]["version"] == "2.0"
    assert sorted(n["name"] for n in gltf["nodes"]) == ["ODU-01_f00", "ODU-02_f00", "building"]
    assert {n["extras"]["group"] for n in gltf["nodes"]} == {"building", "odu"}
    assert len(gltf["meshes"]) == 3 and len(gltf["materials"]) == 2
    acc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert acc["count"] == len(a.faces) * 3 and acc["type"] == "VEC3"
    view = gltf["bufferViews"][acc["bufferView"]]
    pos = np.frombuffer(binary, "<f4", count=acc["count"] * 3, offset=view.get("byteOffset", 0)).reshape(-1, 3)
    # y-up: z của mô hình (0..2) thành y của glTF
    assert pos[:, 1].min() == pytest.approx(0.0) and pos[:, 1].max() == pytest.approx(2.0)
    assert acc["min"][1] == pytest.approx(0.0) and acc["max"][1] == pytest.approx(2.0)


def test_glb_normals_are_unit(tmp_path):
    write_glb(tmp_path / "s.glb", {"building": {"building": box(0, 0, 1, 1, 0, 0, 2)}})
    gltf, binary = _read_glb(tmp_path / "s.glb")
    nacc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]]
    view = gltf["bufferViews"][nacc["bufferView"]]
    n = np.frombuffer(binary, "<f4", count=nacc["count"] * 3, offset=view.get("byteOffset", 0)).reshape(-1, 3)
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-5)


def test_glb_yup_winding_and_normals_outward(tmp_path):
    # hộp x 0..2, y 0..2 (z-up), z 0..1 => glTF: y-up, z' = -y
    write_glb(tmp_path / "s.glb", {"building": {"building": box(1, 1, 2, 2, 0, 0, 1)}})
    gltf, binary = _read_glb(tmp_path / "s.glb")
    attrs = gltf["meshes"][0]["primitives"][0]["attributes"]

    def load(idx):
        acc = gltf["accessors"][idx]
        view = gltf["bufferViews"][acc["bufferView"]]
        return np.frombuffer(binary, "<f4", count=acc["count"] * 3, offset=view.get("byteOffset", 0)).reshape(-1, 3)

    pos, nrm = load(attrs["POSITION"]), load(attrs["NORMAL"])
    tris = pos.reshape(-1, 3, 3)
    geo = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    geo /= np.linalg.norm(geo, axis=1)[:, None]
    assert np.allclose(np.repeat(geo, 3, axis=0), nrm, atol=1e-5)  # pháp tuyến khớp chiều đỉnh
    centre = np.array([1.0, 0.5, -1.0])
    out = tris.mean(axis=1) - centre
    assert (np.einsum("ij,ij->i", geo, out) > 0).all()  # hướng ra ngoài
    # mặt đáy (y'=0) hướng xuống
    bottom = (tris[:, :, 1] == 0).all(axis=1)
    assert (geo[bottom][:, 1] < 0).all()
