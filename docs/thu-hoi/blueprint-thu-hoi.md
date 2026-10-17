# Blueprint — THU HỒI HÀNG từ khách về công ty (vanchuyen + ketoan)

> Bản thiết kế chung cho HAI repo. Bản này nằm ở cả `vanchuyen/docs/thu-hoi/` lẫn
> `ketoan/docs/thu-hoi/` — sửa một bên thì chép sang bên kia.

## 1. Nghiệp vụ

Siêu thị (kênh MT) xuất trả hàng: hàng date / cận date, hàng thời vụ sau mùa, hàng
lỗi. Siêu thị gửi **phiếu xuất trả** (PDF/ảnh), công ty phải **cho xe vào lấy**, hàng
về kho thì **kiểm đếm**, rồi kế toán **lập hóa đơn trả về** (Sales Invoice `is_return`)
để ghi giảm công nợ.

Hôm nay việc này không có chỗ nào theo dõi: sổ `MT Hang Hoan` của ketoan chỉ có dòng
"lập tay" cho hàng date, còn `Su Co Van Chuyen` của vanchuyen chỉ cho đơn giao qua
nhà xe. Lần siêu thị gọi trả hàng mà chưa ai đi lấy, hay hàng đã về kho mà chưa ai lập
phiếu trả, là việc **vô hình** — lộ ra lúc siêu thị trừ tiền khi thanh toán.

Một **LÔ THU HỒI** = một lần siêu thị gọi trả, đi qua 6 chặng:

| # | Chặng | App giữ | Ai bấm |
|---|---|---|---|
| 1 | Tạo yêu cầu | vanchuyen | điều hành / tổ trưởng |
| 2 | Đã lấy hàng | vanchuyen | lái xe được giao (hoặc điều phối) |
| 3 | Đã nhận hàng | vanchuyen | điều phối / điều hành (hàng xuống kho) |
| 4 | Đã kiểm hàng | ketoan | người kiểm bấm **Chốt phiếu** |
| 5 | Đã nhập chứng từ | ketoan | MÁY SUY: hóa đơn trả về nháp phủ đủ số đã kiểm |
| 6 | Xong | ketoan | MÁY SUY: mọi hóa đơn trả về đã ghi sổ |

Giữa 3 và 4 có chặng phụ **Đang kiểm** (đã mở phiếu kiểm, chưa chốt) — để thấy việc
đang làm dở, không phải để bấm.

## 2. Hai bảng, hai chủ — không ai ghi bảng của người kia

Đúng luật đã có giữa hai app (`MT Hang Hoan` ↔ `Su Co Van Chuyen`): **mỗi app chỉ ghi
bảng của mình, đọc chéo thì đọc sống và mềm** (`table_exists` trước khi đọc).

```
vanchuyen: Lo Thu Hoi (TH-.YYYY.-.####)         ketoan: Kiem Hang Thu Hoi (name = tên lô)
  ├ khách + shipping_address_name                  ├ lo_thu_hoi  (Data, KHÔNG Link)
  ├ ngày yêu cầu, số phiếu xuất trả siêu thị       ├ company / customer / địa chỉ (chép lúc mở)
  ├ điều phối: ngày hẹn, lái xe, xe, chuyến        ├ items: Kiem Hang Thu Hoi Dong (SL ĐVT kho)
  ├ trang_thai: Tạo yêu cầu → Đã lấy → Đã nhận     ├ da_chot · khong_lap_hd (KTT)
  ├ items: Lo Thu Hoi Hang (SL siêu thị KHAI)      └ trang_thai: Đang kiểm → … → Xong
  └ File đính kèm (private, xem qua proxy có guard)
                         Sales Invoice.custom_kiem_hang_thu_hoi  (ketoan tạo, no_copy)
```

- `Kiem Hang Thu Hoi` **đặt tên bằng chính tên lô** (`autoname: field:lo_thu_hoi`):
  một lô chỉ có một phiếu kiểm, và hai người cùng bấm "Bắt đầu kiểm" thì khóa chính
  chặn người thứ hai — không cần chốt trùng bằng code như `MT Hang Hoan` phải làm.
