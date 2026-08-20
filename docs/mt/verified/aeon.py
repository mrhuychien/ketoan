"""Parser THAM CHIẾU cho bảng kê thanh toán AEON — bản đọc ĐỘC LẬP.

verified = True  (đo trên docs/mt/samples/'chi tiet thanh to\\xa0n AEON.xls')

MỤC ĐÍCH: đây KHÔNG phải mã chạy trong app. Nó là bản đọc thứ hai, viết theo
cách khác hẳn `ketoan/api/mt_advice.py: parse_aeon` — ở đây CỐ Ý dùng chỉ số cột
cứng đọc thẳng từ file mẫu, thay vì dò header theo nhãn. Hai bản làm khác cách
mà ra cùng một số tiền thì con số đó đáng tin; giống nhau vì cùng một lỗi thì
gần như không thể. `crosscheck_mt2.py` chạy phép so đó.

CẤU TRÚC FILE (6 sheet, khối header r1–r11 LẶP y hệt ở cả 6):

  Summary(00_265294)    r11 'CREDIT TERM' | 'NET PAYMENT', r12 = E30 | 48.913.623
  Doc(00E30_265294)     r13 header; r14–r34 slip 311 (hàng bán, 21 dòng)
                        r35/r36 'Total Contract PO' / 'TOTAL PO' = 61.884.000
                        r37–r43 slip 312 (hàng trả, 7 dòng, lưu DƯƠNG)
                        r44/r45 'Total Contract GRN' / 'TOTAL GRN' = −2.545.560
                        r46 header khối tổng, r47–r51 số kiểm tra
  Costsumm / Rebsumm    DANH MỤC mã khoản trừ, 3 khối cột (mã, mô tả, tiền)
  Costdet(00E30_265294) r13 header; 5 nhóm mã, mỗi nhóm kết bằng 'Sub-Total'
                        r49 'Total' = 10.424.817
  DcCharges(...)        bảng ĐÔI hai khối cột song song, r26 'Total' = 2.512.222

CỘT sheet Doc (1-based):
   1 SLIP TYPE   2 CONTRACT NO.   3 SLIP NO.   4 SUPPLIER INVOICE / CN NO.
   5 STORE CODE  6 DELIVERY / RETURN DATE      7 AMOUNT
   8 DEPT CODE   9 DEPT DESCRIPTION           10 REMARKS

CỘT sheet Costdet (1-based):
   1 DEDUCTION CODE  2 DEDUCTION DESCRIPTION  3 TYPE  4 CONTRACT NO.  5 SLIP NO
   6 TAX INVOICE     7 STORE CODE             8 SLIP DATE            9 AMOUNT
  10 REMARKS

SỐ ĐÚNG (đã đối chiếu với chính số kiểm tra của file, lệch 0 đồng):
   thanh_toan (311)  =  +61.884.000   (21 dòng)
   ghi_giam   (312)  =   −2.545.560   ( 7 dòng)
   phi     (Costdet) =  −10.424.817   (25 dòng)
   NET               =  +48.913.623   = 'Net Payment' in ở HAI nơi độc lập

BẪY (mỗi cái đều làm lệch tiền, đều đã đo):

1. KHỐI TỔNG NẰM TRONG CHÍNH BẢNG. Cuối sheet Doc có khối tổng mở đầu bằng ĐÚNG
   nhãn 'Slip Type', và các dòng r47/r48 của nó cũng mang mã 311/312. Đọc tiếp
   qua r46 là cộng đôi: 123.768.000 thay vì 61.884.000.

2. HÀNG TRẢ LƯU DƯƠNG, IN ÂM. 7 dòng slip 312 nằm trong bảng với số DƯƠNG
   (434.160; 172.800; …) nhưng 'TOTAL GRN' in −2.545.560. Phân loại phải theo
   cột SLIP TYPE; nếu phân loại theo dấu thì 7 dòng này thành tiền THU VỀ.

3. DcCharges LÀ CHI TIẾT CỦA MỘT DÒNG COSTDET. Tổng DcCharges (2.512.222) bằng
   ĐÚNG dòng mã 'DC' của Costdet. Sinh dòng tiền từ cả hai sheet là cộng trùng
   2.512.222 — mà 'Net Payment' VẪN khớp, vì Net Payment chỉ đối chiếu Costdet.
   Đây là bẫy câm nhất của file này.

4. KHOẢN TRỪ CÓ DÒNG ÂM. Mã RBGPA/RBGPD/RBGPOS/RBPS mỗi mã có 2 dòng âm
   (−8.683; −42.228; …) xen giữa các dòng dương, và Sub-Total là tổng ĐẠI SỐ.
   Lấy `-abs(amt)` là đảo dấu 8 dòng hoàn tiền: lệch đúng 2× tổng các dòng đó.

5. SỐ KIỂM TRA KHÔNG PHẢI 'SỐ CUỐI DÒNG'. Khối tổng có cột 'No of Slips' đứng
   SAU cột 'Amount'. Lấy số cuối dòng thì 'Net Purchase' ra 28 (số slip) thay
   vì 59.338.440 — số kiểm tra biến thành rác mà vẫn trông như số hợp lệ.

6. TAX INVOICE Ở COSTDET LÀ HÓA ĐƠN AEON XUẤT CHO MÌNH (mẫu '1-K26TBE-…',
   '1-K26TDG-…'), KHÔNG phải hóa đơn mình bán ra ('1-C26THG-…'). Đưa nó vào
   `inv_no` là đi khớp nhầm với Sales Invoice của chính mình.

7. TÊN FILE CHỨA \\xa0 (non-breaking space) THẬT: 'chi tiet thanh to\\xa0n AEON.xls'.

CHƯA XÁC MINH (không có trong file mẫu, đừng đoán):
  · Tiền trước thuế / tiền thuế — file chỉ có MỘT cột tiền.
  · Tên siêu thị — chỉ có mã ('8003', '8005', …), không có tên.
  · File nhiều lần thanh toán trong một lần xuất — mẫu chỉ có PAYMENT NO 265294.
"""

