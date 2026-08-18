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
        # KHÔNG nháy kép — đã xác minh nháy làm MISA trả rỗng (§P).
        "fromDate": f"{frm}T00:00:00.000Z",
        "toDate": f"{to}T23:59:59.000Z",
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
        "fromDate": f"{from_date}T00:00:00.000Z", "toDate": f"{to_date}T23:59:59.000Z",
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


# ═══════════════════════════════════════════════════════════════════════════
# raw — in PHẢN HỒI THÔ, bỏ toàn bộ tầng bóc tách của app ra khỏi phương trình
# ═══════════════════════════════════════════════════════════════════════════

def raw(path, payload=None, method="POST", form=1, chars=3000):
    """Gọi 1 endpoint MISA và in NGUYÊN VĂN phản hồi.

        bench --site <site> execute ketoan.api.misa_probe.raw \\
          --kwargs "{'path': 'code/v3sainvoice/paging', 'payload': {'start':'0','length':'2'}}"

    Khi kết quả không như mong đợi, đây là thứ phải xem TRƯỚC: nó loại bỏ mọi
    khả năng do _unwrap / parse_nested_data hiểu sai. In cả mã HTTP, header
    phản hồi, và thân phản hồi nguyên bản.

    KHÔNG in Authorization và không in credential.
    """
    import requests

    from ketoan.api.misa_client import _base_url, _taxcode, get_token

    s = get_settings()
    url = f"{_base_url(s)}/api/v2/{str(path).lstrip('/')}"
    headers = {"Authorization": get_token(), "TaxCode": _taxcode(s)}
    kwargs = {"headers": headers, "timeout": 60}
    if payload is not None:
        if int(form or 0):
            kwargs["data"] = payload
        else:
            headers["Content-Type"] = "application/json"
            kwargs["data"] = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    print(f"{method} {url}")
    print(f"header  : Authorization=<che>, TaxCode={_taxcode(s)}"
          + (f", Content-Type={headers.get('Content-Type')}" if headers.get("Content-Type") else ""))
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False)
        print(f"body    : {body[:800]}{'…' if len(body) > 800 else ''}")
    print("─" * 78)

    try:
        res = requests.request(str(method).upper(), url, **kwargs)
    except Exception as e:
        print(f"✗ {type(e).__name__}: {e}")
        return

    print(f"HTTP {res.status_code}  ·  {len(res.content)} byte  ·  {res.headers.get('Content-Type', '')}")
    print("─" * 78)
    text = res.text or ""
    print(text[:int(chars)])
    if len(text) > int(chars):
        print(f"\n… (còn {len(text) - int(chars)} ký tự)")
    print("─" * 78)
    print("Chép nguyên phần trên gửi lại. Nhớ che nếu có tên khách / MST.")


# ═══════════════════════════════════════════════════════════════════════════
# find_list_endpoint — dò đường dẫn nào trên /api/v2 trả được DANH SÁCH hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

# Quy ước đặt tên của MISA không nhất quán — đã xác minh 3 kiểu khác nhau:
#   GET  code/v3sainvoice/afterpublishing/{id}   → TIỀN TỐ code/
#   POST v3sainvoice/code                        → HẬU TỐ /code
#   POST v3/sainvoicewithcode/list  (bề mặt web) → tên gộp
# Nên không suy luận được đường danh sách, phải dò.
LIST_PATHS = [
    "code/v3sainvoice/paging",
    "v3sainvoice/paging",
    "code/v3sainvoice/list",
    "v3sainvoice/list",
    "sainvoicewithcode/list",
    "code/sainvoicewithcode/list",
    "v3sainvoicewithcode/paging",
    "v3sainvoicewithcode/list",
    "v3sainvoice/paging/code",
    "v3sainvoice/getpaging",
    "code/v3sainvoice/getpaging",
    "v3sainvoice/search",
]


