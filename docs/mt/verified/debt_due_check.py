"""Kiểm tầng CÔNG NỢ MT ĐẾN HẠN (`ketoan/api/mt_debt.py`, phần MT2-F).

    python3 docs/mt/verified/debt_due_check.py

Báo cáo này quyết định GỌI ĐIỆN ĐÒI AI. Sai kiểu nào cũng đắt, nhưng đắt theo
hai chiều ngược nhau, nên phải kiểm cả hai:

  · ĐÒI NHẦM — hóa đơn chuỗi đã trả xong mà vẫn nằm rổ nợ. Nguyên nhân duy nhất
    có thể xảy ra: lấy `si.outstanding_amount` thay vì cộng dòng bảng kê. Kênh
    MT cố ý không tạo Payment Entry nên `outstanding_amount` KHÔNG BAO GIỜ giảm.
  · KHÔNG ĐÒI — hóa đơn đã quá hạn mà bị xếp "chưa đến hạn". Nguyên nhân duy
    nhất có thể xảy ra: đoán hạn mặc định (45 ngày) cho khách chưa khai hạn.

Cộng thêm ba chỗ đã đo được là dễ sai:

  · `due_date = posting_date` của ERPNext nghĩa là CHƯA KHAI Payment Terms,
    không phải "đến hạn ngay hôm xuất hóa đơn".
  · Chuỗi ĐÒI LẠI tiền hóa đơn đã trả (Co.op, HĐ 3176) -> hóa đơn phải quay
    về rổ nợ, không được nằm mãi ở "đã thu đủ".
  · Dòng khớp 'Cần review' KHÔNG được trừ vào nợ — máy mới đoán, chưa ai chốt.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

COMPANY = "HGC"
AS_OF = "2026-08-20"


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


def _row(name, customer, chain, posting, total, paid=0.0, clawed=0.0,
         review=0.0, credit_days=None, due_date=None):
    """Một dòng ĐÚNG NHƯ SQL trả về — đã trừ sẵn tiền bảng kê ở cột remaining.

    Cột `remaining` được tính ở đây theo ĐÚNG công thức trong SQL
    (`GREATEST(total - (paid - clawed), 0)`) để phép kiểm nói về tầng Python;
    còn việc SQL có dùng đúng nguồn tiền hay không thì kiểm riêng ở mục 1.
    """
    return _D(name=name, customer=customer, customer_name=customer,
              posting_date=posting, due_date=due_date, grand_total=total,
              chain=chain, credit_days=credit_days, paid=paid,
              clawed_back=clawed, paid_review=review, last_payment_date=None,
              remaining=max(total - (paid - clawed), 0.0))


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.db.table_exists = lambda dt: True
    frappe.db.has_column = lambda dt, col: True
    frappe.db.sql = lambda *a, **k: []
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    md = importlib.import_module("ketoan.api.mt_debt")
    md._company = lambda company=None: COMPANY

    print("=" * 78)
    print("KIỂM CÔNG NỢ MT ĐẾN HẠN")
    print("=" * 78)
    bad = 0

    # ── 1. Nguồn tiền: BẢNG KÊ, không phải outstanding_amount ────────────
    # Đọc thẳng câu SQL. Đây là phép kiểm về VĂN BẢN, cố ý — nó chặn đúng
    # cái sửa nguy hiểm nhất mà dữ liệu giả không bao giờ lộ ra.
    src = open(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"), encoding="utf-8").read()
    ok = "outstanding_amount" not in src.split('"""', 2)[-1]
    print(f"  {'✅' if ok else '❌'} không nơi nào dùng `outstanding_amount` "
          f"(kênh MT không tạo Payment Entry nên nó luôn = grand_total)")
    bad += not ok

    ok = "_debt_joins" in src
    print(f"  {'✅' if ok else '❌'} dùng chung `_debt_joins()` với màn hình Tổng quan "
          f"-> hai màn hình không thể nói hai số khác nhau")
    bad += not ok

    # ── 1b. HÀNG TRẢ LẠI phải trừ vào chính hóa đơn gốc ──────────────────
    #
    # Quy trình thật: giao hàng -> hàng móp/lỗi -> điều chỉnh hóa đơn MISA ->
    # trả lại trên ERPNext. Một lần bán thành HAI chứng từ ERPNext. Trước khi có
    # `rt`, `return_against` không được dùng ở đâu trong kênh MT: hóa đơn 100tr
    # bị trả 20tr vẫn đòi đủ 100tr mãi mãi.
    print("-" * 78)
    mtsrc = open(os.path.join(rc.REPO, "ketoan/api/mt.py"), encoding="utf-8").read()

    ok = mtsrc.count("def _returns_join") == 1 and mtsrc.count("return_against") >= 1
    print(f"  {'✅' if ok else '❌'} có bảng tạm `rt` cộng phiếu trả hàng theo "
          f"`return_against`")
    bad += not ok

    # Cắt tới `def` cấp 0 kế tiếp — docstring của hàm này dài, cắt theo số ký tự
    # là phép kiểm nhìn hụt thân hàm rồi báo hỏng vì lý do sai.
    body = re.split(r"\n(?=\S)", mtsrc.split("def _returns_join")[1])[0]
    ok = "r.docstatus = 1" in body and "IFNULL(r.return_against, '') != ''" in body \
        and "r.is_return = 1" in body
    print(f"  {'✅' if ok else '❌'} chỉ đếm phiếu trả hàng ĐÃ GHI SỔ và CÓ khai trả cho "
          f"hóa đơn nào — phiếu đứng rời không tự trừ vào đâu")
    bad += not ok

    # Mọi công thức nợ phải đi qua `_NET_DUE`, không ai được dùng grand_total trần.
    # Bắt đúng ca HỎNG: `grand_total` đứng trong một phép tính NỢ mà KHÔNG có
    # `rt.returned` ngay sau. Bắt trần `grand_total` là báo nhầm cả công thức đã
    # đúng — phép kiểm sai kiểu đó còn tệ hơn không có, vì lần sau ai cũng bỏ qua.
    leaks = []
    # Không dùng lookahead: `\s*` lùi được về rỗng nên phép phủ định trượt qua
    # đúng công thức đã đúng. Soi thẳng 60 ký tự kế tiếp cho chắc.
    for f in ("ketoan/api/mt.py", "ketoan/api/mt_debt.py",
              "ketoan/api/mt_opening_store.py"):
        t = open(os.path.join(rc.REPO, f), encoding="utf-8").read()
        for m in re.finditer(r"GREATEST\(ABS\(si\.grand_total\) -", t):
            if "rt.returned" not in t[m.end():m.end() + 60]:
                leaks.append("%s: cột còn nợ" % f)
        for pat, label in ((r"< ABS\(si\.grand_total\) - %\(tol\)s", "điều kiện rổ nợ"),
                           (r"LEAST\(\{?_NET_PAID\}?, ABS\(si\.grand_total\)\)", "cột đã thu")):
            if re.search(pat, t):
                leaks.append("%s: %s" % (f, label))
    ok = not leaks
    print(f"  {'✅' if ok else '❌'} không công thức nợ nào còn dùng `grand_total` trần"
          + ("" if ok else " — " + "; ".join(leaks)))
    bad += not ok

    ok = "_NET_DUE" in src and "rt.returned" in src
    print(f"  {'✅' if ok else '❌'} màn hình Công nợ đến hạn cũng trừ hàng trả lại và trả "
          f"về cột `returned` để kế toán nhìn thấy phần đã trả")
    bad += not ok

    # ── 2. Hóa đơn đã trả đủ KHÔNG được vào rổ nợ ────────────────────────
    print("-" * 78)
    rows = md._enrich([
        _row("SI-PAID", "LOTTE HN", "LOTTE", "2026-05-01", 10_000_000,
             paid=10_000_000, credit_days=45),
    ], AS_OF)
    # SQL đã loại hóa đơn trả đủ; ở tầng Python phải thấy remaining = 0.
    ok = rows[0]["remaining"] == 0
    print(f"  {'✅' if ok else '❌'} hóa đơn chuỗi đã trả đủ -> còn nợ {rows[0]['remaining']:,.0f}đ")
    bad += not ok

    # Chuỗi ĐÒI LẠI tiền hóa đơn đã trả -> phải quay về rổ nợ.
    rows = md._enrich([
        _row("SI-CLAW", "Co.op", "Saigon Co.op", "2026-05-01", 10_000_000,
             paid=10_000_000, clawed=3_121_200, credit_days=45),
    ], AS_OF)
    ok = round(rows[0]["remaining"]) == 3_121_200
    print(f"  {'✅' if ok else '❌'} chuỗi đòi lại 3.121.200đ của HĐ đã trả -> "
          f"quay về nợ {rows[0]['remaining']:,.0f}đ")
    bad += not ok

    # ── 3. Hạn thanh toán: khai -> hóa đơn -> CHƯA KHAI (không đoán) ─────
    print("-" * 78)
    cases = [
        # (mô tả, credit_days, due_date, hạn mong đợi, nguồn)
        ("khai 45 ngày trên Customer", 45, None, "2026-06-15", md.DUE_FROM_TERM),
        ("không khai, hóa đơn có due_date", None, "2026-06-30", "2026-06-30", md.DUE_FROM_INVOICE),
        ("không khai, due_date = ngày hóa đơn", None, "2026-05-01", None, md.DUE_NONE),
        ("không khai gì cả", None, None, None, md.DUE_NONE),
    ]
    for label, days, due, want, want_src in cases:
        r = md._enrich([_row("SI-X", "K", "LOTTE", "2026-05-01", 1_000_000,
                             credit_days=days, due_date=due)], AS_OF)[0]
        ok = r["due_date"] == want and r["due_source"] == want_src
        print(f"  {'✅' if ok else '❌'} {label} -> hạn {r['due_date']} ({r['due_source']})")
        bad += not ok

    # Cái đắt nhất: khách chưa khai hạn KHÔNG được mặc định 45 ngày.
    r = md._enrich([_row("SI-NOTERM", "K", "Emart", "2026-05-01", 9_000_000)], AS_OF)[0]
    ok = r["bucket"] == md.BUCKET_UNKNOWN and r["days_overdue"] is None
    print(f"  {'✅' if ok else '❌'} chưa khai hạn -> rổ riêng {r['bucket']!r}, "
          f"KHÔNG bị đoán thành 'chưa đến hạn'")
    bad += not ok

    # Hai nơi khai lệch nhau -> phải giương cờ, không tự chọn rồi giấu.
    r = md._enrich([_row("SI-CONF", "K", "Central Retail", "2026-05-01", 1_000_000,
                         credit_days=30, due_date="2026-06-10")], AS_OF)[0]
    ok = r["due_conflict"] and r["due_date"] == "2026-05-31"
    print(f"  {'✅' if ok else '❌'} Customer khai 30 ngày mà hóa đơn ghi 2026-06-10 -> "
          f"lấy {r['due_date']} và GIƯƠNG CỜ lệch")
    bad += not ok

    # ── 4. Rổ tuổi nợ: đúng mốc, không hụt không chồng ───────────────────
    print("-" * 78)
    want = [(-1, "chua_den_han"), (0, "chua_den_han"), (1, "qua_han_1_15"),
            (15, "qua_han_1_15"), (16, "qua_han_16_30"), (30, "qua_han_16_30"),
            (31, "qua_han_31_60"), (60, "qua_han_31_60"), (61, "qua_han_60"),
            (999, "qua_han_60"), (None, md.BUCKET_UNKNOWN)]
    miss = [(d, md._bucket_of(d), b) for d, b in want if md._bucket_of(d) != b]
    ok = not miss
    print(f"  {'✅' if ok else '❌'} 11 mốc tuổi nợ vào đúng rổ (kể cả biên 0/1/15/16/60/61)")
    for d, got, b in miss:
        print(f"       └─ {d} ngày -> {got}, đáng lẽ {b}")
    bad += not ok

    # ── 5. Cộng tổng: tiền không được nhân đôi hay rơi mất ───────────────
    print("-" * 78)
    rows = md._enrich([
        _row("A", "Win", "WinCommerce", "2026-05-01", 100_000_000, credit_days=60),
        _row("B", "Win", "WinCommerce", "2026-08-01", 50_000_000, credit_days=60),
        _row("C", "Lot", "LOTTE", "2026-06-01", 30_000_000, paid=10_000_000, credit_days=45),
        _row("D", "Ema", "Emart", "2026-03-01", 7_000_000),          # chưa khai hạn
    ], AS_OF)
    s = md._rollup(rows)

    ok = round(s["total"]) == 177_000_000
    print(f"  {'✅' if ok else '❌'} tổng còn nợ {s['total']:,.0f}đ "
          f"(100tr + 50tr + 20tr + 7tr)")
    bad += not ok

    ok = round(sum(b["amount"] for b in s["buckets"])) == round(s["total"])
    print(f"  {'✅' if ok else '❌'} cộng các rổ = tổng -> không hóa đơn nào rơi ra ngoài")
    bad += not ok

    ok = sum(b["count"] for b in s["buckets"]) == len(rows)
    print(f"  {'✅' if ok else '❌'} đếm các rổ = {len(rows)} hóa đơn -> không đếm trùng")
    bad += not ok

    # Quá hạn KHÔNG được gồm hóa đơn chưa khai hạn: chưa biết hạn thì chưa
    # kết luận được là trễ.
    ok = round(s["overdue"]) == 120_000_000 and s["overdue_count"] == 2
    print(f"  {'✅' if ok else '❌'} quá hạn {s['overdue']:,.0f}đ / {s['overdue_count']} HĐ "
          f"— KHÔNG gộp 7tr chưa khai hạn vào")
    bad += not ok

    ok = s["unknown_term_count"] == 1 and round(s["unknown_term_amount"]) == 7_000_000
    print(f"  {'✅' if ok else '❌'} 7.000.000đ chưa khai hạn được ĐẾM RIÊNG và hiện ra, "
          f"không biến mất im lặng")
    bad += not ok

    ok = round(sum(c["amount"] for c in s["chains"])) == round(s["total"])
    print(f"  {'✅' if ok else '❌'} cộng theo chuỗi = tổng ({len(s['chains'])} chuỗi)")
    bad += not ok

    # ── 6. Thứ tự: nợ già nhất lên trước, chưa khai hạn xuống cuối ───────
    print("-" * 78)
    md._fetch = lambda company, as_of, chain=None, customer=None, search=None: [
        _row("A", "Win", "WinCommerce", "2026-05-01", 100_000_000, credit_days=60),
        _row("B", "Win", "WinCommerce", "2026-08-01", 50_000_000, credit_days=60),
        _row("C", "Lot", "LOTTE", "2026-06-01", 30_000_000, paid=10_000_000, credit_days=45),
        _row("D", "Ema", "Emart", "2026-03-01", 7_000_000),
    ]
    res = md.get_due_invoices(as_of=AS_OF)
    order = [r["name"] for r in res["rows"]]
    ok = order == ["A", "C", "B", "D"]
    print(f"  {'✅' if ok else '❌'} thứ tự đòi nợ: {order} (già nhất trước, chưa khai hạn cuối)")
    bad += not ok

    # A: 01/05 + 60 ngày -> hạn 30/06 -> trễ 51 ngày. C: 01/06 + 45 -> 16/07 -> trễ 35.
    res = md.get_due_invoices(as_of=AS_OF, bucket="qua_han_31_60")
    ok = [r["name"] for r in res["rows"]] == ["A", "C"] and round(res["amount"]) == 120_000_000
    print(f"  {'✅' if ok else '❌'} lọc rổ 'quá hạn 31–60 ngày' -> "
          f"{[r['name'] for r in res['rows']]}, {res['amount']:,.0f}đ "
          f"(bằng đúng tổng quá hạn ở mục 5)")
    bad += not ok

    try:
        md.get_due_invoices(as_of=AS_OF, bucket="rổ-bịa")
        print("  ❌ rổ không hợp lệ -> KHÔNG dừng")
        bad += 1
    except Exception as e:  # noqa: BLE001
        ok = "không hợp lệ" in str(e)
        print(f"  {'✅' if ok else '❌'} rổ tuổi nợ bịa -> dừng, không trả bảng rỗng đánh lừa")
        bad += not ok

    # ── 7. Dòng 'Cần review' KHÔNG được trừ vào nợ ───────────────────────
    print("-" * 78)
    rows = md._enrich([
        _row("SI-REV", "Emart", "Emart", "2026-05-01", 8_000_000,
             review=8_000_000, credit_days=30),
    ], AS_OF)
    ok = round(rows[0]["remaining"]) == 8_000_000
    print(f"  {'✅' if ok else '❌'} dòng khớp 'Cần review' 8tr KHÔNG trừ vào nợ "
          f"(còn {rows[0]['remaining']:,.0f}đ) — máy đoán, chưa ai chốt")
    bad += not ok

    s = md._rollup(rows)
    ok = round(s["pending_review"]) == 8_000_000
    print(f"  {'✅' if ok else '❌'} nhưng vẫn hiện {s['pending_review']:,.0f}đ 'chờ chốt tay' "
          f"để người biết mà xử")
    bad += not ok

    # ── 8. Khai hạn: chặn số vô lý, phân biệt 'xóa khai' với 'hạn 0' ─────
    print("-" * 78)
    saved = {}
    frappe.db.exists = lambda dt, n: True
    frappe.db.commit = lambda *a, **k: None
    frappe.db.set_value = lambda dt, n, f, v, **k: saved.__setitem__(n, v)

    r = md.save_credit_days("KH-WIN", 60)
    ok = saved.get("KH-WIN") == 60 and "60 ngày" in r["message"]
    print(f"  {'✅' if ok else '❌'} khai 60 ngày cho Win -> lưu {saved.get('KH-WIN')}")
    bad += not ok

    r = md.save_credit_days("KH-WIN", 0)
    ok = saved.get("KH-WIN") == 0 and "chưa khai hạn" in r["message"]
    print(f"  {'✅' if ok else '❌'} khai 0 -> XÓA khai báo, nói rõ HĐ quay về rổ chưa khai "
          f"(không phải 'hạn 0 ngày')")
    bad += not ok

    for v, why in ((-5, "âm"), (4000, "vượt quá 365")):
        try:
            md.save_credit_days("KH-WIN", v)
            print(f"  ❌ hạn {v} -> KHÔNG dừng")
            bad += 1
        except Exception as e:  # noqa: BLE001
            ok = why in str(e)
            print(f"  {'✅' if ok else '❌'} hạn {v} ngày -> dừng ({why})")
            bad += not ok

    print("=" * 78)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — nợ tính từ bảng kê, hạn không bao giờ bị đoán, "
          "không đòi nhầm không bỏ sót")
    return 0


if __name__ == "__main__":
    sys.exit(main())
