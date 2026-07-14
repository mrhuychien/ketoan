"""Whitelisted methods — phân hệ Phải thu (công nợ NPP/khách hàng).

Semantics (theo frappe-sales-analytics):
- Công nợ = `Sales Invoice.outstanding_amount` (docstatus=1) — ERPNext tự duy trì
  sau khi phân bổ thanh toán. KHÔNG lọc `is_opening` (nợ đầu kỳ là nợ thật).
- Aging theo `COALESCE(due_date, posting_date)` so với hôm nay.
- DSO ≈ nợ / doanh thu kỳ × số ngày cửa sổ.
Tất cả read-only, guard ở dòng đầu, SQL parameterized.
"""

import frappe
from frappe.utils import flt, today, getdate

from ketoan.api._guard import (
    guard_channel, guard_sales_any, allowed_channels, channel_group_clause,
    resolve_company, get_settings, is_chief,
)


@frappe.whitelist()
def get_ar_summary(company: str | None = None, limit: int = 200, channel: str = "tat-ca") -> dict:
    """Bảng kê công nợ phải thu theo khách hàng + tổng, lọc theo KÊNH
    (npp / mt / khac theo Customer Group; 'tat-ca' chỉ cho kế toán trưởng)."""
    guard_channel(channel)
    company = resolve_company(company)
    limit = min(int(limit or 200), 1000)

    params = {"company": company, "limit": limit}
    ch_clause = channel_group_clause(channel, params, alias="c")

    # Gộp ở mức khách: tổng outstanding + chứng từ quá hạn lâu nhất.
    # Dùng SQL (group + aggregate) thay ORM cho gọn 1 round-trip.
    rows = frappe.db.sql(
        """
        SELECT si.customer,
               si.customer_name,
               c.customer_group,
               SUM(si.outstanding_amount)              AS outstanding,
               MIN(COALESCE(si.due_date, si.posting_date)) AS earliest_due
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.outstanding_amount > 0
          AND {ch}
        GROUP BY si.customer, si.customer_name, c.customer_group
        ORDER BY SUM(si.outstanding_amount) DESC
        LIMIT %(limit)s
        """.format(ch=ch_clause),
        params,
        as_dict=True,
    )

    t = getdate(today())
    total = 0.0
    for r in rows:
        r["outstanding"] = flt(r["outstanding"])
        total += r["outstanding"]
        r["days_overdue"] = (t - getdate(r["earliest_due"])).days if r["earliest_due"] else 0

    return {"company": company, "channel": channel, "total": total, "count": len(rows), "rows": rows}


@frappe.whitelist()
def get_aging(company: str | None = None, channel: str = "tat-ca") -> dict:
    """Tuổi nợ theo rổ cấu hình (Settings), lọc theo kênh."""
    guard_channel(channel)
    company = resolve_company(company)
    s = get_settings()
    b1, b2, b3 = int(s.aging_bucket_1 or 30), int(s.aging_bucket_2 or 60), int(s.aging_bucket_3 or 90)
    params = {"company": company, "today": today(), "b1": b1, "b2": b2, "b3": b3}
    ch_clause = channel_group_clause(channel, params, alias="c")

    # Bucket bằng CASE trên số ngày quá hạn (DATEDIFF), tham số hoá ngưỡng.
    row = frappe.db.sql(
        """
        SELECT
          SUM(CASE WHEN d <= 0                 THEN o ELSE 0 END) AS current_amt,
          SUM(CASE WHEN d > 0  AND d <= %(b1)s THEN o ELSE 0 END) AS b1_amt,
          SUM(CASE WHEN d > %(b1)s AND d <= %(b2)s THEN o ELSE 0 END) AS b2_amt,
          SUM(CASE WHEN d > %(b2)s AND d <= %(b3)s THEN o ELSE 0 END) AS b3_amt,
          SUM(CASE WHEN d > %(b3)s             THEN o ELSE 0 END) AS over_amt,
          SUM(o) AS total_amt
        FROM (
            SELECT si.outstanding_amount AS o,
                   DATEDIFF(%(today)s, COALESCE(si.due_date, si.posting_date)) AS d
            FROM `tabSales Invoice` si
            LEFT JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1 AND si.company = %(company)s AND si.outstanding_amount > 0
              AND {ch}
        ) t
        """.format(ch=ch_clause),
        params,
        as_dict=True,
    )[0]

    buckets = [
        {"key": "current", "label": "Trong hạn", "amount": flt(row.current_amt)},
        {"key": "b1", "label": f"1–{b1} ngày", "amount": flt(row.b1_amt)},
        {"key": "b2", "label": f"{b1+1}–{b2} ngày", "amount": flt(row.b2_amt)},
        {"key": "b3", "label": f"{b2+1}–{b3} ngày", "amount": flt(row.b3_amt)},
        {"key": "over", "label": f">{b3} ngày", "amount": flt(row.over_amt)},
    ]
    return {"company": company, "channel": channel, "buckets": buckets, "total": flt(row.total_amt)}


