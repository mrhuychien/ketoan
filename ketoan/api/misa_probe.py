"""misa_probe — công cụ DÒ endpoint MISA. Chỉ đọc, không ghi gì.

Lý do tồn tại: ràng buộc 13.5 của pack cấm đoán tên field response. Còn 3 chỗ
chưa xác minh (§I của misa_api_contract.md): chi tiết hóa đơn sau phát hành,
danh sách hóa đơn trên bề mặt API, và bảng kê đã sử dụng.

Chạy trên site thật để lấy hình dạng response, rồi mới viết code đọc chúng.

    bench --site <site> execute ketoan.api.misa_probe.run --kwargs "{'ref_id': '<refid>'}"

Đầu ra ĐÃ CHE dữ liệu: chỉ in tên field, kiểu, và mẫu giá trị đã rút gọn/che.
Không in credential, không in token, không ghi bất cứ thứ gì vào database.
"""

import json

import frappe

from ketoan.api.misa_client import MISAError, _pick, call, get_settings

# Field mang thông tin định danh — che giá trị khi in.
SENSITIVE = {
    "accountobjectname", "accountobjectaddress", "receiveremail", "receivername",
    "receivermobile", "contactname", "accountobjecttaxcode", "buyertaxcode",
    "accountobjectcode", "username", "password", "access_token", "token",
}


def _mask(key, value):
    """Rút gọn giá trị để in. Che field định danh, cắt chuỗi dài."""
    k = str(key).lower()
    if isinstance(value, (dict, list)):
        return f"<{type(value).__name__} {len(value)} phần tử>"
    if value is None:
        return "None"
    if k in SENSITIVE:
        s = str(value)
        return f"<che, dài {len(s)}>"
    s = str(value)
    return s if len(s) <= 48 else s[:45] + "…"


def _shape(obj, label="", depth=0):
    """In cấu trúc 1 object: tên field, kiểu, mẫu giá trị đã che."""
    pad = "  " * depth
    if isinstance(obj, list):
        print(f"{pad}{label}: mảng {len(obj)} phần tử")
        if obj:
            _shape(obj[0], "[0]", depth + 1)
        return
    if not isinstance(obj, dict):
        print(f"{pad}{label}: {type(obj).__name__} = {_mask(label, obj)}")
        return
    print(f"{pad}{label}: object {len(obj)} field")
    for k, v in obj.items():
        t = type(v).__name__
        if isinstance(v, dict):
            _shape(v, k, depth + 1)
        elif isinstance(v, list):
            print(f"{pad}  {k:32s} mảng[{len(v)}]")
            if v and isinstance(v[0], dict):
                _shape(v[0], f"{k}[0]", depth + 2)
        else:
            print(f"{pad}  {k:32s} {t:8s} {_mask(k, v)}")


def _try(label, path, payload=None, params=None, method="POST", form=False):
    """Gọi thử 1 endpoint, in kết quả. Lỗi thì in lỗi chứ không dừng cả lượt dò."""
    print("\n" + "═" * 78)
    print(f"THỬ  {label}")
    print(f"     {method} /api/v2/{path}")
    if payload is not None:
        preview = payload if isinstance(payload, dict) else f"<{type(payload).__name__}>"
        print(f"     payload: {json.dumps(preview, ensure_ascii=False)[:200]}")
    print("═" * 78)
    try:
        data = call(path, payload=payload, params=params, method=method, form=form)
    except MISAError as e:
        print(f"  ✗ MISAError [{e.code}] {e.message}")
        return None
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")
        return None
    print("  ✓ gọi được")
    _shape(data, "kết quả", 1)
    return data


