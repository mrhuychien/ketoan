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
    """
    if not amounts:
        return []
    names = chain_customers(chain)
    if not names:
        return []

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
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND ABS(si.grand_total) BETWEEN %(lo)s AND %(hi)s
          AND {cus}
        ORDER BY si.posting_date DESC
        LIMIT 4000
    """, p, as_dict=True)
    return rows


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
    pool = _candidates(a.chain, company, need) if need else []

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
                d["gap"] = round(d["amount"] - flt(si.amount), 2)
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
    done, failed = [], []
    while True:
        todo = [r for r in data["rows"] if r.get("auto")]
        for r in todo:
            try:
                link_statement_line(r["line"], r["auto"]["sales_invoice"])
                done.append({"line": r["line"], "sales_invoice": r["auto"]["sales_invoice"]})
            except Exception as e:  # noqa: BLE001
                # Một dòng hỏng KHÔNG được kéo theo cả lượt: phần còn lại vẫn
                # nối được, và dòng hỏng phải hiện ra kèm lý do chứ không im.
                failed.append({"line": r["line"], "error": cstr(e)})
        if data["page"] >= data["pages"]:
            break
        data = get_statement_reconcile(advice, company=company,
                                       page=data["page"] + 1, page_size=100)

    return {"linked": len(done), "rows": done, "failed": failed,
            "message": _("Đã nối {0} dòng.").format(len(done))
            + (_(" {0} dòng không nối được.").format(len(failed)) if failed else "")}


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
    gap = round(abs(flt(si.grand_total)) - abs(flt(row.total_amount)), 2)
    if abs(gap) <= PAID_TOLERANCE:
        frappe.throw(_(
            "Dòng này không lệch tiền (chênh {0}đ, trong sai số {1}đ) — không có gì "
            "để giải trình.").format(gap, PAID_TOLERANCE))

    doc.db_set({"variance_kind": deduction_type,
                "variance_amount": gap,
                "variance_note": cstr(note or "") or None}, update_modified=False)
    return {"line": line, "variance_kind": deduction_type, "variance_amount": gap,
            "message": _("Đã ghi nhận {0}: {1}đ. Khoản này VẪN còn trên công nợ cho "
                         "tới khi có bút toán ở bước Bút toán.").format(deduction_type, gap)}


@frappe.whitelist()
def commit_statement(advice, expected_hash=None, company=None):
    """Chốt bảng kê và sinh bút toán NHÁP — hai bước, giữ nguyên chốt của B5.

    Không hash  -> đánh dấu đã đối chiếu và TRẢ VỀ bản xem trước + vân tay.
    Có hash     -> ủy quyền `mt_je.create_journal_entries`.

    Giữ hai bước là có chủ đích: `create_journal_entries` đòi vân tay của bản
    xem trước để chắc dữ liệu không đổi giữa chừng. Gộp thành một lời gọi rồi
    tự tính hash ở server là tự ký thay cho người — đúng cái chốt đó sinh ra để
    chặn. Và hệ **không bao giờ** submit: bút toán ra ở trạng thái nháp, chờ
    người duyệt ở bước B5.
    """
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    a = _load(advice, company)

    from ketoan.api import mt_je

    if not expected_hash:
        left = frappe.db.sql(f"""
            SELECT COUNT(*) FROM `tab{LINE}` l
            WHERE l.parent = %(a)s AND l.parenttype = %(pt)s
              AND l.row_kind = %(kind)s AND IFNULL(l.sales_invoice, '') = ''
        """, {"a": a.name, "pt": ADVICE, "kind": KIND_PAYMENT})[0][0]
        # Dòng chưa nối KHÔNG chặn việc chốt — có bảng kê mãi mãi còn một dòng
        # không tìm được hóa đơn, và chặn cứng thì cả bảng kê treo. Nhưng phải
        # NÓI RA số dòng bị bỏ lại, ngay trên nút bấm.
        pre = mt_je.preview_journal_entries(a.name, company=company)
        pre["unlinked"] = cint(left)
        pre["advice"] = a.name
        return pre

    frappe.db.set_value(ADVICE, a.name, {"reconciled": 1, "status": "Đã đối chiếu"},
                        update_modified=False)
    out = mt_je.create_journal_entries(a.name, expected_hash=expected_hash,
                                       company=company)
    out["advice"] = a.name
    return out
