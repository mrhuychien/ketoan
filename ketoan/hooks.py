app_name = "ketoan"
app_title = "Ketoan"
app_publisher = "Hoang Giang JSC"
app_description = "Portal Kế toán Tác nghiệp — Bàn làm việc Công nợ & Quỹ trên ERPNext v16"
app_email = "dev@hoanggiang.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext"]

# ═══════════════════════════════════════════════════════════════════════════
# Install — tạo Role + cấp quyền (idempotent). KHÔNG ship DocPerm qua fixtures
# (hash name, đổi giữa site) → cấp bằng add_permission trong after_install.
# ═══════════════════════════════════════════════════════════════════════════
after_install = "ketoan.install.after_install"

# ═══════════════════════════════════════════════════════════════════════════
# Jinja helpers (dùng cho www context + Print Format sau này)
# ═══════════════════════════════════════════════════════════════════════════
jinja = {
    "methods": [
        "ketoan.utils.format_vnd",
    ],
}

# ═══════════════════════════════════════════════════════════════════════════
# Website — SPA portal phục vụ tại /ketoan (www/ketoan.html + ketoan.py).
# Không cần route rules; Frappe tự map www/<page>.
# ═══════════════════════════════════════════════════════════════════════════

# P0 read-only + deep-link → KHÔNG doc_events ghi sổ.
# (P1: scheduler_events daily snapshot cảnh báo + email digest.)
