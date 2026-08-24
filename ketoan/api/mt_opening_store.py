"""mt_opening_store — CẤT số dư đầu kỳ đã đọc, và bật luật tất toán.

`mt_opening.py` chỉ ĐỌC file Excel. Module này là chỗ con số đó thành dữ liệu
trong phần mềm, đi qua ba bước tách bạch:

    1. NHẬP (Nháp)  — đọc file, nối từng dòng sang Sales Invoice, cất lại.
                      Chưa luật nào bật. Công nợ không nhúc nhích.
    2. NỐI TAY      — dòng nào máy không nối được thì người nối, hoặc người
                      đánh dấu 'Bỏ qua' vì đúng là không có hóa đơn tương ứng.
    3. CHỐT         — bật luật: hóa đơn của chuỗi, ngày <= ngày chốt, KHÔNG có
                      trong danh sách  ->  đã thanh toán.

Chia ba bước vì bước 3 là bước làm biến mất hóa đơn khỏi rổ nợ. Gộp nó vào lúc
tải file lên là để một lần bấm nhầm cuốn trôi vài tỷ mà không ai kịp nhìn.

════════════════════════════════════════════════════════════════════════════
VÌ SAO PHẢI NỐI ĐƯỢC HÓA ĐƠN THÌ MỚI CHO CHỐT
════════════════════════════════════════════════════════════════════════════

Luật tất toán chạy theo **hóa đơn ERPNext**, không theo số hóa đơn trong file.
Một dòng còn nợ không nối được Sales Invoice nào thì nó không GIỮ được hóa đơn
nào lại — và đúng hóa đơn đang còn nợ đó rơi vào vế "không có trong danh sách",
tức là bị coi là đã trả. Nợ thật biến mất, im lặng.

Nên `MT Opening Balance.validate` chặn chốt khi còn dòng nhóm `co_hoa_don` chưa
nối và chưa ai bảo bỏ qua. Module này chỉ đưa ra công cụ để giải quyết chúng.

════════════════════════════════════════════════════════════════════════════
KHỚP DÒNG SANG HÓA ĐƠN — DÙNG LẠI CHỈ MỤC, KHÔNG DỰNG QUY TẮC MỚI
════════════════════════════════════════════════════════════════════════════

Dùng `mt._si_index` (chỉ mục hóa đơn) và `mt._invoice_objection` (phủ quyết:
khác chuỗi / hóa đơn đã hủy bên MISA) — không dựng chỉ mục hay phủ quyết thứ hai.

Phần thu hẹp thì khác `mt._match_row`, và khác vì hai lẽ đo được:

  · **File công nợ không in ký hiệu hóa đơn.** Đã kiểm cả 7 file: chỉ có SỐ, đệm
    0 (`00003333`). Nên nhánh 'ký hiệu + số' của bảng kê không dùng được ở đây.
  · **Bù lại, biết chuỗi của cả file** — thu được về đúng tập khách, cộng ngày và
    tổng tiền của chính hóa đơn. Bảng kê không có ba vế đó cùng lúc.

Vì vậy: thu hẹp bằng khách + ngày + tiền, chỉ nhận khi còn ĐÚNG MỘT ứng viên, và
MỌI liên kết máy đề xuất đều để 'Cần review' — người chốt.

Hỏng theo hai chiều khác nhau, nên phải cẩn thận khác nhau:
  · Bảng kê khớp sai = ghi tiền vào hóa đơn của khách khác.
  · Số dư đầu kỳ khớp sai = giữ nhầm hóa đơn này và tất toán oan hóa đơn kia.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from ketoan.api._guard import guard_manager, guard_mt, is_chief
from ketoan.api.mt import (
    PAID_TOLERANCE,
    SI_NO_FIELD,
    SI_SERIES_FIELD,
    _has_si_field,
    _returns_join,
    _company,
    _customer_in_clause,
    _invoice_objection,
    OBJ_OTHER_CHAIN,
    _mt_clause,
    _debt_joins,
    _require_tables,
    _si_index,
    chain_customers,
    KIND_DEDUCT,
    KIND_PAYMENT,
)
from ketoan.api import mt_opening
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
)
from ketoan.mt.doctype.mt_opening_match.mt_opening_match import (
    ROLE_RETURN,
    ROLE_SALE,
)
from ketoan.mt.doctype.mt_opening_balance.mt_opening_balance import (
    KIND_IN_ERP,
    RESOLUTION_SKIP,
    STATUS_DRAFT,
    STATUS_FINAL,
)

DOCTYPE = "MT Opening Balance"

MAX_UPLOAD_MB = 20
# Trần dòng CÒN NỢ của một chuỗi. File thật lớn nhất có 1.167 dòng còn nợ trên
# CẢ BẢY chuỗi; 5.000 cho một chuỗi là đọc nhầm sheet.
MAX_LINES = 5000


def _tables():
    if not frappe.db.table_exists(DOCTYPE):
        frappe.throw(_(
            "Chức năng số dư đầu kỳ chưa cài trên site này (thiếu bảng {0}). Chạy "
            "`bench --site <site> migrate` rồi thử lại.").format(DOCTYPE))


# ═══════════════════════════════════════════════════════════════════════════
# Nối dòng sang hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

def _amount_hits(si, amount):
    """Số tiền trong file có khớp hóa đơn này không — thử cả trước và sau trả lại."""
    gt = abs(flt(si.get("grand_total")))
    ret = abs(flt(si.get("returned")))
    return (abs(gt - amount) <= PAID_TOLERANCE
            or (ret > 0 and abs(gt - ret - amount) <= PAID_TOLERANCE))


def _suffix(tail):
    """Đánh dấu liên kết lấy từ hóa đơn ĐÃ điều chỉnh, để người soi biết."""
    return "_da_dieu_chinh" if tail.endswith("_da_dieu_chinh") else ""


CONF_SURE = "Chắc chắn"
CONF_REVIEW = "Cần review"
CONF_NONE = "Không khớp"


def _resolve_row(row, idx, chain, cus_chain, allowed):
    """Nối MỘT dòng còn nợ sang Sales Invoice. Trả (name, method, confidence).

    ĐÃ ĐO TRÊN CẢ 7 FILE THẬT: file theo dõi công nợ **không in ký hiệu hóa đơn**,
    chỉ in SỐ, thường đệm 0 (`00003333`, `00004756`). Nên không có nhánh "ký hiệu
    + số" nào ở đây cả — dựng ra một nhánh như thế là code chết mà đọc vào lại
    tưởng đang có phép khớp mạnh.

    Còn lại ba vế để thu hẹp, dùng hết:
      · KHÁCH phải thuộc đúng chuỗi của file  (`chain_customers`)
      · NGÀY hóa đơn
      · TỔNG tiền hóa đơn

    Chỉ nhận khi còn ĐÚNG MỘT ứng viên. Số hóa đơn đánh lại từ 1 theo từng mẫu số
    (file Co.op có cả `00007709` lẫn `00000001`), nên "trùng số" là chuyện bình
    thường — nhận bừa là giữ nhầm hóa đơn này và tất toán oan hóa đơn kia.

    ════════════════════════════════════════════════════════════════════════
    HÓA ĐƠN ĐÃ ĐIỀU CHỈNH VẪN LÀ ỨNG VIÊN — khác hẳn bảng kê thanh toán
    ════════════════════════════════════════════════════════════════════════

    Quy trình thật: giao hàng -> hàng móp/lỗi -> ĐIỀU CHỈNH hóa đơn MISA -> trả
    lại trên ERPNext. Lúc đó `misa_sync._mark_superseded` đặt hóa đơn GỐC thành
    `Đã thay thế`, và `_invoice_objection` coi đó là phủ quyết.

    Ở BẢNG KÊ THANH TOÁN, loại hẳn là đúng: không ai trả tiền cho một hóa đơn
    đã hết hiệu lực.

    Ở SỐ DƯ ĐẦU KỲ thì NGƯỢC LẠI. Dòng trong file công nợ đang nói "hóa đơn này
    CÒN NỢ" — nó nói về khoản phải thu, không nói về hiệu lực pháp lý của tờ hóa
    đơn. Loại hẳn thì dòng đó không giữ được hóa đơn nào lại, và khi chốt, đúng
    hóa đơn đang còn nợ ấy rơi vào vế "không có trong danh sách" -> bị coi là đã
    trả. Nợ thật biến mất.

    Nên ở đây: hóa đơn đã điều chỉnh **vẫn là ứng viên**, chỉ bị ĐẨY XUỐNG SAU —
    ưu tiên hóa đơn còn nguyên hiệu lực, và chỉ lấy hóa đơn đã điều chỉnh khi
    không còn ứng viên nào khác. Vẫn để 'Cần review' như mọi liên kết máy đoán.

    KHÁC CHUỖI thì vẫn LOẠI HẲN — đó là phủ quyết về chủ thể, không phải về
    hiệu lực, và nối chéo chuỗi là sai ở mọi ngữ cảnh.

    ════════════════════════════════════════════════════════════════════════
    HÓA ĐƠN THAY THẾ — CẢ DÒNG NÓI VỀ TỜ THAY THẾ, KHÔNG PHẢI TỜ GỐC
    ════════════════════════════════════════════════════════════════════════

    4/7 file công nợ có cột "HĐ thay thế" (AEON · Central Retail · LOTTE ·
    WinCommerce). Chính TIÊU ĐỀ cột số hóa đơn của Central Retail là
    `'HĐ xóa bỏ'`, của WinCommerce là `'HĐ SD/xóa bỏ'`: khi cột thay thế có
    giá trị, số ở cột kia là số ĐÃ CHẾT.

    ĐÃ ĐO — **NGÀY trên dòng là ngày của TỜ THAY THẾ**: dựng bản đồ số→ngày từ
    các dòng không có thay thế rồi nội suy, Central Retail ra 224/228 dòng khớp
    tờ thay thế, 0 dòng khớp tờ gốc (trung vị trễ 11 ngày, tối đa 64). Bằng
    chứng khỏi cần thống kê — 4 hóa đơn gốc 78/82/95/96 xuất rải rác trong
    tháng đều ghi cùng một ngày 15/01/2026, còn 4 số thay thế 561/562/564/565
    thì liên tiếp: đó là ngày của một LÔ THAY THẾ.

    CHƯA ĐO — **TIỀN thuộc tờ nào thì cần dữ liệu trên site mới biết chắc.**
    Suy luận mạnh (546/546 dòng đã tất toán có `paid == gross`, mà siêu thị trả
    theo tờ CÒN HIỆU LỰC) nhưng vẫn là suy luận. Đừng để nó đi chung câu với vế
    NGÀY như thể cùng độ chắc — code dưới đây thử tiền theo CẢ HAI mốc chứ
    không cược vào một mốc.

    Hệ quả: khóa khớp là SỐ THAY THẾ, và hai phép thu hẹp ngày/tiền chỉ có
    nghĩa với tờ thay thế. Đem ngày+tiền của tờ B so với tờ A là so hai chứng
    từ khác nhau — mà nghiệp vụ "hàng bẹp méo" tồn tại chính vì hai tờ đó KHÁC
    số tiền.

    Trên bộ file mẫu: 59 dòng CÒN NỢ mang số thay thế, tổng 464.169.744đ
    (Central Retail 49 · LOTTE 6 · WinCommerce 4), cả 59 chưa thu đồng nào.

    Mọi liên kết ở đây đều để 'Cần review': máy đề xuất, người chốt.
    """
    # SỐ ĐEM ĐI KHỚP LÀ SỐ CÒN HIỆU LỰC, KHÔNG PHẢI SỐ Ở CỘT "SỐ HÓA ĐƠN".
    # Xem khối chú thích "HÓA ĐƠN THAY THẾ" ở cuối docstring.
    replaced = norm_inv_no(row.get("inv_replaced_by_norm")
                           or row.get("inv_replaced_by") or "")
    no = replaced or norm_inv_no(row.get("inv_no") or "")
    if not no:
        return None, "khong_co_so_hoa_don", CONF_NONE
    if idx is None:
        return None, "site_thieu_field_so_hoa_don", CONF_NONE

    cands = idx["by_no"].get(no) or []
    if not cands:
        # KHÔNG lùi về số đã xóa bỏ. Lùi là giữ lại tờ mà CHÍNH FILE khai là vô
        # hiệu, với số tiền của tờ khác — sai tiền, im lặng. Để dòng treo cho
        # người xử; màn nối tay vẫn bày tờ cũ ra như một lựa chọn CÓ CẢNH BÁO.
        return (None,
                "so_thay_the_khong_co_trong_erpnext" if replaced else "khong_tim_thay_so",
                CONF_NONE)

    # KHÁC CHUỖI -> loại hẳn. `_invoice_objection` gộp hai chuyện khác nhau vào
    # một hàm, nên phải tách lại ở đây: chỉ vế "khác chuỗi" mới là phủ quyết.
    step = [n for n in cands
            if _invoice_objection(idx["info"][n], chain, cus_chain) != OBJ_OTHER_CHAIN
            and (not allowed or idx["info"][n].get("customer") in allowed)]
    if not step:
        return None, "so_co_nhung_khac_chuoi", CONF_NONE

    # Hóa đơn đã điều chỉnh/thay thế: giữ làm ứng viên nhưng ĐẨY XUỐNG SAU.
    live = [n for n in step if not _invoice_objection(idx["info"][n], chain, cus_chain)]
    dead = [n for n in step if n not in live]
    if live:
        step, tail = live, "so_trong_chuoi"
    else:
        step, tail = dead, "so_trong_chuoi_da_dieu_chinh"

    # Lối tắt "còn đúng một ứng viên thì nhận" CHỈ dùng khi khớp bằng số gốc.
    #
    # Với số thay thế thì cấm: số hóa đơn đánh lại từ 1 theo từng mẫu số nên một
    # số ngắn như '4461' đụng hóa đơn năm khác là chuyện có thật (đã đo:
    # WinCommerce r1920 4316->4461 còn nợ 5.348.160, trong khi r1249 có hóa đơn
    # 00004461 của 2025 đã trả đủ). Nhận bừa ở đó là ghi một khoản nợ MA lên hóa
    # đơn đã tất toán, còn tiền thật thì không tờ nào giữ.
    if len(step) == 1 and not replaced:
        return step[0], tail, CONF_REVIEW

    inv_date = row.get("inv_date")
    if inv_date:
        by_date = [n for n in step
                   if cstr(idx["info"][n].get("posting_date")) == cstr(inv_date)]
        if len(by_date) == 1:
            return by_date[0], "so_ngay" + _suffix(tail), CONF_REVIEW
        if by_date:
            step = by_date

    # So TIỀN theo HAI mốc, vì hai bên có thể đang nói về hai thời điểm khác nhau:
    #   · `grand_total`        — hóa đơn GỐC, trước khi điều chỉnh;
    #   · `grand_total − trả lại` — sau khi đã làm phiếu trả hàng trên ERPNext.
    # File công nợ của chuỗi ghi con số nào là tùy chuỗi và tùy thời điểm họ
    # chốt. Chỉ so một mốc là trượt đúng những hóa đơn đã điều chỉnh — mà đó lại
    # là nhóm dễ sai tiền nhất.
    amount = abs(flt(row.get("gross") or 0))
    if amount:
        by_amt = [n for n in step if _amount_hits(idx["info"][n], amount)]
        if len(by_amt) == 1:
            return by_amt[0], "so_ngay_tien" + _suffix(tail), CONF_REVIEW

    if replaced and len(step) == 1:
        return None, "so_thay_the_1_ung_vien_chua_doi_chieu_duoc", CONF_REVIEW
    return None, "con_%d_ung_vien" % len(step), CONF_REVIEW


def _resolve(rows, chain, company):
    """Nối cả danh sách. Trả (rows đã gắn liên kết, thông tin chỉ mục)."""
    from ketoan.api.mt import _customer_chain_map

    want = [r for r in rows if r.get("kind") == KIND_IN_ERP]
    dates = [r["inv_date"] for r in want if r.get("inv_date")]
    idx = _si_index(company, dates)
    cus_chain, _amb = _customer_chain_map()
    allowed = set(chain_customers(chain))

    # Một hóa đơn chỉ còn nợ MỘT lần. Hai dòng cùng trỏ về một Sales Invoice là
    # đọc nhầm hoặc file có dòng lặp — giữ dòng đầu, dòng sau bỏ liên kết và nói
    # ra, chứ không im lặng ghi đè.
    taken = {}
    for r in rows:
        if r.get("kind") != KIND_IN_ERP:
            r["sales_invoice"] = None
            r["match_method"] = "khong_thuoc_nhom_can_khop"
            r["match_confidence"] = CONF_NONE
            continue
        si, method, conf = _resolve_row(r, idx, chain, cus_chain, allowed)
        if si and si in taken:
            r["sales_invoice"] = None
            r["match_method"] = "trung_hoa_don_voi_dong_%s" % taken[si]
            r["match_confidence"] = CONF_REVIEW
            continue
        if si:
            taken[si] = r.get("source_row")
        r["sales_invoice"] = si
        r["match_method"] = method
        r["match_confidence"] = conf
    return rows, idx


# ═══════════════════════════════════════════════════════════════════════════
# Xem trước / ghi
# ═══════════════════════════════════════════════════════════════════════════

def _plan_hash(chain, cutover, golive, rows):
    blob = json.dumps(
        [cstr(chain), cstr(cutover), cstr(golive),
         [[cstr(r.get("source_row")), cstr(r.get("inv_no")),
          # Số thay thế là ĐẦU VÀO QUYẾT ĐỊNH của phép khớp — không băm nó thì
          # sửa cột đó trong file xong vân tay vẫn y nguyên.
          cstr(r.get("inv_replaced_by") or ""),
          round(flt(r.get("remaining")), 2),
          cstr(r.get("sales_invoice") or "")] for r in rows]],
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _read(content, chain, golive, company):
    from ketoan.api.mt_advice import decode_upload

    raw = decode_upload(content)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw(_("File quá {0} MB").format(MAX_UPLOAD_MB))

    res = mt_opening.read_opening(content, chain=chain, golive=golive)
    if not res["reconciled"]:
        frappe.throw(_(
            "File tự lệch ở cột quyết định số dư ({0}) — dòng TỔNG CỘNG in trong file "
            "không bằng tổng các dòng. KHÔNG nhập gì cho tới khi kế toán xem lại file."
        ).format(", ".join(res["blocking"])))
    if len(res["open_rows"]) > MAX_LINES:
        frappe.throw(_("Chuỗi này ra {0} dòng còn nợ — vượt trần {1}, gần như chắc chắn "
                       "đọc nhầm sheet. KHÔNG ghi gì.").format(len(res["open_rows"]), MAX_LINES))
    rows, _idx = _resolve(res["open_rows"], res["chain"], company)
    return res, rows, hashlib.sha1(raw).hexdigest()


def _existing(company, chain):
    got = frappe.db.sql(
        "SELECT name, status FROM `tab%s` WHERE company = %%(c)s AND chain = %%(ch)s LIMIT 1"
        % DOCTYPE, {"c": company, "ch": chain}, as_dict=True)
    return got[0] if got else None


@frappe.whitelist()
def preview_import(content, chain=None, golive=None, cutover=None, company=None):
    """Xem trước bản số dư đầu kỳ sẽ ghi. KHÔNG ghi gì."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    res, rows, file_hash = _read(content, chain, golive, company)
    prev = _existing(company, res["chain"])

    # Dòng có HÓA ĐƠN THAY THẾ — nói ra ngay ở bước xem trước, kèm tiền.
    rep_rows = [r for r in rows if r.get("inv_replaced_by")]
    rep_open = [r for r in rep_rows if abs(flt(r.get("remaining"))) > 0.5]
    rep_miss = [r for r in rep_rows
                if r.get("match_method", "").startswith("so_thay_the")]
    if rep_open:
        res["warnings"].append(
            "%d dòng còn nợ (%s đ) có HÓA ĐƠN THAY THẾ: số ở cột số hóa đơn đã bị XÓA "
            "BỎ, số còn hiệu lực nằm ở cột 'HĐ thay thế' — và NGÀY, SỐ TIỀN trên dòng "
            "cũng là của tờ thay thế. Hệ thống khớp theo số thay thế; tờ mang số đã xóa "
            "bỏ KHÔNG được tự nối."
            % (len(rep_open), "{:,.0f}".format(sum(flt(r["remaining"]) for r in rep_open))))
    if rep_miss:
        res["warnings"].append(
            "Trong đó %d dòng KHÔNG tìm được chứng từ ERPNext mang số thay thế. Thường "
            "là ERPNext vẫn đang giữ số hóa đơn CŨ. Cập nhật số hóa đơn bên ERPNext rồi "
            "nhập lại, hoặc nối tay từng dòng — hệ thống KHÔNG tự lùi về số đã xóa bỏ, "
            "vì làm thế là giữ một tờ vô hiệu với số tiền của tờ khác."
            % len(rep_miss))

    n_match = sum(1 for r in rows if r.get("sales_invoice"))
    left = [r for r in rows
            if r.get("kind") == KIND_IN_ERP and not r.get("sales_invoice")]
    by_conf = {}
    for r in rows:
        k = cstr(r.get("match_confidence") or CONF_NONE)
        by_conf[k] = by_conf.get(k, 0) + 1

    return {
        "chain": res["chain"],
        "chain_detected": res["chain_detected"],
        "golive": res["golive"],
        "cutover": cstr(cutover or ""),
        "sheet": res["sheet"],
        "totals": res["totals"],
        "checks": res["checks"],
        "warnings": res["warnings"],
        "deductions": res["deductions"],
        "n": len(rows),
        "n_matched": n_match,
        "n_unmatched": len(left),
        "n_replaced": len(rep_open),
        "amount_replaced": round(sum(flt(r["remaining"]) for r in rep_open), 2),
        "n_replaced_missing": len(rep_miss),
        "by_confidence": by_conf,
        "sample": rows[:mt_opening.MAX_PREVIEW],
        "unmatched_sample": left[:mt_opening.MAX_PREVIEW],
        "file_hash": file_hash,
        "plan_hash": _plan_hash(res["chain"], cutover, res["golive"], rows),
        "existing": prev,
        "blocked": bool(prev),
        "note": _(
            "Nhập vào ở trạng thái '{0}' — CHƯA đụng gì tới công nợ. Nối xong các dòng "
            "còn treo rồi mới CHỐT; lúc chốt mới bật luật 'hóa đơn trước ngày chốt mà "
            "không có trong danh sách coi như đã thanh toán'.").format(STATUS_DRAFT),
    }


