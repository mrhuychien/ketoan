"""mt_reconcile — ĐỐI SOÁT MỘT BẢNG KÊ, ba vế đặt cạnh nhau.

════════════════════════════════════════════════════════════════════════════
MÀN NÀY GIẢI QUYẾT CÁI GÌ
════════════════════════════════════════════════════════════════════════════

Bảng kê của chuỗi có 142 dòng; 138 dòng máy khớp được, 4 dòng không. Bốn dòng
đó là việc — nhưng chúng nằm rải trong một bảng 142 dòng cùng màu, và cách duy
nhất để làm là mở từng dòng ra so bằng mắt với danh sách hóa đơn ở màn khác.

Ở đây ba vế nằm cùng một hàng: **dòng bảng kê · mức lệch · hóa đơn ERPNext**.
Đọc một hàng là biết chuỗi đã trả gì, mình ghi gì, và lệch bao nhiêu.

════════════════════════════════════════════════════════════════════════════
MODULE NÀY KHÔNG TỰ VIẾT LẠI LUẬT NÀO CỦA TẦNG DƯỚI
════════════════════════════════════════════════════════════════════════════

  · nối dòng vào hóa đơn   ->  `mt.relink_line`
  · sinh bút toán nháp     ->  `mt_je.preview_journal_entries` / `create_...`

Cả hai đã mang sẵn những chốt chặn đắt giá: dòng `Ghi giảm` **không** được nối
(bẫy tiền của Central Retail), hóa đơn phải cùng công ty với bảng kê, phải là
khách kênh MT, không được là phiếu trả hàng, và bút toán **không bao giờ tự ghi
sổ**. Viết lại một bản "cho gọn" ở đây là bỏ đúng những chốt đó — chúng không
nhìn thấy được từ màn hình, nên bản viết lại sẽ trông chạy tốt cho tới ngày
tiền biến khỏi cả hai kênh.

Nên các method dưới đây **ủy quyền**, không sao chép.

════════════════════════════════════════════════════════════════════════════
"GIẢI TRÌNH PHẦN LỆCH" LÀ MỘT CÁI NHÃN, KHÔNG PHẢI MỘT LẦN THU TIỀN
════════════════════════════════════════════════════════════════════════════

Chuỗi trả 3.276.000 cho hóa đơn 3.294.000. Thiếu 18.000, và kế toán biết đó là
phí trưng bày. `explain_variance` ghi lại điều đó.

⚠ NÓ KHÔNG LÀM 18.000 BIẾN MẤT KHỎI CÔNG NỢ. Hóa đơn vẫn còn thiếu 18.000 cho
tới khi có **bút toán** ghi khoản phí đó — việc của bước B5. Cho cái nhãn này
tự trừ công nợ là mở đúng cái lỗ mà MT2-G đã bịt: một khoản được trừ hai lần,
hoặc bị trừ mà không có chứng từ nào đứng sau.

Vì vậy `variance_amount` **máy suy** đúng bằng phần còn thiếu tại thời điểm ghi
nhãn, và KHÔNG một truy vấn tiền nào trong app đọc ba ô `variance_*`.
`reconcile_check` canh chỗ đó.

════════════════════════════════════════════════════════════════════════════
GỢI Ý KHỚP — BA MỨC, VÀ MỨC NÀO CŨNG PHẢI NÓI RA LÀ MỨC NÀO
════════════════════════════════════════════════════════════════════════════

    1. `chac_chan`   số tiền ĐÚNG TỪNG ĐỒNG + cùng điểm giao + trong kỳ
    2. `khac_diem`   số tiền đúng, khác điểm giao
    3. `gan_dung`    lệch trong 0,1%

Chỉ mức 1 mới được "Nhận hết" một lượt. Hai mức sau bày ra để người chọn, và
màn hình phải nói rõ nó là mức nào — một gợi ý không ghi độ tin cậy thì người
dùng đọc thành một kết luận.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from ketoan.api._guard import guard_manager, guard_mt, is_chief
from ketoan.api.mt import (
    KIND_PAYMENT,
    PAID_TOLERANCE,
    SI_NO_FIELD,
    SI_SERIES_FIELD,
    _company,
    _has_si_field,
    _require_tables,
    chain_customers,
    norm_text,
)

ADVICE = "MT Payment Advice"
LINE = "MT Payment Advice Line"

# Khoản trừ giải thích phần lệch — gõ ĐÚNG như options trong DocType JSON.
VAR_TRUNG_BAY = "Phí trưng bày"
VAR_CHIET_KHAU = "Chiết khấu thương mại"
VAR_HANG_TRA = "Hàng trả"
VAR_KHAC = "Khác"
VARIANCE_KINDS = (VAR_TRUNG_BAY, VAR_CHIET_KHAU, VAR_HANG_TRA, VAR_KHAC)

# Ba mức gợi ý. Khai ở MỘT chỗ vì cả truy vấn, cả nút "Nhận hết", cả màn hình
# đều đọc nó — ba bản sao thì "nhận hết" sẽ có ngày nhận cả mức 2.
SUG_CHAC_CHAN = "chac_chan"
SUG_KHAC_DIEM = "khac_diem"
SUG_GAN_DUNG = "gan_dung"

SUGGEST_LABEL = {
    SUG_CHAC_CHAN: "khớp số tiền và điểm giao",
    SUG_KHAC_DIEM: "khớp số tiền, khác điểm giao",
    SUG_GAN_DUNG: "gần đúng (lệch dưới 0,1%)",
}

# Ngưỡng "gần đúng". 0,1% của một hóa đơn 3 triệu là 3.000đ — đủ rộng để bắt
# sai số làm tròn, đủ hẹp để không gợi ý một hóa đơn khác hẳn.
NEAR_RATIO = 0.001

# Bộ lọc của màn hình.
F_CHUA_NOI = "chua_noi"
F_LECH_TIEN = "lech_tien"
F_DA_KHOP = "da_khop"
FILTERS = (F_CHUA_NOI, F_LECH_TIEN, F_DA_KHOP)

MAX_CANDIDATES = 6

# Trần rổ ứng viên quét một lượt. Chạm trần thì màn hình PHẢI nói ra: rổ đầy
# rồi lặng lẽ bỏ phần còn lại thì dòng nào không tìm được hóa đơn sẽ hiện
# "chuỗi chưa gán khách, hoặc hóa đơn chưa ghi sổ" — hai nguyên nhân đều SAI,
# và kế toán đi kiểm hai thứ hoàn toàn lành lặn.
CAND_CAP = 4000


def _tables():
    if not frappe.db.has_column(LINE, "variance_kind"):
        frappe.throw(_(
            "Màn đối soát bảng kê chưa được cài trên site này (bảng {0} thiếu ô "
            "`variance_kind`). Quản trị chạy: bench --site TÊN_SITE migrate"
        ).format(LINE))


def _load(advice, company):
    """Bảng kê, đã kiểm công ty. SQL thô không đi qua permission — chốt ở đây."""
    a = frappe.db.get_value(
        ADVICE, advice,
        ["name", "company", "chain", "customer", "advice_no", "payment_date",
         "status", "reconciled", "je_state", "total_payment", "file_name"],
        as_dict=True)
    if not a:
        frappe.throw(_("Không tìm thấy bảng kê {0}").format(advice))
    if cstr(a.company) != cstr(company):
        frappe.throw(_("Bảng kê {0} thuộc công ty {1}.").format(advice, a.company),
                     frappe.PermissionError)
    return a


def _si_col(field, alias="si"):
    return f"{alias}.`{field}`" if _has_si_field(field) else "NULL"


# ═══════════════════════════════════════════════════════════════════════════
# GỢI Ý KHỚP
# ═══════════════════════════════════════════════════════════════════════════

def _candidates(chain, company, amounts):
    """Rổ hóa đơn ứng viên cho CẢ TRANG, lấy trong MỘT truy vấn.

    Một truy vấn cho mỗi dòng là 142 lượt quét `tabSales Invoice` cho một lần mở
    màn hình. Quét đúng MỘT khoảng tiền bao trọn mọi mức gợi ý rồi xếp hạng
    trong Python.

    Chuỗi chưa gán khách nào -> rổ RỖNG, không phải "mọi hóa đơn": gợi ý lấy từ
    chuỗi khác là mời người dùng nối tiền LOTTE vào hóa đơn AEON.

    Hóa đơn ĐÃ THU ĐỦ bị loại khỏi rổ (`pd.paid`). Một hóa đơn đã nhận đủ tiền
    ở bảng kê tháng trước mà vẫn hiện lên như ứng viên "chắc chắn" cho một dòng
    tháng này là mời ghi có hai lần trên cùng một khoản nợ — và vì hai dòng nằm
    ở hai bảng kê khác nhau, không màn hình nào bày cả hai cạnh nhau để ai đó
    kịp thấy. Trả GÓP thì KHÔNG bị loại: `pd.paid` mới bằng một phần, và
    "một hóa đơn trả nhiều kỳ" là chuyện thường ở kênh này (Co.op tách 8 kỳ).
    """
    if not amounts:
        return [], False
    names = chain_customers(chain)
    if not names:
        return [], False

    p = {"company": company}
    keys = []
    for i, n in enumerate(names):
        p["c%d" % i] = n
        keys.append("%%(c%d)s" % i)
    cus = "si.customer IN (%s)" % ", ".join(keys)

    # Khoảng tiền cần quét: bao trọn mọi mức, kể cả `gần đúng`.
    lo = min(amounts) * (1 - NEAR_RATIO) - 1
    hi = max(amounts) * (1 + NEAR_RATIO) + 1
    p["lo"] = lo
    p["hi"] = hi

    ship = _si_col("shipping_address_name")
    rows = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, ABS(si.grand_total) AS amount,
               si.customer, si.customer_name,
               {_si_col(SI_SERIES_FIELD)} AS inv_series,
               {_si_col(SI_NO_FIELD)} AS inv_no,
               {ship} AS ship_to
        FROM `tabSales Invoice` si
        LEFT JOIN (
            SELECT l.sales_invoice AS si, SUM(ABS(l.total_amount)) AS paid
            FROM `tab{LINE}` l
            INNER JOIN `tab{ADVICE}` a ON a.name = l.parent
            WHERE l.parenttype = %(pt)s AND l.row_kind = %(kind)s
              AND a.docstatus < 2
              AND l.sales_invoice IS NOT NULL AND l.sales_invoice != ''
            GROUP BY l.sales_invoice
        ) pd ON pd.si = si.name
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND ABS(si.grand_total) BETWEEN %(lo)s AND %(hi)s
          AND IFNULL(pd.paid, 0) < ABS(si.grand_total) - %(tol)s
          AND {cus}
        ORDER BY si.posting_date DESC
        LIMIT %(cap)s
    """, dict(p, cap=CAND_CAP + 1, pt=ADVICE, kind=KIND_PAYMENT,
              tol=PAID_TOLERANCE), as_dict=True)
    return rows[:CAND_CAP], len(rows) > CAND_CAP


