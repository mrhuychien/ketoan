#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm ĐỘT BIẾN cho `misa_return_nocopy_check.py` — phá từng chỗ sửa, bộ kiểm
PHẢI đỏ.

`misa_return_nocopy_check.py` chứng minh mã HIỆN TẠI chạy đúng. Nó KHÔNG chứng
minh điều quan trọng hơn: mai kia có ai gỡ bộ lọc ra thì bộ kiểm có thấy không.
Bộ này gài lại đúng 22 cách làm hỏng — trong đó hai cái từng là cạm bẫy thật:

  · Gỡ bộ lọc `is_return` mà VẪN ĐẾM (đột biến 7). Khẳng định kiểu "có biến
    so_tra_hang" vẫn đạt y nguyên — đúng cái lỗi "canh định nghĩa thay vì canh
    chỗ dùng".
  · Lọc kiểu SQL `!= 1` / so sánh thẳng `= 0` không bọc IFNULL (đột biến 8, 17)
    làm rụng hàng `is_return = NULL`, tức tắt việc phát hiện hóa đơn bị hủy/bị
    thay thế của TOÀN BỘ chứng từ cũ. Bẫy patch v0_0_17 đã phải chữa một lần.

    python3 docs/mt/verified/misa_return_mutation_check.py   # exit 0 = đạt
