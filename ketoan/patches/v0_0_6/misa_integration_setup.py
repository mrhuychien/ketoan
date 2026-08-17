"""Patch: dựng nền tích hợp MISA meInvoice (Phase 1).

Tạo role `MISA Reconciler`, custom field `custom_misa_*` trên Sales Invoice, và
cấp quyền 3 DocType mới cho Kế toán trưởng + MISA Reconciler.
Idempotent — chạy lại không sinh trùng.
"""


def execute():
    from ketoan.install import setup_misa_integration

    setup_misa_integration()