@frappe.whitelist()
def get_customer_detail(customer: str, company: str | None = None) -> dict:
    """360° công nợ 1 khách: hóa đơn outstanding, hạn mức, khoản thu chưa khớp."""
    guard_sales_any()
    if not customer:
        frappe.throw("Thiếu mã khách hàng")
    company = resolve_company(company)

    info = frappe.db.get_value(
        "Customer", customer, ["customer_name", "customer_group", "territory"], as_dict=True
    ) or {}

    # "Chỉ xem nếu liên quan": khách phải thuộc kênh user phụ trách.
    if not is_chief():
        st = get_settings()
        npp_g = st.npp_customer_group or "NPP"
        mt_g = st.get("mt_customer_group") or "MT"
        grp = info.get("customer_group") or ""
        ch = "npp" if grp == npp_g else ("mt" if grp == mt_g else "khac")
        if ch not in allowed_channels():
            frappe.throw("Khách hàng này thuộc kênh khác — bạn không có quyền xem", frappe.PermissionError)

    invoices = frappe.db.sql(
        """
        SELECT name, posting_date, due_date, grand_total, outstanding_amount, status,
               DATEDIFF(%(today)s, COALESCE(due_date, posting_date)) AS days_overdue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND customer = %(customer)s
          AND outstanding_amount > 0
        ORDER BY COALESCE(due_date, posting_date) ASC
        """,
        {"today": today(), "company": company, "customer": customer},
        as_dict=True,
    )
    for inv in invoices:
        inv["grand_total"] = flt(inv["grand_total"])
        inv["outstanding_amount"] = flt(inv["outstanding_amount"])

    outstanding = sum(i["outstanding_amount"] for i in invoices)

    # Hạn mức tín dụng: Customer Credit Limit là child table (theo company) → đọc an toàn.
    credit_limit = _get_credit_limit(customer, company)

    # Khoản thu chưa khớp (advance) của khách.
    unallocated = flt(
        frappe.db.sql(
            """
            SELECT SUM(unallocated_amount) FROM `tabPayment Entry`
            WHERE docstatus = 1 AND party_type = 'Customer' AND party = %(customer)s
              AND company = %(company)s AND unallocated_amount > 0
            """,
            {"customer": customer, "company": company},
        )[0][0]
        or 0
    )

    return {
        "customer": customer,
        "customer_name": info.get("customer_name"),
        "customer_group": info.get("customer_group"),
        "territory": info.get("territory"),
        "outstanding": outstanding,
        "credit_limit": credit_limit,
        "over_limit": bool(credit_limit and outstanding > credit_limit),
        "unallocated_payment": unallocated,
        "invoices": invoices,
        "tasks": _customer_tasks(customer, company),
    }


