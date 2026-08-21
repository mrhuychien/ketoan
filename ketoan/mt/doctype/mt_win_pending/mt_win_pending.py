"""MT Win Pending — đợt giao Winmart ĐÃ GIAO nhưng CHƯA XUẤT HÓA ĐƠN.

Winmart chỉ cho xuất hóa đơn SAU KHI họ nhận hàng và có phiếu nhập kho trên hệ
của họ (SOP §2.2). Giữa lúc giao và lúc xuất hóa đơn có một khoảng trống mà
KHÔNG hệ nào theo dõi: ERPNext chưa có hóa đơn, portal chưa có gì, và kế toán
đang phải nhớ bằng file Excel.

Đo trên file theo dõi công nợ thật: 9 đợt giao đang nằm ở khoảng trống này
(46.665.180đ), ghi trong cột 'Ngày gửi chứng từ' là `chưa giao hàng`, không số
hóa đơn, chỉ có số PO. File Excel CỘNG chúng vào cột `Số còn nợ` — nhưng chúng
KHÔNG phải công nợ: chưa xuất hóa đơn thì chưa phải khoản phải thu.

DocType này là chỗ đứng của khoảng trống đó.

════════════════════════════════════════════════════════════════════════════
KHÓA TỰ NHIÊN LÀ SỐ PO
════════════════════════════════════════════════════════════════════════════

Một đợt giao = một PO. Trùng PO trong cùng công ty thì chặn: hai dòng cùng PO
nghĩa là cùng một đợt hàng bị theo dõi hai lần, và tới lúc xuất hóa đơn sẽ có
người xuất hai lần.

════════════════════════════════════════════════════════════════════════════
TIỀN Ở ĐÂY LÀ TIỀN DỰ KIẾN
════════════════════════════════════════════════════════════════════════════

`total_amount` tính theo ĐƠN GIAO. Số thật là số trên PHIẾU NHẬP KHO của Win —
SOP §2.2: lệch số lượng thì xuất hóa đơn theo SỐ THỰC NHẬN, phần chênh làm xuất
trả. Vì vậy `grn_amount` là một trường RIÊNG, không ghi đè lên tiền dự kiến:
giữ cả hai mới thấy được đợt nào lệch và lệch bao nhiêu.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_text,
)

STATUS_DELIVERING = "Đang giao"
STATUS_RECEIVED = "Đã nhận - chờ xuất HĐ"
STATUS_INVOICED = "Đã xuất hóa đơn"
STATUS_CANCELLED = "Hủy"

# Trạng thái còn nằm trong danh sách chờ. Hai cái còn lại đã ra khỏi vòng đời.
OPEN_STATUSES = (STATUS_DELIVERING, STATUS_RECEIVED)

SOURCE_MANUAL = "Nhập tay"
SOURCE_OPENING = "Số dư đầu kỳ"

# Lệch giữa tiền dự kiến và tiền phiếu nhập kho quá ngần này thì phải nói ra.
# 1đ chỉ để chống rác dấu phẩy động.
AMOUNT_EPS = 1.0


class MTWinPending(Document):
    def validate(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.company:
            frappe.throw(_("Đợt giao phải thuộc một công ty"))

        self.po_no = norm_text(self.po_no)
        self.grn_no = norm_text(self.grn_no)
        if not self.po_no:
            frappe.throw(_("Thiếu số PO — đó là khóa duy nhất của một đợt giao"))

        self.status = self.status or STATUS_DELIVERING
        self.source = self.source or SOURCE_MANUAL
        self.total_amount = flt(self.amount_before_vat) + flt(self.vat_amount)

        self._check_duplicate_po()
        self._check_status()

    def _check_duplicate_po(self):
        """Một PO chỉ được theo dõi MỘT dòng trong cùng công ty.

        Không tính dòng đã Hủy: PO bị hủy rồi giao lại là chuyện có thật, và
        chặn cả dòng hủy thì kế toán không tạo lại được.
        """
        dup = frappe.db.sql("""
            SELECT name, status FROM `tabMT Win Pending`
            WHERE company = %(company)s AND po_no = %(po)s
              AND name != %(me)s AND status != %(cancelled)s
            LIMIT 1
        """, {"company": self.company, "po": self.po_no,
              "me": self.name or "", "cancelled": STATUS_CANCELLED}, as_dict=True)
        if dup:
            frappe.throw(_(
                "PO {0} đã được theo dõi ở {1} (trạng thái '{2}'). Một đợt giao chỉ "
                "theo dõi MỘT dòng — hai dòng cùng PO là tới lúc xuất hóa đơn sẽ có "
                "người xuất hai lần."
            ).format(self.po_no, dup[0].name, dup[0].status))

    def _check_status(self):
        if self.status == STATUS_RECEIVED and not self.grn_no:
            frappe.throw(_(
                "Trạng thái '{0}' phải có Số phiếu nhập kho Win — đó chính là thứ cho "
                "phép xuất hóa đơn (SOP §2.2). Chưa có phiếu thì vẫn là '{1}'."
            ).format(STATUS_RECEIVED, STATUS_DELIVERING))

        if self.status == STATUS_INVOICED:
            if not self.sales_invoice:
                frappe.throw(_("Trạng thái '{0}' phải gắn Hóa đơn đã xuất")
                             .format(STATUS_INVOICED))
            si = frappe.db.get_value("Sales Invoice", self.sales_invoice,
                                     ["docstatus", "company"], as_dict=True)
            if not si:
                frappe.throw(_("Không tìm thấy hóa đơn {0}").format(self.sales_invoice))
            if si.docstatus != 1:
                frappe.throw(_("Hóa đơn {0} chưa ghi sổ").format(self.sales_invoice))
            if cstr(si.company) != cstr(self.company):
                frappe.throw(_("Hóa đơn {0} thuộc công ty {1}, khác công ty {2} của đợt giao")
                             .format(self.sales_invoice, si.company, self.company))

        # Lệch giữa tiền dự kiến và tiền phiếu nhập kho KHÔNG chặn — SOP §2.2
        # nói rõ lệch là chuyện bình thường và xử bằng xuất trả phần chênh.
        # Nhưng phải để lại vết, nếu không thì lệch trôi qua không ai biết.
        if self.grn_amount and abs(flt(self.grn_amount) - flt(self.total_amount)) > AMOUNT_EPS:
            diff = flt(self.grn_amount) - flt(self.total_amount)
            note = _("Lệch {0} đ giữa đơn giao ({1}) và phiếu nhập kho ({2}) — "
                     "xuất hóa đơn theo SỐ THỰC NHẬN, phần chênh làm xuất trả.").format(
                "{:,.0f}".format(diff), "{:,.0f}".format(flt(self.total_amount)),
                "{:,.0f}".format(flt(self.grn_amount)))
            if note not in cstr(self.note):
                self.note = (cstr(self.note) + "\n" + note).strip()
