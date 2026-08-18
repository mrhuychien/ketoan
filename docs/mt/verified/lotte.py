"""Parser ĐÃ CHẠY THẬT trên file mẫu của chuỗi lotte — bản tham chiếu.

verified = True
sheet = 'Payment deduct detail(1) — file chỉ có ĐÚNG 1 sheet, 135 dòng x 15 cột, MỌI ô đều là text (xlrd ctype=1, kể cả tiền và ngày). Định dạng BIFF .xls thật (CDFV2), phải dùng xlrd 2.x; openpyxl KHÔNG đọc được.'
header_row = 1

columns:
  inv_series -> 'Tax No'
  inv_no -> 'Invoice No'
  inv_date -> 'Invoice Date'
  write_date -> 'Write Date'
  store_code -> 'Store CD'
  store_name -> 'Store Name'
  vendor_code -> 'Vendor CD'
  vendor_name -> 'Vendor Name'
  doc_no -> "Deduct Name (CHỈ khi giá trị không thuộc 3 danh mục '*- Auto' — lúc đó nó là số chứng từ, vd '260626-01006-1-0265')"
  amount_before_vat -> 'Pay Amt'
  vat_amount -> 'Vat Amt'
  total_amount -> 'Total Amt'
  payment_date -> 'Payment Date'
  description -> 'Deduct Cause'
  row_kind_source -> 'Deduct Name + Deduct Cause (KHÔNG dùng dấu tiền)'
  stt -> 'NO'

invoice_parse: Ký hiệu và số nằm ở HAI cột riêng, không phải một chuỗi: inv_series = Tax No, inv_no = Invoice No. Ví dụ thật: Tax No='1C26THG' + Invoice No='3996' (dòng 12), Tax No='C26THG' + Invoice No='4742' (dòng 28). Cùng một file dùng lẫn '1C26THG' (35 dòng) và 'C26THG' (10 dòng) cho cùng dải số hóa đơn ⇒ khi khớp phải chuẩn hóa bằng re.sub(r'^\d+','',series.upper()) để '1C26THG' == 'C26THG' (đúng bài học §E của contract), nhưng vẫn lưu bản gốc để đối soát. Đã kiểm: KHÔNG có dòng nào chỉ có Tax No mà thiếu Invoice No hoặc ngược lại; KHÔNG có dòng nào vừa có Invoice No vừa có Deduct Name; 45/45 dòng có Invoice No đều có đủ Write Date + Invoice Date; 45 số hóa đơn đều DUY NHẤT (không trùng kể cả khi bỏ ký hiệu).
date_parse: Chuỗi 8 ký tự YYYYMMDD -> ISO. '20260523' -> '2026-05-23'. KHÔNG phải serial ngày Excel: ô là TEXT nên tuyệt đối không gọi xlrd.xldate_as_tuple (sẽ ném lỗi hoặc ra ngày 1970). Áp dụng cho cả 3 cột ngày: Write Date, Invoice Date, Payment Date. Ô rỗng '' -> None (dòng khấu trừ không có Write/Invoice Date; dòng SUB SUM/SUM không có Payment Date). Đã kiểm: 100% giá trị ngày khác rỗng đều khớp regex \d{8}; không có dòng nào write_date < inv_date. Khoảng inv_date thật: 2026-04-21..2026-06-13; write_date: 2026-05-18..2026-06-15.
amount_parse: Chuỗi có dấu phẩy ngăn nghìn, dấu trừ ĐỨNG TRƯỚC, không có phần thập phân. Dạng thật quan sát được (thay mọi chữ số bằng 9): '9' (tức '0'), '99,999', '999,999', '9,999,999', '99,999,999', '999,999,999', '-9,999', '-99,999', '-999,999', '-9,999,999'. Quy tắc: bỏ NBSP/space, bắt cả dạng '(1,234)' và '1,234-' để phòng bản xuất khác, bỏ dấu phẩy, ép qua regex \d+(\.\d+)? rồi Decimal — KHÔNG dùng float vì cộng 116 dòng phải khớp ĐÚNG TỪNG ĐỒNG với dòng SUM của LOTTE. Ô rỗng -> None. Bất biến đã kiểm trên 100% dòng: Pay Amt + Vat Amt == Total Amt (đúng cả với dòng SUB SUM). Thuế suất suy ra từ 45/45 dòng hóa đơn đều là 8%.
payment_dates: ['2026-07-10 (thô: 20260710) — 97 dòng chi tiết', '2026-07-30 (thô: 20260730) — 19 dòng chi tiết, TOÀN BỘ là hóa đơn hàng hóa, không có một khoản trừ nào']

row_types:
  {"kind": "thanh_toan", "label": "Hóa đơn hàng hóa", "count": 45, "sign": "DƯƠNG (Pay 256.420.000 / Vat 20.513.600 / Total 276.933.600)", "rule": "Tax No và Invoice No đều KHÁC RỖNG. Đây là điều kiện duy nhất đáng tin — không dùng 'Deduct Name rỗng' (xem bẫy NET OFF)."}
  {"kind": "chiet_khau", "label": "Chiết khấu cơ bản (Basic discount - Auto)", "count": 21, "sign": "ÂM (Total -31.460.649)", "rule": "Deduct Name == 'Basic discount - Auto'. Deduct Cause = 'CHIET KHAU CO BAN 202606_007466'."}
  {"kind": "phi", "label": "Phí bán hàng (Sale services fee - Auto)", "count": 21, "sign": "ÂM (Total -8.489.365)", "rule": "Deduct Name == 'Sale services fee - Auto'. Deduct Cause = 'PHI BAN HANG 202606_007466'."}
  {"kind": "phi", "label": "Phí dịch vụ khác (Other services fee - Auto)", "count": 21, "sign": "ÂM (Total -6.454.447)", "rule": "Deduct Name == 'Other services fee - Auto'. Deduct Cause = 'PHI DICH VU KHAC 202606_007466'."}
  {"kind": "ghi_giam", "label": "Hàng trả lại (Hang tra lai)", "count": 2, "sign": "ÂM (Total -809.335 cho cả 2 dòng: -213.715 và -595.620)", "rule": "Deduct Cause == 'Hang tra lai'. BẪY: Deduct Name ở 2 dòng này KHÔNG phải danh mục mà là SỐ CHỨNG TỪ trả hàng ('260626-01006-1-0265', '260707-01005-1-0099') ⇒ phải map vào doc_no, và whitelist Deduct Name theo 3 giá trị '- Auto' sẽ bỏ sót 2 dòng này."}
  {"kind": "ghi_giam", "label": "NET OFF REGULAR 09.07.2026 (cấn trừ)", "count": 6, "sign": "CẢ HAI DẤU — 5 dòng dương (1.459.985 x2, 963.097, 879.575, 767.097) và 1 dòng ÂM (-5.529.739, dòng 129 store 01001). Tổng Total = 0 ở cột Vat.", "rule": "Deduct Name RỖNG + Invoice No RỖNG + Deduct Cause bắt đầu 'NET OFF REGULAR'. Đây là loại dòng KHÔNG có trong contract hiện tại."}
  {"kind": "bo_qua", "label": "SUB SUM (tổng theo từng siêu thị)", "count": 17, "sign": "hỗn hợp — chỉ là số cộng, không phải tiền phát sinh", "rule": "Deduct Cause == 'SUB SUM'. Store CD/Store Name/Payment Date đều RỖNG. Dùng làm số kiểm tra, không ghi nhận."}
  {"kind": "bo_qua", "label": "SUM (tổng toàn file, dòng cuối cùng r135)", "count": 1, "sign": "212.703.522 / 17.016.282 / 229.719.804", "rule": "Deduct Cause == 'SUM'. Contract hiện chỉ nêu 'SUB SUM' ⇒ THIẾU dòng này; lọc bằng == 'SUB SUM' sẽ nhân đôi toàn bộ số tiền của file."}

totals:
  tong_dong_file = 135 (1 dòng header + 134 dòng dữ liệu)
  phan_loai_du_134 = 45 thanh_toan + 21 chiet_khau + 42 phi + 8 ghi_giam + 17 SUB SUM + 1 SUM = 134 ✓
  dong_chi_tiet_ghi_nhan = 116
  thanh_toan = pay 256.420.000 | vat 20.513.600 | total 276.933.600 (45 dòng)
  chiet_khau = pay -29.130.231 | vat -2.330.418 | total -31.460.649 (21 dòng)
  phi = pay -13.836.863 | vat -1.106.949 | total -14.943.812 (42 dòng)
  ghi_giam = pay -749.384 | vat -59.951 | total -809.335 (8 dòng)
  tong_cong_chi_tiet = pay 212.703.522 | vat 17.016.282 | total 229.719.804
  so_kiem_tra_trong_file_SUM_r135 = pay 212.703.522 | vat 17.016.282 | total 229.719.804
  khop_SUM = KHỚP TUYỆT ĐỐI cả 3 cột, sai lệch 0 đồng
  khop_SUB_SUM = 17/17 nhóm SUB SUM khớp đúng từng đồng cả 3 cột với tổng các dòng chi tiết đứng ngay trước nó (đã in đối chiếu từng dòng)
  tong_cac_SUB_SUM = 229.719.804 == dòng SUM ⇒ SUM = tổng các SUB SUM, không tính trùng
  theo_payment_date = {'2026-07-10': '116 dòng? không — 97 dòng chi tiết | net total 93.915.204 (thanh_toan +141.129.000 / chiet_khau -31.460.649 / phi -14.943.812 / ghi_giam -809.335)', '2026-07-30': '19 dòng, toàn bộ thanh_toan | total 135.804.600, KHÔNG có khoản trừ nào', 'tong_2_ngay': '93.915.204 + 135.804.600 = 229.719.804 ✓ khớp dòng SUM'}
  kiem_tra_noi_tai = Pay Amt + Vat Amt == Total Amt đúng ở 134/134 dòng (parser raise nếu lệch)
  thue_suat = 45/45 dòng hóa đơn có vat/pay == 0.08 (8%)

BẪY:
  - BẪY LỚN NHẤT — 'Deduct Name rỗng = hàng hóa' trong contract là SAI. Có 6 dòng 'NET OFF REGULAR 09.07.2026' cũng có Deduct Name rỗng nhưng KHÔNG có hóa đơn. Điều kiện đúng phải là: Tax No và Invoice No đều khác rỗng. Deduct Name rỗng gồm 69 dòng = 45 hóa đơn + 17 SUB SUM + 1 SUM + 6 NET OFF.
  - BẪY DẤU — 'LOTTE: hàng hóa DƯƠNG, khấu trừ ÂM' KHÔNG phải quy tắc phân loại được. Dòng NET OFF r2/r7/r51/r66/r92 DƯƠNG (tối đa 1.459.985) nhưng r129 store 01001 ÂM -5.529.739. Phân loại bằng dấu là ghi nhận ngược chiều tiền ~5,5 triệu.
  - BẪY SỐ KIỂM TRA — file có HAI mức tổng: 17 dòng 'SUB SUM' (mỗi siêu thị) VÀ 1 dòng 'SUM' cuối file (r135). Contract chỉ nêu SUB SUM. Nếu chỉ lọc Deduct Cause == 'SUB SUM' thì dòng SUM 229.719.804 lọt vào dữ liệu và tổng file bị NHÂN ĐÔI.
  - BẪY SUB SUM KHÔNG THEO NGÀY — 11/17 nhóm SUB SUM TRỘN cả 2 payment date (hóa đơn 20260730 + khấu trừ 20260710 trong cùng một SUB SUM, vd store 01017 = 41.111.928). Tuyệt đối KHÔNG dùng SUB SUM làm số tiền của một lần thanh toán. Tiền thực trả phải nhóm lại theo cột Payment Date của từng dòng.
  - BẪY Deduct Name kiêm hai vai — với 2 dòng 'Hang tra lai', cột Deduct Name chứa SỐ CHỨNG TỪ ('260626-01006-1-0265') chứ không phải tên danh mục. Whitelist Deduct Name theo 3 giá trị '- Auto' của contract sẽ bỏ sót/hiểu sai 2 dòng ghi giảm -809.335. Phân loại phải: 3 giá trị '- Auto' là danh mục; giá trị khác = số chứng từ, đọc loại từ Deduct Cause.
  - BẪY store không có hóa đơn — store 01019 và 01018 chỉ có NET OFF + 3 khoản trừ, SUB SUM Total = 0 đúng bằng 0 (1.459.985 = 296.946+173.219+989.820). Nghĩa là khấu trừ được cấn trừ hết bằng NET OFF, không phát sinh tiền mặt. Nếu ghi nhận NET OFF thành 'thanh toán hàng hóa' sẽ khai khống doanh thu thu tiền 1.459.985/store.
  - BẪY ĐỊNH DẠNG FILE — .xls BIFF thật (CDFV2), openpyxl ném lỗi. Bắt buộc xlrd 2.x. Cột 'NO', 'Store CD' ('01019'), 'Invoice No' ('3996'), tiền, ngày — TẤT CẢ đều là ô TEXT (ctype=1). Ép float/int sẽ mất số 0 đầu của Store CD ('01019' -> 1019) và làm hỏng khớp mã siêu thị.
  - BẪY ngày — Payment/Write/Invoice Date là chuỗi '20260523', KHÔNG phải serial Excel. Gọi xlrd.xldate_as_tuple là sai ngày.
  - BẪY ký hiệu — cùng file có cả '1C26THG' (35 dòng) và 'C26THG' (10 dòng) cho cùng dải số hóa đơn, kể cả trong cùng một cửa hàng. Phải bỏ chữ số đầu khi khớp, nếu không 10 hóa đơn sẽ không tìm được Sales Invoice.
  - BẪY cột SUB SUM — dòng SUB SUM có Store CD RỖNG (chỉ còn Vendor Name), nên không nhóm được theo Store CD của chính dòng đó; phải nhóm theo khối các dòng chi tiết đứng TRƯỚC dòng SUB SUM.
  - Tiền phải parse bằng Decimal. Với float, tổng 116 dòng vẫn có nguy cơ lệch hàng đơn vị khi đối chiếu với 229.719.804 — mà lệch 1 đồng cũng là báo động giả cho kế toán.

CHƯA XÁC MINH:
  - Ý nghĩa kế toán của 'NET OFF REGULAR 09.07.2026': suy đoán là bút toán cấn trừ công nợ kỳ trước (dòng dương bù đúng bằng tổng khấu trừ ở 2 store không có hóa đơn), nhưng CHƯA hỏi kế toán MT xác nhận. Đặc biệt dòng ÂM -5.529.739 (store 01001) chưa rõ là gì. Đây là 6 dòng KHÔNG có hóa đơn ⇒ không thể tự khớp Sales Invoice, bắt buộc con người quyết định.
  - Số chứng từ hàng trả lại '260626-01006-1-0265' / '260707-01005-1-0099': chưa biết cấu trúc (nghi là YYMMDD-storeCD-?-seq) và chưa biết ánh xạ sang chứng từ nào bên ERPNext (Sales Return / Credit Note). Chưa xác minh có tồn tại trong hệ thống hay không.
  - Ánh xạ Store CD (01001..01019) -> Customer / địa điểm giao hàng của ERPNext. File chỉ có mã + tên tiếng Anh không dấu ('Nha Trang Gold Coast', 'Nam Sai Gon'). Store 01007 và 01014 không xuất hiện — chưa rõ là không có phát sinh hay đã đóng.
  - Vendor CD '007466' = CONG TY CO PHAN HOANG GIANG — chưa xác minh đây là mã cố định của LOTTE cấp cho công ty, hay thay đổi theo hợp đồng.
  - Chỉ có MỘT file LOTTE để kiểm. Chưa biết bản xuất kỳ khác có thêm loại Deduct Name mới, có ô số thay vì text, có dấu trừ hậu tố, hay nhiều hơn 2 payment date hay không. Parser đã phòng các dạng đó bằng cách RAISE chứ không đoán, nhưng chưa có file thật để chứng minh.
  - Chưa xác minh dòng SUM cuối file luôn nằm ở dòng cuối cùng và Deduct Cause luôn đúng chữ 'SUM' (bản xuất tiếng Việt có thể ghi khác). Parser hiện match chuỗi chính xác.
  - Chưa xác minh quan hệ giữa Write Date và Invoice Date về nghiệp vụ (Write Date luôn >= Invoice Date trong file này, chênh 1-31 ngày) — nghi là ngày LOTTE ghi nhận vào hệ thống.
  - Chưa kiểm 45 số hóa đơn này có thật sự tồn tại trong Sales Invoice của ERPNext hay không (môi trường này không có bench/DB).
"""

