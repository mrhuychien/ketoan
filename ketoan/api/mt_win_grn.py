"""mt_win_grn — đọc PHIẾU NHẬP KHO của Winmart (PDF) và đối soát trước khi xuất HĐ.

SOP §2.2 nói rõ: *"Xuất HĐ CHỈ sau khi có phiếu nhập kho trên hệ Win và khớp
**PO + hàng hóa** với đơn trên ERPNext. Lệch số lượng → làm xuất trả phần chênh
trên ERPNext, xuất hóa đơn theo số thực nhận."*

Đây là khâu đó. Trước module này, kế toán mở PDF ra đọc bằng mắt rồi so tay với
hóa đơn — sai một mã hàng hoặc một số lượng thì hóa đơn sai, và Win trả hồ sơ.

════════════════════════════════════════════════════════════════════════════
PHIẾU NHẬP KHO NÓI GÌ — ĐO TRÊN HAI FILE THẬT
════════════════════════════════════════════════════════════════════════════

    Số Phiếu        5195070958        <- số phiếu nhập kho
    Ngày thực hiện  30/07/2026
    Số đơn hàng     4193445648        <- SỐ PO, khóa để nối sang hóa đơn
    Cửa hàng / kho  1312 WMP_AMBIENT_BINH DUONG1_HANGTHUONG
    Nhà cung cấp    0002007766 CTY CP HOÀNG GIANG
    Delivery Note   4193445648

    STT  Mã hàng   Tên hàng                                    Số lượng  ĐVT
    1    10325502  HOÀNG GIANG Bánh Đậu xanh rồng vàng 300g    40        HOP

⚠ PHIẾU KHÔNG CÓ TIỀN — chỉ có SỐ LƯỢNG. Nên đối soát được `PO` + `mã hàng` +
`số lượng`, KHÔNG đối soát được thành tiền. Đừng dựng ra một phép so tiền nào ở
đây; số tiền vẫn phải lấy từ đơn giá trên hóa đơn.

════════════════════════════════════════════════════════════════════════════
NỐI SANG HÓA ĐƠN BẰNG HAI FIELD CỦA SITE
════════════════════════════════════════════════════════════════════════════

    Số đơn hàng  <->  `Sales Invoice.custom_po_`
    Mã hàng      <->  `Sales Invoice Item.custom_ma_win`

CẢ HAI ĐỀU LÀ FIELD CỦA SITE, không do app này tạo. Vì vậy PHẢI dò bằng
`has_column` trước khi dùng: site chưa có thì báo đúng field còn thiếu, chứ
không ném lỗi SQL khó hiểu, và tuyệt đối không đoán sang field khác.

════════════════════════════════════════════════════════════════════════════
BỐN KẾT LUẬN, KHÔNG GỘP THÀNH "KHỚP / KHÔNG KHỚP"
════════════════════════════════════════════════════════════════════════════

  · khop        — có trên cả hai, số lượng bằng nhau
  · lech_sl     — có trên cả hai, số lượng khác  -> xuất HĐ theo SỐ THỰC NHẬN
  · thieu_tren_hd  — phiếu có, hóa đơn KHÔNG    -> hóa đơn thiếu hàng
  · thua_tren_hd   — hóa đơn có, phiếu KHÔNG    -> Win không nhận, phải xuất trả

Gộp bốn thứ này thành một chữ "không khớp" là bắt kế toán mở lại PDF đọc tay —
đúng việc mà module này sinh ra để bỏ.

MODULE NÀY KHÔNG SỬA HÓA ĐƠN, KHÔNG TẠO CHỨNG TỪ. Chỗ duy nhất nó ghi là dòng
`MT Win Pending` của chính đợt giao đó: đánh dấu "đã nhận, chờ xuất HĐ" kèm số
phiếu — đúng cái mà trước đây kế toán gõ tay từ PDF sang.
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from ketoan.api._guard import guard_manager, guard_mt, is_chief
from ketoan.api.mt import _company, _require_tables
from ketoan.api.mt_advice import decode_upload, to_date
from ketoan.api.mt_rebate_pdf import is_pdf, label_value, lines_of, read_words
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_text,
)
from ketoan.mt.doctype.mt_win_pending.mt_win_pending import (
    STATUS_CANCELLED,
    STATUS_DELIVERING,
    STATUS_RECEIVED,
)

SI_PO_FIELD = "custom_po_"
SII_CODE_FIELD = "custom_ma_win"

PENDING_DOCTYPE = "MT Win Pending"

# Trần dòng hàng trên một phiếu. Hai phiếu mẫu có 1 và 5 dòng; vượt xa mức này
# là đọc nhầm bảng.
MAX_LINES = 500

# Sai số so số lượng. Số lượng Win là số nguyên (HOP/THUNG) nhưng vẫn để một
# khoảng rất nhỏ phòng ô lưu 40.000000001.
QTY_EPS = 0.001

MATCH_OK = "khop"
MATCH_QTY = "lech_sl"
MATCH_MISSING_SI = "thieu_tren_hd"
MATCH_EXTRA_SI = "thua_tren_hd"

MATCH_LABEL = {
    MATCH_OK: "Khớp",
    MATCH_QTY: "Lệch số lượng",
    MATCH_MISSING_SI: "Phiếu có, hóa đơn KHÔNG có",
    MATCH_EXTRA_SI: "Hóa đơn có, phiếu KHÔNG có",
}

# Dòng hàng: `1  10325502  HOÀNG GIANG Bánh Đậu xanh rồng vàng 300g  40  HOP`
#             STT  mã hàng  tên hàng (có cả số bên trong)            SL  ĐVT
#
# Tên hàng CHỨA SỐ ('300g', '210g') nên không thể tách bằng "lấy số cuối cùng".
# Neo vào ĐVT ở cuối dòng: nó là chữ in hoa không dấu, và số lượng đứng ngay
# trước nó.
ROW_RE = re.compile(
    r"^(?P<stt>\d{1,3})\s+"
    r"(?P<code>\d{6,})\s+"
    r"(?P<name>.+?)\s+"
    r"(?P<qty>-?[\d.,]+)\s+"
    r"(?P<uom>[A-Za-zÀ-ỹ]{1,12})\s*$"
)

HEADER_LABELS = ("Số Phiếu", "Số đơn hàng", "Mã hàng", "Số lượng")


def _qty(s):
    """Số lượng Win: '40', '1.234', '1,234'. Không phải tiền nên không có phần lẻ."""
    t = cstr(s).replace(" ", "").replace(".", "").replace(",", "")
    if not re.fullmatch(r"-?\d+", t):
        return None
    return float(t)


def read_grn(content):
    """base64 -> nội dung một phiếu nhập kho Winmart. THUẦN ĐỌC."""
    raw = decode_upload(content)
    if not is_pdf(raw):
        frappe.throw(_("File không phải PDF. Phiếu nhập kho Win là bản PDF tải từ hệ "
                       "thống của Win."))

    pages = read_words(raw)
    words = [w for pg in pages for w in pg]
    blob = " ".join(t for t, _w in lines_of(words))

    missing = [lb for lb in HEADER_LABELS if lb.lower() not in blob.lower()]
    if missing:
        frappe.throw(_("File PDF thiếu các nhãn {0} — không phải phiếu nhập kho Winmart, "
                       "hoặc Win đã đổi mẫu.").format(", ".join(missing)))

    grn_no = label_value(words, "Số Phiếu")
    po_no = label_value(words, "Số đơn hàng")
    grn_date = None
    m = re.search(r"Ngày thực hiện\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", blob)
    if m:
        grn_date = to_date(m.group(1))

    # Tên kho CÓ DẤU CÁCH (`1312 WMP_AMBIENT_BINH DUONG1_HANGTHUONG`), nên
    # không lấy được bằng "hai token sau nhãn" — đã đo: cách đó cắt cụt thành
    # `1312 WMP_AMBIENT_BINH`. Lấy tới nhãn kế tiếp trên cùng dòng.
    store = None
    m = re.search(r"Cửa hàng\s*/\s*kho\s+(.+?)\s+(?:Người tạo|Nhóm mua|$)", blob)
    if m:
        store = re.sub(r"\s+", " ", m.group(1)).strip()

    vendor = None
    m = re.search(r"Nhà cung cấp\s+(\d{6,})", blob)
    if m:
        vendor = m.group(1)

    lines = []
    for text, _ws in lines_of(words):
        mt = ROW_RE.match(text.strip())
        if not mt:
            continue
        qty = _qty(mt.group("qty"))
        if qty is None:
            continue
        if len(lines) >= MAX_LINES:
            frappe.throw(_("Phiếu có hơn {0} dòng hàng — đọc nhầm bảng. KHÔNG đối soát.")
                         .format(MAX_LINES))
        lines.append({
            "stt": cint(mt.group("stt")),
            "item_code": norm_text(mt.group("code")),
            "item_name": norm_text(mt.group("name")),
            "qty": qty,
            "uom": norm_text(mt.group("uom")),
        })

    if not lines:
        frappe.throw(_(
            "Không đọc được dòng hàng nào trên phiếu. Nếu đây là bản SCAN (ảnh) thì "
            "phải xin lại file PDF gốc từ hệ thống Win."))

    # Số phiếu và số đơn hàng đều là số dài; `label_value` trả float nên phải
    # đưa về chuỗi KHÔNG có phần lẻ, nếu không '4193445648.0' sẽ không khớp
    # `custom_po_` nào cả.
    def _as_no(v):
        if v is None:
            return None
        return cstr(cint(v)) if float(v).is_integer() else cstr(v)

    dup = [c for c in {l["item_code"] for l in lines}
           if sum(1 for l in lines if l["item_code"] == c) > 1]

    return {
        "grn_no": _as_no(grn_no),
        "po_no": _as_no(po_no),
        "grn_date": grn_date,
        "store": store,
        "vendor_code": vendor,
        "lines": lines,
        "n_lines": len(lines),
        "total_qty": round(sum(l["qty"] for l in lines), 3),
        # Mã hàng trùng trên CÙNG một phiếu: Win tách hai dòng cho cùng mã là
        # chuyện có thể xảy ra (hai lô). Phải cộng dồn khi đối soát chứ không
        # lấy dòng đầu — nhưng vẫn nói ra để người biết.
        "duplicate_codes": sorted(dup),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Đối soát với hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

def _fields_ready():
    """Hai field của SITE. Thiếu cái nào thì nói ĐÚNG cái đó."""
    miss = []
    if not frappe.db.has_column("Sales Invoice", SI_PO_FIELD):
        miss.append("`Sales Invoice.%s` (số PO)" % SI_PO_FIELD)
    if not frappe.db.has_column("Sales Invoice Item", SII_CODE_FIELD):
        miss.append("`Sales Invoice Item.%s` (mã hàng Win)" % SII_CODE_FIELD)
    return miss


def _invoices_for_po(company, po_no):
    """Hóa đơn mang đúng số PO này. Gồm cả bản NHÁP — đối soát là việc TRƯỚC khi
    ghi sổ, chặn ở `docstatus = 1` thì đúng lúc cần lại không có gì để soi."""
    return frappe.db.sql("""
        SELECT si.name, si.docstatus, si.posting_date, si.customer, si.customer_name,
               si.grand_total
        FROM `tabSales Invoice` si
        WHERE si.company = %(company)s AND si.docstatus < 2
          AND si.{po} = %(po)s
        ORDER BY si.docstatus DESC, si.name
    """.format(po=SI_PO_FIELD), {"company": company, "po": po_no}, as_dict=True)


def _si_items(names):
    if not names:
        return []
    keys = {"n%d" % i: n for i, n in enumerate(names)}
    return frappe.db.sql("""
        SELECT sii.parent, sii.item_code, sii.item_name, sii.qty, sii.uom,
               sii.{code} AS ma_win
        FROM `tabSales Invoice Item` sii
        WHERE sii.parent IN ({ph})
    """.format(code=SII_CODE_FIELD,
               ph=", ".join("%%(n%d)s" % i for i in range(len(names)))),
        keys, as_dict=True)


def match_grn(grn, company):
    """Đối soát nội dung phiếu với hóa đơn mang cùng số PO."""
    miss = _fields_ready()
    if miss:
        return {"ok": False, "blocked": True, "invoices": [], "lines": [],
                "reason": _("Site chưa có field {0} — không đối soát được mã hàng. "
                            "Khai field rồi thử lại.").format(" và ".join(miss))}

    po = cstr(grn.get("po_no") or "")
    if not po:
        return {"ok": False, "blocked": True, "invoices": [], "lines": [],
                "reason": _("Phiếu không có `Số đơn hàng` — không có khóa nào để nối "
                            "sang hóa đơn.")}

    invoices = _invoices_for_po(company, po)
    if not invoices:
        return {"ok": False, "blocked": False, "invoices": [], "lines": [],
                "reason": _(
                    "Chưa có hóa đơn nào mang số PO {0}. Đó có thể là đúng — Win chỉ "
                    "cho xuất hóa đơn SAU khi có phiếu này. Lập hóa đơn rồi đối soát "
                    "lại trước khi ghi sổ.").format(po)}

    items = _si_items([i.name for i in invoices])

    # Cộng dồn theo MÃ WIN ở cả hai phía: một mã có thể nằm trên nhiều dòng
    # (Win tách lô; hóa đơn tách theo đơn giá). So từng dòng rời là báo lệch giả.
    want = {}
    for l in grn["lines"]:
        e = want.setdefault(l["item_code"], {"qty": 0.0, "name": l["item_name"]})
        e["qty"] += flt(l["qty"])
    got = {}
    no_code = []
    for it in items:
        code = norm_text(it.ma_win)
        if not code:
            no_code.append({"invoice": it.parent, "item_code": it.item_code,
                            "item_name": it.item_name, "qty": flt(it.qty)})
            continue
        e = got.setdefault(code, {"qty": 0.0, "item_code": it.item_code,
                                  "name": it.item_name, "invoices": set()})
        e["qty"] += flt(it.qty)
        e["invoices"].add(it.parent)

    out = []
    for code in sorted(set(want) | set(got)):
        w = want.get(code)
        g = got.get(code)
        if w and g:
            status = MATCH_OK if abs(w["qty"] - g["qty"]) <= QTY_EPS else MATCH_QTY
        elif w:
            status = MATCH_MISSING_SI
        else:
            status = MATCH_EXTRA_SI
        out.append({
            "ma_win": code,
            "name": (w or g).get("name"),
            "qty_grn": round(w["qty"], 3) if w else None,
            "qty_si": round(g["qty"], 3) if g else None,
            "diff": round((g["qty"] if g else 0) - (w["qty"] if w else 0), 3),
            "item_code": g.get("item_code") if g else None,
            "invoices": sorted(g["invoices"]) if g else [],
            "status": status,
            "status_label": MATCH_LABEL[status],
        })

    counts = {k: sum(1 for x in out if x["status"] == k) for k in MATCH_LABEL}
    warnings = []
    if no_code:
        warnings.append(
            "%d dòng trên hóa đơn KHÔNG có mã hàng Win (`%s` để trống) — không đối "
            "soát được, và Win đối chiếu theo mã của họ. Điền mã rồi soát lại."
            % (len(no_code), SII_CODE_FIELD))
    if grn.get("duplicate_codes"):
        warnings.append(
            "Phiếu có mã hàng lặp trên nhiều dòng (%s) — đã CỘNG DỒN theo mã khi đối "
            "soát." % ", ".join(grn["duplicate_codes"]))
    if len(invoices) > 1:
        warnings.append(
            "%d hóa đơn cùng mang số PO %s — đã cộng dồn cả %d. Kiểm xem có hóa đơn "
            "nào lập trùng không." % (len(invoices), po, len(invoices)))
    draft = [i.name for i in invoices if cint(i.docstatus) == 0]
    if draft:
        warnings.append("Có %d hóa đơn còn NHÁP (%s) — đối soát trước khi ghi sổ là "
                        "đúng lúc." % (len(draft), ", ".join(draft[:3])))

    return {
        "ok": counts[MATCH_QTY] == 0 and counts[MATCH_MISSING_SI] == 0
              and counts[MATCH_EXTRA_SI] == 0 and not no_code,
        "blocked": False,
        "reason": "",
        "invoices": invoices,
        "lines": out,
        "counts": counts,
        "items_without_code": no_code,
        "warnings": warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Whitelisted — CHỈ ĐỌC
# ═══════════════════════════════════════════════════════════════════════════

MAX_UPLOAD_MB = 12


@frappe.whitelist()
def preview(content, company=None):
    """Đọc phiếu nhập kho + đối soát với hóa đơn cùng PO. KHÔNG ghi gì."""
    guard_mt()
    _require_tables()
    company = _company(company)

    raw = decode_upload(content)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw(_("File quá {0} MB").format(MAX_UPLOAD_MB))

    grn = read_grn(content)
    result = match_grn(grn, company)
    pending = _pending_for_po(company, grn.get("po_no"))
    return {
        "grn": grn,
        "match": result,
        "pending": pending,
        "plan_hash": _grn_hash(grn),
        # Nút "ghi vào đợt giao" chỉ hiện cho người mà backend thật sự cho ghi —
        # bày nút rồi từ chối là bắt người dùng đoán vì sao.
        "can_attach": is_chief(),
        "note": _(
            "Phiếu nhập kho KHÔNG có tiền — chỉ có số lượng. Đối soát được PO, mã hàng "
            "và số lượng; thành tiền vẫn lấy theo đơn giá trên hóa đơn. Lệch số lượng "
            "thì xuất hóa đơn theo SỐ THỰC NHẬN, phần chênh làm xuất trả (SOP §2.2)."),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Ghi số phiếu vào đợt giao đang chờ
# ═══════════════════════════════════════════════════════════════════════════

def _grn_hash(grn):
    """Vân tay phiếu — client phải gửi lại đúng cái vừa xem trước."""
    blob = json.dumps(
        [cstr(grn.get("grn_no")), cstr(grn.get("po_no")), cstr(grn.get("grn_date")),
         [[l["item_code"], round(flt(l["qty"]), 3)] for l in grn.get("lines") or []]],
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _pending_for_po(company, po_no):
    """Đợt giao đang theo dõi mang đúng số PO này (nếu có)."""
    if not po_no or not frappe.db.table_exists(PENDING_DOCTYPE):
        return None
    rows = frappe.db.sql("""
        SELECT name, customer, customer_name, po_no, delivery_date, total_amount,
               status, grn_no, grn_date
        FROM `tab%s`
        WHERE company = %%(company)s AND po_no = %%(po)s AND status != %%(cancelled)s
        ORDER BY modified DESC
    """ % PENDING_DOCTYPE,
        {"company": company, "po": cstr(po_no), "cancelled": STATUS_CANCELLED},
        as_dict=True)
    return rows[0] if rows else None


@frappe.whitelist()
def attach_grn(content, expected_hash, company=None):
    """Đánh dấu đợt giao là ĐÃ NHẬN và ghi số phiếu nhập kho vào đó.

    CHỈ ghi lên `MT Win Pending`. Không đụng hóa đơn: lệch số lượng là việc con
    người quyết (xuất theo số thực nhận, phần chênh làm xuất trả) — máy sửa hóa
    đơn thay người ở đây là sai cả SOP lẫn nguyên tắc của app.
    """
    guard_manager()
    _require_tables()
    company = _company(company)

    if not frappe.db.table_exists(PENDING_DOCTYPE):
        frappe.throw(_("Site chưa có bảng {0}. Chạy `bench migrate` rồi thử lại.")
                     .format(PENDING_DOCTYPE))

    raw = decode_upload(content)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw(_("File quá {0} MB").format(MAX_UPLOAD_MB))

    grn = read_grn(content)
    if not expected_hash or expected_hash != _grn_hash(grn):
        frappe.throw(_(
            "Nội dung phiếu đã đổi so với lúc xem trước. Xem lại rồi mới ghi."))

    po = cstr(grn.get("po_no") or "")
    row = _pending_for_po(company, po)
    if not row:
        frappe.throw(_(
            "Không có đợt giao nào đang theo dõi mang số PO {0}. Thêm đợt giao đó vào "
            "danh sách chờ trước, rồi mới gắn phiếu nhập kho — nếu không thì số phiếu "
            "này không treo vào đâu cả.").format(po))

    doc = frappe.get_doc(PENDING_DOCTYPE, row.name)
    # Đã gắn một số phiếu KHÁC rồi thì dừng lại hỏi người. Ghi đè âm thầm là xóa
    # mất vết của lần nhận trước mà không ai biết.
    if cstr(doc.grn_no) and cstr(doc.grn_no) != cstr(grn["grn_no"]):
        frappe.throw(_(
            "Đợt giao PO {0} đã gắn phiếu nhập kho {1}; phiếu vừa tải lên là {2}. "
            "Hai phiếu cho cùng một PO thì phải xem lại — sửa tay trên đợt giao nếu "
            "đúng là thay phiếu."
        ).format(po, doc.grn_no, grn["grn_no"]))

    doc.grn_no = grn["grn_no"]
    if grn.get("grn_date"):
        doc.grn_date = grn["grn_date"]
    if doc.status in (STATUS_DELIVERING,):
        doc.status = STATUS_RECEIVED
    doc.save()
    frappe.db.commit()
    return {
        "name": doc.name,
        "po_no": doc.po_no,
        "status": doc.status,
        "grn_no": doc.grn_no,
        "grn_date": cstr(doc.grn_date or ""),
        "message": _("Đã ghi phiếu nhập kho {0} vào đợt giao PO {1} — trạng thái: {2}.")
                   .format(doc.grn_no, doc.po_no, doc.status),
    }
