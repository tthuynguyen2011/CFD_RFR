# Nghiệm thu giai đoạn 2 trên bản vẽ thật Spring Light

Ngày: 2026-11-26. Sau review chéo (xem `2026-11-26-stage2-review-findings.md`) và vòng sửa, 342 test pass.

## Kết quả

| Bản vẽ | Kết quả |
|---|---|
| `03 Case study/04.Spring Light/SPRING_PLAN.dxf` (13 MB) | `ingest` 11 s: 1 view mặt bằng, 10 layer có vai trò, 28 ban công, 182 đoạn lan can. Đường bao 3 tháp (mỗi tháp khoảng 1665 m²). `geometry` 10 s: 19 tầng, mọi phần kín, dựng 3D đúng (đã xem viewer). Không có dàn nóng trong file này. |
| `04 WIP/01.Spring light/1.Layout/20260731-Typical tower 1 (ODU).dwg` | LibreDWG chuyển được (13 s). Sau khi bung block, tải 81 s, 103.354 primitive. V1, V2 là mặt đứng/mặt cắt Revit (không dựng được đường bao kín). V3 là tờ chi tiết dàn nóng (14 dàn nóng nhận diện được, 3 lồng che bị loại theo diện tích). V4 giống mặt bằng, chưa kiểm tra. |

## Phát hiện về dữ liệu (cần quyết định)

1. **Dàn nóng và mặt bằng nằm ở hai nơi khác nhau.** `SPRING_PLAN.dxf` có ban công, lan can nhưng không có dàn nóng. Tờ chi tiết dàn nóng chỉ có 3 cụm cục bộ, không cùng hệ tọa độ với mặt bằng. Tool chưa có cách đặt dàn nóng lên mặt bằng.
2. **Thông số dàn nóng nằm sẵn trong chữ của tờ chi tiết** (H x W x D = 990 x 980 x 370 mm, 16 kW, louver thoáng 80 %, 40 tầng, TP.HCM). Có thể trích tự động để điền thư viện ODU và `project.yaml`.
3. Chân đế block "ODU VRF MINI" đo từ bản vẽ ra 0,98 x 1,02 m trong khi nhãn ghi sâu 0,37 m. Khi dùng `--library` tool lấy kích thước từ thư viện.
4. Số tầng thật là 40, mẫu `project.yaml` đang là 19.

## Việc chưa làm

- Cách đặt dàn nóng lên mặt bằng (đặt theo quy tắc trên từng ban công, hoặc đăng ký tờ chi tiết với mặt bằng, hoặc người dùng cung cấp mặt bằng đã vẽ dàn nóng).
- Heuristic phân biệt mặt bằng với mặt đứng/mặt cắt để chọn view mặc định (hiện chọn theo số vai trò layer, trên DWG thật phải dùng `--view`).
- Phát hiện sân trong/giếng trời lớn (cảnh báo hiện chỉ đo lỗ nhỏ).
- Trích thông số dàn nóng từ chữ trong bản vẽ; Excel và PDF.
- Cột (`plan.columns`) chưa dùng trong dựng 3D.
- Tải DXF lớn chậm (80 s cho 143 MB); cân nhắc bộ đệm.
