#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm ĐỘT BIẾN cho `misa_return_cleanup_check.py`.

Công cụ dọn GHI VÀO CHỨNG TỪ ĐÃ GHI SỔ, nên câu hỏi "bộ kiểm có thấy không khi
nó bị sửa hỏng" không được để ngỏ. Mỗi đột biến dưới đây là một cách làm hỏng
có hậu quả thật — xoá số kế toán gõ tay, đè mất ghi chú, dọn theo kế hoạch
chưa ai đọc, dọn xong mà không còn gì để lùi.

Đột biến 1 và 2 là ĐÚNG HAI LỖI đã làm bản đầu ra 0 dọn / 479 cần người xem
trên site — bộ kiểm cũ báo xanh với cả hai. Nếu một ngày chúng quay lại, bộ
này phải đỏ.

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

TAP_A_DUOI = '    "custom_misa_org_inv",\n)\n\n# Tiếng ồn'

M = [
    # ── Hai lỗi đã gây ra 0/479 trên site ──────────────────────────────
    ("1. tiếng ồn thành BẰNG CHỨNG: last_checked vào TAP_A (lỗi 0/479 số 1)", CL,
     TAP_A_DUOI,
     '    "custom_misa_org_inv", "custom_misa_last_checked",\n)\n\n# Tiếng ồn'),

    ("2. chốt 'không có gì để dọn' xét cả tiếng ồn (lỗi 0/479 số 2)", CL,
     "        if not a and not ref_muon:\n            continue",
     "        if not a and not ref_muon and not r.get('custom_misa_last_checked'):\n"
     "            continue"),

    ("3. ghi chú vào TAP_A làm bằng chứng", CL,
     TAP_A_DUOI,
     '    "custom_misa_org_inv", "custom_misa_note",\n)\n\n# Tiếng ồn'),

    ("4. ô số cũ vn_einvoice_number vào TAP_A làm bằng chứng", CL,
     TAP_A_DUOI,
     '    "custom_misa_org_inv", "vn_einvoice_number",\n)\n\n# Tiếng ồn'),

    # ── Dữ liệu người ──────────────────────────────────────────────────
    ("5. dọn ô số cũ BẤT KỂ có bằng số đi vay hay không (xoá số gõ tay)", CL,
     "if _co_gia_tri(r.get(f)) and nguon in a and cstr(r.get(f)) == cstr(a[nguon]):",
     "if _co_gia_tri(r.get(f)):"),

    ("6. ĐÈ ô ghi chú thay vì nối thêm", CL,
     'gia_tri["custom_misa_note"] = (cu_note + "\\n" + dong) if cu_note else dong',
     'gia_tri["custom_misa_note"] = dong'),

    ("7. bỏ chốt 'field khác gốc' — dọn cả chứng từ người đã sửa", CL,
     "        if khac:\n", "        if False:\n"),

    # ── Cờ khóa / trạng thái cuối ──────────────────────────────────────
    ("8. khóa chặn kể cả khi GIỐNG gốc (chép theo) — chặn oan", CL,
     "if cint(r.no_locked) and not cint(g.no_locked):", "if cint(r.no_locked):"),

    ("9. bỏ chặn trạng thái cuối khác gốc — dọn 'Đã thay thế' không hỏi ai", CL,
     "if r.trang_thai in TRANG_THAI_CUOI and cstr(r.trang_thai) != cstr(g.trang_thai):",
     "if False:"),

    ("10. bỏ chốt gốc đã hủy", CL,
     "        if cint(g.docstatus) == 2:", "        if False:"),

    ("11. trả hàng không có gốc bị nhồi vào can_tay (nhiễu trở lại)", CL,
     '            _ngoai("khong_goc", r)\n            continue',
     '            can_tay.append({"si": r.name, "ly_do": "khong goc"})\n            continue'),

    # ── Vân tay ────────────────────────────────────────────────────────
    ("12. bỏ phép đối vân tay", CL,
     "    if thuc != van_tay:", "    if False:"),

    ("13. vân tay không băm trạng thái + cờ khóa cũ (sẽ bị ghi đè)", CL,
     '             "tt": cstr(r["trang_thai_cu"]),\n'
     '             "khoa": cint(r["no_locked_cu"]),\n',
     ''),

    # (Không có đột biến "vân tay không băm cho_phep / bo_qua": đó là đột biến
    # TƯƠNG ĐƯƠNG. Hai tham số này chỉ đổi được việc sẽ làm bằng cách đổi KẾ
    # HOẠCH, mà nội dung kế hoạch — tên, giá trị sắp xoá, RefID/trạng thái/cờ
    # cũ — đã được băm (đột biến 13, 15). Không có cách nào ghi khác đi mà vân
    # tay đứng yên. Băm thêm hai tham số là lớp đệm, không phải chốt; viết một
    # phép kiểm giả vờ chúng là chốt thì bộ kiểm nói dối.)

    ("15. vân tay không băm giá trị sắp xoá", CL,
     '             "xoa": {k: cstr(v) for k, v in sorted(r["cu"].items())}}',
     '             }'),

    # ── Ghi ────────────────────────────────────────────────────────────
    ("16. cờ khóa để None thay vì 0 (rơi khỏi vòng quét 2)", CL,
     'gia_tri["custom_misa_no_locked"] = 0', 'gia_tri["custom_misa_no_locked"] = None'),

    ("17. không cấp RefID mới", CL,
     '            gia_tri["custom_misa_ref_id"] = moi\n', ''),

    ("18. ghi mà không khai update_modified=False", CL,
     'frappe.db.set_value("Sales Invoice", r["si"], gia_tri, update_modified=False)',
     'frappe.db.set_value("Sales Invoice", r["si"], gia_tri)'),

    ("19. ghi đè TRƯỚC rồi mới lưu giá trị cũ", CL,
     '            frappe.get_doc({\n                "doctype": "Comment",',
     '            frappe.db.set_value("Sales Invoice", r["si"], {f: None for f in r["cu"]},\n'
     '                                update_modified=False)\n'
     '            frappe.get_doc({\n                "doctype": "Comment",'),

    ("20. xem_truoc GHI luôn", CL,
     "    van_tay = _van_tay(ke_hoach, bo_qua, cho_phep)\n    co_so =",
     "    for _r in ke_hoach:\n"
     "        frappe.db.set_value('Sales Invoice', _r['si'], {'custom_misa_status': 'x'},"
     " update_modified=False)\n"
     "    van_tay = _van_tay(ke_hoach, bo_qua, cho_phep)\n    co_so ="),

    # ── Lùi ────────────────────────────────────────────────────────────
    ("21. hoan_tac không soi `moc` — lùi theo Comment của nguồn khác", CL,
     '        if d.get("moc") != MOC or d.get("van_tay") != van_tay:', '        if False:'),

    ("22. hoan_tac không trả ghi chú cũ", CL,
     '                gia_tri["custom_misa_note"] = d.get("note_cu")', '                pass'),

    # ── Hậu quả lên MT Hàng Hoàn ───────────────────────────────────────
    ("23. đếm MT Hàng Hoàn quên dòng đã có bảng kê siêu thị", CL,
     "a.docstatus < 2)''' if co_bang_ke else \"\"}",
     "a.docstatus < 2)''' if False else \"\"}"),
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
