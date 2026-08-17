"""misa_sync — các job đồng bộ với MISA meInvoice.

Nguyên tắc cô lập blast radius: chỉ job nào ĐƯỢC PHÉP mới ghi vào Sales Invoice.
Ở giai đoạn này mới có `ensure_ref_id` — sinh khóa nối trước khi ghi sổ.

`poll_pending` / `pull_official` / `pull_statement` chưa viết: còn chờ xác minh
hình dạng response (docs/misa/misa_api_contract.md §I.3). Dùng `misa_probe.py`
để lấy, KHÔNG đoán tên field.
"""

import uuid

import frappe


def ensure_ref_id(doc, method=None):
    """doc_events Sales Invoice.before_submit — sinh `custom_misa_ref_id` nếu chưa có.

    Đây là khóa nối gốc giữa ERPNext và MISA: phải tồn tại TRƯỚC khi đẩy, và phải
    được lưu lại (luồng cũ sinh uuid rồi vứt đi — xem §L.4.1 của contract).

    before_submit là thời điểm cuối cùng còn ghi được field thường mà không cần
    allow_on_submit.

    BẤT DI BẤT DỊCH: hàm này KHÔNG BAO GIỜ được chặn submit. Kế toán phải ghi sổ
    được kể cả khi tích hợp MISA hỏng hoàn toàn (ràng buộc 13.3 của pack).
    """
    try:
        if not doc.meta.has_field("custom_misa_ref_id"):
            return  # chưa migrate — im lặng bỏ qua
        if (doc.get("custom_misa_ref_id") or "").strip():
            return
        doc.custom_misa_ref_id = str(uuid.uuid4())
        if doc.meta.has_field("custom_misa_status") and not doc.get("custom_misa_status"):
            doc.custom_misa_status = "Chưa đẩy"
    except Exception:
        frappe.log_error(frappe.get_traceback(), "misa_sync.ensure_ref_id")


@frappe.whitelist()
def backfill_ref_id(limit=500):
    """Cấp `custom_misa_ref_id` cho hóa đơn ĐÃ ghi sổ mà còn thiếu.

    Hóa đơn cũ không có khóa nối nào dùng được (§L.4.1). Sinh ref_id bây giờ
    KHÔNG giúp khớp ngược với MISA — MISA giữ ref_id khác do luồng cũ sinh rồi
    vứt — nhưng bảo đảm mọi hóa đơn đều có khóa để các bước sau bám vào.

    Ghi bằng db_set(update_modified=False): tuyệt đối không save() chứng từ đã
    ghi sổ (ràng buộc 13.2 của pack).
    """
    from ketoan.api._guard import guard_manager

    guard_manager()
    limit = int(limit or 500)

    rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "custom_misa_ref_id": ("in", ["", None])},
        fields=["name"],
        order_by="posting_date desc",
        limit=limit,
    )
    done = 0
    for r in rows:
        try:
            frappe.db.set_value(
                "Sales Invoice", r.name, "custom_misa_ref_id", str(uuid.uuid4()), update_modified=False
            )
            done += 1
            if done % 50 == 0:
                frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"misa_sync.backfill_ref_id {r.name}")
    frappe.db.commit()

    remaining = frappe.db.count(
        "Sales Invoice", {"docstatus": 1, "custom_misa_ref_id": ("in", ["", None])}
    )
    return {"updated": done, "remaining": remaining}
