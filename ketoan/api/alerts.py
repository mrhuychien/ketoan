"""Whitelisted method — Cảnh báo tác nghiệp P0 (alert engine).

Biến rủi ro im lặng thành việc hiện trên màn hình. Rule nằm trong code, ngưỡng
lấy từ Ketoan Portal Settings. Mỗi alert: {code, severity, title, count, amount,
hint, link}. Read-only, guard ở dòng đầu.

P0:
- A1 NPP/khách vượt hạn mức tín dụng
- A2 nợ quá hạn theo rổ >b1/>b2/>b3
- A3 khoản thu chưa khớp (Payment Entry unallocated)
- A4 quỹ tiền mặt âm (chắc chắn sai dữ liệu)
"""

from urllib.parse import quote

import frappe
from frappe.utils import flt, today

from ketoan.api._guard import guard_view, resolve_company, get_settings, cash_account_types


@frappe.whitelist()
def get_alerts(company: str | None = None) -> dict:
    """Gộp toàn bộ cảnh báo P0 cho 1 company."""
    guard_view()
    company = resolve_company(company)
    s = get_settings()

    alerts = []
    alerts.extend(_alert_credit_limit(company, s))
    alerts.extend(_alert_overdue(company, s))
    alerts.extend(_alert_unallocated(company))
    alerts.extend(_alert_cash_negative(company))

    severity_rank = {"danger": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), -flt(a.get("amount"))))
    return {"company": company, "as_of": today(), "alerts": alerts}


def _alert_credit_limit(company: str, s) -> list:
    """A1: khách có outstanding > hạn mức tín dụng."""
    if not s.enable_credit_limit_alert:
        return []
    # Join outstanding theo khách với hạn mức (Customer Credit Limit theo company).
    rows = frappe.db.sql(
        """
        SELECT si.customer, si.customer_name,
               SUM(si.outstanding_amount) AS outstanding,
               ccl.credit_limit
        FROM `tabSales Invoice` si
        JOIN `tabCustomer Credit Limit` ccl
          ON ccl.parent = si.customer AND ccl.parenttype = 'Customer'
         AND ccl.company = %(company)s
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.outstanding_amount > 0
          AND ccl.credit_limit > 0
        GROUP BY si.customer, si.customer_name, ccl.credit_limit
        HAVING SUM(si.outstanding_amount) > ccl.credit_limit
        ORDER BY (SUM(si.outstanding_amount) - ccl.credit_limit) DESC
        """,
        {"company": company},
        as_dict=True,
    )
    if not rows:
        return []
    items = [
        {
            "customer": r.customer,
            "label": r.customer_name or r.customer,
            "outstanding": flt(r.outstanding),
            "credit_limit": flt(r.credit_limit),
            "over": flt(r.outstanding) - flt(r.credit_limit),
            "link": f"/app/customer/{quote(r.customer)}",
        }
        for r in rows
    ]
    return [
        {
            "code": "A1",
            "severity": "danger",
            "title": "Khách vượt hạn mức tín dụng",
            "count": len(items),
            "amount": sum(i["over"] for i in items),
            "hint": "Tổng nợ vượt hạn mức — cân nhắc khóa đơn / thu hồi.",
            "items": items,
        }
    ]


def _alert_overdue(company: str, s) -> list:
    """A2: nợ quá hạn theo 3 rổ (>b1 / >b2 / >b3 ngày)."""
    b1, b2, b3 = int(s.aging_bucket_1 or 30), int(s.aging_bucket_2 or 60), int(s.aging_bucket_3 or 90)
    row = frappe.db.sql(
        """
        SELECT
          SUM(CASE WHEN d > %(b1)s THEN o ELSE 0 END) AS over_b1,
          SUM(CASE WHEN d > %(b2)s THEN o ELSE 0 END) AS over_b2,
          SUM(CASE WHEN d > %(b3)s THEN o ELSE 0 END) AS over_b3,
          SUM(CASE WHEN d > %(b1)s THEN 1 ELSE 0 END) AS cnt_b1
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
    over_b1 = flt(row.over_b1)
    if over_b1 <= 0:
        return []
    sev = "danger" if flt(row.over_b3) > 0 else "warning"
    return [
        {
            "code": "A2",
            "severity": sev,
            "title": f"Nợ quá hạn (>{b1} ngày)",
            "count": int(row.cnt_b1 or 0),
            "amount": over_b1,
            "hint": f">{b1}: {_vnd(over_b1)} · >{b2}: {_vnd(row.over_b2)} · >{b3}: {_vnd(row.over_b3)}",
            "link": "/app/accounts-receivable",
            "breakdown": {
                f">{b1}": over_b1,
                f">{b2}": flt(row.over_b2),
                f">{b3}": flt(row.over_b3),
            },
        }
    ]


def _alert_unallocated(company: str) -> list:
    """A3: khoản thu của khách chưa khớp hóa đơn (Payment Entry unallocated)."""
    rows = frappe.db.sql(
        """
        SELECT name, party, party_name, posting_date, unallocated_amount
        FROM `tabPayment Entry`
        WHERE docstatus = 1 AND company = %(company)s
          AND party_type = 'Customer' AND unallocated_amount > 0
        ORDER BY unallocated_amount DESC
        LIMIT 100
        """,
        {"company": company},
        as_dict=True,
    )
    if not rows:
        return []
    items = [
        {
            "label": f"{r.party_name or r.party} · {r.name}",
            "amount": flt(r.unallocated_amount),
            "link": f"/app/payment-entry/{quote(r.name)}",
        }
        for r in rows
    ]
    return [
        {
            "code": "A3",
            "severity": "warning",
            "title": "Khoản thu chưa khớp hóa đơn",
            "count": len(items),
            "amount": sum(i["amount"] for i in items),
            "hint": "Phân bổ khoản thu vào hóa đơn để công nợ đúng.",
            "items": items,
        }
    ]


def _alert_cash_negative(company: str) -> list:
    """A4: TK tiền mặt/tiền gửi có số dư âm (gần như chắc chắn sai dữ liệu)."""
    types = cash_account_types()
    rows = frappe.db.sql(
        """
        SELECT gle.account, acc.account_name, SUM(gle.debit - gle.credit) AS balance
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND acc.account_type IN %(types)s AND acc.is_group = 0
          AND gle.posting_date <= %(today)s
        GROUP BY gle.account, acc.account_name
        HAVING SUM(gle.debit - gle.credit) < -0.5
        ORDER BY SUM(gle.debit - gle.credit) ASC
        """,
        {"company": company, "types": types, "today": today()},
        as_dict=True,
    )
    if not rows:
        return []
    items = [
        {
            "label": r.account_name or r.account,
            "amount": flt(r.balance),
            "link": f"/app/general-ledger?account={quote(r.account)}",
        }
        for r in rows
    ]
    return [
        {
            "code": "A4",
            "severity": "danger",
            "title": "Quỹ tiền mặt/tiền gửi âm",
            "count": len(items),
            "amount": sum(i["amount"] for i in items),
            "hint": "Số dư âm là dấu hiệu sai dữ liệu — kiểm tra chứng từ.",
            "items": items,
        }
    ]


def _vnd(n) -> str:
    return f"{round(flt(n)):,.0f}".replace(",", ".")
