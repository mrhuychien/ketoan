from frappe.model.document import Document


class KiemHangThuHoiDong(Document):
    """Một mã hàng ĐẾM THẬT lúc hàng thu hồi về kho — số theo ĐVT kho.

    `chi_tiet` giữ cách người kiểm đếm ("2 Thùng + 3 Hộp", JSON) để mở lại bàn số
    đúng tab; `qty` là tổng quy đổi do SERVER tính từ hệ số trên Item, không tin
    hệ số client gửi. Mọi luật nằm ở controller cha."""

    pass
