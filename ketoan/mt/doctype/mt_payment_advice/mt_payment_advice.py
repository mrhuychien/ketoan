"""MT Payment Advice — bảng kê thanh toán của MỘT chuỗi siêu thị cho MỘT kỳ.

Phạm vi cố ý HẸP: chỉ GHI NHẬN dòng đọc từ file + đánh dấu kết quả đối soát.
DocType này TUYỆT ĐỐI không tạo/sửa/hủy Payment Entry, Journal Entry hay bất kỳ
chứng từ kế toán nào — con người quyết định hạch toán sau khi xem bảng kê.

MỘT FILE ≠ MỘT BẢN GHI: một file có thể chứa nhiều kỳ thanh toán (LOTTE có 2
Payment Date trong cùng file; Co.op có 8 sheet = 8 lần thanh toán riêng). Mỗi kỳ
phải là MỘT MT Payment Advice riêng, nếu không thì gộp nhầm tiền của hai kỳ.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import norm_text

# Ánh xạ loại dòng -> trường tổng. Dòng "Khác" gộp chung với "Ghi giảm" ở
# total_other: cả hai đều là khoản chưa phân loại chắc chắn, để kế toán soi tay.
_KIND_TO_TOTAL = {
    "Thanh toán": "total_payment",
    "Chiết khấu": "total_discount",
    "Phí": "total_fee",
    "Ghi giảm": "total_other",
    "Khác": "total_other",
}

_TOTAL_FIELDS = ("total_payment", "total_discount", "total_fee", "total_other")

# Trạng thái bút toán — do MÁY tính từ docstatus của các Journal Entry mang
# `custom_mt_source_name` = tên bảng kê này. Kế toán không sửa tay được
# (`read_only` trên field), và `ketoan.api.mt_je.sync_advice_state` tính lại mỗi
# lần JE được submit/cancel — kể cả khi thao tác thẳng trên Desk, không qua portal.
JE_STATE_NONE = "Chưa sinh"
JE_STATE_DRAFT = "Đã sinh nháp"
JE_STATE_PARTIAL = "Đã duyệt một phần"
JE_STATE_ALL = "Đã duyệt đủ"


class MTPaymentAdvice(Document):
    def validate(self):
        self.advice_no = norm_text(self.advice_no)
        self.file_name = norm_text(self.file_name)
        if not self.status:
            self.status = "Nháp"

        # Công ty rỗng = bản ghi VÔ HÌNH. Sáu truy vấn của màn hình MT đều lọc
        # `a.company = %(company)s`, kể cả `_paid_subquery`, nên một bảng kê
        # thiếu công ty sẽ không hiện ở đâu cả VÀ tiền của nó không được tính là
        # đã thu — hóa đơn đã trả vẫn nằm rổ "chưa thanh toán". Không báo gì.
        #
        # reqd=1 lo đường Desk; nhánh này lo đường code gọi thẳng.
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.company:
            frappe.throw(_("Bảng kê phải thuộc một công ty"))

        self._validate_lines()
        self._compute_totals()
        self._warn_declared_mismatch()
        self._validate_status()

    def _validate_lines(self):
        """Frappe KHÔNG tự chạy validate() của child doctype — phải gọi tay.

        Nếu không gọi, inv_no_norm rỗng và mọi phép khớp hóa đơn sẽ trượt trong im
        lặng (khớp hụt = báo "chưa thanh toán" cho hóa đơn đã được trả).
        """
        for row in self.lines or []:
            row.validate()

    def _compute_totals(self):
        """Cộng tổng theo LOẠI DÒNG, giữ nguyên dấu mà tầng đọc file đã ghi.

        KHÔNG dùng abs() và KHÔNG đảo dấu ở đây: mỗi chuỗi một quy ước dấu
        (Central Retail/Emart để hàng hóa ÂM, LOTTE để hàng hóa DƯƠNG). Dấu là
        chốt để đối chiếu với dòng tổng do chính chuỗi in trong file — đổi dấu ở
        tầng này là mất chốt đối chiếu.
        """
        totals = {f: 0.0 for f in _TOTAL_FIELDS}
        for row in self.lines or []:
            field = _KIND_TO_TOTAL.get(row.row_kind)
            if not field:
                # row_kind là trường bắt buộc; tới đây mà rỗng nghĩa là dữ liệu
                # nhập sai -> báo lỗi chứ không âm thầm bỏ tiền ra khỏi tổng.
                frappe.throw(_("Dòng {0}: chưa chọn Loại dòng.").format(row.idx))
            totals[field] += flt(row.total_amount)

        for field, value in totals.items():
            setattr(self, field, value)

    def _warn_declared_mismatch(self):
        """So tổng đọc được với SỐ KIỂM TRA do chính chuỗi in trong file.

        CẢNH BÁO chứ không chặn: Co.op làm tròn chiết khấu ở cấp dòng và tiền
        thanh toán ở cấp nhóm độc lập nhau nên lệch ±1..3 đồng là BÌNH THƯỜNG và
        đã được xác minh trên file thật. Chặn cứng ở đây sẽ khóa nghiệp vụ đúng;
        ngược lại lệch lớn thì kế toán phải thấy ngay. Con người quyết định.
        """
        checks = (
            (self.declared_total_payment, self.total_payment, _("Tổng thanh toán")),
            (self.declared_total_discount, self.total_discount, _("Tổng chiết khấu")),
        )
        # Tính lười — chỉ cần khi gặp số kiểm tra BẰNG 0 (xem lý do bên dưới).
        first_save = None
        for declared, computed, label in checks:
            if declared is None:
                # None = FILE KHÔNG IN số kiểm tra (mt._declared trả None, và
                # commit_advice cũng để None khi số của chuỗi đo đại lượng khác)
                # -> không có gì để so.
                continue
            if not flt(declared):
                # SỐ 0 DO CHUỖI IN RA LÀ MỘT KHẲNG ĐỊNH ("kỳ này không có chiết
                # khấu"), KHÔNG phải "thiếu số kiểm tra". Bản cũ dùng
                # `if not declared: continue` nên nuốt luôn ca này: WinCommerce
                # có declared_total_discount = 0 thật, mà nhánh sinh dòng chiết
                # khấu của tầng đọc file thì CHƯA từng chạy trên dữ liệu thật —
                # nếu nó đọc nhầm cột và đẻ ra chiết khấu ma thì đây là chốt duy
                # nhất bắt được, mà chốt đó lại đang tắt.
                #
                # NHƯNG: cột Currency của MariaDB là NOT NULL DEFAULT 0, nên khi
                # ĐỌC LẠI bản ghi cũ, None đã hóa 0 và không còn phân biệt được
                # với "chuỗi in số 0". Chỉ tin số 0 ở LẦN LƯU ĐẦU (lúc None còn
                # nguyên trong bộ nhớ). Không chặn ở đây thì mỗi lần Kế toán
                # trưởng bấm Save một bảng kê Central Retail (declared để None vì
                # 'Overall Result' đo NET chứ không đo tổng thanh toán) sẽ nổ
                # cảnh báo lệch cả 721 triệu — kêu sai riết thì kế toán quen tay
                # bấm bỏ qua, tới lúc lệch THẬT không ai còn nhìn.
                if first_save is None:
                    first_save = not frappe.db.exists(self.doctype, self.name) if self.name else True
                if not first_save:
                    continue
            diff = flt(declared) - flt(computed)
            if diff:
                frappe.msgprint(
                    _("{0}: file ghi {1}, cộng từ các dòng ra {2} — lệch {3}. Kiểm tra trước khi đánh dấu đã đối chiếu.").format(
                        label, flt(declared), flt(computed), diff
                    ),
                    title=_("Lệch số kiểm tra"),
                    indicator="orange",
                )

    def _validate_status(self):
        """'Đã ghi nhận' là trạng thái con người đã chốt — bắt buộc đã đối chiếu.

        Không tự tick 'reconciled' hộ kế toán ở bất kỳ nhánh nào.
        """
        if self.status == "Đã ghi nhận" and not self.reconciled:
            frappe.throw(_("Chưa tick 'Đã đối chiếu khớp' thì không được chuyển trạng thái 'Đã ghi nhận'."))

        # 'Đã ghi nhận' phải có nghĩa ĐÃ VÀO SỔ, không phải "kế toán tick cho xong".
        #
        # VÌ SAO chặn ở đây: màn hình Công nợ MT và báo cáo đọc trạng thái này để
        # nói "kỳ này xong rồi". Đặt tay trên Desk trong khi bút toán vẫn còn nháp
        # là màn hình nói dối — và người phát hiện ra sẽ là kiểm toán, không phải
        # kế toán. `je_state` do máy tính, nên chốt này không cãi được.
        if self.status == "Đã ghi nhận" and self.je_state != JE_STATE_ALL:
            frappe.throw(_(
                "Bút toán của bảng kê này đang ở '{0}'. 'Đã ghi nhận' chỉ đặt được khi "
                "MỌI bút toán liên quan đã được duyệt (ghi sổ)."
            ).format(self.je_state or JE_STATE_NONE))
