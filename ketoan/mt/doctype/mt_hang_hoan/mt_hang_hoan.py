"""MT Hang Hoan — sổ việc GIẤY TỜ của một lần hàng quay về.

════════════════════════════════════════════════════════════════════════════
VÌ SAO PHẢI CÓ BẢNG NÀY, KHÔNG ĐỌC THẲNG `Su Co Van Chuyen`
════════════════════════════════════════════════════════════════════════════

App `vanchuyen` đã có `Su Co Van Chuyen`, và cột `trang_thai` của nó có đủ
Mới / Đang xử lý / Đã xử lý / Đóng. Nhìn thì thừa. Nhưng cột đó thuộc về ĐIỀU
HÀNH và mang nghĩa **việc vận chuyển xong**, không phải **giấy tờ xong**:

    su_co_van_chuyen.py:31  on_update -> _stamp_si()
    _stamp_si: trang_thai vào nhóm ĐÓNG  ->  Sales Invoice.custom_co_su_co = 0

Điều hành bấm "Đã xử lý" ngay khi nhà xe xác nhận hàng đã về. Nếu màn kế toán
lọc theo cột đó — cách lọc tự nhiên nhất — thì việc "chưa xuất hóa đơn điều
chỉnh" BIẾN MẤT khỏi màn hình ngay hôm đó, im lặng, không log. Lộ ra vài tháng
sau khi siêu thị từ chối thanh toán, hoặc khi ký tờ khai thiếu chứng từ.

Nên trạng thái GIẤY TỜ phải là dữ liệu của app này, và phải SUY TỪ CHỨNG TỪ CÓ
THẬT chứ không ai gõ tay:

    chưa có phiếu trả                       -> "Chưa lập phiếu trả"
    có phiếu trả, chưa có chứng từ thuế     -> "Chưa có chứng từ thuế"
    có cả hai                               -> "Đã đủ chứng từ"

════════════════════════════════════════════════════════════════════════════
VÌ SAO GHI ĐÍCH DANH `credit_note`, KHÔNG SUY BẰNG EXISTS
════════════════════════════════════════════════════════════════════════════

Quan hệ sự cố <-> phiếu trả là NHIỀU-NHIỀU qua Sales Invoice. Một hóa đơn có
thể vừa móp lúc giao (tháng 6) vừa bị trả hàng date (tháng 8). Suy "đã lập
phiếu trả" bằng `EXISTS(return_against = si)` thì kế toán lập MỘT phiếu trả là
CẢ HAI dòng cùng rời khỏi hàng đợi — phiếu thứ hai không bao giờ được lập, công
nợ thừa vĩnh viễn, và không màn hình nào kêu.

════════════════════════════════════════════════════════════════════════════
CHI TIẾT MÃ HÀNG NẰM BÊN `vanchuyen`, KHÔNG Ở ĐÂY
════════════════════════════════════════════════════════════════════════════

Ba số lượng của một lần hàng về — siêu thị trả / thực về sân / lọc dùng được —
thì HAI cái sau chỉ điều phối và thủ kho biết, mà họ không vào được portal kế
toán. Đặt bảng ở đây là bắt kế toán chép lại số của người khác, và việc chép
lại thì hai tuần nữa sẽ không ai chép. Bảng đó là `Su Co Hang Ve` bên
`vanchuyen`; app này chỉ ĐỌC.

════════════════════════════════════════════════════════════════════════════
`su_co` LÀ DATA, KHÔNG PHẢI LINK
════════════════════════════════════════════════════════════════════════════

Link tới DocType của app khác làm app này KHÔNG CÀI ĐƯỢC trên site chưa có
`vanchuyen` (Frappe kiểm options của Link lúc migrate). Hai app chạy chung site
là chuyện của hôm nay; ràng chết vào nhau là chuyện của mãi mãi.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

# Trạng thái giấy tờ — MÁY SUY, không ai gõ.
GIAY_CHUA_TRA = "Chưa lập phiếu trả"
GIAY_CHUA_CT = "Chưa có chứng từ thuế"
GIAY_XONG = "Đã đủ chứng từ"

# Chứng từ thuế phải làm. "Không cần chứng từ" là một kết luận HỢP LỆ, không
# phải ô trống: hàng giao lại nguyên lô thì hóa đơn gốc vẫn đúng, đòi chứng từ
# ở đó là báo động giả không bao giờ tắt được.
CT_THAY_THE = "Hóa đơn thay thế"
CT_DIEU_CHINH = "Hóa đơn điều chỉnh"
CT_SIEU_THI = "Siêu thị xuất hóa đơn trả"
CT_KHONG_CAN = "Không cần chứng từ"


class MTHangHoan(Document):
    def validate(self):
        self._check_credit_note()
        self._derive_paper_status()

    def _check_credit_note(self):
        """Phiếu trả phải là PHIẾU TRẢ, và phải trả cho ĐÚNG hóa đơn gốc."""
        if not self.credit_note:
            return
        cn = frappe.db.get_value(
            "Sales Invoice", self.credit_note,
            ["is_return", "return_against", "docstatus"], as_dict=True)
        if not cn:
            frappe.throw(_("Không tìm thấy phiếu trả {0}.").format(self.credit_note))
        if not cn.is_return:
            frappe.throw(_("{0} không phải phiếu trả hàng (is_return = 0).").format(self.credit_note))
        # `return_against` trống là lỗi đang được `mt_gl_bridge` đo hằng ngày:
        # phiếu trả vẫn ghi giảm 131 trên sổ cái nhưng không trừ được vào hóa
        # đơn nào, nên rổ hóa đơn vẫn tính đủ nợ. Chặn ngay từ đây.
        if not cn.return_against:
            frappe.throw(_(
                "Phiếu trả {0} chưa khai 'trả cho hóa đơn nào' (Return Against). "
                "Chưa khai thì nó ghi giảm công nợ mà không trừ vào hóa đơn nào."
            ).format(self.credit_note))
        if self.sales_invoice and cn.return_against != self.sales_invoice:
            frappe.throw(_(
                "Phiếu trả {0} trả cho hóa đơn {1}, không phải {2}."
            ).format(self.credit_note, cn.return_against, self.sales_invoice))

    def _derive_paper_status(self):
        """Suy trạng thái giấy tờ. KHÔNG đọc `trang_thai` bên vanchuyen."""
        if not self.credit_note:
            self.trang_thai_giay = GIAY_CHUA_TRA
            self.ngay_xong_giay = None
            return

        if self.chung_tu_can == CT_KHONG_CAN:
            self.trang_thai_giay = GIAY_XONG
        else:
            self.misa_no = self.misa_no or _doc_no_of(self.credit_note)
            self.trang_thai_giay = GIAY_XONG if self.misa_no else GIAY_CHUA_CT

        if self.trang_thai_giay == GIAY_XONG and not self.ngay_xong_giay:
            self.ngay_xong_giay = nowdate()
        elif self.trang_thai_giay != GIAY_XONG:
            self.ngay_xong_giay = None


def _doc_no_of(credit_note):
    """Số chứng từ thuế đang gắn với phiếu trả — HỎI CẢ HAI PHÍA.

    Phía mình: số hóa đơn thay thế/điều chỉnh trên chính phiếu trả.
    Phía siêu thị: dòng `Ghi giảm` của bảng kê đã trỏ về phiếu trả này
    (`MT Payment Advice Line.return_invoice`, MT2-AK).

    Hỏi một phía là ca "siêu thị tự xuất hóa đơn" báo thiếu chứng từ VĨNH VIỄN —
    mình sẽ không bao giờ có hóa đơn MISA nào cho phiếu trả đó.
    """
    from ketoan.api.mt import SI_NO_FIELD

    if frappe.db.has_column("Sales Invoice", SI_NO_FIELD):
        ours = frappe.db.get_value("Sales Invoice", credit_note, SI_NO_FIELD)
        if ours:
            return ours

    if not frappe.db.table_exists("MT Payment Advice Line"):
        return None
    if not frappe.db.has_column("MT Payment Advice Line", "return_invoice"):
        return None
    return frappe.db.get_value(
        "MT Payment Advice Line", {"return_invoice": credit_note}, "inv_no")
