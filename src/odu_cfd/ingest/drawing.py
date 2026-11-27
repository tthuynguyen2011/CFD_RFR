import math
import re
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf import path as ezpath
from ezdxf import recover
from ezdxf.math import Vec3

from ..errors import IngestError
from .layers import classify_layers
from .odu_detect import NAME_PATTERN

UNIT_SCALE = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}
INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}

PATH_TYPES = frozenset({"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE"})
FLATTEN_TOL_M = 0.005
TEXT_MAX_LEN = 80
_NAME_RE = re.compile(NAME_PATTERN)

# INSERT trên layer có các vai trò này được bung đệ quy thành path; INSERT khác chỉ giữ hộp bao.
STRUCT_ROLES = frozenset({"wall_ext", "slab", "balcony", "rail", "column"})
MAX_DEPTH = 8  # độ sâu lồng block tối đa
MAX_EXPANDED_PATHS = 600_000  # tổng số path sinh ra từ việc bung INSERT
MAX_VISITS = 3_000_000  # tổng số lần thăm INSERT (chặn bùng nổ lồng nhiều cấp)
MAX_MINSERT = 20_000  # số bản tối đa của một MINSERT
# Hộp bao chân đế dàn nóng không tính chữ/kích thước/ký hiệu đi kèm.
BOX_EXCLUDE = frozenset(
    {"TEXT", "MTEXT", "DIMENSION", "ATTRIB", "ATTDEF", "POINT", "LEADER", "MLEADER"}
)


@dataclass(frozen=True)
class Primitive:
    kind: str  # "path" | "insert"
    layer: str
    points: tuple  # ((x, y), ...) mét. path: đã làm phẳng; insert: 4 góc chân đế theo thứ tự quanh hình
    closed: bool = False
    name: str = ""  # tên block (insert)
    rotation_deg: float = 0.0  # insert: góc của cạnh đầu (p0->p1) sau biến đổi, 0..360


@dataclass(frozen=True)
class Text:
    text: str
    x: float
    y: float
    layer: str


@dataclass(frozen=True)
class Drawing:
    primitives: tuple
    texts: tuple
    layers: tuple  # tên layer có primitive, đã sắp xếp
    units: str
    scale_to_m: float
    skipped: dict  # {loại đối tượng: số lượng} không đọc được/không hỗ trợ


def _resolve_units(doc, units_override):
    if units_override is not None:
        if units_override not in UNIT_SCALE:
            raise IngestError(
                f"đơn vị '{units_override}' không hợp lệ; chỉ nhận {', '.join(UNIT_SCALE)}"
            )
        return units_override
    code = doc.header.get("$INSUNITS", 0)
    if code not in INSUNITS:
        raise IngestError(
            f"bản vẽ không khai báo đơn vị ($INSUNITS={code}) hoặc đơn vị không được hỗ trợ; "
            f"hãy chỉ định bằng --units ({', '.join(UNIT_SCALE)})"
        )
    return INSUNITS[code]


def _subpath_primitives(path, layer, scale, flatten_dist):
    out = []
    for sub in path.sub_paths():
        pts = tuple((v.x * scale, v.y * scale) for v in sub.flattening(flatten_dist))
        if len(pts) < 2:
            continue
        closed = bool(sub.is_closed)
        if closed and len(pts) > 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        out.append(Primitive("path", layer, pts, closed))
    return out


def _path_primitives(entity, layer, scale, flatten_dist):
    return _subpath_primitives(ezpath.make_path(entity), layer, scale, flatten_dist)


def _text_of(entity):
    kind = entity.dxftype()
    if kind == "TEXT":
        return entity.dxf.text, entity.dxf.insert
    return entity.plain_text(), entity.dxf.insert


def _angle_deg(p0, p1):
    a = round(math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 360.0, 6)
    return 0.0 if a >= 360.0 else a


