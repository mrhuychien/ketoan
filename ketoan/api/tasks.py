"""Việc cần xử lý — gom theo nghiệp vụ, lọc theo vai trò của user.

Mỗi nhóm: {group, icon, items:[{label, count, route|href, severity}]}.
Chỉ trả nhóm user có quyền; từng đếm bọc try/except (thiếu doctype/field thì bỏ qua).
"""

import frappe
from frappe.utils import flt, today

from ketoan.api._guard import (
    guard_view, capabilities, resolve_company, get_settings, channel_group_clause,
)
from ketoan.utils import je_remark_field


def _count(sql: str, params) -> int:
    try:
        return int(frappe.db.sql(sql, params)[0][0] or 0)
    except Exception:
        return 0


def _late_bonus_task(company: str) -> dict:
    """Số NPP đang trả chậm quá ân hạn → thưởng 2% bị phạt/cắt (bàn NPP)."""
    try:
        from ketoan.api.npp import get_debts
        n = int(get_debts(company).get("late_count") or 0)
    except Exception:
        n = 0
    return {"label": "NPP đang trễ hạn — nguy cơ phạt/cắt thưởng", "count": n,
            "route": "/doi-chieu-npp?tab=debt", "severity": "warning"}


def _selling_price_task(company: str, channel: str) -> dict:
    """Item 'giá bán lệch bảng giá không có Pricing Rule' cho 1 kênh (30 ngày)."""
    try:
        from ketoan.api.prices import get_selling_price_watch
        n = int(get_selling_price_watch(company, channel=channel, days=30)["alert_count"])
    except Exception:
        n = 0
    return {"label": "Giá bán lệch bảng giá (không có Pricing Rule)", "count": n,
            "route": f"/cong-no/{channel}?tab=gia", "severity": "warning"}


def _overdue_customers(company: str, channel: str, b1: int) -> int:
    """Số khách của kênh có hóa đơn quá hạn > b1 ngày."""
    params = {"company": company, "today": today(), "b1": b1}
    ch = channel_group_clause(channel, params, alias="c")
    return _count(
        f"""
        SELECT COUNT(DISTINCT si.customer)
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s AND si.outstanding_amount > 0
          AND DATEDIFF(%(today)s, COALESCE(si.due_date, si.posting_date)) > %(b1)s
          AND {ch}
        """,
        params,
    )


