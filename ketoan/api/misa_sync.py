"""misa_sync — các job đồng bộ với MISA meInvoice.

Nguyên tắc cô lập blast radius: chỉ job ở đây được ghi vào Sales Invoice, và chỉ
ghi bằng `db_set(update_modified=False)` — TUYỆT ĐỐI không `save()` chứng từ đã
ghi sổ.

Hợp đồng API: docs/misa/misa_api_contract.md §L.2 (token) và §M (chi tiết hóa
đơn sau phát hành). Mọi tên field dưới đây đều đã xác minh trên dữ liệu thật.
"""

import uuid

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from ketoan.api.misa_client import MISAError, call, get_settings, invoice_path
from ketoan.api.misa_desk import invoice_links

# Field ERPNext nhận số hóa đơn về. Nhóm vn_einvoice_* là mặt hiển thị cho kế
# toán (6 màn hình của app đang đọc), nhóm custom_misa_* là dữ liệu kỹ thuật.
LEGACY_NO = "vn_einvoice_number"
LEGACY_DATE = "vn_einvoice_date"
LEGACY_LOOKUP = "vn_einvoice_lookup_code"


# ═══════════════════════════════════════════════════════════════════════════
# Khóa nối
# ═══════════════════════════════════════════════════════════════════════════

def ensure_ref_id(doc, method=None):
    """doc_events Sales Invoice.before_submit — sinh `custom_misa_ref_id` nếu chưa có.

    Đây là khóa nối gốc giữa ERPNext và MISA: phải tồn tại TRƯỚC khi đẩy và phải
    được lưu lại (luồng cũ sinh uuid rồi vứt đi — §L.4.1).

    BẤT DI BẤT DỊCH: hàm này KHÔNG BAO GIỜ được chặn submit. Kế toán phải ghi sổ
    được kể cả khi tích hợp MISA hỏng hoàn toàn (ràng buộc 13.3).
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

    Lưu ý: ref_id sinh bây giờ KHÔNG khớp ngược được với MISA — MISA giữ ref_id
    khác do luồng cũ sinh rồi vứt (§L.4.1). Hóa đơn cũ phải đối soát bằng tầng
    MST + ngày + tiền. Cấp ref_id ở đây chỉ để mọi hóa đơn đều có khóa.
    """
    from ketoan.api._guard import guard_manager

    guard_manager()
    rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "custom_misa_ref_id": ("is", "not set")},
        pluck="name",
        order_by="posting_date desc",
        limit=int(limit or 500),
    )
    done = 0
    for name in rows:
        try:
            frappe.db.set_value(
                "Sales Invoice", name, "custom_misa_ref_id", str(uuid.uuid4()), update_modified=False
            )
            done += 1
            if done % 50 == 0:
                frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"misa_sync.backfill_ref_id {name}")
    frappe.db.commit()
    return {
        "updated": done,
        "remaining": frappe.db.count(
            "Sales Invoice", {"docstatus": 1, "custom_misa_ref_id": ("is", "not set")}
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Chuẩn hóa giá trị MISA trả về
# ═══════════════════════════════════════════════════════════════════════════

def misa_date(v):
    """MISA trả '2026-08-17T00:00:00+07:00' (chi tiết) hoặc '...T00:00:00' (danh sách).

    Cắt 10 ký tự đầu. KHÔNG dùng parser tự đoán múi giờ — lệch 1 ngày là sai sổ.
    """
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else None


def _pick(d, *names):
    """Lấy key không phân biệt hoa thường (§H.1)."""
    if not isinstance(d, dict):
        return None
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(str(n).lower())
        if v not in (None, ""):
            return v
    return None


def _as_invoice(data):
    """`afterpublishing` trả về object, hoặc mảng rỗng khi chưa có/sai route."""
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    return data if isinstance(data, dict) else None


# ═══════════════════════════════════════════════════════════════════════════
# So tiền
# ═══════════════════════════════════════════════════════════════════════════

def check_amount_drift(si, misa, tolerance):
    """So 3 vế: trước thuế / thuế / tổng. Trả về list mô tả chỗ lệch (rỗng = khớp).

    Phải tách 3 vế — lệch thuế suất mà tổng vẫn trùng là tình huống có thật.
    Hóa đơn trả về mang số âm ở ERPNext nên so theo trị tuyệt đối.
    """
    pairs = (
        ("trước thuế", _pick(misa, "TotalAmountWithoutVAT"), si.get("net_total")),
        ("thuế GTGT", _pick(misa, "TotalVATAmount"), si.get("total_taxes_and_charges")),
        ("tổng tiền", _pick(misa, "TotalAmount"), si.get("grand_total")),
    )
    out = []
    for label, m, e in pairs:
        if m is None:
            continue
        diff = abs(flt(m)) - abs(flt(e))
        if abs(diff) > flt(tolerance):
            out.append(f"{label}: MISA {flt(m):,.0f} ≠ ERPNext {flt(e):,.0f} (lệch {diff:,.0f})")
    return out


def _todo(si_name, description):
    """Giao việc cho kế toán. Hệ thống KHÔNG tự sửa/hủy hóa đơn (ràng buộc 13.4)."""
    try:
        if frappe.db.exists(
            "ToDo", {"reference_type": "Sales Invoice", "reference_name": si_name, "status": "Open"}
        ):
            return
        frappe.get_doc({
            "doctype": "ToDo",
            "description": description,
            "reference_type": "Sales Invoice",
            "reference_name": si_name,
            "priority": "High",
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"misa_sync._todo {si_name}")


# ═══════════════════════════════════════════════════════════════════════════
# poll_pending — kéo số hóa đơn về Sales Invoice
# ═══════════════════════════════════════════════════════════════════════════

def _write(si_name, values):
    """Ghi nhiều field bằng db_set. Bỏ field không tồn tại trên site."""
    meta = frappe.get_meta("Sales Invoice")
    payload = {k: v for k, v in values.items() if meta.has_field(k)}
    if payload:
        frappe.db.set_value("Sales Invoice", si_name, payload, update_modified=False)


@frappe.whitelist()
def poll_pending(limit=500, lookback_days=60, trigger_type="Manual"):
    """Hỏi MISA số hóa đơn cho các SI đã đẩy mà chưa có số, rồi ghi ngược về.

    Quét: docstatus=1, có custom_misa_ref_id, chưa có custom_misa_inv_no,
          posting_date >= hôm nay − lookback_days.

    Mỗi hóa đơn: GET code/v3sainvoice/afterpublishing/{ref_id} (§M).
      · chưa có số  → custom_misa_status = 'Đã đẩy (nháp)'
      · có số       → ghi ký hiệu/số/ngày/mã tra cứu/mã CQT + nhóm vn_einvoice_*
                    → so tiền 3 vế; lệch thì đặt 'Lệch tiền' và tạo ToDo
      · bị hủy      → 'Đã hủy'    (IsInvoiceDeleted=True)
      · bị thay thế → 'Đã thay thế' (OrgRefID có giá trị)
    Luôn cập nhật custom_misa_last_checked, kể cả khi chưa có số.

    Trả về tên bản ghi `MISA Sync Run`.
    """
    from ketoan.api._guard import guard_manager

    guard_manager()
    return _poll_pending(int(limit or 500), int(lookback_days or 60), trigger_type)


def _poll_pending(limit, lookback_days, trigger_type="Manual"):
    settings = get_settings()
    tolerance = flt(settings.amount_tolerance) or 1.0

    run = frappe.get_doc({
        "doctype": "MISA Sync Run",
        "job_type": "poll_pending",
        "trigger_type": trigger_type,
        "from_date": frappe.utils.add_days(nowdate(), -lookback_days),
        "to_date": nowdate(),
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    rows = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "custom_misa_ref_id": ("is", "set"),
            "custom_misa_inv_no": ("is", "not set"),
            "posting_date": (">=", frappe.utils.add_days(nowdate(), -lookback_days)),
        },
        fields=[
            "name", "custom_misa_ref_id", "net_total", "total_taxes_and_charges",
            "grand_total", "is_return",
        ],
        order_by="posting_date desc",
        limit=limit,
    )

    stat = {"fetched": 0, "updated": 0, "matched": 0, "mismatched": 0}
    errors = []

    for i, si in enumerate(rows):
        try:
            data = call(
                invoice_path(f"v3sainvoice/afterpublishing/{si.custom_misa_ref_id}", settings),
                method="GET",
            )
        except MISAError as e:
            errors.append(f"{si.name}: [{e.code}] {e.message}")
            continue
        except Exception as e:
            errors.append(f"{si.name}: {type(e).__name__}")
            continue

        inv = _as_invoice(data)
        stat["fetched"] += 1
        now = now_datetime()

        if not inv:
            # MISA chưa biết hóa đơn này — đã đẩy dạng nháp, hoặc chưa từng đẩy.
            _write(si.name, {"custom_misa_status": "Đã đẩy (nháp)", "custom_misa_last_checked": now})
            continue

        inv_no = _pick(inv, "InvNo")
        if not inv_no or str(inv_no).startswith("<"):
            # MISA giữ chỗ '<Chưa cấp số>' khi hóa đơn còn nháp.
            _write(si.name, {"custom_misa_status": "Đã đẩy (nháp)", "custom_misa_last_checked": now})
            continue

        drift = check_amount_drift(si, inv, tolerance)
        if _pick(inv, "IsInvoiceDeleted") is True:
            status = "Đã hủy"
        elif _pick(inv, "OrgRefID"):
            status = "Đã thay thế"
        elif drift:
            status = "Lệch tiền"
        else:
            status = "Đã phát hành"

        inv_date = misa_date(_pick(inv, "InvDate"))
        values = {
            "custom_misa_inv_no": str(inv_no),
            "custom_misa_inv_series": _pick(inv, "InvSeries") or "",
            "custom_misa_inv_date": inv_date,
            "custom_misa_transaction_id": _pick(inv, "TransactionID") or "",
            "custom_misa_invoice_code": _pick(inv, "InvoiceCode") or "",
            "custom_misa_link": invoice_links({
                "custom_misa_ref_id": si.custom_misa_ref_id,
                "custom_misa_transaction_id": _pick(inv, "TransactionID"),
                "custom_misa_inv_no": inv_no,
                "custom_misa_inv_series": _pick(inv, "InvSeries"),
                "custom_misa_invoice_code": _pick(inv, "InvoiceCode"),
            }, settings).get("primary"),
            "custom_misa_status": status,
            "custom_misa_last_checked": now,
            # Đồng bộ ngược sang nhóm hiển thị — chỉ ghi khi đang trống, không đè
            # số kế toán đã điền tay (rủi ro E4).
            **_legacy_values(si.name, inv_no, inv_date, _pick(inv, "TransactionID")),
        }
        if drift:
            values["custom_misa_note"] = " · ".join(drift)

        _write(si.name, values)
        stat["updated"] += 1
        if drift:
            stat["mismatched"] += 1
            _todo(si.name, _("Hóa đơn {0} lệch tiền với MISA: {1}").format(si.name, " · ".join(drift)))
        else:
            stat["matched"] += 1
        if status in ("Đã hủy", "Đã thay thế"):
            _todo(si.name, _("Hóa đơn {0} trên MISA đang ở trạng thái {1} — cần xử lý").format(si.name, status))

        if (i + 1) % 50 == 0:
            frappe.db.commit()

    frappe.db.commit()

    if errors:
        run.error_log = "\n".join(errors[-200:])
    for k, v in stat.items():
        setattr(run, k, v)
    run.status = "Lỗi" if (errors and not stat["updated"]) else ("Thành công một phần" if errors else "Thành công")
    run.finished_at = now_datetime()
    run.save(ignore_permissions=True)
    frappe.db.commit()
    return run.name


def _legacy_values(si_name, inv_no, inv_date, transaction_id):
    """Điền nhóm vn_einvoice_* — CHỈ khi đang trống (rủi ro E4: không đè số nhập tay)."""
    meta = frappe.get_meta("Sales Invoice")
    out = {}
    current = frappe.db.get_value(
        "Sales Invoice", si_name,
        [f for f in (LEGACY_NO, LEGACY_DATE, LEGACY_LOOKUP) if meta.has_field(f)] or ["name"],
        as_dict=True,
    ) or {}
    if meta.has_field(LEGACY_NO) and not (current.get(LEGACY_NO) or "").strip():
        out[LEGACY_NO] = str(inv_no)
    if meta.has_field(LEGACY_DATE) and not current.get(LEGACY_DATE) and inv_date:
        out[LEGACY_DATE] = inv_date
    if meta.has_field(LEGACY_LOOKUP) and transaction_id:
        # lookup_code cũ là rác do lỗi §L.4.1 → ghi đè bằng mã tra cứu thật.
        out[LEGACY_LOOKUP] = str(transaction_id)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Job theo lịch — chỉ chạy khi bật công tắc
# ═══════════════════════════════════════════════════════════════════════════

def scheduled_poll_pending():
    """cron — hỏi số hóa đơn. Dừng ngay ở dòng đầu nếu chưa bật đồng bộ tự động."""
    try:
        if not get_settings().enable_auto_sync:
            return
        frappe.enqueue(
            "ketoan.api.misa_sync._poll_pending",
            queue="long", timeout=1800,
            limit=500, lookback_days=60, trigger_type="Scheduled",
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "misa_sync.scheduled_poll_pending")
