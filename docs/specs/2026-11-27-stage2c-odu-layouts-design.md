# Giai đoạn 2c: phương án bố trí dàn nóng và trình chỉnh 3D

Ngày: 2026-11-27. Bổ sung cho giai đoạn 2 (`2026-11-26-stage2-ingest-geometry-design.md`) theo yêu cầu: vị trí dàn nóng
do kiến trúc đề xuất ban đầu, CFD dùng để chọn phương án hợp lý, nên người dùng phải chỉnh tay được vị trí và hướng
xoay, tốt nhất ngay trên hình 3D.

## 1. Thay đổi quan điểm

Dàn nóng không còn là dữ liệu cố định đọc từ bản vẽ mà là **biến thiết kế**. Một dự án có nhiều **phương án bố trí**
(layout). Giai đoạn CFD sau này chạy ma trận kịch bản gió x phương án bố trí và so sánh nhiệt độ hút từng dàn;
giai đoạn `mitigate` sẽ sinh thêm phương án và xếp hạng. Vì vậy mỗi phương án là một file riêng, có thể sao chép,
so sánh, lưu vào git.

## 2. Mô hình dữ liệu

**Ban công** (`<dự án>/balconies.yaml`, do `geometry` sinh, người dùng sửa cờ `allowed`): mỗi ban công trích từ bản vẽ
có `id` (`B01`, `B02`, ... đánh số theo tâm: y rồi x, làm tròn 1 mm), `centroid`, `area_m2`, `polygon`, `allowed`
(mặc định true), `note`. Chạy lại `geometry` giữ nguyên `allowed`/`note` cho ban công có tâm trùng (cách < 0,5 m).
`allowed: false` nghĩa là kiến trúc không cho đặt dàn nóng ở ban công đó.

**Phương án bố trí** (`<dự án>/layouts/<tên>.yaml`, tên khớp `^[A-Za-z0-9_.-]{1,64}$`):

```yaml
name: KT-v1
description: Phương án kiến trúc đề xuất
source: architect          # architect | rule | drawing | manual
floors: "4-19,22-23"       # mức tầng 1-based mà bố trí này áp dụng (tầng 1 có sàn ở z = 0)
odus:
  - id: ODU-01             # ^[A-Za-z0-9_.-]+$, duy nhất
    x: 6.46                # tâm chân đế, mét, hệ tọa độ bản vẽ
    y: 1.615
    rotation_deg: 180      # xoay ngược chiều kim đồng hồ quanh tâm
    model_id: null         # null = project.odu.model_id
    size: null             # [w, d] mét; null = lấy từ thư viện, nếu không có thì mặc định trong geometry
    floors: null           # null = dùng floors của phương án; hoặc chuỗi riêng
```

Quy ước hướng: chân đế có rộng w theo trục cục bộ x, sâu d theo trục cục bộ y. **Mặt thổi (front) là trục cục bộ +y**,
nên hướng thổi trên mặt bằng = `rotation_deg + 90°` (góc ngược chiều kim đồng hồ từ trục +x). Viewer vẽ mũi tên hướng thổi.
Quy ước mặt hút/thổi chi tiết cho CFD thuộc giai đoạn CFD.

Kích thước mặc định khi không có thư viện: `geometry.odu_default_width_m` (1,0) và `geometry.odu_default_depth_m` (0,4)
trong `project.yaml`, kiểm tra dương hữu hạn có cận trên 5 m, như các tham số hình học khác.

## 3. Kiểm tra tính hợp lệ (dùng chung CLI, server và dựng 3D)

Lỗi (chặn lưu, chặn dựng 3D):
- tầng ngoài [1, `num_floors`] hoặc danh sách tầng rỗng, id sai/trùng, tọa độ không hữu hạn;
- chân đế không nằm trọn trong một ban công (dung sai 1 mm); nằm trong ban công `allowed: false`;
- hai dàn nóng chồng nhau (diện tích giao > 1e-4 m²) ở ít nhất một tầng chung.

Cảnh báo (không chặn): chiều cao dàn nóng cộng sàn không thấp hơn chiều cao tầng (đã có ở dựng 3D); ban công cho phép
nhưng bố trí không đặt dàn nào (chỉ hiển thị trong CLI `layout validate --verbose`).

## 4. Sinh bố trí tự động (a) và từ bản vẽ (c)

**Theo quy tắc** (`layout auto`): với mỗi ban công `allowed` (lọc theo `--min-area`, `--balconies`):
1. Hướng ra ngoài `n_out` = từ điểm gần nhất của khối nhà (đường bao trừ ban công) tới tâm ban công. Nếu không có khối nhà thì theo trục ngắn của hình chữ nhật bao nhỏ nhất.
2. Dàn nóng dựa lưng vào tường: tâm cách mặt tường `wall_gap + d/2` theo `n_out`; hàng xếp dọc theo `t` (n_out xoay +90°), căn giữa ban công, khoảng hở `spacing`.
3. `--pattern row` xếp một hàng, `grid` nhiều hàng từ tường ra; số lượng `--count`, bớt đi (kèm cảnh báo) nếu không đủ chỗ.
4. `--facing outward` (mặt thổi theo `n_out`) hoặc một góc tuyệt đối theo độ.
5. Id tuần tự `ODU-01`... theo thứ tự ban công; dàn nào không nằm trọn ban công thì bỏ kèm cảnh báo.

