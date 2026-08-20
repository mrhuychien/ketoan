# BƯỚC 0 — kết quả đọc trước, trước khi design MT-2

Ngày 20/08/2026. Kết luận của bước "đọc trước, không làm lại cái đã có".

## Nguồn đã đọc

| # | Nguồn | Tình trạng |
|---|---|---|
| 1 | `docs/blueprint/00_blueprint_p0.md` | ✅ |
| 2 | `docs/mt/mt_payment_advice_contract.md` | ✅ §A–§J |
| 3 | `docs/mt/verified/*.py` + `profiles.json` | ✅ 5 parser đã chạy thật |
| 4 | `ketoan/mt/doctype/`, `ketoan/api/mt_advice.py`, `ketoan/api/mt.py` | ✅ |
| 5 | `ketoan/misa_integration/` | ✅ |
| 6 | `docs/mt/SOP_ke_toan_MT_RVHG.md` | ✅ (thiếu lúc đầu, đã bổ sung) |
| 7 | `docs/mt/samples/` | ✅ 17 file |

## Quyết định chốt ở bước này

1. **Custom field**: giữ `create_custom_fields` + patch, KHÔNG đổi sang fixtures.
   Brief ghi "qua fixtures" nhưng repo đã đi đường patch nhất quán qua 12 patch
   (13 field MISA, `custom_mt_chain`). Đổi giữa chừng là rước rủi ro trùng định
   nghĩa field mà không được gì.
2. **File mẫu commit vào repo**. Đã mất một lần khi container khởi động lại,
   kéo theo mất khả năng chứng minh parser còn đúng.

## Sai lệch giữa brief và thực tế — phải xử trước khi design

### S1. Mega không có file thanh toán

MT2-A ghi "parser thanh toán 3 chuỗi mới: AEON, Fuji, **Mega**". Nhưng mẫu Mega
là `Chi tiết doanh số Mega Market.xlsx` — doanh số, KHÔNG phải chi tiết thanh
toán. Chính Phụ lục A3 cũng ghi Mega = "Nguồn tính CK cho MT Discount Notice".
Trong 17 file không có file thanh toán Mega nào.

⇒ **MT2-A = AEON + Fuji.** Mega chuyển sang MT2-B (chiều chiết khấu).

### S2. Việc brief coi là chưa quyết thì đã ship từ MT-1

Brief: "Chốt giải pháp đọc `.xls` ngay đầu MT2-A … quyết định trong design,
không né." Đã quyết và đã chạy: `xlrd>=2.0.1` khai trong `pyproject.toml`,
`mt_advice._sheets_xls()` đọc BIFF, LOTTE và Emart đang chạy trên đường này.
Không cần quyết lại.

### S3. Ba skill brief nhắc đều không có trên môi trường

`frappe-portal-spa`, `frappe-sales-analytics`, `frappe-app-shipping-gotchas` —
hook đầu phiên báo không pull được kho `mrhuychien/claude-skills.git`. Chỉ có bộ
`nextcode-*`. Convention lấy từ chính repo thay thế.

## Đã xác minh trên file thật (không đọc từ brief)

### AEON — `chi tiet thanh to\xa0n AEON.xls`

- **Tên file chứa non-breaking space** (`to\xa0n`). Nhận diện chuỗi theo tên
  file sẽ trượt — phải chuẩn hóa `\xa0` → space trước khi so.
- 6 sheet, tên sheet mang `PAYMENT NO` và credit term:
  `Summary(00_265294)` · `Doc(00E30_265294)` · `Costsumm(...)` · `Rebsumm(...)` ·
  `Costdet(...)` · `DcCharges(...)`.
- **Khối header r0–r10 lặp lại ở MỌI sheet** (SUPPLIER `0000003114`,
  PAYMENT DATE `17/08/2026`, PAYMENT NO `265294`, CREDIT TERM `E30`).
- `Doc`: header r12, dữ liệu từ r13. Cột: SLIP TYPE (`311`) · CONTRACT NO
  (`OS-001`) · SLIP NO · SUPPLIER INVOICE / CN NO (`1-C26THG-00004246`) ·
  STORE CODE · DELIVERY / RETURN DATE · AMOUNT · DEPT CODE · DEPT DESCRIPTION ·
  REMARKS.
- `Costdet`: header r12. TAX INVOICE = hóa đơn AEON xuất cho mình
  (`1-K26TBE-0031915`, `1-K26TDG-0007092`) → nguồn JE phí.
- `DcCharges`: **bảng ĐÔI** — hai khối cột song song (0–5 và 7–12), cùng khuôn
  STORE · SLIP NO · DELIVERY DATE · RATE (3.5) · COST AMOUNT · CHARGES.
- `Summary`: `NET PAYMENT` = **48.913.623** → chốt đối chiếu.

### Fuji — `CHI TIẾT THANH TOÁN FUJI.Xls`

- Đuôi file **`.Xls` viết hoa** — nhận định dạng phải theo byte đầu, không theo đuôi.
- 1 sheet `Mẫu in tài liệu kinh doanh` (xuất từ Bravo).
- Phần 1: header 2 tầng r13–r14, dữ liệu từ r15. STT · THEO HĐTC (NGÀY/THÁNG +
  SỐ HĐTC) · THEO PHIẾU NK/XK (NGÀY/THÁNG + SỐ PNK 18 số).
- **Số hóa đơn có khoảng trắng thừa ở đuôi** (`'4409                     '`)
  → bắt buộc `.strip()`.
- Phần 2: header r26, bảng tổng theo hóa đơn (STT · NGÀY HÓA ĐƠN · SỐ HÓA ĐƠN ·
  SỐ TIỀN) → đối chiếu chéo với phần 1.

### Mega — `Chi tiết doanh số Mega Market.xlsx`

- 1 sheet phẳng, header r1, dữ liệu r2+. Store `590072` · Supplier Number
  `27063` · Invoice No & PO `1C26THG_00004450` (tách bằng `_`) · Base Amount ·
  Good Receiving Date · Cut off date.

### Năm chuỗi cũ — file mẫu khớp bản đã dùng ở MT-1

Kích thước trùng khít từng file với bộ mẫu gốc. Chạy lại
`docs/mt/verified/regression_check.py`: **cả 5 chuỗi ra đúng từng đồng**
(WinCommerce 36 dòng · Central Retail 184 · LOTTE 45 / 2 kỳ · Emart 26 ·
Co.op 443 / 8 kỳ).

## Bộ kiểm chứng hồi quy nay nằm TRONG repo

`docs/mt/verified/regression_check.py` — chạy không cần bench (stub `frappe` vừa
đủ để nạp tầng đọc file). Trước đây bộ này nằm ở scratchpad và đã mất một lần
khi container khởi động lại.

    python3 docs/mt/verified/regression_check.py

Mọi thay đổi tầng đọc file phải chạy lại cái này trước khi commit.
