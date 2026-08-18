"""misa_push — đẩy Sales Invoice sang MISA meInvoice.

Thay thế phần đẩy trong Client Script (§L của misa_api_contract.md). Credential
KHÔNG BAO GIỜ rời máy chủ: Client Script chỉ gọi xuống đây bằng tên hóa đơn.

Payload chép nguyên từ luồng đang chạy — đã được xác nhận chéo bằng response
`afterpublishing` của một hóa đơn thật (§M.4) — kèm ba chỗ sửa:

  · thuế suất lấy THẬT từ từng dòng hóa đơn thay vì cứng 8% (§L.4.3);
  · ký hiệu và mã mẫu lấy từ MISA Settings thay vì hằng số cũ đã sai (§M.4);
  · RefID lấy từ `custom_misa_ref_id` và được GIỮ LẠI (§L.4.1).

Ràng buộc:
  · không `save()` chứng từ đã ghi sổ, chỉ `db_set(update_modified=False)`;
  · không tự hủy/sửa hóa đơn theo dữ liệu MISA — chỉ đặt trạng thái;
  · từ chối đẩy khi tổng tiền dựng được lệch với hóa đơn ERPNext (thà dừng còn
    hơn phát hành sai).
"""

import json
import uuid

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from ketoan.api.misa_client import MISAError, call, get_settings

# Mã hàng xuất theo "Gói" thay vì "Hộp" khi bán theo hộp (giữ nguyên luồng cũ).
GOI_ITEMS = {"BX", "CĐ", "BXRM", "BXSD", "BXMC", "BXCR"}

# Khách hàng nối mã PO vào tên người mua thay vì tạo dòng ghi chú riêng.
PO_IN_NAME = {"Mega Market", "Winmart", "ST KingFood Mart"}
PO_COMMA = {"BigC"}

AMOUNT_GUARD = 1.0  # đồng — lệch quá mức này thì DỪNG, không đẩy

# Đường dẫn đẩy hóa đơn có mã. HẬU TỐ /code, không phải tiền tố code/ như
# đường đọc — xác minh từ luồng đang chạy trên production (§L.3).
PUSH_PATH = "v3sainvoice/code"


# ═══════════════════════════════════════════════════════════════════════════
# Thuế suất
# ═══════════════════════════════════════════════════════════════════════════

def vat_lines(si):
    """Các dòng trong bảng thuế THẬT SỰ là thuế GTGT.

    Bảng `taxes` của ERPNext chứa cả phí vận chuyển, phụ thu... Gộp hết vào tiền
    thuế thì hóa đơn gửi MISA khai sai thuế GTGT, và tệ hơn: chốt chặn so tiền
    dùng chính con số đó cho cả hai vế nên vế "thuế" thành đẳng thức luôn đúng,
    không bao giờ bắt được sai sót.

    Nhận diện: tính trên Net Total / Previous Row (không phải "Actual" nhập tay).
    """
    out = []
    for t in (si.get("taxes") or []):
        ctype = (t.get("charge_type") or "").strip()
        if ctype in ("On Net Total", "On Previous Row Amount", "On Previous Row Total"):
            out.append(t)
    return out


def vat_accounts(si) -> set:
    """Tập tài khoản thuế GTGT có trên chính hóa đơn này."""
    return {(t.get("account_head") or "").strip() for t in vat_lines(si) if t.get("account_head")}


def _row_vat_rate(row, fallback, accounts=None):
    """Thuế suất THẬT của một dòng hóa đơn.

    ERPNext lưu `item_tax_rate` dạng chuỗi JSON {"<tài khoản thuế>": <suất>}.
    Mẫu thuế thường khai CẢ tài khoản đầu ra lẫn đầu vào dùng chung, nên
    sum() toàn bộ dict cho ra thuế suất GẤP ĐÔI. Chỉ lấy tài khoản có mặt trên
    bảng thuế của chính hóa đơn này.
    """
    raw = row.get("item_tax_rate")
    if raw:
        try:
            rates = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if accounts:
                vals = [flt(v) for k, v in rates.items() if (k or "").strip() in accounts]
            else:
                vals = []
            if not vals and len(rates) == 1:
                vals = [flt(v) for v in rates.values()]   # chỉ 1 khóa thì không thể nhầm
            if vals:
                return flt(max(vals))
        except Exception:
            pass
    return flt(fallback)


