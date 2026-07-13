"""Whitelisted methods — phân hệ Phải trả (công nợ nhà cung cấp).

Semantics đối xứng với receivables:
- Công nợ NCC = `Purchase Invoice.outstanding_amount` (docstatus=1).
- Aging theo `COALESCE(due_date, posting_date)` so với hôm nay (rổ từ Settings).
- Kiểm soát: trùng hóa đơn NCC (cùng supplier + bill_no) — lỗi nhập hoặc gian lận;
  khớp 3 chiều: hóa đơn mua thiếu liên kết nhập kho (Purchase Receipt).
Tất cả read-only, guard_purchase ở dòng đầu, SQL parameterized.
"""

import frappe
from frappe.utils import flt, today, getdate, add_days

from ketoan.api._guard import guard_purchase, resolve_company, get_settings


@frappe.whitelist()
def get_ap_summary(company: str | None = None, limit: int = 200) -> dict:
    """Bảng kê công nợ phải trả theo NCC + tổng."""
    guard_purchase()
    company = resolve_company(company)
    limit = min(int(limit or 200), 1000)

    rows = frappe.db.sql(
        """
        SELECT pi.supplier,
               pi.supplier_name,
               s.supplier_group,
               SUM(pi.outstanding_amount)                  AS outstanding,
               MIN(COALESCE(pi.due_date, pi.posting_date)) AS earliest_due
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabSupplier` s ON s.name = pi.supplier
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.outstanding_amount > 0
        GROUP BY pi.supplier, pi.supplier_name, s.supplier_group
        ORDER BY SUM(pi.outstanding_amount) DESC
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
    """Tuổi nợ phải trả theo rổ cấu hình (Settings)."""
    guard_purchase()
    company = resolve_company(company)
    s = get_settings()
    b1, b2, b3 = int(s.aging_bucket_1 or 30), int(s.aging_bucket_2 or 60), int(s.aging_bucket_3 or 90)

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
            FROM `tabPurchase Invoice`
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
def get_due_schedule(company: str | None = None, days_ahead: int = 14) -> dict:
    """Lịch thanh toán: hóa đơn NCC đến hạn trong `days_ahead` ngày tới (kèm quá hạn)."""
    guard_purchase()
    company = resolve_company(company)
    days_ahead = min(int(days_ahead or 14), 90)

    rows = frappe.db.sql(
        """
        SELECT name, supplier, supplier_name, posting_date, due_date, bill_no,
               grand_total, outstanding_amount,
               DATEDIFF(COALESCE(due_date, posting_date), %(today)s) AS days_to_due
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
          AND COALESCE(due_date, posting_date) <= DATE_ADD(%(today)s, INTERVAL %(ahead)s DAY)
        ORDER BY COALESCE(due_date, posting_date) ASC
        LIMIT 300
        """,
        {"company": company, "today": today(), "ahead": days_ahead},
        as_dict=True,
    )
    overdue_total = 0.0
    upcoming_total = 0.0
    for r in rows:
        r["outstanding_amount"] = flt(r["outstanding_amount"])
        r["grand_total"] = flt(r["grand_total"])
        if r["days_to_due"] < 0:
            overdue_total += r["outstanding_amount"]
        else:
            upcoming_total += r["outstanding_amount"]

    return {
        "company": company, "days_ahead": days_ahead, "rows": rows,
        "overdue_total": overdue_total, "upcoming_total": upcoming_total,
    }


@frappe.whitelist()
def get_supplier_detail(supplier: str, company: str | None = None) -> dict:
    """360° công nợ 1 NCC: hóa đơn outstanding, khoản chi chưa khớp."""
    guard_purchase()
    if not supplier:
        frappe.throw("Thiếu mã nhà cung cấp")
    company = resolve_company(company)

    info = frappe.db.get_value(
        "Supplier", supplier, ["supplier_name", "supplier_group", "tax_id"], as_dict=True
    ) or {}

    invoices = frappe.db.sql(
        """
        SELECT name, posting_date, due_date, bill_no, grand_total, outstanding_amount, status,
               DATEDIFF(%(today)s, COALESCE(due_date, posting_date)) AS days_overdue
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND supplier = %(supplier)s
          AND outstanding_amount > 0
        ORDER BY COALESCE(due_date, posting_date) ASC
        """,
        {"today": today(), "company": company, "supplier": supplier},
        as_dict=True,
    )
    for inv in invoices:
        inv["grand_total"] = flt(inv["grand_total"])
        inv["outstanding_amount"] = flt(inv["outstanding_amount"])

    outstanding = sum(i["outstanding_amount"] for i in invoices)

    # Khoản chi trả trước chưa khớp hóa đơn.
    unallocated = flt(
        frappe.db.sql(
            """
            SELECT SUM(unallocated_amount) FROM `tabPayment Entry`
            WHERE docstatus = 1 AND party_type = 'Supplier' AND party = %(supplier)s
              AND company = %(company)s AND unallocated_amount > 0
            """,
            {"supplier": supplier, "company": company},
        )[0][0]
        or 0
    )

    return {
        "supplier": supplier,
        "supplier_name": info.get("supplier_name"),
        "supplier_group": info.get("supplier_group"),
        "tax_id": info.get("tax_id"),
        "outstanding": outstanding,
        "unallocated_payment": unallocated,
        "invoices": invoices,
    }


@frappe.whitelist()
def get_controls(company: str | None = None) -> dict:
    """Kiểm soát mua hàng:
    - duplicates: hóa đơn NCC trùng (cùng supplier + bill_no, >1 hóa đơn) — lỗi nhập/gian lận.
    - missing_receipt: hóa đơn mua cập nhật kho... không liên kết Purchase Receipt (khớp 3 chiều thiếu).
    """
    guard_purchase()
    company = resolve_company(company)

    # Trùng hóa đơn NCC theo (supplier, bill_no) — chỉ xét bill_no khác rỗng.
    duplicates = frappe.db.sql(
        """
        SELECT supplier, supplier_name, bill_no,
               COUNT(*) AS cnt,
               SUM(grand_total) AS total,
               GROUP_CONCAT(name ORDER BY posting_date SEPARATOR ', ') AS invoices
        FROM `tabPurchase Invoice`
        WHERE docstatus < 2 AND company = %(company)s
          AND IFNULL(bill_no, '') != ''
        GROUP BY supplier, supplier_name, bill_no
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC, SUM(grand_total) DESC
        LIMIT 100
        """,
        {"company": company},
        as_dict=True,
    )
    for d in duplicates:
        d["total"] = flt(d["total"])

    # Hóa đơn mua đã ghi sổ nhưng KHÔNG dòng nào liên kết Purchase Receipt
    # (khớp 3 chiều PO–PR–PI thiếu vế nhập kho). Bỏ qua hóa đơn tự cập nhật kho.
    missing_receipt = frappe.db.sql(
        """
        SELECT pi.name, pi.supplier_name, pi.posting_date, pi.grand_total
        FROM `tabPurchase Invoice` pi
        WHERE pi.docstatus = 1 AND pi.company = %(company)s
          AND IFNULL(pi.update_stock, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM `tabPurchase Invoice Item` pii
              WHERE pii.parent = pi.name AND IFNULL(pii.purchase_receipt, '') != ''
          )
        ORDER BY pi.posting_date DESC
        LIMIT 100
        """,
        {"company": company},
        as_dict=True,
    )
    for m in missing_receipt:
        m["grand_total"] = flt(m["grand_total"])

    return {"company": company, "duplicates": duplicates, "missing_receipt": missing_receipt}
