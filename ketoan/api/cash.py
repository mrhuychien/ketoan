"""Whitelisted methods — phân hệ Tiền & quỹ (sổ quỹ tiền mặt / tiền gửi).

Số dư & dòng tiền tính từ GL Entry trên các TK có account_type Cash/Bank
(theo cấu hình Settings). Read-only, guard ở dòng đầu.
"""

import frappe
from frappe import _
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


# ═══════════════════════════════════════════════════════════════════════════
# Sổ cái từng tài khoản NGAY TRÊN PORTAL (kế toán hạch toán)
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_ledger_accounts(company: str | None = None) -> list:
    """Danh sách TK chi tiết (leaf) cho combobox sổ cái — TK có phát sinh nhiều
    trong 12 tháng gần nhất lên trước (client hiện top, gõ để tìm)."""
    guard_cash()
    company = resolve_company(company)
    return frappe.db.sql(
        """
        SELECT a.name, a.account_name, a.account_number, a.root_type, a.account_type,
               COALESCE(u.cnt, 0) AS usage_count
        FROM `tabAccount` a
        LEFT JOIN (
            SELECT account, COUNT(*) AS cnt
            FROM `tabGL Entry`
            WHERE is_cancelled = 0
              AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 365 DAY)
            GROUP BY account
        ) u ON u.account = a.name
        WHERE a.company = %(company)s AND a.is_group = 0 AND a.disabled = 0
        ORDER BY COALESCE(u.cnt, 0) DESC, a.account_number ASC, a.name ASC
        LIMIT 1000
        """,
        {"company": company},
        as_dict=True,
    )


@frappe.whitelist()
def get_account_ledger(account: str, company: str | None = None,
                       from_date: str | None = None, to_date: str | None = None) -> dict:
    """Sổ cái 1 tài khoản: dư đầu kỳ, phát sinh (số dư lũy kế từng dòng), dư cuối.

    Mỗi dòng kèm đối ứng (against), đối tượng, diễn giải + link mở chứng từ Desk.
    Giới hạn 2000 dòng/kỳ (trả cờ truncated để client báo thu hẹp kỳ).
    """
    guard_cash()
    company = resolve_company(company)
    if not account:
        frappe.throw(_("Chưa chọn tài khoản"))
    acc = frappe.db.get_value(
        "Account", account,
        ["company", "is_group", "account_name", "account_number", "root_type", "account_type"],
        as_dict=True,
    )
    if not acc or acc.company != company:
        frappe.throw(_("Tài khoản không hợp lệ với công ty đang chọn"))
    if acc.is_group:
        frappe.throw(_("Đây là tài khoản tổng hợp — hãy chọn tài khoản chi tiết"))
    to_date = to_date or today()

    params = {"company": company, "account": account, "to": to_date}
    opening = 0.0
    if from_date:
        params["from"] = from_date
        opening = flt(frappe.db.sql(
            """SELECT SUM(debit - credit) FROM `tabGL Entry`
               WHERE is_cancelled = 0 AND company = %(company)s
                 AND account = %(account)s AND posting_date < %(from)s""",
            params,
        )[0][0] or 0)

    from_clause = "AND posting_date >= %(from)s" if from_date else ""
    rows = frappe.db.sql(
        f"""SELECT posting_date, voucher_type, voucher_no, debit, credit,
                   against, party_type, party, remarks
            FROM `tabGL Entry`
            WHERE is_cancelled = 0 AND company = %(company)s AND account = %(account)s
              AND posting_date <= %(to)s {from_clause}
            ORDER BY posting_date ASC, creation ASC
            LIMIT 2001""",
        params,
        as_dict=True,
    )
    truncated = len(rows) > 2000
    rows = rows[:2000]

    running = opening
    total_debit = 0.0
    total_credit = 0.0
    out = []
    for r in rows:
        d, c = flt(r.debit), flt(r.credit)
        running += d - c
        total_debit += d
        total_credit += c
        vt = r.voucher_type or "Journal Entry"
        out.append({
            "posting_date": str(r.posting_date),
            "voucher_type": vt,
            "voucher_no": r.voucher_no,
            "debit": d, "credit": c, "balance": running,
            "against": (r.against or "")[:140],
            "party": r.party or "",
            "remarks": (r.remarks or "")[:180],
            "route": f"/desk/{frappe.scrub(vt).replace('_', '-')}/{r.voucher_no}",
        })

    label = ((acc.account_number + " — ") if acc.account_number else "") + (acc.account_name or account)
    return {
        "company": company, "account": account, "account_label": label,
        "root_type": acc.root_type, "account_type": acc.account_type,
        "from_date": from_date, "to_date": to_date,
        "opening": opening, "rows": out,
        "total_debit": total_debit, "total_credit": total_credit,
        "closing": running, "truncated": truncated,
    }
