"""misa_vat — API cho trang "Hóa đơn VAT" trên portal kế toán.

Chỉ ĐỌC và tổng hợp. Mọi thao tác ghi (đồng bộ, khớp, chốt tay) nằm ở
misa_sync / misa_reconcile và có guard riêng.

Bốn rổ hóa đơn:
  · linked    — hóa đơn ERPNext đã có số hóa đơn MISA
  · erp_only  — đã ghi sổ trên ERPNext mà CHƯA có số MISA (nguy cơ chưa phát hành)
  · misa_only — có trên MISA mà không nối được về ERPNext (nguy cơ xuất ngoài sổ)
  · mismatch  — nối được nhưng LỆCH TIỀN

Hai rổ giữa mới là thứ đáng lo về thuế: một bên bán mà chưa xuất hóa đơn, một
bên xuất hóa đơn mà không có trong sổ.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, nowdate

from ketoan.api._guard import guard_sales_any, is_chief

BUCKETS = ("linked", "erp_only", "misa_only", "mismatch")


def _range(from_date, to_date):
    to_date = to_date or nowdate()
    from_date = from_date or add_months(to_date, -1)
    return from_date, to_date


def _company(company=None):
    return company or frappe.defaults.get_user_default("Company")


# ═══════════════════════════════════════════════════════════════════════════
# Tổng quan
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_overview(company=None, from_date=None, to_date=None):
    """Đếm + tổng tiền của 4 rổ, kèm tình trạng đồng bộ gần nhất."""
    guard_sales_any()
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)
    p = {"company": company, "fd": from_date, "td": to_date}

    linked = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, IFNULL(SUM(ABS(grand_total)), 0) AS amt
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
          AND posting_date BETWEEN %(fd)s AND %(td)s
          AND IFNULL(custom_misa_inv_no, '') != ''
    """, p, as_dict=True)[0]

    erp_only = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, IFNULL(SUM(ABS(grand_total)), 0) AS amt
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
          AND posting_date BETWEEN %(fd)s AND %(td)s
          AND IFNULL(custom_misa_inv_no, '') = ''
    """, p, as_dict=True)[0]

    misa_only = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, IFNULL(SUM(ABS(total_amount)), 0) AS amt
        FROM `tabMISA Invoice Snapshot`
        WHERE inv_date BETWEEN %(fd)s AND %(td)s
          AND IFNULL(sales_invoice, '') = ''
          AND IFNULL(is_deleted, 0) = 0
    """, p, as_dict=True)[0]

    mismatch = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, IFNULL(SUM(ABS(total_amount)), 0) AS amt
        FROM `tabMISA Invoice Snapshot`
        WHERE inv_date BETWEEN %(fd)s AND %(td)s AND match_status = 'Lệch tiền'
    """, p, as_dict=True)[0]

    # Hóa đơn ERPNext bị MISA báo lệch mà CHƯA có snapshot nào trỏ tới — phải
    # cộng thêm chứ không lấy max: hai tập này rời nhau, max sẽ đếm thiếu.
    si_mismatch = frappe.db.sql("""
        SELECT COUNT(*) AS cnt FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND si.custom_misa_status = 'Lệch tiền'
          AND NOT EXISTS (
              SELECT 1 FROM `tabMISA Invoice Snapshot` s WHERE s.sales_invoice = si.name
          )
    """, p, as_dict=True)[0]

    last = frappe.get_all(
        "MISA Sync Run",
        fields=["name", "job_type", "status", "finished_at", "fetched", "matched", "mismatched", "error_log"],
        order_by="creation desc", limit=1,
    )

    has_snapshot = frappe.db.count("MISA Invoice Snapshot") > 0

    return {
        "from_date": from_date,
        "to_date": to_date,
        "buckets": {
            "linked": {"count": linked.cnt, "amount": flt(linked.amt)},
            "erp_only": {"count": erp_only.cnt, "amount": flt(erp_only.amt)},
            "misa_only": {"count": misa_only.cnt, "amount": flt(misa_only.amt)},
            "mismatch": {"count": mismatch.cnt + si_mismatch.cnt, "amount": flt(mismatch.amt)},
        },
        "last_sync": last[0] if last else None,
        "has_snapshot": has_snapshot,
        "can_sync": is_chief(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Danh sách từng rổ
# ═══════════════════════════════════════════════════════════════════════════

def _si_rows(company, from_date, to_date, linked: bool, search, limit, offset=0):
    p = {"company": company, "fd": from_date, "td": to_date, "limit": limit, "offset": offset}
    where = "IFNULL(si.custom_misa_inv_no, '') != ''" if linked else "IFNULL(si.custom_misa_inv_no, '') = ''"
    if search:
        p["kw"] = f"%{search}%"
        where += " AND (si.name LIKE %(kw)s OR si.customer_name LIKE %(kw)s OR si.custom_misa_inv_no LIKE %(kw)s)"
    total = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s AND {where}
    """, p)[0][0]
    rows = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, si.customer, si.customer_name,
               si.net_total, si.total_taxes_and_charges, si.grand_total, si.is_return,
               si.custom_misa_inv_series AS inv_series, si.custom_misa_inv_no AS inv_no,
               si.custom_misa_inv_date AS inv_date, si.custom_misa_status AS misa_status,
               si.custom_misa_transaction_id AS transaction_id, si.custom_misa_link AS link,
               si.custom_misa_ref_id AS ref_id, si.custom_misa_pushed_at AS pushed_at,
               si.custom_misa_note AS note
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s AND {where}
        ORDER BY si.posting_date DESC, si.name DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return rows, total


