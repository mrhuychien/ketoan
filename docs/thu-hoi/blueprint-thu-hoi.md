# Blueprint — THU HỒI HÀNG từ khách về công ty (vanchuyen + ketoan)

> Bản thiết kế chung cho HAI repo. Bản này nằm ở cả `vanchuyen/docs/thu-hoi/` lẫn
> `ketoan/docs/thu-hoi/` — sửa một bên thì chép sang bên kia.

## 1. Nghiệp vụ

Siêu thị (kênh MT) xuất trả hàng: hàng date / cận date, hàng thời vụ sau mùa, hàng
lỗi. Siêu thị gửi **phiếu xuất trả** (PDF/ảnh) và thường cả **mail liệt kê hàng cần
thu**; công ty thuê **đơn vị vận chuyển (Viettel Post / Nhất Tín) vào lấy**, hàng về kho
thì **kiểm đếm**, rồi kế toán **lập hóa đơn trả về** (Sales Invoice `is_return`) để ghi
giảm công nợ.

Hôm nay việc này không có chỗ nào theo dõi: sổ `MT Hang Hoan` của ketoan chỉ có dòng
"lập tay" cho hàng date, còn `Su Co Van Chuyen` của vanchuyen chỉ cho đơn giao qua
nhà xe. Lần siêu thị gọi trả hàng mà chưa ai đi lấy, hay hàng đã về kho mà chưa ai lập
phiếu trả, là việc **vô hình** — lộ ra lúc siêu thị trừ tiền khi thanh toán.

Một **LÔ THU HỒI** = một lần siêu thị gọi trả, đi qua 6 chặng:

| # | Chặng | App giữ | Ai bấm |
|---|---|---|---|
| 1 | Tạo yêu cầu | vanchuyen | điều hành / tổ trưởng |
| 2 | Đã lấy hàng | vanchuyen | điều hành / tổ trưởng (đơn vị thu hồi báo đã lấy) |
| 3 | Đã nhận hàng | vanchuyen | điều hành / tổ trưởng (hàng về kho, đếm kiện) |
| 4 | Đã kiểm hàng | ketoan | người kiểm bấm **Chốt phiếu** |
| 5 | Đã nhập chứng từ | ketoan | MÁY SUY: hóa đơn trả về nháp phủ đủ số đã kiểm |
| 6 | Xong | ketoan | MÁY SUY: mọi hóa đơn trả về đã ghi sổ |

Giữa 3 và 4 có chặng phụ **Đang kiểm** (đã mở phiếu kiểm, chưa chốt) — để thấy việc
đang làm dở, không phải để bấm. Ngoài tiến trình có **Đã hủy** (xem §5b): lô dừng hẳn,
giữ lại làm dấu vết.

## 2. Hai bảng, hai chủ — không ai ghi bảng của người kia

Đúng luật đã có giữa hai app (`MT Hang Hoan` ↔ `Su Co Van Chuyen`): **mỗi app chỉ ghi
bảng của mình, đọc chéo thì đọc sống và mềm** (`table_exists` trước khi đọc).

