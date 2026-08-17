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

from ketoan.api.misa_client import MISAError, call, get_settings

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