# -*- coding: utf-8 -*-
"""Đọc bảng kê thanh toán LOTTE (Payment_deduct_detail*_LOTTE.xls).

VÌ SAO tách riêng: LOTTE là file BIFF .xls, MỌI ô đều là TEXT (ctype=1) —
kể cả tiền và ngày. openpyxl không đọc được .xls nên bắt buộc dùng xlrd.
"""
import re
from decimal import Decimal

import xlrd  # xlrd 2.x CHỈ đọc .xls — đúng nhu cầu ở đây

# Nhãn cột đọc từ file thật, không suy đoán.
COL_NO = "NO"; COL_STORE_CD = "Store CD"; COL_STORE_NAME = "Store Name"
COL_VENDOR_CD = "Vendor CD"; COL_VENDOR_NAME = "Vendor Name"
COL_WRITE_DATE = "Write Date"; COL_INVOICE_DATE = "Invoice Date"
COL_TAX_NO = "Tax No"; COL_INVOICE_NO = "Invoice No"
COL_DEDUCT_NAME = "Deduct Name"; COL_DEDUCT_CAUSE = "Deduct Cause"
COL_PAY = "Pay Amt"; COL_VAT = "Vat Amt"; COL_TOTAL = "Total Amt"
COL_PAYMENT_DATE = "Payment Date"

