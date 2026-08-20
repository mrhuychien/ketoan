"""mt_rebate_pdf — đọc `Rebate Settlement` của Emart (THISO Retail), định dạng PDF.

Đây là chuỗi DUY NHẤT gửi cơ sở tính chiết khấu bằng PDF. Bốn chuỗi kia gửi
Excel nên `mt_discount_read` đọc bằng `read_sheets`; file này là đường vào thứ
hai của cùng một hợp đồng dữ liệu — trả về ĐÚNG bộ khóa mà
`mt_discount_read.read_discount_basis` mong đợi.

════════════════════════════════════════════════════════════════════════════
VÌ SAO ĐỌC ĐƯỢC PDF NÀY MÀ KHÔNG PHẢI PDF NÀO CŨNG ĐỌC ĐƯỢC
════════════════════════════════════════════════════════════════════════════

File do hệ thống Emart in ra, có TẦNG VĂN BẢN thật (không phải ảnh scan). Chữ
đọc ra kèm tọa độ, nên dựng lại được từng dòng. File scan sẽ ra 0 ký tự — khi
đó parser DỪNG và nói rõ, tuyệt đối không đoán.

════════════════════════════════════════════════════════════════════════════
BA TÍN HIỆU ĐỘC LẬP NÓI "AI XUẤT HÓA ĐƠN" — PHẢI KHỚP CẢ BA
════════════════════════════════════════════════════════════════════════════

SOP §2.5: dòng `Rebate` (Monthly Discount 3%) thì MÌNH xuất hóa đơn theo quy
trình BKCK; các dòng `Fee` (~8%) thì EMART xuất → hạch toán JE phí. Lấy nhầm
một dòng `Fee` vào bảng kê là xuất hóa đơn cho khoản mình không được xuất, VÀ
ghi nhận hai lần cùng một khoản.

File in ra ba dấu hiệu, hoàn toàn độc lập với nhau:

  1. Cột `Rebate type`  -> `Rebate` / `Fee` / `Support`
  2. Tiền tố mã khoản   -> `AP%…` (Emart NỢ mình → mình xuất)
                           `AR%…` (Emart THU mình → Emart xuất)
  3. Cột `Settlement Type` -> `Vendor Tax Invoice` / `E-mart Tax Invoice`

Ba cái phải nói cùng một điều. Lệch nhau → DỪNG và nêu đích danh dòng đó, chứ
không lấy hai chọi một: chuỗi đổi quy ước mà mình vẫn suy theo đa số thì sai
âm thầm, còn dừng lại thì kế toán đọc file bằng mắt trong ba mươi giây.

════════════════════════════════════════════════════════════════════════════
SỐ KIỂM TRA — LẤY TỪ CHÍNH FILE, KHÔNG TỰ NGHĨ RA
════════════════════════════════════════════════════════════════════════════

Đo trên file thật (kỳ 07.2026, NCC 100968):

  · Σ dòng Rebate  = `Rebate Amount:`  = 2.737.350
  · Σ dòng Fee     = `Fee Amount:`     = 8.212.050
  · Σ dòng Support = `Support Amount:` = 0
  · Σ mọi dòng     = `Total`           = 10.949.400
  · `Net Amount`   = `Invoice Amount` − `Return Amount` = 91.245.000 − 0
  · từng dòng: `Net Amount` × `Rate` = `Settlement Amount`
       91.245.000 × 3% = 2.737.350 · × 2% = 1.824.900 · × 1% = 912.450

Sáu phép, ba trong số đó (Rebate/Fee/Support) chia nhau đúng tập dòng mà phép
thứ tư (Total) cộng lại — nên thêm/bớt/xếp nhầm loại một dòng là ít nhất một
phép sẽ kêu.
"""

import re

import frappe
from frappe import _
from frappe.utils import cstr, flt

from ketoan.api.mt_advice import _check, to_date, to_number

