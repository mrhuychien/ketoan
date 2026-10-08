#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm ĐỘT BIẾN cho `misa_return_cleanup_check.py`.

Công cụ dọn GHI VÀO CHỨNG TỪ ĐÃ GHI SỔ, nên câu hỏi "bộ kiểm có thấy không khi
nó bị sửa hỏng" không được để ngỏ. Mỗi đột biến dưới đây là một cách làm hỏng
có hậu quả thật — xoá số của chứng từ người ta sửa tay, dọn theo kế hoạch chưa
ai đọc, hay dọn xong mà không còn gì để lùi.

    python3 docs/mt/verified/misa_return_cleanup_mutation_check.py
"""
import io
import os
import shutil
import subprocess
import sys

# .../ketoan/docs/mt/verified/<file> → gốc repo là 3 bậc cha.
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", ".."))
CHECK = "docs/mt/verified/misa_return_cleanup_check.py"
CL = "ketoan/api/misa_return_cleanup.py"

M = [
 ("1. bỏ luật 'chỉ xoá cái giống hệt bản gốc' — xoá cả field người sửa tay", CL,
  """            if cstr(vt) == cstr(vg):
                cu[f] = vt                    # GIỐNG HỆT bản gốc ⇒ là bản chép
            else:
                khac.append(f)""",
  """            cu[f] = vt  # dot bien: xoa bat ke co giong ban goc hay khong"""),

 ("2. vẫn phát hiện field khác nhưng DỌN NỬA VỜI thay vì để người xem", CL,
  "        if khac:\n", "        if False:\n"),

 ("3. bỏ phép đối vân tay — dọn theo kế hoạch chưa ai đọc", CL,
  '    if thuc != cstr(van_tay).strip():', '    if False:'),

 ("4. vân tay chỉ băm TÊN chứng từ, không băm giá trị sắp xoá", CL,
  '''            {"si": r["si"],
             "xoa": {k: cstr(v) for k, v in sorted(r["cu"].items())}}''',
  '''            {"si": r["si"]}'''),

 ("5. ghi đè TRƯỚC rồi mới lưu giá trị cũ (mất điện là mất đường lùi)", CL,
  '''            frappe.get_doc({
                "doctype": "Comment",''',
  '''            frappe.db.set_value("Sales Invoice", r["si"],
                                {f: None for f in r["cu"]}, update_modified=False)
            frappe.get_doc({
                "doctype": "Comment",'''),

 ("6. cờ khóa để None thay vì 0 (rơi khỏi vòng quét 2)", CL,
  'gia_tri["custom_misa_no_locked"] = 0', 'gia_tri["custom_misa_no_locked"] = None'),

 ("7. không cấp RefID mới — vẫn để trùng RefID bản gốc", CL,
  '            gia_tri["custom_misa_ref_id"] = moi\n', ''),

 ("8. ghi mà không khai update_modified=False", CL,
  '''            frappe.db.set_value("Sales Invoice", r["si"], gia_tri, update_modified=False)''',
  '''            frappe.db.set_value("Sales Invoice", r["si"], gia_tri)'''),

 ("9. bỏ chốt 'không có gì để dọn thì im lặng' — mọi trả hàng vào can_tay", CL,
  '''        if all(r.get(f) in (None, "") for f in fields):
            continue''',
  '''        if False:
            continue'''),

 ("10. bỏ chốt 'RefID dùng chung với >1 hóa đơn bán' — dọn cả nhóm lạ", CL,
  '        if len(goc) > 1:', '        if False:'),

 ("11. hoan_tac không soi `moc` — lùi theo Comment của nguồn khác", CL,
  '        if d.get("moc") != MOC or d.get("van_tay") != van_tay:',
  '        if False:'),

 ("12. xem_truoc GHI luôn thay vì chỉ xem", CL,
  '''    ke_hoach, can_tay, bq = _dung_ke_hoach(bo_qua, limit)
    return {
        "van_tay": _van_tay(ke_hoach, bq),''',
  '''    ke_hoach, can_tay, bq = _dung_ke_hoach(bo_qua, limit)
    for _r in ke_hoach:
        frappe.db.set_value("Sales Invoice", _r["si"],
                            {"custom_misa_status": "Chưa đẩy"}, update_modified=False)
    return {
        "van_tay": _van_tay(ke_hoach, bq),'''),
]


def run():
    # Xoá __pycache__ + chạy với -B: hai đột biến xoá cùng số byte, ghi trong
    # cùng một giây, là Python nạp lại .pyc của lần trước — báo đỏ (hoặc XANH)
    # vì mã CŨ. Đã đo được chuyện này ở bộ đột biến chị em.
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
        print(out0[-2000:])
        return 1

    lot, ap = [], 0
    for ten, f, old, new in M:
        path = os.path.join(REPO, f)
        src = io.open(path, encoding="utf-8").read()
        n = src.count(old)
        if n != 1:
            print(f"  ⚠ {ten}: KHÔNG ÁP ĐƯỢC ({n} khớp) — sửa đột biến, "
                  f"đừng bỏ qua")
            lot.append(ten)
            continue
        ap += 1
        io.open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
        try:
            rc1, out1 = run()
        finally:
            io.open(path, "w", encoding="utf-8").write(src)
        if rc1 != 0:
            do = [l.strip() for l in out1.splitlines() if l.strip().startswith("❌")]
            print(f"  ✅ {ten}  → ĐỎ: {do[0][:84] if do else '(nổ giữa chừng)'}")
        else:
            print(f"  ❌ {ten}  → VẪN XANH (bộ kiểm không canh được)")
            lot.append(ten)

    rc2, _ = run()
    print("\nSau khi phục hồi:", "ĐẠT" if rc2 == 0 else "ĐỎ ❌ (file chưa về nguyên)")
    print(f"KẾT: {ap - len(lot)}/{ap} đột biến áp được đã bị bắt")
    return 0 if (not lot and rc2 == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
