"""MT Account Map — bút toán MT vào TÀI KHOẢN NÀO. Cấu hình, không hardcode.

Ba sự kiện, mỗi cái một bộ tài khoản (§4 SOP, chốt 20/08/2026):

    Nhận thanh toán        Nợ 112              Có 131
    Chiết khấu mình xuất   Nợ 5211 + 33311     Có 131
    Phí chuỗi xuất         Nợ 6411 + 1331      Có 131

VÌ SAO là DocType chứ không phải hằng số trong code: số hiệu tài khoản là 112,
nhưng TÀI KHOẢN CON cụ thể (112 - ngân hàng nào) khác nhau theo công ty và đổi
được. Chôn tên account vào code là mỗi lần mở tài khoản ngân hàng mới phải sửa
mã và deploy lại.

TRA CỨU: dòng riêng của chuỗi thắng dòng mặc định. Không tìm thấy -> THROW,
tuyệt đối không lấy TK mặc định cứng: sinh bút toán vào SAI tài khoản còn tệ hơn
không sinh, vì nó nằm im trong sổ cho tới lúc quyết toán.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

EVENT_PAYMENT = "Nhận thanh toán"
EVENT_DISCOUNT = "Chiết khấu mình xuất"
EVENT_FEE = "Phí chuỗi xuất"

EVENTS = (EVENT_PAYMENT, EVENT_DISCOUNT, EVENT_FEE)

# Sự kiện -> tiền tố số hiệu TK mong đợi. CHỈ dùng để CẢNH BÁO khi kế toán chọn
# tài khoản trông lạ, KHÔNG dùng để chặn: hệ thống tài khoản của từng công ty có
# thể khác, và chặn cứng theo số hiệu là bắt kế toán sửa code.
EXPECTED_PREFIX = {
    EVENT_PAYMENT: {"debit": ("112", "111"), "credit": ("131",)},
    EVENT_DISCOUNT: {"debit": ("521", "511"), "tax": ("333",), "credit": ("131",)},
    EVENT_FEE: {"debit": ("641", "642", "635"), "tax": ("133",), "credit": ("131",)},
}


class MTAccountMap(Document):
    def validate(self):
        self._check_natural_key()
        self._check_accounts()
        self._warn_unexpected_prefix()

    def _check_natural_key(self):
        """(sự kiện, chuỗi, công ty) là DUY NHẤT trong các dòng ĐANG DÙNG.

        Hai dòng cùng khóa thì `_resolve` trả dòng nào là do thứ tự đọc quyết
        định — bút toán vào TK này hay TK kia thành chuyện may rủi. Chỉ soi các
        dòng `active`: giữ lại dòng cũ đã tắt là lịch sử, không phải xung đột.
        """
        if not self.active:
            return
        dup = frappe.db.get_value("MT Account Map", {
            "event": self.event,
            "chain": self.chain or "",
            "company": self.company,
            "active": 1,
            "name": ("!=", self.name or ""),
        }, "name")
        if dup:
            frappe.throw(_(
                "Đã có dòng đang dùng cho sự kiện '{0}' · chuỗi '{1}' · công ty {2}: {3}. "
                "Hai dòng cùng khóa thì bút toán vào tài khoản nào là chuyện may rủi."
            ).format(self.event, self.chain or "(mặc định)", self.company, dup))

    def _check_accounts(self):
        """TK phải thuộc ĐÚNG công ty và KHÔNG phải TK tổng hợp.

        Ghi vào tài khoản của công ty khác là bút toán không bao giờ lên đúng sổ;
        ghi vào TK nhóm (`is_group`) thì ERPNext từ chối lúc submit — nhưng lúc
        đó JE đã sinh hàng loạt rồi và kế toán phải xóa tay từng cái.
        """
        for field, label in (("debit_account", "TK Nợ chính"),
                             ("tax_account", "TK Nợ thuế"),
                             ("credit_account", "TK Có")):
            acc = self.get(field)
            if not acc:
                continue
            info = frappe.db.get_value("Account", acc,
                                       ["company", "is_group", "account_type"], as_dict=True)
            if not info:
                frappe.throw(_("{0}: không tìm thấy tài khoản {1}").format(label, acc))
            if info.company != self.company:
                frappe.throw(_("{0} ({1}) thuộc công ty {2}, không phải {3}")
                             .format(label, acc, info.company, self.company))
            if info.is_group:
                frappe.throw(_("{0} ({1}) là tài khoản TỔNG HỢP — không ghi bút toán vào được")
                             .format(label, acc))

        # TK Có của cả ba sự kiện đều là phải thu khách hàng. ERPNext ĐÒI
        # party_type/party trên dòng có `account_type = 'Receivable'`; tầng sinh
        # JE đã điền, nhưng nếu kế toán chọn nhầm một TK không phải phải thu thì
        # dòng đó sẽ KHÔNG trừ được công nợ của khách nào cả — im lặng.
        if self.credit_account:
            at = frappe.db.get_value("Account", self.credit_account, "account_type")
            if at != "Receivable":
                frappe.msgprint(_(
                    "TK Có ({0}) không phải loại 'Receivable'. Bút toán sẽ ghi được "
                    "nhưng KHÔNG trừ công nợ của khách nào — kiểm lại trước khi dùng."
                ).format(self.credit_account), indicator="orange", alert=True)

    def _warn_unexpected_prefix(self):
        """Số hiệu TK trông lạ so với §4 SOP -> nhắc, không chặn."""
        want = EXPECTED_PREFIX.get(self.event) or {}
        odd = []
        for key, field in (("debit", "debit_account"), ("tax", "tax_account"),
                           ("credit", "credit_account")):
            acc, prefixes = self.get(field), want.get(key)
            if not (acc and prefixes):
                continue
            num = frappe.db.get_value("Account", acc, "account_number") or ""
            if num and not str(num).startswith(prefixes):
                odd.append("%s = %s (mong %s…)" % (field, num, "/".join(prefixes)))
        if odd:
            frappe.msgprint(_("Số hiệu tài khoản khác thường lệ của sự kiện '{0}': {1}. "
                              "Vẫn lưu được — chỉ nhắc để soát lại.")
                            .format(self.event, " · ".join(odd)),
                            indicator="orange", alert=True)


def resolve(event, chain, company):
    """Bộ TK áp dụng cho (sự kiện, chuỗi, công ty). Không có -> THROW.

    Dòng riêng của chuỗi THẮNG dòng mặc định (`chain` rỗng). Đây là thứ tự duy
    nhất đúng: khai một dòng riêng cho LOTTE mà vẫn bị dòng mặc định che thì cấu
    hình riêng thành vô nghĩa mà không có gì báo.
    """
    rows = frappe.get_all(
        "MT Account Map",
        filters={"event": event, "company": company, "active": 1},
        fields=["name", "chain", "debit_account", "tax_account", "credit_account", "tax_rate"],
        limit_page_length=0)
    exact = [r for r in rows if (r.chain or "") == (chain or "")]
    default = [r for r in rows if not (r.chain or "")]
    hit = (exact or default or [None])[0]

    if not hit:
        frappe.throw(_(
            "Chưa cấu hình tài khoản cho sự kiện '{0}' (chuỗi {1}, công ty {2}). "
            "Vào MT Account Map khai TK Nợ / TK Có rồi làm lại. KHÔNG sinh bút toán "
            "bằng tài khoản đoán."
        ).format(event, chain or "bất kỳ", company))
    if not (hit.debit_account and hit.credit_account):
        frappe.throw(_(
            "Dòng cấu hình {0} (sự kiện '{1}') còn thiếu TK Nợ hoặc TK Có. Điền nốt "
            "rồi làm lại — bút toán thiếu một vế là bút toán không cân."
        ).format(hit.name, event))
    return {
        "name": hit.name,
        "chain": hit.chain or "",
        "debit_account": hit.debit_account,
        "tax_account": hit.tax_account or None,
        "credit_account": hit.credit_account,
        "tax_rate": flt(hit.tax_rate),
        # Người duyệt phải biết bút toán đang dùng dòng RIÊNG hay dòng MẶC ĐỊNH.
        "is_default_row": not (hit.chain or ""),
    }
