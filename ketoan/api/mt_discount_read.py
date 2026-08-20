# -*- coding: utf-8 -*-
"""mt_discount_read — tầng ĐỌC file cơ sở tính chiết khấu của chuỗi siêu thị.

Đây là chiều NGƯỢC LẠI với `mt_advice`: ở kia chuỗi báo "tôi đã trả anh bao
nhiêu", ở đây chuỗi báo "doanh số của anh là bao nhiêu, chiết khấu bấy nhiêu" —
và MÌNH là bên phải xuất hóa đơn chiết khấu (§3 SOP, quy trình BKCK).

Module này THUẦN ĐỌC: không ghi database, không tạo chứng từ. Con người xem
bảng kê, đối chiếu, rồi mới quyết định xuất hóa đơn.

═══════════════════════════════════════════════════════════════════════════════
HAI CÁCH TÍNH CHIẾT KHẤU — KHÁC NHAU THẬT, ĐÃ ĐO
═══════════════════════════════════════════════════════════════════════════════

    MODE_PER_LINE     Central Retail — CỘNG TỪNG DÒNG cột `RB_VALUE`
    MODE_RATE_TOTAL   LOTTE, Mega    — TỶ LỆ × TỔNG

Không phải hai cách viết của cùng một phép tính. Đo trên mẫu BKCK 261 của BigC:

    Tổng Cộng                  715.000.265
    'Số tiền chiết khấu 3.35%'  23.952.537   ← BigC in ra
    715.000.265 × 3,35%       = 23.952.508,88 ← tự tính lại   LỆCH 28,12đ

BigC làm tròn TỪNG DÒNG. Còn LOTTE thì `tỷ lệ × tổng` khớp tuyệt đối trên cả 7
kỳ mẫu. Áp nhầm cách không chỉ sai vài chục đồng — nó là sai NGUYÊN TẮC: một bên
là con số CHUỖI ĐÃ CHỐT, một bên là con số mình tự tính lại.

═══════════════════════════════════════════════════════════════════════════════
NGUYÊN TẮC (kế thừa nguyên từ hợp đồng đọc file thanh toán)
═══════════════════════════════════════════════════════════════════════════════

* **Không đoán tên cột.** Dò header theo NHÃN, mọi nhãn dưới đây đọc từ file thật.
* **Không đoán tỷ lệ.** File không in tỷ lệ thì trả `rate=None` và tầng trên
  phải lấy từ cấu hình hợp đồng; không có cả hai thì DỪNG.
* **Không tự dựng cơ sở tính từ Sales Invoice của mình.** Cơ sở là số CHUỖI đã
  chốt; chênh lệch với hóa đơn của mình chính là thứ phải đi truy (§3.2 SOP).
* **Dòng bị loại phải được BÁO kèm tiền**, không biến mất im lặng.

Kết quả trả về:

    {
      "chain_key", "chain", "vendor_code",
      "mode":      "per_line" | "rate_on_total",
      "rate":      3.35 | None,          # None = file không in, lấy từ cấu hình
      "groups":    [ {key, buyer_code, group_label, n_rows, n_invoices,
                      base_amount, discount_amount|None} ],
      "rows":      [ {group_key, store_code, store_name, inv_series, inv_no,
                      inv_date, base_amount, discount_amount|None, rate|None,
                      note, source_row, needs_review} ],
      "excluded":  [ {reason, n_rows, amount} ],
      "checks":    [ {label, declared, computed, diff, ok} ],
      "warnings":  [...],
    }
"""

import frappe
from frappe import _
from frappe.utils import cstr, flt

from ketoan.api._guard import guard_mt
from ketoan.api.mt_advice import (
    _check,
    _g,
    _row_texts,
    decode_upload,
    read_sheets,
    strip_tones,
    to_date,
    to_number,
)
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_text,
)

MODE_PER_LINE = "per_line"
MODE_RATE_TOTAL = "rate_on_total"

MODE_LABEL = {
    MODE_PER_LINE: "Cộng chiết khấu từng dòng (số của chuỗi)",
    MODE_RATE_TOTAL: "Tỷ lệ × tổng doanh số",
}

# Khóa ASCII -> nhãn chuỗi. Dùng lại đúng danh sách của `mt_advice.CHAIN_LABEL`
# nhưng CHỈ những chuỗi mà MÌNH xuất hóa đơn chiết khấu (§2 SOP).
DISCOUNT_CHAIN_LABEL = {
    "central_retail": "Central Retail",
    "lotte": "LOTTE",
    "mega_market": "Mega Market",
    # Emart gửi PDF chứ không gửi Excel — đọc bằng `mt_rebate_pdf`, không đi qua
    # `read_sheets`. Xem nhánh PDF trong `read_discount_basis`.
    "emart": "Emart",
}