import xlrd

# Chỉ số cột 1-based, đọc thẳng từ file mẫu. CỐ Ý cứng — bản tham chiếu phải
# độc lập với logic dò header của bản chạy thật, nếu không thì hai bên cùng sai
# một kiểu và phép đối chiếu chéo mất sạch ý nghĩa.
DOC_SLIP, DOC_CONTRACT, DOC_INV, DOC_STORE, DOC_DATE, DOC_AMT = 1, 2, 4, 5, 6, 7
COST_CODE, COST_TAXINV, COST_STORE, COST_DATE, COST_AMT = 1, 6, 7, 8, 9
SUM_SLIP, SUM_DESC, SUM_AMT, SUM_N = 1, 5, 7, 8

SLIP_KIND = {"311": "thanh_toan", "312": "ghi_giam"}


def _sheet(book, prefix):
    for name in book.sheet_names():
        if name.lower().startswith(prefix.lower()):
            return book.sheet_by_name(name)
    return None


def _txt(sheet, r, c):
    """Ô (1-based) -> chuỗi trim. Float nguyên -> '311' chứ không '311.0'."""
    if r > sheet.nrows or c > sheet.ncols:
        return ""
    v = sheet.cell_value(r - 1, c - 1)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    return str(v).replace("\xa0", " ").strip()


def _num(sheet, r, c):
    if r > sheet.nrows or c > sheet.ncols:
        return None
    cell = sheet.cell(r - 1, c - 1)
    return float(cell.value) if cell.ctype == xlrd.XL_CELL_NUMBER else None


def _summary_row(doc):
    """Dòng bắt đầu khối tổng cuối sheet Doc = lần thứ HAI gặp nhãn 'Slip Type'."""
    seen = 0
    for r in range(1, doc.nrows + 1):
        if _txt(doc, r, DOC_SLIP).strip().lower() == "slip type":
            seen += 1
            if seen == 2:
                return r
    return doc.nrows + 1


