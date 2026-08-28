"""Kiểm chứng hồi quy tầng ĐỌC FILE của kênh MT trên file mẫu thật.

Vì sao nằm trong repo chứ không phải scratchpad: bộ kiểm này đã bị mất một lần
khi container khởi động lại, kéo theo mất luôn khả năng chứng minh parser còn
đúng. Nằm trong repo thì mọi phiên sau chạy lại được.

    python3 docs/mt/verified/regression_check.py

Chạy KHÔNG cần bench: `frappe` được stub vừa đủ để nạp `ketoan.api.mt_advice`.
Chỉ chứng minh tầng đọc file — không chạm database, không chạm khớp hóa đơn.
"""

import base64
import collections
import datetime
import os
import sys
import types

# .../docs/mt/verified/regression_check.py -> lùi 4 cấp mới tới gốc repo.
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SAMPLES = os.path.join(REPO, "docs", "mt", "samples")

# Số ĐÚNG đã xác minh trên file mẫu thật (xem §J của mt_payment_advice_contract.md).
#
# `reconciled` được kiểm như một số ĐÚNG chứ không chỉ in ra: một parser đọc
# thiếu tiền mà vẫn báo `reconciled=True` là ca hỏng nguy hiểm nhất của module —
# kế toán nhìn thấy chữ "đã đối chiếu khớp" rồi nạp thẳng vào sổ.
EXPECTED = {
    "Chi tiết thanh toán Winmart.xlsx": {
        "chain": "wincommerce", "thanh_toan": 245795904, "pay_lines": 36, "periods": 1,
        "reconciled": True},
    # CÙNG MỘT CHỨNG TỪ với dòng trên, ở dạng PDF gốc do WinCommerce gửi. Hai
    # định dạng phải ra CÙNG con số — mọi thay đổi ở parser từ nay bị soi trên
    # cả hai đường đọc, không chỉ đường Excel.
    "Chi tiết thanh toán Winmart.PDF": {
        "chain": "wincommerce", "thanh_toan": 245795904, "pay_lines": 36, "periods": 1,
        "reconciled": True},
    "Chi tiết thanh toán BigC.xlsx": {
        "chain": "central_retail", "thanh_toan": -721996632, "phi": 134708790,
        "chiet_khau": 27240347, "ghi_giam": 5119605, "pay_lines": 184, "periods": 1,
        "reconciled": True},
    "Chi tiết thanh toán Lotte.xls": {
        "chain": "lotte", "thanh_toan": 276933600, "pay_lines": 45, "periods": 2,
        "reconciled": True},
    "Chi tiết thanh toán Emart.xls": {
        "chain": "emart", "thanh_toan": -191554740, "chiet_khau": 5266245,
        "phi": 27388670, "pay_lines": 26, "periods": 1, "reconciled": True},
    "Chi tiết thanh toán Coopmart.xlsx": {
        "chain": "coop", "thanh_toan": 8451787806, "pay_lines": 443, "periods": 8,
        "reconciled": True},

    # ── MT-2 ────────────────────────────────────────────────────────────────
    # AEON: NET = 61.884.000 − 2.545.560 − 10.424.817 = 48.913.623, đúng bằng
    # 'NET PAYMENT' mà file in ở HAI nơi độc lập (khối tổng sheet Doc + sheet
    # Summary). `phi` KHÔNG được là −12.937.039: cộng thêm 2.512.222 nghĩa là
    # sheet DcCharges đã bị cộng trùng với dòng mã DC của Costdet.
    # Tên file có \xa0 (non-breaking space) THẬT — giữ nguyên, đừng "sửa" thành
    # dấu cách thường, file trên đĩa mang đúng ký tự đó.
    "chi tiet thanh to\xa0n AEON.xls": {
        "chain": "aeon", "thanh_toan": 61884000, "ghi_giam": -2545560,
        "phi": -10424817, "net": 48913623, "pay_lines": 21, "periods": 1,
        "rows": 53, "reconciled": True, "needs_review": 0},

    # Fuji: 90.010.980 − 8.191.071 − 10.126.136 = 71.693.773.
    # `thanh_toan` KHÔNG được là 180.021.960: nhân đôi nghĩa là khối 1 (theo
    # phiếu nhập kho) đã bị sinh dòng tiền cùng khối 2 (theo hóa đơn) — cùng một
    # số tiền nhìn từ hai phía.
    # `periods` = 0 vì file KHÔNG in ngày thanh toán ở bất kỳ đâu.
    "CHI TIẾT THANH TOÁN FUJI.Xls": {
        "chain": "fuji", "thanh_toan": 90010980, "ghi_giam": -8191071,
        "chiet_khau": -2618419, "phi": -7507717, "net": 71693773,
        "pay_lines": 10, "periods": 0, "rows": 23, "reconciled": True,
        "needs_review": 7},

    # Mega Market: bảng kê CẤN TRỪ HẾT — 313.983.000 hóa đơn bán ra trừ đúng
    # bằng 313.983.000 chứng từ ghi giảm, tiền thực nhận BẰNG 0.
    # `thanh_toan` KHÔNG được là 0: bằng 0 nghĩa là 8 dòng ký hiệu THG đã bị xếp
    # nhầm sang ghi giảm — tổng NET vẫn ra 0 nên KHÔNG số kiểm tra nào bắt được.
    # `reconciled` = False là ĐÚNG và sẽ mãi như vậy: file không in dòng tổng,
    # số bảng kê hay số tiền thanh toán nào để đối chiếu.
    "cttt_mega.xls": {
        "chain": "mega_market", "thanh_toan": 313983000, "ghi_giam": -313983000,
        "net": 0, "pay_lines": 8, "periods": 1, "rows": 18, "reconciled": False,
        "needs_review": 0},
}


