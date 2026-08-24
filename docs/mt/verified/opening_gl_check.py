#!/usr/bin/env python3
"""Kiểm ĐỐI CHIẾU số dư đầu kỳ Excel ↔ SỔ CÁI ERPNext (MT2-T).

Một màn hình đối chiếu hỏng theo kiểu riêng của nó: nó KHÔNG ném lỗi. Nó in ra
hai con số và một chỗ lệch, kế toán đọc, tin, rồi chốt số dư đầu kỳ. Nên bộ kiểm
này không soi "có chạy không" mà soi bốn thứ:

  1. **Cầu nối phải CỘNG ĐỦ.** Bốn khoản mục cộng lại đúng bằng chỗ lệch, số dư
     còn lại đúng 0 — và đúng 0 ở mọi hình dạng dữ liệu, kể cả các hình dạng cố
     ý dựng ra để phá. Một cầu nối "gần đúng" tệ hơn không có: nó khiến người ta
     tin rằng đã giải thích xong.

  2. **So đúng vế.** File cộng cả đơn đã giao CHƯA xuất hóa đơn vào "Số còn nợ"
     (46.665.180đ trên file WinCommerce mẫu). Chưa có hóa đơn thì không có bút
     toán — so `opening_debt` với sổ cái là chắc chắn lệch đúng bằng số đó, mỗi
     lần, mãi mãi.

  3. **KHÔNG áp luật tất toán vào vế ERPNext.** Bản đã chốt làm mọi hóa đơn
     ngoài danh sách rơi khỏi rổ nợ. Áp luật rồi mới so thì khoản (2) luôn bằng
     0, cầu nối tự khớp một cách vô nghĩa, và ta mất đúng con số quý nhất: số
     tiền mà việc chốt đã lấy đi.

  4. **Hai màn hình một con số.** Khoản (2) ở đây và "chốt xong X đồng rời khỏi
     công nợ" ở màn hình chốt phải là CÙNG một biểu thức. Lệch nhau thì kế toán
     đối chiếu hai màn hình ra hai số và không biết tin cái nào.

Chạy KHÔNG cần bench — stub frappe của `regression_check`. Không câu SQL nào
chạy thật.
"""

import ast
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


# ── thế giới giả ───────────────────────────────────────────────────────────
# Chuỗi TEST có hai pháp nhân, đúng hình dạng thật của Central Retail.
CUSTOMERS = ["CUS-EB-3003172", "CUS-EB-3006634"]


class World:
    """Khai bằng DỮ LIỆU, không mock từng lời gọi.

    `gl`      — số dư sổ cái từng khách tại ngày chốt
    `basket`  — rổ hóa đơn từng khách: (đã nối, chưa nối, n_đã_nối, n_chưa_nối)
    """

    def __init__(self, gl=None, basket=None):
        self.gl = dict(gl if gl is not None else
                       {"CUS-EB-3003172": 900_000_000.0, "CUS-EB-3006634": 300_000_000.0})
        self.basket = dict(basket if basket is not None else {
            "CUS-EB-3003172": (500_000_000.0, 380_000_000.0, 40, 210),
            "CUS-EB-3006634": (200_000_000.0, 90_000_000.0, 12, 60),
        })
        self.queries = []

    def sql(self, query, params=None, as_dict=False, **kw):
        self.queries.append(query)
        if "tabGL Entry" in query:
            return [_D(customer=c, bal=v) for c, v in self.gl.items()]
        # Dấu hiệu là tên bảng có BACKTICK — `tabSales Invoice`. Nhận diện bằng
        # chuỗi không backtick thì stub im lặng trả rỗng và cả bộ kiểm chạy trên
        # một cái rổ hóa đơn trống, xanh hết mà chẳng kiểm gì.
        if "`tabSales Invoice`" in query:
            return [_D(customer=c, customer_name="Tên " + c,
                       listed=b[0], not_listed=b[1], n_listed=b[2], n_not_listed=b[3])
                    for c, b in self.basket.items()]
        return []


