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

════════════════════════════════════════════════════════════════════════════
"BỎ QUA" — VÀ RANH GIỚI CỦA NÓ
════════════════════════════════════════════════════════════════════════════

Danh sách này lấy MỌI hóa đơn trống ô số HĐĐT, nên trong đó luôn có một ít tờ
không bao giờ xử được. Chúng nằm mãi ở đó, và một danh sách việc-phải-làm không
bao giờ về 0 là danh sách người ta thôi nhìn. Vì vậy có `set_skip`.

⚠ BỎ QUA CHỈ ẨN DÒNG KHỎI DANH SÁCH NÀY. Không đụng công nợ, không đụng doanh
thu, không đụng sổ cái 131 — `mt_debt`, `mt_gl_bridge`, `mt.get_overview` đều
KHÔNG đọc cờ đó. Bỏ qua một hóa đơn KHÔNG làm nó hết là doanh thu, cũng không
làm nó hết nợ. Nếu có ngày một trong số đó đọc cờ này, nó thành đường tắt để
giấu công nợ — và đó là chuyện khác hẳn, phải bàn lại từ đầu.

Ba chốt đi kèm: lý do BẮT BUỘC · số tờ đã bỏ qua LUÔN được đếm và hiện ra ·
mở lại được bất cứ lúc nào (`list_skipped` là chỗ xem lại).

Ngoài `set_skip`, module CHỈ ĐỌC. Và `set_skip` ghi bằng
`db_set(..., update_modified=False)` — không `save()` trên chứng từ đã ghi sổ.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

from ketoan.api._guard import guard_manager, guard_mt
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


def _col(field):
    """`si.<field>` nếu site có ô đó, không thì `NULL`.

    `po_no` và `shipping_address_name` là ô CHUẨN của ERPNext, nhưng bản dựng
    site có thể đã gỡ hoặc đổi. Hỏi trước vẫn rẻ hơn một câu SQL gãy giữa màn
    hình đang chạy.
    """
    return f"si.{field}" if frappe.db.has_column("Sales Invoice", field) else "NULL"


