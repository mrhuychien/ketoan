"""mt — API cho 3 màn hình kế toán kênh MT (siêu thị hiện đại).

Ba màn hình:
  · Tổng quan       → get_overview()       — 3 rổ + công nợ chuỗi
  · Danh sách hóa đơn → get_invoices()     — chia trang 20 dòng
  · Công nợ theo chuỗi → get_chain_summary()

Và luồng nạp bảng kê thanh toán của chuỗi:
  · preview_advice()  — đọc file + khớp hóa đơn, KHÔNG ghi gì (bắt buộc)
  · commit_advice()   — tạo MT Payment Advice + dòng, có vân tay kế hoạch
  · relink_line()     — kế toán chốt tay liên kết một dòng với Sales Invoice

════════════════════════════════════════════════════════════════════════════
RÀNG BUỘC KHÔNG ĐƯỢC PHÁ
════════════════════════════════════════════════════════════════════════════

1. MỘT NGUỒN SỰ THẬT cho trạng thái thanh toán. KHÔNG có cột "đã thanh toán"
   trên Sales Invoice. Trạng thái được SUY RA bằng cách cộng dồn các dòng
   `MT Payment Advice Line` có row_kind='Thanh toán' đang trỏ về hóa đơn đó.
   Một hóa đơn có thể được trả LÀM NHIỀU LẦN (nhiều bảng kê, nhiều kỳ) nên
   phải CỘNG DỒN rồi mới so với grand_total — so từng dòng một là báo "chưa
   thanh toán" cho hóa đơn đã trả đủ qua 2 kỳ.

2. Module này TUYỆT ĐỐI KHÔNG tạo/sửa/hủy Payment Entry, Journal Entry hay bất
   kỳ chứng từ kế toán nào. Chỉ GHI NHẬN dòng đọc từ file + đánh dấu. Con người
   quyết định hạch toán. Hệ quả phải chấp nhận: `si.outstanding_amount` của
   ERPNext KHÔNG phản ánh tiền chuỗi đã trả (vì không có Payment Entry) — nên
   mọi con số công nợ ở đây tính từ bảng kê, và phải nói rõ như vậy trên màn
   hình, đừng để kế toán tưởng đó là số dư sổ cái.

3. Không đụng tới Sales Invoice đã ghi sổ. Module này không db_set lên Sales
   Invoice dòng nào — nó chỉ ĐỌC.

4. Chỉ dòng row_kind='Thanh toán' mới được nối Sales Invoice (child doctype đã
   chặn ở validate). Dòng chiết khấu của Central Retail mang ký hiệu hóa đơn
   bán ra của chính mình mà KHÔNG phải thanh toán hóa đơn đó.

════════════════════════════════════════════════════════════════════════════
HỢP ĐỒNG VỚI `ketoan.api.mt_advice` (tầng đọc file)
════════════════════════════════════════════════════════════════════════════

Module này KHÔNG đọc Excel. Toàn bộ việc đọc 5 định dạng file nằm ở
`ketoan.api.mt_advice`, dùng theo hợp đồng sau:

    mt_advice.CHAIN_LABEL -> {khóa ASCII: nhãn}   # trùng options field `chain`
    mt_advice.read_payment_advice(content: str, chain=None) -> dict

`content` là base64 (có/không tiền tố data URI) — tầng đọc tự nhận .xlsx/.xls
theo CHỮ KÝ BYTE, không theo đuôi tên file. Trả về MỘT dict cho CẢ FILE:

    {
      "chain": "LOTTE", "chain_key": "lotte",
      "advice_no": str | None,          # nếu file chỉ có một số chứng từ
      "payment_dates": ["2026-07-10", "2026-07-30"],
      "declared_totals": {...},         # SỐ KIỂM TRA đọc từ chính file
      "computed_totals": {...},
      "checks": [{label, declared, computed, diff, ok}, ...],
      "reconciled": bool,               # MỌI số kiểm tra đều khớp?
      "groups": [ {key, advice_no, payment_date, n_rows, ...}, ... ],
      "rows": [ {...bộ khóa chuẩn...} ],   # CHỈ dòng tiền, không có dòng tổng
      "warnings": [str],
    }

Mỗi phần tử `rows`:
    row_kind (ASCII: thanh_toan/chiet_khau/phi/ghi_giam/khac), row_kind_label,
    row_subtype, inv_series, inv_series_norm, inv_no, inv_no_norm, inv_date,
    store_code, store_name, doc_no, description, amount_before_vat, vat_amount,
    total_amount (ĐỘ LỚN), signed_amount (GIỮ DẤU), payment_date, needs_review,
    source_sheet, source_row

MỘT FILE ≠ MỘT BẢN GHI. `groups` là các LẦN THANH TOÁN riêng nằm trong cùng một
file: Co.op 8 sheet = 8 kỳ (mỗi kỳ một số chứng từ + một bộ số kiểm tra), LOTTE
2 Payment Date, Central Retail 2 Clearing Doc. Gộp lại thành một bản ghi là cộng
nhầm tiền của hai kỳ vào nhau (§J.3 của hợp đồng). Tầng đọc KHÔNG chia sẵn dòng
theo nhóm, nên `_split_advices()` ở dưới phải chia lại — và chia xong PHẢI đối
chiếu với `n_rows` mà tầng đọc công bố, chia sai là chia sai tiền.

DẤU: lưu `signed_amount` vào `total_amount` của dòng DocType (field ghi rõ "giữ
nguyên DẤU đọc được từ file") — dấu là chốt đối chiếu với dòng tổng do chuỗi in
ra. Khi CỘNG TIỀN ĐÃ THU thì dùng ABS(), nhưng chỉ trên dòng 'Thanh toán', nơi
bản chất đã biết chắc nhờ cột loại chứng từ, chứ không suy bản chất từ dấu.
"""

import base64
import hashlib
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, cstr, flt, getdate, nowdate

from ketoan.api._guard import (
    channel_group_clause,
    guard_manager,
    guard_mt,
    is_chief,
    resolve_company,
)
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)
from ketoan.mt.doctype.mt_payment_advice_line.mt_payment_advice_line import norm_series_mt

PAGE_SIZE = 20
MAX_PAGE_SIZE = 200

# Nhãn row_kind trong DocType (tiếng Việt có dấu). Fieldname vẫn ASCII.
KIND_PAYMENT = "Thanh toán"
KIND_DISCOUNT = "Chiết khấu"
KIND_FEE = "Phí"
KIND_DEDUCT = "Ghi giảm"
KIND_OTHER = "Khác"

# Các loại dòng KHẤU TRỪ — không phải hóa đơn, không nối Sales Invoice.
DEDUCTION_KINDS = (KIND_DISCOUNT, KIND_FEE, KIND_DEDUCT, KIND_OTHER)

# row_kind ASCII của tầng đọc file -> nhãn của DocType.
#
# Dòng nào tầng đọc KHÔNG nhận diện được sẽ vào 'Khác' chứ KHÔNG bị bỏ im lặng:
# bỏ im lặng là mất tiền khỏi tổng mà không ai thấy. Chỉ 'bo_qua'/'kiem_tra'
# (dòng tiêu đề, dòng cộng, số kiểm tra) mới được loại — cộng chúng vào là nhân
# đôi tiền của cả trang.
ROW_KIND_MAP = {
    "thanh_toan": KIND_PAYMENT,
    "chiet_khau": KIND_DISCOUNT,
    "phi": KIND_FEE,
    "ghi_giam": KIND_DEDUCT,
    "ghi_giam_khong_ky_hieu": KIND_DEDUCT,
    "khac": KIND_OTHER,
    # cho phép tầng đọc trả thẳng nhãn tiếng Việt
    KIND_PAYMENT: KIND_PAYMENT,
    KIND_DISCOUNT: KIND_DISCOUNT,
    KIND_FEE: KIND_FEE,
    KIND_DEDUCT: KIND_DEDUCT,
    KIND_OTHER: KIND_OTHER,
}

# Dòng KHÔNG phải tiền phát sinh: tiêu đề, phân cách, dòng cộng nhóm, số kiểm tra.
ROW_KIND_DROP = {"bo_qua", "kiem_tra", "bo qua", ""}

BUCKETS = ("chua_thanh_toan", "da_thanh_toan", "chiet_khau", "tat_ca")

# Sai số cho phép khi kết luận "đã thu đủ tiền hóa đơn".
#
# 1 đồng, không hơn. Lệch làm tròn ±1..3đ đã đo được ở Co.op nằm ở CẤP NHÓM
# siêu thị (tổng nhóm vs tổng dòng), không phải ở số tiền của từng hóa đơn —
# nên không cần nới ở đây. Nới rộng là tự động đánh dấu "đã trả đủ" cho hóa đơn
# còn thiếu tiền thật.
PAID_TOLERANCE = 1.0

