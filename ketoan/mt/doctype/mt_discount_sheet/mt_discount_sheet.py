"""MT Discount Sheet — BẢNG KÊ CHIẾT KHẤU (BKCK) mình lập để xuất hóa đơn CK.

Chứng từ HAI BÊN KÝ. Sai ở đây không chỉ là dữ liệu xấu — nó dẫn tới một hóa đơn
GTGT sai, và hóa đơn đã xuất thì phải làm hóa đơn điều chỉnh, để lại vết với cơ
quan thuế. Vì vậy DocType này chặn nhiều hơn mức thông thường.

ĐÁNH SỐ: `sheet_no` dạng `NNN/BKCK/HG-MT`, MỘT DÃY CHUNG TOÀN CÔNG TY — không
tách theo chuỗi. Quan sát mẫu thật: 141 · 155 · 172 · 229 · 243 · 260 ·
**261 (BigC)** · 280 · 300 — số của Central Retail nằm xen giữa dãy của LOTTE.
Số được cấp khi CHỐT bảng kê (`status = 'Đã chốt'`), không phải lúc tạo nháp:
bảng kê nháp bị xóa mà đã ăn mất một số là dãy thủng lỗ, và kiểm toán sẽ hỏi.

BÊN MUA lấy từ `Customer` / `MT Store.address`, TUYỆT ĐỐI không lấy từ cột
`SUPPLIERNAME` của file chuỗi — cột đó là tên CỦA MÌNH (xem §L.3 hợp đồng).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)
from ketoan.mt.doctype.mt_discount_term.mt_discount_term import MODE_PER_LINE, MODE_RATE_TOTAL

# Hậu tố cố định của dãy số bảng kê. Đổi nó là đổi cả lịch sử chứng từ đã ký,
# nên để hằng số có tên chứ không rải chuỗi khắp nơi.
SHEET_NO_SUFFIX = "BKCK/HG-MT"

STATUS_DRAFT = "Nháp"
STATUS_FINAL = "Đã chốt"
STATUS_INVOICED = "Đã xuất hóa đơn"

# Sai số cho phép khi soát tổng. Tiền VND nguyên đồng; 0,5 chỉ để chống rác dấu
# phẩy động khi chuỗi xuất số thực.
MONEY_EPS = 0.5


class MTDiscountSheet(Document):
    def validate(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.company:
            frappe.throw(_("Bảng kê phải thuộc một công ty"))

        self.buyer_name = norm_text(self.buyer_name)
        self.buyer_tax_id = norm_text(self.buyer_tax_id).replace(" ", "")
        self.discount_invoice_series = norm_series(self.discount_invoice_series)
        self.discount_invoice_no = norm_text(self.discount_invoice_no)

        for row in self.lines or []:
            # Frappe KHÔNG tự chạy validate() của child doctype — phải gọi tay,
            # nếu không `inv_no_norm` rỗng và mọi phép khớp hóa đơn trượt câm.
            row.validate()

        self._check_invoice_numbers()
        self._compute_totals()
        self._validate_status()

    def _check_invoice_numbers(self):
        """Số hóa đơn: HOẶC mọi dòng đều có, HOẶC không dòng nào có. Cấm lẫn lộn.

        VÌ SAO KHÔNG ĐẶT `reqd = 1` TRÊN `inv_no`:

        Emart chốt chiết khấu GỘP CẢ KỲ trên `All-Store Thiso Retail`, không tách
        theo hóa đơn — bảng kê Emart có đúng một dòng và dòng đó KHÔNG có số hóa
        đơn. Đó là hình dạng thật của chứng từ. Để `reqd = 1` thì `doc.insert()`
        ném `MandatoryError` và nghiệp vụ chiết khấu Emart không dùng được, trong
        khi mọi phép kiểm ngoại tuyến vẫn xanh (chúng dựng kế hoạch chứ không ghi).

        VÌ SAO KHÔNG BỎ HẲN GUARD:

        Với 3 chuỗi còn lại, bảng kê in MỘT DÒNG / HÓA ĐƠN. Một dòng mất số hóa
        đơn ở đó nghĩa là tầng đọc file sót cột — dòng vẫn mang tiền và vẫn cộng
        vào tổng, nên hóa đơn chiết khấu ra đúng số tiền mà bảng kê đính kèm thì
        thiếu căn cứ cho một phần tiền. Chuỗi ký xong mới phát hiện là phải làm
        hóa đơn điều chỉnh.

        Ranh giới đúng vì vậy là TÍNH ĐỒNG NHẤT, không phải sự tồn tại: trống hết
        = chuỗi chốt gộp; có hết = chốt theo hóa đơn; lẫn lộn = đọc sót.
        """
        rows = self.lines or []
        if not rows:
            return
        blank = [r.idx for r in rows if not norm_text(r.inv_no)]
        if blank and len(blank) != len(rows):
            frappe.throw(_(
                "Bảng kê có {0}/{1} dòng KHÔNG có số hóa đơn (dòng {2}…) trong khi các "
                "dòng khác có. Trống lẫn lộn nghĩa là tầng đọc file sót cột số hóa đơn — "
                "các dòng đó vẫn mang tiền và vẫn cộng vào tổng, nên hóa đơn chiết khấu "
                "sẽ đúng tiền mà bảng kê đính kèm thiếu căn cứ. Kiểm lại file rồi lập lại."
            ).format(len(blank), len(rows), blank[0]))

    def _compute_totals(self):
        """Tổng của bảng kê + số tiền chiết khấu, theo ĐÚNG cách tính đã chốt.

        HAI CÁCH, KHÔNG THAY NHAU ĐƯỢC (§L.2 hợp đồng):

          · `MODE_PER_LINE`   — cộng `discount_amount` từng dòng. Chuỗi làm tròn
            từng dòng nên tự tính lại từ tổng lệch ~30đ.
          · `MODE_RATE_TOTAL` — `tỷ lệ × tổng`. Khớp 0đ trên cả 7 kỳ mẫu LOTTE.

        Thuế của chiết khấu tính TRÊN SỐ CHIẾT KHẤU, không phải cộng thuế các
        dòng: mẫu thật in 23.952.537 × 8% = 1.916.202,96 đúng từng đồng.
        """
        self.total_base = sum(flt(r.amount_before_vat) for r in self.lines or [])
        self.total_vat = sum(flt(r.vat_amount) for r in self.lines or [])
        self.total_gross = flt(self.total_base) + flt(self.total_vat)

        if self.mode == MODE_PER_LINE:
            missing = [r.idx for r in self.lines or [] if r.discount_amount is None]
            if missing and self.status != STATUS_DRAFT:
                frappe.throw(_(
                    "Cách tính '{0}' nhưng {1} dòng không có Tiền chiết khấu (dòng {2}…). "
                    "File của chuỗi phải in chiết khấu từng dòng thì mới dùng cách này."
                ).format(MODE_PER_LINE, len(missing), missing[0]))
            self.discount_base = sum(flt(r.discount_amount) for r in self.lines or [])
        elif self.mode == MODE_RATE_TOTAL:
            if not flt(self.rate) and self.status != STATUS_DRAFT:
                frappe.throw(_("Cách tính '{0}' bắt buộc phải có Tỷ lệ chiết khấu")
                             .format(MODE_RATE_TOTAL))
            self.discount_base = flt(self.total_base) * flt(self.rate) / 100.0
        else:
            frappe.throw(_("Chưa chọn cách tính chiết khấu"))

        vat_rate = flt(self.vat_rate) or 8.0
        self.vat_rate = vat_rate
        self.discount_vat = flt(self.discount_base) * vat_rate / 100.0
        self.discount_gross = flt(self.discount_base) + flt(self.discount_vat)

    def _validate_status(self):
        if not self.status:
            self.status = STATUS_DRAFT

        if self.status == STATUS_DRAFT:
            return

        # ── Từ đây là bảng kê SẼ ĐƯỢC KÝ và dùng để xuất hóa đơn ────────────
        if not (self.lines or []):
            frappe.throw(_("Bảng kê không có dòng nào — không chốt được"))
        if not self.customer:
            frappe.throw(_("Chưa có Khách hàng (bên mua) — bảng kê là chứng từ hai bên ký"))
        if not self.buyer_tax_id:
            frappe.throw(_(
                "Chưa có MST bên mua. Hóa đơn chiết khấu ghi sai/thiếu MST người mua là "
                "hóa đơn không hợp lệ — điền địa chỉ cho điểm siêu thị rồi lập lại."
            ))
        if flt(self.discount_base) == 0:
            frappe.throw(_("Số tiền chiết khấu bằng 0 — không xuất hóa đơn cho bảng kê rỗng"))
        if not self.sheet_no:
            self._assign_sheet_no()

        if self.status == STATUS_INVOICED and not self.discount_invoice_no:
            frappe.throw(_("Trạng thái '{0}' phải có Số hóa đơn chiết khấu")
                         .format(STATUS_INVOICED))

    def _assign_sheet_no(self):
        """Cấp số bảng kê — MỘT DÃY CHUNG toàn công ty.

        Cấp lúc CHỐT chứ không lúc tạo: bảng kê nháp bị xóa mà đã ăn mất một số
        là dãy thủng lỗ, và kiểm toán sẽ hỏi vì sao thiếu số.

        `for update` khóa các dòng đang đọc cho tới hết giao dịch, nên hai người
        chốt cùng lúc không lấy trùng số. Không dùng `naming_series` của Frappe
        vì khuôn `NNN/BKCK/HG-MT` có số ở ĐẦU — naming_series không diễn đạt được.
        """
        row = frappe.db.sql("""
            SELECT IFNULL(MAX(sheet_seq), 0) AS mx
            FROM `tabMT Discount Sheet`
            WHERE company = %(company)s
            FOR UPDATE
        """, {"company": self.company}, as_dict=True)
        self.sheet_seq = cint(row[0].mx if row else 0) + 1
        self.sheet_no = "%d/%s" % (self.sheet_seq, SHEET_NO_SUFFIX)

    def on_trash(self):
        if cstr(self.status) != STATUS_DRAFT:
            frappe.throw(_(
                "Chỉ xóa được bảng kê ở trạng thái '{0}'. Bảng kê {1} đã chốt và đã ăn "
                "một số trong dãy — xóa là dãy thủng lỗ."
            ).format(STATUS_DRAFT, self.sheet_no or self.name))
