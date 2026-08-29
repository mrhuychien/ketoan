"""Patch: ô `custom_mt_einv_skip` (+ lý do / người / ngày) trên Sales Invoice.

VÌ SAO CẦN
══════════

Danh sách "đã ghi sổ, chưa có số HĐĐT" lấy MỌI hóa đơn trống ô số. Trong đó
luôn có một ít tờ không bao giờ xử được — hóa đơn nội bộ, hóa đơn đã hủy bên
ngoài hệ, hóa đơn của kỳ cũ đã chốt bằng cách khác. Chúng nằm mãi ở đó, và một
danh sách việc-phải-làm không bao giờ về 0 là danh sách người ta thôi nhìn.

Ô này để kế toán loại đúng những tờ đó, có ghi lý do và người quyết.

⚠ KHÔNG ĐỘNG TỚI SỔ SÁCH. Nó chỉ ẩn dòng khỏi MỘT danh sách rà soát. Công nợ,
thẻ hai cuốn sổ, sổ cái 131 — không cái nào đọc nó.

Quy tắc: THÊM FIELD MỚI = THÊM PATCH MỚI. Không có ngoại lệ.

PATCH KHÔNG BỎ QUA HÓA ĐƠN NÀO
══════════════════════════════

Không có hóa đơn nào đang ở tình huống đó tại thời điểm cài (tính năng ra đời
cùng patch này), và đoán hộ ở đây là tự tay giấu việc của người ta.
"""

import frappe


def execute():
    from ketoan.install import setup_mt_fields

    setup_mt_fields()
    frappe.clear_cache(doctype="Sales Invoice")

    if not frappe.db.has_column("Sales Invoice", "custom_mt_einv_skip"):
        frappe.logger().info(
            "ketoan: chưa tạo được custom_mt_einv_skip — chạy lại migrate (v0_0_18)")
        return

    # Cột Check mới trên bảng có sẵn dữ liệu: MariaDB điền NULL, không phải 0.
    #
    # Tầng đọc lọc bằng `IFNULL(..., 0) = 0` nên NULL vẫn an toàn — nhưng để
    # NULL thì bộ lọc trên Desk ("Bỏ qua = No") lại KHÔNG thấy hóa đơn cũ, và
    # kế toán đọc thành "chỉ có ngần này hóa đơn". Chuẩn hóa về 0 ngay.
    frappe.db.sql("""
        UPDATE `tabSales Invoice`
        SET custom_mt_einv_skip = 0
        WHERE custom_mt_einv_skip IS NULL
    """)
    frappe.db.commit()
    frappe.logger().info("ketoan: ô bỏ qua soát HĐĐT (v0_0_18)")
