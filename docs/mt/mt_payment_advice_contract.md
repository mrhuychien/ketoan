# Bảng kê thanh toán chuỗi siêu thị — hợp đồng đọc file

Nguồn: 5 file THẬT do kế toán MT cung cấp (18/08/2026). Mọi tên cột dưới đây
đọc từ file thật, không suy đoán. Chưa xác minh thì ghi rõ là chưa.

## A. Năm chuỗi, năm định dạng — không cái nào giống cái nào

| Chuỗi | File mẫu | Định dạng | Dòng | Nơi để số hóa đơn |
|---|---|---|---|---|
| WinCommerce | `Payment_Advice_from_Wincommerce_*.xlsx` | .xlsx, **9 sheet** `Table 1..9` | 86 | `Số hóa đơn` = `1C26THG#1730` |
| Central Retail (EB/GO!) | `HOANG_GIANG_*_EB.xlsx` | .xlsx 1 sheet | 198 | `Reference` = `C26THG\|4675` |
| LOTTE | `Payment_deduct_detail*_LOTTE.xls` | **.xls** | 135 | `Tax No`=`1C26THG` + `Invoice No`=`3996` (2 cột) |
| Emart | `APT_*_emart.xls` | **.xls** | 71 | `Invoice no` = `4406` (**không có ký hiệu**) |
| Saigon Co.op | `HOANGGIANG26_CO.OP.xlsx` | .xlsx, **9 sheet** `Sheet1..Sheet9` | 817 | `HÓA ĐƠN NCC` = `'P0007272` + ký hiệu nằm trong `DIỄN GIẢI` |

⚠️ **Hai file là `.xls` (BIFF), không phải `.xlsx`.** `misa_import._rows()` hiện chỉ
đọc `.xlsx` qua openpyxl và `.csv` — **không đọc được `.xls`**. Phải bổ sung
`xlrd` hoặc bắt kế toán "Save As .xlsx". Đây là chốt chặn triển khai, không
phải chi tiết nhỏ.

## B. Ba quy ước DẤU khác nhau — cấm phân loại dòng bằng dấu

| Chuỗi | Hàng hóa | Chiết khấu / phí |
|---|---|---|
| Central Retail, Emart | **âm** | **dương** |
| LOTTE | **dương** | **âm** |
| WinCommerce, Co.op | dương | dương (cột riêng) |

⇒ Phân loại dòng phải dựa vào **cột loại chứng từ** của từng chuỗi, tuyệt đối
không dựa vào dấu. Lấy dấu làm căn cứ là ghi nhận ngược chiều tiền.

## C. Cột phân loại dòng của từng chuỗi

| Chuỗi | Cột | Giá trị thật quan sát được |
|---|---|---|
| Central Retail | `Doc.Type` | `K1` = hàng hóa · `D1` = phí (Reference `K26TEB\|...`) |
| Emart | `Document Type` | `RE` = hàng hóa · `I0` = chiết khấu · `I1` = phí hỗ trợ |
| LOTTE | `Deduct Name` | rỗng = hàng hóa · `Sale services fee - Auto` · `Other services fee - Auto` · `Basic discount - Auto` |
| WinCommerce | — | sheet `Table 5` = thanh toán · `Table 7` = sau tiêu đề "Chiết khấu" |
| Co.op | cột `CHIẾT KHẤU` riêng | mỗi dòng vừa có `TRỊ GIÁ` vừa có chiết khấu |

## D. Dòng RÁC phải bỏ

| Chuỗi | Dòng phải bỏ |
|---|---|
| Central Retail | `Overall Result` (r2), dòng `Terms of Pmnt = 'Result'` (r3) |
| LOTTE | `Deduct Cause = 'SUB SUM'` |
| Emart | `Document Number` = `chiết khấu` / `phí hỗ trợ` (dòng cộng) |
| WinCommerce | dòng `**********` xen giữa |
| Co.op | 17 dòng tiêu đề đầu; header **2 tầng** ở r18–r19 |

## E. Ký hiệu hóa đơn KHÔNG nhất quán ngay trong một file

File Central Retail có cả `C26THG|4675` và `1C26THG|4674`. LOTTE có cả
`1C26THG` và `C26THG`. Cùng một dải hóa đơn.

⇒ Khớp ký hiệu phải **bỏ qua chữ số dạng hóa đơn ở đầu**: `C26THG` và
`1C26THG` là MỘT. Cùng bài học với `OrgInvSeries` ở §R.7 của hợp đồng MISA.

## F. Số hóa đơn — quy tắc tách theo từng chuỗi

| Chuỗi | Giá trị thô | Ký hiệu | Số |
|---|---|---|---|
| WinCommerce | `1C26THG#1730` | `1C26THG` | `1730` |
| Central Retail | `C26THG\|4675` | `C26THG` | `4675` |
| LOTTE | 2 cột | `Tax No` | `Invoice No` |
| Emart | `4406` | **không có** → lấy từ hồ sơ chuỗi | `4406` |
| Co.op | `'P0007272` + `1C25THG\|BANH…` | từ `DIỄN GIẢI` | `7272` (bỏ `'`, bỏ chữ đầu, bỏ số 0 thừa) |

Emart không cấp ký hiệu ⇒ khớp bằng **số + ngày + tiền**, và luôn đánh dấu
"cần review". Đoán ký hiệu cho Emart là gán nhầm hóa đơn.

## G. Bẫy riêng của Co.op — tiền thanh toán là của CẢ NHÓM