@frappe.whitelist()
def commit_import(content, expected_hash, chain=None, golive=None, cutover=None,
                  company=None):
    """Ghi bản số dư đầu kỳ ở trạng thái Nháp."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    if not cutover:
        frappe.throw(_("Chưa khai NGÀY CHỐT SỐ DƯ. Không có mốc đó thì không biết hóa "
                       "đơn nào thuộc phần đã chuyển giao."))

    res, rows, file_hash = _read(content, chain, golive, company)
    if not expected_hash or expected_hash != _plan_hash(res["chain"], cutover,
                                                        res["golive"], rows):
        frappe.throw(_(
            "Nội dung đã đổi so với lúc xem trước. Xem lại rồi mới ghi — vân tay kế "
            "hoạch là chốt duy nhất chống việc ghi một thứ khác với thứ đã duyệt."))

    prev = _existing(company, res["chain"])
    if prev:
        frappe.throw(_(
            "Chuỗi {0} đã có bản số dư đầu kỳ ({1}, trạng thái {2}). Số dư đầu kỳ chỉ "
            "nhập MỘT LẦN — nhập lần hai là cộng đôi công nợ."
        ).format(res["chain"], prev["name"], prev["status"]))

    doc = frappe.new_doc(DOCTYPE)
    doc.company = company
    doc.chain = res["chain"]
    doc.status = STATUS_DRAFT
    doc.cutover_date = getdate(cutover)
    doc.golive_date = getdate(res["golive"])
    doc.file_hash = file_hash
    doc.sheet_name = res["sheet"]
    doc.imported_by = frappe.session.user
    doc.opening_debt_gross = flt(res["totals"]["opening_debt_gross"])

    for r in rows:
        doc.append("lines", {
            "source_row": cint(r.get("source_row")),
            "kind": r.get("kind"),
            "party": r.get("party"),
            "inv_no": r.get("inv_no"),
            "inv_replaced_by": r.get("inv_replaced_by"),
            "inv_date": r.get("inv_date") or None,
            "net": flt(r.get("net")), "vat": flt(r.get("vat")),
            "gross": flt(r.get("gross")), "paid": flt(r.get("paid")),
            "returns": flt(r.get("returns")), "remaining": flt(r.get("remaining")),
            "sales_invoice": r.get("sales_invoice") or None,
            "match_method": r.get("match_method"),
            "match_confidence": r.get("match_confidence"),
            "note": r.get("note"),
        })
    # Liên kết máy tự nối phải vào BẢNG `matches` — `sales_invoice` trên dòng
    # giờ chỉ là bản sao được tính lại từ đó. Chỉ ghi `sales_invoice` thôi thì
    # `_sync_matches` sẽ xóa sạch nó ngay ở lần validate đầu tiên.
    auto = [r for r in rows if r.get("sales_invoice")]
    info = {}
    if auto:
        keys = {"m%d" % i: r["sales_invoice"] for i, r in enumerate(auto)}
        for x in frappe.db.sql(
            "SELECT name, grand_total, is_return, posting_date, return_against "
            "FROM `tabSales Invoice` WHERE name IN (%s)"
            % ", ".join("%%(m%d)s" % i for i in range(len(auto))), keys, as_dict=True):
            info[x.name] = x
    for i, r in enumerate(auto):
        x = info.get(r["sales_invoice"])
        if not x:
            continue
        is_ret = cint(x.is_return)
        doc.append("matches", {
            "line_no": rows.index(r) + 1,
            "sales_invoice": x.name,
            "role": ROLE_RETURN if is_ret else ROLE_SALE,
            "si_amount": -abs(flt(x.grand_total)) if is_ret else abs(flt(x.grand_total)),
            "si_is_return": is_ret,
            "si_posting_date": x.posting_date,
            "return_against": x.return_against,
        })

    for d in res["deductions"]:
        doc.append("deductions", {
            "sheet": d.get("sheet"), "n_rows": cint(d.get("n_rows")),
            "gross": flt(d.get("gross")), "offset_amount": flt(d.get("offset")),
            "remaining": flt(d.get("remaining")),
            "unreadable": 1 if d.get("unreadable") else 0,
        })
    doc.insert()
    frappe.db.commit()
    return {
        "name": doc.name, "chain": doc.chain, "status": doc.status,
        "n": len(doc.lines), "n_unmatched": cint(doc.n_unmatched),
        "opening_debt": flt(doc.opening_debt),
        "message": _("Đã nhập số dư đầu kỳ {0}: {1} dòng còn nợ, nợ ròng {2} đ. Còn {3} "
                     "dòng chưa nối được hóa đơn — xử lý hết rồi mới chốt được.").format(
            doc.chain, len(doc.lines), "{:,.0f}".format(flt(doc.opening_debt)),
            cint(doc.n_unmatched)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Xem / sửa dòng treo
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def list_openings(company=None):
    """Tình trạng số dư đầu kỳ của từng chuỗi."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    from ketoan.install import MT_CHAINS

    rows = frappe.db.sql("""
        SELECT name, chain, status, cutover_date, golive_date, opening_debt,
               opening_debt_gross, deduction_open, no_invoice_amount, debt_carried,
               n_rows, n_matched, n_unmatched,
               n_in_erp, n_pre_golive, n_no_invoice, n_settled
        FROM `tab%s` WHERE company = %%(c)s
    """ % DOCTYPE, {"c": company}, as_dict=True)
    by_chain = {r.chain: r for r in rows}

    # MỘT lần đọc bản đồ khách -> chuỗi cho cả 8 chuỗi. Gọi `chain_customers`
    # trong vòng lặp là 8 câu SQL giống hệt nhau cho cùng một câu trả lời.
    from ketoan.api.mt import _customer_chain_map
    cmap, _amb = _customer_chain_map()
    n_cus = {}
    for _c, ch in cmap.items():
        n_cus[ch] = n_cus.get(ch, 0) + 1

    out = []
    for ch in MT_CHAINS:
        r = by_chain.get(ch)
        out.append({
            "chain": ch,
            "doc": r,
            "status": (r or {}).get("status") or "",
            "n_customers": cint(n_cus.get(ch)),
        })
    return {
        "rows": out,
        "can_manage": is_chief(),
        "total_opening": round(sum(flt(r.opening_debt) for r in rows), 2),
        "total_carried": round(sum(flt(r.debt_carried) for r in rows), 2),
        "n_done": sum(1 for r in rows if r.status == STATUS_FINAL),
        "note": _(
            "Mỗi chuỗi chốt số dư MỘT LẦN. Bản '{0}' chưa bật luật gì; bản '{1}' bật "
            "luật: hóa đơn của chuỗi có ngày <= ngày chốt mà không nằm trong danh sách "
            "còn nợ thì coi như đã thanh toán trước khi chuyển giao."
        ).format(STATUS_DRAFT, STATUS_FINAL),
    }


