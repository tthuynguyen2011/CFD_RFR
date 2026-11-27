# ODU-CFD: Công cụ tự động đánh giá nhiệt độ ban công đặt dàn nóng — Thiết kế

Ngày: 2026-11-26 · Trạng thái: bản nháp chờ duyệt

## 1. Mục tiêu

Phần mềm chạy local (không cần internet) nhận bản vẽ CAD, PDF, thông số dàn nóng (ODU) và khí hậu,
tự động mô phỏng CFD cho **toàn bộ tòa nhà**, và xuất:

1. Nhiệt độ hút vào của từng dàn nóng, nhiệt độ từng ban công, **chỉ số quẩn gió R**.
2. **Mô hình 3D** tòa nhà, ban công, dàn nóng (STL/glTF + viewer 3D).
3. **Mô phỏng dòng chảy CFD**: trường nhiệt độ, vận tốc, đường dòng, mặt cắt (ảnh + viewer 3D tương tác).
4. Báo cáo Excel + Word, và **giải pháp giảm nhiệt** có xếp hạng.

Độ chính xác mục tiêu: khớp báo cáo của hãng (Daikin, Panasonic) trong ±2 °C trên nhiệt độ hút từng dàn,
được kiểm chứng bằng dữ liệu thực có trong `00. CFD SIMULATION`.

Không nằm trong phạm vi: tool cũ (`03 Case study`, `00_TOOLS`) — ngừng dùng, không sửa, không xóa; chỉ đọc dữ liệu gốc.

## 2. Ràng buộc

- Offline hoàn toàn khi chạy. Thư viện web (three.js) được vendored trong repo, không tải lúc chạy.
- Windows trước (blueCFD-Core 2024 = OpenFOAM 12, đã có tại `C:\blueCFD-Core-2024`), Linux/cloud dùng cùng OpenFOAM 12.
- Code và dữ liệu chạy trong `D:\CFD_Tool\` (D còn ~428 GB). Bản vẽ gốc trên ổ mạng chỉ đọc.
- Không thêm phụ thuộc runtime ngoài các gói đã có: ezdxf, numpy, scipy, shapely, pyvista/vtk, matplotlib,
  openpyxl, python-docx, pymupdf, pypdf, PyYAML (thêm), pytest (dev). GUI dùng thư viện chuẩn Python.
- Máy hiện tại (4 lõi, 16 GB) chạy chế độ sàng lọc thô. Kết quả chính thức ±2 °C cần máy mạnh hơn;
  tool phải cảnh báo rõ khi lưới/cấu hình không đủ cho mức tin cậy chính thức.

## 3. Kiến trúc

```
D:\CFD_Tool\
  docs\specs, docs\plans
  src\odu_cfd\
    ingest\      đọc DWG/DXF, PDF, Excel -> project.yaml + ảnh kiểm tra
    climate\     nhiệt độ thiết kế, profile gió ABL, bộ kịch bản
    odu\         thư viện model dàn nóng + ngưỡng từng hãng
    geometry\    dựng tòa nhà, ban công, lan can, ODU -> STL + glTF
    cfd\         sinh case OpenFOAM (vĩ mô + vi mô), kiểm tra lưới/hội tụ
    runner\      backend chạy: local-blueCFD | WSL/Linux | cloud (cùng giao diện)
    post\        T_hút từng dàn, R, đường dòng, mặt cắt, báo cáo
    viewer\      viewer 3D offline (HTML + three.js vendored)
    mitigate\    quét phương án giảm nhiệt, xếp hạng
    validate\    so với dữ liệu hãng, độc lập lưới (GCI)
    app\         giao diện local (localhost) + CLI
  projects\<tên>\  input\, project.yaml, cases\, results\, report\
  library\         model ODU, khí hậu
  tests\
