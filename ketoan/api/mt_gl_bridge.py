"""mt_gl_bridge — đối chiếu SỔ CÁI TK 131 với SỔ KẾ TOÁN THEO DÕI, từng chuỗi.

════════════════════════════════════════════════════════════════════════════
BA CUỐN SỔ, KHÔNG PHẢI HAI
════════════════════════════════════════════════════════════════════════════

  A · Sổ kế toán theo dõi   — hóa đơn còn nợ ĐÃ xuất HĐĐT (cột theo trên Excel)
  B · Rổ hóa đơn MT         — mọi hóa đơn còn nợ, kể cả chưa xuất HĐĐT
  C · Sổ cái TK 131         — số dư phải thu thật sự trên sổ

A và B là hai lát của cùng một tập (xem `mt_debt`). C thì đến từ chỗ khác hẳn:
nó là hệ quả của BÚT TOÁN, còn A/B là hệ quả của BẢNG KÊ CHUỖI.

Kênh MT cố ý KHÔNG tạo Payment Entry (ràng buộc số 2 của `mt.py`): tiền chuỗi
trả được ghi nhận trên bảng kê trước, bút toán do người duyệt sau. Nên C tụt
lại sau B đúng bằng phần tiền đã khớp mà chưa ai ghi sổ. Lệch là BÌNH THƯỜNG.
Câu hỏi đúng không phải "có lệch không" mà là "lệch nằm ở đâu".

════════════════════════════════════════════════════════════════════════════
KHÔNG SO HAI SỐ — DỰNG CẦU NỐI
════════════════════════════════════════════════════════════════════════════

In ra "lệch 412 triệu" là không dùng được: kế toán không biết 412 triệu đó nằm
ở đâu, nên hoặc bỏ qua, hoặc sửa bừa một bên cho khớp. Cả hai tệ hơn không có
màn hình. Nên ở đây là một dãy khoản mục cộng lại ĐÚNG chỗ lệch:

    Sổ cái 131 (C) − Rổ hóa đơn MT (B)
      = (1) sổ cái lệch so với chính hóa đơn ERPNext   C_hd − Σ(gộp − trả lại)
      + (2) hóa đơn KHÔNG còn trong rổ                 Σ_tất cả − Σ_còn nợ
      + (3) tiền bảng kê đã trừ khỏi rổ                 Σ đã trả (trên HĐ còn nợ)
      + (4) bút toán ghi thẳng vào 131                  C_khác

Đẳng thức ĐÚNG VỀ ĐẠI SỐ, không nhờ làm tròn:

    (1)+(2)+(3)+(4) = C_hd − Σ_còn nợ(gộp−trả lại) + Σ_còn nợ(đã trả) + C_khác
                    = C − B

Nghĩa là màn hình còn dư một đồng thì đó là LỖI CODE, không phải "sai số cho
phép" — và `gl_bridge_check` kiểm đúng chỗ đó.

════════════════════════════════════════════════════════════════════════════
VÌ SAO KHÔNG QUY ĐƯỢC VỀ TỪNG HÓA ĐƠN
════════════════════════════════════════════════════════════════════════════

Cách tự nhiên nhất là so từng hóa đơn: sổ cái nói còn X, bảng kê nói còn Y.
KHÔNG LÀM ĐƯỢC, và lý do nằm ngay trong code: `mt_je` cố ý KHÔNG gắn
`reference_name` lên dòng Có 131 (xem chú thích ở `mt_je.py`) — bút toán MT ghi
TỔNG. Nên trên `tabGL Entry`, tiền chuỗi trả không trỏ về hóa đơn nào cả.

Ép quy về từng hóa đơn thì phải ĐOÁN (FIFO, hay khớp theo số tiền), và đoán sai
ở đây là chỉ tay vào một hóa đơn đã thu đủ mà bảo "còn nợ". Cầu nối ở mức TỔNG
nói ít hơn nhưng không bao giờ nói sai.

MODULE NÀY CHỈ ĐỌC. Không ghi field, không sinh bút toán.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, nowdate

from ketoan.api._guard import guard_mt
from ketoan.api.mt import (
    KIND_PAYMENT,
    PAID_TOLERANCE,
    _company,
    _customer_in_clause,
    _debt_joins,
    _mt_clause,
    _require_tables,
    chain_customers,
    opening_open_clause,
)
from ketoan.api.mt_opening_gl import _party_in_clause
from ketoan.api.receivables import _racc_clause
from ketoan.install import MT_CHAINS

# Tiền VND nguyên đồng. 1đ chỉ để chống rác dấu phẩy động khi cộng dồn.
EPS = 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Vế SỔ CÁI — tách theo LOẠI CHỨNG TỪ
# ═══════════════════════════════════════════════════════════════════════════

def gl_split(company, customers, as_of):
    """Số dư 131 của một nhóm khách, tách 'từ hóa đơn' và 'từ chứng từ khác'.

    Tách theo `voucher_type` chứ không theo `against_voucher`: bút toán MT
    không gắn reference (xem chú thích đầu module), nên `against_voucher` rỗng
    và mọi phép gộp theo nó sẽ dồn hết vào một rổ vô nghĩa.

    'Từ hóa đơn' gồm CẢ phiếu trả hàng — nó cũng là Sales Invoice và cũng ghi
    thẳng vào 131. Gom chung là đúng: vế đem so bên rổ hóa đơn cũng đã trừ hàng
    trả lại rồi.
    """
    if not customers:
        return {"si": 0.0, "other": 0.0, "total": 0.0}
    p = {"company": company, "as_of": getdate(as_of)}
    racc = _racc_clause(p)
    in_party = _party_in_clause(customers, p)
    rows = frappe.db.sql(f"""
        SELECT CASE WHEN gle.voucher_type = 'Sales Invoice' THEN 'si' ELSE 'other' END AS k,
               SUM(gle.debit - gle.credit) AS bal
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.party_type = 'Customer'
          AND {racc}
          AND gle.posting_date <= %(as_of)s
          AND {in_party}
        GROUP BY k
    """, p, as_dict=True)
    out = {"si": 0.0, "other": 0.0}
    for r in rows:
        out[r.k] = flt(r.bal)
    out["total"] = round(out["si"] + out["other"], 2)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Vế RỔ HÓA ĐƠN
# ═══════════════════════════════════════════════════════════════════════════

def _invoice_side(company, customers, as_of):
    """Ba tổng của rổ hóa đơn, lấy trong MỘT lượt quét.

    · `all_net`   — MỌI hóa đơn bán đã ghi sổ: gộp − hàng trả lại. KHÔNG áp
                    luật số dư đầu kỳ, KHÔNG lọc theo còn nợ hay đã thu.
                    Đây là vế đem so với phần sổ cái đến từ hóa đơn.
    · `open_net`  — chỉ hóa đơn CÒN NỢ (đúng tập của `mt_debt`).
    · `open_paid` — tiền bảng kê đã trừ trên chính các hóa đơn còn nợ đó.

    Ba tổng phải lấy từ CÙNG một câu, cùng một mệnh đề `còn nợ`: lấy hai câu
    rời là sớm muộn một câu được sửa còn câu kia thì không, và cầu nối lệch
    một khoản không ai giải thích được.
    """
    if not customers:
        return {"all_net": 0.0, "open_net": 0.0, "open_paid": 0.0, "open_count": 0}

    p = {"company": company, "as_of": getdate(as_of), "tol": PAID_TOLERANCE,
         "kind_payment": KIND_PAYMENT}
    from ketoan.api.mt import KIND_DEDUCT
    p["kind_deduct"] = KIND_DEDUCT
    mt = _mt_clause(p)
    join = _debt_joins()
    in_cus = _customer_in_clause(customers, p)
    opening = opening_open_clause(p, company)

    # Điều kiện "CÒN NỢ" — chép ĐÚNG mệnh đề của `mt_debt._fetch`. Lệch một chữ
    # ở đây là hai màn hình nói về hai tập hóa đơn khác nhau.
    is_open = (f"((IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0))"
               f" < (ABS(si.grand_total) - IFNULL(rt.returned, 0)) - %(tol)s"
               f" AND {opening})")

    r = frappe.db.sql(f"""
        SELECT
          IFNULL(SUM(ABS(si.grand_total) - IFNULL(rt.returned, 0)), 0) AS all_net,
          IFNULL(SUM(CASE WHEN {is_open}
                     THEN ABS(si.grand_total) - IFNULL(rt.returned, 0) ELSE 0 END), 0) AS open_net,
          IFNULL(SUM(CASE WHEN {is_open}
                     THEN IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0) ELSE 0 END), 0) AS open_paid,
          SUM(CASE WHEN {is_open} THEN 1 ELSE 0 END) AS open_count
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND si.posting_date <= %(as_of)s
          AND {mt} AND {in_cus}
    """, p, as_dict=True)[0]
    return {"all_net": flt(r.all_net), "open_net": flt(r.open_net),
            "open_paid": flt(r.open_paid), "open_count": cint(r.open_count)}


# ═══════════════════════════════════════════════════════════════════════════
# NGUYÊN NHÂN — chỉ những thứ ĐO ĐƯỢC
# ═══════════════════════════════════════════════════════════════════════════

def _causes(company, customers, chain, as_of):
    """Các nguyên nhân lệch mà app ĐO được, kèm số tiền.

    ⚠ Đây là DANH SÁCH NGHI CAN có số, KHÔNG phải phân rã của chỗ lệch. Chúng
    chồng lấn nhau và không cộng lại thành cầu nối — cầu nối là bốn khoản ở
    `build()`. Trộn hai thứ này là mời người đọc cộng nhầm.
    """
    out = []

    # 1. Bảng kê đã khớp nhưng BÚT TOÁN CHƯA GHI SỔ.
    #
    # Đây là nguyên nhân số một theo cấu tạo của kênh MT: tiền được ghi nhận
    # trên bảng kê trước, bút toán do người duyệt sau. Trong khoảng giữa, sổ
    # theo dõi đã trừ tiền còn sổ cái thì chưa.
    p = {"company": company, "chain": chain, "kind": KIND_PAYMENT}
    rows = frappe.db.sql("""
        SELECT IFNULL(SUM(l.total_amount), 0) AS amt, COUNT(DISTINCT a.name) AS n
        FROM `tabMT Payment Advice` a
        JOIN `tabMT Payment Advice Line` l ON l.parent = a.name
        WHERE a.company = %(company)s AND a.chain = %(chain)s
          AND l.row_kind = %(kind)s
          AND IFNULL(a.je_state, '') != 'Đã duyệt đủ'
    """, p, as_dict=True)
    amt = flt(rows[0].amt) if rows else 0.0
    if abs(amt) > EPS:
        out.append({
            "key": "je_chua_ghi_so",
            "label": _("Tiền trên bảng kê đã khớp nhưng bút toán CHƯA ghi sổ đủ"),
            "amount": round(amt, 2),
            "count": cint(rows[0].n),
            "why": _(
                "Kênh MT cố ý không tạo Payment Entry: tiền chuỗi trả được ghi nhận trên "
                "bảng kê trước, bút toán do người duyệt sau. Trong khoảng giữa, sổ theo dõi "
                "đã trừ tiền còn sổ cái 131 thì chưa — nên sổ cái CAO HƠN."),
            "action": _("Vào bước Bút toán, duyệt các bút toán nháp."),
            "step": "but-toan",
        })

    # 2. Phiếu trả hàng KHÔNG khai `return_against`.
    #
    # Nó ghi giảm 131 trên sổ cái nhưng không trừ được vào hóa đơn nào, nên rổ
    # hóa đơn vẫn tính đủ nợ. Sổ cái THẤP HƠN đúng bằng số này.
    from ketoan.api.mt_debt import _orphan_returns
    orp = _orphan_returns(company, as_of)
    if cint(orp.get("orphan_return_count")):
        out.append({
            "key": "tra_hang_khong_goc",
            "label": _("Phiếu trả hàng chưa khai 'trả cho hóa đơn nào'"),
            "amount": -round(flt(orp.get("orphan_return_amount")), 2),
            "count": cint(orp.get("orphan_return_count")),
            "why": _(
                "Phiếu trả hàng vẫn ghi giảm 131 trên sổ cái, nhưng không khai hóa đơn gốc "
                "thì không trừ được vào hóa đơn nào — rổ hóa đơn vẫn tính đủ nợ."),
            "action": _("Mở phiếu trả hàng, điền Return Against."),
            "step": "cong-no",
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════
# CẦU NỐI
# ═══════════════════════════════════════════════════════════════════════════

def build(company, chain, as_of):
    """Cầu nối SỔ CÁI ↔ RỔ HÓA ĐƠN cho MỘT chuỗi. Bốn khoản cộng lại = chỗ lệch."""
    customers = chain_customers(chain)
    gl = gl_split(company, customers, as_of)
    inv = _invoice_side(company, customers, as_of)

    b = round(inv["open_net"] - inv["open_paid"], 2)      # rổ hóa đơn còn nợ
    c = round(gl["total"], 2)                             # sổ cái 131

    items = [
        {
            "key": "so_cai_ngoai_hoa_don",
            "label": _("Sổ cái lệch so với chính hóa đơn ERPNext"),
            "amount": round(gl["si"] - inv["all_net"], 2),
            "why": _(
                "Phần ghi vào 131 từ chứng từ loại Sales Invoice mà KHÔNG khớp tổng hóa đơn "
                "bán trừ hàng trả lại. Thường do phiếu trả hàng chưa khai hóa đơn gốc, hoặc "
                "hóa đơn hạch toán vào tài khoản phải thu khác."),
        },
        {
            "key": "hoa_don_ngoai_ro",
            "label": _("Hóa đơn KHÔNG còn trong rổ còn nợ"),
            "amount": round(inv["all_net"] - inv["open_net"], 2),
            "why": _(
                "Hóa đơn đã thu đủ theo bảng kê, hoặc bị luật tất toán số dư đầu kỳ loại ra. "
                "Rổ không tính chúng nữa, nhưng sổ cái vẫn giữ cho tới khi có bút toán."),
        },
        {
            "key": "tien_bang_ke_da_tru",
            "label": _("Tiền bảng kê đã trừ trên hóa đơn còn nợ"),
            "amount": round(inv["open_paid"], 2),
            "why": _(
                "Tiền chuỗi đã trả cho các hóa đơn VẪN đang còn nợ. Rổ đã trừ; sổ cái chỉ "
                "trừ khi bút toán được ghi sổ."),
        },
        {
            "key": "but_toan_vao_131",
            "label": _("Bút toán ghi thẳng vào 131"),
            "amount": round(gl["other"], 2),
            "why": _(
                "Mọi chứng từ KHÔNG phải hóa đơn có động vào 131: bút toán thu tiền, chiết "
                "khấu, phí, số dư nhập tay. Số âm là đã ghi giảm nợ."),
        },
    ]
    diff = round(c - b, 2)
    residual = round(diff - sum(i["amount"] for i in items), 2)

    return {
        "chain": chain,
        "gl_total": c,
        "gl_si": round(gl["si"], 2),
        "gl_other": round(gl["other"], 2),
        "basket_open": b,
        "basket_all": round(inv["all_net"], 2),
        "open_count": inv["open_count"],
        "diff": diff,
        "items": items,
        # Phải LUÔN bằng 0. Khác 0 là lỗi code, không phải sai số cho phép.
        "residual": residual,
        "balanced": abs(residual) <= EPS,
        "n_customers": len(customers),
        "causes": _causes(company, customers, chain, as_of),
    }


@frappe.whitelist()
def compare(company=None, as_of=None, chain=None):
    """Ba cuốn sổ cạnh nhau + cầu nối.

    `chain` -> chỉ chuỗi đó. Bàn làm việc của một chuỗi dùng nhánh này: quét sổ
    cái cho cả 8 chuỗi để hiện một ô là bắt màn hình chờ 8 lần công việc cần.
    """
    guard_mt()
    _require_tables()
    company = _company(company)
    as_of = getdate(as_of or nowdate())

    chain = cstr(chain or "").strip() or None
    if chain and chain not in MT_CHAINS:
        frappe.throw(_("Không có chuỗi '{0}' trong danh sách chuỗi kênh MT").format(chain))
    labels = [chain] if chain else list(MT_CHAINS)

    from ketoan.api import mt_debt

    # Lọc ngay ở `_fetch` khi chỉ hỏi một chuỗi — quét cả kênh rồi bỏ đi là
    # trả giá đúng phần đã bỏ.
    rows = mt_debt._enrich(mt_debt._fetch(company, as_of, chain=chain), as_of)
    roll = mt_debt._rollup(rows)
    by_chain = {c["chain"]: c for c in roll["chains"]}

    out = []
    for label in labels:
        d = by_chain.get(label) or {}
        br = build(company, label, as_of)
        br.update({
            # A — cột kế toán theo dõi trên Excel.
            "tracked": round(flt(d.get("einv_issued")), 2),
            "tracked_count": cint(d.get("einv_issued_n")),
            "einv_known": bool(d.get("einv_known")),
            "no_einv": round(flt(d.get("einv_pending")), 2),
        })
        out.append(br)

    out.sort(key=lambda r: -abs(r["diff"]))
    return {
        "company": company,
        "chain": chain or "",
        "as_of": cstr(as_of),
        "chains": out,
        "totals": {
            "tracked": round(sum(r["tracked"] for r in out), 2),
            "basket_open": round(sum(r["basket_open"] for r in out), 2),
            "gl_total": round(sum(r["gl_total"] for r in out), 2),
            "diff": round(sum(r["diff"] for r in out), 2),
        },
        "all_balanced": all(r["balanced"] for r in out),
        "note": _(
            "Sổ cái 131 đến từ BÚT TOÁN; hai cột kia đến từ BẢNG KÊ CHUỖI. Kênh MT cố ý "
            "không tạo Payment Entry, nên sổ cái luôn tụt lại sau đúng bằng phần tiền đã "
            "khớp mà chưa ai ghi sổ. Lệch là bình thường — câu hỏi là lệch nằm ở đâu."),
    }