# Sai số cho phép khi soát 'cơ sở × tỷ lệ = chiết khấu' TỪNG DÒNG. Chuỗi làm
# tròn tới đồng nên lệch dưới 1đ/dòng là bình thường; quá 1đ mới là đọc nhầm cột.
RATE_EPS = 1.0


def _norm(label) -> str:
    """Nhãn cột -> khóa so khớp: bỏ dấu, bỏ mọi ký tự không phải chữ/số."""
    import re
    return re.sub(r"[^a-z0-9]+", "", strip_tones(label))


def _find_header(grid, *required, start=1, limit=40):
    """Dòng header chứa ĐỦ các nhãn bắt buộc. Trả (r 1-based, {khóa: cột}).

    Dò theo NHÃN chứ không hardcode chỉ số dòng: mẫu Winmart để header ở r2,
    Central Retail ở r1 — và kỳ sau chuỗi thêm một dòng tiêu đề là gãy hết.
    """
    want = [_norm(x) for x in required]
    for r in range(start, min(len(grid), start + limit - 1) + 1):
        cols = {_norm(t): c for c, t in enumerate(_row_texts(grid[r - 1]), start=1) if t}
        if all(w in cols for w in want):
            return r, cols
    return None, {}


def _col(cols, *names):
    for n in names:
        c = cols.get(_norm(n))
        if c:
            return c
    return None


def _gv(grid, r, c):
    """`_g` chấp nhận cột None (nhãn không có trong file) -> None."""
    return _g(grid, r, c) if c else None


def _row(**kw):
    """Một dòng cơ sở tính chiết khấu, BỘ KHÓA CHUẨN dùng chung cho mọi chuỗi."""
    return {
        "group_key": kw.get("group_key") or "",
        "buyer_code": kw.get("buyer_code") or None,
        "store_code": kw.get("store_code") or None,
        "store_name": kw.get("store_name") or None,
        "inv_series": kw.get("inv_series") or None,
        "inv_no": kw.get("inv_no") or None,
        "inv_no_norm": norm_inv_no(kw.get("inv_no") or "") or None,
        "inv_date": kw.get("inv_date"),
        # GIỮ NGUYÊN DẤU: dòng hàng trả là số âm và phải trừ thẳng vào cơ sở.
        "base_amount": flt(kw.get("base_amount")),
        # None = file KHÔNG in chiết khấu -> tầng trên tính bằng tỷ lệ cấu hình.
        "discount_amount": (None if kw.get("discount_amount") is None
                            else flt(kw["discount_amount"])),
        "rate": (None if kw.get("rate") is None else flt(kw["rate"])),
        "note": kw.get("note") or None,
        "needs_review": bool(kw.get("needs_review")),
        "source_row": kw.get("source_row"),
    }


def _sheet(sheets):
    """Sheet dữ liệu duy nhất. Nhiều sheet có nội dung -> báo, không chọn bừa."""
    live = [(n, g) for n, g in sheets if any(any(_row_texts(row)) for row in g)]
    if not live:
        frappe.throw(_("File không có sheet nào chứa dữ liệu"))
    return live[0][0], live[0][1], [n for n, _g2 in live[1:]]


# ═══════════════════════════════════════════════════════════════════════════
# Central Retail — 1.770 dòng × 17 cột, sheet 'Data'
# ═══════════════════════════════════════════════════════════════════════════

# Nhóm chiết khấu MÌNH được xuất hóa đơn. Ba nhóm còn lại (`Fee for EBS`,
# `Fee for store`, `Support for store`) do EB xuất — chúng đã được xử ở MT2-D
# dưới dạng dòng `D1` của file thanh toán. Lấy cả bốn nhóm là (a) xuất hóa đơn
# cho khoản mình không được xuất, và (b) ghi nhận hai lần cùng một khoản.
CR_OUR_GROUP = "Discount for store"