def _snapshot_rows(from_date, to_date, where_extra, search, limit, offset=0):
    p = {"fd": from_date, "td": to_date, "limit": limit, "offset": offset}
    where = where_extra
    if search:
        p["kw"] = f"%{search}%"
        where += " AND (s.inv_no LIKE %(kw)s OR s.buyer_name LIKE %(kw)s OR s.buyer_tax_code LIKE %(kw)s)"
    total = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tabMISA Invoice Snapshot` s
        WHERE s.inv_date BETWEEN %(fd)s AND %(td)s AND {where}
    """, p)[0][0]
    rows = frappe.db.sql(f"""
        SELECT s.name, s.inv_series, s.inv_no, s.inv_date, s.buyer_name, s.buyer_tax_code,
               s.amount_before_vat, s.vat_amount, s.total_amount, s.transaction_id,
               s.invoice_code, s.sales_invoice, s.match_status, s.match_method,
               s.match_confidence, s.origin, s.is_deleted, s.note
        FROM `tabMISA Invoice Snapshot` s
        WHERE s.inv_date BETWEEN %(fd)s AND %(td)s AND {where}
        ORDER BY s.inv_date DESC, s.inv_no DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return rows, total


PAGE_SIZE = 20


@frappe.whitelist()
def get_invoices(bucket, company=None, from_date=None, to_date=None, search=None,
                 page=1, page_size=PAGE_SIZE):
    """Một TRANG hóa đơn của 1 rổ. bucket ∈ linked | erp_only | misa_only | mismatch.

    Phân trang ở tầng SQL chứ không nạp hết rồi cắt ở trình duyệt: một tháng có
    tới hơn nghìn hóa đơn.
    """
    guard_sales_any()
    if bucket not in BUCKETS:
        frappe.throw(_("Rổ không hợp lệ: {0}").format(bucket))
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)
    page = max(1, int(page or 1))
    page_size = min(max(1, int(page_size or PAGE_SIZE)), 200)
    offset = (page - 1) * page_size
    search = (search or "").strip()

    if bucket == "linked":
        source, (rows, total) = "erp", _si_rows(company, from_date, to_date, True, search, page_size, offset)
    elif bucket == "erp_only":
        source, (rows, total) = "erp", _si_rows(company, from_date, to_date, False, search, page_size, offset)
    elif bucket == "misa_only":
        source, (rows, total) = "misa", _snapshot_rows(
            from_date, to_date, "IFNULL(s.sales_invoice, '') = '' AND IFNULL(s.is_deleted, 0) = 0",
            search, page_size, offset)
    else:
        source, (rows, total) = "misa", _snapshot_rows(
            from_date, to_date, "s.match_status = 'Lệch tiền'", search, page_size, offset)

    return {
        "source": source, "rows": rows, "total": total,
        "page": page, "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


@frappe.whitelist()
def search_invoices(txt=None, company=None, limit=20):
    """Tìm Sales Invoice để chốt tay liên kết với 1 hóa đơn MISA."""
    guard_sales_any()
    txt = (txt or "").strip()
    if not txt:
        return []
    return frappe.db.sql("""
        SELECT si.name, si.posting_date, si.customer_name, si.grand_total,
               si.custom_misa_inv_no AS inv_no
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND (si.name LIKE %(kw)s OR si.customer_name LIKE %(kw)s)
        ORDER BY si.posting_date DESC
        LIMIT %(limit)s
    """, {"company": _company(company), "kw": f"%{txt}%", "limit": min(int(limit or 20), 50)}, as_dict=True)


# ═══════════════════════════════════════════════════════════════════════════
# Đồng bộ từ portal — kéo MISA về rồi khớp, trong một lần bấm
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def sync_now(company=None, from_date=None, to_date=None):
    """Nút "Đồng bộ MISA": đưa việc kéo + hỏi số + khớp sang hàng đợi nền.

    Chỉ kế toán trưởng.

    KHÔNG chạy trong request: một tháng có tới 1260 hóa đơn (§P) và bước hỏi số
    gọi MISA MỘT LẦN cho mỗi hóa đơn — chạy đồng bộ là chắc chắn timeout gateway,
    và tệ hơn là timeout GIỮA CHỪNG để lại dữ liệu nạp dở.
    """
    from ketoan.api._guard import guard_manager

    guard_manager()
    from_date, to_date = _range(from_date, to_date)

    frappe.enqueue(
        "ketoan.api.misa_vat._run_sync",
        queue="long", timeout=1800,
        from_date=from_date, to_date=to_date,
    )
    return {
        "queued": True,
        "from_date": from_date,
        "to_date": to_date,
        "message": _("Đã xếp lịch đồng bộ {0} → {1}. Chạy nền vài phút, xem tiến độ ở MISA Sync Run.")
        .format(from_date, to_date),
    }


def _run_sync(from_date, to_date):
    """Thân của sync_now — chạy trong hàng đợi long."""
    from ketoan.api.misa_reconcile import match_snapshots
    from ketoan.api.misa_sync import _poll_pending, _pull_invoices

    result = {"from_date": from_date, "to_date": to_date}

    # 1. Kéo danh sách hóa đơn MISA về snapshot (không đụng Sales Invoice).
    try:
        run_name = _pull_invoices(from_date, to_date, trigger_type="Manual")
        result["pull_run"] = run_name
        result["pulled"] = frappe.db.get_value(
            "MISA Sync Run", run_name, ["fetched", "created", "updated", "status", "error_log"], as_dict=True
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "misa_vat.sync_now/pull")
        result["pulled"] = {"fetched": 0, "status": "Lỗi", "error_log": str(e)[:500]}

    # 2. Hỏi số hóa đơn cho các SI đã đẩy mà chưa có số.
    try:
        _poll_pending(500, 60, trigger_type="Manual")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "misa_vat.sync_now/poll")

    # 3. Khớp snapshot với Sales Invoice.
    try:
        result["matched"] = match_snapshots(from_date, to_date)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "misa_vat.sync_now/match")
        result["matched"] = {"error": str(e)[:500]}

    return result
