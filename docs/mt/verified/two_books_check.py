#!/usr/bin/env python3
"""Kiểm HAI CUỐN SỔ CÔNG NỢ đặt cạnh nhau.

════════════════════════════════════════════════════════════════════════════
VẤN ĐỀ
════════════════════════════════════════════════════════════════════════════

ERPNext ghi công nợ **ngay khi Sales Invoice được ghi sổ**. Kế toán thì theo dõi
trên Excel theo **đầu hóa đơn điện tử**, vì siêu thị chỉ trả tiền cho hóa đơn đã
phát hành. Hai con số khác nhau, và chênh lệch KHÔNG phải sai sót: đó là hàng đã
giao, đã ghi sổ, **chưa xuất hóa đơn điện tử**.

Trước thay đổi này, phần mềm chỉ theo dõi MỘT trong hai cuốn sổ. Kế toán vẫn phải
giữ Excel riêng — và hai bên lệch nhau thì không ai biết lệch ở đâu.

════════════════════════════════════════════════════════════════════════════
HAI CHỐT CHẶN BỘ KIỂM NÀY GIỮ
════════════════════════════════════════════════════════════════════════════

1. **HAI VẾ PHẢI CỘNG LẠI ĐÚNG BẰNG TỔNG.** Cách dễ nhất để hỏng là dựng màn
   công nợ THỨ HAI với truy vấn riêng; đến một ngày hai màn lệch nhau và không
   ai biết tin cái nào. Ở đây là MỘT tập dòng bổ đôi trong CÙNG vòng lặp, nên
   đẳng thức đúng theo cấu tạo — và bộ kiểm khóa nó lại.

2. **PHẢI HỎI CẢ HAI Ô SỐ HÓA ĐƠN.** `custom_misa_inv_no` (luồng tích hợp) và
   `vn_einvoice_number` (luồng cũ, kế toán gõ tay). Hóa đơn cũ chưa chạy
   `misa_legacy` thì ô thứ nhất TRỐNG trong khi hóa đơn đã phát hành từ lâu. Chỉ
   hỏi ô thứ nhất là toàn bộ hóa đơn cũ bị xếp vào "chưa xuất HĐĐT" — một danh
   sách việc phải làm dài hàng nghìn dòng, toàn việc không có thật, và kế toán
   sẽ bỏ luôn cả màn hình.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import ast
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


def row(remaining, has_einvoice, chain="WinCommerce", overdue=None):
    return {"remaining": float(remaining), "has_einvoice": has_einvoice,
            "chain": chain, "days_overdue": overdue, "due_conflict": False,
            "paid_review": 0.0, "bucket": None}


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    md = importlib.import_module("ketoan.api.mt_debt")
    mt = importlib.import_module("ketoan.api.mt")

    for r in ():
        pass
    print("=" * 82)
    print("KIỂM HAI CUỐN SỔ CÔNG NỢ")
    print("=" * 82)
    bad = 0

    # ── 1. Hai vế cộng lại ĐÚNG tổng, ở mọi hình dạng ────────────────────
    shapes = [
        ("thường: có cả hai loại", [row(100, 1), row(250, 0), row(40, 0, "LOTTE")]),
        ("tất cả ĐÃ xuất HĐĐT", [row(100, 1), row(250, 1)]),
        ("tất cả CHƯA xuất HĐĐT", [row(100, 0), row(250, 0)]),
        ("rỗng", []),
        ("số lẻ đồng", [row(1234567.89, 1), row(7654321.11, 0)]),
        ("nhiều chuỗi", [row(10, 1, "AEON"), row(20, 0, "LOTTE"),
                         row(30, 1, "Central Retail"), row(40, 0, "Emart")]),
    ]
    for label, rows in shapes:
        for i, r in enumerate(rows):
            r["bucket"] = md.BUCKET_UNKNOWN
        res = md._rollup(rows)
        e = res.get("by_einvoice")
        if not rows:
            ok = e is None or (e["issued"]["amount"] == 0 and e["pending"]["amount"] == 0)
            print(f"  {'✅' if ok else '❌'} {label} -> không sinh số ma")
            bad += not ok
            continue
        got = round(e["issued"]["amount"] + e["pending"]["amount"], 2)
        ok = got == round(res["total"], 2)
        print(f"  {'✅' if ok else '❌'} {label}: {e['issued']['amount']:,.0f} + "
              f"{e['pending']['amount']:,.0f} = {got:,.0f} (tổng {res['total']:,.0f})")
        bad += not ok

        n = e["issued"]["count"] + e["pending"]["count"]
        ok = n == res["total_count"]
        print(f"     {'✅' if ok else '❌'} và số hóa đơn cũng cộng đủ ({n}/{res['total_count']})")
        bad += not ok

    # ── 2. Cộng theo CHUỖI cũng phải khớp ────────────────────────────────
    print("-" * 82)
    rows = [row(100, 1), row(250, 0), row(40, 0, "LOTTE"), row(60, 1, "LOTTE")]
    for r in rows:
        r["bucket"] = md.BUCKET_UNKNOWN
    res = md._rollup(rows)
    ok = all(round(c["einv_issued"] + c["einv_pending"], 2) == round(c["amount"], 2)
             for c in res["chains"])
    print(f"  {'✅' if ok else '❌'} mỗi chuỗi: đã xuất + chưa xuất = nợ của chuỗi đó")
    bad += not ok

    tong_chuoi = round(sum(c["einv_pending"] for c in res["chains"]), 2)
    ok = tong_chuoi == round(res["by_einvoice"]["pending"]["amount"], 2)
    print(f"  {'✅' if ok else '❌'} cộng 'chưa xuất' của các chuỗi = tổng 'chưa xuất'")
    bad += not ok

    # ── 3. Site chưa có ô số HĐĐT -> KHÔNG chia bừa ──────────────────────
    print("-" * 82)
    rows = [dict(row(100, None), bucket=md.BUCKET_UNKNOWN),
            dict(row(250, None), bucket=md.BUCKET_UNKNOWN)]
    res = md._rollup(rows)
    ok = res["by_einvoice"] is None
    print(f"  {'✅' if ok else '❌'} không có ô số HĐĐT -> trả None, KHÔNG xếp hết vào "
          f"'chưa xuất' (không biết ≠ chưa xuất)")
    bad += not ok

    # ── 4. HỎI CẢ HAI Ô — chốt chặn quan trọng nhất ──────────────────────
    print("-" * 82)
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()
    expr = mt.einvoice_issued_expr()
    ok = expr and "custom_misa_inv_no" in expr and "vn_einvoice_number" in expr
    print(f"  {'✅' if ok else '❌'} hỏi CẢ `custom_misa_inv_no` LẪN `vn_einvoice_number` — "
          f"hóa đơn cũ chưa chạy misa_legacy vẫn được tính là ĐÃ xuất")
    bad += not ok

    ok = expr and " OR " in expr
    print(f"  {'✅' if ok else '❌'} nối bằng OR (có MỘT trong hai ô là đã xuất), không phải AND")
    bad += not ok

    # chỉ có ô mới
    frappe.get_meta = lambda dt: type(
        "M", (), {"has_field": staticmethod(lambda f: f == "custom_misa_inv_no")})()
    e2 = mt.einvoice_issued_expr()
    ok = e2 and "custom_misa_inv_no" in e2 and "vn_einvoice_number" not in e2
    print(f"  {'✅' if ok else '❌'} site thiếu ô cũ -> chỉ hỏi ô đang có, không sinh SQL gãy")
    bad += not ok

    # không có ô nào
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: False)})()
    ok = mt.einvoice_issued_expr() is None
    print(f"  {'✅' if ok else '❌'} site không có ô nào -> trả None để tầng trên bỏ hẳn phép chia")
    bad += not ok

    # ── 5. Bộ lọc danh sách: chặn giá trị lạ, không im lặng bỏ qua ───────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/mt.py"), encoding="utf-8").read()
    seg = src.split("def get_invoices")[1].split("\ndef ")[0]
    ok = 'einvoice not in ("da", "chua")' in seg and "frappe.throw" in seg
    print(f"  {'✅' if ok else '❌'} giá trị lọc lạ -> CHẶN. Im lặng bỏ qua thì màn hình tưởng "
          f"đang lọc mà thật ra hiện cả hai vế — con số đọc ra sai gấp đôi")
    bad += not ok

    pg = src.split("def _invoice_page")[1].split("\ndef ")[0]
    ok = "einvoice_issued_expr()" in pg and '"NOT "' in pg
    print(f"  {'✅' if ok else '❌'} danh sách lọc bằng CHÍNH biểu thức dùng để cộng số — "
          f"một định nghĩa, không hai")
    bad += not ok

    # ── 6. Một định nghĩa cho cả app ────────────────────────────────────
    print("-" * 82)
    users = []
    for f in ("mt.py", "mt_debt.py"):
        t = open(os.path.join(rc.REPO, "ketoan/api", f), encoding="utf-8").read()
        if "einvoice_issued_expr" in t:
            users.append(f)
    ok = set(users) == {"mt.py", "mt_debt.py"}
    print(f"  {'✅' if ok else '❌'} cả tầng tổng quan lẫn tầng công nợ dùng chung "
          f"`einvoice_issued_expr` ({', '.join(users)})")
    bad += not ok

    # KHÔNG được có định nghĩa thứ hai của trục HAI CUỐN SỔ.
    #
    # Quét hẹp, có chủ ý: chỉ soi các module CÔNG NỢ, và chỉ soi ô CŨ
    # `vn_einvoice_number`. Vì sao không quét cả `custom_misa_inv_no` toàn app:
    # ba chỗ khác dùng nó để hỏi câu KHÁC, và chúng đúng khi làm vậy —
    #   · `mt_win`      — gom hóa đơn nộp hồ sơ Win, cần đúng số MISA để đặt tên file;
    #   · `mt_discount` — in số hóa đơn lên bảng kê chiết khấu;
    #   · `misa_vat`    — định nghĩa của chính nó là "nối được với MISA hay chưa".
    # Gộp chúng vào đây là bắt ba màn hình trả lời một câu không phải câu của nó.
    stray = []
    for f in ("mt_debt.py", "mt_hub.py"):
        t = open(os.path.join(rc.REPO, "ketoan/api", f), encoding="utf-8").read()
        if "vn_einvoice_number" in t:
            stray.append(f)
    # Đếm trong CODE, không đếm trong văn — xem `regression_check.code_only`.
    #
    # Bản đầu đếm bằng `src.count(...)` và nó báo hỏng vì chính cái docstring
    # đang DẶN "đừng gõ lại tên ô" có nhắc tên ô. Phép kiểm đếm cả chú thích thì
    # cách duy nhất để nó xanh lại là bớt giải thích — ngược chiều mong muốn.
    n_mt = rc.code_only(os.path.join(rc.REPO, "ketoan/api/mt.py")).count(
        '"vn_einvoice_number"')
    ok = not stray and n_mt == 1
    print(f"  {'✅' if ok else '❌'} ô cũ `vn_einvoice_number` chỉ xuất hiện ĐÚNG MỘT LẦN trong "
          f"`mt.py` (hằng số của `einvoice_issued_expr`), không rải sang module công nợ nào "
          f"{'' if ok else '— ' + ', '.join(stray or []) + f' / mt.py x{n_mt}'}")
    bad += not ok

    # ── 7. TÁCH THEO TỪNG CHUỖI — dữ kiện phải đủ để XẾP THỨ TỰ LÀM ──────
    #
    # Tiền và số tờ nói "to bao nhiêu". Ngày tờ cũ nhất nói "đọng bao lâu", và
    # đọng lâu mới là thứ quyết định gọi chuỗi nào trước. Thiếu nó thì bảng chỉ
    # xếp được theo số to, tức là luôn bỏ quên khoản nhỏ mà chết lâu.
    print("-" * 82)
    rows = [dict(row(100, 1, "WinCommerce"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-08-01"),
            dict(row(250, 0, "WinCommerce"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-03-15"),
            dict(row(70, 0, "WinCommerce"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-07-20"),
            dict(row(60, 1, "LOTTE"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-06-01")]
    res = md._rollup(rows)
    by = {c["chain"]: c for c in res["chains"]}

    ok = by["WinCommerce"]["einv_issued_n"] == 1 and by["WinCommerce"]["einv_pending_n"] == 2
    print(f"  {'✅' if ok else '❌'} mỗi chuỗi đếm CẢ HAI vế (Win: 1 đã xuất / 2 chưa xuất) — "
          f"chỉ đếm vế chưa xuất thì không nói được 'còn bao nhiêu phần trăm'")
    bad += not ok

    ok = by["WinCommerce"]["einv_pending_oldest"] == "2026-03-15"
    print(f"  {'✅' if ok else '❌'} tờ chưa xuất CŨ NHẤT của chuỗi = 2026-03-15 "
          f"(không phải tờ mới hơn, cũng không phải tờ đã xuất)")
    bad += not ok

    ok = res["by_einvoice"]["pending"]["oldest"] == "2026-03-15"
    print(f"  {'✅' if ok else '❌'} mức toàn kênh lấy tờ cũ nhất của MỌI chuỗi")
    bad += not ok

    ok = by["LOTTE"]["einv_pending_oldest"] is None and by["LOTTE"]["einv_pending"] == 0
    print(f"  {'✅' if ok else '❌'} chuỗi xuất hết -> không bịa ra ngày 'cũ nhất'")
    bad += not ok

    # Cờ "biết hay không" ĐẶT THEO TỪNG CHUỖI.
    mixed = [dict(row(100, None, "AEON"), bucket=md.BUCKET_UNKNOWN, posting_date="2026-01-01"),
             dict(row(200, 0, "Emart"), bucket=md.BUCKET_UNKNOWN, posting_date="2026-01-01")]
    r2 = {c["chain"]: c for c in md._rollup(mixed)["chains"]}
    ok = r2["AEON"]["einv_known"] is False and r2["Emart"]["einv_known"] is True
    print(f"  {'✅' if ok else '❌'} chuỗi không có dữ kiện HĐĐT -> `einv_known` False, để giao "
          f"diện nói 'chưa biết' thay vì vẽ 0đ (0đ đọc thành 'đã xuất hết')")
    bad += not ok

    # ── 7b. SỐ HĐĐT ĐÃ CHẾT nằm TRONG vế "đòi được", không thành vế thứ ba ──
    #
    # Hóa đơn bị hủy / bị thay thế trên MISA vẫn giữ nguyên số cũ, nên
    # `einvoice_issued_expr()` vẫn tính là "đã xuất" và nó rơi vào cột "Đòi
    # được". Nhưng siêu thị không trả theo một số đã chết. Đếm riêng để cảnh
    # báo — KHÔNG tách thành vế thứ ba, vì tách là hai vế thôi cộng lại bằng
    # tổng, mà đẳng thức đó là thứ duy nhất giữ cho thẻ không nói dối.
    print("-" * 82)
    rows = [dict(row(100, 1, "WinCommerce"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-05-01", misa_dead=1),
            dict(row(300, 1, "WinCommerce"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-05-02", misa_dead=0),
            dict(row(50, 0, "WinCommerce"), bucket=md.BUCKET_UNKNOWN,
                 posting_date="2026-05-03", misa_dead=0)]
    res = md._rollup(rows)
    e = res["by_einvoice"]
    ok = (round(e["issued"]["amount"], 2) == 400.0
          and round(e["issued"]["dead_amount"], 2) == 100.0
          and e["issued"]["dead_count"] == 1)
    print(f"  {'✅' if ok else '❌'} số đã chết ({e['issued']['dead_amount']:,.0f}đ) nằm TRONG "
          f"'đòi được' ({e['issued']['amount']:,.0f}đ), không cộng thêm")
    bad += not ok

    ok = round(e["issued"]["amount"] + e["pending"]["amount"], 2) == round(res["total"], 2)
    print(f"  {'✅' if ok else '❌'} và hai vế VẪN cộng lại đúng bằng tổng — đẳng thức không bị "
          f"cảnh báo mới làm hỏng")
    bad += not ok

    frappe.get_meta = lambda dt: type(
        "M", (), {"has_field": staticmethod(lambda f: f != "custom_misa_status")})()
    ok = mt.misa_dead_expr() is None
    print(f"  {'✅' if ok else '❌'} site chưa có ô trạng thái MISA -> trả None, không bịa ra "
          f"'số đã chết'")
    bad += not ok
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()

    dsrc = open(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"), encoding="utf-8").read()
    ok = "Đã hủy" not in dsrc and "Đã thay thế" not in dsrc
    print(f"  {'✅' if ok else '❌'} danh sách trạng thái 'đã chết' chỉ khai MỘT nơi (`mt.py`), "
          f"không chép sang module công nợ")
    bad += not ok

    # ── 8. BỘ LỌC: một luật cho CẢ tổng hợp lẫn danh sách ────────────────
    print("-" * 82)
    ok = md._filter_einvoice([{"has_einvoice": None}], "chua", known=False) \
        == ([{"has_einvoice": None}], False, False)
    print(f"  {'✅' if ok else '❌'} site không có ô HĐĐT -> KHÔNG lọc, và báo về `applied=False`. "
          f"Lọc lúc đó là biến 'không biết' thành 'chưa xuất'")
    bad += not ok

    keep, applied, known = md._filter_einvoice(
        [{"has_einvoice": 1}, {"has_einvoice": 0}], "chua", known=True)
    ok = applied and known and len(keep) == 1 and keep[0]["has_einvoice"] == 0
    print(f"  {'✅' if ok else '❌'} có dữ kiện -> lọc thật, giữ đúng vế được hỏi")
    bad += not ok

    # "KHÔNG BIẾT" (thiếu ô) ≠ "KHÔNG CÓ GÌ" (hết nợ).
    #
    # Cách sai — và đã từng nằm trong chính bản này — là suy cờ từ dữ liệu:
    # `any(has_einvoice is not None for r in rows)`. Công nợ sạch thì nó ra
    # False, và màn hình đi bảo kế toán chạy `bench migrate` cho một site
    # hoàn toàn ổn.
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()
    ok = md.einv_available() is True
    print(f"  {'✅' if ok else '❌'} có ô số HĐĐT -> `einv_available()` True")
    bad += not ok

    _, _, known0 = md._filter_einvoice([], "chua")
    ok = known0 is True
    print(f"  {'✅' if ok else '❌'} HẾT NỢ (0 dòng) mà site VẪN có ô -> vẫn báo 'biết'. "
          f"Suy cờ từ dữ liệu là bảo kế toán migrate một site không hỏng")
    bad += not ok

    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: False)})()
    ok = md.einv_available() is False
    print(f"  {'✅' if ok else '❌'} thật sự thiếu ô -> False")
    bad += not ok
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()

    try:
        md._norm_einvoice("bịa")
        ok = False
    except Exception:
        ok = True
    print(f"  {'✅' if ok else '❌'} giá trị lọc lạ -> CHẶN ở cả tầng công nợ, không riêng "
          f"`mt.get_invoices`")
    bad += not ok

    # ── 9. CHỐT CHẶN LỚN NHẤT: con số trên thẻ = danh sách bấm ra ────────
    #
    # Lỗi thật đã xảy ra (MT2-X): thẻ đếm bằng `mt_debt._fetch` (posting_date
    # <= as_of, KHÔNG chặn dưới — nợ là SỐ DƯ) còn danh sách bấm ra dùng
    # `mt._invoice_page` (posting_date BETWEEN fd AND td, mặc định portal là 3
    # THÁNG GẦN ĐÂY). Thẻ nói 65 tờ, bấm vào ra ít hơn, và tờ bị giấu chính là
    # tờ cũ nhất — thứ nguy hiểm nhất.
    #
    # Đây là phép kiểm CHẠY THẬT, không phải đọc chữ trong file.
    print("-" * 82)
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.db.table_exists = lambda dt: True
    md._company = lambda company=None: "HGC"
    md._orphan_returns = lambda company, as_of: {"orphan_return_count": 0,
                                                 "orphan_return_amount": 0.0}
    AS_OF = "2026-08-28"

    def _r(name, amount, has_e, posting):
        return {"name": name, "customer": "K", "customer_name": "K",
                "posting_date": posting, "due_date": None, "grand_total": amount,
                "chain": "WinCommerce", "credit_days": 0, "paid": 0.0,
                "clawed_back": 0.0, "paid_review": 0.0, "last_payment_date": None,
                "returned": 0.0, "has_einvoice": has_e, "remaining": amount}

    FIXTURE = [
        _r("SI-CU", 250, 0, "2025-11-02"),      # CŨ HƠN 3 THÁNG — tờ từng bị giấu
        _r("SI-MOI", 70, 0, "2026-08-01"),
        _r("SI-DAXUAT", 100, 1, "2026-07-01"),
    ]
    md._fetch = lambda company, as_of, chain=None, customer=None, search=None: [
        dict(r) for r in FIXTURE]

    s = md.get_due_summary(as_of=AS_OF, einvoice="chua")
    l = md.get_due_invoices(as_of=AS_OF, einvoice="chua", page_size=200)
    ok = (round(s["total"], 2) == round(l["amount"], 2)
          and s["total_count"] == l["total"])
    print(f"  {'✅' if ok else '❌'} lọc 'chưa xuất': tổng hợp {s['total']:,.0f}đ/{s['total_count']}HĐ "
          f"= danh sách {l['amount']:,.0f}đ/{l['total']}HĐ — đầu trang và bảng dưới CÙNG một tập")
    bad += not ok

    ok = "SI-CU" in [r["name"] for r in l["rows"]]
    print(f"  {'✅' if ok else '❌'} hóa đơn cũ hơn 3 tháng VẪN có trong danh sách — chính chỗ "
          f"này là lỗi đã lọt ra người dùng ở MT2-X")
    bad += not ok

    ok = [r["name"] for r in l["rows"]] == ["SI-CU", "SI-MOI"]
    print(f"  {'✅' if ok else '❌'} và chỉ đúng hai tờ chưa xuất, không lẫn tờ đã xuất")
    bad += not ok

    s_all = md.get_due_summary(as_of=AS_OF)
    ok = round(s_all["total"], 2) == 420.0 and round(s["total"], 2) == 320.0
    print(f"  {'✅' if ok else '❌'} bỏ lọc thì tổng quay về đủ ({s_all['total']:,.0f}đ) — "
          f"bộ lọc không dính lại")
    bad += not ok

    # Vì sao KHÔNG được quay lại dùng `mt.get_invoices` cho phần chênh này.
    mtsrc2 = open(os.path.join(rc.REPO, "ketoan/api/mt.py"), encoding="utf-8").read()
    pg2 = mtsrc2.split("def _invoice_page")[1].split("\ndef ")[0]
    fetch_src = open(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"),
                     encoding="utf-8").read().split("def _fetch")[1].split("\ndef ")[0]
    ok = ("posting_date BETWEEN" in pg2) and ("posting_date BETWEEN" not in fetch_src)
    print(f"  {'✅' if ok else '❌'} hai đường VẪN khác nhau về phạm vi ngày "
          f"(`_invoice_page` chặn khoảng, `_fetch` không) — nên phần chênh phải đi màn công nợ")
    bad += not ok

    # ── 9b. KHÁCH CHƯA GÁN CHUỖI phải nằm TRONG tổng của bảng chuỗi ──────
    #
    # `mt_hub.get_board` chỉ lặp qua MT_CHAINS. Khách chưa khai `custom_mt_chain`
    # (hoặc bị gán hai chuỗi nên bản đồ cố ý trả None) rơi vào nhóm chuỗi rỗng.
    # Để nhóm đó ngoài `totals` là hỏng theo kiểu khó thấy nhất: thẻ cộng 100đ,
    # bấm vào mở công nợ KHÔNG lọc chuỗi nên ra 1.000đ.
    print("-" * 82)
    hub = importlib.import_module("ketoan.api.mt_hub")
    hub._capabilities = lambda: {}
    hub._company = lambda company=None: "HGC"
    md._fetch = lambda company, as_of, chain=None, customer=None, search=None: [
        dict(_r("SI-WIN", 100, 0, "2026-05-01")),
        dict(_r("SI-LAC", 900, 0, "2026-05-01"), chain=""),
    ]
    # `_enrich` gán lại chuỗi bằng bản đồ khách->chuỗi; giả lập đúng một khách
    # thuộc Win, khách còn lại không thuộc đâu.
    hub_mt = importlib.import_module("ketoan.api.mt")
    hub_mt._customer_chain_map = lambda: ({"KWIN": "WinCommerce"}, [])
    md._customer_chain_map = hub_mt._customer_chain_map
    md._fetch = lambda company, as_of, chain=None, customer=None, search=None: [
        dict(_r("SI-WIN", 100, 0, "2026-05-01"), customer="KWIN"),
        dict(_r("SI-LAC", 900, 0, "2026-05-01"), customer="KLAC"),
    ]
    board = hub.get_board()
    tt = board["totals"]
    ok = round(tt["debt"], 2) == 1000.0
    print(f"  {'✅' if ok else '❌'} tổng của bảng chuỗi = {tt['debt']:,.0f}đ, tức CÓ cộng 900đ "
          f"của khách chưa gán chuỗi (danh sách bấm ra cũng gồm nó)")
    bad += not ok

    ok = round(tt["debt_no_einv"], 2) == 1000.0 and tt["debt_no_einv_count"] == 2
    print(f"  {'✅' if ok else '❌'} vế 'chưa xuất HĐĐT' cũng cộng đủ ({tt['debt_no_einv']:,.0f}đ "
          f"/ {tt['debt_no_einv_count']} HĐ)")
    bad += not ok

    u = board["unassigned_debt"] or {}
    ok = bool(u) and round(u["debt"], 2) == 900.0 and u.get("unassigned") is True
    print(f"  {'✅' if ok else '❌'} và nhóm đó hiện thành MỘT DÒNG riêng để còn đi gán chuỗi")
    bad += not ok

    rows_sum = round(sum(c["debt"] for c in board["chains"])
                     + (u.get("debt") or 0), 2)
    ok = rows_sum == round(tt["debt"], 2)
    print(f"  {'✅' if ok else '❌'} các dòng của bảng cộng lại ĐÚNG bằng con số ghi ngay trên đầu "
          f"({rows_sum:,.0f} = {tt['debt']:,.0f})")
    bad += not ok

    md._fetch = lambda company, as_of, chain=None, customer=None, search=None: []
    b0 = hub.get_board()
    ok = b0["totals"]["debt_einv_known"] is True and b0["unassigned_debt"] is None
    print(f"  {'✅' if ok else '❌'} site SẠCH NỢ mà vẫn có ô HĐĐT -> `debt_einv_known` True "
          f"(không đi bảo kế toán chạy migrate), và không mọc dòng rỗng")
    bad += not ok

    # ── 9c. HẠN XUẤT HÓA ĐƠN RIÊNG CỦA CHUỖI ────────────────────────────
    #
    # Nguồn: SOP §5 (Lịch tháng) — "Ngày 1–5: Xuất nốt toàn bộ HĐ hàng tháng
    # trước cho Emart (deadline ngày 5)". Chỉ Emart có; bảy chuỗi còn lại KHÔNG
    # có hạn quy định và tuyệt đối không được bịa ra một cái nghe hợp lý.
    print("-" * 82)
    DL = [  # (hôm nay, tờ cũ nhất, vỡ hạn?, vì sao)
        ("2026-08-28", "2026-07-31", True,  "HĐ tháng 7 hạn 05/08 — đã qua"),
        ("2026-08-05", "2026-07-31", False, "đúng ngày 5 thì VẪN còn hạn"),
        ("2026-08-06", "2026-07-31", True,  "quá đúng một ngày"),
        ("2026-08-28", "2026-08-01", False, "HĐ tháng 8 hạn 05/09"),
        ("2026-01-03", "2025-12-20", False, "vắt năm, còn trong ân hạn"),
        ("2026-01-06", "2025-12-20", True,  "vắt năm, đã vỡ hạn"),
    ]
    miss = [(t, o, w) for t, o, w, _y in DL
            if (hub._einv_deadline("Emart", o, t) or {}).get("breached") != w]
    ok = not miss
    print(f"  {'✅' if ok else '❌'} luật hạn Emart đúng cả 6 mốc (kể cả đúng-ngày-5 và vắt năm)"
          f"{'' if ok else ' — sai: ' + str(miss)}")
    bad += not ok

    ok = hub._einv_deadline("WinCommerce", "2020-01-01", "2026-08-28") is None
    print(f"  {'✅' if ok else '❌'} chuỗi KHÔNG có hạn khai -> None. Bịa hạn cho 7 chuỗi còn lại "
          f"là dạy kế toán đọc lướt qua cả cột cảnh báo")
    bad += not ok

    ok = hub._einv_deadline("Emart", None, "2026-08-28") is None
    print(f"  {'✅' if ok else '❌'} xuất hết rồi -> không kêu")
    bad += not ok

    ok = set(hub.EINV_DEADLINE) == {"Emart"}
    print(f"  {'✅' if ok else '❌'} bảng hạn chỉ chép thứ CÓ trong SOP — thêm chuỗi vào đây phải "
          f"kèm trích dẫn văn bản, không thì bộ kiểm này chặn")
    bad += not ok

    # BỘ GIẢ PHẢI ĐÚNG, nếu không mọi phép trên đều vô nghĩa mà vẫn báo ĐẠT.
    # `add_months` từng được giả bằng `lambda d, n: _gd(d)` — trả về chính ngày
    # đưa vào, bỏ hẳn `n`. Luật hạn khi đó chấm "vỡ hạn" cho đúng những trường
    # hợp còn trong hạn, và lỗi trông y như lỗi của code.
    from frappe.utils import add_months as _am
    fixt = [("2026-08-03", -1, "2026-07-03"), ("2026-01-03", -1, "2025-12-03"),
            ("2026-03-31", -1, "2026-02-28"), ("2024-03-31", -1, "2024-02-29"),
            ("2026-11-15", 2, "2027-01-15")]
    wrong = [(d, n, str(_am(d, n)), w) for d, n, w in fixt if str(_am(d, n)) != w]
    ok = not wrong
    print(f"  {'✅' if ok else '❌'} bộ giả `add_months` cộng tháng THẬT (vắt năm, kẹp cuối tháng, "
          f"năm nhuận){'' if ok else ' — sai: ' + str(wrong)}")
    bad += not ok

    # ── 10. Giao diện ───────────────────────────────────────────────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    ok = "twoBooks" in js and "debt_no_einv" in js
    print(f"  {'✅' if ok else '❌'} bảng điều khiển MT bày HAI số cạnh nhau")
    bad += not ok

    ok = "twoBooksRow" in js and "debt_einv_count" in js and "debt_no_einv_oldest" in js
    print(f"  {'✅' if ok else '❌'} và tách CHI TIẾT THEO TỪNG CHUỖI, kèm số tờ và ngày tờ cũ nhất")
    bad += not ok

    seg = js.split("function openDueEinv")[1].split("\nfunction ")[0]
    ok = ('"cong-no"' in seg and '"g-cong-no"' in seg
          and "state.bucket" not in seg and "state.einvoice" not in seg)
    print(f"  {'✅' if ok else '❌'} bấm vào phần chênh đi màn CÔNG NỢ ĐẾN HẠN (cùng hàm với con "
          f"số), KHÔNG đi danh sách hóa đơn bị chặn khoảng ngày")
    bad += not ok

    ok = 'data-einv="chua"' in js and "Đang lọc:" in js and 'id="dd-einv-clear"' in js
    print(f"  {'✅' if ok else '❌'} màn công nợ nói RA là đang lọc, và tắt được ngay tại chỗ")
    bad += not ok

    ok = "if (!t.debt_einv_known)" in js
    print(f"  {'✅' if ok else '❌'} chưa có ô số HĐĐT -> nói 'chưa tách được', KHÔNG vẽ 0đ")
    bad += not ok

    ok = "unassigned_debt" in js and "(chưa gán chuỗi)" in js
    print(f"  {'✅' if ok else '❌'} nợ của khách CHƯA GÁN CHUỖI hiện thành MỘT DÒNG của bảng — "
          f"để nó ngoài bảng thì các dòng không cộng lại bằng con số ghi trên đầu")
    bad += not ok

    # Bàn làm việc của MỘT chuỗi cũng phải bày hai con số CẠNH NHAU.
    #
    # Việc đi đòi và việc xuất nốt hóa đơn đều làm THEO CHUỖI. Bắt kế toán quay
    # về bảng tổng để đọc con số của chuỗi mình đang làm là bắt họ nhớ một con
    # số qua hai màn hình — và nhớ nhầm thì không chỗ nào bắt được.
    # Soi TRONG `chainShell`, không soi cả file.
    #
    # Bản đầu khẳng định `"twoBooksChain(c)" in js` — và nó ĐẠT ngay cả khi đã
    # gỡ chỗ gọi, vì chuỗi đó cũng nằm trong chính dòng `function
    # twoBooksChain(c) {`. Phép kiểm dò chuỗi trên cả file luôn có nguy cơ này:
    # nó thấy ĐỊNH NGHĨA và tưởng là CHỖ DÙNG.
    ok = rc.js_calls(js, "chainShell", "twoBooksChain")
    print(f"  {'✅' if ok else '❌'} `chainShell` GỌI `twoBooksChain` — bàn làm việc của một chuỗi "
          f"cũng bày hai cuốn sổ cạnh nhau")
    bad += not ok

    seg_cb = js.split("function twoBooksChain")[1].split("\n// Hạn xuất")[0]
    ok = "formatVND(c.debt)" in seg_cb
    print(f"  {'✅' if ok else '❌'} và in ra TỔNG mà hai vế cộng lại — không nói tổng thì hai "
          f"con số cạnh nhau thành hai nguồn sự thật")
    bad += not ok

    ok = "!c.debt_einv_known" in seg_cb
    print(f"  {'✅' if ok else '❌'} chuỗi chưa biết -> nói 'chưa tách được', KHÔNG vẽ 0đ")
    bad += not ok

    ok = ('#cb-open"' in js or "'#cb-open'" in js) and "openDueEinv(container, state, state.chain" in js
    print(f"  {'✅' if ok else '❌'} bấm vào mở đúng danh sách của CHÍNH chuỗi đang xem")
    bad += not ok

    ok = "deadlineNote" in js and "einv_deadline" in js
    print(f"  {'✅' if ok else '❌'} hạn riêng của chuỗi hiện ngay trên con số 'chưa đòi được'")
    bad += not ok

    ok = "state.dueAsOf" in seg
    print(f"  {'✅' if ok else '❌'} bấm vào thì XÓA ngày 'tính đến' cũ — bảng chuỗi luôn tính đến "
          f"hôm nay, màn công nợ thì nhớ ngày kế toán chọn lần trước")
    bad += not ok

    # ── 11. NÚT CHẾT — cả lớp lỗi mà bộ kiểm CŨ đã cấp ✅ nhầm ───────────
    #
    # Bản MT2-X gắn `#tb-open` rồi gọi `loadTab(container, state)`. Nhưng
    # `loadTab` bắt đầu bằng `querySelector("#mt-body"); if (!body) return;`,
    # mà `boardShell` KHÔNG hề có `#mt-body` — chỉ `chainShell` và `globalShell`
    # có. Nút bấm không làm gì cả, và bộ kiểm cũ vẫn ĐẠT vì nó chỉ dò xem chuỗi
    # `id="tb-open"` có trong file không.
    #
    # Ở tầng bảng chuỗi, đổi màn hình PHẢI đi qua `paint()`.
    print("-" * 82)
    shell = js.split("function boardShell")[1].split("\n// Một thẻ chuỗi")[0]
    ok = "mt-body" not in shell
    print(f"  {'✅' if ok else '❌'} `boardShell` vẫn KHÔNG có `#mt-body` (tiền đề của phép dưới)")
    bad += not ok

    bindb = js.split("function bindBoard")[1].split("\n// Mở danh sách")[0]
    ok = "loadTab(" not in bindb and "paint(" in js.split("function openDueEinv")[1][:900]
    print(f"  {'✅' if ok else '❌'} không handler nào của bảng chuỗi gọi `loadTab` — ở tầng này "
          f"`loadTab` thoát ngay dòng đầu, tức NÚT CHẾT mà không báo lỗi gì")
    bad += not ok

    i_bucket = js.index("state.bucket = b.dataset.payview;")
    ok = 'state.einvoice = "";' in js[i_bucket:i_bucket + 400]
    print(f"  {'✅' if ok else '❌'} đổi rổ thì BỎ lọc — giữ lại là kế toán đọc 'rổ đã thu đủ' "
          f"mà thật ra đang xem một lát cắt của nó")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — hai vế luôn cộng lại đúng tổng ở CẢ mức toàn kênh lẫn từng chuỗi, "
          "luật 'đã xuất HĐĐT' chỉ có MỘT định nghĩa, và con số bấm vào ra ĐÚNG tập đã đếm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
