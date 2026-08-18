"""misa_sync — các job đồng bộ với MISA meInvoice.

Nguyên tắc cô lập blast radius: chỉ job ở đây được ghi vào Sales Invoice, và chỉ
ghi bằng `db_set(update_modified=False)` — TUYỆT ĐỐI không `save()` chứng từ đã
ghi sổ.

Hợp đồng API: docs/misa/misa_api_contract.md §L.2 (token) và §M (chi tiết hóa
đơn sau phát hành). Mọi tên field dưới đây đều đã xác minh trên dữ liệu thật.
"""

import re
import time
import uuid

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from ketoan.api.misa_client import PAGE_SLEEP, MISAError, call, get_settings, invoice_path
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

        # Hóa đơn sửa đổi (amend) được sao chép từ bản đã hủy, mang theo nguyên
        # ref_id và cả số hóa đơn của bản cũ. Không dọn thì: ref_id đã có nên
        # không sinh mới, pushed_at đã có nên push_invoice trả "đã xuất rồi", và
        # bản sửa đổi VĨNH VIỄN không bao giờ được phát hành — trong khi màn hình
        # vẫn hiện số hóa đơn của bản đã hủy.
        #
        # Không trông vào no_copy: frappe.model.copy_doc bỏ qua cờ đó khi amend.
        if doc.get("amended_from"):
            for f in ("custom_misa_inv_no", "custom_misa_inv_series", "custom_misa_inv_date",
                      "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
                      "custom_misa_pushed_at", "custom_misa_last_checked", "custom_misa_note",
                      "custom_misa_relation", "custom_misa_org_ref_id", "custom_misa_org_inv",
                      "vn_einvoice_number", "vn_einvoice_date", "vn_einvoice_lookup_code"):
                if doc.meta.has_field(f):
                    doc.set(f, None)
            doc.custom_misa_ref_id = str(uuid.uuid4())
            if doc.meta.has_field("custom_misa_status"):
                doc.custom_misa_status = "Chưa đẩy"
            return

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


