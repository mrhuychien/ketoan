"""Parser THAM CHIẾU cho bảng kê thanh toán Fuji Mart — bản đọc ĐỘC LẬP.

verified = True  (đo trên docs/mt/samples/'CHI TIẾT THANH TOÁN FUJI.Xls')

MỤC ĐÍCH: KHÔNG phải mã chạy trong app. Bản đọc thứ hai, viết theo cách khác
hẳn `ketoan/api/mt_advice.py: parse_fuji` — ở đây CỐ Ý dùng chỉ số dòng/cột cứng
đọc thẳng từ file mẫu thay vì dò header hai tầng theo nhãn. Hai bản khác cách mà
ra cùng một số thì con số đó đáng tin. `crosscheck_mt2.py` chạy phép so đó.

CẤU TRÚC FILE: MỘT sheet duy nhất, tên 'Mẫu in tài liệu kinh doanh', 65 dòng x
14 cột. **Mười ba dòng đầu TRỐNG HOÀN TOÀN** — file KHÔNG có tiêu đề, KHÔNG có
số bảng kê, KHÔNG có ngày thanh toán ở bất kỳ đâu. Đuôi file là '.Xls' VIẾT HOA.

BỐN KHỐI (không phải hai):

  K1  r14–r15 header 2 tầng, r16–r25 dữ liệu — HÓA ĐƠN ↔ PHIẾU NHẬP KHO
      c1 STT | c2 ngày HĐTC | c3 số HĐTC | c5 ngày PNK | c8 số PNK
      c11 mã kho nhập | c14 GIÁ TRỊ TIỀN THEO PNK            Σ = 90.010.980
  K2  r27 header, r28–r37 dữ liệu — TỔNG THEO HÓA ĐƠN
      c1 STT | c2 ngày hóa đơn | c4 số hóa đơn | c7 số tiền   Σ = 90.010.980
  K3  r40–r41 header 2 tầng, r42–r47 dữ liệu — HÀNG TRẢ (số đã ÂM sẵn)
      c1 STT | c2 ngày | c4 số PNK/XK | c7 giá trị           Σ = −8.191.071
  K4  r51 header, r52–r65 — CHIẾT KHẤU / HỖ TRỢ, mỗi mục HAI dòng
      dòng TÊN:      c2 tên khoản | c12 tiền
      dòng CHI TIẾT: c1 STT | c6 doanh số BAS | c9 tỷ lệ | c10 căn cứ | c12 tiền
                                                            Σ = 10.126.136

SỐ ĐÚNG:
   thanh_toan (K2)        = +90.010.980  (10 dòng)
   ghi_giam   (K3)        =  −8.191.071  ( 6 dòng)
   chiet_khau (K4, 2 mục) =  −2.618.419
   phi        (K4, 5 mục) =  −7.507.717
   NET                    = +71.693.773

BẢY MỤC CỦA K4 (phân loại theo NHÃN, không theo dấu, không theo thứ tự):
   1 Chiết khấu doanh số không điều kiện  81.819.909 × 1%     =   818.199
   2 Chiết khấu thanh toán                90.010.980 × 2%     = 1.800.220
   3 Hỗ trợ hợp tác chiến lược            81.819.909 × 0,5%   =   409.100
   4 Hỗ trợ thẻ khách hàng thân thiết     81.819.909 × 2%     = 1.636.398
   5 Hỗ trợ thuê mướn                     90.010.980 × 1%     =   900.110
   6 Hỗ trợ trưng bày                     90.010.980 × 2,75%  = 2.475.302
   7 Hỗ trợ vận chuyển qua DC SGW         69.560.235 × 3%     = 2.086.807

BẪY (mỗi cái đều làm lệch tiền, đều đã đo):

1. NHÂN ĐÔI DOANH THU. K1 và K2 là CÙNG MỘT SỐ TIỀN nhìn từ hai phía (phiếu
   nhập kho vs hóa đơn), cùng bằng 90.010.980. Sinh dòng tiền từ cả hai là ra
   180.021.960. Chỉ K2 sinh tiền; K1 dùng để đối chiếu chéo và để lấy số PNK +
   mã kho gắn vào từng hóa đơn.

2. CỘNG TRÙNG DÒNG TÊN VÀ DÒNG CHI TIẾT của K4 — hai dòng in CÙNG một số tiền.
   Đọc gộp là gấp đôi toàn bộ chiết khấu (20.252.272 thay vì 10.126.136), và
   đẳng thức 'dòng tên = dòng chi tiết' KHÔNG bắt được vì cả hai vế cùng gấp
   đôi. Chốt duy nhất bắt được là SỐ THỨ TỰ cuối cùng của khối (= 7 mục).

3. BỎ SÓT K3 THÌ SỐ KIỂM TRA KHỚP GIẢ. Nếu không đọc khối hàng trả thì
   'tổng hóa đơn − hàng trả' tụt về đúng 90.010.980 — mà 90.010.980 LẠI LÀ một
   trong các doanh số căn cứ in trong file, nên phép kiểm vẫn tìm thấy và báo
   khớp. Phải đếm số dòng của K3 bằng cột STT (độc lập cột tiền) mới bắt được.

4. 'NGÀY/THÁNG' XUẤT HIỆN HAI LẦN ở tầng 2 của K1 — một lần dưới nhóm
   'THEO HĐTC' (c2, ngày hóa đơn), một lần dưới nhóm 'THEO PHIẾU NK/XK' (c5,
   ngày nhập kho). Tra nhãn phẳng là lấy nhầm ngày; mà Fuji không in ký hiệu
   nên tầng khớp phải dựa vào 'số + NGÀY + tiền' — ngày sai là trượt sạch.

5. KHÔNG CÓ KÝ HIỆU HÓA ĐƠN. Cột số hóa đơn chỉ có số trần ('4409'), lại còn
   đệm hơn 20 dấu cách ở đuôi ('4409                    ') nên phải strip.
   Giống Emart: inv_series = None BẮT BUỘC, và mọi dòng luôn 'Cần review'.

6. Ô NGÀY LÀ EXCEL SERIAL (ctype=3, ví dụ 46174 = 2026-06-01), KHÔNG phải text.
   Đọc bằng str() ra '46174.0'. Phải qua xldate_as_tuple với datemode của
   workbook (datemode = 0 ở file này).

7. KHÔNG CÓ NGÀY THANH TOÁN. Kế toán phải điền tay sau khi nạp, nếu không bảng
   kê không lên đúng kỳ trên màn hình Công nợ MT.

CHƯA XÁC MINH (không có trong file mẫu, đừng đoán):
  · Căn cứ 69.560.235 của mục 7 — không suy ra được từ số nào khác trong file.
    Nhiều khả năng là doanh số riêng phần hàng đi qua DC SGW. Luôn cần người xem.
  · Số PNK/XK của K3 là '2829' cho CẢ 6 dòng — không phải khóa phân biệt, và
    không nối được về hóa đơn nào.
  · Tiền trước thuế / tiền thuế — file chỉ có MỘT cột tiền.
  · Tên/mã siêu thị — chỉ có 'MÃ KHO NHẬP' của K1 ('129', '303', '209', …).
"""