def run(ref_id=None, from_date=None, to_date=None):
    """Dò các endpoint còn thiếu. Truyền ref_id lấy từ 1 hóa đơn đã phát hành trên MISA."""
    s = get_settings()
    print(f"base_url      : {(s.base_url_webapp or '').rstrip('/')}")
    print(f"MST           : {(s.taxcode or '')[:4]}…")
    print(f"hóa đơn có mã : {bool(s.use_code_route)}")
    print(f"có AppID      : {s.has_appid()}")

    prefix = "code/" if s.use_code_route else ""

    if ref_id:
        _try("U3 — chi tiết hóa đơn sau phát hành",
             f"{prefix}v3sainvoice/afterpublishing/{ref_id}", method="GET")
        if prefix:
            _try("U3b — thử KHÔNG có tiền tố code/",
                 f"v3sainvoice/afterpublishing/{ref_id}", method="GET")
    else:
        print("\n⚠ Bỏ qua U3: chưa truyền ref_id. Lấy 1 RefID của hóa đơn đã phát hành trên MISA.")

    frm = from_date or frappe.utils.add_days(frappe.utils.nowdate(), -7)
    to = to_date or frappe.utils.nowdate()
    paging = {
        "start": 0,
        "length": 2,
        "fromDate": f'"{frm}T00:00:00.000Z"',
        "toDate": f'"{to}T23:59:59.000Z"',
    }

    _try("danh sách hóa đơn trên bề mặt API",
         f"{prefix}v3sainvoice/paging", payload=paging, form=True)
    _try("bảng kê hóa đơn đã sử dụng",
         "v3report/ipusedamount/paging", payload=paging, form=True)
    _try("tài nguyên hóa đơn còn lại",
         "resource/GetTotalUsedInvoiceQuantityByInvTemplate",
         params={"invTemplateNo": s.inv_template_no or "1",
                 "invSeries": (s.series_list() or [""])[0]},
         method="GET")

    print("\n" + "═" * 78)
    print("Xong. Chép TOÀN BỘ output ở trên gửi lại — giá trị đã được che sẵn.")
    print("═" * 78)


# ═══════════════════════════════════════════════════════════════════════════
# Soi bố cục form Sales Invoice — dùng khi nghi field bị nuốt vào section MISA
# ═══════════════════════════════════════════════════════════════════════════

def show_si_layout(around="custom_misa_section", context=40):
    """In thứ tự field THẬT của Sales Invoice quanh section MISA.

        bench --site <site> execute ketoan.api.misa_probe.show_si_layout

    Section Break thu gọn nuốt mọi field đứng sau nó. Nếu thấy nhóm thông tin
    xuất hóa đơn nằm SAU `custom_misa_section` thì đó chính là chỗ chúng "biến mất".
    """
    meta = frappe.get_meta("Sales Invoice")
    fields = list(meta.fields)
    names = [df.fieldname for df in fields]

    if around not in names:
        print(f"⚠ Không tìm thấy {around} trên form. Đã chạy migrate chưa?")
        return

    pos = names.index(around)
    lo, hi = max(0, pos - context), min(len(fields), pos + context + 1)

    print(f"Sales Invoice có {len(fields)} field. Đang xem quanh {around} (vị trí {pos + 1}).\n")
    section = ""
    for i in range(lo, hi):
        df = fields[i]
        if df.fieldtype in ("Section Break", "Tab Break"):
            section = df.label or df.fieldname
        mark = "  ◀── SECTION MISA BẮT ĐẦU TỪ ĐÂY" if df.fieldname == around else ""
        cue = ">>" if i > pos and not df.fieldname.startswith("custom_misa") else "  "
        print(f" {cue} {i + 1:3d}. {df.fieldtype:14s} {df.fieldname:34s} [{section[:24]}]{mark}")

    after = [df.fieldname for df in fields[pos + 1:] if not df.fieldname.startswith("custom_misa")]
    print()
    if after:
        print(f"🚨 CÓ {len(after)} field KHÔNG thuộc nhóm MISA nằm SAU section MISA — bị nuốt vào phần thu gọn:")
        for n in after:
            print(f"     · {n}")
        print("\n   Sửa: bench --site <site> execute ketoan.install.repair_misa_field_order")
    else:
        print("✅ Không field nào bị nuốt — section MISA nằm ở cuối form, đúng vị trí.")

    cf = frappe.db.get_value(
        "Custom Field", "Sales Invoice-custom_misa_section", ["insert_after", "collapsible"], as_dict=True
    )
    print(f"\nCustom Field custom_misa_section: insert_after={cf and cf.insert_after!r} collapsible={cf and cf.collapsible}")


# ═══════════════════════════════════════════════════════════════════════════
# Chẩn đoán rổ "Chỉ có trên MISA" — vì sao chưa có hóa đơn nào
# ═══════════════════════════════════════════════════════════════════════════

