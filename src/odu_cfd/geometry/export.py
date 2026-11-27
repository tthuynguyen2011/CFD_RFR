import json
import re
import struct
from pathlib import Path

import numpy as np

from ..errors import IngestError
from .mesh import Mesh

_COLORS = {
    "building": [0.72, 0.72, 0.72, 1.0],
    "balcony": [0.85, 0.78, 0.62, 1.0],
    "rail": [0.30, 0.70, 0.75, 1.0],
    "odu": [0.90, 0.35, 0.10, 1.0],
}
_DEFAULT_COLOR = [0.72, 0.72, 0.72, 1.0]


def _safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(name)) or "_"


def _triangles(mesh: Mesh):
    return mesh.vertices[mesh.faces]  # (m, 3, 3)


def _unit_normals(tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    length = np.linalg.norm(n, axis=1)
    length[length == 0] = 1.0
    return n / length[:, None]


def check_region_names(regions):
    """Tên vùng STL sau khi làm sạch phải duy nhất; trùng thì lỗi rõ, không ghi đè âm thầm."""
    seen = {}
    for raw in regions:
        name = _safe_name(raw)
        if name in seen:
            raise IngestError(
                f"tên vùng '{seen[name]}' và '{raw}' trùng nhau sau khi làm sạch ('{name}') trong STL; "
                "hãy đổi id dàn nóng cho khác nhau"
            )
        seen[name] = raw


def write_stl(path, regions):
    check_region_names(regions)
    lines = []
    for raw, mesh in regions.items():
        name = _safe_name(raw)
        lines.append(f"solid {name}")
        tris = _triangles(mesh)
        normals = _unit_normals(tris)
        for n, t in zip(normals, tris):
            lines.append(f"  facet normal {n[0]:.9g} {n[1]:.9g} {n[2]:.9g}")
            lines.append("    outer loop")
            for v in t:
                lines.append(f"      vertex {v[0]:.9g} {v[1]:.9g} {v[2]:.9g}")
            lines.append("    endloop")
            lines.append("  endfacet")
        lines.append(f"endsolid {name}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")


def _to_yup(a):
    """(x, y, z) -> (x, z, -y): phép quay giữ chiều ngược kim đồng hồ."""
    return np.stack([a[..., 0], a[..., 2], -a[..., 1]], axis=-1)


def _pad(data, fill):
    return data + fill * ((-len(data)) % 4)


def write_glb(path, groups):
    binary = bytearray()
    buffer_views, accessors, meshes, nodes, materials = [], [], [], [], []
    material_index = {}
    for group, regions in groups.items():
        if group not in material_index:
            material_index[group] = len(materials)
            materials.append(
                {
                    "name": group,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": _COLORS.get(group, _DEFAULT_COLOR),
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.9,
                    },
                    "doubleSided": True,
                }
            )
        for name, mesh in regions.items():
            tris = _triangles(mesh)
            if len(tris) == 0:
                continue
            pos = _to_yup(tris).astype("<f4").reshape(-1, 3)
            nrm = _to_yup(np.repeat(_unit_normals(tris), 3, axis=0)).astype("<f4")
            attrs = {}
            for key, arr in (("POSITION", pos), ("NORMAL", nrm)):
                buffer_views.append(
                    {"buffer": 0, "byteOffset": len(binary), "byteLength": arr.nbytes, "target": 34962}
                )
                binary += arr.tobytes()
                acc = {
                    "bufferView": len(buffer_views) - 1,
                    "componentType": 5126,
                    "count": len(arr),
                    "type": "VEC3",
                }
                if key == "POSITION":
                    acc["min"] = [float(v) for v in arr.min(axis=0)]
                    acc["max"] = [float(v) for v in arr.max(axis=0)]
                accessors.append(acc)
                attrs[key] = len(accessors) - 1
            meshes.append(
                {
                    "name": str(name),
                    "primitives": [{"attributes": attrs, "material": material_index[group], "mode": 4}],
                }
            )
            nodes.append({"name": str(name), "mesh": len(meshes) - 1, "extras": {"group": group}})
    gltf = {
        "asset": {"version": "2.0", "generator": "odu-cfd"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(_pad(bytes(binary), b"\0"))}],
    }
    jbytes = _pad(json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), b" ")
    bbytes = _pad(bytes(binary), b"\0")
    total = 12 + 8 + len(jbytes) + 8 + len(bbytes)
    out = (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(jbytes), 0x4E4F534A)
        + jbytes
        + struct.pack("<II", len(bbytes), 0x004E4942)
        + bbytes
    )
    Path(path).write_bytes(out)
