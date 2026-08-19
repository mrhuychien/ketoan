"""mt — API cho 3 màn hình kế toán kênh MT (siêu thị hiện đại).

Ba màn hình:
  · Tổng quan       → get_overview()       — 3 rổ + công nợ chuỗi
  · Danh sách hóa đơn → get_invoices()     — chia trang 20 dòng
  · Công nợ theo chuỗi → get_chain_summary()

Và luồng nạp bảng kê thanh toán của chuỗi:
  · preview_advice()  — đọc file + khớp hóa đơn, KHÔNG ghi gì (bắt buộc)
  · commit_advice()   — tạo MT Payment Advice + dòng, có vân tay kế hoạch
  · relink_line()     — kế toán chốt tay liên kết một dòng với Sales Invoice

════════════════════════════════════════════════════════════════════════════
RÀNG BUỘC KHÔNG ĐƯỢC PHÁ
════════════════════════════════════════════════════════════════════════════

1. MỘT NGUỒN SỰ THẬT cho trạng thái thanh toán. KHÔNG có cột "đã thanh toán"
   trên Sales Invoice. Trạng thái được SUY RA bằng cách cộng dồn các dòng
   `MT Payment Advice Line` có row_kind='Thanh toán' đang trỏ về hóa đơn đó.
   Một hóa đơn có thể được trả LÀM NHIỀU LẦN (nhiều bảng kê, nhiều kỳ) nên
   phải CỘNG DỒN rồi mới so với grand_total — so từng dòng một là báo "chưa
   thanh toán" cho hóa đơn đã trả đủ qua 2 kỳ.

2. Module này TUYỆT ĐỐI KHÔNG tạo/sửa/hủy Payment Entry, Journal Entry hay bất
   kỳ chứng từ kế toán nào. Chỉ GHI NHẬN dòng đọc từ file + đánh dấu. Con người
   quyết định hạch toán. Hệ quả phải chấp nhận: `si.outstanding_amount` của
   ERPNext KHÔNG phản ánh tiền chuỗi đã trả (vì không có Payment Entry) — nên
   mọi con số công nợ ở đây tính từ bảng kê, và phải nói rõ như vậy trên màn
   hình, đừng để kế toán tưởng đó là số dư sổ cái.

3. Không đụng tới Sales Invoice đã ghi sổ. Module này không db_set lên Sales
   Invoice dòng nào — nó chỉ ĐỌC.

4. Chỉ dòng row_kind='Thanh toán' mới được nối Sales Invoice (child doctype đã
   chặn ở validate). Dòng chiết khấu của Central Retail mang ký hiệu hóa đơn
   bán ra của chính mình mà KHÔNG phải thanh toán hóa đơn đó.

════════════════════════════════════════════════════════════════════════════
HỢP ĐỒNG VỚI `ketoan.api.mt_advice` (tầng đọc file)
════════════════════════════════════════════════════════════════════════════

Module này KHÔNG đọc Excel. Toàn bộ việc đọc 5 định dạng file nằm ở
`ketoan.api.mt_advice`, dùng theo hợp đồng sau:

    mt_advice.CHAIN_LABEL -> {khóa ASCII: nhãn}   # trùng options field `chain`
    mt_advice.read_payment_advice(content: str, chain=None) -> dict

`content` là base64 (có/không tiền tố data URI) — tầng đọc tự nhận .xlsx/.xls
theo CHỮ KÝ BYTE, không theo đuôi tên file. Trả về MỘT dict cho CẢ FILE:

    {
      "chain": "LOTTE", "chain_key": "lotte",
      "advice_no": str | None,          # nếu file chỉ có một số chứng từ
      "payment_dates": ["2026-07-10", "2026-07-30"],
      "declared_totals": {...},         # SỐ KIỂM TRA đọc từ chính file
      "computed_totals": {...},
      "checks": [{label, declared, computed, diff, ok}, ...],
      "reconciled": bool,               # MỌI số kiểm tra đều khớp?
      "groups": [ {key, advice_no, payment_date, n_rows, ...}, ... ],
      "rows": [ {...bộ khóa chuẩn...} ],   # CHỈ dòng tiền, không có dòng tổng
      "warnings": [str],
    }

Mỗi phần tử `rows`:
    row_kind (ASCII: thanh_toan/chiet_khau/phi/ghi_giam/khac), row_kind_label,
    row_subtype, inv_series, inv_series_norm, inv_no, inv_no_norm, inv_date,
    store_code, store_name, doc_no, description, amount_before_vat, vat_amount,
    total_amount (ĐỘ LỚN), signed_amount (GIỮ DẤU), payment_date, needs_review,
    source_sheet, source_row

MỘT FILE ≠ MỘT BẢN GHI. `groups` là các LẦN THANH TOÁN riêng nằm trong cùng một
file: Co.op 8 sheet = 8 kỳ (mỗi kỳ một số chứng từ + một bộ số kiểm tra), LOTTE
2 Payment Date, Central Retail 2 Clearing Doc. Gộp lại thành một bản ghi là cộng
nhầm tiền của hai kỳ vào nhau (§J.3 của hợp đồng). Tầng đọc KHÔNG chia sẵn dòng
theo nhóm, nên `_split_advices()` ở dưới phải chia lại — và chia xong PHẢI đối
chiếu với `n_rows` mà tầng đọc công bố, chia sai là chia sai tiền.

DẤU: lưu `signed_amount` vào `total_amount` của dòng DocType (field ghi rõ "giữ
nguyên DẤU đọc được từ file") — dấu là chốt đối chiếu với dòng tổng do chuỗi in
ra. Khi CỘNG TIỀN ĐÃ THU thì dùng ABS(), nhưng chỉ trên dòng 'Thanh toán', nơi
bản chất đã biết chắc nhờ cột loại chứng từ, chứ không suy bản chất từ dấu.
"""

import base64
import hashlib
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, cstr, flt, getdate, nowdate

from ketoan.api._guard import (
    channel_group_clause,
    get_settings,
    guard_manager,
    guard_mt,
    is_chief,
    resolve_company,
)
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)
from ketoan.mt.doctype.mt_payment_advice_line.mt_payment_advice_line import norm_series_mt

PAGE_SIZE = 20
MAX_PAGE_SIZE = 200

# Nhãn row_kind trong DocType (tiếng Việt có dấu). Fieldname vẫn ASCII.
KIND_PAYMENT = "Thanh toán"
KIND_DISCOUNT = "Chiết khấu"
KIND_FEE = "Phí"
KIND_DEDUCT = "Ghi giảm"
KIND_OTHER = "Khác"

# Các loại dòng KHẤU TRỪ — không phải hóa đơn, không nối Sales Invoice.
DEDUCTION_KINDS = (KIND_DISCOUNT, KIND_FEE, KIND_DEDUCT, KIND_OTHER)

# row_kind ASCII của tầng đọc file -> nhãn của DocType.
#
# Dòng nào tầng đọc KHÔNG nhận diện được sẽ vào 'Khác' chứ KHÔNG bị bỏ im lặng:
# bỏ im lặng là mất tiền khỏi tổng mà không ai thấy. Chỉ 'bo_qua'/'kiem_tra'
# (dòng tiêu đề, dòng cộng, số kiểm tra) mới được loại — cộng chúng vào là nhân
# đôi tiền của cả trang.
ROW_KIND_MAP = {
    "thanh_toan": KIND_PAYMENT,
    "chiet_khau": KIND_DISCOUNT,
    "phi": KIND_FEE,
    "ghi_giam": KIND_DEDUCT,
    "ghi_giam_khong_ky_hieu": KIND_DEDUCT,
    "khac": KIND_OTHER,
    # cho phép tầng đọc trả thẳng nhãn tiếng Việt
    KIND_PAYMENT: KIND_PAYMENT,
    KIND_DISCOUNT: KIND_DISCOUNT,
    KIND_FEE: KIND_FEE,
    KIND_DEDUCT: KIND_DEDUCT,
    KIND_OTHER: KIND_OTHER,
}

# Dòng KHÔNG phải tiền phát sinh: tiêu đề, phân cách, dòng cộng nhóm, số kiểm tra.
ROW_KIND_DROP = {"bo_qua", "kiem_tra", "bo qua", ""}

BUCKETS = ("chua_thanh_toan", "da_thanh_toan", "chiet_khau", "tat_ca")

# Sai số cho phép khi kết luận "đã thu đủ tiền hóa đơn".
#
# 1 đồng, không hơn. Lệch làm tròn ±1..3đ đã đo được ở Co.op nằm ở CẤP NHÓM
# siêu thị (tổng nhóm vs tổng dòng), không phải ở số tiền của từng hóa đơn —
# nên không cần nới ở đây. Nới rộng là tự động đánh dấu "đã trả đủ" cho hóa đơn
# còn thiếu tiền thật.
PAID_TOLERANCE = 1.0

# Trần an toàn cho file tải lên (base64 nở ~4/3 so với file gốc).
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Field số hóa đơn trên Sales Invoice — dùng chung với luồng MISA để hai tầng
# đối soát không lệch nhau.
SI_SERIES_FIELD = "custom_misa_inv_series"
SI_NO_FIELD = "custom_misa_inv_no"


# ═══════════════════════════════════════════════════════════════════════════
# Tiện ích chung
# ═══════════════════════════════════════════════════════════════════════════

def _range(from_date, to_date):
    to_date = to_date or nowdate()
    from_date = from_date or add_months(to_date, -1)
    return from_date, to_date


def _require_tables():
    """Bảng của DocType MT đã được tạo chưa.

    VÌ SAO cần: DocType mới chỉ thành BẢNG sau `bench migrate`. Chưa migrate mà
    mở màn hình thì mọi truy vấn ném thẳng lỗi MariaDB thô — kế toán nhận được
    đúng câu `(1146, "Table 'xxx.tabMT Payment Advice Line' doesn't exist")` và
    không có cách nào đoán ra phải làm gì. Đổi thành câu chỉ rõ việc cần làm.

    Kiểm cả bảng CON: bảng cha có thể tạo được trong khi bảng con thất bại, và
    phần lớn truy vấn của module này đọc bảng con.
    """
    for dt in ("MT Payment Advice", "MT Payment Advice Line"):
        if not frappe.db.table_exists(dt):
            frappe.throw(_(
                "Chức năng Công nợ MT chưa được cài đặt trên site này (thiếu bảng {0}). "
                "Quản trị chạy: bench --site TÊN_SITE migrate"
            ).format(dt))


def _company(company=None):
    """Công ty của màn hình — LUÔN kiểm quyền, kể cả khi lấy từ mặc định.

    VÌ SAO: mọi truy vấn của module này là `frappe.db.sql` thô, mà SQL thô KHÔNG
    đi qua permission và KHÔNG áp User Permission của Frappe. Client tự đặt
    `?company=` là đọc trọn công nợ, tên khách, số hóa đơn của công ty khác —
    và `commit_advice` còn GHI bảng kê vào công ty do client chỉ định. Nên chốt
    chặn duy nhất phải nằm ở đây.
    """
    asked = company                       # giá trị client gửi lên, có thể rỗng
    company = resolve_company(company)
    if not company:
        frappe.throw(_("Chưa xác định được công ty"))

    # Kiểm bằng USER PERMISSION, KHÔNG bằng has_permission("Company").
    #
    # has_permission đòi role phải có quyền đọc DocType `Company`, mà ma trận
    # quyền của app (install._SALES_CHANNEL_PERMS) không hề cấp Company cho vai
    # trò nào. User portal chỉ mang role của app này sẽ bị chặn ngay dòng đầu
    # của MỌI method — khóa sạch màn hình MT của người dùng hợp lệ.
    #
    # User Permission mới đúng là thứ khai "user này được đụng công ty nào".
    # Không khai gì = không bị giới hạn — đúng ngữ nghĩa của Frappe.
    try:
        from frappe.permissions import get_user_permissions

        # Truyền user TƯỜNG MINH: ở Frappe v16 tham số này BẮT BUỘC. Gọi thiếu
        # thì mọi method của màn hình MT ném "missing 1 required positional
        # argument: 'user'" — đã xảy ra thật.
        allowed = get_user_permissions(frappe.session.user).get("Company") or []
    except Exception:
        # Chữ ký/vị trí hàm này đã đổi giữa các bản Frappe. Không đoán tiếp, và
        # cũng KHÔNG bỏ qua chốt chặn — lùi về quy tắc chặt hơn: chỉ chấp nhận
        # đúng công ty mặc định của user, tức là client không được tự chọn công
        # ty khác. Hỏng thì hỏng theo hướng KHÓA, không theo hướng MỞ.
        frappe.log_error(frappe.get_traceback(), "mt._company/user_permissions")
        default = resolve_company(None)
        if asked and default and company != default:
            frappe.throw(_("Bạn không có quyền trên công ty {0}").format(company),
                         frappe.PermissionError)
        return company

    if allowed:
        names = {d.get("doc") for d in allowed if isinstance(d, dict) and d.get("doc")}
        if names and company not in names:
            frappe.throw(_("Bạn không có quyền trên công ty {0}").format(company),
                         frappe.PermissionError)
    return company


def _page(page, page_size):
    page = max(1, cint(page or 1))
    page_size = min(max(1, cint(page_size or PAGE_SIZE)), MAX_PAGE_SIZE)
    return page, page_size, (page - 1) * page_size


def _has_si_field(field):
    return bool(frappe.get_meta("Sales Invoice").has_field(field))


def _mt_clause(params):
    """Mệnh đề lọc khách hàng kênh MT (theo Customer Group khai trong Settings)."""
    return channel_group_clause("mt", params, alias="c")


