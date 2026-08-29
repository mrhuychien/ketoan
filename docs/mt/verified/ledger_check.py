#!/usr/bin/env python3
"""Kiểm SỔ THEO DÕI HÓA ĐƠN — cuốn Excel kế toán vẫn giữ.

════════════════════════════════════════════════════════════════════════════
BỐN CHỐT CHẶN
════════════════════════════════════════════════════════════════════════════

1. **PHẢI THU = TIỀN HĐ − HÀNG TRẢ LẠI.** Đây là con số kế toán đem đi đòi.
   Lấy thẳng `grand_total` là đòi cả phần hàng đã trả về kho — đúng cái lỗi mà
   `_returns_join` sinh ra để sửa (xem `mt.py`).

2. **CHIẾT KHẤU THUỘC VỀ ĐỢT, KHÔNG THUỘC VỀ HÓA ĐƠN.** Bảng kê trừ chiết
   khấu/phí trên TỔNG đợt; không chứng từ nào nói tờ hóa đơn này chịu bao
   nhiêu. Chia đều cho từng tờ để mỗi dòng có một ô "chiết khấu" cho đẹp là
   BỊA, và con số bịa đó sẽ được đem đi đối chiếu với chuỗi.

3. **"CHƯA XUẤT HĐĐT" ĐỨNG TRƯỚC MỌI TRẠNG THÁI TIỀN.** Siêu thị không trả cho
   tờ chưa phát hành, nên nói "chưa thu" ở đó là đổ lỗi nhầm chỗ: việc phải làm
   là xuất hóa đơn, không phải đi đòi. Nhưng site chưa có ô số HĐĐT thì KHÔNG
   được dùng trạng thái này — không biết ≠ chưa xuất.

4. **ĐÂY LÀ SỔ TRONG KỲ, KHÔNG PHẢI SỐ DƯ.** Cột "Còn lại" cộng lại là công nợ
   của các tờ TRONG KỲ ĐANG XEM. Hai con số gần giống nhau mà khác nghĩa là chỗ
   dễ chép nhầm vào báo cáo nhất, nên màn hình phải nói ra.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


def row(name, total, returned=0.0, paid=0.0, clawed=0.0, has_e=1,
        review=0.0, date="2026-05-01"):
    return {"name": name, "customer": "K1", "customer_name": "Win BD",
            "posting_date": date, "due_date": None,
            "grand_total": total, "misa_series": "1C26THG",
            "misa_no": "1234" if has_e else None, "misa_status": None,
            "po_no": "PO-1", "ship_to": "ADDR-1",
            "returned": returned, "n_returns": 1 if returned else 0,
            "paid": paid, "clawed_back": clawed, "paid_review": review,
            "pay_lines": 1 if paid else 0, "has_einvoice": has_e}


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: True
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()

    ml = importlib.import_module("ketoan.api.mt_ledger")
    ml._company = lambda company=None: "HGC"
    ml._attach_advices = lambda rows: [r.setdefault("advices", []) for r in rows]

    print("=" * 82)
    print("KIỂM SỔ THEO DÕI HÓA ĐƠN")
    print("=" * 82)
    bad = 0

    # ── 1. PHẢI THU = TIỀN HĐ − HÀNG TRẢ LẠI ────────────────────────────
    FIX = [
        row("SI-A", 100.0),                                  # chưa thu
        row("SI-B", 100.0, returned=20.0, paid=80.0),         # trả 20, thu đủ 80
        row("SI-C", 100.0, paid=40.0),                        # thu một phần
        row("SI-D", 100.0, has_e=0),                          # chưa xuất HĐĐT
        row("SI-E", 100.0, paid=110.0, clawed=10.0),          # trả rồi đòi lại 10
    ]
    ml._rows = lambda *a, **k: [dict(r) for r in FIX]
    d = ml.get_ledger()
    by = {r["name"]: r for r in d["rows"]}

    ok = by["SI-B"]["net_due"] == 80.0 and by["SI-B"]["remaining"] == 0.0
    print(f"  {'✅' if ok else '❌'} PHẢI THU = tiền HĐ − hàng trả lại (100 − 20 = "
          f"{by['SI-B']['net_due']}), và thu 80 là ĐỦ — không đòi phần đã trả về kho")
    bad += not ok

    ok = by["SI-E"]["paid_net"] == 100.0 and by["SI-E"]["remaining"] == 0.0
    print(f"  {'✅' if ok else '❌'} ĐÃ NHẬN trừ phần chuỗi đòi lại (110 − 10 = "
          f"{by['SI-E']['paid_net']})")
    bad += not ok

    ok = all(r["remaining"] >= 0 for r in d["rows"])
    print(f"  {'✅' if ok else '❌'} 'Còn lại' không bao giờ âm — trả vượt là chuyện khác, "
          f"không phải nợ âm")
    bad += not ok

    # ── 2. TRẠNG THÁI ───────────────────────────────────────────────────
    print("-" * 82)
    want = {"SI-A": "chua_thu", "SI-B": "da_thu_du", "SI-C": "thu_mot_phan",
            "SI-D": "chua_xuat_hddt", "SI-E": "da_thu_du"}
    got = {k: v["status"] for k, v in by.items()}
    ok = got == want
    print(f"  {'✅' if ok else '❌'} trạng thái đúng cho cả năm hình dạng: {got}")
    bad += not ok

    ok = by["SI-D"]["status"] == ml.ST_NO_EINV
    print(f"  {'✅' if ok else '❌'} 'chưa xuất HĐĐT' ĐỨNG TRƯỚC trạng thái tiền — siêu thị không "
          f"trả cho tờ chưa phát hành, nói 'chưa thu' ở đó là đổ lỗi nhầm chỗ")
    bad += not ok

    # Site chưa có ô số HĐĐT -> KHÔNG được dùng trạng thái đó.
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: False)})()
    ml._rows = lambda *a, **k: [dict(r, has_einvoice=None) for r in FIX]
    d0 = ml.get_ledger()
    ok = not any(r["status"] == ml.ST_NO_EINV for r in d0["rows"])
    print(f"  {'✅' if ok else '❌'} site chưa có ô số HĐĐT -> KHÔNG tờ nào bị chấm 'chưa xuất' "
          f"(không biết ≠ chưa xuất)")
    bad += not ok
    ok = d0["einv_known"] is False
    print(f"  {'✅' if ok else '❌'} và trả cờ `einv_known=False` để màn hình nói được điều đó")
    bad += not ok
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()
    ml._rows = lambda *a, **k: [dict(r) for r in FIX]

    # ── 3. TỔNG là của CẢ BỘ LỌC, không phải của trang ──────────────────
    print("-" * 82)
    d = ml.get_ledger()
    t = d["totals"]
    ok = (t["count"] == 5 and t["grand_total"] == 500.0 and t["returned"] == 20.0
          and t["net_due"] == 480.0)
    print(f"  {'✅' if ok else '❌'} tổng cộng đúng: {t['count']} tờ · HĐ {t['grand_total']} · "
          f"trả hàng {t['returned']} · phải thu {t['net_due']}")
    bad += not ok

    ok = round(t["net_due"] - t["paid"], 2) >= t["remaining"] - 0.01
    print(f"  {'✅' if ok else '❌'} phải thu − đã nhận ≥ còn lại (chênh là phần trả VƯỢT của "
          f"từng tờ, không được cấn sang tờ khác)")
    bad += not ok

    # `page_size` bị kẹp sàn 10 (một trang 2 dòng là bắt người ta lật cả ngày),
    # nên phải dựng đủ dòng mới thấy được phân trang.
    BIG = [row("SI-%02d" % i, 100.0, paid=(50.0 if i % 2 else 0.0)) for i in range(1, 26)]
    ml._rows = lambda *a, **k: [dict(r) for r in BIG]
    d1 = ml.get_ledger(page_size=10)
    ok = (len(d1["rows"]) == 10 and d1["totals"]["count"] == 25
          and d1["totals"]["grand_total"] == 2500.0 and d1["pages"] == 3)
    print(f"  {'✅' if ok else '❌'} lật trang KHÔNG làm tổng nhảy theo ({len(d1['rows'])} dòng "
          f"trên trang, tổng vẫn {d1['totals']['count']} tờ / "
          f"{d1['totals']['grand_total']:,.0f}đ, {d1['pages']} trang)")
    bad += not ok

    d2 = ml.get_ledger(page_size=10, page=3)
    ok = len(d2["rows"]) == 5 and d2["totals"] == d1["totals"]
    print(f"  {'✅' if ok else '❌'} và trang cuối vẫn giữ NGUYÊN bộ tổng")
    bad += not ok
    ml._rows = lambda *a, **k: [dict(r) for r in FIX]

    # ── 4. Lọc trạng thái + tìm ─────────────────────────────────────────
    print("-" * 82)
    cases = [
        ({"status": "chua_thu"}, ["SI-A"]),
        ({"status": "da_thu_du"}, ["SI-B", "SI-E"]),
        ({"status": "chua_xuat_hddt"}, ["SI-D"]),
        ({"q": "SI-C"}, ["SI-C"]),
        ({"q": "PO-1"}, ["SI-A", "SI-B", "SI-C", "SI-D", "SI-E"]),
        ({"q": "1234"}, ["SI-A", "SI-B", "SI-C", "SI-E"]),
        ({"q": "không-có"}, []),
    ]
    miss = []
    for kw, wantn in cases:
        gotn = sorted(r["name"] for r in ml.get_ledger(**kw)["rows"])
        if gotn != sorted(wantn):
            miss.append((kw, gotn, wantn))
    ok = not miss
    print(f"  {'✅' if ok else '❌'} lọc trạng thái + tìm theo số HĐ MISA / PO / chứng từ "
          f"({len(cases)} ca){'' if ok else ' — sai: ' + str(miss)}")
    bad += not ok

    try:
        ml.get_ledger(status="bịa")
        ok, msg = False, "(không chặn)"
    except Exception as e:
        msg = str(e)
        ok = "Trạng thái không hợp lệ" in msg
    print(f"  {'✅' if ok else '❌'} trạng thái lạ -> CHẶN kèm thông báo đọc được ({msg[:44]!r})")
    bad += not ok

    ok = sum(v["count"] for v in d["by_status"].values()) == t["count"]
    print(f"  {'✅' if ok else '❌'} bốn nhóm trạng thái cộng lại = tổng số tờ — không tờ nào rơi "
          f"ra ngoài cả bốn nhóm")
    bad += not ok

    # ── 5. CÙNG mệnh đề với `mt_debt` ───────────────────────────────────
    #
    # Sổ này là cùng tập hóa đơn của màn công nợ, chỉ bỏ điều kiện "còn nợ" và
    # đổi phạm vi ngày. Lệch một mệnh đề là sổ và màn công nợ nói về hai tập
    # khác nhau, và kế toán sẽ đem hai con số đi đối chiếu.
    print("-" * 82)
    src = rc.code_only(os.path.join(rc.REPO, "ketoan/api/mt_ledger.py"))
    dsrc = rc.code_only(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"))
    for token, why in (
            ("_debt_joins", "cùng bảng tạm tiền đã trả + hàng trả lại"),
            ("opening_open_clause", "cùng luật tất toán số dư đầu kỳ"),
            ("_mt_clause", "cùng quy tắc 'khách nào là MT'"),
            ("chain_customers", "cùng quy tắc 'khách nào thuộc chuỗi nào'"),
            ("einvoice_issued_expr", "cùng luật 'đã xuất HĐĐT'")):
        ok = token in src and token in dsrc or (token == "einvoice_issued_expr" and token in src)
        print(f"  {'✅' if ok else '❌'} dùng `{token}` — {why}")
        bad += not ok

    ok = "outstanding_amount" not in src
    print(f"  {'✅' if ok else '❌'} KHÔNG dùng `outstanding_amount` (kênh MT không tạo Payment "
          f"Entry nên nó luôn bằng grand_total)")
    bad += not ok

    ok = "guard_mt()" in src and "db_set" not in src and ".save(" not in src
    print(f"  {'✅' if ok else '❌'} có guard, và module CHỈ ĐỌC")
    bad += not ok

    # ── 6. CHIẾT KHẤU KHÔNG BỊ CHIA CHO TỪNG HÓA ĐƠN ────────────────────
    print("-" * 82)
    trace_src = src.split("def get_trace")[1]
    ok = "deduction_note" in src and "row_kind != %(kind)s" in trace_src
    print(f"  {'✅' if ok else '❌'} khoản trừ lấy ở tầng ĐỢT (mọi dòng KHÔNG phải thanh toán "
          f"của chính đợt đó), kèm lời nói rõ nó thuộc về đợt")
    bad += not ok

    # Không được có phép chia nào trên khoản trừ — đó là dấu hiệu bổ đầu.
    ok = not any(tok in trace_src for tok in ("/ len(", "/ n_", "* ratio", "pro_rata"))
    print(f"  {'✅' if ok else '❌'} và KHÔNG chia đều cho từng hóa đơn — không chứng từ nào nói "
          f"tờ này chịu bao nhiêu, con số bịa sẽ bị đem đi đối chiếu với chuỗi")
    bad += not ok

    ldr = src.split("def get_ledger")[1].split("\n@frappe")[0]
    ok = "chiet_khau" not in ldr and "deduction" not in ldr
    print(f"  {'✅' if ok else '❌'} dòng sổ KHÔNG có cột chiết khấu riêng — nó không tồn tại ở "
          f"tầng hóa đơn")
    bad += not ok

    # ── 7. Giao diện ────────────────────────────────────────────────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    ok = rc.js_calls(js, "loadTab", "loadLedger") and '"so-theo-doi"' in js
    print(f"  {'✅' if ok else '❌'} sổ là một BƯỚC trong vòng đời chuỗi và `loadTab` có xử")
    bad += not ok

    lrow = rc.js_body(js, "ledgerRow")
    for tok, label in (("r.misa_no", "số HĐ MISA"), ("r.po_no", "số PO"),
                       ("r.ship_to", "điểm giao"), ("r.returned", "hàng trả lại"),
                       ("r.net_due", "phải thu"), ("r.paid_net", "đã nhận"),
                       ("r.remaining", "còn lại"), ("r.advices", "đợt thanh toán")):
        ok = tok in lrow
        print(f"  {'✅' if ok else '❌'} dòng sổ có cột {label}")
        bad += not ok

    ok = "KHÔNG phải số dư công nợ" in js
    print(f"  {'✅' if ok else '❌'} màn hình NÓI RA 'còn lại' không phải số dư công nợ — hai con "
          f"số gần giống nhau mà khác nghĩa là chỗ dễ chép nhầm nhất")
    bad += not ok

    ok = "mtLedgerTrace" in rc.js_body(js, "openTrace") and "data-trace" in lrow
    print(f"  {'✅' if ok else '❌'} bấm một dòng mở ra ĐỜI của tờ đó")
    bad += not ok

    ok = "state.ledPage" in js and "thuộc về CẢ ĐỢT" in js or "deduction_note" in js
    print(f"  {'✅' if ok else '❌'} phân trang riêng, và màn chi tiết in lời nói rõ khoản trừ "
          f"thuộc về cả đợt")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — phải thu trừ hàng trả lại, chiết khấu ở tầng đợt không chia bừa, "
          "'chưa xuất HĐĐT' đứng trước trạng thái tiền, và sổ nói rõ nó không phải số dư")
    return 0


if __name__ == "__main__":
    sys.exit(main())
