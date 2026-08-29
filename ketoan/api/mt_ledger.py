"""mt_ledger — SỔ THEO DÕI HÓA ĐƠN kênh MT: đúng cuốn Excel kế toán vẫn giữ.

════════════════════════════════════════════════════════════════════════════
CÔNG VIỆC THẬT CỦA KẾ TOÁN MT, TRƯỚC KHI CÓ PHẦN MỀM
════════════════════════════════════════════════════════════════════════════

Họ ngồi giữa BA cuốn sổ, và cả ngày là đi lại giữa chúng:

  ERPNext  — theo dõi HÀNG: đơn nào đã giao, giao cho điểm nào, PO nào.
  MISA     — theo dõi HÓA ĐƠN: tờ nào đã phát hành, tờ nào bị thay thế.
  Excel    — cuốn sổ THẬT SỰ LÀM VIỆC, mở suốt ngày.

Việc chính không phải là ba việc rời. Nó là MỘT việc: **căn hóa đơn MISA cho
khớp với hàng đã đi**, rồi theo dõi tờ hóa đơn đó tới lúc thu được tiền.

Cuốn Excel là nơi việc đó diễn ra, và nó có đúng một hình dạng: MỘT DÒNG MỖI
HÓA ĐƠN, các cột đi từ trái sang phải theo đời của tờ hóa đơn —

    số HĐ · ngày · hàng (chứng từ ERPNext, PO, điểm giao)
        -> tiền HĐ -> trả hàng -> phải thu
        -> đã nhận -> còn lại
        -> thuộc đợt thanh toán nào, đợt đó bị trừ những khoản gì

Ba câu hỏi cuốn sổ đó trả lời, và không màn hình nào của app trả lời trọn vẹn:

  1. Hóa đơn nào ĐÃ được thanh toán, tờ nào CHƯA?
  2. Khoản tiền về đó bị CẤN TRỪ những chiết khấu / phí nào?
  3. Tờ nào có HÓA ĐƠN XUẤT TRẢ, trả bao nhiêu?

Module này dựng lại đúng cuốn sổ đó — không phải một báo cáo mới, mà là chỗ
LÀM VIỆC quen thuộc, với dữ liệu đã có sẵn trong app.

════════════════════════════════════════════════════════════════════════════
CHIẾT KHẤU THUỘC VỀ ĐỢT THANH TOÁN, KHÔNG THUỘC VỀ HÓA ĐƠN
════════════════════════════════════════════════════════════════════════════

Đây là chỗ dễ dựng sai nhất, và dựng sai thì sai tiền.

Bảng kê của chuỗi là MỘT ĐỢT: nhiều dòng trả cho nhiều hóa đơn, rồi một loạt
dòng TRỪ LẠI (chiết khấu tháng, phí hỗ trợ, ghi giảm, NET OFF). Phần lớn dòng
trừ lại KHÔNG gắn hóa đơn nào — chúng là khoản của cả đợt.

    tiền về thực nhận = Σ dòng trả cho hóa đơn − Σ dòng trừ lại

Nên ở đây khoản trừ được bày ở tầng ĐỢT, kèm câu nói rõ nó thuộc về đợt. Chia
đều cho từng hóa đơn để mỗi dòng có một ô "chiết khấu" cho đẹp là BỊA: không
chứng từ nào nói tờ hóa đơn này chịu bao nhiêu, và con số bịa đó sẽ được đem đi
đối chiếu với chuỗi.

════════════════════════════════════════════════════════════════════════════
ĐÂY LÀ SỔ TRONG KỲ, KHÔNG PHẢI SỐ DƯ
════════════════════════════════════════════════════════════════════════════

Sổ này lọc theo NGÀY HÓA ĐƠN, và cố ý bày cả tờ đã thu đủ — vì câu hỏi số 1 là
"tờ nào đã thanh toán". Cột `Còn lại` cộng lại là công nợ CỦA CÁC TỜ TRONG KỲ
ĐANG XEM, không phải số dư công nợ. Số dư nằm ở màn Công nợ đến hạn, tính theo
`as_of` và không chặn dưới. Màn hình nói ra điều đó, không để ai tự suy.

Tập hóa đơn ở đây dùng ĐÚNG các mệnh đề của `mt_debt._fetch` — trừ điều kiện
"còn nợ". Nên lọc sang trạng thái `chua_thu` + `thu_mot_phan` là ra đúng tập
của màn công nợ, chỉ khác phạm vi ngày.

MODULE NÀY CHỈ ĐỌC.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from ketoan.api._guard import guard_mt
from ketoan.api.mt import (
    KIND_DEDUCT,
    KIND_PAYMENT,
    PAID_TOLERANCE,
    SI_NO_FIELD,
    SI_SERIES_FIELD,
    _company,
    _customer_in_clause,
    _debt_joins,
    _mt_clause,
    _range,
    _require_tables,
    chain_customers,
    einvoice_issued_expr,
    opening_open_clause,
)

PAGE_SIZE = 50
MAX_PAGE = 200

# Trạng thái của MỘT dòng sổ — đúng thứ tự đời của tờ hóa đơn.
#
# Khóa ASCII, nhãn tiếng Việt. Đây là cột kế toán liếc mắt vào đầu tiên, nên nó
# phải trả lời được "tờ này đang ở đâu" mà không cần đọc bốn cột số.
ST_NO_EINV = "chua_xuat_hddt"
ST_UNPAID = "chua_thu"
ST_PARTIAL = "thu_mot_phan"
ST_PAID = "da_thu_du"

STATUS_LABEL = {
    ST_NO_EINV: "Chưa xuất HĐĐT",
    ST_UNPAID: "Chưa thu",
    ST_PARTIAL: "Thu một phần",
    ST_PAID: "Đã thu đủ",
}
STATUSES = tuple(STATUS_LABEL)


def _status(r, einv_known):
    """Trạng thái của một dòng sổ.

    "Chưa xuất HĐĐT" đứng TRƯỚC mọi trạng thái tiền: siêu thị không trả cho tờ
    chưa phát hành, nên nói "chưa thu" ở đó là đổ lỗi nhầm chỗ — việc phải làm
    là xuất hóa đơn, không phải đi đòi.

    Site chưa có ô số HĐĐT thì KHÔNG dùng trạng thái này: không biết ≠ chưa xuất.
    """
    if einv_known and not cint(r.get("has_einvoice")):
        return ST_NO_EINV
    due = flt(r.get("net_due"))
    paid = flt(r.get("paid_net"))
    if paid <= PAID_TOLERANCE:
        return ST_UNPAID
    if paid >= due - PAID_TOLERANCE:
        return ST_PAID
    return ST_PARTIAL


def _rows(company, from_date, to_date, chain=None, customer=None):
    """Mọi hóa đơn BÁN của kênh MT trong kỳ, kèm tiền đã trả và hàng trả lại.

    Dùng ĐÚNG `_debt_joins` + `opening_open_clause` của `mt_debt` — trừ điều
    kiện "còn nợ", vì sổ này cố ý bày cả tờ đã thu đủ. Lệch một mệnh đề là sổ
    và màn công nợ nói về hai tập hóa đơn khác nhau.
    """
    einv = einvoice_issued_expr()
    p = {"company": company, "fd": getdate(from_date), "td": getdate(to_date),
         "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}
    mt = _mt_clause(p)
    join = _debt_joins()
    opening = opening_open_clause(p, company)

    extra = ""
    if chain:
        extra += " AND " + _customer_in_clause(chain_customers(chain), p)
    if customer:
        p["cus"] = customer
        extra += " AND si.customer = %(cus)s"

    def col(f):
        return f"si.{f}" if frappe.db.has_column("Sales Invoice", f) else "NULL"

    return frappe.db.sql(f"""
        SELECT si.name, si.customer, si.customer_name, si.posting_date, si.due_date,
               ABS(si.grand_total) AS grand_total,
               {col(SI_SERIES_FIELD)} AS misa_series,
               {col(SI_NO_FIELD)} AS misa_no,
               {col("custom_misa_status")} AS misa_status,
               {col("po_no")} AS po_no,
               {col("shipping_address_name")} AS ship_to,
               IFNULL(rt.returned, 0) AS returned,
               IFNULL(rt.n_returns, 0) AS n_returns,
               IFNULL(p.paid, 0) AS paid,
               IFNULL(p.clawed_back, 0) AS clawed_back,
               IFNULL(p.paid_review, 0) AS paid_review,
               IFNULL(p.pay_lines, 0) AS pay_lines,
               {einv or "NULL"} AS has_einvoice
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND {opening}
          AND {mt} {extra}
        ORDER BY si.posting_date DESC, si.name DESC
    """, p, as_dict=True)


def _attach_discount_tick(rows):
    """Tick CHIẾT KHẤU: tờ này đã được xử chiết khấu chưa.

    ════════════════════════════════════════════════════════════════════════
    TICK, KHÔNG PHẢI SỐ TIỀN — VÀ ĐÓ LÀ CHỦ Ý
    ════════════════════════════════════════════════════════════════════════

    Chiết khấu/phí bị trừ trên TỔNG ĐỢT thanh toán, không trên từng hóa đơn.
    Cho mỗi dòng một ô "chiết khấu" bằng tiền là phải chia đợt cho các tờ, mà
    không chứng từ nào nói tờ này chịu bao nhiêu — con số bịa đó rồi sẽ được đem
    đi đối chiếu với chuỗi.

    Cái kế toán THẬT SỰ cần theo dõi là câu hỏi CÓ/KHÔNG: *tờ này đã đi qua
    khâu chiết khấu chưa*. Ba trạng thái, ba nghĩa khác nhau:

      · `co`      — có khoản trừ, VÀ khoản đó gắn ĐÍCH DANH tờ này.
      · `theo_dot`— đợt đã trả tờ này CÓ khoản trừ, nhưng của cả đợt.
      · `khong`   — đợt đã trả tờ này KHÔNG có khoản trừ nào.
      · `chua`    — chưa đợt nào trả tờ này, nên CHƯA BIẾT. Không phải "không".

    Tách `chua` khỏi `khong` là chốt chặn: gộp lại thì hóa đơn chưa thanh toán
    hiện dấu "không có chiết khấu", và kế toán đọc thành đã kiểm rồi.
    """
    names = [r["name"] for r in rows]
    for r in rows:
        r["discount"] = "chua"
        r["discount_note"] = ""
    if not names:
        return

    # 1. Khoản trừ gắn ĐÍCH DANH hóa đơn này.
    direct = frappe.db.sql("""
        SELECT l.sales_invoice, COUNT(*) AS n
        FROM `tabMT Payment Advice Line` l
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind != %(kind)s
          AND l.sales_invoice IN %(names)s
        GROUP BY l.sales_invoice
    """, {"names": tuple(names), "kind": KIND_PAYMENT}, as_dict=True)
    direct_set = {d.sales_invoice for d in direct}

    # 2. Đợt đã trả tờ này có khoản trừ nào không.
    #
    # Hỏi ở tầng ĐỢT vì đó đúng là tầng khoản trừ tồn tại. Kết quả hiện thành
    # "theo đợt" chứ không thành một con số của tờ.
    per_advice = {}
    advices = set()
    for r in rows:
        for a in r.get("advices") or []:
            advices.add(a["advice"])
    if advices:
        got = frappe.db.sql("""
            SELECT l.parent AS advice, COUNT(*) AS n
            FROM `tabMT Payment Advice Line` l
            WHERE l.parenttype = 'MT Payment Advice'
              AND l.parent IN %(advices)s AND l.row_kind != %(kind)s
            GROUP BY l.parent
        """, {"advices": tuple(advices), "kind": KIND_PAYMENT}, as_dict=True)
        per_advice = {g.advice: cint(g.n) for g in got}

    for r in rows:
        adv = r.get("advices") or []
        if r["name"] in direct_set:
            r["discount"] = "co"
            r["discount_note"] = _("Có khoản trừ gắn đích danh hóa đơn này")
        elif not adv:
            r["discount"] = "chua"
            r["discount_note"] = _("Chưa đợt thanh toán nào trả tờ này — chưa biết")
        elif any(per_advice.get(a["advice"]) for a in adv):
            r["discount"] = "theo_dot"
            r["discount_note"] = _(
                "Đợt thanh toán trả tờ này CÓ khoản trừ, nhưng khoản đó của cả đợt — "
                "không chứng từ nào nói riêng tờ này chịu bao nhiêu")
        else:
            r["discount"] = "khong"
            r["discount_note"] = _("Đợt thanh toán trả tờ này không có khoản trừ nào")


def _attach_returns(rows):
    """Phiếu trả hàng của từng tờ, KÈM chứng từ MISA đi cùng nó.

    ════════════════════════════════════════════════════════════════════════
    HAI LOẠI TRẢ HÀNG, HAI ĐƯỜNG CHỨNG TỪ — ĐỪNG GỘP
    ════════════════════════════════════════════════════════════════════════

    a) HÀNG MÓP TRONG VẬN CHUYỂN. Siêu thị chỉ nhận theo thực tế, tức hóa đơn
       GỐC ghi sai số lượng ngay từ đầu. Chứng từ đúng: **hóa đơn thay thế**
       trên MISA (`custom_misa_relation = 'Hóa đơn thay thế'`), tờ gốc thành
       'Bị thay thế'.

    b) HÀNG DATE / THỜI VỤ TRẢ LẠI. Siêu thị đã nhận, đã bày bán, rồi trả về.
       Đây là giao dịch MỚI, không phải sửa tờ cũ. Chứng từ đúng: siêu thị xuất
       hóa đơn trả cho mình, HOẶC mình xuất **hóa đơn điều chỉnh giảm**.

    App không đoán được cái nào là cái nào — chỉ NGƯỜI biết hàng móp hay hàng
    date. Nên ở đây chỉ ĐỌC RA chứng từ MISA đang gắn với phiếu trả, và chỉ ra
    tờ nào CHƯA có chứng từ nào. Đó là việc còn thiếu, và nó thường bị quên đúng
    ở đây: phiếu trả đã ghi trên ERPNext, hóa đơn phía MISA thì chưa ai làm.
    """
    names = [r["name"] for r in rows]
    for r in rows:
        r["returns"] = []
        r["returns_no_misa"] = 0
    if not names:
        return

    def col(f):
        return f"r.{f}" if frappe.db.has_column("Sales Invoice", f) else "NULL"

    rets = frappe.db.sql(f"""
        SELECT r.return_against AS si, r.name, r.posting_date,
               ABS(r.grand_total) AS amount,
               {col("custom_misa_relation")} AS misa_relation,
               {col(SI_NO_FIELD)} AS misa_no,
               {col("custom_misa_status")} AS misa_status
        FROM `tabSales Invoice` r
        WHERE r.docstatus = 1 AND r.return_against IN %(names)s
        ORDER BY r.posting_date, r.name
    """, {"names": tuple(names)}, as_dict=True)

    by_si = defaultdict(list)
    for x in rets:
        by_si[x.si].append({
            "name": x.name,
            "posting_date": cstr(x.posting_date),
            "amount": flt(x.amount),
            "misa_relation": cstr(x.misa_relation or ""),
            "misa_no": cstr(x.misa_no or ""),
            "misa_status": cstr(x.misa_status or ""),
            # CHƯA có chứng từ MISA nào đi cùng phiếu trả này.
            "misa_missing": not (cstr(x.misa_no or "") or cstr(x.misa_relation or "")),
        })
    for r in rows:
        r["returns"] = by_si.get(r["name"], [])
        r["returns_no_misa"] = sum(1 for x in r["returns"] if x["misa_missing"])


def _attach_advices(rows):
    """Gắn ĐỢT THANH TOÁN đã trả cho từng hóa đơn của TRANG hiện tại.

    Cột "thuộc đợt nào" là cột kế toán dò ngược nhiều nhất: chuỗi gọi hỏi về
    một hóa đơn thì việc đầu tiên là mở đúng bảng kê đã trả nó.
    """
    names = [r["name"] for r in rows if cint(r.get("pay_lines"))]
    for r in rows:
        r["advices"] = []
    if not names:
        return
    lines = frappe.db.sql("""
        SELECT l.sales_invoice, l.parent AS advice, l.total_amount,
               IFNULL(l.payment_date, a.payment_date) AS payment_date,
               a.advice_no, a.status, a.je_state
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind)s
          AND l.sales_invoice IN %(names)s
        ORDER BY payment_date, l.idx
    """, {"names": tuple(names), "kind": KIND_PAYMENT}, as_dict=True)
    by_si = defaultdict(list)
    for ln in lines:
        by_si[ln.sales_invoice].append({
            "advice": ln.advice,
            "advice_no": cstr(ln.advice_no or ""),
            "payment_date": cstr(ln.payment_date or ""),
            "amount": flt(ln.total_amount),
            "status": cstr(ln.status or ""),
            "je_state": cstr(ln.je_state or ""),
        })
    for r in rows:
        r["advices"] = by_si.get(r["name"], [])


@frappe.whitelist()
def get_ledger(company=None, from_date=None, to_date=None, chain=None, customer=None,
               status=None, q=None, page=1, page_size=PAGE_SIZE):
    """Sổ theo dõi hóa đơn: MỘT DÒNG MỖI HÓA ĐƠN, đủ đời của nó."""
    guard_mt()
    _require_tables()
    company = _company(company)
    from_date, to_date = _range(from_date, to_date)
    page = max(1, cint(page))
    page_size = min(MAX_PAGE, max(10, cint(page_size) or PAGE_SIZE))

    status = cstr(status or "").strip() or None
    if status and status not in STATUSES:
        frappe.throw(_("Trạng thái không hợp lệ: {0}").format(status))

    rows = _rows(company, from_date, to_date, chain=chain, customer=customer)
    einv_known = einvoice_issued_expr() is not None

    out = []
    for r in rows:
        d = dict(r)
        d["grand_total"] = flt(r["grand_total"])
        d["returned"] = flt(r["returned"])
        # PHẢI THU của tờ này = tiền hóa đơn TRỪ hàng đã trả lại. Đây là con số
        # kế toán đem đi đòi, không phải `grand_total`.
        d["net_due"] = round(d["grand_total"] - d["returned"], 2)
        d["paid_net"] = round(flt(r["paid"]) - flt(r["clawed_back"]), 2)
        d["remaining"] = round(max(d["net_due"] - d["paid_net"], 0.0), 2)
        d["paid_review"] = flt(r["paid_review"])
        d["posting_date"] = cstr(r["posting_date"])
        d["status"] = _status(d, einv_known)
        d["status_label"] = STATUS_LABEL[d["status"]]
        out.append(d)

    if status:
        out = [r for r in out if r["status"] == status]

    q = cstr(q or "").strip().lower()
    if q:
        def hay(r):
            return " ".join(cstr(r.get(k) or "") for k in
                            ("name", "misa_no", "misa_series", "po_no",
                             "customer_name", "customer", "ship_to")).lower()
        out = [r for r in out if q in hay(r)]

    # Tổng của CẢ bộ lọc, không phải của trang đang xem — nếu không thì lật
    # trang là mọi con số tổng nhảy theo và không cộng ra cái gì.
    totals = {
        "count": len(out),
        "grand_total": round(sum(r["grand_total"] for r in out), 2),
        "returned": round(sum(r["returned"] for r in out), 2),
        "net_due": round(sum(r["net_due"] for r in out), 2),
        "paid": round(sum(r["paid_net"] for r in out), 2),
        "remaining": round(sum(r["remaining"] for r in out), 2),
    }
    by_status = {k: {"count": 0, "amount": 0.0} for k in STATUSES}
    n_returned = sum(1 for r in out if r["returned"])
    for r in out:
        b = by_status[r["status"]]
        b["count"] += 1
        b["amount"] = round(b["amount"] + r["remaining"], 2)

    total = len(out)
    start = (page - 1) * page_size
    page_rows = out[start:start + page_size]
    _attach_advices(page_rows)
    # THỨ TỰ QUAN TRỌNG: tick chiết khấu đọc `advices`, nên phải chạy SAU.
    _attach_discount_tick(page_rows)
    _attach_returns(page_rows)

    return {
        "rows": page_rows,
        "total": total,
        "pages": max(1, -(-total // page_size)),
        "page": page,
        "page_size": page_size,
        "totals": totals,
        "by_status": by_status,
        "n_returned": n_returned,
        "discount_label": {
            "co": "Có (đích danh)", "theo_dot": "Có (theo đợt)",
            "khong": "Không", "chua": "Chưa biết"},
        "status_label": dict(STATUS_LABEL),
        "einv_known": einv_known,
        "from_date": cstr(from_date),
        "to_date": cstr(to_date),
        "chain": cstr(chain or ""),
        "customer": cstr(customer or ""),
        "status": status or "",
        "q": cstr(q or ""),
        "note": _(
            "Sổ này lọc theo NGÀY HÓA ĐƠN và bày cả tờ đã thu đủ. Cột 'Còn lại' cộng lại "
            "là công nợ CỦA CÁC TỜ TRONG KỲ ĐANG XEM — không phải số dư công nợ. Số dư "
            "nằm ở màn Công nợ đến hạn."),
    }


@frappe.whitelist()
def get_trace(sales_invoice, company=None):
    """Đời của MỘT tờ hóa đơn: tiền về từ đâu, đợt đó bị trừ gì, trả hàng nào.

    Đây là cái kế toán mở ra khi chuỗi gọi hỏi về một hóa đơn.
    """
    guard_mt()
    _require_tables()
    company = _company(company)

    si = cstr(sales_invoice or "").strip()
    if not si or not frappe.db.exists("Sales Invoice", si):
        frappe.throw(_("Không có hóa đơn {0}").format(si or "(trống)"))
    if frappe.db.get_value("Sales Invoice", si, "company") != company:
        frappe.throw(_("Hóa đơn {0} thuộc công ty khác").format(si))

    pays = frappe.db.sql("""
        SELECT l.name AS line, l.parent AS advice, l.total_amount, l.source_row,
               l.match_method, l.match_confidence,
               IFNULL(l.payment_date, a.payment_date) AS payment_date,
               a.advice_no, a.chain, a.status, a.je_state
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind)s AND l.sales_invoice = %(si)s
        ORDER BY payment_date, l.idx
    """, {"si": si, "kind": KIND_PAYMENT}, as_dict=True)

    # KHOẢN TRỪ CỦA CHÍNH CÁC ĐỢT ĐÃ TRẢ TỜ NÀY.
    #
    # ⚠ Chúng thuộc về ĐỢT, không thuộc về tờ hóa đơn này. Bày ra vì đó đúng là
    # câu hỏi kế toán có ("tiền về đợt này bị trừ những gì"), nhưng KHÔNG chia
    # cho từng hóa đơn: không chứng từ nào nói tờ này chịu bao nhiêu.
    advices = sorted({p.advice for p in pays})
    deducts = []
    if advices:
        deducts = frappe.db.sql("""
            SELECT l.parent AS advice, l.row_kind, l.description, l.doc_no,
                   l.total_amount, l.sales_invoice, a.advice_no
            FROM `tabMT Payment Advice Line` l
            INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
            WHERE l.parenttype = 'MT Payment Advice'
              AND l.parent IN %(advices)s
              AND l.row_kind != %(kind)s
            ORDER BY l.parent, l.idx
        """, {"advices": tuple(advices), "kind": KIND_PAYMENT}, as_dict=True)

    def rcol(f):
        return f"r.{f}" if frappe.db.has_column("Sales Invoice", f) else "NULL"

    rets = frappe.db.sql(f"""
        SELECT r.name, r.posting_date, ABS(r.grand_total) AS amount,
               {rcol("custom_misa_relation")} AS misa_relation,
               {rcol(SI_NO_FIELD)} AS misa_no,
               {rcol(SI_SERIES_FIELD)} AS misa_series,
               {rcol("custom_misa_status")} AS misa_status
        FROM `tabSales Invoice` r
        WHERE r.return_against = %(si)s AND r.docstatus = 1
        ORDER BY r.posting_date, r.name
    """, {"si": si}, as_dict=True)

    by_advice = defaultdict(list)
    for d in deducts:
        by_advice[d.advice].append({
            "kind": cstr(d.row_kind or ""),
            "description": cstr(d.description or ""),
            "doc_no": cstr(d.doc_no or ""),
            "amount": flt(d.total_amount),
            "sales_invoice": cstr(d.sales_invoice or ""),
        })

    batches = []
    for a in advices:
        first = next(p for p in pays if p.advice == a)
        lines = [p for p in pays if p.advice == a]
        ded = by_advice.get(a, [])
        batches.append({
            "advice": a,
            "advice_no": cstr(first.advice_no or ""),
            "chain": cstr(first.chain or ""),
            "payment_date": cstr(first.payment_date or ""),
            "status": cstr(first.status or ""),
            "je_state": cstr(first.je_state or ""),
            "paid_this_invoice": round(sum(flt(x.total_amount) for x in lines), 2),
            "deductions": ded,
            "deduction_total": round(sum(x["amount"] for x in ded), 2),
        })

    return {
        "sales_invoice": si,
        "batches": batches,
        "returns": [{
            "name": r.name, "posting_date": cstr(r.posting_date),
            "amount": flt(r.amount),
            "misa_relation": cstr(r.misa_relation or ""),
            "misa_series": cstr(r.misa_series or ""),
            "misa_no": cstr(r.misa_no or ""),
            "misa_status": cstr(r.misa_status or ""),
            "misa_missing": not (cstr(r.misa_no or "") or cstr(r.misa_relation or "")),
        } for r in rets],
        "returned_total": round(sum(flt(r.amount) for r in rets), 2),
        # HAI LOẠI TRẢ HÀNG, HAI ĐƯỜNG CHỨNG TỪ. App KHÔNG đoán được cái nào là
        # cái nào — chỉ NGƯỜI biết hàng móp hay hàng date. Nên nói ra cả hai
        # đường và để người chọn, thay vì chọn hộ rồi sai.
        "return_note": _(
            "Hai loại trả hàng đi hai đường chứng từ khác nhau, và app không đoán thay "
            "được:\n"
            "· HÀNG MÓP TRONG VẬN CHUYỂN — siêu thị chỉ nhận theo thực tế, tức hóa đơn "
            "gốc ghi sai số lượng ngay từ đầu. Chứng từ đúng: HÓA ĐƠN THAY THẾ trên MISA.\n"
            "· HÀNG DATE / THỜI VỤ TRẢ LẠI — siêu thị đã nhận rồi mới trả. Đây là giao "
            "dịch MỚI, không phải sửa tờ cũ. Chứng từ đúng: siêu thị xuất hóa đơn trả cho "
            "mình, HOẶC mình xuất HÓA ĐƠN ĐIỀU CHỈNH GIẢM."),
        "deduction_note": _(
            "Các khoản trừ dưới đây thuộc về CẢ ĐỢT thanh toán, không phải riêng hóa đơn "
            "này. Bảng kê của chuỗi trừ chiết khấu/phí trên tổng đợt, không chứng từ nào "
            "nói tờ hóa đơn này chịu bao nhiêu — nên app KHÔNG chia đều cho từng tờ."),
    }
