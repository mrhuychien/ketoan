"""Whitelisted methods — phân hệ Tiền & quỹ (sổ quỹ tiền mặt / tiền gửi).

Số dư & dòng tiền tính từ GL Entry trên các TK có account_type Cash/Bank
(theo cấu hình Settings). Read-only, guard ở dòng đầu.
"""

import frappe
from frappe.utils import flt, today, add_days

from ketoan.api._guard import guard_cash, resolve_company, cash_account_types


@frappe.whitelist()
def get_balances(company: str | None = None, as_of: str | None = None) -> dict:
    """Số dư từng TK tiền mặt/tiền gửi tại thời điểm `as_of` (mặc định hôm nay)."""
    guard_cash()
    company = resolve_company(company)
    as_of = as_of or today()
    types = cash_account_types()

    rows = frappe.db.sql(
        """
        SELECT gle.account,
               acc.account_name,
               acc.account_type,
               SUM(gle.debit - gle.credit) AS balance
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.posting_date <= %(as_of)s
          AND acc.account_type IN %(types)s
          AND acc.is_group = 0
        GROUP BY gle.account, acc.account_name, acc.account_type
        HAVING ROUND(SUM(gle.debit - gle.credit), 2) <> 0
        ORDER BY acc.account_type, SUM(gle.debit - gle.credit) DESC
        """,
        {"company": company, "as_of": as_of, "types": types},
        as_dict=True,
    )
    for r in rows:
        r["balance"] = flt(r["balance"])

    total = sum(r["balance"] for r in rows)
    return {"company": company, "as_of": as_of, "rows": rows, "total": total}


@frappe.whitelist()
def get_cashflow(company: str | None = None, from_date: str | None = None, to_date: str | None = None) -> dict:
    """Dòng tiền thu (debit) / chi (credit) theo ngày trên TK tiền."""
    guard_cash()
    company = resolve_company(company)
    to_date = to_date or today()
    from_date = from_date or add_days(to_date, -30)
    types = cash_account_types()

    rows = frappe.db.sql(
        """
        SELECT gle.posting_date,
               SUM(gle.debit)  AS inflow,
               SUM(gle.credit) AS outflow
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND acc.account_type IN %(types)s
          AND acc.is_group = 0
        GROUP BY gle.posting_date
        ORDER BY gle.posting_date ASC
        """,
        {"company": company, "from_date": from_date, "to_date": to_date, "types": types},
        as_dict=True,
    )
    inflow = 0.0
    outflow = 0.0
    for r in rows:
        r["inflow"] = flt(r["inflow"])
        r["outflow"] = flt(r["outflow"])
        r["net"] = r["inflow"] - r["outflow"]
        inflow += r["inflow"]
        outflow += r["outflow"]

    return {
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "rows": rows,
        "total_inflow": inflow,
        "total_outflow": outflow,
        "net": inflow - outflow,
    }


@frappe.whitelist()
def get_transactions(
    company: str | None = None,
    account: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict:
    """List giao dịch GL trên TK tiền (mới nhất trước), kèm chứng từ để deep-link."""
    guard_cash()
    company = resolve_company(company)
    to_date = to_date or today()
    from_date = from_date or add_days(to_date, -30)
    limit = min(int(limit or 100), 500)
    types = cash_account_types()

    params = {
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "types": types,
        "limit": limit,
    }
    account_clause = ""
    if account:
        account_clause = "AND gle.account = %(account)s"
        params["account"] = account

    rows = frappe.db.sql(
        f"""
        SELECT gle.name, gle.posting_date, gle.account, gle.debit, gle.credit,
               gle.voucher_type, gle.voucher_no, gle.against, gle.remarks,
               gle.party_type, gle.party
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND acc.account_type IN %(types)s
          AND acc.is_group = 0
          {account_clause}
        ORDER BY gle.posting_date DESC, gle.creation DESC
        LIMIT %(limit)s
        """,
        params,
        as_dict=True,
    )
    for r in rows:
        r["debit"] = flt(r["debit"])
        r["credit"] = flt(r["credit"])

    return {"company": company, "from_date": from_date, "to_date": to_date, "rows": rows}
