app_name = "ketoan"
app_title = "Ketoan"
app_publisher = "Hoang Giang JSC"
app_description = "Portal Kế toán Tác nghiệp — Bàn làm việc Công nợ & Quỹ trên ERPNext v16"
app_email = "dev@hoanggiang.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext"]

# ═══════════════════════════════════════════════════════════════════════════
# Install — tạo Role + cấp quyền (idempotent). KHÔNG ship DocPerm qua fixtures
# (hash name, đổi giữa site) → cấp bằng add_permission trong after_install.
# ═══════════════════════════════════════════════════════════════════════════
after_install = "ketoan.install.after_install"

# ═══════════════════════════════════════════════════════════════════════════
# Jinja helpers (dùng cho www context + Print Format sau này)
# ═══════════════════════════════════════════════════════════════════════════
jinja = {
    "methods": [
        "ketoan.utils.format_vnd",
    ],
}

# ═══════════════════════════════════════════════════════════════════════════
# Website — SPA portal phục vụ tại /ketoan (www/ketoan.html + ketoan.py).
# Không cần route rules; Frappe tự map www/<page>.
# ═══════════════════════════════════════════════════════════════════════════

# P0 read-only + deep-link → KHÔNG doc_events ghi sổ.
# (P1: scheduler_events daily snapshot cảnh báo + email digest.)

# ═══════════════════════════════════════════════════════════════════════════
# MISA meInvoice — sinh khóa nối trước khi ghi sổ.
#
# before_submit là thời điểm cuối còn ghi được field thường. Hàm bọc try/except
# toàn bộ: tích hợp MISA hỏng KHÔNG được chặn kế toán ghi sổ.
# Chưa bật scheduler_events — job theo lịch chỉ bật sau khi chạy tay đạt.
# ═══════════════════════════════════════════════════════════════════════════
doc_events = {
    "Sales Invoice": {
        "before_submit": "ketoan.api.misa_sync.ensure_ref_id",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # Kênh MT — đồng bộ trạng thái bút toán về bảng kê nguồn.
    #
    # VÌ SAO cần: `MT Payment Advice.je_state` suy từ docstatus của các Journal
    # Entry mang `custom_mt_source_name`. Kế toán hoàn toàn có thể submit/cancel
    # bút toán THẲNG TRÊN DESK, không qua portal — thiếu hook thì bảng kê đứng
    # mãi ở "Đã sinh nháp" trong khi bút toán đã ghi sổ, và màn hình nói dối.
    #
    # Hàm bọc try/except toàn bộ: tích hợp MT hỏng KHÔNG được chặn việc ghi sổ.
    # Nó dùng db_set chứ không save() — save() sẽ chạy lại validate() của bảng
    # kê và ném lỗi ngược vào chính giao dịch submit đang chạy.
    # ═══════════════════════════════════════════════════════════════════════
    "Journal Entry": {
        "on_submit": "ketoan.api.mt_je.sync_advice_state",
        "on_cancel": "ketoan.api.mt_je.sync_advice_state",
    },
}

# Job hỏi số hóa đơn. Đăng ký sẵn nhưng BẤT HOẠT: hàm dừng ở dòng đầu khi
# MISA Settings.enable_auto_sync = 0 (mặc định). Chỉ bật sau khi chạy tay đạt.
#
# Chạy 30 phút/lần trong GIỜ HÀNH CHÍNH, vì xuất và ký hóa đơn chỉ diễn ra
# trong khung đó. Hai dòng cron ghép lại đúng 7:30 → 17:30:
#     "30 7"      → 7:30
#     "0,30 8-17" → 8:00, 8:30, … 17:00, 17:30
# Dùng "0,30 7-17" cho gọn thì dư một lượt 7:00, nên tách làm hai cho khớp.
#
# Cron của Frappe tính theo MÚI GIỜ khai ở System Settings, không phải giờ máy
# chủ. Khai sai múi giờ là cả khung giờ lệch mà không có gì báo — vì vậy
# `scheduled_poll_pending` còn tự kiểm khung giờ lần nữa theo MISA Settings.
#
# Ngoài khung giờ KHÔNG mất dữ liệu: hóa đơn ký muộn sẽ được lượt sáng hôm sau
# quét lại, vì `poll_pending` nhìn lùi `lookback_days` (mặc định 60 ngày).
scheduler_events = {
    "cron": {
        "30 7 * * *": [
            "ketoan.api.misa_sync.scheduled_poll_pending",
        ],
        "0,30 8-17 * * *": [
            "ketoan.api.misa_sync.scheduled_poll_pending",
        ],
    },
}
