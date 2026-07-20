"""Whitelisted methods — Đối chiếu công nợ kênh NPP.

- get_debts: công nợ từng NPP (số dư GL phải thu), DS bình quân tháng, số cần
  thanh toán theo chính sách (thường / Tết).
- get_discount_eligible / create_discount_entries: chương trình chiết khấu theo
  THÁNG — NPP có DOANH SỐ THÁNG (debit 131 từ Sales Invoice) ≥ ngưỡng → chiết khấu
  = % × doanh số tháng; tạo bút toán (Nợ 6412 / Có 131) DRAFT, chống trùng theo
  marker [CK2-<customer>-<YYYY-MM>] ghi trong trường remark.
Read-only trừ create_discount_entries (ghi DRAFT). Guard ở dòng đầu, SQL parameterized.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import (
    flt, today, getdate, get_first_day, get_last_day,
    formatdate, money_in_words, escape_html,
)

from ketoan.api._guard import guard_npp, guard_sales_any, resolve_company, get_settings
from ketoan.utils import je_remark_field, format_vnd


def _cfg() -> dict:
    """Tham số NPP từ Ketoan Portal Settings (kèm default an toàn)."""
    s = get_settings()
    return {
        "group": s.npp_customer_group or "NPP",
        "due_days": int(s.invoice_due_days or 30),
        "threshold": flt(s.discount_threshold) or 100000000.0,
        "discount_pct": flt(s.discount_percent) or 2.0,
        "tet_start_month": int(s.tet_start_month or 11),
        "tet_pct": flt(s.tet_payment_percent) or 50.0,
        "receivable_account": s.receivable_account or None,
        "discount_expense_account": s.discount_expense_account or None,
        # Chính sách thanh toán & phạt thưởng. Ân hạn / % phạt cho phép giá trị 0
        # hợp lệ → chỉ fallback khi field CHƯA đặt (None).
        "pay_window_start": int(s.get("pay_window_start") or 5),
        "pay_window_end": int(s.get("pay_window_end") or 10),
        "grace_days": _int_or(s.get("pay_grace_days"), 5),
        "penalty_days": int(s.get("pay_penalty_days") or 10),
        "penalty_pct": _flt_or(s.get("pay_penalty_percent"), 50.0),
    }


def _int_or(v, default: int) -> int:
    return int(v) if v not in (None, "") else default


def _flt_or(v, default: float) -> float:
    return flt(v) if v not in (None, "") else default


def _penalty_tier(late_days, cfg: dict) -> dict:
    """Phân mức phạt thưởng theo số ngày TRẢ CHẬM (so hạn hóa đơn).

    ≤ ân hạn        → full  (giữ 100% thưởng)
    (ân hạn, mốc]   → half  (phạt penalty_pct% → giữ phần còn lại)
    > mốc           → cut   (cắt toàn bộ thưởng của tháng)
    """
    g, p = cfg["grace_days"], cfg["penalty_days"]
    if late_days is None or late_days <= g:
        return {"tier": "full", "keep": 1.0, "label": "Đúng hạn", "sev": "ok"}
    if late_days <= p:
        keep = max(0.0, 1.0 - cfg["penalty_pct"] / 100.0)
        return {"tier": "half", "keep": keep,
                "label": f"Trả chậm {late_days} ngày — phạt {cfg['penalty_pct']:.0f}% thưởng", "sev": "warning"}
    return {"tier": "cut", "keep": 0.0,
            "label": f"Trả chậm {late_days} ngày (>{p}) — cắt thưởng", "sev": "danger"}


def _policy(cfg: dict):
    """Trả về (policy, tet_start_date). Tết khi tháng >= tet_start_month hoặc <= 2."""
    t = getdate(today())
    start_m = cfg["tet_start_month"]
    is_tet = (t.month >= start_m) or (t.month <= 2)
    if is_tet:
        tet_year = t.year if t.month >= start_m else t.year - 1
        return "tet", f"{tet_year}-{start_m:02d}-01"
    return "normal", None


def _receivable_clause(cfg: dict, params: dict) -> str:
    """Mệnh đề lọc TK phải thu cho GL: account cụ thể hoặc account_type Receivable."""
    if cfg["receivable_account"]:
        params["racc"] = cfg["receivable_account"]
        return "gle.account = %(racc)s"
    return "acc.account_type = 'Receivable'"


def _npp_customers(cfg: dict):
    return frappe.get_all(
        "Customer",
        filters={"customer_group": cfg["group"], "disabled": 0},
        fields=["name", "customer_name", "mobile_no"],
    )


def _month_range(month: str | None):
    """month='YYYY-MM' → (first_day, last_day, 'YYYY-MM'). Mặc định tháng hiện tại."""
    if month:
        y, m = [int(x) for x in month.split("-")[:2]]
        d = getdate(f"{y}-{m:02d}-01")
    else:
        d = getdate(today())
    first = get_first_day(d)
    last = get_last_day(d)
    return str(first), str(last), f"{first.year}-{first.month:02d}"


def _marker(customer: str, month_key: str) -> str:
    """Khóa chống trùng bút toán chiết khấu — ghi thẳng vào trường remark của Journal Entry."""
    return f"[CK2-{customer}-{month_key}]"


def _existing_discount_je(month_key: str) -> dict:
    """Map marker -> tên JE chiết khấu đã tạo trong tháng (dò trong field remark)."""
    field = je_remark_field()
    candidates = frappe.get_all(
        "Journal Entry",
        filters={field: ["like", f"%-{month_key}]%"], "docstatus": ["<", 2]},
        fields=["name", field],
    )
    pattern = re.compile(r"\[CK2-.*-" + re.escape(month_key) + r"\]")
    ex = {}
    for c in candidates:
        m = pattern.search(c.get(field) or "")
        if m:
            ex[m.group(0)] = c.name
    return ex


def _month_sales(company: str, names: tuple, first: str, last: str, cfg: dict) -> dict:
    """Doanh số THUẦN tháng theo NPP = SUM(debit − credit) TK phải thu từ Sales
    Invoice trong tháng — net hàng trả về (credit note cùng voucher_type) và loại
    hóa đơn số dư đầu kỳ (is_opening)."""
    params = {"company": company, "names": names, "first": first, "last": last}
    rclause = _receivable_clause(cfg, params)
    rows = frappe.db.sql(
        f"""
        SELECT gle.party AS customer, SUM(gle.debit - gle.credit) AS sales
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND gle.party_type = 'Customer' AND gle.party IN %(names)s
          AND gle.voucher_type = 'Sales Invoice'
          AND IFNULL(gle.is_opening, 'No') != 'Yes'
          AND gle.posting_date BETWEEN %(first)s AND %(last)s
          AND {rclause}
        GROUP BY gle.party
        """,
        params,
        as_dict=True,
    )
    return {r.customer: flt(r.sales) for r in rows}


def _current_overdue(company: str, names: tuple, cfg: dict) -> dict:
    """Số ngày TRẢ CHẬM hiện tại của từng NPP = max(today − hạn) trên các hóa đơn
    còn nợ đã đến hạn. Hạn = due_date (nếu có) hoặc posting + due_days."""
    rows = frappe.db.sql(
        """
        SELECT customer,
               MAX(DATEDIFF(%(today)s, COALESCE(due_date, DATE_ADD(posting_date, INTERVAL %(dd)s DAY)))) AS late
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND customer IN %(names)s
          AND IFNULL(is_return, 0) = 0 AND outstanding_amount > 0.5
        GROUP BY customer
        """,
        {"company": company, "names": names, "today": today(), "dd": cfg["due_days"]},
        as_dict=True,
    )
    return {r.customer: int(r.late or 0) for r in rows}


def _month_payment_lateness(company: str, names: tuple, first: str, last: str, cfg: dict) -> dict:
    """Số ngày trả chậm TỆ NHẤT của hóa đơn PHÁT SINH trong tháng M (dùng cho phạt
    thưởng của tháng đó): với HĐ còn nợ → today − hạn; HĐ đã tất toán → ngày thanh
    toán cuối (Payment Entry) − hạn; lấy MAX, kẹp ≥ 0."""
    rows = frappe.db.sql(
        """
        SELECT si.customer,
               MAX(GREATEST(
                 DATEDIFF(
                   CASE WHEN si.outstanding_amount > 0.5 THEN %(today)s
                        -- Đã tất toán: dùng ngày Payment Entry; nếu tất toán bằng JE/bù
                        -- trừ (không có PE) thì coi như ĐÚNG HẠN (không phạt oan).
                        ELSE COALESCE(lp.pdate, si.due_date,
                                      DATE_ADD(si.posting_date, INTERVAL %(dd)s DAY)) END,
                   COALESCE(si.due_date, DATE_ADD(si.posting_date, INTERVAL %(dd)s DAY))
                 ), 0)) AS late
        FROM `tabSales Invoice` si
        LEFT JOIN (
          SELECT per.reference_name AS rn, MAX(pe.posting_date) AS pdate
          FROM `tabPayment Entry Reference` per
          JOIN `tabPayment Entry` pe ON pe.name = per.parent
          WHERE pe.docstatus = 1 AND per.reference_doctype = 'Sales Invoice'
          GROUP BY per.reference_name
        ) lp ON lp.rn = si.name
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.customer IN %(names)s
          AND IFNULL(si.is_return, 0) = 0 AND si.base_grand_total > 0
          AND si.posting_date BETWEEN %(first)s AND %(last)s
        GROUP BY si.customer
        """,
        {"company": company, "names": names, "first": first, "last": last,
         "today": today(), "dd": cfg["due_days"]},
        as_dict=True,
    )
    return {r.customer: int(r.late or 0) for r in rows}


@frappe.whitelist()
def get_debts(company: str | None = None) -> dict:
    """Bảng đối chiếu công nợ NPP + chính sách thanh toán."""
    guard_npp()
    company = resolve_company(company)
    cfg = _cfg()
    policy, tet_start = _policy(cfg)

    customers = _npp_customers(cfg)
    if not customers:
        return {
            "company": company, "policy": policy, "tet_start": tet_start,
            "config": {"due_days": cfg["due_days"], "tet_pct": cfg["tet_pct"], "group": cfg["group"]},
            "rows": [], "total_debt": 0, "total_required": 0,
            "note": _("Không tìm thấy khách trong nhóm '{0}'").format(cfg["group"]),
        }

    names = tuple(c.name for c in customers)
    base = {"company": company, "names": names, "today": today()}

    # 1) Công nợ theo GL phải thu (số dư = debit - credit).
    rparams = dict(base)
    rclause = _receivable_clause(cfg, rparams)
    debt_rows = frappe.db.sql(
        f"""
        SELECT gle.party AS customer, SUM(gle.debit - gle.credit) AS debt
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND gle.party_type = 'Customer' AND gle.party IN %(names)s
          AND {rclause}
        GROUP BY gle.party
        """,
        rparams,
        as_dict=True,
    )
    debt = {r.customer: flt(r.debt) for r in debt_rows}

    # 2) Doanh số bình quân tháng (trailing 365 ngày / 12), loại opening/return.
    sales_rows = frappe.db.sql(
        """
        SELECT customer, SUM(base_grand_total) AS rev
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND customer IN %(names)s
          AND IFNULL(is_opening,'No') != 'Yes' AND IFNULL(is_return,0) = 0
          AND posting_date >= DATE_SUB(%(today)s, INTERVAL 365 DAY)
        GROUP BY customer
        """,
        base,
        as_dict=True,
    )
    monthly = {r.customer: flt(r.rev) / 12.0 for r in sales_rows}

    # 3) requiredPayment theo chính sách.
    if policy == "normal":
        # Chốt đơn cần thanh toán = outstanding của HĐ ĐÃ ĐẾN HẠN (quá hạn HĐ,
        # tức đơn đến hạn 30 ngày chốt vào kỳ thu 5–10 hàng tháng).
        params = dict(base, due_days=cfg["due_days"])
        over_rows = frappe.db.sql(
            """
            SELECT customer, SUM(outstanding_amount) AS overdue
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s AND customer IN %(names)s
              AND outstanding_amount > 0 AND IFNULL(is_return, 0) = 0
              AND DATEDIFF(%(today)s, COALESCE(due_date, DATE_ADD(posting_date, INTERVAL %(due_days)s DAY))) >= 0
            GROUP BY customer
            """,
            params,
            as_dict=True,
        )
        overdue = {r.customer: flt(r.overdue) for r in over_rows}
        tet_total = {}
    else:
        params = dict(base, tet_start=tet_start)
        tet_rows = frappe.db.sql(
            """
            SELECT customer, SUM(grand_total) AS tet_total
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s AND customer IN %(names)s
              AND grand_total > 0 AND posting_date >= %(tet_start)s
            GROUP BY customer
            """,
            params,
            as_dict=True,
        )
        tet_total = {r.customer: flt(r.tet_total) for r in tet_rows}
        overdue = {}

    # 4) Số ngày trả chậm hiện tại → mức ảnh hưởng thưởng (cảnh báo cho kế toán).
    overdue_days = _current_overdue(company, names, cfg)

    rows = []
    total_debt = 0.0
    total_required = 0.0
    late_count = 0
    for c in customers:
        d = debt.get(c.name, 0.0)
        if policy == "normal":
            required = overdue.get(c.name, 0.0)
        else:
            allowed = tet_total.get(c.name, 0.0) * cfg["tet_pct"] / 100.0
            required = max(0.0, d - allowed)
        required = min(required, max(d, 0.0))

        if d < -0.5:
            status = "negative"
        elif required > 0.5:
            status = "due"
        else:
            status = "normal"

        # CẢNH BÁO SỚM (real-time) theo mức trả chậm HIỆN TẠI của HĐ còn nợ —
        # KHÁC với mức phạt chính thức (tính theo HĐ từng THÁNG ở tab Chiết khấu).
        late = overdue_days.get(c.name, 0)
        tier = _penalty_tier(late, cfg)
        if tier["tier"] == "half":
            impact = f"Đang trễ {late} ngày — nguy cơ phạt {cfg['penalty_pct']:.0f}% thưởng"
            late_count += 1
        elif tier["tier"] == "cut":
            impact = f"Đang trễ {late} ngày (>{cfg['penalty_days']}) — nguy cơ cắt thưởng"
            late_count += 1
        else:
            impact = ""

        rows.append({
            "customer": c.name,
            "customer_name": c.customer_name or c.name,
            "mobile_no": c.mobile_no,
            "debt": d,
            "monthly_sales": monthly.get(c.name, 0.0),
            "required_payment": required,
            "status": status,
            "overdue_days": late,
            "bonus_tier": tier["tier"],
            "bonus_impact": impact,
            "bonus_sev": tier["sev"],
        })
        total_debt += d
        total_required += required

    rows.sort(key=lambda r: r["debt"], reverse=True)
    return {
        "company": company,
        "policy": policy,
        "tet_start": tet_start,
        "config": {
            "due_days": cfg["due_days"], "tet_pct": cfg["tet_pct"], "group": cfg["group"],
            "pay_window_start": cfg["pay_window_start"], "pay_window_end": cfg["pay_window_end"],
            "grace_days": cfg["grace_days"], "penalty_days": cfg["penalty_days"],
            "penalty_pct": cfg["penalty_pct"], "discount_pct": cfg["discount_pct"],
        },
        "rows": rows,
        "total_debt": total_debt,
        "total_required": total_required,
        "late_count": late_count,
    }


@frappe.whitelist()
def get_discount_eligible(company: str | None = None, month: str | None = None) -> dict:
    """NPP đủ điều kiện chiết khấu trong THÁNG: doanh số tháng ≥ ngưỡng → % doanh số."""
    guard_npp()
    company = resolve_company(company)
    cfg = _cfg()
    first, last, mkey = _month_range(month)

    cfg_out = {
        "threshold": cfg["threshold"],
        "discount_pct": cfg["discount_pct"],
        "grace_days": cfg["grace_days"],
        "penalty_days": cfg["penalty_days"],
        "penalty_pct": cfg["penalty_pct"],
        "discount_account_set": bool(cfg["discount_expense_account"] and cfg["receivable_account"]),
    }
    customers = _npp_customers(cfg)
    if not customers:
        return {"company": company, "month": mkey, "config": cfg_out, "rows": [], "total_discount": 0}

    names = tuple(c.name for c in customers)
    sales = _month_sales(company, names, first, last, cfg)
    # Trả chậm của HĐ phát sinh trong tháng → phạt thưởng.
    lateness = _month_payment_lateness(company, names, first, last, cfg)

    # JE chiết khấu đã tạo cho tháng này (để khóa, tránh tạo trùng) — dò trong remark.
    ex_map = _existing_discount_je(mkey)

    rows = []
    for c in customers:
        s = sales.get(c.name, 0.0)
        if s < cfg["threshold"]:
            continue
        base_amount = round(s * cfg["discount_pct"] / 100.0)
        late = lateness.get(c.name, 0)
        tier = _penalty_tier(late, cfg)
        disc = round(base_amount * tier["keep"])
        je_name = ex_map.get(_marker(c.name, mkey))
        if je_name:
            status = "created"
        elif tier["tier"] == "cut" or disc <= 0:
            status = "cut"
        else:
            status = "pending"
        rows.append({
            "customer": c.name,
            "customer_name": c.customer_name or c.name,
            "monthly_sales": s,
            "base_amount": base_amount,
            "discount_amount": disc,
            "overdue_days": late,
            "tier": tier["tier"],
            "penalty_label": tier["label"],
            "penalty_sev": tier["sev"],
            "status": status,
            "je_name": je_name,
            "route": f"/desk/journal-entry/{je_name}" if je_name else None,
        })

    rows.sort(key=lambda r: r["monthly_sales"], reverse=True)
    return {
        "company": company,
        "month": mkey,
        "config": cfg_out,
        "rows": rows,
        "total_discount": sum(r["discount_amount"] for r in rows),
    }


@frappe.whitelist()
def create_discount_entries(customers, month: str | None = None, company: str | None = None) -> dict:
    """Tạo bút toán chiết khấu (Nợ 6412 / Có 131) theo doanh số THÁNG — DRAFT.

    Server tự tính chiết khấu từ doanh số tháng thật (không tin client). Khóa
    chống trùng theo marker [CK2-<customer>-<YYYY-MM>] trong trường remark.
    """
    guard_npp()
    company = resolve_company(company)
    cfg = _cfg()

    if not cfg["discount_expense_account"] or not cfg["receivable_account"]:
        frappe.throw(_("Chưa cấu hình TK chi phí chiết khấu / TK phải thu trong Ketoan Portal Settings"))

    if isinstance(customers, str):
        customers = json.loads(customers)
    if not customers:
        frappe.throw(_("Chưa chọn NPP nào"))

    first, last, mkey = _month_range(month)
    names = tuple(customers)
    sales = _month_sales(company, names, first, last, cfg)
    lateness = _month_payment_lateness(company, names, first, last, cfg)

    existing = set(_existing_discount_je(mkey).keys())

    created = []
    skipped = []
    for cust in customers:
        s = sales.get(cust, 0.0)
        if s < cfg["threshold"]:
            skipped.append({"customer": cust, "reason": "Doanh số tháng dưới ngưỡng"})
            continue
        mk = _marker(cust, mkey)
        if mk in existing:
            skipped.append({"customer": cust, "reason": "Đã có bút toán tháng này"})
            continue
        # Server tự áp phạt thưởng theo mức trả chậm (không tin client).
        tier = _penalty_tier(lateness.get(cust, 0), cfg)
        amount = round(round(s * cfg["discount_pct"] / 100.0) * tier["keep"])
        if tier["tier"] == "cut" or amount <= 0:
            skipped.append({"customer": cust, "reason": tier["label"] if tier["tier"] != "full" else "Chiết khấu = 0"})
            continue
        penalty_note = "" if tier["tier"] == "full" else f" ({tier['label']})"

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = last
        je.company = company
        # Ghi thẳng vào trường remark: marker chống trùng + diễn giải + ghi chú phạt.
        je.set(je_remark_field(), f"{mk} Chiết khấu {cfg['discount_pct']}% doanh số tháng {mkey} — {cust}{penalty_note}")
        je.append("accounts", {
            "account": cfg["discount_expense_account"],
            "debit_in_account_currency": amount,
        })
        je.append("accounts", {
            "account": cfg["receivable_account"],
            "credit_in_account_currency": amount,
            "party_type": "Customer",
            "party": cust,
        })
        je.insert()
        created.append({
            "customer": cust, "name": je.name, "amount": amount,
            "route": f"/desk/journal-entry/{je.name}",
        })

    return {"created": created, "skipped": skipped, "count": len(created), "month": mkey}


# ═══════════════════════════════════════════════════════════════════════════
# Xuất biên bản đối chiếu công nợ (PDF) gửi NPP — đơn lẻ & hàng loạt
# ═══════════════════════════════════════════════════════════════════════════

_RECON_STYLE = """
* { font-family: "Be Vietnam Pro","DejaVu Sans",Arial,sans-serif; }
body { color:#1e293b; font-size:12px; }
h1 { text-align:center; font-size:18px; margin:4px 0; }
.sub { text-align:center; color:#555; margin-bottom:14px; font-size:12px; }
.meta { margin:10px 0; line-height:1.7; }
.meta b { display:inline-block; min-width:130px; }
table.gl { width:100%; border-collapse:collapse; margin-top:8px; }
table.gl th, table.gl td { border:1px solid #cbd5e1; padding:6px 8px; font-size:11px; }
table.gl th { background:#f1f5f9; text-align:left; }
.num { text-align:right; white-space:nowrap; }
.tot td { font-weight:bold; background:#f8fafc; }
.words { font-style:italic; margin:8px 0 18px; }
.sign { width:100%; margin-top:26px; border:none; }
.sign td { border:none; text-align:center; vertical-align:top; width:50%; font-size:12px; }
.sign .role { font-weight:bold; }
.sign .hint { color:#777; font-size:10px; }
.pagebreak { page-break-after:always; }
"""


def _recon_default_period(to_date: str | None):
    to_date = to_date or today()
    from_date = str(getdate(to_date).replace(month=1, day=1))
    return from_date, to_date


def _recon_fragment(company_name: str, customer: str, from_date: str, to_date: str, cfg: dict) -> str:
    """HTML 1 biên bản đối chiếu cho 1 khách (không kèm <html>/<style>)."""
    # Số dư đầu kỳ
    op_params = {"company": cfg["_company"], "customer": customer, "from": from_date}
    op_clause = _receivable_clause(cfg, op_params)
    opening = flt(
        frappe.db.sql(
            f"""
            SELECT SUM(gle.debit - gle.credit)
            FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
              AND gle.party_type = 'Customer' AND gle.party = %(customer)s
              AND {op_clause} AND gle.posting_date < %(from)s
            """,
            op_params,
        )[0][0]
        or 0
    )

    # Phát sinh trong kỳ
    pr_params = {"company": cfg["_company"], "customer": customer, "from": from_date, "to": to_date}
    pr_clause = _receivable_clause(cfg, pr_params)
    entries = frappe.db.sql(
        f"""
        SELECT gle.posting_date, gle.voucher_type, gle.voucher_no, gle.remarks,
               gle.debit, gle.credit
        FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND gle.party_type = 'Customer' AND gle.party = %(customer)s
          AND {pr_clause} AND gle.posting_date BETWEEN %(from)s AND %(to)s
        ORDER BY gle.posting_date ASC, gle.creation ASC
        """,
        pr_params,
        as_dict=True,
    )

    info = frappe.db.get_value(
        "Customer", customer, ["customer_name", "tax_id", "mobile_no"], as_dict=True
    ) or {}

    total_debit = sum(flt(e.debit) for e in entries)
    total_credit = sum(flt(e.credit) for e in entries)
    closing = opening + total_debit - total_credit

    running = opening
    rows = []
    for e in entries:
        running += flt(e.debit) - flt(e.credit)
        rows.append(
            "<tr>"
            f"<td>{formatdate(e.posting_date)}</td>"
            f"<td>{escape_html(e.voucher_no or '')}</td>"
            f"<td>{escape_html((e.remarks or e.voucher_type or '')[:80])}</td>"
            f"<td class='num'>{format_vnd(e.debit) if flt(e.debit) else ''}</td>"
            f"<td class='num'>{format_vnd(e.credit) if flt(e.credit) else ''}</td>"
            f"<td class='num'>{format_vnd(running)}</td>"
            "</tr>"
        )
    rows_html = "".join(rows) or "<tr><td colspan='6' style='text-align:center;color:#888'>Không có phát sinh trong kỳ</td></tr>"

    cust_name = escape_html(info.get("customer_name") or customer)
    tax = escape_html(info.get("tax_id") or "")
    phone = escape_html(info.get("mobile_no") or "")
    closing_words = money_in_words(abs(closing), "VND")

    return f"""
    <div style="text-align:center;font-weight:bold;font-size:13px">{escape_html(company_name)}</div>
    <h1>BIÊN BẢN ĐỐI CHIẾU CÔNG NỢ</h1>
    <div class="sub">Kỳ: {formatdate(from_date)} — {formatdate(to_date)}</div>
    <div class="meta">
      <div><b>Khách hàng:</b> {cust_name}</div>
      {f'<div><b>Mã số thuế:</b> {tax}</div>' if tax else ''}
      {f'<div><b>Điện thoại:</b> {phone}</div>' if phone else ''}
      <div><b>Dư nợ đầu kỳ:</b> {format_vnd(opening)}</div>
    </div>
    <table class="gl">
      <thead><tr><th>Ngày</th><th>Chứng từ</th><th>Diễn giải</th><th class="num">Phát sinh nợ</th><th class="num">Đã thanh toán</th><th class="num">Lũy kế</th></tr></thead>
      <tbody>
        <tr class="tot"><td colspan="5">Dư nợ đầu kỳ</td><td class="num">{format_vnd(opening)}</td></tr>
        {rows_html}
        <tr class="tot"><td colspan="3">Cộng phát sinh</td><td class="num">{format_vnd(total_debit)}</td><td class="num">{format_vnd(total_credit)}</td><td></td></tr>
        <tr class="tot"><td colspan="5">Dư nợ cuối kỳ</td><td class="num">{format_vnd(closing)}</td></tr>
      </tbody>
    </table>
    <div class="words">Số tiền còn phải thu bằng chữ: {closing_words}</div>
    <p>Hai bên thống nhất số liệu công nợ nêu trên là đúng và đầy đủ tính đến ngày {formatdate(to_date)}.</p>
    <table class="sign"><tr>
      <td><div class="role">ĐẠI DIỆN KHÁCH HÀNG</div><div class="hint">(Ký, ghi rõ họ tên, đóng dấu)</div></td>
      <td><div class="role">ĐẠI DIỆN {escape_html(company_name.upper())}</div><div class="hint">(Ký, ghi rõ họ tên, đóng dấu)</div></td>
    </tr></table>
    """


def _recon_document(fragments: list) -> str:
    body = '<div class="pagebreak"></div>'.join(fragments)
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{_RECON_STYLE}</style></head><body>{body}</body></html>'


def _render_pdf_download(html: str, filename: str):
    from frappe.utils.pdf import get_pdf
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = get_pdf(html, options={"orientation": "Portrait"})
    frappe.local.response.type = "download"


@frappe.whitelist()
def export_reconciliation(customer: str, from_date: str | None = None, to_date: str | None = None, company: str | None = None):
    """Xuất biên bản đối chiếu công nợ 1 khách ra PDF (download).

    Mở cho mọi kế toán kênh bán hàng — nhưng khách phải thuộc kênh của mình
    (dùng chung từ 360° khách: NPP, MT, Du lịch/Khác).
    """
    guard_sales_any()
    company = resolve_company(company)
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Khách hàng không tồn tại"))
    from ketoan.api.receivables import _assert_customer_channel
    _assert_customer_channel(customer)
    from_date, to_date = (from_date or _recon_default_period(to_date)[0]), (to_date or today())

    cfg = _cfg()
    cfg["_company"] = company
    company_name = frappe.db.get_value("Company", company, "company_name") or company
    html = _recon_document([_recon_fragment(company_name, customer, from_date, to_date, cfg)])

    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", customer)[:40]
    _render_pdf_download(html, f"DoiChieuCongNo_{safe}_{to_date}.pdf")


@frappe.whitelist()
def export_reconciliation_bulk(customers, from_date: str | None = None, to_date: str | None = None, company: str | None = None):
    """Xuất biên bản đối chiếu hàng loạt nhiều NPP vào 1 PDF (mỗi khách 1 trang)."""
    guard_npp()
    company = resolve_company(company)
    if isinstance(customers, str):
        customers = json.loads(customers)
    customers = [c for c in (customers or []) if frappe.db.exists("Customer", c)]
    if not customers:
        frappe.throw(_("Chưa chọn NPP hợp lệ nào"))
    if len(customers) > 200:
        frappe.throw(_("Tối đa 200 NPP mỗi lần xuất"))
    from_date, to_date = (from_date or _recon_default_period(to_date)[0]), (to_date or today())

    cfg = _cfg()
    cfg["_company"] = company
    company_name = frappe.db.get_value("Company", company, "company_name") or company
    fragments = [_recon_fragment(company_name, c, from_date, to_date, cfg) for c in customers]
    html = _recon_document(fragments)

    _render_pdf_download(html, f"DoiChieuCongNo_{len(customers)}NPP_{to_date}.pdf")
