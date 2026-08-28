#!/usr/bin/env python3
"""Kiểm KHỞI TẠO ĐỢT GIAO WIN TỪ SỐ DƯ ĐẦU KỲ ĐÃ CHỐT.

════════════════════════════════════════════════════════════════════════════
VÌ SAO CÓ ĐƯỜNG VÀO THỨ HAI
════════════════════════════════════════════════════════════════════════════

Số dư đầu kỳ Win đã được nạp và CHỐT một lần rồi. Bắt kế toán đi tìm lại đúng
file Excel cũ để nạp lần nữa là mời một lỗi rất khó thấy: nạp nhầm bản sửa sau,
hoặc nhầm kỳ. Và `MT Win Pending` không giữ liên kết ngược về file, nên không
chỗ nào đối chiếu được hai lần đọc.

════════════════════════════════════════════════════════════════════════════
BỐN CHỐT CHẶN
════════════════════════════════════════════════════════════════════════════

1. CHỈ NHẬN BẢN "ĐÃ CHỐT". Bản nháp còn sửa được; dựng đợt giao từ nó rồi chốt
   lại khác đi là các PO đứng đó không còn căn cứ nào.

2. HAI ĐƯỜNG VÀO PHẢI RA CÙNG MỘT DANH SÁCH. Đọc từ file và đọc từ bản đã chốt
   là hai đường tới cùng một sự thật — lệch nhau thì một trong hai đang sai mà
   không ai biết cái nào.

3. CHẶN THEO CÙNG MỘT LUẬT. Trùng PO ở đường này mà lọt ở đường kia là tạo hai
   bản ghi cho cùng một đợt giao.

4. VÂN TAY KẾ HOẠCH kiểm ở MỘT chỗ (`_write_plan`). Để mỗi đường tự kiểm là
   sớm muộn một đường quên, và đường đó ghi khác thứ người duyệt đã xem.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import ast
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


class _Line:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Doc:
    def __init__(self, name, chain, status, lines, company="HGC", cutover_date="2026-06-30"):
        self.name = name
        self.chain = chain
        self.status = status
        self.lines = lines
        self.company = company
        self.cutover_date = cutover_date


def line(row, po, net, vat, gross, kind="chua_co_hoa_don", party="CN BÌNH DƯƠNG"):
    return _Line(source_row=row, kind=kind, note=po, party=party,
                 net=net, vat=vat, gross=gross, remaining=gross)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: True
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    wp = importlib.import_module("ketoan.api.mt_win_pending")
    wp._company = lambda company=None: "HGC"
    wp._tables = lambda: None

    print("=" * 82)
    print("KIỂM KHỞI TẠO ĐỢT GIAO WIN TỪ SỐ DƯ ĐÃ CHỐT")
    print("=" * 82)
    bad = 0

    LINES = [
        line(2190, "4194417760", 4_200_000, 420_000, 4_620_000),
        line(2191, "4194417761", 3_000_000, 300_000, 3_300_000),
        # Dòng CÓ số hóa đơn -> KHÔNG thuộc danh sách chờ.
        line(2192, "4194417762", 1_000_000, 100_000, 1_100_000, kind="co_hoa_don"),
        # Không có PO -> chặn, vì không có khóa nào để theo dõi.
        line(2193, "", 500_000, 50_000, 550_000),
    ]
    DOC = _Doc("MT-OPEN-00001", "WinCommerce", "Đã chốt", LINES)

    store = {"doc": DOC, "exists": True}
    frappe.get_doc = lambda dt, nm: store["doc"]
    frappe.db.exists = lambda dt, nm=None: store["exists"]
    frappe.db.sql = lambda *a, **k: []          # chưa PO nào được theo dõi

    # ── 1. Đọc đúng nhóm dòng ───────────────────────────────────────────
    doc, rows = wp._seed_rows_from_opening("MT-OPEN-00001", "HGC")
    ok = [r["po_no"] for r in rows] == ["4194417760", "4194417761", None]
    print(f"  {'✅' if ok else '❌'} chỉ lấy nhóm 'chưa có số hóa đơn' — dòng CÓ hóa đơn không "
          f"phải đợt giao chờ. Thực tế: {[r['po_no'] for r in rows]}")
    bad += not ok

    ok = rows[0]["total_amount"] == 4_620_000 and rows[0]["amount_before_vat"] == 4_200_000
    print(f"  {'✅' if ok else '❌'} tiền lấy nguyên từ dòng đã chốt, không tính lại")
    bad += not ok

    # ── 2. Chỉ nhận bản ĐÃ CHỐT ─────────────────────────────────────────
    print("-" * 82)
    for status in ("Nháp", "", None):
        store["doc"] = _Doc("MT-OPEN-00001", "WinCommerce", status, LINES)
        try:
            wp._seed_rows_from_opening("MT-OPEN-00001", "HGC")
            ok = False
        except Exception:
            ok = True
        print(f"  {'✅' if ok else '❌'} trạng thái {status!r} -> CHẶN. Bản nháp còn sửa được; "
              f"chốt lại khác đi thì các PO vừa tạo không còn căn cứ")
        bad += not ok

    store["doc"] = _Doc("MT-OPEN-00002", "LOTTE", "Đã chốt", LINES)
    try:
        wp._seed_rows_from_opening("MT-OPEN-00002", "HGC")
        ok = False
    except Exception:
        ok = True
    print(f"  {'✅' if ok else '❌'} bản của chuỗi khác -> CHẶN (danh sách đợt giao chỉ có ở Win)")
    bad += not ok

    store["doc"] = _Doc("MT-OPEN-00003", "WinCommerce", "Đã chốt", LINES, company="KHAC")
    try:
        wp._seed_rows_from_opening("MT-OPEN-00003", "HGC")
        ok = False
    except Exception:
        ok = True
    print(f"  {'✅' if ok else '❌'} bản của công ty khác -> CHẶN")
    bad += not ok

    store["exists"] = False
    try:
        wp._seed_rows_from_opening("KHONG-CO", "HGC")
        ok = False
    except Exception:
        ok = True
    print(f"  {'✅' if ok else '❌'} bản không tồn tại -> CHẶN, không trả danh sách rỗng")
    bad += not ok
    store["exists"] = True

    # ── 3. Chặn theo CÙNG một luật với đường đọc file ───────────────────
    print("-" * 82)
    store["doc"] = DOC
    plan, blocked = wp._plan([
        {"po_no": "P1", "total_amount": 10.0, "amount_before_vat": 9.0,
         "vat_amount": 1.0, "party": "A", "source_row": 1},
        {"po_no": None, "total_amount": 20.0, "amount_before_vat": 18.0,
         "vat_amount": 2.0, "party": "B", "source_row": 2},
        {"po_no": "P1", "total_amount": 30.0, "amount_before_vat": 27.0,
         "vat_amount": 3.0, "party": "C", "source_row": 3},
    ], "HGC")
    ok = [r["po_no"] for r in plan] == ["P1"] and len(blocked) == 2
    print(f"  {'✅' if ok else '❌'} thiếu PO -> chặn; PO TRÙNG NGAY TRONG lần nạp -> chặn "
          f"(dòng thứ hai không thêm gì, chỉ tạo bản ghi đôi)")
    bad += not ok

    frappe.db.sql = lambda *a, **k: [("P9",)]
    plan2, blocked2 = wp._plan([
        {"po_no": "P9", "total_amount": 10.0, "amount_before_vat": 9.0,
         "vat_amount": 1.0, "party": "A", "source_row": 1}], "HGC")
    ok = not plan2 and blocked2 and "đã được theo dõi" in blocked2[0]["reason"]
    print(f"  {'✅' if ok else '❌'} PO đã có trong hệ -> chặn, không tạo bản ghi thứ hai")
    bad += not ok
    frappe.db.sql = lambda *a, **k: []

    # ── 4. HAI ĐƯỜNG DÙNG CHUNG `_plan` và `_write_plan` ────────────────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/mt_win_pending.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    calls = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            calls[n.name] = {c.func.id for c in ast.walk(n)
                             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    ok = ("_plan" in calls.get("preview_seed", set())
          and "_plan" in calls.get("preview_seed_from_opening", set()))
    print(f"  {'✅' if ok else '❌'} hai đường xem trước dùng CHUNG `_plan` — chặn theo hai luật "
          f"khác nhau là tạo hai bản ghi cho cùng một đợt giao")
    bad += not ok

    ok = ("_write_plan" in calls.get("commit_seed", set())
          and "_write_plan" in calls.get("commit_seed_from_opening", set()))
    print(f"  {'✅' if ok else '❌'} hai đường ghi dùng CHUNG `_write_plan`")
    bad += not ok

    # Vân tay kế hoạch phải kiểm Ở TRONG `_write_plan`, không ở từng đường.
    body = src.split("def _write_plan")[1].split("\n@frappe.whitelist")[0]
    ok = "expected_hash != pre[\"plan_hash\"]" in body and "frappe.throw" in body
    print(f"  {'✅' if ok else '❌'} vân tay kế hoạch kiểm Ở MỘT CHỖ — để mỗi đường tự kiểm là "
          f"sớm muộn một đường quên, và đường đó ghi khác thứ đã duyệt")
    bad += not ok

    n_hash = sum(1 for f in ("commit_seed", "commit_seed_from_opening")
                 if "plan_hash" in src.split("def %s" % f)[1].split("\n@frappe")[0].split("\ndef ")[0])
    ok = n_hash == 0
    print(f"  {'✅' if ok else '❌'} và KHÔNG đường nào tự kiểm lại lần nữa (tránh hai luật lệch)")
    bad += not ok

    # ── 5. Guard ─────────────────────────────────────────────────────────
    print("-" * 82)
    want = {"preview_seed_from_opening": "guard_mt()",
            "commit_seed_from_opening": "guard_manager()"}
    miss = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in want:
            b = [x for x in n.body
                 if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant))]
            if not b or ast.unparse(b[0]) != want[n.name]:
                miss.append(n.name)
    ok = not miss
    print(f"  {'✅' if ok else '❌'} guard đúng ở DÒNG ĐẦU (xem trước = kế toán MT, ghi = trưởng)"
          f"{'' if ok else ' — sai: ' + str(miss)}")
    bad += not ok

    # ── 6. Giao diện có tuyến vào ────────────────────────────────────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    ok = 'id="wp-seed-open"' in js and "pickWinPendingFromOpening" in js
    print(f"  {'✅' if ok else '❌'} có nút 'Khởi tạo từ số dư đã chốt' và nó được nối handler")
    bad += not ok

    ok = "runWinPendingSeed" in js and js.count("wp-seed-go") == 2
    print(f"  {'✅' if ok else '❌'} hai đường dùng CHUNG khung xem trước — vẽ hai lần là sớm "
          f"muộn một bên quên hiện phần 'dòng bị chặn', tức ghi ít hơn người duyệt tưởng")
    bad += not ok

    ok = "win.doc.name" in js
    print(f"  {'✅' if ok else '❌'} lấy tên bản ghi từ `doc.name` — `list_openings` trả một dòng "
          f"mỗi chuỗi, tên nằm TRONG `doc`, không ở cấp ngoài")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — chỉ nhận bản đã chốt, hai đường vào chặn và ghi theo cùng một luật")
    return 0


if __name__ == "__main__":
    sys.exit(main())
