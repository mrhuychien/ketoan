"""Kiểm BỘ LỌC CHUỖI — vào một chuỗi thì chỉ được thấy chuỗi đó.

    python3 docs/mt/verified/chain_filter_check.py

Bộ kiểm này sinh ra từ một lỗi thật, nhìn thấy bằng mắt trên site: vào bàn làm
việc của **Central Retail** mà danh sách hóa đơn hiện cả AEON, Winmart, Mega
Market.

Nguyên nhân: `mt.get_invoices` KHAI tham số `chain` và chỉ chuyển nó xuống nhánh
khấu trừ; ba rổ hóa đơn còn lại gọi `_invoice_page(...)` không truyền, mà hàm đó
thậm chí không có tham số ấy. Tham số NHẬN RỒI BỎ QUA — không lỗi, không cảnh
báo, người gọi tưởng đã lọc.

════════════════════════════════════════════════════════════════════════════
BA ĐIỀU PHÉP KIỂM NÀY KHÓA LẠI
════════════════════════════════════════════════════════════════════════════

1. LỌC THẬT SỰ LỌC. Không chỉ kiểm "hàm nhận tham số" — kiểm câu SQL PHÁT RA có
   mệnh đề ràng buộc đúng khách của chuỗi đó không.

2. RỖNG LÀ RỖNG. Chuỗi chưa có khách nào -> mệnh đề `1 = 0`. Bỏ qua bộ lọc khi
   danh sách rỗng chính là cách lỗi trên tái sinh: "chuỗi X" hiện toàn bộ mọi
   chuỗi.

3. MỘT QUY TẮC DUY NHẤT. "Khách nào thuộc chuỗi nào" từng có HAI cách tính:
   `mt._customer_chain_map()` (field khai thắng, không khai thì suy từ bảng kê)
   và lọc thẳng `c.custom_mt_chain` (chỉ field khai). Khách đã có bảng kê
   WinCommerce mà chưa kịp khai field thì hiện là "WinCommerce" ở màn công nợ
   nhưng BIẾN MẤT khỏi danh sách gom hồ sơ Win — mà đó là cái làm hồ sơ nộp tiền.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

COMPANY = "HGC"

# Bản đồ khách -> chuỗi dùng cho mọi phép dưới đây.
#   · KH-LOTTE-A/B : khai tường minh
#   · KH-LOTTE-C   : CHƯA khai field, chỉ suy được từ bảng kê -> quy tắc hẹp bỏ sót
#   · KH-AEON      : chuỗi khác, không được lọt vào
CHAIN_MAP = {
    "KH-LOTTE-A": "LOTTE",
    "KH-LOTTE-B": "LOTTE",
    "KH-LOTTE-C": "LOTTE",
    "KH-AEON": "AEON",
    "KH-WIN": "WinCommerce",
}


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


class Spy:
    """Ghi lại mọi câu SQL phát ra cùng tham số ràng buộc."""

    def __init__(self):
        self.calls = []

    def __call__(self, query, values=None, **kw):
        q = " ".join(str(query).split())
        self.calls.append((q, dict(values or {})))
        if q.upper().startswith("SELECT COUNT"):
            return [[0]]
        return []

    def last(self, must_contain):
        for q, v in reversed(self.calls):
            if must_contain in q:
                return q, v
        raise AssertionError("không có câu SQL nào chứa %r" % must_contain)

    def bound_customers(self, q, v):
        """Tên khách thật sự được ràng buộc vào mệnh đề IN của câu này.

        KHÔNG cắt chuỗi trong ngoặc bằng `[^)]*`: placeholder `%(cc0)s` có sẵn
        dấu `)` nên regex đó dừng giữa chừng và luôn trả rỗng — phép kiểm sẽ
        báo hỏng cả khi bộ lọc chạy đúng.
        """
        if "customer IN (" not in q:
            return None
        keys = sorted((k for k in v if re.fullmatch(r"cc\d+", k)),
                      key=lambda k: int(k[2:]))
        return sorted(v[k] for k in keys)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.db.table_exists = lambda dt: True
    frappe.db.has_column = lambda dt, col: True
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.get_cached_doc = lambda *a, **k: _D(
        npp_customer_group="NPP", mt_customer_group="MT", default_company=COMPANY)

    class _Meta:
        def has_field(self, f):
            return True

    frappe.get_meta = lambda *a, **k: _Meta()

    mt = importlib.import_module("ketoan.api.mt")
    mt._company = lambda company=None: COMPANY
    mt._customer_chain_map = lambda: (dict(CHAIN_MAP), [])

    print("=" * 78)
    print("KIỂM BỘ LỌC CHUỖI")
    print("=" * 78)
    bad = 0

    want_lotte = sorted(k for k, v in CHAIN_MAP.items() if v == "LOTTE")

    # ── 1. Ba rổ HÓA ĐƠN đều lọc theo chuỗi ──────────────────────────────
    for bucket in ("chua_thanh_toan", "da_thanh_toan", "tat_ca"):
        spy = Spy()
        frappe.db.sql = spy
        mt.get_invoices(bucket, chain="LOTTE")
        q, v = spy.last("tabSales Invoice")
        got = spy.bound_customers(q, v)
        ok = got == want_lotte
        print(f"  {'✅' if ok else '❌'} rổ `{bucket}` lọc đúng {len(want_lotte)} khách của "
              f"LOTTE -> {got}")
        if not ok and got is None:
            print("       └─ câu SQL KHÔNG có mệnh đề lọc khách nào — "
                  "tham số `chain` bị bỏ qua")
        bad += not ok

    # ── 2. Rổ KHẤU TRỪ lọc theo chuỗi của BẢNG KÊ ────────────────────────
    print("-" * 78)
    spy = Spy()
    frappe.db.sql = spy
    mt.get_invoices("chiet_khau", chain="LOTTE")
    q, v = spy.last("tabMT Payment Advice Line")
    ok = "a.chain = %(chain)s" in q and v.get("chain") == "LOTTE"
    print(f"  {'✅' if ok else '❌'} rổ `chiet_khau` lọc theo chuỗi ghi trên BẢNG KÊ "
          f"(dòng khấu trừ thuộc về bảng kê, không thuộc hóa đơn)")
    bad += not ok

    # ── 3. RỖNG LÀ RỖNG, không phải TẤT CẢ ───────────────────────────────
    print("-" * 78)
    spy = Spy()
    frappe.db.sql = spy
    mt.get_invoices("tat_ca", chain="Chuỗi Chưa Có Khách Nào")
    q, _v = spy.last("tabSales Invoice")
    ok = "1 = 0" in q
    print(f"  {'✅' if ok else '❌'} chuỗi CHƯA có khách nào -> mệnh đề `1 = 0` "
          f"(rỗng nghĩa là KHÔNG GÌ CẢ)")
    if not ok:
        print("       └─ bỏ qua bộ lọc khi rỗng = màn hình 'chuỗi X' hiện TOÀN BỘ mọi chuỗi")
    bad += not ok

    # Không truyền chuỗi (màn liên chuỗi) thì KHÔNG được tự thêm `1 = 0`.
    spy = Spy()
    frappe.db.sql = spy
    mt.get_invoices("tat_ca")
    q, _v = spy.last("tabSales Invoice")
    ok = "1 = 0" not in q and "customer IN" not in q
    print(f"  {'✅' if ok else '❌'} KHÔNG chọn chuỗi (màn liên chuỗi) -> không lọc khách, "
          f"cũng không chặn sạch")
    bad += not ok

    # ── 4. Không rò chuỗi khác vào ───────────────────────────────────────
    print("-" * 78)
    spy = Spy()
    frappe.db.sql = spy
    mt.get_invoices("tat_ca", chain="AEON")
    q, v = spy.last("tabSales Invoice")
    got = spy.bound_customers(q, v) or []
    leak = [c for c in got if CHAIN_MAP.get(c) != "AEON"]
    ok = got == ["KH-AEON"] and not leak
    print(f"  {'✅' if ok else '❌'} lọc AEON -> đúng {got}, không rò khách chuỗi khác")
    bad += not ok

    # ── 5. MỘT quy tắc duy nhất, dùng chung ba nơi ───────────────────────
    print("-" * 78)
    ok = mt.chain_customers("LOTTE") == want_lotte
    print(f"  {'✅' if ok else '❌'} `mt.chain_customers('LOTTE')` -> {want_lotte}")
    bad += not ok

    # Hồ sơ Win phải dùng CHUNG bản đồ, không phải chỉ field khai.
    mw = importlib.import_module("ketoan.api.mt_win")
    got = mw._win_customers(COMPANY)
    ok = got == ["KH-WIN"]
    print(f"  {'✅' if ok else '❌'} hồ sơ Win dùng chung bản đồ -> {got}")
    bad += not ok

    src_win = open(os.path.join(rc.REPO, "ketoan/api/mt_win.py"), encoding="utf-8").read()
    ok = 'filters={"custom_mt_chain"' not in src_win
    print(f"  {'✅' if ok else '❌'} `mt_win` KHÔNG còn tự lọc `custom_mt_chain` "
          f"(quy tắc hẹp hơn, bỏ sót khách chưa khai field)")
    bad += not ok

    # Công nợ cũng phải dùng chung.
    md = importlib.import_module("ketoan.api.mt_debt")
    md._company = lambda company=None: COMPANY
    spy = Spy()
    frappe.db.sql = spy
    md.get_due_invoices(chain="LOTTE", as_of="2026-08-20")
    q, v = spy.last("tabSales Invoice")
    got = spy.bound_customers(q, v)
    ok = got == want_lotte
    print(f"  {'✅' if ok else '❌'} công nợ đến hạn lọc đúng {len(want_lotte)} khách LOTTE "
          f"-> {got}")
    bad += not ok

    src_debt = open(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"), encoding="utf-8").read()
    ok = "c.custom_mt_chain = %(chain)s" not in src_debt
    print(f"  {'✅' if ok else '❌'} `mt_debt` KHÔNG còn lọc thẳng `c.custom_mt_chain`")
    bad += not ok

    # ── 6. Gộp theo chuỗi cũng theo bản đồ, không theo cột thô ───────────
    print("-" * 78)
    rows = [
        _D(name="SI-1", customer="KH-LOTTE-C", customer_name="C", posting_date="2026-05-01",
           due_date=None, grand_total=9_000_000, chain="", credit_days=45, paid=0,
           clawed_back=0, paid_review=0, last_payment_date=None, remaining=9_000_000),
    ]
    out = md._enrich(rows, "2026-08-20")
    ok = out[0]["chain"] == "LOTTE"
    print(f"  {'✅' if ok else '❌'} hóa đơn của khách CHƯA khai field vẫn được gộp vào "
          f"LOTTE (cột thô rỗng, bản đồ suy ra) -> {out[0]['chain']!r}")
    if not ok:
        print("       └─ lọc và gộp chạy hai quy tắc: hóa đơn lọt bộ lọc rồi rơi vào")
        print("          nhóm chuỗi rỗng khi gộp — tiền biến khỏi mọi thẻ chuỗi")
    bad += not ok

    s = md._rollup(out)
    ok = [c["chain"] for c in s["chains"]] == ["LOTTE"]
    print(f"  {'✅' if ok else '❌'} bảng gộp theo chuỗi ra {[c['chain'] for c in s['chains']]}")
    bad += not ok

    # ── 6b. Lập chỉ mục hóa đơn cho BKCK cũng phải giới hạn theo chuỗi ───
    print("-" * 78)
    mdis = importlib.import_module("ketoan.api.mt_discount")
    spy = Spy()
    frappe.db.sql = spy
    mdis._si_index(COMPANY, "LOTTE")
    q, v = spy.last("tabSales Invoice")
    got = spy.bound_customers(q, v)
    ok = got == want_lotte
    print(f"  {'✅' if ok else '❌'} chỉ mục hóa đơn của bảng kê chiết khấu chỉ lấy khách "
          f"LOTTE -> {got}")
    if got is None:
        print("       └─ lấy hóa đơn MỌI chuỗi: chỉ mục khóa theo SỐ hóa đơn (không kèm")
        print("          ký hiệu) nên dòng BKCK có thể nối vào hóa đơn của chuỗi khác")
    bad += not ok

    # ── 7. Không hàm nào NHẬN `chain` rồi bỏ quên ────────────────────────
    print("-" * 78)
    import ast

    leaks = []
    for fname in ("mt.py", "mt_debt.py", "mt_je.py", "mt_discount.py", "mt_store.py",
                  "mt_hub.py", "mt_win.py", "mt_advice.py", "mt_discount_read.py"):
        path = os.path.join(rc.REPO, "ketoan/api", fname)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            args = [a.arg for a in fn.args.args]
            if "chain" not in args:
                continue
            body = ast.dump(ast.Module(body=fn.body, type_ignores=[]))
            # `chain` phải xuất hiện trong THÂN hàm, không chỉ ở chữ ký.
            if "'chain'" not in body and '"chain"' not in body and "id='chain'" not in body:
                leaks.append("%s::%s" % (fname, fn.name))
    ok = not leaks
    print(f"  {'✅' if ok else '❌'} không hàm nào nhận `chain` rồi không dùng tới")
    for x in leaks:
        print(f"       └─ {x}")
    bad += not ok

    print("=" * 78)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — vào một chuỗi chỉ thấy chuỗi đó, rỗng là rỗng, "
          "một quy tắc dùng chung")
    return 0


if __name__ == "__main__":
    sys.exit(main())
