"""Whitelisted methods — Đối trừ công nợ NPP (trả hàng + chiết khấu) & HĐĐT.

Không DocType riêng — vòng đời bám chứng từ gốc:
- Trả hàng  = Sales Invoice is_return NHÁP (tạo từ hóa đơn gốc).
- Chiết khấu = Journal Entry nháp mang marker [CK2-...] (flow sẵn có).
Trạng thái suy ra: nháp chưa đính kèm = "Chờ hóa đơn NPP"; nháp có đính kèm =
"Chờ KTT duyệt"; đã submit = "Đã trừ công nợ". KTT duyệt (submit) qua approve_case.

Hàng đi: Sales Invoice chưa điền `vn_einvoice_number` = chưa xuất hóa đơn điện tử.
"""

import frappe
from frappe import _
from frappe.utils import flt, today, add_days

from ketoan.api._guard import guard_npp, guard_manager, resolve_company, get_settings, is_chief
from ketoan.utils import je_remark_field


def _attach_counts(doctype: str, names: list) -> dict:
    """Đếm file đính kèm theo chứng từ (1 query File)."""
    if not names:
        return {}
    rows = frappe.get_all(
        "File",
        filters={"attached_to_doctype": doctype, "attached_to_name": ["in", names]},
        fields=["attached_to_name"],
        limit=5000,
    )
    out = {}
    for r in rows:
        out[r.attached_to_name] = out.get(r.attached_to_name, 0) + 1
    return out


def _status(docstatus: int, attachments: int) -> str:
    if int(docstatus) == 1:
        return "done"          # Đã trừ công nợ
    return "cho_duyet" if attachments else "cho_hoadon"


@frappe.whitelist()
def get_cases(company: str | None = None, days: int = 90) -> dict:
    """Danh sách hồ sơ đối trừ: SI trả về + JE chiết khấu (nháp + đã submit gần đây)."""
    guard_npp()
    company = resolve_company(company)
    days = min(int(days or 90), 365)
    since = add_days(today(), -days)
    group = get_settings().npp_customer_group or "NPP"

    # Trả hàng: SI is_return của khách nhóm NPP.
    si_rows = frappe.db.sql(
        """
        SELECT si.name, si.customer, si.customer_name, si.posting_date,
               si.grand_total, si.docstatus, si.return_against
        FROM `tabSales Invoice` si
        JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.is_return = 1 AND si.company = %(company)s
          AND c.customer_group = %(group)s
          AND (si.docstatus = 0 OR (si.docstatus = 1 AND si.posting_date >= %(since)s))
        ORDER BY si.modified DESC
        LIMIT 200
        """,
        {"company": company, "group": group, "since": since},
        as_dict=True,
    )
    si_att = _attach_counts("Sales Invoice", [r.name for r in si_rows])

    # Chiết khấu: JE mang marker [CK2- trong field remark.
    field = je_remark_field()
    je_rows = frappe.db.sql(
        f"""
        SELECT name, posting_date, total_debit, docstatus, `{field}` AS remark
        FROM `tabJournal Entry`
        WHERE company = %(company)s AND docstatus < 2
          AND `{field}` LIKE '%%[CK2-%%'
          AND (docstatus = 0 OR posting_date >= %(since)s)
        ORDER BY modified DESC
        LIMIT 200
        """,
        {"company": company, "since": since},
        as_dict=True,
    )
    je_att = _attach_counts("Journal Entry", [r.name for r in je_rows])
    # Đối tượng khách của JE (dòng có party Customer).
    parties = {}
    if je_rows:
        for p in frappe.get_all(
            "Journal Entry Account",
            filters={"parent": ["in", [r.name for r in je_rows]], "party_type": "Customer"},
            fields=["parent", "party"],
            limit=1000,
        ):
            parties.setdefault(p.parent, p.party)

    cases = []
    for r in si_rows:
        att = si_att.get(r.name, 0)
        cases.append({
            "loai": "Trả hàng",
            "doctype": "Sales Invoice",
            "name": r.name,
            "customer": r.customer,
            "label": r.customer_name or r.customer,
            "date": str(r.posting_date) if r.posting_date else None,
            "amount": abs(flt(r.grand_total)),
            "against": r.return_against,
            "attachments": att,
            "status": _status(r.docstatus, att),
            "route": f"/app/sales-invoice/{r.name}",
        })
    for r in je_rows:
        att = je_att.get(r.name, 0)
        cust = parties.get(r.name)
        cases.append({
            "loai": "Chiết khấu",
            "doctype": "Journal Entry",
            "name": r.name,
            "customer": cust,
            "label": cust or (r.remark or "")[:40],
            "date": str(r.posting_date) if r.posting_date else None,
            "amount": flt(r.total_debit),
            "against": None,
            "attachments": att,
            "status": _status(r.docstatus, att),
            "route": f"/app/journal-entry/{r.name}",
        })

    order = {"cho_hoadon": 0, "cho_duyet": 1, "done": 2}
    cases.sort(key=lambda x: (order.get(x["status"], 9), x["date"] or ""), reverse=False)
    counts = {"cho_hoadon": 0, "cho_duyet": 0, "done": 0}
    for x in cases:
        counts[x["status"]] = counts.get(x["status"], 0) + 1

    return {"company": company, "cases": cases, "counts": counts, "can_approve": is_chief()}


