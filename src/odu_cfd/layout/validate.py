"""Kiểm tra phương án bố trí: một nguồn logic duy nhất cho CLI, server và dựng 3D."""

import math
import re
from dataclasses import dataclass

from shapely.strtree import STRtree

from ..geometry.mesh import box_polygon
from .model import ID_RE, format_floors

CONTAIN_TOL_M = 1e-3
OVERLAP_AREA_M2 = 1e-4


@dataclass(frozen=True)
class Problem:
    level: str  # "error" | "warning"
    odu_id: str | None
    message: str


def odu_footprint(p, size):
    """Chân đế: w theo x cục bộ, d theo y cục bộ, xoay ngược chiều kim đồng hồ quanh (x, y)."""
    return box_polygon(p.x, p.y, size[0], size[1], p.rotation_deg)


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _floor_problems(floors, num_floors, who, odu_id):
    out = []
    label = f"{who}: " if who else ""
    if floors is None or len(floors) == 0:
        return [Problem("error", odu_id, f"{label}danh sách tầng rỗng")]
    seen = set()
    for f in floors:
        if not isinstance(f, int) or isinstance(f, bool):
            out.append(Problem("error", odu_id, f"{label}tầng {f!r} không phải số nguyên"))
        elif f < 1 or f > num_floors:
            out.append(Problem("error", odu_id, f"{label}tầng {f} ngoài phạm vi 1..{num_floors} của công trình"))
        if f in seen:
            out.append(Problem("error", odu_id, f"{label}tầng {f} bị trùng trong danh sách tầng"))
        seen.add(f)
    return out


def validate_layout(layout, balconies, num_floors, sizes) -> list:
    problems = []
    problems += _floor_problems(layout.floors, num_floors, "phương án", None)

    bal_buf = [b.polygon.buffer(CONTAIN_TOL_M) for b in balconies]
    bal_tree = STRtree(bal_buf) if bal_buf else None

    items = []  # (placement, footprint, floors-set)
    seen_ids = set()
    for p in layout.odus:
        oid = p.odu_id
        if not isinstance(oid, str) or re.fullmatch(ID_RE, oid) is None:
            problems.append(Problem("error", oid if isinstance(oid, str) else None, f"id dàn nóng {oid!r} không hợp lệ"))
            continue
        if oid in seen_ids:
            problems.append(Problem("error", oid, f"{oid}: id bị trùng"))
            continue
        seen_ids.add(oid)

        if p.floors is not None:
            fp_problems = _floor_problems(p.floors, num_floors, oid, oid)
            problems += fp_problems
            fl_ok = not fp_problems
        else:
            fl_ok = True

        if not (_finite(p.x) and _finite(p.y) and _finite(p.rotation_deg)):
            problems.append(Problem("error", oid, f"{oid}: tọa độ hoặc góc xoay không phải số hữu hạn"))
            continue
        size = sizes.get(oid)
        if size is None:
            problems.append(Problem("error", oid, f"{oid}: thiếu kích thước chân đế"))
            continue
        if not (isinstance(size, (tuple, list)) and len(size) == 2 and all(_finite(s) and s > 0 for s in size)):
            problems.append(Problem("error", oid, f"{oid}: kích thước chân đế {size!r} không hợp lệ"))
            continue

        fp = odu_footprint(p, size)
        contained = []
        if bal_tree is not None:
            for idx in sorted(bal_tree.query(fp)):
                if bal_buf[int(idx)].contains(fp):
                    contained.append(balconies[int(idx)])
        if not contained:
            problems.append(
                Problem("error", oid, f"{oid}: ngoài ban công (chân đế không nằm trọn trong ban công nào)")
            )
        elif not any(b.allowed for b in contained):
            bid = sorted(b.balcony_id for b in contained)[0]
            problems.append(Problem("error", oid, f"{oid}: ban công {bid} không cho phép đặt dàn nóng"))

        if fl_ok:
            items.append((oid, fp, frozenset(layout.floors_of(p))))

    if len(items) > 1:
        tree = STRtree([fp for _, fp, _ in items])
        for i, (oid, fp, fl) in enumerate(items):
            for j in sorted(tree.query(fp)):
                j = int(j)
                if j <= i:
                    continue
                oid2, fp2, fl2 = items[j]
                shared = fl & fl2
                if not shared:
                    continue
                if fp.intersection(fp2).area > OVERLAP_AREA_M2:
                    problems.append(
                        Problem(
                            "error",
                            oid,
                            f"{oid} và {oid2} chồng nhau ở tầng {format_floors(sorted(shared))}",
                        )
                    )
    return problems
