"""misa_reconcile — khớp hóa đơn MISA với Sales Invoice.

Bốn tầng khớp, dừng ở tầng đầu tiên trúng. Ba tầng đầu là khóa định danh nên
chắc chắn; tầng 4 chỉ suy ra từ MST + ngày + tiền nên luôn đánh dấu "Cần review",
kế toán chốt bằng tay.

Hệ thống KHÔNG tự kết luận nguồn gốc hóa đơn: snapshot không khớp được để
`origin='Chưa xác định'`. Sai ở đây là sai báo cáo thuế.
"""

import frappe
from frappe.utils import flt, now_datetime

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)

# MST chi nhánh dạng 0301175691-044 — vòng ngoài mới cắt đuôi, vòng trong khớp
# đủ chuỗi. Mẫu thật có 4 chi nhánh khác nhau cùng MST gốc (§H.3).
def base_taxcode(v) -> str:
    return norm_text(v).replace(" ", "").split("-")[0]


def _si_index(from_date, to_date):
    """Nạp Sales Invoice trong khoảng vào 4 chỉ mục tra ngược."""
    rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "posting_date": ("between", [from_date, to_date])},
        fields=["name", "custom_misa_ref_id", "custom_misa_transaction_id",
                "custom_misa_inv_series", "custom_misa_inv_no",
                "custom_mã_số_thuế", "posting_date", "grand_total"],
        limit=50000,
    )
    by_ref, by_txn, by_no, by_amt = {}, {}, {}, {}
    for r in rows:
        if r.custom_misa_ref_id:
            by_ref.setdefault(norm_text(r.custom_misa_ref_id), r.name)
        if r.custom_misa_transaction_id:
            by_txn.setdefault(norm_text(r.custom_misa_transaction_id), r.name)
        if r.custom_misa_inv_series and r.custom_misa_inv_no:
            by_no.setdefault((norm_series(r.custom_misa_inv_series), norm_inv_no(r.custom_misa_inv_no)), r.name)
        key = (base_taxcode(r.get("custom_mã_số_thuế")), str(r.posting_date), round(abs(flt(r.grand_total))))
        if key[0]:
            by_amt.setdefault(key, []).append(r.name)
    return by_ref, by_txn, by_no, by_amt


def _match_one(snap, idx):
    """Trả về (sales_invoice, match_method, match_confidence) hoặc (None, None, None)."""
    by_ref, by_txn, by_no, by_amt = idx

    hit = by_ref.get(norm_text(snap.get("ref_id")))
    if hit:
        return hit, "ref_id", "Chắc chắn"

    hit = by_txn.get(norm_text(snap.get("transaction_id")))
    if hit:
        return hit, "transaction_id", "Chắc chắn"

    hit = by_no.get((norm_series(snap.get("inv_series")), norm_inv_no(snap.get("inv_no"))))
    if hit:
        return hit, "so_hoa_don", "Chắc chắn"

    # Tầng 4 — suy đoán. Chỉ nhận khi DUY NHẤT một hóa đơn trùng cả 3 vế; nhiều
    # hóa đơn cùng MST/ngày/tiền là chuyện thường, đoán bừa là sai báo cáo thuế.
    key = (base_taxcode(snap.get("buyer_tax_code")), str(snap.get("inv_date") or ""),
           round(abs(flt(snap.get("total_amount")))))
    cands = by_amt.get(key) or []
    if len(cands) == 1:
        return cands[0], "mst_ngay_tien", "Cần review"
    return None, None, None


def _status(snap, si_name, tolerance):
    """Trạng thái đối soát. Vòng đời đọc từ cờ THẬT của MISA (§M.3), không đoán."""
    from ketoan.api.misa_sync import EINVOICE_RELATION, RELATION_DELTA, RELATION_SUPERSEDED

    if snap.get("is_deleted"):
        return "Đã hủy"

    # Hóa đơn ĐÃ BỊ THAY THẾ thì hết hiệu lực — kể cả khi chưa nối được về
    # ERPNext. Xếp nó vào rổ "Chỉ có trên MISA" là báo động giả: nó không phải
    # hóa đơn ngoài sổ, nó là hóa đơn đã chết. Đọc từ EInvoiceStatus (§R.7).
    relation = EINVOICE_RELATION.get(str(snap.get("einvoice_status") or "").strip())
    if relation in RELATION_SUPERSEDED:
        return "Đã thay thế"

    if not si_name:
        return "Chỉ có trên MISA"

    # Hóa đơn điều chỉnh mang phần CHÊNH, không phải tổng — so với grand_total
    # của hóa đơn gốc là chắc chắn ra "Lệch tiền" giả.
    if relation in RELATION_DELTA:
        return "Khớp"

    si = frappe.db.get_value(
        "Sales Invoice", si_name, ["net_total", "total_taxes_and_charges", "grand_total"], as_dict=True
    ) or {}
    # Endpoint danh sách của MISA KHÔNG trả tách thuế — TotalAmountWithoutVAT và
    # TotalVATAmount về 0.0 ở cả 30/30 bản ghi thật (§H.2). So 0 đó với net_total
    # thật của ERPNext thì MỌI hóa đơn khớp đều bị gắn "Lệch tiền" — rổ cảnh báo
    # đầy báo động giả, kế toán mất niềm tin rồi bỏ qua cả cảnh báo thật.
    #
    # Nguyên tắc: chỉ so vế nào MISA THẬT SỰ có số. Riêng tổng tiền thì luôn có
    # nên luôn so — và một mình nó đã đủ bắt lệch tiền.
    pairs = (
        ("truoc_thue", snap.get("amount_before_vat"), si.get("net_total"), False),
        ("thue", snap.get("vat_amount"), si.get("total_taxes_and_charges"), False),
        ("tong", snap.get("total_amount"), si.get("grand_total"), True),
    )
    for _key, m, e, always in pairs:
        if not always and not flt(m):
            continue   # MISA không cấp số cho vế này → không có gì để so
        if abs(abs(flt(m)) - abs(flt(e))) > flt(tolerance):
            return "Lệch tiền"
    return "Khớp"