@frappe.whitelist()
def get_opening(name, company=None, only=None, page=1, page_size=50):
    """Một bản số dư đầu kỳ + danh sách dòng (phân trang)."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)

    lines = list(doc.lines or [])
    if only == "treo":
        lines = doc.unresolved()
    elif only == "review":
        lines = [l for l in lines if cstr(l.match_confidence) == CONF_REVIEW]
    elif only:
        lines = [l for l in lines if cstr(l.kind) == only]

    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))
    total = len(lines)
    start = (page - 1) * page_size

    return {
        "doc": {
            "name": doc.name, "chain": doc.chain, "status": doc.status,
            "cutover_date": cstr(doc.cutover_date), "golive_date": cstr(doc.golive_date),
            "opening_debt": flt(doc.opening_debt),
            "opening_debt_gross": flt(doc.opening_debt_gross),
            "deduction_open": flt(doc.deduction_open),
            "no_invoice_amount": flt(doc.no_invoice_amount),
            "debt_carried": flt(doc.debt_carried),
            "n_rows": cint(doc.n_rows), "n_matched": cint(doc.n_matched),
            "n_unmatched": cint(doc.n_unmatched), "n_in_erp": cint(doc.n_in_erp),
            "n_pre_golive": cint(doc.n_pre_golive), "n_no_invoice": cint(doc.n_no_invoice),
            "n_settled": cint(doc.n_settled), "sheet_name": doc.sheet_name,
            "file_hash": doc.file_hash,
        },
        "deductions": [d.as_dict() for d in (doc.deductions or [])],
        "rows": [_line_out(l) for l in lines[start:start + page_size]],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "kind_label": mt_opening.KIND_LABEL,
        "can_manage": is_chief(),
    }


def _line_out(l):
    return {
        "row": cint(l.idx), "source_row": cint(l.source_row), "kind": l.kind,
        "party": l.party, "inv_no": l.inv_no,
        "inv_replaced_by": l.inv_replaced_by,
        "inv_date": cstr(l.inv_date or ""),
        "net": flt(l.net), "vat": flt(l.vat), "gross": flt(l.gross),
        "paid": flt(l.paid), "returns": flt(l.returns), "remaining": flt(l.remaining),
        "sales_invoice": l.sales_invoice, "match_method": l.match_method,
        "match_confidence": l.match_confidence, "resolution": l.resolution,
        "n_matched_docs": cint(l.n_matched_docs),
        "match_amount": flt(l.match_amount), "match_diff": flt(l.match_diff),
        "note": l.note,
    }


def _load(name, company):
    doc = frappe.get_doc(DOCTYPE, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bản số dư {0} thuộc công ty khác").format(name))
    return doc


def _row(doc, row):
    for l in doc.lines or []:
        if cint(l.idx) == cint(row):
            return l
    frappe.throw(_("Không có dòng số {0} trong bản số dư này").format(row))


def _editable(doc):
    if doc.status == STATUS_FINAL:
        frappe.throw(_(
            "Bản số dư của {0} đã CHỐT — sửa liên kết bây giờ là đổi tập hóa đơn còn "
            "nợ dưới chân các màn hình đang dùng. Mở lại về '{1}' trước."
        ).format(doc.chain, STATUS_DRAFT))


def _check_invoice(si, doc, company):
    """Chứng từ này có được phép nối vào bản số dư của chuỗi đó không."""
    got = frappe.db.get_value(
        "Sales Invoice", si,
        ["company", "customer", "docstatus", "is_return", "grand_total",
         "posting_date", "return_against"], as_dict=True)
    if not got:
        frappe.throw(_("Không có chứng từ {0}").format(si))
    if cstr(got.company) != cstr(company):
        frappe.throw(_("Chứng từ {0} thuộc công ty khác").format(si))
    if cint(got.docstatus) != 1:
        frappe.throw(_("Chứng từ {0} chưa ghi sổ — nối vào đây là giữ lại một chứng từ "
                       "chưa tồn tại về mặt sổ sách.").format(si))
    allowed = set(chain_customers(doc.chain))
    if allowed and got.customer not in allowed:
        frappe.throw(_(
            "Chứng từ {0} là của khách {1}, không thuộc chuỗi {2}. Nối chéo chuỗi là giữ "
            "nhầm hóa đơn của chuỗi này và tất toán oan hóa đơn của chuỗi kia."
        ).format(si, got.customer, doc.chain))
    return got


@frappe.whitelist()
def add_match(name, row, sales_invoice, note=None, company=None):
    """Nối THÊM một chứng từ ERPNext vào một dòng số dư.

    Một hóa đơn MISA có thể ứng với NHIỀU chứng từ ERPNext. Ca thật:

        MISA 5449 = 4.893.696đ
          ├─ hóa đơn đi          +5.893.696
          └─ hóa đơn trả về      −1.000.000   (siêu thị không nhận vì bẹp méo)

    Chiều tiền lấy từ chính chứng từ (`is_return`), KHÔNG do người gõ — gõ tay
    dấu là mở đường cho một lần gõ nhầm làm lệch cả dòng.
    """
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    _editable(doc)
    l = _row(doc, row)

    si = cstr(sales_invoice).strip()
    if not si:
        frappe.throw(_("Chưa chọn chứng từ nào."))
    if any(cstr(m.sales_invoice) == si and cint(m.line_no) == cint(row)
           for m in doc.matches or []):
        frappe.throw(_("Chứng từ {0} đã nối vào dòng này rồi.").format(si))

    got = _check_invoice(si, doc, company)
    is_ret = cint(got.is_return)
    doc.append("matches", {
        "line_no": cint(row),
        "sales_invoice": si,
        "role": ROLE_RETURN if is_ret else ROLE_SALE,
        # DẤU lấy từ `is_return`, không lấy từ dấu của `grand_total`: ERPNext để
        # credit note mang số âm, nhưng quy ước đó không phải chỗ nào cũng giữ.
        "si_amount": -abs(flt(got.grand_total)) if is_ret else abs(flt(got.grand_total)),
        "si_is_return": is_ret,
        "si_posting_date": got.posting_date,
        "return_against": got.return_against,
        "note": note or None,
    })
    l.match_method = "nguoi_chot"
    l.match_confidence = CONF_SURE
    doc.save()
    frappe.db.commit()

    warn = ""
    if is_ret and not cstr(got.return_against):
        warn = _(
            "Chứng từ trả về {0} KHÔNG khai `Return Against` — nó không tự trừ vào hóa "
            "đơn nào, nên công nợ đang cao hơn thực tế {1} đ. Nối vào đây chỉ ghi lại "
            "quan hệ, KHÔNG sửa được con số. Mở chứng từ, điền `Return Against` rồi số "
            "tự đúng."
        ).format(si, "{:,.0f}".format(abs(flt(got.grand_total))))
    return {"row": cint(row), "line": _line_out(l),
            "matches": _matches_out(doc, row),
            "n_unmatched": cint(doc.n_unmatched),
            "warning": warn,
            "message": _("Đã nối {0} vào dòng {1}. Cộng các chứng từ: {2} đ, file ghi "
                         "{3} đ, lệch {4} đ.").format(
                si, row, "{:,.0f}".format(flt(l.match_amount)),
                "{:,.0f}".format(flt(l.gross)), "{:,.0f}".format(flt(l.match_diff)))}


@frappe.whitelist()
def remove_match(name, row, sales_invoice, company=None):
    """Gỡ một liên kết khỏi dòng."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    _editable(doc)
    l = _row(doc, row)

    si = cstr(sales_invoice).strip()
    keep = [m for m in doc.matches or []
            if not (cstr(m.sales_invoice) == si and cint(m.line_no) == cint(row))]
    if len(keep) == len(doc.matches or []):
        frappe.throw(_("Dòng {0} không nối chứng từ {1}.").format(row, si))
    doc.matches = []
    for m in keep:
        doc.append("matches", {k: m.get(k) for k in
                               ("line_no", "sales_invoice", "role", "si_amount",
                                "si_is_return", "si_posting_date", "return_against", "note")})
    if not doc.matches_of(row):
        l.match_method = "nguoi_go_lien_ket"
        l.match_confidence = CONF_NONE
    doc.save()
    frappe.db.commit()
    return {"row": cint(row), "line": _line_out(l),
            "matches": _matches_out(doc, row),
            "n_unmatched": cint(doc.n_unmatched),
            "message": _("Đã gỡ {0} khỏi dòng {1}.").format(si, row)}