def _paid_subquery():
    """Bảng tạm: mỗi Sales Invoice đã được bảng kê MT trả bao nhiêu tiền.

    CỘNG DỒN mọi dòng 'Thanh toán' trỏ về hóa đơn đó, bất kể thuộc bảng kê nào —
    một hóa đơn có thể được chuỗi trả làm nhiều lần (Co.op tách 8 kỳ trong một
    file; LOTTE có 2 ngày thanh toán). So từng dòng riêng lẻ với grand_total sẽ
    báo "chưa thanh toán" cho hóa đơn thực ra đã trả đủ.

    ABS() vì mỗi chuỗi một quy ước dấu — nhưng chỉ áp trên dòng đã được xác định
    là 'Thanh toán' bằng CỘT LOẠI CHỨNG TỪ ở tầng đọc file, không phải bằng dấu.

    Đếm cả bảng kê còn ở trạng thái 'Nháp': dòng đã được ghi nhận nghĩa là tiền
    đã về theo bản kê của chuỗi. Trạng thái Nháp/Đã đối chiếu/Đã ghi nhận nói về
    việc CON NGƯỜI đã soi tới đâu, không nói về việc tiền đã về hay chưa.

    HAI CỘT, cố ý tách:
      · `paid`        — chỉ dòng khớp 'Chắc chắn' (ký hiệu + số, hoặc người chốt
        tay). Đây là cột quyết định hóa đơn nằm rổ nào.
      · `paid_review` — dòng máy ĐOÁN ('Cần review': Emart khớp bằng số+ngày+tiền,
        dòng lệch chuỗi, dòng vượt tiền hóa đơn). Gộp chung vào `paid` là để một
        phỏng đoán tự đẩy hóa đơn ra khỏi rổ nợ — sai thì không còn màn hình nào
        hiện nó ra để người phát hiện.

    Lọc company NGAY TRONG JOIN: bảng kê của công ty khác không được phép làm
    hóa đơn của công ty này thành "đã thanh toán".

    `clawed_back` — TIỀN CHUỖI ĐÒI LẠI trên đúng hóa đơn đó (dòng 'Ghi giảm' có
    nối Sales Invoice). Quan sát thật: Co.op đòi lại tiền một hóa đơn đã trả
    bằng một dòng ghi giảm mang CÙNG số hóa đơn (HĐ 3176, −3.121.200đ). Không
    trừ ra thì hóa đơn vẫn hiện "đã thu đủ" trong khi tiền đã bị lấy lại — sai
    đúng hai lần số đó khi đối chiếu với sao kê.

    ⚠ CHƯA ĐỦ: tầng khớp tự động hiện chỉ nối Sales Invoice cho dòng 'Thanh
    toán' (xem `_match_row`), nên `clawed_back` chỉ có số khi người chốt tay
    liên kết cho dòng ghi giảm. Cột này vì vậy là bước đúng nhưng chưa khép kín
    — mở rộng khớp tự động cho dòng ghi giảm phải kiểm được trên database thật
    trước, vì dòng chiết khấu của Central Retail cũng mang ký hiệu hóa đơn bán
    ra của chính mình mà KHÔNG hề trả cho hóa đơn đó.
    """
    return """
        LEFT JOIN (
            SELECT l.sales_invoice AS si_name,
                   SUM(CASE WHEN l.match_confidence = 'Chắc chắn'
                            THEN ABS(l.total_amount) ELSE 0 END) AS paid,
                   SUM(CASE WHEN IFNULL(l.match_confidence, '') != 'Chắc chắn'
                            THEN ABS(l.total_amount) ELSE 0 END) AS paid_review,
                   SUM(CASE WHEN l.row_kind = %(kind_deduct)s
                            THEN ABS(l.total_amount) ELSE 0 END) AS clawed_back,
                   SUM(CASE WHEN l.row_kind = %(kind_payment)s THEN 1 ELSE 0 END) AS pay_lines,
                   MAX(IFNULL(l.payment_date, a.payment_date)) AS last_payment_date
            FROM `tabMT Payment Advice Line` l
            INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
                   AND a.company = %(company)s
            WHERE l.parenttype = 'MT Payment Advice'
              AND l.row_kind IN (%(kind_payment)s, %(kind_deduct)s)
              AND IFNULL(l.sales_invoice, '') != ''
            GROUP BY l.sales_invoice
        ) p ON p.si_name = si.name
    """


# Điều kiện của từng rổ hóa đơn.
#
# `is_return = 0` ở rổ "chưa thanh toán": hóa đơn trả hàng là khoản GHI GIẢM
# công nợ, không phải khoản phải thu. Để nó nằm trong rổ nợ thì rổ đó lúc nào
# cũng đầy phiếu trả hàng không bao giờ "được thanh toán" — báo động giả.
#
# Dùng TIỀN RÒNG (đã trả trừ đã đòi lại), không dùng `p.paid` trần: chuỗi đòi
# lại tiền của một hóa đơn đã trả thì hóa đơn đó phải quay về rổ nợ, không thì
# nó nằm mãi ở "đã thu đủ" trong khi tiền đã bị lấy đi.
_NET_PAID = "(IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0))"

_BUCKET_WHERE = {
    "chua_thanh_toan": f"si.is_return = 0 AND {_NET_PAID} < ABS(si.grand_total) - %(tol)s",
    "da_thanh_toan": f"{_NET_PAID} > 0 AND {_NET_PAID} >= ABS(si.grand_total) - %(tol)s",
    "tat_ca": "1 = 1",
}


# ═══════════════════════════════════════════════════════════════════════════
# Màn hình 1 — Tổng quan
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_overview(company=None, from_date=None, to_date=None):
    """Ba rổ của kênh MT + công nợ chuỗi.

    Ba rổ: hóa đơn CHƯA thu đủ tiền · hóa đơn ĐÃ thu đủ · các khoản chuỗi TRỪ
    LẠI (chiết khấu / phí / ghi giảm).
    """
    guard_mt()
    _require_tables()
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)

    p = {"company": company, "fd": from_date, "td": to_date,
         "tol": PAID_TOLERANCE, "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}
    mt = _mt_clause(p)
    join = _paid_subquery()

    def bucket(where):
        return frappe.db.sql(f"""
            SELECT COUNT(*) AS cnt,
                   IFNULL(SUM(ABS(si.grand_total)), 0) AS amount,
                   IFNULL(SUM(GREATEST(ABS(si.grand_total) - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), 0)), 0) AS remaining,
                   IFNULL(SUM(LEAST((IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), ABS(si.grand_total))), 0) AS collected,
                   IFNULL(SUM(IFNULL(p.paid_review, 0)), 0) AS pending_review
            FROM `tabSales Invoice` si
            INNER JOIN `tabCustomer` c ON c.name = si.customer
            {join}
            WHERE si.docstatus = 1 AND si.company = %(company)s
              AND si.posting_date BETWEEN %(fd)s AND %(td)s
              AND {mt} AND {where}
        """, p, as_dict=True)[0]

    chua = bucket(_BUCKET_WHERE["chua_thanh_toan"])
    da = bucket(_BUCKET_WHERE["da_thanh_toan"])

    # Rổ 3 đếm DÒNG BẢNG KÊ, không đếm hóa đơn: khoản chuỗi trừ lại thường không
    # gắn với hóa đơn nào (phí hỗ trợ, chiết khấu tháng, NET OFF).
    #
    # CỘNG THEO DẤU rồi mới lấy độ lớn Ở CẤP (chuỗi, loại) — KHÔNG ABS từng dòng.
    # VÌ SAO: LOTTE có 5 dòng 'NET OFF REGULAR' DƯƠNG nằm lẫn trong các dòng ghi
    # giảm ÂM; ABS từng dòng lật chiều 5 dòng đó, thổi ghi giảm LOTTE từ 809.335đ
    # (số đúng, §J) lên 11.868.813đ. Ngược lại KHÔNG được cộng thẳng theo dấu qua
    # nhiều chuỗi: §B của hợp đồng ghi rõ mỗi chuỗi một quy ước dấu (chiết khấu
    # Central Retail dương +27.240.347, LOTTE âm −31.460.649) nên cộng chung là
    # hai chuỗi triệt tiêu nhau. Lấy độ lớn theo từng chuỗi mới ra "chuỗi trừ lại
    # bao nhiêu".
    ded = frappe.db.sql(f"""
        SELECT a.chain, l.row_kind, COUNT(*) AS cnt,
               IFNULL(SUM(l.total_amount), 0) AS amount
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind IN ({', '.join(['%(k' + str(i) + ')s' for i in range(len(DEDUCTION_KINDS))])})
          AND a.company = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
        GROUP BY a.chain, l.row_kind
    """, dict(p, **{f"k{i}": k for i, k in enumerate(DEDUCTION_KINDS)}), as_dict=True)

    by_kind = {}
    for r in ded:
        d = by_kind.setdefault(r.row_kind, {"count": 0, "amount": 0.0})
        d["count"] += cint(r.cnt)
        d["amount"] += abs(flt(r.amount))

    # Công nợ chuỗi: tính tới HẾT to_date, không giới hạn trong khoảng xem.
    # Công nợ là SỐ DƯ, không phải phát sinh trong kỳ.
    #
    # KHÔNG dùng si.outstanding_amount của ERPNext: module này cố ý không tạo
    # Payment Entry, nên outstanding_amount vẫn bằng nguyên grand_total dù chuỗi
    # đã trả. Con số ở đây là "công nợ theo bảng kê chuỗi", phải ghi rõ như vậy
    # trên màn hình.
    debt = frappe.db.sql(f"""
        SELECT
            IFNULL(SUM(CASE WHEN si.is_return = 0
                            THEN GREATEST(ABS(si.grand_total) - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), 0) ELSE 0 END), 0) AS unpaid,
            IFNULL(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) AS credit_notes,
            SUM(CASE WHEN si.is_return = 0
                     AND (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)) < ABS(si.grand_total) - %(tol)s THEN 1 ELSE 0 END) AS unpaid_count
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date <= %(td)s AND {mt}
    """, p, as_dict=True)[0]

    # Dòng thanh toán chưa nối được hóa đơn nào — tiền đã về mà không biết của
    # hóa đơn nào. Đây là việc CẦN NGƯỜI làm, phải hiện ngay ở tổng quan.
    unmatched = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, IFNULL(SUM(ABS(l.total_amount)), 0) AS amount
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind_payment)s
          AND IFNULL(l.sales_invoice, '') = ''
          AND a.company = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
    """, p, as_dict=True)[0]

    need_review = frappe.db.sql("""
        SELECT COUNT(*) AS cnt
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.match_confidence = 'Cần review'
          AND a.company = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
    """, p, as_dict=True)[0]

    # Bảng kê KHÔNG điền công ty. Từ nay mọi truy vấn lọc `a.company = ...` cứng
    # (bản ghi thiếu company trước đây được tính cho MỌI công ty ⇒ nhân đôi khoản
    # ghi giảm trên toàn hệ thống). Đổi lại, bản ghi thiếu company sẽ biến khỏi
    # mọi màn hình — nên phải ĐẾM và hiện ra, tuyệt đối không để tiền mất im lặng.
    orphan = frappe.db.sql("""
        SELECT COUNT(*) AS cnt
        FROM `tabMT Payment Advice` a
        WHERE IFNULL(a.company, '') = ''
    """, as_dict=True)[0]

    advices = frappe.db.sql("""
        SELECT a.name, a.chain, a.customer, a.advice_no, a.payment_date, a.status,
               a.total_payment, a.total_discount, a.total_fee, a.total_other,
               a.declared_total_payment, a.reconciled, a.file_name
        FROM `tabMT Payment Advice` a
        WHERE a.company = %(company)s
          AND a.payment_date BETWEEN %(fd)s AND %(td)s
        ORDER BY a.payment_date DESC, a.creation DESC
        LIMIT 20
    """, p, as_dict=True)

    deduction_total = sum(v["amount"] for v in by_kind.values())

    return {
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "tolerance": PAID_TOLERANCE,
        "buckets": {
            "chua_thanh_toan": {"count": chua.cnt, "amount": flt(chua.amount),
                                "remaining": flt(chua.remaining), "collected": flt(chua.collected),
                                # Tiền đã về nhưng liên kết mới là PHỎNG ĐOÁN —
                                # chưa được trừ vào nợ, phải hiện riêng.
                                "pending_review": flt(chua.pending_review)},
            "da_thanh_toan": {"count": da.cnt, "amount": flt(da.amount),
                              "collected": flt(da.collected),
                              "pending_review": flt(da.pending_review)},
            "chiet_khau": {"count": sum(v["count"] for v in by_kind.values()),
                           "amount": deduction_total,
                           "by_kind": by_kind},
        },
        # Công nợ theo BẢNG KÊ CHUỖI, không phải số dư sổ cái (xem chú thích SQL).
        "debt": {
            "unpaid_invoices": flt(debt.unpaid),
            "unpaid_count": cint(debt.unpaid_count),
            "credit_notes": flt(debt.credit_notes),
            "estimate": flt(debt.unpaid) - flt(debt.credit_notes),
            "as_of": to_date,
            "note": _("Tính từ bảng kê thanh toán của chuỗi, KHÔNG phải số dư sổ cái "
                      "(hệ thống cố ý không tự tạo Payment Entry)."),
        },
        "attention": {
            "unmatched_payment_lines": {"count": unmatched.cnt, "amount": flt(unmatched.amount)},
            "need_review_lines": cint(need_review.cnt),
            # Bảng kê thiếu công ty: không còn được tính vào bất kỳ công ty nào.
            "advices_missing_company": cint(orphan.cnt),
        },
        "recent_advices": advices,
        "can_import": is_chief(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Màn hình 2 — Danh sách hóa đơn (chia trang 20/trang)
# ═══════════════════════════════════════════════════════════════════════════

def _invoice_page(company, from_date, to_date, where, search, page_size, offset, sort=None):
    p = {"company": company, "fd": from_date, "td": to_date, "tol": PAID_TOLERANCE,
         "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT, "limit": page_size, "offset": offset}
    mt = _mt_clause(p)
    join = _paid_subquery()
    if search:
        p["kw"] = f"%{search}%"
        where += (" AND (si.name LIKE %(kw)s OR si.customer_name LIKE %(kw)s"
                  f" OR si.{SI_NO_FIELD} LIKE %(kw)s)") if _has_si_field(SI_NO_FIELD) else \
                 " AND (si.name LIKE %(kw)s OR si.customer_name LIKE %(kw)s)"

    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND {mt} AND {where}
    """, p)[0][0]

    series_col = f"si.{SI_SERIES_FIELD}" if _has_si_field(SI_SERIES_FIELD) else "NULL"
    no_col = f"si.{SI_NO_FIELD}" if _has_si_field(SI_NO_FIELD) else "NULL"
    order = sort or "si.posting_date DESC, si.name DESC"

    rows = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, si.customer, si.customer_name, si.is_return,
               si.net_total, si.total_taxes_and_charges, si.grand_total,
               {series_col} AS inv_series, {no_col} AS inv_no,
               IFNULL(p.paid, 0) AS paid,
               IFNULL(p.clawed_back, 0) AS clawed_back,
               IFNULL(p.paid_review, 0) AS paid_review,
               IFNULL(p.pay_lines, 0) AS pay_lines,
               p.last_payment_date,
               GREATEST(ABS(si.grand_total) - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), 0) AS remaining
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND {mt} AND {where}
        ORDER BY {order}
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)

    _attach_payment_lines(rows)
    return rows, total


