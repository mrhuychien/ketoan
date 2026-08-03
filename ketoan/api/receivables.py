"""Whitelisted methods — phân hệ Phải thu (công nợ NPP/khách hàng).

NGUỒN SỰ THẬT = GL ENTRY (không phải hóa đơn):
- Công nợ khách = SUM(debit - credit) trên GL Entry các TK phải thu (theo
  Settings.receivable_account, không cấu hình thì account_type='Receivable')
  với party_type='Customer' — gồm cả nợ đầu kỳ, JE, khoản thu trước (số âm),
  không chỉ Sales Invoice.outstanding_amount.
- Aging: gộp GL theo chứng từ gốc (COALESCE(against_voucher, voucher_no)) →
  số dư mở từng chứng từ, tuổi theo due_date của SI (nếu là SI) hoặc ngày
  phát sinh. Tổng aging khớp tổng công nợ GL.
- DSO ≈ nợ GL / doanh thu kỳ × số ngày cửa sổ.
Tất cả read-only, guard ở dòng đầu, SQL parameterized.
"""

import frappe
from frappe.utils import flt, today, getdate

from ketoan.utils import format_vnd
from ketoan.api._guard import (
    guard_channel, guard_sales_any, allowed_channels, channel_group_clause,
    resolve_company, get_settings, is_chief,
)


def _racc_clause(params: dict) -> str:
    """Mệnh đề TK phải thu: TK cụ thể từ Settings hoặc account_type Receivable.
    (Query phải JOIN `tabAccount` acc ON acc.name = gle.account.)"""
    st = get_settings()
    if st.receivable_account:
        params["racc"] = st.receivable_account
        return "gle.account = %(racc)s"
    return "acc.account_type = 'Receivable'"


# ═══════════════════════════════════════════════════════════════════════════
# Hóa đơn CÒN NỢ — phân bổ số dư GL theo FIFO (tiền trả cấn trừ hóa đơn CŨ trước)
#
# KHÔNG dùng Sales Invoice.outstanding_amount: khách trả tiền qua bút toán JE
# hoặc phiếu thu chưa khớp hóa đơn thì trường này vẫn giữ nguyên → hóa đơn đã
# thanh toán vẫn hiện "quá hạn — cần thu".
# Quy tắc chốt với nghiệp vụ: số dư còn lại thuộc về các hóa đơn MỚI NHẤT; đi
# từ hóa đơn mới nhất (theo hạn thanh toán) trở về trước, phân bổ dần số dư —
# hóa đơn nhận phân bổ = còn nợ, hóa đơn cũ hơn coi như đã thanh toán.
# Hệ quả: công nợ quá hạn = tổng công nợ − công nợ hóa đơn chưa tới hạn.
# ═══════════════════════════════════════════════════════════════════════════

def _due_expr(alias: str = "si") -> str:
    """Hạn thanh toán: due_date, không có thì ngày HĐ + số ngày đến hạn (Settings)."""
    return f"COALESCE({alias}.due_date, DATE_ADD({alias}.posting_date, INTERVAL %(due_days)s DAY))"


def invoice_due_days() -> int:
    return int(get_settings().invoice_due_days or 30)


def _fifo_invoice_rows(company: str, customers: tuple, due_days: int, limit: int = 20000) -> dict:
    """Hóa đơn bán (loại hàng trả về) của các khách — sắp MỚI NHẤT TRƯỚC theo hạn TT."""
    if not customers:
        return {}
    due = _due_expr()
    rows = frappe.db.sql(
        f"""
        SELECT si.name, si.customer, si.posting_date, si.status,
               si.base_grand_total AS grand_total, {due} AS due
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND si.customer IN %(customers)s
          AND IFNULL(si.is_return, 0) = 0
          AND si.base_grand_total > 0
        ORDER BY si.customer ASC, {due} DESC, si.posting_date DESC, si.creation DESC
        LIMIT {int(limit)}
        """,
        {"company": company, "customers": tuple(customers), "due_days": due_days},
        as_dict=True,
    )
    out = {}
    for r in rows:
        out.setdefault(r.customer, []).append(r)
    return out


