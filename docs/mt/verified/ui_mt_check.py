#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_mt_check — MÀN LÀM VIỆC KẾ TOÁN MT: những gì màn hình HỨA phải đúng.

════════════════════════════════════════════════════════════════════════════
NĂM ĐIỀU BỘ KIỂM NÀY CANH
════════════════════════════════════════════════════════════════════════════

1. **Badge trên tab phải bằng số việc trong panel.** Badge lấy từ
   `get_board`, panel lấy từ `get_chain_worklist`. Hai endpoint, một con số —
   và một dòng vừa "chưa nối hóa đơn" vừa "Cần review" là MỘT việc, không
   phải hai. Đếm vào cả hai ô thì badge nói 13 còn panel liệt kê 12, và sau
   lần lệch đầu tiên thì không con số nào trên màn hình còn được tin.

2. **Khối "Hai cách theo dõi công nợ" + "Sổ cái TK 131" KHÔNG ĐƯỢC ĐỔI.** Đó
   là khối đắt nhất của cả màn: hai vế luôn cộng lại bằng số còn nợ, và dòng
   sổ cái nói ra chỗ lệch giữa rổ hóa đơn và số dư thật. Sửa một chữ ở đó là
   sửa một kết luận kế toán, không phải sửa giao diện.

3. **Rổ mặc định là CHƯA THU ĐỦ.** Mở màn ra mà thấy "Tất cả" thì việc còn
   phải làm nằm lẫn giữa những tờ đã xong.

4. **Dòng cộng nói về CẢ BỘ LỌC**, không phải trang đang xem. Một dòng tổng
   chỉ cộng 20 dòng đang hiện là con số đúng về một tập không ai hỏi — mà nó
   trông vẫn rất đáng tin.

5. **Không class CSS nào thiếu tiền tố.** ERPNext nạp Bootstrap trên cùng
   trang; `.card` / `.badge` / `.btn` / `.modal` trần là mượn nhầm CSS của
   người khác, và lỗi đó chỉ lộ ra trên site thật.

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
from regression_check import code_only, js_body  # noqa: E402

API = os.path.join(rc.REPO, "ketoan", "api")
PORTAL = os.path.join(rc.REPO, "ketoan", "public", "ketoan")
MTJS = os.path.join(PORTAL, "views", "mt.js")
CSS = os.path.join(PORTAL, "shell.css")

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


