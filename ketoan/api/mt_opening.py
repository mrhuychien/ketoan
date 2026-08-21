"""mt_opening — đọc file Excel THEO DÕI CÔNG NỢ đang dùng, để nhập SỐ DƯ ĐẦU KỲ.

Kế toán MT theo dõi công nợ trên bảy file Excel (mỗi chuỗi một file), có file
chạy từ 2018. Muốn bỏ hẳn Excel thì phải mang được số dư đang treo vào hệ thống,
nếu không ngày đầu tiên dùng phần mềm là ngày mọi con số công nợ đều sai.

════════════════════════════════════════════════════════════════════════════
SAI HAI CHIỀU NGƯỢC NHAU — PHẢI XỬ CẢ HAI
════════════════════════════════════════════════════════════════════════════

Kênh MT suy "còn nợ" = `grand_total` của Sales Invoice trừ tiền đã trả cộng từ
dòng bảng kê. Với dữ liệu lịch sử, cả hai vế đều thiếu:

  · Hóa đơn ĐÃ có trong ERPNext, đã trả xong từ trước khi có phần mềm — không có
    bảng kê nào ghi lại. Hệ thống thấy nguyên `grand_total` là chưa trả.
    → CÔNG NỢ BỊ THỔI PHỒNG.

  · Hóa đơn CHƯA có trong ERPNext (cũ hơn ngày go-live) mà vẫn còn treo tiền.
    Hệ thống không biết nó tồn tại.
    → CÔNG NỢ BỊ HỤT.

Hai lỗi này KHÔNG bù nhau và không được xử chung một kiểu. File Excel đã có sẵn
cả `Số đã trả` lẫn `Số còn nợ` cho từng hóa đơn — nhập đúng hai cột đó là xử
được cả hai chiều.

════════════════════════════════════════════════════════════════════════════
BẢY FILE, BẢY BỐ CỤC — ĐO TRÊN FILE THẬT, KHÔNG ĐOÁN
════════════════════════════════════════════════════════════════════════════

Khối tiền thì giống nhau ở cả bảy, nằm trên DÒNG HEADER PHỤ:

    Dịch vụ | VAT x% | TỔNG | Số đã trả | [HTL] | Số còn nợ

Nhưng mọi thứ khác thì khác: dòng header ở r4/r5/r6 tùy file, cột số hóa đơn khi
thì nhãn `SỐ HĐ` khi thì `HĐ xóa bỏ` / `HĐ SD/xóa bỏ`, VAT khi 8% khi 10%, và
AEON/Mega có thêm khối chiết khấu chen ngang. Vì vậy dò theo NHÃN, tuyệt đối
không hardcode chỉ số cột.

════════════════════════════════════════════════════════════════════════════
BA BẪY ĐÃ ĐO ĐƯỢC TRÊN CHÍNH BẢY FILE NÀY
════════════════════════════════════════════════════════════════════════════

1. TIÊU ĐỀ TRONG FILE NÓI DỐI. File `CÔNG NỢ BIGC 2026.xlsx` ghi ô A2 là
   `CÔNG NỢ VINCOM` — trùng hệt file WinCommerce (chép file rồi sửa thiếu).
   ⇒ TUYỆT ĐỐI không nhận diện chuỗi bằng tiêu đề. Nhận bằng CHỮ KÝ CỘT, và
   không chắc thì để người chọn.

2. DÒNG TỔNG CỘNG CỦA CHÍNH FILE CÓ THỂ SAI. Ô tổng VAT của Saigon Co.op mang
   công thức `=SUM(F9:F340)` trong khi bốn cột kia cộng tới dòng 3755 — nó chỉ
   cộng 332 trên 2.477 dòng, thiếu 1.429.358.702đ. Từng dòng thì `Dịch vụ + VAT
   = TỔNG` đúng cả 2.477 dòng.
   ⇒ Số kiểm tra phải soát TỪNG CỘT RIÊNG và báo đích danh cột lệch, không gộp
   thành một câu "file không khớp" rồi bỏ cả file. Cột VAT lệch KHÔNG chặn việc
   nhập số dư: thứ cần nhập là `TỔNG`, `Số đã trả`, `Số còn nợ` — cả ba khớp.

3. CÓ DÒNG NỢ ÂM. AEON có 2 dòng `Số còn nợ` âm (tổng −736.020đ) — hàng trả lại
   / trả thừa. Cộng riêng phần dương ra 176.580.000đ, cộng cả dấu ra 175.843.980đ
   đúng bằng số file in.
   ⇒ Cộng THEO DẤU. Lọc `> 0` rồi cộng là thổi phồng công nợ đúng bằng hai lần
   phần âm.

MODULE NÀY CHỈ ĐỌC. Ghi là việc của `commit_opening` ở tầng trên.
"""

