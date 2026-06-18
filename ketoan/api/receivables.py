"""Whitelisted methods — phân hệ Phải thu (công nợ NPP/khách hàng).

Semantics (theo frappe-sales-analytics):
- Công nợ = `Sales Invoice.outstanding_amount` (docstatus=1) — ERPNext tự duy trì
  sau khi phân bổ thanh toán. KHÔNG lọc `is_opening` (nợ đầu kỳ là nợ thật).
- Aging theo `COALESCE(due_date, posting_date)` so với hôm nay.
- DSO ≈ nợ / doanh thu kỳ × số ngày cửa sổ.
Tất cả read-only, guard ở dòng đầu, SQL parameterized.
"""

import frappe
from frappe.utils import flt, today, getdate

from ketoan.api._guard import guard_view, resolve_company, get_settings


@frappe.whitelist()
def get_ar_summary(company: str | None = None, limit: int = 200) -> dict:
    """Bảng kê công nợ phải thu theo khách hàng + tổng.

    Trả: {total, count, rows:[{customer, customer_name, customer_group,
    outstanding, earliest_due, days_overdue}]}.
    """
    guard_view()
    company = resolve_company(company)
    limit = min(int(limit or 200), 1000)

    # Gộp ở mức khách: tổng outstanding + chứng từ quá hạn lâu nhất.
    # Dùng SQL (group + aggregate) thay ORM cho gọn 1 round-trip.
    rows = frappe.db.sql(
        """
        SELECT si.customer,
               si.customer_name,
               c.customer_group,
               SUM(si.outstanding_amount)              AS outstanding,
               MIN(COALESCE(si.due_date, si.posting_date)) AS earliest_due
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.outstanding_amount > 0
        GROUP BY si.customer, si.customer_name, c.customer_group
        ORDER BY SUM(si.outstanding_amount) DESC
        LIMIT %(limit)s
        """,
        {"company": company, "limit": limit},
        as_dict=True,
    )

    t = getdate(today())
    total = 0.0
    for r in rows:
        r["outstanding"] = flt(r["outstanding"])
        total += r["outstanding"]
        r["days_overdue"] = (t - getdate(r["earliest_due"])).days if r["earliest_due"] else 0

    return {"company": company, "total": total, "count": len(rows), "rows": rows}


@frappe.whitelist()
def get_aging(company: str | None = None) -> dict:
    """Tuổi nợ theo rổ cấu hình (Settings): trong hạn / 1-b1 / b1-b2 / b2-b3 / >b3."""
    guard_view()
    company = resolve_company(company)
    s = get_settings()
    b1, b2, b3 = int(s.aging_bucket_1 or 30), int(s.aging_bucket_2 or 60), int(s.aging_bucket_3 or 90)

    # Bucket bằng CASE trên số ngày quá hạn (DATEDIFF), tham số hoá ngưỡng.
    row = frappe.db.sql(
        """
        SELECT
          SUM(CASE WHEN d <= 0                 THEN o ELSE 0 END) AS current_amt,
          SUM(CASE WHEN d > 0  AND d <= %(b1)s THEN o ELSE 0 END) AS b1_amt,
          SUM(CASE WHEN d > %(b1)s AND d <= %(b2)s THEN o ELSE 0 END) AS b2_amt,
          SUM(CASE WHEN d > %(b2)s AND d <= %(b3)s THEN o ELSE 0 END) AS b3_amt,
          SUM(CASE WHEN d > %(b3)s             THEN o ELSE 0 END) AS over_amt,
          SUM(o) AS total_amt
        FROM (
            SELECT outstanding_amount AS o,
                   DATEDIFF(%(today)s, COALESCE(due_date, posting_date)) AS d
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
        ) t
        """,
        {"company": company, "today": today(), "b1": b1, "b2": b2, "b3": b3},
        as_dict=True,
    )[0]

    buckets = [
        {"key": "current", "label": "Trong hạn", "amount": flt(row.current_amt)},
        {"key": "b1", "label": f"1–{b1} ngày", "amount": flt(row.b1_amt)},
        {"key": "b2", "label": f"{b1+1}–{b2} ngày", "amount": flt(row.b2_amt)},
        {"key": "b3", "label": f"{b2+1}–{b3} ngày", "amount": flt(row.b3_amt)},
        {"key": "over", "label": f">{b3} ngày", "amount": flt(row.over_amt)},
    ]
    return {"company": company, "buckets": buckets, "total": flt(row.total_amt)}


