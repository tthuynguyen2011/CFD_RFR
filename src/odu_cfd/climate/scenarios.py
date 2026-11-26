from dataclasses import dataclass

from ..errors import ConfigError


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    wind_speed_ms: float
    wind_from_deg: float
    transient: bool


def build_scenarios(wind) -> list:
    """Tạo danh sách kịch bản từ cấu hình gió (WindConfig).

    Lặng gió (0 m/s) -> một kịch bản 'calm' transient (steady RANS không đáng tin).
    Mỗi tốc độ > 0 -> một kịch bản steady cho mỗi hướng.
    """
    scenarios = []
    for speed in wind.speeds_ms:
        if speed == 0:
            scenarios.append(Scenario("calm", 0.0, 0.0, True))
            continue
        for direction in wind.directions_deg:
            scenario_id = f"w{speed:g}_d{int(direction):03d}"
            scenarios.append(Scenario(scenario_id, speed, direction, False))
    ids = [s.scenario_id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise ConfigError("'climate.wind' sinh ra scenario_id trùng nhau (tốc độ gió quá gần nhau); hãy dùng các giá trị khác biệt rõ hơn")
    return scenarios