import xlrd

# Mốc dòng/cột 1-based đọc thẳng từ file mẫu. CỐ Ý cứng — bản tham chiếu phải
# độc lập với logic dò header hai tầng của bản chạy thật.
B1_FIRST, B1_LAST = 16, 25
B1_DATE, B1_INV, B1_PNK, B1_KHO, B1_AMT = 2, 3, 8, 11, 14

B2_FIRST, B2_LAST = 28, 37
B2_DATE, B2_INV, B2_AMT = 2, 4, 7

B3_FIRST, B3_LAST = 42, 47
B3_DATE, B3_PNK, B3_AMT = 2, 4, 7

B4_FIRST, B4_LAST = 52, 65
B4_STT, B4_NAME, B4_BASE, B4_RATE, B4_AMT = 1, 2, 6, 9, 12


def _txt(sheet, r, c):
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


def _date(sheet, r, c, datemode):
    """BẪY 6: ô ngày là serial Excel (ctype=3), str() ra '46174.0'."""
    if r > sheet.nrows or c > sheet.ncols:
        return None
    cell = sheet.cell(r - 1, c - 1)
    if cell.ctype != xlrd.XL_CELL_DATE:
        return None
    y, mo, d = xlrd.xldate_as_tuple(cell.value, datemode)[:3]
    return "%04d-%02d-%02d" % (y, mo, d) if y else None


def _kind(name):
    """Phân loại theo NHÃN. 'Chiết khấu *' -> chiết khấu; 'Hỗ trợ *' -> phí."""
    low = name.lower()
    if low.startswith("chiết khấu"):
        return "chiet_khau"
    if low.startswith("hỗ trợ"):
        return "phi"
    return "khac"