@frappe.whitelist()
def get_return_sources(customer: str, company: str | None = None) -> list:
    """Hóa đơn gốc (submitted, không phải return) của 1 NPP để tạo trả hàng."""
    guard_npp()
    company = resolve_company(company)
    if not customer:
        frappe.throw(_("Thiếu khách hàng"))
    return frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "company": company, "customer": customer, "is_return": 0},
        fields=["name", "posting_date", "grand_total", "outstanding_amount"],
        order_by="posting_date desc",
        limit=30,
    )


@frappe.whitelist()
def create_return(invoice: str, company: str | None = None) -> dict:
    """Tạo Sales Invoice trả về NHÁP từ hóa đơn gốc (make_return_doc chuẩn ERPNext)."""
    guard_npp()
    company = resolve_company(company)
    src = frappe.db.get_value("Sales Invoice", invoice, ["docstatus", "company", "is_return"], as_dict=True)
    if not src or src.docstatus != 1 or src.is_return:
        frappe.throw(_("Hóa đơn gốc không hợp lệ"))
    if src.company != company:
        frappe.throw(_("Hóa đơn không thuộc công ty đang chọn"))

    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    doc = make_return_doc("Sales Invoice", invoice)
    doc.insert()  # tôn trọng quyền create Sales Invoice của user
    return {"name": doc.name, "route": f"/app/sales-invoice/{doc.name}"}


@frappe.whitelist()
def upload_invoice_attachment(doctype: str, name: str, filename: str, content: str) -> dict:
    """Đính kèm hóa đơn NPP (file base64) vào chứng từ NHÁP (SI return / JE chiết khấu)."""
    guard_npp()
    if doctype not in ("Sales Invoice", "Journal Entry"):
        frappe.throw(_("Loại chứng từ không hợp lệ"))
    docstatus = frappe.db.get_value(doctype, name, "docstatus")
    if docstatus is None:
        frappe.throw(_("Chứng từ không tồn tại"))
    if int(docstatus) != 0:
        frappe.throw(_("Chỉ đính kèm vào chứng từ nháp"))

    b64 = (content or "").split(",")[-1]
    file_doc = frappe.get_doc({
        "doctype": "File",
        "attached_to_doctype": doctype,
        "attached_to_name": name,
        "file_name": filename or "hoa-don-npp.pdf",
        "is_private": 1,
        "content": b64,
        "decode": True,
    })
    file_doc.save()
    return {"file_url": file_doc.file_url, "name": file_doc.name}


@frappe.whitelist()
def approve_case(doctype: str, name: str) -> dict:
    """KTT duyệt: kiểm đã đính kèm hóa đơn NPP rồi submit chứng từ → trừ công nợ."""
    guard_manager()
    if doctype not in ("Sales Invoice", "Journal Entry"):
        frappe.throw(_("Loại chứng từ không hợp lệ"))
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus != 0:
        frappe.throw(_("Chứng từ không ở trạng thái nháp"))
    if not frappe.db.exists("File", {"attached_to_doctype": doctype, "attached_to_name": name}):
        frappe.throw(_("Chưa đính kèm hóa đơn NPP — không thể duyệt"))
    doc.submit()  # tôn trọng quyền submit của KTT
    return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist()
def get_missing_einvoice(company: str | None = None, days: int = 60) -> dict:
    """Hàng đi chưa xuất HĐĐT: SI submitted (khách NPP) có vn_einvoice_number rỗng."""
    guard_npp()
    company = resolve_company(company)
    days = min(int(days or 60), 365)
    if not frappe.db.has_column("Sales Invoice", "vn_einvoice_number"):
        return {"supported": False, "rows": [], "note": "Site chưa có field vn_einvoice_number"}

    group = get_settings().npp_customer_group or "NPP"
    rows = frappe.db.sql(
        """
        SELECT si.name, si.customer_name, si.posting_date, si.grand_total
        FROM `tabSales Invoice` si
        JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.is_return = 0
          AND c.customer_group = %(group)s
          AND si.posting_date >= %(since)s
          AND IFNULL(si.vn_einvoice_number, '') = ''
        ORDER BY si.posting_date DESC
        LIMIT 200
        """,
        {"company": company, "group": group, "since": add_days(today(), -days)},
        as_dict=True,
    )
    for r in rows:
        r["grand_total"] = flt(r["grand_total"])
    return {"supported": True, "rows": rows, "total": sum(r["grand_total"] for r in rows)}


# ═══════════════════════════════════════════════════════════════════════════
# Hồ sơ khách hàng (nhánh Quản lý KH) — file đính kèm trên Customer
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_customer_files(customer: str) -> list:
    """File đính kèm của 1 Customer (hợp đồng, phụ lục, ĐKKD...)."""
    from ketoan.api._guard import guard_sales_any

    guard_sales_any()
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Khách hàng không tồn tại"))
    return frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Customer", "attached_to_name": customer},
        fields=["name", "file_name", "file_url", "creation", "file_size"],
        order_by="creation desc",
        limit=100,
    )


@frappe.whitelist()
def upload_customer_file(customer: str, filename: str, content: str) -> dict:
    """Upload hồ sơ (base64) đính kèm vào Customer."""
    from ketoan.api._guard import guard_sales_any

    guard_sales_any()
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Khách hàng không tồn tại"))
    b64 = (content or "").split(",")[-1]
    file_doc = frappe.get_doc({
        "doctype": "File",
        "attached_to_doctype": "Customer",
        "attached_to_name": customer,
        "file_name": filename or "ho-so.pdf",
        "is_private": 1,
        "content": b64,
        "decode": True,
    })
    file_doc.save()
    return {"file_url": file_doc.file_url, "name": file_doc.name}
