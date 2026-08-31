"""mt_hoan — HÀNG HOÀN CHỜ XỬ LÝ: hàng đợi việc giấy tờ của một lần hàng quay về.

════════════════════════════════════════════════════════════════════════════
CÂU HỎI NÀY KHÁC CÂU HỎI CỦA SỔ THEO DÕI HÓA ĐƠN
════════════════════════════════════════════════════════════════════════════

Sổ theo dõi (`mt_ledger`) lấy TỜ HÓA ĐƠN làm đơn vị, và cột `N chưa có HĐ` của
nó đếm **phiếu trả hàng đã lập mà chưa có chứng từ thuế**. Đúng, nhưng nó không
bao giờ đếm được cái nguy hiểm hơn:

    lần hàng quay về mà CHƯA AI LẬP PHIẾU TRẢ.

Chưa có phiếu trả thì không có gì để đếm — việc đó vô hình với mọi màn hình
đang có. Hóa đơn gốc vẫn đòi đủ tiền, siêu thị vẫn trừ phần hàng trả khi trả
tiền, và chênh lệch chỉ lộ ra ở khâu đối soát vài tháng sau, lúc không ai còn
nhớ chuyến hàng nào.

Nên màn này lấy **LẦN HÀNG QUAY VỀ** làm đơn vị, không lấy tờ hóa đơn. Một hóa
đơn có thể vừa móp lúc giao (tháng 6) vừa bị trả hàng date (tháng 8) — hai lần,
hai phiếu trả, hai việc. Đếm theo hóa đơn là gộp hai việc thành một.

════════════════════════════════════════════════════════════════════════════
BỐN Ô CỦA HÀNG ĐỢI
════════════════════════════════════════════════════════════════════════════

    chua_vao_so     phiếu sự cố bên `vanchuyen` CHƯA có dòng nào trong sổ này
    chua_phieu_tra  đã vào sổ, chưa lập phiếu trả hàng trên ERPNext
    chua_chung_tu   đã có phiếu trả, chưa có hóa đơn thay thế/điều chỉnh
    xong            đủ chứng từ (hoặc đã kết luận "không cần")

Ba ô đầu là VIỆC. Ô `chua_vao_so` đứng trước vì nó là ô duy nhất mà việc còn
nằm ngoài tầm nhìn của kế toán.

════════════════════════════════════════════════════════════════════════════
VÌ SAO KHÔNG TỰ TẠO DÒNG SỔ TỪ PHIẾU SỰ CỐ
════════════════════════════════════════════════════════════════════════════

Cách gọn nhất là một `doc_events` trên `Su Co Van Chuyen`: có sự cố thì đẻ luôn
một dòng `MT Hang Hoan`. Không làm, vì hai lẽ:

1. Hook trỏ vào DocType của app khác thì `ketoan` KHÔNG CÀI ĐƯỢC trên site chưa
   có `vanchuyen` — đúng lý do `MT Hang Hoan.su_co` là Data chứ không phải Link.

2. **Không phải sự cố nào cũng sinh việc kế toán.** Giao chậm rồi giao đủ, sai
   địa chỉ rồi giao lại — hóa đơn gốc vẫn đúng, không chứng từ nào phải làm. Tự
   tạo hàng loạt là dựng một hàng đợi đầy việc không có thật, và hàng đợi như
   thế thì hai tuần nữa không ai mở. Lúc đó nó nuốt luôn việc thật.

Nên: **máy liệt kê ứng viên, NGƯỜI bấm nhận.**

Và "bỏ qua" KHÔNG cần cờ riêng: nhận vào sổ rồi chốt `chung_tu_can = "Không cần
chứng từ"` là dòng ra khỏi hàng đợi ngay, mà vẫn còn dấu vết ai kết luận, lúc
nào. Một cái cờ `bo_qua` riêng thì làm được đúng việc đó nhưng mất phần "kết
luận là gì" — và phần đó chính là thứ người soát sau sẽ hỏi.

════════════════════════════════════════════════════════════════════════════
ĐỌC SỐNG TỪ `vanchuyen`; BẢN CHÉP CHỈ LÀ LƯỚI AN TOÀN
════════════════════════════════════════════════════════════════════════════

`MT Hang Hoan` chép `loai_su_co` · `huong_xu_ly` · `po_no` sang cột read-only
của mình lúc nhận. Nhưng **`huong_xu_ly` là khóa chính quyết định chứng từ phải
làm** ("Hủy đơn" chỉ tồn tại ở cột đó), và điều phối sửa nó sau khi làm việc với
siêu thị là chuyện thường. Đọc bản chép thì kế toán làm việc trên một tiền đề
đã cũ mà không có gì báo.

Nên danh sách ĐỌC SỐNG từ `tabSu Co Van Chuyen` khi site có app đó, và **nói ra
chỗ đã đổi** (`da_doi`) thay vì lặng lẽ tráo giá trị dưới tay người đang đọc.
Bản chép chỉ được dùng khi phiếu sự cố không còn (bị xóa, hoặc site gỡ app).

`sync_hoan` là chỗ ghi bản chép mới — người bấm, không phải máy ghi lúc đọc.

════════════════════════════════════════════════════════════════════════════
KHÔNG LỌC THEO `Su Co Van Chuyen.trang_thai`
════════════════════════════════════════════════════════════════════════════

Cột đó thuộc ĐIỀU HÀNH và nghĩa là *vận chuyển xong* — điều phối bấm "Đã xử lý"
ngay khi nhà xe xác nhận hàng về. Lọc hàng đợi kế toán theo nó là việc "chưa
xuất hóa đơn điều chỉnh" biến mất khỏi màn hình ngay hôm đó, im lặng.

Màn hình vẫn **HIỆN** cột đó (kế toán cần biết điều hành đang ở đâu), nhưng
KHÔNG có mệnh đề `WHERE` nào đọc nó. `hoan_check` canh đúng chỗ này.

════════════════════════════════════════════════════════════════════════════
`return_invoice` — CHỨNG TỪ, KHÔNG PHẢI TIỀN (MT2-AK)
════════════════════════════════════════════════════════════════════════════

Module này đọc `MT Payment Advice Line.return_invoice` để biết "siêu thị đã tự
xuất hóa đơn trả" — và chỉ đọc ở **một hàm duy nhất**, `_chung_tu_sieu_thi`,
hàm đó KHÔNG cộng tiền, KHÔNG `SUM(`, KHÔNG chạm `total_amount`. Cho dòng ghi
giảm nối vào đường tiền là trừ lần thứ hai một lần trả hàng đã được phiếu trả
trừ rồi (`mt._returns_join`). `return_doc_check` quét mọi hàm trong `api/` theo
đúng luật này.

Ngoài `create_hoan` · `save_hoan` · `sync_hoan` · `delete_hoan` (ghi trên bảng
CỦA APP NÀY), module CHỈ ĐỌC. Nó không bao giờ ghi vào bảng của `vanchuyen`:
`db.set_value` bên đó bỏ qua `_stamp_si()` và cờ `custom_co_su_co` trên Sales
Invoice kẹt vĩnh viễn.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, nowdate

from ketoan.api._guard import guard_manager, guard_mt, is_chief
from ketoan.api.mt import (
    SI_NO_FIELD,
    SI_PO_FIELD,
    _company,
    _customer_chain_map,
    _customer_in_clause,
    _mt_clause,
    _page,
    _require_tables,
    chain_customers,
    po_column,
)
from ketoan.mt.doctype.mt_hang_hoan.mt_hang_hoan import (
    CT_DIEU_CHINH,
    CT_KHONG_CAN,
    CT_SIEU_THI,
    CT_THAY_THE,
    GIAY_CHUA_CT,
    GIAY_CHUA_TRA,
    GIAY_XONG,
)

DOCTYPE = "MT Hang Hoan"
SU_CO = "Su Co Van Chuyen"
SU_CO_ITEM = "Su Co Hang Ve"

# Ô hàng đợi. `cho_xu_ly` gộp hai ô việc — mặc định của màn hình, vì câu hỏi
# hằng ngày là "còn việc gì", không phải "còn việc loại nào".
B_CHUA_VAO_SO = "chua_vao_so"
B_CHUA_PHIEU_TRA = "chua_phieu_tra"
B_CHUA_CHUNG_TU = "chua_chung_tu"
B_CHO_XU_LY = "cho_xu_ly"
B_XONG = "xong"
BUCKETS = (B_CHUA_VAO_SO, B_CHUA_PHIEU_TRA, B_CHUA_CHUNG_TU, B_CHO_XU_LY, B_XONG)

CHUNG_TU_OPTIONS = (CT_THAY_THE, CT_DIEU_CHINH, CT_SIEU_THI, CT_KHONG_CAN)

TRANG_THAI_HANG = ("Chưa về", "Đang về", "Đã về sân", "Đã lọc xong")

# Cột chép sang sổ này lúc nhận phiếu sự cố. Khai MỘT chỗ vì `create_hoan` ghi
# nó, `sync_hoan` ghi lại nó, và danh sách so lệch đọc nó — ba nơi lệch nhau thì
# "đã đổi" báo sai, mà một cảnh báo hay báo sai thì sớm muộn cũng bị bỏ qua.
COPIED = (
    ("loai_su_co", "loai_su_co"),
    ("huong_xu_ly", "huong_xu_ly"),
    ("ngay_xay_ra", "ngay_phat_sinh"),
    ("trang_thai_hang", "hang_ve_trang_thai"),
    ("ngay_hang_ve", "ngay_hang_ve"),
)

# Cột QUYẾT ĐỊNH chứng từ phải làm. Chỉ ba cột này được báo "đã đổi": báo mọi
# cột thì mỗi lần điều phối gõ thêm một chữ vào ghi chú là cả danh sách nhấp
# nháy, và cảnh báo nhấp nháy vì chuyện vặt là cảnh báo bị tắt.
DRIFT_WATCH = ("loai_su_co", "huong_xu_ly", "ngay_xay_ra")

MAX_ROWS = 200


def _tables():
    """Bảng của app NÀY đã migrate chưa."""
    if not frappe.db.table_exists(DOCTYPE):
        frappe.throw(_(
            "Sổ hàng hoàn chưa được cài trên site này (thiếu bảng {0}). "
            "Quản trị chạy: bench --site TÊN_SITE migrate"
        ).format(DOCTYPE))


def _has_vanchuyen():
    """Site có app `vanchuyen` (đã migrate) hay không.

    KHÔNG ném lỗi khi thiếu: sổ hàng hoàn vẫn dùng được cho dòng lập tay (hàng
    date siêu thị trả, không đi qua sự cố vận chuyển nào). Chỉ ô "chưa vào sổ"
    là tắt, và màn hình phải NÓI RÕ vì sao nó tắt — một ô trống không lời giải
    thích thì người dùng đọc thành "không còn việc".
    """
    return bool(frappe.db.table_exists(SU_CO))


def _sc_col(field, alias="sc"):
    """`sc.<field>` nếu bảng sự cố có cột đó, không thì `NULL`.

    Bản `vanchuyen` cũ hơn bản vá VC-HH chưa có nhóm hàng-về. Hỏi trước vẫn rẻ
    hơn một câu SQL gãy giữa màn hình đang chạy, và rẻ hơn nhiều so với việc bắt
    người dùng đoán rằng hai app phải nâng cấp cùng lúc.
    """
    return f"{alias}.`{field}`" if frappe.db.has_column(SU_CO, field) else "NULL"


def _si_col(field, alias="si"):
    return f"{alias}.`{field}`" if frappe.db.has_column("Sales Invoice", field) else "NULL"


def _chain_filter(chain, params, alias="si"):
    """Mệnh đề lọc CHUỖI — dùng chung MỘT quy tắc với cả app.

    Chuỗi rỗng/không khai khách nào thì `_customer_in_clause` trả `1 = 0`, tức
    KHÔNG GÌ CẢ. Bỏ qua bộ lọc khi rỗng là màn "chuỗi X" hiện hóa đơn của mọi
    chuỗi — lỗi đã xảy ra thật một lần rồi.
    """
    if not chain:
        return "1 = 1"
    return _customer_in_clause(chain_customers(chain), params, prefix="hh", alias=alias)


# ═══════════════════════════════════════════════════════════════════════════
# ĐỌC PHIẾU SỰ CỐ BÊN `vanchuyen` — CHỈ ĐỌC
# ═══════════════════════════════════════════════════════════════════════════

def _su_co_rows(names):
    """{tên phiếu sự cố: bản ghi SỐNG}. Site chưa có app thì trả {} — không nổ."""
    if not names or not _has_vanchuyen():
        return {}
    rows = frappe.db.sql(f"""
        SELECT sc.name, sc.sales_invoice, sc.loai_su_co, sc.trang_thai,
               sc.ngay_phat_sinh, sc.creation,
               {_sc_col("huong_xu_ly")} AS huong_xu_ly,
               {_sc_col("po")} AS po,
               {_sc_col("tinh")} AS tinh,
               {_sc_col("mo_ta")} AS mo_ta,
               {_sc_col("hang_ve_trang_thai")} AS hang_ve_trang_thai,
               {_sc_col("ngay_du_kien_ve")} AS ngay_du_kien_ve,
               {_sc_col("ngay_hang_ve")} AS ngay_hang_ve,
               {_sc_col("stock_entry")} AS stock_entry,
               {_sc_col("tong_mat_duong")} AS tong_mat_duong,
               {_sc_col("boi_thuong_trang_thai")} AS boi_thuong_trang_thai,
               {_sc_col("boi_thuong_so_tien")} AS boi_thuong_so_tien
        FROM `tab{SU_CO}` sc
        WHERE sc.name IN %(names)s
    """, {"names": tuple(names)}, as_dict=True)
    return {r.name: r for r in rows}


def _su_co_items(su_co):
    """Bảng mã hàng của một phiếu sự cố — BA số lượng, đọc thẳng bên kia.

    KHÔNG chép sang app này (MT2-AM): hai trong ba số lượng chỉ điều phối và
    thủ kho biết, mà họ không vào được portal kế toán. Chép là bắt kế toán gõ
    lại số của người khác, và việc gõ lại thì hai tuần nữa không ai gõ.
    """
    if not su_co or not frappe.db.table_exists(SU_CO_ITEM):
        return []
    return frappe.db.sql(f"""
        SELECT it.item_code, it.item_name, it.uom,
               it.sl_tra, it.sl_ve, it.sl_nhap_lai, it.sl_hong,
               it.don_gia, it.tien_mat_duong
        FROM `tab{SU_CO_ITEM}` it
        WHERE it.parent = %(p)s AND it.parenttype = %(t)s
        ORDER BY it.idx
    """, {"p": su_co, "t": SU_CO}, as_dict=True)


# ═══════════════════════════════════════════════════════════════════════════
# CHỨNG TỪ PHÍA SIÊU THỊ — ĐỌC, KHÔNG CỘNG (MT2-AK)
# ═══════════════════════════════════════════════════════════════════════════

def _chung_tu_sieu_thi(credit_notes):
    """{phiếu trả: số hóa đơn siêu thị đã xuất} — lấy từ dòng `Ghi giảm` bảng kê.

    ⚠ HÀM NÀY KHÔNG ĐƯỢC CỘNG TIỀN, và đó không phải chuyện văn phong.

    Hàng trả đã được trừ khỏi công nợ ĐÚNG MỘT LẦN bằng chính phiếu trả
    (`mt._returns_join`). Dòng ghi giảm trên bảng kê nói về CÙNG lần trả hàng
    đó; cho nó vào một phép cộng tiền là trừ lần thứ hai. `return_doc_check`
    quét mọi hàm trong `api/` và bắt bất kỳ hàm nào vừa nhắc `return_invoice`
    vừa mang dấu hiệu cộng tiền — kể cả hàm viết sau này.

    Nên ở đây chỉ có `inv_no`. Không `SUM(`, không cột tiền nào.
    """
    if not credit_notes:
        return {}
    if not frappe.db.table_exists("MT Payment Advice Line"):
        return {}
    if not frappe.db.has_column("MT Payment Advice Line", "return_invoice"):
        return {}
    rows = frappe.db.sql("""
        SELECT l.return_invoice AS cn, l.inv_no, l.parent AS advice
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.return_invoice IN %(cns)s
          AND a.docstatus < 2
    """, {"cns": tuple(credit_notes)}, as_dict=True)
    out = {}
    for r in rows:
        if r.cn and r.cn not in out:
            out[r.cn] = {"inv_no": cstr(r.inv_no or ""), "advice": cstr(r.advice or "")}
    return out


def _tuoi(ngay, as_of=None):
    """Tuổi việc, tính TỪ NGÀY XẢY RA.

    Không tính từ ngày nhập phiếu: nhà xe báo trễ vài ngày là thường, và tính
    từ ngày nhập giấu đi đúng phần chậm trễ mà màn hình này sinh ra để lộ.
    Không có ngày xảy ra thì trả None — "chưa biết" không được hiển thị thành 0.
    """
    if not ngay:
        return None
    return (getdate(as_of or nowdate()) - getdate(ngay)).days


# ═══════════════════════════════════════════════════════════════════════════
# DANH SÁCH
# ═══════════════════════════════════════════════════════════════════════════

def _counts(company, chain, params_base):
    """Đếm CẢ BỐN ô, luôn luôn — kể cả ô đang không xem.

    Hiện đúng ô đang mở thì kế toán không biết còn gì ở ô khác, và cái ô người
    ta không biết là ô không ai mở.
    """
    p = dict(params_base)
    where = ["h.company = %(company)s", _chain_filter(chain, p, alias="si")]
    rows = frappe.db.sql(f"""
        SELECT h.trang_thai_giay AS tt, COUNT(*) AS n
        FROM `tab{DOCTYPE}` h
        INNER JOIN `tabSales Invoice` si ON si.name = h.sales_invoice
        WHERE {" AND ".join(where)}
        GROUP BY h.trang_thai_giay
    """, p, as_dict=True)
    by = {cstr(r.tt or ""): cint(r.n) for r in rows}
    out = {
        B_CHUA_PHIEU_TRA: by.get(GIAY_CHUA_TRA, 0),
        B_CHUA_CHUNG_TU: by.get(GIAY_CHUA_CT, 0),
        B_XONG: by.get(GIAY_XONG, 0),
        B_CHUA_VAO_SO: _count_ung_vien(company, chain),
    }
    out[B_CHO_XU_LY] = out[B_CHUA_PHIEU_TRA] + out[B_CHUA_CHUNG_TU]
    return out


def _ung_vien_sql(company, chain, params, search=None):
    """Phiếu sự cố trên hóa đơn MT mà sổ này CHƯA có dòng nào.

    `NOT EXISTS` theo `su_co`, KHÔNG theo `sales_invoice`: một hóa đơn có thể có
    hai lần hàng về, và loại theo hóa đơn thì lần thứ hai biến mất khỏi danh
    sách ngay khi lần thứ nhất được nhận — đúng lần chưa ai làm gì.
    """
    params["company"] = company
    where = [
        "si.company = %(company)s",
        # Chỉ hóa đơn ĐÃ GHI SỔ. Hóa đơn nháp chưa là công nợ, hóa đơn đã hủy
        # thì không còn gì để điều chỉnh.
        "si.docstatus = 1",
        _mt_clause(params),
        _chain_filter(chain, params, alias="si"),
        f"NOT EXISTS (SELECT 1 FROM `tab{DOCTYPE}` h WHERE h.su_co = sc.name)",
    ]
    if cstr(search).strip():
        params["q"] = "%" + cstr(search).strip() + "%"
        where.append("(sc.name LIKE %(q)s OR sc.sales_invoice LIKE %(q)s "
                     "OR si.customer_name LIKE %(q)s)")
    return " AND ".join(where)


def _count_ung_vien(company, chain):
    if not _has_vanchuyen():
        return 0
    p = {}
    w = _ung_vien_sql(company, chain, p)
    return cint(frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tab{SU_CO}` sc
        INNER JOIN `tabSales Invoice` si ON si.name = sc.sales_invoice
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {w}
    """, p)[0][0])


