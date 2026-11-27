import pytest

from odu_cfd.ingest.drawing import load_drawing
from odu_cfd.ingest.layers import classify_layers
from odu_cfd.ingest.views import find_views


def test_far_clusters_become_separate_views_best_first(tower_dxf):
    d = load_drawing(tower_dxf)
    views = find_views(d, layer_roles=classify_layers(d.layers))
    assert [v.view_id for v in views] == ["V1", "V2"]
    v1, v2 = views
    assert v1.bbox[0] == pytest.approx(0.0, abs=0.01) and v1.bbox[2] < 40
    assert v2.bbox[0] > 400
    assert v1.n_primitives > v2.n_primitives
    assert v1.layer_counts["A-BALC"] == 2
    assert "A-101" in v1.labels


def test_large_gap_merges_everything(tower_dxf):
    d = load_drawing(tower_dxf)
    assert len(find_views(d, gap_m=1000.0)) == 1


def test_primitives_inside_gap_stay_together(tower_dxf):
    d = load_drawing(tower_dxf)
    assert find_views(d)[0].n_primitives == 13   # 4 tường + 2 ban công + 2 lan can + 4 ODU + 1 lồng che


def _two_cluster_drawing(tmp_path):
    import ezdxf

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i in range(30):  # cụm nhiều đối tượng nhưng chỉ một layer không có vai trò
        msp.add_line((500, i), (520, i), dxfattribs={"layer": "A-JUNK"})
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 8), (0, 8)], close=True, dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 4), (10, 4), dxfattribs={"layer": "A-FLOOR"})
    p = tmp_path / "rank.dxf"
    doc.saveas(p)
    return p


def test_views_are_ranked_by_role_count_not_primitive_count(tmp_path):
    d = load_drawing(_two_cluster_drawing(tmp_path))
    views = find_views(d, layer_roles=classify_layers(d.layers))
    assert views[0].bbox[0] < 100 and views[0].n_primitives == 2   # tòa nhà: 2 vai trò, 2 đối tượng
    assert views[1].n_primitives == 30                              # rác: 1 layer không vai trò, 30 đối tượng


def test_degenerate_views_rank_last_and_are_flagged(tmp_path):
    import ezdxf

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i in range(40):
        msp.add_line((500 + i, 0), (500 + i + 0.5, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 8), (0, 8)], close=True, dxfattribs={"layer": "A-WALL"})
    p = tmp_path / "deg.dxf"
    doc.saveas(p)
    d = load_drawing(p)
    views = find_views(d, layer_roles=classify_layers(d.layers))
    assert [v.degenerate for v in views] == [False, True]
    assert views[1].n_primitives == 40
