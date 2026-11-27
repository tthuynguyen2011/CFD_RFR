class ConfigError(Exception):
    """Cấu hình hoặc dữ liệu đầu vào không hợp lệ; thông báo chỉ rõ trường sai."""


class IngestError(ConfigError):
    """Lỗi đọc bản vẽ hoặc dựng hình học."""