def read_rows(path):
    """Trả danh sách dòng tiền: [{kind, inv_series, inv_no, amount, ...}]."""
    book = xlrd.open_workbook(path)
    doc = _sheet(book, "Doc")
    cost = _sheet(book, "Costdet")
    end = _summary_row(doc)

    # PAYMENT DATE nằm ở r8 cột 7 của khối header (cột 6 là nhãn).
    pay_date = _txt(doc, 8, 7)
    advice_no = _txt(doc, 11, 2)

    rows = []
    for r in range(14, end):
        slip = _txt(doc, r, DOC_SLIP)
        if slip not in SLIP_KIND:
            continue
        amt = _num(doc, r, DOC_AMT)
        if amt is None:
            continue
        raw = _txt(doc, r, DOC_INV)
        parts = [p for p in raw.split("-") if p]
        # '1-C26THG-00004246': cụm đầu là SỐ MẪU hóa đơn, bỏ đi.
        series, no = (parts[1], parts[2]) if len(parts) == 3 else ("", raw)
        rows.append({
            "kind": SLIP_KIND[slip],
            "inv_series": series,
            "inv_no": no,
            # Hàng trả lưu dương trong bảng -> đảo dấu cho đúng chiều tiền.
            "amount": -amt if SLIP_KIND[slip] == "ghi_giam" else amt,
            "store_code": _txt(doc, r, DOC_STORE),
            "doc_no": _txt(doc, r, DOC_CONTRACT),
            "inv_date": _txt(doc, r, DOC_DATE),
            "payment_date": pay_date,
            "advice_no": advice_no,
            "excel_row": r,
        })

    if cost:
        for r in range(14, cost.nrows + 1):
            code = _txt(cost, r, COST_CODE)
            amt = _num(cost, r, COST_AMT)
            if not code or amt is None:
                continue          # dòng 'Sub-Total' / 'Total' đều có mã RỖNG
            rows.append({
                "kind": "phi",
                "inv_series": "",
                "inv_no": "",
                # `-amt` chứ KHÔNG `-abs(amt)`: dòng gốc âm là khoản hoàn lại.
                "amount": -amt,
                "code": code,
                # Hóa đơn AEON xuất cho MÌNH -> doc_no, không phải inv_no.
                "doc_no": _txt(cost, r, COST_TAXINV),
                "store_code": _txt(cost, r, COST_STORE),
                "inv_date": _txt(cost, r, COST_DATE),
                "payment_date": pay_date,
                "excel_row": r,
            })
    return rows


def extract_check_totals(path):
    """Số kiểm tra do chính AEON in ra. Lệch dù 1 đồng là KHÔNG được nạp."""
    book = xlrd.open_workbook(path)
    doc = _sheet(book, "Doc")
    cost = _sheet(book, "Costdet")
    summ = _sheet(book, "Summary")
    dcs = _sheet(book, "DcCharges")
    sr = _summary_row(doc)

    out = {}
    for r in range(sr + 1, doc.nrows + 1):
        amt = _num(doc, r, SUM_AMT)
        if amt is None:
            continue
        code = _txt(doc, r, SUM_SLIP)
        label = code if code in SLIP_KIND else _txt(doc, r, SUM_DESC).lower()
        if not label:
            continue
        out[label] = amt
        n = _num(doc, r, SUM_N)
        if n is not None:
            out["n_" + label] = n

    if cost:
        for r in range(cost.nrows, 0, -1):
            if _txt(cost, r, 8).lower() == "total":
                out["costdet_total"] = _num(cost, r, COST_AMT)
                break
    if summ:
        # r11 nhãn 'NET PAYMENT' ở cột 2, r12 giá trị ngay dưới.
        out["summary_net_payment"] = _num(summ, 12, 2)
    if dcs:
        for r in range(dcs.nrows, 0, -1):
            if _txt(dcs, r, 12).lower() == "total":
                out["dccharges_total"] = _num(dcs, r, 13)
                break
    return out


if __name__ == "__main__":
    import os
    import sys

    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "samples",
        "chi tiet thanh to\xa0n AEON.xls")
    rs = read_rows(p)
    agg = {}
    for x in rs:
        agg[x["kind"]] = agg.get(x["kind"], 0.0) + x["amount"]
    for k, v in sorted(agg.items()):
        print(f"  {k:12} {v:>16,.0f}  ({sum(1 for x in rs if x['kind'] == k)} dòng)")
    print(f"  {'NET':12} {sum(agg.values()):>16,.0f}")
    print("  số kiểm tra:", {k: (f"{v:,.0f}" if v is not None else None)
                             for k, v in extract_check_totals(p).items()})