def _fallback_rate(si):
    """Thuế suất bình quân, tính từ RIÊNG các dòng thuế GTGT."""
    net = flt(si.net_total)
    if not net:
        return 0.0
    vat_total = sum(flt(t.get("tax_amount")) for t in vat_lines(si))
    return vat_total / net * 100.0


# ═══════════════════════════════════════════════════════════════════════════
# Dựng payload
# ═══════════════════════════════════════════════════════════════════════════

def _line(row, idx, ref_id, by_box, vat_rate):
    """Một dòng hàng. RefID của dòng phải BẰNG RefID hóa đơn (§M.5)."""
    cf = flt(row.conversion_factor) or 1.0
    if by_box:
        qty = flt(row.stock_qty) or flt(row.qty) * cf
        unit_price = flt(row.net_rate) / cf if cf else flt(row.net_rate)
        unit_name = "Gói" if row.item_code in GOI_ITEMS else "Hộp"
    else:
        qty = flt(row.qty)
        unit_price = flt(row.net_rate)
        unit_name = row.uom

    amount = flt(qty * unit_price, 2)
    vat_amount = flt(amount * vat_rate / 100.0, 2)

    return {
        "RefDetailID": str(uuid.uuid4()),
        "RefID": ref_id,
        "InventoryItemCode": row.item_code,
        "Description": row.item_name,
        "UnitName": unit_name,
        "Quantity": qty,
        "InWards": 0.0,
        "UnitPrice": unit_price,
        "AmountOC": amount,
        "Amount": amount,
        "DiscountRate": 0.0,
        "DiscountAmountOC": 0.0,
        "DiscountAmount": 0.0,
        "VATRate": vat_rate,
        "VATAmountOC": vat_amount,
        "VATAmount": vat_amount,
        "WageAmountOC": 0.0,
        "WageAmount": 0.0,
        "WagePriceAmount": 0.0,
        "WagePriceDiscountAmount": 0.0,
        "WageDiscountAmountOC": 0.0,
        "SortOrder": idx,
        "IsPromotion": False,
        "IsTemp": False,
        "CompanyID": 0,
        "InventoryItemType": 0,
        "UnitAfterTax": 0.0,
        "AmountAfterTax": 0.0,
        "OutWards": 0.0,
        "SortOrderView": idx,
        "CustomData": "{}",
        "TaxReductionAmount": 0.0,
        "TaxReductionAmountOC": 0.0,
    }


def _po_line(po_no, ref_id, idx):
    """Dòng ghi chú '(Chi tiết theo đơn hàng ...)' — InventoryItemType=3."""
    return {
        "RefDetailID": str(uuid.uuid4()),
        "RefID": ref_id,
        "InventoryItemType": 3,
        "Description": f"(Chi tiết theo đơn hàng {po_no})",
        "SortOrder": idx,
        "SortOrderView": None,
        "CustomData": "{}",
        "Quantity": 0.0,
        "UnitPrice": 0.0,
        "Amount": 0.0,
        "AmountOC": 0.0,
        "DiscountRate": 0.0,
        "DiscountAmount": 0.0,
        "DiscountAmountOC": 0.0,
        "VATRate": 0.0,
        "VATAmount": 0.0,
        "VATAmountOC": 0.0,
    }