def diagnose_vat(from_date=None, to_date=None):
    """Trả lời một lượt: đã đồng bộ chưa, kéo được bao nhiêu, endpoint có ăn không.

        bench --site <site> execute ketoan.api.misa_probe.diagnose_vat

    Thử 3 biến thể tham số của endpoint danh sách để biết biến thể nào ăn —
    endpoint này là thứ DUY NHẤT chưa xác minh trong cả luồng (§M.6).
    Chỉ ĐỌC, không ghi gì vào database.
    """
    from ketoan.api.misa_sync import PAGING_BASE, PAGING_COLUMNS, _paging_call

    to_date = to_date or frappe.utils.nowdate()
    from_date = from_date or frappe.utils.add_months(to_date, -1)
    s = get_settings()

    print("═" * 78)
    print("1. DỮ LIỆU ĐANG CÓ TRONG DATABASE")
    print("═" * 78)
    total = frappe.db.count("MISA Invoice Snapshot")
    print(f"   MISA Invoice Snapshot : {total} bản ghi")
    if total:
        rng = frappe.db.sql(
            "SELECT MIN(inv_date) a, MAX(inv_date) b FROM `tabMISA Invoice Snapshot`", as_dict=True)[0]
        unlinked = frappe.db.count("MISA Invoice Snapshot", {"sales_invoice": ("is", "not set")})
        print(f"   khoảng ngày           : {rng.a} → {rng.b}")
        print(f"   chưa nối Sales Invoice: {unlinked}")
    print(f"   khoảng đang xem       : {from_date} → {to_date}")

    print()
    print("═" * 78)
    print("2. CÁC LẦN ĐỒNG BỘ GẦN NHẤT")
    print("═" * 78)
    runs = frappe.get_all(
        "MISA Sync Run",
        fields=["name", "job_type", "status", "fetched", "created", "updated", "finished_at", "error_log"],
        order_by="creation desc", limit=5)
    if not runs:
        print("   ⚠ CHƯA CHẠY ĐỒNG BỘ LẦN NÀO → rổ trống là đúng.")
        print("     Bấm nút 'Đồng bộ MISA' trên trang, hoặc:")
        print("     bench --site <site> execute ketoan.api.misa_sync.pull_invoices")
    for r in runs:
        print(f"   {r.name}  {r.job_type:15s} {r.status:22s} kéo={r.fetched} mới={r.created} sửa={r.updated}")
        if r.error_log:
            for line in r.error_log.splitlines()[:4]:
                print(f"        ↳ {line[:150]}")

    print()
    print("═" * 78)
    print("3. THỬ ENDPOINT DANH SÁCH — 3 BIẾN THỂ THAM SỐ")
    print("═" * 78)
    prefix = "code/" if s.use_code_route else ""
    base = dict(PAGING_BASE)
    base.update({
        "draw": "1", "columns": PAGING_COLUMNS, "start": "0", "length": "5",
        "fromDate": f'"{from_date}T00:00:00.000Z"', "toDate": f'"{to_date}T23:59:59.000Z"',
    })

    full_filter = ('[{"FilterValue":6,"FilterOperator":"=","FilterType":"comboboxenum",'
                   '"FilterProperty":"PublishStatus","DisplayText":"Phát hành","enumname":"PublishStatus"}]')
    variants = [
        ("A · như code hiện tại (publishStatus=6, filter rỗng)", dict(base)),
        ("B · filter đầy đủ giống lưới thật", dict(base, **{"filter": full_filter})),
        ("C · lấy TẤT CẢ trạng thái (publishStatus=-1)", dict(base, **{"publishStatus": "-1"})),
    ]
    winner = None
    for label, payload in variants:
        print(f"\n   ── {label}")
        try:
            dropped = set()
            rows, meta = _paging_call(s, payload, dropped)
            if dropped:
                print(f"      (tự gỡ tham số MISA không nhận: {', '.join(sorted(dropped))})")
        except MISAError as e:
            print(f"      ✗ MISAError [{e.code}] {str(e.message)[:160]}")
            continue
        except Exception as e:
            print(f"      ✗ {type(e).__name__}: {str(e)[:160]}")
            continue
        total = _pick(meta, "recordsFiltered") or _pick(meta, "recordsTotal") or 0
        print(f"      → trang này {len(rows)} bản ghi · MISA khai tổng cộng {total}")
        if total and len(rows) < int(total or 0) and len(rows) < 5:
            print("        (bình thường — đang giới hạn length=5 để dò)")
        if rows:
            winner = winner or label
            r0 = rows[0]
            for k in ("InvSeries", "InvNo", "InvDate", "TotalAmount", "TotalAmountWithoutVAT", "TotalVATAmount"):
                print(f"         {k:24s} {r0.get(k)}")

    print()
    print("═" * 78)
    if winner:
        print(f"✅ Biến thể ĂN: {winner}")
        print("   Gửi lại dòng này cho em để chốt bộ tham số.")
    else:
        print("❌ Cả 3 biến thể đều trả 0 bản ghi.")
        print("   Endpoint danh sách trên bề mặt API không dùng được → cần đường khác.")
        print("   Gửi em nguyên output này.")
    print("═" * 78)
