# Giai đoạn 2c: phương án bố trí dàn nóng và trình chỉnh 3D - kết quả

Ngày: 2026-11-27. 786 test pass, 1 bỏ qua (test tích hợp cần `ODU_CFD_SAMPLE_DWG`). Chưa commit.

## Đã có

- Phương án bố trí: `layouts/<tên>.yaml` (x, y, góc xoay, model, kích thước, tầng áp dụng). Quy ước: mặt thổi là trục cục bộ +y, hướng thổi = rotation + 90°.
- Ban công có id và cờ `allowed`: `balconies.yaml`. Giữ cờ khi chạy lại `geometry`, cảnh báo khi cờ/ghi chú bị mất vì ban công dời quá 0,5 m.
- Kiểm tra hợp lệ dùng chung (CLI, server, dựng 3D): ngoài ban công, ban công không cho phép, chồng nhau ở tầng chung, tầng ngoài phạm vi, id, kích thước.
- (a) `layout auto`: dựa lưng tường, hàng hoặc lưới, hướng thổi ra ngoài tính từ các cạnh hở của ban công, trượt tìm chỗ cho ban công L/U. (c) `layout from-ingest`.
- `geometry --layout TÊN` ghi thư mục tự đủ `input/geometry/layouts/<TÊN>/` (STL, GLB, geometry.json, viewer.html); phương án lỗi thì không ghi gì và không đổi `balconies.yaml`.
- `odu-cfd edit`: server 127.0.0.1 + trang chỉnh 3D/mặt bằng (kéo, xoay, nhập số, thêm/nhân bản/xóa, hoàn tác, lưu, chuyển phương án, bật/tắt ban công).

## Review chéo lần 1 và sửa

Reviewer độc lập (opus) tìm: hướng thổi sai ở 7/28 ban công thật; vách nhà dày vài mm chắn ban công (19/28 ban công); mất cờ allowed khi ban công dời; `auto` không đặt được ở ban công L/U; server không timeout; tên Windows đặc biệt (CON, NUL...); validate và save không nhất quán; test mũi tên/ô hướng thổi yếu. Tất cả đã sửa trừ những mục ghi ở "Chưa làm". Sau sửa: 0/28 ban công sai hướng và 28/28 ban công đặt được 4 dàn; building.stl còn vách mỏng bằng 0 (cảnh báo "bỏ 19 mảnh tường mỏng < 12 cm, 1,21 m²"); mutation M12/M13/M14 của trang chỉnh đều làm test đỏ.

## Giới hạn và chưa làm

- Chưa kiểm bằng chuột/phím thật (chỉ gọi hàm và sự kiện con trỏ tổng hợp qua Edge headless). Cần người dùng thử kéo, xoay, phím R/Delete/Ctrl+S trên màn hình thật.
- Chưa đo hiệu năng trình chỉnh với 112 dàn x 16 tầng (cảnh có ~1900 đối tượng động, dàn mờ tối đa 4000 hộp).
- Bật/tắt `allowed` ban công chưa vào lịch sử hoàn tác; lưu không phát hiện hai tab ghi chồng nhau; kéo dàn không bị kẹp trong ban công (chỉ báo đỏ).
- Dàn nằm vắt qua hai ban công chạm nhau bị báo "ngoài ban công" (suy luận, chưa chạy riêng).
- Ban công L/U: dàn có thể không dựa đúng mặt lưng thật.
- `?selftest=1` trên dự án thật ghi `layouts/selftest.yaml` và bật/tắt ban công B01 hai lần (không dùng trên dự án thật).
- Cảnh báo sân trong lớn vẫn chưa phát hiện được (từ giai đoạn 2).
- Hút/thổi chi tiết từng mặt cho CFD, giai đoạn `mitigate`, trích thông số dàn nóng từ chữ trong bản vẽ, Excel/PDF: chưa làm.

## Cách dùng nhanh (Spring Light)

```
odu-cfd init projects/spring
odu-cfd ingest projects/spring SPRING_PLAN.dxf
odu-cfd ingest projects/spring --confirm
odu-cfd geometry projects/spring                      # sinh balconies.yaml, plan.json, base.glb
odu-cfd layout balconies projects/spring --deny B07   # ban công không cho đặt
odu-cfd layout auto projects/spring --name KT-v1 --floors "4-19,22-23" --count 4 --pattern grid --size 0.98,0.37
odu-cfd edit projects/spring --layout KT-v1           # chỉnh tay trên 3D, Ctrl+S lưu
odu-cfd geometry projects/spring --layout KT-v1       # dựng STL/GLB theo phương án
odu-cfd view projects/spring --layout KT-v1
```
