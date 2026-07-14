"""Patch: cấp lại quyền nghiệp vụ sau khi mở rộng ma trận BUSINESS_PERMS
(tiền lương/hạch toán/trưởng + báo cáo tài chính). Idempotent."""


def execute():
    from ketoan.install import create_portal_roles, grant_business_permissions

    create_portal_roles()
    grant_business_permissions()