class _Loader:
    """Duyệt INSERT: layer kết cấu bung thành path, ứng viên dàn nóng thành hộp bao chính xác,
    INSERT cấp cao nhất còn lại thành hộp bao nhanh."""

    def __init__(self, doc, scale, flatten_dist, role_of):
        self.doc, self.scale, self.flat = doc, scale, flatten_dist
        self.role_of = role_of
        self.prims = []
        self.layers = set()
        self.skipped = {}
        self.cache = ezbbox.Cache()
        self._content = {}
        self._box = {}
        self._has_cand = {}
        self.n_paths = 0
        self.visits = 0
        self.limit_hit = False

    def skip(self, key):
        self.skipped[key] = self.skipped.get(key, 0) + 1

    def content(self, name):
        got = self._content.get(name)
        if got is None:
            paths, inserts = [], []
            for e in self.doc.blocks[name]:
                kind = e.dxftype()
                try:
                    if kind in PATH_TYPES:
                        paths.append((e.dxf.layer, ezpath.make_path(e)))
                    elif kind == "INSERT":
                        inserts.append(e)
                except Exception:  # noqa: BLE001
                    self.skip(kind)
            got = self._content[name] = (paths, inserts)
        return got

    def instances(self, ins):
        n = ins.mcount
        if n <= 1:
            return [ins]
        if n > MAX_MINSERT:
            self.skip("INSERT-limit")
            return []
        return list(ins.multi_insert())

    def is_candidate(self, name, layer):
        return self.role_of(layer) == "odu" or bool(_NAME_RE.search(name))

    def has_candidate(self, name):
        if name in self._has_cand:
            return self._has_cand[name]
        self._has_cand[name] = False  # chặn vòng lặp
        found = False
        if name in self.doc.blocks:
            for child in self.content(name)[1]:
                cn = child.dxf.name
                if cn not in self.doc.blocks:
                    continue
                cl = child.dxf.layer
                if _NAME_RE.search(cn) or (cl != "0" and self.role_of(cl) == "odu") or self.has_candidate(cn):
                    found = True
                    break
        self._has_cand[name] = found
        return found

    def block_box(self, name, exact, depth=0):
        key = (name, exact)
        if key in self._box:
            return self._box[key]
        self._box[key] = None
        if name not in self.doc.blocks:
            return None
        ents = [
            e for e in self.doc.blocks[name] if e.dxftype() not in BOX_EXCLUDE and e.dxftype() != "INSERT"
        ]
        box = ezbbox.extents(ents, fast=not exact, cache=self.cache)
        pts = [box.extmin, box.extmax] if box.has_data else []
        if depth < MAX_DEPTH:
            for child in self.content(name)[1]:
                cb = self.block_box(child.dxf.name, exact, depth + 1)
                if cb is None:
                    continue
                x0, y0, x1, y1 = cb
                corners = [Vec3(x0, y0), Vec3(x1, y0), Vec3(x1, y1), Vec3(x0, y1)]
                for inst in self.instances(child):
                    pts.extend(inst.matrix44().transform_vertices(corners))
        res = None
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            res = (min(xs), min(ys), max(xs), max(ys))
        self._box[key] = res
        return res

    def emit_box(self, name, layer, m, exact):
        bb = self.block_box(name, exact)
        if bb is None:
            self.skip("INSERT-empty")
            return
        x0, y0, x1, y1 = bb
        corners = [Vec3(x0, y0), Vec3(x1, y0), Vec3(x1, y1), Vec3(x0, y1)]
        pts = tuple((v.x * self.scale, v.y * self.scale) for v in m.transform_vertices(corners))
        rot = _angle_deg(pts[0], pts[1])
        self.prims.append(Primitive("insert", layer, pts, True, name=name, rotation_deg=rot))
        self.layers.add(layer)

    def visit(self, ins, m, layer, depth, top, force_expand=False):
        self.visits += 1
        if self.visits > MAX_VISITS:
            self.limit_hit = True
            return
        name = ins.dxf.name
        if name not in self.doc.blocks:
            self.skip("INSERT-empty")
            return
        if self.is_candidate(name, layer):
            self.emit_box(name, layer, m, exact=True)
            return
        struct = force_expand or self.role_of(layer) in STRUCT_ROLES
        if top and not struct:
            self.emit_box(name, layer, m, exact=False)
        if struct or self.has_candidate(name):
            if depth >= MAX_DEPTH:
                self.skip("INSERT-depth")
                return
            self.walk(name, m, layer, depth, struct)

    def walk(self, name, m, layer, depth, expand_paths):
        paths, inserts = self.content(name)
        if expand_paths:
            for lay, p in paths:
                if self.n_paths >= MAX_EXPANDED_PATHS:
                    self.limit_hit = True
                    return
                eff = layer if lay == "0" else lay  # layer "0" thừa hưởng layer của INSERT
                try:
                    got = _subpath_primitives(p.transform(m), eff, self.scale, self.flat)
                except Exception:  # noqa: BLE001
                    self.skip("PATH")
                    continue
                self.n_paths += len(got)
                if got:
                    self.prims.extend(got)
                    self.layers.add(eff)
        for child in inserts:
            clayer = layer if child.dxf.layer == "0" else child.dxf.layer
            for inst in self.instances(child):
                try:
                    self.visit(inst, inst.matrix44() @ m, clayer, depth + 1, False, expand_paths)
                except Exception:  # noqa: BLE001
                    self.skip("INSERT")
                if self.limit_hit:
                    return


