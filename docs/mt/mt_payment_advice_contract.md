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

## K.5 Mega Market — có option, chưa có parser

`Mega Market` nằm trong `MT_CHAINS` để **gán khách được ngay**, nhưng chưa có
tầng đọc (chưa có file bảng kê mẫu thật — file `Chi tiết doanh số Mega Market.xlsx`
là bảng **doanh số**, không phải bảng kê thanh toán). Nạp file cho chuỗi này báo
lỗi rõ ràng chứ **không** đọc bừa bằng parser chuỗi khác: parser sai chuỗi không
"đọc thiếu", nó **đọc sai cột tiền** và vẫn ra một con số trông hợp lý.

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
