"""Whitelisted method — TRANG GIÁM SÁT phòng kế toán (Kế toán trưởng).

Gom toàn bộ chỉ số giám sát các phân hệ vào 1 lần gọi (tái dùng method từng
phân hệ — chief qua được mọi guard). Mỗi khối bọc try/except: một phân hệ
lỗi/thiếu dữ liệu không làm sập cả trang.

Kèm khối GIÁM SÁT PRICING RULE:
- đang hiệu lực / đã tắt; HẾT HẠN mà còn bật (cần xử lý); sắp hết hạn (7 ngày);
- tần suất áp dụng 30 ngày (đếm từ sii.pricing_rules của Sales Invoice) —
  lộ rule đang bật nhưng KHÔNG được dùng và rule dùng nhiều nhất.
"""

import json

import frappe
from frappe.utils import flt, today, add_days, getdate

from ketoan.api._guard import guard_manager, resolve_company


def _m(label, value, fmt="num", sev=None, route=None, href=None):
    return {"label": label, "value": value, "fmt": fmt, "sev": sev, "route": route, "href": href}


@frappe.whitelist()
def get_overview(company: str | None = None) -> dict:
    """Toàn bộ chỉ số giám sát phòng kế toán + khối Pricing Rule."""
    guard_manager()
    company = resolve_company(company)
    sections = []

    # ── Phải thu (GL) ───────────────────────────────────────────────────────
    try:
        from ketoan.api import receivables
        aging = receivables.get_aging(company)
        overdue = sum(b["amount"] for b in aging["buckets"] if b["key"] != "current")
        dso = receivables.get_dso(company)
        unalloc = flt(frappe.db.sql(
            """SELECT SUM(unallocated_amount) FROM `tabPayment Entry`
               WHERE docstatus = 1 AND party_type = 'Customer'
                 AND company = %(company)s AND unallocated_amount > 0""",
            {"company": company})[0][0] or 0)
        sections.append({"key": "thu", "title": "Công nợ phải thu (GL)", "icon": "fa-file-invoice-dollar", "metrics": [
            _m("Tổng công nợ", aging["total"], "vnd", None, "/cong-no"),
            _m("Nợ quá hạn", overdue, "vnd", "danger" if overdue > 0 else "ok", "/cong-no"),
            _m("DSO (ngày thu tiền bình quân)", dso["dso"] or 0, "num", None, "/cong-no"),
            _m("Khoản thu chưa khớp hóa đơn", unalloc, "vnd", "warning" if unalloc > 0 else "ok", "/canh-bao"),
        ]})
    except Exception:
        pass

    # ── Đối trừ & HĐĐT kênh NPP ─────────────────────────────────────────────
    try:
        from ketoan.api.doitru import get_cases, get_missing_einvoice
        c = get_cases(company)
        rc, jc = c["returns_counts"], c["je_counts"]
        ein = get_missing_einvoice(company)
        ein_n = len(ein["rows"]) if ein.get("supported") else 0
        sections.append({"key": "doitru", "title": "Đối trừ NPP & hóa đơn điện tử", "icon": "fa-handshake", "metrics": [
            _m("Trả hàng chờ hóa đơn NPP", rc["cho_hoadon"], "num", "warning" if rc["cho_hoadon"] else "ok", "/doi-chieu-npp?tab=trahang"),
            _m("Trả hàng chờ KTT duyệt", rc["cho_duyet"], "num", "danger" if rc["cho_duyet"] else "ok", "/doi-chieu-npp?tab=trahang"),
            _m("Bút toán JE chờ hóa đơn NPP", jc["cho_hoadon"], "num", "warning" if jc["cho_hoadon"] else "ok", "/doi-chieu-npp?tab=butoan"),
            _m("Bút toán JE chờ KTT duyệt", jc["cho_duyet"], "num", "danger" if jc["cho_duyet"] else "ok", "/doi-chieu-npp?tab=butoan"),
            _m("Hàng đi chưa xuất HĐĐT (60 ngày)", ein_n, "num", "danger" if ein_n else "ok", "/doi-chieu-npp?tab=einvoice"),
        ]})
    except Exception:
        pass

    # ── Giám sát giá mua vào / bán ra ──────────────────────────────────────
    try:
        from ketoan.api.prices import get_price_watch, get_selling_price_watch
        metrics = []
        pw = get_price_watch(company, days=90)
        metrics.append(_m("Giá nhập NVL biến động ≥ 10% (90 ngày)", pw["alert_count"], "num",
                          "danger" if pw["alert_count"] else "ok", "/cong-no-ncc?tab=gia"))
        for ch, label in (("npp", "NPP"), ("mt", "MT"), ("khac", "Du lịch, Khác")):
            try:
                sp = get_selling_price_watch(company, channel=ch, days=30)
                metrics.append(_m(f"Giá bán lệch bảng giá không rule — kênh {label} (30 ngày)",
                                  sp["alert_count"], "num",
                                  "danger" if sp["alert_count"] else "ok", f"/cong-no/{ch}?tab=gia"))
            except Exception:
                pass
        sections.append({"key": "gia", "title": "Giám sát giá mua / giá bán", "icon": "fa-tags", "metrics": metrics})
    except Exception:
        pass

    # ── Phải trả & kiểm soát mua hàng ───────────────────────────────────────
    try:
        from ketoan.api import payables
        ap = payables.get_aging(company)
        ap_over = sum(b["amount"] for b in ap["buckets"] if b["key"] != "current")
        ctl = payables.get_controls(company)
        due = payables.get_due_schedule(company, days_ahead=7)
        sections.append({"key": "tra", "title": "Công nợ phải trả & mua hàng (GL)", "icon": "fa-truck-field", "metrics": [
            _m("Tổng phải trả", ap["total"], "vnd", None, "/cong-no-ncc"),
            _m("Phải trả quá hạn", ap_over, "vnd", "danger" if ap_over > 0 else "ok", "/cong-no-ncc"),
            _m("Hóa đơn đến hạn/quá hạn 7 ngày", len(due["rows"]), "num",
               "warning" if due["rows"] else "ok", "/cong-no-ncc?tab=due"),
            _m("Nghi trùng hóa đơn NCC", len(ctl["duplicates"]), "num",
               "danger" if ctl["duplicates"] else "ok", "/cong-no-ncc?tab=control"),
            _m("Thiếu liên kết nhập kho (3 chiều)", len(ctl["missing_receipt"]), "num",
               "warning" if ctl["missing_receipt"] else "ok", "/cong-no-ncc?tab=control"),
        ]})
    except Exception:
        pass

    # ── Quỹ tiền & sổ sách ─────────────────────────────────────────────────
    try:
        from ketoan.api.cash import get_balances
        bal = get_balances(company)
        neg = [r for r in bal["rows"] if flt(r["balance"]) < 0]
        je_draft = int(frappe.db.sql(
            "SELECT COUNT(*) FROM `tabJournal Entry` WHERE docstatus = 0 AND company = %(company)s",
            {"company": company})[0][0] or 0)
        metrics = [
            _m("Tổng số dư quỹ", bal["total"], "vnd", "danger" if bal["total"] < 0 else None, "/quy"),
            _m("Tài khoản tiền âm", len(neg), "num", "danger" if neg else "ok", "/quy"),
            _m("Bút toán nháp chờ ghi sổ", je_draft, "num", "warning" if je_draft else "ok",
               None, "/desk/journal-entry?docstatus=0"),
        ]
        for dt, label in (("SalaryDay", "Phiếu công nhật nháp"), ("SalaryProduct", "Phiếu công khoán nháp")):
            if frappe.db.exists("DocType", dt):
                n = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{dt}` WHERE docstatus = 0")[0][0] or 0)
                metrics.append(_m(label, n, "num", "warning" if n else "ok", "/luong"))
        sections.append({"key": "quy", "title": "Quỹ tiền, sổ sách & lương", "icon": "fa-wallet", "metrics": metrics})
    except Exception:
        pass

    # ── Cảnh báo tác nghiệp ─────────────────────────────────────────────────
    try:
        from ketoan.api.alerts import get_alerts
        al = get_alerts(company)["alerts"]
        n_danger = sum(1 for a in al if a["severity"] == "danger")
        sections.append({"key": "canhbao", "title": "Trung tâm cảnh báo", "icon": "fa-triangle-exclamation", "metrics": [
            _m("Cảnh báo đang mở", len(al), "num", "warning" if al else "ok", "/canh-bao"),
            _m("Mức nghiêm trọng (danger)", n_danger, "num", "danger" if n_danger else "ok", "/canh-bao"),
        ]})
    except Exception:
        pass

    return {
        "company": company,
        "as_of": today(),
        "sections": sections,
        "pricing": _pricing_rules_watch(company),
    }


def _pricing_rules_watch(company: str) -> dict:
    """Giám sát Pricing Rule: hiệu lực / hết hạn còn bật / sắp hết hạn /
    tần suất áp dụng 30 ngày (từ sii.pricing_rules)."""
    out = {"supported": True, "active": 0, "disabled": 0,
           "expired_enabled": [], "expiring_soon": [], "unused_30d": [], "top_used": []}
    try:
        if not frappe.db.exists("DocType", "Pricing Rule"):
            return {"supported": False}
        rules = frappe.get_all(
            "Pricing Rule",
            or_filters=[["company", "=", company], ["company", "is", "not set"]],
            fields=["name", "title", "apply_on", "selling", "buying", "disable",
                    "rate_or_discount", "discount_percentage", "rate",
                    "valid_from", "valid_upto", "for_price_list", "priority"],
            order_by="modified desc",
            limit=300,
        )
        t = getdate(today())
        soon = getdate(add_days(today(), 7))

        # Tần suất áp dụng 30 ngày: đọc sii.pricing_rules (JSON list tên rule).
        usage = {}
        try:
            lines = frappe.db.sql(
                """SELECT sii.pricing_rules
                   FROM `tabSales Invoice Item` sii
                   JOIN `tabSales Invoice` si ON si.name = sii.parent
                   WHERE si.docstatus = 1 AND si.company = %(company)s
                     AND si.posting_date >= %(since)s
                     AND IFNULL(sii.pricing_rules, '') NOT IN ('', '[]')
                   LIMIT 20000""",
                {"company": company, "since": add_days(today(), -30)},
            )
            for (pr,) in lines:
                try:
                    for name in json.loads(pr):
                        usage[name] = usage.get(name, 0) + 1
                except Exception:
                    continue
        except Exception:
            pass

        def brief(r):
            gia = ""
            if r.rate_or_discount == "Discount Percentage":
                gia = f"giảm {flt(r.discount_percentage)}%"
            elif r.rate_or_discount == "Rate":
                gia = f"giá {flt(r.rate):,.0f}"
            elif r.rate_or_discount:
                gia = r.rate_or_discount
            return {
                "name": r.name,
                "title": r.title or r.name,
                "kind": "Bán" if r.selling else ("Mua" if r.buying else "?"),
                "detail": gia,
                "price_list": r.for_price_list or "",
                "valid_from": str(r.valid_from) if r.valid_from else "",
                "valid_upto": str(r.valid_upto) if r.valid_upto else "",
                "used_30d": usage.get(r.name, 0),
                "route": f"/desk/pricing-rule/{r.name}",
            }

        for r in rules:
            if r.disable:
                out["disabled"] += 1
                continue
            upto = getdate(r.valid_upto) if r.valid_upto else None
            if upto and upto < t:
                out["expired_enabled"].append(brief(r))   # HẾT HẠN mà còn bật
                continue
            out["active"] += 1
            if upto and t <= upto <= soon:
                out["expiring_soon"].append(brief(r))
            if r.selling and usage.get(r.name, 0) == 0:
                out["unused_30d"].append(brief(r))

        used = [brief(r) for r in rules if not r.disable and usage.get(r.name, 0) > 0]
        used.sort(key=lambda x: -x["used_30d"])
        out["top_used"] = used[:10]
        out["expired_enabled"] = out["expired_enabled"][:10]
        out["expiring_soon"] = out["expiring_soon"][:10]
        out["unused_30d"] = out["unused_30d"][:10]
        return out
    except Exception:
        return {"supported": False}
