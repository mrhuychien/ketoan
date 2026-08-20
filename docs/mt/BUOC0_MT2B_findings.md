# BƯỚC 0 — MT2-B (chiều chiết khấu), đọc file thật trước khi code

Ngày 20/08/2026. Cùng kỷ luật đã dùng ở MT2-A: **không đoán tên cột, không đoán
cách tính**. Mọi con số dưới đây đo trên file trong `docs/mt/samples/`.

---

## 1. Ba file cơ sở tính chiết khấu — ba hình dạng khác hẳn nhau

| Chuỗi | File | Sheet | Dòng × cột | Khóa hóa đơn | CK nằm ở đâu |
|---|---|---|---|---|---|
| Central Retail | `Chi tiết doanh số BigC.xlsx` | `Data` | 1.770 × 17 | `INVOICENO` = `C26THG\|6320` | **có sẵn** cột `RB_VALUE` |
| LOTTE | `7466- chi tiết doanh số Lotte.xlsx` | `Sheet1` | 227 × 17 | `Invoice No` = `00000984` | **KHÔNG có** — tỷ lệ từ hợp đồng |
| Mega Market | `Chi tiết doanh số Mega Market.xlsx` | `Sheet1` | 6 × 7 | `Invoice No & PO.` = `1C26THG_00004450` | **KHÔNG có** — chỉ có `Base Amount` |

Emart: `Chi tiết doanh số Emart.PDF` — **PDF, không đọc bằng máy được**. Rebate
3% (§2.5 SOP) phải nhập tay cho tới khi Emart gửi bản Excel.

---

## 2. HAI cách tính chiết khấu, và chúng KHÁC NHAU THẬT

Đây là phát hiện quan trọng nhất của bước này. Đo trên chính hai mẫu BKCK:

### Central Retail — **cộng từng dòng**, KHÔNG phải tỷ lệ × tổng

Mẫu `Bảng kê chi tiết hóa đơn chiết khấu BigC…xlsx` (BKCK 261, kỳ 06.2026):

```
Tổng Cộng:                 715.000.265
Số tiền chiết khấu 3.35%:   23.952.537
715.000.265 × 3,35%      =  23.952.508,88     ← LỆCH 28,12đ
```

Trên file doanh số 07.2026 cũng vậy: `Σ RB_VALUE` = 25.324.144 trong khi
`Σ IM_VALUE × 3,35%` = 25.324.111,44 — **lệch 32,56đ**. BigC làm tròn **từng
dòng**, nên bảng kê phải cộng dòng, không được tính lại từ tổng.

### LOTTE — **tỷ lệ × tổng**, khớp tuyệt đối

Sáu kỳ trong `Mẫu bảng kê hóa đơn chiết khấu Lotte Mart.xlsx`, lệch 0đ cả sáu:

| Kỳ | BKCK | Tổng Cộng | Số tiền cần chiết khấu | × 10% |
|---|---|---|---|---|
| 11.2025 | 155 | 85.843.000 | 8.584.300 | ✓ |
| 12.2025 | 172 | 226.512.000 | 22.651.200 | ✓ |
| 03.2026 | 229 | 17.772.000 | 1.777.200 | ✓ |
| 04.2026 | 243 | 104.690.000 | 10.469.000 | ✓ |
| 05.2026 | 260 | 46.650.000 | 4.665.000 | ✓ |
| 06.2026 | 280 | 45.040.000 | 4.504.000 | ✓ |
| 07.2026 | 300 | 55.460.000 | 5.546.000 | ✓ |

*(03.2026 = 1.777.200 và 07.2026 = 5.546.000 khớp đúng hai con số §2.3 SOP nêu
làm mẫu đã kiểm chứng.)*

⇒ **`mode` phải là thuộc tính của cấu hình từng chuỗi, không phải hằng số trong
code.** Áp nhầm cách là sai tiền — ít thì vài chục đồng, nhưng nó là **sai
nguyên tắc**: một bên là số CHUỖI đã chốt, một bên là số mình tự tính lại.

---

## 3. Bẫy — mỗi cái đều làm sai tiền

1. **Central Retail: chỉ nhóm `Discount for store`.** Bốn nhóm trong file:

   | RB_GROUP | Dòng | RB_VALUE | Ai xuất hóa đơn |
   |---|---|---|---|
   | `Discount for store` | 177 | 25.324.144 | **MÌNH** → BKCK |
   | `Fee for EBS` | 177 | 7.559.436 | EB xuất |
   | `Fee for store` | 531 | 62.365.380 | EB xuất |
   | `Support for store` | 885 | 29.859.815 | EB xuất |

   Lấy nhầm là **xuất hóa đơn cho khoản mình không được xuất** — và ba nhóm kia
   đã được xử ở MT2-D dưới dạng dòng `D1` trong file thanh toán, nên lấy cả là
   ghi nhận hai lần.

2. **Central Retail: `IM_VALUE` LẶP LẠI ở mọi nhóm.** Cùng 755.943.625 xuất
   hiện ở `Discount for store` và `Fee for EBS`; `Fee for store` ra
   2.267.830.875 = **3×** vì có 3 tỷ lệ. Cộng `IM_VALUE` toàn file là nhân
   doanh số lên **6 lần**.