def _probe_once(path, payload, form=True, method="POST"):
    """Gọi thô 1 lần, trả (http, so_ban_ghi, tong_khai, tom_tat)."""
    import requests

    from ketoan.api.misa_client import _base_url, _taxcode, get_token

    s = get_settings()
    url = f"{_base_url(s)}/api/v2/{path.lstrip('/')}"
    headers = {"Authorization": get_token(), "TaxCode": _taxcode(s)}
    kwargs = {"headers": headers, "timeout": 60}
    if payload is not None:
        if form:
            kwargs["data"] = payload
        else:
            headers["Content-Type"] = "application/json"
            kwargs["data"] = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        res = requests.request(method, url, **kwargs)
    except Exception as e:
        return None, None, None, f"{type(e).__name__}"

    if res.status_code != 200:
        return res.status_code, None, None, (res.text or "")[:110].replace("\n", " ")
    try:
        body = res.json()
    except Exception:
        return 200, None, None, "phản hồi không phải JSON"
    if not isinstance(body, dict):
        n = len(body) if isinstance(body, list) else None
        return 200, n, None, "trả thẳng mảng"

    err = _pick(body, "error", "dataError")
    if _pick(body, "success") is False or err:
        return 200, None, None, ("LỖI: " + str(err)[:110].replace("\n", " "))

    data = _pick(body, "data")
    rows = None
    if isinstance(data, list):
        rows = len(data)
    elif isinstance(data, str):
        try:
            parsed = json.loads(data) if data.strip() else []
            rows = len(parsed) if isinstance(parsed, list) else 1
        except Exception:
            rows = None
    total = _pick(body, "recordsFiltered") or _pick(body, "recordsTotal") or 0
    extra = ",".join(k for k in body if k.lower() in ("servertime", "summary", "resulttoken"))
    return 200, rows, total, extra


def find_list_endpoint(from_date=None, to_date=None):
    """Dò xem đường dẫn nào trả được danh sách hóa đơn. Chỉ đọc, không ghi.

        bench --site <site> execute ketoan.api.misa_probe.find_list_endpoint

    Vòng 1 quét đường dẫn với tham số tối thiểu. Vòng 2 chỉ chạy trên đường dẫn
    nào sống, thử các biến thể ngày/phạm vi.
    """
    import time as _t

    to_date = to_date or frappe.utils.nowdate()
    from_date = from_date or frappe.utils.add_days(to_date, -30)
    s = get_settings()

    print("═" * 92)
    print(f"VÒNG 1 — quét {len(LIST_PATHS)} đường dẫn với tham số tối thiểu (start/length)")
    print("═" * 92)
    print(f"{'đường dẫn':38s} {'HTTP':>5s} {'dòng':>6s} {'khai':>7s}  ghi chú")
    print("─" * 92)

    alive = []
    for p in LIST_PATHS:
        http, rows, total, note = _probe_once(p, {"start": "0", "length": "5"})
        mark = "  ← CÓ DỮ LIỆU" if rows else ""
        print(f"{p:38s} {str(http):>5s} {str(rows):>6s} {str(total):>7s}  {note}{mark}")
        if http == 200 and rows is not None:
            alive.append(p)
        _t.sleep(0.2)

    if not alive:
        print("\n❌ Không đường dẫn nào trả về cấu trúc danh sách. Bề mặt API này không có")
        print("   endpoint liệt kê hóa đơn → phải đi đường nhập file.")
        return

    print()
    print("═" * 92)
    print(f"VÒNG 2 — thử biến thể tham số trên {len(alive)} đường dẫn còn sống")
    print("═" * 92)

    variants = [
        ("chỉ start/length", {"start": "0", "length": "5"}),
        ("ngày KHÔNG nháy", {"start": "0", "length": "5",
                             "fromDate": f"{from_date}T00:00:00.000Z", "toDate": f"{to_date}T23:59:59.000Z"}),
        ("ngày CÓ nháy", {"start": "0", "length": "5",
                          "fromDate": f'"{from_date}T00:00:00.000Z"', "toDate": f'"{to_date}T23:59:59.000Z"'}),
        ("ngày trần yyyy-mm-dd", {"start": "0", "length": "5", "fromDate": from_date, "toDate": to_date}),
        ("kèm đơn vị + mẫu HĐ", {"start": "0", "length": "5",
                                 "lstOrganizationUnit": s.organization_unit_id or "",
                                 "invTemplate": s.inv_template_no or "1"}),
        ("gửi JSON thay vì form", {"start": 0, "length": 5}),
    ]
    for p in alive:
        print(f"\n── {p}")
        for label, payload in variants:
            form = label != "gửi JSON thay vì form"
            http, rows, total, note = _probe_once(p, payload, form=form)
            mark = "   ← CÓ DỮ LIỆU" if rows else ""
            print(f"   {label:24s} HTTP {str(http):>3s} · dòng {str(rows):>4s} · khai {str(total):>5s}  {note}{mark}")
            _t.sleep(0.2)

    print()
    print("═" * 92)
    print("Chép nguyên bảng trên gửi lại.")
    print("═" * 92)