# Trần an toàn cho file tải lên (base64 nở ~4/3 so với file gốc).
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Field số hóa đơn trên Sales Invoice — dùng chung với luồng MISA để hai tầng
# đối soát không lệch nhau.
SI_SERIES_FIELD = "custom_misa_inv_series"
SI_NO_FIELD = "custom_misa_inv_no"


# ═══════════════════════════════════════════════════════════════════════════
# Tiện ích chung
# ═══════════════════════════════════════════════════════════════════════════

def _range(from_date, to_date):
    to_date = to_date or nowdate()
    from_date = from_date or add_months(to_date, -1)
    return from_date, to_date


def _company(company=None):
    company = resolve_company(company)
    if not company:
        frappe.throw(_("Chưa xác định được công ty"))
    return company


def _page(page, page_size):
    page = max(1, cint(page or 1))
    page_size = min(max(1, cint(page_size or PAGE_SIZE)), MAX_PAGE_SIZE)
    return page, page_size, (page - 1) * page_size


def _has_si_field(field):
    return bool(frappe.get_meta("Sales Invoice").has_field(field))


def _mt_clause(params):
    """Mệnh đề lọc khách hàng kênh MT (theo Customer Group khai trong Settings)."""
    return channel_group_clause("mt", params, alias="c")


def _paid_subquery():
    """Bảng tạm: mỗi Sales Invoice đã được bảng kê MT trả bao nhiêu tiền.

    CỘNG DỒN mọi dòng 'Thanh toán' trỏ về hóa đơn đó, bất kể thuộc bảng kê nào —
    một hóa đơn có thể được chuỗi trả làm nhiều lần (Co.op tách 8 kỳ trong một
    file; LOTTE có 2 ngày thanh toán). So từng dòng riêng lẻ với grand_total sẽ
    báo "chưa thanh toán" cho hóa đơn thực ra đã trả đủ.

    ABS() vì mỗi chuỗi một quy ước dấu — nhưng chỉ áp trên dòng đã được xác định
    là 'Thanh toán' bằng CỘT LOẠI CHỨNG TỪ ở tầng đọc file, không phải bằng dấu.

    Đếm cả bảng kê còn ở trạng thái 'Nháp': dòng đã được ghi nhận nghĩa là tiền
    đã về theo bản kê của chuỗi. Trạng thái Nháp/Đã đối chiếu/Đã ghi nhận nói về
    việc CON NGƯỜI đã soi tới đâu, không nói về việc tiền đã về hay chưa.
    """
    return """
        LEFT JOIN (
            SELECT l.sales_invoice AS si_name,
                   SUM(ABS(l.total_amount)) AS paid,
                   COUNT(*) AS pay_lines,
                   MAX(IFNULL(l.payment_date, a.payment_date)) AS last_payment_date
            FROM `tabMT Payment Advice Line` l
            INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
            WHERE l.parenttype = 'MT Payment Advice'
              AND l.row_kind = %(kind_payment)s
              AND IFNULL(l.sales_invoice, '') != ''
            GROUP BY l.sales_invoice
        ) p ON p.si_name = si.name
    """


# Điều kiện của từng rổ hóa đơn.
#
# `is_return = 0` ở rổ "chưa thanh toán": hóa đơn trả hàng là khoản GHI GIẢM
# công nợ, không phải khoản phải thu. Để nó nằm trong rổ nợ thì rổ đó lúc nào
# cũng đầy phiếu trả hàng không bao giờ "được thanh toán" — báo động giả.
_BUCKET_WHERE = {
    "chua_thanh_toan": "si.is_return = 0 AND IFNULL(p.paid, 0) < ABS(si.grand_total) - %(tol)s",
    "da_thanh_toan": "IFNULL(p.paid, 0) > 0 AND IFNULL(p.paid, 0) >= ABS(si.grand_total) - %(tol)s",
    "tat_ca": "1 = 1",
}


# ═══════════════════════════════════════════════════════════════════════════
# Màn hình 1 — Tổng quan
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_overview(company=None, from_date=None, to_date=None):
    """Ba rổ của kênh MT + công nợ chuỗi.

    Ba rổ: hóa đơn CHƯA thu đủ tiền · hóa đơn ĐÃ thu đủ · các khoản chuỗi TRỪ
    LẠI (chiết khấu / phí / ghi giảm).
    """
    guard_mt()
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)

    p = {"company": company, "fd": from_date, "td": to_date,
         "tol": PAID_TOLERANCE, "kind_payment": KIND_PAYMENT}
    mt = _mt_clause(p)
    join = _paid_subquery()

    def bucket(where):
        return frappe.db.sql(f"""
            SELECT COUNT(*) AS cnt,
                   IFNULL(SUM(ABS(si.grand_total)), 0) AS amount,
                   IFNULL(SUM(GREATEST(ABS(si.grand_total) - IFNULL(p.paid, 0), 0)), 0) AS remaining,
                   IFNULL(SUM(LEAST(IFNULL(p.paid, 0), ABS(si.grand_total))), 0) AS collected
            FROM `tabSales Invoice` si
            INNER JOIN `tabCustomer` c ON c.name = si.customer
            {join}
            WHERE si.docstatus = 1 AND si.company = %(company)s
              AND si.posting_date BETWEEN %(fd)s AND %(td)s
              AND {mt} AND {where}
        """, p, as_dict=True)[0]

    chua = bucket(_BUCKET_WHERE["chua_thanh_toan"])
    da = bucket(_BUCKET_WHERE["da_thanh_toan"])

    # Rổ 3 đếm DÒNG BẢNG KÊ, không đếm hóa đơn: khoản chuỗi trừ lại thường không
    # gắn với hóa đơn nào (phí hỗ trợ, chiết khấu tháng, NET OFF).
    ded = frappe.db.sql(f"""
        SELECT l.row_kind, COUNT(*) AS cnt, IFNULL(SUM(ABS(l.total_amount)), 0) AS amount
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind IN ({', '.join(['%(k' + str(i) + ')s' for i in range(len(DEDUCTION_KINDS))])})
          AND IFNULL(a.company, %(company)s) = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
        GROUP BY l.row_kind
    """, dict(p, **{f"k{i}": k for i, k in enumerate(DEDUCTION_KINDS)}), as_dict=True)

    by_kind = {r.row_kind: {"count": r.cnt, "amount": flt(r.amount)} for r in ded}

    # Công nợ chuỗi: tính tới HẾT to_date, không giới hạn trong khoảng xem.
    # Công nợ là SỐ DƯ, không phải phát sinh trong kỳ.
    #
    # KHÔNG dùng si.outstanding_amount của ERPNext: module này cố ý không tạo
    # Payment Entry, nên outstanding_amount vẫn bằng nguyên grand_total dù chuỗi
    # đã trả. Con số ở đây là "công nợ theo bảng kê chuỗi", phải ghi rõ như vậy
    # trên màn hình.
    debt = frappe.db.sql(f"""
        SELECT
            IFNULL(SUM(CASE WHEN si.is_return = 0
                            THEN GREATEST(ABS(si.grand_total) - IFNULL(p.paid, 0), 0) ELSE 0 END), 0) AS unpaid,
            IFNULL(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) AS credit_notes,
            SUM(CASE WHEN si.is_return = 0
                     AND IFNULL(p.paid, 0) < ABS(si.grand_total) - %(tol)s THEN 1 ELSE 0 END) AS unpaid_count
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date <= %(td)s AND {mt}
    """, p, as_dict=True)[0]

    # Dòng thanh toán chưa nối được hóa đơn nào — tiền đã về mà không biết của
    # hóa đơn nào. Đây là việc CẦN NGƯỜI làm, phải hiện ngay ở tổng quan.
    unmatched = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, IFNULL(SUM(ABS(l.total_amount)), 0) AS amount
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind_payment)s
          AND IFNULL(l.sales_invoice, '') = ''
          AND IFNULL(a.company, %(company)s) = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
    """, p, as_dict=True)[0]

    need_review = frappe.db.sql("""
        SELECT COUNT(*) AS cnt
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.match_confidence = 'Cần review'
          AND IFNULL(a.company, %(company)s) = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
    """, p, as_dict=True)[0]

    advices = frappe.db.sql("""
        SELECT a.name, a.chain, a.customer, a.advice_no, a.payment_date, a.status,
               a.total_payment, a.total_discount, a.total_fee, a.total_other,
               a.declared_total_payment, a.reconciled, a.file_name
        FROM `tabMT Payment Advice` a
        WHERE IFNULL(a.company, %(company)s) = %(company)s
          AND a.payment_date BETWEEN %(fd)s AND %(td)s
        ORDER BY a.payment_date DESC, a.creation DESC
        LIMIT 20
    """, p, as_dict=True)

    deduction_total = sum(v["amount"] for v in by_kind.values())

    return {
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "tolerance": PAID_TOLERANCE,
        "buckets": {
            "chua_thanh_toan": {"count": chua.cnt, "amount": flt(chua.amount),
                                "remaining": flt(chua.remaining), "collected": flt(chua.collected)},
            "da_thanh_toan": {"count": da.cnt, "amount": flt(da.amount),
                              "collected": flt(da.collected)},
            "chiet_khau": {"count": sum(v["count"] for v in by_kind.values()),
                           "amount": deduction_total,
                           "by_kind": by_kind},
        },
        # Công nợ theo BẢNG KÊ CHUỖI, không phải số dư sổ cái (xem chú thích SQL).
        "debt": {
            "unpaid_invoices": flt(debt.unpaid),
            "unpaid_count": cint(debt.unpaid_count),
            "credit_notes": flt(debt.credit_notes),
            "estimate": flt(debt.unpaid) - flt(debt.credit_notes),
            "as_of": to_date,
            "note": _("Tính từ bảng kê thanh toán của chuỗi, KHÔNG phải số dư sổ cái "
                      "(hệ thống cố ý không tự tạo Payment Entry)."),
        },
        "attention": {
            "unmatched_payment_lines": {"count": unmatched.cnt, "amount": flt(unmatched.amount)},
            "need_review_lines": cint(need_review.cnt),
        },
        "recent_advices": advices,
        "can_import": is_chief(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Màn hình 2 — Danh sách hóa đơn (chia trang 20/trang)
# ═══════════════════════════════════════════════════════════════════════════

def _invoice_page(company, from_date, to_date, where, search, page_size, offset, sort=None):
    p = {"company": company, "fd": from_date, "td": to_date, "tol": PAID_TOLERANCE,
         "kind_payment": KIND_PAYMENT, "limit": page_size, "offset": offset}
    mt = _mt_clause(p)
    join = _paid_subquery()
    if search:
        p["kw"] = f"%{search}%"
        where += (" AND (si.name LIKE %(kw)s OR si.customer_name LIKE %(kw)s"
                  f" OR si.{SI_NO_FIELD} LIKE %(kw)s)") if _has_si_field(SI_NO_FIELD) else \
                 " AND (si.name LIKE %(kw)s OR si.customer_name LIKE %(kw)s)"

    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND {mt} AND {where}
    """, p)[0][0]

    series_col = f"si.{SI_SERIES_FIELD}" if _has_si_field(SI_SERIES_FIELD) else "NULL"
    no_col = f"si.{SI_NO_FIELD}" if _has_si_field(SI_NO_FIELD) else "NULL"
    order = sort or "si.posting_date DESC, si.name DESC"

    rows = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, si.customer, si.customer_name, si.is_return,
               si.net_total, si.total_taxes_and_charges, si.grand_total,
               {series_col} AS inv_series, {no_col} AS inv_no,
               IFNULL(p.paid, 0) AS paid,
               IFNULL(p.pay_lines, 0) AS pay_lines,
               p.last_payment_date,
               GREATEST(ABS(si.grand_total) - IFNULL(p.paid, 0), 0) AS remaining
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND {mt} AND {where}
        ORDER BY {order}
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)

    _attach_payment_lines(rows)
    return rows, total


