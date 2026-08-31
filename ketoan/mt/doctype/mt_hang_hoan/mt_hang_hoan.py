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

    kết luận "Không cần chứng từ"           -> "Đã đủ chứng từ"
    chưa có phiếu trả                       -> "Chưa lập phiếu trả"
    có phiếu trả, chưa có chứng từ thuế     -> "Chưa có chứng từ thuế"
    có cả hai                               -> "Đã đủ chứng từ"

Nhánh đầu hỏi TRƯỚC: lần hàng về "giao lại nguyên lô, hóa đơn gốc vẫn đúng"
không bao giờ cần một phiếu trả, nên hỏi `credit_note` trước là giam nó vĩnh
viễn ở "Chưa lập phiếu trả".

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
from frappe.utils import cint, nowdate

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
        self._check_one_row_per_su_co()
        self._check_one_row_per_credit_note()
        self._check_credit_note()
        self._derive_paper_status()

    def _check_one_row_per_su_co(self):
        """MỘT phiếu sự cố -> MỘT dòng sổ. Nhận hai lần không thành hai việc.

        Màn "Hàng hoàn chờ xử lý" liệt kê phiếu sự cố CHƯA có dòng nào ở đây rồi
        để kế toán bấm nhận. Hai người cùng mở màn hình, cùng bấm, là hai dòng
        cho một lần hàng về — và từ đó mọi con số đếm việc đều gấp đôi cho đúng
        những sự cố đông người xem nhất.

        Chỉ chặn khi `su_co` CÓ giá trị: dòng lập tay (hàng date siêu thị trả,
        không đi qua sự cố vận chuyển nào) để trống ô này, và nhiều dòng cùng
        trống là bình thường.
        """
        if not self.su_co:
            return
        dup = frappe.db.get_value(
            "MT Hang Hoan", {"su_co": self.su_co, "name": ["!=", self.name]}, "name")
        if dup:
            frappe.throw(_(
                "Phiếu sự cố {0} đã có trong sổ hàng hoàn ({1}). Mỗi lần hàng về "
                "chỉ một dòng."
            ).format(self.su_co, dup), frappe.DuplicateEntryError)

    def _check_one_row_per_credit_note(self):
        """MỘT phiếu trả -> MỘT dòng sổ. Đây là mặt còn lại của cùng một lỗ.

        Hóa đơn SI-1 móp lúc giao tháng 6 và bị trả hàng date tháng 8 -> hai
        dòng sổ, và mỗi dòng cần MỘT phiếu trả riêng. Nếu cả hai cùng nối vào
        RET-1 thì cả hai cùng suy ra `misa_no` của RET-1, cùng nhảy sang "Đã đủ
        chứng từ", hàng đợi sạch bong — còn lần trả tháng 8 thì không ai lập
        phiếu nữa. Đúng cái hại mà docstring của bảng này đã gọi tên: "phiếu
        thứ hai không bao giờ được lập, công nợ thừa vĩnh viễn, và không màn
        hình nào kêu".

        Màn hình có khóa sẵn ô đã dùng (`_phieu_tra_ung_vien.da_dung`), nhưng
        đó là khóa VẼ LÚC MỞ TRANG: hai người cùng mở trước khi ai kịp lưu thì
        cả hai đều thấy nó còn trống. Và Desk thì chỉ có một ô Link trần. Chốt
        chặn phải nằm ở đây.
        """
        if not self.credit_note:
            return
        dup = frappe.db.get_value(
            "MT Hang Hoan",
            {"credit_note": self.credit_note, "name": ["!=", self.name]}, "name")
        if dup:
            frappe.throw(_(
                "Phiếu trả {0} đã nối vào dòng {1}. Mỗi phiếu trả chỉ thuộc MỘT lần "
                "hàng về — lần này cần phiếu trả riêng của nó."
            ).format(self.credit_note, dup), frappe.DuplicateEntryError)

    def _check_credit_note(self):
        """Phiếu trả phải là PHIẾU TRẢ, ĐÃ GHI SỔ, và trả cho ĐÚNG hóa đơn gốc."""
        if not self.credit_note:
            return
        cn = frappe.db.get_value(
            "Sales Invoice", self.credit_note,
            ["is_return", "return_against", "docstatus"], as_dict=True)
        if not cn:
            frappe.throw(_("Không tìm thấy phiếu trả {0}.").format(self.credit_note))
        if not cn.is_return:
            frappe.throw(_("{0} không phải phiếu trả hàng (is_return = 0).").format(self.credit_note))
        # CHỈ PHIẾU ĐÃ GHI SỔ MỚI TÍNH. `mt._returns_join` chỉ cộng phiếu trả
        # `docstatus = 1`; nối một phiếu nháp vào đây là sổ này báo "đã lập
        # phiếu trả" trong khi công nợ vẫn đang đòi đủ tiền hóa đơn gốc. Hai
        # màn hình nói hai đằng về cùng một lần trả hàng, và cái sai là cái
        # bảo việc đã xong.
        if cint(cn.docstatus) != 1:
            frappe.throw(_(
                "Phiếu trả {0} chưa ghi sổ (hoặc đã hủy). Ghi sổ phiếu trả trước, "
                "rồi mới nối vào sổ hàng hoàn — công nợ chỉ trừ phiếu đã ghi sổ."
            ).format(self.credit_note))
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
        # "Không cần chứng từ" HỎI TRƯỚC, không phải sau khi đã có phiếu trả.
        #
        # Bản đầu hỏi `credit_note` trước, nên lần hàng về mà kết luận là "giao
        # lại nguyên lô, hóa đơn gốc vẫn đúng" bị kẹt vĩnh viễn ở "Chưa lập
        # phiếu trả" — đúng cái nó không bao giờ cần lập. Một hàng đợi có dòng
        # không bao giờ ra được là hàng đợi người ta thôi nhìn, và lúc đó nó
        # nuốt luôn những dòng thật.
        if self.chung_tu_can == CT_KHONG_CAN:
            self.trang_thai_giay = GIAY_XONG
        elif not self.credit_note:
            self.trang_thai_giay = GIAY_CHUA_TRA
            self.ngay_xong_giay = None
            return
        else:
            # SUY LẠI TỪ ĐẦU, không giữ số cũ.
            #
            # `self.misa_no or _doc_no_of(...)` giữ số của phiếu trả CŨ khi kế
            # toán đổi sang phiếu khác — và đổi phiếu là thao tác bình thường ở
            # đây, vì một hóa đơn có thể có nhiều phiếu trả và màn hình bày ra
            # cả danh sách để chọn. Chọn nhầm rồi chọn lại là dòng mang số chứng
            # từ của một lần trả hàng khác mà vẫn báo "Đã đủ chứng từ".
            #
            # Ô này `read_only` nên không ai gõ tay vào — không có gì để mà giữ.
            self.misa_no = _doc_no_of(self.credit_note)
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