def _allocate_open(rows: list, balance) -> list:
    """Phân bổ số dư vào danh sách hóa đơn (đã sắp MỚI NHẤT TRƯỚC).

    Trả về các hóa đơn CÒN NỢ, sắp lại cũ → mới, kèm `outstanding_amount` là
    phần thực còn nợ của hóa đơn đó và `days_overdue` theo hạn thanh toán.
    """
    remaining = flt(balance)
    if remaining <= 0.5 or not rows:
        return []
    t = getdate(today())
    open_rows = []
    for r in rows:
        if remaining <= 0.5:
            break
        amt = min(remaining, flt(r.grand_total))
        remaining -= amt
        due = getdate(r.due) if r.get("due") else getdate(r.posting_date)
        open_rows.append({
            "name": r.name,
            "posting_date": str(r.posting_date) if r.posting_date else None,
            "due_date": str(r.due) if r.get("due") else None,
            "grand_total": flt(r.grand_total),
            "outstanding_amount": amt,
            "days_overdue": (t - due).days,
            "status": r.get("status"),
        })
    open_rows.sort(key=lambda x: (x["due_date"] or "", x["posting_date"] or ""))
    return open_rows


def open_invoices_map(company: str, balances: dict, limit: int = 20000) -> dict:
    """{khách: [hóa đơn còn nợ]} — phân bổ FIFO số dư GL của từng khách."""
    names = tuple(c for c, b in balances.items() if flt(b) > 0.5)
    if not names:
        return {}
    rows = _fifo_invoice_rows(company, names, invoice_due_days(), limit)
    return {c: _allocate_open(rows.get(c, []), balances[c]) for c in names}


def collection_schedule(as_of=None) -> dict:
    """LỊCH THU theo tháng: chốt ngày N, thu từ ngày N đến ngày M (Ketoan Portal Settings).

    Trả về kỳ thu ĐANG MỞ hoặc SẮP TỚI — cửa sổ thu tháng này đã đóng (qua ngày M)
    thì chuyển sang kỳ tháng sau. Hóa đơn có hạn ≤ mốc chốt của kỳ phải thanh toán
    trong kỳ đó (gồm cả hóa đơn quá hạn từ kỳ trước chưa thu được).
    """
    from frappe.utils import add_months, get_last_day

    s = get_settings()
    start = int(s.get("pay_window_start") or 5)
    end = int(s.get("pay_window_end") or 10)

    def at(d, day):
        d = getdate(d)
        return d.replace(day=min(int(day), getdate(get_last_day(d)).day))

    t = getdate(as_of or today())
    # Qua ngày kết thúc cửa sổ thu → kỳ tháng sau.
    cutoff = at(t if t.day <= end else getdate(add_months(t, 1)), start)
    win_end = at(cutoff, end)
    return {
        "cutoff": str(cutoff),
        "window_start": str(cutoff),
        "window_end": str(win_end),
        "next_cutoff": str(at(getdate(add_months(cutoff, 1)), start)),
        "prev_cutoff": str(at(getdate(add_months(cutoff, -1)), start)),
        "in_window": bool(cutoff <= t <= win_end),
        "days_to_window": max((cutoff - t).days, 0),
        "day_start": start,
        "day_end": end,
    }


def receivable_balances(company: str, channel: str = "tat-ca", customers: tuple | None = None) -> dict:
    """Số dư phải thu (GL) > 0 theo từng khách — nguồn cho phân bổ FIFO."""
    params = {"company": company}
    ch = channel_group_clause(channel, params, alias="c")
    racc = _racc_clause(params)
    cust_clause = ""
    if customers:
        params["customers"] = tuple(customers)
        cust_clause = "AND gle.party IN %(customers)s"
    rows = frappe.db.sql(
        f"""
        SELECT gle.party AS customer, SUM(gle.debit - gle.credit) AS bal
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        JOIN `tabCustomer` c ON c.name = gle.party
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND gle.party_type = 'Customer' AND {racc} AND {ch} {cust_clause}
        GROUP BY gle.party
        HAVING ROUND(SUM(gle.debit - gle.credit), 2) > 0
        LIMIT 5000
        """,
        params,
        as_dict=True,
    )
    return {r.customer: flt(r.bal) for r in rows}


