"""Parser ĐÃ CHẠY THẬT trên file mẫu của chuỗi emart — bản tham chiếu.

verified = True
sheet = 'Sheet1 (workbook chỉ có ĐÚNG 1 sheet, visibility=0; nrows=71, ncols=11)'
header_row = 9

columns:
  doc_no -> 'Document Number (cột index 2)'
  row_kind_source -> 'Document Type (cột index 3)'
  inv_no -> 'Invoice no (cột index 4)'
  posting_date_KHONG_DUNG -> 'Posting Date (cột index 5) — ngày Emart ghi sổ, KHÔNG phải ngày hóa đơn'
  inv_date -> 'Document Date (cột index 6)'
  net_due_date_KHONG_PHAI_payment_date -> 'Net due date (cột index 7)'
  currency -> 'Document currency (cột index 8) — toàn bộ 48 dòng data = VND'
  total_amount -> 'Amount in doc. curr. (cột index 9)'
  description -> 'Text (cột index 10)'
  payment_date -> "KHÔNG có trong bảng — lấy từ khối header: ô 'PAYMENT DATE:' (r5c2) → giá trị r5c4 = '15/09/2025'"
  vendor_code -> "ô 'VENDOR CODE:' (r6c2) → r6c4 = '100968' (mã NCC Hoàng Giang tại Emart, KHÔNG phải mã siêu thị)"
  vendor_name -> "ô 'VENDOR NAME:' (r7c2) → r7c4 = 'CÔNG TY CỔ PHẦN HOÀNG GIANG'"
  amount_before_vat -> 'KHÔNG CÓ trong file'
  vat_amount -> 'KHÔNG CÓ trong file'
  store_code -> 'KHÔNG CÓ trong file'
  store_name -> 'KHÔNG CÓ trong file'
  inv_series -> 'KHÔNG CÓ trong file (Emart không cấp ký hiệu)'

invoice_parse: Emart KHÔNG CẤP KÝ HIỆU HÓA ĐƠN — cột 'Invoice no' chỉ chứa CHỮ SỐ THUẦN, không có dấu phân cách nào (khác WinCommerce '1C26THG#1730', Central Retail 'C26THG|4675'). Ví dụ thật: '4406', '4403', '3816', '3182', '8239', '7574'. => inv_series = None BẮT BUỘC, tuyệt đối không đoán ký hiệu (đoán = gán nhầm hóa đơn). inv_no giữ nguyên dạng CHUỖI, không int() (mất số 0 đầu nếu Emart đổi định dạng). Ba dòng chiết khấu I0 (r10-12) có Invoice no HOÀN TOÀN RỖNG → inv_no = None, chỉ có Document Number 1200297339. 26 dòng RE có 26 số hóa đơn phân biệt (3182, 3816, 3820, 3841, 3933, 3934, 4000, 4034, 4035, 4036, 4121, 4122, 4160, 4163, 4164, 4259, 4268, 4328, 4330, 4334, 4335, 4403, 4404, 4406, 4409, 4413). 19 dòng phí I1 chỉ có 2 số: 8239 (18 dòng) và 7574 (1 dòng) — nằm NGOÀI dải số hóa đơn hàng hóa (max 4413), nhiều khả năng là series hóa đơn phí riêng của Hoàng Giang. Theo hợp đồng §F: khớp Emart bằng SỐ + NGÀY + TIỀN và luôn đánh dấu "cần review".
date_parse: Mọi ô ngày đều là TEXT (ctype=1), KHÔNG phải Excel serial — 48/48 dòng data có Document Date ctype=1, nên không đụng tới datemode (datemode=0). CÓ HAI DẤU PHÂN CÁCH TRONG CÙNG MỘT FILE: header 'PAYMENT DATE: 15/09/2025' dùng dấu GẠCH CHÉO, còn các cột ngày trong bảng dùng dấu GẠCH NGANG ('31-08-2025'). Regex phải nhận cả hai: ^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$. Thứ tự luôn dd trước mm sau. Chuẩn hóa về ISO yyyy-mm-dd. inv_date lấy từ 'Document Date' (ngày hóa đơn NCC), KHÔNG lấy 'Posting Date' (ngày Emart ghi sổ) — hai ngày này khác nhau ở hầu hết dòng RE (vd hóa đơn 4406: Document Date 25-08-2025 vs Posting Date 31-08-2025). Dải inv_date: 2025-06-25 → 2025-08-31, 0 dòng lỗi ngày.
amount_parse: Cột 'Amount in doc. curr.' 100% là ctype=2 (number thuần), KHÔNG có dấu phân cách nghìn dạng text, KHÔNG có ngoặc đơn âm, KHÔNG có phần thập phân (kiểm tra: 0/48 giá trị có phần lẻ). Đọc trực tiếp float(cell.value). GIỮ NGUYÊN DẤU của file — tuyệt đối không abs(): dấu chính là chốt đối chiếu với dòng TOTAL (RE âm, I0/I1 dương, cộng tất cả = TOTAL). Vẫn giữ nhánh dự phòng parse text kiểu VN ('1.234.567' → '.' là phân cách nghìn, ',' là thập phân, '(x)' là âm) phòng khi Emart đổi cách xuất. Toàn bộ 48 dòng data đều Document currency = 'VND', không có ngoại tệ.
payment_dates: ['2025-09-15']

row_types:
  {"kind": "chiet_khau", "label": "Document Type = I0 (Text = 'Chiết khấu -08/2025')", "count": 3, "sign": "DƯƠNG trong file (+5.266.245) = khoản Emart TRỪ LẠI", "rule": "Document Type == 'I0'. Dòng 10-12."}
  {"kind": "phi", "label": "Document Type = I1 (Text = 'Phí hỗ trợ -08/2025' và 'Chi phí tạo mã sản phẩm mới 2025-AUG-378')", "count": 19, "sign": "DƯƠNG trong file (+27.388.670) = khoản Emart TRỪ LẠI", "rule": "Document Type == 'I1'. Dòng 14-32. 18 dòng phí hỗ trợ (Invoice no 8239) + 1 dòng chi phí tạo mã (Invoice no 7574, 10.800.000)."}
  {"kind": "thanh_toan", "label": "Document Type = RE (Text = 'Phải trả tiền mua hàng' / 'NHAN 4.8')", "count": 26, "sign": "ÂM trong file (-191.554.740) = tiền Emart phải trả cho mình", "rule": "Document Type == 'RE'. Dòng 34-59. 26 số hóa đơn KHÁC NHAU, không trùng."}
  {"kind": "bo_qua", "label": "Dòng cộng nhóm: 'chiết khấu' (r13), 'phí hỗ trợ' (r33), 'phải trả tiền mua hàng' (r60)", "count": 3, "sign": "theo nhóm", "rule": "Document Type RỖNG, nhãn nằm ở cột Document Number, có số tiền ở cột Amount. Dùng làm SỐ KIỂM TRA, không nạp."}
  {"kind": "bo_qua", "label": "Dòng tổng cuối 'TOTAL' = -158.899.825", "count": 1, "sign": "âm", "rule": "Document Number == 'TOTAL', Document Type rỗng. Số kiểm tra cuối cùng."}
  {"kind": "bo_qua", "label": "Dòng trống hoàn toàn (r1, r2, r4, r8, r62, r70)", "count": 6, "sign": "-", "rule": "mọi ô rỗng"}
  {"kind": "bo_qua", "label": "Khối header nhà cung cấp: 'PAYMENT DETAILS' (r3), PAYMENT DATE (r5), VENDOR CODE + 'Page: 1/1' (r6), VENDOR NAME (r7)", "count": 4, "sign": "-", "rule": "nằm TRƯỚC dòng tiêu đề (r9). Chứa payment_date và vendor — phải đọc, không nạp thành dòng tiền."}
  {"kind": "bo_qua", "label": "Dòng tiêu đề cột (r9)", "count": 1, "sign": "-", "rule": "chứa đồng thời 'Document Number' + 'Document Type' + 'Amount in doc. curr.'"}
  {"kind": "bo_qua", "label": "Ghi chú liên hệ Emart (r63-r69) + dòng footer 'This report is automatically sent from Emart Vietnam system' (r71)", "count": 8, "sign": "-", "rule": "Document Type rỗng, không có số tiền. Chứa ký tự \\xa0 (non-breaking space)."}

totals:
  parser_doc_thanh_toan_RE = -191554740
  parser_doc_chiet_khau_I0 = 5266245
  parser_doc_phi_I1 = 27388670
  parser_NET_cong_tat_ca_48_dong = -158899825
  file_check_dong_cong_chiet_khau_r13 = 5266245
  file_check_dong_cong_phi_ho_tro_r33 = 27388670
  file_check_dong_cong_phai_tra_tien_mua_hang_r60 = -191554740
  file_check_TOTAL_r61 = -158899825
  lech_chiet_khau = 0
  lech_phi = 0
  lech_hang_hoa = 0
  lech_NET = 0
  khop = KHỚP TUYỆT ĐỐI cả 4 số kiểm tra, lệch = 0.00 đồng
  kiem_tra_cong_don = -191.554.740 + 27.388.670 + 5.266.245 = -158.899.825 = đúng dòng TOTAL. Tiền thực Emart chuyển = 158.899.825 VND.
  so_dong_data = 48
  census_71_dong = 6 trống + 4 header NCC + 1 tiêu đề + 3 I0 + 19 I1 + 26 RE + 3 dòng cộng nhóm + 1 TOTAL + 8 ghi chú = 71 = nrows. KHỚP.

BẪY:
  - BẪY TIỀN LỚN NHẤT — file có 4 dòng tổng chứ không phải 2. Hợp đồng §D và gợi ý ban đầu chỉ nói bỏ 'chiết khấu'/'phí hỗ trợ'. File thật còn có dòng cộng 'phải trả tiền mua hàng' (r60, -191.554.740) và dòng 'TOTAL' (r61, -158.899.825). Bỏ sót r60 là cộng dư -191.554.740 (nhân đôi toàn bộ hàng hóa). Cần bổ sung vào hợp đồng.
  - BẪY CHÍ MẠNG — nhãn dòng cộng 'phải trả tiền mua hàng' (r60) TRÙNG NGUYÊN VĂN với nội dung cột Text của 25/26 dòng hàng hóa thật ('Phải trả tiền mua hàng'). Lọc dòng rác bằng cách quét chuỗi trên toàn dòng sẽ XÓA SẠCH 26 dòng hàng hóa. Phải lọc theo cột Document Type, và nhãn tổng nằm ở cột Document Number (khác cột với Text).
  - Phân loại BẮT BUỘC theo Document Type (RE/I0/I1), KHÔNG theo dấu. Emart để hàng hóa ÂM, chiết khấu/phí DƯƠNG — ngược hẳn LOTTE. Lấy dấu làm căn cứ là ghi ngược chiều tiền (hợp đồng §B).
  - payment_date KHÔNG nằm trong bảng, chỉ có ở khối header (r5). BẪY: cột 'Net due date' của 26 dòng RE tình cờ trùng đúng ngày thanh toán 15-09-2025, nhưng 22 dòng I0/I1 lại là 31-08-2025. Ai thấy vậy mà lấy 'Net due date' làm ngày thanh toán sẽ gán sai kỳ cho toàn bộ chiết khấu và phí.
  - Ngày trong CÙNG một file dùng HAI dấu phân cách: header '15/09/2025' (gạch chéo), bảng '31-08-2025' (gạch ngang). Regex chỉ nhận '-' sẽ trả None cho payment_date của MỌI dòng.
  - Ba dòng chiết khấu I0 có Invoice no RỖNG. Code bắt buộc phải có invoice number sẽ vứt mất 5.266.245 đồng, hoặc tệ hơn là raise và bỏ cả file.
  - Document Number KHÔNG duy nhất: 7 mã bị lặp ĐÚNG 3 lần mỗi mã (1200297339, 1200297322, 1200297324, 1200297328, 1200297329, 1200297335, 1200297337) với số tiền khác nhau. Dedupe theo doc_no là mất 14/48 dòng tiền.
  - Số tiền cũng bị lặp trong cùng doc_no khác nhau (836.879, 549.640, 509.329, 1.673.763, 1.099.278, 1.018.655 mỗi số xuất hiện nhiều lần). Dedupe theo (invoice, amount) hay (doc_no, amount) đều mất tiền.
  - Bảng LỆCH 2 CỘT TRỐNG sang phải: cột 0 và 1 rỗng hoàn toàn ở cả 71 dòng, dữ liệu bắt đầu từ index 2. Đã xác minh bằng quét toàn bộ. Đọc theo index cứng 0/1 là ra rỗng hết.
  - Dòng footer r71 nằm ĐÚNG cột 'Document currency' (index 8). Ai nhận diện dòng data bằng 'ô Document currency có giá trị' sẽ nhặt luôn dòng chữ 'This report is automatically sent from Emart Vietnam system'.
  - File là .xls BIFF thật (Composite Document File V2, Excel, code page 1252), openpyxl KHÔNG đọc được. xlrd 2.0.2 đọc được vì là .xls. misa_import._rows() hiện chưa đọc .xls — vẫn là chốt chặn triển khai như hợp đồng §A đã ghi.
  - Phần ghi chú r64-r69 chứa ký tự \xa0 (non-breaking space), không phải space thường — strip() thường không sạch. Không ảnh hưởng dòng tiền nhưng ảnh hưởng nếu ai đó so khớp chuỗi.
  - File KHÔNG có cột tách trước VAT / tiền VAT, chỉ MỘT cột tiền tổng. amount_before_vat và vat_amount buộc phải để None. Tự chia 1.1 hay 1.08 là bịa số.
  - File KHÔNG tách theo siêu thị thành viên. VENDOR CODE 100968 / VENDOR NAME 'CÔNG TY CỔ PHẦN HOÀNG GIANG' là mã của CHÍNH NHÀ CUNG CẤP trong hệ thống Emart, KHÔNG phải mã cửa hàng. Nhồi 100968 vào store_code là sai nghĩa.
  - Dòng r6 có 'Page: 1/1' ở cột 10 — file này chỉ 1 trang. Chưa biết file nhiều trang trông thế nào (xem mục chưa xác minh).
  - Trong 19 dòng phí I1 có 1 dòng khác bản chất: 'Chi phí tạo mã sản phẩm mới 2025-AUG-378' 10.800.000đ, Invoice no 7574 — không phải phí hỗ trợ định kỳ. Gộp chung vào 'phí' vẫn đúng tổng nhưng khi hạch toán con người cần thấy nó tách ra (đã giữ nguyên ở description).

CHƯA XÁC MINH:
  - Ý nghĩa chính xác của I0 vs I1 do Emart định nghĩa — mới suy từ cột Text ('Chiết khấu' vs 'Phí hỗ trợ'). Chưa có tài liệu Emart xác nhận. Nếu Emart phát sinh mã Document Type khác (I2, KR, DZ...) parser hiện raise/bỏ qua âm thầm — đã cho vào nhánh bỏ qua nhưng chưa gặp mẫu thật.
  - Invoice no 8239 và 7574 của các dòng phí nằm ngoài dải hóa đơn hàng hóa (3182-4413). Chưa xác minh đây là series hóa đơn khác của Hoàng Giang hay là chứng từ nội bộ Emart. Không được khớp mù sang Sales Invoice.
  - Ba dòng chiết khấu I0 không có Invoice no — chưa biết khớp về hóa đơn nào, hay là khoản trừ không gắn hóa đơn. Cần kế toán MT xác nhận trước khi ghi nhận.
  - Ánh xạ VENDOR CODE 100968 → Customer nào trong ERPNext (hợp đồng §I vẫn để trống mục này cho mọi chuỗi).
  - Chưa xác minh trường hợp file Emart NHIỀU TRANG (file này 'Page: 1/1') — chưa biết Emart có lặp lại khối header/dòng tiêu đề giữa file hay không. Nếu có, hàm _find_header hiện chỉ lấy dòng tiêu đề ĐẦU TIÊN và mọi dòng tiêu đề sau sẽ rơi vào nhánh bỏ qua (an toàn về tiền), nhưng chưa có mẫu để khẳng định.
  - Chưa xác minh file Emart có nhiều PAYMENT DATE trong một file hay không (bẫy §H của LOTTE). File này chỉ 1 ngày (15/09/2025) và ngày đó nằm ở header nên nếu Emart gộp nhiều kỳ, parser hiện sẽ gán SAI cùng một ngày cho tất cả. Cần thêm file mẫu.
  - Cột 'Posting Date' hiện bị bỏ vì bộ khóa chuẩn không có chỗ chứa. Nếu đối soát cần ngày Emart ghi sổ thì phải bổ sung khóa mới vào hợp đồng.
  - Chưa xác minh Emart có xuất file .xlsx trong trường hợp nào không — mới thấy 1 mẫu .xls.
"""

