"""mt_debt — Công nợ MT ĐẾN HẠN theo term từng khách.

SOP §5 giao việc hàng tuần: "Xem report Công nợ MT đến hạn (theo term từng
Customer); nhắc/đòi các HĐ quá hạn." Đây là tầng tính cho việc đó.

════════════════════════════════════════════════════════════════════════════
BA ĐIỀU QUYẾT ĐỊNH ĐỘ ĐÚNG CỦA CON SỐ
════════════════════════════════════════════════════════════════════════════

1. CÒN NỢ BAO NHIÊU — lấy từ BẢNG KÊ CHUỖI, không lấy `outstanding_amount`.

   Kênh MT cố ý không tạo Payment Entry (ràng buộc số 2 của `mt.py`), nên
   `si.outstanding_amount` vẫn bằng nguyên `grand_total` kể cả khi chuỗi đã
   trả xong từ lâu. Dùng nó thì màn hình này sẽ đòi tiền những hóa đơn đã thu
   đủ — gọi điện đòi nhầm khách là hỏng quan hệ, không phải lỗi làm tròn.

   Dùng ĐÚNG công thức của `mt.get_overview` (`_debt_joins` + `_NET_PAID` + `_NET_DUE`)
   để hai màn hình không bao giờ nói hai số khác nhau về cùng một hóa đơn.

2. ĐẾN HẠN NGÀY NÀO — theo THỨ TỰ ƯU TIÊN, và LUÔN nói rõ lấy từ đâu.

     a. `Customer.custom_mt_credit_days` -> posting_date + N ngày   (`khai`)
     b. `Sales Invoice.due_date` khi nó LỚN HƠN posting_date        (`hoa_don`)
     c. không có gì  -> rổ riêng `chua_khai_han`, KHÔNG xếp hạn

   (a) đứng trước (b) vì SOP §2.1 giao cho kế toán khai hạn trên Customer;
   nhưng (b) vẫn được giữ để hóa đơn có Payment Terms không bị rơi vào rổ
   "chưa khai" oan.

   ⚠ TUYỆT ĐỐI KHÔNG mặc định 45 ngày cho khách chưa khai. Số 45 trong SOP là
   hạn của LOTTE và Co.op, không phải hạn của "chuỗi khác". Đoán 45 ngày cho
   một khách hạn thật 30 ngày là báo "chưa đến hạn" cho hóa đơn ĐÃ quá hạn 15
   ngày — im lặng đúng vào lúc cần kêu.

3. LỆCH HẠN — khi có CẢ (a) và (b) mà chúng ra hai ngày khác nhau, ghi cờ
   `due_conflict`. Không tự chọn bên nào là đúng rồi giấu bên kia: một trong
   hai chỗ khai sai, và chỉ người mới biết chỗ nào.

════════════════════════════════════════════════════════════════════════════
KHÔNG GHI GÌ
════════════════════════════════════════════════════════════════════════════

Module này CHỈ ĐỌC, trừ đúng một method `save_credit_days` ghi số ngày lên
Customer (`db.set_value`, không đụng Sales Invoice). Không tạo chứng từ, không
sửa hóa đơn, không đánh dấu gì lên bảng kê.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate

from ketoan.api._guard import guard_manager, guard_mt
from ketoan.api.mt import (
    PAID_TOLERANCE,
    _customer_chain_map,
    _customer_in_clause,
    chain_customers,
    KIND_DEDUCT,
    KIND_PAYMENT,
    _company,
    _mt_clause,
    opening_open_clause,
    _debt_joins,
    _require_tables,
)

# ═══════════════════════════════════════════════════════════════════════════
# Rổ tuổi nợ
#
# Mốc 15/30/60 theo cách kế toán MT thực sự hành động: dưới 15 ngày là nhắc
# nhẹ qua mail đầu mối; 16–30 là gọi; trên 30 là leo lên trưởng phòng; trên 60
# là rủi ro thu hồi. Đổi mốc thì đổi ở ĐÂY, frontend đọc nhãn từ đây xuống.
# ═══════════════════════════════════════════════════════════════════════════

BUCKETS = (
    ("chua_den_han",   "Chưa đến hạn",      None, 0),
    ("qua_han_1_15",   "Quá hạn 1–15 ngày",    1, 15),
    ("qua_han_16_30",  "Quá hạn 16–30 ngày",  16, 30),
    ("qua_han_31_60",  "Quá hạn 31–60 ngày",  31, 60),
    ("qua_han_60",     "Quá hạn trên 60 ngày", 61, None),
)
BUCKET_UNKNOWN = "chua_khai_han"
BUCKET_LABEL = dict([(k, lb) for k, lb, _a, _b in BUCKETS]
                    + [(BUCKET_UNKNOWN, "Chưa khai hạn thanh toán")])

DUE_FROM_TERM = "khai"        # từ Customer.custom_mt_credit_days
DUE_FROM_INVOICE = "hoa_don"  # từ Sales Invoice.due_date
DUE_NONE = "chua_khai"

MAX_ROWS = 2000


def _bucket_of(days_overdue):
    """days_overdue > 0 nghĩa là ĐÃ quá hạn bấy nhiêu ngày."""
    if days_overdue is None:
        return BUCKET_UNKNOWN
    for key, _label, lo, hi in BUCKETS:
        if lo is None:
            if days_overdue <= (hi or 0):
                return key
            continue
        if days_overdue >= lo and (hi is None or days_overdue <= hi):
            return key
    return BUCKETS[-1][0]


def _has_credit_days():
    """Field hạn thanh toán do patch v0_0_16 tạo — có thể chưa migrate."""
    return frappe.db.has_column("Customer", "custom_mt_credit_days")


def _resolve_due(row, as_of):
    """Ngày đến hạn + NGUỒN của nó + cờ lệch. Không đoán khi thiếu dữ liệu.

    Trả về (due_date | None, source, conflict_bool).
    """
    posting = getdate(row.get("posting_date"))

    days = cint(row.get("credit_days") or 0)
    by_term = add_days(posting, days) if days > 0 else None

    raw = row.get("due_date")
    by_inv = getdate(raw) if raw else None
    # due_date = posting_date là ERPNext lấy tạm vì KHÔNG có Payment Terms.
    # Đó là "không biết hạn", không phải "hạn ngay hôm nay".
    if by_inv is not None and by_inv <= posting:
        by_inv = None

    conflict = bool(by_term and by_inv and by_term != by_inv)
    if by_term:
        return by_term, DUE_FROM_TERM, conflict
    if by_inv:
        return by_inv, DUE_FROM_INVOICE, conflict
    return None, DUE_NONE, False


def _fetch(company, as_of, chain=None, customer=None, search=None):
    """Mọi hóa đơn MT còn nợ tính tới `as_of`, kèm số đã trả theo bảng kê.

    KHÔNG lọc theo khoảng ngày phát sinh: công nợ là SỐ DƯ. Hóa đơn xuất tháng
    3 còn nợ vẫn phải hiện ở báo cáo tháng 8, nếu không thì khoản nợ già nhất
    — khoản nguy hiểm nhất — chính là khoản biến mất khỏi màn hình.
    """
    p = {"company": company, "as_of": getdate(as_of), "tol": PAID_TOLERANCE,
         "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}
    mt = _mt_clause(p)
    join = _debt_joins()

    extra = ""
    if chain:
        # DÙNG CHUNG quy tắc "khách nào thuộc chuỗi nào" với mọi màn hình khác
        # (`mt.chain_customers`). Lọc thẳng `c.custom_mt_chain` là quy tắc HẸP
        # HƠN: nó bỏ sót khách đã có bảng kê của chuỗi mà chưa kịp khai field,
        # nên cùng một chuỗi ra hai tập khách ở hai màn hình.
        extra += " AND " + _customer_in_clause(chain_customers(chain), p)
    if customer:
        p["customer"] = customer
        extra += " AND si.customer = %(customer)s"
    if cstr(search).strip():
        # Tìm phải lọc CẢ tổng hợp lẫn danh sách, không chỉ danh sách: hai con số
        # trên cùng màn hình nói về hai tập hóa đơn khác nhau là cách chắc chắn
        # để kế toán đọc nhầm.
        p["q"] = "%" + cstr(search).strip() + "%"
        extra += (" AND (si.name LIKE %(q)s OR si.customer_name LIKE %(q)s"
                  " OR c.name LIKE %(q)s)")

    credit = "c.custom_mt_credit_days" if _has_credit_days() else "NULL"

    # Hóa đơn đã tất toán TRƯỚC ngày chuyển giao không còn là nợ. Gọi đúng cái
    # hàm mà `mt.get_overview` gọi — màn hình công nợ và rổ 'chưa thanh toán'
    # phải nói về CÙNG một tập hóa đơn, nếu không kế toán đối chiếu hai màn hình
    # ra hai số khác nhau mà không biết tin cái nào.
    opening = opening_open_clause(p, p["company"])

    return frappe.db.sql(f"""
        SELECT si.name, si.customer, si.customer_name, si.posting_date, si.due_date,
               ABS(si.grand_total) AS grand_total,
               IFNULL(c.custom_mt_chain, '') AS chain,
               {credit} AS credit_days,
               IFNULL(p.paid, 0) AS paid,
               IFNULL(p.clawed_back, 0) AS clawed_back,
               IFNULL(p.paid_review, 0) AS paid_review,
               p.last_payment_date,
               IFNULL(rt.returned, 0) AS returned,
               GREATEST(ABS(si.grand_total) - IFNULL(rt.returned, 0)
                        - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), 0) AS remaining
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND si.posting_date <= %(as_of)s
          AND (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)) < (ABS(si.grand_total) - IFNULL(rt.returned, 0)) - %(tol)s
          AND {opening}
          AND {mt} {extra}
        ORDER BY si.posting_date ASC, si.name ASC
    """, p, as_dict=True)


def _enrich(rows, as_of):
    """Gắn ngày đến hạn, số ngày quá hạn, rổ — cho từng hóa đơn.

    CHUỖI của hóa đơn cũng gán ở đây, bằng ĐÚNG bản đồ mà bộ lọc dùng. Nếu để
    nguyên cột `custom_mt_chain` đọc thẳng từ SQL thì lọc và gộp chạy theo hai
    quy tắc: khách chưa khai field sẽ lọt qua bộ lọc (vì bản đồ suy được chuỗi
    cho họ) rồi rơi vào nhóm chuỗi rỗng khi gộp — tiền biến khỏi mọi thẻ chuỗi.
    """
    as_of = getdate(as_of)
    mapping, _amb = _customer_chain_map()
    out = []
    for r in rows:
        d = dict(r)
        d["chain"] = mapping.get(cstr(r.get("customer"))) or ""
        due, source, conflict = _resolve_due(r, as_of)
        d["due_date"] = cstr(due) if due else None
        d["due_source"] = source
        d["due_conflict"] = conflict
        d["days_overdue"] = (as_of - due).days if due else None
        d["bucket"] = _bucket_of(d["days_overdue"])
        d["bucket_label"] = BUCKET_LABEL[d["bucket"]]
        d["remaining"] = flt(r.get("remaining"))
        d["grand_total"] = flt(r.get("grand_total"))
        d["paid_review"] = flt(r.get("paid_review"))
        d["last_payment_date"] = cstr(r.get("last_payment_date") or "") or None
        out.append(d)
    return out


def _rollup(rows):
    """Cộng theo rổ và theo chuỗi. Đếm CẢ số hóa đơn, không chỉ tiền."""
    by_bucket = {}
    for key, label, _lo, _hi in BUCKETS:
        by_bucket[key] = {"key": key, "label": label, "count": 0, "amount": 0.0}
    by_bucket[BUCKET_UNKNOWN] = {"key": BUCKET_UNKNOWN,
                                 "label": BUCKET_LABEL[BUCKET_UNKNOWN],
                                 "count": 0, "amount": 0.0}

    by_chain = {}
    total = 0.0
    overdue = 0.0
    overdue_count = 0
    conflicts = 0
    review = 0.0

    for r in rows:
        amt = flt(r["remaining"])
        total += amt
        b = by_bucket[r["bucket"]]
        b["count"] += 1
        b["amount"] += amt

        if r["days_overdue"] is not None and r["days_overdue"] > 0:
            overdue += amt
            overdue_count += 1
        if r["due_conflict"]:
            conflicts += 1
        review += flt(r.get("paid_review"))

        ch = r.get("chain") or ""
        c = by_chain.setdefault(ch, {"chain": ch, "count": 0, "amount": 0.0,
                                     "overdue": 0.0, "unknown_term": 0})
        c["count"] += 1
        c["amount"] += amt
        if r["days_overdue"] is not None and r["days_overdue"] > 0:
            c["overdue"] += amt
        if r["bucket"] == BUCKET_UNKNOWN:
            c["unknown_term"] += 1

    chains = sorted(by_chain.values(), key=lambda x: -x["overdue"])
    return {
        "buckets": [by_bucket[k] for k, _l, _a, _b in BUCKETS] + [by_bucket[BUCKET_UNKNOWN]],
        "chains": chains,
        "total": total,
        "total_count": len(rows),
        "overdue": overdue,
        "overdue_count": overdue_count,
        "unknown_term_count": by_bucket[BUCKET_UNKNOWN]["count"],
        "unknown_term_amount": by_bucket[BUCKET_UNKNOWN]["amount"],
        "due_conflicts": conflicts,
        "pending_review": review,
    }


def _orphan_returns(company, as_of):
    """Phiếu trả hàng KHÔNG khai `return_against` — không trừ được vào hóa đơn nào.

    Quy trình nói là luôn khai, và `_returns_join` dựa hẳn vào điều đó để trừ
    hàng trả lại khỏi hóa đơn gốc. Nhưng "luôn khai" là CAM KẾT QUY TRÌNH, không
    phải ràng buộc hệ thống — ERPNext cho lập credit note rời hoàn toàn.

    Một phiếu rời thì không trừ vào đâu cả, và cách nó hỏng là IM LẶNG: công nợ
    cao hơn thực tế đúng bằng số đó, không có lỗi, không có cảnh báo. Nên đếm nó
    ra và hiện lên. Hệ thống KHÔNG tự đoán nó thuộc hóa đơn nào — đoán là ghi
    giảm nhầm hóa đơn; người khai `return_against` rồi số tự đúng.
    """
    # `_mt_clause` NHÉT tham số vào chính dict truyền vào. Đưa `{}` rồi dùng dict
    # khác để chạy là thiếu bind param -> nổ SQL. Dùng đúng một dict.
    p = {"company": company, "as_of": getdate(as_of)}
    row = frappe.db.sql("""
        SELECT COUNT(*) AS n, IFNULL(SUM(ABS(r.grand_total)), 0) AS amount
        FROM `tabSales Invoice` r
        INNER JOIN `tabCustomer` c ON c.name = r.customer
        WHERE r.docstatus = 1 AND r.is_return = 1
          AND r.company = %(company)s
          AND r.posting_date <= %(as_of)s
          AND IFNULL(r.return_against, '') = ''
          AND {mt}
    """.format(mt=_mt_clause(p)), p, as_dict=True)[0]
    return {
        "orphan_return_count": cint(row.n),
        "orphan_return_amount": flt(row.amount),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Method cho portal
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_due_summary(company=None, as_of=None, chain=None, search=None):
    """Tổng hợp công nợ MT đến hạn: theo rổ tuổi nợ và theo chuỗi."""
    guard_mt()
    _require_tables()
    company = _company(company)
    as_of = getdate(as_of or nowdate())

    rows = _enrich(_fetch(company, as_of, chain=chain, search=search), as_of)
    data = _rollup(rows)
    # Đếm ở ĐÂY chứ không trong `_rollup`: `_rollup` chỉ nhận `rows`, mà phiếu
    # trả hàng rời KHÔNG nằm trong `rows` — chính vì nó không nối vào hóa đơn
    # nào nên nó vắng mặt khỏi mọi màn hình. Đó là lý do phải đếm riêng.
    data.update(_orphan_returns(company, as_of))
    data["as_of"] = cstr(as_of)
    data["company"] = company
    data["chain"] = chain or ""
    data["search"] = cstr(search or "")
    data["has_credit_days_field"] = _has_credit_days()
    # Nguồn tiền đã trả là BẢNG KÊ CHUỖI, không phải sổ cái. Nói thẳng trên
    # màn hình để không ai đem con số này đi đối chiếu với số dư TK 131.
    data["basis_note"] = _(
        "Số còn nợ tính từ dòng thanh toán trên bảng kê chuỗi đã nạp, "
        "KHÔNG phải số dư tài khoản 131 trên sổ cái.")
    return data


@frappe.whitelist()
def get_due_invoices(company=None, as_of=None, bucket=None, chain=None,
                     customer=None, search=None, page=1, page_size=50):
    """Danh sách hóa đơn còn nợ, lọc theo rổ tuổi nợ / chuỗi / khách."""
    guard_mt()
    _require_tables()
    company = _company(company)
    as_of = getdate(as_of or nowdate())
    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))

    rows = _enrich(_fetch(company, as_of, chain=chain, customer=customer,
                          search=search), as_of)
    if bucket and bucket != "tat_ca":
        if bucket not in BUCKET_LABEL:
            frappe.throw(_("Rổ tuổi nợ không hợp lệ: {0}").format(bucket))
        rows = [r for r in rows if r["bucket"] == bucket]

    # Nợ già nhất lên trước — đó là thứ tự người đi đòi cần.
    # Hóa đơn chưa khai hạn xếp cuối: chưa biết hạn thì chưa đòi được.
    rows.sort(key=lambda r: (r["days_overdue"] is None,
                             -(r["days_overdue"] or 0), r["posting_date"]))

    total = len(rows)
    start = (page - 1) * page_size
    return {
        "rows": rows[start:start + page_size],
        "total": total,
        "pages": max(1, -(-total // page_size)),
        "page": page,
        "page_size": page_size,
        "amount": sum(flt(r["remaining"]) for r in rows),
        "bucket": bucket or "tat_ca",
        "bucket_label": BUCKET_LABEL.get(bucket or "", _("Tất cả")),
        "as_of": cstr(as_of),
        # KHÔNG cắt bớt dòng nào — cắt là giấu nợ. Chỉ báo "nhiều" để màn hình
        # gợi ý lọc bớt.
        "heavy": total > MAX_ROWS,
    }


@frappe.whitelist()
def get_credit_terms(company=None):
    """Bảng khai hạn thanh toán của từng khách MT — để kế toán soi chỗ trống."""
    guard_mt()
    _require_tables()
    company = _company(company)

    if not _has_credit_days():
        return {"rows": [], "has_field": False, "missing": 0,
                "message": _("Chưa chạy migrate — field hạn thanh toán chưa có.")}

    p = {"company": company}
    mt = _mt_clause(p)
    rows = frappe.db.sql(f"""
        SELECT c.name AS customer, c.customer_name,
               IFNULL(c.custom_mt_chain, '') AS chain,
               IFNULL(c.custom_mt_credit_days, 0) AS credit_days,
               COUNT(si.name) AS n_invoices
        FROM `tabCustomer` c
        LEFT JOIN `tabSales Invoice` si
               ON si.customer = c.name AND si.docstatus = 1
              AND si.company = %(company)s
        WHERE {mt}
        GROUP BY c.name, c.customer_name, c.custom_mt_chain, c.custom_mt_credit_days
        ORDER BY c.custom_mt_chain ASC, c.customer_name ASC
    """, p, as_dict=True)

    out = [dict(r, credit_days=cint(r.credit_days)) for r in rows]
    return {
        "rows": out,
        "has_field": True,
        "missing": sum(1 for r in out if not r["credit_days"]),
        # Khách chưa khai hạn mà VẪN CÓ hóa đơn là chỗ đau nhất: nợ của họ
        # không bao giờ vào rổ quá hạn.
        "missing_with_invoices": sum(1 for r in out
                                     if not r["credit_days"] and cint(r["n_invoices"]) > 0),
    }


@frappe.whitelist()
def save_credit_days(customer, credit_days, company=None):
    """Khai hạn thanh toán MT cho một khách. Chỉ trưởng/kế toán quản lý."""
    guard_manager()
    _require_tables()
    company = _company(company)

    if not _has_credit_days():
        frappe.throw(_("Chưa chạy migrate — field hạn thanh toán chưa có trên Customer."))
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Không có khách hàng {0}").format(customer))

    days = cint(credit_days)
    if days < 0:
        frappe.throw(_("Hạn thanh toán không thể âm"))
    if days > 365:
        frappe.throw(_("Hạn {0} ngày vượt quá 365 — kiểm lại, nhiều khả năng gõ nhầm.")
                     .format(days))

    # `days = 0` là XÓA khai báo, đưa khách về rổ "chưa khai hạn". Đó là hành
    # động hợp lệ và có ý nghĩa khác hẳn "hạn 0 ngày" — nên phải nói rõ ra.
    frappe.db.set_value("Customer", customer, "custom_mt_credit_days", days,
                        update_modified=False)
    frappe.db.commit()
    return {
        "customer": customer,
        "credit_days": days,
        "message": (_("Đã xóa khai hạn của {0} — hóa đơn của khách này quay về rổ "
                      "'chưa khai hạn'.").format(customer) if days == 0
                    else _("Hạn thanh toán của {0}: {1} ngày.").format(customer, days)),
    }