def _attach_payment_lines(rows):
    """Gắn các dòng bảng kê đã trả cho từng hóa đơn của TRANG hiện tại.

    Chỉ chạy trên ≤20 hóa đơn nên rẻ; và kế toán cần thấy NGAY tiền của hóa đơn
    này về từ bảng kê nào, kỳ nào — nhất là hóa đơn được trả làm nhiều lần.
    """
    names = [r["name"] for r in rows if r.get("pay_lines")]
    if not names:
        for r in rows:
            r["payments"] = []
        return
    lines = frappe.db.sql("""
        SELECT l.name AS line, l.parent AS advice, l.sales_invoice, l.total_amount,
               l.match_method, l.match_confidence, l.source_row,
               IFNULL(l.payment_date, a.payment_date) AS payment_date,
               a.chain, a.advice_no, a.status
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind_payment)s
          AND l.sales_invoice IN %(names)s
        ORDER BY payment_date, l.idx
    """, {"names": tuple(names), "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}, as_dict=True)
    grouped = defaultdict(list)
    for ln in lines:
        grouped[ln.sales_invoice].append(ln)
    for r in rows:
        r["payments"] = grouped.get(r["name"], [])


def _deduction_page(company, from_date, to_date, search, page_size, offset, chain=None):
    """Rổ 'chiết khấu' KHÔNG phải danh sách hóa đơn — nó là danh sách DÒNG khấu trừ.

    Chuỗi trừ lại chiết khấu, phí dịch vụ, hàng trả lại... phần lớn không gắn với
    hóa đơn nào. Ép chúng vào khung "hóa đơn" là bịa liên kết.
    """
    p = {"company": company, "fd": from_date, "td": to_date,
         "limit": page_size, "offset": offset}
    where = ["l.parenttype = 'MT Payment Advice'",
             "a.company = %(company)s",
             "IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s"]
    kinds = []
    for i, k in enumerate(DEDUCTION_KINDS):
        p[f"k{i}"] = k
        kinds.append(f"%(k{i})s")
    where.append(f"l.row_kind IN ({', '.join(kinds)})")
    if chain:
        p["chain"] = chain
        where.append("a.chain = %(chain)s")
    if search:
        p["kw"] = f"%{search}%"
        where.append("(l.description LIKE %(kw)s OR l.doc_no LIKE %(kw)s"
                     " OR l.store_name LIKE %(kw)s OR l.inv_no LIKE %(kw)s)")
    w = " AND ".join(where)

    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE {w}
    """, p)[0][0]

    rows = frappe.db.sql(f"""
        SELECT l.name AS line, l.parent AS advice, l.row_kind, l.inv_series, l.inv_no,
               l.inv_date, l.store_code, l.store_name, l.doc_no, l.description,
               l.amount_before_vat, l.vat_amount, l.total_amount, l.source_row,
               IFNULL(l.payment_date, a.payment_date) AS payment_date,
               a.chain, a.advice_no, a.customer, a.status
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE {w}
        ORDER BY payment_date DESC, a.name DESC, l.idx
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return rows, total


@frappe.whitelist()
def get_invoices(bucket, company=None, from_date=None, to_date=None, search=None,
                 page=1, page_size=PAGE_SIZE, chain=None):
    """Một TRANG của một rổ. bucket ∈ chua_thanh_toan | da_thanh_toan | chiet_khau | tat_ca.

    Chia trang ở tầng SQL, 20 dòng/trang. Kênh MT một tháng có hàng nghìn hóa
    đơn — nạp hết rồi cắt ở trình duyệt là treo máy kế toán.
    """
    guard_mt()
    _require_tables()
    if bucket not in BUCKETS:
        frappe.throw(_("Rổ không hợp lệ: {0}").format(bucket))
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)
    page, page_size, offset = _page(page, page_size)
    search = norm_text(search)

    if bucket == "chiet_khau":
        source = "mt_line"
        rows, total = _deduction_page(company, from_date, to_date, search, page_size, offset, chain)
    else:
        source = "erp"
        rows, total = _invoice_page(company, from_date, to_date, _BUCKET_WHERE[bucket],
                                    search, page_size, offset)

    return {
        "bucket": bucket,
        "source": source,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "tolerance": PAID_TOLERANCE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Màn hình 3 — Công nợ theo từng chuỗi
# ═══════════════════════════════════════════════════════════════════════════

def _customer_chain_map():
    """Customer -> chuỗi siêu thị, LẤY TỪ bảng kê kế toán đã chốt.

    KHÔNG đoán chuỗi từ tên khách hàng. Hợp đồng đọc file (§I) ghi rõ: ánh xạ mã
    nhà cung cấp của chuỗi sang Customer của ERPNext CHƯA được xác minh. Nguồn
    đáng tin duy nhất là trường `customer` mà kế toán tự điền trên MT Payment
    Advice.

    Khách hàng bị gán cho HAI chuỗi khác nhau thì trả về None cho khách đó —
    dồn vào nhóm "Chưa gán chuỗi" để người xử lý, chứ không chọn bừa một chuỗi.
    """
    rows = frappe.db.sql("""
        SELECT customer, chain, COUNT(*) AS n
        FROM `tabMT Payment Advice`
        WHERE IFNULL(customer, '') != '' AND IFNULL(chain, '') != ''
        GROUP BY customer, chain
    """, as_dict=True)
    by_cus = defaultdict(set)
    for r in rows:
        by_cus[r.customer].add(r.chain)
    mapping, ambiguous = {}, []
    for cus, chains in by_cus.items():
        if len(chains) == 1:
            mapping[cus] = next(iter(chains))
        else:
            ambiguous.append({"customer": cus, "chains": sorted(chains)})
    return mapping, ambiguous


UNASSIGNED = "Chưa gán chuỗi"

# Tỷ lệ tiền tối thiểu để coi MỘT khách hàng là chủ của cả kỳ thanh toán.
# 0.9 chứ không phải 1.0: một dòng khớp nhầm lẻ loi không nên phá kết luận, nhưng
# 10% tiền đi chỗ khác thì phải để người nhìn.
CUSTOMER_DOMINANT = 0.9


def detect_customer(lines, chain=None):
    """Đoán KHÁCH HÀNG của một kỳ thanh toán. Trả (customer, confidence, evidence, candidates).

    ⚠ KHÔNG đọc mã/tên trong file. Lý do đã xác minh trên cả 5 file thật: cái mà
    bảng kê in ra là ĐỊNH DANH CỦA CHÍNH TA, không phải của khách —
        LOTTE   `Vendor CD 007466`  = CONG TY CO PHAN HOANG GIANG
        Emart   `VENDOR CODE 100968` = CÔNG TY CỔ PHẦN HOÀNG GIANG
        Co.op   `Mã cung cấp 012556` = 233-Cty CP Hoang Giang
    Lấy mấy mã đó làm khách là gán ngược chiều mua bán. Còn mã BÊN MUA thì mỗi
    chuỗi một kiểu và ánh xạ sang Customer của ERPNext CHƯA chuỗi nào xác minh
    (§I hợp đồng): Central Retail có 2 `Account`, Co.op có 120 mã siêu thị thành
    viên, LOTTE 19 `Store CD`, Emart không có gì.

    Nguồn đáng tin duy nhất là SỔ CỦA CHÍNH MÌNH: hóa đơn đã khớp được thì
    `Sales Invoice.customer` chính là người ta đã xuất bán cho. Không cần bảng
    ánh xạ nào, và không thể sai theo kiểu đoán tên.

    Ba tầng, dừng ở tầng đầu tiên kết luận được:
      1. Từ hóa đơn đã khớp — cân theo TIỀN, không theo số dòng (một hóa đơn 100tr
         nặng hơn năm hóa đơn 1tr). Một khách chiếm >= 90% tiền -> 'Chắc chắn'.
      2. Nhiều khách cùng đáng kể -> KHÔNG chọn. Đây là chuyện THẬT: một bảng kê
         Co.op trả cho nhiều pháp nhân thành viên. Chọn đại khách lớn nhất là
         ghi tiền của pháp nhân này sang công nợ của pháp nhân khác.
      3. Không khớp được hóa đơn nào -> tra lịch sử: chuỗi này trước giờ kế toán
         gán cho khách nào. Đúng một khách -> đề xuất, nhưng 'Cần xác nhận'.
    """
    by_cus = defaultdict(lambda: {"amount": 0.0, "lines": 0, "name": None})
    total = 0.0
    for ln in lines:
        if ln.get("row_kind") != KIND_PAYMENT or not ln.get("_si_customer"):
            continue
        amt = abs(flt(ln.get("total_amount")))
        d = by_cus[ln["_si_customer"]]
        d["amount"] += amt
        d["lines"] += 1
        d["name"] = d["name"] or ln.get("_si_customer_name")
        total += amt

    cands = sorted(
        ({"customer": k, "customer_name": v["name"], "amount": v["amount"],
          "lines": v["lines"], "share": (v["amount"] / total) if total else 0.0}
         for k, v in by_cus.items()),
        key=lambda x: -x["amount"])

    if cands and total > 0:
        top = cands[0]
        if len(cands) == 1:
            return top["customer"], "Chắc chắn", "hoa_don_da_khop", cands
        if top["share"] >= CUSTOMER_DOMINANT:
            return top["customer"], "Chắc chắn", "hoa_don_da_khop_ap_dao", cands
        # Nhiều khách cùng đáng kể — KHÔNG chọn hộ.
        return None, "Nhiều khách", "nhieu_khach_trong_mot_ky", cands

    # Chưa khớp được hóa đơn nào. Lùi về lịch sử do kế toán tự chốt.
    if chain:
        hist = frappe.db.sql("""
            SELECT a.customer, COUNT(*) AS n
            FROM `tabMT Payment Advice` a
            WHERE a.chain = %(chain)s AND IFNULL(a.customer, '') != ''
            GROUP BY a.customer ORDER BY n DESC
        """, {"chain": chain}, as_dict=True)
        if len(hist) == 1:
            cus = hist[0].customer
            return cus, "Cần xác nhận", "lich_su_bang_ke_cua_chuoi", [{
                "customer": cus,
                "customer_name": frappe.db.get_value("Customer", cus, "customer_name"),
                "amount": 0.0, "lines": 0, "share": 0.0}]
        if len(hist) > 1:
            return None, "Nhiều khách", "lich_su_chuoi_co_nhieu_khach", [{
                "customer": h.customer,
                "customer_name": frappe.db.get_value("Customer", h.customer, "customer_name"),
                "amount": 0.0, "lines": h.n, "share": 0.0} for h in hist]

    return None, "Không xác định", "khong_co_can_cu", []


@frappe.whitelist()
def get_chain_summary(company=None, from_date=None, to_date=None):
    """Công nợ theo từng chuỗi: đã xuất · đã thu · chiết khấu · phí · còn lại.

    Hai trục thời gian KHÁC NHAU, cố ý tách bạch:
      · "đã xuất / đã thu / còn lại" tính trên HÓA ĐƠN ghi sổ trong kỳ (tiền của
        các hóa đơn đó thu lúc nào cũng tính, kể cả kỳ sau) — đây là công nợ.
      · "nhận trong kỳ / chiết khấu / phí" tính trên BẢNG KÊ có ngày thanh toán
        trong kỳ — đây là dòng tiền.
    Gộp hai trục vào một cột là ra con số không có nghĩa kế toán nào.
    """
    guard_mt()
    _require_tables()
    from_date, to_date = _range(from_date, to_date)
    company = _company(company)
    mapping, ambiguous = _customer_chain_map()

    p = {"company": company, "fd": from_date, "td": to_date,
         "tol": PAID_TOLERANCE, "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}
    mt = _mt_clause(p)
    join = _paid_subquery()

    # Gom theo KHÁCH HÀNG rồi mới quy về chuỗi trong Python: SQL không biết ánh
    # xạ khách -> chuỗi (nó nằm trong bảng kê do kế toán chốt).
    by_customer = frappe.db.sql(f"""
        SELECT si.customer, si.customer_name,
               COUNT(*) AS cnt,
               IFNULL(SUM(CASE WHEN si.is_return = 0 THEN ABS(si.grand_total) ELSE 0 END), 0) AS invoiced,
               IFNULL(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.grand_total) ELSE 0 END), 0) AS returns_amt,
               IFNULL(SUM(LEAST((IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), ABS(si.grand_total))), 0) AS collected,
               IFNULL(SUM(CASE WHEN si.is_return = 0
                          THEN GREATEST(ABS(si.grand_total) - (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)), 0) ELSE 0 END), 0) AS outstanding,
               SUM(CASE WHEN si.is_return = 0
                        AND (IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0)) < ABS(si.grand_total) - %(tol)s THEN 1 ELSE 0 END) AS unpaid_count
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.posting_date BETWEEN %(fd)s AND %(td)s AND {mt}
        GROUP BY si.customer, si.customer_name
    """, p, as_dict=True)

    # Dòng tiền theo bảng kê trong kỳ.
    #
    # Dòng 'Thanh toán' ABS ngay từng dòng (bản chất đã biết chắc nhờ cột loại
    # chứng từ). Dòng KHẤU TRỪ thì cộng THEO DẤU rồi mới lấy độ lớn ở cấp
    # (chuỗi, loại): LOTTE có dòng NET OFF dương lẫn trong ghi giảm âm, ABS từng
    # dòng là lật chiều chúng (xem chú thích ở get_overview).
    by_advice = frappe.db.sql("""
        SELECT a.chain, l.row_kind, COUNT(*) AS n,
               IFNULL(SUM(CASE WHEN l.row_kind = %(kind_payment)s
                               THEN ABS(l.total_amount) ELSE l.total_amount END), 0) AS amt
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND a.company = %(company)s
          AND IFNULL(l.payment_date, a.payment_date) BETWEEN %(fd)s AND %(td)s
        GROUP BY a.chain, l.row_kind
    """, p, as_dict=True)

    def blank(chain):
        return {
            "chain": chain, "customers": [], "invoice_count": 0, "unpaid_count": 0,
            "invoiced": 0.0, "returns": 0.0, "collected": 0.0, "outstanding": 0.0,
            "received_in_period": 0.0, "discount": 0.0, "fee": 0.0, "other": 0.0,
            "advice_lines": 0,
        }

    out = {}
    for r in by_customer:
        chain = mapping.get(r.customer) or UNASSIGNED
        d = out.setdefault(chain, blank(chain))
        d["customers"].append({"customer": r.customer, "customer_name": r.customer_name,
                               "invoiced": flt(r.invoiced), "outstanding": flt(r.outstanding)})
        d["invoice_count"] += cint(r.cnt)
        d["unpaid_count"] += cint(r.unpaid_count)
        d["invoiced"] += flt(r.invoiced)
        d["returns"] += flt(r.returns_amt)
        d["collected"] += flt(r.collected)
        d["outstanding"] += flt(r.outstanding)

    kind_field = {KIND_PAYMENT: "received_in_period", KIND_DISCOUNT: "discount",
                  KIND_FEE: "fee", KIND_DEDUCT: "other", KIND_OTHER: "other"}
    for r in by_advice:
        d = out.setdefault(r.chain or UNASSIGNED, blank(r.chain or UNASSIGNED))
        field = kind_field.get(r.row_kind)
        if not field:
            # row_kind lạ (DocType đổi options mà quên sửa đây) — không nuốt tiền
            # vào hư không, dồn vào "other" để còn thấy.
            field = "other"
        # Độ lớn ở cấp (chuỗi, loại) — xem chú thích của truy vấn.
        d[field] += abs(flt(r.amt))
        d["advice_lines"] += cint(r.n)

    # 'received_in_period' là TIỀN HÀNG GỘP của các dòng thanh toán, KHÔNG phải
    # số tiền chuỗi thực chuyển vào tài khoản: chuỗi trừ chiết khấu/phí/ghi giảm
    # trước khi chuyển. Đo trên file thật: Co.op 8.451.787.806 gộp vs 6.200.078.656
    # chuỗi in ra là thực trả — lệch 2.251.709.150đ. Kế toán đối chiếu cột này với
    # sao kê ngân hàng sẽ thấy lệch mà không hiểu vì sao, nên phải có cột 'thực
    # nhận ước tính' bên cạnh và nói rõ trong `note`.
    for d in out.values():
        d["net_received_est"] = (flt(d["received_in_period"]) - flt(d["discount"])
                                 - flt(d["fee"]) - flt(d["other"]))

    chains = sorted(out.values(), key=lambda x: -x["outstanding"])
    totals = blank("TỔNG")
    totals["net_received_est"] = 0.0
    for d in chains:
        for k in ("invoice_count", "unpaid_count", "advice_lines", "invoiced", "returns",
                  "collected", "outstanding", "received_in_period", "discount", "fee", "other",
                  "net_received_est"):
            totals[k] += d[k]
    totals["customers"] = []

    return {
        "from_date": from_date, "to_date": to_date, "company": company,
        "chains": chains,
        "totals": totals,
        # Khách hàng bị gán nhiều chuỗi — kế toán phải sửa, hệ thống không tự chọn.
        "ambiguous_customers": ambiguous,
        "note": _("'Đã xuất / còn lại' tính theo hóa đơn ghi sổ trong kỳ; "
                  "'nhận trong kỳ / chiết khấu / phí' tính theo ngày thanh toán của bảng kê. "
                  "'Nhận trong kỳ' là TIỀN HÀNG GỘP của các dòng thanh toán, KHÔNG phải số "
                  "tiền chuỗi chuyển khoản — chuỗi trừ chiết khấu/phí/ghi giảm trước khi "
                  "chuyển; cột 'Thực nhận (ước tính)' mới là số so được với sao kê ngân hàng."),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Đọc file bảng kê + khớp hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

def _check_size(content):
    """Chặn file khổng lồ TRƯỚC khi đưa vào openpyxl/xlrd.

    Tầng đọc file tự giải base64; ở đây chỉ giải để đo kích thước và bắt file
    rỗng sớm, vì một file hỏng vài chục MB đủ làm treo worker của kế toán.
    """
    raw = base64.b64decode((content or "").split(",")[-1])
    if not raw:
        frappe.throw(_("File rỗng"))
    if len(raw) > MAX_UPLOAD_BYTES:
        frappe.throw(_("File quá lớn ({0} MB). Tách bớt rồi tải lại.")
                     .format(round(len(raw) / 1024 / 1024, 1)))
    return len(raw)


def _advice_module():
    """Nạp tầng đọc file. Thiếu module thì BÁO RÕ chứ không nuốt lỗi."""
    try:
        from ketoan.api import mt_advice
    except ImportError:
        frappe.throw(_("Chưa có module đọc file bảng kê (ketoan.api.mt_advice)."))
    return mt_advice


def _read_file(content, chain):
    """Gọi tầng đọc file theo đúng hợp đồng ở đầu module.

    `chain` để trống thì tầng đọc TỰ NHẬN theo dấu hiệu trong file và THROW nếu
    không nhận ra — cố ý không đoán bừa: chọn nhầm parser vẫn ra một con số
    trông hợp lý nhưng đọc sai cột tiền.
    """
    mod = _advice_module()
    if chain:
        labels = getattr(mod, "CHAIN_LABEL", {}) or {}
        if chain not in labels and chain not in labels.values():
            frappe.throw(_("Chuỗi không hợp lệ: {0}").format(chain))
    fn = getattr(mod, "read_payment_advice", None)
    if not callable(fn):
        frappe.throw(_("Module ketoan.api.mt_advice thiếu hàm read_payment_advice(content, chain)."))
    parsed = fn(content, chain=chain or None) or {}
    if not parsed.get("chain"):
        frappe.throw(_("Tầng đọc file không trả về tên chuỗi — không ghi nhận."))
    return parsed


# Các trường có thể dùng để chia dòng về đúng LẦN THANH TOÁN của nó. Thứ tự này
# đã đối chiếu trên cả 5 file thật:
#   · Co.op         -> source_sheet (8 sheet = 8 kỳ)
#   · Central Retail-> doc_no       (2 Clearing Doc. trong 1 file)
#   · LOTTE         -> payment_date (2 Payment Date trong 1 file)
#   · WinCommerce, Emart -> chỉ 1 nhóm, không phải chia
_GROUP_FIELDS = ("source_sheet", "doc_no", "payment_date")


def _split_advices(parsed):
    """Chia `rows` về đúng từng nhóm trong `groups`. Trả [(group, rows)].

    Tầng đọc công bố nhóm (kèm `n_rows`) nhưng KHÔNG gắn số hiệu nhóm lên từng
    dòng, nên ở đây phải chia lại. Cách chia: thử lần lượt từng trường ứng viên,
    chỉ chấp nhận trường nào dựng lại ĐÚNG bộ khóa nhóm VÀ ĐÚNG số dòng của mỗi
    nhóm mà tầng đọc đã đếm.

    VÌ SAO khắt khe tới mức đó: chia sai là chia sai TIỀN — dồn 8 kỳ Co.op vào
    một phiếu, hoặc đẩy nhầm 21 dòng của Clearing Doc. này sang Clearing Doc.
    kia. Không trường nào dựng lại đúng thì DỪNG và bắt người xử lý, tuyệt đối
    không gộp tạm cho xong (gộp tạm chính là lỗi §J.3 của hợp đồng).
    """
    rows = parsed.get("rows") or []
    groups = parsed.get("groups") or []

    if len(groups) <= 1:
        g = dict(groups[0]) if groups else {}
        return [(g, rows)]

    keys = [cstr(g.get("key")) for g in groups]
    if len(set(keys)) == len(keys):
        for field in _GROUP_FIELDS:
            buckets = defaultdict(list)
            for r in rows:
                buckets[cstr(r.get(field) or "")].append(r)
            if set(buckets) != set(keys):
                continue
            if any(len(buckets[k]) != cint(g.get("n_rows")) for g, k in zip(groups, keys)):
                continue
            return [(dict(g), buckets[k]) for g, k in zip(groups, keys)]

    frappe.throw(_(
        "File có {0} lần thanh toán nhưng không chia được dòng về từng lần một cách "
        "chắc chắn. KHÔNG ghi nhận — gộp chung là cộng nhầm tiền của các kỳ vào nhau."
    ).format(len(groups)))


# ─────────────────────────────────────────────────────────────────────────
# Chỉ mục Sales Invoice để khớp
# ─────────────────────────────────────────────────────────────────────────

# Trần số dòng nạp vào chỉ mục hóa đơn. Vượt trần thì chỉ mục BỊ CẮT CỤT: hóa
# đơn rơi ra ngoài sẽ không khớp được và nằm mãi ở rổ "chưa thanh toán" — phải
# đếm trước và cảnh báo, không được cắt im lặng.
MAX_SI_INDEX_ROWS = 200000


def _si_index(company, dates):
    """Chỉ mục hóa đơn bán ra để khớp với dòng bảng kê.

    Khoảng ngày nới rộng quanh dải ngày hóa đơn đọc được trong file: chuỗi trả
    tiền cho hóa đơn xuất từ nhiều tháng trước (Co.op trả 20/01/2026 cho hóa đơn
    19/02/2025), nên không được lọc theo tháng thanh toán.

    CHỈ nạp hóa đơn của KHÁCH KÊNH MT và CHỈ hóa đơn bán ra (is_return = 0):
      · Kênh: cả 5 chuỗi dùng chung dải ký hiệu (C26THG), và hóa đơn kênh NPP
        cũng nằm trong dải đó. Không lọc kênh là để một dòng bảng kê siêu thị
        đánh dấu "đã thu" cho hóa đơn của nhà phân phối.
      · Trả hàng: ERPNext 'Create Return' COPY nguyên custom field sang credit
        note, nên credit note mang ĐÚNG ký hiệu/số của hóa đơn gốc. Để nó trong
        chỉ mục thì hoặc dòng thanh toán nối thẳng vào credit note (âm tiền),
        hoặc có 2 ứng viên và hóa đơn gốc VĨNH VIỄN không khớp được.
    """
    if not (_has_si_field(SI_SERIES_FIELD) and _has_si_field(SI_NO_FIELD)):
        return None

    if dates:
        fd, td = add_days(min(dates), -120), add_days(max(dates), 120)
    else:
        # Không có ngày hóa đơn nào đọc được -> quét rộng 3 năm còn hơn không khớp.
        td = nowdate()
        fd = add_months(td, -36)

    p = {"company": company, "fd": cstr(fd), "td": cstr(td)}
    mt = _mt_clause(p)

    # Hóa đơn bên MISA đã HỦY hoặc ĐÃ BỊ THAY THẾ vẫn còn docstatus=1 và vẫn giữ
    # nguyên số hóa đơn cũ ở ERPNext -> vẫn khớp "Chắc chắn" vào một hóa đơn đã
    # chết. Kéo trạng thái đó vào chỉ mục để hạ độ tin cậy (không loại hẳn: dòng
    # tiền vẫn có thật, chỉ là phải có người nhìn).
    snap_join, snap_cols = "", "0 AS snap_dead, 0 AS snap_deleted"
    if frappe.db.exists("DocType", "MISA Invoice Snapshot"):
        snap_cols = "IFNULL(s.dead, 0) AS snap_dead, IFNULL(s.is_deleted, 0) AS snap_deleted"
        snap_join = """
        LEFT JOIN (
            SELECT sales_invoice,
                   MAX(CASE WHEN match_status IN ('Đã hủy', 'Đã thay thế') THEN 1 ELSE 0 END) AS dead,
                   MAX(IFNULL(is_deleted, 0)) AS is_deleted
            FROM `tabMISA Invoice Snapshot`
            WHERE IFNULL(sales_invoice, '') != ''
            GROUP BY sales_invoice
        ) s ON s.sales_invoice = si.name
        """

    base = f"""
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        {snap_join}
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.is_return = 0
          AND si.posting_date BETWEEN %(fd)s AND %(td)s
          AND si.{SI_NO_FIELD} > ''
          AND {mt}
    """

    total = cint(frappe.db.sql(f"SELECT COUNT(*) {base}", p)[0][0])
    p["limit"] = MAX_SI_INDEX_ROWS
    rows = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, si.grand_total, si.customer, si.customer_name,
               si.is_return, c.customer_group, {snap_cols},
               si.{SI_SERIES_FIELD} AS inv_series, si.{SI_NO_FIELD} AS inv_no
        {base}
        ORDER BY si.posting_date DESC, si.name DESC
        LIMIT %(limit)s
    """, p, as_dict=True)

    # CHỈ MỤC HAI TẦNG.
    #
    # `by_exact` giữ ký hiệu NGUYÊN VĂN, `by_key` giữ ký hiệu đã cắt mẫu số.
    # VÌ SAO cần cả hai: `norm_series_mt` cắt chữ số mẫu số ở đầu để 'C26THG' và
    # '1C26THG' gặp được nhau (§E — lẫn lộn ngay trong một file). Nhưng cắt xong
    # thì '1C26THG' và '2C26THG' cũng chung một khóa, mà theo TT78 đó là HAI mẫu
    # số khác nhau (1 = hóa đơn GTGT, 2 = hóa đơn bán hàng), MỖI MẪU SỐ ĐÁNH SỐ
    # ĐỘC LẬP TỪ 1 — tức là số 4675 của mẫu 1 và số 4675 của mẫu 2 là hai hóa đơn
    # hoàn toàn khác nhau, của hai khách khác nhau.
    #
    # Chỉ có một tầng thì buộc phải chọn: hoặc khớp hụt, hoặc ghi tiền sang hóa
    # đơn khác. Hai tầng thì thử đúng trước, nới sau, và nới thì hạ độ tin cậy.
    by_exact, by_key, by_no = defaultdict(list), defaultdict(list), defaultdict(list)
    info = {}
    for r in rows:
        info[r.name] = r
        no = norm_inv_no(r.inv_no)
        if not no:
            continue
        exact = norm_series(r.inv_series)
        if exact:
            by_exact[(exact, no)].append(r.name)
        loose = norm_series_mt(r.inv_series)
        if loose:
            by_key[(loose, no)].append(r.name)
        by_no[no].append(r.name)
    return {"by_exact": by_exact, "by_key": by_key, "by_no": by_no, "info": info,
            "from": cstr(fd), "to": cstr(td),
            "count": total, "truncated": total > MAX_SI_INDEX_ROWS}


def _invoice_objection(si, chain, cus_chain):
    """Lý do KHÔNG được để một liên kết ở mức 'Chắc chắn'. Trả method ASCII hoặc None.

    · Khác chuỗi: cả 5 chuỗi dùng chung dải ký hiệu C26THG, nên chỉ cần đọc lệch
      một chữ số là tiền của chuỗi này được ghi vào hóa đơn của chuỗi khác — hai
      chuỗi lệch công nợ ngược chiều nhau mà không có cảnh báo nào. Ánh xạ khách
      hàng -> chuỗi lấy từ chính các bảng kê kế toán đã chốt (không đoán theo tên).
      Khách chưa từng xuất hiện trên bảng kê nào thì KHÔNG kết luận gì.
    · Hóa đơn bên MISA đã hủy / đã bị thay thế: tiền có thật nhưng hóa đơn đã chết.
    """
    if cus_chain and chain:
        other = cus_chain.get(si.get("customer"))
        if other and other != chain:
            return "khac_chuoi"
    if cint(si.get("snap_dead")) or cint(si.get("snap_deleted")):
        return "hoa_don_da_huy_thay_the"
    return None


def _match_row(row, idx, chain_key=None, chain=None, cus_chain=None):
    """Khớp MỘT dòng thanh toán với Sales Invoice.

    Trả (sales_invoice, match_method, match_confidence, ghi_chú).

    Bốn nguyên tắc, mỗi cái đều đã có bằng chứng từ file thật:
      · Chỉ khớp dòng 'Thanh toán'. Dòng chiết khấu của Central Retail mang ký
        hiệu hóa đơn bán ra của chính mình mà KHÔNG phải trả cho hóa đơn đó.
      · Ký hiệu phải bỏ chữ số dạng hóa đơn ở đầu: 'C26THG' và '1C26THG' là MỘT
        (§E — đã gặp lẫn lộn ngay trong một file ở Central Retail, LOTTE, Co.op).
      · Nhiều ứng viên thì KHÔNG nối. Nối bừa là đánh dấu đã trả cho hóa đơn của
        khách khác.
      · Emart không cấp ký hiệu -> khớp bằng SỐ + NGÀY + TIỀN và LUÔN 'Cần review'.

    Cờ `needs_review` của tầng đọc file luôn HẠ độ tin cậy xuống 'Cần review',
    kể cả khi ký hiệu + số khớp đúng một hóa đơn: tầng đọc bật cờ đó khi CHÍNH
    NÓ không chắc đã hiểu đúng dòng (Emart không có ký hiệu, Co.op có dòng trả
    hàng không đọc ra ký hiệu, LOTTE có dòng NET OFF không gắn hóa đơn).
    """
    no = norm_inv_no(row.get("inv_no") or "")
    if not no:
        return None, "khong_co_so_hoa_don", "Không khớp", None
    if idx is None:
        return None, "site_thieu_field_so_hoa_don", "Không khớp", None

    raw_series = norm_series(row.get("inv_series") or "")
    series = norm_series_mt(row.get("inv_series") or "")

    if series:
        # TẦNG 1 — ký hiệu nguyên văn. Khớp ở đây là chắc chắn nhất: cùng mẫu số,
        # cùng dải hóa đơn, không phải suy luận gì.
        cands = idx["by_exact"].get((raw_series, no)) or []
        method, downgrade = "ky_hieu_so", None

        if not cands:
            # TẦNG 2 — nới bằng cách cắt mẫu số. CHỈ được nới khi ký hiệu trong
            # FILE không có mẫu số (vd 'C26THG'): đó đúng là ca §E mà chuỗi in
            # thiếu chữ số đầu. Nếu file CÓ mẫu số mà tầng 1 trượt thì tuyệt đối
            # không nới — nới là gán số 4675 của mẫu 1 vào hóa đơn mẫu 2.
            if raw_series and raw_series == series:
                cands = idx["by_key"].get((series, no)) or []
                method = "ky_hieu_thieu_mau_so"
                # Nới thì hạ độ tin cậy: ta đang ĐOÁN rằng ký hiệu thiếu mẫu số
                # ứng với đúng mẫu số của hóa đơn tìm được.
                downgrade = "Cần review"

        if len(cands) == 1:
            si = idx["info"][cands[0]]
            diff = abs(abs(flt(row.get("total_amount"))) - abs(flt(si.grand_total)))
            # Lệch tiền KHÔNG làm mất liên kết: chuỗi có quyền trả từng phần, và
            # tổng nhiều kỳ mới đủ. Chênh lệch được trả về để _summarize hiện ra.
            bad = _invoice_objection(si, chain, cus_chain)
            if bad:
                return cands[0], bad, "Cần review", (flt(diff) or None)
            return cands[0], method, (downgrade or "Chắc chắn"), (flt(diff) or None)
        if len(cands) > 1:
            return None, f"trung_{len(cands)}_hoa_don", "Cần review", None
        return None, "khong_tim_thay_ky_hieu_so", "Không khớp", None

    # Không có ký hiệu. Nhánh này CHỈ dành cho Emart — chuỗi duy nhất không in ký
    # hiệu (§A). Chuỗi khác mà bóc ký hiệu ra rỗng nghĩa là ĐỌC HỎNG (WinCommerce
    # đổi dấu '#', Central Retail thiếu '|' trong Reference): khớp bằng số trần
    # trên chỉ mục gộp cả 5 chuỗi là vơ nhầm hóa đơn của chuỗi khác. Thà không
    # khớp và để người nối tay.
    if cstr(chain_key) != "emart":
        return None, "thieu_ky_hieu", "Không khớp", None

    # Thu hẹp bằng ngày hóa đơn VÀ số tiền, và chỉ nhận khi còn ĐÚNG MỘT ứng viên.
    # Ba vế cùng khớp mà vẫn để 'Cần review' vì đây là suy đoán, không phải khóa
    # tự nhiên.
    cands = idx["by_no"].get(no) or []
    if not cands:
        return None, "khong_tim_thay_so", "Không khớp", None
    inv_date = row.get("inv_date")
    amount = abs(flt(row.get("total_amount")))
    narrowed = []
    for name in cands:
        si = idx["info"][name]
        # Ứng viên thuộc chuỗi khác (hoặc hóa đơn đã hủy/thay thế) bị LOẠI khỏi
        # danh sách chứ không chỉ hạ độ tin cậy: ở nhánh đoán này, giữ lại là
        # mời hệ thống chọn nhầm hóa đơn của chuỗi khác.
        if _invoice_objection(si, chain, cus_chain):
            continue
        if inv_date and cstr(si.posting_date) != cstr(inv_date):
            continue
        if amount and abs(abs(flt(si.grand_total)) - amount) > PAID_TOLERANCE:
            continue
        narrowed.append(name)
    if len(narrowed) == 1:
        return narrowed[0], "so_ngay_tien", "Cần review", None
    return None, f"khong_ky_hieu_{len(cands)}_ung_vien", "Cần review", None


# ─────────────────────────────────────────────────────────────────────────
# Kế hoạch nạp
# ─────────────────────────────────────────────────────────────────────────

def _prior_paid(names):
    """Mỗi hóa đơn ĐÃ được các bảng kê ghi nhận trả bao nhiêu (trước file này).

    Dùng để phát hiện dòng làm hóa đơn bị trả VƯỢT giá trị: hai chuỗi cùng ghi
    nhầm một số hóa đơn, hoặc một kỳ bị nạp lại dưới tên file khác. Cộng cả dòng
    'Cần review' vào đây là cố ý — câu hỏi ở đây là "hóa đơn này đã bị phân bổ
    bao nhiêu tiền rồi", không phải "tiền đã chắc chắn về chưa".
    """
    names = sorted(n for n in set(names or []) if n)
    if not names:
        return {}
    rows = frappe.db.sql("""
        SELECT l.sales_invoice AS si, IFNULL(SUM(ABS(l.total_amount)), 0) AS paid
        FROM `tabMT Payment Advice Line` l
        WHERE l.parenttype = 'MT Payment Advice'
          AND l.row_kind = %(kind_payment)s
          AND l.sales_invoice IN %(names)s
        GROUP BY l.sales_invoice
    """, {"names": tuple(names), "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}, as_dict=True)
    return {r.si: flt(r.paid) for r in rows}


def _flag_overpaid(lines):
    """Hạ độ tin cậy dòng làm tổng tiền phân bổ VƯỢT giá trị hóa đơn.

    Trả nhiều đợt là bình thường (Co.op 8 kỳ, LOTTE 2 ngày) nên chỉ chặn khi
    TỔNG đã vượt — vượt nghĩa là hoặc nối nhầm hóa đơn, hoặc bảng kê bị nạp hai
    lần. Không xóa liên kết: kế toán phải nhìn thấy dòng đó và tự quyết.
    """
    matched = [ln for ln in lines if ln.get("sales_invoice")]
    if not matched:
        return
    before = _prior_paid([ln["sales_invoice"] for ln in matched])
    running = defaultdict(float)
    for ln in matched:
        si = ln["sales_invoice"]
        gt = abs(flt(ln.get("_si_grand_total")))
        running[si] += abs(flt(ln.get("total_amount")))
        allocated = flt(before.get(si, 0.0)) + running[si]
        if gt and allocated > gt + PAID_TOLERANCE:
            ln["_overpaid"] = allocated - gt
            ln["_paid_before"] = flt(before.get(si, 0.0))
            if ln.get("match_confidence") == "Chắc chắn":
                ln["match_confidence"] = "Cần review"
                ln["match_method"] = "vuot_tien_hoa_don"


def _map_rows(raw_rows, company, idx, chain=None, chain_key=None, cus_chain=None):
    """Dòng của tầng đọc file -> dòng của DocType, kèm kết quả khớp."""
    lines, dropped = [], 0
    for r in raw_rows or []:
        kind_raw = norm_text(r.get("row_kind"))
        if kind_raw in ROW_KIND_DROP:
            dropped += 1
            continue
        kind = ROW_KIND_MAP.get(kind_raw)
        unknown_kind = None
        if not kind:
            # Không vứt dòng có tiền chỉ vì không hiểu loại — dồn vào 'Khác' và
            # ghi lại nguyên văn để kế toán phân loại tay.
            kind, unknown_kind = KIND_OTHER, kind_raw

        line = {
            "row_kind": kind,
            "inv_series": norm_series(r.get("inv_series")),
            "inv_no": norm_text(r.get("inv_no")),
            "inv_no_norm": norm_inv_no(r.get("inv_no")),
            "inv_date": r.get("inv_date") or None,
            "store_code": norm_text(r.get("store_code")),
            "store_name": norm_text(r.get("store_name")),
            "doc_no": norm_text(r.get("doc_no")),
            "description": r.get("description") or None,
            # KHÔNG tự suy tiền trước thuế / tiền thuế khi file không có cột —
            # chia 1.1 hay 1.08 để ra số là bịa tiền.
            "amount_before_vat": flt(r.get("amount_before_vat")) if r.get("amount_before_vat") is not None else None,
            "vat_amount": flt(r.get("vat_amount")) if r.get("vat_amount") is not None else None,
            # `signed_amount` GIỮ NGUYÊN DẤU của file, `total_amount` của tầng đọc
            # là ĐỘ LỚN. Field DocType ghi rõ "giữ nguyên DẤU đọc được từ file" —
            # dấu là chốt đối chiếu với dòng tổng do chuỗi in ra. Lấy nhầm bản độ
            # lớn là mọi khoản chuỗi TRỪ LẠI biến thành khoản CỘNG THÊM.
            "total_amount": flt(r["signed_amount"] if r.get("signed_amount") is not None
                                else r.get("total_amount")),
            "payment_date": r.get("payment_date") or None,
            "source_row": cint(r.get("source_row")),
        }
        if unknown_kind:
            line["_unknown_kind"] = unknown_kind

        if kind == KIND_PAYMENT:
            si, method, conf, diff = _match_row(r, idx, chain_key=chain_key,
                                                chain=chain, cus_chain=cus_chain)
            if si and r.get("needs_review") and conf == "Chắc chắn":
                # Tầng đọc tự thấy dòng này đáng ngờ -> không được để 'Chắc chắn'
                # dù ký hiệu + số khớp đúng một hóa đơn.
                conf = "Cần review"
            line["sales_invoice"] = si
            line["match_method"] = method
            line["match_confidence"] = conf
            if si:
                info = idx["info"][si]
                line["_si_customer"] = info.customer
                line["_si_customer_name"] = info.customer_name
                line["_si_grand_total"] = flt(info.grand_total)
                line["_amount_diff"] = diff
        else:
            # Dòng khấu trừ KHÔNG được nối hóa đơn (child doctype cũng chặn).
            line["sales_invoice"] = None
            line["match_method"] = None
            line["match_confidence"] = None
        lines.append(line)
    _flag_overpaid(lines)
    return lines, dropped


def _totals(lines):
    t = {"total_payment": 0.0, "total_discount": 0.0, "total_fee": 0.0, "total_other": 0.0}
    field = {KIND_PAYMENT: "total_payment", KIND_DISCOUNT: "total_discount",
             KIND_FEE: "total_fee", KIND_DEDUCT: "total_other", KIND_OTHER: "total_other"}
    for ln in lines:
        t[field[ln["row_kind"]]] += flt(ln["total_amount"])
    return t


def _content_fingerprint(chain, payment_date, lines):
    """Vân tay NỘI DUNG của một kỳ thanh toán — danh tính thật của bảng kê.

    VÌ SAO không dùng tên file: LOTTE và Emart KHÔNG in số chứng từ (advice_no
    luôn rỗng), nên tên file từng là khóa chống trùng duy nhất — mà tên file của
    đúng hai chuỗi đó nhúng dấu thời gian xuất ('Payment_deduct_detail2026081408
    5903_CTTT_LOTTE.xls', 'APT_20250915_15094_100968_emart.xls'). Xuất lại cùng
    kỳ hôm sau, hoặc chỉ cần Save As tên khác, là nạp được lần hai và mọi hóa đơn
    của kỳ đó có paid gấp đôi.

    Vân tay lấy từ (số dòng nguồn, loại dòng, số hóa đơn, số tiền) của TOÀN BỘ
    dòng trong kỳ + chuỗi + ngày thanh toán. Cùng nội dung thì cùng vân tay dù
    tên file khác.
    """
    h = hashlib.sha1()
    h.update("F|{}|{}\n".format(chain or "", cstr(payment_date or "")).encode())
    for s in sorted(
        "{}|{}|{}|{}".format(cint(ln.get("source_row")), cstr(ln.get("row_kind") or ""),
                             norm_text(ln.get("inv_no")) or "",
                             round(flt(ln.get("total_amount")), 2))
        for ln in (lines or [])
    ):
        h.update((s + "\n").encode())
    return h.hexdigest()


def _existing_advice(chain, payment_date, advice_no, lines):
    """Bảng kê đã nạp rồi hay chưa — nạp hai lần là nhân đôi tiền đã thu.

    Hai lớp, cố ý theo thứ tự này:
      1. Số chứng từ của chuỗi (Co.op / Central Retail / WinCommerce có) — khóa
         tự nhiên, rẻ nhất.
      2. Vân tay nội dung — lớp duy nhất bắt được LOTTE và Emart (không có số
         chứng từ). KHÔNG lọc theo công ty: nạp cùng một file sang công ty khác
         vẫn là nạp trùng, phải chặn.
    """
    advice_no = norm_text(advice_no)
    pd = payment_date or None
    if advice_no:
        name = frappe.db.get_value(
            "MT Payment Advice",
            {"chain": chain, "payment_date": pd, "advice_no": advice_no}, "name")
        if name:
            return name

    want = _content_fingerprint(chain, pd, lines)
    cands = frappe.db.sql_list("""
        SELECT a.name FROM `tabMT Payment Advice` a
        WHERE a.chain = %(chain)s
          AND ((%(pd)s IS NULL AND a.payment_date IS NULL) OR a.payment_date = %(pd)s)
        ORDER BY a.creation DESC
        LIMIT 50
    """, {"chain": chain, "pd": cstr(pd) if pd else None})
    if not cands:
        return None

    rows = frappe.db.sql("""
        SELECT l.parent, l.source_row, l.row_kind, l.inv_no, l.total_amount
        FROM `tabMT Payment Advice Line` l
        WHERE l.parenttype = 'MT Payment Advice' AND l.parent IN %(names)s
    """, {"names": tuple(cands)}, as_dict=True)
    by_parent = defaultdict(list)
    for r in rows:
        by_parent[r.parent].append(r)
    for name in cands:
        if _content_fingerprint(chain, pd, by_parent.get(name) or []) == want:
            return name
    return None


def _declared(group, parsed, single, group_keys, parsed_key):
    """Số kiểm tra của MỘT kỳ, lấy theo thứ tự ưu tiên `group_keys`.

    Số tổng của CẢ FILE chỉ được dùng khi file có ĐÚNG MỘT kỳ. Dùng cho file
    nhiều kỳ là gán tổng của 8 kỳ Co.op cho từng kỳ — kỳ nào cũng "lệch" và cảnh
    báo lệch số kiểm tra trở thành vô nghĩa.
    """
    for k in group_keys:
        v = group.get(k)
        if v is not None:
            return flt(v)
    if single:
        v = (parsed.get("declared_totals") or {}).get(parsed_key)
        if v is not None:
            return flt(v)
    return None


# Sai số khi đối chiếu số kiểm tra. Tiền VND nguyên đồng nên về nguyên tắc phải
# lệch ĐÚNG 0; nới 3đ vì Co.op làm tròn chiết khấu ở cấp DÒNG và tiền thanh toán
# ở cấp NHÓM độc lập nhau (đã đo thật: lệch ±1đ ở 17/374 nhóm, ±3đ mỗi sheet).
DECLARED_TOLERANCE = 3.0


def _declared_relation(declared, totals):
    """Số kiểm tra do chuỗi in ra đang đo ĐẠI LƯỢNG NÀO của kỳ này?

    VÌ SAO phải hỏi câu này: mỗi chuỗi in một loại tổng khác nhau, và chúng
    KHÔNG cùng đơn vị đo với "tổng các dòng Thanh toán":
      · WinCommerce 'Tổng cộng'      = đúng tổng dòng thanh toán.
      · Emart 'phải trả tiền mua hàng' = đúng tổng dòng thanh toán.
      · Central Retail 'Result <doc>' = NET của cả kỳ (hàng − phí − chiết khấu
        − trả hàng). Đã kiểm trên file thật: −601.476.840 + 108.674.534 +
        27.240.347 + 5.119.605 = −460.442.354, khớp tuyệt đối.
      · Co.op 'Tổng Tiền'            = trị giá hàng + hàng trả lại (không trừ
        chiết khấu): 2.737.170.738 − 24.727.032 = 2.712.443.706, khớp tuyệt đối.

    Nhét thẳng con số đó vào `declared_total_payment` thì DocType so nó với tổng
    dòng thanh toán và kỳ nào cũng kêu lệch — kế toán quen tay bấm bỏ qua, tới
    lúc lệch THẬT thì không ai thấy nữa. Nên chỉ nhận vào field khi hai vế đo
    CÙNG một đại lượng; các quan hệ còn lại đưa ra màn xem trước và ghi chú.
    """
    if declared is None:
        return None, None
    tp = flt(totals["total_payment"])
    ck = flt(totals["total_discount"])
    fee = flt(totals["total_fee"])
    other = flt(totals["total_other"])
    for label, value in (
        ("total_payment", tp),
        ("total_payment+total_other", tp + other),
        ("net", tp + ck + fee + other),
    ):
        if abs(flt(declared) - value) <= DECLARED_TOLERANCE:
            return label, value
    # Không khớp đại lượng nào -> có thể là LỆCH THẬT (đọc sót dòng, sai cột
    # tiền). Phải để cảnh báo của DocType nổ.
    return None, None


def _plan(content, filename, chain, company):
    """Dựng kế hoạch nạp. KHÔNG ghi gì — dùng chung cho xem trước và nạp thật."""
    parsed = _read_file(content, chain)
    chain = parsed.get("chain")
    parts = _split_advices(parsed)
    if not parts or not any(rows for _g, rows in parts):
        frappe.throw(_("Không đọc được dòng tiền nào trong file"))

    # Dải ngày hóa đơn của CẢ file -> khoảng nạp chỉ mục Sales Invoice một lần
    # duy nhất, dùng chung cho mọi kỳ (Co.op 8 kỳ mà quét lại 8 lần là quá tốn).
    dates = []
    for r in parsed.get("rows") or []:
        if r.get("inv_date"):
            try:
                dates.append(getdate(r["inv_date"]))
            except Exception:
                pass
    idx = _si_index(company, dates)

    # Ánh xạ khách hàng -> chuỗi, lấy từ các bảng kê kế toán đã chốt (§I: KHÔNG
    # đoán chuỗi theo tên khách). Dùng để chặn tiền chuỗi này chạy sang hóa đơn
    # của chuỗi khác — cả 5 chuỗi dùng chung dải ký hiệu.
    cus_chain, _amb = _customer_chain_map()
    chain_key = cstr(parsed.get("chain_key") or "")

    single = len(parts) == 1
    fallback_date = None
    pay_dates = parsed.get("payment_dates") or []
    if single and len(pay_dates) == 1:
        fallback_date = pay_dates[0]

    plan = []
    for group, rows in parts:
        lines, dropped = _map_rows(rows, company, idx, chain=chain,
                                   chain_key=chain_key, cus_chain=cus_chain)
        totals = _totals(lines)
        payment_date = group.get("payment_date") or fallback_date or None
        advice_no = norm_text(group.get("advice_no")
                              or (parsed.get("advice_no") if single else None))
        # Co.op in cả 'Tổng Tiền' (trị giá hàng) lẫn 'Tổng Tiền Thanh Toán' (thực
        # trả sau chiết khấu); `declared_gross` mới là số so được với các DÒNG.
        reported = _declared(group, parsed, single,
                             ("declared_gross", "declared_payment"), "total_payment")
        relation, matched = _declared_relation(reported, totals)
        plan.append({
            "chain": chain,
            # company đi vào kế hoạch (và vào vân tay kế hoạch): người duyệt xem
            # trước cho công ty A mà lúc nạp lại ghi vào công ty B thì vân tay
            # phải lệch, nếu không bảng kê chui sang sổ công ty khác không dấu vết.
            "company": company,
            "advice_no": advice_no,
            "payment_date": cstr(payment_date) if payment_date else None,
            "group_key": cstr(group.get("key")) or None,
            "source_sheet": rows[0].get("source_sheet") if rows else None,
            # Chỉ đưa vào field khi số của file đo ĐÚNG "tổng dòng thanh toán",
            # hoặc khi nó không khớp đại lượng nào (để cảnh báo của DocType nổ).
            "declared_total_payment": reported if relation in (None, "total_payment") else None,
            "declared_total_discount": _declared(group, parsed, single,
                                                 ("declared_discount",), "total_discount"),
            # Giữ nguyên số chuỗi in ra + đại lượng nó đo, để màn xem trước và
            # ghi chú nói được "khớp cái gì", không mất bằng chứng.
            "declared_reported": reported,
            "declared_relation": relation,
            "declared_matched_value": matched,
            "lines": lines,
            "dropped_rows": dropped,
            "totals": totals,
            "existing": _existing_advice(chain, payment_date, advice_no, lines),
            # Chỉ mục hóa đơn bị cắt cụt -> có hóa đơn KHÔNG nằm trong chỉ mục,
            # dòng thanh toán của nó sẽ báo "chưa nối được hóa đơn" như một lỗi
            # khớp bình thường. Phải đi theo kế hoạch ra tới màn hình.
            "index_truncated": bool(idx and idx.get("truncated")),
            "index_count": cint(idx.get("count")) if idx else 0,
        })
    return chain, plan, parsed


def _plan_hash(plan):
    """Vân tay của ĐÚNG kế hoạch người vừa xem.

    `commit_advice` dựng lại kế hoạch từ đầu, nên giữa lúc xem trước và lúc bấm
    nạp, một hóa đơn mới ghi sổ (hoặc một liên kết bị sửa) có thể làm kết quả
    khớp đổi mà không ai nhìn thấy. So vân tay thì lệch một dòng cũng dừng lại.
    """
    h = hashlib.sha1()
    for a in plan:
        h.update("A|{}|{}|{}|{}|{}\n".format(
            a["chain"], a["advice_no"], a["payment_date"], a["group_key"] or "",
            a.get("company") or "").encode())
        for ln in a["lines"]:
            h.update("L|{}|{}|{}|{}|{}|{}|{}\n".format(
                ln["source_row"], ln["row_kind"], ln["inv_series"], ln["inv_no"],
                ln["total_amount"], ln.get("sales_invoice") or "",
                ln.get("match_confidence") or "").encode())
    return h.hexdigest()


def _public_line(ln):
    """Bỏ khóa nội bộ (_...) trước khi trả ra client."""
    return {k: v for k, v in ln.items() if not k.startswith("_")}


def _summarize(a):
    """Tóm tắt một kỳ thanh toán để hiện ở màn xem trước."""
    lines = a["lines"]
    pay = [ln for ln in lines if ln["row_kind"] == KIND_PAYMENT]
    matched = [ln for ln in pay if ln.get("sales_invoice")]
    review = [ln for ln in lines if ln.get("match_confidence") == "Cần review"]
    unknown = [ln for ln in lines if ln.get("_unknown_kind")]

    # Một hóa đơn được nối bởi NHIỀU dòng trong CÙNG một kỳ: có thể đúng (chuỗi
    # tách dòng) nhưng cũng có thể là đọc trùng dòng -> phải hiện ra cho người xem.
    seen = defaultdict(int)
    for ln in matched:
        seen[ln["sales_invoice"]] += 1
    repeated = [{"sales_invoice": k, "lines": v} for k, v in seen.items() if v > 1]

    declared = a["declared_total_payment"]
    diff = None if declared is None else flt(declared) - flt(a["totals"]["total_payment"])

    def _ref(ln, **extra):
        d = {"source_row": ln.get("source_row"),
             "inv_series": ln.get("inv_series"), "inv_no": ln.get("inv_no"),
             "sales_invoice": ln.get("sales_invoice"),
             "match_method": ln.get("match_method"),
             "match_confidence": ln.get("match_confidence"),
             "total_amount": flt(ln.get("total_amount")),
             "si_customer": ln.get("_si_customer"),
             "si_customer_name": ln.get("_si_customer_name"),
             "si_grand_total": ln.get("_si_grand_total")}
        d.update(extra)
        return d

    # LƯỚI AN TOÀN cho mọi lỗi nối nhầm hóa đơn: dòng khớp được nhưng số tiền
    # LỆCH so với grand_total. Trước đây chênh lệch này được tính rồi vứt đi
    # (_public_line lọc mọi khóa '_'), nên một dòng nối nhầm sang hóa đơn của
    # chuỗi khác hiện ra như một dòng khớp hoàn hảo. Lệch KHÔNG chặn nạp (chuỗi
    # được trả từng phần), nhưng phải nhìn thấy được.
    mismatches = [_ref(ln, diff=flt(ln["_amount_diff"]))
                  for ln in matched if flt(ln.get("_amount_diff")) > PAID_TOLERANCE]
    # Dòng đẩy tổng tiền phân bổ vượt giá trị hóa đơn (nối nhầm, hoặc kỳ này đã
    # được nạp ở đâu đó rồi).
    overpaid = [_ref(ln, over=flt(ln["_overpaid"]), paid_before=flt(ln.get("_paid_before")))
                for ln in matched if ln.get("_overpaid")]

    # Nhận diện khách hàng cho ĐÚNG KỲ NÀY, không phải cho cả file: một file
    # Co.op chứa 8 kỳ và các kỳ hoàn toàn có thể thuộc pháp nhân thành viên khác
    # nhau. Gán một khách cho cả file là dồn công nợ của nhiều pháp nhân vào một.
    det_cus, det_conf, det_ev, det_cands = detect_customer(lines, a["chain"])

    return {
        "chain": a["chain"],
        "advice_no": a["advice_no"],
        "payment_date": a["payment_date"],
        "group_key": a["group_key"],
        "source_sheet": a["source_sheet"],
        "detected_customer": det_cus,
        "detected_confidence": det_conf,
        "detected_evidence": det_ev,
        "customer_candidates": det_cands,
        "line_count": len(lines),
        "dropped_rows": a["dropped_rows"],
        "payment_lines": len(pay),
        "matched": len(matched),
        "unmatched": len(pay) - len(matched),
        "need_review": len(review),
        "unknown_kind": len(unknown),
        "repeated_invoices": repeated,
        # Ba lưới an toàn của màn xem trước, cạnh 'problems' (dòng KHÔNG khớp):
        "amount_mismatches": mismatches,
        "overpaid_invoices": overpaid,
        # Dòng bị hạ độ tin cậy vì hóa đơn thuộc chuỗi khác / đã hủy / đã thay thế.
        "cross_chain": [_ref(ln) for ln in matched
                        if ln.get("match_method") in ("khac_chuoi", "hoa_don_da_huy_thay_the")],
        "index_truncated": a.get("index_truncated"),
        "totals": a["totals"],
        "declared_total_payment": declared,
        "declared_total_discount": a["declared_total_discount"],
        # Số chuỗi in ra + đại lượng nó đo (total_payment / +ghi giảm / net).
        # 'declared_relation' = None nghĩa là KHÔNG khớp đại lượng nào — nghi
        # đọc sót dòng hoặc sai cột tiền, phải soi trước khi nạp.
        "declared_reported": a["declared_reported"],
        "declared_relation": a["declared_relation"],
        "declared_matched_value": a["declared_matched_value"],
        # Lệch số kiểm tra: cảnh báo, KHÔNG chặn. Co.op làm tròn ở cấp dòng và
        # cấp nhóm độc lập nhau nên lệch ±1..3đ là bình thường và đã đo trên file
        # thật; lệch lớn thì kế toán phải thấy ngay.
        "declared_diff": diff,
        "existing": a["existing"],
    }


@frappe.whitelist()
def preview_advice(content, filename=None, chain=None, company=None):
    """XEM TRƯỚC bảng kê: đọc file, khớp hóa đơn, KHÔNG ghi bất cứ thứ gì.

    Bắt buộc chạy trước `commit_advice` — trả về `plan_hash` mà commit đòi.
    """
    guard_mt()
    _require_tables()
    company = _company(company)
    _check_size(content)
    filename = norm_text(filename)
    chain, plan, parsed = _plan(content, filename, chain, company)

    advices = []
    for a in plan:
        s = _summarize(a)
        s["sample"] = [_public_line(ln) for ln in a["lines"][:20]]
        s["problems"] = [_public_line(ln) for ln in a["lines"]
                         if ln["row_kind"] == KIND_PAYMENT and not ln.get("sales_invoice")][:50]
        advices.append(s)

    grand = {k: sum(a["totals"][k] for a in plan)
             for k in ("total_payment", "total_discount", "total_fee", "total_other")}

    warnings = list(parsed.get("warnings") or [])
    if any(a.get("index_truncated") for a in plan):
        # Chỉ mục hóa đơn bị cắt cụt: hóa đơn ngoài chỉ mục sẽ báo "chưa nối được
        # hóa đơn" y hệt một lỗi khớp thường -> công nợ bị thổi phồng mà không ai
        # biết vì sao. Phải nói thẳng ra.
        warnings.append(_(
            "Chỉ mục hóa đơn bị cắt ở {0} dòng (khoảng ngày quá rộng). Kết quả khớp "
            "có thể THIẾU hóa đơn — đừng coi 'chưa nối được hóa đơn' là kết luận."
        ).format(MAX_SI_INDEX_ROWS))

    return {
        "chain": chain,
        "file_name": filename,
        "company": company,
        "advice_count": len(plan),
        "advices": advices,
        "grand_totals": grand,
        "warnings": warnings,
        # Đối chiếu THẬT nằm ở đây: tầng đọc so tổng của nó với SỐ KIỂM TRA do
        # chính chuỗi in trong file. `reconciled=False` KHÔNG chặn nạp — nhưng
        # kế toán phải nhìn thấy trước khi bấm, và trạng thái 'Đã ghi nhận' vẫn
        # đòi người tự tick 'Đã đối chiếu khớp'.
        "checks": parsed.get("checks") or [],
        "reconciled": bool(parsed.get("reconciled")),
        "declared_totals": parsed.get("declared_totals") or {},
        "computed_totals": parsed.get("computed_totals") or {},
        # Có bản ghi cũ cùng chuỗi + ngày + số chứng từ: nạp đè là nhân đôi tiền.
        "duplicates": [a["existing"] for a in plan if a["existing"]],
        "plan_hash": _plan_hash(plan),
        "can_commit": is_chief(),
        "customer_required": _("Chọn Khách hàng của chuỗi — hệ thống KHÔNG tự đoán "
                               "ánh xạ mã nhà cung cấp sang Customer."),
    }


def _note_text(note, a, parsed):
    """Ghi chú của kế toán + dấu vết đối chiếu của tầng đọc file.

    Kết quả đối chiếu số kiểm tra được ĐÓNG luôn vào bản ghi: sáu tháng sau,
    người soi lại phải thấy được lúc nạp file có khớp hay không mà không cần
    tìm lại file gốc.
    """
    parts = [cstr(note).strip()] if note else []
    if not parsed.get("reconciled"):
        bad = [c.get("label") for c in (parsed.get("checks") or []) if not c.get("ok")]
        parts.append(_("[Tự động] Lúc nạp: CHƯA khớp số kiểm tra của file{0}.")
                     .format((": " + ", ".join(cstr(b) for b in bad)) if bad else ""))
    else:
        parts.append(_("[Tự động] Lúc nạp: khớp toàn bộ số kiểm tra in trong file."))
    if a.get("declared_reported") is not None:
        rel = {
            "total_payment": _("tổng dòng thanh toán"),
            "total_payment+total_other": _("tổng dòng thanh toán + ghi giảm"),
            "net": _("tổng thuần cả kỳ (hàng − chiết khấu − phí − ghi giảm)"),
        }.get(a.get("declared_relation"))
        parts.append(
            _("[Tự động] Số chuỗi in trong file: {0} — {1}.").format(
                flt(a["declared_reported"]),
                _("khớp {0}").format(rel) if rel
                else _("KHÔNG khớp đại lượng nào cộng được từ các dòng, cần soi lại")))
    pay = [ln for ln in a["lines"] if ln["row_kind"] == KIND_PAYMENT]
    miss = [ln for ln in pay if not ln.get("sales_invoice")]
    if miss:
        parts.append(_("[Tự động] {0}/{1} dòng thanh toán chưa nối được hóa đơn.")
                     .format(len(miss), len(pay)))
    return "\n".join(p for p in parts if p) or None


def _todo_for(doc, a):
    """Giao việc cho người, KHÔNG tự hạch toán.

    Ràng buộc của dự án: file nhập chỉ được GHI NHẬN + đánh dấu + tạo ToDo. Mọi
    Payment Entry / Journal Entry do con người lập. ToDo hỏng không được làm
    hỏng việc nạp bảng kê — nên nuốt lỗi và ghi log.
    """
    pay = [ln for ln in a["lines"] if ln["row_kind"] == KIND_PAYMENT]
    miss = [ln for ln in pay if not ln.get("sales_invoice")]
    review = [ln for ln in a["lines"] if ln.get("match_confidence") == "Cần review"]
    if not miss and not review:
        return
    try:
        frappe.get_doc({
            "doctype": "ToDo",
            "description": _(
                "Bảng kê {0} ({1}, ngày {2}): {3} dòng thanh toán chưa nối hóa đơn, "
                "{4} dòng cần xem lại. Đối chiếu rồi lập chứng từ hạch toán bằng tay — "
                "hệ thống KHÔNG tự tạo Payment Entry."
            ).format(doc.name, doc.chain, cstr(doc.payment_date), len(miss), len(review)),
            "reference_type": "MT Payment Advice",
            "reference_name": doc.name,
            "priority": "Medium",
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mt.commit_advice/todo %s" % doc.name)


def _commit_lock():
    """Khóa quanh KIỂM TRÙNG + GHI.

    Kiểm trùng (SELECT) và insert nằm rời nhau là TOCTOU: file Co.op 8 kỳ chạy
    vài chục giây, gateway trả 504, kế toán bấm "Thử lại" trong khi request đầu
    còn đang chạy -> cả hai đều thấy "chưa có bản ghi nào" -> 16 bản ghi thay vì
    8 -> tiền đã thu của chuỗi nhân đôi. Hai tab trình duyệt cũng đủ gây ra.

    MỘT khóa duy nhất cho cả luồng nạp, KHÔNG khóa theo chuỗi/theo file: chuỗi
    có thể chưa biết lúc lấy khóa (client để trống, tầng đọc tự nhận), và hai
    file khác tên vẫn có thể là cùng một kỳ. Nạp bảng kê là việc thủ công, hiếm —
    xếp hàng toàn cục không mất gì, còn khóa sai khóa thì mất tiền.

    Đây là khóa cấp máy chủ — phòng thủ tầng DB (unique index trên MT Payment
    Advice) vẫn phải bổ sung ở tầng DocType.
    """
    try:
        from frappe.utils.synchronization import filelock
    except ImportError:
        from contextlib import nullcontext
        frappe.log_error("frappe.utils.synchronization.filelock không có — "
                         "nạp bảng kê chạy KHÔNG có khóa chống trùng song song",
                         "mt.commit_advice")
        return nullcontext()
    return filelock("mt_advice_commit", timeout=180)


@frappe.whitelist()
def commit_advice(content, filename=None, chain=None, expected_hash=None,
                  company=None, customer=None, note=None):
    """Nạp thật: tạo MT Payment Advice + dòng. MỖI KỲ THANH TOÁN MỘT BẢN GHI.

    Chỉ GHI NHẬN. KHÔNG tạo Payment Entry / Journal Entry — con người quyết định
    hạch toán sau khi soi bảng kê.
    """
    guard_manager()
    _require_tables()
    company = _company(company)
    _check_size(content)
    filename = norm_text(filename)
    if customer and not frappe.db.exists("Customer", customer):
        frappe.throw(_("Không tìm thấy khách hàng {0}").format(customer))
    # Từ đây tới frappe.db.commit() nằm TRONG khóa: dựng lại kế hoạch, kiểm trùng
    # và ghi phải là một khối không xen kẽ được (xem _commit_lock).
    with _commit_lock():
        return _commit_advice_locked(content, filename, chain, expected_hash,
                                     company, customer, note)


def _commit_advice_locked(content, filename, chain, expected_hash, company, customer, note):
    chain, plan, parsed = _plan(content, filename, chain, company)

    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới nạp được"))
    if _plan_hash(plan) != expected_hash:
        frappe.throw(_(
            "Dữ liệu đã đổi kể từ lúc xem trước (hóa đơn khớp được đã thay đổi). "
            "Xem lại rồi nạp — không ghi gì cả."
        ))

    dup = [a for a in plan if a["existing"]]
    if dup:
        # Nạp lại cùng một bảng kê là cộng đôi tiền đã thu, và mọi hóa đơn của kỳ
        # đó lập tức trông như đã trả gấp đôi. Xóa bản cũ rồi nạp lại nếu muốn.
        frappe.throw(_("Bảng kê đã được nạp rồi: {0}. Xóa bản cũ trước nếu muốn nạp lại.")
                     .format(", ".join(a["existing"] for a in dup)))

    # Dòng khớp được nhưng hóa đơn thuộc KHÁCH KHÁC với khách của bảng kê. Không
    # chặn (một chuỗi có thể có nhiều Customer: mỗi vùng/mỗi pháp nhân một mã),
    # nhưng phải trả về cho người nạp nhìn — tiền chạy sang hóa đơn của khách
    # khác là kiểu sai không tự lộ ra ở bất kỳ tổng nào.
    other_customer = []
    if customer:
        for a in plan:
            for ln in a["lines"]:
                if ln.get("sales_invoice") and ln.get("_si_customer") \
                        and ln["_si_customer"] != customer:
                    other_customer.append({
                        "advice_group": a["group_key"], "source_row": ln.get("source_row"),
                        "sales_invoice": ln["sales_invoice"],
                        "si_customer": ln["_si_customer"],
                        "total_amount": flt(ln.get("total_amount")),
                    })

    created = []
    auto_customer = []
    for a in plan:
        # Khách hàng: người chọn tay ĐÈ máy. Không chọn thì lấy máy nhận diện,
        # nhưng CHỈ khi máy chắc chắn — tự điền một phỏng đoán vào field công nợ
        # là gán tiền cho khách mà không ai kiểm.
        #
        # Nhận diện theo TỪNG KỲ, vì một file Co.op 8 kỳ có thể thuộc nhiều pháp
        # nhân thành viên khác nhau.
        row_customer = customer or None
        if not row_customer:
            det, conf, ev, _c = detect_customer(a["lines"], a["chain"])
            if det and conf == "Chắc chắn":
                row_customer = det
                auto_customer.append({"advice_group": a["group_key"],
                                      "customer": det, "evidence": ev})

        doc = frappe.get_doc({
            "doctype": "MT Payment Advice",
            "chain": a["chain"],
            "customer": row_customer,
            "company": company,
            "advice_no": a["advice_no"],
            "payment_date": a["payment_date"],
            "file_name": filename,
            "status": "Nháp",
            "declared_total_payment": a["declared_total_payment"],
            "declared_total_discount": a["declared_total_discount"],
            "note": _note_text(note, a, parsed),
            # KHÔNG tự tick 'reconciled': DocType ghi rõ kế toán tự tick sau khi
            # soi lệch. Kết quả đối chiếu của tầng đọc chỉ đi vào ghi chú.
            "lines": [_public_line(ln) for ln in a["lines"]],
        })
        doc.insert()
        _todo_for(doc, a)
        created.append({
            "name": doc.name,
            "chain": doc.chain,
            "advice_no": doc.advice_no,
            "payment_date": cstr(doc.payment_date),
            "lines": len(doc.lines or []),
            "total_payment": flt(doc.total_payment),
            "total_discount": flt(doc.total_discount),
            "total_fee": flt(doc.total_fee),
            "total_other": flt(doc.total_other),
            "declared_total_payment": flt(doc.declared_total_payment),
        })
    frappe.db.commit()

    warnings = list(parsed.get("warnings") or [])
    if other_customer:
        warnings.append(_("{0} dòng nối vào hóa đơn của khách khác với khách đã chọn — soi lại.")
                        .format(len(other_customer)))
    if any(a.get("index_truncated") for a in plan):
        warnings.append(_("Chỉ mục hóa đơn bị cắt cụt lúc khớp — có dòng 'chưa nối được "
                          "hóa đơn' chỉ vì hóa đơn không nằm trong chỉ mục."))

    if auto_customer:
        # Máy tự điền khách thì phải NÓI RA. Điền im lặng nghĩa là gán công nợ
        # cho một khách hàng mà không ai xác nhận.
        warnings.append(_("Đã tự nhận diện khách hàng cho {0} kỳ (suy từ hóa đơn đã khớp). "
                          "Kiểm lại trên bảng kê nếu thấy lạ.").format(len(auto_customer)))

    return {
        "created": created,
        "advice_count": len(created),
        "auto_customer": auto_customer,
        "lines_on_other_customer": other_customer,
        "warnings": warnings,
        "checks": parsed.get("checks") or [],
        "reconciled": bool(parsed.get("reconciled")),
        "message": _("Đã ghi nhận {0} bảng kê từ file {1}. "
                     "Hệ thống KHÔNG tự hạch toán — kiểm tra rồi lập chứng từ tay.")
        .format(len(created), filename),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Chốt tay liên kết dòng ↔ hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def relink_line(line, sales_invoice=None, note=None):
    """Kế toán chốt tay (hoặc gỡ) liên kết một dòng bảng kê với Sales Invoice.

    KHÔNG chặn khi hóa đơn đã có dòng khác trỏ tới: một hóa đơn được chuỗi trả
    làm nhiều lần là chuyện thường (Co.op tách 8 kỳ, LOTTE 2 ngày thanh toán).
    Chỉ BÁO LẠI các liên kết đang có để người chốt tự nhìn — chặn cứng ở đây sẽ
    khóa mất nghiệp vụ trả nhiều đợt.
    """
    guard_manager()
    _require_tables()
    row = frappe.db.get_value(
        "MT Payment Advice Line", line,
        ["name", "parent", "parenttype", "row_kind", "inv_series", "inv_no",
         "total_amount", "sales_invoice"], as_dict=True)
    if not row or row.parenttype != "MT Payment Advice":
        frappe.throw(_("Không tìm thấy dòng bảng kê {0}").format(line))

    if row.row_kind != KIND_PAYMENT:
        # BẪY TIỀN THẬT: dòng chiết khấu của Central Retail (Doc.Type=KS) mang ký
        # hiệu hóa đơn bán ra của chính mình mà KHÔNG phải thanh toán hóa đơn đó.
        # Nối là đánh dấu hóa đơn "đã thanh toán" trong khi thực tế chưa.
        frappe.throw(_("Dòng loại '{0}' không được nối hóa đơn. Chỉ dòng '{1}' mới được khớp.")
                     .format(row.row_kind or "", KIND_PAYMENT))

    others = []
    if sales_invoice:
        si = frappe.db.get_value("Sales Invoice", sales_invoice,
                                 ["name", "docstatus", "company", "customer", "customer_name",
                                  "grand_total", "is_return"],
                                 as_dict=True)
        if not si:
            frappe.throw(_("Không tìm thấy hóa đơn {0}").format(sales_invoice))
        if si.docstatus != 1:
            frappe.throw(_("Hóa đơn {0} chưa ghi sổ (docstatus={1})").format(sales_invoice, si.docstatus))

        # Modal chọn hóa đơn dùng API tìm kiếm CHUNG của luồng MISA: nó trả hóa
        # đơn của CẢ ba kênh và MỌI công ty. Không chặn ở đây thì một dòng LOTTE
        # (kênh MT, công ty A) nối được vào hóa đơn khách NPP của công ty B —
        # hóa đơn đó biến khỏi rổ nợ kênh NPP, còn tiền LOTTE thì không hiện ở
        # màn hình MT nào (mọi truy vấn MT lọc customer_group='MT'). Tiền biến
        # mất khỏi cả hai kênh, không cảnh báo.
        adv = frappe.db.get_value("MT Payment Advice", row.parent,
                                  ["company", "chain"], as_dict=True) or frappe._dict()
        if adv.company and si.company and si.company != adv.company:
            frappe.throw(_("Hóa đơn {0} thuộc công ty {1}, khác công ty {2} của bảng kê.")
                         .format(sales_invoice, si.company, adv.company))
        if si.is_return:
            # Credit note được ERPNext copy nguyên ký hiệu/số của hóa đơn gốc nên
            # rất dễ chọn nhầm; và dòng 'Thanh toán' không bao giờ trả cho một
            # phiếu trả hàng.
            frappe.throw(_("Hóa đơn {0} là phiếu trả hàng — dòng thanh toán không nối "
                           "vào phiếu trả hàng.").format(sales_invoice))
        mt_group = (get_settings().get("mt_customer_group") or "MT")
        cg = frappe.db.get_value("Customer", si.customer, "customer_group")
        if cstr(cg) != cstr(mt_group):
            frappe.throw(_("Khách hàng {0} của hóa đơn {1} thuộc nhóm '{2}', không phải "
                           "kênh MT ('{3}') — không nối bảng kê siêu thị vào hóa đơn này.")
                         .format(si.customer, sales_invoice, cg or "", mt_group))
        others = frappe.db.sql("""
            SELECT l.name AS line, l.parent AS advice, l.total_amount,
                   IFNULL(l.payment_date, a.payment_date) AS payment_date, a.chain
            FROM `tabMT Payment Advice Line` l
            INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
            WHERE l.parenttype = 'MT Payment Advice' AND l.sales_invoice = %(si)s
              AND l.name != %(line)s AND l.row_kind = %(kind_payment)s
        """, {"si": sales_invoice, "line": line, "kind_payment": KIND_PAYMENT, "kind_deduct": KIND_DEDUCT}, as_dict=True)

    values = {
        "sales_invoice": sales_invoice or None,
        "match_method": "thu_cong" if sales_invoice else None,
        "match_confidence": "Chắc chắn" if sales_invoice else "Không khớp",
    }
    # Bảng kê KHÔNG phải chứng từ đã ghi sổ, nhưng vẫn dùng db_set: save() cả
    # document cha sẽ chạy lại validate và bắn msgprint lệch số kiểm tra mỗi lần
    # chốt một dòng — và không có gì trong tổng tiền thay đổi khi đổi liên kết.
    frappe.db.set_value("MT Payment Advice Line", line, values, update_modified=False)

    # ĐẨY MỐC THỜI GIAN CỦA BẢN GHI CHA. Frappe kiểm xung đột ghi bằng
    # check_if_latest() trên `modified` của CHA, còn bảng con thì bị xóa-và-chèn-
    # lại nguyên khối khi ai đó Save form. Không đẩy mốc: một form Desk mở từ
    # trước, bấm Save sau, sẽ qua được check_if_latest và ghi đè im lặng liên kết
    # vừa chốt tay — hóa đơn quay lại rổ "chưa thanh toán" trong khi Comment vẫn
    # ghi "đã chốt", dẫn người soi lại đi sai hướng.
    frappe.db.set_value("MT Payment Advice", row.parent, "modified",
                        frappe.utils.now(), update_modified=False)

    # Vết kiểm toán đi vào Comment của bảng kê, KHÔNG đè lên trường dữ liệu đọc
    # từ file (description là nguyên văn của chuỗi, đè là mất bằng chứng gốc).
    text = _("Chốt tay liên kết: {0} → {1}").format(
        row.sales_invoice or _("(chưa nối)"), sales_invoice or _("(gỡ liên kết)"))
    if note:
        text += "<br>" + frappe.utils.escape_html(cstr(note))
    try:
        frappe.get_doc("MT Payment Advice", row.parent).add_comment("Comment", text)
    except Exception:
        # Không ghi được vết thì vẫn giữ liên kết đã chốt, chỉ log lại.
        frappe.log_error(frappe.get_traceback(), "mt.relink_line/comment")

    frappe.db.commit()
    return {
        "line": line,
        "advice": row.parent,
        "previous": row.sales_invoice,
        **values,
        "other_lines_on_invoice": others,
    }