```
vanchuyen: Lo Thu Hoi (TH-.YYYY.-.####)         ketoan: Kiem Hang Thu Hoi (name = tên lô)
  ├ khách + shipping_address_name                  ├ lo_thu_hoi  (Data, KHÔNG Link)
  ├ ngày yêu cầu, số phiếu xuất trả siêu thị       ├ company / customer / địa chỉ (chép lúc mở)
  ├ điều phối thu hồi: đơn vị (Viettel Post /       ├ items: Kiem Hang Thu Hoi Dong (SL ĐVT kho)
  │   Nhất Tín), mã vận đơn, ngày thu, số kiện      ├ da_chot · khong_lap_hd (KTT)
  ├ chi_tiet_hang: dán NGUYÊN VĂN mail siêu thị    └ trang_thai: Đang kiểm → … → Xong
  ├ trang_thai: Tạo yêu cầu → Đã lấy → Đã nhận
  └ File đính kèm: ảnh/PDF/Excel/Word/mail (private, xem qua proxy có guard)
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

Bên vận chuyển KHÔNG gõ từng mã hàng: siêu thị khai gì thì nằm ở mail (dán nguyên văn
vào `chi_tiet_hang`) và file đính kèm. Mã hàng + số lượng chính xác là việc của kế toán:
`Kiem Hang Thu Hoi Dong.qty` là số **đếm thật** lúc hàng về, ĐVT kho, đếm **mù** (màn
kiểm hàng trên điện thoại không hiện số khai) — lệch với số siêu thị khai là thứ đáng
tiền nhất: siêu thị trừ tiền theo số họ khai, mình chỉ trả về theo số mình nhận.

Bản đầu có bảng hàng khai có cấu trúc (`Lo Thu Hoi Hang`, mã + ĐVT + số lượng) do bên vận
chuyển gõ. Đã bỏ khỏi màn hình và khỏi lô (không còn field cha); DocType giữ lại để các
lô cũ vẫn có số khai — ketoan đọc mềm, lô nào có thì bảng so sánh mới hiện cột "khai".

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
  Kế toán chọn hóa đơn gốc trong danh sách ứng viên = MỌI hóa đơn bán đã ghi sổ của ĐÚNG
  khách + ĐÚNG điểm giao của lô (50 tờ một trang, mới nhất trước, tìm theo số HĐ / PO /
  số HĐĐT), mỗi dòng đủ khách · điểm giao · địa chỉ · số tiền · còn nợ · đã trả về. Không
  lọc theo mã đã kiểm: tờ không còn gì để trả vẫn hiện, chỉ khóa nút lập + nói lý do. Hàng
  giao điểm khác rồi siêu thị gom về đây trả → "Xem mọi điểm của khách" (vẫn đúng khách).
  Làm lại tới khi phủ đủ.
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

## 5b. Hủy yêu cầu — GIỮ dấu vết, không xóa

Siêu thị rút yêu cầu, lập trùng lô, đơn vị vận chuyển không lấy được hàng… → điều hành
bấm **Hủy yêu cầu** (`vanchuyen.api.thu_hoi.huy_lo`), lý do BẮT BUỘC. Lô sang **Đã hủy**
kèm `ly_do_huy` · `huy_boi` · `huy_luc` · `huy_tu` (chặng lúc hủy). "Xóa lô" vẫn chỉ cho lô
lập nhầm còn "Tạo yêu cầu"; hủy thì lô còn đó để trả lời "lô này đi đâu rồi".

- **Đã hủy không phải một nấc của 7 chặng**: không tính vào "Đang mở", có pill riêng, xếp
  CUỐI danh sách ở cả hai app (`FIELD()` trả 0 cho giá trị lạ = lên đầu — phải liệt kê).
- **Chỉ hủy khi kế toán CHƯA mở phiếu kiểm.** Đã mở thì phiếu kiểm / hóa đơn trả về đang
  dựng trên lô: kế toán **xóa phiếu kiểm** trước (phiếu chưa chốt, chưa có hóa đơn trả
  về), hoặc KTT kết luận **không lập hóa đơn trả về** (lô thành Xong). Controller `Lo Thu
  Hoi` chặn thêm một lần — kể cả sửa trên Desk.
- **Không chạy đua**: `huy_lo` khóa hàng lô + đọc KHÓA phiếu kiểm (`FOR UPDATE`);
  `bat_dau_kiem` bên ketoan đọc lô bằng KHÓA. Hai nút bấm cùng lúc thì một bên chờ bên
  kia xong rồi thấy kết quả — không có lô vừa hủy vừa đang kiểm.
- **Lô hủy chỉ xem**: không sửa, không chuyển chặng, không xóa; đính kèm VẪN thêm được
  (mail hủy của siêu thị hay đến sau). Kế toán thấy khung "đã HỦY" + lý do, không có nút
  "Bắt đầu kiểm hàng"; controller `Kiem Hang Thu Hoi` cũng không cho mở phiếu cho lô hủy
  (kể cả tạo tay trên Desk).
- **Khôi phục** (`khoi_phuc_lo`) khi hủy nhầm: về ĐÚNG chặng `huy_tu`, dấu hủy trên bản
  ghi được xóa; dấu cũ còn trong lịch sử thay đổi (Version — DocType bật `track_changes`).

## 6. Quyền

| | vanchuyen | ketoan |
|---|---|---|
| Lập/sửa/xóa lô, đính kèm, điều phối thu hồi, chuyển chặng, hủy / khôi phục | điều hành (quyền ghi Sales Invoice), tổ trưởng, admin | — |
| Theo dõi, kiểm hàng, chốt, mở lại, lập HĐ trả về | — | kế toán kênh bán hàng (NPP/MT/Du lịch) + KTT |
| Kết luận "Không lập hóa đơn trả" | — | KTT |

DocType chỉ cấp DocPerm System Manager (vanchuyen, như `Su Co Van Chuyen`) / vai trò kế
toán (ketoan); mọi thao tác portal qua whitelisted method có guard ở dòng đầu,
`ignore_permissions` chỉ dùng SAU guard trên đúng bản ghi. File đính kèm **private**,
xem qua method proxy có guard của từng app (kế toán không có quyền DocType bên vận
chuyển nên không mở thẳng được file private). Proxy chỉ mở **trong tab** ảnh / PDF; loại
khác **tải về** — và upload không nhận loại chạy được script (html / svg / xml / js…): proxy
phục vụ file trên chính tên miền của site, inline một .html là script chạy bằng phiên
đăng nhập của người xem (Frappe cũng tự ép tải về các loại này ở `/private/files`).

## 7. Màn hình

- vanchuyen `#/thu-hoi` (điều hành + tổ trưởng): danh sách thẻ, pill đếm theo chặng
  tổng, tìm khách/điểm/số phiếu/mã vận đơn; `#/thu-hoi/new` · `#/thu-hoi/:id`: khách →
  chọn điểm (lọc theo Dynamic Link của khách, kèm mã điểm `MT Store` nếu có; chọn xong
  danh sách thu lại, "Đổi điểm" để mở lại), ngày yêu cầu, số phiếu siêu thị, liên hệ, lý
  do, ô dán chi tiết hàng từ mail, điều phối thu hồi (đơn vị / mã vận đơn / ngày thu /
  số kiện), đính kèm nhiều file, nút chuyển chặng + lùi chặng, **Hủy yêu cầu** (lý do
  bắt buộc, có gợi ý một chạm) / **Khôi phục**.