# -*- coding: utf-8 -*-
"""Đọc bảng kê thanh toán chuỗi Emart (file .xls BIFF do hệ thống Emart VN xuất).

Chỉ ĐỌC + phân loại. Không hạch toán, không tạo/sửa chứng từ.
Đã CHẠY THẬT trên /root/.claude/uploads/.../c1426645-APT_20250915_15094_100968_emart.xls
-> 48 dòng data, khớp tuyệt đối cả 4 số kiểm tra trong file (lệch 0đ).
"""
import re
import xlrd

# Mã loại chứng từ THẬT quan sát trong file Emart. Phân loại dòng BẮT BUỘC dựa
# vào cột này, KHÔNG dựa vào dấu tiền: Emart để hàng hóa ÂM còn chiết khấu/phí
# DƯƠNG, trong khi LOTTE làm ngược lại. Lấy dấu làm căn cứ là ghi ngược chiều tiền.
DOC_TYPE_KIND = {
    "RE": "thanh_toan",   # hàng hóa - tiền Emart trả cho mình (âm trong file)
    "I0": "chiet_khau",   # chiết khấu Emart trừ lại (dương trong file)
    "I1": "phi",          # phí hỗ trợ / chi phí tạo mã (dương trong file)
}

# Nhãn cột lấy NGUYÊN VĂN từ dòng tiêu đề của file thật, không suy đoán.
H_DOC_NO = "Document Number"
H_DOC_TYPE = "Document Type"
H_INV_NO = "Invoice no"
H_POSTING = "Posting Date"
H_DOC_DATE = "Document Date"
H_DUE = "Net due date"
H_CURR = "Document currency"
H_AMOUNT = "Amount in doc. curr."
H_TEXT = "Text"


