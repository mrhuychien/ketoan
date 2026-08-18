"""misa_client — TẦNG HTTP duy nhất nói chuyện với MISA meInvoice.

Chỉ làm: lấy token, gắn header, retry, bóc wrapper. KHÔNG business logic, KHÔNG
đụng DocType nào ngoài `MISA Settings`.

Hợp đồng đã xác minh (docs/misa/misa_api_contract.md §L.2):

    POST {base}/api/v2/oauth
        header TaxCode: <MST>
        body   form-urlencoded: grant_type=password & username= & password=
        → response.access_token

    Mọi lời gọi sau đó: Authorization: Bearer <token> + TaxCode: <MST>

BẢO MẬT — bất di bất dịch:
  · credential chỉ đọc từ fieldtype Password của `MISA Settings`;
  · KHÔNG log body request token, KHÔNG log giá trị token, KHÔNG log header;
  · `MISAError` chỉ mang mã lỗi + thông điệp đã lọc.
"""

import json
import time

import frappe
from frappe import _

TIMEOUT = 60                 # giây, mọi request
RETRY_BACKOFF = (2, 4, 8)    # chỉ cho lỗi mạng và 5xx
PAGE_SLEEP = 0.2             # giãn cách khi loop phân trang
TOKEN_TTL = 1800             # cache token 30': chưa quan sát được expires_in nên để ngắn
_TOKEN_KEY = "misa_token"


class MISAError(Exception):
    """Lỗi nghiệp vụ/giao tiếp MISA. KHÔNG bao giờ chứa credential."""

    def __init__(self, code, message, raw=None):
        self.code = str(code or "")
        self.message = str(message or "")
        self.raw = raw
        super().__init__(f"[{self.code}] {self.message}" if self.code else self.message)


# ═══════════════════════════════════════════════════════════════════════════
# Cấu hình
# ═══════════════════════════════════════════════════════════════════════════

def get_settings():
    return frappe.get_single("MISA Settings")


def _base_url(settings=None) -> str:
    s = settings or get_settings()
    return (s.base_url_webapp or "https://app.meinvoice.vn").rstrip("/")


def _taxcode(settings=None) -> str:
    s = settings or get_settings()
    code = (s.taxcode or "").strip()
    if not code:
        frappe.throw(_("Chưa khai Mã số thuế trong MISA Settings"))
    return code


def _credentials(settings=None):
    """(username, password). Đọc từ fieldtype Password — Frappe giải mã tại chỗ."""
    s = settings or get_settings()
    user = (s.username or "").strip()
    pwd = s.get_password("password", raise_exception=False) or ""
    if not (user and pwd):
        frappe.throw(_("Chưa khai tài khoản MISA trong MISA Settings"))
    return user, pwd


def invoice_path(tail: str, settings=None) -> str:
    """Ghép route hóa đơn, tự thêm tiền tố `code/` khi công ty dùng hóa đơn CÓ MÃ.

    tail: phần sau, ví dụ "v3sainvoice/afterpublishing/abc" hoặc "v3sainvoice".
    """
    s = settings or get_settings()
    tail = tail.lstrip("/")
    return f"code/{tail}" if s.use_code_route else tail


# ═══════════════════════════════════════════════════════════════════════════
# Token
# ═══════════════════════════════════════════════════════════════════════════

def get_token(force_refresh: bool = False) -> str:
    """Trả về chuỗi 'Bearer <token>'. Cache trong frappe.cache().

    force_refresh: dùng khi gặp 401 — đăng nhập lại đúng MỘT lần.
    """
    cache = frappe.cache()
    if not force_refresh:
        cached = cache.get_value(_TOKEN_KEY)
        if cached:
            return cached

    settings = get_settings()
    user, pwd = _credentials(settings)
    url = f"{_base_url(settings)}/api/v2/oauth"

    try:
        import requests

        res = requests.post(
            url,
            headers={"TaxCode": _taxcode(settings)},
            data={"grant_type": "password", "username": user, "password": pwd},
            timeout=TIMEOUT,
        )
    except Exception as e:
        # Tuyệt đối không đưa `data` vào thông điệp lỗi.
        raise MISAError("network", f"Không gọi được {url}: {type(e).__name__}")

    if res.status_code != 200:
        raise MISAError(f"http_{res.status_code}", f"Đăng nhập MISA thất bại ({res.status_code})")

    try:
        body = res.json()
    except Exception:
        raise MISAError("bad_json", "Phản hồi đăng nhập không phải JSON")

    token = _pick(body, "access_token")
    if not token:
        raise MISAError("no_token", "Phản hồi đăng nhập không có access_token")

    value = f"Bearer {token}"
    # expires_in chưa xác minh: nếu MISA có trả thì tôn trọng, trừ hao 300s.
    expires = _pick(body, "expires_in")
    try:
        ttl = max(60, int(expires) - 300) if expires else TOKEN_TTL
    except (TypeError, ValueError):
        ttl = TOKEN_TTL
    cache.set_value(_TOKEN_KEY, value, expires_in_sec=min(ttl, TOKEN_TTL))
    return value


def clear_token():
    frappe.cache().delete_value(_TOKEN_KEY)


# ═══════════════════════════════════════════════════════════════════════════
# Gọi API
# ═══════════════════════════════════════════════════════════════════════════

