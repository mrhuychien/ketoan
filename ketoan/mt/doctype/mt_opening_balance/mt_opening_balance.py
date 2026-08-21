"""MT Opening Balance — số dư đầu kỳ của MỘT chuỗi, chốt MỘT LẦN.

Đây là bản ghi của việc chuyển từ theo dõi công nợ trên Excel sang phần mềm.
Nó KHÔNG phải chứng từ kế toán: không sinh bút toán, không đụng sổ. Nó là
**danh sách hóa đơn còn nợ tại ngày chốt**, và chính danh sách đó bật một luật
đọc:

    Hóa đơn của chuỗi này, ngày <= `cutover_date`, mà KHÔNG có tên trong danh
    sách  ->  coi như ĐÃ THANH TOÁN trước khi chuyển giao.

Luật đó là cách nghĩ ngược mà kế toán đã chốt: ghi cái CHƯA trả, mặc định phần
còn lại đã trả. Nó thu gọn việc nhập từ 9.497 dòng xuống 1.167 dòng và chỉ phải
tin MỘT cột thay vì hai.

════════════════════════════════════════════════════════════════════════════
HAI CÁI CHẶN, VÌ CẢ HAI ĐỀU LÀ TIỀN TỶ
════════════════════════════════════════════════════════════════════════════

1. **MỘT chuỗi chốt MỘT LẦN.** Nhập lại lần hai là cộng đôi số dư — riêng bộ
   file mẫu là ~5 tỷ. Chặn ở đây, không chỉ chặn trên giao diện.

2. **Chốt khi còn dòng chưa nối được hóa đơn là để hóa đơn thật bị tất toán
   oan.** Một dòng `phải khớp ERPNext` không nối được Sales Invoice nào thì nó
   không giữ được hóa đơn nào lại; đến khi chốt, chính hóa đơn đang còn nợ đó
   rơi vào vế "không có trong danh sách" và biến mất khỏi công nợ. Nên muốn
   chốt thì mọi dòng nhóm đó phải hoặc nối được hóa đơn, hoặc được NGƯỜI đánh
   dấu `Bỏ qua`.

Trạng thái `Nháp` không bật luật gì cả — nhập vào, soi, nối tay, rồi mới chốt.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt

STATUS_DRAFT = "Nháp"
STATUS_FINAL = "Đã chốt"

# Nhóm của một dòng còn nợ — GIỮ ĐÚNG khóa của `ketoan.api.mt_opening`, đừng
# đặt thêm tên mới ở đây.
KIND_NO_INVOICE = "chua_co_hoa_don"
KIND_PRE_GOLIVE = "truoc_golive"
KIND_IN_ERP = "co_hoa_don"

RESOLUTION_SKIP = "Bỏ qua"


class MTOpeningBalance(Document):
    def validate(self):
        self._check_one_per_chain()
        self._check_dates()
        self._recount()
        if self.status == STATUS_FINAL:
            self._check_ready_to_finalize()

    # ── chặn 1: một chuỗi một lần ────────────────────────────────────────
    def _check_one_per_chain(self):
        other = frappe.db.sql("""
            SELECT name FROM `tabMT Opening Balance`
            WHERE company = %(company)s AND chain = %(chain)s AND name != %(name)s
            LIMIT 1
        """, {"company": self.company, "chain": self.chain,
              "name": self.name or "__new__"})
        if other:
            frappe.throw(_(
                "Chuỗi {0} đã có bản số dư đầu kỳ ({1}). Số dư đầu kỳ chỉ nhập MỘT "
                "LẦN cho mỗi chuỗi — nhập lần hai là cộng đôi công nợ. Muốn nhập lại "
                "thì xóa bản cũ trước, và chỉ xóa được khi nó còn ở trạng thái {2}."
            ).format(self.chain, other[0][0], STATUS_DRAFT))

    def _check_dates(self):
        if self.golive_date and self.cutover_date and \
                cstr(self.cutover_date) < cstr(self.golive_date):
            frappe.throw(_(
                "Ngày chốt số dư ({0}) sớm hơn ngày ERPNext bắt đầu có dữ liệu ({1}) — "
                "không có hóa đơn nào trong khoảng đó để tất toán, gần như chắc chắn "
                "gõ nhầm một trong hai ngày."
            ).format(self.cutover_date, self.golive_date))

    def _recount(self):
        """Đếm lại từ chính các dòng — KHÔNG tin con số client gửi lên."""
        lines = self.lines or []
        self.n_rows = len(lines)
        self.n_in_erp = sum(1 for l in lines if l.kind == KIND_IN_ERP)
        self.n_pre_golive = sum(1 for l in lines if l.kind == KIND_PRE_GOLIVE)
        self.n_no_invoice = sum(1 for l in lines if l.kind == KIND_NO_INVOICE)
        self.n_matched = sum(1 for l in lines if cstr(l.sales_invoice))
        self.n_unmatched = len(self.unresolved())

        self.deduction_open = round(sum(flt(d.remaining) for d in (self.deductions or [])), 2)
        # `opening_debt_gross` do tầng đọc file tính trên MỌI dòng (kể cả dòng đã
        # tất toán, giá trị 0) và đã đối chiếu với dòng TỔNG CỘNG in trong file.
        # Không tính lại từ `lines` ở đây: `lines` chỉ giữ dòng CÒN NỢ.
        self.opening_debt = round(flt(self.opening_debt_gross) - flt(self.deduction_open), 2)

        # Đơn ĐÃ GIAO nhưng CHƯA xuất hóa đơn không phải khoản phải thu. File
        # Excel vẫn cộng chúng vào `Số còn nợ` (9 dòng, 46.665.180đ trên file
        # WinCommerce mẫu) — mang nguyên sang là thổi phồng công nợ bằng đúng số
        # đó. Tách ra chứ KHÔNG lặng lẽ trừ khỏi `opening_debt`: con số đó phải
        # giữ nguyên để còn đối chiếu ngược lại dòng TỔNG CỘNG in trong file.
        self.no_invoice_amount = round(
            sum(flt(l.remaining) for l in lines if l.kind == KIND_NO_INVOICE), 2)
        self.debt_carried = round(flt(self.opening_debt) - flt(self.no_invoice_amount), 2)

    def unresolved(self):
        """Dòng 'phải khớp ERPNext' chưa nối hóa đơn và cũng chưa ai bảo bỏ qua."""
        return [l for l in (self.lines or [])
                if l.kind == KIND_IN_ERP
                and not cstr(l.sales_invoice)
                and cstr(l.resolution) != RESOLUTION_SKIP]

    # ── chặn 2: không chốt khi còn dòng treo ─────────────────────────────
    def _check_ready_to_finalize(self):
        left = self.unresolved()
        if left:
            frappe.throw(_(
                "Còn {0} dòng thuộc nhóm 'phải khớp hóa đơn ERPNext' chưa nối được hóa "
                "đơn nào (ví dụ: số {1}). Chốt bây giờ thì đúng những hóa đơn đó rơi "
                "vào vế 'không có trong danh sách' và bị coi là đã thanh toán — mất "
                "tiền thật khỏi công nợ. Nối hóa đơn cho từng dòng, hoặc đánh dấu "
                "'{2}' nếu đã xem và xác nhận không có hóa đơn tương ứng."
            ).format(len(left),
                     ", ".join(cstr(l.inv_no or "(trống)") for l in left[:5]),
                     RESOLUTION_SKIP))

        dup = _duplicate_invoices(self.lines or [])
        if dup:
            frappe.throw(_(
                "Cùng một hóa đơn ERPNext bị nối cho nhiều dòng: {0}. Một hóa đơn chỉ "
                "còn nợ MỘT lần — nối trùng là giữ nhầm hóa đơn và bỏ sót hóa đơn khác."
            ).format(", ".join(dup[:5])))

    def on_trash(self):
        if self.status == STATUS_FINAL:
            frappe.throw(_(
                "Bản số dư đầu kỳ của {0} đã CHỐT — xóa là mọi hóa đơn trước ngày chốt "
                "quay lại rổ công nợ cùng lúc. Mở lại về '{1}' trước nếu thật sự cần."
            ).format(self.chain, STATUS_DRAFT))


def _duplicate_invoices(lines):
    seen, dup = set(), []
    for l in lines:
        si = cstr(l.sales_invoice)
        if not si:
            continue
        if si in seen and si not in dup:
            dup.append(si)
        seen.add(si)
    return dup


def finalized_for(company):
    """Các bản đã CHỐT của công ty này. Đây là nguồn duy nhất của luật tất toán."""
    if not frappe.db.table_exists("MT Opening Balance"):
        return []
    return frappe.db.sql("""
        SELECT name, chain, cutover_date
        FROM `tabMT Opening Balance`
        WHERE company = %(company)s AND status = %(final)s
        ORDER BY chain
    """, {"company": company, "final": STATUS_FINAL}, as_dict=True)
