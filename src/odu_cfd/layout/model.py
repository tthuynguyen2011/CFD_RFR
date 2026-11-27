"""Mô hình phương án bố trí dàn nóng: dữ liệu bất biến, tầng, hướng thổi."""

from dataclasses import dataclass

from ..errors import ConfigError

SOURCES = ("architect", "rule", "drawing", "manual")
NAME_RE = r"^[A-Za-z0-9_.-]{1,64}$"
ID_RE = r"^[A-Za-z0-9_.-]+$"
MAX_FLOOR = 1000


@dataclass(frozen=True)
class OduPlacement:
    odu_id: str
    x: float
    y: float
    rotation_deg: float
    model_id: str | None = None
    size: tuple | None = None  # (w, d) mét hoặc None
    floors: tuple | None = None  # tuple[int] mức tầng 1-based hoặc None


@dataclass(frozen=True)
class Layout:
    name: str
    description: str
    source: str  # architect | rule | drawing | manual
    floors: tuple  # tuple[int] tăng dần, không trùng
    odus: tuple  # tuple[OduPlacement]

    def floors_of(self, p: OduPlacement) -> tuple:
        return p.floors if p.floors is not None else self.floors


def _to_int(text, segment, whole):
    if not text.isascii() or not text.isdigit():
        raise ConfigError(f"tầng '{whole}': đoạn '{segment}' không phải số nguyên dương")
    return int(text)


def parse_floors(text) -> tuple:
    """'4-19,22-23' -> (4, ..., 19, 22, 23). Tăng dần, không trùng, mỗi tầng >= 1."""
    if not isinstance(text, str):
        raise ConfigError(f"danh sách tầng phải là chuỗi như '4-19,22-23', nhận được {text!r}")
    if not text.strip():
        raise ConfigError("danh sách tầng rỗng (ví dụ '4-19,22-23')")
    out = []
    for raw in text.split(","):
        seg = raw.strip()
        if not seg:
            raise ConfigError(f"tầng '{text}': có đoạn rỗng")
        if "-" in seg:
            parts = seg.split("-")
            if len(parts) != 2:
                raise ConfigError(f"tầng '{text}': đoạn '{seg}' sai cú pháp")
            lo = _to_int(parts[0].strip(), seg, text)
            hi = _to_int(parts[1].strip(), seg, text)
            if lo > hi:
                raise ConfigError(f"tầng '{text}': đoạn '{seg}' có đầu lớn hơn cuối")
            nums = range(lo, hi + 1)
        else:
            nums = [_to_int(seg, seg, text)]
        for n in nums:
            if n < 1 or n > MAX_FLOOR:
                raise ConfigError(f"tầng '{text}': đoạn '{seg}' ngoài khoảng 1..{MAX_FLOOR}")
            if out and n <= out[-1]:
                raise ConfigError(f"tầng '{text}': đoạn '{seg}' trùng hoặc không tăng dần")
            out.append(n)
    return tuple(out)


def format_floors(floors) -> str:
    """(4, 5, 6, 9) -> '4-6,9'."""
    fl = list(floors)
    parts = []
    i = 0
    while i < len(fl):
        j = i
        while j + 1 < len(fl) and fl[j + 1] == fl[j] + 1:
            j += 1
        parts.append(str(fl[i]) if i == j else f"{fl[i]}-{fl[j]}")
        i = j + 1
    return ",".join(parts)


def front_angle_deg(p) -> float:
    """Hướng thổi trên mặt bằng (độ, ngược chiều kim đồng hồ từ +x), chuẩn hóa [0, 360)."""
    a = (p.rotation_deg + 90.0) % 360.0
    return 0.0 if a >= 360.0 else a