def _rank(line, invoices):
    """Xếp hạng ứng viên cho MỘT dòng bảng kê. Trả về danh sách đã xếp."""
    amt = abs(flt(line.get("total_amount")))
    store = norm_text(line.get("store_name")) or ""
    out = []
    for si in invoices:
        gap = abs(flt(si.amount) - amt)
        if gap <= PAID_TOLERANCE:
            same = bool(store) and store in (norm_text(si.get("ship_to")) or "")
            level = SUG_CHAC_CHAN if same else SUG_KHAC_DIEM
        elif amt and gap <= amt * NEAR_RATIO:
            level = SUG_GAN_DUNG
        else:
            continue
        out.append({
            "sales_invoice": si.name,
            "posting_date": cstr(si.posting_date or ""),
            "amount": flt(si.amount),
            "inv_series": cstr(si.inv_series or ""),
            "inv_no": cstr(si.inv_no or ""),
            "ship_to": cstr(si.ship_to or ""),
            "customer_name": cstr(si.customer_name or ""),
            "gap": round(flt(si.amount) - amt, 2),
            "level": level,
            "level_label": SUGGEST_LABEL[level],
        })
    order = {SUG_CHAC_CHAN: 0, SUG_KHAC_DIEM: 1, SUG_GAN_DUNG: 2}
    out.sort(key=lambda x: (order[x["level"]], abs(x["gap"])))
    return out[:MAX_CANDIDATES]