Cột `THANH TOÁN / TIỀN` chỉ điền ở **dòng đầu mỗi siêu thị thành viên**, là
tổng của cả nhóm, KHÔNG phải tiền của riêng dòng đó. Cộng cột này theo từng
dòng là nhân số tiền lên nhiều lần.

Header file còn có 3 số kiểm tra ở r13–r15: `Tổng Tiền`, `Tổng Giá Trị Chiết
Khấu`, `Tổng Tiền Thanh Toán` — dùng làm **chốt đối chiếu** sau khi đọc.

## H. Một file có thể chứa NHIỀU ngày thanh toán

LOTTE: cùng file có `Payment Date` = `20260710` và `20260730`. Không được coi
cả file là một lần thanh toán.

## I. Chưa xác minh

- Ý nghĩa `Terms of Pmnt` (`A040`) của Central Retail.
- `Số đối soát` (`2000141337`) của WinCommerce — giống nhau ở mọi dòng.
- Co.op: `SỐ HÓA ĐƠN LH` (`197-SIPI-122025-1090629`) là chứng từ bên Co.op.
- Ánh xạ mã nhà cung cấp → Customer của ERPNext cho từng chuỗi.


---

## J. ✅ ĐÃ XÁC MINH — chạy parser thật trên cả 5 file (18/08/2026)

Mỗi chuỗi được một agent riêng viết parser, **chạy thật**, rồi đối chiếu với số
kiểm tra có sẵn trong file. Bản parser tham chiếu lưu ở `docs/mt/verified/`.

| Chuỗi | Dòng | Thanh toán | Chiết khấu | Phí | Ghi giảm | Đối chiếu số kiểm tra |
|---|---|---|---|---|---|---|
| WinCommerce | 85 | 245.795.904 | 0 | — | — | ✅ khớp **3** chốt độc lập, lệch 0đ |
| Central Retail | 197 | 721.996.632 | 27.240.347 | 134.708.790 | 5.119.605 | ✅ khớp `Overall Result` −554.927.890 |
| LOTTE | 134 | 276.933.600 | −31.460.649 | −14.943.812 | −809.335 | ✅ |
| Emart | 48 | −191.554.740 | 5.266.245 | 27.388.670 | — | ✅ |
| Saigon Co.op | 577 | 8.451.787.806 | — | — | −913.698.214 | ✅ khớp `kiem_tra` 7.538.089.592 |

### J.1 🚨 HAI LẦN ĐỌC ĐẦU CỦA TÔI ĐỀU SAI — cả hai đều do `head` cắt mất

**WinCommerce có 9 sheet, không phải 7.** Và `Table 6` **KHÔNG** phải tiêu đề mục
"Chiết khấu" — nó là **chân trang bản in**: `Chiết khấu | Số tiền / Số dư mang
sang trang sau | 0 | 70.880.508`. Hai chữ "Chiết khấu" ở đó là nhãn **cột**,
không phải nhãn **mục**. Bằng chứng số học: 70.880.508 = đúng tổng `Table 5`.

⇒ `Table 7` và `Table 8` là **phần tiếp theo của cùng bảng thanh toán**. Nếu tin
cách đọc ban đầu:
- 134.593.596đ bị ghi nhận **sai loại** (thành chiết khấu),
- 40.321.800đ của `Table 8` bị **bỏ quên hoàn toàn**,
- tổng chỉ còn 70.880.508 thay vì 245.795.904 — **mất 71% số tiền**.

**Saigon Co.op có 9 sheet, không phải 1** (`Sheet1..Sheet9`, 817 dòng). Chỉ đọc
`Sheet1` là bỏ sót 7/8 kỳ thanh toán.

⇒ Bài học: file là **PDF convert sang Excel**, mỗi **trang in** thành một sheet.
Bảng dữ liệu bị cắt rời giữa các sheet. **Bắt buộc quét MỌI sheet và dò header
theo nhãn**, cấm hardcode tên sheet hay chỉ số cột.

### J.2 Lệch cột giữa các sheet của cùng một file

`Table 7` của WinCommerce có **thêm một cột A rỗng** (merged `A1:A42`) nên mọi
cột dịch phải 1 ô so với `Table 5`/`Table 8`. Hardcode chỉ số cột là đọc lệch
cột tiền của 21/36 dòng.

### J.3 Một file = NHIỀU kỳ thanh toán

| Chuỗi | Số kỳ trong file mẫu | Các ngày |
|---|---|---|
| Saigon Co.op | **8** | 20/01 · 23/02 · 24/03 · 23/04 · 25/05 · 22/06 · 07/07 · 22/07 |
| LOTTE | **2** | 10/07 · 30/07 |
| WinCommerce, Central Retail | 1 | |

⇒ Một file Co.op phải sinh ra **8 bản ghi `MT Payment Advice`**, không phải 1.
Gộp cả file làm một lần thanh toán là sai kỳ công nợ.

### J.4 Số kiểm tra rất dễ bị cộng nhầm thành tiền

WinCommerce có `Số dư mang sang trang sau 70.880.508` và `Tổng cộng 245.795.904`
nằm ngay trong vùng dữ liệu. Cộng cả hai vào là ra **561.472.316đ** thay vì
245.795.904đ. Phải nhận diện, **loại khỏi tổng**, rồi **dùng làm chốt đối chiếu**.

Số tổng còn có thể nằm **trong chuỗi**: `Table 9` ghi `******245.795.904*`. Ép
`float()` thẳng là `ValueError`; và dấu `.` ở đây là phân cách **nghìn** kiểu VN,
đọc nhầm thành thập phân là **sai 1000 lần**.
