"""Patch: field trục quan hệ thay thế/điều chỉnh + trạng thái "Chờ cấp mã".

Thêm `custom_misa_relation`, `custom_misa_org_ref_id`, `custom_misa_org_inv` và
mở rộng options của `custom_misa_status`.

Kèm sửa dữ liệu: bản cũ đặt `custom_misa_status='Đã thay thế'` cho chính hóa đơn
THAY THẾ (bản còn hiệu lực) thay vì hóa đơn BỊ thay thế — ngược hẳn ý nghĩa. Đợt
đồng bộ sau không tự sửa được vì vòng quét bỏ qua trạng thái đó, nên phải gỡ ở
đây rồi để `poll_pending` tính lại từ dữ liệu MISA.

Quy tắc: THÊM FIELD MỚI = THÊM PATCH MỚI. Không có ngoại lệ.
"""

import frappe


def execute():
    from ketoan.install import setup_misa_integration

    setup_misa_integration()
    frappe.clear_cache(doctype="Sales Invoice")

    if not frappe.db.has_column("Sales Invoice", "custom_misa_status"):
        return

    # Đưa về "Đã phát hành" chứ không xóa trắng: chúng đều là hóa đơn đã có số
    # thật trên MISA. poll_pending sẽ chấm lại đúng ở lần chạy tới.
    stuck = frappe.db.sql(
        """SELECT name FROM `tabSales Invoice`
           WHERE custom_misa_status = 'Đã thay thế'
             AND IFNULL(custom_misa_inv_no, '') != ''""", as_dict=True)
    for r in stuck:
        frappe.db.set_value("Sales Invoice", r.name, {
            "custom_misa_status": "Đã phát hành",
            "custom_misa_relation": "Hóa đơn thay thế/điều chỉnh",
        }, update_modified=False)

    frappe.db.commit()
    frappe.logger().info(
        f"ketoan: field vòng đời MISA (v0_0_10), chấm lại {len(stuck)} hóa đơn")
