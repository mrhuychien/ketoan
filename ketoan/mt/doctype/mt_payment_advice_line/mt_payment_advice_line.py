"""MT Payment Advice Line — một dòng của bảng kê thanh toán chuỗi siêu thị.

Đây là bản GHI NHẬN dòng đọc từ file của chuỗi (WinCommerce / Central Retail /
LOTTE / Emart / Saigon Co.op), KHÔNG phải chứng từ kế toán. Việc hạch toán
(Payment Entry / Journal Entry) do con người quyết định.

Chuẩn hóa ký hiệu + số hóa đơn dùng ĐÚNG hàm của MISA Invoice Snapshot để hai
tầng đối soát không lệch nhau. Lệch chuẩn hóa = khớp hụt hóa đơn.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)

# Chỉ dòng thanh toán hàng hóa mới được nối sang Sales Invoice.
ROW_KIND_PAYMENT = "Thanh toán"

# Chỉ dòng ghi giảm mới được nối `return_invoice` — xem docstring của
# `_validate_return_invoice` bên dưới.
ROW_KIND_DEDUCT = "Ghi giảm"


# Ký hiệu hóa đơn điện tử theo TT78/2021: <mẫu số 1 chữ số><C hoặc K><2 chữ số
# năm><3 ký tự do người bán tự đặt>, ví dụ '1C26THG'. 'C' = có mã cơ quan thuế,
# 'K' = không có mã. Chỉ chữ số ĐỨNG NGAY TRƯỚC 'C'/'K' mới là mẫu số.
_MAU_SO_DAU = re.compile(r"^\d(?=[CK])")


def norm_series_mt(s) -> str:
    """Ký hiệu để SO KHỚP: chuẩn hóa như MISA rồi bỏ ĐÚNG MỘT chữ số mẫu số ở đầu.

    VÌ SAO phải bỏ: §E của hợp đồng — ngay trong MỘT file của chuỗi đã có cả
    'C26THG' và '1C26THG' cho CÙNG một dải hóa đơn (đã gặp thật ở Central Retail,
    LOTTE, Co.op). Không bỏ thì coi là hai ký hiệu khác nhau và hóa đơn không tìm
    được Sales Invoice.

    VÌ SAO chỉ bỏ ĐÚNG MỘT chữ số, và chỉ khi phần còn lại vẫn là ký hiệu hợp lệ
    (bắt đầu bằng 'C'/'K'): chữ số đầu là MẪU SỐ hóa đơn theo TT78 (1 = hóa đơn
    GTGT, 2 = hóa đơn bán hàng...), MỖI MẪU SỐ ĐÁNH SỐ ĐỘC LẬP TỪ 1. Bản cũ dùng
    `re.sub(r"^\\d+", ...)` nên nuốt sạch mọi chữ số đầu: '01C26THG' và '11C26THG'
    bị gộp vào cùng một khóa với 'C26THG' dù là ba dải hóa đơn khác nhau — khớp
    nhầm là ghi tiền của hóa đơn này sang hóa đơn kia.

    ⚠ GIỚI HẠN CÒN LẠI (không sửa được ở tầng hàm này): '1C26THG' và '2C26THG'
    vẫn cho cùng kết quả 'C26THG'. Hàm được dùng ĐỐI XỨNG cho cả chỉ mục Sales
    Invoice lẫn dòng file (mt._si_index / mt._match_row) nên không thể phân biệt
    "file thiếu mẫu số" với "file có mẫu số khác". Muốn khớp chặt phải đánh chỉ
    mục HAI TẦNG ở mt.py: khóa exact (norm_series) thử trước, chỉ rơi xuống khóa
    loose này khi ký hiệu trong file KHÔNG có mẫu số và loose cho đúng 1 ứng viên.

    Chỉ dùng ở TẦNG KHỚP. Trường inv_series vẫn lưu NGUYÊN VĂN của file để còn
    đối soát ngược với bản in của chuỗi.
    """
    v = norm_series(s)
    if not v:
        return ""
    # Ký hiệu toàn chữ số / không đúng dạng TT78 -> trả nguyên bản, không nuốt
    # mất dữ liệu và không tự bịa ra một khóa khớp rộng hơn thực tế.
    return _MAU_SO_DAU.sub("", v)


class MTPaymentAdviceLine(Document):
    def validate(self):
        """Chuẩn hóa + chặn nối nhầm hóa đơn.

        LƯU Ý: Frappe KHÔNG tự gọi validate() của child doctype khi lưu cha —
        MT Payment Advice.validate() phải gọi tay cho từng dòng.
        """
        self.inv_series = norm_series(self.inv_series)
        self.inv_no = norm_text(self.inv_no)
        self.inv_no_norm = norm_inv_no(self.inv_no)
        self.store_code = norm_text(self.store_code)
        self.store_name = norm_text(self.store_name)
        self.doc_no = norm_text(self.doc_no)
        self.match_method = norm_text(self.match_method)

        if self.sales_invoice and self.row_kind != ROW_KIND_PAYMENT:
            # BẪY TIỀN THẬT: dòng chiết khấu của Central Retail (Doc.Type=KS) mang
            # ký hiệu hóa đơn bán ra của chính mình ('1C26THG|5656') nhưng KHÔNG
            # phải thanh toán hóa đơn đó. Nối sang Sales Invoice là đánh dấu hóa
            # đơn "đã thanh toán" trong khi thực tế chưa.
            frappe.throw(
                _("Dòng {0}: loại dòng '{1}' KHÔNG được nối Hóa đơn ERPNext. Chỉ dòng '{2}' mới được khớp.").format(
                    self.idx, self.row_kind or "", ROW_KIND_PAYMENT
                )
            )

        if not self.sales_invoice:
            # Không còn nối SI thì "cách khớp" cũ vô nghĩa. Giữ nguyên độ tin cậy
            # vì "Không khớp" là kết luận hợp lệ cho dòng chưa có hóa đơn.
            self.match_method = None

        self._validate_return_invoice()

    def _validate_return_invoice(self):
        """`return_invoice` — nối CHỨNG TỪ, tuyệt đối không nối TIỀN.

        ════════════════════════════════════════════════════════════════════
        VÌ SAO CÓ Ô NÀY
        ════════════════════════════════════════════════════════════════════

        Siêu thị trả hàng date/thời vụ thì CÓ THỂ chính siêu thị xuất hóa đơn
        trả hàng, chứ không phải mình. Khi đó phiếu trả hàng trên ERPNext sẽ
        KHÔNG BAO GIỜ có số hóa đơn MISA của mình — và màn sổ theo dõi sẽ kêu
        "chưa có HĐ" mãi mãi. Báo động giả kêu mãi thì sau hai tuần không ai
        nhìn nữa, và lúc đó nó nuốt luôn cả những cảnh báo thật.

        Số hóa đơn của siêu thị đã nằm sẵn trong bảng kê thanh toán, ở dòng
        `Ghi giảm`. Nên chỉ cần trỏ dòng đó về phiếu trả là đủ chứng minh
        "đã có chứng từ thuế" — không phải gõ tay ô nào.

        ════════════════════════════════════════════════════════════════════
        VÌ SAO KHÔNG DÙNG LUÔN `sales_invoice` CHO VIỆC NÀY
        ════════════════════════════════════════════════════════════════════

        Vì `sales_invoice` là ĐƯỜNG TIỀN. `mt._paid_join` cộng dồn nó để ra
        "đã trả bao nhiêu". Mà hàng trả lại ĐÃ được trừ khỏi công nợ MỘT LẦN
        rồi, bằng chính phiếu trả (`_returns_join` từ MT2-N). Cho dòng ghi
        giảm nối vào đường tiền là trừ HAI LẦN cùng một lần trả hàng — và
        `mt_advice` đã chặn ở ba chỗ vì đúng lý do đó.

        Nên đây là ô THỨ HAI, cố ý tách hẳn. Không mệnh đề tính tiền nào được
        đọc nó; `two_books_check` có phép kiểm chứng minh điều đó.
        """
        if not self.return_invoice:
            return

        if self.row_kind != ROW_KIND_DEDUCT:
            frappe.throw(
                _("Dòng {0}: chỉ dòng '{1}' mới được nối Phiếu trả hàng. Dòng '{2}' "
                  "thì hóa đơn nối ở ô 'Hóa đơn ERPNext'.").format(
                    self.idx, ROW_KIND_DEDUCT, self.row_kind or ""))

        # Phải đúng là PHIẾU TRẢ. Trỏ nhầm sang hóa đơn bán ra thì màn hình
        # tưởng hóa đơn đó đã đủ chứng từ trả hàng trong khi nó chưa hề bị trả.
        if not frappe.db.get_value("Sales Invoice", self.return_invoice, "is_return"):
            frappe.throw(
                _("Dòng {0}: {1} không phải phiếu trả hàng (is_return = 0).").format(
                    self.idx, self.return_invoice))