def read_rows(path):
    book = xlrd.open_workbook(path)
    sh = book.sheet_by_index(0)
    dm = book.datemode

    # K1: chỉ để tra cứu, KHÔNG sinh tiền (BẪY 1).
    by_inv = {}
    for r in range(B1_FIRST, B1_LAST + 1):
        no = _txt(sh, r, B1_INV)
        if not no:
            continue
        by_inv[no.lstrip("0") or no] = {
            "pnk": _txt(sh, r, B1_PNK),
            "kho": _txt(sh, r, B1_KHO),
            "amount": _num(sh, r, B1_AMT),
        }

    rows = []
    for r in range(B2_FIRST, B2_LAST + 1):
        no = _txt(sh, r, B2_INV)          # BẪY 5: đệm dấu cách, đã strip trong _txt
        amt = _num(sh, r, B2_AMT)
        if not no or amt is None:
            continue
        ref = by_inv.get(no.lstrip("0") or no, {})
        rows.append({
            "kind": "thanh_toan",
            "inv_series": "",             # BẪY 5: Fuji KHÔNG in ký hiệu
            "inv_no": no,
            "amount": amt,
            "inv_date": _date(sh, r, B2_DATE, dm),
            "doc_no": ref.get("pnk", ""),
            "store_code": ref.get("kho", ""),
            "excel_row": r,
        })

    for r in range(B3_FIRST, B3_LAST + 1):
        amt = _num(sh, r, B3_AMT)
        if amt is None:
            continue
        rows.append({
            "kind": "ghi_giam",
            "inv_series": "", "inv_no": "",
            "amount": amt,                # đã ÂM sẵn trong file, giữ nguyên dấu
            "inv_date": _date(sh, r, B3_DATE, dm),
            "doc_no": _txt(sh, r, B3_PNK),
            "excel_row": r,
        })

    # K4: cặp (dòng TÊN, dòng CHI TIẾT). BẪY 2 — chỉ lấy MỘT lần.
    name = None
    for r in range(B4_FIRST, B4_LAST + 1):
        label = _txt(sh, r, B4_NAME)
        if label:
            name = (label, r)
            continue
        stt = _num(sh, r, B4_STT)
        amt = _num(sh, r, B4_AMT)
        if stt is None or amt is None or name is None:
            continue
        rows.append({
            "kind": _kind(name[0]),
            "inv_series": "", "inv_no": "",
            "amount": -abs(amt),          # khoản trừ làm GIẢM tiền về
            "name": name[0],
            "base": _num(sh, r, B4_BASE),
            "rate": _num(sh, r, B4_RATE),
            "stt": int(stt),
            "excel_row": r,
        })
        name = None
    return rows


def extract_check_totals(path):
    """Số kiểm tra của Fuji đều là ĐẲNG THỨC GIỮA HAI SỐ DO FILE IN RA.

    File không in tổng thanh toán ròng, nên không có một con số 'chốt hạ' duy
    nhất như AEON. Bù lại có bốn đẳng thức độc lập, đủ để bắt mọi lỗi đọc cột.
    """
    book = xlrd.open_workbook(path)
    sh = book.sheet_by_index(0)
    b1 = sum(_num(sh, r, B1_AMT) or 0 for r in range(B1_FIRST, B1_LAST + 1))
    b2 = sum(_num(sh, r, B2_AMT) or 0 for r in range(B2_FIRST, B2_LAST + 1))
    b3 = sum(_num(sh, r, B3_AMT) or 0 for r in range(B3_FIRST, B3_LAST + 1))
    bases, stts, label_sum, detail_sum = [], [], 0.0, 0.0
    for r in range(B4_FIRST, B4_LAST + 1):
        if _txt(sh, r, B4_NAME):
            label_sum += _num(sh, r, B4_AMT) or 0
            continue
        if _num(sh, r, B4_STT) is None:
            continue
        detail_sum += _num(sh, r, B4_AMT) or 0
        bases.append(_num(sh, r, B4_BASE))
        stts.append(int(_num(sh, r, B4_STT)))
    return {
        "k1_tong_theo_pnk": b1,
        "k2_tong_theo_hoa_don": b2,
        "k3_hang_tra": b3,
        "k4_dong_ten": label_sum,
        "k4_dong_chi_tiet": detail_sum,
        "k4_so_muc_theo_stt": max(stts) if stts else None,
        "doanh_so_can_cu": sorted(set(b for b in bases if b is not None)),
        # Hai đẳng thức phải đúng: k1 == k2, và k2 + k3 phải nằm trong `bases`.
        "lech_k1_k2": b1 - b2,
        "can_cu_rong_co_trong_file": any(
            abs((b or 0) - (b2 + b3)) < 0.5 for b in bases),
    }


if __name__ == "__main__":
    import os
    import sys

    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "samples",
        "CHI TIẾT THANH TOÁN FUJI.Xls")
    rs = read_rows(p)
    agg = {}
    for x in rs:
        agg[x["kind"]] = agg.get(x["kind"], 0.0) + x["amount"]
    for k, v in sorted(agg.items()):
        print(f"  {k:12} {v:>16,.0f}  ({sum(1 for x in rs if x['kind'] == k)} dòng)")
    print(f"  {'NET':12} {sum(agg.values()):>16,.0f}")
    for k, v in extract_check_totals(p).items():
        print(f"  {k:28} {v}")