def _cell_text(sheet, r, c, datemode=0):
    """Lấy giá trị ô về dạng chuỗi đã trim. Trả '' cho ô rỗng/lỗi.

    Trong file Emart mọi ô ngày đều là TEXT ('31-08-2025'), nhưng vẫn xử lý
    ctype=3 (xldate) phòng khi Emart đổi cách xuất -> tránh vỡ âm thầm.
    """
    if c >= sheet.ncols or r >= sheet.nrows:
        return ""
    cv = sheet.cell(r, c)
    t, v = cv.ctype, cv.value
    if t == xlrd.XL_CELL_EMPTY or t == xlrd.XL_CELL_BLANK:
        return ""
    if t == xlrd.XL_CELL_TEXT:
        # \xa0 (non-breaking space) có thật trong phần Note của file
        return v.replace("\xa0", " ").strip()
    if t == xlrd.XL_CELL_NUMBER:
        return ("%d" % v) if float(v).is_integer() else repr(v)
    if t == xlrd.XL_CELL_DATE:
        y, mo, d, hh, mi, ss = xlrd.xldate_as_tuple(v, datemode)
        return "%04d-%02d-%02d" % (y, mo, d)
    if t == xlrd.XL_CELL_BOOLEAN:
        return "1" if v else "0"
    return ""


