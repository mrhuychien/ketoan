"""ĐO cột `HĐ thay thế` (`inv_replaced_by`) trên BẢY file công nợ mẫu thật.

⚠ ĐÂY LÀ BỘ ĐO, KHÔNG PHẢI BỘ KIỂM. Nó chỉ IN SỐ LIỆU và LUÔN trả 0 — không
khẳng định điều gì, không hỏng được. Vì thế tên file cố ý KHÔNG kết thúc bằng
`_check.py`: để nó không lọt vào vòng chạy toàn bộ và tạo ra cảm giác an toàn
giả ("20/20 ĐẠT" trong khi một trong số đó không kiểm gì cả).

Phần KHẲNG ĐỊNH nằm ở `opening_store_check.py`, mục 2f.

Vì sao có bộ đo này: `mt_opening._find_id_cols` ĐÃ dò ra cột "hóa đơn thay thế"
nhưng không tầng nào dùng, còn `mt_opening_store._resolve_row` thì khớp Sales
Invoice CHỈ bằng `inv_no`. Kế toán yêu cầu: dòng nào có số thay thế thì phải
khớp theo SỐ THAY THẾ. Trước khi sửa một dòng code nào, phải đo được:

  1. Cột đó dò ra từ NHÃN THẬT nào, ở dòng nào, cột nào — từng chuỗi.
  2. Giá trị trong cột có khuôn gì (đệm 0? ký hiệu? luôn là số? nhiều số?).
  3. Các dòng CÒN NỢ mang số thay thế — in đủ để kế toán soi tay.
  4. CÂU HỎI QUAN TRỌNG NHẤT: có dòng nào mà `inv_replaced_by` trùng `inv_no`
     của một dòng KHÁC trong cùng file không? Nếu có, khớp theo số thay thế sẽ
     làm HAI dòng cùng trỏ về MỘT Sales Invoice.
  5. Dòng có số thay thế thì `remaining` bằng 0 hay khác 0?

    python3 docs/mt/verified/replaced_inv_check.py

Chạy KHÔNG cần bench: dùng lại `_stub_frappe` của `regression_check.py` (một quy
tắc một chỗ — không chép lại bộ giả frappe). CHỈ ĐỌC FILE, không chạm database.
"""

import base64
import collections
import datetime
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CONGNO = os.path.join(REPO, "docs", "mt", "samples", "congno")

# Đo trên đúng bảy file đang dùng. Tên file -> chuỗi (tham số `chain` chỉ để
# `read_opening` khỏi throw khi chữ ký cột không đủ; nó KHÔNG đổi cách đọc cột).
FILES = [
    ("congno_aeon.xlsx", "AEON"),
    ("congno_central_retail.xlsx", "Central Retail"),
    ("congno_emart.xlsx", "Emart"),
    ("congno_lotte.xlsx", "LOTTE"),
    ("congno_mega_market.xlsx", "Mega Market"),
    ("congno_saigon_coop.xlsx", "Saigon Co.op"),
    ("congno_wincommerce.xlsx", "WinCommerce"),
]

MONEY_EPS = 1.0


def _load():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import regression_check as rc

    rc._stub_frappe()
    sys.path.insert(0, REPO)
    import importlib

    return (importlib.import_module("ketoan.api.mt_opening"),
            importlib.import_module("ketoan.api.mt_advice"),
            importlib.import_module(
                "ketoan.misa_integration.doctype.misa_invoice_snapshot"
                ".misa_invoice_snapshot"))


def _label_trace(mo, ma, grid, money_row):
    """Lặp lại ĐÚNG vòng quét của `_find_id_cols` để nói ra nhãn THẬT đã trúng.

    Không đọc mò ô header: đi cùng thứ tự dòng (money_row-1, -2, +0, +1, +2) và
    cùng luật "nhãn tìm được TRƯỚC thắng", nếu không thì báo cáo sẽ nói một nhãn
    mà parser thật lại lấy nhãn khác.
    """
    taken = {}
    all_hits = []
    for rr in (money_row - 1, money_row - 2, money_row, money_row + 1, money_row + 2):
        if rr < 1 or rr > len(grid):
            continue
        for c, txt in enumerate(ma._row_texts(grid[rr - 1]), start=1):
            k = mo._norm(txt)
            if k not in mo.ID_LABELS:
                continue
            key = mo.ID_LABELS[k]
            all_hits.append((key, rr, c, txt, k))
            if key not in taken:
                taken[key] = (rr, c, txt, k)
    return taken, all_hits