def _attach_payment_lines(rows):
    """Gắn các dòng bảng kê đã trả cho từng hóa đơn của TRANG hiện tại.

    Chỉ chạy trên ≤20 hóa đơn nên rẻ; và kế toán cần thấy NGAY tiền của hóa đơn
    này về từ bảng kê nào, kỳ nào — nhất là hóa đơn được trả làm nhiều lần.
    """
    names = [r["name"] for r in rows if r.get("pay_lines")]
    if not names:
        for r in rows:
            r["payments"] = []
        return
    lines = frappe.db.sql("""
        SELECT l.name AS line, l.parent AS advice, l.sales_invoice, l.total_amount,
               l.match_method, l.match_confidence, l.source_row,
               IFNULL(l.payment_date, a.payment_date) AS payment_date,
               a.chain, a.advice_no, a.status
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind_payment)s
          AND l.sales_invoice IN %(names)s
        ORDER BY payment_date, l.idx
    """, {"names": tuple(names), "kind_payment": KIND_PAYMENT}, as_dict=True)
    grouped = defaultdict(list)
    for ln in lines:
        grouped[ln.sales_invoice].append(ln)
    for r in rows:
        r["payments"] = grouped.get(r["name"], [])


def _deduction_page(company, from_date, to_date, search, page_size, offset, chain=None):
    """Rổ 'chiết khấu' KHÔNG phải danh sách hóa đơn — nó là danh sách DÒNG khấu trừ.

    Chuỗi trừ lại chiết khấu, phí dịch vụ, hàng trả lại... phần lớn không gắn với
    hóa đơn nào. Ép chúng vào khung "hóa đơn" là bịa liên kết.
    """
    p = {"company": company, "fd": from_date, "td": to_date,
         "limit": page_size, "offset": offset}
    where = ["l.parenttype = 'MT Payment Advice'",
             "IFNULL(a.company, %(company)s) = %(company)s",
             "IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s"]
    kinds = []
    for i, k in enumerate(DEDUCTION_KINDS):
        p[f"k{i}"] = k
        kinds.append(f"%(k{i})s")
    where.append(f"l.row_kind IN ({', '.join(kinds)})")
    if chain:
        p["chain"] = chain
        where.append("a.chain = %(chain)s")
    if search:
        p["kw"] = f"%{search}%"
        where.append("(l.description LIKE %(kw)s OR l.doc_no LIKE %(kw)s"
                     " OR l.store_name LIKE %(kw)s OR l.inv_no LIKE %(kw)s)")
    w = " AND ".join(where)

    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE {w}
    """, p)[0][0]

    rows = frappe.db.sql(f"""
        SELECT l.name AS line, l.parent AS advice, l.row_kind, l.inv_series, l.inv_no,
               l.inv_date, l.store_code, l.store_name, l.doc_no, l.description,
               l.amount_before_vat, l.vat_amount, l.total_amount, l.source_row,
               IFNULL(l.payment_date, a.payment_date) AS payment_date,
               a.chain, a.advice_no, a.customer, a.status
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE {w}
        ORDER BY payment_date DESC, a.name DESC, l.idx
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return rows, total