def _num(sheet, r, c, datemode=0):
    """Đọc số tiền, GIỮ NGUYÊN DẤU của file.

    Không dùng abs(): dấu chính là thông tin đối chiếu với dòng TOTAL.
    Nếu một ngày nào đó Emart xuất tiền dạng text ('1.234.567') thì nhánh
    text ở dưới xử lý; hiện tại 100% ô tiền là ctype=2 (number).
    """
    if c >= sheet.ncols or r >= sheet.nrows:
        return None
    cv = sheet.cell(r, c)
    if cv.ctype == xlrd.XL_CELL_NUMBER:
        return float(cv.value)
    if cv.ctype == xlrd.XL_CELL_TEXT:
        s = cv.value.replace("\xa0", " ").strip()
        if not s:
            return None
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()").replace(" ", "")
        # định dạng VN: '.' là phân cách nghìn, ',' là thập phân
        s = s.replace(".", "").replace(",", ".")
        try:
            val = float(s)
        except ValueError:
            return None
        return -val if neg else val
    return None


_DATE_RE = re.compile(r"^\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*$")


def _iso_date(s):
    """Chuẩn hóa ngày về ISO yyyy-mm-dd.

    BẪY: cùng một file dùng HAI dấu phân cách — header 'PAYMENT DATE: 15/09/2025'
    dùng '/', còn các cột ngày trong bảng dùng '-' ('31-08-2025'). Phải nhận cả hai.
    Thứ tự luôn là NGÀY trước, THÁNG sau (dd-mm-yyyy) — đọc nhầm thành mm-dd
    sẽ sai kỳ thanh toán ở mọi ngày có ngày <= 12.
    """
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = _DATE_RE.match(s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= d <= 31 and 1 <= mo <= 12):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def _find_header(sheet, datemode):
    """Tìm dòng tiêu đề và ánh xạ nhãn -> chỉ số cột.

    KHÔNG hardcode 'header ở dòng 9, lệch 2 cột': file Emart có 2 cột trống bên
    trái và 8 dòng đầu là thông tin nhà cung cấp; nếu Emart thêm/bớt một dòng
    thì hardcode sẽ đọc lệch toàn bộ. Dò theo nhãn thật an toàn hơn.
    """
    for r in range(sheet.nrows):
        cols = {}
        for c in range(sheet.ncols):
            t = _cell_text(sheet, r, c, datemode)
            if t:
                cols[t] = c
        if H_DOC_NO in cols and H_DOC_TYPE in cols and H_AMOUNT in cols:
            return r, cols
    raise ValueError("Khong tim thay dong tieu de Emart (thieu Document Number/Type/Amount)")


