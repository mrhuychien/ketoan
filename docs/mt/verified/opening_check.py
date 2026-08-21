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

GRAND_TOTAL = 5_059_095_894      # nợ GỘP cả bảy chuỗi (chỉ sheet hóa đơn mình xuất)

# Ba chuỗi có sheet ghi giảm. `stated_net` là con số CHÍNH FILE TỰ IN RA —
# đây là phép đối chiếu mạnh nhất của cả bộ kiểm: parser không được tự nghĩ ra
# số ròng, nó phải ra đúng số kế toán đã tính tay trong file.
NET_CASES = [
    ("Central Retail",    952_935, 1_631_913_105),
    ("Saigon Co.op",  132_250_823,   979_846_237),
    ("WinCommerce",    50_764_968, 1_279_114_686),
]

NET_TOTAL = 4_875_127_168        # nợ RÒNG cả bảy chuỗi — số thật sự mang sang


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
        if round(t["opening_debt_gross"]) != remaining:
            errs.append(f"nợ gộp {t['opening_debt_gross']:,.0f} != {remaining:,}")
        if t["n_open"] != n_open:
            errs.append(f"{t['n_open']} dòng còn nợ != {n_open}")
        if not r["reconciled"]:
            errs.append("ba cột quyết định số dư KHÔNG khớp: %s" % r["blocking"])
        grand += t["opening_debt_gross"]
        ok = not errs
        print(f"  {'✅' if ok else '❌'} {chain:<15} {t['n_rows']:>5} dòng · "
              f"{t['n_open']:>4} còn nợ · gộp {t['opening_debt_gross']:>16,.0f}đ")
        for e in errs:
            print(f"       └─ {e}")
        bad += not ok

    print("-" * 84)
    ok = round(grand) == GRAND_TOTAL
    print(f"  {'✅' if ok else '❌'} TỔNG NỢ GỘP CẢ BẢY CHUỖI: {grand:,.0f}đ "
          f"(mong {GRAND_TOTAL:,})")
    bad += not ok

    # ── 1b. Sheet GHI GIẢM — mỗi file tự in ra nợ RÒNG, phải khớp ────────
    #
    # Kế toán mô tả sheet này: "hóa đơn xuất trả, hóa đơn dịch vụ siêu thị xuất
    # cho mình". Cả hai đều LÀM GIẢM số phải thu. Bỏ qua nó là nhập THỪA công nợ
    # đúng 183.968.726đ.
    print("-" * 84)
    net_grand = 0.0
    for chain, ded_open, stated_net in NET_CASES:
        r = results.get(chain)
        if not r:
            continue
        t = r["totals"]
        errs = []
        if round(t["deduction_open"]) != ded_open:
            errs.append(f"ghi giảm {t['deduction_open']:,.0f} != {ded_open:,}")
        if round(t["opening_debt"]) != stated_net:
            errs.append(f"nợ ròng {t['opening_debt']:,.0f} != {stated_net:,}")
        ok = not errs
        print(f"  {'✅' if ok else '❌'} {chain:<15} gộp {t['opening_debt_gross']:>15,.0f} "
              f"− ghi giảm {t['deduction_open']:>13,.0f} = {t['opening_debt']:>15,.0f}đ"
              f"{'  (= số file tự in)' if ok and stated_net else ''}")
        for e in errs:
            print(f"       └─ {e}")
        bad += not ok
    for chain in ("AEON", "Emart", "LOTTE", "Mega Market"):
        r = results.get(chain)
        if not r:
            continue
        ok = r["totals"]["deduction_open"] == 0
        print(f"  {'✅' if ok else '❌'} {chain:<15} không có sheet ghi giảm -> "
              f"nợ ròng = nợ gộp")
        bad += not ok
    net_grand = sum(r["totals"]["opening_debt"] for r in results.values())
    ok = round(net_grand) == NET_TOTAL
    print(f"  {'✅' if ok else '❌'} TỔNG NỢ RÒNG — con số THẬT SỰ mang sang: "
          f"{net_grand:,.0f}đ (mong {NET_TOTAL:,})")
    bad += not ok

    # Cột 'đã cấn trừ' / 'còn lại' của Central Retail KHÔNG có nhãn — phải suy ra
    # bằng cách ĐỀ XUẤT rồi CHỨNG MINH, không đếm cột mù.
    r = results.get("Central Retail")
    if r and r["deductions"]:
        d = r["deductions"][0]
        ok = (not d["unreadable"]) and d["columns"].get("paid") == 7 \
            and d["columns"].get("remaining") == 8
        print(f"  {'✅' if ok else '❌'} Central Retail: hai cột cuối của sheet ghi giảm "
              f"KHÔNG có nhãn -> suy ra cột {d['columns'].get('paid')}/{d['columns'].get('remaining')} "
              f"bằng phép `TỔNG − đã cấn trừ = còn lại`")
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

    # ── 8. Ba nhóm dòng còn nợ — ba đường xử khác hẳn nhau ──────────────
    #
    # ERPNext site này chỉ có dữ liệu TỪ 01/05/2026. Nên "còn nợ" không phải một
    # cục: hóa đơn trước mốc đó KHÔNG có trong ERPNext để mà nối.
    print("-" * 84)
    GOLIVE = "2026-05-01"
    agg = {}
    for fname, chain, *_ in CASES:
        r = read(fname, golive=GOLIVE)
        for e in r["totals"]["by_kind"]:
            a = agg.setdefault(e["kind"], {"label": e["label"], "n": 0, "amount": 0.0})
            a["n"] += e["n"]
            a["amount"] += e["amount"]

    WANT = [
        (mo.KIND_IN_ERP,      1101, 4_434_428_970),
        (mo.KIND_PRE_GOLIVE,    57,   578_001_744),
        (mo.KIND_NO_INVOICE,     9,    46_665_180),
    ]
    for kind, n, amount in WANT:
        a = agg.get(kind) or {"label": kind, "n": 0, "amount": 0.0}
        ok = a["n"] == n and round(a["amount"]) == amount
        print(f"  {'✅' if ok else '❌'} {a['label']:<46} {a['n']:>5} dòng "
              f"{a['amount']:>17,.0f}đ")
        if not ok:
            print(f"       └─ mong {n} dòng / {amount:,}đ")
        bad += not ok

    ok = sum(a["n"] for a in agg.values()) == 1167
    print(f"  {'✅' if ok else '❌'} ba nhóm cộng lại = 1.167 dòng còn nợ, không dòng nào "
          f"rơi ra ngoài")
    bad += not ok

    # Không khai `golive` -> KHÔNG được tự đoán một mốc.
    r = read("congno_saigon_coop.xlsx")
    pre = next(e for e in r["totals"]["by_kind"] if e["kind"] == mo.KIND_PRE_GOLIVE)
    ok = pre["n"] == 0 and any("CHƯA khai ngày" in w for w in r["warnings"])
    print(f"  {'✅' if ok else '❌'} không khai ngày go-live -> KHÔNG tự đoán mốc, "
          f"báo ra là chưa tách được")
    bad += not ok

    # Dòng KHÔNG có số hóa đơn phải tách kể cả khi chưa khai go-live: nó không
    # phải công nợ hóa đơn, và điều đó không phụ thuộc mốc ngày nào.
    r = read("congno_wincommerce.xlsx")
    noinv = next(e for e in r["totals"]["by_kind"] if e["kind"] == mo.KIND_NO_INVOICE)
    ok = noinv["n"] == 9 and round(noinv["amount"]) == 46_665_180
    print(f"  {'✅' if ok else '❌'} 9 dòng `chưa giao hàng` của Win tách được KHÔNG cần "
          f"biết ngày go-live ({noinv['amount']:,.0f}đ)")
    bad += not ok

    ok = any("chưa giao" in w for w in r["warnings"])
    print(f"  {'✅' if ok else '❌'} và được NÊU RA — file vẫn cộng chúng vào `Số còn nợ`")
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
