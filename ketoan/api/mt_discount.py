# -*- coding: utf-8 -*-
"""mt_discount — lập BẢNG KÊ CHIẾT KHẤU (BKCK) từ file doanh số của chuỗi.

Quy trình §3 SOP, năm bước:

    1. Nạp file doanh số / TBCK        -> `mt_discount_read` (MT2-B1)
    2. Đối chiếu với hóa đơn ERPNext   -> `preview_sheets` khớp và BÁO chênh lệch
    3. Lập bảng kê, lấy số kế tiếp     -> `commit_sheets` + `finalize_sheet`
    4. Xuất hóa đơn CK trên MISA       -> con người làm, `set_invoice` ghi số về
    5. Sinh JE chiết khấu -> duyệt     -> `create_journal_entry` + MT2-E

BẢNG KÊ LÀ CHỨNG TỪ HAI BÊN KÝ, và nó dẫn tới một hóa đơn GTGT. Sai ở đây phải
sửa bằng hóa đơn điều chỉnh, để lại vết với cơ quan thuế. Vì vậy:

  · Bên mua LẤY TỪ `MT Store` / `Customer`, tuyệt đối không từ cột
    `SUPPLIERNAME` của file chuỗi — cột đó là tên CỦA MÌNH (§L.3 hợp đồng).
  · Nhóm nào chưa xác định được bên mua thì KHÔNG lập bảng kê, báo rõ phải sửa
    gì. Lập bảng kê với bên mua trống rồi điền sau là mời người ký nhầm.
  · Tỷ lệ và cách tính lấy từ `MT Discount Term`; thiếu -> DỪNG, không đoán.
  · Xem trước BẮT BUỘC, commit đòi vân tay của đúng bản vừa xem.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, today

from ketoan.api._guard import guard_manager, guard_mt, is_chief
from ketoan.api.mt_discount_read import DISCOUNT_CHAIN_LABEL, read_discount_basis
from ketoan.mt.doctype.mt_discount_sheet.mt_discount_sheet import (
    STATUS_DRAFT,
    STATUS_FINAL,
    STATUS_INVOICED,
)
from ketoan.mt.doctype.mt_discount_term.mt_discount_term import (
    MODE_PER_LINE,
    MODE_RATE_TOTAL,
    READ_MODE_TO_LABEL,
)
from ketoan.mt.doctype.mt_discount_term.mt_discount_term import resolve as resolve_term
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_text,
)

SOURCE_DT = "MT Discount Sheet"

# Trần số bảng kê dựng trong một lần nạp. Thật: LOTTE 14 chi nhánh, Central
# Retail 1–2 pháp nhân. 200 là dư rất xa mà vẫn chặn được ca một cột bị đọc nhầm
# thành khóa nhóm rồi sinh ra hàng nghìn "bảng kê".
MAX_SHEETS = 200


def _require_tables():
    for dt in ("MT Discount Sheet", "MT Discount Sheet Line", "MT Discount Term", "MT Store"):
        if not frappe.db.table_exists(dt):
            frappe.throw(_(
                "Chức năng bảng kê chiết khấu chưa được cài trên site này (thiếu bảng {0}). "
                "Quản trị chạy: bench --site TÊN_SITE migrate"
            ).format(dt))


def _company(company=None):
    from ketoan.api.mt import _company as _mt_company
    return _mt_company(company)


# ─────────────────────────────────────────────────────────────────────────
# Xác định BÊN MUA — chỗ dễ sai nhất, vì nó in lên chứng từ hai bên ký
# ─────────────────────────────────────────────────────────────────────────

def _resolve_buyer(chain, group):
    """(khách, điểm, địa chỉ, tên in, MST, địa chỉ in) cho MỘT nhóm. Không ra -> lý do.

    Thứ tự tra, dừng ở bước đầu tiên trúng:

      1. `MT Store` theo (chuỗi, MÃ ĐIỂM)      — LOTTE, Mega: khóa nhóm là mã điểm
      2. `MT Store` theo (chuỗi, MÃ NCC)       — Central Retail: khóa nhóm là mã
                                                 pháp nhân EB mình đăng ký
      3. Khách kênh MT của chuỗi, nếu có ĐÚNG MỘT

    Không ra thì TRẢ LÝ DO, không đoán. Bảng kê ký nhầm pháp nhân là hóa đơn sai
    người mua.
    """
    key = cstr(group.get("key") or "")
    store = None
    if key:
        store = frappe.db.get_value(
            "MT Store", {"chain": chain, "store_code": key},
            ["name", "customer", "address", "tax_id", "store_name"], as_dict=True)
        if not store:
            store = frappe.db.get_value(
                "MT Store", {"chain": chain, "vendor_code": key},
                ["name", "customer", "address", "tax_id", "store_name"], as_dict=True)

    customer = store.customer if store else None
    if not customer:
        cands = frappe.get_all("Customer",
                               filters={"custom_mt_chain": chain, "disabled": 0},
                               fields=["name"], limit_page_length=0) \
            if frappe.db.has_column("Customer", "custom_mt_chain") else []
        if len(cands) == 1:
            customer = cands[0].name
        elif not store:
            return None, ("Không tìm thấy điểm siêu thị nào của chuỗi %s mang mã '%s'. "
                          "Vào màn 'Điểm siêu thị' tạo/sửa điểm và gán pháp nhân."
                          % (chain, key))
        else:
            return None, ("Điểm '%s' chưa gán pháp nhân. Vào màn 'Điểm siêu thị' gán khách "
                          "hàng cho điểm này." % (store.store_name or key))

    cus = frappe.db.get_value("Customer", customer, ["customer_name", "tax_id"], as_dict=True)
    if not cus:
        return None, "Khách hàng %s không tồn tại" % customer

    address = store.address if store else None
    addr_txt, addr_tax = "", None
    if address:
        a = frappe.db.get_value("Address", address,
                                ["address_line1", "address_line2", "city", "state",
                                 "country", "gstin"], as_dict=True)
        if a:
            addr_txt = ", ".join(x for x in (a.address_line1, a.address_line2, a.city,
                                             a.state, a.country) if x)
            addr_tax = norm_text(a.gstin)

    # MST: ưu tiên MST RIÊNG của điểm (chi nhánh LOTTE có MST riêng dạng
    # 0304741634-015), rồi tới MST trên địa chỉ, cuối cùng mới tới MST pháp nhân.
    tax_id = norm_text(store.tax_id if store else "") or addr_tax or norm_text(cus.tax_id)

    return {
        "customer": customer,
        "store": store.name if store else None,
        "address": address,
        # Tên in trên bảng kê: tên PHÁP NHÂN trên hệ thống của mình. Với LOTTE,
        # tên chi nhánh đầy đủ nằm ở Customer của chi nhánh đó.
        "buyer_name": cus.customer_name or customer,
        "buyer_tax_id": tax_id,
        "buyer_address": addr_txt,
        "store_label": (store.store_name if store else None),
    }, None


# ─────────────────────────────────────────────────────────────────────────
# Dựng kế hoạch bảng kê
# ─────────────────────────────────────────────────────────────────────────

def _si_index(company, chain):
    """Chỉ mục hóa đơn bán ra để đối chiếu: (ký hiệu chuẩn, số chuẩn) -> hóa đơn.

    Chỉ để ĐỐI CHIẾU và cảnh báo, KHÔNG để dựng dòng bảng kê: cơ sở tính chiết
    khấu là số CHUỖI đã chốt, chênh lệch với hóa đơn của mình chính là thứ phải
    đi truy (§3.2 SOP).
    """
    # Site chưa chạy patch MISA thì không có cột số hóa đơn -> bỏ đối chiếu,
    # bảng kê vẫn lập được (cơ sở là số của CHUỖI, không phải hóa đơn của mình).
    if not frappe.db.has_column("Sales Invoice", "custom_misa_inv_no"):
        return {}
    rows = frappe.db.sql("""
        SELECT si.name, si.custom_misa_inv_no AS inv_no,
               si.grand_total, si.base_net_total, si.posting_date, si.customer
        FROM `tabSales Invoice` si
        WHERE si.company = %(company)s AND si.docstatus = 1
          AND IFNULL(si.custom_misa_inv_no, '') != ''
    """, {"company": company}, as_dict=True)
    idx = {}
    for r in rows:
        idx.setdefault(norm_inv_no(r.inv_no), []).append(r)
    return idx


def _build_plan(parsed, company, period_label, sheet_date, filename):
    """Kế hoạch: mỗi NHÓM của file thành MỘT bảng kê. THUẦN ĐỌC."""
    chain = parsed["chain"]
    warnings = list(parsed.get("warnings") or [])
    groups = parsed["groups"]

    if len(groups) > MAX_SHEETS:
        frappe.throw(_(
            "File dựng ra {0} bảng kê — vượt trần {1}. Gần như chắc chắn một cột đã bị "
            "đọc nhầm thành khóa nhóm. KHÔNG lập gì; kiểm lại file."
        ).format(len(groups), MAX_SHEETS))

    by_group = {}
    for r in parsed["rows"]:
        by_group.setdefault(cstr(r["group_key"]), []).append(r)

    si_idx = _si_index(company, chain)
    plan, blocked = [], []

    for g in groups:
        rows = by_group.get(cstr(g["key"])) or []
        buyer, why = _resolve_buyer(chain, g)
        if not buyer:
            blocked.append({"key": g["key"], "group_label": g.get("group_label"),
                            "n_rows": g["n_rows"], "base_amount": g["base_amount"],
                            "reason": why})
            continue

        term = resolve_term(chain, buyer["customer"], company)

        # Cách tính: điều khoản đã khai LÀ CHÍNH. Nhưng nếu file in chiết khấu
        # từng dòng mà điều khoản lại bảo 'tỷ lệ × tổng' (hoặc ngược lại) thì
        # BÁO — đó là dấu hiệu hợp đồng đã đổi mà chưa ai cập nhật cấu hình.
        file_mode = READ_MODE_TO_LABEL.get(parsed["mode"])
        if file_mode and term["mode"] != file_mode:
            warnings.append(
                "Nhóm %s: điều khoản khai '%s' nhưng file của chuỗi ra dạng '%s'. "
                "Dùng theo ĐIỀU KHOẢN — kiểm lại hợp đồng nếu không đúng ý."
                % (g["key"], term["mode"], file_mode))

        # Tỷ lệ: file THẮNG khi file có in (đó là số chuỗi đã chốt); không có thì
        # lấy từ điều khoản.
        rate = parsed.get("rate")
        rate_src = "file của chuỗi"
        if rate is None:
            rate = term["rate"]
            rate_src = "điều khoản %s" % term["name"]
        if term["mode"] == MODE_RATE_TOTAL and not flt(rate):
            frappe.throw(_(
                "Nhóm {0}: cách tính là '{1}' nhưng không có tỷ lệ — cả file lẫn điều "
                "khoản đều không khai. Khai tỷ lệ ở MT Discount Term rồi làm lại."
            ).format(g["key"], MODE_RATE_TOTAL))

        vat_rate = flt(term["vat_rate"]) or 8.0

        # ── Gộp dòng theo HÓA ĐƠN. File chi tiết theo sản phẩm (LOTTE 227 dòng
        # cho 26 hóa đơn); bảng kê in MỘT dòng / hóa đơn.
        by_inv, order = {}, []
        for r in rows:
            k = (cstr(r["inv_series"] or ""), cstr(r["inv_no_norm"] or r["inv_no"] or ""))
            if k not in by_inv:
                by_inv[k] = {"inv_series": r["inv_series"], "inv_no": r["inv_no"],
                             "inv_no_norm": r["inv_no_norm"], "inv_date": r["inv_date"],
                             "amount_before_vat": 0.0, "discount_amount": 0.0,
                             "has_discount": True, "note": r["note"],
                             "store_code": r["store_code"], "source_row": r["source_row"]}
                order.append(k)
            e = by_inv[k]
            e["amount_before_vat"] += flt(r["base_amount"])
            if r["discount_amount"] is None:
                e["has_discount"] = False
            else:
                e["discount_amount"] += flt(r["discount_amount"])
            # Ngày sớm nhất của hóa đơn — chuỗi ghi ngày nhận hàng theo từng dòng.
            if r["inv_date"] and (not e["inv_date"] or r["inv_date"] < e["inv_date"]):
                e["inv_date"] = r["inv_date"]

        lines, n_matched, mismatch = [], 0, []
        for k in order:
            e = by_inv[k]
            base = flt(e["amount_before_vat"])
            vat = base * vat_rate / 100.0
            si = None
            cands = si_idx.get(cstr(e["inv_no_norm"] or "")) or []
            if len(cands) == 1:
                si = cands[0]
                n_matched += 1
                # Chênh lệch doanh số chuỗi báo vs hóa đơn của mình — §3.2 SOP
                # bảo phải đi truy (hàng trả, móp lỗi, hóa đơn điều chỉnh).
                mine = flt(si.base_net_total) or (flt(si.grand_total) / (1 + vat_rate / 100.0))
                if abs(mine - base) > 1.0:
                    mismatch.append({"inv_no": e["inv_no"], "chain": base, "ours": mine,
                                     "sales_invoice": si.name})
            lines.append({
                "inv_series": e["inv_series"], "inv_no": e["inv_no"],
                "inv_no_norm": e["inv_no_norm"], "inv_date": e["inv_date"],
                "amount_before_vat": round(base, 2), "vat_amount": round(vat, 2),
                "total_amount": round(base + vat, 2),
                "discount_amount": (round(e["discount_amount"], 2) if e["has_discount"] else None),
                "note": e["note"], "store_code": e["store_code"],
                "sales_invoice": si.name if si else None,
                "match_note": ("khớp %s" % si.name) if si else "chưa khớp hóa đơn ERPNext",
                "source_row": e["source_row"],
            })

        total_base = sum(l["amount_before_vat"] for l in lines)
        total_vat = sum(l["vat_amount"] for l in lines)
        if term["mode"] == MODE_PER_LINE:
            disc_base = sum(flt(l["discount_amount"]) for l in lines)
        else:
            disc_base = total_base * flt(rate) / 100.0
        disc_vat = disc_base * vat_rate / 100.0

        if mismatch:
            warnings.append(
                "Nhóm %s: %d hóa đơn có doanh số chuỗi báo LỆCH với hóa đơn của mình "
                "(ví dụ HĐ %s: chuỗi %s đ vs mình %s đ). Truy hàng trả / móp lỗi / hóa "
                "đơn điều chỉnh trước khi xuất chiết khấu."
                % (g["key"], len(mismatch), mismatch[0]["inv_no"],
                   "{:,.0f}".format(mismatch[0]["chain"]), "{:,.0f}".format(mismatch[0]["ours"])))

        plan.append({
            "group_key": g["key"],
            "group_label": g.get("group_label"),
            "chain": chain, "company": company,
            "customer": buyer["customer"], "store": buyer["store"],
            "address": buyer["address"], "buyer_name": buyer["buyer_name"],
            "buyer_tax_id": buyer["buyer_tax_id"], "buyer_address": buyer["buyer_address"],
            "mode": term["mode"], "rate": flt(rate), "rate_source": rate_src,
            "vat_rate": vat_rate,
            "discount_term": term["name"], "term_is_default": term["is_default_row"],
            "period_label": period_label, "sheet_date": sheet_date,
            "source_file": filename,
            "n_lines": len(lines), "n_matched": n_matched, "n_mismatch": len(mismatch),
            "total_base": round(total_base, 2), "total_vat": round(total_vat, 2),
            "total_gross": round(total_base + total_vat, 2),
            "discount_base": round(disc_base, 2), "discount_vat": round(disc_vat, 2),
            "discount_gross": round(disc_base + disc_vat, 2),
            "lines": lines,
            "existing": _existing_sheet(chain, buyer["customer"], period_label, company),
        })

    if blocked:
        warnings.append(
            "%d nhóm KHÔNG lập được bảng kê vì chưa xác định được bên mua (%s đ). "
            "Bảng kê là chứng từ hai bên ký — không lập với bên mua trống."
            % (len(blocked), "{:,.0f}".format(sum(b["base_amount"] for b in blocked))))
    return plan, blocked, warnings


def _existing_sheet(chain, customer, period_label, company):
    """Bảng kê CÙNG (chuỗi, khách, kỳ) đã có chưa — chặn lập trùng."""
    if not period_label:
        return None
    return frappe.db.get_value("MT Discount Sheet", {
        "chain": chain, "customer": customer,
        "period_label": period_label, "company": company,
    }, "name")


def _plan_hash(plan):
    h = hashlib.sha1()
    for p in plan:
        h.update("S|{}|{}|{}|{:.2f}|{:.2f}\n".format(
            p["group_key"], p["customer"], p["period_label"] or "",
            flt(p["total_base"]), flt(p["discount_base"])).encode())
        for l in p["lines"]:
            h.update("L|{}|{}|{:.2f}\n".format(
                l["inv_series"] or "", l["inv_no"] or "",
                flt(l["amount_before_vat"])).encode())
    return h.hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# Whitelisted
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def preview_sheets(content, chain=None, period_label=None, sheet_date=None,
                   filename=None, company=None):
    """XEM TRƯỚC các bảng kê dựng được từ file doanh số. KHÔNG ghi gì."""
    guard_mt()
    _require_tables()
    company = _company(company)

    parsed = read_discount_basis(content, chain=chain)
    sheet_date = cstr(sheet_date or today())
    plan, blocked, warnings = _build_plan(
        parsed, company, norm_text(period_label), sheet_date, norm_text(filename))

    return {
        "chain": parsed["chain"],
        "chain_key": parsed["chain_key"],
        "mode": parsed["mode"],
        "mode_label": parsed["mode_label"],
        "file_rate": parsed.get("rate"),
        "reconciled": parsed["reconciled"],
        "checks": parsed["checks"],
        "excluded": parsed["excluded"],
        "basis_totals": parsed["totals"],
        "plan_hash": _plan_hash(plan),
        "sheets": [{k: v for k, v in p.items() if k != "lines"} | {"sample": p["lines"][:30],
                                                                   "n_lines": len(p["lines"])}
                   for p in plan],
        "blocked": blocked,
        "warnings": warnings,
        "can_commit": bool(plan) and not any(p["existing"] for p in plan),
        "note": _(
            "Bảng kê được tạo ở trạng thái 'Nháp' và CHƯA ăn số. Số bảng kê "
            "(NNN/BKCK/HG-MT) chỉ được cấp khi bấm CHỐT — bảng kê nháp bị xóa mà đã ăn "
            "số là dãy thủng lỗ."
        ),
    }


@frappe.whitelist()
def commit_sheets(content, chain=None, period_label=None, sheet_date=None,
                  filename=None, expected_hash=None, company=None):
    """Tạo `MT Discount Sheet` ở trạng thái NHÁP. Chưa cấp số, chưa xuất hóa đơn."""
    guard_manager()
    _require_tables()
    company = _company(company)

    parsed = read_discount_basis(content, chain=chain)
    sheet_date = cstr(sheet_date or today())
    plan, blocked, warnings = _build_plan(
        parsed, company, norm_text(period_label), sheet_date, norm_text(filename))

    if not plan:
        frappe.throw(_("Không dựng được bảng kê nào từ file này"))
    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới lập bảng kê được"))
    if _plan_hash(plan) != expected_hash:
        frappe.throw(_(
            "Dữ liệu đã đổi kể từ lúc xem trước (điểm siêu thị, điều khoản hoặc hóa đơn "
            "đã thay đổi). Xem lại rồi lập — không ghi gì cả."
        ))
    dup = [p for p in plan if p["existing"]]
    if dup:
        frappe.throw(_("Đã có bảng kê cho kỳ này: {0}. Xóa bản cũ trước nếu muốn lập lại.")
                     .format(", ".join(p["existing"] for p in dup)))

    created, failed = [], []
    for i, p in enumerate(plan):
        sp = "mt_bkck_%d" % i
        try:
            frappe.db.savepoint(sp)
            doc = frappe.new_doc(SOURCE_DT)
            for f in ("chain", "company", "customer", "store", "address", "buyer_name",
                      "buyer_tax_id", "buyer_address", "mode", "rate", "vat_rate",
                      "discount_term", "period_label", "sheet_date", "source_file"):
                doc.set(f, p[f])
            doc.status = STATUS_DRAFT
            for l in p["lines"]:
                doc.append("lines", {
                    "inv_series": l["inv_series"], "inv_no": l["inv_no"],
                    "inv_date": l["inv_date"],
                    "amount_before_vat": l["amount_before_vat"],
                    "vat_amount": l["vat_amount"],
                    "discount_amount": l["discount_amount"],
                    "note": l["note"], "store_code": l["store_code"],
                    "sales_invoice": l["sales_invoice"],
                    "match_note": l["match_note"], "source_row": l["source_row"],
                })
            doc.insert()
            created.append({"name": doc.name, "customer": doc.customer,
                            "n_lines": len(doc.lines),
                            "discount_gross": flt(doc.discount_gross)})
        except Exception as e:                                   # noqa: BLE001
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:                                    # noqa: BLE001
                pass
            frappe.log_error(frappe.get_traceback(), "ketoan: mt_discount.commit_sheets")
            failed.append({"group_key": p["group_key"], "error": cstr(e)[:300]})

    frappe.db.commit()
    return {
        "created": created, "failed": failed, "blocked": blocked, "warnings": warnings,
        "message": _("Đã lập {0} bảng kê NHÁP. Chưa ăn số — bấm CHỐT từng bảng kê để cấp số.")
                   .format(len(created)),
    }


@frappe.whitelist()
def list_sheets(from_date=None, to_date=None, chain=None, status=None, customer=None,
                search=None, page=1, page_size=20, company=None):
    """Danh sách bảng kê chiết khấu, có lọc + chia trang."""
    guard_mt()
    _require_tables()
    company = _company(company)

    page = max(1, cint(page) or 1)
    page_size = min(100, max(1, cint(page_size) or 20))
    where = ["s.company = %(company)s"]
    params = {"company": company}
    if from_date and to_date:
        where.append("s.sheet_date BETWEEN %(fd)s AND %(td)s")
        params["fd"], params["td"] = from_date, to_date
    if chain:
        where.append("s.chain = %(chain)s")
        params["chain"] = chain
    if status:
        where.append("s.status = %(status)s")
        params["status"] = status
    if customer:
        where.append("s.customer = %(customer)s")
        params["customer"] = customer
    if search:
        where.append("(s.name LIKE %(q)s OR IFNULL(s.sheet_no,'') LIKE %(q)s "
                     "OR IFNULL(s.buyer_name,'') LIKE %(q)s "
                     "OR IFNULL(s.discount_invoice_no,'') LIKE %(q)s)")
        params["q"] = "%" + cstr(search).strip() + "%"
    clause = " AND ".join(where)

    head = frappe.db.sql("""
        SELECT COUNT(*) AS n, IFNULL(SUM(s.discount_gross), 0) AS amount
        FROM `tabMT Discount Sheet` s WHERE """ + clause, params, as_dict=True)[0]

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = frappe.db.sql("""
        SELECT s.name, s.sheet_no, s.sheet_date, s.chain, s.customer, s.buyer_name,
               s.buyer_tax_id, s.period_label, s.status, s.mode, s.rate, s.vat_rate,
               s.total_base, s.discount_base, s.discount_vat, s.discount_gross,
               s.discount_invoice_series, s.discount_invoice_no, s.discount_invoice_date,
               IFNULL(s.je_state, 'Chưa sinh') AS je_state,
               (SELECT COUNT(*) FROM `tabMT Discount Sheet Line` l
                 WHERE l.parent = s.name AND l.parenttype = 'MT Discount Sheet') AS n_lines
        FROM `tabMT Discount Sheet` s
        WHERE {clause}
        ORDER BY s.sheet_date DESC, s.creation DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """.format(clause=clause), params, as_dict=True)

    total = cint(head.n)
    return {
        "rows": rows, "total": total, "total_amount": flt(head.amount),
        "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 1,
        "statuses": [STATUS_DRAFT, STATUS_FINAL, STATUS_INVOICED],
        "chains": sorted(DISCOUNT_CHAIN_LABEL.values()),
        "can_manage": is_chief(),
    }


@frappe.whitelist()
def get_sheet(name, company=None):
    """Chi tiết MỘT bảng kê — để soi và để in."""
    guard_mt()
    _require_tables()
    company = _company(company)

    doc = frappe.get_doc(SOURCE_DT, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bảng kê {0} thuộc công ty khác").format(name))
    return {
        "doc": doc.as_dict(),
        "lines": [l.as_dict() for l in doc.lines or []],
        "can_manage": is_chief(),
        "print_url": "/api/method/frappe.utils.print_format.download_pdf"
                     "?doctype=MT%%20Discount%%20Sheet&name=%s&format=BKCK%%20MT" % doc.name,
    }


@frappe.whitelist()
def finalize_sheet(name, sheet_date=None, company=None):
    """CHỐT bảng kê -> cấp số `NNN/BKCK/HG-MT` và khóa lại để đem đi ký.

    Số chỉ cấp ở đây, không cấp lúc tạo nháp: nháp bị xóa mà đã ăn số là dãy
    thủng lỗ, và kiểm toán sẽ hỏi vì sao thiếu số.
    """
    guard_manager()
    _require_tables()
    company = _company(company)

    doc = frappe.get_doc(SOURCE_DT, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bảng kê {0} thuộc công ty khác").format(name))
    if doc.status != STATUS_DRAFT:
        frappe.throw(_("Bảng kê {0} đã ở trạng thái '{1}' — không chốt lại được")
                     .format(doc.sheet_no or name, doc.status))
    if sheet_date:
        doc.sheet_date = getdate(sheet_date)
    doc.status = STATUS_FINAL
    doc.save()
    frappe.db.commit()
    return {"name": doc.name, "sheet_no": doc.sheet_no, "status": doc.status,
            "message": _("Đã chốt bảng kê số {0}.").format(doc.sheet_no)}


@frappe.whitelist()
def set_invoice(name, invoice_no, invoice_series=None, invoice_date=None, company=None):
    """Ghi SỐ HÓA ĐƠN CHIẾT KHẤU đã xuất trên MISA về bảng kê (§3.5 SOP)."""
    guard_manager()
    _require_tables()
    company = _company(company)

    doc = frappe.get_doc(SOURCE_DT, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bảng kê {0} thuộc công ty khác").format(name))
    if doc.status == STATUS_DRAFT:
        frappe.throw(_("Chốt bảng kê trước rồi mới ghi số hóa đơn — hóa đơn chiết khấu "
                       "phải dẫn chiếu số bảng kê."))
    if not norm_text(invoice_no):
        frappe.throw(_("Chưa nhập số hóa đơn chiết khấu"))

    doc.discount_invoice_no = norm_text(invoice_no)
    doc.discount_invoice_series = norm_text(invoice_series)
    doc.discount_invoice_date = getdate(invoice_date) if invoice_date else doc.sheet_date
    doc.status = STATUS_INVOICED
    doc.save()
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status,
            "discount_invoice_no": doc.discount_invoice_no,
            "message": _("Đã ghi hóa đơn chiết khấu {0} cho bảng kê {1}.")
                       .format(doc.discount_invoice_no, doc.sheet_no)}


# ═══════════════════════════════════════════════════════════════════════════
# BÚT TOÁN CHIẾT KHẤU (§3.5 SOP, bước cuối)
#
#     Nợ 5211 (chiết khấu) + Nợ 33311 (thuế GTGT đầu ra được giảm)
#     Có 131 — MỘT dòng tổng cho pháp nhân ký bảng kê
#
# Tài khoản lấy từ `MT Account Map`, sự kiện 'Chiết khấu mình xuất'. Vẫn NHÁP:
# ràng buộc P0 'không ghi sổ' áp cho cả chiều chiết khấu, con người duyệt ở tab
# 'Duyệt bút toán' (MT2-E) — chung một chỗ với bút toán thanh toán.
# ═══════════════════════════════════════════════════════════════════════════

JE_KIND = "Chiết khấu"


def _je_plan(doc):
    """Kế hoạch bút toán của MỘT bảng kê chiết khấu. THUẦN ĐỌC."""
    from ketoan.api.mt_je import _existing_je, _fingerprint
    from ketoan.mt.doctype.mt_account_map.mt_account_map import EVENT_DISCOUNT
    from ketoan.mt.doctype.mt_account_map.mt_account_map import resolve as resolve_accounts

    if doc.status == STATUS_DRAFT:
        frappe.throw(_(
            "Bảng kê {0} còn là NHÁP (chưa ăn số). Chốt bảng kê trước rồi mới sinh bút "
            "toán — bút toán phải dẫn chiếu số bảng kê."
        ).format(doc.name))

    base = flt(doc.discount_base)
    vat = flt(doc.discount_vat)
    if not base:
        frappe.throw(_("Bảng kê {0} có số tiền chiết khấu bằng 0").format(doc.sheet_no))
    if not doc.customer:
        frappe.throw(_("Bảng kê {0} chưa có khách hàng — dòng 131 không có đối tượng")
                     .format(doc.sheet_no))

    acc = resolve_accounts(EVENT_DISCOUNT, doc.chain, doc.company)
    if vat and not acc.get("tax_account"):
        # Thuế GTGT của hóa đơn chiết khấu dồn vào TK chiết khấu là ghi thuế
        # thành chi phí — sai bản chất và mất khấu trừ.
        frappe.throw(_(
            "Bảng kê {0} có {1} đ thuế GTGT nhưng MT Account Map của sự kiện '{2}' chưa "
            "khai TK Nợ thuế. Khai rồi làm lại."
        ).format(doc.sheet_no, "{:,.0f}".format(vat), EVENT_DISCOUNT))

    posting_date = cstr(doc.discount_invoice_date or doc.sheet_date)
    debit = [{"account": acc["debit_account"], "amount": base, "label": "Chiết khấu"}]
    if vat:
        debit.append({"account": acc["tax_account"], "amount": vat, "label": "Thuế GTGT"})

    total = base + vat
    entry = {
        "kind": JE_KIND, "event": EVENT_DISCOUNT, "accounts": acc,
        "posting_date": posting_date, "total": total,
        "debit_lines": debit,
        "credit_lines": [{
            "account": acc["credit_account"], "amount": total,
            "party_type": "Customer", "party": doc.customer,
            "party_name": doc.buyer_name,
            "reference_type": None, "reference_name": None,
            "n_rows": len(doc.lines or []),
        }],
        "remark": _je_remark(doc),
        "n_review": 0,
        "note_no_reference": (
            "Bút toán gộp theo BẢNG KÊ: giảm số dư 131 của khách, KHÔNG giảm outstanding "
            "của từng hóa đơn. Danh sách hóa đơn nằm trong diễn giải và trên bảng kê."),
        "fingerprint": _fingerprint(doc.name, JE_KIND, posting_date, total,
                                    source_dt=SOURCE_DT),
    }
    entry["duplicate"] = _existing_je(entry["fingerprint"])
    return entry


def _je_remark(doc):
    """Diễn giải — phải tra ngược được về bảng kê và hóa đơn mà không mở gì thêm."""
    head = " · ".join(x for x in (
        "Chiết khấu %s" % (doc.chain or ""),
        "bảng kê số %s" % (doc.sheet_no or doc.name),
        ("kỳ %s" % doc.period_label) if doc.period_label else "",
        ("ngày %s" % cstr(doc.sheet_date)) if doc.sheet_date else "",
    ) if x)
    lines = [head, "Bên mua: %s%s" % (doc.buyer_name or doc.customer,
                                      " · MST %s" % doc.buyer_tax_id if doc.buyer_tax_id else "")]
    if doc.discount_invoice_no:
        lines.append("Hóa đơn chiết khấu: %s%s" % (
            (doc.discount_invoice_series + " ") if doc.discount_invoice_series else "",
            doc.discount_invoice_no))
    else:
        lines.append("CHƯA có số hóa đơn chiết khấu — ghi số vào bảng kê sau khi xuất trên MISA.")
    lines.append("Cách tính: %s%s · doanh số %s đ · thuế %s%%" % (
        doc.mode, (" %s%%" % doc.rate) if flt(doc.rate) else "",
        "{:,.0f}".format(flt(doc.total_base)), doc.vat_rate))
    lines.append("Gồm %d hóa đơn:" % len(doc.lines or []))
    for l in (doc.lines or [])[:60]:
        lines.append("  • %s%s (%s): %s đ%s" % (
            (l.inv_series + " ") if l.inv_series else "", l.inv_no,
            cstr(l.inv_date or ""), "{:,.0f}".format(flt(l.amount_before_vat)),
            (" · PO %s" % l.note) if l.note else ""))
    if len(doc.lines or []) > 60:
        lines.append("  • …và %d hóa đơn nữa (xem bảng kê %s)"
                     % (len(doc.lines) - 60, doc.sheet_no or doc.name))
    return "\n".join(lines)


@frappe.whitelist()
def preview_journal_entry(name, company=None):
    """XEM TRƯỚC bút toán chiết khấu của MỘT bảng kê. KHÔNG ghi gì."""
    guard_mt()
    _require_tables()
    company = _company(company)

    doc = frappe.get_doc(SOURCE_DT, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bảng kê {0} thuộc công ty khác").format(name))
    entry = _je_plan(doc)
    return {
        "sheet": doc.name, "sheet_no": doc.sheet_no, "chain": doc.chain,
        "customer": doc.customer, "status": doc.status,
        "je_state": doc.je_state or "Chưa sinh",
        "plan_hash": hashlib.sha1(entry["fingerprint"].encode()).hexdigest(),
        "entries": [entry],
        "can_create": not entry["duplicate"] and is_chief(),
        "note": _("Bút toán sinh ở trạng thái NHÁP. Duyệt ở tab 'Duyệt bút toán'."),
    }


@frappe.whitelist()
def create_journal_entry(name, expected_hash=None, company=None):
    """Sinh Journal Entry NHÁP cho bảng kê chiết khấu. KHÔNG submit."""
    guard_manager()
    _require_tables()
    company = _company(company)

    from ketoan.api.mt_je import _set_je_state
    from ketoan.utils import je_remark_field

    doc = frappe.get_doc(SOURCE_DT, name)
    if cstr(doc.company) != cstr(company):
        frappe.throw(_("Bảng kê {0} thuộc công ty khác").format(name))
    entry = _je_plan(doc)

    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới sinh bút toán được"))
    if hashlib.sha1(entry["fingerprint"].encode()).hexdigest() != expected_hash:
        frappe.throw(_("Bảng kê đã đổi kể từ lúc xem trước. Xem lại rồi sinh — "
                       "không ghi gì cả."))
    if entry["duplicate"]:
        return {"created": [], "skipped_duplicate": [entry["duplicate"]],
                "je_state": doc.je_state,
                "message": _("Bút toán {0} đã sinh rồi — không sinh lại.")
                           .format(entry["duplicate"])}

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = entry["posting_date"]
    je.set(je_remark_field(), entry["remark"])
    je.custom_mt_source_dt = SOURCE_DT
    je.custom_mt_source_name = doc.name
    je.custom_mt_kind = JE_KIND
    je.custom_mt_fingerprint = entry["fingerprint"]
    for ln in entry["debit_lines"]:
        je.append("accounts", {"account": ln["account"],
                               "debit_in_account_currency": flt(ln["amount"])})
    for ln in entry["credit_lines"]:
        je.append("accounts", {"account": ln["account"],
                               "credit_in_account_currency": flt(ln["amount"]),
                               "party_type": ln["party_type"], "party": ln["party"]})
    # NHÁP. Không submit, không ignore_permissions — bút toán tạo dưới quyền
    # người bấm, đúng ràng buộc P0.
    je.insert()
    state = _set_je_state(doc.name, SOURCE_DT)
    frappe.db.commit()
    return {
        "created": [{"name": je.name, "kind": JE_KIND, "total": flt(entry["total"])}],
        "skipped_duplicate": [], "je_state": state,
        "message": _("Đã sinh bút toán NHÁP {0}. Chưa ghi sổ — duyệt ở tab 'Duyệt bút toán'.")
                   .format(je.name),
    }
