"""Kiểm tầng ĐỌC CƠ SỞ TÍNH CHIẾT KHẤU (`ketoan/api/mt_discount_read.py`).

    python3 docs/mt/verified/discount_basis_check.py

Ba file doanh số thật, ba hình dạng khác hẳn nhau. Phép kiểm nhắm đúng những
chỗ đọc sai thì XUẤT HÓA ĐƠN SAI — mà hóa đơn đã xuất thì phải làm hóa đơn điều
chỉnh, để lại vết với cơ quan thuế:

  1. LẤY NHẦM NHÓM. Central Retail có 4 nhóm trong một file, chỉ 1 nhóm là của
     mình. Ba nhóm kia do EB xuất hóa đơn, và đã được ghi nhận ở MT2-D dưới dạng
     dòng `D1`. Lấy cả bốn = xuất hóa đơn cho khoản mình không được xuất + ghi
     nhận hai lần.
  2. NHÂN DOANH SỐ. `IM_VALUE` của Central Retail lặp lại ở mọi nhóm; cộng toàn
     file là nhân doanh số lên 6 lần.
  3. TÍNH CHIẾT KHẤU SAI CÁCH. BigC làm tròn từng dòng (tỷ lệ × tổng lệch ~30đ),
     LOTTE thì tỷ lệ × tổng khớp tuyệt đối. Hai cách, không thay nhau được.
  4. TÍNH CẢ HÀNG CHƯA NHẬN. LOTTE đánh dấu `NOT RECEIVE` — 35 dòng,
     25.621.900đ. Tính vào là xuất hóa đơn chiết khấu cho hàng chưa giao.
  5. ĐIỀN TÊN MÌNH VÀO Ô BÊN MUA. Cột `SUPPLIERNAME` / `Supplier Name` của cả
     Central Retail lẫn Mega là TÊN CỦA MÌNH, không phải bên mua.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import base64
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

# Số ĐÚNG đo trên file mẫu thật (xem docs/mt/BUOC0_MT2B_findings.md).
EXPECTED = {
    "Chi tiết doanh số BigC.xlsx": {
        "chain": "central_retail", "mode": "per_line", "rate": 3.35,
        "n_rows": 177, "n_groups": 1, "n_invoices": 177,
        "base": 755943625, "discount": 25324144,
        "vendor_code": "3003172", "reconciled": True,
        # Ba nhóm của EB — KHÔNG sinh dòng, nhưng phải báo kèm tiền.
        "excluded": {"Fee for EBS": (177, 7559436),
                     "Fee for store": (531, 62365380),
                     "Support for store": (885, 29859815)},
    },
    "7466- chi tiết doanh số Lotte.xlsx": {
        "chain": "lotte", "mode": "rate_on_total", "rate": None,
        "n_rows": 192, "n_groups": 14, "n_invoices": 26,
        "base": 393014000, "discount": None,
        "vendor_code": "7466", "reconciled": True,
        "excluded": {"Hàng CHƯA NHẬN (Fill in date = NOT RECEIVE)": (35, 25621900)},
    },
    "Chi tiết doanh số Mega Market.xlsx": {
        "chain": "mega_market", "mode": "rate_on_total", "rate": None,
        "n_rows": 6, "n_groups": 1, "n_invoices": 6,
        "base": 95390000, "discount": None,
        "vendor_code": "27063",
        # File Mega KHÔNG có số kiểm tra nào -> 'không kiểm được', khác hẳn
        # 'đã kiểm và khớp'. False ở đây là câu trả lời ĐÚNG.
        "reconciled": False,
        "excluded": {},
    },
}

# Tổng doanh số CẢ BỐN NHÓM của Central Retail. Nếu tầng đọc quên lọc nhóm thì
# `base_amount` sẽ nhảy lên con số này — chốt riêng để bắt đúng lỗi đó.
CR_ALL_GROUPS_BASE = 755943625 + 755943625 + 2267830875 + 3779718125


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    md = importlib.import_module("ketoan.api.mt_discount_read")

    print("=" * 78)
    print("KIỂM TẦNG ĐỌC CƠ SỞ TÍNH CHIẾT KHẤU")
    print("=" * 78)
    bad = 0

    for fname, exp in EXPECTED.items():
        path = os.path.join(rc.SAMPLES, fname)
        if not os.path.exists(path):
            print(f"  ⚠ THIẾU FILE MẪU: {fname}")
            bad += 1
            continue
        content = base64.b64encode(open(path, "rb").read()).decode()

        # TỰ NHẬN DIỆN — không truyền chuỗi. Nhận nhầm chuỗi là đọc nhầm cột
        # tiền mà vẫn ra một con số trông hợp lý.
        try:
            res = md.read_discount_basis(content)
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {fname}: {type(e).__name__}: {str(e)[:90]}")
            bad += 1
            continue

        t = res["totals"]
        errs = []
        if res["chain_key"] != exp["chain"]:
            errs.append(f"tự nhận diện ra '{res['chain_key']}' thay vì '{exp['chain']}'")
        if res["mode"] != exp["mode"]:
            errs.append(f"mode: mong {exp['mode']} thực {res['mode']}")
        if res["rate"] != exp["rate"]:
            errs.append(f"rate: mong {exp['rate']} thực {res['rate']}")
        if t["n_rows"] != exp["n_rows"]:
            errs.append(f"số dòng: mong {exp['n_rows']} thực {t['n_rows']}")
        if t["n_groups"] != exp["n_groups"]:
            errs.append(f"số nhóm: mong {exp['n_groups']} thực {t['n_groups']}")
        if round(t["base_amount"]) != exp["base"]:
            errs.append(f"cơ sở: mong {exp['base']:,} thực {round(t['base_amount']):,}")
        if exp["discount"] is None:
            if t["discount_amount"] is not None:
                errs.append("file KHÔNG in chiết khấu mà tầng đọc lại trả ra số — "
                            "đó là tự tính hộ, sai nguyên tắc")
        elif round(t["discount_amount"] or 0) != exp["discount"]:
            errs.append(f"chiết khấu: mong {exp['discount']:,} thực {round(t['discount_amount'] or 0):,}")
        if str(res.get("vendor_code") or "") != exp["vendor_code"]:
            errs.append(f"mã NCC: mong {exp['vendor_code']} thực {res.get('vendor_code')}")
        if bool(res["reconciled"]) != exp["reconciled"]:
            errs.append(f"reconciled: mong {exp['reconciled']} thực {res['reconciled']}")

        n_inv = sum(g["n_invoices"] for g in res["groups"])
        if n_inv != exp["n_invoices"]:
            errs.append(f"số hóa đơn: mong {exp['n_invoices']} thực {n_inv}")

        got_ex = {e["row_kind"]: (e["n_rows"], round(e["amount"])) for e in res["excluded"]}
        for k, v in exp["excluded"].items():
            if k not in got_ex:
                errs.append(f"thiếu mục bị loại '{k}' — tiền biến mất im lặng")
            elif got_ex[k] != v:
                errs.append(f"mục '{k}': mong {v} thực {got_ex[k]}")

        # KHÔNG được điền tên MÌNH vào nhãn nhóm / tên điểm.
        ours = "HOANG GIANG"
        if any(ours in str(g.get("group_label") or "").upper() for g in res["groups"]):
            errs.append("nhãn nhóm đang mang TÊN CỦA MÌNH — sẽ in nhầm vào ô "
                        "'Đơn vị mua hàng' của bảng kê hai bên ký")

        mark = "✅" if not errs else "❌"
        d = t["discount_amount"]
        print(f"  {mark} {res['chain']:16} {t['n_rows']:4}d/{t['n_groups']:3}nhóm/"
              f"{n_inv:3}HĐ · cơ sở {round(t['base_amount']):>15,} · CK "
              f"{'(theo tỷ lệ)' if d is None else format(round(d), ',')}"
              f" · {res['mode']}")
        for e in res["excluded"]:
            print(f"       ↳ loại: {e['row_kind'][:44]:46} {e['n_rows']:4}d {round(e['amount']):>15,}")
        for e in errs:
            print(f"       └─ {e}")
        bad += bool(errs)

    # ── Chốt riêng: KHÔNG được cộng cả bốn nhóm của Central Retail ────────
    print("-" * 78)
    content = base64.b64encode(
        open(os.path.join(rc.SAMPLES, "Chi tiết doanh số BigC.xlsx"), "rb").read()).decode()
    res = md.read_discount_basis(content)
    got = round(res["totals"]["base_amount"])
    ok = got != CR_ALL_GROUPS_BASE and got == EXPECTED["Chi tiết doanh số BigC.xlsx"]["base"]
    print(f"  {'✅' if ok else '❌'} Central Retail: cơ sở là {got:,} (một nhóm), "
          f"KHÔNG phải {CR_ALL_GROUPS_BASE:,} (cộng cả 4 nhóm = nhân doanh số 6 lần)")
    bad += not ok

    # ── Chốt riêng: hai cách tính KHÁC NHAU THẬT ─────────────────────────
    rows_base = res["totals"]["base_amount"]
    per_line = res["totals"]["discount_amount"]
    rate_total = rows_base * (res["rate"] or 0) / 100.0
    ok = abs(per_line - rate_total) > 1.0
    print(f"  {'✅' if ok else '❌'} hai cách tính lệch thật: cộng dòng {round(per_line):,} vs "
          f"tỷ lệ×tổng {rate_total:,.2f} — lệch {per_line - rate_total:,.2f}đ")
    bad += not ok

    # ── Chốt riêng: ép sai chuỗi phải NỔ, không ra số trông hợp lý ────────
    print("-" * 78)
    pairs = [("Chi tiết doanh số BigC.xlsx", "lotte"),
             ("7466- chi tiết doanh số Lotte.xlsx", "mega_market"),
             ("Chi tiết doanh số Mega Market.xlsx", "central_retail"),
             ("Chi tiết thanh toán Lotte.xls", "lotte")]
    for fname, chain in pairs:
        c = base64.b64encode(open(os.path.join(rc.SAMPLES, fname), "rb").read()).decode()
        try:
            r = md.read_discount_basis(c, chain=chain)
            print(f"  ❌ ép '{fname[:34]}' thành {chain} -> KHÔNG nổ "
                  f"({r['totals']['n_rows']} dòng, {round(r['totals']['base_amount']):,})")
            bad += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ✅ ép '{fname[:34]}' thành {chain} -> dừng: {str(e)[:52]}")

    # Emart CỐ Ý chưa có parser (file Rebate Settlement là PDF). Dùng FILE THẬT
    # để phép kiểm đo đúng nhánh 'chuỗi không có parser', chứ không dừng sớm ở
    # nhánh 'định dạng file không hỗ trợ'.
    real = base64.b64encode(
        open(os.path.join(rc.SAMPLES, "Chi tiết doanh số BigC.xlsx"), "rb").read()).decode()
    try:
        md.read_discount_basis(real, chain="Emart")
        print("  ❌ chuỗi ngoài danh sách -> KHÔNG dừng")
        bad += 1
    except Exception as e:  # noqa: BLE001
        print(f"  ✅ chuỗi ngoài danh sách (Emart, mẫu là PDF) -> dừng: {str(e)[:60]}")

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — đọc đúng nhóm, đúng cách tính, không nhận tên mình làm bên mua"
          if not bad else f"HỎNG {bad} mục")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