def _customer_tasks(customer: str, company: str) -> dict:
    """Việc cần xử lý với riêng 1 khách (bọc try/except từng đếm)."""
    from ketoan.utils import je_remark_field

    def cnt(sql, params):
        try:
            return int(frappe.db.sql(sql, params)[0][0] or 0)
        except Exception:
            return 0

    tasks = {}
    # Hàng trả lại đang xử lý (SI return nháp của khách).
    tasks["pending_returns"] = cnt(
        """SELECT COUNT(*) FROM `tabSales Invoice`
           WHERE is_return = 1 AND docstatus = 0 AND company = %(company)s AND customer = %(customer)s""",
        {"company": company, "customer": customer},
    )
    # Bút toán JE đang treo (chiết khấu, thưởng, hỗ trợ... — JE nháp có party = khách).
    tasks["pending_je"] = cnt(
        """SELECT COUNT(DISTINCT je.name) FROM `tabJournal Entry` je
           JOIN `tabJournal Entry Account` a ON a.parent = je.name
           WHERE je.docstatus = 0 AND je.company = %(company)s
             AND a.party_type = 'Customer' AND a.party = %(customer)s""",
        {"company": company, "customer": customer},
    )
    # Chưa xuất hóa đơn điện tử (60 ngày gần nhất).
    if frappe.db.has_column("Sales Invoice", "vn_einvoice_number"):
        tasks["missing_einvoice"] = cnt(
            """SELECT COUNT(*) FROM `tabSales Invoice`
               WHERE docstatus = 1 AND is_return = 0 AND company = %(company)s AND customer = %(customer)s
                 AND posting_date >= DATE_SUB(%(today)s, INTERVAL 60 DAY)
                 AND IFNULL(vn_einvoice_number, '') = ''""",
            {"company": company, "customer": customer, "today": today()},
        )
    else:
        tasks["missing_einvoice"] = 0
    return tasks


@frappe.whitelist()
def get_dso(company: str | None = None, channel: str = "tat-ca") -> dict:
    """DSO ước tính = tổng nợ / doanh thu kỳ × số ngày cửa sổ (toàn bộ hoặc theo kênh)."""
    guard_channel(channel)
    company = resolve_company(company)
    window = int(get_settings().dso_window_days or 365)

    debt = flt(
        frappe.db.sql(
            """
            SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
            """,
            {"company": company},
        )[0][0]
        or 0
    )

    revenue = frappe.db.sql(
        """
        SELECT SUM(base_grand_total) AS rev
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
          AND IFNULL(is_opening, 'No') != 'Yes'
          AND IFNULL(is_return, 0) = 0
          AND posting_date >= DATE_SUB(%(today)s, INTERVAL %(window)s DAY)
        """,
        {"company": company, "today": today(), "window": window},
        as_dict=True,
    )[0]
    rev = flt(revenue.rev)

    dso = round(debt / rev * window, 1) if rev else None
    return {"company": company, "debt": debt, "revenue_window": rev, "window_days": window, "dso": dso}


def _get_credit_limit(customer: str, company: str) -> float:
    """Hạn mức tín dụng của khách theo company. Bọc try/except (nhiều site không set)."""
    try:
        rows = frappe.get_all(
            "Customer Credit Limit",
            filters={"parent": customer, "parenttype": "Customer", "company": company},
            fields=["credit_limit"],
            limit=1,
        )
        if rows and rows[0].credit_limit:
            return flt(rows[0].credit_limit)
        # fallback: trường credit_limit cũ trên Customer (nếu có)
        legacy = frappe.db.get_value("Customer", customer, "credit_limit")
        return flt(legacy) if legacy else 0.0
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Sổ cái giao dịch 1 khách + việc cần làm gắn từng chứng từ
# ═══════════════════════════════════════════════════════════════════════════

def _assert_customer_channel(customer: str) -> dict:
    """Trả info khách + chặn xem khách kênh khác (trừ kế toán trưởng)."""
    info = frappe.db.get_value(
        "Customer", customer, ["customer_name", "customer_group", "territory"], as_dict=True
    ) or {}
    if not is_chief():
        st = get_settings()
        npp_g = st.npp_customer_group or "NPP"
        mt_g = st.get("mt_customer_group") or "MT"
        grp = info.get("customer_group") or ""
        ch = "npp" if grp == npp_g else ("mt" if grp == mt_g else "khac")
        if ch not in allowed_channels():
            frappe.throw("Khách hàng này thuộc kênh khác — bạn không có quyền xem", frappe.PermissionError)
    return info


