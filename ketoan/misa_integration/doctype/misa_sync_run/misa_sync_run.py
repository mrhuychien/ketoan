"""MISA Sync Run — log 1 lần chạy đồng bộ (poll / pull / reconcile).

Chỉ là bản ghi nhật ký: không submittable, không tác động nghiệp vụ.
error_log CHỈ chứa mã lỗi + mô tả đã lọc — cấm ghi token/mật khẩu vào đây.
"""

from frappe.model.document import Document
from frappe.utils import now_datetime


class MISASyncRun(Document):
    def before_insert(self):
        if not self.started_at:
            self.started_at = now_datetime()
        if not self.status:
            self.status = "Đang chạy"

    def append_error(self, message: str):
        """Nối 1 dòng lỗi vào nhật ký (giữ tối đa 200 dòng cuối cho khỏi phình)."""
        lines = (self.error_log or "").splitlines()
        lines.append(f"[{now_datetime()}] {message}")
        self.error_log = "\n".join(lines[-200:])

    def finish(self, status: str = "Thành công"):
        """Chốt lần chạy. Dùng db_set để không đụng validate khi job đang trong transaction."""
        self.db_set(
            {"status": status, "finished_at": now_datetime()},
            update_modified=False,
        )
