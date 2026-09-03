#!/usr/bin/env python3
"""Kiểm TẦNG ĐỌC PDF của bảng kê thanh toán WinCommerce.

════════════════════════════════════════════════════════════════════════════
PHÉP KIỂM CHÍNH: HAI ĐỊNH DẠNG, MỘT CHỨNG TỪ, PHẢI RA CÙNG MỘT SỐ
════════════════════════════════════════════════════════════════════════════

WinCommerce gửi bảng kê bằng PDF. Trước đây phải có người chuyển sang Excel rồi
mới nạp được — một bước tay nằm giữa chứng từ gốc và sổ sách.

May mắn là bộ mẫu có CẢ HAI bản của CÙNG một chứng từ (thanh toán 25.06.2026,
số 2000141337): bản PDF gốc và bản Excel chuyển đổi đã dùng suốt. Nên phép kiểm
mạnh nhất không phải là "PDF đọc ra số đẹp", mà là:

    đọc từ PDF  ==  đọc từ Excel,  TỪNG DÒNG, TỪNG TRƯỜNG

Trùng nhau tới từng trường thì tầng PDF không thể đang đọc sai cột mà vẫn ra
tổng đúng — kiểu hỏng nguy hiểm nhất của mọi tầng đọc file.

════════════════════════════════════════════════════════════════════════════
VÌ SAO CÒN KIỂM CẢ HÌNH DẠNG LƯỚI
════════════════════════════════════════════════════════════════════════════

Bản in kẻ ngang CẢ TRÊN LẪN DƯỚI hàng tiêu đề. Lần chạy đầu, khối tiêu đề bị
đường kẻ tách thành sheet riêng nên `_wc_find_header` không thấy tiêu đề trên
sheet dữ liệu và **bỏ qua sạch 36 dòng**. Số kiểm tra của file bắt được (0đ so
với 245.795.904đ) — nhưng lưới an toàn không phải là chỗ để đỡ một lỗi đã biết.

Chạy KHÔNG cần bench (stub frappe của `regression_check`), nhưng CẦN
`pdfminer.six`; thiếu thì báo BỎ QUA chứ không giả vờ đạt.
"""

import base64
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

SAMPLES = os.path.join(rc.REPO, "docs/mt/samples")
PDF = os.path.join(SAMPLES, "Chi tiết thanh toán Winmart.PDF")
XLSX = os.path.join(SAMPLES, "Chi tiết thanh toán Winmart.xlsx")