def _shape(v):
    """Khuôn của một giá trị số thay thế -> nhãn ngắn để đếm."""
    s = str(v)
    if re.fullmatch(r"\d+", s):
        return "chỉ chữ số, có đệm 0 đầu" if s != s.lstrip("0") else "chỉ chữ số"
    if re.fullmatch(r"[\d\s,;/+.\-]+", s) and re.search(r"\d", s):
        return "nhiều số / có dấu phân cách"
    return "có chữ hoặc ký tự khác"


NUM_RE = re.compile(r"\d+")


def main():
    mo, ma, snap = _load()
    norm_inv_no = snap.norm_inv_no

    per_chain = []
    print("=" * 100)
    print("ĐO CỘT `HĐ THAY THẾ` (inv_replaced_by) TRÊN 7 FILE CÔNG NỢ THẬT")
    print("=" * 100)

    # ── §1 Nhãn thật của cột, từng chuỗi ────────────────────────────────────
    print()
    print("§1  CỘT `inv_replaced_by` DÒ RA TỪ NHÃN NÀO — ĐỌC Ô HEADER THẬT")
    print("-" * 100)
    for fname, chain in FILES:
        path = os.path.join(CONGNO, fname)
        raw = open(path, "rb").read()
        b64 = base64.b64encode(raw).decode()
        res = mo.read_opening(b64, chain=chain)

        sheets = ma.read_sheets(b64, allow_wide=True)
        (sheet_name, grid, money_row, money_cols), _sk = mo._pick_sheet(sheets)
        taken, all_hits = _label_trace(mo, ma, grid, money_row)

        cols = res["columns"]
        c_rep = cols.get("inv_replaced_by")
        c_inv = cols.get("inv_no")
        print(f"  {chain:16} sheet={sheet_name!r} header_row(money)={money_row} "
              f"total_row={res['total_row']}")
        if c_inv:
            rr, cc, txt, k = taken["inv_no"]
            print(f"      inv_no          -> cột {cc:>3}  nhãn thật ở dòng {rr}: "
                  f"{txt!r}   (khóa _norm = {k!r})")
        else:
            print("      inv_no          -> KHÔNG CÓ")
        if c_rep:
            rr, cc, txt, k = taken["inv_replaced_by"]
            print(f"      inv_replaced_by -> cột {cc:>3}  nhãn thật ở dòng {rr}: "
                  f"{txt!r}   (khóa _norm = {k!r})")
        else:
            print("      inv_replaced_by -> KHÔNG CÓ CỘT NÀY")
        others = [h for h in all_hits
                  if h[0] in ("inv_no", "inv_replaced_by")
                  and (h[1], h[2]) != (taken.get(h[0]) or (None, None))[:2]]
        for key, rr, cc, txt, k in others:
            print(f"      (nhãn {key} khác cũng trúng, BỊ BỎ vì tìm sau: "
                  f"dòng {rr} cột {cc} {txt!r} khóa={k!r})")
        per_chain.append((chain, res, c_rep, c_inv))

    # ── §2 Khuôn giá trị ────────────────────────────────────────────────────
    print()
    print("§2  KHUÔN GIÁ TRỊ TRONG CỘT `inv_replaced_by`")
    print("-" * 100)
    all_shapes = collections.Counter()
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            print(f"  {chain:16} — không có cột, bỏ qua")
            continue
        vals = [r["inv_replaced_by"] for r in res["rows"] if r["inv_replaced_by"]]
        shapes = collections.Counter(_shape(v) for v in vals)
        all_shapes.update(shapes)
        lens = collections.Counter(len(str(v)) for v in vals)
        multi = [v for v in vals if len(NUM_RE.findall(str(v))) > 1]
        nonnum = [v for v in vals if not re.fullmatch(r"\d+", str(v))]
        padded = [v for v in vals if str(v) != str(v).lstrip("0")]
        print(f"  {chain:16} {len(vals):4} dòng có giá trị")
        print(f"      khuôn      : {dict(shapes)}")
        print(f"      độ dài     : {dict(sorted(lens.items()))}")
        print(f"      đệm 0 đầu  : {len(padded)}"
              + (f"   ví dụ {padded[:5]}" if padded else ""))
        print(f"      KHÔNG-toàn-số: {len(nonnum)}"
              + (f"   -> {nonnum[:10]}" if nonnum else ""))
        print(f"      nhiều số 1 ô : {len(multi)}"
              + (f"   -> {multi[:10]}" if multi else ""))
        print(f"      mẫu 8 giá trị đầu: {vals[:8]}")
    print(f"  TỔNG khuôn cả 7 file: {dict(all_shapes)}")

    # ── §3 Dòng CÒN NỢ mang số thay thế ─────────────────────────────────────
    print()
    print("§3  CÁC DÒNG CÒN NỢ (|remaining| > 1đ) MANG SỐ HÓA ĐƠN THAY THẾ")
    print("-" * 100)
    print(f"  {'chuỗi':16} {'dòng':>5} {'inv_no':>14} {'replaced_by':>14} "
          f"{'gross':>16} {'remaining':>16}  inv_date")
    n_open_rep = 0
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            continue
        for r in res["rows"]:
            if not r["inv_replaced_by"]:
                continue
            if abs(float(r["remaining"] or 0)) <= MONEY_EPS:
                continue
            n_open_rep += 1
            print(f"  {chain:16} {r['source_row']:>5} {str(r['inv_no']):>14} "
                  f"{str(r['inv_replaced_by']):>14} "
                  f"{float(r['gross'] or 0):>16,.0f} "
                  f"{float(r['remaining'] or 0):>16,.0f}  {r['inv_date']}")
    print(f"  => TỔNG {n_open_rep} dòng CÒN NỢ mang số thay thế")

    # ── §4 Số thay thế có trùng inv_no của dòng KHÁC không? ─────────────────
    print()
    print("§4  `inv_replaced_by` CÓ TRÙNG `inv_no` CỦA MỘT DÒNG KHÁC TRONG CÙNG FILE?")
    print("     (nếu có -> khớp theo số thay thế làm HAI dòng trỏ về MỘT hóa đơn)")
    print("-" * 100)
    grand_collide = 0
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            print(f"  {chain:16} — không có cột, bỏ qua")
            continue
        rows = res["rows"]
        # Chỉ mục theo SỐ ĐÃ CHUẨN HÓA — đúng thứ `mt._si_index` dùng để khớp
        # ('00000078' và '78' là một hóa đơn).
        by_inv = collections.defaultdict(list)
        for r in rows:
            if r["inv_no"]:
                by_inv[norm_inv_no(r["inv_no"])].append(r)

        collide = []
        for r in rows:
            rep = r["inv_replaced_by"]
            if not rep:
                continue
            hits = [o for o in by_inv.get(norm_inv_no(rep), []) if o is not r]
            if hits:
                collide.append((r, hits))
        grand_collide += len(collide)
        print(f"  {chain:16} {len(collide)} dòng có số thay thế TRÙNG inv_no của "
              f"dòng khác")
        for r, hits in collide:
            print(f"      dòng {r['source_row']}: inv_no={r['inv_no']!r} "
                  f"replaced_by={r['inv_replaced_by']!r} "
                  f"remaining={float(r['remaining'] or 0):,.0f}")
            for o in hits:
                print(f"          ĐỤNG dòng {o['source_row']}: inv_no={o['inv_no']!r} "
                      f"gross={float(o['gross'] or 0):,.0f} "
                      f"remaining={float(o['remaining'] or 0):,.0f} "
                      f"date={o['inv_date']} replaced_by={o['inv_replaced_by']!r}")

        # Hai biến thể phải soi riêng, vì mỗi cái hỏng một kiểu khác nhau:
        same = [r for r in rows if r["inv_replaced_by"] and r["inv_no"]
                and norm_inv_no(r["inv_replaced_by"]) == norm_inv_no(r["inv_no"])]
        if same:
            print(f"      + {len(same)} dòng có replaced_by TRÙNG CHÍNH inv_no của nó: "
                  f"{[(r['source_row'], r['inv_no']) for r in same][:10]}")
        dup_rep = [(v, n) for v, n in collections.Counter(
            norm_inv_no(r["inv_replaced_by"]) for r in rows
            if r["inv_replaced_by"]).items() if n > 1]
        if dup_rep:
            print(f"      + {len(dup_rep)} số thay thế xuất hiện ở NHIỀU dòng: "
                  f"{sorted(dup_rep)[:10]}")
        no_inv = [r for r in rows if r["inv_replaced_by"] and not r["inv_no"]]
        if no_inv:
            print(f"      + {len(no_inv)} dòng có replaced_by nhưng KHÔNG có inv_no: "
                  f"{[(r['source_row'], r['inv_replaced_by']) for r in no_inv][:10]}")
    print(f"  => TỔNG toàn bộ 7 file: {grand_collide} dòng đụng độ")

    # ── §5 remaining của dòng có số thay thế ────────────────────────────────
    print()
    print("§5  DÒNG CÓ SỐ THAY THẾ: `remaining` BẰNG 0 HAY KHÁC 0?")
    print("-" * 100)
    print(f"  {'chuỗi':16} {'có rep':>7} {'rem=0':>7} {'rem>0':>7} {'rem<0':>7} "
          f"{'tiền còn nợ':>18} {'gross của nhóm':>18}")
    t = [0, 0, 0, 0, 0.0, 0.0]
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            continue
        rows = [r for r in res["rows"] if r["inv_replaced_by"]]
        z = sum(1 for r in rows if abs(float(r["remaining"] or 0)) <= MONEY_EPS)
        p = sum(1 for r in rows if float(r["remaining"] or 0) > MONEY_EPS)
        n = sum(1 for r in rows if float(r["remaining"] or 0) < -MONEY_EPS)
        amt = sum(float(r["remaining"] or 0) for r in rows)
        gr = sum(float(r["gross"] or 0) for r in rows)
        print(f"  {chain:16} {len(rows):>7} {z:>7} {p:>7} {n:>7} {amt:>18,.0f} "
              f"{gr:>18,.0f}")
        t[0] += len(rows); t[1] += z; t[2] += p; t[3] += n; t[4] += amt; t[5] += gr
    print(f"  {'TỔNG':16} {t[0]:>7} {t[1]:>7} {t[2]:>7} {t[3]:>7} {t[4]:>18,.0f} "
          f"{t[5]:>18,.0f}")

    # ── §6 Số hóa đơn TỰ NÓ đã trùng nhau trong cùng file chưa? ─────────────
    print()
    print("§6  `inv_no` (đã chuẩn hóa) CÓ TRÙNG GIỮA CÁC DÒNG TRONG CÙNG FILE KHÔNG?")
    print("     (nền của mọi cách khớp — nếu chính số gốc đã trùng thì `_si_index`")
    print("      cũng đang mơ hồ sẵn, không riêng gì số thay thế)")
    print("-" * 100)
    for chain, res, _cr, c_inv in per_chain:
        if not c_inv:
            continue
        cnt = collections.Counter(norm_inv_no(r["inv_no"]) for r in res["rows"]
                                  if r["inv_no"])
        dups = {k: v for k, v in cnt.items() if v > 1}
        rows_in_dup = sum(dups.values())
        open_dups = {}
        for k in dups:
            n_open = sum(1 for r in res["rows"] if r["inv_no"]
                         and norm_inv_no(r["inv_no"]) == k
                         and abs(float(r["remaining"] or 0)) > MONEY_EPS)
            if n_open:
                open_dups[k] = (dups[k], n_open)
        print(f"  {chain:16} {len(cnt):5} số khác nhau | {len(dups):4} số bị dùng lại "
              f"({rows_in_dup} dòng) | {len(open_dups)} số dùng lại mà CÒN NỢ")
        for k, (tot, n_open) in sorted(open_dups.items())[:12]:
            det = [(r["source_row"], r["inv_date"], round(float(r["gross"] or 0)),
                    round(float(r["remaining"] or 0)))
                   for r in res["rows"]
                   if r["inv_no"] and norm_inv_no(r["inv_no"]) == k]
            print(f"      số {k!r}: {tot} dòng, {n_open} còn nợ -> "
                  f"(dòng, ngày, gross, remaining) = {det}")

    # ── §7 Chuỗi thay thế nhiều đời ─────────────────────────────────────────
    print()
    print("§7  CÓ CHUỖI THAY THẾ NHIỀU ĐỜI KHÔNG? (A bị thay bởi B, B lại bị thay bởi C)")
    print("-" * 100)
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            continue
        by_inv = collections.defaultdict(list)
        for r in res["rows"]:
            if r["inv_no"]:
                by_inv[norm_inv_no(r["inv_no"])].append(r)
        chains = []
        for r in res["rows"]:
            if not r["inv_replaced_by"]:
                continue
            for o in by_inv.get(norm_inv_no(r["inv_replaced_by"]), []):
                if o is not r and o["inv_replaced_by"]:
                    chains.append((r, o))
        print(f"  {chain:16} {len(chains)} mắt xích nhiều đời")
        for r, o in chains:
            print(f"      dòng {r['source_row']} inv_no={r['inv_no']!r} -> "
                  f"{r['inv_replaced_by']!r} ; dòng {o['source_row']} "
                  f"inv_no={o['inv_no']!r} -> {o['inv_replaced_by']!r} "
                  f"(gross {float(o['gross'] or 0):,.0f}, "
                  f"remaining {float(o['remaining'] or 0):,.0f})")

    # ── §8 Dòng có số thay thế: tiền được TẤT TOÁN bằng cách nào ────────────
    print()
    print("§8  DÒNG CÓ SỐ THAY THẾ MÀ `remaining`=0 — TẤT TOÁN BẰNG `paid` HAY BẰNG 0?")
    print("     (paid=gross -> file coi là đã THU tiền; paid=0 & gross>0 & rem=0 ->")
    print("      file tự tay ép về 0 vì hóa đơn gốc HẾT HIỆU LỰC)")
    print("-" * 100)
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            continue
        rows = [r for r in res["rows"] if r["inv_replaced_by"]
                and abs(float(r["remaining"] or 0)) <= MONEY_EPS]
        pay_eq = sum(1 for r in rows
                     if abs(float(r["paid"] or 0) - float(r["gross"] or 0)) <= MONEY_EPS)
        pay_zero = sum(1 for r in rows if abs(float(r["paid"] or 0)) <= MONEY_EPS
                       and abs(float(r["gross"] or 0)) > MONEY_EPS)
        gross_zero = sum(1 for r in rows if abs(float(r["gross"] or 0)) <= MONEY_EPS)
        other = len(rows) - pay_eq - pay_zero
        print(f"  {chain:16} rem=0 & có rep: {len(rows):4} | paid=gross: {pay_eq:4} | "
              f"paid=0 mà gross>0: {pay_zero:4} | gross=0: {gross_zero:4} | "
              f"còn lại: {other:4}")
        if pay_zero:
            ex = [(r["source_row"], r["inv_no"], r["inv_replaced_by"],
                   round(float(r["gross"] or 0))) for r in rows
                  if abs(float(r["paid"] or 0)) <= MONEY_EPS
                  and abs(float(r["gross"] or 0)) > MONEY_EPS][:6]
            print(f"      ví dụ paid=0 mà gross>0: {ex}")

    # ── §9 CA NGUY HIỂM: dòng CÒN NỢ mà số thay thế đụng dòng khác ──────────
    print()
    print("§9  CA NGUY HIỂM NHẤT — DÒNG **CÒN NỢ** MÀ SỐ THAY THẾ TRÙNG inv_no DÒNG KHÁC")
    print("-" * 100)
    n_danger = 0
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            continue
        by_inv = collections.defaultdict(list)
        for r in res["rows"]:
            if r["inv_no"]:
                by_inv[norm_inv_no(r["inv_no"])].append(r)
        for r in res["rows"]:
            if not r["inv_replaced_by"]:
                continue
            if abs(float(r["remaining"] or 0)) <= MONEY_EPS:
                continue
            hits = [o for o in by_inv.get(norm_inv_no(r["inv_replaced_by"]), [])
                    if o is not r]
            if not hits:
                continue
            n_danger += 1
            print(f"  {chain}: dòng {r['source_row']} inv_no={r['inv_no']!r} "
                  f"replaced_by={r['inv_replaced_by']!r} gross="
                  f"{float(r['gross'] or 0):,.0f} remaining="
                  f"{float(r['remaining'] or 0):,.0f} date={r['inv_date']}")
            for o in hits:
                print(f"      dòng đang giữ số đó: {o['source_row']} "
                      f"inv_no={o['inv_no']!r} gross={float(o['gross'] or 0):,.0f} "
                      f"paid={float(o['paid'] or 0):,.0f} "
                      f"remaining={float(o['remaining'] or 0):,.0f} "
                      f"date={o['inv_date']}")
                print(f"      => hai dòng KHÁC SỐ TIỀN "
                      f"({float(r['gross'] or 0):,.0f} vs "
                      f"{float(o['gross'] or 0):,.0f})"
                      if abs(float(r["gross"] or 0) - float(o["gross"] or 0)) > MONEY_EPS
                      else "      => hai dòng CÙNG SỐ TIỀN")
    print(f"  => {n_danger} ca (trên tổng 59 dòng còn nợ có số thay thế)")

    # ── §10 Đụng độ là THẬT hay chỉ do SỐ HÓA ĐƠN BỊ DÙNG LẠI QUA NĂM? ──────
    print()
    print("§10 70 CA ĐỤNG ĐỘ: THẬT (dòng riêng của hóa đơn thay thế) HAY GIẢ")
    print("    (số hóa đơn bị dùng lại qua năm)?")
    print("    Hóa đơn thay thế PHẢI ra ĐỜI SAU hóa đơn gốc. Dòng đụng độ mang ngày")
    print("    TRƯỚC ngày hóa đơn gốc thì nó KHÔNG THỂ là hóa đơn thay thế.")
    print("-" * 100)
    tot_after = tot_before = tot_nodate = 0
    for chain, res, c_rep, _c in per_chain:
        if not c_rep:
            continue
        by_inv = collections.defaultdict(list)
        for r in res["rows"]:
            if r["inv_no"]:
                by_inv[norm_inv_no(r["inv_no"])].append(r)
        after = before = nodate = 0
        after_ex = []
        gaps = []
        for r in res["rows"]:
            if not r["inv_replaced_by"]:
                continue
            for o in by_inv.get(norm_inv_no(r["inv_replaced_by"]), []):
                if o is r:
                    continue
                if not r["inv_date"] or not o["inv_date"]:
                    nodate += 1
                elif o["inv_date"] >= r["inv_date"]:
                    after += 1
                    gap = (datetime.date.fromisoformat(o["inv_date"])
                           - datetime.date.fromisoformat(r["inv_date"])).days
                    after_ex.append((r["source_row"], r["inv_no"],
                                     r["inv_replaced_by"], r["inv_date"],
                                     o["source_row"], o["inv_date"],
                                     round(float(r["gross"] or 0)),
                                     round(float(o["gross"] or 0)), gap))
                    gaps.append(gap)
                else:
                    before += 1
        tot_after += after; tot_before += before; tot_nodate += nodate
        print(f"  {chain:16} đụng SAU (có thể THẬT): {after:3} | "
              f"đụng TRƯỚC (dùng lại số, GIẢ): {before:3} | thiếu ngày: {nodate:3}")
        near = [e for e in after_ex if e[8] <= 90]
        print(f"      trong đó cách nhau <= 90 ngày (mới có thể là thay thế THẬT): "
              f"{len(near)}")
        for e in near:
            print(f"      *** dòng {e[0]} inv_no={e[1]!r} rep={e[2]!r} ngày {e[3]} "
                  f"gross {e[6]:,} <-> dòng đụng {e[4]} ngày {e[5]} "
                  f"gross {e[7]:,}  (cách {e[8]} ngày)")
        if gaps:
            gaps.sort()
            print(f"      khoảng cách ngày giữa 2 dòng đụng nhau: nhỏ nhất {gaps[0]}, "
                  f"trung vị {gaps[len(gaps) // 2]}, lớn nhất {gaps[-1]}")
    print(f"  TỔNG: đụng SAU {tot_after} | đụng TRƯỚC {tot_before} | "
          f"thiếu ngày {tot_nodate}")

    print()
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