def build_payload(si, settings):
    """Dựng object hóa đơn gửi MISA từ một Sales Invoice đã ghi sổ."""
    ref_id = (si.get("custom_misa_ref_id") or "").strip()
    if not ref_id:
        frappe.throw(_("Hóa đơn {0} chưa có RefID MISA — ghi sổ lại hoặc chạy backfill_ref_id").format(si.name))

    by_box = bool(si.get("custom_xuất_theo_hộp_"))
    fallback = _fallback_rate(si)

    accounts = vat_accounts(si)
    lines, rates = [], set()
    for i, row in enumerate(si.items, start=1):
        rate = _row_vat_rate(row, fallback, accounts)
        rates.add(round(rate, 4))
        lines.append(_line(row, i, ref_id, by_box, rate))

    po_no = (si.get("custom_po_") or "").strip()
    if po_no and si.customer not in PO_COMMA and si.customer not in PO_IN_NAME:
        lines.append(_po_line(po_no, ref_id, len(lines) + 1))

    buyer = (si.get("custom_tên_người_mua") or " ")
    if si.customer in PO_COMMA and po_no:
        buyer += f", {po_no}"
    elif si.customer in PO_IN_NAME and po_no:
        buyer += f"PO{po_no}"

    total_net = flt(sum(l.get("Amount") or 0 for l in lines), 2)
    total_vat = flt(sum(l.get("VATAmount") or 0 for l in lines), 2)

    # Chốt chặn: payload dựng ra phải khớp chính hóa đơn ERPNext. Lệch thì DỪNG.
    #
    # So với RIÊNG tiền thuế GTGT, không phải total_taxes_and_charges (có thể lẫn
    # phí vận chuyển). Và phải so CẢ VẾ TỔNG: thiếu nó thì hóa đơn có chiết khấu
    # trên tổng sẽ được phát hành với số tiền cao hơn số phải thu trên sổ.
    book_vat = sum(flt(t.get("tax_amount")) for t in vat_lines(si))
    for label, built, book in (
        ("trước thuế", total_net, flt(si.net_total)),
        ("thuế GTGT", total_vat, book_vat),
        ("tổng tiền", flt(total_net + total_vat, 2), flt(si.grand_total)),
    ):
        if abs(abs(built) - abs(book)) > AMOUNT_GUARD:
            frappe.throw(
                _("Không đẩy hóa đơn {0}: {1} dựng ra {2:,.0f} nhưng trên sổ là {3:,.0f}. "
                  "Kiểm tra lại thuế suất / đơn giá trước khi phát hành.")
                .format(si.name, label, built, book)
            )

    payload = {
        "RefID": ref_id,
        "CompanyID": int(settings.company_id) if str(settings.company_id or "").isdigit() else settings.company_id,
        "OrganizationUnitID": settings.organization_unit_id,
        "InvTemplateNo": settings.inv_template_no,
        "InvoiceType": 1,
        "InvSeries": (settings.series_list() or [""])[0],
        "InvDate": str(si.posting_date),
        "InvNo": "<Chưa cấp số>",
        "AccountObjectTaxCode": (si.get("custom_mã_số_thuế") or "").strip(),
        "AccountObjectName": si.get("custom_tên_đơn_vị"),
        "AccountObjectAddress": si.get("custom_địa_chỉ"),
        "ContactName": buyer,
        "ReceiverEmail": si.get("custom_email_nhận_hoá_đơn"),
        "ReceiverName": buyer,
        "PaymentMethod": si.get("custom_hình_thức_thanh_toán"),
        "CurrencyCode": "VND",
        "ExchangeRate": 1.0,
        "VATRate": sorted(rates)[-1] if rates else 0.0,
        "IsMoreVATRate": len(rates) > 1,
        "TotalSaleAmountOC": total_net,
        "TotalVATAmountOC": total_vat,
        "TotalAmountOC": flt(total_net + total_vat, 2),
        "TotalSaleAmount": total_net,
        "TotalVATAmount": total_vat,
        "TotalAmount": flt(total_net + total_vat, 2),
        "EInvoiceStatus": 1,
        "CreatedDate": str(si.posting_date),
        "ModifiedDate": str(si.posting_date),
        "InvoiceDetails": lines,
        "InvoiceTemplateID": settings.invoice_template_id,
        "UserID": settings.misa_user_id,
    }
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# Đẩy
# ═══════════════════════════════════════════════════════════════════════════