- ketoan tab **Thu hồi** `#/thu-hoi`: theo dõi MỌI lô (pill 7 chặng + Đã hủy), `#/thu-hoi/:id`:
  hồ sơ lô (đơn vị thu hồi, chi tiết hàng dán từ mail, đính kèm) + phiếu kiểm + so
  sánh đã kiểm / đã lập hóa đơn (cột "khai" chỉ với lô cũ có bảng hàng khai) + hóa đơn
  trả về.
- ketoan `#/kiem-hang/:id` (mobile, dựng theo màn Ghi hộp của sx): quét mã vạch
  (BarcodeDetector / zxing1d / máy quét cầm tay / gõ tay) hoặc tìm mã → bàn số phím to
  có tab Thùng/Hộp → lưu ngay; chạm số để sửa, ✕ để xóa; **Chốt phiếu** thì khóa,
  **Mở lại** thì sửa tiếp.

## 8. Ngoài phạm vi

- Phiếu nhập kho hàng trả về (Stock Entry) — thủ kho vẫn lập riêng sau khi lọc.
- Đọc phiếu xuất trả / mail bằng AI (như Nhập đơn) — dán nguyên văn + đính kèm là đủ
  cho bản đầu.
- Tra hành trình vận đơn tự động với Viettel Post / Nhất Tín — mới lưu mã vận đơn.
- Tự đưa hóa đơn trả về vào sổ `MT Hang Hoan` (chứng từ thuế) — kế toán MT nhận từ
  màn Hàng hoàn như dòng lập tay.