@frappe.whitelist()
def match_snapshots(from_date, to_date, relink=0):
    """Khớp snapshot MISA với Sales Invoice trong khoảng ngày.

    relink=1 → khớp lại cả snapshot đã có liên kết (dùng sau khi sửa dữ liệu).
    KHÔNG động vào snapshot do người chốt tay (`match_method='thu_cong'`).
    """
    from ketoan.api._guard import guard_manager
    from ketoan.api.misa_client import get_settings

    guard_manager()
    tolerance = flt(get_settings().amount_tolerance) or 1.0

    # Snapshot thiếu inv_date (file nhập tay có thể thiếu) sẽ bị "between" loại
    # sạch — chúng lại chính là loại dễ thành hóa đơn mồ côi nhất. Gộp riêng.
    filters = {"inv_date": ("between", [from_date, to_date])}
    if not int(relink or 0):
        filters["sales_invoice"] = ("is", "not set")

    snaps = frappe.get_all(
        "MISA Invoice Snapshot", filters=filters,
        fields=["name", "ref_id", "transaction_id", "inv_series", "inv_no", "inv_date",
                "buyer_tax_code", "total_amount", "amount_before_vat", "vat_amount",
                "is_deleted", "sales_invoice", "match_method"],
        limit=50000,
    )
    if not snaps:
        return {"scanned": 0, "matched": 0, "mismatched": 0, "orphan": 0}

    idx = _si_index(from_date, to_date)
    stat = {"scanned": len(snaps), "matched": 0, "mismatched": 0, "orphan": 0}

    for i, snap in enumerate(snaps):
        if snap.get("match_method") == "thu_cong":
            continue  # người đã chốt — máy không được đè
        si_name, method, confidence = _match_one(snap, idx)
        status = _status(snap, si_name, tolerance)

        frappe.db.set_value("MISA Invoice Snapshot", snap.name, {
            "sales_invoice": si_name,
            "match_method": method,
            "match_confidence": confidence,
            "match_status": status,
            "origin": "Từ ERPNext" if si_name else "Chưa xác định",
            "last_synced_at": now_datetime(),
        }, update_modified=False)

        if status == "Lệch tiền":
            stat["mismatched"] += 1
        elif si_name:
            stat["matched"] += 1
        else:
            stat["orphan"] += 1
        if (i + 1) % 100 == 0:
            frappe.db.commit()

    frappe.db.commit()
    return stat


@frappe.whitelist()
def relink_snapshot(snapshot, sales_invoice=None, note=None):
    """Kế toán chốt tay liên kết (hoặc gỡ liên kết) một hóa đơn MISA."""
    from ketoan.api._guard import guard_manager
    from ketoan.api.misa_client import get_settings

    guard_manager()
    if sales_invoice and not frappe.db.exists("Sales Invoice", sales_invoice):
        frappe.throw(frappe._("Không tìm thấy hóa đơn {0}").format(sales_invoice))

    # Một hóa đơn ERPNext chỉ được nối với MỘT hóa đơn MISA. Nối chồng là ghi
    # nhận hai hóa đơn điện tử cho cùng một lần bán.
    if sales_invoice:
        taken = frappe.db.get_value(
            "MISA Invoice Snapshot",
            {"sales_invoice": sales_invoice, "name": ("!=", snapshot)},
            ["name", "inv_series", "inv_no"], as_dict=True)
        if taken:
            frappe.throw(frappe._(
                "Hóa đơn {0} đã được nối với hóa đơn MISA {1} số {2}. Gỡ liên kết cũ trước."
            ).format(sales_invoice, taken.inv_series, taken.inv_no))

    snap = frappe.db.get_value(
        "MISA Invoice Snapshot", snapshot,
        ["name", "is_deleted", "amount_before_vat", "vat_amount", "total_amount"], as_dict=True
    )
    if not snap:
        frappe.throw(frappe._("Không tìm thấy bản ghi MISA {0}").format(snapshot))

    tolerance = flt(get_settings().amount_tolerance) or 1.0
    values = {
        "sales_invoice": sales_invoice or None,
        "match_method": "thu_cong" if sales_invoice else None,
        "match_confidence": "Chắc chắn" if sales_invoice else None,
        "match_status": _status(snap, sales_invoice, tolerance),
        "origin": "Từ ERPNext" if sales_invoice else "Chưa xác định",
        "last_synced_at": now_datetime(),
    }
    if note:
        values["note"] = note
    frappe.db.set_value("MISA Invoice Snapshot", snapshot, values, update_modified=False)
    frappe.db.commit()
    return values


@frappe.whitelist()
def mark_origin(snapshot, origin, note=None):
    """Chốt nguồn gốc hóa đơn mồ côi — chỉ con người mới được quyết."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    if origin not in ("Từ ERPNext", "Xuất trực tiếp trên MISA", "Chưa xác định"):
        frappe.throw(frappe._("Nguồn gốc không hợp lệ"))
    values = {"origin": origin}
    if note:
        values["note"] = note
    frappe.db.set_value("MISA Invoice Snapshot", snapshot, values, update_modified=False)
    frappe.db.commit()
    return values