# Số của chính chứng từ, in trên giấy.
DECLARED_TOTAL = 245_795_904
N_ROWS = 36
ADVICE_NO = "2000141337"
PAY_DATE = "2026-06-25"
CARRY_FORWARD = 70_880_508


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def key(res):
    """Vân tay từng dòng — MỌI trường quan trọng, không chỉ số tiền."""
    return sorted((r["inv_series"], r["inv_no"], r["signed_amount"], str(r["inv_date"]),
                   r["doc_no"], r["row_kind"], r["row_subtype"], r["description"],
                   r["needs_review"]) for r in res["rows"])


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    try:
        import pdfminer  # noqa: F401
    except ImportError:
        print("=" * 82)
        print("KIỂM TẦNG ĐỌC PDF BẢNG KÊ WINCOMMERCE")
        print("=" * 82)
        print("  ⚠ BỎ QUA — chưa cài `pdfminer.six`")
        print("=" * 82)
        print("KẾT QUẢ: BỎ QUA — không đọc được PDF, KHÔNG kết luận gì")
        return 0

    ma = importlib.import_module("ketoan.api.mt_advice")
    ap = importlib.import_module("ketoan.api.mt_advice_pdf")

    print("=" * 82)
    print("KIỂM TẦNG ĐỌC PDF BẢNG KÊ WINCOMMERCE")
    print("=" * 82)
    bad = 0

    for f in (PDF, XLSX):
        if not os.path.exists(f):
            print(f"  ❌ THIẾU FILE MẪU: {os.path.basename(f)}")
            return 1

    # ── 1. Hai định dạng, một chứng từ ──────────────────────────────────
    pdf = ma.read_payment_advice(b64(PDF), "wincommerce")
    xl = ma.read_payment_advice(b64(XLSX), "wincommerce")

    ok = key(pdf) == key(xl)
    print(f"  {'✅' if ok else '❌'} đọc từ PDF == đọc từ Excel, TỪNG DÒNG TỪNG TRƯỜNG "
          f"({len(pdf['rows'])} vs {len(xl['rows'])} dòng)")
    bad += not ok
    if not ok:
        sp, sx = set(key(pdf)), set(key(xl))
        for x in list(sx - sp)[:3]:
            print("       chỉ có ở Excel:", x)
        for x in list(sp - sx)[:3]:
            print("       chỉ có ở PDF  :", x)

    # ── 2. Đúng số của chính tờ giấy ────────────────────────────────────
    print("-" * 82)
    got = round(sum(r["signed_amount"] for r in pdf["rows"] if r["row_kind"] == "thanh_toan"), 2)
    ok = got == DECLARED_TOTAL
    print(f"  {'✅' if ok else '❌'} cộng dòng ra {got:,.0f} = dòng 'Tổng cộng' in trên giấy")
    bad += not ok

    ok = len(pdf["rows"]) == N_ROWS
    print(f"  {'✅' if ok else '❌'} đủ {N_ROWS} dòng (11 trang 1 + 21 trang 2 + 4 trang 3)")
    bad += not ok

    d = pdf["declared_totals"]
    ok = d.get("total_payment") == DECLARED_TOTAL
    print(f"  {'✅' if ok else '❌'} đọc được dòng 'Tổng cộng' — dòng in LỆCH PHẢI 34pt so với "
          f"bảng nên phải đọc nguyên văn, không ép vào cột")
    bad += not ok

    ok = d.get("payment_document_amount") == DECLARED_TOTAL
    print(f"  {'✅' if ok else '❌'} đọc được bảng 'Chứng từ thanh toán' (số kiểm tra ĐỘC LẬP "
          f"thứ hai của cùng tờ giấy)")
    bad += not ok

    ok = CARRY_FORWARD in (d.get("carry_forward") or [])
    print(f"  {'✅' if ok else '❌'} đọc được chân trang 'Số dư mang sang trang sau' "
          f"({CARRY_FORWARD:,.0f}) và KHÔNG cộng nó vào tổng")
    bad += not ok

    ok = pdf["advice_no"] == ADVICE_NO
    print(f"  {'✅' if ok else '❌'} số chứng từ thanh toán = {ADVICE_NO} — KHÓA CHỐNG TRÙNG, "
          f"mất nó là nạp hai lần cùng bảng kê")
    bad += not ok

    ok = [str(x) for x in pdf["payment_dates"]] == [PAY_DATE]
    print(f"  {'✅' if ok else '❌'} ngày thanh toán {PAY_DATE} (khối chữ trang 1 và bảng cuối "
          f"khớp nhau, không sinh cảnh báo lệch ngày)")
    bad += not ok

    ok = all(c.get("ok") for c in pdf["checks"])
    print(f"  {'✅' if ok else '❌'} MỌI số kiểm tra của file đều khớp")
    bad += not ok

    # ── 3. Hình dạng lưới — chỗ đã hỏng thật một lần ────────────────────
    print("-" * 82)
    raw = open(PDF, "rb").read()
    sheets = ap.pdf_to_sheets(raw)

    data = [(n, g) for n, g in sheets if len(g) > 1 and len(g[0]) == 6]
    ok = len(data) == 3
    print(f"  {'✅' if ok else '❌'} 3 sheet dữ liệu (mỗi trang in một cái), mỗi sheet 6 cột")
    bad += not ok

    hdr_with_data = 0
    for _n, g in data:
        labels = {str(c).strip() for c in g[0] if c}
        if "Số hóa đơn" in labels and "Số tiền" in labels and len(g) > 1:
            hdr_with_data += 1
    ok = hdr_with_data == 3
    print(f"  {'✅' if ok else '❌'} tiêu đề nằm CÙNG sheet với dữ liệu — bản in kẻ ngang cả "
          f"trên lẫn dưới hàng tiêu đề, tách ra là bỏ sạch 36 dòng")
    bad += not ok

    tong = [g for n, g in sheets if "tổng" in n and g and g[0] and "Tổng cộng" in str(g[0][0])]
    ok = len(tong) == 1
    print(f"  {'✅' if ok else '❌'} dòng 'Tổng cộng' ra sheet riêng, nguyên văn một ô")
    bad += not ok

    # ĐO ĐƯỢC, không suy: chỉ TRANG 1 in dòng 'Số dư mang sang trang sau'. Trang 2
    # kết thúc ở nhãn 'Chiết khấu | Số tiền' mà KHÔNG có dòng giá trị. Đường Excel
    # cũng chỉ đọc ra một số (carry_forward = [70.880.508]) — hai tầng đọc độc lập
    # cùng ra một kết quả, nên đây là hình dạng của bản in chứ không phải lỗi đọc.
    cf = [g for n, g in sheets if "tổng" in n and g and g[0]
          and "mang sang trang sau" in str(g[0][0])]
    ok = len(cf) == 1
    print(f"  {'✅' if ok else '❌'} 1 chân trang 'Số dư mang sang trang sau' — đúng bằng số "
          f"lần bản in in ra nó (trang 2 chỉ có nhãn, không có dòng giá trị)")
    bad += not ok

    # Không dòng dữ liệu nào bị nuốt vào ô khác: mỗi dòng dữ liệu phải đủ 6 ô.
    thieu = [(n, i + 1, r) for n, g in data for i, r in enumerate(g[1:], start=1)
             if sum(1 for c in r if c) != 6]
    ok = not thieu
    print(f"  {'✅' if ok else '❌'} mọi dòng dữ liệu đều đủ 6 ô "
          f"{'' if ok else f'— {len(thieu)} dòng thiếu, vd {thieu[0][:2]}'}")
    bad += not ok

    # ── 4. Nhận diện bằng CHỮ KÝ BYTE, không bằng đuôi tên ──────────────
    print("-" * 82)
    ok = ap.is_pdf(raw) and not ap.is_pdf(open(XLSX, "rb").read())
    print(f"  {'✅' if ok else '❌'} nhận PDF bằng chữ ký `%PDF` — chuỗi từng gửi `.Xls` viết "
          f"hoa và tên file có khoảng trắng không ngắt, đuôi tên không tin được")
    bad += not ok

    got = ma.detect_chain(ap.pdf_to_sheets(raw))
    ok = got == "wincommerce"
    print(f"  {'✅' if ok else '❌'} tự nhận ra chuỗi từ chính PDF (được '{got}') — kế toán "
          f"không phải chọn tay")
    bad += not ok

    # ── 5. PDF không đọc được chữ -> nói rõ, không trả 0 dòng ────────────
    print("-" * 82)
    real = ap.read_words
    try:
        ap.read_words = lambda _raw: []
        msg = ""
        try:
            ap.read_sheets_any(b64(PDF))
        except Exception as e:                                   # noqa: BLE001
            msg = str(e)
        ok = "scan" in msg.lower()
        print(f"  {'✅' if ok else '❌'} PDF quét ảnh -> báo đích danh là file scan, không để "
              f"parser trả 0 dòng rồi đổ cho số kiểm tra")
        bad += not ok
    finally:
        ap.read_words = real

    # ── 6. Đường Excel của 7 chuỗi không bị đụng ────────────────────────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/mt_advice.py"), encoding="utf-8").read()
    seg = src.split("def parse_wincommerce")[1].split("\ndef ")[0]
    ok = "if declared_total is None:" in seg and "total_from_text" in seg
    print(f"  {'✅' if ok else '❌'} dòng tổng đọc nguyên văn CHỈ bù khi sheet có header không "
          f"cho — đường Excel vẫn là nguồn chính")
    bad += not ok

    ok = "from ketoan.api.mt_advice_pdf import read_sheets_any" in src
    print(f"  {'✅' if ok else '❌'} nhập trong hàm, không ở mức module (tránh vòng import "
          f"mt_advice -> mt_advice_pdf -> mt_rebate_pdf -> mt_advice)")
    bad += not ok

    # ── 7. CÓ ĐƯỜNG BẤM TỚI — tầng đọc không có nút thì bằng không có ──
    #
    # `read_sheets_any` nhận PDF từ MT2-W, nhưng ô chọn file của nút "Nạp bảng
    # kê thanh toán" giữ nguyên `.xlsx,.xls` suốt từ MT2-D. Hộp thoại của trình
    # duyệt vì vậy LỌC MẤT đúng cái file duy nhất WinCommerce gửi: cả tầng đọc
    # PDF nằm đó mà không có đường nào bấm tới, và không phép kiểm nào thấy —
    # sáu mục trên chỉ đo tầng dưới.
    print("-" * 82)
    mtjs = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"),
                encoding="utf-8").read()
    seg = mtjs.split("function pickFile(")[1].split("input.click()")[0]
    # Đọc CHÍNH GIÁ TRỊ `accept`, không quét cả thân hàm: chú thích ngay trên nó
    # có chữ `.pdf` và `.PDF`, nên `".pdf" in seg` xanh cả khi ô chọn file đã bị
    # sửa về `.xlsx,.xls` — một mục canh dối, đúng kiểu lỗi nó sinh ra để bắt.
    m = re.search(r'input\.accept\s*=\s*"([^"]*)"', seg)
    exts = [x.strip().lower() for x in (m.group(1) if m else "").split(",")]
    ok = ".pdf" in exts
    print(f"  {'✅' if ok else '❌'} ô chọn file của 'Nạp bảng kê thanh toán' CÓ mời PDF "
          f"(tầng đọc nhận PDF thì cửa vào phải mở)  [{m.group(1) if m else 'KHÔNG THẤY'}]")
    bad += not ok
    ok = m is not None and ".PDF" in m.group(1)
    print(f"  {'✅' if ok else '❌'} và cả đuôi VIẾT HOA — backend so chữ ký byte, hộp thoại "
          f"trình duyệt so đuôi tên")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — PDF và Excel của cùng một chứng từ ra trùng khớp từng trường, "
          "mọi số kiểm tra in trên giấy đều khớp, và không parser nào phải sửa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