3. **LOTTE: `Fill in date = NOT RECEIVE` là hàng CHƯA NHẬN.** 35/227 dòng,
   25.621.900đ. Phải loại khỏi cơ sở tính CK. Chính 35 dòng đó cũng là 35 dòng
   **không có `Invoice No`** — hai dấu hiệu trùng khớp tuyệt đối.

4. **LOTTE: `Pur fg = hàng trả lại`** — 10 dòng, −20.586.100đ, số đã ÂM sẵn.
   GIỮ LẠI, trừ thẳng vào cơ sở (§2.3 SOP).

5. **LOTTE: `Invoice No` là số hóa đơn CỦA MÌNH**, không phải của chuỗi — dạng
   `00000984`, đúng khuôn 8 chữ số như BKCK in ra (`00005913`). 26 hóa đơn phân
   biệt trên 227 dòng.

6. **Mega Market: `Invoice No & PO.` ngăn bằng `_`**, không phải `|` hay `#`:
   `1C26THG_00004450`. Ba chuỗi ba dấu phân cách khác nhau — đây là dấu thứ tư.

---

## 4. Cấu trúc BKCK (bản in) — giống nhau ở cả hai chuỗi

```
r1-r2   tiêu ngữ
r4      BẢNG KÊ HÓA ĐƠN CHIẾT KHẤU / BẢNG KÊ CHIẾT KHẤU THÁNG MM.YYYY
r5      Số: NNN/BKCK/HG-MT   ·   Ngày … tháng … năm …
r6-r9   Đơn vị BÁN: Hoàng Giang · MST 0800280839 · địa chỉ · đại diện
r10-r13 Đơn vị MUA: pháp nhân/chi nhánh · MST · địa chỉ · đại diện
r15     "Hai bên cùng nhau xác nhận chiết khấu các hóa đơn sau:"
r16     Số hóa đơn | Ký hiệu | Ngày | Thành tiền trước thuế | Tiền thuế GTGT | Tổng cộng | Ghi chú
…       một dòng / hóa đơn   (Ghi chú = số PO ở Central Retail)
        Tổng Cộng:                        (3 cột tiền)
        Số tiền [cần] chiết khấu [X%]:    (3 cột tiền)
        NGƯỜI LẬP BẢNG KÊ
```

- **Thuế của chiết khấu = 8%** (kiểm: 23.952.537 × 8% = 1.916.202,96 = đúng ô
  in ra).
- **Một dãy số DUY NHẤT cho cả công ty**, không tách theo chuỗi: quan sát
  141 · 155 · 172 · 229 · 243 · 260 · **261 (BigC)** · 280 · 300 — số 261 của
  Central Retail nằm xen giữa dãy của LOTTE.
- Central Retail gộp **1 bảng kê / pháp nhân EB**; LOTTE tách **1 bảng kê /
  chi nhánh** (bên mua = MST chi nhánh, lấy từ `MT Store.address` — đúng lý do
  MT2-C dựng master điểm siêu thị).
- Dòng tiền ÂM có thật trong BKCK (LOTTE 3.2026 có hai dòng âm: hàng trả).

---

## 5. Hồ sơ thanh toán Winmart

`Mẫu bảng kê ghi nhận hồ sơ thanh toán Winmart.xlsx` — 1 sheet, header ở **r2**:

```
STT | Code | PO VCM | Ký hiệu HĐ | Số hóa đơn | Ngày hóa đơn
    | Số Tiền trước VAT | VAT | Tổng tiền thanh toán | Tên File PDF
```

- `Code` = 2007766 (mã NCC của Hoàng Giang tại WinCommerce) ở **mọi dòng**.
- `Tên File PDF` mẫu thật: **`20260817_2007766_01_PF`** — tức
  `YYYYMMDD_<mã NCC>_<stt hồ sơ>_PF`, chứ không phải `YYYYMMDD_2007766_<stt>`
  như §2.2 SOP viết gọn. **Có hậu tố `_PF`.**
- `STT` trong file mẫu **không theo thứ tự** (3,4,5,6,9,10,1,2,7,8,11…) — nó là
  số thứ tự hồ sơ của Win, không phải thứ tự dòng. Đừng đánh lại.

---

## 6. Kết luận cho thiết kế

1. Cách tính CK (`cộng dòng` vs `tỷ lệ × tổng`) và tỷ lệ phải nằm trong **cấu
   hình theo chuỗi**, đọc từ file khi file có, chặn lại khi không có cả hai.
2. Cơ sở tính CK **đến từ file của chuỗi**, không tự dựng từ Sales Invoice: đó
   là số CHUỖI đã chốt, và chênh với hóa đơn của mình chính là thứ phải đi truy
   (§3.2 SOP).
3. Bên mua của BKCK lấy từ **`MT Store.address`** — MT2-C đã dựng sẵn.
4. Dãy số BKCK là **một dãy chung toàn công ty**.
5. Emart chưa có file máy đọc được ⇒ **không code parser Emart**, để nhập tay.
   Đúng quy tắc "chưa có mẫu thật thì chưa viết parser" đã áp cho Mega ở MT2-A.