```

Các giai đoạn tách rời, mỗi giai đoạn đọc file giai đoạn trước và ghi file riêng, chạy lại được từng bước:
`ingest -> scenarios -> build -> run -> post -> mitigate -> validate`.
Lỗi ở một giai đoạn dừng pipeline và báo nguyên nhân, không để kết quả sai đi tiếp.

## 4. Tự động hóa và giao diện

- **Một lệnh**: `odu-cfd run <project>` chạy toàn bộ pipeline; `odu-cfd <stage>` chạy riêng từng bước.
- **Giao diện local**: `odu-cfd ui` mở server `127.0.0.1` (thư viện chuẩn), trình duyệt hiển thị:
  chọn dự án, kiểm tra đầu vào (ảnh nhận diện ban công/ODU để người dùng xác nhận), theo dõi tiến độ và
  residuals thời gian thực, xem kết quả.
- **Đóng gói**: PyInstaller tạo thư mục chạy được không cần cài Python (giai đoạn sau, sau khi tool ổn định).
- Mọi cấu hình nằm trong một file `project.yaml` (schema có kiểm tra, báo lỗi rõ).

## 5. Đầu vào

| Đầu vào | Dùng cho |
|---|---|
| DWG/DXF mặt bằng tầng, mặt bằng ODU, vị trí/nhà lân cận | hình học, vị trí ODU, bối cảnh |
| PDF layout | tham chiếu đối chiếu, trích bảng nếu có |
| Excel thông số (nhiệt độ, gió, công suất, tải, louver) | `climate`, `odu`, kịch bản |
| Thư viện ODU của hãng | kích thước, lưu lượng, công suất, ngưỡng hút |

Nhận diện ban công/ODU bằng heuristic có **bước xác nhận của người dùng** (ảnh phủ lên bản vẽ); không dùng
tọa độ loại trừ gõ cứng trong code. DWG chuyển qua DXF tự động bằng LibreDWG (`dwg2dxf`, đã thử thật);
nếu không chuyển được thì yêu cầu người dùng xuất DXF và báo rõ. Chi tiết: `2026-11-26-stage2-ingest-geometry-design.md`.

## 6. Mô hình vật lý

1. **Dàn nóng**: Q_thải = công suất lạnh + công suất nén, nhân tỷ lệ tải. T_thổi = T_hút + Q_thải/(ρ·cp·V̇),
   tính theo T_hút thực của từng dàn. Tỷ lệ hoạt động đồng thời chọn dàn tắt theo quy tắc xác định.
   Louver bằng tổn thất áp suất Darcy-Forchheimer + góc lệch hướng thổi; cánh hướng gió là tham số hướng dòng.
2. **Hút và thổi thật**: mỗi dàn có vùng thổi (nguồn động lượng và nhiệt) và vùng hút (sink khối lượng
   bằng đúng lưu lượng) → bảo toàn khối lượng, khí nóng bị hút ngược thật. T_hút = trung bình diện tích
   trên mặt hút (không dùng một ô lưới gần nhất).
3. **Gió/khí hậu**: profile ABL theo độ cao và hệ số địa hình TCVN 2737; miền tính COST 732/AIJ
   (5H trước, 15H sau, 5H hai bên và trên; kiểm tra tỷ lệ chắn < 3%); nhà lân cận từ bản vẽ vị trí;
   nhiều hướng gió, nhiều tốc độ, có kịch bản lặng gió.
4. **Số học**: OpenFOAM 12, kOmega SST, `linearUpwind` bậc hai, steady cho kịch bản có gió, **transient
   (URANS) + trung bình thời gian cho lặng gió**. Lưới snappyHexMesh mịn dần quanh ban công
   (cỡ ô tối thiểu 0,1–0,15 m vĩ mô; 2–5 cm vi mô). ODU không dựng hình học nên lưới không phụ thuộc bề dày 0,34 m.
5. **Đa cấp trong một bài toán toàn tòa nhà**: cấp vĩ mô phủ toàn bộ ODU; cấp vi mô chạy cho các ban công
   báo nóng nhất (điều kiện biên lấy từ vĩ mô) để hiệu chỉnh/xác nhận. Hệ số hiệu chỉnh lấy từ `validate`.

## 7. Đầu ra

Mỗi dự án có thư mục `results\` và `report\`:

- `model3d\`: `building.stl`, `odu.stl`, `scene.glb` (tòa nhà, ban công, ODU, nhà lân cận, có tên đối tượng).
- `flow\`: ảnh PNG mặt cắt ngang tại cao độ ODU từng tầng, mặt cắt đứng, đường dòng, vector vận tốc; nhiệt độ
  bề mặt mặt tiền; dữ liệu VTK gốc.
- `viewer\index.html`: **viewer 3D offline tương tác**: xoay/zoom, bật tắt lớp (tòa nhà, ODU, trường T,
  đường dòng, mặt cắt kéo được), tô màu ODU theo T_hút và theo đạt/không đạt, chọn một ODU xem số liệu.
  Tự chứa dữ liệu, mở bằng trình duyệt không cần server hay mạng.
- `tables\`: CSV/Excel nhiệt độ hút từng ODU, tổng hợp theo ban công/tầng, chỉ số R, kịch bản.
- `report\`: báo cáo Word + Excel (đầu vào, giả định, hình, kết quả, kết luận theo ngưỡng từng hãng,
  độ tin cậy lưới/hội tụ, giải pháp giảm nhiệt).

## 8. Kiểm soát chất lượng (không để kết quả sai âm thầm)

- Kiểm tra lưới tự động: không có ODU nằm trong vùng đặc, chất lượng ô, số ô theo yêu cầu mức tin cậy.
- Hội tụ: residuals + ổn định của chính các đại lượng đầu ra (T_hút từng ODU) trên N vòng cuối; không chỉ
  nhìn residual.
- Bảo toàn khối lượng/năng lượng quanh miền và quanh từng ODU; cảnh báo nếu lệch quá ngưỡng.
- Không kẹp nhiệt độ ẩn (tool cũ kẹp giới hạn trên); nếu có giới hạn an toàn thì ghi cảnh báo vào báo cáo.
- Mỗi kết quả gắn mức tin cậy: `Sàng lọc` hoặc `Chính thức` tùy cấu hình thực tế đã chạy.

## 9. Kiểm chứng

- Dữ liệu chuẩn: bảng nhiệt độ hút từng dàn của Daikin và Panasonic (Spring Light) trong `04 WIP`.
- Chỉ số: sai số trung bình, sai số lớn nhất, xếp hạng ban công (Spearman) so với hãng.
- Độc lập lưới: ba cấp lưới, báo GCI.
- Kiểm chứng ngoài: chạy lại một dự án khác có báo cáo hãng (Sky Bridge hoặc 70 Tây Sơn) không dùng để hiệu chỉnh.
- Kiểm thử tự động (pytest) cho các phần không cần chạy CFD (parse, hình học, mô hình ODU, tính R, báo cáo)
  và một case CFD nhỏ chạy được trong vài phút trên máy hiện tại.

## 10. Giải pháp giảm nhiệt (`mitigate`)

Quét: hướng và góc louver, thổi lên/xuống, hộp dẫn dòng, khoảng cách giữa ODU, so le giữa các tầng, giảm tải
đồng thời, lỗ thoáng trần ban công, dời ODU. Mỗi phương án chạy lại `build -> run -> post`; kết quả xếp hạng
theo mức giảm T_hút lớn nhất và số ODU vượt ngưỡng, ghi rõ giả định. Phương án nặng được chạy ở cấp vi mô
cho ban công liên quan trước, rồi xác nhận lại ở cấp vĩ mô cho các phương án được chọn.

## 11. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| Máy hiện tại không đủ cho kết quả chính thức toàn tòa nhà | Chế độ sàng lọc; backend WSL/cloud cùng giao diện; cảnh báo mức tin cậy |
| DWG không đọc trực tiếp được | Chuyển DXF bằng công cụ có sẵn hoặc yêu cầu xuất DXF |
| Nhận diện ban công/ODU sai | Bước xác nhận bằng ảnh, không gõ cứng tọa độ |
| Steady RANS không hội tụ khi lặng gió | Dùng transient + trung bình thời gian |
| Dữ liệu hãng chỉ là kết quả của phần mềm khác, không phải đo thực tế | Báo cáo gọi rõ là "so với kết quả hãng", không gọi là sai số tuyệt đối |
| three.js cần tải một lần để vendored | Tải lúc phát triển, commit vào repo; runtime offline |

## 12. Thứ tự xây dựng (giai đoạn)

1. Khung dự án, `project.yaml` + schema, thư viện ODU/khí hậu, CLI.
2. `ingest` + `geometry` (DXF -> 3D, xác nhận bằng ảnh) + viewer hình học.
3. `cfd` + `runner` local trên một case nhỏ, kiểm tra lưới/hội tụ.
4. `post` (T_hút, R, ảnh, VTK) + viewer có trường T và đường dòng.
5. `validate` với Spring Light, hiệu chỉnh, kiểm chứng ngoài.
6. `mitigate`, báo cáo Word/Excel.
7. Giao diện local và đóng gói; backend Linux/cloud.

Mỗi giai đoạn có kế hoạch triển khai riêng sau khi spec này được duyệt.
