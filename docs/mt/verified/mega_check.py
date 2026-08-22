#!/usr/bin/env python3
"""Kiểm tầng đọc bảng kê thanh toán Mega Market.

Mega là chuỗi cuối cùng có parser, và nó khác mọi chuỗi khác ở đúng hai điểm
làm nó nguy hiểm:

  1. **File KHÔNG có số kiểm tra nào** — không dòng tổng, không số bảng kê,
     không số tiền thanh toán. Nên không có lưới an toàn kiểu "tổng khớp".
  2. **File KHÔNG có cột phân loại** — chỉ có ký hiệu hóa đơn. Cách duy nhất
     biết dòng nào là tiền về, dòng nào là khoản trừ, là đọc ký hiệu.

Trên file mẫu, DẤU TIỀN trùng khớp loại dòng 18/18. Đó chính là cái bẫy: phân
loại bằng dấu sẽ chạy đúng hôm nay và sai câm vào ngày Mega đổi quy ước, vì
tổng NET không đổi nên không phép kiểm SUM nào bắt được.

Bộ này vì thế soi nặng vào chiều đó: đột biến dấu tiền rồi đòi phân loại KHÔNG
được nhúc nhích.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import base64
import collections
import copy
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

FILE = "cttt_mega.xls"

# Số đã đo trên file thật, và cách nó phải ra.
WANT = {
    "n_rows": 18,
    "n_pay": 8,
    "n_ded": 10,
    "thanh_toan": 313_983_000,
    "ghi_giam": -313_983_000,
    "net": 0,
    "pay_date": "2026-07-10",
    "needs_review": 0,
}


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    ma = importlib.import_module("ketoan.api.mt_advice")
    mega_ref = importlib.import_module("mega")

    path = os.path.join(rc.SAMPLES, FILE)
    if not os.path.exists(path):
        print("THIẾU FILE MẪU:", path)
        return 1
    raw = open(path, "rb").read()
    b64 = base64.b64encode(raw).decode()

    print("=" * 82)
    print("KIỂM BẢNG KÊ THANH TOÁN MEGA MARKET")
    print("=" * 82)
    bad = 0

    # ── 1. Đọc file thật ─────────────────────────────────────────────────
    res = ma.read_payment_advice(b64)
    rows = res["rows"]
    tot = collections.defaultdict(float)
    for r in rows:
        tot[r["row_kind"]] += float(r["signed_amount"] or 0)
    n = collections.Counter(r["row_kind"] for r in rows)

    checks = [
        ("nhận diện chuỗi từ chính file", res["chain_key"] == "mega_market"),
        ("số dòng = %d" % WANT["n_rows"], len(rows) == WANT["n_rows"]),
        ("dòng thanh toán = %d" % WANT["n_pay"], n["thanh_toan"] == WANT["n_pay"]),
        ("dòng ghi giảm = %d" % WANT["n_ded"], n["ghi_giam"] == WANT["n_ded"]),
        ("tiền hóa đơn bán ra = %s" % "{:,.0f}".format(WANT["thanh_toan"]),
         round(tot["thanh_toan"]) == WANT["thanh_toan"]),
        ("tiền ghi giảm = %s" % "{:,.0f}".format(WANT["ghi_giam"]),
         round(tot["ghi_giam"]) == WANT["ghi_giam"]),
        ("NET = 0 (cấn trừ hết)", round(sum(tot.values())) == WANT["net"]),
        ("ngày thanh toán = %s" % WANT["pay_date"],
         res["payment_dates"] == [WANT["pay_date"]]),
        ("không dòng nào phải review", sum(1 for r in rows if r["needs_review"]) == 0),
    ]
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
        bad += not ok

    # ── 2. Không có số kiểm tra -> KHÔNG được báo là đã khớp ─────────────
    print("-" * 82)
    ok = res["checks"] == [] and res["reconciled"] is False
    print(f"  {'✅' if ok else '❌'} file không in số kiểm tra nào -> `checks` rỗng và "
          f"`reconciled`=False ('không kiểm được' KHÔNG phải 'đã kiểm và đúng')")
    bad += not ok

    ok = any("KHÔNG in dòng tổng cộng" in w for w in res["warnings"])
    print(f"  {'✅' if ok else '❌'} nói rõ VÌ SAO không khớp được, kèm số để kế toán đối "
          f"chiếu với thông báo Mega gửi")
    bad += not ok

    ok = any("CẤN TRỪ HẾT" in w for w in res["warnings"])
    print(f"  {'✅' if ok else '❌'} nói rõ tiền thực nhận bằng 0 là do cấn trừ, không "
          f"phải lỗi đọc file")
    bad += not ok

    ok = any("HÓA ĐƠN SIÊU THỊ XUẤT CHO MÌNH" in w for w in res["warnings"]) \
        and any("một tài khoản" in w.lower() for w in res["warnings"])
    print(f"  {'✅' if ok else '❌'} gọi đúng tên 10 dòng kia — hóa đơn siêu thị xuất cho "
          f"mình — và nói rõ chúng vào MỘT tài khoản")
    bad += not ok

    ded = [r for r in rows if r["row_kind"] == "ghi_giam"]
    ok = all("siêu thị xuất cho mình" in (r["row_subtype"] or "") for r in ded)
    print(f"  {'✅' if ok else '❌'} mỗi dòng mang đúng nhãn loại chứng từ, không phải "
          f"'chứng từ ký hiệu ...' chung chung")
    bad += not ok

    # ── 3. BẪY CHÍNH: phân loại theo KÝ HIỆU, không theo DẤU ─────────────
    print("-" * 82)
    sheets = ma.read_sheets(b64)
    name, grid = sheets[0]

    def parse(g):
        return ma.parse_mega([(name, g)])

    base = {(r["source_row"]): r["row_kind"] for r in parse(grid)["rows"]}

    # Lật dấu TOÀN BỘ. Nếu phân loại dựa vào dấu, mọi dòng sẽ đổi loại.
    flip = copy.deepcopy(grid)
    for r in range(1, len(flip)):
        flip[r][5] = -float(flip[r][5])
    out = parse(flip)
    after = {r["source_row"]: r["row_kind"] for r in out["rows"]}
    ok = after == base
    print(f"  {'✅' if ok else '❌'} LẬT DẤU cả 18 dòng -> phân loại KHÔNG đổi một dòng nào "
          f"(phân loại theo ký hiệu, không theo dấu)")
    bad += not ok

    ok = sum(1 for r in out["rows"] if r["needs_review"]) == len(out["rows"])
    print(f"  {'✅' if ok else '❌'} …nhưng CẢ {len(out['rows'])} dòng bị gắn cờ 'cần xem "
          f"lại' — dấu ngược là báo động, không phải để đổi loại")
    bad += not ok

    # Lật dấu ĐÚNG MỘT dòng hóa đơn bán ra.
    one = copy.deepcopy(grid)
    one[5][5] = -float(one[5][5])          # r6 = 1C26THG_00004450
    out1 = parse(one)
    hit = next(r for r in out1["rows"] if r["source_row"] == 6)
    ok = hit["row_kind"] == "thanh_toan" and hit["needs_review"]
    print(f"  {'✅' if ok else '❌'} lật dấu MỘT hóa đơn bán ra -> vẫn là '{hit['row_kind_label']}', "
          f"có cờ review")
    bad += not ok

    # ── 4. Ký hiệu lạ / không tách được ──────────────────────────────────
    print("-" * 82)
    weird = copy.deepcopy(grid)
    weird[5][4] = "1C26THG00004450"        # mất dấu phân cách
    out2 = parse(weird)
    hit = next(r for r in out2["rows"] if r["source_row"] == 6)
    ok = (not hit["inv_series"]) and hit["needs_review"] \
        and hit["row_kind"] == "ghi_giam"
    print(f"  {'✅' if ok else '❌'} tham chiếu KHÔNG có dấu phân cách -> ký hiệu để RỖNG, "
          f"gắn cờ, và KHÔNG được tính là tiền về")
    bad += not ok

    ok = "KHÔNG tách được ký hiệu" in (hit["description"] or "")
    print(f"  {'✅' if ok else '❌'} lý do đi CÙNG DÒNG chứ không chỉ nằm ở cảnh báo chung")
    bad += not ok

    # Mọi dòng thành ghi giảm -> lưới an toàn chung phải kêu.
    allded = copy.deepcopy(grid)
    for r in range(1, len(allded)):
        allded[r][4] = str(allded[r][4]).replace("THG", "TAP")
    out3 = ma.parse_sheets([(name, allded)], "mega_market")
    ok = (not any(r["row_kind"] == "thanh_toan" for r in out3["rows"])
          and any("NGHI ĐỌC SAI LOẠI DÒNG" in w for w in out3["warnings"]))
    print(f"  {'✅' if ok else '❌'} không dòng nào là thanh toán -> lưới an toàn chung kêu "
          f"'nghi đọc sai loại dòng'")
    bad += not ok

    # ── 5. Kiểm cột bằng chính sự thừa của file ──────────────────────────
    print("-" * 82)
    meta = mega_ref.read_meta(path)
    ok = meta["n_desc_ok"] == meta["n_data_rows"] == WANT["n_rows"]
    print(f"  {'✅' if ok else '❌'} {meta['n_desc_ok']}/{meta['n_data_rows']} dòng có "
          f"Description = '<Invoice no>,<Store no>' — đẳng thức này là phép kiểm CỘT")
    bad += not ok

    shift = copy.deepcopy(grid)
    for r in range(1, len(shift)):
        shift[r][3] = "rác"
    out4 = parse(shift)
    ok = any("KHÔNG bằng" in w for w in out4["warnings"])
    print(f"  {'✅' if ok else '❌'} Description không còn khớp -> cảnh báo nghi đọc lệch cột")
    bad += not ok

    # ── 6. Dòng ghi giảm giữ số nhưng KHÔNG bao giờ nối được hóa đơn ─────
    print("-" * 82)
    # Ca thật: 'C26TAP 3264' đụng số hóa đơn '00003264' của mình (29/08/2024).
    ded = [r for r in rows if r["row_kind"] == "ghi_giam"]
    ok = all(r["inv_no"] for r in ded) and any(r["inv_no"] == "3264" for r in ded)
    print(f"  {'✅' if ok else '❌'} {len(ded)} dòng ghi giảm VẪN giữ số chứng từ để kế "
          f"toán đối chiếu (gồm '3264' — số đụng hóa đơn 00003264 của mình)")
    bad += not ok

    src = open(os.path.join(rc.REPO, "ketoan/api/mt.py"), encoding="utf-8").read()
    i = src.index("if kind == KIND_PAYMENT:")
    ok = "_match_row" in src[i:i + 200]
    print(f"  {'✅' if ok else '❌'} khớp hóa đơn CHỈ chạy cho dòng 'Thanh toán' — số đụng "
          f"nhau ở dòng ghi giảm không vơ được hóa đơn nào")
    bad += not ok

    # ── 7. Nhận diện chuỗi không đụng 7 chuỗi kia ────────────────────────
    print("-" * 82)
    others = [
        "chi tiet thanh to\xa0n AEON.xls", "CHI TIẾT THANH TOÁN FUJI.Xls",
        "Chi tiết thanh toán BigC.xlsx", "Chi tiết thanh toán Coopmart.xlsx",
        "Chi tiết thanh toán Emart.xls", "Chi tiết thanh toán Lotte.xls",
        "Chi tiết thanh toán Winmart.xlsx",
    ]
    wrong = []
    for f in others:
        p = os.path.join(rc.SAMPLES, f)
        if not os.path.exists(p):
            continue
        sh = ma.read_sheets(base64.b64encode(open(p, "rb").read()).decode())
        if ma.detect_chain(sh) == "mega_market":
            wrong.append(f)
    ok = not wrong
    print(f"  {'✅' if ok else '❌'} dấu hiệu nhận diện Mega KHÔNG trúng file của 7 chuỗi "
          f"kia ({len(others)} file đã thử)")
    bad += not ok

    # ── 8. Đối chiếu chéo với file CÔNG NỢ Mega ──────────────────────────
    print("-" * 82)
    congno = os.path.join(rc.REPO, "docs/mt/samples/congno/congno_mega_market.xlsx")
    if os.path.exists(congno):
        mo = importlib.import_module("ketoan.api.mt_opening")
        op = mo.read_opening(base64.b64encode(open(congno, "rb").read()).decode(),
                             golive="2026-05-01")
        by_no = {}
        for x in op["rows"]:
            if x.get("inv_no"):
                by_no.setdefault(x["inv_no"].lstrip("0"), []).append(x)
        hit = miss = 0
        for r in rows:
            if r["row_kind"] != "thanh_toan":
                continue
            cands = by_no.get(str(r["inv_no"]).lstrip("0")) or []
            if any(abs(abs(float(c["gross"])) - abs(float(r["signed_amount"]))) < 1
                   for c in cands):
                hit += 1
            else:
                miss += 1
        ok = hit == WANT["n_pay"] and miss == 0
        print(f"  {'✅' if ok else '❌'} {hit}/{hit + miss} hóa đơn bán ra khớp ĐÚNG TỪNG "
              f"ĐỒNG với cột TỔNG của file công nợ Mega — bằng chứng cho cách phân loại")
        bad += not ok
    else:
        print("  ⚠ thiếu file công nợ Mega để đối chiếu chéo")

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — đọc đúng 18 dòng, phân loại bám KÝ HIỆU chứ không bám dấu tiền, "
          "và không giả vờ đã khớp khi file không có số kiểm tra")
    return 0


if __name__ == "__main__":
    sys.exit(main())
