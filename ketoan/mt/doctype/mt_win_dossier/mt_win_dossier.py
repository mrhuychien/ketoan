"""MT Win Dossier — HỒ SƠ THANH TOÁN nộp cho WinCommerce (§2.2 SOP).

Win chỉ xử lý thanh toán khi nhận đủ bảng kê + file PDF hóa đơn ĐẶT ĐÚNG TÊN.
Sai tên file là hồ sơ bị trả về và cả đợt thanh toán trượt kỳ — nên tên file
được SINH RA ở đây chứ không để kế toán gõ tay.

TÊN FILE — đọc từ mẫu thật `Mẫu bảng kê ghi nhận hồ sơ thanh toán Winmart.xlsx`:

    20260817_2007766_01_PF
    └─YYYYMMDD─┘ └NCC─┘ └NN┘└PF

    YYYYMMDD  ngày nộp hồ sơ
    2007766   mã NCC của Hoàng Giang tại WinCommerce
    01        số thứ tự hồ sơ trong ngày
    _PF       hậu tố cố định

§2.2 SOP viết gọn thành `YYYYMMDD_2007766_<stt>` và ĐÃ BỎ MẤT hậu tố `_PF`.
Mẫu thật có, nên ở đây theo mẫu thật.

MỘT HÓA ĐƠN CHỈ NỘP MỘT LẦN. Nộp trùng là Win trả hồ sơ và mất kỳ thanh toán,
nên `validate()` chặn hóa đơn đã nằm trong hồ sơ khác.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, getdate

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import norm_text

STATUS_DRAFT = "Nháp"
STATUS_SUBMITTED = "Đã nộp"

# Hậu tố cố định của tên file PDF. Đọc từ mẫu thật — không suy từ SOP.
PDF_SUFFIX = "PF"


def build_prefix(submit_date, vendor_code, dossier_no):
    """`20260817_2007766_01_PF`. Một chỗ duy nhất dựng tên file."""
    d = getdate(submit_date)
    return "%s_%s_%02d_%s" % (d.strftime("%Y%m%d"), norm_text(vendor_code),
                              cint(dossier_no) or 1, PDF_SUFFIX)


class MTWinDossier(Document):
    def validate(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.company:
            frappe.throw(_("Hồ sơ phải thuộc một công ty"))
        self.vendor_code = norm_text(self.vendor_code)
        if not self.vendor_code:
            frappe.throw(_("Chưa có mã NCC tại WinCommerce — tên file PDF cần mã này"))
        if not self.submit_date:
            frappe.throw(_("Chưa có ngày nộp hồ sơ — tên file PDF cần ngày này"))

        self.file_prefix = build_prefix(self.submit_date, self.vendor_code, self.dossier_no)

        for row in self.lines or []:
            row.validate()
            # Tên file GIỐNG NHAU trên mọi dòng, đúng như mẫu thật: nó định danh
            # HỒ SƠ (một tệp PDF nộp kèm), không định danh từng hóa đơn.
            row.pdf_name = self.file_prefix

        self._number_lines()
        self._check_duplicate_invoices()
        self._compute_totals()

    def _number_lines(self):
        """Đánh STT 1..N cho dòng CHƯA có, giữ nguyên dòng kế toán đã sửa.

        VÌ SAO không đánh lại tất cả: mẫu thật có STT không theo thứ tự
        (3,4,5,6,9,10,1,2,7,8,11…) — đó là cách Win đánh, và kế toán sửa cho khớp
        thì lần lưu sau hệ thống đánh lại là xóa mất công sức của họ.
        """
        used = {cint(r.stt) for r in self.lines or [] if cint(r.stt)}
        nxt = 1
        for row in self.lines or []:
            if cint(row.stt):
                continue
            while nxt in used:
                nxt += 1
            row.stt = nxt
            used.add(nxt)

    def _check_duplicate_invoices(self):
        """Cùng một hóa đơn KHÔNG được nằm ở hai hồ sơ, và không trùng trong một hồ sơ.

        Nộp trùng là Win trả hồ sơ và cả đợt trượt kỳ thanh toán.
        """
        seen = {}
        for row in self.lines or []:
            key = (cstr(row.inv_series or ""), cstr(row.inv_no or ""))
            if key in seen:
                frappe.throw(_("Hóa đơn {0} {1} xuất hiện hai lần trong hồ sơ (dòng {2} và {3})")
                             .format(row.inv_series or "", row.inv_no, seen[key], row.idx))
            seen[key] = row.idx

        names = sorted({cstr(r.sales_invoice) for r in self.lines or [] if r.sales_invoice})
        if not names:
            return
        dup = frappe.db.sql("""
            SELECT l.sales_invoice, l.parent
            FROM `tabMT Win Dossier Line` l
            INNER JOIN `tabMT Win Dossier` d ON d.name = l.parent
            WHERE l.parenttype = 'MT Win Dossier'
              AND l.parent != %(me)s
              AND l.sales_invoice IN %(names)s
            LIMIT 5
        """, {"me": self.name or "", "names": tuple(names)}, as_dict=True)
        if dup:
            frappe.throw(_(
                "Hóa đơn {0} đã nằm trong hồ sơ {1}. Một hóa đơn chỉ nộp MỘT lần — nộp "
                "trùng là Win trả hồ sơ và cả đợt trượt kỳ thanh toán."
            ).format(dup[0].sales_invoice, dup[0].parent))

    def _compute_totals(self):
        self.total_before_vat = sum(flt(r.amount_before_vat) for r in self.lines or [])
        self.total_vat = sum(flt(r.vat_amount) for r in self.lines or [])
        self.total_amount = flt(self.total_before_vat) + flt(self.total_vat)

        if self.status == STATUS_SUBMITTED and not (self.lines or []):
            frappe.throw(_("Hồ sơ rỗng — không đánh dấu 'Đã nộp' được"))

    def on_trash(self):
        if cstr(self.status) == STATUS_SUBMITTED:
            frappe.throw(_(
                "Hồ sơ {0} đã nộp cho WinCommerce — không xóa được. Nếu nộp nhầm thì ghi "
                "chú lại và lập hồ sơ mới."
            ).format(self.file_prefix or self.name))