REQUIRED_COLS = [COL_STORE_CD, COL_TAX_NO, COL_INVOICE_NO, COL_DEDUCT_NAME,
                 COL_DEDUCT_CAUSE, COL_PAY, COL_VAT, COL_TOTAL, COL_PAYMENT_DATE]

# Deduct Name của các khoản trừ tự động. Chỉ 3 giá trị này là "danh mục";
# mọi giá trị Deduct Name khác là SỐ CHỨNG TỪ (vd hàng trả lại), không phải danh mục.
DEDUCT_NAME_KIND = {
    "Basic discount - Auto": ("chiet_khau", "Chiết khấu cơ bản"),
    "Sale services fee - Auto": ("phi", "Phí bán hàng"),
    "Other services fee - Auto": ("phi", "Phí dịch vụ khác"),
}
# Dòng tổng của LOTTE nằm ở cột Deduct Cause. Có HAI mức: SUB SUM (mỗi siêu thị)
# và SUM (tổng toàn file). Bỏ cả hai khỏi dữ liệu, chỉ dùng để đối chiếu.
TOTAL_CAUSES = {"SUB SUM", "SUM"}


def _txt(v):
    """Chuẩn hóa ô về str đã trim. Mọi ô trong file này là text nên rất đơn giản,
    nhưng vẫn phòng trường hợp LOTTE đổi sang ô số ở bản xuất khác."""
    if v is None:
        return ""
    if isinstance(v, float):
        # xlrd trả float cho ô số; số hóa đơn/mã siêu thị là chuỗi -> bỏ .0
        return str(int(v)) if v == int(v) else str(v)
    return str(v).strip()