@frappe.whitelist()
def get_tasks(company: str | None = None) -> dict:
    """Danh sách việc cần xử lý nhóm theo nghiệp vụ (theo vai trò user)."""
    guard_view()
    company = resolve_company(company)
    caps = capabilities()
    s = get_settings()
    b1 = int(s.aging_bucket_1 or 30)
    npp_group = s.npp_customer_group or "NPP"
    field = je_remark_field()
    has_einv = frappe.db.has_column("Sales Invoice", "vn_einvoice_number")

    groups = []

    def add(group, icon, ws, items):
        items = [i for i in items if i and i.get("count")]
        if items:
            groups.append({"group": group, "icon": icon, "ws": ws, "items": items})

    # ── Kế toán NPP ─────────────────────────────────────────────────────────
    if caps.get("npp"):
        items = []
        # Hàng trả lại đang xử lý (SI return nháp — chờ HĐ NPP hoặc chờ duyệt)
        n = _count(
            """SELECT COUNT(*) FROM `tabSales Invoice` si
               JOIN `tabCustomer` c ON c.name = si.customer
               WHERE si.is_return = 1 AND si.docstatus = 0 AND si.company = %(company)s
                 AND c.customer_group = %(group)s""",
            {"company": company, "group": npp_group},
        )
        items.append({"label": "Cần xử lý hàng trả lại", "count": n, "route": "/doi-chieu-npp?tab=trahang", "severity": "warning"})
        # Bút toán JE đang treo (chiết khấu, thưởng, hỗ trợ... — JE nháp gắn khách NPP)
        n = _count(
            """SELECT COUNT(DISTINCT je.name) FROM `tabJournal Entry` je
               JOIN `tabJournal Entry Account` a ON a.parent = je.name AND a.party_type = 'Customer'
               JOIN `tabCustomer` c ON c.name = a.party AND c.customer_group = %(group)s
               WHERE je.docstatus = 0 AND je.company = %(company)s""",
            {"company": company, "group": npp_group},
        )
        items.append({"label": "Cần hoàn tất bút toán JE (chiết khấu, thưởng, hỗ trợ...)", "count": n, "route": "/doi-chieu-npp?tab=butoan", "severity": "warning"})
        # Cần xuất hóa đơn điện tử
        if has_einv:
            n = _count(
                """SELECT COUNT(*) FROM `tabSales Invoice` si
                   JOIN `tabCustomer` c ON c.name = si.customer
                   WHERE si.docstatus = 1 AND si.is_return = 0 AND si.company = %(company)s
                     AND c.customer_group = %(group)s
                     AND si.posting_date >= DATE_SUB(%(today)s, INTERVAL 60 DAY)
                     AND IFNULL(si.vn_einvoice_number, '') = ''""",
                {"company": company, "group": npp_group, "today": today()},
            )
            items.append({"label": "Cần xuất hóa đơn điện tử", "count": n, "route": "/doi-chieu-npp?tab=einvoice", "severity": "danger"})
        # Cần thu / đối chiếu công nợ
        n = _overdue_customers(company, "npp", b1)
        items.append({"label": f"Cần đối chiếu / thu công nợ (quá {b1} ngày)", "count": n, "route": "/doi-chieu-npp?tab=due", "severity": "danger"})
        # NPP trả chậm ảnh hưởng thưởng 2% (phạt/cắt) — kế toán soát trước khi tạo bút toán.
        items.append(_late_bonus_task(company))
        items.append(_selling_price_task(company, "npp"))
        add("Kế toán NPP", "fa-handshake", "npp", items)
        del items  # tránh dùng nhầm ở nhóm sau

    # ── Kênh MT / Du lịch, Khác ─────────────────────────────────────────────
    if caps.get("mt"):
        n = _overdue_customers(company, "mt", b1)
        add("Kế toán MT", "fa-store", "mt", [
            {"label": f"Khách MT quá hạn (> {b1} ngày) cần thu/đối chiếu", "count": n, "route": "/cong-no/mt", "severity": "danger"},
            _selling_price_task(company, "mt"),
        ])
    if caps.get("travel"):
        n = _overdue_customers(company, "khac", b1)
        add("Kế toán Du lịch, Khác", "fa-umbrella-beach", "travel", [
            {"label": f"Khách quá hạn (> {b1} ngày) cần thu/đối chiếu", "count": n, "route": "/cong-no/khac", "severity": "danger"},
            _selling_price_task(company, "khac"),
        ])

    # ── Kế toán mua hàng ────────────────────────────────────────────────────
    if caps.get("purchase"):
        items = []
        n = _count(
            """SELECT COUNT(*) FROM `tabPurchase Invoice`
               WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
                 AND COALESCE(due_date, posting_date) <= DATE_ADD(%(today)s, INTERVAL 7 DAY)""",
            {"company": company, "today": today()},
        )
        items.append({"label": "Hóa đơn NCC đến hạn/quá hạn thanh toán", "count": n, "route": "/cong-no-ncc?tab=due", "severity": "danger"})
        n = _count(
            """SELECT COUNT(*) FROM (
                 SELECT supplier, bill_no FROM `tabPurchase Invoice`
                 WHERE docstatus < 2 AND company = %(company)s AND IFNULL(bill_no,'') != ''
                 GROUP BY supplier, bill_no HAVING COUNT(*) > 1) t""",
            {"company": company},
        )
        items.append({"label": "Nghi trùng hóa đơn NCC cần kiểm tra", "count": n, "route": "/cong-no-ncc?tab=control", "severity": "danger"})
        n = _count(
            """SELECT COUNT(*) FROM `tabPurchase Invoice` pi
               WHERE pi.docstatus = 1 AND pi.company = %(company)s AND IFNULL(pi.update_stock,0)=0
                 AND NOT EXISTS (SELECT 1 FROM `tabPurchase Invoice Item` pii
                                 WHERE pii.parent = pi.name AND IFNULL(pii.purchase_receipt,'') != '')""",
            {"company": company},
        )
        items.append({"label": "Hóa đơn mua thiếu liên kết nhập kho (khớp 3 chiều)", "count": n, "route": "/cong-no-ncc?tab=control", "severity": "warning"})
        # Giá nhập nguyên liệu biến động mạnh (quét PI 90 ngày, ngưỡng mặc định 10%).
        try:
            from ketoan.api.prices import get_price_watch
            n = int(get_price_watch(company, days=90)["alert_count"])
        except Exception:
            n = 0
        items.append({"label": "Giá nhập nguyên liệu biến động mạnh", "count": n, "route": "/cong-no-ncc?tab=gia", "severity": "danger"})
        add("Kế toán mua hàng", "fa-truck-field", "purchase", items)

    # ── Kế toán tiền lương ──────────────────────────────────────────────────
    if caps.get("payroll"):
        items = []
        for dt, label in (("SalaryDay", "Phiếu công nhật nháp cần duyệt"), ("SalaryProduct", "Phiếu công khoán nháp cần duyệt")):
            if frappe.db.exists("DocType", dt):
                n = _count(f"SELECT COUNT(*) FROM `tab{dt}` WHERE docstatus = 0", {})
                items.append({"label": label, "count": n, "route": "/luong", "severity": "warning"})
        add("Kế toán tiền lương", "fa-money-check-dollar", "payroll", items)

    # ── Kế toán hạch toán ───────────────────────────────────────────────────
    if caps.get("gl"):
        n = _count(
            "SELECT COUNT(*) FROM `tabJournal Entry` WHERE docstatus = 0 AND company = %(company)s",
            {"company": company},
        )
        add("Kế toán hạch toán", "fa-book", "gl", [
            {"label": "Bút toán nháp cần kiểm tra & ghi sổ", "count": n, "href": "/desk/journal-entry?docstatus=0", "severity": "warning"},
        ])

    # ── Kế toán trưởng ──────────────────────────────────────────────────────
    if caps.get("chief"):
        items = []
        # Hồ sơ đối trừ CHỜ KTT DUYỆT = chứng từ nháp ĐÃ có đính kèm.
        n1 = _count(
            """SELECT COUNT(*) FROM `tabSales Invoice` si
               WHERE si.is_return = 1 AND si.docstatus = 0 AND si.company = %(company)s
                 AND EXISTS (SELECT 1 FROM `tabFile` f
                             WHERE f.attached_to_doctype='Sales Invoice' AND f.attached_to_name=si.name)""",
            {"company": company},
        )
        n2 = _count(
            """SELECT COUNT(DISTINCT je.name) FROM `tabJournal Entry` je
               JOIN `tabJournal Entry Account` a ON a.parent = je.name AND a.party_type = 'Customer'
               JOIN `tabCustomer` c ON c.name = a.party AND c.customer_group = %(group)s
               WHERE je.docstatus = 0 AND je.company = %(company)s
                 AND EXISTS (SELECT 1 FROM `tabFile` f
                             WHERE f.attached_to_doctype='Journal Entry' AND f.attached_to_name=je.name)""",
            {"company": company, "group": npp_group},
        )
        items.append({"label": "Trả hàng chờ KTT duyệt", "count": n1, "route": "/doi-chieu-npp?tab=trahang", "severity": "danger"})
        items.append({"label": "Bút toán JE chờ KTT duyệt", "count": n2, "route": "/doi-chieu-npp?tab=butoan", "severity": "danger"})
        try:
            from ketoan.api.alerts import get_alerts
            items.append({"label": "Cảnh báo tác nghiệp", "count": len(get_alerts(company)["alerts"]), "route": "/canh-bao", "severity": "warning"})
        except Exception:
            pass
        add("Kế toán trưởng", "fa-user-tie", "chief", items)

    total = sum(i["count"] for g in groups for i in g["items"])
    return {"company": company, "as_of": today(), "groups": groups, "total": total}