- `lo_thu_hoi` là **Data**: ketoan phải cài được trên site chưa có vanchuyen.
- **Trạng thái tổng** của một lô = `COALESCE(kiem.trang_thai, lo.trang_thai)`. Cả hai
  màn (vanchuyen `#/thu-hoi`, ketoan `#/thu-hoi`) hiện cùng một con số.
- vanchuyen **khóa** khách/địa chỉ và không cho lùi/xóa lô khi ketoan đã mở phiếu
  kiểm — hóa đơn trả về dựng trên đúng khách đó.

## 3. Số lượng: KHAI vs KIỂM

`Lo Thu Hoi Hang.qty` là số **siêu thị khai** trên phiếu xuất trả (căn cứ đối chiếu).
`Kiem Hang Thu Hoi Dong.qty` là số **đếm thật** lúc hàng về, ĐVT kho. Phiếu kiểm đếm
**mù** (không điền sẵn từ số khai) rồi mới so: lệch là thứ đáng tiền nhất — siêu thị trừ
tiền theo số họ khai, mình chỉ trả về theo số mình nhận.

## 4. Hóa đơn trả về — luật dựng (đọc từ mã nguồn ERPNext v16 thật)

`erpnext/controllers/sales_and_purchase_return.py`:

- `validate_quantity`: hóa đơn trả về **`update_stock = 0`** (quy ước của ketoan:
  Client Script đặt `update_stock = !is_return`) thì ERPNext so **`qty` theo ĐVT của
  dòng**, không so `stock_qty`. Dòng trả nối `sales_invoice_item` vào dòng gốc "10 Thùng"
  mà ghi "70 Hộp" là so 70 với 10 — sai đơn vị, chặn nhầm hoặc cho qua nhầm.
- Vì vậy mỗi dòng trả nối vào dòng gốc **giữ đúng ĐVT + hệ số của dòng gốc**.
  Luật tách (hàm thuần `ketoan/api/thu_hoi_phan_bo.py`):
  1. Phần **chẵn đơn vị** của dòng gốc (chẵn thùng) → dòng NỐI, ĐVT gốc.
  2. Phần lẻ → dòng NỐI số lẻ **chỉ khi biểu diễn ĐÚNG** ở độ chính xác của ô `qty` và
     ĐVT cho phép số lẻ (24 hộp/thùng: 6 hộp = 0,25 thùng → được; 70/30 → không).
  3. Còn lại → dòng **KHÔNG NỐI**, ĐVT kho, đơn giá = đơn giá dòng gốc ÷ hệ số. ERPNext
     chỉ cảnh báo "Returned Item … does not exist" (không chặn); app tự giữ trần.
  Không bao giờ làm tròn số lượng: hóa đơn trả về là chứng từ có giá trị pháp lý, lệch
  100đ là lệch với số siêu thị trừ.
- Trần trả của một mặt hàng trên một hóa đơn gốc = đã bán − mọi lần trả (nối + không
  nối, **kể cả nháp**). ERPNext chỉ đếm bản đã ghi sổ; đếm cả nháp để hai bản nháp
  không cùng chiếm một phần hàng.
- `return_against` BẮT BUỘC: `mt._returns_join` chỉ trừ phiếu trả có nối hóa đơn gốc;
  phiếu trả đứng rời ghi giảm 131 mà không trừ vào hóa đơn nào.
- Hàng về từ NHIỀU hóa đơn gốc → nhiều hóa đơn trả về, mỗi tờ một `return_against`.
  Kế toán chọn hóa đơn gốc trong danh sách ứng viên (cùng khách, cùng điểm lên trước,
  có mặt hàng cần trả, còn trần trả); làm lại tới khi phủ đủ.
- TK doanh thu dòng trả → TK `5213` của công ty nếu có (Client Script cũng đặt
  "5213 - Hàng bán bị trả lại"). `update_stock = 0`: hàng vào kho bằng phiếu kho riêng
  sau khi lọc, như `Su Co Van Chuyen` đã ghi.
- Tạo **NHÁP** (`doc.insert()` tôn trọng quyền tạo Sales Invoice của người bấm), deep
  link Desk để soát + ghi sổ. Mở và lưu trên Desk thì Client Script tính lại số kiện /
  thể tích / bằng chữ.

