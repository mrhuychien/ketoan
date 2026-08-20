"""Patch: seed 3 dòng `MT Account Map` mặc định cho MỖI công ty.

Theo §4 SOP (chốt 20/08/2026):

    Nhận thanh toán        Nợ 112              Có 131
    Chiết khấu mình xuất   Nợ 5211 + 33311     Có 131
    Phí chuỗi xuất         Nợ 6411 + 1331      Có 131

DÒ TÀI KHOẢN THEO SỐ HIỆU ĐẦU trong Chart of Accounts của chính công ty đó
(`account_number LIKE '112%'`). KHÔNG tìm được, hoặc tìm được NHIỀU hơn một →
tạo dòng với account ĐỂ TRỐNG + ghi log. Tuyệt đối không đoán: sinh bút toán
vào sai tài khoản còn tệ hơn không sinh, vì nó nằm im trong sổ tới lúc quyết
toán mới lộ.

Dòng để trống KHÔNG dùng được — `mt_account_map.resolve()` throw khi thiếu TK Nợ
hoặc TK Có, nên kế toán buộc phải vào điền trước khi sinh bút toán đầu tiên.

Idempotent: đã có dòng cho (sự kiện, chuỗi rỗng, công ty) thì BỎ QUA, không đè.
Kế toán đã chỉnh tài khoản rồi mà patch chạy lại đè về giá trị dò máy là mất
công sức của họ mà không ai hay.
"""

import frappe

# (event, tiền tố TK Nợ, tiền tố TK thuế | None, tiền tố TK Có)
SEED = (
    ("Nhận thanh toán", "112", None, "131"),
    ("Chiết khấu mình xuất", "5211", "33311", "131"),
    ("Phí chuỗi xuất", "6411", "1331", "131"),
)


def _find_account(company, prefix):
    """TK LÁ duy nhất của công ty có số hiệu bắt đầu bằng `prefix`.

    Trả (account | None, lý do). Nhiều ứng viên -> None: chọn hộ một trong ba
    tài khoản ngân hàng là ghi tiền vào nhầm ngân hàng.
    """
    if not prefix:
        return None, ""
    rows = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "disabled": 0,
                 "account_number": ("like", prefix + "%")},
        fields=["name", "account_number"],
        limit_page_length=0)
    if not rows:
        return None, "không có TK nào số hiệu %s…" % prefix
    if len(rows) > 1:
        return None, "có %d TK số hiệu %s… (%s) — không chọn hộ" % (
            len(rows), prefix, ", ".join(r.account_number for r in rows[:4]))
    return rows[0].name, ""


def execute():
    if not frappe.db.table_exists("MT Account Map"):
        # Chưa migrate xong DocType — patch chạy trước khi bảng có là chuyện
        # bình thường ở lần cài đầu; lần migrate sau patch đã đánh dấu xong nên
        # sẽ KHÔNG chạy lại. Ghi log để quản trị biết phải seed tay.
        frappe.log_error("Bảng MT Account Map chưa tồn tại — bỏ qua seed, "
                         "kế toán khai tay trong MT Account Map.",
                         "ketoan: mt_account_map_seed (v0_0_15)")
        return

    companies = frappe.get_all("Company", pluck="name") or []
    created, blanks = 0, []

    for company in companies:
        for event, d_pre, t_pre, c_pre in SEED:
            if frappe.db.exists("MT Account Map",
                                {"event": event, "chain": "", "company": company}):
                continue

            debit, why_d = _find_account(company, d_pre)
            tax, why_t = _find_account(company, t_pre)
            credit, why_c = _find_account(company, c_pre)

            missing = [w for w in (why_d, why_t, why_c) if w]
            note = None
            if missing:
                note = ("Patch v0_0_15 không dò được tài khoản, KHÔNG đoán:\n"
                        + "\n".join("• " + m for m in missing)
                        + "\nKế toán điền tay trước khi sinh bút toán.")
                blanks.append("%s / %s: %s" % (company, event, " · ".join(missing)))

            try:
                doc = frappe.new_doc("MT Account Map")
                doc.event = event
                doc.chain = ""              # dòng MẶC ĐỊNH, áp cho mọi chuỗi
                doc.company = company
                doc.debit_account = debit
                doc.tax_account = tax
                doc.credit_account = credit
                doc.active = 1
                doc.note = note
                # `ignore_mandatory`: dòng seed có thể còn thiếu TK, và đó là ca
                # ĐÚNG Ý — thà có dòng trống để kế toán thấy và điền, còn hơn
                # không có gì rồi tới lúc sinh bút toán mới phát hiện thiếu.
                doc.flags.ignore_mandatory = True
                doc.insert(ignore_permissions=True)
                created += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(),
                                 "ketoan: mt_account_map_seed %s/%s" % (company, event))

    if blanks:
        frappe.log_error("Dòng MT Account Map tạo ra còn THIẾU tài khoản:\n"
                         + "\n".join(blanks),
                         "ketoan: mt_account_map_seed (v0_0_15)")
    frappe.logger().info("ketoan: seed %d dòng MT Account Map cho %d công ty (v0_0_15)"
                         % (created, len(companies)))
    frappe.db.commit()
