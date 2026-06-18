"""Whitelisted method — Dashboard "hôm nay" cho portal.

Gộp các chỉ số đầu trang để mở portal là thấy ngay: tổng nợ, quá hạn theo rổ,
#khách vượt hạn mức, số dư quỹ, khoản thu treo, và số lượng cảnh báo.
Read-only, guard ở dòng đầu. Tái dùng method các phân hệ để tránh trùng logic.
"""

import frappe
from frappe.utils import flt, today

from ketoan.api._guard import guard_view, resolve_company, is_manager
from ketoan.api import receivables, cash, alerts


@frappe.whitelist()
def get_overview(company: str | None = None) -> dict:
    """Trả về toàn bộ thẻ KPI + danh sách cảnh báo cho trang chủ portal."""
    guard_view()
    company = resolve_company(company)

    aging = receivables.get_aging(company)
    dso = receivables.get_dso(company)
    balances = cash.get_balances(company)
    alert_data = alerts.get_alerts(company)

    overdue = sum(b["amount"] for b in aging["buckets"] if b["key"] != "current")

    # Khoản thu treo (advance) toàn công ty.
    unallocated = flt(
        frappe.db.sql(
            """
            SELECT SUM(unallocated_amount) FROM `tabPayment Entry`
            WHERE docstatus = 1 AND party_type = 'Customer'
              AND company = %(company)s AND unallocated_amount > 0
            """,
            {"company": company},
        )[0][0]
        or 0
    )

    a1 = next((a for a in alert_data["alerts"] if a["code"] == "A1"), None)

    return {
        "company": company,
        "as_of": today(),
        "is_manager": is_manager(),
        "cards": {
            "total_ar": aging["total"],
            "overdue": overdue,
            "over_limit_customers": (a1["count"] if a1 else 0),
            "cash_total": balances["total"],
            "unallocated_payment": unallocated,
            "dso": dso["dso"],
        },
        "aging": aging["buckets"],
        "cash_accounts": balances["rows"],
        "alerts": alert_data["alerts"],
    }