def _ung_vien_rows(company, chain, search, limit, offset):
    p = {"limit": limit, "offset": offset}
    w = _ung_vien_sql(company, chain, p, search)
    total = cint(frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tab{SU_CO}` sc
        INNER JOIN `tabSales Invoice` si ON si.name = sc.sales_invoice
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {w}
    """, p)[0][0])
    rows = frappe.db.sql(f"""
        SELECT sc.name AS su_co, sc.sales_invoice, sc.loai_su_co, sc.trang_thai,
               sc.ngay_phat_sinh AS ngay_xay_ra, DATE(sc.creation) AS ngay_bao,
               {_sc_col("huong_xu_ly")} AS huong_xu_ly,
               {_sc_col("hang_ve_trang_thai")} AS trang_thai_hang,
               {_sc_col("ngay_hang_ve")} AS ngay_hang_ve,
               {_sc_col("tong_mat_duong")} AS tong_mat_duong,
               si.customer, si.customer_name, si.posting_date, si.grand_total,
               {po_column()} AS po_no
        FROM `tab{SU_CO}` sc
        INNER JOIN `tabSales Invoice` si ON si.name = sc.sales_invoice
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {w}
        ORDER BY sc.ngay_phat_sinh ASC, sc.name ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return total, rows


def _so_rows(company, chain, statuses, search, limit, offset):
    p = {"company": company, "limit": limit, "offset": offset}
    where = ["h.company = %(company)s", _chain_filter(chain, p, alias="si")]
    if statuses:
        for i, s in enumerate(statuses):
            p["tt%d" % i] = s
        where.append("h.trang_thai_giay IN (%s)"
                     % ", ".join("%%(tt%d)s" % i for i in range(len(statuses))))
    if cstr(search).strip():
        p["q"] = "%" + cstr(search).strip() + "%"
        where.append("(h.name LIKE %(q)s OR h.sales_invoice LIKE %(q)s "
                     "OR h.credit_note LIKE %(q)s OR h.su_co LIKE %(q)s "
                     "OR h.customer_name LIKE %(q)s OR h.po_no LIKE %(q)s)")
    w = " AND ".join(where)

    total = cint(frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tab{DOCTYPE}` h
        INNER JOIN `tabSales Invoice` si ON si.name = h.sales_invoice
        WHERE {w}
    """, p)[0][0])
    rows = frappe.db.sql(f"""
        SELECT h.name, h.su_co, h.sales_invoice, h.customer, h.customer_name,
               h.chain, h.po_no, h.ngay_xay_ra, h.ngay_bao,
               h.loai_su_co, h.huong_xu_ly, h.chung_tu_can, h.ghi_chu,
               h.trang_thai_giay, h.credit_note, h.misa_no, h.ngay_xong_giay,
               h.trang_thai_hang, h.ngay_hang_ve,
               si.posting_date, si.grand_total,
               {_si_col("custom_misa_relation", "cn")} AS cn_misa_relation,
               {_si_col(SI_NO_FIELD, "cn")} AS cn_misa_no,
               ABS(IFNULL(cn.grand_total, 0)) AS cn_amount,
               cn.posting_date AS cn_date
        FROM `tab{DOCTYPE}` h
        INNER JOIN `tabSales Invoice` si ON si.name = h.sales_invoice
        LEFT JOIN `tabSales Invoice` cn ON cn.name = h.credit_note
        WHERE {w}
        ORDER BY (h.ngay_xay_ra IS NULL), h.ngay_xay_ra ASC, h.name ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """, p, as_dict=True)
    return total, rows


def _decorate(rows):
    """Gắn tuổi việc · bản SỐNG bên vanchuyen · chứng từ phía siêu thị."""
    live = _su_co_rows([r.su_co for r in rows if r.su_co])
    theirs = _chung_tu_sieu_thi([r.credit_note for r in rows if r.credit_note])
    out = []
    for r in rows:
        d = dict(r)
        sc = live.get(cstr(r.su_co or ""))
        # ĐỌC SỐNG: giá trị hiện ra là giá trị bên điều hành ĐANG khai, không
        # phải bản chép lúc nhận. Bản chép chỉ dùng khi phiếu sự cố không còn.
        changed = []
        if sc:
            for mine, theirs_field in COPIED:
                new = sc.get(theirs_field)
                old = d.get(mine)
                if mine in DRIFT_WATCH and cstr(old or "") != cstr(new or ""):
                    changed.append({"field": mine, "cu": cstr(old or ""),
                                    "moi": cstr(new or "")})
                if new not in (None, ""):
                    d[mine] = new
            d["su_co_trang_thai"] = cstr(sc.get("trang_thai") or "")
            d["stock_entry"] = cstr(sc.get("stock_entry") or "")
            d["tong_mat_duong"] = flt(sc.get("tong_mat_duong"))
            d["su_co_con"] = True
            # Có phiếu sự cố còn sống -> hai ô hàng vật lý do bên đó giữ.
            d["khoa_hang"] = True
        else:
            # Phiếu sự cố đã bị xóa (hoặc site chưa cài app). KHÔNG xóa dòng sổ:
            # việc giấy tờ vẫn là việc, và mất phiếu nguồn không làm hóa đơn
            # điều chỉnh tự xuất ra.
            d["su_co_trang_thai"] = ""
            d["stock_entry"] = ""
            d["tong_mat_duong"] = 0.0
            d["su_co_con"] = bool(not r.su_co)
            d["khoa_hang"] = False
        d["da_doi"] = changed
        d["tuoi"] = _tuoi(d.get("ngay_xay_ra"))
        cn = cstr(r.credit_note or "")
        t = theirs.get(cn) if cn else None
        d["chung_tu_sieu_thi"] = t or None
        d["grand_total"] = flt(r.get("grand_total"))
        d["cn_amount"] = flt(r.get("cn_amount"))
        out.append(d)
    return out


@frappe.whitelist()
def list_hoan(company=None, bucket=None, chain=None, search=None,
              page=1, page_size=50):
    """Hàng đợi hàng hoàn. Một lần gọi vẽ đủ cả bốn ô đếm + danh sách ô đang xem."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)
    bucket = bucket if bucket in BUCKETS else B_CHO_XU_LY
    page, page_size, offset = _page(page, min(cint(page_size) or 50, MAX_ROWS))

    counts = _counts(company, chain, {"company": company})
    vc = _has_vanchuyen()

    note = ""
    if bucket == B_CHUA_VAO_SO and not vc:
        # KHÔNG ném lỗi và cũng không trả một danh sách rỗng câm: ô trống không
        # lời giải thích thì người dùng đọc thành "không còn việc".
        total, rows = 0, []
        note = _(
            "Site này chưa cài app `vanchuyen` (thiếu bảng {0}), nên không có phiếu sự "
            "cố nào để liệt kê. Sổ hàng hoàn vẫn dùng được: lập dòng trực tiếp từ hóa đơn."
        ).format(SU_CO)
    elif bucket == B_CHUA_VAO_SO:
        total, raw = _ung_vien_rows(company, chain, search, page_size, offset)
        rows = []
        for r in raw:
            d = dict(r)
            d["tuoi"] = _tuoi(r.ngay_xay_ra)
            d["grand_total"] = flt(r.grand_total)
            d["tong_mat_duong"] = flt(r.tong_mat_duong)
            rows.append(d)
    else:
        statuses = {
            B_CHUA_PHIEU_TRA: [GIAY_CHUA_TRA],
            B_CHUA_CHUNG_TU: [GIAY_CHUA_CT],
            B_CHO_XU_LY: [GIAY_CHUA_TRA, GIAY_CHUA_CT],
            B_XONG: [GIAY_XONG],
        }[bucket]
        total, raw = _so_rows(company, chain, statuses, search, page_size, offset)
        rows = _decorate(raw)

    return {
        "bucket": bucket,
        "rows": rows,
        "total": total,
        "page": page,
        "pages": max(1, -(-total // page_size)),
        "page_size": page_size,
        "counts": counts,
        "vanchuyen": vc,
        "chain": chain or "",
        "search": cstr(search or ""),
        "chung_tu_options": list(CHUNG_TU_OPTIONS),
        "trang_thai_hang_options": list(TRANG_THAI_HANG),
        "can_manage": is_chief(),
        "note": note,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CHI TIẾT
# ═══════════════════════════════════════════════════════════════════════════

def _le_cua_chuoi(chain):
    """Chuỗi này TRƯỚC GIỜ dùng chứng từ gì — ĐẾM TRÊN CHỨNG TỪ CÓ THẬT.

    Không phải bảng gợi ý gõ tay. `chung_tu_can` là quyết định của kế toán
    (MT2-AL: "app không đoán, kế toán chốt theo chuỗi"), nhưng "chuỗi này 12/14
    lần dùng hóa đơn thay thế" là một phép đếm trên chứng từ đã phát hành, không
    phải một phỏng đoán — nói ra được mà không tự điền vào ô.

    Trả [] khi site chưa có ô quan hệ MISA: chưa biết thì không bịa.
    """
    if not chain or not frappe.db.has_column("Sales Invoice", "custom_misa_relation"):
        return []
    names = chain_customers(chain)
    if not names:
        return []
    p = {}
    cus = _customer_in_clause(names, p, prefix="lc", alias="r")
    rows = frappe.db.sql(f"""
        SELECT r.custom_misa_relation AS quan_he, COUNT(*) AS n
        FROM `tabSales Invoice` r
        WHERE r.is_return = 1 AND r.docstatus = 1
          AND IFNULL(r.custom_misa_relation, '') != ''
          AND {cus}
        GROUP BY r.custom_misa_relation
        ORDER BY n DESC
    """, p, as_dict=True)
    return [{"quan_he": cstr(r.quan_he), "n": cint(r.n)} for r in rows]


def _phieu_tra_ung_vien(sales_invoice, current=None):
    """Phiếu trả ĐÃ GHI SỔ của hóa đơn gốc — để kế toán CHỌN, không gõ docname.

    Kèm cờ `da_dung`: phiếu đã được một dòng sổ khác nhận rồi. Không giấu nó đi
    — một hóa đơn có thể có hai lần hàng về và hai phiếu trả, nên thấy phiếu nào
    đã dùng là thông tin, còn giấu là mời chọn nhầm rồi tự hỏi vì sao thiếu.
    """
    if not sales_invoice:
        return []
    rows = frappe.db.sql(f"""
        SELECT r.name, r.posting_date, ABS(r.grand_total) AS amount,
               {_si_col("custom_misa_relation", "r")} AS misa_relation,
               {_si_col(SI_NO_FIELD, "r")} AS misa_no,
               {_si_col("custom_misa_status", "r")} AS misa_status
        FROM `tabSales Invoice` r
        WHERE r.return_against = %(si)s AND r.docstatus = 1
        ORDER BY r.posting_date, r.name
    """, {"si": sales_invoice}, as_dict=True)
    if not rows:
        return []
    used = {
        d[0]: d[1] for d in frappe.db.sql(f"""
            SELECT h.credit_note, h.name FROM `tab{DOCTYPE}` h
            WHERE h.credit_note IN %(cns)s
        """, {"cns": tuple(r.name for r in rows)})
    }
    out = []
    for r in rows:
        boi = used.get(r.name)
        out.append({
            "name": r.name,
            "posting_date": cstr(r.posting_date or ""),
            "amount": flt(r.amount),
            "misa_relation": cstr(r.misa_relation or ""),
            "misa_no": cstr(r.misa_no or ""),
            "misa_status": cstr(r.misa_status or ""),
            "da_dung": bool(boi and boi != current),
            "dung_o": cstr(boi or "") if boi and boi != current else "",
        })
    return out


@frappe.whitelist()
def get_hoan(name, company=None):
    """Chi tiết một dòng sổ: bảng mã hàng bên vanchuyen + ứng viên phiếu trả."""
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    row = frappe.db.get_value(DOCTYPE, name, "*", as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy dòng sổ {0}.").format(name))
    if row.company != company:
        frappe.throw(_("Dòng sổ {0} không thuộc công ty {1}.").format(name, company),
                     frappe.PermissionError)

    d = _decorate([frappe._dict(row)])[0]
    d["items"] = _su_co_items(row.su_co)
    # `_su_co_items` chỉ có bảng mã hàng; `tong_mat_duong` đã do `_decorate` đọc
    # sống từ phiếu sự cố, không cộng lại ở đây — cộng lại là hai nguồn.
    d["phieu_tra_ung_vien"] = _phieu_tra_ung_vien(row.sales_invoice, row.credit_note)
    d["le_cua_chuoi"] = _le_cua_chuoi(row.chain)
    d["chung_tu_options"] = list(CHUNG_TU_OPTIONS)
    d["trang_thai_hang_options"] = list(TRANG_THAI_HANG)
    d["can_manage"] = is_chief()
    # Hai kịch bản trả hàng đi hai đường chứng từ, và app KHÔNG đoán được cái
    # nào là cái nào — chỉ NGƯỜI biết hàng móp hay hàng date (MT2-AI).
    d["chung_tu_note"] = _(
        "· HÀNG MÓP TRONG VẬN CHUYỂN — siêu thị chỉ nhận theo thực nhận, tức hóa đơn "
        "gốc ghi sai ngay từ đầu. Chứng từ đúng: HÓA ĐƠN THAY THẾ.\n"
        "· HÀNG DATE / THỜI VỤ TRẢ LẠI — siêu thị đã nhận rồi mới trả. Đây là giao dịch "
        "MỚI, không phải sửa tờ cũ: siêu thị xuất hóa đơn trả cho mình, HOẶC mình xuất "
        "HÓA ĐƠN ĐIỀU CHỈNH GIẢM.\n"
        "· GIAO LẠI NGUYÊN LÔ — hóa đơn gốc vẫn đúng, KHÔNG cần chứng từ nào và cũng "
        "không cần phiếu trả. Chọn 'Không cần chứng từ' để đóng việc.\n"
        "Khi CHÍNH SIÊU THỊ xuất hóa đơn thì mình không có hóa đơn MISA nào cho phiếu "
        "trả — chứng từ về theo BẢNG KÊ THANH TOÁN, ở dòng Ghi giảm đã trỏ về phiếu trả.")
    return d


# ═══════════════════════════════════════════════════════════════════════════
# GHI — CHỈ TRÊN BẢNG CỦA APP NÀY
# ═══════════════════════════════════════════════════════════════════════════

def _stamp_from_si(doc, sales_invoice, chain_map=None):
    """Chép khách · chuỗi · số PO từ hóa đơn gốc."""
    si = frappe.db.get_value(
        "Sales Invoice", sales_invoice,
        ["customer", "customer_name", "company", "docstatus"], as_dict=True)
    if not si:
        frappe.throw(_("Không tìm thấy hóa đơn {0}.").format(sales_invoice))
    if cint(si.docstatus) != 1:
        frappe.throw(_(
            "Hóa đơn {0} chưa ghi sổ (hoặc đã hủy). Chưa ghi sổ thì chưa là công nợ, "
            "và cũng chưa có gì để điều chỉnh."
        ).format(sales_invoice))
    doc.customer = si.customer
    doc.customer_name = si.customer_name
    mapping = chain_map if chain_map is not None else _customer_chain_map()[0]
    doc.chain = mapping.get(si.customer) or ""
    # Tên ô PO đi qua `mt.SI_PO_FIELD` — MỘT nguồn cho cả app (MT2-AJ). Gõ lại
    # chuỗi ở đây là bản sao thứ hai của một cái tên đã đổi một lần rồi, và
    # `po_field_check` đếm đúng chỗ này.
    if frappe.db.has_column("Sales Invoice", SI_PO_FIELD):
        doc.po_no = cstr(frappe.db.get_value("Sales Invoice", sales_invoice,
                                             SI_PO_FIELD) or "")
    return si


def _stamp_from_su_co(doc, sc):
    """Chép các cột điều hành sang bản của mình. MỘT bảng khai ở `COPIED`."""
    for mine, theirs in COPIED:
        v = sc.get(theirs)
        if v not in (None, ""):
            doc.set(mine, v)
    if sc.get("creation"):
        doc.ngay_bao = getdate(sc.get("creation"))
    if not doc.po_no and sc.get("po"):
        doc.po_no = cstr(sc.get("po"))
    if sc.get("mo_ta") and not doc.hang_ve_ghi_chu:
        doc.hang_ve_ghi_chu = cstr(sc.get("mo_ta"))


@frappe.whitelist()
def create_hoan(sales_invoice=None, su_co=None, chung_tu_can=None, ghi_chu=None,
                ngay_xay_ra=None, company=None):
    """Mở một dòng sổ — HAI CỬA, một hàm.

    · từ phiếu sự cố (`su_co`) — hàng móp/thiếu trên đường, điều hành đã ghi;
    · thẳng từ hóa đơn (`sales_invoice`) — hàng date siêu thị trả, thường KHÔNG
      đi qua sự cố vận chuyển nào.

    Một hàm chứ không hai, vì mỗi cửa là một chỗ nữa để quên gọi guard, quên
    kiểm công ty, quên chép chuỗi. Hai cửa lệch nhau thì cửa ít dùng hơn là cửa
    sai.

    Truyền luôn `chung_tu_can = "Không cần chứng từ"` là cách "bỏ qua" một ứng
    viên: dòng vào sổ và ra khỏi hàng đợi ngay, nhưng có dấu vết ai kết luận và
    lúc nào.
    """
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    su_co = cstr(su_co or "").strip()
    sales_invoice = cstr(sales_invoice or "").strip()
    if not su_co and not sales_invoice:
        frappe.throw(_("Phải có phiếu sự cố hoặc hóa đơn gốc."))

    sc = None
    if su_co:
        if not _has_vanchuyen():
            frappe.throw(_(
                "Site này chưa cài app `vanchuyen`, không đọc được phiếu sự cố {0}."
            ).format(su_co))
        sc = _su_co_rows([su_co]).get(su_co)
        if not sc:
            frappe.throw(_("Không tìm thấy phiếu sự cố {0}.").format(su_co))
        if not sales_invoice:
            sales_invoice = cstr(sc.get("sales_invoice") or "")
        elif sales_invoice != cstr(sc.get("sales_invoice") or ""):
            # Nhận phiếu sự cố của hóa đơn A vào dòng ghi hóa đơn B là nối sai
            # việc với sai chứng từ, và sau đó mọi con số trên dòng đều nói về
            # hai hóa đơn khác nhau.
            frappe.throw(_(
                "Phiếu sự cố {0} thuộc hóa đơn {1}, không phải {2}."
            ).format(su_co, sc.get("sales_invoice"), sales_invoice))
        if not sales_invoice:
            frappe.throw(_("Phiếu sự cố {0} chưa gắn hóa đơn nào.").format(su_co))

    if chung_tu_can and chung_tu_can not in CHUNG_TU_OPTIONS:
        frappe.throw(_("Chứng từ cần làm không hợp lệ: {0}").format(chung_tu_can))

    doc = frappe.new_doc(DOCTYPE)
    doc.company = company
    doc.sales_invoice = sales_invoice
    doc.su_co = su_co or None
    si = _stamp_from_si(doc, sales_invoice)
    if si.company != company:
        frappe.throw(_("Hóa đơn {0} thuộc công ty {1}.").format(sales_invoice, si.company),
                     frappe.PermissionError)
    if sc:
        _stamp_from_su_co(doc, sc)
    if ngay_xay_ra:
        doc.ngay_xay_ra = getdate(ngay_xay_ra)
    if not doc.ngay_xay_ra:
        # Không có ngày xảy ra thì không tính được tuổi việc. Lấy ngày hóa đơn
        # làm mốc là bịa; để trống và nói "chưa biết" là thật.
        doc.ngay_xay_ra = None
    if chung_tu_can:
        doc.chung_tu_can = chung_tu_can
    if ghi_chu:
        doc.ghi_chu = cstr(ghi_chu)
    doc.insert()
    return {"name": doc.name, "trang_thai_giay": doc.trang_thai_giay}


@frappe.whitelist()
def save_hoan(name, chung_tu_can=None, credit_note=None, ghi_chu=None,
              trang_thai_hang=None, ngay_hang_ve=None, ngay_xay_ra=None,
              company=None):
    """Kế toán chốt: chứng từ cần làm · phiếu trả · ghi chú.

    Đi qua `Document.save()` chứ không `db.set_value`: trạng thái giấy tờ là
    MÁY SUY trong `validate()`, và ghi thẳng vào cột là bỏ qua đúng phần suy
    đó — dòng đứng nguyên "Chưa lập phiếu trả" trong khi phiếu trả đã nối.
    """
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    doc = frappe.get_doc(DOCTYPE, name)
    if doc.company != company:
        frappe.throw(_("Dòng sổ {0} không thuộc công ty {1}.").format(name, company),
                     frappe.PermissionError)

    if chung_tu_can is not None:
        chung_tu_can = cstr(chung_tu_can).strip()
        if chung_tu_can and chung_tu_can not in CHUNG_TU_OPTIONS:
            frappe.throw(_("Chứng từ cần làm không hợp lệ: {0}").format(chung_tu_can))
        doc.chung_tu_can = chung_tu_can or None
    if credit_note is not None:
        doc.credit_note = cstr(credit_note).strip() or None
        # Gỡ phiếu trả thì số chứng từ cũ phải đi theo. Giữ lại là dòng hiện
        # "đã đủ chứng từ" nhờ một số hóa đơn không còn thuộc về nó.
        if not doc.credit_note:
            doc.misa_no = None
    if ghi_chu is not None:
        doc.ghi_chu = cstr(ghi_chu)
    # HÀNG VẬT LÝ CHỈ CÓ MỘT NGƯỜI GHI, và người đó ở bên `vanchuyen`.
    #
    # Dòng có phiếu sự cố thì danh sách ĐỌC SỐNG `hang_ve_trang_thai` bên đó —
    # cho sửa ở đây là kế toán gõ một giá trị rồi thấy nó lặng lẽ quay về giá
    # trị cũ ở lần mở sau, mà không có gì nói vì sao. Thà chặn kèm câu chỉ chỗ
    # sửa còn hơn nhận rồi nuốt.
    #
    # Dòng LẬP TAY (hàng date siêu thị trả, không qua chuyến xe nào) không có
    # ai bên kia ghi hộ, nên ở đó kế toán mới là người giữ hai ô này.
    khoa_hang = bool(doc.su_co) and bool(_su_co_rows([doc.su_co]).get(doc.su_co))
    if khoa_hang and (trang_thai_hang is not None or ngay_hang_ve is not None):
        frappe.throw(_(
            "Trạng thái hàng vật lý của dòng này do phiếu sự cố {0} bên app vận chuyển "
            "giữ — sửa ở đây thì lần mở sau nó quay về giá trị bên đó. Sửa trên phiếu "
            "sự cố, màn này đọc thẳng sang."
        ).format(doc.su_co))
    if not khoa_hang:
        if trang_thai_hang is not None:
            trang_thai_hang = cstr(trang_thai_hang).strip()
            if trang_thai_hang and trang_thai_hang not in TRANG_THAI_HANG:
                frappe.throw(_("Trạng thái hàng không hợp lệ: {0}").format(trang_thai_hang))
            doc.trang_thai_hang = trang_thai_hang or None
        if ngay_hang_ve is not None:
            doc.ngay_hang_ve = getdate(ngay_hang_ve) if ngay_hang_ve else None
    if ngay_xay_ra is not None:
        doc.ngay_xay_ra = getdate(ngay_xay_ra) if ngay_xay_ra else None

    doc.save()
    return {"name": doc.name, "trang_thai_giay": doc.trang_thai_giay,
            "misa_no": cstr(doc.misa_no or "")}


@frappe.whitelist()
def sync_hoan(name, company=None):
    """Chép lại các cột điều hành từ phiếu sự cố — NGƯỜI bấm, không máy tự ghi.

    Danh sách đã đọc sống rồi, nên hàm này không phải để màn hình đúng: nó để
    bản chép trên Desk và trên bản in đúng theo. Tự ghi mỗi lần đọc là biến một
    màn hình xem thành một màn hình ghi, và mọi lượt mở đều đụng vào chứng từ.
    """
    guard_mt()
    _require_tables()
    _tables()
    company = _company(company)

    doc = frappe.get_doc(DOCTYPE, name)
    if doc.company != company:
        frappe.throw(_("Dòng sổ {0} không thuộc công ty {1}.").format(name, company),
                     frappe.PermissionError)
    if not doc.su_co:
        frappe.throw(_("Dòng này không gắn phiếu sự cố nào để chép lại."))
    sc = _su_co_rows([doc.su_co]).get(doc.su_co)
    if not sc:
        frappe.throw(_(
            "Không còn phiếu sự cố {0} bên `vanchuyen` (đã xóa, hoặc site chưa cài app). "
            "Dòng sổ giữ nguyên bản chép cũ."
        ).format(doc.su_co))
    _stamp_from_su_co(doc, sc)
    doc.save()
    return {"name": doc.name, "trang_thai_giay": doc.trang_thai_giay}


@frappe.whitelist()
def delete_hoan(name, company=None):
    """Xóa một dòng mở nhầm. CHỈ kế toán trưởng.

    Không dùng để "đóng việc": việc đã xử xong thì chốt `chung_tu_can` rồi để
    dòng ở ô `xong` — xóa là mất luôn dấu vết ai kết luận gì.
    """
    guard_manager()
    _tables()
    company = _company(company)
    doc = frappe.get_doc(DOCTYPE, name)
    if doc.company != company:
        frappe.throw(_("Dòng sổ {0} không thuộc công ty {1}.").format(name, company),
                     frappe.PermissionError)
    if doc.credit_note:
        frappe.throw(_(
            "Dòng {0} đã nối phiếu trả {1}. Gỡ phiếu trả trước khi xóa — xóa thẳng là "
            "mất dấu vết việc đã làm."
        ).format(name, doc.credit_note))
    frappe.delete_doc(DOCTYPE, name)
    return {"deleted": name}


# ═══════════════════════════════════════════════════════════════════════════
# ĐẾM CHO BẢNG CHUỖI (`mt_hub.get_board`)
# ═══════════════════════════════════════════════════════════════════════════

def board_counts(company, chain_map=None):
    """{chuỗi: {việc hàng hoàn còn lại}} — cho bàn làm việc của từng chuỗi.

    Gom chuỗi qua `_customer_chain_map`, KHÔNG qua cột `chain` đã chép trên
    dòng sổ. Kế toán đổi chuỗi của một khách thì bản chép trên dòng cũ đứng
    nguyên, và từ đó thẻ chuỗi đếm một đằng còn danh sách bấm vào lọc một nẻo —
    hai con số về cùng một tập, lệch nhau, không ai biết tin cái nào.

    Hàm này KHÔNG ném lỗi khi site chưa migrate: bảng chuỗi phải mở được cả khi
    sổ hàng hoàn chưa cài. Trả {} thì mọi chuỗi hiện 0 việc hàng hoàn — đúng,
    vì chưa có sổ thì chưa có việc nào được ghi.
    """
    out = {}
    if not frappe.db.table_exists(DOCTYPE):
        return out
    mapping = chain_map if chain_map is not None else _customer_chain_map()[0]

    def bucket(ch):
        return out.setdefault(cstr(ch or ""), {
            "hoan_chua_tra": 0, "hoan_chua_ct": 0, "hoan_chua_vao_so": 0})

    rows = frappe.db.sql(f"""
        SELECT h.customer, h.trang_thai_giay AS tt, COUNT(*) AS n
        FROM `tab{DOCTYPE}` h
        WHERE h.company = %(company)s
          AND h.trang_thai_giay IN (%(t1)s, %(t2)s)
        GROUP BY h.customer, h.trang_thai_giay
    """, {"company": company, "t1": GIAY_CHUA_TRA, "t2": GIAY_CHUA_CT}, as_dict=True)
    for r in rows:
        b = bucket(mapping.get(r.customer))
        key = "hoan_chua_tra" if r.tt == GIAY_CHUA_TRA else "hoan_chua_ct"
        b[key] += cint(r.n)

    if _has_vanchuyen():
        p = {"company": company}
        cand = frappe.db.sql(f"""
            SELECT si.customer, COUNT(*) AS n
            FROM `tab{SU_CO}` sc
            INNER JOIN `tabSales Invoice` si ON si.name = sc.sales_invoice
            INNER JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.company = %(company)s AND si.docstatus = 1
              AND {_mt_clause(p)}
              AND NOT EXISTS (SELECT 1 FROM `tab{DOCTYPE}` h WHERE h.su_co = sc.name)
            GROUP BY si.customer
        """, p, as_dict=True)
        for r in cand:
            bucket(mapping.get(r.customer))["hoan_chua_vao_so"] += cint(r.n)

    for b in out.values():
        b["hoan_open"] = b["hoan_chua_tra"] + b["hoan_chua_ct"]
    return out
