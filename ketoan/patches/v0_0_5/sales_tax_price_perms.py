"""Patch: kênh bán hàng (NPP/MT/Du lịch) chọn được BẢNG GIÁ + THUẾ trên hóa đơn
và hàng trả về (Price List / Item Price / Sales Taxes and Charges Template /
Item Tax Template / Tax Category / Pricing Rule — read) + ép if_owner=0 để xem
TOÀN BỘ hóa đơn bán hàng. Idempotent — chỉ gọi lại grant theo ma trận mới."""


def execute():
    from ketoan.install import grant_business_permissions

    grant_business_permissions()