@frappe.whitelist()
def get_ar_summary(company: str | None = None, limit: int = 200, channel: str = "tat-ca") -> dict:
    """Bảng kê công nợ phải thu theo khách + tổng — TÍNH TỪ GL ENTRY, lọc theo
    KÊNH (npp / mt / khac theo Customer Group; 'tat-ca' chỉ cho kế toán trưởng).

    outstanding = SUM(debit - credit) trên TK phải thu; âm = khách trả trước.
    days_overdue lấy từ hóa đơn SI còn nợ sớm hạn nhất (GL không mang hạn thu).
    """
    guard_channel(channel)
    company = resolve_company(company)
    limit = min(int(limit or 200), 1000)

    params = {"company": company, "limit": limit}
    ch_clause = channel_group_clause(channel, params, alias="c")
    racc = _racc_clause(params)

    rows = frappe.db.sql(
        f"""
        SELECT gle.party AS customer,
               COALESCE(c.customer_name, gle.party) AS customer_name,
               c.customer_group,
               SUM(gle.debit - gle.credit) AS outstanding
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        JOIN `tabCustomer` c ON c.name = gle.party
        WHERE gle.is_cancelled = 0
          AND gle.company = %(company)s
          AND gle.party_type = 'Customer'
          AND {racc}
          AND {ch_clause}
        GROUP BY gle.party, c.customer_name, c.customer_group
        HAVING ROUND(SUM(gle.debit - gle.credit), 2) <> 0
        ORDER BY SUM(gle.debit - gle.credit) DESC
        LIMIT %(limit)s
        """,
        params,
        as_dict=True,
    )

    # Quá hạn theo FIFO: phân bổ số dư vào hóa đơn mới nhất trước → hóa đơn còn
    # nợ thật sự; hóa đơn cũ đã được tiền về cấn trừ thì KHÔNG còn tính quá hạn.
    balances = {r["customer"]: flt(r["outstanding"]) for r in rows}
    opens = open_invoices_map(company, balances)

    total = 0.0
    for r in rows:
        r["outstanding"] = flt(r["outstanding"])
        total += r["outstanding"]
        invs = opens.get(r["customer"], [])
        od = [i for i in invs if i["days_overdue"] > 0]
        r["days_overdue"] = max((i["days_overdue"] for i in od), default=0)
        # Quá hạn = tổng nợ − nợ hóa đơn chưa tới hạn (gồm cả nợ không gắn hóa đơn).
        r["overdue_amount"] = max(0.0, r["outstanding"] - sum(
            i["outstanding_amount"] for i in invs if i["days_overdue"] <= 0))

    return {"company": company, "channel": channel, "total": total, "count": len(rows), "rows": rows}


def _bucketize(open_items, due_map, b1: int, b2: int, b3: int) -> tuple:
    """Cộng dồn số dư mở từng chứng từ vào rổ tuổi nợ.

    open_items: [{ref, o, first_date}] từ GL; due_map: ref → hạn (SI/PI).
    Không có hạn (JE, khoản trả trước...) → tuổi theo ngày phát sinh đầu tiên.
    Số âm (trả trước) trừ vào rổ tương ứng — tổng rổ luôn khớp tổng GL.
    """
    t = getdate(today())
    sums = {"current": 0.0, "b1": 0.0, "b2": 0.0, "b3": 0.0, "over": 0.0}
    total = 0.0
    for it in open_items:
        due = due_map.get(it.ref) or it.first_date
        d = (t - getdate(due)).days if due else 0
        o = flt(it.o)
        total += o
        if d <= 0:
            sums["current"] += o
        elif d <= b1:
            sums["b1"] += o
        elif d <= b2:
            sums["b2"] += o
        elif d <= b3:
            sums["b3"] += o
        else:
            sums["over"] += o
    return sums, total


