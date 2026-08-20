"""Kiểm tầng LẬP BẢNG KÊ CHIẾT KHẤU (`ketoan/api/mt_discount.py`) trên file thật.

    python3 docs/mt/verified/discount_sheet_check.py

Bảng kê chiết khấu là CHỨNG TỪ HAI BÊN KÝ và nó dẫn tới một hóa đơn GTGT. Sai ở
đây phải sửa bằng hóa đơn điều chỉnh, để lại vết với cơ quan thuế. Phép kiểm
nhắm đúng những chỗ đó:

  1. SỐ TIỀN CHIẾT KHẤU. Hai cách tính (`cộng dòng` vs `tỷ lệ × tổng`) phải cho
     đúng con số của cách đã chốt, và chúng lệch nhau thật.
  2. GỘP DÒNG THEO HÓA ĐƠN. File chi tiết theo sản phẩm (LOTTE 192 dòng cho 26
     hóa đơn); bảng kê in MỘT dòng / hóa đơn. Gộp sai là in trùng hóa đơn.
  3. KHÔNG LẬP BẢNG KÊ KHI CHƯA RÕ BÊN MUA. Ký nhầm pháp nhân = hóa đơn sai
     người mua.
  4. KHÔNG ĐOÁN TỶ LỆ. Thiếu điều khoản -> DỪNG.
  5. TỔNG CỦA BẢNG KÊ = TỔNG CƠ SỞ. Gộp dòng không được làm mất tiền.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

COMPANY = "HGC"

# Điều khoản chiết khấu giả lập — đúng như đo trên mẫu BKCK thật.
TERMS = {
    "Central Retail": {"mode": "Cộng chiết khấu từng dòng", "rate": 3.35, "vat_rate": 8},
    "LOTTE": {"mode": "Tỷ lệ × tổng doanh số", "rate": 10.0, "vat_rate": 8},
    "Mega Market": {"mode": "Tỷ lệ × tổng doanh số", "rate": 2.0, "vat_rate": 8},
}

CASES = [
    # file, chuỗi, số bảng kê, tổng cơ sở, chiết khấu trước thuế, số hóa đơn
    ("Chi tiết doanh số BigC.xlsx", "Central Retail", 1, 755943625, 25324144, 177),
    ("7466- chi tiết doanh số Lotte.xlsx", "LOTTE", 14, 393014000, 39301400, 26),
    ("Chi tiết doanh số Mega Market.xlsx", "Mega Market", 1, 95390000, 1907800, 6),
]


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


def _install(stores=True, terms=True, si_rows=None):
    """Cắm frappe cho tầng lập bảng kê.

    `stores=True` -> mọi mã nhóm đều tra ra một điểm siêu thị có pháp nhân.
    `terms=False` -> chưa khai điều khoản, để đo nhánh phải DỪNG.
    """
    import frappe

    def _sql(query, values=None, **kw):
        q = " ".join(str(query).split())
        if "tabSales Invoice" in q:
            return list(si_rows or [])
        raise AssertionError("Truy vấn không giả lập: " + q[:120])

    def _get_value(dt, name, field=None, **kw):
        if dt == "MT Store" and isinstance(name, dict):
            if not stores:
                return None
            key = name.get("store_code") or name.get("vendor_code")
            return _D(name="MT-STORE-%s" % key, customer="KH-%s" % key,
                      address="ADDR-%s" % key, tax_id="0304741634-%s" % key,
                      store_name="Điểm %s" % key)
        if dt == "Customer":
            return _D(customer_name="Pháp nhân %s" % name, tax_id="0800280839")
        if dt == "Address":
            return _D(address_line1="Số 1 Đường A", address_line2=None, city="Hà Nội",
                      state=None, country="Việt Nam", gstin=None)
        if dt == "MT Discount Sheet" and isinstance(name, dict):
            return None            # chưa có bảng kê nào cho kỳ này
        return None

    def _get_all(dt, filters=None, **kw):
        if dt == "MT Discount Term":
            if not terms:
                return []
            t = TERMS.get((filters or {}).get("chain"))
            if not t:
                return []
            return [_D(name="MT-CKTERM-%s" % filters["chain"], customer=None,
                       mode=t["mode"], rate=t["rate"], vat_rate=t["vat_rate"])]
        return []

    frappe.db.sql = _sql
    frappe.db.get_value = _get_value
    frappe.db.has_column = lambda dt, col: False   # site chưa có cột MISA -> bỏ đối chiếu
    frappe.get_all = _get_all


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    _install()
    mdr = importlib.import_module("ketoan.api.mt_discount_read")
    md = importlib.import_module("ketoan.api.mt_discount")

    print("=" * 78)
    print("KIỂM TẦNG LẬP BẢNG KÊ CHIẾT KHẤU")
    print("=" * 78)
    bad = 0

    for fname, chain, n_sheets, base, disc_base, n_inv in CASES:
        path = os.path.join(rc.SAMPLES, fname)
        content = base64.b64encode(open(path, "rb").read()).decode()
        parsed = mdr.read_discount_basis(content)
        plan, blocked, warnings = md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", fname)

        errs = []
        if len(plan) != n_sheets:
            errs.append(f"số bảng kê: mong {n_sheets} thực {len(plan)}")
        if blocked:
            errs.append(f"{len(blocked)} nhóm bị chặn dù đã có điểm siêu thị")

        got_base = round(sum(p["total_base"] for p in plan))
        if got_base != base:
            errs.append(f"tổng cơ sở: mong {base:,} thực {got_base:,}")

        # 5. Gộp dòng KHÔNG được làm mất tiền.
        basis = round(parsed["totals"]["base_amount"])
        if got_base != basis:
            errs.append(f"gộp dòng làm mất tiền: cơ sở {basis:,} -> bảng kê {got_base:,}")

        got_disc = round(sum(p["discount_base"] for p in plan))
        if got_disc != disc_base:
            errs.append(f"chiết khấu: mong {disc_base:,} thực {got_disc:,}")

        got_inv = sum(p["n_lines"] for p in plan)
        if got_inv != n_inv:
            errs.append(f"số dòng bảng kê (= số hóa đơn): mong {n_inv} thực {got_inv}")

        # Mọi bảng kê phải có bên mua + MST, và tổng dòng phải khớp tổng bảng kê.
        for p in plan:
            if not p["customer"]:
                errs.append(f"nhóm {p['group_key']}: không có bên mua")
            if not p["buyer_tax_id"]:
                errs.append(f"nhóm {p['group_key']}: không có MST bên mua")
            s = round(sum(l["amount_before_vat"] for l in p["lines"]), 2)
            if abs(s - p["total_base"]) > 0.5:
                errs.append(f"nhóm {p['group_key']}: tổng dòng {s:,.0f} ≠ tổng bảng kê "
                            f"{p['total_base']:,.0f}")
            # Thuế của chiết khấu tính TRÊN SỐ CHIẾT KHẤU (mẫu thật: 23.952.537
            # × 8% = 1.916.202,96), không phải cộng thuế của các dòng.
            want_vat = round(p["discount_base"] * p["vat_rate"] / 100.0, 2)
            if abs(want_vat - p["discount_vat"]) > 0.01:
                errs.append(f"nhóm {p['group_key']}: thuế CK {p['discount_vat']:,.2f} ≠ "
                            f"{p['vat_rate']}% của {p['discount_base']:,.0f}")

        mark = "✅" if not errs else "❌"
        how = ""
        if plan:
            how = plan[0]["mode"][:12]
            if plan[0]["rate"]:
                how += " %s%%" % plan[0]["rate"]
        print(f"  {mark} {chain:16} {len(plan):3} bảng kê · {got_inv:3} dòng · "
              f"cơ sở {got_base:>15,} · CK {got_disc:>13,}  ({how})")
        for e in errs:
            print(f"       └─ {e}")
        bad += bool(errs)

    # ── Central Retail: cộng dòng KHÁC tỷ lệ × tổng ───────────────────────
    print("-" * 78)
    content = base64.b64encode(
        open(os.path.join(rc.SAMPLES, "Chi tiết doanh số BigC.xlsx"), "rb").read()).decode()
    parsed = mdr.read_discount_basis(content)
    plan, _b, _w = md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", "x.xlsx")
    p = plan[0]
    rate_total = p["total_base"] * p["rate"] / 100.0
    ok = abs(p["discount_base"] - rate_total) > 1.0
    print(f"  {'✅' if ok else '❌'} Central Retail dùng CỘNG DÒNG {p['discount_base']:,.0f}, "
          f"không phải tỷ lệ×tổng {rate_total:,.2f} (lệch {p['discount_base']-rate_total:,.2f}đ)")
    bad += not ok

    # ── LOTTE: gộp 192 dòng sản phẩm thành 26 dòng hóa đơn, không trùng ───
    content = base64.b64encode(
        open(os.path.join(rc.SAMPLES, "7466- chi tiết doanh số Lotte.xlsx"), "rb").read()).decode()
    parsed = mdr.read_discount_basis(content)
    plan, _b, _w = md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", "x.xlsx")
    dupes = 0
    for p in plan:
        keys = [(l["inv_series"] or "", l["inv_no_norm"]) for l in p["lines"]]
        dupes += len(keys) - len(set(keys))
    ok = dupes == 0 and sum(p["n_lines"] for p in plan) == 26
    print(f"  {'✅' if ok else '❌'} LOTTE gộp 192 dòng sản phẩm → 26 dòng hóa đơn, "
          f"không dòng nào trùng số hóa đơn trong cùng bảng kê")
    bad += not ok

    # ── CHƯA rõ bên mua -> KHÔNG lập bảng kê ──────────────────────────────
    print("-" * 78)
    _install(stores=False)
    parsed = mdr.read_discount_basis(content)
    plan, blocked, warnings = md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", "x.xlsx")
    ok = (not plan and len(blocked) == 14
          and any("chứng từ hai bên ký" in w for w in warnings))
    print(f"  {'✅' if ok else '❌'} chưa gán điểm siêu thị -> KHÔNG lập bảng kê nào "
          f"({len(blocked)} nhóm bị chặn kèm lý do)")
    if not ok:
        print(f"       └─ plan={len(plan)} blocked={len(blocked)}")
    bad += not ok

    # ── CHƯA khai điều khoản -> DỪNG, không đoán tỷ lệ ────────────────────
    _install(terms=False)
    try:
        md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", "x.xlsx")
        print("  ❌ chưa khai điều khoản -> KHÔNG dừng, đang đoán tỷ lệ")
        bad += 1
    except Exception as e:  # noqa: BLE001
        ok = "MT Discount Term" in str(e)
        print(f"  {'✅' if ok else '❌'} chưa khai điều khoản -> dừng: {str(e)[:56]}")
        bad += not ok

    _install()

    # ── Vân tay kế hoạch ỔN ĐỊNH ─────────────────────────────────────────
    p1, _b, _w = md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", "x.xlsx")
    p2, _b, _w = md._build_plan(parsed, COMPANY, "07.2026", "2026-08-14", "x.xlsx")
    ok = md._plan_hash(p1) == md._plan_hash(p2)
    print(f"  {'✅' if ok else '❌'} vân tay kế hoạch ỔN ĐỊNH giữa hai lần dựng")
    bad += not ok
    # Đổi kỳ -> vân tay PHẢI đổi (nếu không, commit sau khi sửa kỳ sẽ lọt).
    p3, _b, _w = md._build_plan(parsed, COMPANY, "08.2026", "2026-08-14", "x.xlsx")
    ok = md._plan_hash(p1) != md._plan_hash(p3)
    print(f"  {'✅' if ok else '❌'} đổi kỳ -> vân tay ĐỔI theo")
    bad += not ok

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — bảng kê đúng số tiền, đúng bên mua, không đoán tỷ lệ"
          if not bad else f"HỎNG {bad} mục")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
