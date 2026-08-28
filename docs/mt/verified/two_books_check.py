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
    mtsrc = open(os.path.join(rc.REPO, "ketoan/api/mt.py"), encoding="utf-8").read()
    n_mt = mtsrc.count('"vn_einvoice_number"')
    ok = not stray and n_mt == 1
    print(f"  {'✅' if ok else '❌'} ô cũ `vn_einvoice_number` chỉ xuất hiện ĐÚNG MỘT LẦN trong "
          f"`mt.py` (hằng số của `einvoice_issued_expr`), không rải sang module công nợ nào "
          f"{'' if ok else '— ' + ', '.join(stray or []) + f' / mt.py x{n_mt}'}")
    bad += not ok

    # ── 7. Giao diện: bày hai số, và bấm được vào phần chênh ─────────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    ok = "twoBooks" in js and "debt_no_einv" in js
    print(f"  {'✅' if ok else '❌'} bảng điều khiển MT bày HAI số cạnh nhau")
    bad += not ok

    ok = 'id="tb-open"' in js and 'state.einvoice = "chua"' in js
    print(f"  {'✅' if ok else '❌'} bấm vào phần chênh MỞ ĐƯỢC danh sách — con số không mở ra "
          f"được việc phải làm thì chỉ để nhìn")
    bad += not ok

    ok = 'id="einv-clear"' in js and "Đang lọc:" in js
    print(f"  {'✅' if ok else '❌'} khi đang lọc thì NÓI RA và tắt được ngay tại chỗ")
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
    print("KẾT QUẢ: ĐẠT — hai vế luôn cộng lại đúng tổng, luật 'đã xuất HĐĐT' chỉ có MỘT "
          "định nghĩa và hỏi cả hai ô, phần chênh bấm vào xử lý được")
    return 0


if __name__ == "__main__":
    sys.exit(main())