@frappe.whitelist()
def set_line(name, row, resolution=None, note=None, company=None):
    """Đánh dấu 'Bỏ qua' hoặc ghi chú cho một dòng.

    Việc NỐI đã tách sang `add_match` / `remove_match`: một dòng có thể ứng với
    nhiều chứng từ, nên nó không còn là một ô để gán nữa.
    """
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    _editable(doc)
    l = _row(doc, row)

    if resolution is not None:
        r = cstr(resolution).strip()
        if r and r != RESOLUTION_SKIP:
            frappe.throw(_("Chỉ nhận '{0}' hoặc để trống ở ô người chốt.")
                         .format(RESOLUTION_SKIP))
        if r and doc.matches_of(row):
            frappe.throw(_("Dòng {0} đang nối {1} chứng từ — gỡ hết rồi mới đánh dấu "
                           "'{2}' được.").format(row, len(doc.matches_of(row)),
                                                 RESOLUTION_SKIP))
        l.resolution = r or None
    if note is not None:
        l.note = note or None

    doc.save()
    frappe.db.commit()
    return {"row": cint(row), "line": _line_out(l),
            "matches": _matches_out(doc, row),
            "n_unmatched": cint(doc.n_unmatched),
            "message": _("Đã lưu dòng {0}. Còn {1} dòng treo.").format(
                row, cint(doc.n_unmatched))}


