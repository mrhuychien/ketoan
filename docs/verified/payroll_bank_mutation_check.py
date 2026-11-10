#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm ĐỘT BIẾN cho `payroll_bank_check.py`.

Mỗi đột biến là một cách làm hỏng file chuyển khoản lương mà vẫn tải về được:
ngân hàng trả file về (sai kiểu ô, mất danh sách thả xuống, đè tiêu đề), hoặc
tệ hơn — nhận file mà tiền đi sai (đoán bừa ngân hàng hưởng, ghi dòng số tiền
0, trang gửi thiếu dòng Ban lãnh đạo). Đột biến nào không làm bộ kiểm đỏ là
bộ kiểm đang canh hớ.

    python3 docs/verified/payroll_bank_mutation_check.py
"""
import io
import os
import shutil
import subprocess
import sys

# .../ketoan/docs/verified/<file> → gốc repo là 2 bậc cha.
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CHECK = "docs/verified/payroll_bank_check.py"
PB = "ketoan/api/payroll_bank.py"
JSF = "ketoan/public/ketoan/views/payroll.js"

M = [
    # ── Kiểu ô / nội dung ô ────────────────────────────────────────────
    ("1. số tiền ghi thành SỐ (mẫu kẻ ô '@', ngân hàng chờ chữ)", PB,
     '"E": ("s", str(tien))', '"E": ("n", tien)'),

    ("2. bỏ Loại tiền 'VND'", PB,
     '"F": ("s", TIEN_TE), ', ''),

    ("3. tên giữ dấu tiếng Việt", PB,
     'return _gon(re.sub(r"[^A-Z0-9&.\\- ]+", " ", _khong_dau(s).upper()))',
     'return _gon(re.sub(r"[^A-Z0-9&.\\- ]+", " ", cstr(s).upper()))'),

    ("4. nội dung chuyển tiền không làm sạch (dấu, '/')", PB,
     "nd = _lam_sach_noi_dung(noi_dung) or NOI_DUNG_MAC_DINH",
     "nd = cstr(noi_dung) or NOI_DUNG_MAC_DINH"),

    ("5. tài khoản không bỏ dấu cách/chấm", PB,
     '''s = re.sub(r"[\\s.\\-,_']+", "", _khong_dau(s))''',
     "s = _khong_dau(s).strip()"),

    ("6. tài khoản dạng số thành '4681729200.0'", PB,
     "    elif isinstance(v, int):\n        s = str(v)",
     "    elif isinstance(v, int):\n        s = str(float(v))"),

    ("7. bỏ cắt tên dài quá 70", PB,
     "            ten = ten[:MAX_TEN].strip()\n", ""),

    # ── Giữ nguyên mẫu ────────────────────────────────────────────────
    ("8. dữ liệu bắt đầu dòng 3 — đè tiêu đề của mẫu", PB,
     "DONG_DAU = 4", "DONG_DAU = 3"),

    ("9. mất tên vùng domesticBanks (như ExcelJS đọc-ghi lại)", PB,
     "            data = zin.read(info.filename)\n",
     "            data = zin.read(info.filename)\n"
     "            if info.filename == 'xl/workbook.xml':\n"
     "                data = re.sub(rb'<definedName name=\"domesticBanks\">.*?</definedName>', b'', data)\n"),

    ("10. không thoát ký tự XML ('&' trong tên làm hỏng file)", PB,
     "else \"\", escape(s))", "else \"\", s)"),

    ("11. uniqueCount không cập nhật", PB,
     '(so_tham_chieu if m.group(1) == "count" else len(moi))',
     '(so_tham_chieu if m.group(1) == "count" else 0)'),

    ("12. count không cập nhật", PB,
     '(so_tham_chieu if m.group(1) == "count" else len(moi))',
     '(0 if m.group(1) == "count" else len(moi))'),

    ("13. mẫu đổi cột mà vẫn điền theo vị trí cũ", PB,
     "        if not cstr(tieu_de.get(cot)).strip().startswith(dau):",
     "        if False:"),

    # ── Ngân hàng hưởng: không đoán ────────────────────────────────────
    ("14. bỏ tra sheet chi nhánh của mẫu", PB,
     '        ma_nh = bang["chi_nhanh"].get(code)', '        ma_nh = None'),

    ("15. bỏ luật 3 số giữa (mã tổ chức tín dụng)", PB,
     '        d = _mot(bang["theo_tctd"].get(code[2:5]))', '        d = None'),

    ("16. kết quả mơ hồ thì lấy đại một ngân hàng", PB,
     "return next(iter(tap)) if len(tap) == 1 else None",
     "return next(iter(tap)) if tap else None"),

    ("17. bỏ chặn địa danh ('Bình Dương' ra ngân hàng Đài Loan)", PB,
     "            if x and x not in DIA_DANH:", "            if x:"),

    ("18. chữ và mã chỉ hai ngân hàng khác nhau mà vẫn theo mã", PB,
     "        if d_ten and d_ten[2:5] != d[2:5]:", "        if False:"),

    ("19. không dò ra thì ghi chữ gốc vào cột D", PB,
     '            vals["D"] = ("s", hien)', '            vals["D"] = ("s", hien)\n        else:\n'
     '            vals["D"] = ("s", cstr(nh_goc))'),

    # ── Báo / chặn ────────────────────────────────────────────────────
    ("20. ghi cả dòng số tiền 0", PB,
     "        if tien <= 0:", "        if tien < 0:"),

    ("21. bỏ báo tài khoản trùng", PB,
     "        if len(ai) > 1:", "        if False:"),

    ("22. bỏ báo thiếu số tài khoản", PB,
     '            canh_bao.append("%s: thiếu số tài khoản" % nhan)', "            pass"),

    ("23. bỏ chặn sức chứa — quá 988 người không bảo tách file", PB,
     '    if len(du_lieu) > m["suc_chua"]:', "    if False:"),

    ("24. bỏ chốt quyền Kế toán tiền lương", PB,
     "    guard_payroll()\n", ""),

    # ── Trang Tính lương ──────────────────────────────────────────────
    ("25. trang gọi sai method", JSF,
     'var BANK_METHOD = "ketoan.api.payroll_bank.xuat_file_chuyen_khoan";',
     'var BANK_METHOD = "ketoan.api.payroll_bank.xuat_file";'),

    ("26. trang không gửi nội dung chuyển tiền", JSF,
     "{ dong: dong, noi_dung: PB.CK_NOIDUNG }", "{ dong: dong }"),

    ("27. trang tải về chuỗi base64 thay vì file", JSF,
     "saveBlob(b64Blob(r.file_b64), fn);", "saveBlob(new Blob([r.file_b64]), fn);"),

    ("28. trang quên dòng Ban lãnh đạo (tổng file lệch tờ tổng hợp)", JSF,
     "    BLD_NGANHANG.forEach(function (b) { data.push([b.ten, b.tk, roundCK(b.tien), b.cn]); });\n",
     ""),
]


def run():
    # Xoá __pycache__ + chạy với -B: hai đột biến cùng số byte ghi trong cùng một
    # giây là Python nạp lại .pyc của lần trước — báo sai vì mã CŨ.
    for d, dirs, _f in os.walk(REPO):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(d, "__pycache__"), ignore_errors=True)
            dirs.remove("__pycache__")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PAYROLL_BANK_NO_SOFFICE="1")
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