import re

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

# Sai số cho phép khi soát tổng. Tiền VND nguyên đồng; 1đ chỉ để chống rác dấu
# phẩy động vì file có ô lưu 781046413.5999999.
MONEY_EPS = 1.0

# Trần dòng: file lớn nhất hiện có 2.946 dòng. Vượt xa mức này gần như chắc chắn
# là đọc nhầm sheet — DỪNG chứ không cắt bớt.
MAX_ROWS = 20000

# Dò header trong bao nhiêu dòng đầu. File sâu nhất có header ở r7 (AEON).
HEADER_LIMIT = 15


def _norm(label) -> str:
    """Nhãn cột -> khóa so khớp: bỏ dấu, bỏ mọi ký tự không phải chữ/số."""
    return re.sub(r"[^a-z0-9]+", "", strip_tones(label))


# Nhãn CỘT TIỀN trên dòng header phụ -> khóa chuẩn. Đo trên cả bảy file.
MONEY_LABELS = {
    "dichvu": "net",
    "tong": "gross",
    "sodatra": "paid",
    "soconno": "remaining",
    # Hàng trả lại: Emart/Mega ghi `HTL`, AEON ghi cả cụm.
    "htl": "returns",
    "hangtralaiphisdwebid": "returns",
}

# Nhãn CỘT ĐỊNH DANH, nằm trên dòng header CHÍNH (ngay trên dòng tiền) hoặc trên
# dòng tổng. Một số nhãn chỉ xuất hiện ở đúng một chuỗi.
ID_LABELS = {
    "datehd": "inv_date",
    "sohd": "inv_no",
    # Central Retail + WinCommerce để SỐ hóa đơn dưới nhãn "HĐ xóa bỏ" /
    # "HĐ SD/xóa bỏ" — nhãn khó hiểu nhưng ĐÓ LÀ cột số hóa đơn đang dùng.
    "hdxoabo": "inv_no",
    "hdsdxoabo": "inv_no",
    "hdthaythe": "inv_replaced_by",
    "thaythe": "inv_replaced_by",
    "xoabo": "inv_no",
    "tenkhachhang": "party",
    "diadiem": "party",       # LOTTE gọi cột này là "Địa điểm"
    "ngaytt": "pay_date",
    "ghichu": "note",
}


def _find_money_header(grid):
    """Dòng header PHỤ: dòng chứa đủ `Dịch vụ` + `TỔNG` + `Số đã trả` + `Số còn nợ`.

    Dò theo NHÃN chứ không theo chỉ số: header nằm ở r5 (Mega, Win), r6 (BigC,
    Emart, LOTTE, Co.op) hoặc r7 (AEON) tùy file, và kỳ sau kế toán chèn thêm một
    dòng tiêu đề là gãy hết nếu hardcode.
    """
    for r in range(1, min(len(grid), HEADER_LIMIT) + 1):
        cols = {}
        for c, txt in enumerate(_row_texts(grid[r - 1]), start=1):
            k = _norm(txt)
            if not k:
                continue
            if k.startswith("vat"):
                cols.setdefault("vat", c)
            elif k in MONEY_LABELS:
                cols.setdefault(MONEY_LABELS[k], c)
        if {"net", "gross", "paid", "remaining"} <= set(cols):
            return r, cols
    return None, {}


