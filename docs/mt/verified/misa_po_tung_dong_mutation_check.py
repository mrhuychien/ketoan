#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm ĐỘT BIẾN cho `misa_po_tung_dong_check.py`.

Mỗi đột biến là một cách làm hỏng luật "số PO trên từng dòng hàng" mà hóa đơn
vẫn phát hành được — tức là lọt ra MISA và chỉ sửa được bằng hóa đơn thay thế.
Đột biến nào không làm bộ kiểm đỏ là bộ kiểm đang canh hớ.

    python3 docs/mt/verified/misa_po_tung_dong_mutation_check.py
"""
import io
import os
import shutil
import subprocess
import sys

# .../ketoan/docs/mt/verified/<file> → gốc repo là 3 bậc cha.
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", ".."))
CHECK = "docs/mt/verified/misa_po_tung_dong_check.py"
MP = "ketoan/api/misa_push.py"

M = [
    ("1. không nối hậu tố vào dòng hàng", MP,
     '                l["Description"] = mo_ta + hau_to', '                pass'),

    ("2. áp luật cho MỌI khách", MP,
     "    if _po_tung_dong(si):", "    if True:"),

    ("3. ORION VINA vẫn bị thêm dòng ghi chú PO riêng", MP,
     "    elif po_no and si.customer not in PO_COMMA",
     "    if po_no and si.customer not in PO_COMMA"),

    ("4. chỉ khớp mã khách, bỏ tên khách", MP,
     '(_chuan_ten(si.get("customer")), _chuan_ten(si.get("customer_name")))',
     '(_chuan_ten(si.get("customer")),)'),

    ("5. khớp phân biệt hoa/thường", MP,
     '    return " ".join(cstr(s).upper().split())',
     '    return " ".join(cstr(s).split())'),

    ("6. không gộp khoảng trắng thừa", MP,
     '    return " ".join(cstr(s).upper().split())',
     '    return cstr(s).upper()'),

    ("7. ORION VINA thiếu Số PO mà vẫn phát hành", MP,
     "        if not po_no:\n            frappe.throw(_(",
     "        if False:\n            frappe.throw(_("),

    ("8. nối hậu tố hai lần khi tên hàng đã có sẵn", MP,
     "            if not mo_ta.endswith(hau_to):", "            if True:"),

    ("9. viết LIỀN số PO '-PO4500123456' (đúng lỗi kế toán đã báo)", MP,
     'hau_to = f"-PO {po_no}"', 'hau_to = f"-PO{po_no}"'),

    ("9b. sai khuôn hậu tố (' PO' thay vì '-PO')", MP,
     'hau_to = f"-PO {po_no}"', 'hau_to = f" PO {po_no}"'),

    ("10. chỉ nối vào dòng đầu tiên", MP,
     "        for l in lines:\n            mo_ta = cstr(l.get(\"Description\"))",
     "        for l in lines[:1]:\n            mo_ta = cstr(l.get(\"Description\"))"),
]


def run():
    # Xoá __pycache__ + chạy với -B: hai đột biến cùng số byte ghi trong cùng một
    # giây là Python nạp lại .pyc của lần trước — báo sai vì mã CŨ.
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

    lot = []
    for ten, f, old, new in M:
        path = os.path.join(REPO, f)
        src = io.open(path, encoding="utf-8").read()
        n = src.count(old)
        if n != 1:
            print(f"  ⚠ {ten}: KHÔNG ÁP ĐƯỢC ({n} khớp) — sửa đột biến, đừng bỏ qua")
            lot.append(ten)
            continue
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
    print(f"KẾT: {len(M) - len(lot)}/{len(M)} đột biến bị bắt")
    return 0 if (not lot and rc2 == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