def parse_central_retail(sheets, chain_key):
    """Doanh số Central Retail -> cơ sở tính chiết khấu, gộp theo PHÁP NHÂN EB.

    BẪY 1 — BỐN NHÓM TRONG MỘT FILE. Chỉ `Discount for store` là của mình
    (177/1.770 dòng trên file mẫu, 25.324.144đ trong tổng 125.108.775đ của cả
    bốn nhóm).

    BẪY 2 — `IM_VALUE` LẶP LẠI Ở MỌI NHÓM. Cùng 755.943.625 xuất hiện ở cả
    `Discount for store` lẫn `Fee for EBS`; `Fee for store` ra 2.267.830.875 vì
    có 3 tỷ lệ. Cộng `IM_VALUE` toàn file là nhân doanh số lên SÁU LẦN. Vì vậy
    phải LỌC NHÓM TRƯỚC rồi mới cộng.

    BẪY 3 — CHIẾT KHẤU LÀ TỔNG CỦA TỪNG DÒNG, không phải tỷ lệ × tổng. BigC làm
    tròn từng dòng; tự tính lại từ tổng lệch ~30đ. Xem `MODE_PER_LINE`.
    """
    name, grid, extra = _sheet(sheets)
    warnings = []
    if extra:
        warnings.append("File còn sheet %s chưa được đọc — kiểm tay xem có bỏ sót không."
                        % ", ".join("'%s'" % x for x in extra))

    hr, cols = _find_header(grid, "RB_GROUP", "RB_VALUE", "INVOICENO", "IM_VALUE")
    if not hr:
        frappe.throw(_("Không phải file doanh số Central Retail (thiếu cột "
                       "RB_GROUP / RB_VALUE / INVOICENO / IM_VALUE)"))

    c_grp = _col(cols, "RB_GROUP")
    c_inv = _col(cols, "INVOICENO")
    c_im = _col(cols, "IM_VALUE")
    c_rb = _col(cols, "RB_VALUE")
    c_rate = _col(cols, "RB_RATE")
    c_sup = _col(cols, "SUPPLIER")
    c_supn = _col(cols, "SUPPLIERNAME")
    c_site = _col(cols, "SERSITE")
    c_siten = _col(cols, "SITE_NAME")
    c_po = _col(cols, "PO")
    c_date = _col(cols, "RECEPTION_DATE")
    c_unit = _col(cols, "RATE_UNIT")

    rows = []
    other = {}
    rates = set()
    bad_rate_rows = 0
    for r in range(hr + 1, len(grid) + 1):
        grp = norm_text(_gv(grid, r, c_grp))
        if not grp:
            continue
        im = to_number(_gv(grid, r, c_im))
        rb = to_number(_gv(grid, r, c_rb))
        if grp != CR_OUR_GROUP:
            # Nhóm của EB — không sinh dòng, nhưng phải ĐẾM và CỘNG để hiện ra:
            # kế toán cần thấy khoản nào EB sẽ xuất hóa đơn cho mình.
            e = other.setdefault(grp, {"row_kind": grp, "n_rows": 0, "amount": 0.0})
            e["n_rows"] += 1
            e["amount"] += flt(rb)
            continue
        if im is None or rb is None:
            warnings.append("Dòng %d: thiếu IM_VALUE hoặc RB_VALUE — bỏ qua, "
                            "tổng bên dưới sẽ thiếu dòng này." % r)
            continue

        rate = to_number(_gv(grid, r, c_rate))
        unit = norm_text(_gv(grid, r, c_unit))
        if rate is not None:
            rates.add(rate)
            # Soát từng dòng bằng chính ba cột của file. Đây là số kiểm tra DUY
            # NHẤT mà file này có — nó không in dòng tổng nào.
            if "percent" in strip_tones(unit) or not unit:
                if abs(flt(im) * flt(rate) / 100.0 - flt(rb)) > RATE_EPS:
                    bad_rate_rows += 1

        raw = norm_text(_gv(grid, r, c_inv))
        series, no = ("", raw)
        if "|" in raw:
            series, no = raw.split("|", 1)
        buyer = norm_text(_gv(grid, r, c_sup))
        rows.append(_row(
            group_key=buyer,
            buyer_code=buyer,
            store_code=norm_text(_gv(grid, r, c_site)),
            store_name=norm_text(_gv(grid, r, c_siten)),
            inv_series=series.strip(), inv_no=no.strip(),
            inv_date=to_date(_gv(grid, r, c_date)),
            base_amount=im, discount_amount=rb, rate=rate,
            # `Ghi chú` của BKCK Central Retail là SỐ PO — mẫu in ra đúng như vậy.
            note=norm_text(_gv(grid, r, c_po)),
            needs_review=not series.strip(),
            source_row=r))

    if bad_rate_rows:
        warnings.append("%d dòng có `IM_VALUE × RB_RATE` lệch quá 1đ so với `RB_VALUE` — "
                        "nghi đọc nhầm cột, kiểm tay trước khi lập bảng kê." % bad_rate_rows)
    if len(rates) > 1:
        warnings.append("Nhóm '%s' có %d tỷ lệ khác nhau (%s) — bảng kê sẽ in tỷ lệ nào? "
                        "Kiểm hợp đồng." % (CR_OUR_GROUP, len(rates),
                                            ", ".join(str(x) for x in sorted(rates))))

    groups = _group(rows)
    # Nhãn nhóm CỐ Ý để trống. Cột `SUPPLIERNAME` của file là TÊN CỦA MÌNH
    # ('CONG TY CO PHAN HOANG GIANG'), không phải bên mua — bên mua là pháp nhân
    # EB. Điền tên mình vào ô 'Đơn vị mua hàng' của bảng kê là sai trên một
    # chứng từ hai bên ký. Tên bên mua lấy từ Customer/MT Store ở tầng lập bảng kê.
    #
    # Mã nhóm (`SUPPLIER` = 3003172 / 3006634) VẪN đúng và cần: nó phân biệt
    # mình đang bán dưới pháp nhân EB nào (§2.1 SOP).
    our_vendor = next((norm_text(_gv(grid, x["source_row"], c_supn)) for x in rows
                       if norm_text(_gv(grid, x["source_row"], c_supn))), None)

    # Số kiểm tra DUY NHẤT mà file này có: ba cột `IM_VALUE`, `RB_RATE`,
    # `RB_VALUE` phải nhất quán với nhau trên TỪNG dòng. File không in dòng tổng
    # nào, nên không có chốt nào khác.
    checks = [_check("Dòng có `IM_VALUE × RB_RATE` khớp `RB_VALUE`",
                     float(len(rows)), float(len(rows) - bad_rate_rows))]

    return {
        "mode": MODE_PER_LINE,
        "rate": (sorted(rates)[0] if len(rates) == 1 else None),
        "rows": rows,
        "groups": groups,
        "excluded": sorted(other.values(), key=lambda x: -abs(x["amount"])),
        "checks": checks,
        "warnings": warnings,
        "vendor_code": our_vendor and next(
            (r["buyer_code"] for r in rows if r["buyer_code"]), None),
        "sheet": name,
    }