**Từ bản vẽ** (`layout from-ingest`): chuyển các dàn nóng nhận diện ở `ingest.yaml` thành phương án (`source: drawing`),
giữ tâm và góc xoay, bỏ kích thước đo từ bản vẽ (thư viện/mặc định áp dụng, vì hộp bao block hay sai). Dàn nào không rơi
vào ban công nào vẫn giữ lại và bị báo lỗi khi kiểm tra.

## 5. Dựng 3D theo phương án

- `geometry` luôn ghi: `input/geometry/plan.json` (đường bao, ban công có id, lan can, tham số tầng), `base.glb`
  (khối nhà, sàn ban công, lan can) và `balconies.yaml`.
- `geometry --layout TÊN` kiểm tra phương án rồi ghi ra `input/geometry/layouts/<TÊN>/`: `building.stl`, `balcony.stl`,
  `rail.stl`, `odu.stl`, `scene.glb`, `geometry.json`, `viewer.html` (thư mục tự đủ cho một ca CFD). Dàn nóng chỉ xuất hiện
  ở các tầng trong `floors`. Vùng STL đặt tên `<id>_f<NN>` như trước (NN = chỉ số tầng 2 chữ số, tầng 1 là `f00`).
- `geometry` không có `--layout` giữ hành vi cũ (dàn nóng từ `ingest.yaml`, nếu có), nhưng `ingest.yaml` không còn bắt
  buộc có dàn nóng; thiếu thì cảnh báo và hướng dẫn tạo phương án.
- `ingest --confirm` chỉ cần đường bao (wall_ext hoặc slab).

## 6. Trình chỉnh 3D (`odu-cfd edit <dự án> [--layout TÊN]`)

Server cục bộ bằng thư viện chuẩn (`http.server`), chỉ nghe `127.0.0.1`, cổng tự chọn, mở trình duyệt. Không cần internet.
Trang chỉnh dùng lại three.js đã đặt sẵn.

Giao diện:
- Hai chế độ nhìn: **3D** và **mặt bằng** (chiếu trực giao nhìn từ trên xuống, để đặt chính xác).
- Ban công tô màu: cho phép (xanh), không cho phép (xám). Chọn một ban công để bật/tắt `allowed` (lưu vào `balconies.yaml`).
- Chọn tầng đang hiển thị để chỉnh; dàn nóng của các tầng khác cùng phương án hiện mờ. Chỉnh trên tầng điển hình
  áp dụng cho mọi tầng trong `floors`.
- Dàn nóng là hộp w x d x h kèm mũi tên hướng thổi; đỏ khi vi phạm kiểm tra, vàng khi đang chọn.
- Thao tác: bấm chọn; kéo để di chuyển trên mặt sàn ban công; nút và phím xoay (R/Shift+R: ±15°, nút ±90°);
  ô nhập số x, y, góc xoay, hướng thổi; thêm (đặt ở tâm ban công đang chọn), nhân bản, xóa (Delete);
  bắt dính lưới (mặc định 0,05 m) và góc (15°) bật/tắt; hoàn tác/làm lại (Ctrl+Z/Ctrl+Y).
- Kiểm tra liên tục: sau mỗi thay đổi gọi server kiểm tra (một nguồn logic duy nhất bằng Python), danh sách vấn đề hiện ở bảng bên.
- Lưu (Ctrl+S) ghi `layouts/<tên>.yaml` (sao lưu `.bak`); lưu thành phương án mới; chuyển phương án; báo thay đổi chưa lưu.
- Lỗi hợp lệ chặn lưu và hiện nguyên nhân.

API cục bộ: `GET /`, `GET /api/state`, `GET /scene.glb` (= `base.glb`), `POST /api/validate`, `POST /api/save`,
`POST /api/balconies`. Bảo vệ: kiểm tra header `Host` (127.0.0.1/localhost kèm đúng cổng), `Origin` nếu có, token ngẫu nhiên
trong header `X-Token` cho mọi `POST`, giới hạn thân yêu cầu 1 MB, tên phương án theo regex, không bao giờ ghi ngoài
`layouts/` và `balconies.yaml`.

## 7. Kiểm thử

- Mọi logic (tên, tầng, kiểm tra, sinh tự động, từ bản vẽ, server) có test pytest trên bản vẽ tổng hợp; server test bằng
  `http.client` trên cổng 0.
- Trang chỉnh có chế độ tự kiểm `?selftest=1`: chạy chuỗi thao tác (thêm, di chuyển, xoay, hoàn tác, lưu) qua cùng các
  hàm mà giao diện dùng, ghi kết quả JSON vào DOM; kiểm chứng bằng Edge headless (`--dump-dom`) và chụp ảnh.
- Nghiệm thu: `SPRING_PLAN.dxf` (28 ban công): `layout auto`, mở trình chỉnh, di chuyển và xoay một dàn nóng, lưu,
  `geometry --layout`, xem viewer.

## 8. Ngoài phạm vi

Hút/thổi chi tiết của từng mặt cho CFD, thay đổi bố trí tự động để giảm nhiệt (giai đoạn `mitigate`), đăng ký tờ chi tiết dàn
nóng với mặt bằng, trích thông số dàn nóng từ chữ trong bản vẽ, Excel/PDF.
