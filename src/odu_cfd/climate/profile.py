import math

# Hệ số mũ profile gió theo cấp địa hình (tham chiếu AIJ).
# Cần đối chiếu với cấp địa hình TCVN 2737 trước khi dùng cho kết quả chính thức.
TERRAIN_ALPHA = {"I": 0.10, "II": 0.15, "III": 0.20, "IV": 0.27, "V": 0.35}


def wind_speed_at(z_m, ref_speed_ms, ref_height_m, category) -> float:
    """Vận tốc gió ở độ cao z theo luật mũ: u(z) = u_ref * (z / z_ref) ** alpha."""
    if not all(math.isfinite(x) for x in (z_m, ref_speed_ms, ref_height_m)):
        raise ValueError("độ cao và vận tốc phải là số hữu hạn")
    if z_m <= 0 or ref_height_m <= 0:
        raise ValueError("độ cao phải dương")
    if category not in TERRAIN_ALPHA:
        raise ValueError(f"cấp địa hình không hợp lệ: {category!r}")
    return ref_speed_ms * (z_m / ref_height_m) ** TERRAIN_ALPHA[category]