# ═══════════════════════════════════════════════════════════════════════════
# Đọc chữ + tọa độ
# ═══════════════════════════════════════════════════════════════════════════

PDF_MAGIC = b"%PDF"

# Hai chữ cách nhau quá ngần này (điểm in) thì coi là hai từ. Đo trên file thật:
# khoảng cách trong một từ < 0,6pt, giữa hai từ > 1,5pt.
WORD_GAP = 1.2

# Hai chữ lệch nhau dưới ngần này thì coi là CÙNG MỘT DÒNG. Nhãn và số của
# `Return Amount:` lệch baseline 1,2pt trong file thật — để 1,5 là tách đôi,
# nhãn mất số của nó.
LINE_TOL = 3.0

# Ghép nhãn với giá trị bên phải: chấp nhận lệch dọc tới ngần này.
PAIR_TOL = 5.0

MAX_PAGES = 20


def is_pdf(raw: bytes) -> bool:
    """Nhận PDF theo CHỮ KÝ BYTE, không theo đuôi tên file.

    Cùng lý do như `read_sheets` của `mt_advice`: file mẫu Emart có đuôi `.PDF`
    VIẾT HOA, và chuỗi khác từng gửi `.Xls` viết hoa. Đuôi tên là thứ người gõ,
    chữ ký byte là thứ máy ghi.
    """
    return bool(raw) and raw[:4] == PDF_MAGIC


def _require_lib():
    try:
        from pdfminer.high_level import extract_pages  # noqa: F401
    except ImportError:
        frappe.throw(_(
            "Máy chủ chưa cài thư viện đọc PDF (`pdfminer.six`). Chạy "
            "`bench setup requirements` rồi thử lại."))


def read_words(raw: bytes):
    """PDF bytes -> [{text, x0, x1, y}] theo từng trang, gốc tọa độ ở đáy trang.

    Trả về danh sách TRANG, mỗi trang là danh sách TỪ đã sắp theo dòng rồi tới
    cột. Không gộp thành chuỗi ở đây: tầng trên cần tọa độ để ghép nhãn với giá
    trị nằm bên phải nó.
    """
    _require_lib()
    import io

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar

    pages = []
    for pno, page in enumerate(extract_pages(io.BytesIO(raw), laparams=LAParams())):
        if pno >= MAX_PAGES:
            frappe.throw(_("File PDF quá {0} trang — kiểm lại xem có đúng file "
                           "Rebate Settlement không.").format(MAX_PAGES))
        chars = []

        def walk(obj):
            if isinstance(obj, LTChar):
                chars.append(obj)
            elif hasattr(obj, "__iter__"):
                for child in obj:
                    walk(child)

        walk(page)

        rows = {}
        for c in chars:
            rows.setdefault(round(c.y0 / LINE_TOL), []).append(c)

        words = []
        for key in sorted(rows, reverse=True):          # trên xuống dưới
            line = sorted(rows[key], key=lambda c: c.x0)
            buf, x0, x1, ys = "", None, None, []

            def flush():
                if buf.strip():
                    words.append({"text": buf, "x0": x0, "x1": x1,
                                  "y": sum(ys) / len(ys)})

            for c in line:
                ch = c.get_text()
                # HAI cách một PDF tách từ, phải xử CẢ HAI.
                #
                # (a) khoảng trống hình học — không có glyph nào giữa hai chữ;
                # (b) glyph khoảng trắng THẬT — file Emart in ra kiểu này, các
                #     chữ liền mạch về tọa độ nên (a) không bao giờ kích hoạt.
                #
                # Chỉ dùng (a) thì `Store:   ( All-Store Thiso Retail )` ra MỘT
                # từ duy nhất, và mọi phép dò nhãn trên dòng đó im lặng trượt.
                if ch.isspace() or (x1 is not None and c.x0 - x1 > WORD_GAP):
                    flush()
                    buf, x0, ys = "", None, []
                    if ch.isspace():
                        x1 = c.x1
                        continue
                if x0 is None:
                    x0 = c.x0
                buf += ch
                x1 = c.x1
                ys.append(c.y0)
            flush()
        pages.append([w for w in words if w["text"].strip()])

    if not pages or not any(pages):
        frappe.throw(_(
            "Không đọc được chữ nào trong file PDF. Nhiều khả năng đây là bản "
            "SCAN (ảnh) chứ không phải file Emart in ra — xin lại file gốc."))
    return pages