@frappe.whitelist()
def get_aging(company: str | None = None, channel: str = "tat-ca") -> dict:
    """Tuổi nợ theo rổ cấu hình (Settings), lọc theo kênh — TÍNH TỪ GL ENTRY.

    Gộp GL theo chứng từ gốc (against_voucher, không có thì chính voucher) →
    số dư mở từng chứng từ; tuổi theo due_date của SI hoặc ngày phát sinh.
    """
    guard_channel(channel)
    company = resolve_company(company)
    s = get_settings()
    b1, b2, b3 = int(s.aging_bucket_1 or 30), int(s.aging_bucket_2 or 60), int(s.aging_bucket_3 or 90)
    params = {"company": company}
    ch_clause = channel_group_clause(channel, params, alias="c")
    racc = _racc_clause(params)

    items = frappe.db.sql(
        f"""
        SELECT COALESCE(gle.against_voucher, gle.voucher_no) AS ref,
               SUM(gle.debit - gle.credit) AS o,
               MIN(gle.posting_date) AS first_date
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON acc.name = gle.account
        JOIN `tabCustomer` c ON c.name = gle.party
        WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
          AND gle.party_type = 'Customer' AND {racc} AND {ch_clause}
        GROUP BY COALESCE(gle.against_voucher, gle.voucher_no)
        HAVING ROUND(SUM(gle.debit - gle.credit), 2) <> 0
        LIMIT 20000
        """,
        params,
        as_dict=True,
    )

    # Hạn thu cho các chứng từ mở là Sales Invoice.
    refs = [it.ref for it in items if it.ref]
    due_map = {}
    if refs:
        for x in frappe.get_all("Sales Invoice", filters={"name": ["in", refs]},
                                fields=["name", "due_date", "posting_date"], limit=len(refs)):
            due_map[x.name] = x.due_date or x.posting_date

    sums, total = _bucketize(items, due_map, b1, b2, b3)
    buckets = [
        {"key": "current", "label": "Trong hạn", "amount": flt(sums["current"])},
        {"key": "b1", "label": f"1–{b1} ngày", "amount": flt(sums["b1"])},
        {"key": "b2", "label": f"{b1+1}–{b2} ngày", "amount": flt(sums["b2"])},
        {"key": "b3", "label": f"{b2+1}–{b3} ngày", "amount": flt(sums["b3"])},
        {"key": "over", "label": f">{b3} ngày", "amount": flt(sums["over"])},
    ]
    return {"company": company, "channel": channel, "buckets": buckets, "total": flt(total)}


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

    # Tổng công nợ TÍNH TỪ GL (gồm JE, nợ đầu kỳ, khoản thu trước — không chỉ SI).
    gparams = {"company": company, "customer": customer}
    racc = _racc_clause(gparams)
    outstanding = flt(frappe.db.sql(
        f"""SELECT SUM(gle.debit - gle.credit)
            FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
              AND gle.party_type = 'Customer' AND gle.party = %(customer)s AND {racc}""",
        gparams,
    )[0][0] or 0)

    # Hóa đơn CÒN NỢ = phân bổ số dư GL theo FIFO (tiền trả cấn trừ HĐ cũ trước).
    invoices = _allocate_open(
        _fifo_invoice_rows(company, (customer,), invoice_due_days()).get(customer, []),
        outstanding,
    )
    # Công nợ quá hạn = TỔNG công nợ − công nợ hóa đơn chưa tới hạn (công thức chốt
    # với nghiệp vụ). Phần nợ không gắn hóa đơn nào (JE điều chỉnh, nợ đầu kỳ ghi
    # bằng bút toán) vẫn phải nằm trong "cần thu" → tách riêng để kế toán thấy.
    in_term_amount = sum(i["outstanding_amount"] for i in invoices if i["days_overdue"] <= 0)
    overdue_amount = max(0.0, outstanding - in_term_amount)
    unbilled_overdue = max(0.0, overdue_amount - sum(
        i["outstanding_amount"] for i in invoices if i["days_overdue"] > 0))

    # LỊCH THU: hóa đơn có hạn ≤ mốc chốt (ngày 5) phải thanh toán trong kỳ này;
    # hóa đơn đến hạn sau mốc chốt dồn sang kỳ tháng sau.
    sch = collection_schedule()
    cutoff = sch["cutoff"]
    due_now = [i for i in invoices if (i["due_date"] or "") <= cutoff]
    sch["invoice_count"] = len(due_now)
    sch["invoice_amount"] = sum(i["outstanding_amount"] for i in due_now)
    sch["unbilled"] = unbilled_overdue          # nợ không gắn hóa đơn — cũng phải thu
    sch["due_amount"] = sch["invoice_amount"] + unbilled_overdue
    sch["upcoming_amount"] = sum(
        i["outstanding_amount"] for i in invoices if (i["due_date"] or "") > cutoff)

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
        "overdue_amount": overdue_amount,
        "in_term_amount": in_term_amount,
        "unbilled_overdue": unbilled_overdue,
        "schedule": sch,
        "due_days": invoice_due_days(),
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
    # Hồ sơ pháp lý: chưa có file nào đính kèm trên Customer (hợp đồng, ĐKKD...).
    try:
        tasks["missing_docs"] = 0 if frappe.db.exists(
            "File", {"attached_to_doctype": "Customer", "attached_to_name": customer}
        ) else 1
    except Exception:
        tasks["missing_docs"] = 0
    return tasks


