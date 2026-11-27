import math
import re
from dataclasses import dataclass

NAME_PATTERN = r"(?i)(?<![a-z])(odu|vrf|condens\w*|outdoor|dàn nóng|dan nong)(?![a-z])"
_NAME_RE = re.compile(NAME_PATTERN)

MERGE_CENTER_TOL_M = 0.05
MERGE_SIZE_TOL_M = 0.01


@dataclass(frozen=True)
class OduInstance:
    odu_id: str
    block: str
    layer: str
    center: tuple  # (x, y) mét
    size: tuple  # (w, d) mét: hai cạnh đầu của chân đế, trước khi xoay
    rotation_deg: float


def _candidate(prim):
    pts = prim.points
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    w = math.dist(pts[0], pts[1])
    d = math.dist(pts[1], pts[2])
    return OduInstance("", prim.name, prim.layer, (cx, cy), (w, d), prim.rotation_deg)


def _same(a, b):
    return (
        math.dist(a.center, b.center) < MERGE_CENTER_TOL_M
        and abs(a.size[0] - b.size[0]) < MERGE_SIZE_TOL_M
        and abs(a.size[1] - b.size[1]) < MERGE_SIZE_TOL_M
    )


def detect_odus(drawing, view_bbox, layer_roles, area_range_m2=(0.2, 3.0)) -> tuple:
    """Tìm dàn nóng trong view. Trả (odus, excluded); excluded là block ngoài khoảng diện tích chân đế."""
    minx, miny, maxx, maxy = view_bbox
    lo, hi = area_range_m2
    kept, rejected = [], []
    for prim in drawing.primitives:
        if prim.kind != "insert":
            continue
        if layer_roles.get(prim.layer) != "odu" and not _NAME_RE.search(prim.name):
            continue
        cand = _candidate(prim)
        if not (minx <= cand.center[0] <= maxx and miny <= cand.center[1] <= maxy):
            continue
        area = cand.size[0] * cand.size[1]
        target = kept if lo <= area <= hi else rejected
        if not any(_same(cand, o) for o in target):
            target.append(cand)

    def order(o):
        return (round(o.center[1], 3), round(o.center[0], 3))

    odus = [
        OduInstance(f"ODU-{i:02d}", o.block, o.layer, o.center, o.size, o.rotation_deg)
        for i, o in enumerate(sorted(kept, key=order), start=1)
    ]
    excluded = [
        OduInstance(f"X-{i:02d}", o.block, o.layer, o.center, o.size, o.rotation_deg)
        for i, o in enumerate(sorted(rejected, key=order), start=1)
    ]
    return odus, excluded