def _replaced_note(l, has_live):
    """Câu dẫn cho dòng có hóa đơn thay thế — phải là CHỈ DẪN, không phải cảnh báo.

    Khi ERPNext chưa có tờ mang số thay thế, việc ĐÚNG là nối tờ mang số đã xóa
    bỏ để GIỮ khoản nợ lại. Bấm "Bỏ qua" ở đó là xóa khoản nợ. Câu này phải nói
    thẳng cả hai vế kèm SỐ TIỀN, chứ không chỉ cảnh báo chung chung.
    """
    if has_live:
        return _(
            "Dòng này có HÓA ĐƠN THAY THẾ: số {0} đã bị xóa bỏ, số còn hiệu lực là {1} — "
            "ngày và số tiền trên dòng cũng là của tờ {1}. Chọn chứng từ mang số {1}."
        ).format(l.inv_no, l.inv_replaced_by)
    return _(
        "Dòng này có HÓA ĐƠN THAY THẾ ({0} đã xóa bỏ → {1}), nhưng ERPNext CHƯA có chứng "
        "từ nào mang số {1} — ERPNext vẫn đang giữ số cũ.\n\n"
        "Việc cần làm: nối tờ mang số {0} để GIỮ {2} đ ở lại công nợ, rồi ghi chú lý do. "
        "ĐỪNG bấm 'Bỏ qua' — bỏ qua là xóa {2} đ khỏi công nợ khi chốt."
    ).format(l.inv_no, l.inv_replaced_by, "{:,.0f}".format(flt(l.remaining)))