"""
import io, os, shutil, subprocess, sys

# .../ketoan/docs/mt/verified/<file> → gốc repo là 4 bậc cha.
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", ".."))
CHECK = "docs/mt/verified/misa_return_nocopy_check.py"

SYNC = "ketoan/api/misa_sync.py"
INST = "ketoan/install.py"
PATCH = "ketoan/patches/v0_0_19/misa_no_copy.py"
DJ = "ketoan/misa_integration/doctype/misa_sync_run/misa_sync_run.json"
VAT = "ketoan/api/misa_vat.py"
VJS = "ketoan/public/ketoan/views/vat.js"

M = [
 ("1. install.py: bỏ no_copy của custom_misa_inv_no", INST,
  '''            "fieldname": "custom_misa_inv_no",
            "no_copy": 1,''',
  '''            "fieldname": "custom_misa_inv_no",'''),

 ("2. install.py: đặt no_copy cho field layout (section)", INST,
  '"fieldname": "custom_misa_section",',
  '"fieldname": "custom_misa_section", "no_copy": 1,'),

 ("3. patch: bỏ phép ghi thẳng, chỉ trông vào setup_misa_integration", PATCH,
  'frappe.db.set_value("Custom Field", name, "no_copy", 1, update_modified=False)',
  'pass  # dot bien'),

 ("4. patch: danh sách FIELDS thiếu một field", PATCH,
  '"custom_misa_no_locked",', '# "custom_misa_no_locked",'),

 ("5. ensure_ref_id: bỏ nhánh is_return (về như trước)", SYNC,
  'if doc.get("amended_from") or doc.get("is_return"):',
  'if doc.get("amended_from"):'),

 ("6. ensure_ref_id: cờ khóa để None thay vì 0", SYNC,
  'doc.custom_misa_no_locked = 0', 'doc.custom_misa_no_locked = None'),

 ("7. poll_pending: GỠ bộ lọc, vẫn ĐẾM (canh định nghĩa sẽ lọt)", SYNC,
  '''    if so_tra_hang:
        rows = [r for r in rows if not cint(r.get("is_return"))]''',
  '''    if False:
        rows = [r for r in rows if not cint(r.get("is_return"))]'''),

 ("8. poll_pending: lọc kiểu SQL `!= 1` — rụng luôn hàng NULL", SYNC,
  'rows = [r for r in rows if not cint(r.get("is_return"))]',
  'rows = [r for r in rows if r.get("is_return") is not None '
  'and not cint(r.get("is_return"))]'),

 ("9. poll_pending: không nói ra số bỏ qua", SYNC,
  '''    stat = {"fetched": 0, "updated": 0, "matched": 0, "mismatched": 0,
            "skipped_return": so_tra_hang}''',
  '    stat = {"fetched": 0, "updated": 0, "matched": 0, "mismatched": 0}'),

 ("10. doctype: ô skipped_return không còn (đổi tên fieldname)", DJ,
  '"fieldname": "skipped_return",', '"fieldname": "skipped_return_DA_XOA",'),

 ("11. doctype: không dời mốc modified", DJ,
  '"modified": "2026-10-08 00:00:00.000000",',
  '"modified": "2026-08-17 00:00:00.000000",'),

 ("12. doctype: thêm field nhưng quên field_order", DJ,
  '  "skipped_return",\n  "log_section",', '  "log_section",'),
 ("13. vat overview: rổ linked không loại trả hàng", VAT,
  """          AND IFNULL(is_return, 0) = 0
          AND IFNULL(custom_misa_inv_no, '') != ''""",
  """          AND IFNULL(custom_misa_inv_no, '') != ''"""),

 ("14. vat overview: rổ erp_only không loại trả hàng", VAT,
  """          AND IFNULL(is_return, 0) = 0
          AND IFNULL(custom_misa_inv_no, '') = ''""",
  """          AND IFNULL(custom_misa_inv_no, '') = ''"""),

 ("15. _si_rows: rổ tra_hang lọc `= 0` thay vì `= 1`", VAT,
  'where = "IFNULL(si.is_return, 0) = 1"',
  'where = "IFNULL(si.is_return, 0) = 0"'),

 ("16. _si_rows: rổ erp_only không loại trả hàng", VAT,
  'where = "IFNULL(si.is_return, 0) = 0 AND IFNULL(si.custom_misa_inv_no, \'\') = \'\'"',
  'where = "IFNULL(si.custom_misa_inv_no, \'\') = \'\'"'),

 ("17. _si_rows: so sánh thẳng `si.is_return = 0`, bỏ IFNULL (bẫy NULL)", VAT,
  'where = "IFNULL(si.is_return, 0) = 0 AND IFNULL(si.custom_misa_inv_no, \'\') != \'\'"',
  'where = "si.is_return = 0 AND IFNULL(si.custom_misa_inv_no, \'\') != \'\'"'),

 ("18. BUCKETS không có tra_hang (get_invoices chặn rổ mới)", VAT,
  'BUCKETS = ("linked", "erp_only", "misa_only", "mismatch", "tra_hang")',
  'BUCKETS = ("linked", "erp_only", "misa_only", "mismatch")'),

 ("19. overview không trả về rổ tra_hang", VAT,
  '            "tra_hang": {"count": tra_hang.cnt, "amount": flt(tra_hang.amt)},\n', ''),

 ("20. si_mismatch không loại trả hàng", VAT,
  """          AND IFNULL(si.is_return, 0) = 0
          AND si.custom_misa_status = 'Lệch tiền'""",
  """          AND si.custom_misa_status = 'Lệch tiền'"""),

 ("21. vat.js: màn hình không có thẻ rổ tra_hang", VJS,
  '{ key: "tra_hang"', '{ key: "tra_hang_DA_XOA"'),

 ("22. vat.js: rổ trả hàng không bày cột Số HĐ", VJS,
  'const linked = tab === "linked" || tab === "tra_hang";',
  'const linked = tab === "linked";'),
]


def run():
    # XOÁ __pycache__ + chạy với -B.
    #
    # Đã ĐO: hai đột biến khác nhau (13 và 14) báo CÙNG MỘT dòng đỏ với cùng
    # con số. Lý do: chúng xoá đúng một dòng giống nhau nên file mutated có
    # CÙNG KÍCH CỠ, và nếu ghi trong cùng một giây thì mtime cũng trùng —
    # Python coi .pyc của lần trước còn hợp lệ và nạp lại mã CŨ. Cùng cơ chế
    # đó có thể báo XANH cho một đột biến thật, tức nói "bộ kiểm canh được"
    # trong khi nó chưa hề chạy mã đã phá.
    for d, dirs, _f in os.walk(REPO):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(d, "__pycache__"), ignore_errors=True)
            dirs.remove("__pycache__")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-B", CHECK], cwd=REPO,
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def main():
    rc0, out0 = run()
    print("GỐC:", "ĐẠT" if rc0 == 0 else "ĐỎ (phải sửa trước khi đột biến)")
    if rc0 != 0:
        print(out0[-2000:]); return 1

    lot = []
    for i, (ten, f, old, new) in enumerate(M, 1):
        path = os.path.join(REPO, f)
        src = io.open(path, encoding="utf-8").read()
        n = src.count(old)
        if n != 1:
            print(f"  ⚠ {ten}: KHÔNG ÁP ĐƯỢC ({n} khớp)")
            lot.append(ten); continue
        io.open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
        try:
            rc1, out1 = run()
        finally:
            io.open(path, "w", encoding="utf-8").write(src)
        if rc1 != 0:
            do = [l.strip() for l in out1.splitlines() if l.strip().startswith("❌")]
            print(f"  ✅ {ten}  → ĐỎ: {do[0][:88] if do else ''}")
        else:
            print(f"  ❌ {ten}  → VẪN XANH (bộ kiểm không canh được)")
            lot.append(ten)

    rc2, _ = run()
    print("\nSau khi phục hồi:", "ĐẠT" if rc2 == 0 else "ĐỎ ❌ (file chưa về nguyên)")
    print(f"KẾT: {len(M) - len(lot)}/{len(M)} đột biến bị bắt")
    return 0 if (not lot and rc2 == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
