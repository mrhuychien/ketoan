"""Shared utilities + Jinja helpers cho app Ketoan."""

import frappe
from frappe.utils import flt


def format_vnd(amount) -> str:
    """Format số tiền kiểu VN: '1.234.567 ₫'. Dùng trong Jinja/Print Format."""
    n = round(flt(amount))
    return f"{n:,.0f} ₫".replace(",", ".")
