"""Whitelisted method — Tiện ích "Nhập sổ quỹ".

Human-in-loop: tạo Journal Entry (voucher_type Cash Entry) ở trạng thái DRAFT để
người duyệt/submit trong Desk. Chỉ submit khi Settings bật `allow_submit_cashbook`
VÀ người dùng là quản lý. Có guard + validate đầy đủ.

- Chi tiền: Nợ TK đối ứng / Có TK quỹ.
- Thu tiền: Nợ TK quỹ / Có TK đối ứng (nếu gắn khách → dòng có party để đối trừ 131).
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import flt, today, getdate

from ketoan.api._guard import guard_view, resolve_company, get_settings, is_manager


@frappe.whitelist()
def get_form_options(company: str | None = None) -> dict:
    """Tùy chọn cho form nhập sổ quỹ: TK quỹ (Cash/Bank) + TK đối ứng gợi ý."""
    guard_view()
    company = resolve_company(company)

    cash_accounts = frappe.get_all(
        "Account",
        filters={"company": company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0, "disabled": 0},
        fields=["name", "account_name", "account_type"],
        order_by="account_type, name",
    )
    # TK đối ứng gợi ý: chi phí + phải thu (đối trừ khi thu của khách).
    counter_accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 0,
            "disabled": 0,
            "root_type": ["in", ["Expense", "Income", "Asset", "Liability"]],
        },
        fields=["name", "account_name", "root_type"],
        order_by="root_type, name",
        limit=500,
    )
    return {"company": company, "cash_accounts": cash_accounts, "counter_accounts": counter_accounts}


@frappe.whitelist()
def create_entry(
    entry_type: str,
    amount: float,
    cash_account: str,
    counter_account: str,
    content: str,
    posting_date: str | None = None,
    customer: str | None = None,
    company: str | None = None,
    submit: int = 0,
) -> dict:
    """Tạo phiếu thu/chi quỹ dưới dạng Journal Entry.

    entry_type: 'Thu' (Receive) hoặc 'Chi' (Pay).
    Trả về {doctype, name, docstatus, route} để SPA deep-link sang Desk.
    """
    guard_view()
    company = resolve_company(company)
    amount = flt(amount)
    posting_date = posting_date or today()

    # ── Validate ───────────────────────────────────────────────────────────
    if entry_type not in ("Thu", "Chi"):
        frappe.throw(_("Loại phiếu phải là 'Thu' hoặc 'Chi'"))
    if amount <= 0:
        frappe.throw(_("Số tiền phải lớn hơn 0"))
    if not cash_account or not counter_account:
        frappe.throw(_("Thiếu tài khoản quỹ hoặc tài khoản đối ứng"))
    if cash_account == counter_account:
        frappe.throw(_("Tài khoản quỹ và đối ứng phải khác nhau"))
    if getdate(posting_date) > getdate(today()):
        frappe.throw(_("Ngày phiếu không được ở tương lai"))
    _assert_account(cash_account, company)
    _assert_account(counter_account, company)
    if customer and not frappe.db.exists("Customer", customer):
        frappe.throw(_("Khách hàng không tồn tại: {0}").format(customer))

    # ── Dựng Journal Entry ─────────────────────────────────────────────────
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Cash Entry"
    je.posting_date = posting_date
    je.company = company
    je.user_remark = content or ("Thu tiền" if entry_type == "Thu" else "Chi tiền")

    if entry_type == "Thu":
        # Nợ quỹ / Có đối ứng (gắn party nếu là khách để đối trừ công nợ)
        je.append("accounts", {"account": cash_account, "debit_in_account_currency": amount})
        credit_line = {"account": counter_account, "credit_in_account_currency": amount}
        if customer:
            credit_line["party_type"] = "Customer"
            credit_line["party"] = customer
        je.append("accounts", credit_line)
    else:
        # Chi: Nợ đối ứng / Có quỹ
        debit_line = {"account": counter_account, "debit_in_account_currency": amount}
        if customer:
            debit_line["party_type"] = "Customer"
            debit_line["party"] = customer
        je.append("accounts", debit_line)
        je.append("accounts", {"account": cash_account, "credit_in_account_currency": amount})

    # insert() tôn trọng permission của user trên Journal Entry (role bundle Accounts).
    je.insert()

    do_submit = int(submit or 0) and get_settings().allow_submit_cashbook and is_manager()
    if do_submit:
        je.submit()

    return {
        "doctype": "Journal Entry",
        "name": je.name,
        "docstatus": je.docstatus,
        "route": f"/app/journal-entry/{quote(je.name)}",
    }


def _assert_account(account: str, company: str) -> None:
    acc = frappe.db.get_value("Account", account, ["company", "is_group", "disabled"], as_dict=True)
    if not acc:
        frappe.throw(_("Tài khoản không tồn tại: {0}").format(account))
    if acc.company != company:
        frappe.throw(_("Tài khoản {0} không thuộc công ty {1}").format(account, company))
    if acc.is_group:
        frappe.throw(_("Không thể hạch toán vào tài khoản tổng hợp: {0}").format(account))
    if acc.disabled:
        frappe.throw(_("Tài khoản đã bị vô hiệu hóa: {0}").format(account))