# ═══════════════════════════════════════════════════════════════════════════
# Dò bảng giá trị enum trạng thái hóa đơn
# ═══════════════════════════════════════════════════════════════════════════

# Đúng thứ tự hai ô chọn trên màn hình MISA. Thứ tự này KHÔNG phải giá trị enum
# — MISA không đảm bảo mục thứ n mang giá trị n. Vì vậy mới phải dò từng giá
# trị rồi đối chiếu số dòng với chính lưới web, thay vì đoán theo thứ tự.
ENUM_LABELS = {
    "EInvoiceStatus": [
        "Chưa phát hành", "Đang phát hành", "Phát hành lỗi", "Chờ cấp mã",
        "Đã cấp mã", "Từ chối cấp mã", "TĐ không hợp lệ",
    ],
    "ReferenceType": [
        "Hóa đơn mới", "Hóa đơn thay thế", "Hóa đơn điều chỉnh",
        "Hóa đơn đã bị hủy", "Hóa đơn đã bị thay thế", "Hóa đơn đã bị điều chỉnh",
    ],
}


def _enum_filter(prop, value):
    return json.dumps([{
        "FilterValue": value, "FilterOperator": "=", "FilterType": "comboboxenum",
        "FilterProperty": prop, "DisplayText": "", "enumname": prop,
    }], ensure_ascii=False)