def _stub_frappe():
    """Bộ giả frappe tối thiểu — đủ để import module đọc file, không hơn."""
    fr = types.ModuleType("frappe")

    class ValidationError(Exception):
        pass

    fr.ValidationError = ValidationError
    fr.PermissionError = type("PermissionError_", (Exception,), {})
    fr.DoesNotExistError = ValidationError
    fr.DuplicateEntryError = ValidationError

    def _throw(msg, exc=None):
        raise (exc or ValidationError)(str(msg))

    fr.throw = _throw
    fr._ = lambda s, *a, **k: s
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.log_error = lambda *a, **k: None
    fr.get_traceback = lambda *a, **k: ""
    fr.msgprint = lambda *a, **k: None
    fr.enqueue = lambda *a, **k: None
    fr.session = types.SimpleNamespace(user="regression@local")
    fr.local = types.SimpleNamespace()
    fr.get_all = lambda *a, **k: []
    fr.get_doc = lambda *a, **k: None
    fr.new_doc = lambda *a, **k: None
    fr.has_permission = lambda *a, **k: True
    fr.get_roles = lambda *a, **k: []
    fr.defaults = types.SimpleNamespace(get_user_default=lambda *a, **k: None)

    class _DB:
        def get_value(self, *a, **k):
            return None

        def exists(self, *a, **k):
            return None

        def sql(self, *a, **k):
            return []

        def get_single_value(self, *a, **k):
            return None

        def has_column(self, *a, **k):
            return False

        def table_exists(self, *a, **k):
            return True

    fr.db = _DB()

    # `frappe.get_meta(dt).has_field(f)` — production dùng nó ở `_has_si_field`
    # để hỏi "site có ô này chưa". Bộ giả trước đây KHÔNG có, nên mọi bộ kiểm
    # chạm vào đường đó nổ `AttributeError` giữa chừng.
    #
    # Ủy quyền THẲNG sang `db.has_column`: hai câu hỏi đó trả lời cùng một điều,
    # và ủy quyền thì bộ kiểm nào bật `has_column = True` là tự động có luôn
    # `has_field = True` — không phải nhớ bật hai chỗ rồi quên một.
    class _Meta:
        def __init__(self, dt):
            self.doctype = dt

        def has_field(self, field):
            return bool(fr.db.has_column(self.doctype, field))

        def get_field(self, field):
            return None

    fr.get_meta = _Meta
    fr.get_cached_doc = lambda *a, **k: None

    u = types.ModuleType("frappe.utils")
    u.flt = lambda v, p=None: float(v or 0)
    u.cint = lambda v: int(v or 0)
    u.cstr = lambda v: "" if v is None else str(v)

    def _gd(v):
        if isinstance(v, datetime.datetime):
            return v.date()
        if isinstance(v, datetime.date):
            return v
        return datetime.date.fromisoformat(str(v)[:10])

    u.getdate = _gd
    u.now_datetime = lambda: datetime.datetime.now()
    u.nowdate = lambda: str(datetime.date.today())
    u.today = u.nowdate
    u.add_days = lambda d, n: _gd(d) + datetime.timedelta(days=n)
    u.add_months = lambda d, n: _gd(d)
    u.get_datetime = lambda v=None: datetime.datetime.now()
    u.formatdate = lambda v, f=None: str(v)
    u.fmt_money = lambda v, *a, **k: str(v)
    fr.utils = u

    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = u
    m = types.ModuleType("frappe.model")
    sys.modules["frappe.model"] = m
    md = types.ModuleType("frappe.model.document")
    md.Document = type("Document", (), {})
    sys.modules["frappe.model.document"] = md
    sys.modules["frappe.permissions"] = types.ModuleType("frappe.permissions")
    return fr


