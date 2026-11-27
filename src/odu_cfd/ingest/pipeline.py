import shutil
import sys
from pathlib import Path

from ..errors import IngestError
from .config import IngestConfig, read_ingest_config, validate_for_geometry, write_ingest_config
from .drawing import load_drawing
from .dwg import convert_dwg_to_dxf
from .layers import classify_layers
from .odu_detect import detect_odus
from .overlay import render_overlay
from .views import find_views

DEFAULT_AREA_RANGE = (0.2, 3.0)


def _input_dir(project_dir) -> Path:
    inp = Path(project_dir) / "input"
    if not inp.is_dir():
        raise IngestError(f"không thấy thư mục {inp}; hãy chạy 'odu-cfd init <dự án>' trước")
    return inp


def _copy_in(source: Path, inp: Path) -> Path:
    dest = inp / source.name
    if dest.exists() and source.resolve() == dest.resolve():
        return dest
    shutil.copy2(source, dest)
    return dest


def _guard_existing(yaml_path: Path, force: bool) -> None:
    if force or not yaml_path.is_file():
        return
    try:
        status = read_ingest_config(yaml_path).status
    except Exception:  # noqa: BLE001 - file hỏng thì cho ghi đè (có sao lưu)
        return
    if status == "confirmed":
        raise IngestError(
            f"{yaml_path} đã ở trạng thái 'confirmed'; chạy lại ingest sẽ ghi đè các chỉnh sửa tay. "
            "Dùng --force để ghi đè (bản cũ được lưu thành ingest.yaml.bak)"
        )


def run_ingest_full(project_dir, source, view_id=None, units=None, exe=None, force=False):
    """Như run_ingest nhưng trả thêm (excluded, skipped) cho lệnh CLI tóm tắt."""
    project_dir = Path(project_dir)
    inp = _input_dir(project_dir)
    yaml_path = inp / "ingest.yaml"
    _guard_existing(yaml_path, force)
    source = Path(source)
    ext = source.suffix.lower()
    if ext not in (".dwg", ".dxf"):
        raise IngestError(f"định dạng '{source.suffix}' không được hỗ trợ; chỉ nhận .dwg hoặc .dxf")
    if not source.is_file():
        raise IngestError(f"không tìm thấy bản vẽ: {source}")

    copied = _copy_in(source, inp)
    if ext == ".dwg":
        original = f"input/{copied.name}"
        dxf_path = convert_dwg_to_dxf(copied, inp / (copied.stem + ".converted.dxf"), exe=exe)
    else:
        original = None
        dxf_path = copied

    drawing = load_drawing(dxf_path, units_override=units)
    roles = classify_layers(drawing.layers)
    views = find_views(drawing, layer_roles=roles)
    if not views:
        raise IngestError("bản vẽ không có đối tượng hình học nào đọc được")
    wanted = view_id or next((v.view_id for v in views if not v.degenerate), None)
    if wanted is None:
        raise IngestError(
            "mọi view đều suy biến (rộng hoặc cao dưới 1 m, thường chỉ là một đường thẳng); "
            "kiểm tra --units hoặc bản vẽ"
        )
    view = next((v for v in views if v.view_id == wanted), None)
    if view is None:
        options = "; ".join(
            f"{v.view_id}: {v.n_primitives} đối tượng, bbox "
            f"({v.bbox[0]:.1f}, {v.bbox[1]:.1f})-({v.bbox[2]:.1f}, {v.bbox[3]:.1f}) m"
            for v in views[:20]
        )
        raise IngestError(f"không có view '{wanted}'; các view hiện có: {options}")

    if view.degenerate:
        raise IngestError(
            f"view {view.view_id} suy biến (bbox {view.bbox[2] - view.bbox[0]:.2f} x "
            f"{view.bbox[3] - view.bbox[1]:.2f} m, dưới 1 m ở một chiều) nên không thể dựng hình học; "
            "chọn view khác bằng --view"
        )
    odus, excluded = detect_odus(drawing, view.bbox, roles, area_range_m2=DEFAULT_AREA_RANGE)
    cfg = IngestConfig(
        status="proposed",
        source_file=f"input/{dxf_path.name}",
        original_file=original,
        units=drawing.units,
        view_id=view.view_id,
        view_bbox=tuple(float(v) for v in view.bbox),
        layers={name: role for name, role in roles.items() if role is not None},
        odu_area_range_m2=DEFAULT_AREA_RANGE,
        odus=odus,
    )
    if yaml_path.is_file():
        shutil.copy2(yaml_path, inp / "ingest.yaml.bak")
    write_ingest_config(yaml_path, cfg)
    render_overlay(drawing, cfg, inp / "overlay.png", excluded=excluded)
    return cfg, excluded, drawing.skipped


def run_ingest(project_dir, source, view_id=None, units=None, exe=None, force=False) -> IngestConfig:
    return run_ingest_full(project_dir, source, view_id=view_id, units=units, exe=exe, force=force)[0]


def confirm_ingest(project_dir) -> IngestConfig:
    path = _input_dir(project_dir) / "ingest.yaml"
    cfg = read_ingest_config(path)
    validate_for_geometry(cfg)
    cfg.status = "confirmed"
    write_ingest_config(path, cfg)
    if not cfg.odus:
        print(
            "Cảnh báo: chưa có dàn nóng nào trong ingest.yaml; hãy tạo phương án bố trí bằng "
            f"`odu-cfd layout auto {project_dir} ...` hoặc `odu-cfd edit {project_dir}` sau khi chạy `geometry`",
            file=sys.stderr,
        )
    return cfg