def lines_of(words):
    """Từ -> dòng văn bản, dùng để dò nhãn và tách dòng dữ liệu."""
    rows = {}
    for w in words:
        rows.setdefault(round(w["y"] / LINE_TOL), []).append(w)
    out = []
    for key in sorted(rows, reverse=True):
        ws = sorted(rows[key], key=lambda w: w["x0"])
        out.append((" ".join(w["text"] for w in ws).strip(), ws))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Dò nhãn -> giá trị
# ═══════════════════════════════════════════════════════════════════════════

def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", cstr(s).lower())


_NUM = re.compile(r"^-?[\d.,]+$")


def label_value(words, *labels):
    """Số nằm NGAY BÊN PHẢI một nhãn, cùng dòng. None nếu không có nhãn đó.

    Dò theo NHÃN, không theo tọa độ cứng: khối đầu trang của Emart xếp hai cột
    (`Invoice Amount` trái, `Rebate Amount:` phải) và vị trí đổi theo độ dài tên
    nhà cung cấp.
    """
    want = [_norm(x) for x in labels]
    for text, ws in lines_of(words):
        norm = _norm(text)
        for w in want:
            if w not in norm:
                continue
            # tìm chỗ nhãn kết thúc trên dòng này
            acc = ""
            end_x = None
            for i, word in enumerate(ws):
                acc += _norm(word["text"])
                if acc.endswith(w):
                    end_x = word["x1"]
                    rest = ws[i + 1:]
                    break
            if end_x is None:
                continue
            for word in rest:
                if abs(word["y"] - ws[0]["y"]) > PAIR_TOL:
                    continue
                if _NUM.match(word["text"].strip()):
                    return to_number(word["text"])
            # nhãn có mà số không nằm cùng dòng -> KHÔNG lấy bừa số dòng khác
            return None
    return None


_DATE = re.compile(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b")


def _first_date(text):
    """Ngày ĐẦU TIÊN trong đoạn chữ.

    `Settled date:` và `Settled Period:` nằm CÙNG một dòng, nên phần chữ bên
    phải nhãn thứ nhất còn dính cả nhãn thứ hai. Đưa nguyên chuỗi cho `to_date`
    thì ra None — mất ngày chốt kỳ mà không ai báo.
    """
    m = _DATE.search(cstr(text))
    return to_date(m.group(1)) if m else None


def _in_parens(text):
    """Phần trong ngoặc: `( All-Store Thiso Retail ) Currency: VND` -> tên điểm."""
    m = re.search(r"\(([^)]*)\)", cstr(text))
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else (cstr(text).strip() or None)


def label_text(words, *labels):
    """Phần chữ còn lại bên phải một nhãn, cùng dòng."""
    want = [_norm(x) for x in labels]
    for text, ws in lines_of(words):
        norm = _norm(text)
        for w in want:
            if w not in norm:
                continue
            acc = ""
            for i, word in enumerate(ws):
                acc += _norm(word["text"])
                if acc.endswith(w):
                    return " ".join(x["text"] for x in ws[i + 1:]).strip()
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Dòng dữ liệu
# ═══════════════════════════════════════════════════════════════════════════

KIND_REBATE = "Rebate"
KIND_FEE = "Fee"
KIND_SUPPORT = "Support"
KINDS = (KIND_REBATE, KIND_FEE, KIND_SUPPORT)

SETTLE_OURS = "vendortaxinvoice"      # mình xuất hóa đơn
SETTLE_THEIRS = "emarttaxinvoice"     # Emart xuất hóa đơn

# Tiền tố mã khoản. Đo trên file thật: `AP%Monthly Discount` (mình xuất) và
# `AR%Product Dist.Opt.` (Emart xuất). AP = mình được nhận, AR = mình phải trả.
PREFIX_OURS = "AP%"
PREFIX_THEIRS = "AR%"

HEADER_LABELS = ("Rebate type", "Rate", "Net Amount", "Settlement Type", "Settlement Date")

# `Rebate AP%Monthly Discount 3% 91.245.000 2.737.350 Vendor Tax Invoice 31-07-2026`
#  ^kind  ^mã và tên khoản      ^tỷ lệ ^cơ sở      ^tiền         ^ai xuất  ^ngày
ROW_RE = re.compile(
    r"^(?P<kind>Rebate|Fee|Support)\s+"
    r"(?P<code>\S+?%\S*(?:\s+\S+)*?)\s+"
    r"(?P<rate>-?[\d.,]+)\s*%\s+"
    r"(?P<base>-?[\d.,]+)\s+"
    r"(?P<amount>-?[\d.,]+)\s+"
    r"(?P<settle>[A-Za-z][A-Za-z\- ]*?)\s+"
    r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})\s*$"
)


