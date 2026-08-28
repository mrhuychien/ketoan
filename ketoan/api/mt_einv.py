"""mt_einv — SOÁT HÓA ĐƠN MT BỊ BỎ SÓT SỐ HÓA ĐƠN ĐIỆN TỬ.

════════════════════════════════════════════════════════════════════════════
CÂU HỎI NÀY KHÁC CÂU HỎI CỦA THẺ "HAI CUỐN SỔ"
════════════════════════════════════════════════════════════════════════════

Thẻ hai cuốn sổ (`mt_debt`) hỏi: *trong phần CÒN NỢ, bao nhiêu chưa đòi được vì
chưa phát hành hóa đơn điện tử.* Nó chỉ nhìn hóa đơn chưa thu đủ tiền.

Màn này hỏi câu khác hẳn: *hóa đơn nào BỊ BỎ SÓT.* Một hóa đơn đã thu đủ tiền
mà vẫn trống ô số HĐĐT thì không còn là chuyện công nợ — nó là một lỗ hổng
chứng từ. Nên ở đây KHÔNG lọc theo tình trạng thanh toán.

⚠ HAI CON SỐ NÀY KHÔNG BAO GIỜ BẰNG NHAU, và đó là đúng. Đừng đem đối chiếu.

════════════════════════════════════════════════════════════════════════════
"BỎ SÓT" ≠ "CHƯA TỚI LƯỢT" — VÀ ĐÂY LÀ TOÀN BỘ GIÁ TRỊ CỦA MÀN NÀY
════════════════════════════════════════════════════════════════════════════

Danh sách phẳng "mọi hóa đơn trống ô số HĐĐT" gần như vô dụng: phần lớn trong
đó là hàng vừa giao tuần này, chưa tới lượt xuất. Trộn chung thì việc thật nằm
lẫn trong hàng trăm dòng bình thường, và kế toán bỏ luôn cả màn hình.

Kế toán xuất hóa đơn theo thứ tự thời gian. Nên có một MỐC tự nhiên:

    MỐC = hóa đơn MỚI NHẤT đã điền số HĐĐT

  · cũ hơn mốc mà vẫn trống  ->  BỎ SÓT. Đã đi qua nó rồi mà không xuất.
  · mới hơn mốc mà trống     ->  CHƯA TỚI LƯỢT. Bình thường.

Đó chính là "gần nhất tính từ hóa đơn được điền".

MỐC TÍNH THEO TỪNG CHUỖI, không tính chung toàn kênh. Mỗi chuỗi có nhịp xuất
riêng: lấy mốc chung thì chuỗi xuất chậm nhất sẽ bị chấm là bỏ sót toàn bộ, còn
chuỗi xuất nhanh thì không bao giờ lộ lỗ hổng nào.

════════════════════════════════════════════════════════════════════════════
MỐC LÀ MỘT PHỎNG ĐOÁN — NÊN NÓ ĐƯỢC IN RA, KHÔNG GIẤU
════════════════════════════════════════════════════════════════════════════

Giả định "xuất theo thứ tự thời gian" đúng với quy trình, nhưng không phải định
luật. Chuỗi nào xuất nhảy cóc thì mốc bị đẩy lên và một loạt hóa đơn bình
thường bị chấm nhầm là bỏ sót.

Vì vậy màn hình LUÔN nói rõ mốc đang là hóa đơn nào, ngày nào, và đếm CẢ HAI
phía. Người đọc nhìn mốc là biết ngay con số có tin được không — chứ không phải
nhận một danh sách "việc phải làm" mà không biết nó dựng từ đâu.

MODULE NÀY CHỈ ĐỌC. Không ghi, không tạo chứng từ, không sửa hóa đơn.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from ketoan.api._guard import guard_mt
from ketoan.api.mt import (
    SI_NO_FIELD,
    SI_SERIES_FIELD,
    _company,
    _customer_chain_map,
    _customer_in_clause,
    _mt_clause,
    _require_tables,
    chain_customers,
    einvoice_all_fields,
    einvoice_issued_expr,
)
from ketoan.install import MT_CHAINS

MAX_ROWS = 500


def _cols():
    """Cột số/ký hiệu hóa đơn điện tử, chỉ lấy ô SITE THẬT SỰ CÓ."""
    has_no = frappe.db.has_column("Sales Invoice", SI_NO_FIELD)
    has_ser = frappe.db.has_column("Sales Invoice", SI_SERIES_FIELD)
    return (
        f"si.{SI_NO_FIELD}" if has_no else "NULL",
        f"si.{SI_SERIES_FIELD}" if has_ser else "NULL",
    )


def _scan(company, chain=None):
    """Mọi hóa đơn BÁN của kênh MT, kèm cờ đã điền số HĐĐT chưa.

    KHÔNG lọc theo tình trạng thanh toán — xem chú thích đầu module.

    Phiếu trả hàng (`is_return = 1`) bị loại và ĐẾM RIÊNG: hóa đơn điều chỉnh /
    thay thế trên MISA đi theo luật khác (xem `misa_replace`), nên trộn vào đây
    là chấm nhầm cả một loại chứng từ. Loại thì phải nói ra, không loại câm.
    """
    einv = einvoice_issued_expr()
    if not einv:
        return None, []

    p = {"company": company}
    mt = _mt_clause(p)
    extra = ""
    if chain:
        extra = " AND " + _customer_in_clause(chain_customers(chain), p)

    no_col, ser_col = _cols()
    rows = frappe.db.sql(f"""
        SELECT si.name, si.customer, si.customer_name, si.posting_date,
               ABS(si.grand_total) AS grand_total,
               {no_col} AS inv_no, {ser_col} AS inv_series,
               {einv} AS has_einvoice
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND {mt} {extra}
        ORDER BY si.posting_date ASC, si.name ASC
    """, p, as_dict=True)
    return einv, rows


def _returns_missing(company, chain=None):
    """Phiếu trả hàng trống ô số HĐĐT — đếm riêng, không trộn vào danh sách."""
    einv = einvoice_issued_expr()
    if not einv:
        return {"count": 0, "amount": 0.0}
    p = {"company": company}
    mt = _mt_clause(p)
    extra = " AND " + _customer_in_clause(chain_customers(chain), p) if chain else ""
    r = frappe.db.sql(f"""
        SELECT COUNT(*) AS n, IFNULL(SUM(ABS(si.grand_total)), 0) AS amt
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 1
          AND NOT {einv}
          AND {mt} {extra}
    """, p, as_dict=True)
    return {"count": cint(r[0].n) if r else 0,
            "amount": flt(r[0].amt) if r else 0.0}


def _split(rows):
    """Chia hóa đơn trống số thành BỎ SÓT / CHƯA TỚI LƯỢT quanh MỐC.

    `rows` phải đã sắp theo (posting_date, name) TĂNG DẦN — đúng thứ tự mà
    `_scan` trả về. Mốc là phần tử ĐÃ ĐIỀN cuối cùng trong thứ tự đó.

    So sánh bằng CẢ (ngày, tên) chứ không riêng ngày: hai hóa đơn cùng ngày,
    một đã xuất một chưa, thì cái chưa xuất chỉ bị chấm bỏ sót nếu nó đứng
    TRƯỚC cái đã xuất trong đúng thứ tự đang dùng. Chỉ so ngày thì cả hai
    hướng đều sai — hoặc bỏ lọt, hoặc kêu oan.
    """
    frontier = None
    for r in rows:
        if cint(r.get("has_einvoice")):
            frontier = r

    missed, backlog = [], []
    if frontier is None:
        # Chưa hóa đơn nào có số -> KHÔNG có mốc, nên KHÔNG chấm bỏ sót cho ai.
        # Chấm cả rổ là biến "chưa bắt đầu" thành "sai sót hàng loạt".
        backlog = [r for r in rows if not cint(r.get("has_einvoice"))]
        return None, missed, backlog

    key = (cstr(frontier["posting_date"]), frontier["name"])
    for r in rows:
        if cint(r.get("has_einvoice")):
            continue
        (missed if (cstr(r["posting_date"]), r["name"]) < key else backlog).append(r)
    return frontier, missed, backlog


def _sum(rows):
    return {"count": len(rows), "amount": round(sum(flt(r["grand_total"]) for r in rows), 2)}


@frappe.whitelist()
def get_gaps(company=None, chain=None, page=1, page_size=50):
    """Hóa đơn MT bị bỏ sót số HĐĐT, tách khỏi phần chưa tới lượt.

    Không truyền `chain` -> soát toàn kênh, kèm bảng gộp theo từng chuỗi (MỐC
    của mỗi chuỗi tính riêng, xem chú thích đầu module).
    """
    guard_mt()
    _require_tables()
    company = _company(company)
    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))

    einv, rows = _scan(company, chain=chain)
    if not einv:
        return {
            "supported": False, "rows": [], "total": 0, "pages": 1, "page": 1,
            "chains": [], "frontier": None,
            "missed": {"count": 0, "amount": 0.0},
            "backlog": {"count": 0, "amount": 0.0},
            "returns_missing": {"count": 0, "amount": 0.0},
            # Tên ô lấy từ `mt.einvoice_all_fields()`, KHÔNG gõ lại ở đây: mỗi
            # lần gõ lại là một bản sao của luật chờ ngày lệch.
            "note": _(
                "Site chưa có ô số hóa đơn điện tử trên Sales Invoice ({0}) — "
                "chưa soát được. Chạy bench migrate rồi mở lại."
            ).format(" / ".join(einvoice_all_fields())),
        }

    # Gán chuỗi bằng ĐÚNG bản đồ mà mọi màn hình khác dùng. Đọc thẳng cột
    # `custom_mt_chain` là quy tắc hẹp hơn: khách đã có bảng kê mà chưa kịp khai
    # field sẽ rơi vào nhóm rỗng, tức lỗ hổng chứng từ của họ biến khỏi bảng.
    mapping, _amb = _customer_chain_map()
    for r in rows:
        r["chain"] = mapping.get(cstr(r.get("customer"))) or ""
        r["grand_total"] = flt(r["grand_total"])
        r["posting_date"] = cstr(r["posting_date"])

    frontier, missed, backlog = _split(rows) if chain else (None, [], [])

    # Toàn kênh: MỐC TÍNH RIÊNG TỪNG CHUỖI rồi mới gộp. Tính một mốc chung là
    # chuỗi xuất chậm nhất bị chấm bỏ sót toàn bộ, còn chuỗi nhanh không bao giờ
    # lộ lỗ hổng nào.
    by_chain = []
    if not chain:
        groups = {}
        for r in rows:
            groups.setdefault(r["chain"], []).append(r)
        for label in list(MT_CHAINS) + [""]:
            g = groups.get(label)
            if not g:
                continue
            f, m, b = _split(g)
            missed.extend(m)
            backlog.extend(b)
            by_chain.append({
                "chain": label,
                "frontier": _frontier_out(f),
                "missed": _sum(m),
                "backlog": _sum(b),
            })
        by_chain.sort(key=lambda x: -x["missed"]["amount"])

    # Bỏ sót LÂU NHẤT lên trước — đó là thứ tự đi soát.
    missed.sort(key=lambda r: (r["posting_date"], r["name"]))
    total = len(missed)
    start = (page - 1) * page_size
    return {
        "supported": True,
        "company": company,
        "chain": chain or "",
        "rows": missed[start:start + page_size],
        "total": total,
        "pages": max(1, -(-total // page_size)),
        "page": page,
        "page_size": page_size,
        "frontier": _frontier_out(frontier) if chain else None,
        "missed": _sum(missed),
        "backlog": _sum(backlog),
        "chains": by_chain,
        "returns_missing": _returns_missing(company, chain=chain),
        "heavy": total > MAX_ROWS,
    }


def _frontier_out(f):
    if not f:
        return None
    return {
        "name": f["name"],
        "posting_date": cstr(f["posting_date"]),
        "inv_no": cstr(f.get("inv_no") or ""),
        "inv_series": cstr(f.get("inv_series") or ""),
        "customer_name": cstr(f.get("customer_name") or f.get("customer") or ""),
    }