def parse_amount(raw):
    """'1,459,985' -> Decimal('1459985'); '-274,950' -> Decimal('-274950'); '' -> None.

    VÌ SAO dùng Decimal chứ không float: đây là tiền. float('1459985.0') cộng dồn
    135 dòng vẫn ra sai số ở hàng đơn vị khi đối chiếu với dòng SUM của LOTTE.
    VÌ SAO không dùng float(raw.replace(',','')): còn phải chặn dạng (1,234) và
    dấu trừ đứng sau, để nếu LOTTE đổi định dạng thì VỠ TO chứ không âm thầm sai dấu.
    """
    s = _txt(raw)
    if s == "":
        return None
    s = s.replace("\xa0", "").replace(" ", "")
    neg = False
    if s.startswith("(") and s.endswith(")"):   # dạng kế toán (1,234) = âm
        neg, s = True, s[1:-1]
    if s.endswith("-"):                          # dấu trừ đứng sau
        neg, s = True, s[:-1]
    if s.startswith("-"):
        neg, s = True, s[1:]
    s = s.replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        raise ValueError("Không đọc được số tiền LOTTE: %r" % raw)
    val = Decimal(s)
    return -val if neg else val


def parse_date(raw):
    """'20260523' -> '2026-05-23'; '' -> None. LOTTE ghi ngày dạng chuỗi YYYYMMDD.

    VÌ SAO không dùng xlrd.xldate: ô là TEXT, không phải serial ngày của Excel.
    """
    s = _txt(raw)
    if s == "":
        return None
    if not re.fullmatch(r"\d{8}", s):
        raise ValueError("Ngày LOTTE không đúng dạng YYYYMMDD: %r" % raw)
    return "%s-%s-%s" % (s[0:4], s[4:6], s[6:8])


