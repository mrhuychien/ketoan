"""MT Hang Hoan Item — một mã hàng trong lần hàng quay về.

BA số lượng, không phải một — và phiếu trả hàng chỉ giữ được số đầu:

    sl_tra       siêu thị trả bao nhiêu  -> ghi giảm công nợ
    sl_ve        thực về sân bao nhiêu   -> lệch = MẤT TRÊN ĐƯỜNG
    sl_nhap_lai  lọc ra dùng được        -> + sl_hong phải bằng sl_ve

Gộp ba số này làm một là mất đúng thông tin đáng tiền nhất: phần chênh giữa
`sl_tra` và `sl_ve` là căn cứ đòi nhà xe, và không chứng từ kế toán nào ghi nó.
"""

from frappe.model.document import Document


class MTHangHoanItem(Document):
    pass
