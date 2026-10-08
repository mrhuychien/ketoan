"""Patch: `no_copy = 1` cho nhóm field `custom_misa_*` trên Sales Invoice.

VÌ SAO CẦN — đã ĐO ĐƯỢC trên site production (08/10/2026), không phải lo xa:

    91 nhóm / 182 chứng từ dùng chung MỘT `custom_misa_ref_id` và MỘT số hóa đơn.
    Phân loại: 92 hóa đơn BÁN + 90 hóa đơn TRẢ HÀNG.

Mỗi nhóm là một hóa đơn gốc và hóa đơn TRẢ HÀNG của chính nó. Nút "Return" của
ERPNext đi qua `get_mapped_doc` → `frappe/model/mapper.py::map_fields`, và hàm
đó loại field khỏi phép chép CHỈ khi `d.no_copy == 1`:

    no_copy_fields = set([d.fieldname for d in source_doc.meta.get("fields")
                          if (d.no_copy == 1 or d.fieldtype in table_fields)] ...)
    for df in target_doc.meta.get("fields"):
        if df.fieldname not in no_copy_fields:
            val = source_doc.get(df.fieldname)
            if val not in (None, ""):
                target_doc.set(df.fieldname, val)

17/17 field `custom_misa_*` KHÔNG khai `no_copy` (nhóm cũ `vn_einvoice_*` thì
CÓ), nên bản trả hàng chở nguyên RefID + số hóa đơn + cờ đã-đẩy của bản gốc.
`ensure_ref_id` chỉ dọn ở nhánh `amended_from`, mà bản trả hàng KHÔNG phải bản
sửa đổi, nên cleanup không chạy.

HẬU QUẢ ĐÃ ĐO: bản trả hàng hiện số hóa đơn của bản gốc, và vòng quét 2 của
`poll_pending` (không lọc `is_return`) đi hỏi MISA bằng RefID đi vay, nhận về
hóa đơn GỐC, rồi `check_amount_drift` so `abs(m) - abs(e)` giữa tiền gốc và
tiền trả hàng ÂM ⇒ lệch khổng lồ ⇒ dán nhãn "Lệch tiền" cho hàng loạt chứng từ
hoàn toàn bình thường, mỗi 30 phút một lần.

KHÔNG phải phát hành trùng: `misa_push.py` chặn hẳn `is_return` ở cổng đẩy, nên
hóa đơn trả hàng chưa bao giờ được đẩy lên MISA.

Patch này chỉ đặt cờ `no_copy` để chặn VỀ SAU. Nó KHÔNG dọn dữ liệu đã lỡ chép
— việc đó là sửa sổ kế toán, phải qua xem trước và người xác nhận, nằm ở công
cụ riêng.

Vì sao không trông vào `create_custom_fields` tự cập nhật: không xác minh được
hành vi đó trên bản Frappe đang chạy, nên đặt thẳng bằng `set_value` cho chắc.
Idempotent — chạy lại không đổi gì.
"""

import frappe

# 15 field mang DỮ LIỆU. Hai field layout (section/column break) không giữ gì
# nên không cần, và đặt cờ cho chúng chỉ làm nhiễu bản ghi.
FIELDS = (
    "custom_misa_status", "custom_misa_inv_series", "custom_misa_inv_no",
    "custom_misa_inv_date", "custom_misa_transaction_id", "custom_misa_invoice_code",
    "custom_misa_link", "custom_misa_ref_id", "custom_misa_relation",
    "custom_misa_org_ref_id", "custom_misa_org_inv", "custom_misa_pushed_at",
    "custom_misa_last_checked", "custom_misa_note", "custom_misa_no_locked",
)


def execute():
    from ketoan.install import setup_misa_integration

    setup_misa_integration()

    doi = []
    for fn in FIELDS:
        name = frappe.db.get_value(
            "Custom Field", {"dt": "Sales Invoice", "fieldname": fn}, "name")
        if not name:
            continue
        if frappe.db.get_value("Custom Field", name, "no_copy"):
            continue
        frappe.db.set_value("Custom Field", name, "no_copy", 1, update_modified=False)
        doi.append(fn)

    if doi:
        frappe.db.commit()
        frappe.clear_cache(doctype="Sales Invoice")
        frappe.logger().info(
            "ketoan v0_0_19: dat no_copy cho %d field MISA: %s" % (len(doi), ", ".join(doi)))