@frappe.whitelist()
def get_invoices(bucket, company=None, from_date=None, to_date=None, search=None,
                 page=1, page_size=PAGE_SIZE, chain=None):
    """Một TRANG của một rổ. bucket ∈ chua_thanh_toan | da_thanh_toan | chiet_khau | tat_ca.

    Chia trang ở tầng SQL, 20 dòng/trang. Kênh MT một tháng có hàng nghìn hóa
    đơn — nạp hết rồi cắt ở trình duyệt là treo máy kế toán.
    """
    guard_mt()
    if bucket not in BUCKETS:
        frappe.throw(_("Rổ không hợp lệ: {0}").format(bucket))
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)
    page, page_size, offset = _page(page, page_size)
    search = norm_text(search)

    if bucket == "chiet_khau":
        source = "mt_line"
        rows, total = _deduction_page(company, from_date, to_date, search, page_size, offset, chain)
    else:
        source = "erp"
        rows, total = _invoice_page(company, from_date, to_date, _BUCKET_WHERE[bucket],
                                    search, page_size, offset)

    return {
        "bucket": bucket,
        "source": source,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "tolerance": PAID_TOLERANCE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Màn hình 3 — Công nợ theo từng chuỗi
# ═══════════════════════════════════════════════════════════════════════════

def _customer_chain_map():
    """Customer -> chuỗi siêu thị, LẤY TỪ bảng kê kế toán đã chốt.

    KHÔNG đoán chuỗi từ tên khách hàng. Hợp đồng đọc file (§I) ghi rõ: ánh xạ mã
    nhà cung cấp của chuỗi sang Customer của ERPNext CHƯA được xác minh. Nguồn
    đáng tin duy nhất là trường `customer` mà kế toán tự điền trên MT Payment
    Advice.

    Khách hàng bị gán cho HAI chuỗi khác nhau thì trả về None cho khách đó —
    dồn vào nhóm "Chưa gán chuỗi" để người xử lý, chứ không chọn bừa một chuỗi.
    """
    rows = frappe.db.sql("""
        SELECT customer, chain, COUNT(*) AS n
        FROM `tabMT Payment Advice`
        WHERE IFNULL(customer, '') != '' AND IFNULL(chain, '') != ''
        GROUP BY customer, chain
    """, as_dict=True)
    by_cus = defaultdict(set)
    for r in rows:
        by_cus[r.customer].add(r.chain)
    mapping, ambiguous = {}, []
    for cus, chains in by_cus.items():
        if len(chains) == 1:
            mapping[cus] = next(iter(chains))
        else:
            ambiguous.append({"customer": cus, "chains": sorted(chains)})
    return mapping, ambiguous


UNASSIGNED = "Chưa gán chuỗi"


@frappe.whitelist()
def get_chain_summary(company=None, from_date=None, to_date=None):
    """Công nợ theo từng chuỗi: đã xuất · đã thu · chiết khấu · phí · còn lại.

    Hai trục thời gian KHÁC NHAU, cố ý tách bạch:
      · "đã xuất / đã thu / còn lại" tính trên HÓA ĐƠN ghi sổ trong kỳ (tiền của
        các hóa đơn đó thu lúc nào cũng tính, kể cả kỳ sau) — đây là công nợ.
      · "nhận trong kỳ / chiết khấu / phí" tính trên BẢNG KÊ có ngày thanh toán
        trong kỳ — đây là dòng tiền.
    Gộp hai trục vào một cột là ra con số không có nghĩa kế toán nào.
    """
    guard_mt()
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)
    mapping, ambiguous = _customer_chain_map()

    p = {"company": company, "fd": from_date, "td": to_date,
         "tol": PAID_TOLERANCE, "kind_payment": KIND_PAYMENT}
    mt = _mt_clause(p)
    join = _paid_subquery()

    # Gom theo KHÁCH HÀNG rồi mới quy về chuỗi trong Python: SQL không biết ánh
    # xạ khách -> chuỗi (nó nằm trong bảng kê do kế toán chốt).
    by_customer = frappe.db.sql(f"""
        SELECT si.customer, si.customer_name,
               COUNT(*) AS cnt,
               IFNULL(SUM(CASE WHEN si.is_return = 0 THEN ABS(si.grand_total) ELSE 0 END), 0) AS invoiced,
               IFNULL(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) AS returns_amt,
               IFNULL(SUM(LEAST(IFNULL(p.paid, 0), ABS(si.grand_total))), 0) AS collected,
               IFNULL(SUM(CASE WHEN si.is_return = 0
                          THEN GREATEST(ABS(si.grand_total) - IFNULL(p.paid, 0), 0) ELSE 0 END), 0) AS outstanding,
               SUM(CASE WHEN si.is_return = 0
                        AND IFNULL(p.paid, 0) < ABS(si.grand_total) - %(tol)s THEN 1 ELSE 0 END) AS unpaid_count
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s AND {mt}
        GROUP BY si.customer, si.customer_name
    """, p, as_dict=True)

    # Dòng tiền theo bảng kê trong kỳ.
    by_advice = frappe.db.sql("""
        SELECT a.chain, l.row_kind, COUNT(*) AS n, IFNULL(SUM(ABS(l.total_amount)), 0) AS amt
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND IFNULL(a.company, %(company)s) = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
        GROUP BY a.chain, l.row_kind
    """, p, as_dict=True)

    def blank(chain):
        return {
            "chain": chain, "customers": [], "invoice_count": 0, "unpaid_count": 0,
            "invoiced": 0.0, "returns": 0.0, "collected": 0.0, "outstanding": 0.0,
            "received_in_period": 0.0, "discount": 0.0, "fee": 0.0, "other": 0.0,
            "advice_lines": 0,
        }

    out = {}
    for r in by_customer:
        chain = mapping.get(r.customer) or UNASSIGNED
        d = out.setdefault(chain, blank(chain))
        d["customers"].append({"customer": r.customer, "customer_name": r.customer_name,
                               "invoiced": flt(r.invoiced), "outstanding": flt(r.outstanding)})
        d["invoice_count"] += cint(r.cnt)
        d["unpaid_count"] += cint(r.unpaid_count)
        d["invoiced"] += flt(r.invoiced)
        d["returns"] += flt(r.returns_amt)
        d["collected"] += flt(r.collected)
        d["outstanding"] += flt(r.outstanding)

    kind_field = {KIND_PAYMENT: "received_in_period", KIND_DISCOUNT: "discount",
                  KIND_FEE: "fee", KIND_DEDUCT: "other", KIND_OTHER: "other"}
    for r in by_advice:
        d = out.setdefault(r.chain or UNASSIGNED, blank(r.chain or UNASSIGNED))
        field = kind_field.get(r.row_kind)
        if not field:
            # row_kind lạ (DocType đổi options mà quên sửa đây) — không nuốt tiền
            # vào hư không, dồn vào "other" để còn thấy.
            field = "other"
        d[field] += flt(r.amt)
        d["advice_lines"] += cint(r.n)

    chains = sorted(out.values(), key=lambda x: -x["outstanding"])
    totals = blank("TỔNG")
    for d in chains:
        for k in ("invoice_count", "unpaid_count", "advice_lines", "invoiced", "returns",
                  "collected", "outstanding", "received_in_period", "discount", "fee", "other"):
            totals[k] += d[k]
    totals["customers"] = []

    return {
        "from_date": from_date, "to_date": to_date, "company": company,
        "chains": chains,
        "totals": totals,
        # Khách hàng bị gán nhiều chuỗi — kế toán phải sửa, hệ thống không tự chọn.
        "ambiguous_customers": ambiguous,
        "note": _("'Đã xuất / còn lại' tính theo hóa đơn ghi sổ trong kỳ; "
                  "'nhận trong kỳ / chiết khấu / phí' tính theo ngày thanh toán của bảng kê."),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Đọc file bảng kê + khớp hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

def _check_size(content):
    """Chặn file khổng lồ TRƯỚC khi đưa vào openpyxl/xlrd.

    Tầng đọc file tự giải base64; ở đây chỉ giải để đo kích thước và bắt file
    rỗng sớm, vì một file hỏng vài chục MB đủ làm treo worker của kế toán.
    """
    raw = base64.b64decode((content or "").split(",")[-1])
    if not raw:
        frappe.throw(_("File rỗng"))
    if len(raw) > MAX_UPLOAD_BYTES:
        frappe.throw(_("File quá lớn ({0} MB). Tách bớt rồi tải lại.")
                     .format(round(len(raw) / 1024 / 1024, 1)))
    return len(raw)


def _advice_module():
    """Nạp tầng đọc file. Thiếu module thì BÁO RÕ chứ không nuốt lỗi."""
    try:
        from ketoan.api import mt_advice
    except ImportError:
        frappe.throw(_("Chưa có module đọc file bảng kê (ketoan.api.mt_advice)."))
    return mt_advice


def _read_file(content, chain):
    """Gọi tầng đọc file theo đúng hợp đồng ở đầu module.

    `chain` để trống thì tầng đọc TỰ NHẬN theo dấu hiệu trong file và THROW nếu
    không nhận ra — cố ý không đoán bừa: chọn nhầm parser vẫn ra một con số
    trông hợp lý nhưng đọc sai cột tiền.
    """
    mod = _advice_module()
    if chain:
        labels = getattr(mod, "CHAIN_LABEL", {}) or {}
        if chain not in labels and chain not in labels.values():
            frappe.throw(_("Chuỗi không hợp lệ: {0}").format(chain))
    fn = getattr(mod, "read_payment_advice", None)
    if not callable(fn):
        frappe.throw(_("Module ketoan.api.mt_advice thiếu hàm read_payment_advice(content, chain)."))
    parsed = fn(content, chain=chain or None) or {}
    if not parsed.get("chain"):
        frappe.throw(_("Tầng đọc file không trả về tên chuỗi — không ghi nhận."))
    return parsed


# Các trường có thể dùng để chia dòng về đúng LẦN THANH TOÁN của nó. Thứ tự này
# đã đối chiếu trên cả 5 file thật:
#   · Co.op         -> source_sheet (8 sheet = 8 kỳ)
#   · Central Retail-> doc_no       (2 Clearing Doc. trong 1 file)
#   · LOTTE         -> payment_date (2 Payment Date trong 1 file)
#   · WinCommerce, Emart -> chỉ 1 nhóm, không phải chia
_GROUP_FIELDS = ("source_sheet", "doc_no", "payment_date")


def _split_advices(parsed):
    """Chia `rows` về đúng từng nhóm trong `groups`. Trả [(group, rows)].

    Tầng đọc công bố nhóm (kèm `n_rows`) nhưng KHÔNG gắn số hiệu nhóm lên từng
    dòng, nên ở đây phải chia lại. Cách chia: thử lần lượt từng trường ứng viên,
    chỉ chấp nhận trường nào dựng lại ĐÚNG bộ khóa nhóm VÀ ĐÚNG số dòng của mỗi
    nhóm mà tầng đọc đã đếm.

    VÌ SAO khắt khe tới mức đó: chia sai là chia sai TIỀN — dồn 8 kỳ Co.op vào
    một phiếu, hoặc đẩy nhầm 21 dòng của Clearing Doc. này sang Clearing Doc.
    kia. Không trường nào dựng lại đúng thì DỪNG và bắt người xử lý, tuyệt đối
    không gộp tạm cho xong (gộp tạm chính là lỗi §J.3 của hợp đồng).
    """
    rows = parsed.get("rows") or []
    groups = parsed.get("groups") or []

    if len(groups) <= 1:
        g = dict(groups[0]) if groups else {}
        return [(g, rows)]

    keys = [cstr(g.get("key")) for g in groups]
    if len(set(keys)) == len(keys):
        for field in _GROUP_FIELDS:
            buckets = defaultdict(list)
            for r in rows:
                buckets[cstr(r.get(field) or "")].append(r)
            if set(buckets) != set(keys):
                continue
            if any(len(buckets[k]) != cint(g.get("n_rows")) for g, k in zip(groups, keys)):
                continue
            return [(dict(g), buckets[k]) for g, k in zip(groups, keys)]

    frappe.throw(_(
        "File có {0} lần thanh toán nhưng không chia được dòng về từng lần một cách "
        "chắc chắn. KHÔNG ghi nhận — gộp chung là cộng nhầm tiền của các kỳ vào nhau."
    ).format(len(groups)))


# ─────────────────────────────────────────────────────────────────────────
# Chỉ mục Sales Invoice để khớp
# ─────────────────────────────────────────────────────────────────────────

def _si_index(company, dates):
    """Chỉ mục hóa đơn bán ra để khớp với dòng bảng kê.

    Khoảng ngày nới rộng quanh dải ngày hóa đơn đọc được trong file: chuỗi trả
    tiền cho hóa đơn xuất từ nhiều tháng trước (Co.op trả 20/01/2026 cho hóa đơn
    19/02/2025), nên không được lọc theo tháng thanh toán.
    """
    if not (_has_si_field(SI_SERIES_FIELD) and _has_si_field(SI_NO_FIELD)):
        return None

    if dates:
        fd, td = add_days(min(dates), -120), add_days(max(dates), 120)
    else:
        # Không có ngày hóa đơn nào đọc được -> quét rộng 3 năm còn hơn không khớp.
        td = nowdate()
        fd = add_months(td, -36)

    p = {"company": company, "fd": cstr(fd), "td": cstr(td)}
    mt = _mt_clause(p)
    rows = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, si.grand_total, si.customer, si.customer_name,
               si.is_return, c.customer_group,
               si.{SI_SERIES_FIELD} AS inv_series, si.{SI_NO_FIELD} AS inv_no
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND si.{SI_NO_FIELD} > ''
        LIMIT 200000
    """, p, as_dict=True)

    # Chỉ mục 2 là danh sách hóa đơn của KHÁCH KÊNH MT theo số hóa đơn — dùng
    # cho Emart (không có ký hiệu). Thu hẹp về kênh MT để giảm khả năng vơ nhầm
    # hóa đơn của kênh NPP trùng số.
    mt_names = set(frappe.db.sql_list(f"""
        SELECT si.name FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s AND {mt}
    """, p))

    by_key, by_no = defaultdict(list), defaultdict(list)
    info = {}
    for r in rows:
        info[r.name] = r
        key = (norm_series_mt(r.inv_series), norm_inv_no(r.inv_no))
        if key[0] and key[1]:
            by_key[key].append(r.name)
        if key[1] and r.name in mt_names:
            by_no[key[1]].append(r.name)
    return {"by_key": by_key, "by_no": by_no, "info": info, "from": cstr(fd), "to": cstr(td)}


def _match_row(row, idx):
    """Khớp MỘT dòng thanh toán với Sales Invoice.

    Trả (sales_invoice, match_method, match_confidence, ghi_chú).

    Bốn nguyên tắc, mỗi cái đều đã có bằng chứng từ file thật:
      · Chỉ khớp dòng 'Thanh toán'. Dòng chiết khấu của Central Retail mang ký
        hiệu hóa đơn bán ra của chính mình mà KHÔNG phải trả cho hóa đơn đó.
      · Ký hiệu phải bỏ chữ số dạng hóa đơn ở đầu: 'C26THG' và '1C26THG' là MỘT
        (§E — đã gặp lẫn lộn ngay trong một file ở Central Retail, LOTTE, Co.op).
      · Nhiều ứng viên thì KHÔNG nối. Nối bừa là đánh dấu đã trả cho hóa đơn của
        khách khác.
      · Emart không cấp ký hiệu -> khớp bằng SỐ + NGÀY + TIỀN và LUÔN 'Cần review'.

    Cờ `needs_review` của tầng đọc file luôn HẠ độ tin cậy xuống 'Cần review',
    kể cả khi ký hiệu + số khớp đúng một hóa đơn: tầng đọc bật cờ đó khi CHÍNH
    NÓ không chắc đã hiểu đúng dòng (Emart không có ký hiệu, Co.op có dòng trả
    hàng không đọc ra ký hiệu, LOTTE có dòng NET OFF không gắn hóa đơn).
    """
    no = norm_inv_no(row.get("inv_no") or "")
    if not no:
        return None, "khong_co_so_hoa_don", "Không khớp", None
    if idx is None:
        return None, "site_thieu_field_so_hoa_don", "Không khớp", None

    series = norm_series_mt(row.get("inv_series") or "")

    if series:
        cands = idx["by_key"].get((series, no)) or []
        if len(cands) == 1:
            si = idx["info"][cands[0]]
            diff = abs(abs(flt(row.get("total_amount"))) - abs(flt(si.grand_total)))
            # Lệch tiền KHÔNG làm mất liên kết: chuỗi có quyền trả từng phần, và
            # tổng nhiều kỳ mới đủ. Chỉ ghi lại chênh lệch cho người xem.
            return cands[0], "ky_hieu_so", "Chắc chắn", (flt(diff) or None)
        if len(cands) > 1:
            return None, f"trung_{len(cands)}_hoa_don", "Cần review", None
        return None, "khong_tim_thay_ky_hieu_so", "Không khớp", None

    # Không có ký hiệu (Emart). Thu hẹp bằng ngày hóa đơn VÀ số tiền, và chỉ nhận
    # khi còn ĐÚNG MỘT ứng viên. Ba vế cùng khớp mà vẫn để 'Cần review' vì đây là
    # suy đoán, không phải khóa tự nhiên.
    cands = idx["by_no"].get(no) or []
    if not cands:
        return None, "khong_tim_thay_so", "Không khớp", None
    inv_date = row.get("inv_date")
    amount = abs(flt(row.get("total_amount")))
    narrowed = []
    for name in cands:
        si = idx["info"][name]
        if inv_date and cstr(si.posting_date) != cstr(inv_date):
            continue
        if amount and abs(abs(flt(si.grand_total)) - amount) > PAID_TOLERANCE:
            continue
        narrowed.append(name)
    if len(narrowed) == 1:
        return narrowed[0], "so_ngay_tien", "Cần review", None
    return None, f"khong_ky_hieu_{len(cands)}_ung_vien", "Cần review", None


# ─────────────────────────────────────────────────────────────────────────
# Kế hoạch nạp
# ─────────────────────────────────────────────────────────────────────────

def _map_rows(raw_rows, company, idx):
    """Dòng của tầng đọc file -> dòng của DocType, kèm kết quả khớp."""
    lines, dropped = [], 0
    for r in raw_rows or []:
        kind_raw = norm_text(r.get("row_kind"))
        if kind_raw in ROW_KIND_DROP:
            dropped += 1
            continue
        kind = ROW_KIND_MAP.get(kind_raw)
        unknown_kind = None
        if not kind:
            # Không vứt dòng có tiền chỉ vì không hiểu loại — dồn vào 'Khác' và
            # ghi lại nguyên văn để kế toán phân loại tay.
            kind, unknown_kind = KIND_OTHER, kind_raw

        line = {
            "row_kind": kind,
            "inv_series": norm_series(r.get("inv_series")),
            "inv_no": norm_text(r.get("inv_no")),
            "inv_no_norm": norm_inv_no(r.get("inv_no")),
            "inv_date": r.get("inv_date") or None,
            "store_code": norm_text(r.get("store_code")),
            "store_name": norm_text(r.get("store_name")),
            "doc_no": norm_text(r.get("doc_no")),
            "description": r.get("description") or None,
            # KHÔNG tự suy tiền trước thuế / tiền thuế khi file không có cột —
            # chia 1.1 hay 1.08 để ra số là bịa tiền.
            "amount_before_vat": flt(r.get("amount_before_vat")) if r.get("amount_before_vat") is not None else None,
            "vat_amount": flt(r.get("vat_amount")) if r.get("vat_amount") is not None else None,
            # `signed_amount` GIỮ NGUYÊN DẤU của file, `total_amount` của tầng đọc
            # là ĐỘ LỚN. Field DocType ghi rõ "giữ nguyên DẤU đọc được từ file" —
            # dấu là chốt đối chiếu với dòng tổng do chuỗi in ra. Lấy nhầm bản độ
            # lớn là mọi khoản chuỗi TRỪ LẠI biến thành khoản CỘNG THÊM.
            "total_amount": flt(r["signed_amount"] if r.get("signed_amount") is not None
                                else r.get("total_amount")),
            "payment_date": r.get("payment_date") or None,
            "source_row": cint(r.get("source_row")),
        }
        if unknown_kind:
            line["_unknown_kind"] = unknown_kind

        if kind == KIND_PAYMENT:
            si, method, conf, diff = _match_row(r, idx)
            if si and r.get("needs_review") and conf == "Chắc chắn":
                # Tầng đọc tự thấy dòng này đáng ngờ -> không được để 'Chắc chắn'
                # dù ký hiệu + số khớp đúng một hóa đơn.
                conf = "Cần review"
            line["sales_invoice"] = si
            line["match_method"] = method
            line["match_confidence"] = conf
            if si:
                info = idx["info"][si]
                line["_si_customer"] = info.customer
                line["_si_customer_name"] = info.customer_name
                line["_si_grand_total"] = flt(info.grand_total)
                line["_amount_diff"] = diff
        else:
            # Dòng khấu trừ KHÔNG được nối hóa đơn (child doctype cũng chặn).
            line["sales_invoice"] = None
            line["match_method"] = None
            line["match_confidence"] = None
        lines.append(line)
    return lines, dropped


def _totals(lines):
    t = {"total_payment": 0.0, "total_discount": 0.0, "total_fee": 0.0, "total_other": 0.0}
    field = {KIND_PAYMENT: "total_payment", KIND_DISCOUNT: "total_discount",
             KIND_FEE: "total_fee", KIND_DEDUCT: "total_other", KIND_OTHER: "total_other"}
    for ln in lines:
        t[field[ln["row_kind"]]] += flt(ln["total_amount"])
    return t


def _existing_advice(chain, payment_date, advice_no, file_name):
    """Bảng kê đã nạp rồi hay chưa — nạp hai lần là nhân đôi tiền đã thu."""
    filters = {"chain": chain, "payment_date": payment_date or None}
    if norm_text(advice_no):
        filters["advice_no"] = norm_text(advice_no)
    else:
        # Không có số chứng từ thì tên file là dấu hiệu nhận dạng còn lại.
        filters["file_name"] = norm_text(file_name)
    return frappe.db.get_value("MT Payment Advice", filters, "name")


def _declared(group, parsed, single, group_keys, parsed_key):
    """Số kiểm tra của MỘT kỳ, lấy theo thứ tự ưu tiên `group_keys`.

    Số tổng của CẢ FILE chỉ được dùng khi file có ĐÚNG MỘT kỳ. Dùng cho file
    nhiều kỳ là gán tổng của 8 kỳ Co.op cho từng kỳ — kỳ nào cũng "lệch" và cảnh
    báo lệch số kiểm tra trở thành vô nghĩa.
    """
    for k in group_keys:
        v = group.get(k)
        if v is not None:
            return flt(v)
    if single:
        v = (parsed.get("declared_totals") or {}).get(parsed_key)
        if v is not None:
            return flt(v)
    return None


# Sai số khi đối chiếu số kiểm tra. Tiền VND nguyên đồng nên về nguyên tắc phải
# lệch ĐÚNG 0; nới 3đ vì Co.op làm tròn chiết khấu ở cấp DÒNG và tiền thanh toán
# ở cấp NHÓM độc lập nhau (đã đo thật: lệch ±1đ ở 17/374 nhóm, ±3đ mỗi sheet).
DECLARED_TOLERANCE = 3.0


def _declared_relation(declared, totals):
    """Số kiểm tra do chuỗi in ra đang đo ĐẠI LƯỢNG NÀO của kỳ này?

    VÌ SAO phải hỏi câu này: mỗi chuỗi in một loại tổng khác nhau, và chúng
    KHÔNG cùng đơn vị đo với "tổng các dòng Thanh toán":
      · WinCommerce 'Tổng cộng'      = đúng tổng dòng thanh toán.
      · Emart 'phải trả tiền mua hàng' = đúng tổng dòng thanh toán.
      · Central Retail 'Result <doc>' = NET của cả kỳ (hàng − phí − chiết khấu
        − trả hàng). Đã kiểm trên file thật: −601.476.840 + 108.674.534 +
        27.240.347 + 5.119.605 = −460.442.354, khớp tuyệt đối.
      · Co.op 'Tổng Tiền'            = trị giá hàng + hàng trả lại (không trừ
        chiết khấu): 2.737.170.738 − 24.727.032 = 2.712.443.706, khớp tuyệt đối.

    Nhét thẳng con số đó vào `declared_total_payment` thì DocType so nó với tổng
    dòng thanh toán và kỳ nào cũng kêu lệch — kế toán quen tay bấm bỏ qua, tới
    lúc lệch THẬT thì không ai thấy nữa. Nên chỉ nhận vào field khi hai vế đo
    CÙNG một đại lượng; các quan hệ còn lại đưa ra màn xem trước và ghi chú.
    """
    if declared is None:
        return None, None
    tp = flt(totals["total_payment"])
    ck = flt(totals["total_discount"])
    fee = flt(totals["total_fee"])
    other = flt(totals["total_other"])
    for label, value in (
        ("total_payment", tp),
        ("total_payment+total_other", tp + other),
        ("net", tp + ck + fee + other),
    ):
        if abs(flt(declared) - value) <= DECLARED_TOLERANCE:
            return label, value
    # Không khớp đại lượng nào -> có thể là LỆCH THẬT (đọc sót dòng, sai cột
    # tiền). Phải để cảnh báo của DocType nổ.
    return None, None


def _plan(content, filename, chain, company):
    """Dựng kế hoạch nạp. KHÔNG ghi gì — dùng chung cho xem trước và nạp thật."""
    parsed = _read_file(content, chain)
    chain = parsed.get("chain")
    parts = _split_advices(parsed)
    if not parts or not any(rows for _g, rows in parts):
        frappe.throw(_("Không đọc được dòng tiền nào trong file"))

    # Dải ngày hóa đơn của CẢ file -> khoảng nạp chỉ mục Sales Invoice một lần
    # duy nhất, dùng chung cho mọi kỳ (Co.op 8 kỳ mà quét lại 8 lần là quá tốn).
    dates = []
    for r in parsed.get("rows") or []:
        if r.get("inv_date"):
            try:
                dates.append(getdate(r["inv_date"]))
            except Exception:
                pass
    idx = _si_index(company, dates)

    single = len(parts) == 1
    fallback_date = None
    pay_dates = parsed.get("payment_dates") or []
    if single and len(pay_dates) == 1:
        fallback_date = pay_dates[0]

    plan = []
    for group, rows in parts:
        lines, dropped = _map_rows(rows, company, idx)
        totals = _totals(lines)
        payment_date = group.get("payment_date") or fallback_date or None
        advice_no = norm_text(group.get("advice_no")
                              or (parsed.get("advice_no") if single else None))
        # Co.op in cả 'Tổng Tiền' (trị giá hàng) lẫn 'Tổng Tiền Thanh Toán' (thực
        # trả sau chiết khấu); `declared_gross` mới là số so được với các DÒNG.
        reported = _declared(group, parsed, single,
                             ("declared_gross", "declared_payment"), "total_payment")
        relation, matched = _declared_relation(reported, totals)
        plan.append({
            "chain": chain,
            "advice_no": advice_no,
            "payment_date": cstr(payment_date) if payment_date else None,
            "group_key": cstr(group.get("key")) or None,
            "source_sheet": rows[0].get("source_sheet") if rows else None,
            # Chỉ đưa vào field khi số của file đo ĐÚNG "tổng dòng thanh toán",
            # hoặc khi nó không khớp đại lượng nào (để cảnh báo của DocType nổ).
            "declared_total_payment": reported if relation in (None, "total_payment") else None,
            "declared_total_discount": _declared(group, parsed, single,
                                                 ("declared_discount",), "total_discount"),
            # Giữ nguyên số chuỗi in ra + đại lượng nó đo, để màn xem trước và
            # ghi chú nói được "khớp cái gì", không mất bằng chứng.
            "declared_reported": reported,
            "declared_relation": relation,
            "declared_matched_value": matched,
            "lines": lines,
            "dropped_rows": dropped,
            "totals": totals,
            "existing": _existing_advice(chain, payment_date, advice_no, filename),
        })
    return chain, plan, parsed


def _plan_hash(plan):
    """Vân tay của ĐÚNG kế hoạch người vừa xem.

    `commit_advice` dựng lại kế hoạch từ đầu, nên giữa lúc xem trước và lúc bấm
    nạp, một hóa đơn mới ghi sổ (hoặc một liên kết bị sửa) có thể làm kết quả
    khớp đổi mà không ai nhìn thấy. So vân tay thì lệch một dòng cũng dừng lại.
    """
    h = hashlib.sha1()
    for a in plan:
        h.update("A|{}|{}|{}|{}\n".format(
            a["chain"], a["advice_no"], a["payment_date"], a["group_key"] or "").encode())
        for ln in a["lines"]:
            h.update("L|{}|{}|{}|{}|{}|{}|{}\n".format(
                ln["source_row"], ln["row_kind"], ln["inv_series"], ln["inv_no"],
                ln["total_amount"], ln.get("sales_invoice") or "",
                ln.get("match_confidence") or "").encode())
    return h.hexdigest()


def _public_line(ln):
    """Bỏ khóa nội bộ (_...) trước khi trả ra client."""
    return {k: v for k, v in ln.items() if not k.startswith("_")}


def _summarize(a):
    """Tóm tắt một kỳ thanh toán để hiện ở màn xem trước."""
    lines = a["lines"]
    pay = [ln for ln in lines if ln["row_kind"] == KIND_PAYMENT]
    matched = [ln for ln in pay if ln.get("sales_invoice")]
    review = [ln for ln in lines if ln.get("match_confidence") == "Cần review"]
    unknown = [ln for ln in lines if ln.get("_unknown_kind")]

    # Một hóa đơn được nối bởi NHIỀU dòng trong CÙNG một kỳ: có thể đúng (chuỗi
    # tách dòng) nhưng cũng có thể là đọc trùng dòng -> phải hiện ra cho người xem.
    seen = defaultdict(int)
    for ln in matched:
        seen[ln["sales_invoice"]] += 1
    repeated = [{"sales_invoice": k, "lines": v} for k, v in seen.items() if v > 1]

    declared = a["declared_total_payment"]
    diff = None if declared is None else flt(declared) - flt(a["totals"]["total_payment"])

    return {
        "chain": a["chain"],
        "advice_no": a["advice_no"],
        "payment_date": a["payment_date"],
        "group_key": a["group_key"],
        "source_sheet": a["source_sheet"],
        "line_count": len(lines),
        "dropped_rows": a["dropped_rows"],
        "payment_lines": len(pay),
        "matched": len(matched),
        "unmatched": len(pay) - len(matched),
        "need_review": len(review),
        "unknown_kind": len(unknown),
        "repeated_invoices": repeated,
        "totals": a["totals"],
        "declared_total_payment": declared,
        "declared_total_discount": a["declared_total_discount"],
        # Số chuỗi in ra + đại lượng nó đo (total_payment / +ghi giảm / net).
        # 'declared_relation' = None nghĩa là KHÔNG khớp đại lượng nào — nghi
        # đọc sót dòng hoặc sai cột tiền, phải soi trước khi nạp.
        "declared_reported": a["declared_reported"],
        "declared_relation": a["declared_relation"],
        "declared_matched_value": a["declared_matched_value"],
        # Lệch số kiểm tra: cảnh báo, KHÔNG chặn. Co.op làm tròn ở cấp dòng và
        # cấp nhóm độc lập nhau nên lệch ±1..3đ là bình thường và đã đo trên file
        # thật; lệch lớn thì kế toán phải thấy ngay.
        "declared_diff": diff,
        "existing": a["existing"],
    }


@frappe.whitelist()
def preview_advice(content, filename=None, chain=None, company=None):
    """XEM TRƯỚC bảng kê: đọc file, khớp hóa đơn, KHÔNG ghi bất cứ thứ gì.

    Bắt buộc chạy trước `commit_advice` — trả về `plan_hash` mà commit đòi.
    """
    guard_mt()
    company = _company(company)
    _check_size(content)
    filename = norm_text(filename)
    chain, plan, parsed = _plan(content, filename, chain, company)

    advices = []
    for a in plan:
        s = _summarize(a)
        s["sample"] = [_public_line(ln) for ln in a["lines"][:20]]
        s["problems"] = [_public_line(ln) for ln in a["lines"]
                         if ln["row_kind"] == KIND_PAYMENT and not ln.get("sales_invoice")][:50]
        advices.append(s)

    grand = {k: sum(a["totals"][k] for a in plan)
             for k in ("total_payment", "total_discount", "total_fee", "total_other")}

    return {
        "chain": chain,
        "file_name": filename,
        "company": company,
        "advice_count": len(plan),
        "advices": advices,
        "grand_totals": grand,
        "warnings": parsed.get("warnings") or [],
        # Đối chiếu THẬT nằm ở đây: tầng đọc so tổng của nó với SỐ KIỂM TRA do
        # chính chuỗi in trong file. `reconciled=False` KHÔNG chặn nạp — nhưng
        # kế toán phải nhìn thấy trước khi bấm, và trạng thái 'Đã ghi nhận' vẫn
        # đòi người tự tick 'Đã đối chiếu khớp'.
        "checks": parsed.get("checks") or [],
        "reconciled": bool(parsed.get("reconciled")),
        "declared_totals": parsed.get("declared_totals") or {},
        "computed_totals": parsed.get("computed_totals") or {},
        # Có bản ghi cũ cùng chuỗi + ngày + số chứng từ: nạp đè là nhân đôi tiền.
        "duplicates": [a["existing"] for a in plan if a["existing"]],
        "plan_hash": _plan_hash(plan),
        "can_commit": is_chief(),
        "customer_required": _("Chọn Khách hàng của chuỗi — hệ thống KHÔNG tự đoán "
                               "ánh xạ mã nhà cung cấp sang Customer."),
    }


def _note_text(note, a, parsed):
    """Ghi chú của kế toán + dấu vết đối chiếu của tầng đọc file.

    Kết quả đối chiếu số kiểm tra được ĐÓNG luôn vào bản ghi: sáu tháng sau,
    người soi lại phải thấy được lúc nạp file có khớp hay không mà không cần
    tìm lại file gốc.
    """
    parts = [cstr(note).strip()] if note else []
    if not parsed.get("reconciled"):
        bad = [c.get("label") for c in (parsed.get("checks") or []) if not c.get("ok")]
        parts.append(_("[Tự động] Lúc nạp: CHƯA khớp số kiểm tra của file{0}.")
                     .format((": " + ", ".join(cstr(b) for b in bad)) if bad else ""))
    else:
        parts.append(_("[Tự động] Lúc nạp: khớp toàn bộ số kiểm tra in trong file."))
    if a.get("declared_reported") is not None:
        rel = {
            "total_payment": _("tổng dòng thanh toán"),
            "total_payment+total_other": _("tổng dòng thanh toán + ghi giảm"),
            "net": _("tổng thuần cả kỳ (hàng − chiết khấu − phí − ghi giảm)"),
        }.get(a.get("declared_relation"))
        parts.append(
            _("[Tự động] Số chuỗi in trong file: {0} — {1}.").format(
                flt(a["declared_reported"]),
                _("khớp {0}").format(rel) if rel
                else _("KHÔNG khớp đại lượng nào cộng được từ các dòng, cần soi lại")))
    pay = [ln for ln in a["lines"] if ln["row_kind"] == KIND_PAYMENT]
    miss = [ln for ln in pay if not ln.get("sales_invoice")]
    if miss:
        parts.append(_("[Tự động] {0}/{1} dòng thanh toán chưa nối được hóa đơn.")
                     .format(len(miss), len(pay)))
    return "\n".join(p for p in parts if p) or None


def _todo_for(doc, a):
    """Giao việc cho người, KHÔNG tự hạch toán.

    Ràng buộc của dự án: file nhập chỉ được GHI NHẬN + đánh dấu + tạo ToDo. Mọi
    Payment Entry / Journal Entry do con người lập. ToDo hỏng không được làm
    hỏng việc nạp bảng kê — nên nuốt lỗi và ghi log.
    """
    pay = [ln for ln in a["lines"] if ln["row_kind"] == KIND_PAYMENT]
    miss = [ln for ln in pay if not ln.get("sales_invoice")]
    review = [ln for ln in a["lines"] if ln.get("match_confidence") == "Cần review"]
    if not miss and not review:
        return
    try:
        frappe.get_doc({
            "doctype": "ToDo",
            "description": _(
                "Bảng kê {0} ({1}, ngày {2}): {3} dòng thanh toán chưa nối hóa đơn, "
                "{4} dòng cần xem lại. Đối chiếu rồi lập chứng từ hạch toán bằng tay — "
                "hệ thống KHÔNG tự tạo Payment Entry."
            ).format(doc.name, doc.chain, cstr(doc.payment_date), len(miss), len(review)),
            "reference_type": "MT Payment Advice",
            "reference_name": doc.name,
            "priority": "Medium",
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mt.commit_advice/todo %s" % doc.name)


@frappe.whitelist()
def commit_advice(content, filename=None, chain=None, expected_hash=None,
                  company=None, customer=None, note=None):
    """Nạp thật: tạo MT Payment Advice + dòng. MỖI KỲ THANH TOÁN MỘT BẢN GHI.

    Chỉ GHI NHẬN. KHÔNG tạo Payment Entry / Journal Entry — con người quyết định
    hạch toán sau khi soi bảng kê.
    """
    guard_manager()
    company = _company(company)
    _check_size(content)
    filename = norm_text(filename)
    chain, plan, parsed = _plan(content, filename, chain, company)

    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới nạp được"))
    if _plan_hash(plan) != expected_hash:
        frappe.throw(_(
            "Dữ liệu đã đổi kể từ lúc xem trước (hóa đơn khớp được đã thay đổi). "
            "Xem lại rồi nạp — không ghi gì cả."
        ))

    dup = [a for a in plan if a["existing"]]
    if dup:
        # Nạp lại cùng một bảng kê là cộng đôi tiền đã thu, và mọi hóa đơn của kỳ
        # đó lập tức trông như đã trả gấp đôi. Xóa bản cũ rồi nạp lại nếu muốn.
        frappe.throw(_("Bảng kê đã được nạp rồi: {0}. Xóa bản cũ trước nếu muốn nạp lại.")
                     .format(", ".join(a["existing"] for a in dup)))

    if customer and not frappe.db.exists("Customer", customer):
        frappe.throw(_("Không tìm thấy khách hàng {0}").format(customer))

    created = []
    for a in plan:
        doc = frappe.get_doc({
            "doctype": "MT Payment Advice",
            "chain": a["chain"],
            "customer": customer or None,
            "company": company,
            "advice_no": a["advice_no"],
            "payment_date": a["payment_date"],
            "file_name": filename,
            "status": "Nháp",
            "declared_total_payment": a["declared_total_payment"],
            "declared_total_discount": a["declared_total_discount"],
            "note": _note_text(note, a, parsed),
            # KHÔNG tự tick 'reconciled': DocType ghi rõ kế toán tự tick sau khi
            # soi lệch. Kết quả đối chiếu của tầng đọc chỉ đi vào ghi chú.
            "lines": [_public_line(ln) for ln in a["lines"]],
        })
        doc.insert()
        _todo_for(doc, a)
        created.append({
            "name": doc.name,
            "chain": doc.chain,
            "advice_no": doc.advice_no,
            "payment_date": cstr(doc.payment_date),
            "lines": len(doc.lines or []),
            "total_payment": flt(doc.total_payment),
            "total_discount": flt(doc.total_discount),
            "total_fee": flt(doc.total_fee),
            "total_other": flt(doc.total_other),
            "declared_total_payment": flt(doc.declared_total_payment),
        })
    frappe.db.commit()

    return {
        "created": created,
        "advice_count": len(created),
        "warnings": parsed.get("warnings") or [],
        "checks": parsed.get("checks") or [],
        "reconciled": bool(parsed.get("reconciled")),
        "message": _("Đã ghi nhận {0} bảng kê từ file {1}. "
                     "Hệ thống KHÔNG tự hạch toán — kiểm tra rồi lập chứng từ tay.")
        .format(len(created), filename),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Chốt tay liên kết dòng ↔ hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def relink_line(line, sales_invoice=None, note=None):
    """Kế toán chốt tay (hoặc gỡ) liên kết một dòng bảng kê với Sales Invoice.

    KHÔNG chặn khi hóa đơn đã có dòng khác trỏ tới: một hóa đơn được chuỗi trả
    làm nhiều lần là chuyện thường (Co.op tách 8 kỳ, LOTTE 2 ngày thanh toán).
    Chỉ BÁO LẠI các liên kết đang có để người chốt tự nhìn — chặn cứng ở đây sẽ
    khóa mất nghiệp vụ trả nhiều đợt.
    """
    guard_manager()
    row = frappe.db.get_value(
        "MT Payment Advice Line", line,
        ["name", "parent", "parenttype", "row_kind", "inv_series", "inv_no",
         "total_amount", "sales_invoice"], as_dict=True)
    if not row or row.parenttype != "MT Payment Advice":
        frappe.throw(_("Không tìm thấy dòng bảng kê {0}").format(line))

    if row.row_kind != KIND_PAYMENT:
        # BẪY TIỀN THẬT: dòng chiết khấu của Central Retail (Doc.Type=KS) mang ký
        # hiệu hóa đơn bán ra của chính mình mà KHÔNG phải thanh toán hóa đơn đó.
        # Nối là đánh dấu hóa đơn "đã thanh toán" trong khi thực tế chưa.
        frappe.throw(_("Dòng loại '{0}' không được nối hóa đơn. Chỉ dòng '{1}' mới được khớp.")
                     .format(row.row_kind or "", KIND_PAYMENT))

    others = []
    if sales_invoice:
        si = frappe.db.get_value("Sales Invoice", sales_invoice,
                                 ["name", "docstatus", "company", "customer_name", "grand_total"],
                                 as_dict=True)
        if not si:
            frappe.throw(_("Không tìm thấy hóa đơn {0}").format(sales_invoice))
        if si.docstatus != 1:
            frappe.throw(_("Hóa đơn {0} chưa ghi sổ (docstatus={1})").format(sales_invoice, si.docstatus))
        others = frappe.db.sql("""
            SELECT l.name AS line, l.parent AS advice, l.total_amount,
                   IFNULL(l.payment_date, a.payment_date) AS payment_date, a.chain
            FROM `tabMT Payment Advice Line` l
            INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
            WHERE l.parenttype = 'MT Payment Advice' AND l.sales_invoice = %(si)s
              AND l.name != %(line)s AND l.row_kind = %(kind_payment)s
        """, {"si": sales_invoice, "line": line, "kind_payment": KIND_PAYMENT}, as_dict=True)

    values = {
        "sales_invoice": sales_invoice or None,
        "match_method": "thu_cong" if sales_invoice else None,
        "match_confidence": "Chắc chắn" if sales_invoice else "Không khớp",
    }
    # Bảng kê KHÔNG phải chứng từ đã ghi sổ, nhưng vẫn dùng db_set: save() cả
    # document cha sẽ chạy lại validate và bắn msgprint lệch số kiểm tra mỗi lần
    # chốt một dòng — và không có gì trong tổng tiền thay đổi khi đổi liên kết.
    frappe.db.set_value("MT Payment Advice Line", line, values, update_modified=False)

    # Vết kiểm toán đi vào Comment của bảng kê, KHÔNG đè lên trường dữ liệu đọc
    # từ file (description là nguyên văn của chuỗi, đè là mất bằng chứng gốc).
    text = _("Chốt tay liên kết: {0} → {1}").format(
        row.sales_invoice or _("(chưa nối)"), sales_invoice or _("(gỡ liên kết)"))
    if note:
        text += "<br>" + frappe.utils.escape_html(cstr(note))
    try:
        frappe.get_doc("MT Payment Advice", row.parent).add_comment("Comment", text)
    except Exception:
        # Không ghi được vết thì vẫn giữ liên kết đã chốt, chỉ log lại.
        frappe.log_error(frappe.get_traceback(), "mt.relink_line/comment")

    frappe.db.commit()
    return {
        "line": line,
        "advice": row.parent,
        "previous": row.sales_invoice,
        **values,
        "other_lines_on_invoice": others,
    }