@frappe.whitelist()
def get_dso(company: str | None = None, channel: str = "tat-ca") -> dict:
    """DSO ước tính = tổng nợ / doanh thu kỳ × số ngày cửa sổ (toàn bộ hoặc theo kênh)."""
    guard_channel(channel)
    company = resolve_company(company)
    window = int(get_settings().dso_window_days or 365)

    dparams = {"company": company}
    racc = _racc_clause(dparams)
    debt = flt(
        frappe.db.sql(
            f"""
            SELECT SUM(gle.debit - gle.credit)
            FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
              AND gle.party_type = 'Customer' AND {racc}
            """,
            dparams,
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
                   SUM(gle.debit) AS debit, SUM(gle.credit) AS credit,
                   GROUP_CONCAT(DISTINCT gle.against SEPARATOR ', ') AS against
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

    # Hóa đơn nào CÒN NỢ thật (FIFO trên số dư hiện tại) — không tin
    # outstanding_amount vì tiền về qua JE/phiếu thu chưa khớp không cập nhật nó.
    cur_bal = flt(frappe.db.sql(
        f"""SELECT SUM(gle.debit - gle.credit)
            FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
              AND gle.party_type = 'Customer' AND gle.party = %(customer)s AND {racc}""",
        {k: v for k, v in params.items() if k in ("company", "customer", "racc")},
    )[0][0] or 0)
    open_map = {
        i["name"]: i for i in _allocate_open(
            _fifo_invoice_rows(company, (customer,), invoice_due_days()).get(customer, []), cur_bal
        )
    }

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
                op = open_map.get(r.voucher_no)
                if op:
                    dd = op["days_overdue"]
                    if dd > 0:
                        todos.append({"icon": "fa-hand-holding-dollar",
                                      "label": f"Quá hạn {dd} ngày — cần thu {format_vnd(op['outstanding_amount'])}",
                                      "sev": "red"})
                    else:
                        todos.append({"icon": "fa-hourglass-half",
                                      "label": f"Còn nợ {format_vnd(op['outstanding_amount'])} — trong hạn",
                                      "sev": "yellow"})
        elif r.voucher_type == "Payment Entry":
            if pe_unalloc.get(r.voucher_no, 0) > 0:
                todos.append({"icon": "fa-link-slash", "label": "Chưa khớp hóa đơn", "sev": "yellow"})
        out.append({
            "posting_date": str(r.posting_date), "voucher_type": r.voucher_type,
            "voucher_no": r.voucher_no, "debit": flt(r.debit), "credit": flt(r.credit),
            "balance": running, "docstatus": 1, "todos": todos,
            "against": (r.against or "")[:140],
            "route": f"/desk/{frappe.scrub(r.voucher_type).replace('_', '-')}/{r.voucher_no}",
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
            "balance": None, "docstatus": 0, "kind": "return", "against": "",
            "todos": [{"icon": "fa-rotate-left",
                       "label": "Chờ KTT duyệt trả hàng" if has_att else "Chờ hóa đơn NPP (trả hàng)",
                       "sev": "red" if has_att else "yellow"}],
            "route": f"/desk/sales-invoice/{x.name}",
        })
    from ketoan.utils import je_remark_field
    fieldr = je_remark_field()
    je_drafts = frappe.db.sql(
        f"""SELECT DISTINCT je.name, je.posting_date, je.total_debit, je.`{fieldr}` AS remark,
                   (SELECT GROUP_CONCAT(DISTINCT a2.account SEPARATOR ', ')
                    FROM `tabJournal Entry Account` a2
                    WHERE a2.parent = je.name
                      AND NOT (IFNULL(a2.party_type, '') = 'Customer'
                               AND IFNULL(a2.party, '') = %(customer)s)) AS against
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
            "balance": None, "docstatus": 0, "kind": "je", "against": (x.against or "")[:140],
            "todos": [{"icon": "fa-percent" if is_ck else "fa-gift",
                       "label": "Chờ KTT duyệt bút toán" if has_att else "Chờ hóa đơn NPP (bút toán JE)",
                       "sev": "red" if has_att else "yellow"}],
            "route": f"/desk/journal-entry/{x.name}",
        })

    return {
        "customer": customer, "company": company,
        "from_date": from_date, "to_date": to_date,
        "opening": opening, "rows": out, "drafts": drafts,
        "total_debit": total_debit, "total_credit": total_credit, "closing": running,
    }