def find_status_enum(prop="EInvoiceStatus", from_date=None, to_date=None, hi=9):
    """Dò xem mỗi giá trị enum trạng thái ứng với bao nhiêu hóa đơn.

        bench --site <site> execute ketoan.api.misa_probe.find_status_enum \
            --kwargs "{'prop': 'EInvoiceStatus', 'from_date': '2026-01-01'}"

    Chỉ ĐỌC. Cách dùng kết quả: mở lưới hóa đơn trên MISA, lọc lần lượt từng
    mục trong ô chọn, ghi lại số dòng web báo, rồi so với bảng dưới đây. Giá
    trị nào ra ĐÚNG số đó chính là enum của mục đó — đây là bằng chứng, không
    phải suy đoán, nên mới được phép đưa vào code.
    """
    from ketoan.api.misa_sync import PAGING_COLUMNS
    from ketoan.api.misa_client import invoice_path

    s = get_settings()
    to_date = to_date or frappe.utils.nowdate()
    from_date = from_date or frappe.utils.add_days(to_date, -180)
    path = invoice_path("v3sainvoice/paging", s)

    print("═" * 78)
    print(f"DÒ ENUM {prop} · {from_date} → {to_date}")
    print(f"đường dẫn: {path}")
    labels = ENUM_LABELS.get(prop) or []
    if labels:
        print("mục trên màn hình MISA (thứ tự hiển thị, CHƯA phải giá trị enum):")
        for i, lb in enumerate(labels):
            print(f"    {i + 1}. {lb}")
    print("═" * 78)
    print(f"{'giá trị':>8} │ {'số dòng':>8} │ {'tổng khai':>10} │ ghi chú")
    print("─" * 78)

    base = {
        "draw": "1", "columns": PAGING_COLUMNS, "start": "0", "length": "1",
        "fromDate": f"{from_date}T00:00:00.000Z",
        "toDate": f"{to_date}T23:59:59.000Z",
    }
    http, rows, baseline, note = _probe_once(path, dict(base))
    print(f"{'(không lọc)':>8} │ {str(rows):>8} │ {str(baseline):>10} │ {note or ''}")
    print("─" * 78)

    found = {}
    for v in range(0, int(hi) + 1):
        payload = dict(base, **{"filter": _enum_filter(prop, v)})
        http, rows, total, note = _probe_once(path, payload)
        mark = ""
        if http != 200:
            mark = f"HTTP {http}"
        elif total and total != baseline:
            found[v] = total
            mark = "← lọc CÓ tác dụng"
        elif total == baseline:
            mark = "= y hệt lượt không lọc"
        print(f"{v:>8} │ {str(rows):>8} │ {str(total):>10} │ {note or ''} {mark}")

    print("═" * 78)
    if not found:
        # Mọi giá trị ra ĐÚNG tổng của lượt không lọc — kể cả giá trị không có
        # trong ô chọn. Đó là bằng chứng `filter` bị BỎ QUA, tuyệt đối không
        # phải bằng chứng "trạng thái nào cũng có ngần ấy hóa đơn".
        print("Mọi giá trị đều ra đúng tổng của lượt KHÔNG lọc ⇒ tham số `filter`")
        print("bị bề mặt API BỎ QUA. Không suy ra được gì về enum từ đây.")
        print()
        print("Dùng cách khác — kéo dữ liệu thật rồi đối chiếu, không cần lọc:")
        print("    bench --site <site> execute ketoan.api.misa_probe.cross_status \\")
        print(f"        --kwargs \"{{'from_date': '{from_date}', 'pages': 5}}\"")
    else:
        print("Giá trị lọc có tác dụng:", ", ".join(f"{k} ({v} hóa đơn)" for k, v in found.items()))
        print("Đối chiếu số này với số dòng lưới web báo khi lọc từng mục.")
        print("Khớp thì mới ghi vào misa_api_contract.md rồi mới được code.")
    return found


