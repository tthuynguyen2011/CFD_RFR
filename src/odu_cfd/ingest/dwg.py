import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import IngestError

ENV_VAR = "ODU_CFD_DWG2DXF"
_ASK_DXF = "hãy xuất DXF (phiên bản 2018) từ AutoCAD rồi đưa file .dxf vào lệnh ingest"


def _bundled_candidates() -> list:
    repo = Path(__file__).parents[3]
    base = repo / "third_party" / "libredwg"
    return [base / "dwg2dxf.exe", base / "dwg2dxf"]


def locate_dwg2dxf() -> Path:
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env)
        if not p.is_file():
            raise IngestError(f"biến môi trường {ENV_VAR} trỏ tới file không tồn tại: {p}")
        return p
    for cand in _bundled_candidates():
        if Path(cand).is_file():
            return Path(cand)
    found = shutil.which("dwg2dxf")
    if found:
        return Path(found)
    raise IngestError(
        f"không tìm thấy công cụ dwg2dxf (LibreDWG); đặt biến {ENV_VAR} hoặc {_ASK_DXF}"
    )


def _ascii_tmp_root():
    """Thư mục gốc tạm có đường dẫn thuần ASCII (dwg2dxf trên Windows không mở được đường dẫn Unicode)."""
    base = tempfile.gettempdir()
    if base.isascii():
        return base
    fallback = Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "odu_cfd_tmp"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar(out: Path) -> Path:
    return out.with_name(out.name + ".sha256")


def _text(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def _discard(*paths):
    for p in paths:
        try:
            Path(p).unlink()
        except OSError:
            pass


def convert_dwg_to_dxf(dwg: Path, out: Path, exe: Path | None = None) -> Path:
    """Chuyển DWG sang DXF. Đệm theo SHA-256 của DWG (file `<out>.sha256`); kết quả được ghi nguyên tử."""
    dwg, out = Path(dwg), Path(out)
    try:
        with dwg.open("rb") as f:
            magic = f.read(4)
    except OSError as exc:
        raise IngestError(f"không đọc được file {dwg}: {exc}") from exc
    if magic != b"AC10":
        raise IngestError(f"'{dwg}' không phải DWG hợp lệ (thiếu header AC10); nếu là DXF hãy dùng đuôi .dxf")

    digest = _sha256(dwg)
    side = _sidecar(out)
    try:
        cached = side.read_text(encoding="utf-8").strip() == digest
    except OSError:
        cached = False
    if cached and out.is_file() and out.stat().st_size > 0:
        return out

    exe = Path(exe) if exe is not None else locate_dwg2dxf()
    out.parent.mkdir(parents=True, exist_ok=True)
    _discard(out, side)  # không bao giờ để lại kết quả cũ/dở dang
    tmp_final = out.with_name(out.name + ".tmp")

    with tempfile.TemporaryDirectory(dir=_ascii_tmp_root(), prefix="odu_") as work:
        work = Path(work)
        w_in, w_out = work / "in.dwg", work / "out.dxf"
        try:
            shutil.copyfile(dwg, w_in)
        except OSError as exc:
            raise IngestError(f"không chép được {dwg} sang thư mục tạm: {exc}") from exc
        try:
            proc = subprocess.run(
                [str(exe), "-y", "-o", str(w_out), str(w_in)],
                capture_output=True,
                timeout=900,
            )
        except subprocess.TimeoutExpired as exc:
            raise IngestError(f"dwg2dxf chạy quá 900 giây; {_ASK_DXF}") from exc
        except OSError as exc:
            raise IngestError(f"không chạy được dwg2dxf ({exe}): {exc}; {_ASK_DXF}") from exc

        detail = (_text(proc.stderr).strip() or _text(proc.stdout).strip())[-500:]
        if proc.returncode >= 128 or proc.returncode < 0:
            raise IngestError(f"dwg2dxf lỗi nặng (mã {proc.returncode}): {detail}; {_ASK_DXF}")
        if not w_out.is_file() or w_out.stat().st_size == 0:
            raise IngestError(f"dwg2dxf không tạo được file DXF (mã {proc.returncode}): {detail}; {_ASK_DXF}")
        try:
            shutil.copyfile(w_out, tmp_final)
            os.replace(tmp_final, out)
            side.write_text(digest, encoding="utf-8")
        except OSError as exc:
            _discard(tmp_final, out, side)
            raise IngestError(f"không ghi được kết quả chuyển đổi {out}: {exc}") from exc
    return out
