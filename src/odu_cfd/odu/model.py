import math
from dataclasses import dataclass

CP_AIR = 1005.0  # J/(kg.K)
R_AIR = 287.05  # J/(kg.K)
P_ATM = 101325.0  # Pa


@dataclass(frozen=True)
class OduModel:
    model_id: str
    vendor: str
    width_m: float
    depth_m: float
    height_m: float
    airflow_m3_h: float
    cooling_kw: float
    compressor_kw: float
    intake_limit_c: float
    source: str

    def heat_rejection_kw(self, load_fraction: float) -> float:
        """Nhiệt thải ra dàn ngưng = (công suất lạnh + công suất nén) x tải.

        Lưu lượng gió được coi là không đổi theo tải (giả định bảo thủ).
        """
        if isinstance(load_fraction, bool) or not math.isfinite(load_fraction):
            raise ValueError(f"load_fraction phải là số hữu hạn, nhận được {load_fraction!r}")
        if not 0.0 <= load_fraction <= 1.0:
            raise ValueError(f"load_fraction phải trong [0, 1], nhận được {load_fraction}")
        return (self.cooling_kw + self.compressor_kw) * load_fraction

    def discharge_temperature_c(self, intake_c: float, load_fraction: float) -> float:
        """Nhiệt độ thổi theo cân bằng năng lượng tại nhiệt độ hút thực tế."""
        if not math.isfinite(intake_c) or intake_c <= -273.15:
            raise ValueError(f"intake_c phải là số hữu hạn và lớn hơn -273.15, nhận được {intake_c!r}")
        rho = P_ATM / (R_AIR * (intake_c + 273.15))
        mdot = rho * self.airflow_m3_h / 3600.0
        delta_t = self.heat_rejection_kw(load_fraction) * 1000.0 / (mdot * CP_AIR)
        return intake_c + delta_t