def main():
    _stub_frappe()
    sys.path.insert(0, REPO)
    import importlib

    ma = importlib.import_module("ketoan.api.mt_advice")

    bad = 0
    print("=" * 78)
    print("KIỂM CHỨNG HỒI QUY — TẦNG ĐỌC FILE KÊNH MT")
    print("=" * 78)
    for fname, exp in EXPECTED.items():
        path = os.path.join(SAMPLES, fname)
        if not os.path.exists(path):
            print(f"  ⚠ THIẾU FILE MẪU: {fname}")
            bad += 1
            continue
        raw = open(path, "rb").read()
        try:
            res = ma.read_payment_advice(base64.b64encode(raw).decode(), exp["chain"])
        except Exception as e:  # noqa: BLE001 — báo mọi kiểu hỏng, không nuốt
            print(f"  ❌ {fname}: {type(e).__name__}: {str(e)[:80]}")
            bad += 1
            continue

        rows = res.get("rows") or []
        tot = collections.defaultdict(float)
        for r in rows:
            tot[r["row_kind"]] += float(r.get("signed_amount") or 0)
        pay_lines = sum(1 for r in rows if r["row_kind"] == "thanh_toan")
        periods = len({str(r.get("payment_date")) for r in rows if r.get("payment_date")})

        errs = []
        for key in ("thanh_toan", "chiet_khau", "phi", "ghi_giam"):
            if key in exp and round(tot.get(key, 0)) != exp[key]:
                errs.append(f"{key}: mong {exp[key]:,} thực {round(tot.get(key, 0)):,}")
        if "net" in exp and round(sum(tot.values())) != exp["net"]:
            errs.append(f"NET: mong {exp['net']:,} thực {round(sum(tot.values())):,}")
        if pay_lines != exp["pay_lines"]:
            errs.append(f"dòng TT: mong {exp['pay_lines']} thực {pay_lines}")
        if "rows" in exp and len(rows) != exp["rows"]:
            errs.append(f"tổng dòng: mong {exp['rows']} thực {len(rows)}")
        if periods != exp["periods"]:
            errs.append(f"số kỳ: mong {exp['periods']} thực {periods}")
        if "reconciled" in exp and bool(res.get("reconciled")) != exp["reconciled"]:
            errs.append(f"reconciled: mong {exp['reconciled']} thực {res.get('reconciled')}")
        if "needs_review" in exp:
            nr = sum(1 for r in rows if r.get("needs_review"))
            if nr != exp["needs_review"]:
                errs.append(f"dòng cần review: mong {exp['needs_review']} thực {nr}")
        # Số kiểm tra nào KHÔNG khớp thì phải kéo `reconciled` xuống False; nếu
        # có check hỏng mà vẫn reconciled=True thì chính lá chắn đã hỏng.
        n_bad_checks = sum(1 for c in (res.get("checks") or []) if not c.get("ok"))
        if n_bad_checks and res.get("reconciled"):
            errs.append(f"{n_bad_checks} số kiểm tra lệch mà vẫn reconciled=True")

        n_ok = sum(1 for c in (res.get("checks") or []) if c.get("ok"))
        mark = "✅" if not errs else "❌"
        print(f"  {mark} {exp['chain']:16} dòng={len(rows):5} tt={pay_lines:4} "
              f"kỳ={periods} check={n_ok}/{len(res.get('checks') or [])} "
              f"reconciled={res.get('reconciled')}")
        for e in errs:
            print(f"       └─ {e}")
        bad += bool(errs)

    bad += _check_chain_options()

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — mọi chuỗi ra đúng từng đồng" if not bad else f"HỎNG {bad} mục")
    return 1 if bad else 0


def _check_chain_options():
    """Danh sách chuỗi siêu thị phải KHỚP ở cả ba nơi. Trả 1 nếu lệch.

    Lệch thì bảng kê của chuỗi mới nạp xong sẽ bị Frappe từ chối ở tầng validate,
    hoặc ghi được nhưng màn hình lọc theo chuỗi không thấy — tiền vào sổ mà không
    ai nhìn ra. Rẻ để kiểm, đắt để phát hiện muộn.
    """
    print("-" * 78)
    try:
        from ketoan.install import MT_CHAINS, check_chain_options
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ không import được ketoan.install: {type(e).__name__}: {e}")
        return 1
    problems = check_chain_options()
    if problems:
        print("  ❌ danh sách chuỗi LỆCH giữa ba nơi:")
        for pb in problems:
            print(f"       └─ {pb}")
        return 1
    print(f"  ✅ danh sách chuỗi khớp ở cả 3 nơi ({len(MT_CHAINS)} chuỗi): "
          f"{', '.join(MT_CHAINS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
