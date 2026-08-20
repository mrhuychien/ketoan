"""Kiểm tầng đọc `Rebate Settlement` PDF của Emart (`ketoan/api/mt_rebate_pdf.py`).

    python3 docs/mt/verified/rebate_pdf_check.py

Chạy trên FILE THẬT `docs/mt/samples/Chi tiết doanh số Emart.PDF` (kỳ 07.2026,
mã NCC 100968), không dùng dữ liệu bịa.

Đây là chuỗi duy nhất gửi PDF, và là chuỗi mà một dòng đọc nhầm loại sẽ khiến
mình XUẤT HÓA ĐƠN CHO KHOẢN MÌNH KHÔNG ĐƯỢC XUẤT: bảy dòng trong file, chỉ MỘT
dòng (`Rebate AP%Monthly Discount`, 2.737.350đ) là mình xuất; sáu dòng còn lại
(`Fee AR%…`, 8.212.050đ) do Emart xuất cho mình. Lấy nhầm cả bảy là xuất khống
8.212.050đ tiền hóa đơn VÀ ghi nhận hai lần cùng một khoản.

Phần đột biến ở cuối cố ý làm hỏng chính file thật rồi hỏi: parser có kêu không?
Một phép kiểm chỉ chứng minh được điều gì khi nó BIẾT TRƯỢT.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

SAMPLE = "docs/mt/samples/Chi tiết doanh số Emart.PDF"

# Số kiểm tra IN TRÊN FILE — gõ lại từ bản in, không lấy từ parser.
D_INVOICE = 91_245_000
D_RETURN = 0
D_NET = 91_245_000
D_REBATE = 2_737_350
D_FEE = 8_212_050
D_SUPPORT = 0
D_TOTAL = 10_949_400
VENDOR = "100968"
PERIOD = "07.2026"


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    mp = importlib.import_module("ketoan.api.mt_rebate_pdf")
    raw = open(os.path.join(rc.REPO, SAMPLE), "rb").read()

    print("=" * 78)
    print("KIỂM ĐỌC REBATE SETTLEMENT EMART (PDF)")
    print("=" * 78)
    bad = 0

    # ── 1. Nhận dạng file ────────────────────────────────────────────────
    ok = mp.is_pdf(raw)
    print(f"  {'✅' if ok else '❌'} nhận PDF theo chữ ký byte `%PDF` "
          f"(mẫu thật có đuôi `.PDF` VIẾT HOA)")
    bad += not ok

    ok = not mp.is_pdf(b"PK\x03\x04....")
    print(f"  {'✅' if ok else '❌'} file .xlsx KHÔNG bị nhận nhầm là PDF")
    bad += not ok

    # ── 2. Đầu trang: mã NCC, kỳ, ngày chốt, điểm ────────────────────────
    print("-" * 78)
    res = mp.parse_rebate_settlement(raw)
    for label, got, want in (
        ("mã NCC của mình tại Emart", res["vendor_code"], VENDOR),
        ("kỳ chốt", res["period"], PERIOD),
        ("ngày chốt", str(res["settled_date"]), "2026-07-31"),
        ("điểm bán", res["store"], "All-Store Thiso Retail"),
    ):
        ok = got == want
        print(f"  {'✅' if ok else '❌'} {label}: {got!r}")
        bad += not ok

    # Bẫy đã sập một lần ở Central Retail: `Vendor` trong file là CHÍNH MÌNH.
    ok = "vendor_name" not in res
    print(f"  {'✅' if ok else '❌'} KHÔNG đọc tên `Vendor` (đó là tên MÌNH, "
          f"không phải bên mua) — bên mua lấy từ Customer/MT Store")
    bad += not ok

    # ── 3. Số kiểm tra đọc đúng từng đồng ────────────────────────────────
    print("-" * 78)
    dec = res["declared"]
    for label, got, want in (
        ("Invoice Amount", dec["invoice_amount"], D_INVOICE),
        ("Return Amount", dec["return_amount"], D_RETURN),
        ("Net Amount", dec["net_amount"], D_NET),
        ("Rebate Amount", dec["rebate_amount"], D_REBATE),
        ("Fee Amount", dec["fee_amount"], D_FEE),
        ("Support Amount", dec["support_amount"], D_SUPPORT),
        ("Total", dec["total"], D_TOTAL),
    ):
        ok = got is not None and round(got) == want
        print(f"  {'✅' if ok else '❌'} {label}: {got:,.0f}đ" if got is not None
              else f"  ❌ {label}: KHÔNG đọc được")
        bad += not ok

    # ── 4. AI XUẤT HÓA ĐƠN — phần đắt nhất ───────────────────────────────
    print("-" * 78)
    ok = len(res["ours"]) == 1 and len(res["theirs"]) == 6
    print(f"  {'✅' if ok else '❌'} 7 dòng chia đúng: {len(res['ours'])} dòng MÌNH xuất, "
          f"{len(res['theirs'])} dòng EMART xuất")
    bad += not ok

    sum_ours = sum(x["amount"] for x in res["ours"])
    ok = round(sum_ours) == D_REBATE
    print(f"  {'✅' if ok else '❌'} tiền MÌNH xuất {sum_ours:,.0f}đ = `Rebate Amount` "
          f"in trên file")
    bad += not ok

    sum_theirs = sum(x["amount"] for x in res["theirs"])
    ok = round(sum_theirs) == D_FEE
    print(f"  {'✅' if ok else '❌'} tiền EMART xuất {sum_theirs:,.0f}đ = `Fee Amount` "
          f"— KHÔNG lọt vào bảng kê của mình")
    bad += not ok

    o = res["ours"][0]
    ok = (o["kind"] == "Rebate" and o["code"].upper().startswith("AP%")
          and "vendor" in o["settlement_type"].lower())
    print(f"  {'✅' if ok else '❌'} dòng mình xuất khớp CẢ BA tín hiệu: "
          f"{o['kind']} · {o['code']} · {o['settlement_type']}")
    bad += not ok

    # ── 5. Bộ khóa chung + sáu phép đối chiếu ────────────────────────────
    print("-" * 78)
    b = mp.to_basis(raw)
    bads = [c for c in b["checks"] if not c["ok"]]
    ok = not bads
    print(f"  {'✅' if ok else '❌'} {len(b['checks'])} phép đối chiếu với số in trên file "
          f"đều khớp")
    for c in bads:
        print(f"       └─ {c['label']}: file {c['declared']} vs parser {c['computed']}")
    bad += not ok

    ok = (len(b["rows"]) == 1 and round(b["rows"][0]["discount_amount"]) == D_REBATE
          and round(b["rows"][0]["base_amount"]) == D_NET and b["rows"][0]["rate"] == 3.0)
    print(f"  {'✅' if ok else '❌'} bảng kê ra 1 dòng: cơ sở {D_NET:,}đ × 3% = "
          f"{D_REBATE:,}đ (Emart chốt cả kỳ một dòng, không theo hóa đơn)")
    bad += not ok

    ok = len(b["excluded"]) == 6 and all("Emart xuất" in x["reason"] for x in b["excluded"])
    print(f"  {'✅' if ok else '❌'} 6 dòng phí bị loại và NÊU LÝ DO, không biến mất im lặng")
    bad += not ok

    ok = b["mode"] == "rate_on_total" and b["vendor_code"] == VENDOR
    print(f"  {'✅' if ok else '❌'} cách tính `{b['mode']}` + mã NCC {b['vendor_code']} "
          f"khớp bộ khóa chung của `mt_discount_read`")
    bad += not ok

    # Hợp đồng với tầng trên: đủ khóa, không thiếu cái nào.
    md = importlib.import_module("ketoan.api.mt_discount_read")
    want_keys = {"chain_key", "chain", "vendor_code", "mode", "mode_label", "rate",
                 "groups", "rows", "excluded", "checks", "reconciled", "warnings",
                 "totals", "sheets"}
    import base64
    full = md.read_discount_basis(base64.b64encode(raw).decode())
    miss = want_keys - set(full)
    ok = not miss and full["chain_key"] == "emart" and full["reconciled"]
    print(f"  {'✅' if ok else '❌'} `read_discount_basis` rẽ đúng nhánh PDF -> chuỗi "
          f"{full['chain']}, đủ {len(want_keys)} khóa, đối chiếu khớp")
    if miss:
        print(f"       └─ thiếu khóa: {sorted(miss)}")
    bad += not ok

    # ── 5b. DÒ NHÃN: hai bẫy chỉ lộ ra ở bản NHIỀU TRANG ─────────────────
    #
    # File mẫu có đúng một trang nên không bẫy nào lộ. Cả hai đã ĐO ĐƯỢC bằng
    # dòng giả lập, và cả hai đều cướp/làm mất một con số chốt.
    print("-" * 78)

    def _w(txt, y):
        ws, x = [], 0
        for t in txt.split():
            ws.append({"text": t, "x0": x, "x1": x + len(t) * 5, "y": y})
            x += len(t) * 5 + 6
        return ws

    got = mp.label_value(_w("Sub Total 999.999", 300) + _w("Total 10.949.400", 200),
                         "Total", anchored=True)
    ok = got == 10_949_400
    print(f"  {'✅' if ok else '❌'} `Sub Total` KHÔNG cướp được nhãn `Total` -> {got:,.0f}"
          if got else "  ❌ `Total` đọc ra None")
    bad += not ok

    got = mp.label_value(_w("Net Amount Settlement Type", 300)
                         + _w("Net Amount 91.245.000", 200), "Net Amount")
    ok = got == 91_245_000
    print(f"  {'✅' if ok else '❌'} nhãn `Net Amount` lặp lại ở tiêu đề cột (không kèm số) "
          f"-> vẫn lấy được số ở dòng kia: {got:,.0f}" if got else
          "  ❌ `Net Amount` đọc ra None")
    bad += not ok

    # Dòng tiêu đề cột KHÔNG được đọc thành dòng dữ liệu (bản nhiều trang lặp nó).
    hdr = "Rebate type Rebate Rate Net Amount Settlement Settlement Type Settlement Date"
    ok = mp.ROW_RE.match(hdr) is None
    print(f"  {'✅' if ok else '❌'} dòng TIÊU ĐỀ CỘT không khớp văn phạm dòng dữ liệu "
          f"(bản nhiều trang lặp tiêu đề ở mỗi trang)")
    bad += not ok

    # ── 6. ĐỘT BIẾN — phép kiểm phải BIẾT TRƯỢT ──────────────────────────
    print("-" * 78)
    print("  Đột biến: làm hỏng chính file thật, parser phải kêu")

    def mutate(fn, label, want_throw=True):
        nonlocal bad
        orig = mp.lines_of
        mp.lines_of = lambda words: fn(orig(words))
        try:
            b2 = mp.to_basis(raw)
            failed = [c for c in b2["checks"] if not c["ok"]]
            ok2 = bool(failed) if want_throw else not failed
            detail = (failed[0]["label"] if failed else "mọi phép vẫn khớp")
        except Exception as e:                                     # noqa: BLE001
            ok2 = want_throw
            detail = "DỪNG: " + str(e)[:60]
        finally:
            mp.lines_of = orig
        print(f"    {'✅' if ok2 else '❌'} {label} -> {detail}")
        bad += not ok2

    # (a) bỏ một dòng phí -> Fee Amount và Total phải lệch
    mutate(lambda ls: [x for x in ls if "Display Fee" not in x[0]],
           "bỏ dòng `AR%Display Fee` 1.824.900đ")

    # (b) nhân đôi dòng chiết khấu -> Rebate Amount phải lệch
    def dup(ls):
        out = []
        for x in ls:
            out.append(x)
            if x[0].startswith("Rebate AP%"):
                out.append(x)
        return out
    mutate(dup, "nhân đôi dòng `Rebate AP%Monthly Discount`")

    # (c) ĐỔI PHE một dòng phí thành 'Vendor Tax Invoice' -> ba tín hiệu cãi nhau
    mutate(lambda ls: [(x[0].replace("Fee AR%Display Fee", "Fee AR%Display Fee")
                        .replace("E-mart Tax Invoice", "Vendor Tax Invoice")
                        if "Display Fee" in x[0] else x[0], x[1]) for x in ls],
           "sửa 1 dòng phí thành `Vendor Tax Invoice` (mình xuất)")

    # (d) đổi tỷ lệ 1 dòng -> phép 'cơ sở × tỷ lệ = tiền' phải bắt,
    #     dù MỌI tổng vẫn khớp nguyên vẹn
    mutate(lambda ls: [(x[0].replace(" 2% ", " 5% ") if "Display Fee" in x[0] else x[0], x[1])
                       for x in ls],
           "đổi tỷ lệ dòng phí 2% -> 5% (mọi TỔNG vẫn khớp)")

    # (e) không hỏng gì -> phải KHÔNG kêu (chứng minh phép kiểm không kêu bừa)
    mutate(lambda ls: ls, "không sửa gì", want_throw=False)

    print("=" * 78)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — đọc đúng từng đồng, chia đúng ai xuất hóa đơn, "
          "mọi đột biến đều bị bắt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
