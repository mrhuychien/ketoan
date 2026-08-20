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

# Số ĐÚNG đã xác minh ở MT-1 (xem §J của mt_payment_advice_contract.md).
EXPECTED = {
    "Chi tiết thanh toán Winmart.xlsx": {
        "chain": "wincommerce", "thanh_toan": 245795904, "pay_lines": 36, "periods": 1},
    "Chi tiết thanh toán BigC.xlsx": {
        "chain": "central_retail", "thanh_toan": -721996632, "phi": 134708790,
        "chiet_khau": 27240347, "ghi_giam": 5119605, "pay_lines": 184, "periods": 1},
    "Chi tiết thanh toán Lotte.xls": {
        "chain": "lotte", "thanh_toan": 276933600, "pay_lines": 45, "periods": 2},
    "Chi tiết thanh toán Emart.xls": {
        "chain": "emart", "thanh_toan": -191554740, "chiet_khau": 5266245,
        "phi": 27388670, "pay_lines": 26, "periods": 1},
    "Chi tiết thanh toán Coopmart.xlsx": {
        "chain": "coop", "thanh_toan": 8451787806, "pay_lines": 443, "periods": 8},
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
        if pay_lines != exp["pay_lines"]:
            errs.append(f"dòng TT: mong {exp['pay_lines']} thực {pay_lines}")
        if periods != exp["periods"]:
            errs.append(f"số kỳ: mong {exp['periods']} thực {periods}")

        mark = "✅" if not errs else "❌"
        print(f"  {mark} {exp['chain']:16} dòng={len(rows):5} tt={pay_lines:4} "
              f"kỳ={periods} reconciled={res.get('reconciled')}")
        for e in errs:
            print(f"       └─ {e}")
        bad += bool(errs)

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — mọi chuỗi ra đúng từng đồng" if not bad else f"HỎNG {bad} chuỗi")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