def _auto_ok(cands):
    """Gợi ý ĐỦ CHẮC để nhận hàng loạt: đúng MỘT ứng viên, và ở mức 1.

    Hai ứng viên cùng mức 1 nghĩa là hai hóa đơn cùng số tiền cùng điểm giao —
    máy không có cơ sở nào chọn giữa chúng, và chọn bừa một cái là gán tiền vào
    sai hóa đơn mà không ai thấy.
    """
    top = [c for c in cands if c["level"] == SUG_CHAC_CHAN]
    return top[0] if len(top) == 1 else None


# ═══════════════════════════════════════════════════════════════════════════
# ĐỌC
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_statement_reconcile(advice, company=None, filter=None, page=1, page_size=25):
    """Ba vế của một bảng kê: dòng chuỗi trả · mức lệch · hóa đơn ERPNext."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    a = _load(advice, company)

    flt_key = cstr(filter or "").strip() or None
    if flt_key and flt_key not in FILTERS:
        frappe.throw(_("Bộ lọc không hợp lệ: {0}").format(flt_key))
    page = max(1, cint(page))
    page_size = min(100, max(5, cint(page_size) or 25))

    lines = frappe.db.sql(f"""
        SELECT l.name AS line, l.idx, l.row_kind, l.total_amount, l.store_name,
               l.store_code, l.doc_no, l.description, l.inv_series, l.inv_no,
               l.sales_invoice, l.match_confidence, l.match_method,
               l.variance_kind, l.variance_amount, l.variance_note,
               IFNULL(l.payment_date, %(pd)s) AS payment_date
        FROM `tab{LINE}` l
        WHERE l.parent = %(a)s AND l.parenttype = %(pt)s
          AND l.row_kind = %(kind)s
        ORDER BY l.idx
    """, {"a": a.name, "pt": ADVICE, "kind": KIND_PAYMENT,
          "pd": a.payment_date}, as_dict=True)

    linked = [cstr(l.sales_invoice) for l in lines if l.sales_invoice]
    # Tiền ĐÃ TRẢ cho từng hóa đơn, cộng trên MỌI bảng kê — không chỉ bảng kê
    # đang mở.
    #
    # ⚠ ĐÂY LÀ CHỖ BẢN ĐẦU SAI NẶNG NHẤT. Nó so MỘT dòng với TOÀN BỘ hóa đơn,
    # trong khi cả app mô hình hóa "một hóa đơn được trả làm nhiều lần" là
    # chuyện thường — `relink_line` ghi hẳn trong docstring: "Co.op tách 8 kỳ,
    # LOTTE 2 ngày thanh toán". Hóa đơn 3.200.000 trả làm 8 kỳ 400.000 thì CẢ
    # TÁM dòng bị chấm "lệch tiền 2.800.000", chip đếm 8 việc không có thật, và
    # bấm "Giải trình" một dòng là ghi 2.800.000 vào ô phần lệch của một dòng
    # không thiếu một đồng.
    paid_map = {}
    if linked:
        for r in frappe.db.sql(f"""
            SELECT l.sales_invoice AS si, SUM(ABS(l.total_amount)) AS paid
            FROM `tab{LINE}` l
            INNER JOIN `tab{ADVICE}` a ON a.name = l.parent
            WHERE l.parenttype = %(pt)s AND l.row_kind = %(kind)s
              AND a.docstatus < 2 AND l.sales_invoice IN %(n)s
            GROUP BY l.sales_invoice
        """, {"pt": ADVICE, "kind": KIND_PAYMENT,
              "n": tuple(set(linked))}, as_dict=True):
            paid_map[r.si] = flt(r.paid)
    si_map = {}
    if linked:
        ship = _si_col("shipping_address_name")
        for r in frappe.db.sql(f"""
            SELECT si.name, si.posting_date, ABS(si.grand_total) AS amount,
                   si.customer_name,
                   {_si_col(SI_SERIES_FIELD)} AS inv_series,
                   {_si_col(SI_NO_FIELD)} AS inv_no,
                   {ship} AS ship_to
            FROM `tabSales Invoice` si WHERE si.name IN %(n)s
        """, {"n": tuple(set(linked))}, as_dict=True):
            si_map[r.name] = r

    need = [abs(flt(l.total_amount)) for l in lines if not l.sales_invoice]
    pool, pool_cut = _candidates(a.chain, company, need) if need else ([], False)

    rows, n_chua, n_lech, n_khop, n_auto = [], 0, 0, 0, 0
    for l in lines:
        d = {
            "line": l.line, "idx": cint(l.idx),
            "amount": flt(l.total_amount),
            "payment_date": cstr(l.payment_date or ""),
            "store_name": cstr(l.store_name or "") or cstr(l.store_code or ""),
            "doc_no": cstr(l.doc_no or ""),
            "description": cstr(l.description or ""),
            "sales_invoice": cstr(l.sales_invoice or ""),
            "match_confidence": cstr(l.match_confidence or ""),
            "variance_kind": cstr(l.variance_kind or ""),
            "variance_amount": flt(l.variance_amount),
            "variance_note": cstr(l.variance_note or ""),
            "candidates": [], "auto": None, "gap": None, "invoice": None,
            "paid_total": None, "one_of_many": False,
        }
        if d["sales_invoice"]:
            si = si_map.get(d["sales_invoice"])
            if si:
                d["invoice"] = {
                    "name": si.name, "posting_date": cstr(si.posting_date or ""),
                    "amount": flt(si.amount), "inv_series": cstr(si.inv_series or ""),
                    "inv_no": cstr(si.inv_no or ""), "ship_to": cstr(si.ship_to or ""),
                    "customer_name": cstr(si.customer_name or ""),
                }
                # `gap` là của CẢ HÓA ĐƠN, và so hai GIÁ TRỊ TUYỆT ĐỐI.
                #
                # File của Central Retail / Emart mang số tiền ÂM cho dòng
                # thanh toán; so thẳng số có dấu với `ABS(grand_total)` thì
                # mọi dòng đã khớp đúng vẫn ra "lệch gấp đôi số tiền".
                d["paid_total"] = flt(paid_map.get(d["sales_invoice"],
                                                   abs(d["amount"])))
                d["gap"] = round(d["paid_total"] - abs(flt(si.amount)), 2)
                d["one_of_many"] = abs(d["paid_total"] - abs(d["amount"])) > PAID_TOLERANCE
            # LỆCH TIỀN chỉ tính khi CHƯA ai ghi nhãn. Ghi nhãn rồi thì nó
            # không còn là câu hỏi bỏ ngỏ — nhưng tiền vẫn thiếu, và phần thiếu
            # đó nằm ở công nợ chứ không nằm ở đây.
            lech = (d["gap"] is not None and abs(d["gap"]) > PAID_TOLERANCE
                    and not d["variance_kind"])
            d["state"] = F_LECH_TIEN if lech else F_DA_KHOP
            if lech:
                n_lech += 1
            else:
                n_khop += 1
        else:
            d["candidates"] = _rank(l, pool)
            d["auto"] = _auto_ok(d["candidates"])
            if d["auto"]:
                n_auto += 1
            d["state"] = F_CHUA_NOI
            n_chua += 1
        rows.append(d)

    shown = [r for r in rows if not flt_key or r["state"] == flt_key]
    total = len(shown)
    off = (page - 1) * page_size
    shown = shown[off:off + page_size]

    n_all = len(rows)
    return {
        "advice": a.name,
        "advice_no": cstr(a.advice_no or "") or a.name,
        "chain": cstr(a.chain or ""),
        "payment_date": cstr(a.payment_date or ""),
        "status": cstr(a.status or ""),
        "reconciled": cint(a.reconciled),
        "je_state": cstr(a.je_state or ""),
        "file_name": cstr(a.file_name or ""),
        "total_payment": flt(a.total_payment),
        "rows": shown,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "filter": flt_key or "",
        "counts": {F_CHUA_NOI: n_chua, F_LECH_TIEN: n_lech, F_DA_KHOP: n_khop},
        # Tiến độ đọc là "đã nối được bao nhiêu trên tổng", không phải "bao nhiêu
        # dòng không có lỗi": dòng lệch tiền VẪN đã nối được hóa đơn.
        "matched": n_all - n_chua,
        "lines": n_all,
        "auto_ready": n_auto,
        # Rổ ứng viên chạm trần -> "không tìm thấy" ở dưới có thể do CẮT chứ
        # không do dữ liệu. Nói ra, đừng để người đi kiểm nhầm chỗ.
        "pool_truncated": bool(pool_cut),
        "pool_cap": CAND_CAP,
        "variance_kinds": list(VARIANCE_KINDS),
        "tolerance": PAID_TOLERANCE,
        "can_manage": is_chief(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# GHI
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def link_statement_line(line, sales_invoice=None, note=None):
    """Nối một dòng bảng kê vào hóa đơn — ỦY QUYỀN cho `mt.relink_line`.

    Không viết lại: `relink_line` chặn dòng `Ghi giảm` (bẫy tiền Central
    Retail), chặn hóa đơn khác công ty, chặn khách ngoài kênh MT, chặn phiếu
    trả hàng. Bốn chốt đó không nhìn thấy được từ màn hình này.
    """
    from ketoan.api.mt import relink_line

    return relink_line(line, sales_invoice=sales_invoice, note=note)


@frappe.whitelist()
def bulk_link(advice, company=None):
    """Nhận HẾT gợi ý mức 1 của một bảng kê, một lượt.

    Chỉ nhận gợi ý `chac_chan` và CHỈ khi nó là ứng viên duy nhất ở mức đó —
    xem `_auto_ok`. Mỗi dòng vẫn đi qua `relink_line`, nên mọi chốt chặn vẫn
    chạy đủ; hàng loạt ở đây là "bấm hộ nhiều lần", không phải một đường tắt
    vòng qua luật.
    """
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    _load(advice, company)

    data = get_statement_reconcile(advice, company=company, page_size=100)
    done, failed, clashed = [], [], []
    taken = set()
    while True:
        todo = [r for r in data["rows"] if r.get("auto")]
        # Hóa đơn ĐÃ CÓ dòng tiền khác trỏ tới thì KHÔNG nhận tự động.
        #
        # `relink_line` trả về `other_lines_on_invoice` đúng để cảnh báo chuyện
        # này, và bản đầu vứt nó đi — cảnh báo phát ra rồi không ai đọc còn tệ
        # hơn không phát. Ở đây hỏi TRƯỚC khi nối, vì hỏi sau là đã nối rồi.
        #
        # Trả GÓP không rơi vào đây: một kỳ trả nhỏ hơn hẳn hóa đơn, nên `_rank`
        # không xếp nó mức `chac_chan` để mà nhận. Một gợi ý mức 1 rơi vào hóa
        # đơn đã có dòng khác nghĩa là TRẢ TRỌN thêm một lần nữa.
        claimed = set()
        cand = sorted({r["auto"]["sales_invoice"] for r in todo})
        if cand:
            for c in frappe.db.sql(f"""
                SELECT DISTINCT l.sales_invoice AS si
                FROM `tab{LINE}` l
                INNER JOIN `tab{ADVICE}` a ON a.name = l.parent
                WHERE l.parenttype = %(pt)s AND l.row_kind = %(kind)s
                  AND a.docstatus < 2 AND l.sales_invoice IN %(n)s
            """, {"pt": ADVICE, "kind": KIND_PAYMENT, "n": tuple(cand)}, as_dict=True):
                claimed.add(cstr(c.si))
        for r in todo:
            si = r["auto"]["sales_invoice"]
            if si in taken or si in claimed:
                # `_auto_ok` chỉ dám nói "dòng này có ĐÚNG MỘT hóa đơn ứng".
                # Nó KHÔNG nói chiều ngược lại. Hai dòng bảng kê cùng chỉ về một
                # hóa đơn mà nhận cả hai là ghi có hai lần trên một khoản nợ —
                # đúng cái lỗ MT2-G. Dòng thứ hai để người xử lý tay.
                clashed.append({
                    "line": r["line"], "sales_invoice": si,
                    "reason": _("đã nhận ở lượt này") if si in taken
                    else _("hóa đơn đã có dòng tiền khác trỏ tới"),
                })
                continue
            try:
                link_statement_line(r["line"], si)
                done.append({"line": r["line"], "sales_invoice": si})
                taken.add(si)
            except Exception as e:  # noqa: BLE001
                # Một dòng hỏng KHÔNG được kéo theo cả lượt: phần còn lại vẫn
                # nối được, và dòng hỏng phải hiện ra kèm lý do chứ không im.
                failed.append({"line": r["line"], "error": cstr(e)})
        if data["page"] >= data["pages"]:
            break
        data = get_statement_reconcile(advice, company=company,
                                       page=data["page"] + 1, page_size=100)

    msg = _("Đã nối {0} dòng.").format(len(done))
    if failed:
        msg += _(" {0} dòng không nối được.").format(len(failed))
    if clashed:
        msg += _(" {0} dòng KHÔNG nhận tự động vì hóa đơn của chúng đã có tiền trỏ "
                 "tới — nhận nữa là ghi có hai lần. Chúng còn nguyên trong danh "
                 "sách để bạn chọn tay.").format(len(clashed))
    return {"linked": len(done), "rows": done, "failed": failed,
            "clashed": clashed, "message": msg}


@frappe.whitelist()
def explain_variance(line, deduction_type, note=None, company=None):
    """Ghi NHÃN cho phần chuỗi trả thiếu. KHÔNG phải một lần thu tiền.

    ⚠ Hàm này KHÔNG đụng `total_amount`, KHÔNG đụng công nợ. Phần thiếu vẫn còn
    nguyên trên hóa đơn cho tới khi có bút toán ở bước B5. Cho cái nhãn tự trừ
    công nợ là mở lại đúng cái lỗ MT2-G đã bịt.

    `variance_amount` MÁY SUY bằng phần còn thiếu tại thời điểm ghi — không cho
    gõ tay. Một con số đi giải trình mà gõ tay được thì nó là ý kiến.
    """
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)

    deduction_type = cstr(deduction_type).strip()
    if deduction_type and deduction_type not in VARIANCE_KINDS:
        frappe.throw(_("Khoản trừ không hợp lệ: {0}").format(deduction_type))

    row = frappe.db.get_value(
        LINE, line, ["name", "parent", "parenttype", "row_kind", "sales_invoice",
                     "total_amount"], as_dict=True)
    if not row or row.parenttype != ADVICE:
        frappe.throw(_("Không tìm thấy dòng bảng kê {0}").format(line))
    _load(row.parent, company)
    if cstr(row.row_kind) != KIND_PAYMENT:
        frappe.throw(_("Chỉ dòng '{0}' mới có phần lệch để giải trình.").format(KIND_PAYMENT))

    doc = frappe.get_doc(LINE, line)

    if not deduction_type:
        # Gỡ nhãn: dòng quay lại nhóm "lệch tiền" để còn ai đó xử.
        doc.db_set({"variance_kind": None, "variance_amount": 0,
                    "variance_note": None}, update_modified=False)
        return {"line": line, "variance_kind": "", "variance_amount": 0.0}

    if not row.sales_invoice:
        frappe.throw(_(
            "Dòng này chưa nối hóa đơn nào — chưa biết nó trả cho tờ nào thì chưa có "
            "phần lệch để giải trình. Nối hóa đơn trước."))

    si = frappe.db.get_value("Sales Invoice", row.sales_invoice,
                             ["grand_total"], as_dict=True)
    if not si:
        frappe.throw(_("Không tìm thấy hóa đơn {0}").format(row.sales_invoice))

    # ĐO TRÊN CẢ HÓA ĐƠN — cùng một phép với `get_statement_reconcile`. Một hóa
    # đơn được chuỗi trả làm nhiều kỳ thì từng kỳ nhỏ hơn hóa đơn là bình
    # thường; so một kỳ với cả tờ rồi ghi phần chênh vào ô "phần lệch" là ghi
    # một con số không tồn tại.
    paid = flt(frappe.db.sql(f"""
        SELECT SUM(ABS(l.total_amount)) FROM `tab{LINE}` l
        INNER JOIN `tab{ADVICE}` a ON a.name = l.parent
        WHERE l.parenttype = %(pt)s AND l.row_kind = %(kind)s
          AND a.docstatus < 2 AND l.sales_invoice = %(si)s
    """, {"pt": ADVICE, "kind": KIND_PAYMENT, "si": row.sales_invoice})[0][0])

    # MỘT QUY ƯỚC DẤU cho cả module: `gap = tiền chuỗi trả − tiền hóa đơn`.
    # Âm = chuỗi trả THIẾU. Đúng dấu mà `get_statement_reconcile` trả ra và màn
    # hình in ra. Ghi ngược dấu thì ô `variance_amount` trên Desk đọc +18.000
    # trong khi màn hình ghi −18.000 cho cùng một dòng.
    gap = round(paid - abs(flt(si.grand_total)), 2)
    if abs(gap) <= PAID_TOLERANCE:
        frappe.throw(_(
            "Hóa đơn {0} không lệch tiền: chuỗi đã trả {1}đ cho hóa đơn {2}đ (chênh "
            "{3}đ, trong sai số {4}đ) — không có gì để giải trình."
        ).format(row.sales_invoice, paid, abs(flt(si.grand_total)), gap, PAID_TOLERANCE))

    doc.db_set({"variance_kind": deduction_type,
                "variance_amount": gap,
                "variance_note": cstr(note or "") or None}, update_modified=False)
    return {"line": line, "variance_kind": deduction_type, "variance_amount": gap,
            "message": _("Đã ghi nhận {0}: chuỗi trả {1} {2}đ cho hóa đơn {3}. Khoản này "
                         "VẪN còn trên công nợ cho tới khi có bút toán ở bước Bút toán."
                         ).format(deduction_type, _("thiếu") if gap < 0 else _("vượt"),
                                  abs(gap), row.sales_invoice)}


@frappe.whitelist()
def commit_statement(advice, company=None):
    """CHỐT bảng kê: đánh dấu ĐÃ ĐỐI CHIẾU. Bút toán do modal cũ sinh.

    ════════════════════════════════════════════════════════════════════════
    VÌ SAO MỘT BƯỚC, KHÔNG PHẢI HAI
    ════════════════════════════════════════════════════════════════════════

    Bản đầu chia hai: gọi lần đầu trả bản xem trước, gọi lần hai kèm vân tay
    thì mới ghi `reconciled = 1` và sinh bút toán. Nhưng màn hình chỉ gọi MỘT
    lần rồi mở modal bút toán cũ — mà modal đó gọi thẳng
    `mt_je.create_journal_entries`. Nhánh thứ hai **không bao giờ chạy**:

      · bảng kê KHÔNG BAO GIỜ được đánh dấu đã đối chiếu;
      · màn hình vừa hiện chữ "Đã chốt";
      · modal bút toán mở ra ngay sau đó gắn nhãn "chưa tick đối chiếu khớp";
      · và bảng kê ở lại nhóm "Bảng kê chưa đối chiếu" của hàng đợi việc vĩnh
        viễn — đúng cái việc mà nút này sinh ra để đóng.

    Bốn câu trái nhau trong một giây. Sửa cho khớp việc thật: **chốt là chốt** —
    người vừa xem xong ba vế và khẳng định phần khớp đã xong, nên ghi ngay tại
    đây. Bút toán vẫn do modal cũ sinh, vì chốt chặn vân tay của `mt_je` thuộc
    về nó: người phải NHÌN bản xem trước rồi mới bấm sinh.

    Hàm này KHÔNG sinh bút toán và KHÔNG bao giờ submit.
    """
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    a = _load(advice, company)

    left = cint(frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tab{LINE}` l
        WHERE l.parent = %(a)s AND l.parenttype = %(pt)s
          AND l.row_kind = %(kind)s AND IFNULL(l.sales_invoice, '') = ''
    """, {"a": a.name, "pt": ADVICE, "kind": KIND_PAYMENT})[0][0])

    # Dòng chưa nối KHÔNG chặn việc chốt — có bảng kê mãi mãi còn một dòng không
    # tìm được hóa đơn, và chặn cứng thì cả bảng kê treo. Nhưng phải NÓI RA số
    # dòng bị bỏ lại: chúng không vào bút toán nào cả.
    frappe.db.set_value(ADVICE, a.name, {"reconciled": 1, "status": "Đã đối chiếu"},
                        update_modified=False)
    return {
        "advice": a.name,
        "advice_no": cstr(a.advice_no or "") or a.name,
        "reconciled": 1,
        "unlinked": left,
        "message": _("Đã chốt bảng kê {0}.").format(cstr(a.advice_no or "") or a.name)
        + (_(" Còn {0} dòng chưa nối hóa đơn — chúng KHÔNG vào bút toán.").format(left)
           if left else ""),
    }