def load_drawing(path, units_override: str | None = None, layer_roles: dict | None = None) -> Drawing:
    """Đọc DXF thành Drawing (mét). INSERT trên layer có vai trò kết cấu được bung thành path;
    layer_roles=None thì tự phân vai theo tên layer (classify_layers)."""
    path = Path(path)
    if not path.is_file():
        raise IngestError(f"không tìm thấy file bản vẽ: {path}")
    try:
        doc, _auditor = recover.readfile(str(path))
    except (IOError, ezdxf.DXFError) as exc:
        raise IngestError(f"không đọc được DXF '{path}': {exc}") from exc

    msp = doc.modelspace()
    if len(msp) == 0:
        raise IngestError(f"file rỗng hoặc hỏng, không có đối tượng nào trong bản vẽ: {path}")

    units = _resolve_units(doc, units_override)
    scale = UNIT_SCALE[units]
    flatten_dist = FLATTEN_TOL_M / scale

    role_cache = {}

    def role_of(layer):
        if layer_roles is not None:
            return layer_roles.get(layer)
        if layer not in role_cache:
            role_cache[layer] = classify_layers([layer])[layer]
        return role_cache[layer]

    ld = _Loader(doc, scale, flatten_dist, role_of)
    texts = []
    prims, layers = ld.prims, ld.layers

    for e in msp:
        kind = e.dxftype()
        try:
            layer = e.dxf.layer
            if kind in PATH_TYPES:
                got = _path_primitives(e, layer, scale, flatten_dist)
                if not got:
                    ld.skip(kind)
                    continue
                prims.extend(got)
                layers.add(layer)
            elif kind == "INSERT":
                for inst in ld.instances(e):
                    ld.visit(inst, inst.matrix44(), layer, 0, top=True)
                    if ld.limit_hit:
                        break
            elif kind in ("TEXT", "MTEXT"):
                text, ins = _text_of(e)
                text = " ".join(str(text).split())[:TEXT_MAX_LEN]
                if text:
                    texts.append(Text(text, ins.x * scale, ins.y * scale, layer))
            else:
                ld.skip(kind)
        except Exception:  # noqa: BLE001 - đối tượng hỏng không được làm dừng cả bản vẽ
            ld.skip(kind)
    if ld.limit_hit:
        ld.skip("INSERT-limit")

    return Drawing(
        primitives=tuple(prims),
        texts=tuple(texts),
        layers=tuple(sorted(layers)),
        units=units,
        scale_to_m=scale,
        skipped=ld.skipped,
    )