def make_doc(lines=None, matches=None, **kw):
    """Bản số dư đầu kỳ giả. `lines` là list dict, `matches` là list line_no."""
    lines = lines or []
    for i, l in enumerate(lines, start=1):
        l.setdefault("idx", i)
    d = _D(
        name="MTOB-TEST", chain="TEST", company="HGC", status="Nháp",
        cutover_date="2026-07-31", golive_date="2025-01-01",
        opening_debt_gross=1_300_000_000.0, deduction_open=100_000_000.0,
        opening_debt=1_200_000_000.0, no_invoice_amount=46_665_180.0,
        debt_carried=1_153_334_820.0,
        lines=[_D(l) for l in lines],
        matches=[_D(line_no=n, sales_invoice="HD-%04d" % n) for n in (matches or [])],
    )
    d.update(kw)
    return d


def install(world):
    import frappe

    frappe.db.sql = world.sql
    frappe.db.table_exists = lambda *a, **k: True
    frappe.db.get_value = lambda *a, **k: None
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.get_cached_doc = lambda dt: _D(receivable_account="131 - HGC",
                                          mt_customer_group="MT", npp_customer_group="NPP")
    frappe.get_single = frappe.get_cached_doc
    return frappe


def line(kind, remaining, resolution=None):
    return {"kind": kind, "remaining": remaining, "resolution": resolution}


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    w = World()
    install(w)

    gl = importlib.import_module("ketoan.api.mt_opening_gl")
    ob = importlib.import_module("ketoan.mt.doctype.mt_opening_balance.mt_opening_balance")
    gl.chain_customers = lambda ch: list(CUSTOMERS)

    print("=" * 82)
    print("KIỂM ĐỐI CHIẾU SỐ DƯ ĐẦU KỲ EXCEL ↔ SỔ CÁI ERPNEXT")
    print("=" * 82)
    bad = 0

    # ── 1. Cầu nối phải CỘNG ĐỦ, ở mọi hình dạng dữ liệu ─────────────────
    #
    # Bảy hình dạng, chọn theo các kiểu hỏng khác nhau chứ không phải cho nhiều.
    shapes = [
        ("thường: có nối, có treo, có trước go-live", World(), make_doc(
            lines=[line(ob.KIND_IN_ERP, 700_000_000.0),
                   line(ob.KIND_IN_ERP, 300_000_000.0),
                   line(ob.KIND_PRE_GOLIVE, 100_000_000.0),
                   line(ob.KIND_NO_INVOICE, 46_665_180.0),
                   line(ob.KIND_IN_ERP, 6_669_640.0, ob.RESOLUTION_SKIP)],
            matches=[1])),
        ("không nối được dòng nào", World(), make_doc(
            lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)])),
        ("nối hết mọi dòng", World(), make_doc(
            lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)], matches=[1])),
        ("sổ cái ÂM (khách trả trước)", World(gl={"CUS-EB-3003172": -50_000_000.0,
                                                  "CUS-EB-3006634": 0.0}),
         make_doc(lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)], matches=[1])),
        ("ERPNext trống trơn (chưa có hóa đơn nào)", World(gl={}, basket={}),
         make_doc(lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)])),
        ("Excel bằng 0, ERPNext có nợ", World(), make_doc(
            lines=[], opening_debt_gross=0.0, deduction_open=0.0, opening_debt=0.0,
            no_invoice_amount=0.0, debt_carried=0.0)),
        ("bản ĐÃ CHỐT", World(), make_doc(
            lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)], matches=[1],
            status=ob.STATUS_FINAL)),
    ]
    for label, wx, doc in shapes:
        install(wx)
        b = gl.build_bridge("HGC", doc)
        ok = b["balanced"] and abs(b["residual"]) < 0.01
        tail = "" if ok else " — CÒN DƯ {:,.2f}".format(b["residual"])
        print(f"  {'✅' if ok else '❌'} cầu nối cộng đủ — {label}{tail}")
        bad += not ok

        total = round(sum(x["amount"] for x in b["items"]), 2)
        ok = abs(total - b["diff"]) < 0.01
        print(f"     {'✅' if ok else '❌'} tổng bốn khoản = chỗ lệch ({total:,.0f} vs {b['diff']:,.0f})")
        bad += not ok

    # ── 2. So với `debt_carried`, KHÔNG phải `opening_debt` ──────────────
    print("-" * 82)
    install(World())
    doc = make_doc(lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)], matches=[1])
    b = gl.build_bridge("HGC", doc)
    ok = abs(b["diff"] - (b["erp"]["gl"] - doc.debt_carried)) < 0.01
    print(f"  {'✅' if ok else '❌'} vế Excel là CÔNG NỢ MANG SANG, không phải nợ ròng")
    bad += not ok

    ok = abs(b["diff"] - (b["erp"]["gl"] - doc.opening_debt)) > 1000
    print(f"  {'✅' if ok else '❌'} và hai cách đó KHÁC nhau thật ({doc.no_invoice_amount:,.0f}đ) — "
          f"phép kiểm trên không phải trùng hợp")
    bad += not ok

    ok = abs(b["excel"]["no_invoice_amount"] - doc.no_invoice_amount) < 0.01
    print(f"  {'✅' if ok else '❌'} vẫn bày `đơn chưa xuất hóa đơn` ra màn hình chứ không lặng "
          f"lẽ trừ đi — số của file phải đối chiếu ngược lại được")
    bad += not ok

    # File tự khớp: tổng các dòng còn nợ phải ra dòng TỔNG CỘNG in trong file.
    install(World())
    good = make_doc(lines=[line(ob.KIND_IN_ERP, 1_000_000_000.0),
                           line(ob.KIND_PRE_GOLIVE, 200_000_000.0),
                           line(ob.KIND_NO_INVOICE, 46_665_180.0),
                           line(ob.KIND_IN_ERP, 53_334_820.0)],
                    matches=[1])
    b2 = gl.build_bridge("HGC", good)
    ok = b2["excel"]["file_consistent"]
    print(f"  {'✅' if ok else '❌'} file khớp -> không báo động giả "
          f"(lệch {b2['excel']['file_gap']:,.0f})")
    bad += not ok

    install(World())
    b3 = gl.build_bridge("HGC", make_doc(
        lines=[line(ob.KIND_IN_ERP, 1_000_000_000.0)], matches=[1]))
    ok = not b3["excel"]["file_consistent"]
    print(f"  {'✅' if ok else '❌'} dòng bị sửa sau khi nhập -> BÁO, không im lặng dựng cầu "
          f"nối trên con số gốc đã hỏng")
    bad += not ok

    # ── 3. KHÔNG áp luật tất toán vào vế ERPNext ─────────────────────────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/mt_opening_gl.py"), encoding="utf-8").read()
    # Soi bằng AST, không bằng tìm chuỗi: bình luận trong hàm có nhắc đúng tên
    # hàm đó ("CỐ Ý KHÔNG gọi ...") nên tìm chuỗi sẽ báo hỏng một thứ đang đúng.
    fn_node = next(n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.FunctionDef) and n.name == "invoice_basket")
    called = {getattr(c.func, "id", "") or getattr(c.func, "attr", "")
              for c in ast.walk(fn_node) if isinstance(c, ast.Call)}
    for fn in ("opening_open_clause", "opening_settled_expr"):
        ok = fn not in called
        print(f"  {'✅' if ok else '❌'} `invoice_basket` KHÔNG gọi `{fn}` — áp luật rồi mới so "
              f"thì khoản 'hóa đơn ngoài danh sách' luôn bằng 0")
        bad += not ok

    install(World())
    fin = gl.build_bridge("HGC", make_doc(
        lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)], matches=[1], status=ob.STATUS_FINAL))
    ok = fin["erp"]["not_listed"] > 0
    print(f"  {'✅' if ok else '❌'} bản ĐÃ CHỐT vẫn hiện {fin['erp']['not_listed']:,.0f}đ hóa đơn "
          f"ngoài danh sách — đó là số tiền việc chốt đã lấy đi, không được giấu")
    bad += not ok

    # ── 4. Truy vấn sổ cái — bốn bộ lọc, thiếu cái nào cũng sai tiền ─────
    print("-" * 82)
    w2 = World()
    install(w2)
    gl.gl_balance_by_party("HGC", CUSTOMERS, "2026-07-31")
    q = next((x for x in w2.queries if "tabGL Entry" in x), "")
    for needle, why in (
        ("gle.is_cancelled = 0", "bút toán đã hủy vẫn cộng vào số dư"),
        ("gle.party_type = 'Customer'", "gộp cả nhà cung cấp vào công nợ phải thu"),
        ("gle.posting_date <= %(as_of)s", "lấy số dư HÔM NAY chứ không phải tại ngày chốt"),
        ("gle.company = %(company)s", "cộng cả công ty khác"),
    ):
        ok = needle in q
        print(f"  {'✅' if ok else '❌'} lọc `{needle}` — thiếu thì {why}")
        bad += not ok

    # TK phải thu có HAI hình dạng hợp lệ, và phải kiểm CẢ HAI: site khai TK cụ
    # thể trong Settings thì lọc theo TK đó, không khai thì lùi về account_type.
    # Chỉ kiểm một nhánh là nhánh kia có thể trống mà không ai biết.
    ok = "gle.account = %(racc)s" in q and w2.queries[0].count("%(racc)s") >= 1
    print(f"  {'✅' if ok else '❌'} site có khai TK phải thu -> lọc đúng TK đó")
    bad += not ok

    import frappe as _fr
    _fr.get_cached_doc = lambda dt: _D(receivable_account=None, mt_customer_group="MT",
                                       npp_customer_group="NPP")
    w3 = World()
    _fr.db.sql = w3.sql
    gl.gl_balance_by_party("HGC", CUSTOMERS, "2026-07-31")
    q3 = next((x for x in w3.queries if "tabGL Entry" in x), "")
    ok = "acc.account_type = 'Receivable'" in q3
    print(f"  {'✅' if ok else '❌'} site KHÔNG khai -> lùi về `account_type = 'Receivable'`, "
          f"không phải bỏ luôn bộ lọc tài khoản")
    bad += not ok
    install(World())

    ok = gl._party_in_clause([], {}) == "1 = 0"
    print(f"  {'✅' if ok else '❌'} danh sách khách RỖNG -> `1 = 0`, không phải bỏ qua bộ lọc "
          f"(bỏ qua là cộng công nợ toàn công ty vào ô của một chuỗi)")
    bad += not ok

    p = {}
    c = gl._party_in_clause(CUSTOMERS, p)
    ok = "%(gp0)s" in c and p.get("gp0") == CUSTOMERS[0] and CUSTOMERS[0] not in c
    print(f"  {'✅' if ok else '❌'} tên khách đi bằng tham số ràng buộc, không nối chuỗi vào SQL")
    bad += not ok

    # ── 5. Bóc theo pháp nhân phải cộng lại đúng tổng chuỗi ──────────────
    print("-" * 82)
    install(World())
    b = gl.build_bridge("HGC", make_doc(lines=[line(ob.KIND_IN_ERP, 1_153_334_820.0)],
                                        matches=[1]))
    by = b["by_customer"]
    ok = abs(sum(r["gl"] for r in by) - b["erp"]["gl"]) < 0.01
    print(f"  {'✅' if ok else '❌'} cộng sổ cái từng pháp nhân = tổng chuỗi")
    bad += not ok

    ok = abs(sum(r["listed"] + r["not_listed"] for r in by) - b["erp"]["invoice_basket"]) < 0.01
    print(f"  {'✅' if ok else '❌'} cộng rổ hóa đơn từng pháp nhân = tổng chuỗi")
    bad += not ok

    ok = len(by) == len(CUSTOMERS)
    print(f"  {'✅' if ok else '❌'} liệt kê ĐỦ {len(CUSTOMERS)} pháp nhân của chuỗi")
    bad += not ok

    install(World(gl={"CUS-EB-3003172": 900_000_000.0}, basket={}))
    b = gl.build_bridge("HGC", make_doc(lines=[]))
    ok = len(b["by_customer"]) == len(CUSTOMERS)
    print(f"  {'✅' if ok else '❌'} pháp nhân KHÔNG có số dư vẫn hiện (dòng 0 là thông tin, "
          f"dòng vắng mặt là câu hỏi bỏ ngỏ)")
    bad += not ok

    # ── 6. Hai màn hình MỘT con số ───────────────────────────────────────
    print("-" * 82)
    ssrc = open(os.path.join(rc.REPO, "ketoan/api/mt_opening_store.py"), encoding="utf-8").read()
    fseg = ssrc.split("def finalize_preview")[1].split("\ndef ")[0]
    ok = "IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)" in fseg
    print(f"  {'✅' if ok else '❌'} 'chốt xong X đồng rời khỏi công nợ' trừ cả phần đã thu — "
          f"lấy gộp `grand_total` là nói quá tác động của việc chốt")
    bad += not ok

    ok = "IFNULL(rt.returned, 0)" in fseg
    print(f"  {'✅' if ok else '❌'} … và trừ cả hàng đã trả lại")
    bad += not ok

    bseg = src.split("def invoice_basket")[1].split("\ndef ")[0]
    ok = ("IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)" in bseg
          and "IFNULL(rt.returned, 0)" in bseg)
    print(f"  {'✅' if ok else '❌'} cầu nối dùng ĐÚNG biểu thức đó — hai màn hình nói cùng một "
          f"con số về cùng một tập hóa đơn")
    bad += not ok

    kseg = ssrc.split("def _kept_by_erp")[1].split("\ndef ")[0]
    ok = "IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)" in kseg
    print(f"  {'✅' if ok else '❌'} và 'ERPNext nói' trên màn hình chốt cũng vậy")
    bad += not ok

    # ── 7. READ-ONLY: màn hình đối chiếu không được ghi gì ───────────────
    print("-" * 82)
    for pat, why in (("set_value", "ghi thẳng vào chứng từ"),
                     (".save(", "lưu tài liệu"),
                     ("db_set", "ghi field"),
                     ("db.commit", "chốt giao dịch")):
        ok = pat not in src
        print(f"  {'✅' if ok else '❌'} không có `{pat}` — màn hình đối chiếu chỉ ĐỌC")
        bad += not ok

    tree = ast.parse(src)
    n_wl = 0
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "whitelist"
                   for d in node.decorator_list):
            continue
        n_wl += 1
        rest = [x for x in node.body
                if not (isinstance(x, ast.Expr) and isinstance(getattr(x, "value", None),
                                                               ast.Constant))]
        first = rest[0] if rest else None
        got = isinstance(first, ast.Expr) and isinstance(first.value, ast.Call) and \
            getattr(first.value.func, "id", "") == "guard_mt"
        print(f"  {'✅' if got else '❌'} {node.name}() gọi guard_mt() ở dòng đầu")
        bad += not got
    ok = n_wl == 2
    print(f"  {'✅' if ok else '❌'} soi được {n_wl} whitelisted method (compare + chain_detail)")
    bad += not ok

    # ── 8. Có đường vào trên portal ──────────────────────────────────────
    print("-" * 82)
    ajs = open(os.path.join(rc.REPO, "ketoan/public/ketoan/lib/api.js"), encoding="utf-8").read()
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    for name in ("mtOpeningGlCompare", "mtOpeningGlDetail"):
        ok = name in ajs and name in js
        print(f"  {'✅' if ok else '❌'} api.js khai `{name}` và màn hình có dùng")
        bad += not ok

    ok = "glRes = { error: e.message }" in js
    print(f"  {'✅' if ok else '❌'} vế sổ cái hỏng thì chỉ mất hai cột, không trắng cả bảng "
          f"số dư đầu kỳ")
    bad += not ok

    ok = "Cầu nối không cộng đủ" in js
    print(f"  {'✅' if ok else '❌'} màn hình NÓI RA khi cầu nối còn dư, không im lặng hiện "
          f"một bảng sai")
    bad += not ok

    ok = re.search(r"by_customer", js) is not None
    print(f"  {'✅' if ok else '❌'} có bảng bóc theo từng pháp nhân")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — cầu nối cộng đủ ở mọi hình dạng, so đúng vế, không áp luật tất "
          "toán vào vế ERPNext, và hai màn hình nói cùng một con số")
    return 0


if __name__ == "__main__":
    sys.exit(main())