def _assert_header(words):
    """Bảng phải có ĐỦ nhãn cột đã biết. Thiếu một nhãn = Emart đổi mẫu.

    Không dùng nhãn để suy ra chỉ số cột (dòng dữ liệu đọc bằng văn phạm token),
    nhưng vẫn PHẢI kiểm: mẫu đổi mà parser vẫn chạy êm là cách mất tiền im lặng.
    `Settlement Amount` cố ý không nằm trong danh sách — nhãn đó bị xuống dòng,
    chữ `Amount` rơi sang dòng kế.
    """
    blob = " ".join(_norm(t) for t, _ws in lines_of(words))
    missing = [lb for lb in HEADER_LABELS if _norm(lb) not in blob]
    if missing:
        frappe.throw(_("File PDF không có các nhãn cột {0} — không phải mẫu "
                       "Rebate Settlement của Emart, hoặc Emart đã đổi mẫu.")
                     .format(", ".join(missing)))


def _who_issues(kind, code, settle):
    """Ba tín hiệu -> 'ours' | 'theirs'. Lệch nhau thì DỪNG, không lấy đa số."""
    by_settle = {SETTLE_OURS: "ours", SETTLE_THEIRS: "theirs"}.get(_norm(settle))
    up = cstr(code).upper()
    by_prefix = ("ours" if up.startswith(PREFIX_OURS)
                 else "theirs" if up.startswith(PREFIX_THEIRS) else None)
    by_kind = ("ours" if kind == KIND_REBATE
               else "theirs" if kind == KIND_FEE else None)

    seen = {x for x in (by_settle, by_prefix, by_kind) if x}
    if not seen:
        frappe.throw(_("Dòng '{0} {1}' không có dấu hiệu nào cho biết AI xuất hóa "
                       "đơn — không đưa vào bảng kê khi chưa rõ.").format(kind, code))
    if len(seen) > 1:
        frappe.throw(_(
            "Dòng '{0} {1} / {2}' mâu thuẫn: loại khoản nói {3}, mã khoản nói {4}, "
            "cột Settlement Type nói {5}. Emart nhiều khả năng đã đổi quy ước — "
            "kiểm bằng mắt rồi báo lại, KHÔNG đoán theo đa số."
        ).format(kind, code, settle, by_kind or "?", by_prefix or "?", by_settle or "?"))
    return seen.pop()