def cross_status(from_date=None, to_date=None, pages=5, prop="EInvoiceStatus", spread=1):
    """Lập bảng chéo trạng thái ↔ dữ liệu THẬT, kèm số hóa đơn để tra tay.

        bench --site <site> execute ketoan.api.misa_probe.cross_status \
            --kwargs "{'from_date': '2026-01-01', 'pages': 5}"

    Vì sao không dùng `find_status_enum` nữa: tham số `filter` bị bề mặt API
    BỎ QUA — mọi giá trị, kể cả 8 và 9 vốn không có trong ô chọn, đều trả về
    đúng tổng của lượt không lọc. Lọc không có tác dụng thì không suy ra được
    gì từ nó.

    Cách này không cần lọc: kéo hóa đơn thật về rồi đối chiếu từng giá trị
    enum với những thứ ĐÃ xác minh — có mã CQT chưa (`InvoiceCode`, 34 ký tự
    HEX, §H.3), đã cấp số chưa (`InvNo`) — và in kèm vài số hóa đơn mẫu.

    Mở MISA, tra đúng những số hóa đơn đó, đọc trạng thái màn hình hiện. Đó là
    bằng chứng trực tiếp cho từng giá trị enum. Chỉ ĐỌC, không ghi gì.
    """
    from ketoan.api.misa_client import invoice_path
    from ketoan.api.misa_sync import (
        MAX_PAGES, PAGE_SIZE, PAGING_BASE, PAGING_COLUMNS, _paging_call,
    )

    s = get_settings()
    to_date = to_date or frappe.utils.nowdate()
    from_date = from_date or frappe.utils.add_days(to_date, -180)
    pages = min(int(pages or 5), MAX_PAGES)
    path = invoice_path("v3sainvoice/paging", s)

    print("═" * 78)
    print(f"BẢNG CHÉO {prop} · {from_date} → {to_date} · tối đa {pages} trang")
    print("═" * 78)

    buckets = {}
    dropped = set()
    total_rows = 0

    def _payload(start):
        p = dict(PAGING_BASE)
        p.update({
            "draw": "1",
            "fromDate": f"{from_date}T00:00:00.000Z",
            "toDate": f"{to_date}T23:59:59.000Z",
            "columns": PAGING_COLUMNS,
            "start": str(start), "length": str(PAGE_SIZE),
        })
        return p

    # Lấy N trang ĐẦU thì chỉ thấy được một góc: đo thật 18/08/2026, 500 dòng
    # đầu đều là hóa đơn nháp, khiến bảng chéo chỉ có đúng một dòng và tưởng như
    # cả 7787 hóa đơn cùng một trạng thái. Rải đều các mốc trên toàn khoảng mới
    # thấy đủ phổ trạng thái.
    offsets = [p * PAGE_SIZE for p in range(pages)]
    if int(spread or 0):
        _h, _r, reported, _n = _probe_once(path, _payload(0))
        reported = int(reported or 0)
        if reported > pages * PAGE_SIZE:
            step = max(1, (reported - PAGE_SIZE) // max(1, pages - 1)) if pages > 1 else 0
            offsets = [min(i * step, max(0, reported - PAGE_SIZE)) for i in range(pages)]
            print(f"MISA khai {reported} hóa đơn — lấy mẫu rải ở mốc: "
                  + ", ".join(str(o) for o in offsets) + "\n")

    for start in offsets:
        payload = _payload(start)
        try:
            rows, _meta = _paging_call(s, payload, dropped)
        except MISAError as e:
            print(f"  trang {page + 1}: [{e.code}] {e.message}")
            break
        if not rows:
            break
        total_rows += len(rows)

        for row in rows:
            v = _pick(row, prop)
            key = str(v)
            b = buckets.setdefault(key, {
                "n": 0, "co_ma": 0, "co_so": 0, "publish": {}, "sendtax": {},
                "mau": [], "mau_so": [],
            })
            b["n"] += 1

            code = str(_pick(row, "InvoiceCode") or "").strip()
            if len(code) >= 30:
                b["co_ma"] += 1
            no = str(_pick(row, "InvNo") or "").strip()
            if no and not no.startswith("<"):
                b["co_so"] += 1

            for f, k in (("PublishStatus", "publish"), ("SendToTaxStatus", "sendtax")):
                b[k][str(_pick(row, f))] = b[k].get(str(_pick(row, f)), 0) + 1
            # Ưu tiên mẫu ĐÃ CẤP SỐ: hóa đơn nháp thì tra trên MISA cũng không
            # ra được gì để đọc trạng thái.
            label = f"{_pick(row, 'InvSeries') or '?'} {no or '<chưa cấp số>'}"
            if no and not no.startswith("<"):
                if len(b["mau_so"]) < 3:
                    b["mau_so"].append(label)
            elif len(b["mau"]) < 3:
                b["mau"].append(label)

    if not total_rows:
        print("Không kéo được dòng nào — kiểm tra lại khoảng ngày và kết nối.")
        return {}

    print(f"Đã đọc {total_rows} hóa đơn.\n")
    print(f"{prop:>10} │ {'số HĐ':>6} │ {'có mã CQT':>10} │ {'đã cấp số':>10} │ Publish/SendTax")
    print("─" * 78)
    for k in sorted(buckets, key=lambda x: -buckets[x]["n"]):
        b = buckets[k]
        pub = ",".join(f"{a}×{c}" for a, c in sorted(b["publish"].items()))
        stx = ",".join(f"{a}×{c}" for a, c in sorted(b["sendtax"].items()))
        print(f"{k:>10} │ {b['n']:>6} │ {b['co_ma']:>10} │ {b['co_so']:>10} │ {pub} / {stx}")

    nhap = sum(v["n"] - v["co_so"] for v in buckets.values())
    print(f"\nTrong đó {nhap}/{total_rows} là hóa đơn NHÁP (chưa cấp số) — "
          "snapshot cố ý bỏ, không phải kéo thiếu.")

    print("\n" + "═" * 78)
    print("TRA TAY — mở MISA, tìm đúng những số dưới đây, đọc trạng thái màn hình:")
    for k in sorted(buckets, key=lambda x: -buckets[x]["n"]):
        mau = buckets[k]["mau_so"] or buckets[k]["mau"]
        print(f"  {prop}={k:<4} → " + "  ·  ".join(mau))
    print("═" * 78)
    if len(buckets) < 2:
        print("CHỈ RA MỘT GIÁ TRỊ — mẫu chưa đủ phổ. Tăng `pages`, hoặc bỏ `spread`")
        print("để lấy liên tục, hoặc thu hẹp khoảng ngày vào tháng có hóa đơn đã")
        print("phát hành. Đừng kết luận 'cả kho chỉ một trạng thái' từ đây.")
    else:
        print("Ghi kết quả vào misa_api_contract.md §R.5 rồi mới được code.")
        print("Suy luận sẵn có: nhóm nào 'có mã CQT' = 'số HĐ' thì chính là ĐÃ CẤP MÃ;")
        print("nhóm nào chưa cấp số thì nằm ở nửa 'chưa phát hành'.")
    return {k: {"n": v["n"], "co_ma": v["co_ma"], "co_so": v["co_so"],
                "mau": v["mau_so"] or v["mau"]} for k, v in buckets.items()}


# ═══════════════════════════════════════════════════════════════════════════
# Soi đúng vài hóa đơn ĐÃ BIẾT trạng thái — cách chốt enum chắc chắn nhất
# ═══════════════════════════════════════════════════════════════════════════

# Field quyết định hai trục trạng thái (§R.1). In hết, không lọc bớt.
STATUS_FIELDS = (
    "InvSeries", "InvNo", "InvDate", "InvoiceCode", "TransactionID", "RefID",
    "EInvoiceStatus", "PublishStatus", "SendToTaxStatus", "SendInvoiceStatus",
    "InvoiceType", "ReferenceType", "EditVersion",
)
LIFECYCLE_FIELDS = (
    "IsInvoiceDeleted", "DeletedDate", "DeletedReason",
    "OrgRefID", "OrgInvNo", "OrgInvSeries", "OrgInvDate", "OrgInvoiceType",
    "TypeChangeInvoice", "ChangeReason",
    "ErrorInvoiceStatus", "ErrorAnnouncementID", "MessageCode",
)


def inspect_invoices(numbers, from_date=None, to_date=None, max_pages=90):
    """Soi các hóa đơn CỤ THỂ mà người dùng đã đọc sẵn trạng thái trên MISA.

        bench --site <site> execute ketoan.api.misa_probe.inspect_invoices \
            --kwargs "{'numbers': '6689,6654,6679,5589,4486'}"

    Đây là cách chốt bảng enum chắc nhất: đã biết trạng thái THẬT của từng hóa
    đơn (đọc trên màn hình MISA), giờ chỉ cần xem API gắn con số nào cho đúng
    những hóa đơn đó. Không suy đoán, không phụ thuộc tham số lọc (thứ mà bề
    mặt API bỏ qua — §R.5).

    Tìm ref_id trong snapshot trước (tức thì); không có mới quét endpoint danh
    sách. Có ref_id rồi thì gọi `afterpublishing` để lấy nhóm field vòng đời.
    Chỉ ĐỌC, không ghi gì.
    """
    from ketoan.api.misa_client import invoice_path
    from ketoan.api.misa_sync import (
        PAGE_SIZE, PAGING_BASE, PAGING_COLUMNS, _paging_call,
    )
    from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
        norm_inv_no,
    )

    if isinstance(numbers, str):
        numbers = [x.strip() for x in numbers.replace(";", ",").split(",") if x.strip()]
    wanted = {norm_inv_no(n): str(n) for n in (numbers or [])}
    if not wanted:
        print("Chưa truyền số hóa đơn nào.")
        return {}

    s = get_settings()
    to_date = to_date or frappe.utils.nowdate()
    from_date = from_date or frappe.utils.add_days(to_date, -365)

    print("═" * 78)
    print("SOI HÓA ĐƠN ĐÃ BIẾT TRẠNG THÁI · " + ", ".join(wanted.values()))
    print("═" * 78)

    found = {}

    # ── Bước 1: snapshot sẵn có ────────────────────────────────────────────
    for norm, raw in wanted.items():
        rows = frappe.get_all(
            "MISA Invoice Snapshot", filters={"inv_no_norm": norm},
            fields=["name", "inv_series", "inv_no", "ref_id", "invoice_code",
                    "einvoice_status", "publish_status", "send_tax_status",
                    "send_invoice_status", "inv_date"],
            limit=5)
        if rows:
            found[norm] = {"src": "snapshot", "rows": rows}
            print(f"  {raw}: có sẵn trong snapshot ({len(rows)} bản ghi)")

    # ── Bước 2: quét endpoint danh sách cho phần còn thiếu ─────────────────
    missing = [n for n in wanted if n not in found]
    if missing:
        print(f"\n  Còn thiếu {len(missing)} số — quét endpoint danh sách…")
        dropped, start = set(), 0
        for page in range(int(max_pages)):
            payload = dict(PAGING_BASE)
            payload.update({
                "draw": str(page + 1),
                "fromDate": f"{from_date}T00:00:00.000Z",
                "toDate": f"{to_date}T23:59:59.000Z",
                "columns": PAGING_COLUMNS,
                "start": str(start), "length": str(PAGE_SIZE),
            })
            try:
                rows, _meta = _paging_call(s, payload, dropped)
            except MISAError as e:
                print(f"    trang {page + 1}: [{e.code}] {e.message}")
                break
            if not rows:
                break
            for row in rows:
                nn = norm_inv_no(_pick(row, "InvNo"))
                if nn in wanted and nn not in found:
                    found[nn] = {"src": "paging", "raw": row}
                    print(f"    tìm thấy {wanted[nn]} ở trang {page + 1}")
            start += len(rows)
            if all(n in found for n in wanted):
                break

    # ── Bước 3: afterpublishing cho nhóm field vòng đời ────────────────────
    print("\n" + "═" * 78)
    out = {}
    for norm, raw in wanted.items():
        print(f"\n── HÓA ĐƠN {raw} " + "─" * (60 - len(raw)))
        hit = found.get(norm)
        if not hit:
            print("   KHÔNG tìm thấy trong khoảng ngày đang quét.")
            continue

        rec = {}
        if hit["src"] == "paging":
            row = hit["raw"]
            for f in STATUS_FIELDS:
                rec[f] = _mask(f, _pick(row, f))
            ref_id = _pick(row, "RefID")
        else:
            r = hit["rows"][0]
            if len(hit["rows"]) > 1:
                print("   ⚠ nhiều ký hiệu cùng số này: "
                      + ", ".join(f"{x.inv_series} {x.inv_no}" for x in hit["rows"]))
            rec.update({
                "InvSeries": r.inv_series, "InvNo": r.inv_no, "InvDate": str(r.inv_date),
                "InvoiceCode": (r.invoice_code or "")[:12] + "…" if r.invoice_code else "",
                "EInvoiceStatus": r.einvoice_status, "PublishStatus": r.publish_status,
                "SendToTaxStatus": r.send_tax_status, "SendInvoiceStatus": r.send_invoice_status,
            })
            ref_id = r.ref_id

        for k, v in rec.items():
            print(f"   {k:<20} = {v}")

        if not ref_id:
            print("   (không có RefID → không gọi được afterpublishing)")
            out[raw] = rec
            continue

        try:
            data = call(invoice_path(f"v3sainvoice/afterpublishing/{ref_id}", s), method="GET")
        except MISAError as e:
            print(f"   afterpublishing: [{e.code}] {e.message}")
            out[raw] = rec
            continue
        inv = data[0] if isinstance(data, list) and data else data
        if not isinstance(inv, dict):
            print("   afterpublishing: không trả về object")
            out[raw] = rec
            continue

        print("   ── vòng đời (afterpublishing) ──")
        for f in LIFECYCLE_FIELDS:
            v = _pick(inv, f)
            if v not in (None, "", 0, False):
                print(f"   {f:<20} = {_mask(f, v)}")
                rec[f] = _mask(f, v)
        for f in ("EInvoiceStatus", "PublishStatus", "InvoiceType", "ReferenceType"):
            v = _pick(inv, f)
            if v is not None:
                print(f"   {f:<20} = {v}   (afterpublishing)")
                rec[f + "_ap"] = v
        out[raw] = rec

    print("\n" + "═" * 78)
    print("Đối chiếu bảng trên với trạng thái đã đọc trên màn hình MISA,")
    print("ghi vào misa_api_contract.md §R.5, RỒI mới được code.")
    return out


