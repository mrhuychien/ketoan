"""Patch: field `custom_mt_credit_days` trên Customer — hạn thanh toán kênh MT.

Report "Công nợ MT đến hạn" (SOP §5, việc hàng tuần) cần biết mỗi hóa đơn đến
hạn ngày nào. Trước patch này không có chỗ nào khai hạn, nên không tính được.

PATCH NÀY KHÔNG ĐOÁN SỐ NGÀY CHO AI.

Nó chỉ VỚT giá trị đã có sẵn ở nơi khác trong hệ, theo đúng một nguồn:
`Sales Invoice.due_date` mà ERPNext đã tính từ Payment Terms của chính khách
đó. Nếu MỌI hóa đơn đã ghi sổ của một khách đều cách ngày hóa đơn ĐÚNG cùng
một số ngày, thì số ngày đó là hạn thật của khách — đã được ghi vào chứng từ,
không phải suy đoán.

Khách có hóa đơn lệch nhau (30 ngày lẫn 40 ngày, hoặc due_date = posting_date
vì chưa khai Payment Terms) thì để TRỐNG. Kế toán tự khai. Bảng số ngày theo
chuỗi ở SOP (Win 60 · LOTTE 45 · Co.op 45 · AEON 30 · Central Retail 30/40) là
gợi ý cho người, KHÔNG được code cứng: hai pháp nhân Central Retail cùng mang
`custom_mt_chain = Central Retail` nhưng hạn khác nhau 10 ngày.

Quy tắc: THÊM FIELD MỚI = THÊM PATCH MỚI. Không có ngoại lệ.
"""

import frappe

# Hóa đơn dưới ngưỡng này thì mẫu quá mỏng để kết luận hạn của khách.
MIN_INVOICES = 3


def execute():
    from ketoan.install import setup_mt_fields

    setup_mt_fields()
    frappe.clear_cache(doctype="Customer")

    if not frappe.db.has_column("Customer", "custom_mt_credit_days"):
        return

    # DATEDIFF > 0: due_date = posting_date là "ERPNext không có Payment Terms
    # nên lấy tạm ngày hóa đơn" — đó là KHÔNG BIẾT, không phải "hạn 0 ngày".
    rows = frappe.db.sql("""
        SELECT si.customer,
               COUNT(*)                                  AS n,
               COUNT(DISTINCT DATEDIFF(si.due_date, si.posting_date)) AS n_distinct,
               MIN(DATEDIFF(si.due_date, si.posting_date))            AS days
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.is_return = 0
          AND si.due_date IS NOT NULL
          AND DATEDIFF(si.due_date, si.posting_date) > 0
        GROUP BY si.customer
    """, as_dict=True)

    n_set = 0
    n_mixed = 0
    for r in rows:
        if int(r.n or 0) < MIN_INVOICES:
            continue
        if int(r.n_distinct or 0) != 1:
            n_mixed += 1
            continue                      # lệch nhau -> người quyết, không đoán
        if frappe.db.get_value("Customer", r.customer, "custom_mt_credit_days"):
            continue                      # đã khai -> không đè
        frappe.db.set_value("Customer", r.customer, "custom_mt_credit_days",
                            int(r.days), update_modified=False)
        n_set += 1

    frappe.db.commit()
    frappe.logger().info(
        "ketoan: khai hạn MT cho %d khách từ due_date đã ghi sổ; "
        "%d khách hóa đơn lệch hạn -> để trống chờ người khai (v0_0_16)"
        % (n_set, n_mixed))