@frappe.whitelist()
def get_customer_ledger(customer: str, company: str | None = None,
                        from_date: str | None = None, to_date: str | None = None) -> dict:
    """Toàn bộ giao dịch của khách trên TK phải thu (gộp theo chứng từ, số dư lũy kế)
    + TODO gắn từng chứng từ: chưa xuất HĐĐT, quá hạn cần thu, khoản thu chưa khớp.
    Kèm chứng từ NHÁP đang treo (SI trả về, JE chiết khấu) — không tính vào số dư.
    """
    guard_sales_any()
    if not customer:
        frappe.throw("Thiếu mã khách hàng")
    company = resolve_company(company)
    _assert_customer_channel(customer)
    to_date = to_date or today()

    # Mệnh đề TK phải thu: account cụ thể (Settings) hoặc account_type Receivable.
    st = get_settings()
    params = {"company": company, "customer": customer, "to": to_date}
    if st.receivable_account:
        params["racc"] = st.receivable_account
        racc = "gle.account = %(racc)s"
    else:
        racc = "acc.account_type = 'Receivable'"

    # Dư đầu kỳ (trước from_date).
    opening = 0.0
    if from_date:
        params["from"] = from_date
        opening = flt(frappe.db.sql(
            f"""SELECT SUM(gle.debit - gle.credit)
                FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
                  AND gle.party_type = 'Customer' AND gle.party = %(customer)s
                  AND {racc} AND gle.posting_date < %(from)s""",
            params,
        )[0][0] or 0)

    from_clause = "AND gle.posting_date >= %(from)s" if from_date else ""
    rows = frappe.db.sql(
        f"""SELECT MIN(gle.posting_date) AS posting_date, gle.voucher_type, gle.voucher_no,
                   SUM(gle.debit) AS debit, SUM(gle.credit) AS credit
            FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
              AND gle.party_type = 'Customer' AND gle.party = %(customer)s
              AND {racc} AND gle.posting_date <= %(to)s {from_clause}
            GROUP BY gle.voucher_type, gle.voucher_no
            ORDER BY MIN(gle.posting_date) ASC, gle.voucher_no ASC
            LIMIT 1000""",
        params,
        as_dict=True,
    )

    # ── Gom info để gắn TODO ────────────────────────────────────────────────
    has_einv = frappe.db.has_column("Sales Invoice", "vn_einvoice_number")
    si_names = [r.voucher_no for r in rows if r.voucher_type == "Sales Invoice"]
    si_info = {}
    if si_names:
        fields = ["name", "outstanding_amount", "due_date", "posting_date", "is_return", "status"]
        if has_einv:
            fields.append("vn_einvoice_number")
        for x in frappe.get_all("Sales Invoice", filters={"name": ["in", si_names]}, fields=fields, limit=1000):
            si_info[x.name] = x
    pe_names = [r.voucher_no for r in rows if r.voucher_type == "Payment Entry"]
    pe_unalloc = {}
    if pe_names:
        for x in frappe.get_all("Payment Entry", filters={"name": ["in", pe_names]},
                                fields=["name", "unallocated_amount"], limit=1000):
            pe_unalloc[x.name] = flt(x.unallocated_amount)

    t = getdate(today())
    running = opening
    total_debit = 0.0
    total_credit = 0.0
    out = []
    for r in rows:
        running += flt(r.debit) - flt(r.credit)
        total_debit += flt(r.debit)
        total_credit += flt(r.credit)
        todos = []
        if r.voucher_type == "Sales Invoice":
            si = si_info.get(r.voucher_no)
            if si:
                if has_einv and not si.get("is_return") and not (si.get("vn_einvoice_number") or "").strip():
                    todos.append({"icon": "fa-file-circle-exclamation", "label": "Cần xuất HĐĐT", "sev": "red"})
                if flt(si.outstanding_amount) > 0:
                    dd = (t - getdate(si.due_date or si.posting_date)).days
                    if dd > 0:
                        todos.append({"icon": "fa-hand-holding-dollar", "label": f"Quá hạn {dd} ngày — cần thu", "sev": "red"})
                    else:
                        todos.append({"icon": "fa-hourglass-half", "label": "Còn nợ, trong hạn", "sev": "yellow"})
        elif r.voucher_type == "Payment Entry":
            if pe_unalloc.get(r.voucher_no, 0) > 0:
                todos.append({"icon": "fa-link-slash", "label": "Chưa khớp hóa đơn", "sev": "yellow"})
        out.append({
            "posting_date": str(r.posting_date), "voucher_type": r.voucher_type,
            "voucher_no": r.voucher_no, "debit": flt(r.debit), "credit": flt(r.credit),
            "balance": running, "docstatus": 1, "todos": todos,
            "route": f"/app/{frappe.scrub(r.voucher_type).replace('_', '-')}/{r.voucher_no}",
        })

    # ── Chứng từ NHÁP đang treo (không vào số dư) ───────────────────────────
    drafts = []
    for x in frappe.get_all("Sales Invoice",
                            filters={"is_return": 1, "docstatus": 0, "company": company, "customer": customer},
                            fields=["name", "posting_date", "grand_total"], limit=50):
        has_att = frappe.db.exists("File", {"attached_to_doctype": "Sales Invoice", "attached_to_name": x.name})
        drafts.append({
            "posting_date": str(x.posting_date), "voucher_type": "Sales Invoice (trả hàng)",
            "voucher_no": x.name, "debit": 0, "credit": abs(flt(x.grand_total)),
            "balance": None, "docstatus": 0,
            "todos": [{"icon": "fa-rotate-left",
                       "label": "Chờ KTT duyệt trả hàng" if has_att else "Chờ hóa đơn NPP (trả hàng)",
                       "sev": "red" if has_att else "yellow"}],
            "route": f"/app/sales-invoice/{x.name}",
        })
    from ketoan.utils import je_remark_field
    fieldr = je_remark_field()
    je_drafts = frappe.db.sql(
        f"""SELECT DISTINCT je.name, je.posting_date, je.total_debit, je.`{fieldr}` AS remark
            FROM `tabJournal Entry` je
            JOIN `tabJournal Entry Account` a ON a.parent = je.name
            WHERE je.docstatus = 0 AND je.company = %(company)s
              AND a.party_type = 'Customer' AND a.party = %(customer)s
            LIMIT 50""",
        {"company": company, "customer": customer},
        as_dict=True,
    )
    for x in je_drafts:
        has_att = frappe.db.exists("File", {"attached_to_doctype": "Journal Entry", "attached_to_name": x.name})
        is_ck = "[CK2-" in (x.remark or "")
        vt = "Bút toán JE (chiết khấu)" if is_ck else "Bút toán JE (thưởng/hỗ trợ...)"
        drafts.append({
            "posting_date": str(x.posting_date), "voucher_type": vt,
            "voucher_no": x.name, "debit": 0, "credit": flt(x.total_debit),
            "balance": None, "docstatus": 0,
            "todos": [{"icon": "fa-percent" if is_ck else "fa-gift",
                       "label": "Chờ KTT duyệt bút toán" if has_att else "Chờ hóa đơn NPP (bút toán JE)",
                       "sev": "red" if has_att else "yellow"}],
            "route": f"/app/journal-entry/{x.name}",
        })

    return {
        "customer": customer, "company": company,
        "from_date": from_date, "to_date": to_date,
        "opening": opening, "rows": out, "drafts": drafts,
        "total_debit": total_debit, "total_credit": total_credit, "closing": running,
    }