def _find_payment_date(sheet, datemode):
    """Ngày thanh toán nằm ở KHỐI HEADER, không nằm trong bảng.

    BẪY TIỀN: cột 'Net due date' của các dòng RE tình cờ trùng ngày thanh toán
    (15-09-2025) nhưng các dòng I0/I1 lại là 31-08-2025. Lấy 'Net due date' làm
    ngày thanh toán sẽ gán sai kỳ cho toàn bộ chiết khấu và phí.
    """
    for r in range(sheet.nrows):
        for c in range(sheet.ncols):
            t = _cell_text(sheet, r, c, datemode)
            if t.upper().startswith("PAYMENT DATE"):
                # giá trị nằm ở ô có nội dung đầu tiên bên phải
                for c2 in range(c + 1, sheet.ncols):
                    v = _cell_text(sheet, r, c2, datemode)
                    if v:
                        return _iso_date(v)
    return None


def _find_vendor(sheet, datemode):
    """VENDOR CODE/NAME trong file Emart là mã của CHÍNH NHÀ CUNG CẤP (Hoàng Giang)
    trong hệ thống Emart — KHÔNG phải mã siêu thị. File này không tách theo cửa hàng.
    """
    code = name = None
    for r in range(sheet.nrows):
        for c in range(sheet.ncols):
            t = _cell_text(sheet, r, c, datemode).upper()
            if t.startswith("VENDOR CODE"):
                for c2 in range(c + 1, sheet.ncols):
                    v = _cell_text(sheet, r, c2, datemode)
                    if v:
                        code = v
                        break
            elif t.startswith("VENDOR NAME"):
                for c2 in range(c + 1, sheet.ncols):
                    v = _cell_text(sheet, r, c2, datemode)
                    if v:
                        name = v
                        break
    return code, name


