"""Whitelisted methods — phân hệ Phải trả (công nợ nhà cung cấp).

NGUỒN SỰ THẬT = GL ENTRY (không phải hóa đơn):
- Công nợ NCC = SUM(credit - debit) trên GL Entry các TK account_type='Payable'
  với party_type='Supplier' — gồm cả nợ từ bút toán JE, dư đầu kỳ, trả trước
  (số âm) chứ không chỉ Purchase Invoice.outstanding_amount.
- Aging: gộp GL theo chứng từ gốc (COALESCE(against_voucher, voucher_no)) →
  số dư mở từng chứng từ, tuổi theo due_date của PI (nếu là PI) hoặc ngày
  phát sinh; rổ từ Settings. Tổng aging khớp tổng công nợ GL.
- Lịch thanh toán (get_due_schedule) vẫn theo hóa đơn — vì hạn trả nằm trên PI.
- Kiểm soát: trùng hóa đơn NCC (cùng supplier + bill_no); khớp 3 chiều
  (hóa đơn mua thiếu liên kết Purchase Receipt).
Tất cả read-only, guard_purchase ở dòng đầu, SQL parameterized.
"""

import frappe
from frappe.utils import flt, today, getdate, add_days

from ketoan.api._guard import guard_purchase, resolve_company, get_settings


@frappe.whitelist()
def get_ap_summary(company: str | None = None, limit: int = 200) -> dict:
    """Bảng kê công nợ phải trả theo NCC + tổng — TÍNH TỪ GL ENTRY.

    outstanding = SUM(credit - debit) trên TK Payable (party = NCC); âm = ta
    đang ứng trước/NCC nợ lại. days_overdue lấy từ hóa đơn PI còn nợ sớm hạn
    nhất (GL không mang hạn trả).
    """
    guard_purchase()
    company = resolve_company(company)
    limit = min(int(limit or 200), 1000)

    rows = frappe.db.sql(
        """
        SELECT gle.party AS supplier,
               COALESCE(s.supplier_name, gle.party) AS supplier_name,
               s.supplier_group,
               SUM(gle.credit - gle.debit) AS outstanding
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        LEFT JOIN `tabSupplier` s ON s.name = gle.party
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.party_type = 'Supplier'
          AND acc.account_type = 'Payable'
        GROUP BY gle.party, s.supplier_name, s.supplier_group
        HAVING ROUND(SUM(gle.credit - gle.debit), 2) <> 0
        ORDER BY SUM(gle.credit - gle.debit) DESC
        LIMIT %(limit)s
        """,
        {"company": company, "limit": limit},
        as_dict=True,
    )

    # Hạn trả sớm nhất trong các hóa đơn PI còn nợ của từng NCC (chỉ để tính quá hạn).
    due_map = {}
    for x in frappe.db.sql(
        """
        SELECT supplier, MIN(COALESCE(due_date, posting_date)) AS earliest_due
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
        GROUP BY supplier
        """,
        {"company": company},
        as_dict=True,
    ):
        due_map[x.supplier] = x.earliest_due

    t = getdate(today())
    total = 0.0
    for r in rows:
        r["outstanding"] = flt(r["outstanding"])
        total += r["outstanding"]
        due = due_map.get(r["supplier"])
        r["days_overdue"] = max((t - getdate(due)).days, 0) if (due and r["outstanding"] > 0) else 0

    return {"company": company, "total": total, "count": len(rows), "rows": rows}


@frappe.whitelist()
def get_aging(company: str | None = None) -> dict:
    """Tuổi nợ phải trả theo rổ cấu hình (Settings) — TÍNH TỪ GL ENTRY.

    Gộp GL theo chứng từ gốc (against_voucher, không có thì chính voucher) →
    số dư mở từng chứng từ; tuổi theo due_date của PI hoặc ngày phát sinh.
    Số âm (ứng trước NCC) trừ vào rổ — tổng rổ khớp tổng công nợ GL.
    """
    guard_purchase()
    company = resolve_company(company)
    s = get_settings()
    b1, b2, b3 = int(s.aging_bucket_1 or 30), int(s.aging_bucket_2 or 60), int(s.aging_bucket_3 or 90)

    items = frappe.db.sql(
        """
        SELECT COALESCE(gle.against_voucher, gle.voucher_no) AS ref,
               SUM(gle.credit - gle.debit) AS o,
               MIN(gle.posting_date) AS first_date
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND gle.party_type = 'Supplier' AND acc.account_type = 'Payable'
        GROUP BY COALESCE(gle.against_voucher, gle.voucher_no)
        HAVING ROUND(SUM(gle.credit - gle.debit), 2) <> 0
        LIMIT 20000
        """,
        {"company": company},
        as_dict=True,
    )

    # Hạn trả cho các chứng từ mở là Purchase Invoice.
    refs = [it.ref for it in items if it.ref]
    due_map = {}
    if refs:
        for x in frappe.get_all("Purchase Invoice", filters={"name": ["in", refs]},
                                fields=["name", "due_date", "posting_date"], limit=len(refs)):
            due_map[x.name] = x.due_date or x.posting_date

    from ketoan.api.receivables import _bucketize
    sums, total = _bucketize(items, due_map, b1, b2, b3)
    buckets = [
        {"key": "current", "label": "Trong hạn", "amount": flt(sums["current"])},
        {"key": "b1", "label": f"1–{b1} ngày", "amount": flt(sums["b1"])},
        {"key": "b2", "label": f"{b1+1}–{b2} ngày", "amount": flt(sums["b2"])},
        {"key": "b3", "label": f"{b2+1}–{b3} ngày", "amount": flt(sums["b3"])},
        {"key": "over", "label": f">{b3} ngày", "amount": flt(sums["over"])},
    ]
    return {"company": company, "buckets": buckets, "total": flt(total)}


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

    # Còn phải trả TÍNH TỪ GL (gồm JE, nợ đầu kỳ, ứng trước — không chỉ PI).
    outstanding = flt(frappe.db.sql(
        """SELECT SUM(gle.credit - gle.debit)
           FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
           WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
             AND gle.party_type = 'Supplier' AND gle.party = %(supplier)s
             AND acc.account_type = 'Payable'""",
        {"company": company, "supplier": supplier},
    )[0][0] or 0)

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