def _rejected_reason(result, ref_id):
    """Đọc phản hồi của endpoint đẩy, trả lý do TỪ CHỐI hoặc None nếu MISA nhận.

    MISA nhận MẢNG hóa đơn nên báo kết quả theo từng phần tử; cờ success ở tầng
    ngoài đúng không có nghĩa hóa đơn được tạo. Trả None khi không tìm thấy dấu
    hiệu từ chối — im lặng không phải bằng chứng lỗi, nhưng phần tử nào nói rõ
    Success=false thì phải chặn.
    """
    items = result if isinstance(result, list) else ([result] if isinstance(result, dict) else [])
    for it in items:
        if not isinstance(it, dict):
            continue
        low = {str(k).lower(): v for k, v in it.items()}
        rid = str(low.get("refid") or "").strip()
        if rid and ref_id and rid.lower() != str(ref_id).lower():
            continue
        ok = low.get("success")
        code = low.get("errorcode") or low.get("error_code")
        msg = low.get("errormessage") or low.get("message") or low.get("error")
        if ok is False or (code not in (None, "", 0, "0")):
            return f"[{code or 'error'}] {msg or 'MISA không tạo được hóa đơn'}"
    return None


def _guard(si_name):
    """Ai ghi sổ được hóa đơn thì đẩy được hóa đơn đó. Không cấp quyền thừa."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập"), frappe.PermissionError)
    if not frappe.has_permission("Sales Invoice", "submit", doc=si_name):
        frappe.throw(_("Bạn không có quyền phát hành hóa đơn này"), frappe.PermissionError)


def _require(settings):
    missing = [
        label for key, label in (
            ("company_id", "CompanyID"),
            ("organization_unit_id", "OrganizationUnitID"),
            ("inv_template_no", "InvTemplateNo"),
            ("invoice_template_id", "InvoiceTemplateID"),
            ("misa_user_id", "UserID trên MISA"),
        ) if not (settings.get(key) or "")
    ]
    if not settings.series_list():
        missing.append("Ký hiệu hóa đơn đang dùng")
    if missing:
        frappe.throw(_("MISA Settings còn thiếu: {0}").format(", ".join(missing)))


@frappe.whitelist()
def push_invoice(sales_invoice):
    """Đẩy 1 hóa đơn sang MISA. Trả về dict để Client Script hiển thị.

    Chặn đẩy trùng bằng HAI điều kiện: `custom_misa_pushed_at` (luồng mới) và
    `vn_einvoice_lookup_code` (luồng cũ). Bỏ vế thứ hai là hóa đơn cũ bị phát
    hành lần thứ hai.
    """
    _guard(sales_invoice)

    settings = get_settings()
    if not settings.enable_push:
        frappe.throw(_("Chưa bật 'Cho phép đẩy hóa đơn' trong MISA Settings"))
    _require(settings)

    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        frappe.throw(_("Chỉ đẩy hóa đơn đã ghi sổ"))
    if si.get("is_return"):
        # Hóa đơn trả hàng phải đi đường điều chỉnh/thay thế (cần OrgRefID) —
        # quy trình khác hẳn, con người quyết định (rủi ro E2).
        frappe.throw(_("Hóa đơn trả hàng phải xử lý bằng hóa đơn điều chỉnh/thay thế trên MISA"))

    payload = build_payload(si, settings)

    # KHÓA HÀNG ở tầng database (SELECT ... FOR UPDATE) trên chính bản ghi hóa
    # đơn. Không có khóa thì auto-push (chạy ngầm, không khóa màn hình) và nút
    # bấm tay có thể cùng vượt qua bước kiểm "đã đẩy chưa" rồi cùng POST — hai
    # hóa đơn có giá trị pháp lý cho một chứng từ, không rút lại được.
    #
    # Request thứ hai nằm chờ ở đây tới khi request thứ nhất commit, rồi đọc
    # được cờ đã đẩy và dừng. Khóa giữ trong lúc gọi HTTP (tối đa 60s) — đắt,
    # nhưng rẻ hơn nhiều so với phát hành trùng.
    frappe.db.get_value("Sales Invoice", si.name, "name", for_update=True)

    try:
        # Đọc LẠI cờ chặn trùng SAU KHI có khóa — giá trị đọc trước đó có thể đã cũ.
        fresh = frappe.db.get_value(
            "Sales Invoice", si.name,
            ["custom_misa_pushed_at", "vn_einvoice_lookup_code", "custom_misa_inv_no"], as_dict=True) or {}
        if fresh.get("custom_misa_pushed_at") or fresh.get("vn_einvoice_lookup_code") \
                or fresh.get("custom_misa_inv_no"):
            return {"ok": False, "already": True, "message": _("Hóa đơn đã được xuất trước đó")}

        try:
            # ⚠ Đẩy dùng HẬU TỐ `/code`, còn đọc dùng TIỀN TỐ `code/`. Hai quy ước
            # khác nhau của MISA — chép nguyên từ luồng đang chạy, đừng "sửa cho
            # nhất quán": POST v3sainvoice/code  vs  GET code/v3sainvoice/afterpublishing/…
            result = call(PUSH_PATH, payload=[payload], method="POST")
        except MISAError as e:
            frappe.db.set_value(
                "Sales Invoice", si.name,
                {"custom_misa_status": "Phát hành lỗi", "custom_misa_note": f"[{e.code}] {e.message}"[:500]},
                update_modified=False,
            )
            frappe.db.commit()
            return {"ok": False, "message": _("MISA từ chối: {0}").format(e.message)}

        # Endpoint nhận MẢNG hóa đơn nên MISA báo lỗi TỪNG PHẦN TỬ trong thân
        # phản hồi, cờ success ở tầng ngoài vẫn true. Không soi vào đây thì hóa
        # đơn MISA từ chối vẫn bị đánh dấu "đã đẩy" và không bao giờ đẩy lại được.
        rejected = _rejected_reason(result, payload["RefID"])
        if rejected:
            frappe.db.set_value(
                "Sales Invoice", si.name,
                {"custom_misa_status": "Phát hành lỗi", "custom_misa_note": rejected[:500]},
                update_modified=False,
            )
            frappe.db.commit()
            return {"ok": False, "message": _("MISA từ chối: {0}").format(rejected)}

        frappe.db.set_value(
            "Sales Invoice", si.name,
            {
                "custom_misa_pushed_at": now_datetime(),
                "custom_misa_status": "Đã đẩy (nháp)",
                "custom_misa_inv_series": payload["InvSeries"],
                "custom_misa_note": None,
            },
            update_modified=False,
        )
        frappe.db.commit()   # nhả khóa hàng
    except Exception:
        frappe.db.rollback()  # nhả khóa hàng kể cả khi vỡ giữa chừng
        raise
    return {
        "ok": True,
        "message": _("Đã đẩy hóa đơn sang MISA. Số hóa đơn sẽ tự điền về khi MISA cấp số."),
        "ref_id": payload["RefID"],
        "vat_rates": sorted({l.get("VATRate") for l in payload["InvoiceDetails"] if l.get("Quantity")}),
    }


@frappe.whitelist()
def preview_payload(sales_invoice):
    """Xem trước payload sẽ gửi — KHÔNG gọi MISA. Dùng để kiểm trước khi bật đẩy."""
    _guard(sales_invoice)
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    return build_payload(si, get_settings())