## 5. Trạng thái phiếu kiểm — MÁY SUY, giữ bằng hook

```
khong_lap_hd = 1 (KTT kết luận, có lý do)          -> Xong
chưa chốt                                          -> Đang kiểm
chốt, hóa đơn trả về (docstatus<2) chưa phủ ĐÚNG    -> Đã kiểm hàng   (kèm "còn thiếu"/"thừa")
phủ đúng từng mặt hàng, còn bản nháp                -> Đã nhập chứng từ
phủ đúng, mọi bản đã ghi sổ                          -> Xong
```

Kế toán ghi sổ / hủy / xóa hóa đơn trả về THẲNG TRÊN DESK là chuyện thường, nên
`doc_events` Sales Invoice (`after_insert/on_update/on_submit/on_cancel/on_trash`) gọi
`thu_hoi.dong_bo_trang_thai` — bọc try/except, không bao giờ chặn ghi sổ, ghi bằng
`db_set` (không `save()` để khỏi chạy lại validate vào giữa giao dịch của hóa đơn).
Màn chi tiết vẫn suy lại lúc đọc.

## 6. Quyền

| | vanchuyen | ketoan |
|---|---|---|
| Lập/sửa/xóa lô, đính kèm, giao xe | điều hành (quyền ghi Sales Invoice), tổ trưởng, admin | — |
| Bấm "Đã lấy hàng" + chụp chứng từ | lái xe được giao lô | — |
| Theo dõi, kiểm hàng, chốt, mở lại, lập HĐ trả về | — | kế toán kênh bán hàng (NPP/MT/Du lịch) + KTT |
| Kết luận "Không lập hóa đơn trả" | — | KTT |

DocType chỉ cấp DocPerm System Manager (vanchuyen, như `Su Co Van Chuyen`) / vai trò kế
toán (ketoan); mọi thao tác portal qua whitelisted method có guard ở dòng đầu,
`ignore_permissions` chỉ dùng SAU guard trên đúng bản ghi. File đính kèm **private**,
xem qua method proxy có guard của từng app (kế toán không có quyền DocType bên vận
chuyển nên không mở thẳng được file private).

## 7. Màn hình

- vanchuyen `#/thu-hoi` (điều hành + tổ trưởng): danh sách thẻ, pill đếm theo chặng
  tổng, tìm khách/điểm/số phiếu; `#/thu-hoi/new` · `#/thu-hoi/:id`: khách → chọn
  địa chỉ (lọc theo Dynamic Link của khách, kèm mã điểm `MT Store` nếu có), ngày yêu
  cầu, số phiếu siêu thị, liên hệ, lý do, hàng khai, giao xe, đính kèm nhiều file,
  nút chuyển chặng + lùi chặng.
- vanchuyen `#/chuyen` (lái xe): khối "Lấy hàng thu hồi" — lô được giao cho mình, nút
  **Đã lấy hàng** + 📷 chứng từ.
- ketoan tab **Thu hồi** `#/thu-hoi`: theo dõi MỌI lô (pill 7 chặng), `#/thu-hoi/:id`:
  hồ sơ lô (đính kèm, hàng khai) + phiếu kiểm + so khai/kiểm + hóa đơn trả về.
- ketoan `#/kiem-hang/:id` (mobile, dựng theo màn Ghi hộp của sx): quét mã vạch
  (BarcodeDetector / zxing1d / máy quét cầm tay / gõ tay) hoặc tìm mã → bàn số phím to
  có tab Thùng/Hộp → lưu ngay; chạm số để sửa, ✕ để xóa; **Chốt phiếu** thì khóa,
  **Mở lại** thì sửa tiếp.

## 8. Ngoài phạm vi

- Phiếu nhập kho hàng trả về (Stock Entry) — thủ kho vẫn lập riêng sau khi lọc.
- Đọc phiếu xuất trả bằng AI (như Nhập đơn) — đính kèm file là đủ cho bản đầu.
- Tự đưa hóa đơn trả về vào sổ `MT Hang Hoan` (chứng từ thuế) — kế toán MT nhận từ
  màn Hàng hoàn như dòng lập tay.
