"""Kiểm tầng đọc SỐ DƯ ĐẦU KỲ từ 7 file Excel theo dõi công nợ (`mt_opening.py`).

    python3 docs/mt/verified/opening_check.py

Chạy trên BẢY FILE THẬT ở `docs/mt/samples/congno/` — chính các file kế toán đang
dùng để theo dõi công nợ, file cũ nhất chạy từ 2018.

Đây là lần nhập DUY NHẤT quyết định mọi con số công nợ về sau: sai ở đây thì mọi
màn hình, mọi lần đi đòi nợ, mọi bút toán đều sai theo, và không có gì để đối
chiếu nữa vì Excel đã bỏ. Vì vậy phép kiểm bám vào SỐ CHÍNH FILE IN RA, không
bám vào số parser tự cộng.

════════════════════════════════════════════════════════════════════════════
BỐN CHỖ ĐÃ ĐO ĐƯỢC LÀ DỄ SAI
════════════════════════════════════════════════════════════════════════════

1. TIÊU ĐỀ TRONG FILE NÓI DỐI — file BigC ghi `CÔNG NỢ VINCOM`, trùng hệt file
   WinCommerce. Nhận diện bằng tiêu đề là nhập nhầm cả 1,6 tỷ công nợ sang chuỗi
   khác.

2. DÒNG TỔNG CỘNG CỦA CHÍNH FILE CÓ THỂ SAI — ô tổng VAT của Co.op mang công
   thức `=SUM(F9:F340)` trong khi bốn cột kia cộng tới dòng 3755. Không được vì
   một cột hỏng mà bỏ cả file, cũng không được im lặng bỏ qua.

3. DÒNG NỢ ÂM — AEON có 2 dòng `Số còn nợ` âm. Cộng theo dấu ra 175.843.980đ
   (đúng số file in); lọc `> 0` rồi cộng ra 176.580.000đ, thừa 736.020đ.

4. SHEET KHAI RỘNG BẤT THƯỜNG — Emart khai 16.375 cột trong khi cột có dữ liệu
   xa nhất là 17. Chốt chống OOM từ chối cả file; phải cắt cột chứ không từ chối.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

DIR = "docs/mt/samples/congno"

# SỐ FILE TỰ IN RA ở dòng TỔNG CỘNG — gõ lại từ bản in, KHÔNG lấy từ parser.
#   file, chuỗi phải nhận ra, TỔNG hóa đơn, Số đã trả, SỐ CÒN NỢ, số dòng còn nợ
CASES = [
    ("congno_aeon.xlsx",           "AEON",            7_240_148_334,  7_064_304_354,   175_843_980, 51),
    ("congno_central_retail.xlsx", "Central Retail", 10_544_126_584,  8_911_260_544, 1_632_866_040, 367),
    ("congno_emart.xlsx",          "Emart",           6_029_420_844,  5_935_820_484,    93_600_360, 9),
    ("congno_lotte.xlsx",          "LOTTE",           8_909_350_474,  8_289_122_674,   620_227_800, 99),
    ("congno_mega_market.xlsx",    "Mega Market",    13_940_895_324, 13_846_314_324,    94_581_000, 7),
    ("congno_saigon_coop.xlsx",    "Saigon Co.op",   25_075_990_887, 23_963_893_827, 1_112_097_060, 355),
    ("congno_wincommerce.xlsx",    "WinCommerce",    41_698_172_526, 40_368_292_872, 1_329_879_654, 279),
]

GRAND_TOTAL = 5_059_095_894      # tổng số dư đầu kỳ cả bảy chuỗi


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    mo = importlib.import_module("ketoan.api.mt_opening")

    def read(fname, **kw):
        path = os.path.join(rc.REPO, DIR, fname)
        raw = open(path, "rb").read()
        return mo.read_opening(base64.b64encode(raw).decode(), **kw)

    print("=" * 84)
    print("KIỂM ĐỌC SỐ DƯ ĐẦU KỲ TỪ FILE EXCEL THEO DÕI CÔNG NỢ")
    print("=" * 84)
    bad = 0
    grand = 0.0
    results = {}

    # ── 1. Bảy file: nhận đúng chuỗi + ba cột quyết định khớp từng đồng ──
    for fname, chain, gross, paid, remaining, n_open in CASES:
        try:
            r = read(fname)
        except Exception as e:                                     # noqa: BLE001
            print(f"  ❌ {fname}: {str(e)[:72]}")
            bad += 1
            continue
        results[chain] = r
        t = r["totals"]
        errs = []
        if r["chain_detected"] != chain:
            errs.append(f"nhận nhầm chuỗi: {r['chain_detected']!r}")
        if round(r["computed"]["gross"]) != gross:
            errs.append(f"TỔNG {r['computed']['gross']:,.0f} != {gross:,}")
        if round(r["computed"]["paid"]) != paid:
            errs.append(f"đã trả {r['computed']['paid']:,.0f} != {paid:,}")
        if round(t["opening_debt"]) != remaining:
            errs.append(f"còn nợ {t['opening_debt']:,.0f} != {remaining:,}")
        if t["n_open"] != n_open:
            errs.append(f"{t['n_open']} dòng còn nợ != {n_open}")
        if not r["reconciled"]:
            errs.append("ba cột quyết định số dư KHÔNG khớp: %s" % r["blocking"])
        grand += t["opening_debt"]
        ok = not errs
        print(f"  {'✅' if ok else '❌'} {chain:<15} {t['n_rows']:>5} dòng · "
              f"{t['n_open']:>4} còn nợ · {t['opening_debt']:>16,.0f}đ")
        for e in errs:
            print(f"       └─ {e}")
        bad += not ok

    print("-" * 84)
    ok = round(grand) == GRAND_TOTAL
    print(f"  {'✅' if ok else '❌'} TỔNG SỐ DƯ ĐẦU KỲ CẢ BẢY CHUỖI: {grand:,.0f}đ "
          f"(mong {GRAND_TOTAL:,})")
    bad += not ok

    # ── 2. Bẫy 1 — tiêu đề trong file nói dối ────────────────────────────
    print("-" * 84)
    r = results.get("Central Retail")
    if r:
        ok = r["chain_detected"] == "Central Retail"
        print(f"  {'✅' if ok else '❌'} file BigC ghi tiêu đề `CÔNG NỢ VINCOM` mà vẫn nhận "
              f"đúng Central Retail (nhận bằng CHỮ KÝ CỘT, không bằng tiêu đề)")
        bad += not ok

    # Hai file cùng tiêu đề `CÔNG NỢ VINCOM` phải ra HAI chuỗi khác nhau.
    a = results.get("Central Retail", {}).get("chain_detected")
    b = results.get("WinCommerce", {}).get("chain_detected")
    ok = a == "Central Retail" and b == "WinCommerce"
    print(f"  {'✅' if ok else '❌'} hai file cùng tiêu đề -> hai chuỗi khác nhau: {a} · {b}")
    bad += not ok

    # ── 3. Bẫy 2 — cột tổng hỏng thì CẢNH BÁO, không chặn ────────────────
    print("-" * 84)
    r = results.get("Saigon Co.op")
    if r:
        vat = next((c for c in r["checks"] if c["label"] == "Tiền VAT"), None)
        ok = vat is not None and not vat["ok"] and r["reconciled"]
        print(f"  {'✅' if ok else '❌'} Co.op: ô tổng VAT hỏng (`=SUM(F9:F340)`) -> BÁO ra "
              f"nhưng KHÔNG chặn nhập, vì ba cột quyết định số dư vẫn khớp")
        bad += not ok

        ok = any("Tiền VAT" in w for w in r["warnings"])
        print(f"  {'✅' if ok else '❌'} lệch được nêu ĐÍCH DANH cột trong cảnh báo")
        bad += not ok

    # Ba cột quyết định số dư mà lệch thì PHẢI chặn.
    print("-" * 84)
    orig = mo._find_total_row

    def fake_total(grid, money_row, cols):
        r0 = orig(grid, money_row, cols)
        # Bơm sai số vào ô tổng `Số còn nợ` của chính file thật.
        grid[r0 - 1][cols["remaining"] - 1] = 999_999_999
        return r0

    mo._find_total_row = fake_total
    try:
        r = read("congno_lotte.xlsx")
        ok = (not r["reconciled"]) and "SỐ CÒN NỢ" in r["blocking"]
        print(f"  {'✅' if ok else '❌'} bơm sai ô tổng `Số còn nợ` -> DỪNG "
              f"(blocking={r['blocking']})")
        bad += not ok
    finally:
        mo._find_total_row = orig

    # ── 4. Bẫy 3 — dòng nợ ÂM phải cộng theo dấu ─────────────────────────
    print("-" * 84)
    r = results.get("AEON")
    if r:
        # Đọc lại đầy đủ để lấy `rows` (preview đã cắt).
        full = read("congno_aeon.xlsx")
        neg = [x for x in full["rows"] if x["remaining"] < -0.5]
        signed = sum(x["remaining"] for x in full["rows"])
        positive_only = sum(x["remaining"] for x in full["rows"] if x["remaining"] > 0)
        ok = len(neg) == 2 and round(signed) == 175_843_980
        print(f"  {'✅' if ok else '❌'} AEON có {len(neg)} dòng nợ ÂM · cộng THEO DẤU "
              f"{signed:,.0f}đ = số file in")
        bad += not ok

        ok = round(positive_only) == 176_580_000 and round(positive_only) != round(signed)
        print(f"  {'✅' if ok else '❌'} nếu lọc `> 0` rồi cộng sẽ ra {positive_only:,.0f}đ "
              f"— thừa {positive_only - signed:,.0f}đ")
        bad += not ok

        ok = any("ÂM" in w for w in full["warnings"])
        print(f"  {'✅' if ok else '❌'} dòng nợ âm được NÊU RA trong cảnh báo")
        bad += not ok

    # ── 5. Bẫy 4 — sheet khai 16.375 cột vẫn đọc được ────────────────────
    print("-" * 84)
    r = results.get("Emart")
    ok = bool(r) and r["totals"]["n_rows"] == 900
    print(f"  {'✅' if ok else '❌'} Emart khai 16.375 cột (dữ liệu thật tới cột 17) -> "
          f"vẫn đọc được {r['totals']['n_rows'] if r else 0} dòng")
    bad += not ok

    # Đường nạp bảng kê thanh toán KHÔNG được đổi hành vi: mặc định vẫn từ chối.
    ma = importlib.import_module("ketoan.api.mt_advice")
    raw = open(os.path.join(rc.REPO, DIR, "congno_emart.xlsx"), "rb").read()
    b64 = base64.b64encode(raw).decode()
    try:
        ma.read_sheets(b64)
        print("  ❌ `read_sheets` mặc định vẫn nhận sheet khai 16.375 cột")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "quá lớn" in str(e)
        print(f"  {'✅' if ok else '❌'} `read_sheets` mặc định VẪN từ chối sheet khai quá "
              f"rộng — chốt chống OOM của đường nạp bảng kê không bị nới")
        bad += not ok

    # ── 6. Mỗi file nhận ra ĐÚNG MỘT chuỗi, không mập mờ ─────────────────
    print("-" * 84)
    amb = [c for _f, c, *_ in CASES if results.get(c) and results[c]["chain_detected"] != c]
    ok = not amb
    print(f"  {'✅' if ok else '❌'} cả {len(CASES)} file nhận ra đúng một chuỗi, "
          f"không file nào mập mờ")
    for c in amb:
        print(f"       └─ {c} -> {results[c]['chain_detected']!r}")
    bad += not ok

    # Chọn tay phải THẮNG kết quả tự nhận diện — kế toán mới là người quyết.
    r = read("congno_lotte.xlsx", chain="Emart")
    ok = r["chain"] == "Emart" and r["chain_detected"] == "LOTTE"
    print(f"  {'✅' if ok else '❌'} chọn chuỗi bằng tay THẮNG tự nhận diện "
          f"(chọn {r['chain']}, máy đoán {r['chain_detected']}) — và vẫn báo máy đoán gì")
    bad += not ok

    print("=" * 84)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — bảy file đọc đúng từng đồng theo số CHÍNH FILE IN RA, "
          "không file nào nhận nhầm chuỗi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
