import ezdxf

ODU_W, ODU_D = 0.98, 0.47
ODU_POSITIONS = [(5.5, 0.8), (7.0, 0.8), (20.5, 0.8), (22.0, 0.8)]
BALCONIES = [((5, 0), (9, 2)), ((20, 0), (24, 2))]
FAR_X = 500.0


def make_tower_dxf(path, *, unit_code=4):
    """DXF tổng hợp: thân nhà 30x20 m, 2 ban công lõm, lan can, 4 dàn nóng, 1 lồng che, 1 cụm xa."""
    k = 1000.0 if unit_code == 4 else 1.0
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = unit_code
    for name in ("A-WALL", "A-BALC", "A-HANDRAIL", "M-EQPM", "A-ANNO"):
        doc.layers.add(name)

    def rect_block(name, w, d):
        blk = doc.blocks.new(name)
        pts = [(0, 0), (w * k, 0), (w * k, d * k), (0, d * k)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            blk.add_line(a, b)

    rect_block("ODU_TEST", ODU_W, ODU_D)
    rect_block("ENCLOSURE", 2.8, 3.2)

    msp = doc.modelspace()

    def line(a, b, layer):
        msp.add_line((a[0] * k, a[1] * k), (b[0] * k, b[1] * k), dxfattribs={"layer": layer})

    def rect(x0, y0, x1, y1, layer, dx=0.0):
        pts = [(x0 + dx, y0), (x1 + dx, y0), (x1 + dx, y1), (x0 + dx, y1)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            line(a, b, layer)

    rect(0, 0, 30, 20, "A-WALL")
    for (x0, y0), (x1, y1) in BALCONIES:
        msp.add_lwpolyline(
            [(x0 * k, y0 * k), (x1 * k, y0 * k), (x1 * k, y1 * k), (x0 * k, y1 * k)],
            close=True,
            dxfattribs={"layer": "A-BALC"},
        )
    line((5, 0), (9, 0), "A-HANDRAIL")
    line((20, 0), (24, 0), "A-HANDRAIL")
    for x, y in ODU_POSITIONS:
        msp.add_blockref("ODU_TEST", (x * k, y * k), dxfattribs={"layer": "M-EQPM"})
    msp.add_blockref("ENCLOSURE", (12 * k, 5 * k), dxfattribs={"layer": "M-EQPM"})
    rect(0, 0, 10, 10, "A-WALL", dx=FAR_X)
    line((FAR_X, 12), (FAR_X + 5, 12), "A-HANDRAIL")
    msp.add_text("A-101", dxfattribs={"insert": (1 * k, 1 * k), "layer": "A-ANNO", "height": 0.3 * k})
    doc.saveas(path)
