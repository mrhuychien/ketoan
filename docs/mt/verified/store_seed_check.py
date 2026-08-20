"""Kiểm tầng DỰNG MASTER ĐIỂM SIÊU THỊ (`ketoan/api/mt_store.py`) trên dữ liệu thật.

    python3 docs/mt/verified/store_seed_check.py

Cách làm: đọc 7 file mẫu thật bằng chính tầng đọc của app, coi kết quả đó như
"các bảng kê ĐÃ NẠP trên site", rồi cho `_build_plan()` chạy trên đó. Nhờ vậy
phép kiểm này đo đúng thứ sẽ chạy thật, chứ không đo một bộ dữ liệu bịa.

Ba câu hỏi mà bộ này trả lời:

  1. Dựng ra ĐÚNG bao nhiêu điểm cho từng chuỗi? (208 điểm trên 7 file mẫu)
  2. Mã SINH RA từ tên có ỔN ĐỊNH không? Chạy seed lần hai phải ra đúng mã cũ —
     không thì lần nào cũng đẻ thêm một bộ điểm trùng.
  3. Các lá chắn có bật đúng lúc không? Điểm nhiều khách -> để trống. Địa chỉ
     trùng tên -> không nối. Địa chỉ của pháp nhân khác -> không nối.

Chạy KHÔNG cần bench — dùng chung bộ stub frappe của `regression_check`, có bổ
sung `frappe.db.sql` lập trình được.
"""

import base64
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

SAMPLES = [
    ("wincommerce", "WinCommerce", "Chi tiết thanh toán Winmart.xlsx", "KH-WIN"),
    ("central_retail", "Central Retail", "Chi tiết thanh toán BigC.xlsx", "KH-CR"),
    ("lotte", "LOTTE", "Chi tiết thanh toán Lotte.xls", "KH-LOTTE"),
    ("emart", "Emart", "Chi tiết thanh toán Emart.xls", "KH-EMART"),
    ("coop", "Saigon Co.op", "Chi tiết thanh toán Coopmart.xlsx", "KH-COOP"),
    ("aeon", "AEON", "chi tiet thanh to\xa0n AEON.xls", "KH-AEON"),
    ("fuji", "Fuji", "CHI TIẾT THANH TOÁN FUJI.Xls", "KH-FUJI"),
]

# Số điểm ĐÚNG cho từng chuỗi, đo trên 7 file mẫu.
EXPECT_PER_CHAIN = {
    "LOTTE": 17,
    "Saigon Co.op": 120,
    "Central Retail": 59,     # không có mã -> mã SINH RA từ tên
    "AEON": 6,
    "Fuji": 6,                # 'mã kho nhập'
    # WinCommerce, Emart: bảng kê không có cột điểm nào -> không dựng điểm nào
}

# Địa chỉ giả lập trên site để đo phép nối theo cụm trong ngoặc CUỐI.
FAKE_ADDRESSES = [
    # khớp đúng một ứng viên, đúng khách -> PHẢI nối
    ("ADDR-BACGIANG", "Central Retail VN - Kho (BAC GIANG)", "KH-CR"),
    # trùng tên hai địa chỉ -> KHÔNG được nối
    ("ADDR-ANLAC-1", "CR chi nhanh 1 (AN LAC)", "KH-CR"),
    ("ADDR-ANLAC-2", "CR chi nhanh 2 (AN LAC)", "KH-CR"),
    # địa chỉ của PHÁP NHÂN KHÁC -> KHÔNG được nối
    ("ADDR-BALIEU", "Cty khac (BAC LIEU)", "KH-NGUOI-KHAC"),
    # ngoặc ở GIỮA, cụm định danh ở ngoặc CUỐI -> vẫn phải lấy đúng cụm cuối
    ("ADDR-BENTRE", "Cty CP ABC (chi nhanh) - Kho (BEN TRE)", "KH-CR"),
    # không có ngoặc -> phải bỏ qua, không lấy cả tên làm tên điểm
    ("ADDR-KHONGNGOAC", "Kho tong khong ngoac", "KH-CR"),
]


def _load_advice_rows():
    """Đọc 7 file mẫu -> [(chain, store_code, store_name, customer, n)].

    Đúng hình dạng mà `_advice_stores()` trả về khi truy vấn site thật.
    """
    import importlib

    ma = importlib.import_module("ketoan.api.mt_advice")
    agg = collections.Counter()
    for key, chain, fname, customer in SAMPLES:
        path = os.path.join(rc.SAMPLES, fname)
        if not os.path.exists(path):
            raise SystemExit("THIẾU FILE MẪU: " + fname)
        raw = open(path, "rb").read()
        res = ma.read_payment_advice(base64.b64encode(raw).decode(), key)
        for r in res["rows"]:
            agg[(chain, r.get("store_code") or "", r.get("store_name") or "",
                 customer)] += 1
    return [{"chain": c, "store_code": sc, "store_name": sn, "customer": cus, "n": n}
            for (c, sc, sn, cus), n in agg.items()]


