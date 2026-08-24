"""mt_opening_gl — đối chiếu SỐ DƯ ĐẦU KỲ TRÊN EXCEL với SỔ CÁI ERPNext, từng siêu thị.

════════════════════════════════════════════════════════════════════════════
VÌ SAO CẦN, VÀ VÌ SAO KHÔNG CHỈ LÀ "HAI SỐ CẠNH NHAU"
════════════════════════════════════════════════════════════════════════════

File công nợ của siêu thị và sổ cái ERPNext là hai cuốn sổ được ghi bởi hai bên
khác nhau, theo hai quy ước khác nhau. Bày hai con số ra rồi in "lệch 412 triệu"
là **không dùng được**: kế toán không biết 412 triệu đó nằm ở đâu, nên hoặc là
bỏ qua, hoặc là sửa bừa một bên cho khớp. Cả hai đều tệ hơn không có màn hình.

Nên màn hình này không so hai số. Nó dựng **CẦU NỐI** — một dãy khoản mục mà
cộng lại phải ra ĐÚNG chỗ lệch, không dư một đồng:

    Sổ cái ERPNext (B)  −  Excel mang sang (A)
      = (1) sổ cái ngoài rổ hóa đơn        B − B_hd
      + (2) hóa đơn còn nợ KHÔNG có trong danh sách Excel
      + (3) chênh trên chính các dòng đã nối được hóa đơn
      − (4) dòng Excel chưa nối được hóa đơn nào

Đẳng thức này ĐÚNG VỀ ĐẠI SỐ, không phải nhờ làm tròn: cả bốn khoản đều lấy từ
cùng một tập dữ liệu và triệt tiêu nhau về `B − A`. Nghĩa là nếu màn hình hiện
ra một số dư còn lại thì đó là lỗi code, không phải "sai số cho phép" — và bộ
kiểm `opening_gl_check` kiểm đúng chỗ đó.

════════════════════════════════════════════════════════════════════════════
BA CHỖ DỄ SO NHẦM VẾ
════════════════════════════════════════════════════════════════════════════

1. **So với `opening_debt` là so nhầm.** File cộng cả những đơn ĐÃ GIAO nhưng
   CHƯA xuất hóa đơn vào "Số còn nợ" (9 dòng, 46.665.180đ trên file WinCommerce
   mẫu). Chưa có hóa đơn thì không có bút toán, nên sổ cái không thể có chúng.
   Vế đem so là `debt_carried` = `opening_debt` − `no_invoice_amount`.

2. **Không được áp luật tất toán khi tính vế ERPNext.** Bản đã CHỐT làm mọi hóa
   đơn ngoài danh sách rơi khỏi rổ nợ — áp luật rồi mới so thì khoản (2) luôn
   bằng 0 và cầu nối tự khớp một cách vô nghĩa. Cả điểm quý nhất của màn hình
   là chỉ ra ĐÚNG số tiền mà việc chốt đã lấy đi.

3. **Sổ cái tính tại NGÀY CHỐT, không phải hôm nay.** `posting_date <= ngày
   chốt`. Tiền siêu thị trả sau ngày chốt là chuyện của kỳ sau; gộp vào là số
   dư đầu kỳ tự nhiên nhỏ đi đúng bằng số đã thu.

Toàn bộ module READ-ONLY: không ghi một field nào, không sinh bút toán nào.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from ketoan.api._guard import guard_mt, is_chief
from ketoan.api.mt import (
    KIND_DEDUCT,
    KIND_PAYMENT,
    PAID_TOLERANCE,
    _company,
    _customer_in_clause,
    _debt_joins,
    _mt_clause,
    _require_tables,
    chain_customers,
)
from ketoan.api.receivables import _racc_clause
from ketoan.mt.doctype.mt_opening_balance.mt_opening_balance import (
    KIND_NO_INVOICE,
    KIND_PRE_GOLIVE,
    RESOLUTION_SKIP,
    STATUS_FINAL,
)

DOCTYPE = "MT Opening Balance"

# Tiền VND nguyên đồng. 1đ chỉ để chống rác dấu phẩy động khi cộng dồn.
EPS = 1.0


def _tables():
    if not frappe.db.table_exists(DOCTYPE):
        frappe.throw(_(
            "Chức năng số dư đầu kỳ chưa cài trên site này (thiếu bảng {0}). Chạy "
            "`bench --site <site> migrate` rồi thử lại.").format(DOCTYPE))


# ═══════════════════════════════════════════════════════════════════════════
# Vế SỔ CÁI
# ═══════════════════════════════════════════════════════════════════════════

def _party_in_clause(names, params, prefix="gp"):
    """`gle.party IN (...)` bằng tham số ràng buộc. Rỗng là `1 = 0`.

    Cùng một chốt với `mt._customer_in_clause`, chỉ khác tên cột (`party` chứ
    không phải `customer`). Bỏ bộ lọc khi danh sách rỗng thì màn hình "chuỗi X"
    cộng luôn công nợ của MỌI khách toàn công ty vào ô của chuỗi đó.
    """
    if not names:
        return "1 = 0"
    keys = []
    for i, n in enumerate(names):
        k = "%s%d" % (prefix, i)
        params[k] = n
        keys.append("%%(%s)s" % k)
    return "gle.party IN (%s)" % ", ".join(keys)


def gl_balance_by_party(company, customers, as_of):
    """{khách: số dư phải thu} trên SỔ CÁI tại NGÀY CHỐT.

    Nguồn là `tabGL Entry` chứ không phải `Sales Invoice.outstanding_amount` —
    cùng nguồn với mọi báo cáo phải thu khác của app (`receivables.py`). Sổ cái
    mang cả bút toán tay, tiền khách trả trước (số âm) và số dư nhập tay, tức là
    đúng những thứ mà rổ hóa đơn KHÔNG có; nếu lấy từ hóa đơn thì khoản (1) của
    cầu nối vĩnh viễn bằng 0 và ta mất luôn khả năng phát hiện chúng.
    """
    if not customers or not as_of:
        return {}
    params = {"company": company, "as_of": getdate(as_of)}
    racc = _racc_clause(params)
    in_party = _party_in_clause(customers, params)
    rows = frappe.db.sql(f"""
        SELECT gle.party AS customer, SUM(gle.debit - gle.credit) AS bal
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.party_type = 'Customer'
          AND {racc}
          AND gle.posting_date <= %(as_of)s
          AND {in_party}
        GROUP BY gle.party
    """, params, as_dict=True)
    return {r.customer: flt(r.bal) for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
# Vế RỔ HÓA ĐƠN — tách theo "có tên trong danh sách Excel hay không"
# ═══════════════════════════════════════════════════════════════════════════

def invoice_basket(company, chain, as_of, parent=None):
    """Hóa đơn của chuỗi còn nợ tại ngày chốt, chia hai nhóm theo danh sách Excel.

    Công thức nợ là ĐÚNG công thức của `mt.get_overview` / `mt_debt`
    (`_debt_joins` + trừ hàng trả về + trừ đã thu). Dựng phép tính thứ hai ở đây
    là bảo đảm hai màn hình nói hai con số về cùng một hóa đơn.

    CỐ Ý KHÔNG gọi `opening_open_clause`: xem điểm 2 ở đầu module.

    `parent` rỗng (chuỗi chưa nhập file) → mọi hóa đơn đều rơi vào nhóm "không
    có trong danh sách", đúng nghĩa: chưa có danh sách nào cả.
    """
    p = {"company": company, "as_of": getdate(as_of), "tol": PAID_TOLERANCE,
         "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT,
         "parent": cstr(parent or "")}
    in_cus = _customer_in_clause(chain_customers(chain), p, prefix="bcc")
    mt = _mt_clause(p)
    listed = """EXISTS (SELECT 1 FROM `tabMT Opening Match` om
                        WHERE om.parent = %(parent)s
                          AND om.parenttype = 'MT Opening Balance'
                          AND om.sales_invoice = si.name)"""
    if not frappe.db.table_exists("MT Opening Match"):
        listed = "0"

    rows = frappe.db.sql(f"""
        SELECT si.customer,
               COALESCE(si.customer_name, si.customer) AS customer_name,
               SUM(CASE WHEN {listed} THEN 1 ELSE 0 END) AS n_listed,
               SUM(CASE WHEN {listed} THEN 0 ELSE 1 END) AS n_not_listed,
               SUM(CASE WHEN {listed} THEN
                        ABS(si.grand_total) - IFNULL(rt.returned, 0)
                        - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0))
                    ELSE 0 END) AS listed,
               SUM(CASE WHEN {listed} THEN 0 ELSE
                        ABS(si.grand_total) - IFNULL(rt.returned, 0)
                        - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0))
                    END) AS not_listed
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {_debt_joins()}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND si.posting_date <= %(as_of)s
          AND (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0))
              < (ABS(si.grand_total) - IFNULL(rt.returned, 0)) - %(tol)s
          AND {in_cus} AND {mt}
        GROUP BY si.customer, si.customer_name
    """, p, as_dict=True)
    return {r.customer: r for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
# Vế EXCEL
# ═══════════════════════════════════════════════════════════════════════════

def _excel_side(doc):
    """Bóc `debt_carried` thành phần ĐÃ NỐI hóa đơn và phần chưa nối.

    Chỉ phần đã nối mới có mặt bên ERPNext. Phần chưa nối chia tiếp theo lý do,
    vì ba lý do đó đòi ba việc khác nhau:
      · `truoc_golive`   — ERPNext không có chứng từ, và đúng là không nên có;
      · `chua_co_hoa_don` — đơn đã giao chưa xuất hóa đơn (đã trừ khỏi `debt_carried`);
      · còn lại          — dòng 'phải khớp ERPNext' chưa ai nối được: TIỀN THẬT
                           đang không có chứng từ nào giữ, và chốt bây giờ là mất.
    """
    linked = {cint(m.line_no) for m in (doc.matches or []) if cstr(m.sales_invoice)}
    out = {"matched": 0.0, "pre_golive": 0.0, "no_invoice": 0.0,
           "unmatched": 0.0, "skipped": 0.0,
           "n_matched": 0, "n_pre_golive": 0, "n_no_invoice": 0,
           "n_unmatched": 0, "n_skipped": 0}
    for l in doc.lines or []:
        amt = flt(l.remaining)
        if cint(l.idx) in linked:
            out["matched"] += amt
            out["n_matched"] += 1
        elif cstr(l.kind) == KIND_PRE_GOLIVE:
            out["pre_golive"] += amt
            out["n_pre_golive"] += 1
        elif cstr(l.kind) == KIND_NO_INVOICE:
            out["no_invoice"] += amt
            out["n_no_invoice"] += 1
        elif cstr(l.resolution) == RESOLUTION_SKIP:
            out["skipped"] += amt
            out["n_skipped"] += 1
        else:
            out["unmatched"] += amt
            out["n_unmatched"] += 1
    for k in ("matched", "pre_golive", "no_invoice", "unmatched", "skipped"):
        out[k] = round(out[k], 2)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Cầu nối
# ═══════════════════════════════════════════════════════════════════════════

def build_bridge(company, doc):
    """Bốn khoản mục giải thích TRỌN VẸN chỗ lệch giữa hai cuốn sổ.

    Mốc thời gian LUÔN là `cutover_date` của chính bản số dư, không nhận tham số
    ngày từ ngoài. Số dư đầu kỳ được ĐỊNH NGHĨA tại ngày chốt; cho phép chọn
    ngày khác chỉ đẻ ra một con số trông giống nhưng không trả lời câu hỏi nào.
    """
    as_of = doc.cutover_date
    customers = chain_customers(doc.chain)
    gl = gl_balance_by_party(company, customers, as_of)
    basket = invoice_basket(company, doc.chain, as_of, doc.name)
    xl = _excel_side(doc)

    b_gl = round(sum(flt(v) for v in gl.values()), 2)
    b_listed = round(sum(flt(r.listed) for r in basket.values()), 2)
    b_not_listed = round(sum(flt(r.not_listed) for r in basket.values()), 2)
    b_inv = round(b_listed + b_not_listed, 2)

    a_carried = flt(doc.debt_carried)
    a_matched = xl["matched"]

    items = [
        {
            "key": "so_cai_ngoai_ro_hoa_don",
            "label": _("Sổ cái có mà rổ hóa đơn không có"),
            "amount": round(b_gl - b_inv, 2),
            "hint": _(
                "Bút toán tay, phiếu thu chưa cấn trừ hóa đơn, khách trả trước (số âm), "
                "hoặc số dư nhập tay. Khác 0 thì sổ cái và rổ hóa đơn đang kể hai câu "
                "chuyện khác nhau — soi trước khi chốt."),
        },
        {
            "key": "hoa_don_ngoai_danh_sach",
            "label": _("Hóa đơn ERPNext còn nợ mà KHÔNG có trong file"),
            "amount": b_not_listed,
            "hint": _(
                "Chốt bản số dư là đúng {0} đồng này rời khỏi công nợ (coi như đã thanh "
                "toán trước chuyển giao). Đây là số tiền việc chốt lấy đi — nhìn kỹ nó "
                "trước khi bấm."
            ).format("{:,.0f}".format(b_not_listed)),
        },
        {
            "key": "chenh_tren_dong_da_noi",
            "label": _("Chênh trên chính các dòng đã nối được hóa đơn"),
            "amount": round(b_listed - a_matched, 2),
            "hint": _(
                "ERPNext {0} · file {1}. Nối thiếu hóa đơn trả về là nguyên nhân thường "
                "gặp nhất."
            ).format("{:,.0f}".format(b_listed), "{:,.0f}".format(a_matched)),
        },
        {
            "key": "dong_excel_chua_noi",
            "label": _("Dòng file chưa nối được hóa đơn nào"),
            "amount": round(a_matched - a_carried, 2),
            # Liệt kê phần CẤU THÀNH, và có kể cả ghi giảm — nó cũng nằm giữa
            # `debt_carried` và tổng các dòng. Bỏ nó ra thì bốn con số trong câu
            # này không cộng lại ra khoản mục, và người đọc tinh sẽ ngờ cả bảng.
            "hint": _(
                "Gồm: trước go-live {0} · đã đánh dấu bỏ qua {1} · CHƯA xử lý {2} · trừ ghi "
                "giảm chưa cấn trừ {3}. Phần 'CHƯA xử lý' là tiền thật đang không có chứng "
                "từ nào giữ lại — chốt bây giờ là mất."
            ).format("{:,.0f}".format(xl["pre_golive"]),
                     "{:,.0f}".format(xl["skipped"]),
                     "{:,.0f}".format(xl["unmatched"]),
                     "{:,.0f}".format(flt(doc.deduction_open))),
        },
    ]

    diff = round(b_gl - a_carried, 2)
    residual = round(diff - sum(x["amount"] for x in items), 2)

    # Số của FILE tự nó có khớp không: tổng các dòng còn nợ so với dòng TỔNG CỘNG
    # in trong file. `mt_opening` đã checksum lúc đọc, nên khác 0 ở đây nghĩa là
    # dữ liệu đã bị sửa sau khi nhập — và cả cầu nối phía trên chỉ đúng tới mức
    # con số gốc còn đúng.
    file_gap = round(
        (a_carried - xl["matched"])
        - (xl["pre_golive"] + xl["skipped"] + xl["unmatched"] - flt(doc.deduction_open)), 2)

    return {
        "excel": {
            "opening_debt_gross": flt(doc.opening_debt_gross),
            "deduction_open": flt(doc.deduction_open),
            "opening_debt": flt(doc.opening_debt),
            "no_invoice_amount": flt(doc.no_invoice_amount),
            "debt_carried": a_carried,
            "file_gap": file_gap,
            "file_consistent": abs(file_gap) <= EPS,
            **xl,
        },
        "erp": {
            "gl": b_gl,
            "invoice_basket": b_inv,
            "listed": b_listed,
            "not_listed": b_not_listed,
            "n_listed": sum(cint(r.n_listed) for r in basket.values()),
            "n_not_listed": sum(cint(r.n_not_listed) for r in basket.values()),
        },
        "diff": diff,
        "items": items,
        # Đẳng thức phải đúng về đại số (xem docstring đầu module). Còn số dư là
        # LỖI CODE, và phải nói ra chứ không được nuốt: một cầu nối "gần đúng" là
        # thứ khiến kế toán tin nhầm rồi chốt.
        "residual": residual,
        "balanced": abs(residual) <= EPS,
        "by_customer": _by_customer(customers, gl, basket),
    }


def _by_customer(customers, gl, basket):
    """Bóc theo từng PHÁP NHÂN của chuỗi.

    Một chuỗi có nhiều mã khách (Central Retail tối thiểu 2 pháp nhân EB, hạn
    thanh toán còn khác nhau 10 ngày). Chỗ lệch gần như luôn nằm gọn ở MỘT pháp
    nhân — cộng gộp cả chuỗi là giấu đúng manh mối đó đi.
    """
    names = sorted(set(customers) | set(gl) | set(basket))
    out = []
    for n in names:
        b = basket.get(n)
        out.append({
            "customer": n,
            "customer_name": (b.customer_name if b else None) or n,
            "gl": round(flt(gl.get(n)), 2),
            "listed": round(flt(b.listed) if b else 0.0, 2),
            "not_listed": round(flt(b.not_listed) if b else 0.0, 2),
            "n_listed": cint(b.n_listed) if b else 0,
            "n_not_listed": cint(b.n_not_listed) if b else 0,
        })
    out.sort(key=lambda r: -abs(r["gl"]))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def compare(company=None):
    """Bảng đối chiếu Excel ↔ sổ cái cho MỌI chuỗi. Read-only."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    from ketoan.install import MT_CHAINS

    docs = frappe.db.sql("""
        SELECT name, chain, status, cutover_date, opening_debt, no_invoice_amount,
               debt_carried, n_unmatched
        FROM `tab%s` WHERE company = %%(c)s
    """ % DOCTYPE, {"c": company}, as_dict=True)
    by_chain = {r.chain: r for r in docs}

    # MỘT truy vấn sổ cái cho mỗi NGÀY CHỐT khác nhau, không phải mỗi chuỗi.
    # Thực tế cả 7 chuỗi chốt cùng một ngày -> đúng một truy vấn.
    cust_of = {ch: chain_customers(ch) for ch in MT_CHAINS if by_chain.get(ch)}
    by_date = {}
    for ch, d in by_chain.items():
        if ch in cust_of:
            by_date.setdefault(cstr(d.cutover_date), []).extend(cust_of[ch])
    gl_all = {}
    for day, custs in by_date.items():
        gl_all.setdefault(day, {}).update(
            gl_balance_by_party(company, sorted(set(custs)), day))

    rows = []
    for ch in MT_CHAINS:
        d = by_chain.get(ch)
        if not d:
            rows.append({"chain": ch, "has_doc": False, "status": "",
                         "cutover_date": None, "debt_carried": None,
                         "gl": None, "diff": None, "n_customers": 0})
            continue
        custs = cust_of.get(ch) or []
        gl = gl_all.get(cstr(d.cutover_date)) or {}
        b = round(sum(flt(gl.get(c)) for c in custs), 2)
        a = flt(d.debt_carried)
        rows.append({
            "chain": ch, "has_doc": True, "name": d.name, "status": d.status,
            "cutover_date": cstr(d.cutover_date),
            "opening_debt": flt(d.opening_debt),
            "no_invoice_amount": flt(d.no_invoice_amount),
            "debt_carried": a, "gl": b, "diff": round(b - a, 2),
            "n_unmatched": cint(d.n_unmatched),
            "n_customers": len(custs),
        })

    done = [r for r in rows if r["has_doc"]]
    return {
        "rows": rows,
        "total_carried": round(sum(flt(r["debt_carried"]) for r in done), 2),
        "total_gl": round(sum(flt(r["gl"]) for r in done), 2),
        "total_diff": round(sum(flt(r["diff"]) for r in done), 2),
        "n_off": sum(1 for r in done if abs(flt(r["diff"])) > EPS),
        "can_manage": is_chief(),
        "note": _(
            "Vế Excel là CÔNG NỢ MANG SANG (nợ ròng trừ đơn đã giao chưa xuất hóa đơn) — "
            "đơn chưa có hóa đơn thì chưa có bút toán nên sổ cái không thể có chúng. Vế "
            "ERPNext là số dư TK phải thu trên sổ cái tính tại NGÀY CHỐT của chính chuỗi "
            "đó, CHƯA áp luật tất toán. Bấm từng chuỗi để xem chỗ lệch nằm ở đâu."
        ),
    }


@frappe.whitelist()
def chain_detail(name=None, chain=None, company=None):
    """Cầu nối đầy đủ cho MỘT chuỗi: bốn khoản mục + bóc theo pháp nhân. Read-only."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    if not name:
        if not chain:
            frappe.throw(_("Chưa chọn chuỗi để đối chiếu"))
        name = frappe.db.get_value(DOCTYPE, {"company": company, "chain": chain}, "name")
        if not name:
            frappe.throw(_(
                "Chuỗi {0} chưa nhập file số dư đầu kỳ — chưa có vế Excel nào để so."
            ).format(chain))

    doc = frappe.get_doc(DOCTYPE, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bản số dư {0} thuộc công ty khác").format(name))

    out = build_bridge(company, doc)
    out.update({
        "name": doc.name,
        "chain": doc.chain,
        "status": doc.status,
        "finalized": doc.status == STATUS_FINAL,
        "cutover_date": cstr(doc.cutover_date),
        "golive_date": cstr(doc.golive_date),
        "can_manage": is_chief(),
    })
    return out