def _find_id_cols(grid, money_row, cols):
    """Cột định danh nằm ở dòng TRÊN dòng tiền (và đôi khi ở dòng tổng).

    Quét lên 2 dòng và xuống 2 dòng quanh dòng tiền:
      · LOTTE để `HĐ xóa bỏ` / `HĐ thay thế` ở DÒNG TỔNG (r7), dưới dòng tiền.
      · AEON để `XÓA BỎ` / `THAY THẾ` cũng ở dòng tổng (r8).
      · Co.op lặp nguyên dòng header chính xuống dòng tiền.
    Nhãn tìm được TRƯỚC thắng, nên `SỐ HĐ` ở dòng chính không bị `XÓA BỎ` ở dòng
    tổng ghi đè.
    """
    out = dict(cols)
    for rr in (money_row - 1, money_row - 2, money_row, money_row + 1, money_row + 2):
        if rr < 1 or rr > len(grid):
            continue
        for c, txt in enumerate(_row_texts(grid[rr - 1]), start=1):
            k = _norm(txt)
            if k in ID_LABELS and ID_LABELS[k] not in out:
                out[ID_LABELS[k]] = c
    return out


def _find_total_row(grid, money_row, cols):
    """Dòng TỔNG CỘNG = dòng ĐẦU TIÊN sau header có số ở cột `Dịch vụ`.

    Không dò bằng chữ "TỔNG CỘNG": AEON không in chữ đó, dòng tổng của nó chỉ có
    số (và hai chữ `XÓA BỎ` / `THAY THẾ` lạc vào).
    """
    for r in range(money_row + 1, min(money_row + 5, len(grid)) + 1):
        if to_number(_g(grid, r, cols["net"])) is not None:
            return r
    return None


# Chữ ký cột để nhận diện chuỗi. Mỗi bộ phải ĐỦ và chỉ trúng một chuỗi.
#
# KHÔNG dùng tiêu đề trong file: `CÔNG NỢ BIGC 2026.xlsx` ghi A2 là
# `CÔNG NỢ VINCOM`, trùng hệt file WinCommerce.
# `need` = phải CÓ đủ; `absent` = phải KHÔNG có.
#
# VÌ SAO cần vế phủ định: Mega Market và Emart dùng chung `HTL` + `VAT 10%` +
# `SỐ HĐ` + `Ngày TT`, nên chữ ký chỉ-có-vế-khẳng-định làm file Mega trúng CẢ HAI
# và hệ trả "không chắc". Thứ phân biệt là khối chiết khấu `Hỗ trợ tiếp thị 1%`
# — chỉ Mega có. Nói ra bằng vế phủ định thay vì xếp thứ tự ưu tiên rồi lấy cái
# đầu: xếp thứ tự là đoán, phủ định là đo.
CHAIN_SIGNS = {
    "AEON": (("qc4", "the2", "inan2", "htdh3"), ()),
    "Central Retail": (("doanhso", "hdxoabo"), ()),
    "Emart": (("htl", "vat10", "sohd", "ngaytt"), ("hotrotiepthi1",)),
    "LOTTE": (("diadiem", "sodudauky"), ()),
    "Mega Market": (("hotrotiepthi1", "hotrothem3"), ()),
    "Saigon Co.op": (("tenkhachhang", "vat8", "sohd", "ghichu"),
                     ("hdxoabo", "hdsdxoabo", "qc4")),
    "WinCommerce": (("hdsdxoabo", "ngayguichungtuthanhtoan"), ()),
}


def detect_chain(grid):
    """Nhận diện chuỗi từ CHỮ KÝ CỘT. Không chắc -> None để người chọn tay."""
    blob = set()
    for row in grid[:HEADER_LIMIT]:
        for txt in _row_texts(row):
            k = _norm(txt)
            if k:
                blob.add(k)
    hits = [name for name, (need, absent) in CHAIN_SIGNS.items()
            if all(w in blob for w in need) and not any(w in blob for w in absent)]
    return hits[0] if len(hits) == 1 else None


def _pick_sheet(sheets):
    """Sheet công nợ = sheet có dòng header tiền. Nhiều sheet trúng -> lấy cái đầu.

    File thật có sheet phụ (`Sheet1` rỗng, `hd ghi giam`, `HOA DON TRA LAI`).
    Sheet `hd ghi giam` KHÔNG có khối `Dịch vụ/TỔNG/Số đã trả/Số còn nợ` nên
    không lọt vào đây — nhưng vẫn trả về danh sách sheet bỏ qua để nói ra.
    """
    live = []
    for name, grid in sheets:
        r, cols = _find_money_header(grid)
        if r:
            live.append((name, grid, r, cols))
    if not live:
        frappe.throw(_(
            "Không tìm thấy bảng công nợ trong file. Cần một sheet có đủ bốn cột "
            "`Dịch vụ`, `TỔNG`, `Số đã trả`, `Số còn nợ` trên cùng một dòng."))
    skipped = [n for n, _g2 in sheets if n != live[0][0]]
    return live[0], skipped


