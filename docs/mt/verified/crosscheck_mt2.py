"""Đối chiếu CHÉO: bản đọc chạy thật vs bản tham chiếu độc lập (AEON, Fuji, Mega).

    python3 docs/mt/verified/crosscheck_mt2.py

`regression_check.py` so kết quả với số ĐÃ CHỐT — nhưng số đã chốt do chính em
đọc ra, nên nếu lần đọc đầu tiên đã sai thì nó chốt luôn cái sai.

Bộ này so hai bản đọc VIẾT KHÁC CÁCH trên cùng một file:
  · `ketoan/api/mt_advice.py`  — dò header theo NHÃN, quét mọi sheet, chạy thật
  · `docs/mt/verified/{aeon,fuji,mega}.py` — chỉ số dòng/cột CỨNG, đọc thẳng file mẫu

Hai cách đọc khác hẳn nhau mà ra cùng một số tới từng đồng VÀ từng dòng thì con
số đó đáng tin. Giống nhau vì cùng một lỗi thì gần như không thể — muốn trùng
lỗi, cả hai phải cùng nhầm cột theo đúng một kiểu.

So tới cấp DÒNG chứ không chỉ cấp tổng: hai lỗi ngược chiều triệt tiêu nhau ở
tổng là chuyện có thật (một dòng xếp nhầm loại + một dòng khác xếp nhầm ngược lại).
"""

import base64
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

CASES = [
    ("aeon", "chi tiet thanh to\xa0n AEON.xls", "aeon"),
    ("fuji", "CHI TIẾT THANH TOÁN FUJI.Xls", "fuji"),
    ("mega", "cttt_mega.xls", "mega_market"),
]


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    ma = importlib.import_module("ketoan.api.mt_advice")

    print("=" * 78)
    print("ĐỐI CHIẾU CHÉO — bản chạy thật vs bản tham chiếu độc lập")
    print("=" * 78)

    bad = 0
    for mod_name, fname, chain in CASES:
        ref = importlib.import_module(mod_name)
        path = os.path.join(rc.SAMPLES, fname)
        if not os.path.exists(path):
            print(f"  ⚠ THIẾU FILE MẪU: {fname}")
            bad += 1
            continue

        raw = open(path, "rb").read()
        prod = ma.read_payment_advice(base64.b64encode(raw).decode(), chain)
        ref_rows = ref.read_rows(path)

        errs = []

        # 1. Tổng theo từng loại dòng.
        a = collections.defaultdict(float)
        for r in prod["rows"]:
            a[r["row_kind"]] += float(r.get("signed_amount") or 0)
        b = collections.defaultdict(float)
        for r in ref_rows:
            b[r["kind"]] += float(r["amount"])
        for k in sorted(set(a) | set(b)):
            if round(a[k]) != round(b[k]):
                errs.append(f"tổng {k}: chạy-thật {round(a[k]):,} vs tham-chiếu {round(b[k]):,}")

        # 2. Số dòng theo từng loại.
        na = collections.Counter(r["row_kind"] for r in prod["rows"])
        nb = collections.Counter(r["kind"] for r in ref_rows)
        for k in sorted(set(na) | set(nb)):
            if na[k] != nb[k]:
                errs.append(f"số dòng {k}: chạy-thật {na[k]} vs tham-chiếu {nb[k]}")

        # 3. TỚI CẤP DÒNG — khóa (dòng Excel, loại, số tiền làm tròn). Hai lỗi
        #    ngược chiều triệt tiêu nhau ở tổng vẫn lộ ra ở đây.
        ka = collections.Counter(
            (r.get("source_row"), r["row_kind"], round(float(r.get("signed_amount") or 0)))
            for r in prod["rows"])
        kb = collections.Counter(
            (r["excel_row"], r["kind"], round(float(r["amount"]))) for r in ref_rows)
        only_a = list((ka - kb).elements())
        only_b = list((kb - ka).elements())
        for x in only_a[:4]:
            errs.append(f"chỉ có ở bản chạy thật: dòng {x[0]} {x[1]} {x[2]:,}")
        for x in only_b[:4]:
            errs.append(f"chỉ có ở bản tham chiếu: dòng {x[0]} {x[1]} {x[2]:,}")
        if len(only_a) > 4 or len(only_b) > 4:
            errs.append(f"… còn {max(0, len(only_a) - 4) + max(0, len(only_b) - 4)} dòng lệch nữa")

        # 4. Số hóa đơn của các dòng thanh toán.
        ia = sorted(str(r.get("inv_no") or "") for r in prod["rows"]
                    if r["row_kind"] == "thanh_toan")
        ib = sorted(str(r.get("inv_no") or "") for r in ref_rows if r["kind"] == "thanh_toan")
        if ia != ib:
            errs.append(f"danh sách số hóa đơn lệch ({len(ia)} vs {len(ib)})")

        mark = "✅" if not errs else "❌"
        print(f"  {mark} {chain:6} {len(prod['rows']):4} dòng · "
              f"NET {round(sum(a.values())):>15,} · tham chiếu {round(sum(b.values())):>15,}")
        for e in errs:
            print(f"       └─ {e}")
        bad += bool(errs)

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — hai bản đọc độc lập trùng nhau tới từng dòng" if not bad
          else f"HỎNG {bad} chuỗi")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