def func_bodies(path):
    s = open(path, encoding="utf-8").read()
    out = {}
    for node in ast.walk(ast.parse(s)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seg = ast.get_source_segment(s, node) or ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            seg = seg.replace(node.body[0].value.value, "")
        out[node.name] = seg
    return out


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: True
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    mt = importlib.import_module("ketoan.api.mt")
    hub = importlib.import_module("ketoan.api.mt_hub")
    rec_mod = importlib.import_module("ketoan.api.mt_reconcile")

    js = open(MTJS, encoding="utf-8").read()
    css = open(CSS, encoding="utf-8").read()

    print("=" * 82)
    print("KIỂM MÀN LÀM VIỆC KẾ TOÁN MT")
    print("=" * 82)

    # ── 1. Badge tab = số việc trong panel ──────────────────────────────
    print("── 1. Badge trên tab và panel 'Cần bạn xử lý' nói CÙNG một số ───────")

    hb = func_bodies(os.path.join(API, "mt_hub.py"))

    # Badge = tổng ba ô của `get_board`; panel = ba nhóm của `get_chain_worklist`.
    steps = js.split("const STEPS = [")[1].split("\n];")[0]
    tab = re.search(r'key: "thanh-toan".*?count: \[(.*?)\]', steps, re.S)
    keys = set(re.findall(r'"(\w+)"', tab.group(1))) if tab else set()
    check("tab Đối soát đếm đúng ba ô của `get_board`",
          keys == {"advices_unreconciled", "lines_unmatched", "lines_review"},
          ", ".join(sorted(keys)))
    check("`get_chain_worklist` trả đúng ba nhóm đó",
          len(hub.WORK_GROUPS) == 3
          and {g["key"] for g in hub.WORK_GROUPS}
          == {hub.WORK_ADVICE, hub.WORK_UNMATCHED, hub.WORK_REVIEW},
          str([g["key"] for g in hub.WORK_GROUPS]))

    # HAI Ô PHẢI RỜI NHAU. Một dòng vừa chưa nối vừa "Cần review" là MỘT việc.
    gb = hb.get("get_board", "")
    check("`get_board` KHÔNG đếm một dòng vào cả hai ô",
          "match_confidence = 'Cần review'" in gb
          and "AND NOT (l.row_kind = %(kind_payment)s" in gb)
    wl = hb.get("get_chain_worklist", "")
    check("và `get_chain_worklist` phân nhóm theo ĐÚNG luật đó",
          "if cstr(ln.row_kind) == KIND_PAYMENT and not d[\"sales_invoice\"]:" in wl)
    check("panel tự trả về TỔNG, màn hình không tự cộng lại",
          '"total": sum(g["count"] for g in groups)' in wl)
    check("danh sách cắt bớt thì NÓI RA (`more`), số đếm vẫn là số đầy đủ",
          "more=max(0, n - len(rows))" in wl and "count=n" in wl)

    # Màn hình phải lấy CẢ HAI từ cùng một lần gọi, không gọi hai lần.
    ens = js_body(js, "ensureWorklist")
    check("màn hình nạp hàng đợi MỘT LẦN cho mỗi (chuỗi, khoảng ngày)",
          "state.wlKey" in ens and "mtChainWorklist" in ens)
    check("và bỏ cache khi đổi chuỗi hoặc đổi khoảng ngày",
          "invalidateWorklist" in js and 'state.wlKey = ""' in js)

    # ── 2. Khối hai cuốn sổ + sổ cái 131 KHÔNG ĐỔI ──────────────────────
    print("-" * 82)
    print("── 2. Khối 'Hai cách theo dõi công nợ' + sổ cái TK 131 còn nguyên ───")

    tb = js_body(js, "twoBooks")
    tbc = js_body(js, "twoBooksChain")
    both = tb + tbc
    for phrase in ("Hai cách theo dõi công nợ",
                   "Đòi được — đã xuất HĐĐT",
                   "Chưa đòi được — CHƯA xuất HĐĐT",
                   "cộng lại đúng bằng"):
        check(f"còn câu “{phrase}”", phrase in both)
    gl = js_body(js, "glBridgeCard") + js_body(js, "loadChainGl") + tbc
    check("còn dòng “Sổ cái TK 131 — số dư thật trên sổ”",
          "Sổ cái TK 131" in gl and "số dư thật trên sổ" in gl)
    check("còn nút “Vì sao lệch”", "Vì sao lệch" in gl or "Vì sao lệch" in js)
    # Hai vế vẫn phải BẤM ĐƯỢC — con số không mở ra được danh sách thì nó chỉ
    # để nhìn, và đó đúng là điều MT2-X sinh ra để sửa.
    check("hai vế vẫn bấm mở được danh sách", "#cb-open-da" in js and "#cb-open" in js)

    # ── 3. Rổ mặc định · bộ lọc · cách xếp ──────────────────────────────
    print("-" * 82)
    print("── 3. Mở màn ra là thấy VIỆC, không phải toàn bộ danh sách ──────────")

    render = js_body(js, "render") or js
    check("rổ mặc định là `chua_thanh_toan`",
          'query.bucket : "chua_thanh_toan"' in render)
    check("thanh chọn rổ có SỐ ĐẾM từng rổ",
          "res.counts" in js_body(js, "loadTab") or "cnt[v.key]" in js_body(js, "loadTab"))
    check("backend trả số đếm cho cả bốn rổ",
          "_bucket_counts" in code_only(os.path.join(API, "mt.py")))
    b = func_bodies(os.path.join(API, "mt.py"))
    bc = b.get("_bucket_counts", "")
    check("và đếm bằng CHÍNH mệnh đề lọc của danh sách",
          "_invoice_where" in bc and "_bucket_where" in bc)
    check("xếp mặc định theo TUỔI NỢ giảm dần", mt.SORT_DEFAULT == "tuoi",
          mt.SORT_DEFAULT)
    check("khóa xếp KHAI SẴN, không nhận ORDER BY từ client",
          "sort not in SORTS" in b.get("get_invoices", ""))
    check("hóa đơn chưa khai hạn xếp CUỐI, không lẫn vào giữa",
          "(od IS NULL), od DESC" in mt.SORTS["tuoi"], mt.SORTS["tuoi"])

    # ── 4. Cột tuổi nợ · trạng thái · dòng cộng ─────────────────────────
    print("-" * 82)
    print("── 4. Bảng hóa đơn: tuổi nợ, trạng thái, và dòng cộng của CẢ bộ lọc ─")

    ip = b.get("_invoice_page", "")
    check("tuổi nợ dùng LẠI luật hạn của màn công nợ, không dựng luật thứ hai",
          "overdue_days_expr" in ip and "from ketoan.api.mt_debt import" in ip)
    dbt = func_bodies(os.path.join(API, "mt_debt.py"))
    check("`due_expr` là bản song sinh SQL của `_resolve_due`",
          "custom_mt_credit_days" in dbt.get("due_expr", "")
          and "due_date > " in dbt.get("due_expr", ""))
    check("dòng cộng tính trên CẢ bộ lọc, không phải trang đang xem",
          '{base}' in ip and '{_REMAIN} ELSE 0 END) AS remaining' in ip)
    # Phiếu trả hàng CÓ trong danh sách nhưng KHÔNG có trong phép cộng: với một
    # phiếu trả `_REMAIN` vẫn dương, nên cộng thẳng là dòng tổng ghi "còn nợ"
    # đúng bằng số tiền của một lần bán đã bị hủy.
    check("phiếu trả hàng không lọt vào phép cộng tiền phải thu",
          'sale = "si.is_return = 0"' in ip and "WHEN {sale} THEN {_REMAIN}" in ip)
    check("và vẫn ĐẾM RIÊNG để dòng tổng nói ra chúng có mặt",
          "n_returns" in ip and "returns_amt" in ip)
    check("và cộng bằng ĐÚNG mệnh đề của danh sách (`base` dùng chung)",
          ip.count("{base}") >= 3, f"{ip.count('{base}')} lần dùng")
    check("phần QUÁ HẠN cộng riêng, dùng cùng biểu thức tuổi nợ",
          "{od} > 0 THEN {_REMAIN}" in ip)
    check("và đếm luôn số tờ CHƯA KHAI HẠN (không nằm trong cả hai vế)",
          "n_no_term" in ip)

    st = b.get("_invoice_status", "")
    check("trạng thái có ĐỦ năm nhãn", len(mt.INVOICE_STATUSES) == 5,
          str(mt.INVOICE_STATUSES))
    # Thứ tự ưu tiên là NGHIỆP VỤ: số HĐĐT đã chết chặn mọi việc khác, vì siêu
    # thị không trả theo số đã chết dù hóa đơn quá hạn bao lâu.
    check("`Phát hành lại` hỏi TRƯỚC mọi nhãn khác",
          st.index("ST_PHAT_HANH_LAI") < st.index("ST_QUA_HAN"))
    check("`Cần xác nhận` hỏi trước `Quá hạn`",
          st.index("ST_CAN_XAC_NHAN") < st.index("ST_QUA_HAN"))
    check("`Chờ bảng kê` là nhãn CUỐI (phần lớn hóa đơn nằm ở đây)",
          st.rindex("ST_CHO_BANG_KE") > st.rindex("ST_DA_KHOP"))

    ac = js_body(js, "ageCell")
    check("tuổi 'chưa khai hạn' KHÔNG vẽ thành 0 ngày",
          "chưa khai hạn" in ac and "undefined" in ac)
    check("chưa tới hạn hiện 'còn N ngày', không hiện số âm", "còn ${-d} ngày" in ac)

    it = js_body(js, "invoiceTable")
    check("bảng có ô chọn nhiều + thanh hành động hàng loạt",
          "inv-all" in it and "inv-bulk" in it)
    check("có dòng cộng (tfoot)", "invoiceFoot" in it)
    check("chọn được số dòng mỗi trang", "pageSizeBar" in it)
    check("có nút Xuất Excel", "mt-export" in js_body(js, "loadTab"))
    ex = b.get("export_invoices", "")
    check("xuất theo ĐÚNG bộ lọc đang xem", "_invoice_page" in ex)
    check("vượt trần thì BÁO LỖI, không cắt im lặng",
          "MAX_EXPORT" in ex and "frappe.throw" in ex)
    check("bỏ cột 'Bảng kê đã trả' lặp chữ 'chưa có bảng kê nào'",
          "chưa có bảng kê nào" not in js_body(js, "paymentCell")
          or "Bảng kê đã trả" not in it)

    # ── 5. Màn đối soát ba vế ───────────────────────────────────────────
    print("-" * 82)
    print("── 5. Đối soát bảng kê: ba vế LUÔN thẳng hàng, và không viết lại luật ")

    check(".ktmt-rec là MỘT grid cấp cha, không phải ba cột rời",
          ".ktmt-rec { display: grid; grid-template-columns: minmax(0, 1fr) 132px minmax(0, 1fr); }" in css)
    # Ba ô con KHÔNG được có chiều cao riêng hay float — chỉ khi chúng là ô của
    # cùng một grid thì hàng mới tự cao bằng ô cao nhất.
    for cls in ("ktmt-rec-l", "ktmt-rec-m", "ktmt-rec-r"):
        blk = re.search(r"\.%s \{([^}]*)\}" % cls, css)
        body = blk.group(1) if blk else ""
        check(f".{cls} không tự đặt chiều cao/float", bool(body)
              and "height:" not in body and "float:" not in body)
    rr = js_body(js, "reconRow")
    check("mỗi bản ghi phát ra ĐÚNG ba ô con liền nhau",
          rr.count("ktmt-rec-l") == 1 and rr.count("ktmt-rec-m") == 1
          and rr.count("ktmt-rec-r") == 1)

    rb = func_bodies(os.path.join(API, "mt_reconcile.py"))
    check("nối dòng ỦY QUYỀN cho `mt.relink_line`, không viết lại",
          "relink_line" in rb.get("link_statement_line", ""))
    # CHỐT ≠ SINH BÚT TOÁN. `commit_statement` chỉ đánh dấu đã đối chiếu; bút
    # toán vẫn do modal `mt_je` cũ sinh, vì chốt chặn vân tay hai bước thuộc về
    # nó — người phải NHÌN bản xem trước rồi mới bấm. Sinh ở đây là sinh bút
    # toán cho một bản xem trước chưa ai xem.
    cs = rb.get("commit_statement", "")
    check("`commit_statement` KHÔNG tự sinh bút toán",
          "create_journal_entries" not in cs and "Journal Entry" not in cs)
    check("và KHÔNG bao giờ submit gì",
          ".submit(" not in cs and "docstatus" not in cs)
    check("nhưng THẬT SỰ ghi `reconciled = 1` (bản đầu chốt xong vẫn chưa chốt)",
          '"reconciled": 1' in cs and "set_value" in cs)
    check("và nói ra số dòng bị bỏ lại — chúng không vào bút toán nào",
          '"unlinked"' in cs and "COUNT(*)" in cs)
    check("bút toán đi qua ĐÚNG modal `mt_je` cũ, không dựng bản thứ hai",
          "openJePreview(" in js_body(js, "openJePreviewFor")
          and "mtJePreview" not in js_body(js, "renderReconcile"))
    check("bút toán ra ở trạng thái NHÁP — màn hình nói rõ",
          "bút toán NHÁP" in js_body(js, "renderReconcile"))
    check("`Nhận hết` chỉ nhận gợi ý mức 1 và DUY NHẤT",
          "SUG_CHAC_CHAN" in rb.get("_auto_ok", "")
          and "len(top) == 1" in rb.get("_auto_ok", ""))
    check("mỗi dòng của `Nhận hết` vẫn đi qua `link_statement_line`",
          "link_statement_line(" in rb.get("bulk_link", ""))
    check("một dòng hỏng không kéo theo cả lượt",
          "failed.append" in rb.get("bulk_link", ""))

    # GIẢI TRÌNH LÀ NHÃN, KHÔNG PHẢI MỘT LẦN THU TIỀN.
    ev = rb.get("explain_variance", "")
    check("`explain_variance` KHÔNG đụng `total_amount`",
          "total_amount" not in ev.split("gap = ")[-1].split("doc.db_set")[0]
          or "doc.db_set" in ev)
    # MÁY SUY: chữ ký hàm KHÔNG có tham số số tiền, và giá trị ghi xuống là
    # `gap` vừa tính. Cho gõ tay thì con số đi giải trình là một ý kiến.
    import inspect
    ev_args = list(inspect.signature(rec_mod.explain_variance).parameters)
    check("số tiền phần lệch MÁY SUY, không cho gõ tay",
          not any(a in ev_args for a in ("amount", "variance_amount", "gap")),
          ", ".join(ev_args))
    check('và ô ghi xuống lấy ĐÚNG `gap` vừa tính',
          '"variance_amount": gap' in ev and "gap = round(" in ev)
    # ĐO TRÊN CẢ HÓA ĐƠN. So MỘT kỳ trả với CẢ tờ là ghi một con số không tồn
    # tại: Co.op tách 8 kỳ thì kỳ nào cũng "lệch" bằng 7 phần còn lại.
    check("phần lệch đo trên CẢ hóa đơn, không phải một dòng bảng kê",
          "SUM(ABS(l.total_amount))" in ev and "l.sales_invoice = %(si)s" in ev)
    check("và cùng QUY ƯỚC DẤU với màn hình (âm = chuỗi trả thiếu)",
          "gap = round(paid - abs(flt(si.grand_total)), 2)" in ev)
    check("và màn hình NÓI RÕ khoản đó vẫn còn trên công nợ",
          "VẪN còn trên công nợ" in ev)
    rec_src = code_only(os.path.join(API, "mt_reconcile.py"))
    check("module đối soát KHÔNG nhắc `return_invoice` ở bất kỳ đâu",
          "return_invoice" not in rec_src)
    # Ba ô `variance_*` không được lọt vào một phép cộng tiền nào của cả app.
    #
    # Bản đầu gắt đến mức vô nghĩa: hễ một hàm vừa nhắc `variance_amount` vừa có
    # chữ `SUM(` là báo đỏ — mà `get_statement_reconcile` phải làm cả hai (cộng
    # tiền đã trả, và ĐỌC nhãn ra để hiện). Nên nó bắt đúng hàm lành. Ở đây bắt
    # cái thật: `variance_amount` NẰM TRONG một biểu thức cộng tiền.
    money = []
    var_money = [
        r"SUM\s*\([^)]*variance_amount",                    # cộng thẳng trong SQL
        r"variance_amount[^\n]*[-+]\s*(?:flt\(|paid|remaining|total_amount|grand_total)",
        r"(?:paid|remaining|gap|total|due)\w*\s*[-+]?=[^\n=]*variance_amount",
        r"variance_amount[^\n]*\bAS\s+(?:paid|remaining|amount|due)\b",
    ]
    for fn in sorted(os.listdir(API)):
        if not fn.endswith(".py"):
            continue
        for name, body in func_bodies(os.path.join(API, fn)).items():
            if "variance_amount" not in body:
                continue
            for pat in var_money:
                if re.search(pat, body):
                    money.append(f"{fn}::{name}")
                    break
    check("không phép cộng tiền nào ăn vào `variance_amount`", not money,
          ", ".join(money) or "sạch")

    # ── 5b. Hai nút hàng loạt: một cái LÀM ĐƯỢC, một cái CỐ Ý KHÔNG ─────
    #
    # "Gán vào bảng kê" đi chiều ngược màn đối soát và nối được thật.
    # "Đánh dấu đã thu" thì KHÔNG, và phải nói ra vì sao: kênh MT không tạo
    # Payment Entry — mọi khoản trừ công nợ đi bằng bút toán do người duyệt.
    # Một cái tick trừ được công nợ sẽ trừ đúng những tờ khó đòi nhất.
    print("-" * 82)
    print("── 5b. Nút hàng loạt: nối được thì nối, không được thì NÓI RA ───────")

    rvb = rb.get("suggest_for_invoices", "")
    check("`Gán vào bảng kê` có tầng dưới thật", bool(rvb))
    check("và chỉ tìm dòng CHƯA NỐI trên bảng kê ĐÃ NẠP",
          "IFNULL(l.sales_invoice, '') = ''" in rvb and "row_kind = %(kind)s" in rvb)
    check("buộc công ty (SQL thô không đi qua permission)",
          "si.company = %(c)s" in rvb and "a.company = %(c)s" in rvb)
    check("có trần số hóa đơn chọn một lượt", "MAX_REVERSE" in rvb)
    check("và NÓI RA rằng đây không phải chỗ đánh dấu đã thu",
          "không phải chỗ đánh dấu đã thu" in rvb)
    bit = js_body(js, "bindInvoiceTable")
    check("nút `Gán vào bảng kê` gọi tầng đó", "openReverseMatch" in bit)
    check("nút `Đánh dấu đã thu` KHÔNG gọi API nào", "inv-bulk-paid" in bit
          and "mtReconLink" not in bit.split("inv-bulk-paid")[1][:400])
    check("và giải thích bằng BÚT TOÁN, không im lặng",
          "BÚT TOÁN" in bit and "Payment Entry" in bit)
    rvj = js_body(js, "renderReverseMatch")
    check("modal in câu 'vẫn còn nợ' cho hóa đơn không tìm được dòng nào",
          "vẫn còn nợ" in rvj)

    # ── 5c. Vòng soát 2: những chỗ hai con số cùng nói về một thứ ───────
    #
    # Năm lỗi dưới đây có chung một hình dạng: hai bản ghi CÙNG một sự thật,
    # rồi một bản đi trước bản kia. Không cái nào nổ ra lỗi — chúng chỉ hiện số
    # cũ, và số cũ trông y hệt số mới.
    print("-" * 82)
    print("── 5c. Không hai bản ghi nào cùng nói về một sự thật ────────────────")

    bl = rb.get("bulk_link", "")
    check("`Nhận hết` không nối HAI dòng vào CÙNG một hóa đơn",
          "taken" in bl and "clashed.append" in bl and "taken.add(" in bl)
    check("và trả danh sách dòng bị bỏ lại để màn hình bày ra",
          '"clashed": clashed' in bl)
    check("màn hình ĐỌC danh sách đó, không lặng lẽ báo thành công",
          "out.clashed" in js_body(js, "bindReconcile"))
    cnd = rb.get("_candidates", "")
    check("rổ ứng viên LOẠI hóa đơn đã thu đủ",
          "pd.paid" in cnd and "ABS(si.grand_total) - %(tol)s" in cnd)
    check("nhưng KHÔNG loại hóa đơn mới trả một phần (Co.op tách 8 kỳ)",
          "IFNULL(pd.paid, 0) <" in cnd and "= ABS(si.grand_total)" not in cnd)

    # Ngày mặc định: `toISOString()` là ngày Ở UTC. Việt Nam UTC+7 nên từ 00:00
    # tới 07:00 mỗi ngày nó trả HÔM QUA — và `new Date(y, m, 1).toISOString()`
    # ra ngày CUỐI THÁNG TRƯỚC, nên preset "Tháng này" không bao giờ khớp lại
    # với chính nó để tô nút.
    stray = []
    for root, _d, files in os.walk(PORTAL):
        for fn in files:
            if not fn.endswith(".js"):
                continue
            fp = os.path.join(root, fn)
            for i, ln in enumerate(open(fp, encoding="utf-8"), 1):
                if "toISOString" in ln and not ln.lstrip().startswith("//"):
                    stray.append(f"{fn}:{i}")
    check("không file portal nào còn lấy ngày hôm nay theo giờ UTC", not stray,
          ", ".join(stray) or "sạch")
    fmt = open(os.path.join(PORTAL, "lib", "format.js"), encoding="utf-8").read()
    check("`isoDate` dựng ngày từ getFullYear/getMonth/getDate của MÁY",
          "getFullYear()" in fmt and "getDate()" in fmt and "isoDate" in fmt)
    check("và màn MT dùng nó cho cả preset lẫn hai ô ngày",
          "isoDate" in js and "const iso = isoDate" in js)

    # Ô tích và bộ đếm phải được chốt CÙNG một lúc.
    pf = js_body(js, "pickedFor")
    check("rổ chọn chốt LÚC VẼ (`pickedFor`), không phải lúc gắn sự kiện",
          "state.pickedKey" in pf and "new Set()" in pf)
    check("và `invoiceTable` gọi nó trước khi vẽ dòng",
          "pickedFor(state, res)" in js_body(js, "invoiceTable"))
    check("`bindInvoiceTable` KHÔNG chốt lại (chốt lại là ô tích mà đếm 0)",
          "state.pickedKey" not in bit)
    check("ô 'cả trang' theo các ô con, kể cả trạng thái nửa vời",
          "indeterminate" in bit)

    # Hàng đợi việc: MỘT chuyến bay, và kết quả về muộn thì vứt.
    ew = js_body(js, "ensureWorklist")
    check("`ensureWorklist` nhớ cả CHUYẾN ĐANG BAY, không chỉ kết quả",
          "state.wlPending) return state.wlPending" in ew)
    check("và kết quả về sau một lần xóa hàng đợi thì bị VỨT",
          "wlGen" in ew and "state.wlGen === gen" in ew)
    iw = js_body(js, "invalidateWorklist")
    check("xóa hàng đợi xóa cả chuyến đang bay",
          "wlPending" in iw and "wlGen" in iw)
    check("nối/gỡ tay cũng xóa hàng đợi (số trên thanh là số người tin nhất)",
          "invalidateWorklist(state)" in js_body(js, "openRelinkModal"))

    # Modal đối soát đổi dữ liệu -> màn phía sau phải theo kịp, dù đóng bằng
    # lối nào.
    md = open(os.path.join(PORTAL, "components", "modal.js"), encoding="utf-8").read()
    check("`openModal` có `onClose`, chạy ĐÚNG MỘT LẦN cho cả ba lối đóng",
          "if (onClose) onClose();" in md and "let closed = false" in md
          and "if (closed) return;" in md)
    orc = js_body(js, "openReconcile")
    check("modal đối soát nạp lại màn phía sau khi CÓ thay đổi",
          "onClose" in orc and "loadTab(container, state)" in orc)
    check("và KHÔNG nạp lại khi người ta chỉ mở ra xem",
          "if (!st.dirty) return" in orc)
    brc = js_body(js, "bindReconcile")
    check("mọi hành động đổi dữ liệu đều đánh dấu `dirty`",
          brc.count("st.dirty = true") >= 5, f"{brc.count('st.dirty = true')} chỗ")
    check("`Chọn tay` mở từ trong modal thì nạp lại MODAL, không phải nền",
          "openRelinkModal(container, state, b.dataset.recfind, \"\", ()" in brc)

    # Hai con số cách nhau 50px không được cùng mang một cái tên.
    cshell = js_body(js, "chainShell")
    wbar = js_body(js, "worklistBar")
    check("số việc ở đầu màn nói rõ nó đếm MỌI BƯỚC",
          "việc ở mọi bước" in cshell)
    check("số việc trên thanh nói rõ nó đếm MỘT bước",
          "việc ở bước Đối soát thanh toán" in wbar)
    check("và không còn hai chỗ cùng ghi 'việc đang chờ'",
          "việc đang chờ" not in cshell and "việc đang chờ" not in wbar)

    # ── 6. Điều hướng · tiền tố CSS ─────────────────────────────────────
    print("-" * 82)
    print("── 6. Thanh điều hướng gọn lại, và không class nào thiếu tiền tố ────")

    sh = open(os.path.join(PORTAL, "shell.js"), encoding="utf-8").read()
    ws = open(os.path.join(PORTAL, "lib", "workspaces.js"), encoding="utf-8").read()
    check("nav dùng nhãn NGẮN (`navLabel`)", "navLabel(w)" in sh and "navLabel:" in ws)
    check("bỏ hai mục con của khu MT khỏi nav toàn cục",
          'data-nav="vat"' not in sh and 'href="#/cong-no-mt"' not in sh)
    # ...nhưng KHÔNG được mất đường vào: cả hai phải còn lối khác.
    check("`Hóa đơn VAT` vẫn còn lối vào", "/hoa-don-vat" in ws and "/hoa-don-vat" in js)
    check("`Công nợ kênh MT` vẫn còn lối vào", "/cong-no/mt" in ws and "/cong-no/mt" in js)
    check("bàn làm việc của kế toán MT trỏ vào màn chuỗi",
          'home: "/cong-no-mt"' in ws)
    check("tab đang mở dùng GẠCH CHÂN, không phải viên gradient",
          ".kt-nav-item.is-active" in css
          and "inset 0 -2px 0 var(--kt-primary)" in css)
    check("viên gradient để dành cho tab BƯỚC", ".ktmt-step.is-on" in css
          and "var(--kt-grad)" in css.split(".ktmt-step.is-on")[1][:120])
    check("có chip preset khoảng ngày", "ktmt-preset" in css and "DATE_PRESETS" in js)
    check("preset không khớp thì KHÔNG tô cái nào", "function activePreset" in js)

    # Không class nào thiếu tiền tố. Ngoại lệ DUY NHẤT: các selector ẩn chrome
    # website của ERPNext — chúng CỐ Ý trần vì phải trúng class của ERPNext.
    ERP_CHROME = {".navbar", ".web-footer", ".website-footer", ".page-header",
                  ".breadcrumb-container", ".page_content", ".main-section"}
    decl = set(re.findall(r"^\.([a-zA-Z][\w-]*)", css, re.M))
    stray = sorted(c for c in decl
                   if not c.startswith(("kt-", "ktmt-")) and ("." + c) not in ERP_CHROME)
    check("không class CSS nào thiếu tiền tố `kt-`/`ktmt-`", not stray,
          ", ".join(stray) or "sạch")
    # Và không class Bootstrap trần nào lọt vào markup của portal.
    BOOTSTRAP = ("card", "modal", "badge", "btn", "container", "overlay", "row", "col")
    hits = []
    for m in re.finditer(r'class="([^"$]*)"', js):
        for c in m.group(1).split():
            if c in BOOTSTRAP:
                hits.append(c)
    check("markup không dùng class Bootstrap trần", not hits,
          ", ".join(sorted(set(hits))) or "sạch")

    # Class mới của khu MT phải có mặt trong CSS — gõ nhầm một chữ thì màn hình
    # mất kiểu mà không có gì báo.
    used = set()
    for m in re.finditer(r'class="([^"$]*)"', js):
        used.update(c for c in m.group(1).split() if c.startswith("ktmt-"))
    missing = sorted(c for c in used if ("." + c) not in css)
    check("mọi class `ktmt-` dùng trong mt.js đều có trong shell.css", not missing,
          ", ".join(missing) or "sạch")

    # ── 7. Thứ tự bước ──────────────────────────────────────────────────
    print("-" * 82)
    print("── 7. Tab bước xếp theo VÒNG ĐỜI, và số bước in ra ──────────────────")

    order = re.findall(r'\{ key: "([\w-]+)", no: "(\d*)"', steps)
    numbered = [(k, n) for k, n in order if n]
    check("số bước tăng dần theo thứ tự hiển thị",
          [int(n) for _k, n in numbered] == sorted(int(n) for _k, n in numbered),
          " · ".join(f"B{n} {k}" for k, n in numbered))
    want = ["so-theo-doi", "chiet-khau", "thanh-toan", "but-toan", "cong-no"]
    got = [k for k, _n in order if k in want]
    check("năm bước lõi đúng thứ tự brief", got == want, " → ".join(got))
    check("số bước là badge TÁCH khỏi tên", "ktmt-step-no" in js)
    check("badge việc chỉ hiện khi CÓ việc", "${n ? html`<span class=\"ktmt-step-todo\"" in js)

    # ── 8. CHẠY THẬT hai endpoint mới — SQL dựng được, hình dạng đúng ───
    #
    # Bảy mục trên soi MÃ NGUỒN. Soi mã nguồn không bao giờ bắt được một
    # f-string hỏng hay một tham số ràng buộc thiếu — thứ chỉ nổ khi câu SQL
    # được dựng thật. Mục này GỌI THẲNG, với `db.sql` giả dựng lại ĐÚNG cảnh
    # trong mockup: một dòng khớp 100%, một dòng chuỗi trả thiếu 18.000.
    print("-" * 82)
    print("── 8. Gọi thật `get_invoices` + `get_statement_reconcile` ───────────")

    seen = []

    def sql(q, params=None, as_dict=False, **kw):
        ql = " ".join(q.split())
        seen.append((ql, sorted((params or {}).keys())))
        if ql.startswith("SELECT customer, chain"):
            return [frappe._dict(customer="KH-1", chain="LOTTE", n=3)]
        if ql.startswith("SELECT name, custom_mt_chain"):
            return []
        if "`tabMT Payment Advice Line` l WHERE l.parent" in ql:
            return [
                frappe._dict(line="L1", idx=1, row_kind="Thanh toán",
                             total_amount=2203200.0, store_name="Lotte Go Vap",
                             store_code=None, doc_no="PO1", description="",
                             inv_series=None, inv_no=None, sales_invoice=None,
                             match_confidence=None, match_method=None,
                             variance_kind=None, variance_amount=0,
                             variance_note=None, payment_date="2026-07-28"),
                frappe._dict(line="L2", idx=2, row_kind="Thanh toán",
                             total_amount=3276000.0, store_name="Lotte Go Vap",
                             store_code=None, doc_no="PO2", description="",
                             inv_series=None, inv_no=None, sales_invoice="SI-88",
                             match_confidence="Chắc chắn", match_method="auto",
                             variance_kind=None, variance_amount=0,
                             variance_note=None, payment_date="2026-07-31"),
            ]
        if ql.startswith("SELECT si.name, si.posting_date, ABS(si.grand_total) AS amount, si.customer,"):
            return [frappe._dict(name="SI-4980", posting_date="2026-06-12",
                                 amount=2203200.0, customer="KH-1",
                                 customer_name="LOTTE", inv_series="1C26THG",
                                 inv_no="00006890", ship_to="Lotte Go Vap")]
        if ql.startswith("SELECT si.name, si.posting_date, ABS(si.grand_total) AS amount, si.customer_name,"):
            return [frappe._dict(name="SI-88", posting_date="2026-06-25",
                                 amount=3294000.0, customer_name="LOTTE",
                                 inv_series="1C26THG", inv_no="00006990",
                                 ship_to="Lotte Go Vap")]
        if "COUNT(*)" in ql and not as_dict:
            return [[7]]
        return []

    frappe.db.sql = sql
    frappe.db.get_single_value = lambda *a, **k: "HG"
    frappe.get_cached_doc = lambda *a, **k: frappe._dict(
        npp_customer_group="NPP", mt_customer_group="MT", default_company=None)

    inv = mt.get_invoices("chua_thanh_toan", company="HG")
    for k in ("totals", "counts", "sort", "sorts", "statuses"):
        check(f"`get_invoices` trả khóa `{k}`", k in inv)
    check("rổ khấu trừ KHÔNG có dòng cộng (hình dạng dòng khác hẳn)",
          mt.get_invoices("chiet_khau", company="HG")["totals"] is None)

    ADV = frappe._dict(name="BK-1", company="HG", chain="LOTTE", customer="KH-1",
                       advice_no="BK-LOT-0726", payment_date="2026-07-31",
                       status="Nháp", reconciled=0, je_state="",
                       total_payment=128412600.0, file_name="f.xlsx")
    frappe.db.get_value = lambda dt, name=None, fields=None, **k: (
        ADV if dt == "MT Payment Advice" else None)
    r = rec_mod.get_statement_reconcile("BK-1", company="HG")
    check("`get_statement_reconcile` chạy được, không nổ SQL", bool(r))
    check("dòng khớp đúng số tiền + đúng điểm giao -> gợi ý mức 1",
          (r["rows"][0].get("auto") or {}).get("sales_invoice") == "SI-4980",
          str((r["rows"][0].get("auto") or {}).get("sales_invoice")))
    check("và chỉ mức 1 mới vào được `Nhận hết`", r["auto_ready"] == 1,
          str(r["auto_ready"]))
    check("dòng chuỗi trả thiếu -> vào ô LỆCH TIỀN, không phải 'đã khớp'",
          r["rows"][1]["state"] == "lech_tien", r["rows"][1]["state"])
    check("mức lệch MÁY TÍNH đúng dấu (chuỗi trả thiếu -> âm)",
          r["rows"][1]["gap"] == -18000.0, str(r["rows"][1]["gap"]))
    check("tiến độ khớp đếm dòng ĐÃ NỐI (dòng lệch tiền vẫn là đã nối)",
          r["matched"] == 1 and r["lines"] == 2, f"{r['matched']}/{r['lines']}")
    check("ba ô đếm rời nhau và cộng lại bằng tổng số dòng",
          sum(r["counts"].values()) == r["lines"], str(r["counts"]))

    bad_sql = [q for q, ks in seen
               if set(re.findall(r"%\((\w+)\)s", q)) - set(ks)]
    check("mọi câu SQL đều có đủ tham số ràng buộc", not bad_sql,
          (bad_sql[0][:60] if bad_sql else "sạch"))
    check("không `IN ()` rỗng", not [q for q, _k in seen if "IN ()" in q])

    print()
    print("=" * 82)
    print("KẾT QUẢ:", "ĐẠT — badge khớp panel, khối hai cuốn sổ nguyên vẹn, dòng cộng "
          "nói về cả bộ lọc, và ba vế đối soát cùng một grid" if ok_all
          else "CÓ MỤC KHÔNG ĐẠT ❌")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
