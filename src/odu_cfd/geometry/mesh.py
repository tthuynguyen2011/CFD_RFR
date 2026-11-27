import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient


@dataclass(frozen=True)
class Mesh:
    vertices: np.ndarray  # (n, 3) float64
    faces: np.ndarray  # (m, 3) int64, ngược chiều kim đồng hồ nhìn từ ngoài


class _Builder:
    """Gom tam giác và hàn đỉnh trùng theo khóa làm tròn."""

    def __init__(self):
        self._index = {}
        self.vertices = []
        self.faces = []

    def vid(self, x, y, z):
        key = (round(x, 9) + 0.0, round(y, 9) + 0.0, round(z, 9) + 0.0)
        i = self._index.get(key)
        if i is None:
            i = len(self.vertices)
            self._index[key] = i
            self.vertices.append(key)
        return i

    def tri(self, a, b, c):
        self.faces.append((self.vid(*a), self.vid(*b), self.vid(*c)))

    def build(self):
        return Mesh(
            np.array(self.vertices, dtype=np.float64).reshape(-1, 3),
            np.array(self.faces, dtype=np.int64).reshape(-1, 3),
        )


def merge(meshes):
    meshes = list(meshes)
    if not meshes:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    verts, faces, offset = [], [], 0
    for m in meshes:
        verts.append(m.vertices)
        faces.append(m.faces + offset)
        offset += len(m.vertices)
    return Mesh(np.vstack(verts), np.vstack(faces).astype(np.int64))


def volume(mesh):
    if len(mesh.faces) == 0:
        return 0.0
    t = mesh.vertices[mesh.faces]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def is_closed(mesh, tol=1e-6):
    """Mỗi cạnh có hướng (a,b) có số lượng bằng cạnh ngược (b,a); cạnh có hướng lặp lại
    chỉ chấp nhận với cạnh đứng (hai khối chạm nhau dọc một đường thẳng đứng)."""
    if len(mesh.faces) == 0:
        return False
    # hàn đỉnh theo dung sai để các lưới ghép (merge) vẫn nhất quán
    keys = np.round(mesh.vertices / tol).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    f = inverse[mesh.faces]
    if (
        (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 2] == f[:, 0])
    ).any():
        return False
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    count = {}
    for a, b in map(tuple, edges):
        count[(a, b)] = count.get((a, b), 0) + 1
    xy = {}
    for orig, w in zip(mesh.vertices, inverse):
        xy.setdefault(int(w), (round(orig[0] / tol), round(orig[1] / tol)))
    for (a, b), n in count.items():
        if count.get((b, a), 0) != n:
            return False
        if n > 1 and xy[int(a)] != xy[int(b)]:
            return False
    return True


def bounds(mesh):
    lo = mesh.vertices.min(axis=0)
    hi = mesh.vertices.max(axis=0)
    return (float(lo[0]), float(lo[1]), float(lo[2]), float(hi[0]), float(hi[1]), float(hi[2]))


def _polygons(poly):
    if isinstance(poly, Polygon):
        return [poly]
    if isinstance(poly, MultiPolygon):
        return list(poly.geoms)
    raise ValueError("cần Polygon hoặc MultiPolygon")


def extrude_polygon(poly, z0, z1):
    """Đùn đa giác thành lưới kín. Tường bên dựng từ cạnh biên của chính tập tam giác
    CDT (cạnh có hướng không có cạnh ngược), nên luôn khớp mặt trên/dưới."""
    if not z1 > z0:
        raise ValueError("z1 phải lớn hơn z0")
    b = _Builder()
    top = []
    # làm tròn đỉnh về lưới 1 micromet: phép hợp/trừ đa giác để lại đỉnh gần trùng (1e-14 m)
    # làm hỏng tính kín khi hàn đỉnh
    snapped = [q for p0 in _polygons(poly) for q in _polygons(shapely.set_precision(p0, 1e-6))]
    for p in snapped:
        if p.is_empty or p.area <= 0:
            continue
        p = orient(p, 1.0)  # ngoài ngược chiều kim đồng hồ, lỗ thuận chiều
        for tri in shapely.constrained_delaunay_triangles(p).geoms:
            if tri.area <= 0:
                continue
            pts = list(orient(tri, 1.0).exterior.coords)[:3]
            if len(pts) < 3:
                continue
            top.append([(round(x, 9) + 0.0, round(y, 9) + 0.0) for x, y in pts])
    directed = set()
    for a_, b_, c_ in top:
        directed.update(((a_, b_), (b_, c_), (c_, a_)))
    for a_, b_, c_ in top:
        b.tri((*a_, z1), (*b_, z1), (*c_, z1))  # mặt trên
        b.tri((*a_, z0), (*c_, z0), (*b_, z0))  # mặt dưới
    for (px, py), (qx, qy) in sorted(directed):
        if ((qx, qy), (px, py)) in directed:
            continue  # cạnh trong
        b.tri((px, py, z0), (qx, qy, z0), (qx, qy, z1))
        b.tri((px, py, z0), (qx, qy, z1), (px, py, z1))
    return b.build()


def box_polygon(cx, cy, w, d, rotation_deg):
    hw, hd = w / 2.0, d / 2.0
    r = math.radians(rotation_deg)
    cr, sr = math.cos(r), math.sin(r)
    return Polygon(
        [
            (cx + x * cr - y * sr, cy + x * sr + y * cr)
            for x, y in [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
        ]
    )


def box(cx, cy, w, d, rotation_deg, z0, z1):
    return extrude_polygon(box_polygon(cx, cy, w, d, rotation_deg), z0, z1)
