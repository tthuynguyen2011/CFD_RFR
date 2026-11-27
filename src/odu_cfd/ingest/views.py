import math
from dataclasses import dataclass

MAX_CELLS_PER_PRIMITIVE = 4096
MAX_LABELS = 5
MIN_VIEW_SIDE_M = 1.0


@dataclass(frozen=True)
class View:
    view_id: str
    bbox: tuple  # (minx, miny, maxx, maxy) mét, hộp bao gốc
    n_primitives: int
    layer_counts: dict
    labels: tuple
    degenerate: bool = False  # bbox rộng hoặc cao dưới MIN_VIEW_SIDE_M: không thể dựng hình học


def _bbox(prim):
    xs = [p[0] for p in prim.points]
    ys = [p[1] for p in prim.points]
    return min(xs), min(ys), max(xs), max(ys)


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def find_views(drawing, gap_m: float = 20.0, layer_roles: dict | None = None) -> list:
    """Gom primitive thành các view: primitive có hộp bao (nới gap/2) chạm cùng một ô lưới thì cùng view."""
    prims = drawing.primitives
    n = len(prims)
    if n == 0:
        return []
    half = gap_m / 2.0
    boxes = [_bbox(p) for p in prims]
    uf = _UnionFind(n)
    owner = {}  # ô lưới -> chỉ số primitive đầu tiên chạm ô đó
    big = []
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        cx0, cx1 = math.floor((x0 - half) / gap_m), math.floor((x1 + half) / gap_m)
        cy0, cy1 = math.floor((y0 - half) / gap_m), math.floor((y1 + half) / gap_m)
        if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) > MAX_CELLS_PER_PRIMITIVE:
            big.append(i)  # primitive khổng lồ: xử lý riêng, tránh tràn số ô
            continue
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                j = owner.setdefault((cx, cy), i)
                if j != i:
                    uf.union(j, i)
    for i in big:
        bx0, by0, bx1, by1 = boxes[i]
        for j, (x0, y0, x1, y1) in enumerate(boxes):
            if j != i and x1 + half >= bx0 - half and x0 - half <= bx1 + half \
                    and y1 + half >= by0 - half and y0 - half <= by1 + half:
                uf.union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    def rank(idxs):
        layers = {prims[i].layer for i in idxs}
        if layer_roles is None:
            roles = len(layers)
        else:
            roles = len({layer_roles.get(layer) for layer in layers} - {None})
        return roles

    clusters = []
    for idxs in groups.values():
        bb = (
            min(boxes[i][0] for i in idxs),
            min(boxes[i][1] for i in idxs),
            max(boxes[i][2] for i in idxs),
            max(boxes[i][3] for i in idxs),
        )
        degenerate = min(bb[2] - bb[0], bb[3] - bb[1]) < MIN_VIEW_SIDE_M
        clusters.append((degenerate, rank(idxs), len(idxs), bb, idxs))
    # view suy biến luôn xếp sau cùng nên không bao giờ được chọn tự động
    clusters.sort(key=lambda c: (c[0], -c[1], -c[2], c[3][0], c[3][1]))

    views = []
    for k, (degenerate, _roles, count, bb, idxs) in enumerate(clusters, start=1):
        counts = {}
        for i in idxs:
            counts[prims[i].layer] = counts.get(prims[i].layer, 0) + 1
        labels = []
        for t in drawing.texts:
            if bb[0] <= t.x <= bb[2] and bb[1] <= t.y <= bb[3]:
                labels.append(t.text)
                if len(labels) >= MAX_LABELS:
                    break
        views.append(View(f"V{k}", bb, count, counts, tuple(labels), degenerate))
    return views
