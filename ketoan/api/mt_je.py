# -*- coding: utf-8 -*-
"""mt_je — sinh BÚT TOÁN NHÁP từ bảng kê thanh toán MT. Không bao giờ tự ghi sổ.

═══════════════════════════════════════════════════════════════════════════════
RÀNG BUỘC P0 — "KHÔNG GHI SỔ"
═══════════════════════════════════════════════════════════════════════════════

Module này chỉ tạo `Journal Entry` ở trạng thái **Draft** (`docstatus = 0`).
TUYỆT ĐỐI không `submit()` tự động, không tạo `Payment Entry`, không đụng
`GL Entry`. Con người duyệt trên portal (MT2-E) hoặc trên Desk.

Vì sao gắt tới vậy: dữ liệu đầu vào là file do CHUỖI SIÊU THỊ xuất ra, đọc bằng
parser của mình. Mọi mắt xích đều có thể sai, và một bút toán đã ghi sổ thì phải
hủy — để lại vết trong sổ cái mà kiểm toán sẽ hỏi. Nháp thì xóa được.

═══════════════════════════════════════════════════════════════════════════════
BA SỰ KIỆN, BA BÚT TOÁN (§4 SOP, chốt 20/08/2026)
═══════════════════════════════════════════════════════════════════════════════

    Loại dòng bảng kê    Sự kiện                 Bút toán
    ─────────────────────────────────────────────────────────────────────────
    Thanh toán           Nhận thanh toán         Nợ 112 · Có 131 MỘT DÒNG TỔNG
    Chiết khấu           Chiết khấu mình xuất    Nợ 5211 (+33311) · Có 131 GỘP
    Phí                  Phí chuỗi xuất          Nợ 6411 (+1331)  · Có 131 GỘP
    Ghi giảm             — KHÔNG sinh bút toán —
    Khác                 — KHÔNG sinh bút toán —

Số hiệu trên chỉ là ví dụ: TÀI KHOẢN THẬT lấy từ `MT Account Map`, không hardcode.

VÌ SAO 'Ghi giảm' và 'Khác' không sinh bút toán:
  · Ghi giảm = hàng trả / móp lỗi. SOP: đi đường chứng từ trả hàng của ERPNext
    + hóa đơn điều chỉnh MISA, KHÔNG ghi tay. Ghi tay là ghi hai lần một khoản.
  · Khác = tầng đọc file KHÔNG hiểu dòng đó. SOP: "treo, hỏi chuỗi lấy hóa
    đơn/biên bản trước". Ghi sổ một khoản chưa rõ chứng từ là tạo ra một khoản
    không giải trình được.
Cả hai đều được BÁO RÕ ở màn xem trước kèm số tiền — bỏ qua im lặng thì kế toán
tưởng đã ghi hết.

═══════════════════════════════════════════════════════════════════════════════
DÒNG 131 — LUÔN GHI TỔNG, KHÔNG THAM CHIẾU HÓA ĐƠN  (chốt 20/08/2026)
═══════════════════════════════════════════════════════════════════════════════

Cả ba bút toán đều ghi Có 131 bằng MỘT DÒNG TỔNG cho MỘT pháp nhân, không mang
`reference_type='Sales Invoice'`.

VÌ SAO không tách theo hóa đơn ở bút toán thanh toán: việc gạch hóa đơn nào đã
được trả bao nhiêu ĐÃ CÓ MÀN RIÊNG lo (tab 'Quản lý thanh toán'), và ở kênh này
con số "đã thu / còn lại" vốn tính từ CHÍNH CÁC DÒNG BẢNG KÊ chứ không từ
`outstanding_amount` của ERPNext — quyết định đó có từ MT-1. Dựng thêm cơ chế
gạch nợ thứ hai qua reference của JE là tạo HAI NGUỒN SỰ THẬT, và chúng sẽ lệch
nhau ngay kỳ đầu tiên có một hóa đơn bị điều chỉnh.

Với chiết khấu / phí thì còn một lý do dữ liệu nữa: phí của Central Retail
(`D1`), LOTTE (khoản `L`), Emart (`I1`), AEON (`Costdet`), Fuji (7 mục) đều tính
theo KỲ hoặc theo PHIẾU GIAO, không thuộc hóa đơn bán nào. Ép cứng reference thì
5/7 chuỗi không sinh được bút toán phí.

HỆ QUẢ KẾ TOÁN PHẢI BIẾT — và câu này hiện ngay trên màn duyệt, không giấu trong
tooltip: bút toán MT làm GIẢM SỐ DƯ 131 CỦA KHÁCH nhưng KHÔNG giảm
`outstanding_amount` của từng hóa đơn.

Bù lại, `user_remark` ghi ĐẦY ĐỦ để tra ngược được mà không cần mở bảng kê:
chuỗi · kỳ · số chứng từ · danh sách hóa đơn đã gạch (bút toán thanh toán) hoặc
danh sách từng khoản trừ + chứng từ của chuỗi (bút toán chiết khấu/phí). Riêng
Co.op tính 17,75% theo TỪNG hóa đơn thì liệt kê luôn từng hóa đơn.

LỢI THÊM CỦA CÁCH GHI TỔNG: dòng thanh toán chưa nối được hóa đơn vẫn vào bút
toán. Ở bản tách-theo-hóa-đơn chúng buộc phải bị loại để bút toán còn cân, nên
tiền thật đã về mà không được ghi sổ.

═══════════════════════════════════════════════════════════════════════════════
CHỐNG SINH TRÙNG
═══════════════════════════════════════════════════════════════════════════════

`custom_mt_fingerprint` = sha1 của (nguồn, loại, ngày, tổng tiền). Đã có JE mang
cùng vân tay và `docstatus != 2` -> KHÔNG sinh lại. Không có chốt này thì bấm hai lần (mạng chậm, người sốt ruột) là hai bộ bút
toán y hệt nhau, và duyệt cả hai là trừ công nợ khách GẤP ĐÔI.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from ketoan.api._guard import guard_manager, guard_mt
from ketoan.mt.doctype.mt_account_map.mt_account_map import (
    EVENT_DISCOUNT,
    EVENT_FEE,
    EVENT_PAYMENT,
)
from ketoan.mt.doctype.mt_account_map.mt_account_map import resolve as resolve_accounts
from ketoan.mt.doctype.mt_payment_advice.mt_payment_advice import (
    JE_STATE_ALL,
    JE_STATE_DRAFT,
    JE_STATE_NONE,
    JE_STATE_PARTIAL,
)
from ketoan.utils import je_remark_field

SOURCE_DT = "MT Payment Advice"

KIND_PAYMENT = "Thanh toán"
KIND_DISCOUNT = "Chiết khấu"
KIND_FEE = "Phí"
KIND_DEDUCT = "Ghi giảm"
KIND_OTHER = "Khác"

# Loại dòng bảng kê -> (sự kiện MT Account Map, nhãn custom_mt_kind).
# Thứ tự quyết định thứ tự bút toán trên màn xem trước: tiền về trước, khoản trừ sau.
KIND_TO_EVENT = (
    (KIND_PAYMENT, EVENT_PAYMENT, "Thanh toán"),
    (KIND_DISCOUNT, EVENT_DISCOUNT, "Chiết khấu"),
    (KIND_FEE, EVENT_FEE, "Phí"),
)

# Loại dòng CỐ Ý không sinh bút toán, kèm lý do hiện ra cho kế toán.
NO_JE_REASON = {
    KIND_DEDUCT: ("Hàng trả / ghi giảm đi đường chứng từ trả hàng của ERPNext + hóa đơn "
                  "điều chỉnh MISA (§4 SOP). Ghi bút toán tay ở đây là ghi HAI LẦN một khoản."),
    KIND_OTHER: ("Tầng đọc file KHÔNG hiểu loại dòng này. §4 SOP: treo lại, hỏi chuỗi lấy "
                 "hóa đơn/biên bản trước. Ghi sổ khoản chưa rõ chứng từ là tạo ra một khoản "
                 "không giải trình được."),
}

def _require_tables():
    for dt in (SOURCE_DT, "MT Payment Advice Line", "MT Account Map"):
        if not frappe.db.table_exists(dt):
            frappe.throw(_(
                "Chức năng sinh bút toán MT chưa được cài trên site này (thiếu bảng {0}). "
                "Quản trị chạy: bench --site TÊN_SITE migrate"
            ).format(dt))
    # Custom field do PATCH tạo, không do migrate DocType. Thiếu nó thì bút toán
    # sinh ra không truy ngược được VÀ mất sạch chốt chống trùng — nguy hiểm hơn
    # là không sinh được.
    for col in ("custom_mt_source_name", "custom_mt_fingerprint", "custom_mt_kind"):
        if not frappe.db.has_column("Journal Entry", col):
            frappe.throw(_(
                "Journal Entry chưa có field truy vết của kênh MT ({0}). Quản trị chạy: "
                "bench --site TÊN_SITE migrate (patch v0_0_14)."
            ).format(col))


def _company(company=None):
    from ketoan.api.mt import _company as _mt_company
    return _mt_company(company)


# ─────────────────────────────────────────────────────────────────────────
# Dựng kế hoạch bút toán
# ─────────────────────────────────────────────────────────────────────────

def _load_advice(advice, company):
    doc = frappe.get_doc(SOURCE_DT, advice)
    if cstr(doc.company) != cstr(company):
        # Bảng kê của công ty khác: đọc được là rò rỉ công nợ, ghi được là bút
        # toán chui sang sổ công ty khác.
        frappe.throw(_("Bảng kê {0} thuộc công ty {1}, không phải {2}")
                     .format(doc.name, doc.company, company))
    return doc


def _line_amount(row):
    """Tiền của MỘT dòng THANH TOÁN = ĐỘ LỚN.

    `MT Payment Advice Line.total_amount` lưu số GIỮ NGUYÊN DẤU của file (xem
    `mt._map_rows`). Ở dòng thanh toán, mỗi chuỗi một quy ước dấu (Central
    Retail/Emart để hàng hóa ÂM, LOTTE/AEON để DƯƠNG) nên dấu không mang thông
    tin — lấy độ lớn là đúng, và trùng quy ước với `mt._paid_subquery`
    (SUM(ABS(...))) nên số trên bút toán khớp số 'đã thu' trên màn hình.

    CHỈ dùng cho dòng thanh toán. Nhóm khoản trừ phải dùng `_group_amount`.
    """
    return abs(flt(row.get("total_amount")))


def _group_amount(rows):
    """Tiền của MỘT NHÓM khoản trừ = TRỊ TUYỆT ĐỐI CỦA TỔNG ĐẠI SỐ.

    KHÔNG phải tổng các trị tuyệt đối. Đã đo trên file thật: khoản trừ của AEON
    có 8 dòng ÂM (hoàn lại) xen giữa các dòng dương, và `Sub-Total` mà chính
    AEON in ra — cũng là số mà tầng đọc file đã đối chiếu khớp — là tổng ĐẠI SỐ.

        sum(|x|)      = 11.023.025   ← SAI, ghi khống 598.208đ chi phí
        |sum(x)|      = 10.424.817   ← đúng bằng 'Deduction' AEON in ra

    Lệch đúng HAI LẦN tổng các dòng âm. Đây là chỗ dễ sai nhất của cả module:
    con số sai vẫn trông hợp lý, bút toán vẫn CÂN, và không tổng nào trên màn
    hình phát hiện ra — chỉ lộ khi đối chiếu với sao kê ngân hàng.

    Khác với dòng thanh toán: ở đó mỗi dòng gắn một hóa đơn riêng nên phải cộng
    độ lớn từng dòng; ở đây cả nhóm gộp thành MỘT dòng 131 nên cái cần là số
    tiền RÒNG mà chuỗi thật sự trừ.
    """
    return abs(sum(flt(r.get("total_amount")) for r in rows))


def _has_mixed_signs(rows):
    """Nhóm có cả dòng âm lẫn dòng dương? -> phải nói ra, đừng gộp im lặng."""
    vals = [flt(r.get("total_amount")) for r in rows if flt(r.get("total_amount"))]
    return any(v > 0 for v in vals) and any(v < 0 for v in vals)


def _fingerprint(source_name, kind, posting_date, total):
    """Vân tay CHỐNG SINH TRÙNG của một bút toán.

    (nguồn, loại, ngày, tổng tiền) đã đủ định danh: mỗi bảng kê có ĐÚNG một bút
    toán mỗi loại, và cả ba loại đều ghi một dòng tổng. Sinh lại sau khi sửa
    bảng kê thì tổng đổi -> vân tay đổi -> sinh được, đúng ý.
    """
    h = hashlib.sha1()
    h.update("MTJE|{}|{}|{}|{}|{:.2f}\n".format(
        SOURCE_DT, source_name, kind, cstr(posting_date), flt(total)).encode())
    return h.hexdigest()


def _split_tax(total, lines, tax_rate):
    """(tiền trước thuế, tiền thuế). KHÔNG đoán khi file không cho biết.

    Thứ tự ưu tiên:
      1. File có in tách `vat_amount` -> dùng ĐÚNG số của file.
      2. File không tách nhưng kế toán đã KHAI thuế suất ở MT Account Map ->
         tách theo thuế suất đó. Đây không phải đoán: con người khai.
      3. Không có cả hai -> KHÔNG tách, dồn hết vào TK Nợ chính và nói rõ ở
         `user_remark`. 6/7 chuỗi chỉ có MỘT cột tiền (đã gồm thuế); tự chia
         cho 1,1 để "suy ra" thuế là bịa số.
    """
    declared = sum(flt(r.get("vat_amount")) for r in lines if r.get("vat_amount"))
    if declared:
        return flt(total) - flt(declared), flt(declared), "file in tách tiền thuế"
    if flt(tax_rate) > 0:
        base = flt(total) / (1 + flt(tax_rate) / 100.0)
        return base, flt(total) - base, "tách theo thuế suất %s%% khai ở MT Account Map" % tax_rate
    return flt(total), 0.0, ""


def _remark_payment(doc, rows, matched, n_unmatched):
    """Diễn giải bút toán thanh toán — ghi đủ để tra ngược mà không cần mở bảng kê."""
    parts = [
        "Nhận thanh toán %s" % (doc.chain or ""),
        "bảng kê %s" % doc.name,
    ]
    if doc.advice_no:
        parts.append("số chứng từ %s" % doc.advice_no)
    if doc.payment_date:
        parts.append("ngày %s" % cstr(doc.payment_date))
    if doc.file_name:
        parts.append("file %s" % doc.file_name)
    lines = [" · ".join(parts)]
    lines.append("Ghi TỔNG thanh toán của kỳ: %d dòng bảng kê, %d hóa đơn đã gạch được%s."
                 % (len(rows), len(matched),
                    ", %d dòng chưa gạch" % n_unmatched if n_unmatched else ""))

    # Liệt kê hóa đơn để tra ngược ĐƯỢC mà không cần mở bảng kê — bù cho việc
    # dòng 131 không mang reference. Người mở bút toán sau ba tháng cần thấy
    # ngay kỳ này trả cho những hóa đơn nào.
    keys = sorted(matched)
    for si in keys[:60]:
        lines.append("  • %s: %s đ" % (si, "{:,.0f}".format(matched[si]["amount"])))
    if len(keys) > 60:
        lines.append("  • …và %d hóa đơn nữa (xem bảng kê %s)" % (len(keys) - 60, doc.name))

    lines.append("LƯU Ý: bút toán này giảm SỐ DƯ 131 của khách, KHÔNG giảm outstanding "
                 "của từng hóa đơn. Việc gạch từng hóa đơn do tab 'Quản lý thanh toán' "
                 "lo, tính từ chính các dòng bảng kê.")
    return "\n".join(lines)


def _remark_deduction(doc, kind_label, rows, tax_note):
    """Diễn giải ĐẦY ĐỦ cho bút toán gộp — bù cho việc không reference hóa đơn."""
    parts = [
        "%s %s" % (kind_label, doc.chain or ""),
        "bảng kê %s" % doc.name,
    ]
    if doc.advice_no:
        parts.append("số chứng từ %s" % doc.advice_no)
    if doc.payment_date:
        parts.append("kỳ %s" % cstr(doc.payment_date))
    lines = [" · ".join(parts)]

    # Số hóa đơn CỦA CHUỖI xuất cho mình (Central Retail 'D1', AEON 'TAX INVOICE',
    # Emart 'I1'...) nằm ở `doc_no`. Đây là chứng từ gốc của khoản trừ.
    chain_docs = sorted({cstr(r.get("doc_no")) for r in rows if r.get("doc_no")})
    if chain_docs:
        lines.append("Chứng từ của chuỗi: " + ", ".join(chain_docs[:30])
                     + (" …(+%d)" % (len(chain_docs) - 30) if len(chain_docs) > 30 else ""))

    lines.append("Chi tiết %d khoản:" % len(rows))
    for r in rows[:60]:
        desc = cstr(r.get("row_subtype") or r.get("description") or "").strip()
        # Co.op tính 17,75% theo TỪNG hóa đơn -> dữ liệu có sẵn thì phải ghi ra,
        # đó mới đúng nghĩa "ghi tham chiếu đầy đủ" của quyết định Q1.
        ref = ""
        if r.get("inv_no"):
            ref = " [HĐ %s%s]" % (cstr(r.get("inv_series") or ""), cstr(r["inv_no"]))
        lines.append("  • %s%s: %s đ" % (desc[:70] or "(không diễn giải)", ref,
                                         "{:,.0f}".format(_line_amount(r))))
    if len(rows) > 60:
        lines.append("  • …và %d khoản nữa (xem bảng kê %s)" % (len(rows) - 60, doc.name))

    lines.append("LƯU Ý: bút toán gộp này làm GIẢM SỐ DƯ 131 của khách nhưng KHÔNG "
                 "giảm outstanding của từng hóa đơn — chuỗi trừ khoản này vào tổng "
                 "thanh toán của kỳ, không trừ vào một hóa đơn cụ thể.")
    if tax_note:
        lines.append("Thuế: " + tax_note)
    else:
        lines.append("Thuế: file KHÔNG tách tiền thuế và MT Account Map chưa khai thuế "
                     "suất — toàn bộ ghi vào TK Nợ chính, KHÔNG tự suy ra thuế.")
    return "\n".join(lines)


def _build_plan(doc):
    """Kế hoạch bút toán của MỘT bảng kê. THUẦN ĐỌC — không ghi gì.

    Trả (plan, warnings). Mỗi phần tử `plan` là một bút toán sẽ sinh.
    """
    warnings = []

    posting_date = cstr(doc.payment_date or "")
    if not posting_date:
        # Fuji không in ngày thanh toán trong file. Không có ngày thì bút toán
        # rơi vào ngày hôm nay — sai kỳ kế toán mà không có gì báo.
        frappe.throw(_(
            "Bảng kê {0} chưa có Ngày thanh toán. Điền ngày trước khi sinh bút toán — "
            "bút toán không có ngày sẽ rơi vào sai kỳ kế toán."
        ).format(doc.name))

    rows_by_kind = {}
    for r in doc.lines or []:
        rows_by_kind.setdefault(cstr(r.row_kind), []).append(r.as_dict())

    # Loại dòng CỐ Ý không sinh bút toán — báo rõ kèm tiền, không im lặng.
    not_posted = []
    for kind, reason in NO_JE_REASON.items():
        rows = rows_by_kind.get(kind) or []
        if rows:
            item = {
                "row_kind": kind,
                "n_rows": len(rows),
                # Tổng ĐẠI SỐ (xem `_group_amount`): nhóm có dòng âm lẫn dương
                # thì cộng độ lớn từng dòng ra số khống.
                "amount": _group_amount(rows),
                "reason": reason,
            }
            if _has_mixed_signs(rows):
                item["mixed_signs"] = True
                item["amount_gross"] = sum(_line_amount(r) for r in rows)
            not_posted.append(item)

    plan = []
    for kind, event, je_kind in KIND_TO_EVENT:
        rows = rows_by_kind.get(kind) or []
        if not rows:
            continue
        acc = resolve_accounts(event, doc.chain, doc.company)
        if kind == KIND_PAYMENT:
            entry = _plan_payment(doc, rows, acc, je_kind, posting_date, warnings)
        else:
            entry = _plan_deduction(doc, rows, acc, je_kind, event, posting_date, warnings)
        if entry:
            plan.append(entry)

    for e in plan:
        e["duplicate"] = _existing_je(e["fingerprint"])

    return plan, warnings, not_posted


def _plan_payment(doc, rows, acc, je_kind, posting_date, warnings):
    """Nợ 112 · Có 131 MỘT DÒNG TỔNG. Không tách theo hóa đơn.

    CHỐT 20/08/2026 (thay quyết định Q1 cũ): dòng 131 thanh toán chỉ ghi TỔNG
    THANH TOÁN của kỳ, không tách một dòng cho mỗi hóa đơn.

    VÌ SAO đúng: việc gạch hóa đơn nào đã được trả bao nhiêu ĐÃ CÓ MÀN RIÊNG lo
    (tab 'Quản lý thanh toán'), và ở kênh này con số 'đã thu / còn lại' vốn tính
    từ CHÍNH CÁC DÒNG BẢNG KÊ chứ không từ `outstanding_amount` của ERPNext —
    đó là quyết định từ MT-1, không phải phát sinh mới. Nhân đôi cơ chế gạch nợ
    (một ở bảng kê, một ở reference của JE) là hai nguồn sự thật sẽ lệch nhau.

    Hệ quả phải nói ra, và nó hiện trên màn duyệt: bút toán này làm GIẢM SỐ DƯ
    131 của khách nhưng KHÔNG giảm `outstanding_amount` của từng hóa đơn. Giống
    hệt bút toán chiết khấu/phí.

    LỢI THÊM: dòng thanh toán CHƯA nối được hóa đơn vẫn vào bút toán. Ở bản cũ
    (tách theo hóa đơn) chúng buộc phải bị loại để bút toán còn cân, nên tiền
    thật đã về mà không được ghi sổ.
    """
    if not doc.customer:
        # Dòng 131 phải có party. Không có khách thì bút toán không trừ được nợ
        # của ai — mà ERPNext vẫn cho ghi, nên phải chặn ở đây.
        frappe.throw(_(
            "Bảng kê {0} chưa gán Khách hàng. Bút toán thanh toán ghi Có 131 cho MỘT "
            "pháp nhân, không có khách thì không trừ được công nợ của ai."
        ).format(doc.name))

    total = _group_amount(rows)
    if not total:
        return None

    # Thống kê để người duyệt biết tình trạng gạch hóa đơn của kỳ này — CHỈ để
    # thông tin, không còn ảnh hưởng tới số tiền của bút toán nữa.
    matched, n_unmatched, n_review = {}, 0, 0
    for r in rows:
        amt = _line_amount(r)
        si = cstr(r.get("sales_invoice") or "")
        if not si:
            n_unmatched += 1
            continue
        if cstr(r.get("match_confidence")) != "Chắc chắn":
            n_review += 1
        g = matched.setdefault(si, {"sales_invoice": si, "amount": 0.0, "n_rows": 0})
        g["amount"] += amt
        g["n_rows"] += 1

    # Hóa đơn của KHÁCH KHÁC lọt vào bảng kê này: tiền đang được ghi Có 131 cho
    # `doc.customer` trong khi hóa đơn thuộc pháp nhân khác. Không chặn (một
    # chuỗi có nhiều pháp nhân, và bảng kê có thể trả gộp) nhưng phải báo.
    si_info = _invoice_info(list(matched))
    other_customer = sorted({
        cstr(si_info[si].customer) for si in matched
        if si in si_info and si_info[si].customer
        and cstr(si_info[si].customer) != cstr(doc.customer)})
    if other_customer:
        warnings.append(
            "Bảng kê %s: có hóa đơn thuộc khách khác (%s) trong khi bút toán ghi Có 131 "
            "cho %s. Kiểm lại trước khi duyệt — tiền đang trừ nợ của pháp nhân này."
            % (doc.name, ", ".join(other_customer[:3]), doc.customer))
    if n_unmatched:
        warnings.append(
            "Bảng kê %s: %d dòng thanh toán chưa nối được hóa đơn. Tiền VẪN vào bút toán "
            "(bút toán ghi tổng), nhưng hóa đơn tương ứng chưa được gạch — xử lý ở tab "
            "'Quản lý thanh toán'." % (doc.name, n_unmatched))
    if n_review:
        warnings.append(
            "Bảng kê %s: %d dòng nối hóa đơn ở mức 'Cần review' — không ảnh hưởng số tiền "
            "bút toán, nhưng phải soi tay ở màn gạch hóa đơn." % (doc.name, n_review))

    return {
        "kind": je_kind,
        "event": EVENT_PAYMENT,
        "accounts": acc,
        "posting_date": posting_date,
        "total": total,
        "debit_lines": [{"account": acc["debit_account"], "amount": total,
                         "label": "Tiền về"}],
        "credit_lines": [{
            "account": acc["credit_account"], "amount": total,
            "party_type": "Customer", "party": doc.customer,
            "party_name": frappe.db.get_value("Customer", doc.customer, "customer_name"),
            "reference_type": None, "reference_name": None,
            "n_rows": len(rows),
        }],
        "remark": _remark_payment(doc, rows, matched, n_unmatched),
        "n_review": n_review,
        "n_invoices": len(matched),
        "n_unmatched": n_unmatched,
        "mixed_signs": _has_mixed_signs(rows),
        "amount_gross": (sum(_line_amount(r) for r in rows)
                         if _has_mixed_signs(rows) else None),
        "note_no_reference": (
            "Bút toán ghi TỔNG thanh toán: giảm số dư 131 của khách, KHÔNG giảm "
            "outstanding của từng hóa đơn. Việc gạch từng hóa đơn do tab "
            "'Quản lý thanh toán' lo, tính từ chính các dòng bảng kê."),
        "fingerprint": _fingerprint(doc.name, je_kind, posting_date, total),
    }


def _plan_deduction(doc, rows, acc, je_kind, event, posting_date, warnings):
    """Nợ 6411/5211 (+thuế) · Có 131 MỘT DÒNG GỘP. Không reference hóa đơn."""
    # Tổng ĐẠI SỐ, không phải tổng độ lớn — xem `_group_amount`. Sai chỗ này là
    # ghi khống chi phí đúng hai lần tổng các dòng âm.
    total = _group_amount(rows)
    if not total:
        return None

    if not doc.customer:
        # Dòng 131 phải có party. Không có khách thì bút toán không trừ được nợ
        # của ai — và ERPNext vẫn cho ghi, nên phải chặn ở đây.
        frappe.throw(_(
            "Bảng kê {0} chưa gán Khách hàng. Bút toán {1} ghi Có 131 cho MỘT pháp nhân, "
            "không có khách thì không trừ được công nợ của ai."
        ).format(doc.name, je_kind))

    base, tax, tax_note = _split_tax(total, rows, acc.get("tax_rate"))
    debit_lines = [{"account": acc["debit_account"], "amount": base, "label": je_kind}]
    if tax:
        if not acc.get("tax_account"):
            # Có tiền thuế mà không có TK thuế: dồn hết vào TK Nợ chính là ghi
            # thuế GTGT vào chi phí — sai bản chất và mất khấu trừ.
            frappe.throw(_(
                "Bảng kê {0}: xác định được {1} đ tiền thuế nhưng MT Account Map của sự "
                "kiện '{2}' chưa khai TK Nợ thuế. Khai TK thuế rồi làm lại."
            ).format(doc.name, "{:,.0f}".format(tax), event))
        debit_lines.append({"account": acc["tax_account"], "amount": tax, "label": "Thuế GTGT"})

    return {
        "kind": je_kind,
        "event": event,
        "accounts": acc,
        "posting_date": posting_date,
        "total": total,
        "debit_lines": debit_lines,
        "credit_lines": [{
            "account": acc["credit_account"], "amount": total,
            "party_type": "Customer", "party": doc.customer,
            "party_name": frappe.db.get_value("Customer", doc.customer, "customer_name"),
            "reference_type": None, "reference_name": None,
            "n_rows": len(rows),
        }],
        "remark": _remark_deduction(doc, je_kind, rows, tax_note),
        "n_review": 0,
        # Nhóm có cả dòng âm lẫn dương -> bút toán ghi số RÒNG. Phải nói ra:
        # kế toán đối chiếu với hóa đơn của chuỗi sẽ thấy tổng gộp lớn hơn.
        "mixed_signs": _has_mixed_signs(rows),
        "amount_gross": (sum(_line_amount(r) for r in rows)
                         if _has_mixed_signs(rows) else None),
        # Bút toán gộp không gắn hóa đơn nào -> vân tay không có phần SI.
        "fingerprint": _fingerprint(doc.name, je_kind, posting_date, total),
        "note_no_reference": (
            "Bút toán gộp: giảm số dư 131 của khách, KHÔNG giảm outstanding của "
            "từng hóa đơn. Diễn giải ghi đủ chứng từ của chuỗi."),
    }


def _invoice_info(names):
    if not names:
        return {}
    rows = frappe.db.sql("""
        SELECT si.name, si.customer, si.customer_name, si.grand_total,
               si.outstanding_amount, si.docstatus
        FROM `tabSales Invoice` si
        WHERE si.name IN %(names)s
    """, {"names": tuple(names)}, as_dict=True)
    return {r.name: r for r in rows}


def _existing_je(fingerprint):
    """JE đã mang vân tay này và CHƯA bị hủy -> tên bút toán. Không thì None.

    Bỏ qua `docstatus = 2` (đã hủy) là cố ý: hủy rồi thì sinh lại được, đó chính
    là cách sửa một bút toán ghi sai.
    """
    if not fingerprint:
        return None
    return frappe.db.get_value("Journal Entry", {
        "custom_mt_fingerprint": fingerprint,
        "docstatus": ("!=", 2),
    }, "name")


def _plan_hash(plan):
    """Vân tay của ĐÚNG kế hoạch người vừa xem."""
    h = hashlib.sha1()
    for e in plan:
        h.update("E|{}|{}|{:.2f}|{}\n".format(
            e["kind"], e["posting_date"], flt(e["total"]), e["fingerprint"]).encode())
        for ln in e["credit_lines"]:
            h.update("C|{}|{}|{:.2f}\n".format(
                ln.get("reference_name") or "", ln.get("party") or "",
                flt(ln["amount"])).encode())
        for ln in e["debit_lines"]:
            h.update("D|{}|{:.2f}\n".format(ln["account"], flt(ln["amount"])).encode())
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# Trạng thái bút toán của bảng kê
# ─────────────────────────────────────────────────────────────────────────

def compute_je_state(advice):
    """`je_state` suy từ docstatus của các JE mang `custom_mt_source_name = advice`."""
    rows = frappe.db.sql("""
        SELECT docstatus, COUNT(*) AS n
        FROM `tabJournal Entry`
        WHERE custom_mt_source_dt = %(dt)s AND custom_mt_source_name = %(name)s
          AND docstatus != 2
        GROUP BY docstatus
    """, {"dt": SOURCE_DT, "name": advice}, as_dict=True)
    n_draft = sum(cint(r.n) for r in rows if cint(r.docstatus) == 0)
    n_sub = sum(cint(r.n) for r in rows if cint(r.docstatus) == 1)
    if not (n_draft or n_sub):
        return JE_STATE_NONE
    if not n_sub:
        return JE_STATE_DRAFT
    return JE_STATE_ALL if not n_draft else JE_STATE_PARTIAL


def _set_je_state(advice):
    """Ghi `je_state` bằng `db_set`, KHÔNG `save()`.

    VÌ SAO: `save()` chạy lại toàn bộ `validate()` của bảng kê — trong đó có chốt
    "trạng thái 'Đã ghi nhận' phải có je_state = Đã duyệt đủ". Gọi từ hook
    `on_submit` của JE thì bảng kê đang ở giữa chừng, và validate sẽ ném lỗi
    NGƯỢC LẠI vào giao dịch ghi sổ đang chạy — làm hỏng việc submit một bút toán
    hoàn toàn hợp lệ. `update_modified=False` để không đụng vào dấu vết sửa đổi
    của kế toán.
    """
    state = compute_je_state(advice)
    if frappe.db.get_value(SOURCE_DT, advice, "je_state") != state:
        frappe.db.set_value(SOURCE_DT, advice, "je_state", state, update_modified=False)
    return state


def sync_advice_state(doc, method=None):
    """Hook `Journal Entry.on_submit` / `on_cancel` -> cập nhật `je_state` của bảng kê.

    VÌ SAO cần hook chứ không chỉ cập nhật trong portal: kế toán hoàn toàn có thể
    submit/cancel bút toán THẲNG TRÊN DESK, không qua portal. Thiếu hook thì bảng
    kê đứng mãi ở "Đã sinh nháp" trong khi bút toán đã ghi sổ — màn hình nói dối.

    BỌC try/except TOÀN BỘ: tích hợp MT hỏng KHÔNG được chặn việc ghi sổ. Cùng
    nguyên tắc với `misa_sync.ensure_ref_id`.
    """
    try:
        if cstr(getattr(doc, "custom_mt_source_dt", "")) != SOURCE_DT:
            return
        name = cstr(getattr(doc, "custom_mt_source_name", ""))
        if not name or not frappe.db.exists(SOURCE_DT, name):
            return
        _set_je_state(name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan: mt_je.sync_advice_state")


# ═══════════════════════════════════════════════════════════════════════════
# Whitelisted
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_account_map(company=None):
    """Bảng tài khoản đang áp dụng — để màn xem trước nói rõ bút toán vào TK nào."""
    guard_mt()
    _require_tables()
    company = _company(company)

    rows = frappe.db.sql("""
        SELECT m.name, m.event, m.chain, m.active, m.tax_rate, m.note,
               m.debit_account, m.tax_account, m.credit_account,
               da.account_number AS debit_no, da.account_name AS debit_name,
               ta.account_number AS tax_no, ta.account_name AS tax_name,
               ca.account_number AS credit_no, ca.account_name AS credit_name
        FROM `tabMT Account Map` m
        LEFT JOIN `tabAccount` da ON da.name = m.debit_account
        LEFT JOIN `tabAccount` ta ON ta.name = m.tax_account
        LEFT JOIN `tabAccount` ca ON ca.name = m.credit_account
        WHERE m.company = %(company)s
        ORDER BY m.event, IFNULL(m.chain, '')
    """, {"company": company}, as_dict=True)

    incomplete = [r.name for r in rows
                  if cint(r.active) and not (r.debit_account and r.credit_account)]
    return {
        "company": company,
        "rows": rows,
        "incomplete": incomplete,
        "note": _(
            "Bút toán MT lấy tài khoản TỪ BẢNG NÀY, không hardcode trong mã. Dòng có "
            "chuỗi cụ thể thắng dòng để trống (mặc định). Thiếu cấu hình thì hệ thống "
            "DỪNG chứ không lấy tài khoản đoán."
        ),
    }


@frappe.whitelist()
def list_advices(from_date=None, to_date=None, chain=None, je_state=None,
                 search=None, page=1, page_size=20, company=None):
    """Bảng kê + trạng thái bút toán của từng cái. Chỉ đọc, có lọc và chia trang.

    `je_state` được đọc TỪ BẢNG, không tính lại từng dòng: tính lại cho 20 bảng
    kê là 20 truy vấn phụ. Trường này đã do `sync_advice_state` (hook JE) và
    `create_journal_entries` giữ cho đúng.
    """
    guard_mt()
    _require_tables()
    company = _company(company)

    page = max(1, cint(page) or 1)
    page_size = min(100, max(1, cint(page_size) or 20))

    where = ["a.company = %(company)s"]
    params = {"company": company}
    if from_date and to_date:
        where.append("a.payment_date BETWEEN %(fd)s AND %(td)s")
        params["fd"], params["td"] = from_date, to_date
    if chain:
        where.append("a.chain = %(chain)s")
        params["chain"] = chain
    if je_state:
        # Bảng kê chưa từng sinh bút toán có `je_state` NULL chứ không phải
        # 'Chưa sinh' — lọc thẳng bằng '=' là mất hết chúng.
        where.append("IFNULL(a.je_state, %(none)s) = %(jestate)s")
        params["jestate"] = je_state
        params["none"] = JE_STATE_NONE
    if search:
        where.append("(a.name LIKE %(q)s OR IFNULL(a.advice_no,'') LIKE %(q)s "
                     "OR IFNULL(a.customer,'') LIKE %(q)s OR IFNULL(a.file_name,'') LIKE %(q)s)")
        params["q"] = "%" + cstr(search).strip() + "%"
    clause = " AND ".join(where)

    total = cint(frappe.db.sql(
        "SELECT COUNT(*) FROM `tabMT Payment Advice` a WHERE " + clause, params)[0][0])

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = frappe.db.sql("""
        SELECT a.name, a.chain, a.customer, cus.customer_name, a.advice_no,
               a.payment_date, a.status, a.reconciled,
               IFNULL(a.je_state, %(none_state)s) AS je_state,
               a.total_payment, a.total_discount, a.total_fee, a.total_other,
               a.file_name,
               (SELECT COUNT(*) FROM `tabJournal Entry` je
                 WHERE je.custom_mt_source_dt = %(dt)s
                   AND je.custom_mt_source_name = a.name AND je.docstatus = 0) AS je_draft,
               (SELECT COUNT(*) FROM `tabJournal Entry` je
                 WHERE je.custom_mt_source_dt = %(dt)s
                   AND je.custom_mt_source_name = a.name AND je.docstatus = 1) AS je_submitted
        FROM `tabMT Payment Advice` a
        LEFT JOIN `tabCustomer` cus ON cus.name = a.customer
        WHERE {clause}
        ORDER BY a.payment_date DESC, a.creation DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """.format(clause=clause),
        dict(params, dt=SOURCE_DT, none_state=JE_STATE_NONE), as_dict=True)

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 1,
        "je_states": [JE_STATE_NONE, JE_STATE_DRAFT, JE_STATE_PARTIAL, JE_STATE_ALL],
        "can_create": bool(frappe.get_all("MT Account Map",
                                          filters={"company": company, "active": 1},
                                          limit_page_length=1)),
    }


@frappe.whitelist()
def preview_journal_entries(advice, company=None):
    """XEM TRƯỚC bút toán sẽ sinh cho MỘT bảng kê. KHÔNG ghi bất cứ thứ gì.

    Bắt buộc chạy trước `create_journal_entries` — trả `plan_hash` mà nó đòi.
    """
    guard_mt()
    _require_tables()
    company = _company(company)

    doc = _load_advice(advice, company)
    plan, warnings, not_posted = _build_plan(doc)

    return {
        "advice": doc.name,
        "chain": doc.chain,
        "customer": doc.customer,
        "payment_date": cstr(doc.payment_date or ""),
        "advice_no": doc.advice_no,
        "reconciled": cint(doc.reconciled),
        "je_state": doc.je_state or JE_STATE_NONE,
        "plan_hash": _plan_hash(plan),
        "entries": plan,
        "not_posted": not_posted,
        "warnings": warnings,
        "can_create": bool(plan) and not all(e["duplicate"] for e in plan),
        "note": _(
            "Bút toán được sinh ở trạng thái NHÁP. Hệ thống KHÔNG bao giờ tự ghi sổ — "
            "con người duyệt ở tab 'Duyệt bút toán'."
        ),
    }


@frappe.whitelist()
def create_journal_entries(advice, expected_hash=None, company=None):
    """Sinh Journal Entry NHÁP. KHÔNG submit — không bao giờ, không có tham số bật.

    Đòi vân tay của bản xem trước: dữ liệu đổi giữa chừng là dừng, không ghi gì.
    """
    guard_manager()
    _require_tables()
    company = _company(company)

    doc = _load_advice(advice, company)
    plan, warnings, not_posted = _build_plan(doc)

    if not plan:
        frappe.throw(_("Bảng kê này không sinh được bút toán nào"))
    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới sinh bút toán được"))
    if _plan_hash(plan) != expected_hash:
        frappe.throw(_(
            "Dữ liệu đã đổi kể từ lúc xem trước (liên kết hóa đơn hoặc cấu hình tài "
            "khoản đã thay đổi). Xem lại rồi sinh — không ghi gì cả."
        ))

    remark_field = je_remark_field()
    created, skipped_dup, failed = [], [], []

    for i, e in enumerate(plan):
        if e["duplicate"]:
            # Vân tay trùng = bút toán này đã sinh rồi. Sinh lại rồi duyệt cả hai
            # là trừ công nợ khách GẤP ĐÔI.
            skipped_dup.append({"kind": e["kind"], "journal_entry": e["duplicate"]})
            continue
        sp = "mt_je_%d" % i
        try:
            frappe.db.savepoint(sp)
            je = frappe.new_doc("Journal Entry")
            je.voucher_type = "Journal Entry"
            je.company = company
            je.posting_date = e["posting_date"]
            je.set(remark_field, e["remark"])
            je.custom_mt_source_dt = SOURCE_DT
            je.custom_mt_source_name = doc.name
            je.custom_mt_kind = e["kind"]
            je.custom_mt_fingerprint = e["fingerprint"]

            for ln in e["debit_lines"]:
                je.append("accounts", {
                    "account": ln["account"],
                    "debit_in_account_currency": flt(ln["amount"]),
                })
            for ln in e["credit_lines"]:
                # KHÔNG gắn `reference_type`/`reference_name`: bút toán MT ghi
                # TỔNG, việc gạch từng hóa đơn do tab 'Quản lý thanh toán' lo.
                # Nhánh này giữ lại để nếu sau có loại bút toán cần reference
                # thì chỉ việc điền, chứ không phải sửa vòng lặp.
                row = {
                    "account": ln["account"],
                    "credit_in_account_currency": flt(ln["amount"]),
                    "party_type": ln["party_type"],
                    "party": ln["party"],
                }
                if ln.get("reference_name"):
                    row["reference_type"] = ln["reference_type"]
                    row["reference_name"] = ln["reference_name"]
                je.append("accounts", row)

            # NHÁP. Không `submit()`, không `flags.ignore_permissions`: bút toán
            # phải được tạo DƯỚI QUYỀN của người bấm, đúng ràng buộc P0.
            je.insert()
            created.append({"name": je.name, "kind": e["kind"],
                            "total": flt(e["total"]),
                            "n_lines": len(e["debit_lines"]) + len(e["credit_lines"])})
        except Exception as ex:                                  # noqa: BLE001
            # Một bút toán hỏng KHÔNG được kéo theo cái còn lại; savepoint để
            # giao dịch không bẩn.
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:                                    # noqa: BLE001
                pass
            frappe.log_error(frappe.get_traceback(), "ketoan: mt_je.create_journal_entries")
            failed.append({"kind": e["kind"], "error": cstr(ex)[:300]})

    state = _set_je_state(doc.name)
    frappe.db.commit()

    return {
        "advice": doc.name,
        "created": created,
        "skipped_duplicate": skipped_dup,
        "failed": failed,
        "je_state": state,
        "warnings": warnings,
        "not_posted": not_posted,
        "message": _("Đã sinh {0} bút toán NHÁP. Chưa ghi sổ — vào tab 'Duyệt bút toán' để duyệt.")
                   .format(len(created)),
    }
