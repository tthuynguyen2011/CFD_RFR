# Review chéo giai đoạn 2 (lần 1) - phát hiện

Reviewer độc lập (opus, chỉ đọc) chạy trên 225 test pass, bản vẽ tổng hợp và bản vẽ thật Spring Light (`scratch/dwgtest/odu.dxf`, chuyển từ DWG). Script tái hiện: `scratch/review/`. [ĐÃ CHẠY] = kiểm chứng bằng script, [SUY LUẬN] = chỉ đọc code.

## Critical
- **C1** [ĐÃ CHẠY] `ingest/drawing.py` biến mỗi INSERT thành một hộp bao, `geometry/plan2d.py` chỉ lấy primitive `path`. Bản vẽ Revit thật: layer `A-214-M_CURT_WALL` (1820 đối tượng) và `A-340-M_RAILING` (128) toàn INSERT nên mất lan can, đường bao vỡ thành 111 mảnh (lớn nhất 28,3 m²), khối nhà không kín. Sửa: bung đệ quy INSERT trên layer có vai trò kết cấu (wall_ext, slab, balcony, rail, column), chỉ giữ hộp bao cho ứng viên dàn nóng.
- Về view: `V3` của file thật là tờ chi tiết bố trí dàn nóng (khung tờ vẽ trên layer M-EQPM, 4 cụm "ODU VRF MINI", nhãn ghi HxWxD 990x980x370, 16 kW, louver 80 %), không phải mặt bằng. V1 (259x183 m) không có dàn nóng nào. File DWG này có thể không có mặt bằng nào đặt sẵn dàn nóng cùng với đường bao tầng.

## Important
- **I1** [ĐÃ CHẠY] `geometry/mesh.py`: tường bên dựng theo cạnh vòng, mặt trên lấy từ CDT nên lưới không kín khi hai đa giác chạm nhau tại đỉnh hoặc lỗ chạm biên ngoài, nhưng vẫn xuất STL và trả mã 0. Sửa: sinh tường bên từ cạnh biên của tam giác CDT; phần không kín là lỗi (mã 2), không chỉ cảnh báo.
- **I2** [ĐÃ CHẠY] `geometry` chỉ kiểm `status`. Sửa tay `ingest.yaml` vẫn qua: `odus: []`, id trùng (vùng bị ghi đè), `source_file: ../outside.dxf` hoặc đường dẫn tuyệt đối, size 500 m, bbox ±1e9. Sửa: `read_ingest_config` chặt hơn, `geometry` chạy lại cùng kiểm tra tối thiểu như `--confirm`, id duy nhất khớp `^[A-Za-z0-9_.-]+$`, `source_file` tương đối nằm trong `input/`, giới hạn kích thước dàn nóng.
- **I3** [ĐÃ CHẠY] Chạy lại `ingest` ghi đè `ingest.yaml` đã xác nhận và mất sửa tay. Sửa: từ chối khi đang `confirmed` trừ khi `--force`; khi ghi đè thì sao lưu `ingest.yaml.bak`.
- **I4** [ĐÃ CHẠY, LibreDWG thật] `dwg2dxf` lỗi với đường dẫn có tiếng Việt (`tầng điển hình.dwg`, `thư mục/`), mã 1 "File not found"; `text=True` làm đọc stderr lỗi UnicodeDecodeError và mất chi tiết lỗi. Sửa: chuyển đổi trong thư mục tạm tên ASCII rồi chuyển kết quả về; đọc stderr bằng bytes, giải mã `errors="replace"`.
- **I5** [ĐÃ CHẠY] Bộ đệm DXF theo mtime: dùng lại DXF cũ khi DWG mới có mtime cũ hơn; dùng lại file dở dang sau khi dwg2dxf crash (23 byte); `X.dwg` + `input/X.dxf` của người dùng bị coi là kết quả chuyển đổi. Sửa: đệm theo SHA-256 của DWG (file sidecar), ghi ra file tạm rồi đổi tên, xóa output khi lỗi, đặt tên đầu ra riêng (`<tên>.converted.dxf`).
- **I6** Nhận diện dàn nóng. [ĐÃ CHẠY] Chân đế phóng to: block "ODU VRF MINI" ra 0,98x1,022 m trong khi nhãn ghi sâu 0,37 m (hộp bao tính cả chữ/ký hiệu). Góc xoay lấy từ `dxf.rotation` nên sai khi mirror bằng extrusion; dàn nóng lồng trong block nhóm không tìm thấy; MINSERT chỉ đếm 1. Sửa: góc xoay từ `atan2` của các góc đã biến đổi; duyệt INSERT lồng và MINSERT; bỏ TEXT/MTEXT/DIMENSION/ATTRIB khỏi hộp bao; cho phép thư viện ODU ghi đè W x D.
- **I7** [ĐÃ CHẠY] Các phần giao nhau không kiểm tra: lan can dọc mặt tiền giao khối nhà, dàn nóng sát tường giao khối nhà, dàn nóng cao 3,2 m với tầng cao 3,0 m xuyên sàn trên, `rail_height_m=3.5` được nhận. Sửa: trừ lan can cho khối nhà, cảnh báo khi dàn nóng giao khối nhà/lan can, kiểm tra `slab + max(odu_h, rail_h) < floor_height`, cận trên cho `GeometryConfig`.
- **I8** [ĐÃ CHẠY 22 mutation] Mutation còn sống: bỏ lấp lỗ; đảo dấu xoay hộp 3D; đảo dấu xoay overlay; bỏ xếp hạng view theo số vai trò; lan can không nâng lên mặt sàn; bỏ kiểm tra `returncode >= 128` (test hiện pass vì sai lý do). `test_up_to_date_output_is_reused` khẳng định đúng hành vi lỗi của I5. Thiếu test tích hợp `ODU_CFD_SAMPLE_DWG` (spec §5).

## Minor
- m1 view chỉ một đường thẳng cho bbox suy biến, `ingest` vẫn mã 0 nhưng bước sau bị reader từ chối. m2 DXF rỗng báo nhầm "không khai báo đơn vị". m3 sân trong/giếng trời bị lấp thành khối đặc, nên cảnh báo khi lỗ lớn hơn vài m². m4 `_safe_name` làm "ODU 01" và "ODU_01" trùng. m5 các phần chạm mặt đồng phẳng (lưu ý cho snappyHexMesh). m6 tọa độ không dời về gốc (≈ -1000 m); nên ghi offset vào `geometry.json`. m7 `M-567-M_MECH_EQP`, `RFR-MVAC-PAD` không có vai trò (chấp nhận được: không phải dàn nóng); file thật không có layer ban công.

## Đã đạt
subprocess dùng danh sách tham số có timeout, `safe_load`, title được `html.escape`, SHA256SUMS của three.js r147 khớp, STL kín/dương/không suy biến trên ca tổng hợp, GLB y-up đúng, đơn vị mét.