def _store_join():
    """Nối ĐIỂM SIÊU THỊ qua `MT Store.address = si.shipping_address_name`.

    Vì sao không in thẳng `si.shipping_address`: ô đó là HTML đã dựng sẵn
    (`<br>` giữa các dòng), không phải một cái tên. Còn `shipping_address_name`
    là docname kiểu 'WinMart Bình Dương-Shipping' — đọc được nhưng không phải
    tên điểm mà kế toán dùng.

    `MT Store` chính là bảng điểm siêu thị của app, đã có `store_code` +
    `store_name` do kế toán seed. Nối vào đó là hiện đúng cái tên người ta gọi.
    Không khớp thì rơi về docname địa chỉ — KHÔNG bỏ trống, vì trống đọc thành
    "hóa đơn không có địa chỉ giao".
    """
    if not frappe.db.table_exists("MT Store"):
        return "", "NULL", "NULL"
    if not frappe.db.has_column("Sales Invoice", "shipping_address_name"):
        return "", "NULL", "NULL"
    return (
        " LEFT JOIN `tabMT Store` st ON st.address = si.shipping_address_name ",
        "st.store_code", "st.store_name",
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
    st_join, st_code, st_name = _store_join()
    # Hóa đơn ĐÃ BỎ QUA rơi khỏi CẢ HAI nhóm — kể cả nhóm "đã xuất", vì nó cũng
    # không còn tham gia việc dựng MỐC. Để nó lại làm mốc thì một tờ người ta
    # cố ý loại vẫn quyết định tờ nào bị chấm là bỏ sót.
    rows = frappe.db.sql(f"""
        SELECT si.name, si.customer, si.customer_name, si.posting_date,
               ABS(si.grand_total) AS grand_total,
               {no_col} AS inv_no, {ser_col} AS inv_series,
               {_col("po_no")} AS po_no,
               {_col("shipping_address_name")} AS ship_to,
               {st_code} AS store_code, {st_name} AS store_name,
               {einv} AS has_einvoice
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {st_join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND {mt} {extra}{_skip_clause()}
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
          AND {mt} {extra}{_skip_clause()}
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


# Ba tập LIỆT KÊ ĐƯỢC. Cùng một phép chia quanh MỐC, chỉ khác chỗ đứng nhìn.
SCOPES = ("bo_sot", "chua_toi_luot", "tat_ca")


def _apply_filters(rows, q=None, customer=None, store=None, from_date=None, to_date=None):
    """Cắt danh sách theo bộ lọc màn hình. Trả về (rows, có_lọc_gì_không).

    ⚠ CHẠY SAU `_split`, KHÔNG BAO GIỜ TRƯỚC.

    MỐC dựng từ hóa đơn ĐÃ có số. Lọc trước khi dựng mốc thì một bộ lọc ngày
    tháng sẽ ĐỔI LUÔN tờ nào bị chấm là "bỏ sót" — lọc từ 01/07 trở đi là mọi
    tờ đã xuất trước đó biến mất, mốc tụt về sau, và một loạt hóa đơn bình
    thường bỗng thành bỏ sót. Bộ lọc là chuyện của MÀN HÌNH; mốc là chuyện của
    DỮ LIỆU. Trộn hai thứ đó là để giao diện quyết định cái gì bất thường.
    """
    q = cstr(q or "").strip().lower()
    customer = cstr(customer or "").strip()
    store = cstr(store or "").strip()
    from_date = cstr(from_date or "").strip()[:10]
    to_date = cstr(to_date or "").strip()[:10]
    on = bool(q or customer or store or from_date or to_date)
    if not on:
        return rows, False

    def keep(r):
        if customer and cstr(r.get("customer")) != customer:
            return False
        if store and cstr(r.get("ship_to") or "") != store:
            return False
        d = cstr(r.get("posting_date") or "")[:10]
        if from_date and d < from_date:
            return False
        if to_date and d > to_date:
            return False
        if q:
            # Tìm trên MỌI thứ người ta cầm trong tay khi đi tra: số hóa đơn
            # ERPNext, số PO của siêu thị, tên pháp nhân, tên/mã điểm giao.
            hay = " ".join(cstr(r.get(k) or "") for k in
                           ("name", "po_no", "customer_name", "customer",
                            "store_name", "store_code", "ship_to")).lower()
            if q not in hay:
                return False
        return True

    return [r for r in rows if keep(r)], True


@frappe.whitelist()
def get_gaps(company=None, chain=None, page=1, page_size=50, scope="bo_sot",
             q=None, customer=None, store=None, from_date=None, to_date=None):
    """Hóa đơn MT chưa điền số HĐĐT, tách 'bỏ sót' khỏi 'chưa tới lượt'.

    Không truyền `chain` -> soát toàn kênh, kèm bảng gộp theo từng chuỗi (MỐC
    của mỗi chuỗi tính riêng, xem chú thích đầu module).

    `scope` chọn tập nào được LIỆT KÊ — cả ba đều được ĐẾM trong mọi trường hợp:

      · `bo_sot`        — cũ hơn mốc mà vẫn trống. Màn soát dùng cái này.
      · `chua_toi_luot` — mới hơn mốc. Đây chính là "CHỜ XUẤT HÓA ĐƠN": hàng đã
                          ghi sổ, chưa phát hành HĐĐT, và chưa có gì bất thường.
      · `tat_ca`        — cả hai.

    Vì sao có `chua_toi_luot`: bước "Chờ xuất hóa đơn" của WinCommerce cần đúng
    danh sách này, và nó có sẵn trong ERPNext — không phải nhập tay như
    `MT Win Pending` (thứ theo dõi đợt giao CHƯA có hóa đơn, một tập khác hẳn).
    """
    guard_mt()
    _require_tables()
    company = _company(company)
    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))
    scope = cstr(scope or "bo_sot").strip() or "bo_sot"
    if scope not in SCOPES:
        # Im lặng lấy mặc định là màn hình tưởng đang xem một tập, thật ra xem
        # tập khác — con số đọc ra sai mà không chỗ nào báo.
        frappe.throw(_("Phạm vi không hợp lệ: {0}").format(scope))

    einv, rows = _scan(company, chain=chain)
    if not einv:
        return {
            "supported": False, "rows": [], "total": 0, "pages": 1, "page": 1,
            "scope": scope,
            "chains": [], "frontier": None,
            "missed": {"count": 0, "amount": 0.0},
            "backlog": {"count": 0, "amount": 0.0},
            "returns_missing": {"count": 0, "amount": 0.0},
            "skipped": {"count": 0, "amount": 0.0, "supported": False},
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

    # Tập ĐEM LIỆT KÊ. Cả ba tập vẫn được đếm ở `missed`/`backlog` bên dưới,
    # nên đổi `scope` không bao giờ làm biến mất một con số tổng.
    listed = {"bo_sot": missed,
              "chua_toi_luot": backlog,
              "tat_ca": missed + backlog}[scope]

    # CŨ NHẤT LÊN TRƯỚC cho cả ba tập — đó là thứ tự làm việc: tờ đọng lâu nhất
    # là tờ phải xử trước, dù nó thuộc nhóm nào.
    listed = sorted(listed, key=lambda r: (r["posting_date"], r["name"]))
    # LỌC SAU CÙNG — sau khi mốc đã dựng xong. Xem `_apply_filters`.
    n_before = len(listed)
    listed, filtered = _apply_filters(listed, q=q, customer=customer, store=store,
                                      from_date=from_date, to_date=to_date)
    total = len(listed)
    start = (page - 1) * page_size
    return {
        "supported": True,
        "company": company,
        "chain": chain or "",
        "scope": scope,
        "rows": listed[start:start + page_size],
        # Đang lọc thì phải NÓI RA đang lọc và ĐANG GIẤU BAO NHIÊU. Một danh
        # sách bị lọc ngầm là con đường ngắn nhất để đọc ra một con số không
        # phải con số của nhóm đang chọn.
        "filtered": filtered,
        "total_unfiltered": n_before,
        "filters": {"q": cstr(q or ""), "customer": cstr(customer or ""),
                    "store": cstr(store or ""), "from_date": cstr(from_date or ""),
                    "to_date": cstr(to_date or "")},
        "total": total,
        "pages": max(1, -(-total // page_size)),
        "page": page,
        "page_size": page_size,
        "frontier": _frontier_out(frontier) if chain else None,
        "missed": _sum(missed),
        "backlog": _sum(backlog),
        "chains": by_chain,
        "returns_missing": _returns_missing(company, chain=chain),
        # ĐẾM SỐ ĐANG BỊ BỎ QUA và trả về, LUÔN LUÔN.
        #
        # Ẩn dòng mà không nói đã ẩn bao nhiêu là biến danh sách thành thứ không
        # kiểm chứng được: hôm nay 0 việc có thể vì xong hết, cũng có thể vì ai
        # đó bỏ qua sạch. Người đọc phải phân biệt được hai chuyện đó.
        "skipped": _count_skipped(company, chain),
        "heavy": total > MAX_ROWS,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BỎ QUA — loại một hóa đơn khỏi danh sách rà soát
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠ CHỈ ẨN KHỎI DANH SÁCH NÀY. Không đụng công nợ, không đụng doanh thu, không
# đụng sổ cái 131. Bỏ qua một hóa đơn KHÔNG làm nó hết là doanh thu và cũng
# không làm nó hết nợ — `mt_debt`, `mt_gl_bridge`, `mt.get_overview` đều KHÔNG
# đọc cờ này. Nếu có ngày một trong số đó đọc, cờ này thành đường tắt để giấu
# công nợ, và đó là chuyện khác hẳn.

SKIP_FIELD = "custom_mt_einv_skip"
SKIP_NOTE = "custom_mt_einv_skip_note"
SKIP_BY = "custom_mt_einv_skip_by"
SKIP_ON = "custom_mt_einv_skip_on"

MIN_NOTE = 5


def _skip_available():
    return frappe.db.has_column("Sales Invoice", SKIP_FIELD)


def _skip_clause():
    """Mệnh đề "chưa bị bỏ qua". Site chưa migrate -> không lọc gì."""
    if not _skip_available():
        return ""
    # `IFNULL` vì cột Check thêm vào bảng có sẵn dữ liệu là NULL, không phải 0.
    return f" AND IFNULL(si.{SKIP_FIELD}, 0) = 0"


@frappe.whitelist()
def set_skip(sales_invoice, skip=1, note=None, company=None):
    """Bỏ qua / mở lại một hóa đơn trong danh sách soát HĐĐT.

    Ghi bằng `db_set(..., update_modified=False)` — KHÔNG `save()`. Hóa đơn đã
    ghi sổ; `save()` sẽ chạy lại validate của Sales Invoice và có thể ném lỗi
    hoặc tính lại thứ không liên quan gì tới việc đánh dấu này.

    LÝ DO LÀ BẮT BUỘC khi bỏ qua. Sáu tháng sau không ai dựng lại được một
    quyết định không ghi lý do, và cũng không ai dám mở lại nó.
    """
    guard_manager()
    _require_tables()
    company = _company(company)

    if not _skip_available():
        frappe.throw(_(
            "Site chưa có ô '{0}' trên Sales Invoice — chạy `bench migrate` rồi thử lại."
        ).format(SKIP_FIELD))

    si = cstr(sales_invoice or "").strip()
    if not si or not frappe.db.exists("Sales Invoice", si):
        frappe.throw(_("Không có hóa đơn {0}").format(si or "(trống)"))

    row = frappe.db.get_value("Sales Invoice", si,
                              ["company", "docstatus", "is_return"], as_dict=True)
    if row.company != company:
        frappe.throw(_("Hóa đơn {0} thuộc công ty khác ({1})").format(si, row.company))
    if cint(row.docstatus) != 1:
        # Hóa đơn nháp/đã hủy KHÔNG có trong danh sách, nên bỏ qua nó là ghi một
        # dấu vô nghĩa lên chứng từ — và một dấu vô nghĩa vẫn là dấu người sau
        # phải đi giải thích.
        frappe.throw(_("Hóa đơn {0} chưa ghi sổ (hoặc đã hủy) — không nằm trong danh "
                       "sách soát, không cần bỏ qua.").format(si))

    on = cint(skip)
    note = cstr(note or "").strip()
    if on and len(note) < MIN_NOTE:
        frappe.throw(_(
            "Phải ghi LÝ DO bỏ qua (ít nhất {0} ký tự). Bỏ qua mà không nói vì sao thì "
            "sáu tháng sau không ai dựng lại được quyết định này, và cũng không ai dám "
            "mở lại nó.").format(MIN_NOTE))

    vals = {SKIP_FIELD: 1 if on else 0}
    if on:
        vals[SKIP_NOTE] = note
        vals[SKIP_BY] = frappe.session.user
        vals[SKIP_ON] = now_datetime()
    else:
        # MỞ LẠI thì XÓA SẠCH dấu vết bỏ qua.
        #
        # Giữ lại lý do cũ nghe có vẻ "lưu lịch sử", nhưng nó nằm trên chính ô
        # đang hiển thị trên form: hóa đơn không còn bị bỏ qua mà vẫn mang câu
        # "bỏ qua vì ..." là nói dối người đọc form. Lịch sử đã có Version log
        # của Frappe ghi đủ.
        vals[SKIP_NOTE] = None
        vals[SKIP_BY] = None
        vals[SKIP_ON] = None

    doc = frappe.get_doc("Sales Invoice", si)
    for k, v in vals.items():
        doc.db_set(k, v, update_modified=False)
    frappe.db.commit()

    return {
        "sales_invoice": si,
        "skip": bool(on),
        "note": note if on else "",
        "message": (_("Đã bỏ qua hóa đơn {0} khỏi danh sách soát HĐĐT. Công nợ và sổ cái "
                      "KHÔNG đổi.").format(si) if on
                    else _("Đã đưa hóa đơn {0} trở lại danh sách soát.").format(si)),
    }


@frappe.whitelist()
def filter_options(company=None, chain=None):
    """Pháp nhân + điểm giao ĐANG CÓ trong danh sách, để đổ vào ô lọc.

    Lấy từ CHÍNH tập hóa đơn đang soát chứ không liệt kê mọi Customer/Address
    của công ty: ô lọc bày ra một lựa chọn không có dòng nào là mời người dùng
    bấm rồi nhận màn hình trống và tưởng hỏng.
    """
    guard_mt()
    _require_tables()
    company = _company(company)

    _einv, rows = _scan(company, chain=chain)
    cus, sto = {}, {}
    for r in rows:
        c = cstr(r.get("customer") or "")
        if c:
            cus[c] = cstr(r.get("customer_name") or c)
        s_id = cstr(r.get("ship_to") or "")
        if s_id:
            name = cstr(r.get("store_name") or "") or s_id
            code = cstr(r.get("store_code") or "")
            sto[s_id] = ("%s — %s" % (code, name)) if code else name
    return {
        "customers": [{"value": k, "label": v} for k, v in
                      sorted(cus.items(), key=lambda x: x[1])],
        "stores": [{"value": k, "label": v} for k, v in
                   sorted(sto.items(), key=lambda x: x[1])],
    }


@frappe.whitelist()
def list_skipped(company=None, chain=None, page=1, page_size=50):
    """Các hóa đơn ĐANG bị bỏ qua — để còn xem lại và mở ra.

    Bỏ qua mà không có chỗ xem lại thì nó là cái thùng rác một chiều: hóa đơn
    biến mất khỏi mọi màn hình và không ai biết đường tìm.
    """
    guard_mt()
    _require_tables()
    company = _company(company)
    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))

    if not _skip_available():
        return {"supported": False, "rows": [], "total": 0, "pages": 1, "page": 1}

    p = {"company": company, "limit": page_size, "offset": (page - 1) * page_size}
    mt = _mt_clause(p)
    extra = " AND " + _customer_in_clause(chain_customers(chain), p) if chain else ""
    where = f"""si.docstatus = 1 AND si.company = %(company)s
                AND IFNULL(si.{SKIP_FIELD}, 0) = 1
                AND {mt} {extra}"""

    total = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {where}
    """, p)[0][0]
    rows = frappe.db.sql(f"""
        SELECT si.name, si.customer, si.customer_name, si.posting_date,
               ABS(si.grand_total) AS grand_total,
               si.{SKIP_NOTE} AS skip_note, si.{SKIP_BY} AS skip_by,
               si.{SKIP_ON} AS skip_on
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {where}
        ORDER BY si.{SKIP_ON} DESC, si.name DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    for r in rows:
        r["grand_total"] = flt(r["grand_total"])
        r["posting_date"] = cstr(r["posting_date"])
        r["skip_on"] = cstr(r["skip_on"] or "")
    return {
        "supported": True,
        "rows": rows,
        "total": cint(total),
        "pages": max(1, -(-cint(total) // page_size)),
        "page": page,
        "page_size": page_size,
        "amount": round(sum(flt(r["grand_total"]) for r in rows), 2),
    }


def _count_skipped(company, chain=None):
    """Bao nhiêu hóa đơn đang bị bỏ qua — để màn hình nói ra, không giấu."""
    if not _skip_available():
        return {"count": 0, "amount": 0.0, "supported": False}
    p = {"company": company}
    mt = _mt_clause(p)
    extra = " AND " + _customer_in_clause(chain_customers(chain), p) if chain else ""
    r = frappe.db.sql(f"""
        SELECT COUNT(*) AS n, IFNULL(SUM(ABS(si.grand_total)), 0) AS amt
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND IFNULL(si.{SKIP_FIELD}, 0) = 1
          AND {mt} {extra}
    """, p, as_dict=True)
    return {"count": cint(r[0].n) if r else 0,
            "amount": flt(r[0].amt) if r else 0.0, "supported": True}


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
