"""Bản đọc THAM CHIẾU ĐỘC LẬP cho bảng kê thanh toán Mega Market.

Viết KHÁC CÁCH với `ketoan/api/mt_advice.py::parse_mega`, cố ý:

  · bản chạy thật  — dò header theo NHÃN, quét mọi sheet, dùng `split_invoice_ref`
    và `norm_series` của app;
  · bản này        — chỉ số cột CỨNG (0..9) đọc thẳng bằng `xlrd`, tự tách ký
    hiệu bằng regex riêng, tự quyết loại dòng bằng regex riêng.

Hai cách khác hẳn nhau mà ra cùng một số tới từng dòng thì con số đó đáng tin.
Muốn trùng lỗi, cả hai phải cùng nhầm cột theo đúng một kiểu.

Trả list dict theo giao diện chung của `crosscheck_mt2.py`:
    {"excel_row": int (1-based), "kind": str, "amount": float, "inv_no": str}
"""

import re

import xlrd

# Chỉ số cột CỨNG — đọc bằng mắt từ file mẫu, KHÔNG dò nhãn. Đó là điểm khác
# biệt của bản tham chiếu: nếu bản chạy thật dò nhãn sai cột, số sẽ lệch ở đây.
C_STORE = 0
C_DESC = 3
C_INV = 4
C_AMT = 5

# Ký hiệu hóa đơn TT78: [mẫu số]C|K + 2 số năm + 3 ký tự mã người bán.
# Của mình là THG. Regex này viết riêng, không gọi `norm_series` của app.
_RE_REF = re.compile(r"^\s*(?P<ser>[A-Za-z0-9]+)[ _](?P<no>\d+)\s*$")
_OURS = re.compile(r"THG$", re.I)


def read_rows(path):
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)

    out = []
    for r in range(1, sheet.nrows):                 # r0 = header
        cell = sheet.cell(r, C_AMT)
        if cell.ctype != xlrd.XL_CELL_NUMBER:
            continue
        amt = float(cell.value)
        raw = str(sheet.cell_value(r, C_INV)).strip()

        m = _RE_REF.match(raw)
        ser = m.group("ser") if m else ""
        no = m.group("no") if m else raw

        out.append({
            "excel_row": r + 1,                     # 1-based như bản chạy thật
            "kind": "thanh_toan" if _OURS.search(ser) else "ghi_giam",
            "amount": amt,
            "inv_no": no,
        })
    return out


def read_meta(path):
    """Vài số kiểm tra cấu trúc, đọc độc lập — dùng cho `mega_check.py`."""
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    header = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]

    n_desc_ok = 0
    for r in range(1, sheet.nrows):
        store = str(sheet.cell_value(r, C_STORE))
        if store.endswith(".0"):
            store = store[:-2]
        want = "%s,%s" % (str(sheet.cell_value(r, C_INV)).strip(), store)
        if str(sheet.cell_value(r, C_DESC)).strip() == want:
            n_desc_ok += 1

    return {
        "header": header,
        "n_data_rows": sheet.nrows - 1,
        "n_desc_ok": n_desc_ok,
        "n_sheets": book.nsheets,
    }