# ═══════════════════════════════════════════════════════════════════════════
# NỐI NGƯỢC: TỪ HÓA ĐƠN TÌM DÒNG BẢNG KÊ
# ═══════════════════════════════════════════════════════════════════════════
#
# Màn đối soát đi từ BẢNG KÊ: cầm một file của chuỗi rồi tìm hóa đơn cho từng
# dòng. Nhưng kế toán cũng làm chiều ngược lại — nhìn danh sách hóa đơn còn nợ,
# thấy vài tờ đáng lẽ đã được trả, và muốn biết tiền của chúng nằm ở dòng nào.
#
# ⚠ ĐÂY KHÔNG PHẢI "ĐÁNH DẤU ĐÃ THU". Nó chỉ nối hóa đơn với một dòng tiền CÓ
# THẬT trên một bảng kê ĐÃ NẠP. Không có dòng nào khớp thì không nối gì cả —
# hóa đơn vẫn còn nợ, vì nó thật sự còn nợ.

MAX_REVERSE = 50


@frappe.whitelist()
def suggest_for_invoices(invoices, company=None):
    """Với mỗi hóa đơn được chọn: những dòng bảng kê CHƯA NỐI có thể là tiền của nó."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    if isinstance(invoices, str):
        import json as _json
        try:
            invoices = _json.loads(invoices)
        except ValueError:
            invoices = [x.strip() for x in invoices.split(",") if x.strip()]
    names = [cstr(x).strip() for x in (invoices or []) if cstr(x).strip()]
    if not names:
        frappe.throw(_("Chưa chọn hóa đơn nào."))
    if len(names) > MAX_REVERSE:
        frappe.throw(_(
            "Chọn tối đa {0} hóa đơn một lượt. Nhiều hơn thì mỗi dòng bảng kê phải so "
            "với quá nhiều tờ, và gợi ý mất hết ý nghĩa."
        ).format(MAX_REVERSE))

    ship = _si_col("shipping_address_name")
    sis = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, ABS(si.grand_total) AS amount,
               si.customer, si.customer_name, {ship} AS ship_to
        FROM `tabSales Invoice` si
        WHERE si.name IN %(n)s AND si.company = %(c)s
          AND si.docstatus = 1 AND si.is_return = 0
    """, {"n": tuple(names), "c": company}, as_dict=True)
    if not sis:
        frappe.throw(_("Không hóa đơn nào trong danh sách đã chọn thuộc công ty này."))

    lo = min(flt(s.amount) for s in sis) - PAID_TOLERANCE
    hi = max(flt(s.amount) for s in sis) + PAID_TOLERANCE
    lines = frappe.db.sql(f"""
        SELECT l.name AS line, l.parent AS advice, a.advice_no, a.chain,
               l.total_amount, l.store_name, l.store_code, l.description,
               IFNULL(l.payment_date, a.payment_date) AS payment_date
        FROM `tab{LINE}` l
        INNER JOIN `tab{ADVICE}` a ON a.name = l.parent
        WHERE l.parenttype = %(pt)s AND a.company = %(c)s
          AND l.row_kind = %(kind)s
          AND IFNULL(l.sales_invoice, '') = ''
          AND ABS(l.total_amount) BETWEEN %(lo)s AND %(hi)s
        ORDER BY payment_date DESC
        LIMIT 2000
    """, {"pt": ADVICE, "c": company, "kind": KIND_PAYMENT,
          "lo": lo, "hi": hi}, as_dict=True)

    out = []
    for si in sis:
        amt = flt(si.amount)
        store = norm_text(si.ship_to) or ""
        cands = []
        for ln in lines:
            if abs(abs(flt(ln.total_amount)) - amt) > PAID_TOLERANCE:
                continue
            ls = norm_text(ln.store_name) or norm_text(ln.store_code) or ""
            same = bool(ls) and bool(store) and (ls in store or store in ls)
            cands.append({
                "line": ln.line, "advice": ln.advice,
                "advice_no": cstr(ln.advice_no or "") or ln.advice,
                "chain": cstr(ln.chain or ""),
                "amount": flt(ln.total_amount),
                "payment_date": cstr(ln.payment_date or ""),
                "store_name": cstr(ln.store_name or "") or cstr(ln.store_code or ""),
                "level": SUG_CHAC_CHAN if same else SUG_KHAC_DIEM,
                "level_label": SUGGEST_LABEL[SUG_CHAC_CHAN if same else SUG_KHAC_DIEM],
            })
        cands.sort(key=lambda x: (0 if x["level"] == SUG_CHAC_CHAN else 1,
                                  x["payment_date"]), reverse=False)
        out.append({
            "sales_invoice": si.name,
            "posting_date": cstr(si.posting_date or ""),
            "amount": amt,
            "customer_name": cstr(si.customer_name or ""),
            "ship_to": cstr(si.ship_to or ""),
            "candidates": cands[:MAX_CANDIDATES],
            "auto": _auto_ok(cands[:MAX_CANDIDATES]),
        })
    return {
        "rows": out,
        "auto_ready": sum(1 for r in out if r["auto"]),
        "can_manage": is_chief(),
        # NÓI RA điều màn hình này KHÔNG làm: một danh sách "gợi ý nối" rất dễ
        # bị đọc thành "đánh dấu đã thu".
        "note": _(
            "Chỉ nối hóa đơn với dòng tiền CÓ THẬT trên bảng kê đã nạp. Hóa đơn không "
            "có dòng nào khớp thì vẫn còn nợ — đây không phải chỗ đánh dấu đã thu."),
    }