def parse_rebate_settlement(raw: bytes):
    """PDF bytes -> cơ sở tính chiết khấu Emart. THUẦN ĐỌC, không ghi gì."""
    pages = read_words(raw)
    words = [w for pg in pages for w in pg]
    _assert_header(words)

    # CỐ Ý KHÔNG đọc tên nhà cung cấp trên file. `Vendor:` ở đây là CHÍNH MÌNH
    # (Công ty CP Hoàng Giang) — đã một lần suýt in tên mình vào ô "Đơn vị mua
    # hàng" của BKCK vì đọc nhãn tương tự trong file Central Retail. Bên mua lấy
    # từ `Customer` / `MT Store`, không lấy từ file của chuỗi.
    #
    # `(100968)` là MÃ NCC của mình tại Emart — cái này thì cần, để nối đúng
    # khách hàng. Lấy mã đầu tiên trong ngoặc ở khối đầu trang; mã phòng ban
    # `(202000000)` nằm sau nên không bị chọn nhầm.
    vendor_code = None
    for text, _w in lines_of(words):
        m = re.search(r"\((\d{5,})\)", text)
        if m:
            vendor_code = m.group(1)
            break

    period = label_text(words, "Settled Period:")
    settled_date = _first_date(label_text(words, "Settled date:"))
    store = _in_parens(label_text(words, "Store:"))

    dec_invoice = label_value(words, "Invoice Amount")
    dec_return = label_value(words, "Return Amount:")
    dec_net = label_value(words, "Net Amount")
    dec_rebate = label_value(words, "Rebate Amount:")
    dec_fee = label_value(words, "Fee Amount:")
    dec_support = label_value(words, "Support Amount:")
    dec_total = label_value(words, "Total")

    ours, theirs, bad = [], [], []
    for text, _ws in lines_of(words):
        mt = ROW_RE.match(text.strip())
        if not mt:
            continue
        kind = mt.group("kind")
        code = mt.group("code").strip()
        rate = to_number(mt.group("rate"))
        base = to_number(mt.group("base"))
        amount = to_number(mt.group("amount"))
        settle = mt.group("settle").strip()
        if base is None or amount is None or rate is None:
            bad.append(text)
            continue

        side = _who_issues(kind, code, settle)
        item = {
            "kind": kind, "code": code, "rate": rate,
            "base_amount": base, "amount": amount,
            "settlement_type": settle,
            "settlement_date": to_date(mt.group("date")),
            "side": side,
            "source_row": text,
        }
        (ours if side == "ours" else theirs).append(item)

    if bad:
        frappe.throw(_("Có {0} dòng khoản trừ đọc được chữ nhưng KHÔNG đọc được số: {1}")
                     .format(len(bad), " | ".join(bad[:3])))
    if not ours and not theirs:
        frappe.throw(_("Không đọc được dòng khoản nào trong bảng — kiểm lại file."))

    return {
        "vendor_code": vendor_code,
        "period": period,
        "settled_date": settled_date,
        "store": store,
        "declared": {
            "invoice_amount": dec_invoice, "return_amount": dec_return,
            "net_amount": dec_net, "rebate_amount": dec_rebate,
            "fee_amount": dec_fee, "support_amount": dec_support,
            "total": dec_total,
        },
        "ours": ours,
        "theirs": theirs,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Chuyển sang bộ khóa chung của `mt_discount_read`
# ═══════════════════════════════════════════════════════════════════════════

# Lệch cho phép khi soát `cơ sở × tỷ lệ = tiền`. Emart làm tròn tới đồng.
RATE_EPS = 1.0


def to_basis(raw: bytes, chain_key="emart"):
    """Bọc `parse_rebate_settlement` thành đúng hình dạng parser Excel trả về."""
    res = parse_rebate_settlement(raw)
    dec = res["declared"]

    sum_ours = sum(flt(x["amount"]) for x in res["ours"])
    sum_fee = sum(flt(x["amount"]) for x in res["theirs"] if x["kind"] == KIND_FEE)
    sum_sup = sum(flt(x["amount"]) for x in res["theirs"] if x["kind"] == KIND_SUPPORT)
    sum_all = sum_ours + sum(flt(x["amount"]) for x in res["theirs"])

    checks = [
        _check("Chiết khấu mình xuất (Rebate Amount)", dec["rebate_amount"], round(sum_ours, 2)),
        _check("Phí Emart xuất (Fee Amount)", dec["fee_amount"], round(sum_fee, 2)),
        _check("Hỗ trợ (Support Amount)", dec["support_amount"], round(sum_sup, 2)),
        _check("Tổng mọi khoản (Total)", dec["total"], round(sum_all, 2)),
    ]
    # `Net Amount` = `Invoice Amount` − `Return Amount`. Đây là CƠ SỞ tính chiết
    # khấu; đọc nhầm nó thì mọi dòng đều sai cùng một tỷ lệ mà tổng vẫn khớp.
    if dec["invoice_amount"] is not None and dec["return_amount"] is not None:
        checks.append(_check("Giá trị ghi nhận = hóa đơn − hàng trả",
                             dec["net_amount"],
                             round(flt(dec["invoice_amount"]) - flt(dec["return_amount"]), 2)))

    # Từng dòng: cơ sở × tỷ lệ = tiền. Phép này bắt lỗi đọc lệch cột mà tổng
    # không bắt được (đổi chỗ hai dòng cùng tiền thì tổng vẫn đúng).
    off = [x for x in res["ours"] + res["theirs"]
           if abs(flt(x["base_amount"]) * flt(x["rate"]) / 100.0 - flt(x["amount"])) > RATE_EPS]
    checks.append(_check("Số dòng lệch 'cơ sở × tỷ lệ = tiền'", 0.0, float(len(off))))

    warnings = []
    if not res["ours"]:
        warnings.append("Kỳ này Emart KHÔNG có khoản chiết khấu nào mình được xuất "
                        "hóa đơn — chỉ có phí Emart xuất. Không lập bảng kê.")
    if dec["net_amount"] is None:
        warnings.append("Không đọc được 'Net Amount' — không kiểm chéo được cơ sở tính.")

    # Emart KHÔNG chia theo hóa đơn hay theo điểm bán: cả kỳ là MỘT dòng trên
    # `All-Store Thiso Retail`. Bảng kê vì vậy có đúng một dòng — đó là hình
    # dạng thật của chứng từ, không phải parser đọc thiếu.
    rows = []
    for x in res["ours"]:
        rows.append({
            "group_key": cstr(res["vendor_code"] or "emart"),
            "buyer_code": res["vendor_code"],
            "store_code": None,
            "store_name": res["store"],
            "inv_series": None, "inv_no": None, "inv_no_norm": None,
            "inv_date": res["settled_date"],
            "base_amount": flt(x["base_amount"]),
            "discount_amount": flt(x["amount"]),
            "rate": flt(x["rate"]),
            "note": "%s %s (%s)" % (x["kind"], x["code"], x["settlement_type"]),
            "needs_review": False,
            "source_row": x["source_row"],
        })

    groups = []
    if rows:
        groups.append({
            "key": rows[0]["group_key"],
            "buyer_code": res["vendor_code"],
            "group_label": None,
            "n_rows": len(rows), "n_invoices": 0,
            "base_amount": round(sum(flt(r["base_amount"]) for r in rows), 2),
            "discount_amount": round(sum(flt(r["discount_amount"]) for r in rows), 2),
        })

    excluded = [{
        "reason": "Emart xuất hóa đơn cho mình — hạch toán JE phí, KHÔNG đưa vào bảng kê",
        "kind": x["kind"], "code": x["code"], "rate": x["rate"],
        "amount": flt(x["amount"]), "settlement_type": x["settlement_type"],
    } for x in res["theirs"]]

    return {
        "mode": "rate_on_total",
        "rate": (rows[0]["rate"] if len(rows) == 1 else None),
        "vendor_code": res["vendor_code"],
        "rows": rows,
        "groups": groups,
        "excluded": excluded,
        "checks": checks,
        "warnings": warnings,
        "meta": {"period": res["period"], "settled_date": res["settled_date"],
                 "store": res["store"], "declared": dec},
    }
