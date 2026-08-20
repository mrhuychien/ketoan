"""MT Win Dossier Line — MỘT hóa đơn trong hồ sơ thanh toán WinCommerce."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_series,
    norm_text,
)


class MTWinDossierLine(Document):
    def validate(self):
        self.inv_series = norm_series(self.inv_series)
        self.inv_no = norm_text(self.inv_no)
        self.po_vcm = norm_text(self.po_vcm)
        self.pdf_name = norm_text(self.pdf_name)
        if not self.inv_no:
            frappe.throw(_("Dòng {0}: thiếu số hóa đơn").format(self.idx))
        self.total_amount = flt(self.amount_before_vat) + flt(self.vat_amount)
