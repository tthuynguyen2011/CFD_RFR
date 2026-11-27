"""Kiểm thử tích hợp trên bản vẽ thật (spec 5).

Chạy bằng cách đặt biến môi trường ODU_CFD_SAMPLE_DWG là đường dẫn tới DWG hoặc DXF thật, ví dụ (PowerShell):

    $env:ODU_CFD_SAMPLE_DWG = "D:\\du-lieu\\tang-dien-hinh.dwg"
    python -X utf8 -m pytest tests/test_real_sample.py -s

Bỏ qua nếu biến không đặt. File DWG lớn có thể mất vài phút để chuyển đổi và đọc (cần LibreDWG đi kèm
hoặc biến ODU_CFD_DWG2DXF). Nếu bản vẽ cần chỉ định đơn vị, đặt thêm ODU_CFD_SAMPLE_UNITS (mm, cm, m...).
Nếu bản vẽ không có mặt bằng nào có sẵn dàn nóng, test không thất bại mà in rõ điều đó.
"""

import os
from pathlib import Path

import pytest

from odu_cfd.cli import main
from odu_cfd.ingest.config import read_ingest_config
from odu_cfd.ingest.pipeline import run_ingest

SAMPLE = os.environ.get("ODU_CFD_SAMPLE_DWG")

pytestmark = pytest.mark.skipif(
    not SAMPLE or not Path(SAMPLE).is_file(),
    reason="đặt ODU_CFD_SAMPLE_DWG tới một DWG/DXF thật để chạy",
)


def test_real_drawing_ingest_roundtrip(tmp_path, capsys):
    project = tmp_path / "du-an-that"
    assert main(["init", str(project)]) == 0
    cfg = run_ingest(project, SAMPLE, units=os.environ.get("ODU_CFD_SAMPLE_UNITS"))

    path = project / "input" / "ingest.yaml"
    again = read_ingest_config(path)  # ghi ra rồi đọc lại phải khớp và hợp lệ
    assert again == cfg
    assert cfg.status == "proposed"
    assert (project / "input" / cfg.source_file.split("/", 1)[1]).is_file()
    assert (project / "input" / "overlay.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert cfg.view_bbox[2] - cfg.view_bbox[0] >= 1.0 and cfg.view_bbox[3] - cfg.view_bbox[1] >= 1.0
    assert any(role in ("wall_ext", "slab", "balcony", "rail") for role in cfg.layers.values())

    with capsys.disabled():
        print(
            f"\n[real sample] view {cfg.view_id}, {len(cfg.odus)} dàn nóng, "
            f"{len(cfg.layers)} layer có vai trò, đơn vị {cfg.units}"
        )
        if not cfg.odus:
            print("[real sample] view được chọn không có dàn nóng; bản vẽ có thể không có mặt bằng đặt sẵn dàn nóng")
