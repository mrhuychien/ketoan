"""mt_hub — BẢNG ĐIỀU KHIỂN THEO CHUỖI cho kênh MT.

Giao diện cũ xếp theo CHỨC NĂNG (thanh toán · chiết khấu · bút toán · bảng kê ·
hồ sơ · công nợ), mỗi thứ một tab. Nhưng kế toán MT không làm việc theo chức
năng — họ làm theo CHUỖI: hôm nay xử LOTTE cho xong, mai tới Central Retail.
Xếp theo chức năng buộc người dùng tự ghép bảy màn hình lại trong đầu mới thấy
được "chuỗi này còn thiếu gì".

Module này trả về đúng cái để ghép hộ: MỖI CHUỖI MỘT DÒNG, và trên dòng đó là
tiến độ của cả năm bước trong vòng đời tháng (SOP §1).

════════════════════════════════════════════════════════════════════════════
NĂM BƯỚC, VÀ PORTAL LO BƯỚC NÀO
════════════════════════════════════════════════════════════════════════════

  1. Xuất hóa đơn bán          — ERPNext/MISA, KHÔNG thuộc portal
  2. Móp lỗi / trả lại         — ERPNext/MISA, KHÔNG thuộc portal
  3. Chiết khấu                — portal: doanh số -> BKCK -> HĐ CK -> JE
  4. Đối soát thanh toán       — portal: nạp bảng kê -> khớp -> JE
  5. Công nợ đến hạn           — portal: theo hạn khai trên từng khách

Riêng WinCommerce có thêm một việc không nằm trong năm bước: **hồ sơ nộp**
(bảng kê Excel + PDF đặt đúng tên). Win không xử thanh toán khi hồ sơ sai tên.

════════════════════════════════════════════════════════════════════════════
MỖI CHUỖI LÀM KHÁC NHAU — VÀ SỰ KHÁC ĐÓ ĐỌC TỪ CODE, KHÔNG GÕ LẠI
════════════════════════════════════════════════════════════════════════════

Ba năng lực quyết định chuỗi hiện những bước nào:

  · đọc được file thanh toán?  -> `mt_advice.PARSERS`
  · MÌNH xuất hóa đơn CK?      -> `mt_discount_read.DISCOUNT_CHAIN_LABEL`
  · có hồ sơ nộp?              -> `mt_win.WIN_CHAIN`

Lấy từ chính ba nguồn đó chứ không chép lại thành bảng thứ tư: thêm parser cho
Mega mà quên sửa bảng chép thì màn hình nói dối về đúng cái vừa làm xong.

Ví dụ hệ quả có thật: Saigon Co.op **không** nằm trong `DISCOUNT_CHAIN_LABEL`
vì chiết khấu 17,75% bị trừ tại nguồn và **Co.op xuất hóa đơn** — nên bàn làm
việc của Co.op KHÔNG hiện bước "lập bảng kê chiết khấu". Hiện ra là mời kế toán
xuất một hóa đơn mình không được phép xuất.

MODULE NÀY CHỈ ĐỌC. Không ghi, không tạo chứng từ.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, nowdate

from ketoan.api._guard import guard_mt, is_chief
from ketoan.api.mt import (
    KIND_PAYMENT,
    _company,
    _range,
    _require_tables,
)
from ketoan.install import MT_CHAINS

# Trạng thái — gõ đúng như options trong DocType JSON.
ADVICE_DRAFT = "Nháp"
SHEET_DRAFT = "Nháp"
SHEET_FINAL = "Đã chốt"
DOSSIER_DRAFT = "Nháp"

# Năm bước của SOP §1. `portal` = portal có lo bước đó không.
STEPS = (
    {"key": "xuat_hoa_don", "label": "Xuất hóa đơn bán", "portal": False,
     "note": "Làm trên ERPNext/MISA theo PO — không thuộc portal này."},
    {"key": "tra_hang", "label": "Móp lỗi / trả lại", "portal": False,
     "note": "Chứng từ trả hàng ERPNext + hóa đơn điều chỉnh MISA."},
    {"key": "chiet_khau", "label": "Chiết khấu", "portal": True,
     "note": "Nạp doanh số → bảng kê BKCK → chốt số → xuất hóa đơn CK → bút toán."},
    {"key": "thanh_toan", "label": "Đối soát thanh toán", "portal": True,
     "note": "Nạp bảng kê của chuỗi → khớp hóa đơn → sinh và duyệt bút toán."},
    {"key": "cong_no", "label": "Công nợ đến hạn", "portal": True,
     "note": "Hóa đơn còn nợ theo hạn khai trên từng khách."},
)


def _capabilities():
    """(nhãn chuỗi) -> ba năng lực. Đọc từ nguồn thật, không chép bảng."""
    from ketoan.api import mt_win
    from ketoan.api.mt_advice import CHAIN_LABEL, PARSERS
    from ketoan.api.mt_discount_read import DISCOUNT_CHAIN_LABEL, has_parser

    by_label = {}
    for key, label in CHAIN_LABEL.items():
        by_label[label] = {
            "chain_key": key,
            "can_read_payment": key in PARSERS,
            "we_issue_discount": key in DISCOUNT_CHAIN_LABEL and has_parser(key),
            "has_dossier": label == mt_win.WIN_CHAIN,
        }
    # Chuỗi khai trong `MT_CHAINS` mà `CHAIN_LABEL` chưa có -> vẫn phải hiện,
    # kèm cờ tắt hết. Giấu đi là kế toán tưởng chuỗi đó không tồn tại.
    for label in MT_CHAINS:
        by_label.setdefault(label, {"chain_key": None, "can_read_payment": False,
                                    "we_issue_discount": False, "has_dossier": False})
    return by_label


def _count_by_chain(sql, params):
    rows = frappe.db.sql(sql, params, as_dict=True) or []
    return {cstr(r.get("chain") or ""): r for r in rows}


@frappe.whitelist()
def get_board(company=None, from_date=None, to_date=None, as_of=None):
    """MỘT DÒNG MỖI CHUỖI: còn việc gì, ở bước nào.

    Đây là màn hình đầu tiên của kênh MT. Nó phải trả lời được đúng một câu hỏi
    trong ba giây: *chuỗi nào đang cần tôi làm gì?*
    """
    guard_mt()
    _require_tables()
    company = _company(company)
    from_date, to_date = _range(from_date, to_date)
    as_of = getdate(as_of or nowdate())

    p = {"company": company, "fd": from_date, "td": to_date,
         "kind_payment": KIND_PAYMENT, "draft": ADVICE_DRAFT}

    # ── Bước 4: bảng kê thanh toán đã nạp ────────────────────────────────
    advices = _count_by_chain("""
        SELECT a.chain,
               COUNT(*)                                        AS n,
               SUM(CASE WHEN IFNULL(a.reconciled, 0) = 0 THEN 1 ELSE 0 END) AS n_unreconciled,
               SUM(CASE WHEN a.status = %(draft)s THEN 1 ELSE 0 END)        AS n_draft
        FROM `tabMT Payment Advice` a
        WHERE a.company = %(company)s
          AND a.payment_date BETWEEN %(fd)s AND %(td)s
        GROUP BY a.chain
    """, p)

    # Dòng tiền chưa nối được hóa đơn nào + dòng máy mới đoán.
    # ĐẾM RIÊNG HAI LOẠI: "chưa khớp" là tiền không biết của hóa đơn nào; "cần
    # review" là máy đoán mà chưa ai chốt. Gộp chung thì kế toán không biết nên
    # đi tìm hóa đơn hay chỉ cần xác nhận.
    lines = _count_by_chain("""
        SELECT a.chain,
               SUM(CASE WHEN l.row_kind = %(kind_payment)s
                         AND IFNULL(l.sales_invoice, '') = '' THEN 1 ELSE 0 END) AS n_unmatched,
               SUM(CASE WHEN l.match_confidence = 'Cần review' THEN 1 ELSE 0 END) AS n_review
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
               AND a.company = %(company)s
        WHERE l.parenttype = 'MT Payment Advice'
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
        GROUP BY a.chain
    """, p)

    # ── Bút toán nháp chờ duyệt (thuộc cả bước 3 lẫn bước 4) ─────────────
    jes = {}
    if frappe.db.has_column("Journal Entry", "custom_mt_source_name"):
        jes = _count_by_chain("""
            SELECT a.chain, COUNT(*) AS n_draft_je
            FROM `tabJournal Entry` je
            INNER JOIN `tabMT Payment Advice` a ON a.name = je.custom_mt_source_name
            WHERE je.docstatus = 0 AND je.company = %(company)s
              AND je.custom_mt_source_dt = 'MT Payment Advice'
            GROUP BY a.chain
        """, p)
        for chain, r in _count_by_chain("""
            SELECT s.chain, COUNT(*) AS n_draft_je
            FROM `tabJournal Entry` je
            INNER JOIN `tabMT Discount Sheet` s ON s.name = je.custom_mt_source_name
            WHERE je.docstatus = 0 AND je.company = %(company)s
              AND je.custom_mt_source_dt = 'MT Discount Sheet'
            GROUP BY s.chain
        """, p).items():
            e = jes.setdefault(chain, frappe._dict({"chain": chain, "n_draft_je": 0}))
            e["n_draft_je"] = cint(e.get("n_draft_je")) + cint(r.get("n_draft_je"))

    # ── Bước 3: bảng kê chiết khấu ───────────────────────────────────────
    sheets = {}
    if frappe.db.table_exists("MT Discount Sheet"):
        sheets = _count_by_chain("""
            SELECT s.chain,
                   SUM(CASE WHEN s.status = %(sheet_draft)s THEN 1 ELSE 0 END) AS n_draft,
                   SUM(CASE WHEN s.status = %(sheet_final)s THEN 1 ELSE 0 END) AS n_await_invoice,
                   COUNT(*) AS n
            FROM `tabMT Discount Sheet` s
            WHERE s.company = %(company)s AND s.sheet_date BETWEEN %(fd)s AND %(td)s
            GROUP BY s.chain
        """, dict(p, sheet_draft=SHEET_DRAFT, sheet_final=SHEET_FINAL))

    # ── Hồ sơ nộp (chỉ WinCommerce) ──────────────────────────────────────
    n_dossier_draft = 0
    if frappe.db.table_exists("MT Win Dossier"):
        row = frappe.db.sql("""
            SELECT COUNT(*) AS n FROM `tabMT Win Dossier`
            WHERE company = %(company)s AND status = %(dstatus)s
        """, dict(p, dstatus=DOSSIER_DRAFT), as_dict=True)
        n_dossier_draft = cint(row[0].n) if row else 0

    # ── Bước 5: công nợ — dùng ĐÚNG tầng của màn hình công nợ ────────────
    # Không viết lại phép tính: hai màn hình nói hai số khác nhau về cùng một
    # chuỗi là cách nhanh nhất để mất lòng tin vào cả hai.
    from ketoan.api import mt_debt

    debt_rows = mt_debt._enrich(mt_debt._fetch(company, as_of), as_of)
    debt = {c["chain"]: c for c in mt_debt._rollup(debt_rows)["chains"]}

    # Bảng kê KHÔNG điền công ty: không còn được tính vào bất kỳ công ty nào,
    # nên nó biến khỏi mọi màn hình. Phải ĐẾM và hiện ra, không để tiền mất câm.
    orphan = frappe.db.sql("""
        SELECT COUNT(*) AS n FROM `tabMT Payment Advice`
        WHERE IFNULL(company, '') = ''
    """, as_dict=True)
    n_orphan = cint(orphan[0].n) if orphan else 0

    caps = _capabilities()
    out = []
    for label in MT_CHAINS:
        cap = caps.get(label, {})
        a = advices.get(label) or {}
        l = lines.get(label) or {}
        s = sheets.get(label) or {}
        d = debt.get(label) or {}
        j = jes.get(label) or {}

        n_draft_je = cint(j.get("n_draft_je"))
        n_dossier = n_dossier_draft if cap.get("has_dossier") else 0

        # VIỆC CẦN LÀM = những thứ CON NGƯỜI phải động tay. Không cộng "số bảng
        # kê đã nạp" hay "số hóa đơn còn nợ" vào đây: chúng là hiện trạng, không
        # phải việc. Trộn vào thì con số lúc nào cũng to và mất hết ý nghĩa.
        todo = (cint(a.get("n_unreconciled")) + cint(l.get("n_unmatched"))
                + cint(l.get("n_review")) + n_draft_je
                + cint(s.get("n_draft")) + cint(s.get("n_await_invoice")) + n_dossier)

        out.append({
            "chain": label,
            "chain_key": cap.get("chain_key"),
            "can_read_payment": bool(cap.get("can_read_payment")),
            "we_issue_discount": bool(cap.get("we_issue_discount")),
            "has_dossier": bool(cap.get("has_dossier")),
            "todo": todo,
            # bước 3
            "sheets_draft": cint(s.get("n_draft")),
            "sheets_await_invoice": cint(s.get("n_await_invoice")),
            "sheets_total": cint(s.get("n")),
            # bước 4
            "advices": cint(a.get("n")),
            "advices_unreconciled": cint(a.get("n_unreconciled")),
            "lines_unmatched": cint(l.get("n_unmatched")),
            "lines_review": cint(l.get("n_review")),
            "draft_je": n_draft_je,
            # hồ sơ Win
            "dossiers_draft": n_dossier,
            # bước 5
            "debt": flt(d.get("amount")),
            "debt_overdue": flt(d.get("overdue")),
            "debt_invoices": cint(d.get("count")),
            "debt_unknown_term": cint(d.get("unknown_term")),
        })

    # Chuỗi nào nhiều việc nhất lên trước; hết việc thì xếp theo nợ quá hạn.
    out.sort(key=lambda r: (-r["todo"], -r["debt_overdue"], r["chain"]))

    return {
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "as_of": cstr(as_of),
        "steps": list(STEPS),
        "chains": out,
        "orphan_advices": n_orphan,
        "totals": {
            "todo": sum(r["todo"] for r in out),
            "debt": sum(r["debt"] for r in out),
            "debt_overdue": sum(r["debt_overdue"] for r in out),
            "draft_je": sum(r["draft_je"] for r in out),
        },
        "can_manage": is_chief(),
        "basis_note": _(
            "Số còn nợ tính từ dòng thanh toán trên bảng kê chuỗi đã nạp, "
            "KHÔNG phải số dư tài khoản 131 trên sổ cái."),
    }


@frappe.whitelist()
def get_chain(chain, company=None, from_date=None, to_date=None, as_of=None):
    """Một chuỗi: năng lực + tiến độ từng bước. Dùng cho bàn làm việc của chuỗi."""
    guard_mt()
    _require_tables()
    if not cstr(chain).strip():
        frappe.throw(_("Chưa chọn chuỗi siêu thị"))

    board = get_board(company=company, from_date=from_date, to_date=to_date, as_of=as_of)
    hit = next((r for r in board["chains"] if r["chain"] == chain), None)
    if not hit:
        frappe.throw(_("Không có chuỗi '{0}' trong danh sách chuỗi kênh MT").format(chain))

    # Bước nào HIỆN cho chuỗi này. Ẩn bước chuỗi không có là điều đúng, nhưng
    # phải ẩn KÈM LÝ DO ở chỗ khác (xem `blocked` bên dưới) — ẩn câm thì kế toán
    # tưởng portal thiếu tính năng.
    steps = []
    for st in STEPS:
        show = st["portal"]
        why = None
        if st["key"] == "chiet_khau" and not hit["we_issue_discount"]:
            show, why = False, _(
                "Chuỗi này KHÔNG do mình xuất hóa đơn chiết khấu — khoản chiết khấu/phí "
                "do chuỗi xuất hóa đơn cho mình và đi vào bước Đối soát thanh toán.")
        steps.append(dict(st, show=show, reason=why))

    blocked = []
    if not hit["can_read_payment"]:
        blocked.append(_(
            "Chưa có tầng đọc file thanh toán cho {0} — chưa có file mẫu thật để viết. "
            "Bước Đối soát thanh toán vẫn xem được dữ liệu đã nạp, nhưng chưa nạp file "
            "mới được.").format(chain))

    return {
        "chain": chain,
        "company": board["company"],
        "from_date": board["from_date"],
        "to_date": board["to_date"],
        "as_of": board["as_of"],
        "status": hit,
        "steps": steps,
        "blocked": blocked,
        "can_manage": board["can_manage"],
        "basis_note": board["basis_note"],
    }
