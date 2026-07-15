"""Whitelisted methods — Theo dõi GIÁ MUA VÀO & GIÁ BÁN RA.

1) GIÁ NHẬP nguyên liệu (kế toán mua hàng) — quét Purchase Invoice:
- Đơn giá chuẩn hóa về ĐVT KHO: base_net_amount / stock_qty (sau chiết khấu,
  trước thuế) — tránh lệch giả do mua bằng ĐVT khác nhau.
- Mỗi mặt hàng: giá mua GẦN NHẤT vs LẦN TRƯỚC và vs TRUNG BÌNH kỳ; kèm danh
  sách NCC. Biến động vượt ngưỡng (%) → cảnh báo.

2) GIÁ BÁN theo kênh (kế toán kênh bán) — quét Sales Invoice:
- So `rate` (giá bán thật) với `price_list_rate` (giá Bảng giá bán hàng ngay
  trên dòng hóa đơn). Lệch quá dung sai mà KHÔNG có Pricing Rule áp
  (sii.pricing_rules rỗng) → vi phạm; bán khi bảng giá không có giá → cảnh báo.
Read-only, guard ở dòng đầu, SQL parameterized.
"""

import frappe
from frappe import _
from frappe.utils import flt, today, add_days

from ketoan.api._guard import (
    guard_purchase, guard_channel, channel_group_clause, resolve_company,
)


def _purchase_lines(company: str, since: str, item_code: str | None = None) -> list:
    """Dòng mua NVL từ PI submitted (không return), đơn giá theo ĐVT kho."""
    params = {"company": company, "since": since}
    item_clause = ""
    if item_code:
        item_clause = "AND pii.item_code = %(item_code)s"
        params["item_code"] = item_code
    return frappe.db.sql(
        f"""
        SELECT pi.name, pi.posting_date, pi.supplier,
               COALESCE(pi.supplier_name, pi.supplier) AS supplier_name,
               pii.item_code, pii.item_name, pii.stock_uom,
               pii.stock_qty, pii.base_net_amount,
               (pii.base_net_amount / NULLIF(pii.stock_qty, 0)) AS price
        FROM `tabPurchase Invoice Item` pii
        JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pi.docstatus = 1 AND pi.company = %(company)s
          AND IFNULL(pi.is_return, 0) = 0
          AND pi.posting_date >= %(since)s
          AND IFNULL(pii.item_code, '') != ''
          AND pii.stock_qty > 0
          {item_clause}
        ORDER BY pii.item_code, pi.posting_date ASC, pi.creation ASC
        LIMIT 20000
        """,
        params,
        as_dict=True,
    )


@frappe.whitelist()
def get_price_watch(company: str | None = None, days: int = 180, threshold: float = 10) -> dict:
    """Bảng theo dõi giá nhập: mỗi mặt hàng 1 dòng — giá gần nhất, so lần trước,
    so trung bình kỳ, min–max, NCC. alert=True khi |biến động| ≥ threshold %."""
    guard_purchase()
    company = resolve_company(company)
    days = max(7, min(int(days or 180), 730))
    threshold = max(1.0, flt(threshold or 10))
    since = add_days(today(), -days)

    lines = _purchase_lines(company, since)

    items = {}
    for l in lines:
        price = flt(l.price)
        if price <= 0:
            continue
        it = items.setdefault(l.item_code, {
            "item_code": l.item_code,
            "item_name": l.item_name or l.item_code,
            "uom": l.stock_uom or "",
            "series": [],
            "suppliers": {},
        })
        it["series"].append({"date": str(l.posting_date), "price": price,
                             "supplier": l.supplier, "supplier_name": l.supplier_name})
        it["suppliers"][l.supplier] = l.supplier_name

    rows = []
    alert_count = 0
    for it in items.values():
        s = it["series"]
        if not s:
            continue
        last = s[-1]
        prev = s[-2] if len(s) > 1 else None
        prices = [x["price"] for x in s]
        avg = sum(prices) / len(prices)
        chg_last = ((last["price"] - prev["price"]) / prev["price"] * 100) if (prev and prev["price"]) else None
        chg_avg = ((last["price"] - avg) / avg * 100) if avg else None
        # Cảnh báo cần ≥2 lần mua; so-với-TB chỉ xét khi đủ ≥3 điểm cho đỡ nhiễu.
        alert = bool(
            (chg_last is not None and abs(chg_last) >= threshold)
            or (len(s) >= 3 and chg_avg is not None and abs(chg_avg) >= threshold)
        )
        if alert:
            alert_count += 1
        sup_names = list(it["suppliers"].values())
        rows.append({
            "item_code": it["item_code"],
            "item_name": it["item_name"],
            "uom": it["uom"],
            "buys": len(s),
            "supplier_count": len(it["suppliers"]),
            "suppliers": sup_names[:3],
            "last_price": last["price"],
            "last_date": last["date"],
            "last_supplier": last["supplier_name"],
            "prev_price": prev["price"] if prev else None,
            "chg_last_pct": round(chg_last, 1) if chg_last is not None else None,
            "avg_price": avg,
            "chg_avg_pct": round(chg_avg, 1) if chg_avg is not None else None,
            "min_price": min(prices),
            "max_price": max(prices),
            "alert": alert,
        })

    # Cảnh báo trước, trong mỗi nhóm sắp theo |biến động lần trước| giảm dần.
    rows.sort(key=lambda r: (not r["alert"], -abs(r["chg_last_pct"] or 0), -(r["buys"])))

    return {
        "company": company, "days": days, "threshold": threshold,
        "item_count": len(rows), "alert_count": alert_count,
        "rows": rows, "truncated": len(lines) >= 20000,
    }