def parse_emart_payment_advice(path):
    """Trả list dict các dòng DỮ LIỆU (RE/I0/I1) của bảng kê Emart.

    Mọi dòng không có Document Type hợp lệ đều bị bỏ (row_kind='bo_qua' không
    được trả ra) — gồm dòng cộng nhóm, dòng TOTAL, dòng ghi chú, dòng trống.
    """
    wb = xlrd.open_workbook(path)
    sheet = wb.sheet_by_index(0)   # file Emart chỉ có 1 sheet ('Sheet1')
    dm = wb.datemode

    hrow, cols = _find_header(sheet, dm)
    pay_date = _find_payment_date(sheet, dm)
    vendor_code, vendor_name = _find_vendor(sheet, dm)

    c_doc = cols[H_DOC_NO]
    c_type = cols[H_DOC_TYPE]
    c_inv = cols.get(H_INV_NO)
    c_docdate = cols.get(H_DOC_DATE)
    c_amt = cols[H_AMOUNT]
    c_text = cols.get(H_TEXT)

    rows = []
    for r in range(hrow + 1, sheet.nrows):
        doc_type = _cell_text(sheet, r, c_type, dm).upper()
        # BẪY LỚN: các dòng cộng nhóm có nhãn nằm ở cột 'Document Number'
        # ('chiết khấu', 'phí hỗ trợ', 'phải trả tiền mua hàng', 'TOTAL') và
        # để TRỐNG cột Document Type. Ngoài ra nhãn 'phải trả tiền mua hàng'
        # TRÙNG với nội dung cột Text của 26 dòng hàng hóa thật -> lọc theo
        # chuỗi văn bản trên toàn dòng sẽ xóa nhầm sạch hàng hóa.
        # => Chỉ nhận dòng có Document Type thuộc danh sách đã biết.
        kind = DOC_TYPE_KIND.get(doc_type)
        if not kind:
            continue

        amount = _num(sheet, r, c_amt, dm)
        if amount is None:
            # có Document Type mà không có tiền là bất thường -> báo, không nuốt
            raise ValueError("Dong %d co Document Type %r nhung khong doc duoc so tien" % (r + 1, doc_type))

        inv_no = _cell_text(sheet, r, c_inv, dm) if c_inv is not None else ""
        rows.append({
            "row_kind": kind,
            # Emart KHÔNG cấp ký hiệu hóa đơn -> để None, tuyệt đối không đoán.
            "inv_series": None,
            # giữ dạng CHUỖI, không int(): int() làm mất số 0 đầu nếu có.
            # 3 dòng chiết khấu I0 KHÔNG có Invoice no -> None, không được raise.
            "inv_no": inv_no or None,
            # 'Document Date' là ngày hóa đơn của NCC; 'Posting Date' là ngày
            # Emart ghi sổ, hai ngày khác nhau -> dùng Document Date làm ngày hóa đơn.
            "inv_date": _iso_date(_cell_text(sheet, r, c_docdate, dm)) if c_docdate is not None else None,
            # File Emart không tách theo siêu thị thành viên.
            "store_code": None,
            "store_name": None,
            "doc_no": _cell_text(sheet, r, c_doc, dm) or None,
            # File chỉ có MỘT cột tiền, không tách trước/sau VAT -> không bịa.
            "amount_before_vat": None,
            "vat_amount": None,
            # GIỮ NGUYÊN DẤU của file: RE âm, I0/I1 dương. Tổng cộng phải khớp
            # dòng TOTAL của Emart; đổi dấu ở đây là mất chốt đối chiếu.
            "total_amount": amount,
            "payment_date": pay_date,
            "description": (_cell_text(sheet, r, c_text, dm) or None) if c_text is not None else None,
            "_vendor_code": vendor_code,
            "_vendor_name": vendor_name,
            "_excel_row": r + 1,
        })
    return rows


def extract_check_totals(path):
    """Lấy các số kiểm tra do chính Emart in trong file (3 dòng cộng nhóm + TOTAL).

    Bắt buộc đối chiếu sau khi đọc: tổng theo loại phải khớp từng dòng cộng,
    và tổng toàn bộ phải khớp dòng TOTAL. Lệch dù 1 đồng là không được nạp.
    """
    wb = xlrd.open_workbook(path)
    sheet = wb.sheet_by_index(0)
    dm = wb.datemode
    hrow, cols = _find_header(sheet, dm)
    c_doc, c_type, c_amt = cols[H_DOC_NO], cols[H_DOC_TYPE], cols[H_AMOUNT]
    out = {}
    for r in range(hrow + 1, sheet.nrows):
        if _cell_text(sheet, r, c_type, dm):
            continue          # dòng dữ liệu, bỏ qua
        label = _cell_text(sheet, r, c_doc, dm)
        amt = _num(sheet, r, c_amt, dm)
        if label and amt is not None:
            out[label] = amt
    return out