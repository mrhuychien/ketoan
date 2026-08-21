# BƯỚC 0 — Số dư đầu kỳ, đọc bảy file Excel thật trước khi code

> Đo ngày 21/08/2026 trên chính bảy file kế toán đang dùng
> (`docs/mt/samples/congno/`). Mọi con số dưới đây lấy từ file, không phải ước lượng.

---

## 1. Vì sao phải có bước này

Kênh MT suy *"còn nợ"* = `grand_total` của Sales Invoice **trừ** tiền đã trả cộng
từ dòng bảng kê. Với dữ liệu lịch sử, **cả hai vế đều thiếu**, và thiếu theo hai
chiều ngược nhau:

| | Hệ quả |
|---|---|
| Hóa đơn **đã có** trong ERPNext, đã trả xong trước khi có phần mềm — không bảng kê nào ghi lại | công nợ **bị thổi phồng** |
| Hóa đơn **chưa có** trong ERPNext (cũ hơn go-live) mà vẫn treo tiền | công nợ **bị hụt** |

Hai lỗi này **không bù nhau**. File Excel đã có sẵn cả `Số đã trả` lẫn `Số còn nợ`
cho từng hóa đơn — nhập đúng hai cột đó là xử được cả hai chiều.

---

## 2. Số đo được — đây là số dư sẽ mang sang

| Chuỗi | Dòng | Còn nợ | **Số dư đầu kỳ** | Đã trả trong lịch sử |
|---|---:|---:|---:|---:|
| AEON | 593 | 51 | 175.843.980 | 7.064.304.354 |
| Central Retail | 1.949 | 367 | 1.632.866.040 | 8.911.260.544 |
| Emart | 900 | 9 | 93.600.360 | 5.935.820.484 |
| LOTTE | 1.001 | 99 | 620.227.800 | 8.289.122.674 |
| Mega Market | 379 | 7 | 94.581.000 | 13.846.314.324 |
| Saigon Co.op | 2.479 | 355 | 1.112.097.060 | 23.963.893.827 |
| WinCommerce | 2.196 | 279 | 1.329.879.654 | 40.368.292.872 |
| **TỔNG** | **9.497** | **1.167** | **5.059.095.894** | **108.379.009.079** |

Cả bảy khớp **từng đồng** với dòng `TỔNG CỘNG` mà chính file in ra.

---

## 3. Bố cục — bảy file, bảy kiểu

Khối tiền giống nhau ở cả bảy, nằm trên **dòng header phụ**:

```
Dịch vụ | VAT x% | TỔNG | Số đã trả | [HTL] | Số còn nợ
```

Ngoài ra thì khác hết:

| Chuỗi | Header phụ | Cột số hóa đơn | VAT | Riêng |
|---|---|---|---|---|
| AEON | r7 | `SỐ HĐ` | 8% | khối chiết khấu QC/THẺ/IN ẤN/HTĐH |
| Central Retail | r6 | **`HĐ xóa bỏ`** | 8% | hai cột ngày TT theo hai mã EB |
| Emart | r6 | `SỐ HĐ` | **10%** | `HTL` |
| LOTTE | r6 | `SỐ HĐ` | 8% | cột đầu là `Địa điểm`, có `SỐ DƯ ĐẦU KỲ:` |
| Mega Market | r5 | `SỐ HĐ` | **10%** | khối `Hỗ trợ tiếp thị/thêm/trưng bày` |
| Saigon Co.op | r6 | `SỐ HĐ` | 8% | lặp nguyên dòng header chính |
| WinCommerce | r5 | **`HĐ SD/xóa bỏ`** | 8% | thêm `Ngày gửi chứng từ thanh toán` |

⇒ Dò theo **nhãn**, không hardcode chỉ số cột. Central Retail và WinCommerce để
số hóa đơn dưới nhãn `HĐ xóa bỏ` / `HĐ SD/xóa bỏ` — nhãn khó hiểu nhưng đó **là**
cột số hóa đơn đang dùng.

---

## 4. Bốn cái bẫy, đều đo được

### 4.1 Tiêu đề trong file nói dối

`CÔNG NỢ BIGC 2026.xlsx` ghi ô A2 là **`CÔNG NỢ VINCOM`** — trùng hệt file
WinCommerce (chép file rồi sửa thiếu). Nhận diện bằng tiêu đề là nhập nhầm cả
**1,63 tỷ** công nợ Central Retail sang WinCommerce.