def read_opening(content, chain=None):
    """base64 -> số dư đầu kỳ đọc từ file Excel theo dõi công nợ. THUẦN ĐỌC."""
    # `allow_wide`: file Emart khai 16.375 cột trong khi cột có dữ liệu xa nhất
    # là 17 — bề rộng đó là rác định dạng. Đã đo: 0 ô có dữ liệu ngoài cột 200.
    sheets = read_sheets(content, allow_wide=True)
    (sheet_name, grid, money_row, money_cols), skipped = _pick_sheet(sheets)

    cols = _find_id_cols(grid, money_row, money_cols)
    total_row = _find_total_row(grid, money_row, money_cols)
    if not total_row:
        frappe.throw(_("Không tìm thấy dòng TỔNG CỘNG ngay dưới header — không có "
                       "số kiểm tra nào để đối chiếu, KHÔNG nhập."))

    detected = detect_chain(grid)
    chain = norm_text(chain) or detected
    if not chain:
        frappe.throw(_(
            "Không nhận ra chuỗi từ bố cục file. Hãy chọn chuỗi bằng tay.\n"
            "(Lưu ý: tiêu đề ghi trong file KHÔNG đáng tin — file BigC ghi là "
            "'CÔNG NỢ VINCOM'.)"))

    declared = {k: to_number(_g(grid, total_row, c)) for k, c in money_cols.items()}

    rows = []
    warnings = []
    for r in range(total_row + 1, len(grid) + 1):
        vals = {k: to_number(_g(grid, r, c)) for k, c in money_cols.items()}
        if all(v is None for v in vals.values()):
            continue
        if len(rows) >= MAX_ROWS:
            frappe.throw(_("File có hơn {0} dòng — gần như chắc chắn đọc nhầm sheet. "
                           "KHÔNG nhập gì.").format(MAX_ROWS))

        inv_no = norm_text(_g(grid, r, cols["inv_no"])) if "inv_no" in cols else ""
        rows.append({
            "source_row": r,
            "party": norm_text(_g(grid, r, cols["party"])) if "party" in cols else "",
            "inv_no": inv_no or None,
            "inv_no_norm": norm_inv_no(inv_no) or None,
            "inv_replaced_by": (norm_text(_g(grid, r, cols["inv_replaced_by"]))
                                if "inv_replaced_by" in cols else None) or None,
            "inv_date": to_date(_g(grid, r, cols["inv_date"])) if "inv_date" in cols else None,
            "pay_date": to_date(_g(grid, r, cols["pay_date"])) if "pay_date" in cols else None,
            "note": (norm_text(_g(grid, r, cols["note"])) if "note" in cols else "") or None,
            # GIỮ NGUYÊN DẤU ở mọi cột tiền — xem bẫy số 3 ở đầu module.
            "net": flt(vals.get("net") or 0),
            "vat": flt(vals.get("vat") or 0),
            "gross": flt(vals.get("gross") or 0),
            "paid": flt(vals.get("paid") or 0),
            "returns": flt(vals.get("returns") or 0),
            "remaining": flt(vals.get("remaining") or 0),
        })

    computed = {k: round(sum(flt(x[k]) for x in rows), 2)
                for k in ("net", "vat", "gross", "paid", "returns", "remaining")}

    # Số kiểm tra: TỪNG CỘT RIÊNG, nêu đích danh cột lệch. Xem bẫy số 2 — ô tổng
    # VAT của Co.op cộng thiếu 2.145 dòng, mà ba cột quyết định số dư thì đúng.
    checks = [
        _check("Tiền dịch vụ (chưa VAT)", declared.get("net"), computed["net"]),
        _check("Tiền VAT", declared.get("vat"), computed["vat"]),
        _check("TỔNG tiền hóa đơn", declared.get("gross"), computed["gross"]),
        _check("Số đã trả", declared.get("paid"), computed["paid"]),
        _check("SỐ CÒN NỢ", declared.get("remaining"), computed["remaining"]),
    ]
    if "returns" in money_cols:
        checks.append(_check("Hàng trả lại", declared.get("returns"), computed["returns"]))

    # Ba cột này quyết định số dư mang sang. Lệch ở đây thì DỪNG.
    critical = {"TỔNG tiền hóa đơn", "Số đã trả", "SỐ CÒN NỢ"}
    bad_critical = [c for c in checks if c["label"] in critical and not c["ok"]]
    soft = [c for c in checks if c["label"] not in critical and not c["ok"]]
    for c in soft:
        warnings.append(
            "Cột '%s' trong file tự lệch: dòng TỔNG CỘNG ghi %s nhưng cộng các dòng ra "
            "%s (lệch %s). Thường là công thức SUM trong file bị hụt dải — đã gặp ở "
            "Saigon Co.op. KHÔNG chặn việc nhập số dư vì cột này không quyết định số dư."
            % (c["label"], "{:,.0f}".format(c["declared"] or 0),
               "{:,.0f}".format(c["computed"]), "{:,.0f}".format(c["diff"] or 0)))

    n_neg = sum(1 for x in rows if flt(x["remaining"]) < -MONEY_EPS)
    if n_neg:
        warnings.append(
            "%d dòng có `Số còn nợ` ÂM (tổng %s đ) — hàng trả lại hoặc trả thừa. "
            "Số dư mang sang cộng THEO DẤU, không lọc bỏ dòng âm."
            % (n_neg, "{:,.0f}".format(sum(flt(x["remaining"]) for x in rows
                                           if flt(x["remaining"]) < 0))))
    if skipped:
        warnings.append("Bỏ qua %d sheet khác trong file: %s."
                        % (len(skipped), ", ".join(skipped[:5])))
    if "inv_no" not in cols:
        warnings.append("File KHÔNG có cột số hóa đơn — không nối được với hóa đơn "
                        "trong ERPNext, mọi dòng sẽ là nợ đầu kỳ độc lập.")

    open_rows = [x for x in rows if abs(flt(x["remaining"])) > MONEY_EPS]

    return {
        "chain": chain,
        "chain_detected": detected,
        "sheet": sheet_name,
        "skipped_sheets": skipped,
        "header_row": money_row,
        "total_row": total_row,
        "columns": {k: v for k, v in sorted(cols.items())},
        "rows": rows,
        "open_rows": open_rows,
        "declared": declared,
        "computed": computed,
        "checks": checks,
        # `reconciled` chỉ nói về BA CỘT quyết định số dư. Cột VAT lệch được ghi
        # vào `warnings` và vẫn cho nhập — xem bẫy số 2.
        "reconciled": not bad_critical,
        "blocking": [c["label"] for c in bad_critical],
        "warnings": warnings,
        "totals": {
            "n_rows": len(rows),
            "n_open": len(open_rows),
            "opening_debt": round(sum(flt(x["remaining"]) for x in rows), 2),
            "paid_history": round(sum(flt(x["paid"]) for x in rows), 2),
            "gross": computed["gross"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Whitelisted — CHỈ ĐỌC
# ═══════════════════════════════════════════════════════════════════════════

MAX_PREVIEW = 60
MAX_UPLOAD_MB = 20


@frappe.whitelist()
def preview(content, chain=None):
    """Xem trước số dư đầu kỳ đọc từ file Excel theo dõi công nợ. KHÔNG ghi gì."""
    guard_mt()
    raw = decode_upload(content)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw(_("File quá {0} MB").format(MAX_UPLOAD_MB))

    res = read_opening(content, chain=chain)
    out = dict(res)
    # Xem trước ưu tiên dòng CÒN NỢ — đó là thứ mang sang; dòng đã tất toán chỉ
    # cần con số tổng.
    out["sample"] = res["open_rows"][:MAX_PREVIEW]
    out.pop("rows", None)
    out.pop("open_rows", None)
    from ketoan.install import MT_CHAINS

    out["chains"] = list(MT_CHAINS)
    return out
