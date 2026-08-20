"""MT Discount Term — điều khoản chiết khấu của từng chuỗi. Cấu hình, không hardcode.

Trả lời hai câu mà file doanh số của chuỗi KHÔNG trả lời được:

  · Chiết khấu tính THẾ NÀO? (cộng từng dòng, hay tỷ lệ × tổng)
  · Tỷ lệ bao nhiêu?

VÌ SAO là DocType chứ không phải hằng số: đo trên mẫu thật, LOTTE 10% còn
Central Retail 3,35% — và tỷ lệ đổi theo hợp đồng từng năm, từng pháp nhân.
Chôn vào mã là mỗi lần ký lại hợp đồng phải deploy.

VÌ SAO `mode` cũng phải cấu hình chứ không suy từ file: hai cách tính KHÁC NHAU
THẬT, không thay nhau được. Đo trên mẫu BKCK 261 của BigC:

    Tổng Cộng                   715.000.265
    'Số tiền chiết khấu 3.35%'   23.952.537     ← BigC in ra
    715.000.265 × 3,35%        = 23.952.508,88  ← tự tính lại      LỆCH 28,12đ

BigC làm tròn TỪNG DÒNG. LOTTE thì tỷ lệ × tổng khớp 0đ trên cả 7 kỳ mẫu.

TRA CỨU: dòng của KHÁCH thắng dòng mặc định của chuỗi. Không tìm thấy -> THROW,
tuyệt đối không lấy tỷ lệ đoán: xuất hóa đơn chiết khấu sai số tiền thì phải làm
hóa đơn điều chỉnh, để lại vết với cơ quan thuế.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

MODE_PER_LINE = "Cộng chiết khấu từng dòng"
MODE_RATE_TOTAL = "Tỷ lệ × tổng doanh số"

# Khóa ASCII của tầng đọc file (`mt_discount_read`) -> nhãn DocType.
READ_MODE_TO_LABEL = {
    "per_line": MODE_PER_LINE,
    "rate_on_total": MODE_RATE_TOTAL,
}


class MTDiscountTerm(Document):
    def validate(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.company:
            frappe.throw(_("Điều khoản phải thuộc một công ty"))

        # Tỷ lệ × tổng mà không có tỷ lệ thì không tính được gì. Chặn ngay ở
        # đây, đừng để tới lúc lập bảng kê mới phát hiện.
        if self.mode == MODE_RATE_TOTAL and not flt(self.rate):
            frappe.throw(_("Cách tính '{0}' bắt buộc phải có Tỷ lệ chiết khấu")
                         .format(MODE_RATE_TOTAL))
        if flt(self.rate) < 0 or flt(self.rate) > 100:
            frappe.throw(_("Tỷ lệ chiết khấu phải trong khoảng 0–100%"))
        if flt(self.vat_rate) < 0 or flt(self.vat_rate) > 100:
            frappe.throw(_("Thuế suất phải trong khoảng 0–100%"))

        self._check_natural_key()

    def _check_natural_key(self):
        """(chuỗi, khách, công ty) DUY NHẤT trong các dòng ĐANG ÁP DỤNG.

        Hai dòng cùng khóa thì tỷ lệ nào được dùng là do thứ tự đọc quyết định —
        và số tiền trên hóa đơn chiết khấu thành chuyện may rủi.
        """
        if not cint(self.active):
            return
        dup = frappe.db.get_value("MT Discount Term", {
            "chain": self.chain,
            "customer": self.customer or "",
            "company": self.company,
            "active": 1,
            "name": ("!=", self.name or ""),
        }, "name")
        if dup:
            frappe.throw(_(
                "Đã có điều khoản đang áp dụng cho chuỗi '{0}' · khách '{1}' · công ty {2}: {3}"
            ).format(self.chain, self.customer or "(mặc định)", self.company, dup))


def resolve(chain, customer, company):
    """Điều khoản áp dụng cho (chuỗi, khách, công ty). Không có -> THROW.

    Dòng của KHÁCH thắng dòng mặc định của chuỗi — đây là thứ tự duy nhất đúng:
    khai riêng cho một pháp nhân mà vẫn bị dòng chung che thì cấu hình riêng
    thành vô nghĩa mà không có gì báo.
    """
    rows = frappe.get_all(
        "MT Discount Term",
        filters={"chain": chain, "company": company, "active": 1},
        fields=["name", "customer", "mode", "rate", "vat_rate"],
        limit_page_length=0)
    exact = [r for r in rows if cint(bool(r.customer)) and r.customer == customer]
    default = [r for r in rows if not r.customer]
    hit = (exact or default or [None])[0]
    if not hit:
        frappe.throw(_(
            "Chưa cấu hình điều khoản chiết khấu cho chuỗi '{0}' (khách {1}, công ty {2}). "
            "Vào MT Discount Term khai cách tính + tỷ lệ rồi làm lại. KHÔNG lập bảng kê "
            "bằng tỷ lệ đoán — xuất hóa đơn sai số tiền thì phải làm hóa đơn điều chỉnh."
        ).format(chain, customer or "bất kỳ", company))
    return {
        "name": hit.name,
        "customer": hit.customer or None,
        "mode": hit.mode,
        "rate": flt(hit.rate),
        "vat_rate": flt(hit.vat_rate) or 8.0,
        "is_default_row": not hit.customer,
    }