@frappe.whitelist()
def get_customer_detail(customer: str, company: str | None = None) -> dict:
    """360° công nợ 1 khách: hóa đơn outstanding, hạn mức, khoản thu chưa khớp."""
    guard_view()
    if not customer:
        frappe.throw("Thiếu mã khách hàng")
    company = resolve_company(company)

    info = frappe.db.get_value(
        "Customer", customer, ["customer_name", "customer_group", "territory"], as_dict=True
    ) or {}

    invoices = frappe.db.sql(
        """
        SELECT name, posting_date, due_date, grand_total, outstanding_amount, status,
               DATEDIFF(%(today)s, COALESCE(due_date, posting_date)) AS days_overdue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND customer = %(customer)s
          AND outstanding_amount > 0
        ORDER BY COALESCE(due_date, posting_date) ASC
        """,
        {"today": today(), "company": company, "customer": customer},
        as_dict=True,
    )
    for inv in invoices:
        inv["grand_total"] = flt(inv["grand_total"])
        inv["outstanding_amount"] = flt(inv["outstanding_amount"])

    outstanding = sum(i["outstanding_amount"] for i in invoices)

    # Hạn mức tín dụng: Customer Credit Limit là child table (theo company) → đọc an toàn.
    credit_limit = _get_credit_limit(customer, company)

    # Khoản thu chưa khớp (advance) của khách.
    unallocated = flt(
        frappe.db.sql(
            """
            SELECT SUM(unallocated_amount) FROM `tabPayment Entry`
            WHERE docstatus = 1 AND party_type = 'Customer' AND party = %(customer)s
              AND company = %(company)s AND unallocated_amount > 0
            """,
            {"customer": customer, "company": company},
        )[0][0]
        or 0
    )

    return {
        "customer": customer,
        "customer_name": info.get("customer_name"),
        "customer_group": info.get("customer_group"),
        "territory": info.get("territory"),
        "outstanding": outstanding,
        "credit_limit": credit_limit,
        "over_limit": bool(credit_limit and outstanding > credit_limit),
        "unallocated_payment": unallocated,
        "invoices": invoices,
    }


@frappe.whitelist()
def get_dso(company: str | None = None) -> dict:
    """DSO ước tính = tổng nợ / doanh thu kỳ × số ngày cửa sổ.

    Doanh thu kỳ: Sales Invoice trong cửa sổ, LỌC is_opening và is_return.
    """
    guard_view()
    company = resolve_company(company)
    window = int(get_settings().dso_window_days or 365)

    debt = flt(
        frappe.db.sql(
            """
            SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
            """,
            {"company": company},
        )[0][0]
        or 0
    )

    revenue = frappe.db.sql(
        """
        SELECT SUM(base_grand_total) AS rev
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
          AND IFNULL(is_opening, 'No') != 'Yes'
          AND IFNULL(is_return, 0) = 0
          AND posting_date >= DATE_SUB(%(today)s, INTERVAL %(window)s DAY)
        """,
        {"company": company, "today": today(), "window": window},
        as_dict=True,
    )[0]
    rev = flt(revenue.rev)

    dso = round(debt / rev * window, 1) if rev else None
    return {"company": company, "debt": debt, "revenue_window": rev, "window_days": window, "dso": dso}


def _get_credit_limit(customer: str, company: str) -> float:
    """Hạn mức tín dụng của khách theo company. Bọc try/except (nhiều site không set)."""
    try:
        rows = frappe.get_all(
            "Customer Credit Limit",
            filters={"parent": customer, "parenttype": "Customer", "company": company},
            fields=["credit_limit"],
            limit=1,
        )
        if rows and rows[0].credit_limit:
            return flt(rows[0].credit_limit)
        # fallback: trường credit_limit cũ trên Customer (nếu có)
        legacy = frappe.db.get_value("Customer", customer, "credit_limit")
        return flt(legacy) if legacy else 0.0
    except Exception:
        return 0.0