⇒ Nhận bằng **chữ ký cột**. Không chắc → để người chọn.

### 4.2 Dòng TỔNG CỘNG của chính file có thể sai

Ô tổng VAT của Saigon Co.op mang công thức **`=SUM(F9:F340)`** trong khi bốn cột
kia cộng tới dòng 3755 — nó chỉ cộng **332 trên 2.477 dòng**, thiếu
**1.429.358.702đ**. Từng dòng thì `Dịch vụ + VAT = TỔNG` đúng cả 2.477 dòng.

AEON cũng vậy ở cột `Hàng trả lại`: dòng tổng ghi `0`, các dòng cộng ra
**121.819.086đ**.

⇒ Soát **từng cột riêng**, nêu **đích danh** cột lệch. Cột VAT/hàng trả lại lệch
**không chặn** việc nhập số dư — thứ quyết định số dư là `TỔNG`, `Số đã trả`,
`Số còn nợ`, và cả ba khớp. Nhưng lệch ở **ba cột đó** thì **dừng**.

*Đây chính là lý do bỏ Excel: file đã sai mà không ai biết, vì không có gì soát nó.*

### 4.3 Có dòng nợ âm

AEON có **2 dòng** `Số còn nợ` âm (tổng **−736.020đ**) — hàng trả lại / trả thừa.

| cách cộng | ra | |
|---|---:|---|
| theo dấu | 175.843.980 | ✅ đúng số file in |
| lọc `> 0` rồi cộng | 176.580.000 | ❌ thừa 736.020 |

⇒ Cộng **theo dấu**.

### 4.4 Sheet khai rộng bất thường

Emart khai **16.375 cột** trong khi cột có dữ liệu xa nhất là **17** (đo: 0 ô có
dữ liệu ngoài cột 200). Chốt chống OOM của `read_sheets` từ chối cả file.

⇒ Thêm `allow_wide=True`: **cắt** cột thay vì từ chối. An toàn vì OOM đến từ việc
*vật chất hóa* ô — đọc với `max_col` đã cắt thì bộ nhớ bị chặn bởi
(số dòng × trần cột) bất kể sheet khai bao nhiêu. Trần **dòng** giữ nguyên, và
đường nạp bảng kê thanh toán **không đổi hành vi** (mặc định vẫn từ chối).

---

## 5. Sheet phụ — bỏ qua nhưng phải nói ra

| File | Sheet phụ |
|---|---|
| Central Retail | `hd ghi giam` (451 dòng) |
| WinCommerce | `hd ghi giam` (1.038 dòng) · `Sheet1` |
| Saigon Co.op | `HOA DON TRA LAI` (879 dòng) · `Sheet1` |
| AEON, Mega | `Sheet1` |

Các sheet này **không** có khối `Dịch vụ/TỔNG/Số đã trả/Số còn nợ` nên không lọt
vào bảng công nợ. Chúng vẫn được **đếm và báo ra** — hóa đơn ghi giảm và hóa đơn
trả lại là tiền thật, chỉ là chưa thuộc phạm vi số dư đầu kỳ.

---

## 6. Còn phải chốt

1. **Ngày chốt số dư.** File có ghi vài mốc rời rạc và không thống nhất
   (`CÔNG NỢ KHỚP 30/06/2026` ở Emart nhưng cột tổng ra số khác;
   `KHỚP CÔNG NỢ TẠI NGÀY 19/1…` ở Mega). ⇒ Kế toán **nhập tay** ngày chốt cho
   mỗi lần nhập, không đọc từ file.

2. **Nối với hóa đơn trong ERPNext.** Số hóa đơn trong Excel là số MISA đã chuẩn
   hóa được, nhưng **chưa đo** tỷ lệ khớp vì cần database thật. Dòng khớp được →
   ghi lịch sử đã trả cho đúng hóa đơn đó; dòng không khớp → nợ đầu kỳ độc lập.

3. **Có sinh bút toán không.** Đề xuất: **không**. Số dư đầu kỳ là bản ghi nhận
   để màn hình công nợ đúng, không phải chứng từ kế toán. Bút toán số dư đầu kỳ
   trên sổ cái là việc riêng của kế toán tổng hợp, làm một lần trên ERPNext.