def check_schedule():
    """Kiểm khung giờ đồng bộ tự động — múi giờ, giờ hiện tại, các mốc sắp chạy.

        bench --site <site> execute ketoan.api.misa_probe.check_schedule

    Lý do cần: cron của Frappe tính theo múi giờ khai ở System Settings, KHÔNG
    phải giờ máy chủ. Khai lệch thì cả khung 7:30–17:30 chạy sai giờ mà không
    có gì báo — job vẫn "chạy đủ", chỉ là chạy lúc không ai xuất hóa đơn.
    """
    from ketoan.api.misa_sync import in_sync_window

    s = get_settings()
    tz = frappe.db.get_single_value("System Settings", "time_zone")
    now = frappe.utils.now_datetime()

    print("═" * 78)
    print("KHUNG GIỜ ĐỒNG BỘ TỰ ĐỘNG")
    print("═" * 78)
    print(f"  múi giờ (System Settings) : {tz or '(chưa khai)'}")
    print(f"  giờ site đang thấy        : {now:%Y-%m-%d %H:%M:%S} ({_weekday_vn(now)})")
    print()
    print(f"  bật đồng bộ tự động       : {bool(s.enable_auto_sync)}")
    print(f"  khung giờ khai            : {s.get('sync_from_time') or '(trống)'} → {s.get('sync_to_time') or '(trống)'}")
    print(f"  chỉ T2–T7                 : {bool(s.get('sync_workdays_only'))}")
    print()
    inside = in_sync_window(s, now)
    print(f"  ⇒ NGAY BÂY GIỜ            : {'ĐANG trong khung, job sẽ chạy' if inside else 'NGOÀI khung, job dừng ngay'}")
    if not s.enable_auto_sync:
        print("     (nhưng enable_auto_sync đang TẮT nên vẫn không chạy)")

    fires = [(7, 30)] + [(h, m) for h in range(8, 18) for m in (0, 30)]
    print(f"\n  cron trong hooks.py nổ {len(fires)} lần/ngày:")
    print("     " + ", ".join(f"{h:02d}:{m:02d}" for h, m in fires[:6]) + " … "
          + ", ".join(f"{h:02d}:{m:02d}" for h, m in fires[-2:]))

    lech = [f"{h:02d}:{m:02d}" for h, m in fires
            if not in_sync_window(s, now.replace(hour=h, minute=m))]
    if lech:
        print(f"\n  ⚠ {len(lech)} mốc cron nằm NGOÀI khung giờ khai trong Settings: "
              + ", ".join(lech))
        print("     Cron vẫn nổ nhưng job dừng ngay — sửa khung giờ trong MISA Settings")
        print("     hoặc sửa cron trong hooks.py cho khớp.")
    else:
        print("\n  ✅ Mọi mốc cron đều nằm trong khung giờ khai.")
    print("═" * 78)
    print("Nếu 'giờ site đang thấy' lệch giờ Việt Nam, sửa Time Zone trong")
    print("System Settings — cron và khung giờ đều tính theo đó.")
    return {"time_zone": tz, "now": str(now), "in_window": inside,
            "enabled": bool(s.enable_auto_sync)}


def _weekday_vn(d):
    return ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật")[d.weekday()]
