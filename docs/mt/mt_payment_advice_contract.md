# Bảng kê thanh toán chuỗi siêu thị — hợp đồng đọc file

Nguồn: 5 file THẬT do kế toán MT cung cấp (18/08/2026). Mọi tên cột dưới đây
đọc từ file thật, không suy đoán. Chưa xác minh thì ghi rõ là chưa.

## A. Năm chuỗi, năm định dạng — không cái nào giống cái nào

| Chuỗi | File mẫu | Định dạng | Dòng | Nơi để số hóa đơn |
|---|---|---|---|---|
| WinCommerce | `Payment_Advice_from_Wincommerce_*.xlsx` | .xlsx, **7 sheet** `Table 1..7` | 23 + 44 | `Số hóa đơn` = `1C26THG#1730` |
| Central Retail (EB/GO!) | `HOANG_GIANG_*_EB.xlsx` | .xlsx 1 sheet | 198 | `Reference` = `C26THG\|4675` |
| LOTTE | `Payment_deduct_detail*_LOTTE.xls` | **.xls** | 135 | `Tax No`=`1C26THG` + `Invoice No`=`3996` (2 cột) |
| Emart | `APT_*_emart.xls` | **.xls** | 71 | `Invoice no` = `4406` (**không có ký hiệu**) |
| Saigon Co.op | `HOANGGIANG26_CO.OP.xlsx` | .xlsx 1 sheet | 131 | `HÓA ĐƠN NCC` = `'P0007272` + ký hiệu nằm trong `DIỄN GIẢI` |

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
