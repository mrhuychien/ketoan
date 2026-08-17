"""misa_desk — phương thức phục vụ nút bấm / hiển thị trên Desk.

Không chứa logic đồng bộ. Ở đây chỉ dựng đường dẫn mở hóa đơn bên MISA.

Link tra cứu đã xác minh trên hóa đơn thật (§N của misa_api_contract.md). Mẫu
vẫn để trong `MISA Settings` chứ không hardcode, để MISA đổi dạng URL thì sửa
cấu hình là xong, không phải sửa code.
"""

from urllib.parse import quote

import frappe
from frappe import _

# Mẫu mặc định — dùng tạm khi chưa khai trong MISA Settings.
#
# Link tra cứu ĐÃ XÁC MINH trên hóa đơn thật: tham số `sc` chính là mã tra cứu
# MISA cấp, tức field TransactionID. Các tham số khác trong link MISA gửi khách
# (m, n, c, b, d, t, r) chỉ điền sẵn email/tên người mua — bỏ đi vẫn mở đúng.
#
# Trang quản trị app3 mở hóa đơn bằng cửa sổ nổi, KHÔNG đổi URL, nên không có
# link sâu tới từng hóa đơn. Vì vậy link tra cứu mới là đường dẫn chính.
DEFAULT_INVOICE_URL = "https://app3.meinvoice.vn/v3/hoa-don"
DEFAULT_LOOKUP_URL = "https://www.meinvoice.vn/tra-cuu/?sc={transaction_id}"

PLACEHOLDERS = ("ref_id", "transaction_id", "inv_no", "inv_series", "invoice_code", "taxcode")


def build_url(template, **ctx):
    """Thay chỗ giữ {ref_id} {transaction_id} {inv_no} {inv_series} {invoice_code} {taxcode}.

    Mẫu không có chỗ giữ nào thì trả về nguyên mẫu — vẫn mở đúng trang danh sách.
    Thiếu giá trị cho một chỗ giữ đang dùng thì trả None, thà không có link còn
    hơn link hỏng.
    """
    template = (template or "").strip()
    if not template:
        return None
    url = template
    for key in PLACEHOLDERS:
        token = "{" + key + "}"
        if token not in url:
            continue
        value = ctx.get(key)
        if not value:
            return None
        url = url.replace(token, quote(str(value), safe=""))
    return url


def invoice_links(si, settings=None):
    """Hai đường dẫn cho 1 hóa đơn: mở trên MISA (kế toán) và tra cứu công khai (khách)."""
    from ketoan.api.misa_client import get_settings

    settings = settings or get_settings()
    ctx = {
        "ref_id": si.get("custom_misa_ref_id"),
        "transaction_id": si.get("custom_misa_transaction_id"),
        "inv_no": si.get("custom_misa_inv_no"),
        "inv_series": si.get("custom_misa_inv_series"),
        "invoice_code": si.get("custom_misa_invoice_code"),
        "taxcode": (settings.taxcode or "").strip(),
    }
    misa = build_url(settings.invoice_url_template or DEFAULT_INVOICE_URL, **ctx)
    lookup = build_url(settings.lookup_url_template or DEFAULT_LOOKUP_URL, **ctx)
    return {
        "misa": misa,
        "lookup": lookup,
        # Link lưu vào hóa đơn: ưu tiên link tra cứu vì nó mở ĐÚNG hóa đơn đó.
        # Link quản trị chỉ mở trang danh sách nên không đáng lưu.
        "primary": lookup or misa,
        "transaction_id": ctx["transaction_id"],
        "inv_no": ctx["inv_no"],
    }


@frappe.whitelist()
def get_invoice_links(sales_invoice):
    """Đường dẫn MISA của 1 hóa đơn — phục vụ nút bấm trên form."""
    if not frappe.has_permission("Sales Invoice", "read", doc=sales_invoice):
        frappe.throw(_("Bạn không có quyền xem hóa đơn này"), frappe.PermissionError)
    si = frappe.db.get_value(
        "Sales Invoice", sales_invoice,
        ["custom_misa_ref_id", "custom_misa_transaction_id", "custom_misa_inv_no",
         "custom_misa_inv_series", "custom_misa_invoice_code"],
        as_dict=True,
    ) or {}
    return invoice_links(si)


@frappe.whitelist()
def backfill_links(limit=2000):
    """Điền `custom_misa_link` cho hóa đơn đã có mã tra cứu mà chưa có link.

    Chạy lại sau khi sửa mẫu URL trong MISA Settings để cập nhật hàng loạt.
    """
    from ketoan.api._guard import guard_manager
    from ketoan.api.misa_client import get_settings
    from ketoan.install import ensure_misa_fields

    guard_manager()
    # Field có thể chưa tồn tại nếu site migrate trước khi field được thêm vào
    # app — tạo bù tại chỗ thay vì để truy vấn gãy "Unknown column".
    created = ensure_misa_fields("custom_misa_link", "custom_misa_transaction_id")
    settings = get_settings()
    rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "custom_misa_transaction_id": ("is", "set")},
        fields=["name", "custom_misa_ref_id", "custom_misa_transaction_id", "custom_misa_inv_no",
                "custom_misa_inv_series", "custom_misa_invoice_code", "custom_misa_link"],
        limit=int(limit or 2000),
    )
    done = 0
    for si in rows:
        url = invoice_links(si, settings).get("primary")
        if url and url != si.get("custom_misa_link"):
            frappe.db.set_value("Sales Invoice", si.name, "custom_misa_link", url, update_modified=False)
            done += 1
            if done % 100 == 0:
                frappe.db.commit()
    frappe.db.commit()
    return {"updated": done, "scanned": len(rows), "fields_created": created}
