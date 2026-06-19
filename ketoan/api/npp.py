"""Whitelisted methods — Đối chiếu công nợ kênh NPP.

Tái hiện nghiệp vụ trang "Đối chiếu Công nợ NPP":
- Công nợ từng NPP (GL receivable), doanh số bình quân tháng, số cần thanh toán
  theo chính sách (thường / Tết).
- Chiết khấu: NPP có công nợ ≥ ngưỡng → tạo bút toán chiết khấu (Nợ 6412 / Có 131),
  DRAFT, human-in-loop.
Read-only trừ create_discount_entries (ghi DRAFT). Guard ở dòng đầu, SQL parameterized.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, today, getdate

from ketoan.api._guard import guard_view, resolve_company, get_settings, is_manager


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
    }


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


@frappe.whitelist()
def get_debts(company: str | None = None) -> dict:
    """Bảng đối chiếu công nợ NPP + chính sách + cấu hình chiết khấu."""
    guard_view()
    company = resolve_company(company)
    cfg = _cfg()
    policy, tet_start = _policy(cfg)

    customers = frappe.get_all(
        "Customer",
        filters={"customer_group": cfg["group"], "disabled": 0},
        fields=["name", "customer_name", "mobile_no"],
    )
    if not customers:
        return {
            "company": company, "policy": policy, "tet_start": tet_start, "config": cfg,
            "rows": [], "total_debt": 0, "total_required": 0,
            "note": _("Không tìm thấy khách trong nhóm '{0}'").format(cfg["group"]),
        }

    names = tuple(c.name for c in customers)
    base = {"company": company, "names": names, "today": today()}

    # 1) Công nợ theo GL phải thu (số dư sổ cái = debit - credit).
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

    # 3) Số liệu phục vụ requiredPayment.
    if policy == "normal":
        params = dict(base, due_days=cfg["due_days"])
        over_rows = frappe.db.sql(
            """
            SELECT customer, SUM(outstanding_amount) AS overdue
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s AND customer IN %(names)s
              AND outstanding_amount > 0
              AND DATEDIFF(%(today)s, COALESCE(due_date, posting_date)) > %(due_days)s
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

    rows = []
    total_debt = 0.0
    total_required = 0.0
    for c in customers:
        d = debt.get(c.name, 0.0)
        if policy == "normal":
            required = overdue.get(c.name, 0.0)
        else:
            allowed = tet_total.get(c.name, 0.0) * cfg["tet_pct"] / 100.0
            required = max(0.0, d - allowed)
        required = min(required, max(d, 0.0))  # không đòi quá số đang nợ

        if d < -0.5:
            status = "negative"
        elif required > 0.5:
            status = "due"
        else:
            status = "normal"

        rows.append({
            "customer": c.name,
            "customer_name": c.customer_name or c.name,
            "mobile_no": c.mobile_no,
            "debt": d,
            "monthly_sales": monthly.get(c.name, 0.0),
            "required_payment": required,
            "discount_eligible": d >= cfg["threshold"],
            "discount_amount": round(d * cfg["discount_pct"] / 100.0) if d >= cfg["threshold"] else 0,
            "status": status,
        })
        total_debt += d
        total_required += required

    rows.sort(key=lambda r: r["debt"], reverse=True)
    return {
        "company": company,
        "policy": policy,
        "tet_start": tet_start,
        "config": {
            "threshold": cfg["threshold"],
            "discount_pct": cfg["discount_pct"],
            "due_days": cfg["due_days"],
            "tet_pct": cfg["tet_pct"],
            "group": cfg["group"],
            "discount_account_set": bool(cfg["discount_expense_account"] and cfg["receivable_account"]),
        },
        "rows": rows,
        "total_debt": total_debt,
        "total_required": total_required,
    }


@frappe.whitelist()
def create_discount_entries(customers, company: str | None = None) -> dict:
    """Tạo bút toán chiết khấu (Nợ 6412 / Có 131) cho danh sách NPP — DRAFT.

    customers: JSON list tên Customer. Server tự tính chiết khấu từ công nợ thật
    (không tin số client gửi). Cần cấu hình TK chiết khấu + TK phải thu ở Settings.
    """
    guard_view()
    company = resolve_company(company)
    cfg = _cfg()

    if not cfg["discount_expense_account"] or not cfg["receivable_account"]:
        frappe.throw(_("Chưa cấu hình TK chi phí chiết khấu / TK phải thu trong Ketoan Portal Settings"))

    if isinstance(customers, str):
        customers = json.loads(customers)
    if not customers:
        frappe.throw(_("Chưa chọn NPP nào"))

    names = tuple(customers)
    rparams = {"company": company, "names": names}
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

    created = []
    skipped = []
    for cust in customers:
        d = debt.get(cust, 0.0)
        if d < cfg["threshold"]:
            skipped.append({"customer": cust, "reason": "Dưới ngưỡng chiết khấu"})
            continue
        amount = round(d * cfg["discount_pct"] / 100.0)
        if amount <= 0:
            skipped.append({"customer": cust, "reason": "Chiết khấu = 0"})
            continue

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = today()
        je.company = company
        je.user_remark = f"Chiết khấu {cfg['discount_pct']}% công nợ NPP — {cust}"
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
        je.insert()  # tôn trọng permission JE của user
        created.append({
            "customer": cust,
            "name": je.name,
            "amount": amount,
            "route": f"/app/journal-entry/{je.name}",
        })

    return {"created": created, "skipped": skipped, "count": len(created)}
