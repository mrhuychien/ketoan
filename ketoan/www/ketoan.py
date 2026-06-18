"""Context cho SPA portal kế toán tác nghiệp tại /ketoan.

Render server-side: user, full name, isManager, roles, company, settings (ngưỡng
+ account cho nhập sổ quỹ), assetVersion, csrf. SPA đọc window.KETOAN_CONTEXT,
không gọi thêm API để biết mình là ai.
"""

import frappe
from frappe import _


def get_context(context):
    # Chặn Guest → đẩy về login.
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/ketoan"
        raise frappe.Redirect

    from ketoan.api._guard import VIEW_ROLES, is_manager, resolve_company, get_settings

    roles = set(frappe.get_roles())
    if not (VIEW_ROLES & roles):
        frappe.throw(_("Bạn không có quyền truy cập portal kế toán tác nghiệp"), frappe.PermissionError)

    settings = get_settings()
    company = resolve_company()

    context.no_cache = 1
    context.no_breadcrumbs = 1
    context.title = "Kế toán Tác nghiệp"

    # assetVersion: làm sạch ký tự để dùng trong query ?v=
    context.asset_version = frappe.utils.now().replace(" ", "T").replace(":", "-")

    context.ketoan_context = {
        "user": frappe.session.user,
        "fullName": frappe.utils.get_fullname(frappe.session.user),
        "isManager": is_manager(),
        "roles": sorted(roles),
        "company": company,
        "csrfToken": frappe.session.data.csrf_token if frappe.session.data else "",
        "assetVersion": context.asset_version,
        "settings": {
            "agingBuckets": [
                int(settings.aging_bucket_1 or 30),
                int(settings.aging_bucket_2 or 60),
                int(settings.aging_bucket_3 or 90),
            ],
            "cashBankFilter": settings.cash_bank_account_filter or "Cash and Bank",
            "allowSubmitCashbook": bool(settings.allow_submit_cashbook),
        },
    }
    return context
