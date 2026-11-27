# Giai đoạn 2: đọc bản vẽ CAD và dựng hình học 3D

Ngày: 2026-11-26. Mở rộng mục 5 và giai đoạn 2 của `2026-11-26-odu-cfd-tool-design.md`.

## 1. Mục tiêu

Từ bản vẽ DWG hoặc DXF của dự án, tool tự động dựng ra mô hình 3D của tòa nhà (khối nhà, sàn ban công,
lan can, dàn nóng) để giai đoạn sau dùng làm hình học CFD. Người dùng phải xem và xác nhận kết quả
nhận diện trước khi dựng, vì bản vẽ thực tế không có quy ước thống nhất.

Đầu ra của giai đoạn:
- `input/ingest.yaml`: kết quả nhận diện (mặt bằng được chọn, vai trò từng layer, danh sách dàn nóng), có trạng thái `proposed` hoặc `confirmed`.
- `input/overlay.png`: ảnh phủ nhận diện lên bản vẽ để người dùng kiểm tra.
- `input/geometry/`: `building.stl`, `balcony.stl`, `rail.stl`, `odu.stl` (STL nhiều vùng, hệ trục z hướng lên, đơn vị mét), `scene.glb`, `geometry.json` (tóm tắt và kiểm tra chất lượng), `viewer.html` (viewer 3D chạy offline).

## 2. Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| DWG | Tool tự gọi `dwg2dxf` của LibreDWG. Tìm theo thứ tự: biến môi trường `ODU_CFD_DWG2DXF`, `third_party/libredwg/` trong repo, `PATH`. Không tìm thấy hoặc lỗi nặng thì báo người dùng xuất DXF từ AutoCAD (DXF 2018). |
| Đã thử thật | LibreDWG 0.14.9313 chuyển được `Typical tower 1 (ODU).dwg` (AC1032, 13 s, 129/129 layer, ezdxf đọc 0 lỗi) và file AC1021. |
| Đơn vị | Lấy từ `$INSUNITS`. Nếu bằng 0 (không khai báo) thì yêu cầu `--units`, không đoán. |
| Một file nhiều view | Bản vẽ Revit xuất ra chứa mặt bằng, mặt đứng, mặt cắt ở các tọa độ rất xa nhau. Tool gom primitive thành các view theo khoảng cách, đề xuất view có nhiều vai trò layer nhất, người dùng đổi được bằng `--view`. |
| Nhận diện layer | Luật theo từ khóa tên layer (bảng cố định, có test) cho ra vai trò: `wall_ext`, `wall_int`, `balcony`, `rail`, `column`, `slab`, `odu`. Người dùng sửa trong `ingest.yaml`. Không gõ cứng tọa độ hay tên layer của một dự án. |
| Nhận diện dàn nóng | Block (INSERT) nằm trong view và thuộc layer vai trò `odu`, hoặc có tên khớp mẫu `odu`, `vrf`, `condens`, `outdoor`, `dàn nóng`. Loại theo diện tích chân đế (mặc định 0,2 đến 3 m²) để bỏ khung hộp, lồng che. Gộp các block trùng vị trí. |
| Xác nhận | `geometry` từ chối chạy khi `status` chưa là `confirmed`. `odu-cfd ingest <dự án> --confirm` đặt trạng thái sau khi người dùng xem ảnh và sửa file. Có kiểm tra tối thiểu (có đường bao, có ít nhất một dàn nóng). |
| Phạm vi | Giai đoạn này chỉ xử lý CAD. Excel thông số và PDF tham chiếu chuyển sang giai đoạn dùng đến chúng (thư viện ODU, kiểm chứng) để tránh làm thừa. |

## 3. Mô hình hình học

Mặt bằng tầng điển hình được lặp `building.num_floors` lần với bước `building.floor_height_m` (từ `project.yaml`).

- **Khối nhà**: đường bao tầng (đa giác lấp đầy từ tường ngoài/sàn) trừ phần ban công lõm, đùn từ z = 0 đến tổng chiều cao, một khối kín.
- **Sàn ban công**: đa giác ban công, dày `geometry.slab_thickness_m` (mặc định 0,15 m), mỗi tầng một tấm.
- **Lan can**: đường lan can dày `geometry.rail_thickness_m` (0,05 m), cao `geometry.rail_height_m` (1,1 m) tính từ mặt sàn ban công. Độ rỗng của lan can là tham số của giai đoạn CFD, không xử lý ở đây.
- **Dàn nóng**: hộp theo chân đế đọc từ bản vẽ (đã tính tỷ lệ và góc xoay), cao theo thư viện ODU nếu có `--library`, nếu không dùng `geometry.odu_default_height_m` (1,0 m). Mỗi dàn lặp ở mọi tầng, tên `ODU-01_f00`, `ODU-01_f01`, ...
- Mọi phần là khối kín, hướng pháp tuyến nhất quán (kiểm tra bằng số, ghi vào `geometry.json`), vì snappyHexMesh cần bề mặt kín.

Cảnh báo ghi vào `geometry.json`: dàn nóng nằm ngoài mọi đa giác ban công, đường bao rỗng hoặc quá nhỏ, phần không kín.

## 4. Viewer 3D offline

`viewer.html` là một file duy nhất: three.js (bản UMD r147, giấy phép MIT) đặt sẵn trong repo, scene.glb nhúng base64. Xoay/phóng/dịch, bật tắt từng nhóm (khối nhà, sàn, lan can, dàn nóng), dàn nóng tô màu riêng. Không tải gì từ mạng. three.js được tải một lần lúc phát triển, ghi SHA-256.

## 5. Kiểm thử

- Mọi test dùng bản vẽ DXF tổng hợp sinh bằng ezdxf (`tests/dxf_factory.py`), không phụ thuộc file mạng nội bộ.
- Test tích hợp trên bản vẽ thật Spring Light chạy khi đặt biến `ODU_CFD_SAMPLE_DWG`, bỏ qua nếu không có.
- Nghiệm thu giai đoạn: chạy `ingest` rồi `geometry` trên Spring Light (DWG thật), xem `overlay.png` và `viewer.html`, ghi ghi chú các điểm heuristic chưa đúng.

## 6. Rủi ro

| Rủi ro | Cách xử lý |
|---|---|
| LibreDWG đọc sót đối tượng ở file khác | Báo rõ số lỗi, cho phép xuất DXF thủ công |
| Tường vẽ nét đôi hoặc không khép kín | Lấp lỗ, bỏ mảnh nhỏ; không dựng được thì báo lỗi nêu layer, không đoán |
| Dàn nóng vẽ bằng block đặt tên tùy ý | Người dùng sửa danh sách trong `ingest.yaml` sau khi xem ảnh |
| Bản LibreDWG là bản dev, chưa có checksum cho zip | Ghi phiên bản đã thử, ghim khi đóng gói |
| LibreDWG giấy phép GPL | Dùng nội bộ không vướng; xem lại nếu phân phối ra ngoài |