def normalize_series(series):
    """'1C26THG' và 'C26THG' là MỘT ký hiệu — chữ số dạng hóa đơn ở đầu chỉ là
    số thứ tự mẫu, không thuộc ký hiệu. Bỏ nó khi so khớp, nhưng vẫn giữ bản gốc."""
    return re.sub(r"^\d+", "", _txt(series).upper())


def classify(rec):
    """Phân loại dòng. TUYỆT ĐỐI không dựa vào DẤU của số tiền.

    Bẫy thật trong file: dòng 'NET OFF REGULAR' có Deduct Name RỖNG giống hệt dòng
    hàng hóa, và có dòng mang số ÂM (-5,529,739) — nếu lấy 'Deduct Name rỗng =
    hàng hóa' hoặc lấy dấu để phân loại thì ghi nhận ngược chiều tiền.
    """
    cause = rec["_deduct_cause"]
    name = rec["_deduct_name"]
    if cause in TOTAL_CAUSES:
        return "bo_qua", cause
    if name in DEDUCT_NAME_KIND:
        return DEDUCT_NAME_KIND[name]
    if rec["inv_no"]:
        # Chỉ dòng có ĐỦ Tax No + Invoice No mới là hóa đơn hàng hóa được thanh toán.
        return "thanh_toan", "Hóa đơn hàng hóa"
    if name:
        # Deduct Name có giá trị nhưng không thuộc 3 danh mục -> là số chứng từ.
        # Quan sát thật: Deduct Cause = 'Hang tra lai', Deduct Name = '260626-01006-1-0265'.
        return "ghi_giam", cause or "Ghi giảm theo chứng từ"
    # Không hóa đơn, không Deduct Name, không phải dòng tổng: khoản cấn trừ tự do
    # ('NET OFF REGULAR ...'). Dấu có thể + hoặc -, phải giữ nguyên dấu của file.
    return "ghi_giam", cause or "Không rõ"