def _mark_superseded(org_ref_id, by_si, by_inv_no, by_inv_series):
    """Đánh dấu hóa đơn GỐC đã bị hóa đơn khác thay thế/điều chỉnh.

    Chỉ ghi trạng thái + giao việc. Hệ thống KHÔNG tự hủy Sales Invoice dựa
    trên dữ liệu MISA (ràng buộc 13.4) — người quyết định.
    """
    try:
        org = frappe.db.get_value(
            "Sales Invoice", {"custom_misa_ref_id": org_ref_id},
            ["name", "docstatus", "custom_misa_status"], as_dict=True)
        if not org or org.name == by_si:
            return  # MISA giữ bản gốc mà ERPNext không có — không bịa ra liên kết
        if org.custom_misa_status == "Đã thay thế":
            return

        frappe.db.set_value("Sales Invoice", org.name, {
            "custom_misa_status": "Đã thay thế",
            "custom_misa_relation": "Bị thay thế/điều chỉnh",
            "custom_misa_org_inv": " ".join(
                x for x in (str(by_inv_series or "").strip(), str(by_inv_no or "").strip()) if x),
        }, update_modified=False)

        if org.docstatus == 1:
            # Bản gốc vẫn đang ghi sổ trong khi bản thay thế cũng đã phát hành:
            # một lần bán đang được ghi nhận hai lần.
            _todo(org.name, _(
                "Hóa đơn {0} đã BỊ hóa đơn {1} thay thế/điều chỉnh trên MISA nhưng vẫn đang ghi sổ "
                "— kiểm tra xem có khai trùng doanh thu không"
            ).format(org.name, by_si))
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"misa_sync._mark_superseded {org_ref_id}")


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
      · chưa có mã CQT → 'Chờ cấp mã' (có số nhưng InvoiceCode rỗng)
      · có OrgRefID → bản này LÀ bản thay thế/điều chỉnh (còn hiệu lực);
                      hóa đơn GỐC mới bị đặt 'Đã thay thế'
    Luôn cập nhật custom_misa_last_checked, kể cả khi chưa có số.

    Trả về tên bản ghi `MISA Sync Run`.
    """
    from ketoan.api._guard import guard_manager

    guard_manager()
    return _poll_pending(int(limit or 500), int(lookback_days or 60), trigger_type)


def _poll_pending(limit, lookback_days, trigger_type="Manual"):
    settings = get_settings()
    tolerance = flt(settings.amount_tolerance) or 1.0
    # Hóa đơn CÓ mã của cơ quan thuế thì mã CQT là điều kiện hợp lệ. Đơn vị dùng
    # hóa đơn KHÔNG mã thì không bao giờ có mã đó — bắt buộc phải nhìn cờ này,
    # không thì mọi hóa đơn của họ đứng vĩnh viễn ở "Chờ cấp mã".
    needs_tax_code = bool(settings.use_code_route)

    run = frappe.get_doc({
        "doctype": "MISA Sync Run",
        "job_type": "poll_pending",
        "trigger_type": trigger_type,
        "from_date": frappe.utils.add_days(nowdate(), -lookback_days),
        "to_date": nowdate(),
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    since = frappe.utils.add_days(nowdate(), -lookback_days)
    fields = [
        "name", "custom_misa_ref_id", "net_total", "total_taxes_and_charges",
        "grand_total", "is_return", "custom_misa_pushed_at", "custom_misa_inv_no",
    ]

    # Vòng 1 — hóa đơn CHƯA có số: hỏi xem MISA cấp số chưa.
    rows = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "custom_misa_ref_id": ("is", "set"),
            "custom_misa_inv_no": ("is", "not set"),
            "posting_date": (">=", since),
        },
        fields=fields, order_by="posting_date desc", limit=limit,
    )

    # Vòng 2 — hóa đơn ĐÃ có số nhưng chưa ở trạng thái cuối.
    #
    # Thiếu vòng này thì hóa đơn bị HỦY hoặc bị THAY THẾ trên MISA sau khi đã cấp
    # số sẽ không bao giờ bị phát hiện: bộ lọc vòng 1 loại chúng ra, nên nhánh
    # "Đã hủy"/"Đã thay thế" thành code chết. Rủi ro thuế thật — sổ vẫn ghi hóa
    # đơn hợp lệ trong khi bên MISA nó đã bị hủy.
    watch = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "custom_misa_ref_id": ("is", "set"),
            "custom_misa_inv_no": ("is", "set"),
            "custom_misa_status": ("not in", ["Đã hủy", "Đã thay thế"]),
            "posting_date": (">=", since),
        },
        fields=fields, order_by="custom_misa_last_checked asc", limit=limit,
    )
    seen_names = {r.name for r in rows}
    rows = rows + [r for r in watch if r.name not in seen_names]

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

        # MISA không biết hóa đơn này. Chỉ được nói "đã đẩy (nháp)" khi ta THẬT
        # SỰ đã đẩy — backfill_ref_id cấp ref_id cho cả hóa đơn chưa từng đẩy,
        # ghi bừa "đã đẩy" là khẳng định sai về nghĩa vụ thuế.
        pending = "Đã đẩy (nháp)" if si.get("custom_misa_pushed_at") else "Chưa đẩy"

        if not inv:
            if si.get("custom_misa_inv_no"):
                # Hóa đơn đã có số mà lần này MISA không trả — có thể lỗi tạm.
                # Chỉ ghi nhận đã kiểm, KHÔNG hạ trạng thái đang đúng.
                _write(si.name, {"custom_misa_last_checked": now})
            else:
                _write(si.name, {"custom_misa_status": pending, "custom_misa_last_checked": now})
            continue

        inv_no = _pick(inv, "InvNo")
        if not inv_no or str(inv_no).startswith("<"):
            # MISA giữ chỗ '<Chưa cấp số>' khi hóa đơn còn nháp.
            _write(si.name, {"custom_misa_status": pending, "custom_misa_last_checked": now})
            continue

        drift = check_amount_drift(si, inv, tolerance)
        inv_code = str(_pick(inv, "InvoiceCode") or "").strip()
        org_ref = str(_pick(inv, "OrgRefID") or "").strip()

        # ─ TRỤC 1: giá trị pháp lý ────────────────────────────────────────
        #
        # `OrgRefID` KHÔNG thuộc trục này. §M.3: "OrgRefID có giá trị → bản này
        # THAY THẾ hóa đơn OrgRefID" — tức bản đang xét là bản MỚI, còn hiệu
        # lực. Bản cũ dán nhãn "Đã thay thế" lên chính nó là ngược: hóa đơn
        # sống bị coi như đã chết, còn hóa đơn chết thật (bản gốc) thì không ai
        # đụng tới và vẫn hiện "Đã phát hành".
        #
        # Mã CQT là ranh giới pháp lý thật: có số hóa đơn mới chỉ là MISA đã
        # đánh số, phải có mã cơ quan thuế cấp thì hóa đơn mới hợp lệ. Gọi
        # "Đã phát hành" khi chưa có mã là khẳng định sai nghĩa vụ thuế.
        if _pick(inv, "IsInvoiceDeleted") is True:
            status = "Đã hủy"
        elif needs_tax_code and not inv_code:
            status = "Chờ cấp mã"
        elif drift:
            status = "Lệch tiền"
        else:
            status = "Đã phát hành"

        # ─ TRỤC 2: quan hệ thay thế/điều chỉnh ────────────────────────────
        #
        # Chỉ chốt "có quan hệ" hay "không", chưa tách thay thế với điều chỉnh:
        # phân biệt hai loại phải đọc `TypeChangeInvoice`, mà bảng giá trị của
        # enum đó chưa xác minh (§M.3 mẫu thật trả None). Đoán ở đây là sai kỳ
        # kê khai — hóa đơn thay thế xóa hiệu lực bản gốc, hóa đơn điều chỉnh
        # thì bản gốc vẫn còn hiệu lực và chỉ cộng thêm phần chênh.
        relation = "Hóa đơn thay thế/điều chỉnh" if org_ref else "Hóa đơn mới"
        org_inv = " ".join(x for x in (
            str(_pick(inv, "OrgInvSeries") or "").strip(),
            str(_pick(inv, "OrgInvNo") or "").strip(),
        ) if x)

        inv_date = misa_date(_pick(inv, "InvDate"))
        values = {
            "custom_misa_inv_no": str(inv_no),
            "custom_misa_inv_series": _pick(inv, "InvSeries") or "",
            "custom_misa_inv_date": inv_date,
            "custom_misa_transaction_id": _pick(inv, "TransactionID") or "",
            "custom_misa_invoice_code": inv_code,
            "custom_misa_relation": relation,
            "custom_misa_org_ref_id": org_ref,
            "custom_misa_org_inv": org_inv,
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
        conflict = values.pop("__conflict__", None)
        notes = list(drift)
        if conflict:
            notes.append(conflict)
            status = "Lệch tiền" if status == "Đã phát hành" else status
        if notes:
            values["custom_misa_note"] = " · ".join(notes)
            values["custom_misa_status"] = status

        _write(si.name, values)
        stat["updated"] += 1
        if notes:
            stat["mismatched"] += 1
            _todo(si.name, _("Hóa đơn {0} lệch với MISA: {1}").format(si.name, " · ".join(notes)))
        else:
            stat["matched"] += 1
        if status in ("Đã hủy", "Đã thay thế"):
            _todo(si.name, _("Hóa đơn {0} trên MISA đang ở trạng thái {1} — cần xử lý").format(si.name, status))
        if status == "Chờ cấp mã":
            _todo(si.name, _(
                "Hóa đơn {0} đã có số nhưng cơ quan thuế CHƯA cấp mã — chưa hợp lệ để giao khách"
            ).format(si.name))

        # Bản gốc mới là bản hết hiệu lực. Không dán nhãn cho nó thì hai hóa đơn
        # cùng hiện "Đã phát hành" cho một lần bán — doanh thu và thuế đầu ra
        # bị khai gấp đôi.
        if org_ref:
            _mark_superseded(org_ref, si.name, inv_no, _pick(inv, "InvSeries"))

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
    if meta.has_field(LEGACY_NO):
        have = (current.get(LEGACY_NO) or "").strip()
        if not have:
            out[LEGACY_NO] = str(inv_no)
        elif have != str(inv_no):
            # Không đè số kế toán đã điền tay, NHƯNG cũng không được im lặng:
            # 6 màn hình đang đọc field này sẽ tiếp tục hiện số sai.
            out["__conflict__"] = f"Số hóa đơn lệch: sổ ghi {have}, MISA cấp {inv_no}"
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


# ═══════════════════════════════════════════════════════════════════════════
# pull_invoices — kéo danh sách hóa đơn MISA về MISA Invoice Snapshot
# ═══════════════════════════════════════════════════════════════════════════

# Bộ tham số chép NGUYÊN từ request thật của lưới hóa đơn MISA (§J.3). Đừng
# rút gọn: thử với 4 tham số đã trả về mảng rỗng (§M.6).
#
# `columns` quyết định field nào có giá trị trong response (§J.6) — thêm
# TotalAmountWithoutVAT/TotalVATAmount để lấy được tách thuế ngay từ danh sách.
PAGING_COLUMNS = ",".join([
    "InvSeries", "InvDate", "InvNo", "InvoiceCode", "AccountObjectName",
    "AccountObjectTaxCode", "ContactName", "PaymentStatus", "TotalAmount",
    "TotalAmountWithoutVAT", "TotalVATAmount", "TotalAmountOC",
    "EInvoiceStatus", "PublishStatus", "TransactionID", "SendInvoiceStatus",
    "RefID", "SendToTaxStatus", "ApproveStep", "CurrencyCode",
    "OrganizationUnitID", "EditVersion", "AccountObjectCode", "ReceiverEmail",
    "InvoiceType", "IsTemplatePetrol", "BusinessArea", "IsTradeDiscountInvoice",
    "ListNo", "ListDate", "SortOrder",
])

# invoiceSummaryStatus đã bị GỠ: MISA dựng SQL từ tham số gửi lên, và tham số
# đó trỏ vào cột `InvoiceSummaryStatus` không tồn tại trong bảng hóa đơn CÓ MÃ
# → "Unknown column ... in 'where clause'". Lưới trên app3 gửi được vì nó chạy
# trên bảng khác.
# ĐÃ XÁC MINH trên site thật (§P): chỉ cần start + length + fromDate + toDate.
# Mọi tham số khác chép từ lưới web đều KHÔNG cần, và invoiceSummaryStatus còn
# làm vỡ SQL. Giữ bộ tối giản — thêm thứ chưa xác minh chỉ tạo thêm chỗ hỏng.
PAGING_BASE = {}

PAGE_SIZE = 100  # server tôn trọng length (đã thử 5); vòng lặp tiến theo số dòng THẬT
MAX_PAGES = 100


# Cột MISA báo thiếu → tham số cần gỡ. Bảng hóa đơn có mã và không mã khác nhau
# về cột, nên bộ tham số chép từ lưới web không phải lúc nào cũng dùng được.
_UNKNOWN_COL = re.compile(r"Unknown column '([^']+)'", re.I)


# Bộ tối giản ĐÃ XÁC MINH trả dữ liệu. Dùng làm lưới an toàn khi bộ đầy đủ rỗng.
MINIMAL_KEYS = ("start", "length", "fromDate", "toDate")


def _paging_call(settings, payload, dropped, max_drop=6):
    """Gọi endpoint danh sách, tự gỡ tham số nào khiến MISA vỡ SQL rồi gọi lại.

    Trả về (rows, meta). `dropped` là set dùng chung giữa các trang để đã gỡ rồi
    thì trang sau không gửi lại.

    Nếu bộ đầy đủ trả 0 dòng, thử lại bằng bộ TỐI GIẢN đã xác minh: `columns`
    chưa được kiểm chứng cùng biến thể chạy được, thà lấy được dữ liệu với ít
    cột còn hơn im lặng trả rỗng.
    """
    rows, meta = _paging_try(settings, payload, dropped, max_drop)
    if not rows and any(k not in MINIMAL_KEYS for k in payload):
        minimal = {k: v for k, v in payload.items() if k in MINIMAL_KEYS}
        rows2, meta2 = _paging_try(settings, minimal, set(), max_drop)
        if rows2:
            frappe.logger().info("misa: bộ tham số đầy đủ trả rỗng, dùng bộ tối giản")
            return rows2, meta2
    return rows, meta


def _paging_try(settings, payload, dropped, max_drop=6):
    payload = {k: v for k, v in payload.items() if k not in dropped}
    for _ in range(max_drop):
        try:
            data, meta = call(invoice_path("v3sainvoice/paging", settings),
                              payload=payload, method="POST", form=True, with_meta=True)
            return (data if isinstance(data, list) else []), meta
        except MISAError as e:
            m = _UNKNOWN_COL.search(e.message or "")
            if not m:
                raise
            col = m.group(1).lower()
            victim = next((k for k in payload if k.lower() == col), None)
            if not victim:
                raise MISAError(e.code, f"{e.message} — không tìm được tham số ứng với cột {m.group(1)}")
            dropped.add(victim)
            payload.pop(victim)
            frappe.logger().info(f"misa: gỡ tham số {victim} (MISA báo thiếu cột {m.group(1)})")
    raise MISAError("too_many_drops", "Gỡ quá nhiều tham số mà MISA vẫn vỡ SQL")


def _upsert_snapshot(row, source_api="statement"):
    """Ghi 1 hóa đơn MISA vào snapshot theo khóa tự nhiên (ký hiệu, số chuẩn hóa).

    KHÔNG đè `sales_invoice` / `match_status` / `transaction_id` đã có — kết quả
    đối soát và liên kết do người chốt không được job kéo dữ liệu ghi đè.
    Trả về "created" | "updated" | None.
    """
    from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
        norm_inv_no, norm_series,
    )

    series = norm_series(_pick(row, "InvSeries"))
    inv_no = str(_pick(row, "InvNo") or "").strip()
    if not (series and inv_no) or inv_no.startswith("<"):
        return None

    values = {
        "inv_series": series,
        "inv_no": inv_no,
        "inv_no_norm": norm_inv_no(inv_no),
        "inv_date": misa_date(_pick(row, "InvDate")),
        "ref_id": _pick(row, "RefID") or "",
        "invoice_code": _pick(row, "InvoiceCode") or "",
        "buyer_tax_code": str(_pick(row, "AccountObjectTaxCode") or "").replace(" ", ""),
        "buyer_name": _pick(row, "AccountObjectName") or "",
        "amount_before_vat": flt(_pick(row, "TotalAmountWithoutVAT")),
        "vat_amount": flt(_pick(row, "TotalVATAmount")),
        "total_amount": flt(_pick(row, "TotalAmount")),
        "publish_status": str(_pick(row, "PublishStatus") or ""),
        "einvoice_status": str(_pick(row, "EInvoiceStatus") or ""),
        "send_tax_status": str(_pick(row, "SendToTaxStatus") or ""),
        "send_invoice_status": str(_pick(row, "SendInvoiceStatus") or ""),
        "invoice_type": str(_pick(row, "InvoiceType") or ""),
        "currency_code": _pick(row, "CurrencyCode") or "VND",
        "organization_unit_id": _pick(row, "OrganizationUnitID") or "",
        "edit_version": int(flt(_pick(row, "EditVersion"))),
        "source_api": source_api,
        "last_synced_at": now_datetime(),
    }

    existing = frappe.db.get_value(
        "MISA Invoice Snapshot",
        {"inv_series": series, "inv_no_norm": values["inv_no_norm"]},
        ["name", "transaction_id", "amount_before_vat", "vat_amount", "total_amount", "ref_id"],
        as_dict=True,
    )
    txn = _pick(row, "TransactionID")

    if existing:
        if txn and not existing.transaction_id:
            values["transaction_id"] = txn
        # Endpoint danh sách trả tách thuế = 0 (§H.2). Ghi đè 0 lên số đã nạp từ
        # bảng kê là xóa dữ liệu và đẻ ra "Lệch tiền" giả. Chỉ ghi khi có giá trị.
        for f in ("amount_before_vat", "vat_amount", "total_amount"):
            if not values.get(f) and flt(existing.get(f)):
                values.pop(f, None)
        if not values.get("ref_id") and existing.get("ref_id"):
            values.pop("ref_id", None)
        frappe.db.set_value("MISA Invoice Snapshot", existing.name, values, update_modified=False)
        return "updated"

    values["transaction_id"] = txn or ""
    values["origin"] = "Chưa xác định"
    values["match_status"] = "Chưa xác định"
    doc = frappe.get_doc(dict(doctype="MISA Invoice Snapshot", **values))
    doc.flags.ignore_permissions = True
    doc.insert()
    return "created"


@frappe.whitelist()
def pull_invoices(from_date=None, to_date=None, trigger_type="Manual"):
    """Kéo danh sách hóa đơn MISA trong khoảng ngày về snapshot.

    KHÔNG ghi gì vào Sales Invoice — cô lập blast radius (ràng buộc 13.7).
    Phân trang dừng khi mảng rỗng, KHÔNG dựa recordsTotal (§H).
    """
    from ketoan.api._guard import guard_manager

    guard_manager()
    return _pull_invoices(from_date, to_date, trigger_type)


def _pull_invoices(from_date=None, to_date=None, trigger_type="Manual"):
    settings = get_settings()
    to_date = to_date or nowdate()
    from_date = from_date or frappe.utils.add_months(to_date, -1)

    run = frappe.get_doc({
        "doctype": "MISA Sync Run", "job_type": "pull_statement",
        "trigger_type": trigger_type, "from_date": from_date, "to_date": to_date,
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    stat = {"fetched": 0, "created": 0, "updated": 0}
    errors = []
    start = 0
    reported = 0   # tổng số MISA tự khai
    dropped = set()  # tham số đã gỡ vì MISA vỡ SQL

    for page in range(MAX_PAGES):
        payload = dict(PAGING_BASE)
        payload.update({
            "draw": str(page + 1),
            # KHÔNG dấu nháy kép. Lưới web gửi kèm nháy vì tầng của nó tự bóc;
            # bề mặt /api/v2 model-bind thẳng vào DateTime nên chuỗi có nháy parse
            # HỎNG, rơi về khoảng rỗng và trả 0 dòng mà KHÔNG hề báo lỗi. Đây đúng
            # là thủ phạm của cả chuỗi "0 bản ghi" trước đó (§P).
            "fromDate": f"{from_date}T00:00:00.000Z",
            "toDate": f"{to_date}T23:59:59.000Z",
            "columns": PAGING_COLUMNS,
            "start": str(start),
            "length": str(PAGE_SIZE),
        })
        try:
            rows, meta = _paging_call(settings, payload, dropped)
            # MISA tự khai tổng số (§H). Giữ lại để đối chiếu: kéo thiếu mà
            # không biết còn nguy hiểm hơn kéo được 0.
            for key in ("recordsFiltered", "recordsTotal"):
                n = _pick(meta, key)
                if n:
                    reported = max(reported, int(flt(n)))
        except MISAError as e:
            errors.append(f"trang {page + 1}: [{e.code}] {e.message}")
            break
        except Exception as e:
            errors.append(f"trang {page + 1}: {type(e).__name__}")
            break

        if not rows:
            break  # hết dữ liệu — KHÔNG dựa recordsTotal

        for row in rows:
            try:
                res = _upsert_snapshot(row)
                if res:
                    stat["fetched"] += 1
                    stat[res] += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), "misa_sync._upsert_snapshot")
                errors.append(f"hóa đơn {_pick(row, 'InvNo')}: lỗi ghi snapshot")
        frappe.db.commit()

        # Tiến theo SỐ DÒNG THẬT NHẬN ĐƯỢC, không theo length yêu cầu: server trả
        # ít hơn length là chuyện thường, cộng cứng PAGE_SIZE sẽ nhảy cóc bỏ sót.
        # Và chỉ dừng khi trang trả 0 dòng (đã xử ở trên), không suy đoán từ số ít.
        start += len(rows)
        time.sleep(PAGE_SLEEP)

    if not stat["fetched"] and not errors:
        errors.append(
            "MISA trả về 0 bản ghi. Nhiều khả năng endpoint danh sách trên bề mặt API cần thêm "
            "tham số (§M.6) — dùng lưới trên app3.meinvoice.vn để lấy request thật rồi bổ sung."
        )

    # Đối chiếu số lượng: MISA khai bao nhiêu, ta ghi được bao nhiêu.
    # KHÔNG được im lặng khi thiếu — trang sẽ báo "không có hóa đơn ngoài sổ"
    # trong khi thực tế chưa kéo hết, tức là sai theo hướng nguy hiểm nhất.
    if stat["fetched"] and not reported:
        errors.append(
            "Không đọc được tổng số MISA khai (recordsTotal) nên KHÔNG đối chiếu được đã kéo "
            "đủ chưa. Coi kết quả là chưa đầy đủ cho tới khi kiểm tay."
        )
    if reported and stat["fetched"] < reported:
        errors.append(
            f"KÉO THIẾU: MISA khai {reported} hóa đơn trong khoảng {from_date} → {to_date} "
            f"nhưng chỉ ghi được {stat['fetched']}. Kết quả đối soát CHƯA ĐỦ TIN CẬY — "
            "đừng kết luận 'không có hóa đơn ngoài sổ' cho tới khi khớp số."
        )

    if dropped:
        errors.append("Đã gỡ tham số MISA không nhận: " + ", ".join(sorted(dropped)))

    for k, v in stat.items():
        setattr(run, k, v)
    if errors:
        run.error_log = "\n".join(errors[-200:])
    run.status = "Lỗi" if (errors and not stat["fetched"]) else ("Thành công một phần" if errors else "Thành công")
    run.finished_at = now_datetime()
    run.save(ignore_permissions=True)
    frappe.db.commit()
    return run.name