@frappe.whitelist()
def get_price_history(item_code: str, company: str | None = None, days: int = 365) -> dict:
    """Lịch sử giá nhập 1 mặt hàng: từng lần mua (mới nhất trước) + % so lần liền trước."""
    guard_purchase()
    if not item_code:
        frappe.throw(_("Thiếu mã nguyên liệu"))
    company = resolve_company(company)
    days = max(7, min(int(days or 365), 1095))
    since = add_days(today(), -days)

    lines = _purchase_lines(company, since, item_code=item_code)
    out = []
    prev_price = None
    for l in lines:  # đang ASC theo ngày → tính % so lần liền trước
        price = flt(l.price)
        if price <= 0:
            continue
        chg = ((price - prev_price) / prev_price * 100) if prev_price else None
        out.append({
            "date": str(l.posting_date),
            "invoice": l.name,
            "supplier": l.supplier,
            "supplier_name": l.supplier_name,
            "qty": flt(l.stock_qty),
            "uom": l.stock_uom or "",
            "price": price,
            "chg_pct": round(chg, 1) if chg is not None else None,
            "route": f"/desk/purchase-invoice/{l.name}",
        })
    out.reverse()  # mới nhất trước

    item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
    return {"company": company, "item_code": item_code, "item_name": item_name,
            "days": days, "rows": out}


# ═══════════════════════════════════════════════════════════════════════════
# Giá BÁN theo kênh — so với Bảng giá bán hàng, bắt lệch không có Pricing Rule
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_selling_price_watch(company: str | None = None, channel: str = "tat-ca",
                            days: int = 90, tolerance: float = 1) -> dict:
    """Soát giá bán của 1 kênh: mỗi mặt hàng 1 dòng — số lần bán, số dòng
    LỆCH BẢNG GIÁ KHÔNG CÓ PRICING RULE (quá dung sai %) và số dòng bán khi
    bảng giá chưa có giá. Kèm các vi phạm gần nhất để soát từng hóa đơn."""
    guard_channel(channel)
    company = resolve_company(company)
    days = max(7, min(int(days or 90), 365))
    tolerance = max(0.1, flt(tolerance or 1))
    since = add_days(today(), -days)

    params = {"company": company, "since": since}
    ch = channel_group_clause(channel, params, alias="c")
    lines = frappe.db.sql(
        f"""
        SELECT si.name, si.posting_date,
               COALESCE(si.customer_name, si.customer) AS customer_name,
               COALESCE(si.selling_price_list, '') AS price_list,
               sii.item_code, sii.item_name, sii.uom,
               sii.rate, sii.price_list_rate,
               IFNULL(sii.pricing_rules, '') AS pricing_rules
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %(company)s
          AND IFNULL(si.is_return, 0) = 0
          AND si.posting_date >= %(since)s
          AND IFNULL(sii.item_code, '') != ''
          AND {ch}
        ORDER BY sii.item_code, si.posting_date ASC, si.creation ASC
        LIMIT 20000
        """,
        params,
        as_dict=True,
    )

    items = {}
    viol_lines = 0
    for l in lines:
        rate, plr = flt(l.rate), flt(l.price_list_rate)
        it = items.setdefault(l.item_code, {
            "item_code": l.item_code, "item_name": l.item_name or l.item_code,
            "uom": l.uom or "", "sold": 0, "viols": [],
            "off_price": 0, "no_price": 0, "price_lists": set(),
        })
        it["sold"] += 1
        if l.price_list:
            it["price_lists"].add(l.price_list)

        has_rule = (l.pricing_rules or "").strip() not in ("", "[]")
        vtype = None
        if plr <= 0:
            vtype = "no_price"      # bảng giá kênh chưa có giá mặt hàng này
        elif abs((rate - plr) / plr * 100) > tolerance and not has_rule:
            vtype = "off_price"     # bán lệch bảng giá mà không có Pricing Rule
        if not vtype:
            continue
        viol_lines += 1
        it[vtype] += 1
        it["viols"].append({
            "type": vtype, "date": str(l.posting_date), "invoice": l.name,
            "customer": l.customer_name, "rate": rate, "price_list_rate": plr,
            "diff_pct": round((rate - plr) / plr * 100, 1) if plr else None,
            "price_list": l.price_list,
            "route": f"/desk/sales-invoice/{l.name}",
        })

    rows = []
    for it in items.values():
        viols = it["viols"]
        rows.append({
            "item_code": it["item_code"], "item_name": it["item_name"], "uom": it["uom"],
            "sold": it["sold"],
            "viol_count": len(viols),
            "off_price_count": it["off_price"],
            "no_price_count": it["no_price"],
            "price_lists": sorted(it["price_lists"])[:3],
            "last_viol": viols[-1] if viols else None,
            "recent_viols": viols[-8:][::-1],  # mới nhất trước, tối đa 8
            "alert": bool(viols),
        })
    rows.sort(key=lambda r: (not r["alert"], -r["viol_count"], -r["sold"]))

    return {
        "company": company, "channel": channel, "days": days, "tolerance": tolerance,
        "item_count": len(rows), "alert_count": sum(1 for r in rows if r["alert"]),
        "viol_lines": viol_lines, "rows": rows, "truncated": len(lines) >= 20000,
    }