def parse_lotte_payment_advice(path):
    """Đọc file bảng kê LOTTE -> list[dict] khóa chuẩn.

    Trả về MỌI dòng dữ liệu, kể cả dòng tổng (row_kind='bo_qua') để tầng trên còn
    đối chiếu được; tầng ghi nhận phải tự lọc row_kind != 'bo_qua'.
    """
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)  # file thật chỉ có 1 sheet: 'Payment deduct detail(1)'

    header_row = None
    for r in range(min(sheet.nrows, 20)):
        vals = [_txt(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
        if COL_TAX_NO in vals and COL_INVOICE_NO in vals and COL_TOTAL in vals:
            header_row = r
            break
    if header_row is None:
        raise ValueError("Không tìm thấy dòng tiêu đề LOTTE (cần 'Tax No'/'Invoice No'/'Total Amt')")

    idx = {}
    for c in range(sheet.ncols):
        label = _txt(sheet.cell_value(header_row, c))
        if label and label not in idx:
            idx[label] = c
    missing = [c for c in REQUIRED_COLS if c not in idx]
    if missing:
        raise ValueError("File LOTTE thiếu cột bắt buộc: %s" % missing)

    def cell(r, label):
        return _txt(sheet.cell_value(r, idx[label])) if label in idx else ""

    out = []
    for r in range(header_row + 1, sheet.nrows):
        vals = [_txt(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
        if not any(vals):
            continue  # dòng trắng cuối file
        series_raw = cell(r, COL_TAX_NO)
        rec = {
            "row_no": r + 1,                       # 1-indexed như người dùng nhìn trong Excel
            "row_kind": None,
            "inv_series": series_raw or None,
            "inv_series_norm": normalize_series(series_raw) or None,
            "inv_no": cell(r, COL_INVOICE_NO) or None,
            "inv_date": parse_date(cell(r, COL_INVOICE_DATE)),
            "write_date": parse_date(cell(r, COL_WRITE_DATE)),
            "store_code": cell(r, COL_STORE_CD) or None,
            "store_name": cell(r, COL_STORE_NAME) or None,
            "doc_no": None,
            "amount_before_vat": parse_amount(cell(r, COL_PAY)),
            "vat_amount": parse_amount(cell(r, COL_VAT)),
            "total_amount": parse_amount(cell(r, COL_TOTAL)),
            "payment_date": parse_date(cell(r, COL_PAYMENT_DATE)),
            "description": None,
            "_deduct_name": cell(r, COL_DEDUCT_NAME),
            "_deduct_cause": cell(r, COL_DEDUCT_CAUSE),
        }
        kind, label = classify(rec)
        rec["row_kind"] = kind
        rec["description"] = (rec["_deduct_cause"] or label) if kind != "thanh_toan" else label
        rec["kind_label"] = label
        if kind == "ghi_giam" and rec["_deduct_name"] and rec["_deduct_name"] not in DEDUCT_NAME_KIND:
            # Deduct Name ở đây là SỐ CHỨNG TỪ ghi giảm của LOTTE, không phải danh mục.
            rec["doc_no"] = rec["_deduct_name"]
        # Kiểm tra nội tại: Pay + Vat phải bằng Total. Lệch là đọc sai cột.
        a, v, t = rec["amount_before_vat"], rec["vat_amount"], rec["total_amount"]
        if a is not None and v is not None and t is not None and a + v != t:
            raise ValueError("Dòng %d: Pay+Vat != Total (%s+%s != %s)" % (rec["row_no"], a, v, t))
        out.append(rec)
    return out
