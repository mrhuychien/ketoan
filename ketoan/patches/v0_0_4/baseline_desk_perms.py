"""Patch: cấp quyền nền Desk (Page/Report/Company/Print/File...) cho mọi vai trò
kế toán — fix 'không có quyền truy cập doctype ... tài liệu Trang'. Idempotent."""


def execute():
    from ketoan.install import create_portal_roles, grant_business_permissions

    create_portal_roles()
    grant_business_permissions()