def _matches_out(doc, row):
    return [{"sales_invoice": m.sales_invoice, "role": m.role,
             "si_amount": flt(m.si_amount), "si_is_return": cint(m.si_is_return),
             "si_posting_date": cstr(m.si_posting_date or ""),
             "return_against": m.return_against, "note": m.note}
            for m in doc.matches_of(row)]


@frappe.whitelist()
def search_invoices(name, row, q=None, company=None, limit=20):
    """Hóa đơn ứng viên cho một dòng treo — CHỈ trong chuỗi của bản số dư.

    ════════════════════════════════════════════════════════════════════════
    LỖI BẢN ĐẦU: TÌM SỐ HÓA ĐƠN TRONG MÃ CHỨNG TỪ ERPNEXT
    ════════════════════════════════════════════════════════════════════════

    Bản đầu lấy số hóa đơn của dòng (`00005449`) làm từ khóa rồi so với
    `si.name LIKE '%%00005449%%'`. `si.name` là mã chứng từ ERPNext
    (`ACC-SINV-2026-00123`) — nó KHÔNG BAO GIỜ chứa số hóa đơn. Nên màn hình
    luôn ra "Không có hóa đơn nào khớp", với MỌI dòng treo. Cả đường nối tay
    coi như không dùng được, mà nhìn thì tưởng "đúng là không có hóa đơn nào".

    Số hóa đơn nằm ở `custom_misa_inv_no`. Phải tìm ở ĐÓ.

    ════════════════════════════════════════════════════════════════════════
    KHÔNG BAO GIỜ TRẢ MÀN HÌNH RỖNG KHI CHUỖI CÓ HÓA ĐƠN
    ════════════════════════════════════════════════════════════════════════

    Người vào đây là vì máy đã chịu thua. Lọc cứng theo số rồi trả rỗng là bắt
    họ tự đoán tiếp mà không có gì trong tay. Nên trả về ứng viên xếp theo mức
    gần, và nói rõ vì sao từng cái được xếp lên trên:

        1. trùng SỐ hóa đơn
        2. trùng SỐ TIỀN (thử cả trước lẫn sau khi trừ hàng trả lại)
        3. gần NGÀY nhất

    Gõ từ khóa thì lọc; để trống thì liệt kê theo thứ tự trên.
    """
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    l = _row(doc, row)

    # Xếp hạng theo SỐ CÒN HIỆU LỰC. Bản trước lấy `l.inv_no` nên gắn badge
    # "trùng số hóa đơn" cho tờ ĐÃ XÓA BỎ và đẩy nó lên đầu, trong khi thứ tự
    # phụ (gần `l.inv_date` nhất — ngày của tờ THAY THẾ) lại đẩy tờ đó xuống.
    # Hai tín hiệu đánh nhau, kế toán nhận một gợi ý tự mâu thuẫn.
    want_rep = norm_inv_no(l.inv_replaced_by or "")
    want_no = want_rep or norm_inv_no(l.inv_no or "")
    dead_no = norm_inv_no(l.inv_no or "") if want_rep else ""
    want_amt = abs(flt(l.gross or 0))

    names = chain_customers(doc.chain)
    p = {"company": company, "limit": min(200, max(20, cint(limit) or 50))}
    where = [_customer_in_clause(names, p)]

    has_no = _has_si_field(SI_NO_FIELD)
    has_series = _has_si_field(SI_SERIES_FIELD)
    kw = cstr(q or "").strip()
    if kw:
        p["kw"] = "%" + kw + "%"
        cols = ["si.name LIKE %(kw)s", "si.customer_name LIKE %(kw)s"]
        if has_no:
            cols.append("si.{0} LIKE %(kw)s".format(SI_NO_FIELD))
        if has_series:
            cols.append("si.{0} LIKE %(kw)s".format(SI_SERIES_FIELD))
        where.append("(%s)" % " OR ".join(cols))

    if l.inv_date:
        p["d"] = cstr(l.inv_date)
        order = "ABS(DATEDIFF(si.posting_date, %(d)s)) ASC, si.posting_date DESC"
    else:
        order = "si.posting_date DESC"

    no_col = "si.{0}".format(SI_NO_FIELD) if has_no else "''"
    ser_col = "si.{0}".format(SI_SERIES_FIELD) if has_series else "''"
    rows = frappe.db.sql("""
        SELECT si.name, si.posting_date, si.customer, si.customer_name,
               ABS(si.grand_total) AS grand_total,
               si.is_return, si.return_against,
               IFNULL(rt.returned, 0) AS returned,
               {no_col} AS inv_no, {ser_col} AS inv_series
        FROM `tabSales Invoice` si
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND {where}
        ORDER BY {order}
        LIMIT %(limit)s
    """.format(no_col=no_col, ser_col=ser_col, join=_returns_join(),
               where=" AND ".join(where), order=order), p, as_dict=True)

    # HAI SỐ CỦA DÒNG PHẢI CÓ MẶT, BẤT KỂ NGÀY.
    #
    # Truy vấn trên cắt bằng `LIMIT` sau khi xếp theo ĐỘ GẦN NGÀY, mà ngày trên
    # dòng là ngày của TỜ THAY THẾ. Nên tờ ERPNext đang giữ (mang số đã xóa bỏ,
    # ngày của tờ gốc) bị xếp theo một ngày không phải của nó: đã đo trên
    # Central Retail, trung vị 140 hóa đơn cùng chuỗi gần ngày hơn nó, cá biệt
    # 432. Với LIMIT 20 thì 49/49 dòng còn nợ (337.497.624đ) mở modal ra là
    # MÀN HÌNH KHÔNG CÓ TỜ CẦN CHỌN — tệ hơn màn hình trắng, vì nó có nội dung.
    #
    # Nên lấy riêng đúng hai số đó và ghép lên đầu.
    if not kw:
        pins = [x for x in (want_no, dead_no) if x]
        if pins and has_no:
            pp = dict(p)
            for i, v in enumerate(pins):
                pp["pin%d" % i] = v
            pin_rows = frappe.db.sql("""
                SELECT si.name, si.posting_date, si.customer, si.customer_name,
                       ABS(si.grand_total) AS grand_total,
                       si.is_return, si.return_against,
                       IFNULL(rt.returned, 0) AS returned,
                       {no_col} AS inv_no, {ser_col} AS inv_series
                FROM `tabSales Invoice` si
                {join}
                WHERE si.docstatus = 1 AND si.company = %(company)s
                  AND {in_cus}
                  AND TRIM(LEADING '0' FROM IFNULL({no_col}, '')) IN ({ph})
                LIMIT 40
            """.format(no_col=no_col, ser_col=ser_col, join=_returns_join(),
                       in_cus=_customer_in_clause(names, pp, prefix="pc"),
                       ph=", ".join("%%(pin%d)s" % i for i in range(len(pins)))),
                pp, as_dict=True)
            have = {r.name for r in rows}
            rows = [r for r in pin_rows if r.name not in have] + rows

    # Xếp lại theo mức GẦN, và nói rõ vì sao — người đang phải quyết bằng mắt.
    linked = {cstr(m.sales_invoice) for m in doc.matches_of(row)}
    # Phần CÒN THIẾU của dòng — sau khi đã nối được vài chứng từ, ứng viên đáng
    # gợi ý là cái bù đúng chỗ hụt, không phải cái bằng tổng ban đầu.
    gap = round(flt(l.gross) - flt(l.match_amount), 2) if doc.matches_of(row) else want_amt

    for r in rows:
        why = []
        rno = norm_inv_no(r.inv_no)
        if want_no and rno == want_no:
            why.append("trùng số hóa đơn thay thế" if want_rep else "trùng số hóa đơn")
        # Tờ mang số ĐÃ XÓA BỎ vẫn được bày ra — có site chưa kịp cập nhật số
        # mới nên đó là tờ duy nhất tồn tại. Nhưng phải gắn nhãn, không được để
        # nó trông như một gợi ý bình thường.
        if dead_no and rno == dead_no:
            why.append("số ĐÃ XÓA BỎ (tờ ERPNext đang giữ)")
        if want_amt and _amount_hits(r, want_amt):
            why.append("trùng số tiền")
        if gap and abs(abs(flt(r.grand_total)) - abs(gap)) <= PAID_TOLERANCE:
            why.append("bù đúng phần còn thiếu")
        if l.inv_date and cstr(r.posting_date) == cstr(l.inv_date):
            why.append("trùng ngày")
        r["why"] = why
        r["net_due"] = round(flt(r.grand_total) - flt(r.returned), 2)
        # Chứng từ trả về vào đây với dấu ÂM — để người nhìn thấy ngay nó sẽ
        # TRỪ vào phép cộng chứ không cộng thêm.
        r["signed"] = -abs(flt(r.grand_total)) if cint(r.is_return) else abs(flt(r.grand_total))
        r["linked"] = 1 if cstr(r.name) in linked else 0
        r["is_dead_no"] = 1 if (dead_no and rno == dead_no) else 0
        r["is_live_no"] = 1 if (want_rep and rno == want_no) else 0
        r["rank"] = -len(why)
    rows.sort(key=lambda r: r["rank"])

    # Có tờ mang SỐ THAY THẾ thì nó lên đầu. KHÔNG có thì tờ mang số ĐÃ XÓA BỎ
    # lên đầu — và đó là hành động ĐÚNG, không phải phương án cuối:
    #
    #   nối tờ đó  -> khoản nợ được GIỮ LẠI (tiền lấy từ ERPNext, không lấy từ file)
    #   không nối  -> khi chốt, chính hóa đơn đó rơi vào vế "không có trong danh
    #                 sách" và bị coi là ĐÃ THANH TOÁN. Mất trắng.
    #
    # Bản đầu xếp nó xuống cuối và dán nhãn đỏ — tức là giao diện đẩy người dùng
    # về phía nút "Bỏ qua", cái nút xóa tiền. Đã sửa.
    has_live = any(r["is_live_no"] for r in rows)
    if want_rep and not has_live:
        rows.sort(key=lambda r: (-r["is_dead_no"], r["rank"]))

    # Đọc BẢNG LIÊN KẾT, không đọc `lines[].sales_invoice` — cái đó chỉ là BẢN
    # SAO của liên kết CHÍNH. Một chứng từ đang là vế THỨ HAI của dòng khác
    # (hóa đơn trả về chẳng hạn) sẽ hiện "chưa dùng", người bấm Chọn, rồi
    # `_check_matches` mới ném lỗi lúc lưu — bắt họ thao tác thừa để nhận một
    # câu từ chối lẽ ra phải thấy từ đầu.
    used = {cstr(m.sales_invoice) for m in (doc.matches or []) if cstr(m.sales_invoice)}
    for r in rows:
        r["taken"] = 1 if r.name in used else 0
    msg = ""
    if not names:
        msg = _("Chuỗi {0} chưa gán khách hàng nào — không có hóa đơn nào để chọn.").format(
            doc.chain)
    elif not has_no:
        msg = _("Site chưa có field `{0}` trên Sales Invoice nên không tìm được theo SỐ "
                "hóa đơn, chỉ tìm được theo mã chứng từ và tên khách.").format(SI_NO_FIELD)

    return {
        "rows": rows,
        "line": _line_out(l),
        "matches": _matches_out(doc, row),
        "chain": doc.chain,
        "want_no": want_no,
        "dead_no": dead_no,
        "message": msg,
        "note": _(
            "Một hóa đơn MISA có thể ứng với NHIỀU chứng từ ERPNext — ví dụ hóa đơn đi "
            "cộng hóa đơn trả về khi siêu thị không nhận hàng bẹp méo. Bấm 'Chọn' lần "
            "lượt từng cái; hóa đơn trả về vào với dấu TRỪ. Cộng lại phải ra đúng số "
            "trong file thì mới chốt được."),
        "note_replaced": (_replaced_note(l, has_live) if want_rep else ""),
        "has_live_no": 1 if has_live else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Chốt — bước bật luật
# ═══════════════════════════════════════════════════════════════════════════

def _settled_query(company, chain, cutover, parent, params):
    """Hóa đơn SẼ bị coi là đã tất toán khi bản này chốt.

    CHỈ đếm hóa đơn HIỆN đang nằm trong rổ nợ: hóa đơn đã được bảng kê ghi nhận
    trả đủ thì vốn đã ra khỏi rổ, gộp vào đây là thổi phồng tác động của việc
    chốt.
    """
    params.update({"company": company, "cut": cstr(cutover), "parent": parent,
                   "tol": PAID_TOLERANCE,
                   "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT})
    in_cus = _customer_in_clause(chain_customers(chain), params, prefix="scc")
    mt = _mt_clause(params)
    join = _debt_joins()
    return """
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND si.posting_date <= %(cut)s
          AND {in_cus} AND {mt}
          AND (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)) < (ABS(si.grand_total) - IFNULL(rt.returned, 0)) - %(tol)s
          AND NOT EXISTS (SELECT 1 FROM `tabMT Opening Match` om
                          WHERE om.parent = %(parent)s
                            AND om.parenttype = 'MT Opening Balance'
                            AND om.sales_invoice = si.name)
    """.format(join=join, in_cus=in_cus, mt=mt)


@frappe.whitelist()
def finalize_preview(name, company=None, limit=50):
    """Chốt bản này thì bao nhiêu hóa đơn ERPNext rời khỏi công nợ. KHÔNG ghi gì."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)

    p = {}
    base = _settled_query(company, doc.chain, doc.cutover_date, doc.name, p)
    agg = frappe.db.sql("SELECT COUNT(*) AS n, IFNULL(SUM(ABS(si.grand_total)), 0) AS amount "
                        + base, p, as_dict=True)[0]
    p["limit"] = min(200, max(10, cint(limit) or 50))
    sample = frappe.db.sql("""
        SELECT si.name, si.posting_date, si.customer_name, ABS(si.grand_total) AS grand_total
        """ + base + " ORDER BY si.posting_date DESC LIMIT %(limit)s", p, as_dict=True)

    left = doc.unresolved()
    off = doc.amount_off()
    kept = [l for l in (doc.lines or []) if cstr(l.sales_invoice)]
    erp = _kept_by_erp(company, doc)
    return {
        "name": doc.name, "chain": doc.chain, "status": doc.status,
        "cutover_date": cstr(doc.cutover_date),
        "n_settled": cint(agg.n), "amount_settled": flt(agg.amount),
        "sample": sample,
        "n_kept": len(kept),
        "amount_kept": round(sum(flt(l.remaining) for l in kept), 2),
        "n_unresolved": len(left),
        "unresolved": [_line_out(l) for l in left[:50]],
        # HAI VẾ CỦA CÙNG MỘT SỐ, đặt cạnh nhau.
        #
        # `amount_kept` là số của FILE; `amount_kept_erp` là số của ERPNext tính
        # bằng ĐÚNG công thức nợ (`_NET_DUE`). Trước đây màn hình chỉ có vế đầu,
        # nên giữ nhầm tờ — tờ đã xóa bỏ thay vì tờ thay thế — làm nợ mang sang
        # đổi thật mà KHÔNG con số nào trên màn hình nhúc nhích.
        "amount_kept_erp": flt(erp["amount"]),
        "amount_kept_diff": round(flt(erp["amount"])
                                  - round(sum(flt(l.remaining) for l in kept), 2), 2),
        "n_kept_erp": cint(erp["n"]),
        # Chứng từ đã nối mà nay KHÔNG còn hiệu lực (bị hủy / bị amend). Chúng
        # không giữ được gì nữa: mọi truy vấn nợ đòi `docstatus = 1`, nên hóa
        # đơn tương ứng rơi vào vế "không có trong danh sách" và bị tất toán.
        "stale_matches": erp["stale"],
        "n_stale": len(erp["stale"]),
        "n_amount_off": len(off),
        "amount_off": [_line_out(l) for l in off[:50]],
        "amount_off_total": round(sum(flt(l.match_diff) for l in off), 2),
        "n_pre_golive": cint(doc.n_pre_golive),
        "n_no_invoice": cint(doc.n_no_invoice),
        "ready": not left,
        "plan_hash": _finalize_hash(doc, cint(agg.n)),
        "can_manage": is_chief(),
        "note": _(
            "Chốt xong: {0} hóa đơn ERPNext của chuỗi {1} có ngày <= {2} rời khỏi rổ nợ "
            "(coi như đã thanh toán trước chuyển giao), {3} hóa đơn ở lại vì có tên "
            "trong danh sách còn nợ. Nhóm 'trước go-live' ({4} dòng) và 'chưa có số hóa "
            "đơn' ({5} dòng) không nối hóa đơn nào nên không ảnh hưởng phép này."
        ).format(cint(agg.n), doc.chain, cstr(doc.cutover_date), len(kept),
                 cint(doc.n_pre_golive), cint(doc.n_no_invoice)),
    }


def _kept_by_erp(company, doc):
    """Số tiền ERPNext nói về chính các chứng từ đã nối, và những tờ đã CHẾT.

    Dùng lại `_NET_DUE` của `mt.py` — cùng một công thức nợ với mọi màn hình
    khác, không dựng phép tính thứ hai.
    """
    names = sorted({cstr(m.sales_invoice) for m in (doc.matches or [])
                    if cstr(m.sales_invoice)})
    if not names:
        return {"n": 0, "amount": 0.0, "stale": []}
    p = {"company": company, "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}
    keys = {"k%d" % i: n for i, n in enumerate(names)}
    p.update(keys)
    ph = ", ".join("%%(k%d)s" % i for i in range(len(names)))
    rows = frappe.db.sql("""
        SELECT si.name, si.docstatus, si.is_return,
               (ABS(si.grand_total) - IFNULL(rt.returned, 0)) AS net_due
        FROM `tabSales Invoice` si
        {join}
        WHERE si.name IN ({ph})
    """.format(join=_debt_joins(), ph=ph), p, as_dict=True)

    found = {r.name: r for r in rows}
    amount = sum(flt(r.net_due) for r in rows
                 if cint(r.docstatus) == 1 and not cint(r.is_return))
    stale = []
    for n in names:
        r = found.get(n)
        if r is None:
            stale.append({"sales_invoice": n, "reason": "không còn tồn tại"})
        elif cint(r.docstatus) != 1:
            stale.append({"sales_invoice": n,
                          "reason": "đã hủy hoặc đã sửa đổi (docstatus=%d)" % cint(r.docstatus)})
    return {"n": len(names), "amount": round(amount, 2), "stale": stale}


def _finalize_hash(doc, n_settled):
    blob = json.dumps([cstr(doc.name), cstr(doc.chain), cstr(doc.cutover_date),
                       cint(n_settled),
                       sorted(cstr(l.sales_invoice) for l in (doc.lines or [])
                              if cstr(l.sales_invoice))],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


@frappe.whitelist()
def finalize(name, expected_hash, company=None):
    """Chốt — bật luật tất toán cho chuỗi này."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    if doc.status == STATUS_FINAL:
        frappe.throw(_("Bản số dư của {0} đã chốt rồi.").format(doc.chain))

    pre = finalize_preview(name, company=company)
    if not expected_hash or expected_hash != pre["plan_hash"]:
        frappe.throw(_(
            "Tập hóa đơn đã đổi so với lúc xem trước. Xem lại rồi mới chốt — chốt là "
            "bước làm hóa đơn biến mất khỏi rổ nợ."))

    doc.n_settled = cint(pre["n_settled"])
    doc.status = STATUS_FINAL
    doc.save()
    frappe.db.commit()
    return {
        "name": doc.name, "chain": doc.chain, "status": doc.status,
        "n_settled": cint(doc.n_settled),
        "message": _("Đã chốt số dư đầu kỳ {0}. {1} hóa đơn trước ngày {2} rời khỏi công "
                     "nợ, {3} hóa đơn ở lại. Nợ đầu kỳ mang sang: {4} đ.").format(
            doc.chain, cint(doc.n_settled), cstr(doc.cutover_date), cint(pre["n_kept"]),
            "{:,.0f}".format(flt(doc.opening_debt))),
    }


@frappe.whitelist()
def reopen(name, company=None):
    """Mở lại về Nháp — tắt luật tất toán của chuỗi này."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    if doc.status != STATUS_FINAL:
        frappe.throw(_("Bản số dư của {0} đang ở trạng thái {1}, không phải bản đã chốt.")
                     .format(doc.chain, doc.status))
    n_was = cint(doc.n_settled)
    doc.status = STATUS_DRAFT
    # Xóa luôn con số đã chốt: giữ lại là màn hình vẫn khoe "N hóa đơn đã tất
    # toán" trong khi luật đã tắt và N hóa đơn đó đang nằm lại trong rổ nợ.
    doc.n_settled = 0
    doc.save()
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status,
            "message": _("Đã mở lại bản số dư {0}. Luật tất toán TẮT — {1} hóa đơn "
                         "trước ngày chốt quay lại rổ nợ ngay bây giờ. Chốt lại sau khi "
                         "sửa xong.").format(doc.chain, n_was)}


@frappe.whitelist()
def delete_opening(name, company=None):
    """Xóa một bản số dư — chỉ xóa được bản còn Nháp."""
    guard_manager()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)
    chain = doc.chain
    doc.delete()
    frappe.db.commit()
    return {"deleted": name, "chain": chain,
            "message": _("Đã xóa bản số dư đầu kỳ của {0}.").format(chain)}


@frappe.whitelist()
def settled_invoices(name, company=None, page=1, page_size=50):
    """Danh sách hóa đơn đã được tất toán nhờ bản số dư này."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    doc = _load(name, company)

    page = max(1, cint(page))
    page_size = min(200, max(10, cint(page_size) or 50))
    p = {}
    base = _settled_query(company, doc.chain, doc.cutover_date, doc.name, p)
    total = cint(frappe.db.sql("SELECT COUNT(*) " + base, p)[0][0])
    p["limit"] = page_size
    p["offset"] = (page - 1) * page_size
    rows = frappe.db.sql("""
        SELECT si.name, si.posting_date, si.customer, si.customer_name,
               ABS(si.grand_total) AS grand_total,
               IFNULL(p.paid, 0) AS paid
        """ + base + """
        ORDER BY si.posting_date DESC, si.name DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return {
        "rows": rows, "total": total, "page": page, "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "chain": doc.chain, "status": doc.status,
        "cutover_date": cstr(doc.cutover_date),
        "note": _(
            "Các hóa đơn này có ngày <= {0} và KHÔNG có tên trong danh sách còn nợ, nên "
            "được coi là đã thanh toán trước khi chuyển giao. {1}"
        ).format(cstr(doc.cutover_date),
                 _("Bản số dư đang ở trạng thái {0} nên luật CHƯA bật — đây là danh sách "
                   "dự kiến.").format(doc.status) if doc.status != STATUS_FINAL else ""),
    }
