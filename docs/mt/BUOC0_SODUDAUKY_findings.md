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

Hai lỗi này **không bù nhau**. Cách xử đã chốt ở **§7**: chỉ nhập hóa đơn **còn
nợ** + một **ngày chuyển giao**, phần trước ngày đó không có trong danh sách thì
mặc định đã tất toán.

---

## 2. Số đo được — nợ GỘP (chưa trừ ghi giảm, xem §6)

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
Đây là nợ **gộp**; số thật sự mang sang là **4.875.127.168đ** — xem §6.

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

## 5. Sheet phụ

| File | Sheet phụ | Xử lý |
|---|---|---|
| Central Retail | `hd ghi giam` (310 dòng dữ liệu) | **đọc** — xem §6 |
| WinCommerce | `hd ghi giam` (1.033 dòng) · `Sheet1` | **đọc** — xem §6 |
| Saigon Co.op | `HOA DON TRA LAI` (701 dòng) · `Sheet1` | **đọc** — xem §6 |
| AEON, Mega | `Sheet1` | rỗng, bỏ qua kèm cảnh báo |

`Sheet1` rỗng thì bỏ qua nhưng vẫn **đếm và báo ra**, không im lặng.

---

## 6. Sheet ghi giảm — loại dữ liệu THỨ HAI

Kế toán mô tả: *"theo dõi các hóa đơn xuất trả, hóa đơn dịch vụ siêu thị xuất cho
mình"*. Cả hai đều **làm giảm** số phải thu. Bỏ qua là nhập **thừa** công nợ.

Ba file có sheet này, và **chính file tự in ra số nợ ròng** — phép đối chiếu mạnh
nhất có được, vì parser không được tự nghĩ ra số mà phải ra đúng số kế toán đã
tính tay:

| Chuỗi | Sheet chính | − ghi giảm | **Nợ ròng** | File tự in |
|---|---:|---:|---:|---|
| Central Retail | 1.632.866.040 | 952.935 | **1.631.913.105** | ✅ |
| Saigon Co.op | 1.112.097.060 | 132.250.823 | **979.846.237** | ✅ |
| WinCommerce | 1.329.879.654 | 50.764.968 | **1.279.114.686** | ✅ |

⇒ **Tổng nợ ròng đầu kỳ = 4.875.127.168đ**, không phải 5.059.095.894đ.
Chênh **183.968.726đ**.

**Central Retail không đặt nhãn** cho hai cột `đã cấn trừ` / `còn lại` — header
chỉ tới `TỔNG`. Không đếm cột mù, mà **đề xuất rồi chứng minh**: thử mọi cặp cột
sau `TỔNG`, giữ cặp thỏa `TỔNG − đã cấn trừ = còn lại` trên ≥90% dòng dữ liệu.
Soát trên **dòng dữ liệu** chứ không trên dòng tổng — dòng tổng của sheet ghi
giảm WinCommerce tự nó cũng hỏng (in 10.042.710.309 trong khi các dòng cộng ra
15.998.326.629; **dải SUM hụt thứ ba** trong bộ file này).

---

## 7. Mô hình nhập — ghi nhận cái CHƯA trả, mặc định phần còn lại đã trả

Kế toán chốt hướng: thay vì nhập cả 9.497 dòng để ghi từng hóa đơn đã trả bao
nhiêu, chỉ nhập **hóa đơn còn nợ** + một **ngày chuyển giao**; hóa đơn trước ngày
đó mà không có trong danh sách thì **mặc định đã tất toán**.

| | Nhập cả 9.497 dòng | **Chỉ nhập 1.167 dòng còn nợ** |
|---|---|---|
| Phải tin cột | `Số đã trả` **và** `Số còn nợ` | chỉ `Số còn nợ` |
| Dòng phải soi tay | 9.497 | **1.167** |
| Hóa đơn sót khỏi Excel | thành "còn nợ" | thành "đã trả" |

Cột `Số còn nợ` là cột đã khớp **từng đồng** ở cả bảy file, nên tin nó là hợp lý.

⚠ **Chiều rủi ro bị lật.** Hóa đơn sót khỏi Excel giờ âm thầm thành *đã trả* thay
vì âm thầm thành *còn nợ*. Chốt chặn: khi nhập phải **đếm và hiện ra** có bao
nhiêu hóa đơn trong ERPNext bị tự động tất toán và tổng bao nhiêu tiền. Con số đó
bất thường thì nhìn là biết.

---

## 8. Còn phải chốt

1. **Ngày chuyển giao.** Kế toán nhập tay, không đọc từ file — các mốc ghi trong
   file rời rạc và mâu thuẫn (`CÔNG NỢ KHỚP 30/06/2026` ở Emart nhưng cột tổng ra
   số khác; `KHỚP CÔNG NỢ TẠI NGÀY 19/1…` ở Mega).

2. **Chỉ nhập MỘT LẦN.** File này chỉ đưa lên một lần để chuyển giao. ⇒ Chuỗi đã
   nhập rồi thì **chặn nhập lại**, trừ khi xóa bản cũ — nhập hai lần là cộng đôi
   gần 5 tỷ.

3. **Nối với hóa đơn trong ERPNext.** Số hóa đơn trong Excel chuẩn hóa được,
   nhưng **chưa đo** tỷ lệ khớp vì cần database thật.

4. **Không sinh bút toán.** Số dư đầu kỳ là bản ghi nhận để màn hình công nợ
   đúng, không phải chứng từ kế toán. Bút toán số dư đầu kỳ trên sổ cái là việc
   riêng của kế toán tổng hợp, làm một lần trên ERPNext.
