"""misa_replace — gán SỐ HÓA ĐƠN THAY THẾ lên chứng từ ĐÃ GHI SỔ.

════════════════════════════════════════════════════════════════════════════
NGHIỆP VỤ
════════════════════════════════════════════════════════════════════════════

Hàng đi, hóa đơn đã phát hành và đã ký. Đến kho siêu thị mới phát hiện hàng bẹp
méo, siêu thị không nhận đủ. Hóa đơn đã ký thì không sửa được, nên MISA phát
hành HÓA ĐƠN THAY THẾ mang SỐ MỚI; số cũ chết. Bên ERPNext chứng từ bán vẫn là
chứng từ cũ — thường kèm một hóa đơn TRẢ VỀ cho phần hàng bị từ chối.

Kết quả: MỘT hóa đơn MISA (bản thay thế) ứng với chứng từ ERPNext cũ, nhưng
`custom_misa_inv_no` trên chứng từ đó vẫn đang giữ SỐ ĐÃ CHẾT.

════════════════════════════════════════════════════════════════════════════
VÌ SAO PHẢI SỬA, KHÔNG ĐỂ VẬY ĐƯỢC
════════════════════════════════════════════════════════════════════════════

Mọi thứ đối chiếu từ bên ngoài đều gọi theo SỐ MỚI:

  · bảng kê thanh toán siêu thị trả tiền theo số thay thế (đo trên file Central
    Retail: 16 dòng trả theo số thay thế / 1 dòng theo số gốc);
  · file công nợ đầu kỳ ghi số thay thế ở cột "HĐ thay thế" (59 dòng còn nợ,
    464.169.744đ trên bộ file mẫu);
  · tra cứu thuế, đối chiếu với siêu thị, biên bản — đều số mới.

Chứng từ giữ số chết thì không đồng tiền nào về khớp được với nó. Nó nằm lại rổ
"chưa thanh toán" vĩnh viễn, còn khoản tiền thật thì thành tiền không rõ nguồn.

════════════════════════════════════════════════════════════════════════════
BA CHỐT CHẶN, VÌ ĐÂY LÀ ĐƯỜNG GHI LÊN CHỨNG TỪ ĐÃ GHI SỔ
════════════════════════════════════════════════════════════════════════════

1. **XEM TRƯỚC BẮT BUỘC.** `apply` đòi `expected_hash` dựng từ `preview`. Ghi
   sai số hóa đơn là sai báo cáo thuế, và không có nút hoàn tác.

2. **KHÔNG hai chứng từ cùng mang một số.** Số hóa đơn là khóa mà tiền về đi
   theo; hai chứng từ cùng số là một lần trả tiền tất toán hai chứng từ.

3. **SỐ CŨ KHÔNG BAO GIỜ BỊ XÓA.** Nó chuyển sang `custom_misa_org_inv` (và
   ref_id cũ sang `custom_misa_org_ref_id`) cùng một dòng nhật ký trong
   `custom_misa_note`. Mất dấu số cũ là mất khả năng giải trình với cơ quan
   thuế về chính hóa đơn đã hủy đó.

════════════════════════════════════════════════════════════════════════════
HAI CHẾ ĐỘ — KHÁC NHAU Ở CHỖ CÓ BIẾT RefID CỦA BẢN THAY THẾ KHÔNG
════════════════════════════════════════════════════════════════════════════

A. **Có bản thay thế trong bảng kê MISA** (`MISA Invoice Snapshot`). Lấy được
   RefID thật của nó → chuyển luôn `custom_misa_ref_id` sang bản mới. Từ đó
   `poll_pending` hỏi ĐÚNG hóa đơn đang sống: số, ngày, mã CQT, cả việc bản mới
   có bị hủy tiếp hay không đều tự về. Cờ khóa để 0.

B. **Chưa kéo bảng kê / không tìm thấy.** Chỉ gán được số, ref_id vẫn trỏ hóa
   đơn chết. Nếu để yên, vòng quét 2 của `poll_pending` sẽ hỏi theo ref_id đó,
   MISA trả số cũ, và số vừa gán bị ghi đè ngược — lặng lẽ, mỗi lần đồng bộ.
   Nên chế độ B BẮT BUỘC bật `custom_misa_no_locked` (patch v0_0_17), đổi lại
   chứng từ không còn được theo dõi hủy/thay thế tự động.

   B là lựa chọn cuối. `preview` luôn chỉ đường về A: kéo bảng kê MISA trước.

Ràng buộc chung của app: KHÔNG `save()` chứng từ đã ghi sổ — chỉ
`db_set(update_modified=False)`. Hệ thống KHÔNG tự hủy/sửa chứng từ theo dữ
liệu MISA; ở đây con người gõ số và bấm nút, máy chỉ kiểm rồi ghi.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cstr, flt, now_datetime

from ketoan.api._guard import guard_manager
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)

# Field trên Sales Invoice mà màn hình này đọc. Site chưa migrate thiếu field
# nào thì `_si` bỏ field đó ra chứ không gãy.
SI_READ = (
    "name", "docstatus", "company", "customer", "customer_name", "posting_date",
    "is_return", "return_against", "net_total", "total_taxes_and_charges", "grand_total",
    "custom_misa_inv_no", "custom_misa_inv_series", "custom_misa_inv_date",
    "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
    "custom_misa_ref_id", "custom_misa_status", "custom_misa_relation",
    "custom_misa_org_inv", "custom_misa_org_ref_id", "custom_misa_no_locked",
    "custom_misa_note", "vn_einvoice_number", "vn_einvoice_date",
)

LEGACY_NO = "vn_einvoice_number"
LEGACY_DATE = "vn_einvoice_date"

RELATION_REPLACEMENT = "Hóa đơn thay thế"


def _has(field):
    return bool(frappe.get_meta("Sales Invoice").has_field(field))


def _si(name):
    fields = [f for f in SI_READ if f == "name" or _has(f)]
    return frappe.db.get_value("Sales Invoice", name, fields, as_dict=True)


# ═══════════════════════════════════════════════════════════════════════════
# Tìm bản thay thế trong bảng kê MISA
# ═══════════════════════════════════════════════════════════════════════════

SNAP_READ = ("name", "inv_series", "inv_no", "inv_no_norm", "inv_date", "ref_id",
             "transaction_id", "invoice_code", "einvoice_status", "is_deleted",
             "amount_before_vat", "vat_amount", "total_amount", "sales_invoice")


def find_snapshots(inv_no, inv_series=None):
    """Bản ghi bảng kê MISA mang số này. Lọc thêm theo ký hiệu nếu có khai.

    So bằng `inv_no_norm` (đã bỏ số 0 đứng đầu) — MISA in '00006537' còn người
    gõ '6537'. So thô là không bao giờ tìm thấy.
    """
    if not frappe.db.table_exists("MISA Invoice Snapshot"):
        return []
    no = norm_inv_no(inv_no)
    if not no:
        return []
    rows = frappe.get_all("MISA Invoice Snapshot", filters={"inv_no_norm": no},
                          fields=list(SNAP_READ), limit=50) or []
    ser = norm_series(inv_series)
    if ser:
        rows = [r for r in rows if norm_series(r.inv_series) == ser]
    return rows


def _stale_snapshots(si_name, keep=None):
    """Bản ghi bảng kê đang nối với chứng từ này, trừ bản đang định nối."""
    if not frappe.db.table_exists("MISA Invoice Snapshot"):
        return []
    rows = frappe.get_all(
        "MISA Invoice Snapshot", filters={"sales_invoice": si_name},
        fields=["name", "inv_series", "inv_no", "einvoice_status"], limit=20) or []
    return [r for r in rows if r.name != keep]


def _relation_label(snap):
    from ketoan.api.misa_sync import EINVOICE_RELATION

    return EINVOICE_RELATION.get(cstr(snap.get("einvoice_status")).strip()) or ""


# ═══════════════════════════════════════════════════════════════════════════
# Kế hoạch
# ═══════════════════════════════════════════════════════════════════════════

def _collisions(si, no, ser):
    """Chứng từ KHÁC đang mang cùng số hóa đơn, trong cùng công ty.

    Tách hai mức có chủ ý:
      · cùng số + cùng ký hiệu (hoặc cả hai đều trống)  → CHẶN. Đúng một hóa đơn.
      · cùng số, khác ký hiệu                            → CẢNH BÁO. MISA đánh số
        lại từ đầu mỗi năm/mỗi ký hiệu nên trùng số khác ký hiệu là hợp lệ; nhưng
        đối soát thanh toán khớp chủ yếu theo SỐ, nên vẫn phải bày ra.
    """
    if not _has("custom_misa_inv_no"):
        return [], []
    rows = frappe.db.sql("""
        SELECT si.name, si.customer_name, si.posting_date, si.grand_total,
               si.custom_misa_inv_series AS inv_series, si.custom_misa_inv_no AS inv_no,
               si.docstatus
        FROM `tabSales Invoice` si
        WHERE si.docstatus < 2
          AND si.company = %(company)s
          AND si.name != %(me)s
          AND TRIM(LEADING '0' FROM IFNULL(si.custom_misa_inv_no, '')) = %(no)s
        ORDER BY si.posting_date DESC
        LIMIT 20
    """, {"company": si.get("company"), "me": si.get("name"), "no": no}, as_dict=True)

    hard, soft = [], []
    for r in rows:
        rs = norm_series(r.inv_series)
        (hard if rs == ser else soft).append(r)
    return hard, soft


def _plan(sales_invoice, inv_no, inv_series=None):
    """Dựng kế hoạch đổi số. KHÔNG ghi gì.

    Trả dict: `si`, `blocks` (chặn hẳn), `warnings` (người tự quyết), `changes`
    (field → [cũ, mới]), `mode`, `snapshot`, `money`.
    """
    blocks, warnings = [], []

    si = _si(sales_invoice) if sales_invoice else None
    if not si:
        return {"ok": False, "blocks": [_("Không tìm thấy hóa đơn {0}").format(sales_invoice or "")],
                "warnings": [], "changes": {}, "mode": None, "si": None}

    if si.docstatus != 1:
        blocks.append(_(
            "Hóa đơn {0} chưa ghi sổ (hoặc đã hủy). Màn hình này chỉ sửa số trên chứng "
            "từ ĐÃ ghi sổ — chứng từ nháp thì sửa thẳng trên form."
        ).format(si.name))

    no = norm_inv_no(inv_no)
    ser = norm_series(inv_series)
    if not no:
        blocks.append(_("Chưa nhập số hóa đơn thay thế, hoặc số không đọc được"))

    old_no = norm_inv_no(si.get("custom_misa_inv_no"))
    old_ser = norm_series(si.get("custom_misa_inv_series"))

    snaps = find_snapshots(no, ser) if no else []
    snap = None
    if len(snaps) > 1:
        blocks.append(_(
            "Bảng kê MISA có {0} hóa đơn mang số {1} (ký hiệu: {2}). Nhập thêm ký hiệu "
            "để chỉ đúng một bản — máy không chọn hộ."
        ).format(len(snaps), no, ", ".join(sorted({cstr(s.inv_series) or "?" for s in snaps}))))
    elif snaps:
        snap = snaps[0]
        if snap.get("is_deleted"):
            blocks.append(_(
                "Hóa đơn {0} trên MISA đang ở trạng thái ĐÃ XÓA BỎ. Gán số đã xóa lên "
                "chứng từ đang ghi sổ là khai một hóa đơn không còn hiệu lực."
            ).format(no))
        taken = cstr(snap.get("sales_invoice"))
        if taken and taken != si.name:
            blocks.append(_(
                "Hóa đơn MISA số {0} đã được nối với chứng từ {1}. Gỡ liên kết đó trước "
                "(màn hình Hóa đơn VAT) — một hóa đơn MISA chỉ thuộc về một chứng từ."
            ).format(no, taken))
        rel = _relation_label(snap)
        if rel in ("Bị thay thế", "Bị điều chỉnh"):
            blocks.append(_(
                "Hóa đơn {0} chính nó cũng đã {1} trên MISA — nó không phải bản đang sống. "
                "Tra lại số của bản mới nhất."
            ).format(no, rel.lower()))
        elif rel and rel != RELATION_REPLACEMENT:
            warnings.append(_(
                "Bản MISA số {0} đang mang quan hệ '{1}', không phải '{2}'. Kiểm lại đây có "
                "đúng là hóa đơn thay thế không."
            ).format(no, rel, RELATION_REPLACEMENT))

    # Ký hiệu cuối cùng: người gõ > bảng kê MISA > giữ nguyên ký hiệu cũ. Phải
    # chốt TRƯỚC khi dò trùng — dò trùng phân biệt "cùng số cùng ký hiệu" (chặn)
    # với "cùng số khác ký hiệu" (cảnh báo), nên sai ký hiệu là sai luôn mức chặn.
    new_ser = ser or (norm_series(snap.get("inv_series")) if snap else "") or old_ser

    if no:
        hard, soft = _collisions(si, no, new_ser)
        for r in hard:
            blocks.append(_(
                "Chứng từ {0} ({1}) ĐANG mang số {2} {3}. Hai chứng từ cùng một số hóa đơn "
                "thì một lần siêu thị trả tiền sẽ tất toán cả hai."
            ).format(r.name, r.customer_name or "", cstr(r.inv_series), cstr(r.inv_no)))
        for r in soft:
            warnings.append(_(
                "Chứng từ {0} cũng mang số {1} nhưng khác ký hiệu ({2}). Đối soát thanh toán "
                "khớp theo SỐ nên vẫn có thể lẫn — kiểm lại."
            ).format(r.name, cstr(r.inv_no), cstr(r.inv_series) or "trống"))

    if not old_no:
        warnings.append(_(
            "Chứng từ này chưa có số hóa đơn MISA nào. Đây không phải việc THAY THẾ mà là "
            "gán số lần đầu — nếu là hóa đơn cũ nhập tay thì dùng 'Chuyển số HĐ cũ' đúng hơn."
        ))

    # Bản ghi bảng kê đang nối với chứng từ này mà KHÔNG phải bản thay thế —
    # đó chính là hóa đơn đã chết. Phải gỡ ra, và phải gỡ TRƯỚC khi nối bản mới:
    # `relink_snapshot` từ chối nối khi chứng từ đã có bản MISA khác, nên bỏ qua
    # bước này là bản thay thế mãi nằm ở rổ "Chỉ có trên MISA" — màn hình đối
    # soát vẫn báo hóa đơn ngoài sổ ngay sau khi người ta vừa xử lý xong.
    stale = _stale_snapshots(si.name, snap["name"] if snap else None)
    if stale:
        warnings.append(_(
            "Bản MISA cũ ({0}) đang nối với chứng từ này sẽ được GỠ ra và đánh dấu "
            "'Đã thay thế'. Bản ghi vẫn còn nguyên để tra cứu, chỉ không còn là hóa "
            "đơn của chứng từ này nữa."
        ).format(", ".join(f"{cstr(s.inv_series)} {cstr(s.inv_no)}" for s in stale)))

    # ── tiền ──────────────────────────────────────────────────────────────
    money = _money(si, snap)
    if money.get("diff") is not None and abs(money["diff"]) > 1:
        warnings.append(_(
            "Tiền chưa khớp: MISA {0:,.0f}đ · ERPNext {1:,.0f}đ (hóa đơn {2:,.0f} − trả về "
            "{3:,.0f}) — lệch {4:,.0f}đ. Số tiền công nợ vẫn lấy theo ERPNext; gán số không "
            "làm tiền đúng lên. Thiếu hóa đơn trả về thì lập trước rồi quay lại."
        ).format(money["misa"], money["erp_net"], money["erp_gross"],
                 money["returned"], money["diff"]))

    # ── chế độ + thay đổi ────────────────────────────────────────────────
    ref_new = cstr(snap.get("ref_id")).strip() if snap else ""
    old_ref = cstr(si.get("custom_misa_ref_id")).strip()

    # Hai câu hỏi KHÁC NHAU, đừng gộp:
    #   `repoint`      — có phải GHI lại ô ref_id không (đã đúng sẵn thì không).
    #   `has_live_ref` — sau thao tác, ref_id trên chứng từ có trỏ bản ĐANG SỐNG không.
    # Gộp lại thì lần chạy thứ hai của cùng một việc (ref_id đã đúng từ lần
    # trước) bị xếp nhầm sang chế độ gán tay và tự khóa đồng bộ của chính chứng
    # từ vừa làm đúng.
    repoint = bool(ref_new and ref_new != old_ref)
    has_live_ref = bool(ref_new)
    mode = "theo_bang_ke" if has_live_ref else "gan_tay"

    if not snap:
        warnings.append(_(
            "Chưa tìm thấy hóa đơn số {0} trong bảng kê MISA. Vẫn gán được, nhưng phải KHÓA "
            "đồng bộ cho chứng từ này (không thì lần đồng bộ sau ghi đè số cũ trở lại) — và "
            "khóa rồi thì máy không còn tự phát hiện hóa đơn bị hủy nữa. Nên kéo bảng kê MISA "
            "trước: Hóa đơn VAT → Đồng bộ MISA, rồi làm lại ở đây."
        ).format(no or "?"))
    elif not ref_new:
        warnings.append(_(
            "Bản MISA số {0} có trong bảng kê nhưng không kèm RefID, nên vẫn phải khóa đồng bộ."
        ).format(no))

    changes = {}

    def _set(field, new):
        if not _has(field):
            return
        old = si.get(field)
        if cstr(old or "") != cstr(new or ""):
            changes[field] = [old, new]

    _set("custom_misa_inv_no", no)
    _set("custom_misa_inv_series", new_ser)
    if snap and snap.get("inv_date"):
        _set("custom_misa_inv_date", cstr(snap.get("inv_date")))
    if snap and cstr(snap.get("transaction_id")).strip():
        _set("custom_misa_transaction_id", cstr(snap.get("transaction_id")).strip())
    if snap and cstr(snap.get("invoice_code")).strip():
        _set("custom_misa_invoice_code", cstr(snap.get("invoice_code")).strip())
    _set("custom_misa_relation", RELATION_REPLACEMENT)
    # `old_no != no` là chốt chặn, không phải tối ưu. Chạy lại đúng việc này lần
    # thứ hai (số đã đúng từ lần trước) thì `old_no` CHÍNH LÀ số mới — ghi nó vào
    # ô "Hóa đơn gốc" là xóa mất dấu vết của số đã chết, đúng thứ duy nhất còn
    # dùng để giải trình với cơ quan thuế về hóa đơn đã hủy.
    if old_no and old_no != no:
        _set("custom_misa_org_inv", " ".join(x for x in (old_ser, old_no) if x))
    if repoint:
        _set("custom_misa_ref_id", ref_new)
        if old_ref:
            _set("custom_misa_org_ref_id", old_ref)
    _set("custom_misa_no_locked", 0 if has_live_ref else 1)
    # Trạng thái nằm TRONG kế hoạch chứ không tra thêm ở `apply`: mọi ô sắp bị
    # ghi đều phải hiện ra bảng "sẽ ghi" và nằm trong vân tay.
    _set("custom_misa_status", "Đã phát hành")
    # `vn_einvoice_number` là mặt hiển thị mà 6 màn hình của app đang đọc. Để
    # nguyên số chết ở đó thì màn hình vẫn hiện số cũ, và `_legacy_values` của
    # misa_sync sẽ báo "Số hóa đơn lệch" mỗi lần đồng bộ, mãi mãi.
    _set(LEGACY_NO, no)
    if snap and snap.get("inv_date"):
        _set(LEGACY_DATE, cstr(snap.get("inv_date")))

    if not changes and not blocks:
        blocks.append(_(
            "Chứng từ {0} đã đang mang đúng số {1} và không có gì để cập nhật thêm."
        ).format(si.name, no))

    return {
        "ok": not blocks,
        "si": si,
        "old": {"inv_no": old_no, "inv_series": old_ser, "ref_id": old_ref},
        "new": {"inv_no": no, "inv_series": new_ser, "ref_id": ref_new},
        "snapshot": snap,
        "snapshot_relation": _relation_label(snap) if snap else "",
        "stale": stale,
        "mode": mode,
        "locked": 0 if has_live_ref else 1,
        "money": money,
        "changes": changes,
        "blocks": blocks,
        "warnings": warnings,
    }


def _money(si, snap):
    """Ba con số đem đối chiếu, và phép trừ được bày ra chứ không giấu."""
    from ketoan.api.misa_sync import returns_against

    ret = returns_against(si.get("name")) if si else {"n": 0, "grand_total": 0}
    gross = abs(flt(si.get("grand_total"))) if si else 0.0
    returned = flt(ret.get("grand_total"))
    net = gross - returned
    misa = flt(snap.get("total_amount")) if snap else None
    return {
        "erp_gross": gross,
        "returned": returned,
        "n_returns": int(ret.get("n") or 0),
        "erp_net": net,
        "misa": misa,
        "diff": (abs(misa) - net) if misa is not None else None,
    }


def _plan_hash(plan):
    """Vân tay của ĐÚNG kế hoạch người vừa xem.

    `apply` dựng lại kế hoạch từ đầu. Giữa lúc xem và lúc bấm, đồng bộ MISA có
    thể vừa chạy và đổi số/ref_id trên chính chứng từ này — so vân tay thì lệch
    một field cũng dừng lại, không ghi gì.
    """
    h = hashlib.sha1()
    h.update(f"{plan['si']['name']}|{plan['mode']}|{plan['locked']}\n".encode())
    for s in sorted(cstr(x.get("name")) for x in (plan.get("stale") or [])):
        h.update(f"stale|{s}\n".encode())
    for k in sorted(plan["changes"]):
        old, new = plan["changes"][k]
        h.update(f"{k}|{cstr(old)}|{cstr(new)}\n".encode())
    return h.hexdigest()


def _out(plan):
    """Bỏ object nặng ra khỏi phần trả về cho giao diện."""
    si = plan.get("si") or {}
    snap = plan.get("snapshot") or None
    return {
        "ok": plan["ok"],
        "sales_invoice": si.get("name"),
        "customer_name": si.get("customer_name"),
        "posting_date": cstr(si.get("posting_date") or ""),
        "old": plan.get("old") or {},
        "new": plan.get("new") or {},
        "mode": plan.get("mode"),
        "locked": plan.get("locked"),
        "money": plan.get("money") or {},
        "snapshot": ({
            "name": snap.get("name"),
            "inv_series": snap.get("inv_series"),
            "inv_no": snap.get("inv_no"),
            "inv_date": cstr(snap.get("inv_date") or ""),
            "total_amount": flt(snap.get("total_amount")),
            "relation": plan.get("snapshot_relation"),
        } if snap else None),
        "stale": [{"name": s.get("name"), "inv_series": cstr(s.get("inv_series")),
                   "inv_no": cstr(s.get("inv_no"))} for s in (plan.get("stale") or [])],
        "changes": [{"field": k, "old": cstr(v[0] or ""), "new": cstr(v[1] or "")}
                    for k, v in sorted((plan.get("changes") or {}).items())],
        "blocks": plan.get("blocks") or [],
        "warnings": plan.get("warnings") or [],
        "plan_hash": _plan_hash(plan) if plan.get("si") else "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def preview(sales_invoice, inv_no, inv_series=None):
    """Xem trước việc đổi số hóa đơn sang bản thay thế. KHÔNG ghi gì."""
    guard_manager()
    if not _has("custom_misa_inv_no"):
        frappe.throw(_("Site chưa có field số hóa đơn MISA — chạy `bench migrate` trước"))
    return _out(_plan(sales_invoice, inv_no, inv_series))


@frappe.whitelist()
def search(txt, limit=20):
    """Tìm chứng từ đã ghi sổ theo tên / số hóa đơn MISA / tên khách."""
    guard_manager()
    kw = norm_text(txt)
    if not kw or len(kw) < 2:
        return []
    has_no = _has("custom_misa_inv_no")
    no_col = "si.custom_misa_inv_no" if has_no else "''"
    return frappe.db.sql(f"""
        SELECT si.name, si.customer_name, si.posting_date, si.grand_total,
               {no_col} AS inv_no
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND (si.name LIKE %(like)s
               OR si.customer_name LIKE %(like)s
               OR TRIM(LEADING '0' FROM IFNULL({no_col}, '')) = %(no)s)
        ORDER BY si.posting_date DESC
        LIMIT {int(limit or 20)}
    """, {"like": f"%{kw}%", "no": norm_inv_no(kw)}, as_dict=True)


@frappe.whitelist()
def apply(sales_invoice, inv_no, inv_series=None, expected_hash=None, reason=None):
    """Ghi thật. Đòi `expected_hash` lấy từ `preview` — xem trước là bắt buộc."""
    guard_manager()
    if not _has("custom_misa_inv_no"):
        frappe.throw(_("Site chưa có field số hóa đơn MISA — chạy `bench migrate` trước"))

    plan = _plan(sales_invoice, inv_no, inv_series)
    if not plan["ok"]:
        frappe.throw(_("Không đổi được số: {0}").format(" · ".join(plan["blocks"])))
    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới đổi được"))
    if _plan_hash(plan) != expected_hash:
        frappe.throw(_(
            "Chứng từ đã đổi kể từ lúc xem trước (có thể đồng bộ MISA vừa chạy). Xem lại "
            "rồi làm — không ghi gì cả."
        ))

    si = plan["si"]
    values = {k: v[1] for k, v in plan["changes"].items()}

    # Link tra cứu dựng lại theo SỐ MỚI. Bỏ qua thì nút tra cứu trên form vẫn mở
    # ra hóa đơn đã chết.
    try:
        from ketoan.api.misa_client import get_settings
        from ketoan.api.misa_desk import invoice_links

        if _has("custom_misa_link"):
            link = invoice_links({
                "custom_misa_ref_id": plan["new"]["ref_id"] or plan["old"]["ref_id"],
                "custom_misa_transaction_id": values.get("custom_misa_transaction_id"),
                "custom_misa_inv_no": plan["new"]["inv_no"],
                "custom_misa_inv_series": plan["new"]["inv_series"],
                "custom_misa_invoice_code": values.get("custom_misa_invoice_code"),
            }, get_settings()).get("primary")
            if link:
                values["custom_misa_link"] = link
    except Exception:
        frappe.log_error(frappe.get_traceback(), "misa_replace.apply link")

    if _has("custom_misa_note"):
        values["custom_misa_note"] = _note(si, plan, reason)

    # Chứng từ đã ghi sổ: chỉ db_set, KHÔNG save(). Xem docstring module.
    frappe.db.set_value("Sales Invoice", si.name, values, update_modified=False)

    link = _link_snapshot(plan, reason)
    frappe.db.commit()

    msg = _("Đã đổi sang số {0}. Số cũ {1} lưu ở 'Hóa đơn gốc'.").format(
        plan["new"]["inv_no"], plan["old"]["inv_no"] or "(trống)")
    if link.get("error"):
        # Số trên chứng từ đã ghi xong; chỉ phần nối bảng kê hỏng. Nói thẳng
        # việc còn lại, không để người dùng tưởng đã xong hết.
        msg += " " + _(
            "NHƯNG chưa chuyển được liên kết bảng kê MISA ({0}) — vào Hóa đơn VAT nối tay."
        ).format(link["error"])
    return {
        "sales_invoice": si.name,
        "inv_no": plan["new"]["inv_no"],
        "inv_series": plan["new"]["inv_series"],
        "mode": plan["mode"],
        "locked": plan["locked"],
        "snapshot": link,
        "fields": sorted(values.keys()),
        "message": msg,
    }


def _note(si, plan, reason):
    """Nối thêm MỘT dòng nhật ký, không đè ô ghi chú.

    Ô này đang mang cảnh báo đối soát của misa_sync/misa_push và cả chữ kế toán
    tự gõ. Đè lên là xóa mất cảnh báo thật.
    """
    old = cstr(si.get("custom_misa_note") or "").strip()
    line = _("[{0}] {1} đổi số hóa đơn {2} → {3} ({4}){5}").format(
        cstr(now_datetime())[:16],
        frappe.session.user,
        plan["old"]["inv_no"] or "(trống)",
        plan["new"]["inv_no"],
        _("theo bảng kê MISA") if plan["mode"] == "theo_bang_ke" else _("gán tay, khóa đồng bộ"),
        (" · " + norm_text(reason)) if norm_text(reason) else "",
    )
    return (old + "\n" + line) if old else line


def _link_snapshot(plan, reason):
    """Chuyển liên kết bảng kê MISA: gỡ bản CHẾT ra, nối bản THAY THẾ vào.

    Thứ tự bắt buộc là gỡ trước nối sau. `relink_snapshot` từ chối nối khi chứng
    từ đã có bản MISA khác, nên nối trước là hỏng cả hai việc: bản cũ vẫn nối,
    bản mới vẫn nằm ở rổ "Chỉ có trên MISA" — màn hình đối soát báo hóa đơn ngoài
    sổ ngay sau khi người ta vừa xử lý xong.

    Không nuốt lỗi: số hóa đơn trên chứng từ đã ghi xong ở `apply`, nên phần này
    hỏng thì phải NÓI ra để người vào màn hình Hóa đơn VAT nối tay, chứ không
    được lặng lẽ bỏ qua.
    """
    out = {"unlinked": [], "linked": None, "error": None}
    si_name = plan["si"].name
    try:
        from ketoan.api.misa_reconcile import relink_snapshot

        for s in plan.get("stale") or []:
            frappe.db.set_value("MISA Invoice Snapshot", s["name"], {
                "sales_invoice": None,
                # `validate` của snapshot tự dọn method/confidence khi hết liên
                # kết, nhưng ở đây ghi thẳng DB nên phải tự dọn.
                "match_method": None,
                "match_confidence": None,
                "match_status": "Đã thay thế",
                "note": _("Bị hóa đơn {0} thay thế — gỡ khỏi {1} ngày {2} bởi {3}").format(
                    plan["new"]["inv_no"], si_name, cstr(now_datetime())[:16], frappe.session.user),
                "last_synced_at": now_datetime(),
            }, update_modified=False)
            out["unlinked"].append(s["name"])

        snap = plan.get("snapshot")
        if snap:
            relink_snapshot(snap["name"], si_name,
                            note=norm_text(reason) or _("Nối theo hóa đơn thay thế"))
            out["linked"] = snap["name"]
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "misa_replace._link_snapshot")
        out["error"] = cstr(e)
    return out


@frappe.whitelist()
def list_locked(limit=200):
    """Chứng từ đang KHÓA đồng bộ — để không ai quên chúng ở đó.

    Khóa là đánh đổi có thật: chứng từ đó không còn được `poll_pending` theo dõi
    hủy/thay thế. Kéo bảng kê MISA về rồi làm lại một lượt là gỡ được khóa.
    """
    guard_manager()
    if not frappe.db.has_column("Sales Invoice", "custom_misa_no_locked"):
        return {"supported": False, "rows": [], "total": 0}
    rows = frappe.db.sql("""
        SELECT si.name, si.customer_name, si.posting_date, si.grand_total,
               si.custom_misa_inv_series AS inv_series,
               si.custom_misa_inv_no AS inv_no,
               si.custom_misa_org_inv AS org_inv
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND IFNULL(si.custom_misa_no_locked, 0) = 1
        ORDER BY si.posting_date DESC
        LIMIT %(limit)s
    """, {"limit": int(limit or 200)}, as_dict=True)
    return {
        "supported": True,
        "rows": rows,
        "total": frappe.db.count("Sales Invoice",
                                 {"docstatus": 1, "custom_misa_no_locked": 1}),
    }