class _D(dict):
    """`frappe._dict`: dict truy cập được bằng thuộc tính.

    Bắt buộc giả lập đúng kiểu này — `frappe.db.sql(as_dict=True)` thật trả về
    nó, và mã trong app đọc `r.store_code`. Trả dict trần là phép kiểm nổ ở chỗ
    mà bản chạy thật hoàn toàn bình thường.
    """

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _install_db_stub(advice_rows, addresses, existing=()):
    """Cắm `frappe.db.sql` và `frappe.get_all` trả dữ liệu giả lập.

    Nhận diện truy vấn theo NHÃN BẢNG trong câu SQL, không theo thứ tự gọi: thứ
    tự gọi đổi khi refactor thì phép kiểm phải vẫn đúng, chứ không im lặng trả
    nhầm bộ dữ liệu cho nhầm truy vấn.
    """
    import frappe

    def _sql(query, values=None, **kw):
        q = " ".join(str(query).split())
        if "tabMT Payment Advice Line" in q:
            return [_D(r) for r in advice_rows]
        if "tabAddress" in q:
            return [_D(address=a, title=t, customer=c) for a, t, c in addresses]
        raise AssertionError("Truy vấn không được giả lập: " + q[:120])

    frappe.db.sql = _sql
    frappe.get_all = lambda dt, **kw: ([_D(e) for e in existing]
                                       if dt == "MT Store" else [])


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    advice_rows = _load_advice_rows()
    _install_db_stub(advice_rows, FAKE_ADDRESSES)
    ms = importlib.import_module("ketoan.api.mt_store")

    print("=" * 78)
    print("KIỂM TẦNG DỰNG MASTER ĐIỂM SIÊU THỊ")
    print("=" * 78)

    bad = 0
    plan, warnings = ms._build_plan("HGC")

    # ── 1. Số điểm theo từng chuỗi ─────────────────────────────────────────
    per = collections.Counter(p["chain"] for p in plan)
    for chain in sorted(set(per) | set(EXPECT_PER_CHAIN)):
        want = EXPECT_PER_CHAIN.get(chain, 0)
        got = per.get(chain, 0)
        mark = "✅" if got == want else "❌"
        synth = sum(1 for p in plan if p["chain"] == chain and p["code_synthesized"])
        noname = sum(1 for p in plan if p["chain"] == chain
                     and p["store_name"] == p["store_code"])
        print(f"  {mark} {chain:16} {got:4} điểm (mong {want})"
              f"{'  · mã SINH RA từ tên' if synth else ''}"
              f"{'  · chưa có tên thật' if noname else ''}")
        bad += got != want
    print(f"     tổng {len(plan)} điểm · {len(warnings)} cảnh báo")

    # ── 2. Co.op: tên KHÔNG có mã phải bị bỏ, kèm cảnh báo ─────────────────
    print("-" * 78)
    coop_warn = [w for w in warnings if w.startswith("Saigon Co.op")]
    ok = len(coop_warn) == 1 and "pháp nhân mẹ" in coop_warn[0]
    print(f"  {'✅' if ok else '❌'} Co.op: dòng pháp nhân mẹ (tên không có mã) bị bỏ + cảnh báo")
    if not ok:
        print(f"       └─ cảnh báo Co.op thực tế: {coop_warn}")
    bad += not ok

    # Và nó KHÔNG được lọt vào master dưới dạng mã sinh ra.
    leaked = [p for p in plan if p["chain"] == "Saigon Co.op" and p["code_synthesized"]]
    print(f"  {'✅' if not leaked else '❌'} Co.op: không điểm nào có mã sinh ra "
          f"(chuỗi này CÓ mã thật)")
    bad += bool(leaked)

    # ── 3. Mã sinh ra phải ỔN ĐỊNH giữa hai lần chạy ───────────────────────
    plan2, _w2 = ms._build_plan("HGC")
    same = ([(p["chain"], p["store_code"]) for p in plan]
            == [(p["chain"], p["store_code"]) for p in plan2])
    hash_same = ms._plan_hash(plan) == ms._plan_hash(plan2)
    print(f"  {'✅' if same and hash_same else '❌'} mã sinh ra ỔN ĐỊNH: "
          f"chạy lần hai ra đúng bộ mã cũ, vân tay không đổi")
    bad += not (same and hash_same)

    # ── 4. Nối địa chỉ theo cụm trong ngoặc CUỐI ───────────────────────────
    print("-" * 78)
    by_name = {(p["chain"], p["store_name"]): p for p in plan}

    def _addr(name):
        p = by_name.get(("Central Retail", name))
        return (p or {}).get("address") or ""

    cases = [
        ("BAC GIANG", "ADDR-BACGIANG", "khớp đúng một địa chỉ, đúng khách -> NỐI"),
        ("AN LAC", "", "hai địa chỉ trùng tên -> KHÔNG nối"),
        ("BAC LIEU", "", "địa chỉ của pháp nhân khác -> KHÔNG nối"),
    ]
    for store, want, what in cases:
        got = _addr(store)
        mark = "✅" if got == want else "❌"
        print(f"  {mark} {what}")
        if got != want:
            print(f"       └─ điểm '{store}': mong address={want!r}, thực {got!r}")
        bad += got != want

    # Ngoặc CUỐI, không phải ngoặc đầu: 'Cty CP ABC (chi nhanh) - Kho (BEN TRE)'
    inner = ms.name_in_last_parens("Cty CP ABC (chi nhanh) - Kho (BEN TRE)")
    ok = inner == "BEN TRE"
    print(f"  {'✅' if ok else '❌'} lấy cụm trong ngoặc CUỐI, không phải ngoặc đầu "
          f"(được {inner!r})")
    bad += not ok

    ok = ms.name_in_last_parens("Kho tong khong ngoac") is None
    print(f"  {'✅' if ok else '❌'} không có ngoặc -> None (không lấy cả tên làm tên điểm)")
    bad += not ok

    # ── 5. Sinh mã từ tên ──────────────────────────────────────────────────
    print("-" * 78)
    for src, want in (("AN LAC", "AN_LAC"),
                      ("Gò Vấp (khu B)", "GO_VAP_KHU_B"),
                      ("Đà Nẵng", "DA_NANG"),
                      ("  ...  ", "")):
        got = ms.code_from_name(src)
        mark = "✅" if got == want else "❌"
        print(f"  {mark} code_from_name({src!r}) = {got!r}")
        bad += got != want

    # ── 6. Mã điểm giữ NGUYÊN số 0 ở đầu ───────────────────────────────────
    zero = [p for p in plan if p["store_code"].startswith("0")]
    ok = any(p["chain"] == "LOTTE" for p in zero) and any(p["chain"] == "Fuji" for p in zero)
    print(f"  {'✅' if ok else '❌'} mã giữ NGUYÊN số 0 ở đầu "
          f"({len(zero)} điểm, ví dụ {sorted(p['store_code'] for p in zero)[:5]})")
    bad += not ok

    # ── 7. Chạy lại khi master ĐÃ CÓ -> không tạo trùng ────────────────────
    print("-" * 78)
    existing = [{"name": "MT-STORE-%05d" % (i + 1), "chain": p["chain"],
                 "store_code": p["store_code"], "store_name": p["store_name"],
                 "customer": p["customer"], "address": p["address"], "active": 1}
                for i, p in enumerate(plan)]
    _install_db_stub(advice_rows, FAKE_ADDRESSES, existing)
    plan3, _w3 = ms._build_plan("HGC")
    n_new = sum(1 for p in plan3 if p["status"] == ms.STATUS_NEW)
    n_same = sum(1 for p in plan3 if p["status"] == ms.STATUS_EXISTS)
    ok = n_new == 0 and n_same == len(plan)
    print(f"  {'✅' if ok else '❌'} chạy lần hai khi master đã đầy: "
          f"{n_new} tạo mới · {n_same} bỏ qua (mong 0 / {len(plan)})")
    bad += not ok

    # Master bị sửa tay -> phải báo LỆCH, tuyệt đối không đè.
    edited = [dict(e) for e in existing]
    edited[0]["customer"] = "KH-KE-TOAN-SUA-TAY"
    _install_db_stub(advice_rows, FAKE_ADDRESSES, edited)
    plan4, _w4 = ms._build_plan("HGC")
    n_diff = sum(1 for p in plan4 if p["status"] == ms.STATUS_DIFF)
    ok = n_diff == 1 and sum(1 for p in plan4 if p["status"] == ms.STATUS_NEW) == 0
    print(f"  {'✅' if ok else '❌'} kế toán sửa tay -> báo LỆCH ({n_diff} điểm), "
          f"seed KHÔNG đè")
    bad += not ok

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — tầng dựng master chạy đúng trên dữ liệu thật"
          if not bad else f"HỎNG {bad} mục")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