# ═══════════════════════════════════════════════════════════════════════════
# LOTTE — 227 dòng × 17 cột, chi tiết theo SẢN PHẨM, gộp theo SIÊU THỊ
# ═══════════════════════════════════════════════════════════════════════════

LT_NOT_RECEIVED = "NOT RECEIVE"


def parse_lotte(sheets, chain_key):
    """Doanh số LOTTE -> cơ sở tính chiết khấu, gộp theo TỪNG SIÊU THỊ.

    BẪY 1 — `Fill in date = NOT RECEIVE` LÀ HÀNG CHƯA NHẬN (§2.3 SOP). Trên file
    mẫu: 35/227 dòng, 25.621.900đ. Tính vào cơ sở là xuất hóa đơn chiết khấu cho
    hàng LOTTE chưa nhận. Chính 35 dòng đó cũng là 35 dòng KHÔNG có `Invoice No`
    — hai dấu hiệu trùng khớp tuyệt đối, nên chốt lại bằng cả hai.

    BẪY 2 — `Pur fg = hàng trả lại` thì GIỮ, không loại: số đã ÂM sẵn và phải
    trừ thẳng vào cơ sở (10 dòng, −20.586.100đ trên file mẫu).

    BẪY 3 — `Invoice No` LÀ SỐ HÓA ĐƠN CỦA MÌNH (`00000984`), không phải của
    LOTTE. Đúng khuôn 8 chữ số mà BKCK in ra.

    File KHÔNG in tỷ lệ chiết khấu -> `rate = None`, tầng trên lấy từ hợp đồng.
    """
    name, grid, extra = _sheet(sheets)
    warnings = []
    if extra:
        warnings.append("File còn sheet %s chưa được đọc — kiểm tay."
                        % ", ".join("'%s'" % x for x in extra))

    hr, cols = _find_header(grid, "Invoice No", "Amt", "Str cd", "Fill in date")
    if not hr:
        frappe.throw(_("Không phải file doanh số LOTTE (thiếu cột "
                       "Invoice No / Amt / Str cd / Fill in date)"))

    c_inv = _col(cols, "Invoice No")
    c_amt = _col(cols, "Amt")
    c_str = _col(cols, "Str cd")
    c_strn = _col(cols, "Str nm")
    c_fill = _col(cols, "Fill in date")
    c_fg = _col(cols, "Pur fg")
    c_date = _col(cols, "Pur dt")
    c_ven = _col(cols, "Ven cd")
    c_tax = _col(cols, "Tax rt")

    rows = []
    excl_nr = {"row_kind": "Hàng CHƯA NHẬN (Fill in date = NOT RECEIVE)",
               "n_rows": 0, "amount": 0.0}
    excl_noinv = {"row_kind": "Không có số hóa đơn (dù đã nhận)",
                  "n_rows": 0, "amount": 0.0}
    vendor, tax_rates = None, set()
    n_return = 0

    for r in range(hr + 1, len(grid) + 1):
        amt = to_number(_gv(grid, r, c_amt))
        if amt is None:
            continue
        fill = norm_text(_gv(grid, r, c_fill)).upper()
        inv = norm_text(_gv(grid, r, c_inv))
        vendor = vendor or norm_text(_gv(grid, r, c_ven))
        tr = to_number(_gv(grid, r, c_tax))
        if tr is not None:
            tax_rates.add(tr)

        if fill == LT_NOT_RECEIVED:
            excl_nr["n_rows"] += 1
            excl_nr["amount"] += flt(amt)
            continue
        if not inv:
            # Đã nhận mà không có số hóa đơn: KHÔNG đưa vào bảng kê (bảng kê là
            # danh sách hóa đơn), nhưng phải báo — đây là tiền có thật.
            excl_noinv["n_rows"] += 1
            excl_noinv["amount"] += flt(amt)
            continue

        store = norm_text(_gv(grid, r, c_str))
        if norm_text(_gv(grid, r, c_fg)) and "tra" in strip_tones(_gv(grid, r, c_fg) or ""):
            n_return += 1
        rows.append(_row(
            group_key=store, buyer_code=store,
            store_code=store, store_name=norm_text(_gv(grid, r, c_strn)),
            # LOTTE không in ký hiệu ở file này — chỉ số hóa đơn.
            inv_series="", inv_no=inv,
            inv_date=to_date(_gv(grid, r, c_date)),
            base_amount=amt, discount_amount=None, rate=None,
            note=norm_text(_gv(grid, r, c_fg)),
            needs_review=False,
            source_row=r))

    if excl_noinv["n_rows"]:
        warnings.append("%d dòng ĐÃ NHẬN nhưng không có số hóa đơn (%s đ) — không vào "
                        "được bảng kê. Truy hóa đơn trước khi xuất chiết khấu."
                        % (excl_noinv["n_rows"], "{:,.0f}".format(excl_noinv["amount"])))
    if len(tax_rates) > 1:
        warnings.append("File có %d thuế suất khác nhau (%s) — bảng kê chiết khấu chỉ in "
                        "MỘT thuế suất." % (len(tax_rates), ", ".join(str(x) for x in sorted(tax_rates))))

    groups = _group(rows)
    for g in groups:
        g["group_label"] = next((x["store_name"] for x in rows
                                 if x["group_key"] == g["key"] and x["store_name"]), None)

    excluded = [e for e in (excl_nr, excl_noinv) if e["n_rows"]]

    # CHỐT TRÙNG KHỚP HAI DẤU HIỆU. Trên file mẫu, 35 dòng `NOT RECEIVE` cũng
    # chính là 35 dòng không có `Invoice No` — hai cột độc lập nói cùng một điều.
    # Đếm lại CẢ HAI một cách độc lập rồi so: lệch nghĩa là LOTTE đổi cách điền,
    # và khi đó việc loại dòng theo `Fill in date` không còn an toàn nữa.
    n_no_inv = 0
    for r in range(hr + 1, len(grid) + 1):
        if to_number(_gv(grid, r, c_amt)) is None:
            continue
        if not norm_text(_gv(grid, r, c_inv)):
            n_no_inv += 1
    checks = [_check("Dòng 'NOT RECEIVE' = dòng không có số hóa đơn",
                     float(n_no_inv), float(excl_nr["n_rows"]))]
    return {
        "mode": MODE_RATE_TOTAL,
        "rate": None,                      # file KHÔNG in tỷ lệ
        "rows": rows,
        "groups": groups,
        "excluded": excluded,
        "checks": checks,
        "warnings": warnings,
        "vendor_code": vendor,
        "n_return_rows": n_return,
        "sheet": name,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Mega Market — 6 dòng × 7 cột
# ═══════════════════════════════════════════════════════════════════════════

def parse_mega(sheets, chain_key):
    """Doanh số Mega Market -> cơ sở tính chiết khấu.

    BẪY — `Invoice No & PO.` ngăn bằng DẤU GẠCH DƯỚI: `1C26THG_00004450`.
    Ba chuỗi trước dùng ba dấu khác nhau (`#` WinCommerce, `|` Central Retail,
    `-` AEON); đây là dấu thứ tư. Tách bằng regex chung là nuốt nhầm.

    File KHÔNG in chiết khấu lẫn tỷ lệ -> tầng trên lấy tỷ lệ từ hợp đồng.
    """
    name, grid, extra = _sheet(sheets)
    warnings = []
    if extra:
        warnings.append("File còn sheet %s chưa được đọc — kiểm tay."
                        % ", ".join("'%s'" % x for x in extra))

    hr, cols = _find_header(grid, "Invoice No & PO.", "Base Amount")
    if not hr:
        frappe.throw(_("Không phải file doanh số Mega Market (thiếu cột "
                       "'Invoice No & PO.' / 'Base Amount')"))

    c_inv = _col(cols, "Invoice No & PO.")
    c_amt = _col(cols, "Base Amount")
    c_store = _col(cols, "Store")
    c_sup = _col(cols, "Supplier Number")
    c_supn = _col(cols, "Supplier Name")
    c_grd = _col(cols, "Good Receiving Date")
    c_cut = _col(cols, "Cut off date")

    rows, vendor, cutoffs = [], None, set()
    for r in range(hr + 1, len(grid) + 1):
        amt = to_number(_gv(grid, r, c_amt))
        raw = norm_text(_gv(grid, r, c_inv))
        if amt is None or not raw:
            continue
        vendor = vendor or norm_text(_gv(grid, r, c_sup))
        cut = to_date(_gv(grid, r, c_cut))
        if cut:
            cutoffs.add(cut)
        series, no = ("", raw)
        if "_" in raw:
            series, no = raw.split("_", 1)
        rows.append(_row(
            group_key=norm_text(_gv(grid, r, c_store)),
            buyer_code=norm_text(_gv(grid, r, c_sup)),
            store_code=norm_text(_gv(grid, r, c_store)),
            # `Supplier Name` là TÊN CỦA MÌNH, không phải tên siêu thị. Để trống
            # còn hơn điền tên mình vào ô tên điểm bán (cùng lỗi đã sửa ở
            # Central Retail). Tên điểm lấy từ `MT Store` theo mã.
            store_name=None,
            inv_series=series.strip(), inv_no=no.strip(),
            inv_date=to_date(_gv(grid, r, c_grd)),
            base_amount=amt, discount_amount=None, rate=None,
            note=("cut-off %s" % cut) if cut else None,
            needs_review=not series.strip(),
            source_row=r))

    if len(cutoffs) > 1:
        warnings.append("File có %d ngày cut-off khác nhau (%s) — mỗi kỳ một bảng kê, "
                        "kiểm lại trước khi gộp." % (len(cutoffs), ", ".join(sorted(cutoffs))))

    groups = _group(rows)

    # File Mega KHÔNG có dòng tổng, không có tỷ lệ, không có cột chiết khấu —
    # nghĩa là KHÔNG có số kiểm tra nào. `reconciled` sẽ là False, và đó là câu
    # trả lời ĐÚNG: "không kiểm được" khác hẳn "đã kiểm và khớp".
    warnings.append("File Mega Market không in dòng tổng, tỷ lệ hay tiền chiết khấu — "
                    "KHÔNG có số kiểm tra nào để đối chiếu. Kế toán phải soi tay tổng "
                    "%s đ trên %d hóa đơn trước khi lập bảng kê."
                    % ("{:,.0f}".format(sum(r["base_amount"] for r in rows)), len(rows)))
    return {
        "mode": MODE_RATE_TOTAL,
        "rate": None,
        "rows": rows,
        "groups": groups,
        "excluded": [],
        "checks": [],
        "warnings": warnings,
        "vendor_code": vendor,
        "sheet": name,
    }


# ═══════════════════════════════════════════════════════════════════════════

def _group(rows):
    """Gộp dòng thành NHÓM = một bảng kê. Mỗi nhóm một pháp nhân/chi nhánh.

    Central Retail gộp theo pháp nhân EB (1 BKCK/pháp nhân), LOTTE tách theo
    từng chi nhánh (1 BKCK/chi nhánh) — §3 SOP. Cùng một phép gộp, khác khóa.
    """
    out = {}
    for r in rows:
        k = cstr(r["group_key"])
        g = out.setdefault(k, {"key": k, "buyer_code": r["buyer_code"],
                               "n_rows": 0, "invoices": set(),
                               "base_amount": 0.0, "discount_amount": 0.0,
                               "has_discount": True})
        g["n_rows"] += 1
        g["base_amount"] += flt(r["base_amount"])
        if r["discount_amount"] is None:
            g["has_discount"] = False
        else:
            g["discount_amount"] += flt(r["discount_amount"])
        if r["inv_no"]:
            g["invoices"].add((r["inv_series"] or "", r["inv_no_norm"] or r["inv_no"]))
    res = []
    for g in out.values():
        res.append({
            "key": g["key"], "buyer_code": g["buyer_code"],
            "group_label": g.get("group_label"),
            "n_rows": g["n_rows"], "n_invoices": len(g["invoices"]),
            "base_amount": round(g["base_amount"], 2),
            # None khi file không in chiết khấu -> tầng trên tính bằng tỷ lệ.
            "discount_amount": (round(g["discount_amount"], 2) if g["has_discount"] else None),
        })
    return sorted(res, key=lambda x: -abs(x["base_amount"]))


PARSERS = {
    "central_retail": parse_central_retail,
    "lotte": parse_lotte,
    "mega_market": parse_mega,
    # Emart KHÔNG nằm ở đây: file của nó là PDF, không có `sheets` để đưa vào.
    # Nó có đường đọc riêng (`PDF_PARSERS`) nhận thẳng bytes.
}

# Chuỗi gửi PDF. Nhận bytes thay vì `sheets`, trả về cùng bộ khóa.
PDF_PARSERS = {
    "emart": lambda raw, key: _rebate_pdf().to_basis(raw, key),
}


def _rebate_pdf():
    # Import trễ: `pdfminer.six` chỉ cần khi thật sự có file PDF, không bắt cả
    # module gãy nếu máy chủ chưa `bench setup requirements`.
    from ketoan.api import mt_rebate_pdf
    return mt_rebate_pdf


def has_parser(key):
    return key in PARSERS or key in PDF_PARSERS


def _detect(sheets):
    """Nhận diện chuỗi từ NHÃN CỘT. Không chắc -> None để người chọn tay."""
    blob = set()
    for _name, grid in sheets:
        for row in grid[:40]:
            blob |= {_norm(t) for t in _row_texts(row) if t}
    signs = {
        "central_retail": ("rbgroup", "rbvalue", "imvalue"),
        "lotte": ("invoiceno", "amt", "strcd", "fillindate"),
        "mega_market": ("invoicenopo", "baseamount"),
        # Emart không qua đây (file PDF, rẽ nhánh trước `read_sheets`).
    }
    hits = [k for k, need in signs.items() if all(w in blob for w in need)]
    return hits[0] if len(hits) == 1 else None


def read_discount_basis(content, chain=None):
    """base64 -> cơ sở tính chiết khấu (xem docstring đầu module). THUẦN ĐỌC."""
    raw = decode_upload(content)

    # NHẬN DẠNG THEO CHỮ KÝ BYTE, không theo đuôi tên file: mẫu Emart có đuôi
    # `.PDF` viết hoa. Phải rẽ TRƯỚC `read_sheets` — đưa PDF vào đó thì thông
    # báo lỗi nói "file Excel hỏng", kế toán đi tìm nhầm chỗ.
    if _rebate_pdf().is_pdf(raw):
        return _read_pdf_basis(raw, chain)

    sheets = read_sheets(content)
    if chain:
        key = _resolve(chain)
        if not key:
            frappe.throw(_("Không có chuỗi tên '{0}' trong danh sách chuỗi mình xuất "
                           "hóa đơn chiết khấu").format(chain))
    else:
        key = _detect(sheets)
        if not key:
            frappe.throw(_("Không nhận ra chuỗi từ file doanh số. Hãy chọn chuỗi bằng tay."))
    if key not in PARSERS:
        frappe.throw(_(
            "Chưa có tầng đọc file doanh số cho chuỗi {0}. Cần một file mẫu thật để "
            "viết — KHÔNG đọc bừa bằng parser chuỗi khác."
        ).format(DISCOUNT_CHAIN_LABEL.get(key, key)))

    res = PARSERS[key](sheets, key)
    rows = res["rows"]
    total_base = sum(flt(r["base_amount"]) for r in rows)
    has_disc = all(r["discount_amount"] is not None for r in rows) and bool(rows)
    total_disc = (sum(flt(r["discount_amount"]) for r in rows) if has_disc else None)

    warnings = list(res.get("warnings") or [])
    if not rows:
        warnings.append("KHÔNG đọc được dòng doanh số nào — không lập được bảng kê.")
    reconciled = bool(res.get("checks")) and all(c["ok"] for c in res["checks"])

    return {
        "chain_key": key,
        "chain": DISCOUNT_CHAIN_LABEL[key],
        "vendor_code": res.get("vendor_code"),
        "mode": res["mode"],
        "mode_label": MODE_LABEL[res["mode"]],
        "rate": res.get("rate"),
        "groups": res["groups"],
        "rows": rows,
        "excluded": res.get("excluded") or [],
        "checks": res.get("checks") or [],
        "reconciled": reconciled,
        "warnings": warnings,
        "totals": {"base_amount": round(total_base, 2),
                   "discount_amount": (None if total_disc is None else round(total_disc, 2)),
                   "n_rows": len(rows), "n_groups": len(res["groups"])},
        "sheets": [{"name": n, "rows": len(g)} for n, g in read_sheets(content)],
    }


def _read_pdf_basis(raw, chain=None):
    """Nhánh PDF. Cùng bộ khóa trả về như nhánh Excel, không thiếu khóa nào."""
    key = _resolve(chain) if chain else None
    if chain and not key:
        frappe.throw(_("Không có chuỗi tên '{0}' trong danh sách chuỗi mình xuất "
                       "hóa đơn chiết khấu").format(chain))
    if key and key not in PDF_PARSERS:
        frappe.throw(_("Chuỗi {0} không gửi file PDF — chọn lại chuỗi hoặc file.")
                     .format(DISCOUNT_CHAIN_LABEL.get(key, key)))
    if not key:
        # Chỉ MỘT chuỗi gửi PDF nên suy ra được; thêm chuỗi PDF thứ hai thì phải
        # dò bằng dấu hiệu trong file, KHÔNG mặc định cái đầu danh sách.
        if len(PDF_PARSERS) != 1:
            frappe.throw(_("Có nhiều chuỗi gửi PDF — hãy chọn chuỗi bằng tay."))
        key = next(iter(PDF_PARSERS))

    res = PDF_PARSERS[key](raw, key)
    rows = res["rows"]
    total_base = sum(flt(r["base_amount"]) for r in rows)
    has_disc = all(r["discount_amount"] is not None for r in rows) and bool(rows)
    total_disc = (sum(flt(r["discount_amount"]) for r in rows) if has_disc else None)

    warnings = list(res.get("warnings") or [])
    if not rows:
        warnings.append("KHÔNG đọc được dòng doanh số nào — không lập được bảng kê.")
    reconciled = bool(res.get("checks")) and all(c["ok"] for c in res["checks"])

    return {
        "chain_key": key,
        "chain": DISCOUNT_CHAIN_LABEL[key],
        "vendor_code": res.get("vendor_code"),
        "mode": res["mode"],
        "mode_label": MODE_LABEL[res["mode"]],
        "rate": res.get("rate"),
        "groups": res["groups"],
        "rows": rows,
        "excluded": res.get("excluded") or [],
        "checks": res.get("checks") or [],
        "reconciled": reconciled,
        "warnings": warnings,
        "totals": {"base_amount": round(total_base, 2),
                   "discount_amount": (None if total_disc is None else round(total_disc, 2)),
                   "n_rows": len(rows), "n_groups": len(res["groups"])},
        # PDF không có sheet. Trả khóa rỗng thay vì bỏ khóa: frontend đọc
        # `res.sheets.length` và sẽ nổ nếu khóa biến mất.
        "sheets": [],
        "meta": res.get("meta") or {},
    }


def _resolve(chain):
    c = norm_text(chain)
    if c in DISCOUNT_CHAIN_LABEL:
        return c
    for k, label in DISCOUNT_CHAIN_LABEL.items():
        if strip_tones(label) == strip_tones(c):
            return k
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Whitelisted — CHỈ ĐỌC
# ═══════════════════════════════════════════════════════════════════════════

MAX_PREVIEW = 50
MAX_UPLOAD_MB = 12


@frappe.whitelist()
def preview(content, chain=None):
    """Xem trước cơ sở tính chiết khấu đọc từ file. KHÔNG ghi gì."""
    guard_mt()
    raw = decode_upload(content)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw(_("File quá {0} MB").format(MAX_UPLOAD_MB))

    res = read_discount_basis(content, chain=chain)
    out = dict(res)
    out["sample"] = res["rows"][:MAX_PREVIEW]
    out["n_rows_total"] = len(res["rows"])
    out.pop("rows", None)
    out["chains"] = [{"key": k, "label": v, "has_parser": has_parser(k)}
                     for k, v in DISCOUNT_CHAIN_LABEL.items()]
    return out