def call(path: str, payload=None, params=None, method: str = "POST", form: bool = False, with_meta: bool = False):
    """Gọi 1 endpoint MISA, trả về phần Data đã bóc wrapper.

    path   : phần sau /api/v2/, ví dụ "v3sainvoice/code".
    payload: dict/list — gửi JSON, hoặc dict — gửi form khi form=True.
    form   : True → Content-Type form-urlencoded (một số endpoint yêu cầu).

    Retry 2s/4s/8s cho lỗi mạng và 5xx. KHÔNG retry 4xx, trừ 401 → lấy lại
    token đúng một lần rồi thử lại.
    """
    import requests

    url = f"{_base_url()}/api/v2/{path.lstrip('/')}"
    taxcode = _taxcode()
    retried_auth = False
    last_err = None

    for attempt in range(len(RETRY_BACKOFF) + 1):
        headers = {"Authorization": get_token(force_refresh=retried_auth), "TaxCode": taxcode}
        kwargs = {"headers": headers, "params": params, "timeout": TIMEOUT}
        if payload is not None:
            if form:
                kwargs["data"] = payload
            else:
                headers["Content-Type"] = "application/json"
                kwargs["data"] = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            res = requests.request(method.upper(), url, **kwargs)
        except Exception as e:
            last_err = MISAError("network", f"{type(e).__name__} khi gọi {path}")
            if attempt < len(RETRY_BACKOFF):
                time.sleep(RETRY_BACKOFF[attempt])
                continue
            raise last_err

        if res.status_code == 401 and not retried_auth:
            # Token hết hạn → đăng nhập lại đúng MỘT lần, không tính là retry.
            clear_token()
            retried_auth = True
            continue

        if 500 <= res.status_code < 600:
            last_err = MISAError(f"http_{res.status_code}", f"MISA lỗi máy chủ khi gọi {path}")
            if attempt < len(RETRY_BACKOFF):
                time.sleep(RETRY_BACKOFF[attempt])
                continue
            raise last_err

        if res.status_code != 200:
            raise MISAError(f"http_{res.status_code}", f"MISA từ chối {path} ({res.status_code})")

        return _unwrap(res, path, with_meta=with_meta)

    raise last_err or MISAError("unknown", f"Không gọi được {path}")


# ═══════════════════════════════════════════════════════════════════════════
# Bóc wrapper
# ═══════════════════════════════════════════════════════════════════════════

def _pick(d, *names):
    """Lấy key KHÔNG phân biệt hoa thường.

    Bộ API chính thức tài liệu ghi {Success, Data, ErrorCode}; bộ web app trả
    {success, data, errorCode} (§H.1). Không hardcode một kiểu.
    """
    if not isinstance(d, dict):
        return None
    lowered = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = lowered.get(str(n).lower())
        if v is not None:
            return v
    return None


def _unwrap(res, path: str, with_meta: bool = False):
    """Kiểm cờ success rồi trả về Data đã parse. Trả nguyên body nếu không có wrapper.

    with_meta=True → trả (data, wrapper) để đọc recordsTotal/recordsFiltered.
    """
    try:
        body = res.json()
    except Exception:
        raise MISAError("bad_json", f"Phản hồi {path} không phải JSON")

    if not isinstance(body, dict):
        return body  # một số endpoint trả thẳng mảng

    ok = _pick(body, "success")
    if ok is False:
        code = _pick(body, "errorCode", "ErrorCode")
        if isinstance(code, list):
            code = ",".join(str(c) for c in code) or "error"
        msg = _pick(body, "error", "Errors", "dataError", "message") or f"MISA từ chối {path}"
        raise MISAError(code or "error", _text(msg), raw=body)

    if "data" in {str(k).lower() for k in body}:
        data = parse_nested_data(_pick(body, "data"))
        return (data, body) if with_meta else data
    return (body, body) if with_meta else body


def parse_nested_data(data):
    """`data` của MISA là CHUỖI JSON lồng (§H.1) — parse phòng thủ.

    Tài liệu MISA có ví dụ trả nhiều bản ghi mà thiếu [] bao ngoài. Không parse
    được thì log_error và trả rỗng, KHÔNG raise — hỏng 1 mẻ không được làm chết job.
    """
    if data is None or data == "":
        return []
    if isinstance(data, (list, dict)):
        return data

    text = str(data).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Thiếu ngoặc vuông bao ngoài: "{...},{...}"
    try:
        return json.loads(f"[{text}]")
    except Exception:
        frappe.log_error(
            f"Không parse được data của MISA (dài {len(text)} ký tự), 300 ký tự đầu:\n{text[:300]}",
            "misa_client.parse_nested_data",
        )
        return []


def _text(v) -> str:
    if isinstance(v, (list, tuple)):
        return "; ".join(_text(x) for x in v if x)
    if isinstance(v, dict):
        return _text(_pick(v, "message", "Message") or json.dumps(v, ensure_ascii=False))
    return str(v or "")


# ═══════════════════════════════════════════════════════════════════════════
# Kiểm tra kết nối — phục vụ nút "Thử kết nối" trên MISA Settings
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def test_connection():
    """Lấy token thật để xác nhận cấu hình đúng. KHÔNG trả token về client."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    clear_token()
    try:
        get_token(force_refresh=True)
    except MISAError as e:
        return {"ok": False, "code": e.code, "message": e.message}
    s = get_settings()
    return {
        "ok": True,
        "message": _("Đăng nhập MISA thành công"),
        "base_url": _base_url(s),
        "taxcode": _taxcode(s),
        "use_code_route": bool(s.use_code_route),
        "has_appid": s.has_appid(),
    }
