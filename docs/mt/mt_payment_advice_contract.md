# Bảng kê thanh toán chuỗi siêu thị — hợp đồng đọc file

Nguồn: 5 file THẬT do kế toán MT cung cấp (18/08/2026). Mọi tên cột dưới đây
đọc từ file thật, không suy đoán. Chưa xác minh thì ghi rõ là chưa.

> **AEON và Fuji Mart bổ sung ở [PHỤ LỤC K](#phụ-lục-k--aeon-và-fuji-mart-mt-2-20082026)
> (20/08/2026).** Mục A–J bên dưới viết khi mới có 5 chuỗi; mọi nguyên tắc trong
> đó vẫn nguyên giá trị, nhưng các bảng liệt kê "5 chuỗi" nay là **7**.

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

---

# PHỤ LỤC K — AEON và Fuji Mart (MT-2, 20/08/2026)

Nguồn: 2 file THẬT trong `docs/mt/samples/`. Mọi tên cột đọc từ file thật.
Bản đọc chạy thật: `ketoan/api/mt_advice.py: parse_aeon` / `parse_fuji`.
Bản đọc tham chiếu độc lập: `docs/mt/verified/aeon.py` / `fuji.py`.
Ba bộ kiểm chạy được không cần bench:

    python3 docs/mt/verified/regression_check.py   # 7 chuỗi ra đúng từng đồng
    python3 docs/mt/verified/crosscheck_mt2.py     # 2 bản đọc độc lập trùng nhau
    python3 docs/mt/verified/mutation_check.py     # số kiểm tra CÓ bắt được lỗi tiền

## K.1 Hai định dạng mới

| Chuỗi | File mẫu | Định dạng | Nơi để số hóa đơn |
|---|---|---|---|
| AEON | `chi tiet thanh to\xa0n AEON.xls` | **.xls**, **6 sheet** | `SUPPLIER INVOICE / CN NO.` = `1-C26THG-00004246` |
| Fuji Mart | `CHI TIẾT THANH TOÁN FUJI.Xls` | **.xls**, đuôi **VIẾT HOA**, 1 sheet | `SỐ HÓA ĐƠN` = `4409` (**không có ký hiệu**) |

⚠️ Tên file AEON chứa **`\xa0` (non-breaking space) thật** — giữa `to` và `n`.
Đuôi file Fuji **viết hoa** `.Xls`. Cả hai lý do đó là vì sao nhận diện định dạng
phải theo **chữ ký file** (magic bytes `D0 CF 11 E0`), không theo đuôi tên.

## K.2 AEON — sáu sheet, chỉ HAI sheet sinh tiền

| Sheet | Vai trò |
|---|---|
| `Summary(00_265294)` | `NET PAYMENT` = 48.913.623 — nguồn kiểm tra **độc lập** |
| `Doc(00E30_265294)` | **SINH TIỀN** — hàng bán (slip 311) + hàng trả (slip 312) |
| `Costsumm` / `Rebsumm` | **DANH MỤC** mã khoản trừ, gần như toàn 0 — chỉ để soát |
| `Costdet(00E30_265294)` | **SINH TIỀN** — 25 dòng khoản trừ, 5 mã |
| `DcCharges(...)` | **CHI TIẾT** của đúng dòng mã `DC` ở Costdet — **KHÔNG sinh tiền** |

Khối header `r1–r11` **lặp y hệt ở cả 6 sheet**, nhưng `PAYMENT NO:` và
`CREDIT TERM:` **chỉ có** ở 5 sheet sau, **không có** ở `Summary`.

**Số đúng:** `+61.884.000 (21) − 2.545.560 (7) − 10.424.817 (25) = +48.913.623`.

### Bốn bẫy tiền của AEON

1. **Khối tổng nằm TRONG bảng.** Cuối `Doc` có khối tổng mở đầu bằng **đúng
   nhãn `Slip Type`**, và các dòng của nó cũng mang mã `311`/`312`. Đọc tiếp qua
   đó là **cộng đôi**: 123.768.000 thay vì 61.884.000.
2. **`DcCharges` là chi tiết, không phải khoản trừ riêng.** Tổng của nó
   (2.512.222) bằng **đúng** dòng mã `DC` của `Costdet`. Sinh tiền từ cả hai là
   cộng trùng — mà `Net Payment` **vẫn khớp**, vì Net Payment chỉ đối chiếu
   `Costdet`. Đây là bẫy **câm nhất** của file này.
3. **Hàng trả lưu DƯƠNG, in ÂM.** 7 dòng slip 312 nằm trong bảng với số dương
   nhưng `TOTAL GRN` in −2.545.560. Phân loại theo dấu là biến hàng trả thành
   **tiền thu về** trên đúng hóa đơn đó (§B).
4. **Khoản trừ có dòng ÂM thật.** Bốn mã `RBGPA/RBGPD/RBGPOS/RBPS` mỗi mã có 2
   dòng âm (−8.683; −42.228 …) xen giữa các dòng dương, `Sub-Total` là tổng
   **đại số**. `-abs(amt)` là đảo dấu 8 dòng hoàn tiền → lệch đúng **2×** tổng
   các dòng đó. Phải dùng `-amt`.

Thêm một bẫy đọc (không lệch tiền nhưng làm hỏng số kiểm tra): khối tổng có cột
`No of Slips` **đứng sau** cột `Amount`. Lấy "số cuối dòng" thì `Net Purchase`
ra **28** (số slip) thay vì 59.338.440.

`TAX INVOICE` ở `Costdet` (`1-K26TBE-…`, `1-K26TDG-…`) là **hóa đơn AEON xuất
cho mình**, không phải hóa đơn mình bán ra (`1-C26THG-…`) → vào `doc_no`, tuyệt
đối không vào `inv_no`.

**Tách số hóa đơn:** `1-C26THG-00004246` có **HAI** dấu `-`, không phải một, nên
`split_invoice_ref` (cắt tại dấu **đầu tiên**) trả sai ký hiệu `'1'`. Cụm đầu là
**số mẫu hóa đơn** → bỏ; ký hiệu `C26THG`; số `00004246`.

**16 số kiểm tra**, khớp tuyệt đối, lệch 0đ: 2 tổng theo slip · 3 tổng khối
(`Net Purchase`/`Deduction`/`Net Payment`) · 3 số lượng slip · 5 `Sub-Total`
theo mã · `Costdet Total` · `NET PAYMENT` sheet Summary · `DcCharges = dòng DC`.

## K.3 Fuji Mart — BỐN khối trong một sheet

| Khối | Dòng | Nội dung | Sinh tiền? |
|---|---|---|---|
| K1 | r14–r25 (header 2 tầng) | hóa đơn ↔ phiếu nhập kho + mã kho | **KHÔNG** |
| K2 | r27–r37 | tổng theo hóa đơn | **CÓ** — 90.010.980 |
| K3 | r40–r47 (header 2 tầng) | hàng trả, số **âm sẵn** | **CÓ** — −8.191.071 |
| K4 | r51–r65 | chiết khấu / hỗ trợ, mỗi mục **HAI dòng** | **CÓ** — −10.126.136 |

**Số đúng:** `+90.010.980 − 8.191.071 − 10.126.136 = +71.693.773`.

**File KHÔNG có ngày thanh toán và KHÔNG có số bảng kê** — 13 dòng đầu trống
trơn, đã soi hết 65×14 ô. Không bịa: trả `None` + cảnh báo để kế toán điền tay.

### Bốn bẫy tiền của Fuji

1. **Nhân đôi doanh thu.** K1 và K2 là **cùng một số tiền nhìn từ hai phía**
   (phiếu nhập kho vs hóa đơn), cùng bằng 90.010.980. Sinh tiền từ cả hai ra
   180.021.960. K1 chỉ dùng để đối chiếu chéo và lấy số PNK + mã kho.
2. **Cộng trùng dòng tên và dòng chi tiết của K4** — hai dòng in **cùng** số
   tiền. Và đẳng thức "dòng tên = dòng chi tiết" **KHÔNG bắt được**, vì cả hai
   vế cùng gấp đôi. Chốt duy nhất bắt được là **số thứ tự cuối khối** (= 7 mục).
3. **Bỏ sót K3 thì số kiểm tra khớp GIẢ.** Không đọc khối hàng trả thì
   "tổng hóa đơn − hàng trả" tụt về đúng 90.010.980 — mà đó **lại là một doanh
   số căn cứ in trong file** — nên phép kiểm vẫn tìm thấy và báo khớp. Phải đếm
   số dòng của K3 bằng **cột STT**, độc lập cột tiền.
4. **`NGÀY/THÁNG` xuất hiện HAI LẦN** ở tầng 2 của K1: `c2` dưới nhóm
   `THEO HĐTC` (ngày hóa đơn) và `c5` dưới nhóm `THEO PHIẾU NK/XK` (ngày nhập
   kho). Tra nhãn phẳng là lấy nhầm ngày — mà Fuji **không có ký hiệu** nên tầng
   khớp phải dựa vào `số + NGÀY + tiền`; ngày sai là trượt sạch.

Thêm: số hóa đơn đệm **hơn 20 dấu cách** ở đuôi (`'4409                    '`);
ô ngày là **serial Excel** (ctype 3, `46174` = 2026-06-01), `str()` ra `'46174.0'`.

**Bảy mục khối 4** (phân loại theo NHÃN — `Chiết khấu *` → chiết khấu,
`Hỗ trợ *` → phí):

| # | Tên | Căn cứ | Tỷ lệ | Tiền |
|---|---|---|---|---|
| 1 | Chiết khấu doanh số không điều kiện | 81.819.909 | 1% | 818.199 |
| 2 | Chiết khấu thanh toán | 90.010.980 | 2% | 1.800.220 |
| 3 | Hỗ trợ hợp tác chiến lược | 81.819.909 | 0,5% | 409.100 |
| 4 | Hỗ trợ thẻ khách hàng thân thiết | 81.819.909 | 2% | 1.636.398 |
| 5 | Hỗ trợ thuê mướn | 90.010.980 | 1% | 900.110 |
| 6 | Hỗ trợ trưng bày | 90.010.980 | 2,75% | 2.475.302 |
| 7 | Hỗ trợ vận chuyển qua DC SGW | **69.560.235** | 3% | 2.086.807 |

Căn cứ của mục 7 **không suy ra được** từ số nào khác trong file → dòng đó luôn
gắn cờ *cần người xem*, kèm cảnh báo nêu rõ hai đại lượng đã thử đối chiếu.

Fuji **không in tổng thanh toán ròng**, nên **8 số kiểm tra** đều là **đẳng thức
giữa hai số do chính file in ra**: K1 = K2 · số dòng K1 = K2 · khớp từng hóa đơn
K1↔K2 · dòng tên = dòng chi tiết · số mục theo STT · số dòng hàng trả · tổng hóa
đơn = căn cứ in trong file · tổng hóa đơn − hàng trả = căn cứ in trong file.

## K.4 Fuji vào nhóm "chuỗi không có ký hiệu"

`ketoan/api/mt.py: SERIESLESS_CHAINS = ("emart", "fuji")`. Đây là **hai** chuỗi
duy nhất được phép khớp bằng `số + ngày + tiền` và **luôn** để `Cần review`.
Chuỗi **ngoài** danh sách này mà bóc ký hiệu ra rỗng nghĩa là **đọc hỏng**, và
khớp bằng số trần trên chỉ mục gộp mọi chuỗi là **vơ nhầm hóa đơn của chuỗi
khác** — cả 7 chuỗi dùng chung dải ký hiệu `C26THG`.

## K.5 Mega Market — bảng phẳng tiếng Anh, KHÔNG có số kiểm tra

File mẫu thật: `docs/mt/samples/cttt_mega.xls` (`.xls` BIFF, 1 sheet `Sheet1`,
header dòng 1, **18 dòng dữ liệu**, 10 cột).

| c1 | c2 | c3 | c4 | c5 | c6 | c7 | c8 | c9 | c10 |
|---|---|---|---|---|---|---|---|---|---|
| Store no | Supplier code | Supplier name | Description | Invoice no | Amount | Invoice Date | GL date | Due date | Payment date |

`GL date` và `Due date` **rỗng toàn bộ**. `Payment date` giống nhau ở mọi dòng
(2026-07-10) — đó là ngày thanh toán. `Store no` ra từ ô số nên mang đuôi `.0`
(`590072.0`), phải cắt.

### K.5.1 Hai loại chứng từ — phân biệt bằng KÝ HIỆU, không bằng dấu tiền

```
1C26THG_00004450   <- hóa đơn BÁN RA của mình   (8 dòng, tất cả DƯƠNG)
C26TAP 3269        <- chứng từ ký hiệu khác      (10 dòng, tất cả ÂM)
```

Ký hiệu và số cách nhau bằng `_` (hóa đơn của mình, số đệm 0 tám chữ) hoặc bằng
**dấu cách** (chứng từ kia, số trần) — **cùng một file dùng cả hai**.

Dấu và loại trùng khớp **18/18 dòng**. Đó chính là cái bẫy: phân loại theo dấu
chạy đúng hôm nay và sai câm vào ngày Mega đổi quy ước, vì tổng NET không đổi
nên **không phép kiểm SUM nào bắt được**. Đúng điều cấm ở §B.

Quy tắc thật: ba ký tự cuối của ký hiệu là **mã người bán** (TT78:
`<mẫu số><C|K><2 số năm><3 ký tự>`). Của mình là `THG` — hằng số
`mt_advice.OUR_ISSUER_CODE`, đổi pháp nhân thì đổi ở đó, không rải `'THG'` vào
từng parser. Dấu chỉ dùng để **gắn cờ** `needs_review`, không bao giờ để đổi loại.

**Bằng chứng cho cách phân loại** — đối chiếu với `congno_mega_market.xlsx`:
cả **8/8** dòng ký hiệu THG khớp **đúng từng đồng** với cột TỔNG của hóa đơn
tương ứng, và cả 8 đều đã về `Số còn nợ = 0`. Không dòng `C26TAP` nào khớp được.

⚠ Số của `C26TAP` **đụng** số hóa đơn của mình: `C26TAP 3264` và hóa đơn
`00003264` (29/08/2024) cùng tồn tại. Đúng ca §MT2-G — dòng ghi giảm vẫn giữ số
để kế toán đối chiếu, nhưng không đường nào cho nó nối Sales Invoice.

### K.5.2 File này KHÔNG có số kiểm tra nào

Không dòng TỔNG CỘNG, không ô net payment, không số bảng kê. Nên `checks` để
**rỗng** và `reconciled` = **False**, và sẽ mãi như vậy. Nhét một phép kiểm cấu
trúc vào `checks` để màn hình sáng xanh là **nói dối** về thứ chưa từng được đối
chiếu — "không kiểm được" không phải là "đã kiểm và đúng".

Thứ duy nhất kiểm được là **cột**, bằng chính sự thừa của file:
`Description == "<Invoice no>,<Store no>"` đúng **18/18** dòng. Đọc lệch cột thì
đẳng thức đó vỡ, và parser cảnh báo.

### K.5.3 Bảng kê mẫu CẤN TRỪ HẾT

313.983.000đ hóa đơn bán ra trừ **đúng bằng** 313.983.000đ chứng từ ghi giảm →
**tiền thực nhận bằng 0**. Không phải lỗi đọc file, và parser nói thẳng ra —
kế toán chờ tiền vào tài khoản mà không thấy sẽ đi tìm nhầm chỗ.

### K.5.4 Hạn chế còn lại

File **không có cột phân loại** khoản trừ, nên 10 dòng ghi giảm không tách được
đâu là chiết khấu, đâu là phí, đâu là hàng trả lại. Tất cả vào một nhóm
`Ghi giảm` và hạch toán vào **một** tài khoản theo `MT Account Map`. Cần tách
thì phải sửa loại dòng trên chứng từ trước khi sinh bút toán. Parser cảnh báo
điều này ở mỗi lần nạp.

`Chi tiết doanh số Mega Market.xlsx` là bảng **doanh số** (cơ sở tính chiết
khấu), không phải bảng kê thanh toán — hai đường đọc khác nhau.

## K.6 Danh sách chuỗi có ĐÚNG MỘT nguồn

`ketoan/install.py: MT_CHAINS`. Ba nơi tiêu thụ nó phải khớp tuyệt đối:

| Nơi | Cách lấy |
|---|---|
| `ketoan/api/mt.py: CHAIN_OPTIONS` | `from ketoan.install import MT_CHAINS` |
| `mt_payment_advice.json: chain.options` | tệp tĩnh — kiểm bằng `check_chain_options()` |
| `mt.js` ô chọn chuỗi | backend gửi xuống qua `get_overview.chain_options` |
| `Customer.custom_mt_chain` | patch `v0_0_13` nới options |

`ketoan.install.check_chain_options()` đối chiếu cả ba và được
`regression_check.py` chạy. **Thêm chuỗi mới = sửa đúng một chỗ.**

⚠️ `create_custom_fields` **chỉ TẠO** field lần đầu, **không cập nhật** `options`
của field đã có → thêm chuỗi vào `MT_CHAINS` **bắt buộc** kèm một patch mới.

---

# PHỤ LỤC L — CHIỀU CHIẾT KHẤU: file cơ sở tính CK (MT2-B, 20/08/2026)

Chiều **ngược lại** với phụ lục A–K: ở kia chuỗi báo *"tôi đã trả anh bao nhiêu"*,
ở đây chuỗi báo *"doanh số của anh bao nhiêu"* — và **mình** là bên xuất hóa đơn
chiết khấu (§3 SOP, quy trình BKCK).

Bản đọc: `ketoan/api/mt_discount_read.py` · Bộ kiểm:
`python3 docs/mt/verified/discount_basis_check.py` · Chi tiết BƯỚC 0:
`docs/mt/BUOC0_MT2B_findings.md`.

## L.1 Ba file, ba hình dạng

| Chuỗi | File | Khóa hóa đơn | Chiết khấu |
|---|---|---|---|
| Central Retail | `Chi tiết doanh số BigC.xlsx` · `Data` · 1.770×17 | `INVOICENO` = `C26THG\|6320` | **có sẵn** cột `RB_VALUE` |
| LOTTE | `7466- chi tiết doanh số Lotte.xlsx` · 227×17 | `Invoice No` = `00000984` | **không có** — tỷ lệ hợp đồng |
| Mega Market | `Chi tiết doanh số Mega Market.xlsx` · 6×7 | `Invoice No & PO.` = `1C26THG_00004450` | **không có** — chỉ `Base Amount` |

Emart: `Chi tiết doanh số Emart.PDF` là **PDF**. Chưa viết parser — đúng quy tắc
"chưa có mẫu máy đọc được thì chưa viết".

**Dấu phân cách ký hiệu│số nay có BỐN loại**: `#` WinCommerce · `|` Central
Retail · `-` AEON · `_` Mega Market. Dùng regex chung "ký tự không phải chữ số"
là nuốt nhầm — mỗi chuỗi truyền dấu tường minh (§F).

## L.2 🚨 HAI CÁCH TÍNH CHIẾT KHẤU, KHÔNG THAY NHAU ĐƯỢC

| Mode | Chuỗi | Phép tính |
|---|---|---|
| `per_line` | Central Retail | **cộng từng dòng** `RB_VALUE` |
| `rate_on_total` | LOTTE, Mega | **tỷ lệ × tổng** |

Đo trên mẫu BKCK 261 của BigC:

```
Tổng Cộng                   715.000.265
'Số tiền chiết khấu 3.35%'   23.952.537    ← BigC in ra
715.000.265 × 3,35%        = 23.952.508,88 ← tự tính lại      LỆCH 28,12đ
```

Trên file doanh số 07.2026 cũng vậy: `Σ RB_VALUE` = 25.324.144 vs
`Σ IM_VALUE × 3,35%` = 25.324.111,44 — **lệch 32,56đ**. BigC làm tròn **từng
dòng**.

LOTTE thì ngược lại: `tỷ lệ × tổng` khớp **0đ trên cả 7 kỳ** mẫu (BKCK 155, 172,
229, 243, 260, 280, 300 — tỷ lệ 10%).

⇒ `mode` là **thuộc tính cấu hình của từng chuỗi**, không phải hằng số trong mã.

## L.3 Bẫy

1. **Central Retail có BỐN nhóm, chỉ MỘT là của mình.**

   | `RB_GROUP` | Dòng | `RB_VALUE` | Ai xuất hóa đơn |
   |---|---|---|---|
   | `Discount for store` | 177 | 25.324.144 | **MÌNH** → BKCK |
   | `Fee for EBS` | 177 | 7.559.436 | EB |
   | `Fee for store` | 531 | 62.365.380 | EB |
   | `Support for store` | 885 | 29.859.815 | EB |

   Lấy nhầm = xuất hóa đơn cho khoản mình không được xuất, **và** ghi nhận hai
   lần (ba nhóm kia đã vào sổ ở MT2-D dưới dạng dòng `D1`).

2. **`IM_VALUE` LẶP LẠI ở mọi nhóm** — cộng toàn file là nhân doanh số **6 lần**
   (7.559.436.250 thay vì 755.943.625). Phải LỌC NHÓM TRƯỚC rồi mới cộng.

3. **LOTTE `Fill in date = NOT RECEIVE` là hàng CHƯA NHẬN** — 35/227 dòng,
   25.621.900đ. Tính vào là xuất hóa đơn chiết khấu cho hàng chưa giao. Chính 35
   dòng đó cũng là 35 dòng **không có `Invoice No`**; tầng đọc chốt bằng **cả
   hai** dấu hiệu và báo lệch nếu chúng không còn trùng nhau.

4. **LOTTE `Pur fg = hàng trả lại` thì GIỮ** — 10 dòng, −20.586.100đ, số âm sẵn,
   trừ thẳng vào cơ sở.

5. **`SUPPLIERNAME` / `Supplier Name` là TÊN CỦA MÌNH**, không phải bên mua. Điền
   nó vào ô *"Đơn vị mua hàng"* của BKCK là sai trên một chứng từ hai bên ký. Tên
   bên mua lấy từ `Customer` / `MT Store.address`.

6. **Mega Market không có số kiểm tra nào** — không dòng tổng, không tỷ lệ, không
   cột chiết khấu. `reconciled = False` ở đây là câu trả lời **đúng**: "không
   kiểm được" khác hẳn "đã kiểm và khớp".

## L.4 Cấu trúc BKCK (bản in, giống nhau ở cả hai chuỗi)

```
Số: NNN/BKCK/HG-MT   ·   Ngày … tháng … năm …
Đơn vị bán: Hoàng Giang · MST 0800280839 · địa chỉ · đại diện
Đơn vị mua: pháp nhân / chi nhánh · MST · địa chỉ · đại diện
Số hóa đơn | Ký hiệu | Ngày | Trước thuế | Thuế GTGT | Tổng cộng | Ghi chú
…                                                    (Ghi chú = số PO ở CR)
Tổng Cộng:                       (3 cột tiền)
Số tiền [cần] chiết khấu [X%]:   (3 cột tiền)
```

- Thuế của chiết khấu = **8%** (kiểm: 23.952.537 × 8% = 1.916.202,96 = đúng ô in).
- **Một dãy số duy nhất toàn công ty**, không tách theo chuỗi: 141 · 155 · 172 ·
  229 · 243 · 260 · **261 (BigC)** · 280 · 300 — số của BigC nằm xen giữa dãy LOTTE.
- Central Retail gộp **1 bảng kê / pháp nhân EB**; LOTTE tách **1 bảng kê / chi
  nhánh** (bên mua = MST chi nhánh, lấy từ `MT Store.address`).
- **Dòng tiền ÂM có thật** trong BKCK (LOTTE 3.2026 có 2 dòng hàng trả).

## L.5 Hồ sơ thanh toán WinCommerce

`Mẫu bảng kê ghi nhận hồ sơ thanh toán Winmart.xlsx` — header ở **r2**:
`STT | Code | PO VCM | Ký hiệu HĐ | Số hóa đơn | Ngày hóa đơn | Số Tiền trước VAT
| VAT | Tổng tiền thanh toán | Tên File PDF`

- `Code` = **2007766** (mã NCC của Hoàng Giang tại Win) ở mọi dòng.
- Tên file PDF mẫu thật: **`20260817_2007766_01_PF`** — tức
  `YYYYMMDD_<mã NCC>_<stt hồ sơ>_PF`, **có hậu tố `_PF`** mà §2.2 SOP viết gọn
  đã bỏ mất.
- `STT` trong file **không theo thứ tự** (3,4,5,6,9,10,1,2,7,8,11…) — đó là số
  thứ tự hồ sơ của Win, không phải thứ tự dòng. Đừng đánh lại.
