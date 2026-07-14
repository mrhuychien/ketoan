"""Whitelisted methods — Đối trừ công nợ NPP (TÁCH 2 nhóm) & HĐĐT.

Không DocType riêng — vòng đời bám chứng từ gốc:
- TRẢ HÀNG   = Sales Invoice is_return NHÁP (tạo từ hóa đơn gốc).
- BÚT TOÁN JE = Journal Entry nháp có dòng party Customer thuộc nhóm NPP
  (chiết khấu [CK2-...], thưởng, hỗ trợ, điều chỉnh...).
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
    """Hồ sơ đối trừ TÁCH 2 nhóm: `returns` (SI trả về) và `jes` (bút toán JE:
    chiết khấu, thưởng, hỗ trợ...). `counts` gộp chung để tương thích KPI cũ."""
    guard_npp()
    company = resolve_company(company)
    days = min(int(days or 90), 365)
    since = add_days(today(), -days)
    group = get_settings().npp_customer_group or "NPP"

    # ── TRẢ HÀNG: SI is_return của khách nhóm NPP ───────────────────────────
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

    returns = []
    for r in si_rows:
        att = si_att.get(r.name, 0)
        returns.append({
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

    # ── BÚT TOÁN JE: mọi JE có dòng party Customer thuộc nhóm NPP ──────────
    # (không chỉ marker [CK2-] — gồm cả thưởng, hỗ trợ, điều chỉnh công nợ).
    field = je_remark_field()
    je_rows = frappe.db.sql(
        f"""
        SELECT je.name, MIN(a.party) AS party, MIN(c.customer_name) AS party_name,
               je.posting_date, je.total_debit, je.docstatus, je.`{field}` AS remark
        FROM `tabJournal Entry` je
        JOIN `tabJournal Entry Account` a ON a.parent = je.name AND a.party_type = 'Customer'
        JOIN `tabCustomer` c ON c.name = a.party AND c.customer_group = %(group)s
        WHERE je.company = %(company)s AND je.docstatus < 2
          AND (je.docstatus = 0 OR je.posting_date >= %(since)s)
        GROUP BY je.name, je.posting_date, je.total_debit, je.docstatus, je.`{field}`
        ORDER BY je.modified DESC
        LIMIT 200
        """,
        {"company": company, "group": group, "since": since},
        as_dict=True,
    )
    je_att = _attach_counts("Journal Entry", [r.name for r in je_rows])

    jes = []
    for r in je_rows:
        att = je_att.get(r.name, 0)
        remark = r.remark or ""
        purpose = "Chiết khấu" if "[CK2-" in remark else "Thưởng/Hỗ trợ/Khác"
        jes.append({
            "doctype": "Journal Entry",
            "name": r.name,
            "customer": r.party,
            "label": r.party_name or r.party,
            "date": str(r.posting_date) if r.posting_date else None,
            "amount": flt(r.total_debit),
            "purpose": purpose,
            "remark": remark[:120],
            "attachments": att,
            "status": _status(r.docstatus, att),
            "route": f"/app/journal-entry/{r.name}",
        })

    order = {"cho_hoadon": 0, "cho_duyet": 1, "done": 2}
    for lst in (returns, jes):
        lst.sort(key=lambda x: (order.get(x["status"], 9), x["date"] or ""))

    def tally(lst):
        c = {"cho_hoadon": 0, "cho_duyet": 0, "done": 0}
        for x in lst:
            c[x["status"]] = c.get(x["status"], 0) + 1
        return c

    rc, jc = tally(returns), tally(jes)
    counts = {k: rc[k] + jc[k] for k in rc}  # gộp — tương thích KPI cũ

    return {
        "company": company,
        "returns": returns, "jes": jes,
        "returns_counts": rc, "je_counts": jc, "counts": counts,
        "can_approve": is_chief(),
    }


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
def get_je_options(company: str | None = None) -> dict:
    """Dữ liệu cho modal tạo Bút toán JE trên portal: danh sách NPP + TK chi phí."""
    guard_npp()
    company = resolve_company(company)
    s = get_settings()
    group = s.npp_customer_group or "NPP"
    customers = frappe.get_all(
        "Customer",
        filters={"customer_group": group, "disabled": 0},
        fields=["name", "customer_name"],
        order_by="customer_name asc",
        limit=500,
    )
    expense_accounts = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": "Expense"},
        fields=["name", "account_name"],
        order_by="name asc",
        limit=500,
    )
    receivable = s.receivable_account or frappe.db.get_value("Company", company, "default_receivable_account")
    return {
        "customers": customers,
        "expense_accounts": expense_accounts,
        "default_expense_account": s.discount_expense_account or "",
        "receivable_account": receivable or "",
        "today": today(),
    }


@frappe.whitelist()
def create_je(customer: str, amount, remark: str, expense_account: str | None = None,
              posting_date: str | None = None, company: str | None = None,
              filename: str | None = None, content: str | None = None) -> dict:
    """Tạo Bút toán JE NHÁP từ portal (thưởng, hỗ trợ, điều chỉnh...):
    Nợ TK chi phí / Có TK phải thu (party = NPP). Kèm đính kèm hóa đơn nếu có.
    Đi tiếp quy trình đối trừ: đính kèm HĐ NPP → KTT duyệt → trừ công nợ."""
    guard_npp()
    company = resolve_company(company)
    s = get_settings()
    group = s.npp_customer_group or "NPP"

    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Số tiền phải lớn hơn 0"))
    if not (remark or "").strip():
        frappe.throw(_("Nhập diễn giải cho bút toán"))
    if not customer or frappe.db.get_value("Customer", customer, "customer_group") != group:
        frappe.throw(_("Khách không thuộc nhóm NPP"))

    expense_account = expense_account or s.discount_expense_account
    if not expense_account:
        frappe.throw(_("Chưa chọn TK chi phí (hoặc cấu hình mặc định trong Ketoan Portal Settings)"))
    acc = frappe.db.get_value("Account", expense_account, ["company", "is_group"], as_dict=True)
    if not acc or acc.company != company or acc.is_group:
        frappe.throw(_("TK chi phí không hợp lệ với công ty đang chọn"))

    receivable = s.receivable_account or frappe.db.get_value("Company", company, "default_receivable_account")
    if not receivable:
        frappe.throw(_("Chưa cấu hình TK phải thu (Ketoan Portal Settings hoặc Company)"))

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = posting_date or today()
    je.company = company
    je.set(je_remark_field(), f"{remark.strip()} — {customer}")
    je.append("accounts", {"account": expense_account, "debit_in_account_currency": amount})
    je.append("accounts", {
        "account": receivable, "credit_in_account_currency": amount,
        "party_type": "Customer", "party": customer,
    })
    je.insert()  # NHÁP — tôn trọng quyền create Journal Entry của user

    if content:
        b64 = (content or "").split(",")[-1]
        frappe.get_doc({
            "doctype": "File",
            "attached_to_doctype": "Journal Entry",
            "attached_to_name": je.name,
            "file_name": filename or "hoa-don-npp.pdf",
            "is_private": 1,
            "content": b64,
            "decode": True,
        }).save()

    return {"name": je.name, "route": f"/app/journal-entry/{je.name}"}


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
