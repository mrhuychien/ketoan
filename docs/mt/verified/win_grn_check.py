"""Kiểm ĐỌC PHIẾU NHẬP KHO WINMART + ĐỐI SOÁT (`ketoan/api/mt_win_grn.py`).

    python3 docs/mt/verified/win_grn_check.py

Chạy trên HAI PHIẾU THẬT ở `docs/mt/samples/pnk/`.

SOP §2.2: *"Xuất HĐ CHỈ sau khi có phiếu nhập kho trên hệ Win và khớp PO + hàng
hóa. Lệch số lượng → xuất trả phần chênh, xuất hóa đơn theo số thực nhận."*
Đây là khâu quyết định hóa đơn Winmart đúng hay sai; sai thì Win trả hồ sơ và cả
đợt trượt kỳ thanh toán.

════════════════════════════════════════════════════════════════════════════
NĂM CHỖ ĐÃ ĐO ĐƯỢC LÀ DỄ SAI
════════════════════════════════════════════════════════════════════════════

1. TÊN HÀNG CHỨA SỐ (`300g`, `210g`, `Đ.Xanh Th.Hạng RV 170g`). Tách số lượng
   bằng "lấy số cuối dòng" là lấy nhầm `170` làm số lượng. Phải neo vào ĐVT.

2. SỐ PO LÀ SỐ DÀI. Đọc ra float thì thành `4193445648.0` và không khớp
   `custom_po_` nào cả — im lặng báo "chưa có hóa đơn".

3. TÊN KHO CÓ DẤU CÁCH (`1312 WMP_AMBIENT_BINH DUONG1_HANGTHUONG`). Lấy "hai
   token sau nhãn" thì cắt cụt.

4. MỘT MÃ CÓ THỂ NẰM TRÊN NHIỀU DÒNG ở cả hai phía (Win tách lô, hóa đơn tách
   theo đơn giá). So từng dòng rời là báo lệch giả -> phải CỘNG DỒN theo mã.

5. BỐN KẾT LUẬN, KHÔNG GỘP. `lệch số lượng`, `phiếu có hóa đơn không`, `hóa đơn
   có phiếu không` là ba việc phải làm khác hẳn nhau. Gộp thành "không khớp" là
   bắt kế toán mở lại PDF đọc tay.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

DIR = "docs/mt/samples/pnk"
COMPANY = "HGC"

# Gõ lại từ chính bản in của hai phiếu.
CASES = {
    "pnk_4193445648.pdf": {
        "grn_no": "5195070958", "po_no": "4193445648", "grn_date": "2026-07-30",
        "store": "1312 WMP_AMBIENT_BINH DUONG1_HANGTHUONG", "vendor": "0002007766",
        "lines": [("10325502", 40, "HOP")],
    },
    "pnk_4190754676.pdf": {
        "grn_no": "5189984522", "po_no": "4190754676", "grn_date": "2026-06-11",
        "store": "1355 WMT_AMBIENT_BINHDUONG_FT", "vendor": "0002007766",
        "lines": [("10325502", 20, "HOP"), ("10325504", 30, "HOP"),
                  ("10406885", 30, "HOP"), ("10406887", 80, "HOP"),
                  ("10640275", 24, "HOP")],
    },
}


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.db.table_exists = lambda dt: True
    frappe.db.has_column = lambda dt, col: True
    frappe.db.commit = lambda *a, **kw: None

    mg = importlib.import_module("ketoan.api.mt_win_grn")
    mg._company = lambda company=None: COMPANY

    def read(fname):
        raw = open(os.path.join(rc.REPO, DIR, fname), "rb").read()
        return mg.read_grn(base64.b64encode(raw).decode())

    print("=" * 82)
    print("KIỂM ĐỌC PHIẾU NHẬP KHO WINMART + ĐỐI SOÁT")
    print("=" * 82)
    bad = 0
    got = {}

    # ── 1. Hai phiếu đọc đúng từng trường ────────────────────────────────
    for fname, want in CASES.items():
        g = read(fname)
        got[fname] = g
        errs = []
        for k in ("grn_no", "po_no", "store"):
            if g[k] != want[k if k != "store" else "store"]:
                errs.append(f"{k}: {g[k]!r} != {want[k]!r}")
        if str(g["grn_date"]) != want["grn_date"]:
            errs.append(f"ngày: {g['grn_date']} != {want['grn_date']}")
        if g["vendor_code"] != want["vendor"]:
            errs.append(f"NCC: {g['vendor_code']!r} != {want['vendor']!r}")
        lines = [(l["item_code"], l["qty"], l["uom"]) for l in g["lines"]]
        if lines != [(c, float(q), u) for c, q, u in want["lines"]]:
            errs.append(f"dòng hàng: {lines}")
        ok = not errs
        print(f"  {'✅' if ok else '❌'} {fname:<24} phiếu {g['grn_no']} · PO {g['po_no']} · "
              f"{g['n_lines']} dòng · SL {g['total_qty']:g}")
        for e in errs:
            print(f"       └─ {e}")
        bad += not ok

    # ── 2. Bẫy: tên hàng chứa số ─────────────────────────────────────────
    print("-" * 82)
    g = got["pnk_4190754676.pdf"]
    row = next(l for l in g["lines"] if l["item_code"] == "10640275")
    ok = row["qty"] == 24 and "170g" in row["item_name"]
    print(f"  {'✅' if ok else '❌'} tên hàng chứa số (`…RV 170g`) -> số lượng vẫn ra "
          f"{row['qty']:g}, không lấy nhầm 170")
    bad += not ok

    row = next(l for l in g["lines"] if l["item_code"] == "10406887")
    ok = row["qty"] == 80 and "200g" in row["item_name"]
    print(f"  {'✅' if ok else '❌'} `…Trái cây 200g` -> số lượng {row['qty']:g}, "
          f"không lấy nhầm 200")
    bad += not ok

    # ── 3. Bẫy: số PO phải là CHUỖI SỐ NGUYÊN ────────────────────────────
    print("-" * 82)
    ok = all(isinstance(x["po_no"], str) and "." not in x["po_no"] for x in got.values())
    print(f"  {'✅' if ok else '❌'} số PO là chuỗi số nguyên "
          f"({[x['po_no'] for x in got.values()]}) — `4193445648.0` sẽ không khớp "
          f"`custom_po_` nào")
    bad += not ok

    # ── 4. Đối soát — bốn kết luận ───────────────────────────────────────
    print("-" * 82)
    g = got["pnk_4190754676.pdf"]

    def with_si(items, invoices=None):
        """Cắm hóa đơn giả cho phép đối soát."""
        inv = invoices if invoices is not None else [
            _D(name="SI-1", docstatus=0, posting_date="2026-06-12", customer="KH-WIN",
               customer_name="Win", grand_total=0)]

        def _sql(query, values=None, **kw):
            q = " ".join(str(query).split())
            if "tabSales Invoice Item" in q:
                return list(items)
            if "tabSales Invoice" in q:
                return list(inv)
            return []
        frappe.db.sql = _sql

    # (a) Khớp hoàn toàn
    with_si([_D(parent="SI-1", item_code="BDX300", item_name="x", qty=q, uom="HOP",
                ma_win=c) for c, q, _u in CASES["pnk_4190754676.pdf"]["lines"]])
    m = mg.match_grn(g, COMPANY)
    ok = m["ok"] and m["counts"][mg.MATCH_OK] == 5
    print(f"  {'✅' if ok else '❌'} hóa đơn khớp đủ 5 mã -> ĐẠT, {m['counts'][mg.MATCH_OK]} dòng khớp")
    bad += not ok

    # (b) Lệch số lượng -> xuất HĐ theo SỐ THỰC NHẬN
    items = [_D(parent="SI-1", item_code="x", item_name="x", qty=q, uom="HOP", ma_win=c)
             for c, q, _u in CASES["pnk_4190754676.pdf"]["lines"]]
    items[0]["qty"] = 18                      # phiếu ghi 20
    with_si(items)
    m = mg.match_grn(g, COMPANY)
    row = next(x for x in m["lines"] if x["ma_win"] == "10325502")
    ok = (not m["ok"]) and row["status"] == mg.MATCH_QTY and row["diff"] == -2
    print(f"  {'✅' if ok else '❌'} hóa đơn ghi 18 mà phiếu ghi 20 -> `{row['status']}`, "
          f"lệch {row['diff']:g}")
    bad += not ok

    # (c) Phiếu có, hóa đơn KHÔNG -> hóa đơn thiếu hàng
    with_si(items[:4])
    m = mg.match_grn(g, COMPANY)
    row = next(x for x in m["lines"] if x["ma_win"] == "10640275")
    ok = row["status"] == mg.MATCH_MISSING_SI and row["qty_si"] is None
    print(f"  {'✅' if ok else '❌'} mã 10640275 có trên phiếu mà hóa đơn không -> "
          f"`{row['status']}`")
    bad += not ok

    # (d) Hóa đơn có, phiếu KHÔNG -> Win không nhận, phải xuất trả
    with_si(items + [_D(parent="SI-1", item_code="z", item_name="hàng lạ", qty=5,
                        uom="HOP", ma_win="99999999")])
    m = mg.match_grn(g, COMPANY)
    row = next(x for x in m["lines"] if x["ma_win"] == "99999999")
    ok = row["status"] == mg.MATCH_EXTRA_SI and row["qty_grn"] is None
    print(f"  {'✅' if ok else '❌'} mã 99999999 có trên hóa đơn mà phiếu không -> "
          f"`{row['status']}`")
    bad += not ok

    ok = len(set(mg.MATCH_LABEL)) == 4
    print(f"  {'✅' if ok else '❌'} bốn kết luận TÁCH RIÊNG, không gộp thành "
          f"'khớp / không khớp'")
    bad += not ok

    # ── 5. Cộng dồn theo mã khi một mã nằm nhiều dòng ────────────────────
    print("-" * 82)
    split = [_D(parent="SI-1", item_code="a", item_name="x", qty=12, uom="HOP", ma_win="10325502"),
             _D(parent="SI-1", item_code="a", item_name="x", qty=8, uom="HOP", ma_win="10325502")]
    with_si(split + items[1:])
    m = mg.match_grn(g, COMPANY)
    row = next(x for x in m["lines"] if x["ma_win"] == "10325502")
    ok = row["status"] == mg.MATCH_OK and row["qty_si"] == 20
    print(f"  {'✅' if ok else '❌'} hóa đơn tách 12 + 8 cho cùng mã -> cộng dồn thành "
          f"{row['qty_si']:g}, KHỚP (không báo lệch giả)")
    bad += not ok

    # ── 6. Dòng hóa đơn THIẾU mã Win -> phải kêu ─────────────────────────
    print("-" * 82)
    with_si(items + [_D(parent="SI-1", item_code="q", item_name="chưa gắn mã", qty=3,
                        uom="HOP", ma_win=None)])
    m = mg.match_grn(g, COMPANY)
    ok = (not m["ok"]) and len(m["items_without_code"]) == 1 \
        and any("custom_ma_win" in w for w in m["warnings"])
    print(f"  {'✅' if ok else '❌'} dòng hóa đơn để trống `custom_ma_win` -> KHÔNG kết "
          f"luận đạt, và nêu đích danh field")
    bad += not ok

    # ── 7. Field của SITE thiếu -> báo ĐÚNG field, không nổ SQL ──────────
    print("-" * 82)
    frappe.db.has_column = lambda dt, col: col != "custom_ma_win"
    m = mg.match_grn(g, COMPANY)
    ok = m["blocked"] and "custom_ma_win" in m["reason"]
    print(f"  {'✅' if ok else '❌'} site thiếu `custom_ma_win` -> báo đích danh field, "
          f"không ném lỗi SQL")
    bad += not ok

    frappe.db.has_column = lambda dt, col: col != "custom_po_"
    m = mg.match_grn(g, COMPANY)
    ok = m["blocked"] and "custom_po_" in m["reason"]
    print(f"  {'✅' if ok else '❌'} site thiếu `custom_po_` -> báo đích danh field")
    bad += not ok
    frappe.db.has_column = lambda dt, col: True

    # ── 8. Chưa có hóa đơn cho PO -> KHÔNG coi là lỗi ────────────────────
    print("-" * 82)
    with_si([], invoices=[])
    m = mg.match_grn(g, COMPANY)
    ok = (not m["ok"]) and (not m["blocked"]) and "SAU khi có phiếu" in m["reason"]
    print(f"  {'✅' if ok else '❌'} chưa có hóa đơn mang PO đó -> nói rõ đó có thể là "
          f"ĐÚNG (Win chỉ cho xuất HĐ sau khi có phiếu), không báo như lỗi")
    bad += not ok

    # ── 9. File không phải PDF / không phải phiếu Win ────────────────────
    print("-" * 82)
    try:
        mg.read_grn(base64.b64encode(b"PK\x03\x04 not a pdf").decode())
        print("  ❌ file không phải PDF -> KHÔNG dừng")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "không phải PDF" in str(e)
        print(f"  {'✅' if ok else '❌'} file không phải PDF -> dừng")
        bad += not ok

    other = os.path.join(rc.REPO, "docs/mt/samples/Chi tiết doanh số Emart.PDF")
    if os.path.exists(other):
        try:
            mg.read_grn(base64.b64encode(open(other, "rb").read()).decode())
            print("  ❌ PDF khác (Rebate Settlement Emart) -> KHÔNG dừng")
            bad += 1
        except Exception as e:                                     # noqa: BLE001
            ok = "không phải phiếu nhập kho" in str(e)
            print(f"  {'✅' if ok else '❌'} PDF của chuỗi khác -> dừng, nêu rõ không phải "
                  f"phiếu nhập kho Win")
            bad += not ok

    # ── 10. Ghi phiếu vào đợt giao — chỗ DUY NHẤT module này ghi ─────────
    print("-" * 82)
    content = base64.b64encode(
        open(os.path.join(rc.REPO, DIR, "pnk_4193445648.pdf"), "rb").read()).decode()
    grn = mg.read_grn(content)
    h = mg._grn_hash(grn)

    saved = {}

    class _Pending(_D):
        def save(self):
            saved.update(dict(self))

    def _mount(row):
        """Cắm một dòng `MT Win Pending` giả cho PO 4193445648."""
        def _sql(query, values=None, **kw):
            q = " ".join(str(query).split())
            if "MT Win Pending" in q:
                return [row] if row else []
            return []
        frappe.db.sql = _sql
        doc = _Pending(row or {})
        frappe.get_doc = lambda dt, name=None: doc
        return doc

    # (a) vân tay sai -> KHÔNG ghi
    _mount(_D(name="WP-1", po_no="4193445648", status=mg.STATUS_DELIVERING, grn_no=None))
    saved.clear()
    try:
        mg.attach_grn(content, "sai-vantay", company=COMPANY)
        print("  ❌ vân tay sai -> VẪN ghi")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "đã đổi so với lúc xem trước" in str(e) and not saved
        print(f"  {'✅' if ok else '❌'} vân tay phiếu sai -> chặn, KHÔNG ghi gì")
        bad += not ok

    # (b) không có đợt giao nào mang PO đó -> KHÔNG tự tạo
    _mount(None)
    saved.clear()
    try:
        mg.attach_grn(content, h, company=COMPANY)
        print("  ❌ không có đợt giao -> tự ý tạo/ghi")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "Không có đợt giao nào" in str(e) and not saved
        print(f"  {'✅' if ok else '❌'} chưa theo dõi PO đó -> dừng và bảo thêm đợt "
              f"giao trước, KHÔNG tự tạo")
        bad += not ok

    # (c) đợt giao đã gắn phiếu KHÁC -> không ghi đè âm thầm
    _mount(_D(name="WP-1", po_no="4193445648", status=mg.STATUS_RECEIVED,
              grn_no="5100000000"))
    saved.clear()
    try:
        mg.attach_grn(content, h, company=COMPANY)
        print("  ❌ đã có phiếu khác -> ghi đè âm thầm")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "đã gắn phiếu nhập kho" in str(e) and not saved
        print(f"  {'✅' if ok else '❌'} đợt giao đã gắn phiếu khác -> dừng hỏi người, "
              f"không xóa vết phiếu cũ")
        bad += not ok

    # (d) đường đúng: ghi số phiếu + ngày, chuyển sang 'đã nhận'
    doc = _mount(_D(name="WP-1", po_no="4193445648", status=mg.STATUS_DELIVERING,
                    grn_no=None, grn_date=None))
    saved.clear()
    out = mg.attach_grn(content, h, company=COMPANY)
    ok = (saved.get("grn_no") == "5195070958"
          and str(saved.get("grn_date")) == "2026-07-30"
          and saved.get("status") == mg.STATUS_RECEIVED
          and out["status"] == mg.STATUS_RECEIVED)
    print(f"  {'✅' if ok else '❌'} gắn đúng: phiếu {saved.get('grn_no')} · "
          f"{saved.get('grn_date')} · trạng thái -> {saved.get('status')}")
    bad += not ok

    # (e) KHÔNG đụng gì tới hóa đơn
    ok = not any(k in saved for k in ("sales_invoice", "total_amount", "amount_before_vat"))
    print(f"  {'✅' if ok else '❌'} chỉ ghi lên đợt giao — không sửa hóa đơn, không "
          f"đụng tiền")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — đọc đúng hai phiếu thật, bốn kết luận đối soát tách riêng, "
          "thiếu field thì báo đích danh, và đường ghi vào đợt giao có chốt vân tay")
    return 0


if __name__ == "__main__":
    sys.exit(main())
