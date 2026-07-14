"""Patch: cấp quyền DocType nghiệp vụ cho các vai trò kế toán (BUSINESS_PERMS)
+ mở các Report chuẩn (GL/AR/AP...). Idempotent — reuse install."""

import frappe


def execute():
    from ketoan.install import create_portal_roles, grant_business_permissions

    create_portal_roles()  # đảm bảo role tồn tại trước
    grant_business_permissions()
