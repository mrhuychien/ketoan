"""mt_win_pending — theo dõi đợt giao Winmart CHƯA XUẤT HÓA ĐƠN.

Winmart chỉ cho xuất hóa đơn SAU KHI họ nhận hàng và có phiếu nhập kho trên hệ
của họ (SOP §2.2). Khoảng giữa "đã giao" và "đã xuất hóa đơn" hiện KHÔNG hệ nào
theo dõi:

  · ERPNext chưa có hóa đơn -> không hiện ở màn công nợ nào;
  · portal chưa có gì;
  · kế toán đang nhớ bằng dòng rời trong file Excel.

Và file Excel đang xử SAI khoảng đó: 9 đợt giao (46.665.180đ) bị CỘNG vào cột
`Số còn nợ` dù chưa xuất hóa đơn. Chưa xuất hóa đơn thì chưa phải khoản phải
thu — cộng vào là thổi phồng công nợ.

════════════════════════════════════════════════════════════════════════════
VÒNG ĐỜI MỘT ĐỢT GIAO
════════════════════════════════════════════════════════════════════════════

    Đang giao ──(có phiếu nhập kho Win)──> Đã nhận, chờ xuất HĐ
                                                  │
                                                  ├─(xuất hóa đơn)──> Đã xuất HĐ
                                                  └─(hủy đơn)───────> Hủy

Chỉ hai trạng thái đầu còn nằm trong danh sách chờ.

════════════════════════════════════════════════════════════════════════════
CÁI NÀY *KHÔNG* PHẢI KHÂU ĐỐI SOÁT PHIẾU NHẬP KHO
════════════════════════════════════════════════════════════════════════════

SOP §2.2 đòi khớp **PO + hàng hóa** giữa phiếu nhập kho Win và đơn trên ERPNext,
rồi lệch số lượng thì xuất trả phần chênh. Khâu ĐỐI SOÁT ĐÓ CHƯA CÓ — module này
mới là chỗ ĐỨNG của đợt giao và ghi lại số phiếu nhập kho khi kế toán nhập tay.

Nói rõ ra để không ai tưởng đã có: `grn_amount` ở đây do NGƯỜI gõ, không phải
máy kéo từ hệ Win về.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from ketoan.api._guard import guard_manager, guard_mt, is_chief
from ketoan.api.mt import _company, _require_tables, chain_customers
from ketoan.api.mt_win import WIN_CHAIN
from ketoan.mt.doctype.mt_win_pending.mt_win_pending import (
    OPEN_STATUSES,
    SOURCE_OPENING,
    STATUS_CANCELLED,
    STATUS_DELIVERING,
    STATUS_INVOICED,
    STATUS_RECEIVED,
)

DOCTYPE = "MT Win Pending"

# Trần một lần khởi tạo. File thật có 9 dòng; vượt xa mức này là đọc nhầm.
MAX_SEED = 500


def _tables():
    if not frappe.db.table_exists(DOCTYPE):
        frappe.throw(_(
            "Chức năng theo dõi đợt giao Winmart chưa được cài trên site này (thiếu "
            "bảng {0}). Chạy `bench --site <site> migrate` rồi thử lại.").format(DOCTYPE))


@frappe.whitelist()
def list_pending(company=None, status=None, search=None, page=1, page_size=50):
    """Danh sách đợt giao Winmart chưa xuất hóa đơn."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))

    p = {"company": company, "limit": page_size, "offset": (page - 1) * page_size}
    where = ["p.company = %(company)s"]
    if status:
        p["status"] = status
        where.append("p.status = %(status)s")
    else:
        # Mặc định CHỈ hiện đợt còn chờ. Đợt đã xuất hóa đơn / đã hủy vẫn tra
        # được bằng bộ lọc, nhưng không làm loãng danh sách việc phải làm.
        for i, s in enumerate(OPEN_STATUSES):
            p["s%d" % i] = s
        where.append("p.status IN (%s)" % ", ".join("%%(s%d)s" % i
                                                    for i in range(len(OPEN_STATUSES))))
    if cstr(search).strip():
        p["q"] = "%" + cstr(search).strip() + "%"
        where.append("(p.po_no LIKE %(q)s OR p.customer_name LIKE %(q)s "
                     "OR p.grn_no LIKE %(q)s)")
    w = " AND ".join(where)

    total = frappe.db.sql("SELECT COUNT(*) FROM `tab%s` p WHERE %s" % (DOCTYPE, w), p)[0][0]
    rows = frappe.db.sql("""
        SELECT p.name, p.customer, p.customer_name, p.po_no, p.delivery_date,
               p.amount_before_vat, p.vat_amount, p.total_amount,
               p.status, p.grn_no, p.grn_date, p.grn_amount,
               p.sales_invoice, p.source, p.note
        FROM `tab%s` p
        WHERE %s
        ORDER BY p.delivery_date ASC, p.po_no ASC
        LIMIT %%(limit)s OFFSET %%(offset)s
    """ % (DOCTYPE, w), p, as_dict=True)

    # Tổng của CẢ bộ lọc, không phải của trang đang xem.
    agg = frappe.db.sql("""
        SELECT COUNT(*) AS n, IFNULL(SUM(p.total_amount), 0) AS amount,
               SUM(CASE WHEN p.status = %%(recv)s THEN 1 ELSE 0 END) AS n_received
        FROM `tab%s` p WHERE %s
    """ % (DOCTYPE, w), dict(p, recv=STATUS_RECEIVED), as_dict=True)[0]

    return {
        "rows": rows,
        "total": cint(total),
        "pages": max(1, -(-cint(total) // page_size)),
        "page": page,
        "page_size": page_size,
        "amount": flt(agg.amount),
        "n_received": cint(agg.n_received),
        "statuses": [STATUS_DELIVERING, STATUS_RECEIVED, STATUS_INVOICED, STATUS_CANCELLED],
        "can_manage": is_chief(),
        "note": _(
            "Đây là hàng ĐÃ GIAO nhưng CHƯA xuất hóa đơn — chưa phải khoản phải thu, "
            "nên KHÔNG nằm trong công nợ. Win chỉ cho xuất hóa đơn sau khi có phiếu "
            "nhập kho của họ."),
    }


@frappe.whitelist()
def save_pending(name=None, customer=None, po_no=None, delivery_date=None,
                 amount_before_vat=None, vat_amount=None, status=None,
                 grn_no=None, grn_date=None, grn_amount=None,
                 sales_invoice=None, note=None, company=None):
    """Thêm / sửa một đợt giao. Chỉ trưởng hoặc kế toán quản lý."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)

    if name:
        doc = frappe.get_doc(DOCTYPE, name)
        if cstr(doc.company) != cstr(company):
            frappe.throw(_("Đợt giao {0} thuộc công ty khác").format(name))
    else:
        doc = frappe.new_doc(DOCTYPE)
        doc.company = company

    # `is not None` chứ không `if value`: gửi chuỗi rỗng là XÓA, không gửi là
    # GIỮ NGUYÊN. Dùng `if value` thì một lần lưu thiếu trường sẽ âm thầm xóa
    # mất số phiếu nhập kho mà không ai biết.
    if customer is not None:
        doc.customer = customer or None
    if po_no is not None:
        doc.po_no = po_no
    if delivery_date is not None:
        doc.delivery_date = getdate(delivery_date) if delivery_date else None
    if amount_before_vat is not None:
        doc.amount_before_vat = flt(amount_before_vat)
    if vat_amount is not None:
        doc.vat_amount = flt(vat_amount)
    if status is not None:
        doc.status = status
    if grn_no is not None:
        doc.grn_no = grn_no or None
    if grn_date is not None:
        doc.grn_date = getdate(grn_date) if grn_date else None
    if grn_amount is not None:
        doc.grn_amount = flt(grn_amount)
    if sales_invoice is not None:
        doc.sales_invoice = sales_invoice or None
    if note is not None:
        doc.note = note or None

    doc.save()
    frappe.db.commit()
    return {"name": doc.name, "po_no": doc.po_no, "status": doc.status,
            "total_amount": flt(doc.total_amount),
            "message": _("Đã lưu đợt giao PO {0}.").format(doc.po_no)}


@frappe.whitelist()
def delete_pending(name, company=None):
    """Xóa một đợt giao. KHÔNG xóa được đợt đã xuất hóa đơn."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)

    doc = frappe.get_doc(DOCTYPE, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Đợt giao {0} thuộc công ty khác").format(name))
    if doc.status == STATUS_INVOICED:
        frappe.throw(_(
            "Đợt giao PO {0} đã xuất hóa đơn {1} — xóa là mất vết nối giữa đơn giao và "
            "hóa đơn. Muốn bỏ theo dõi thì chuyển trạng thái 'Hủy'."
        ).format(doc.po_no, doc.sales_invoice))
    po = doc.po_no
    doc.delete()
    frappe.db.commit()
    return {"deleted": name, "po_no": po,
            "message": _("Đã xóa đợt giao PO {0}.").format(po)}


# ═══════════════════════════════════════════════════════════════════════════
# Khởi tạo từ file theo dõi công nợ — 9 dòng `chưa giao hàng`
# ═══════════════════════════════════════════════════════════════════════════

def _seed_rows(content, company):
    """Dòng CÒN NỢ mà KHÔNG có số hóa đơn trong file công nợ WinCommerce.

    Đó chính là các đợt đã giao chưa xuất hóa đơn. Cột `Ghi chú` của file Win
    giữ số PO (đo trên file thật: r2190 ghi 4194417760).
    """
    from ketoan.api import mt_opening

    res = mt_opening.read_opening(content, chain=WIN_CHAIN)
    if res["chain"] != WIN_CHAIN:
        frappe.throw(_("File này là của chuỗi {0}, không phải {1} — danh sách đợt giao "
                       "chỉ có ở WinCommerce.").format(res["chain"], WIN_CHAIN))

    rows = []
    for x in res["open_rows"]:
        if x.get("inv_no"):
            continue                      # đã có hóa đơn -> không thuộc danh sách chờ
        po = cstr(x.get("note") or "").strip()
        rows.append({
            "po_no": po or None,
            "party": x.get("party"),
            "amount_before_vat": flt(x.get("net")),
            "vat_amount": flt(x.get("vat")),
            "total_amount": flt(x.get("gross")) or flt(x.get("remaining")),
            "source_row": x.get("source_row"),
        })
    return res, rows


def _plan_hash(rows):
    """Vân tay kế hoạch — client phải gửi lại đúng cái đã xem trước."""
    blob = json.dumps([[r["po_no"], round(flt(r["total_amount"]), 2)] for r in rows],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


@frappe.whitelist()
def preview_seed(content, company=None):
    """Xem trước danh sách đợt giao dựng từ file công nợ Win. KHÔNG ghi gì."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    res, rows = _seed_rows(content, company)
    if len(rows) > MAX_SEED:
        frappe.throw(_("Dựng ra {0} đợt giao — vượt trần {1}. Gần như chắc chắn đọc nhầm "
                       "cột. KHÔNG ghi gì.").format(len(rows), MAX_SEED))

    existing = set()
    if rows:
        pos = [r["po_no"] for r in rows if r["po_no"]]
        if pos:
            keys = {}
            for i, po in enumerate(pos):
                keys["p%d" % i] = po
            got = frappe.db.sql(
                "SELECT po_no FROM `tab%s` WHERE company = %%(company)s AND po_no IN (%s)"
                % (DOCTYPE, ", ".join("%%(p%d)s" % i for i in range(len(pos)))),
                dict(keys, company=company))
            existing = {r[0] for r in got}

    blocked = []
    plan = []
    for r in rows:
        if not r["po_no"]:
            blocked.append(dict(r, reason="Không có số PO — không có khóa nào để theo dõi"))
        elif r["po_no"] in existing:
            blocked.append(dict(r, reason="PO đã được theo dõi rồi"))
        else:
            plan.append(r)

    return {
        "chain": res["chain"],
        "rows": plan,
        "blocked": blocked,
        "plan_hash": _plan_hash(plan),
        "total_amount": round(sum(flt(r["total_amount"]) for r in plan), 2),
        "n": len(plan),
        "note": _(
            "Đây là các dòng trong file công nợ CÓ tiền nhưng KHÔNG có số hóa đơn — "
            "hàng đã giao, chưa xuất hóa đơn. File Excel đang cộng chúng vào `Số còn "
            "nợ`; chúng KHÔNG phải công nợ và sẽ được theo dõi riêng ở đây."),
    }


@frappe.whitelist()
def commit_seed(content, expected_hash, company=None):
    """Tạo danh sách đợt giao từ file công nợ Win."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)

    pre = preview_seed(content, company=company)
    if not expected_hash or expected_hash != pre["plan_hash"]:
        frappe.throw(_(
            "Nội dung file đã đổi so với lúc xem trước. Xem lại rồi mới ghi — vân tay "
            "kế hoạch là chốt duy nhất chống việc ghi một thứ khác với thứ đã duyệt."))

    created, failed = [], []
    for r in pre["rows"]:
        sp = "wpd_%s" % cstr(r["po_no"])[:24]
        frappe.db.savepoint(sp)
        try:
            doc = frappe.new_doc(DOCTYPE)
            doc.company = company
            doc.po_no = r["po_no"]
            doc.amount_before_vat = flt(r["amount_before_vat"])
            doc.vat_amount = flt(r["vat_amount"])
            doc.status = STATUS_DELIVERING
            doc.source = SOURCE_OPENING
            # KHÔNG đoán Customer từ tên chi nhánh trong file. Tên đó là chuỗi tự
            # do ('CHI NHÁNH BÌNH DƯƠNG - CÔNG TY...'), khớp mờ sang Customer là
            # gán sai pháp nhân cho một đợt hàng sắp xuất hóa đơn.
            doc.note = _("Khởi tạo từ số dư đầu kỳ, dòng {0} của file công nợ. "
                         "Bên mua ghi trong file: {1}. Chọn lại Customer trước khi "
                         "xuất hóa đơn.").format(r["source_row"], r["party"] or "(trống)")
            doc.flags.ignore_mandatory = True     # `customer` để người chọn
            doc.insert(ignore_permissions=False)
            created.append({"name": doc.name, "po_no": doc.po_no,
                            "total_amount": flt(doc.total_amount)})
        except Exception as e:                                     # noqa: BLE001
            frappe.db.rollback(save_point=sp)
            failed.append({"po_no": r["po_no"], "error": cstr(e)[:200]})

    frappe.db.commit()
    return {
        "created": created,
        "failed": failed,
        "blocked": pre["blocked"],
        "total_amount": round(sum(flt(c["total_amount"]) for c in created), 2),
        "message": _("Đã tạo {0} đợt giao chờ xuất hóa đơn ({1} đ). {2} dòng lỗi, "
                     "{3} dòng bị chặn.").format(
            len(created), "{:,.0f}".format(sum(flt(c["total_amount"]) for c in created)),
            len(failed), len(pre["blocked"])),
        "warning": _(
            "Các đợt vừa tạo CHƯA có Customer — file chỉ ghi tên chi nhánh dạng chữ tự "
            "do, khớp mờ sang Customer là gán sai pháp nhân cho đơn sắp xuất hóa đơn. "
            "Chọn Customer cho từng đợt trước khi xuất."),
    }


@frappe.whitelist()
def search_win_customers(company=None):
    """Pháp nhân thuộc chuỗi WinCommerce — để chọn bên mua cho đợt giao."""
    guard_mt()
    _require_tables()
    _company(company)
    names = chain_customers(WIN_CHAIN)
    if not names:
        return {"rows": [], "message": _(
            "Chưa có khách hàng nào thuộc chuỗi {0}. Gán chuỗi cho khách rồi mới chọn "
            "được bên mua.").format(WIN_CHAIN)}
    keys = {"n%d" % i: n for i, n in enumerate(names)}
    rows = frappe.db.sql(
        "SELECT name, customer_name FROM `tabCustomer` WHERE name IN (%s) ORDER BY customer_name"
        % ", ".join("%%(n%d)s" % i for i in range(len(names))), keys, as_dict=True)
    return {"rows": rows, "message": ""}
