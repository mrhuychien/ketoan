"""Patch: set giá trị mặc định cho Single `Ketoan Portal Settings` nếu chưa cấu hình.
Idempotent — chỉ set khi field còn rỗng."""

import frappe


def execute():
    try:
        settings = frappe.get_single("Ketoan Portal Settings")
    except Exception:
        return  # DocType chưa sync — bỏ qua an toàn

    changed = False
    defaults = {
        "aging_bucket_1": 30,
        "aging_bucket_2": 60,
        "aging_bucket_3": 90,
        "dso_window_days": 365,
        "cash_bank_account_filter": "Cash and Bank",
        "enable_credit_limit_alert": 1,
    }
    for field, value in defaults.items():
        if not settings.get(field):
            settings.set(field, value)
            changed = True

    # Công ty mặc định: lấy từ Global Defaults nếu chưa set
    if not settings.get("default_company"):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if company:
            settings.default_company = company
            changed = True

    if changed:
        settings.flags.ignore_permissions = True
        settings.save()
