#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm ĐỘT BIẾN cho `payroll_bank_check.py`.

Mỗi đột biến là một cách làm hỏng file chuyển khoản lương mà vẫn tải về được:
ngân hàng trả file về (sai kiểu ô, mất danh sách thả xuống, đè tiêu đề, ô ngân
hàng không đúng chuỗi trong danh sách), hoặc tệ hơn — nhận file mà tiền đi sai
(tự đoán ngân hàng hưởng, ghi dòng số tiền 0, trang gửi thiếu dòng Ban lãnh
đạo), hoặc lệnh đổi dữ liệu ghi chuỗi sai. Đột biến nào không làm bộ kiểm đỏ
là bộ kiểm đang canh hớ.

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
SQL = "docs/luong/sql/doi_ngan_hang_2026_11.sql"

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

    # ── Ngân hàng hưởng: nguyên văn phiếu lương, soi theo danh sách ──────
    ("14. cột D bỏ dấu/IN HOA thay vì chuỗi phiếu lương", PB,
     '            vals["D"] = ("s", nh)                  # phiếu lương (đã đổi 3 chuỗi cũ)',
     '            vals["D"] = ("s", _lam_sach_ten(nh))'),

    ("15. cột D tự đoán một ngân hàng khi phiếu ghi sai", PB,
     '            vals["D"] = ("s", nh)                  # phiếu lương (đã đổi 3 chuỗi cũ)',
     '            vals["D"] = ("s", VI_DU_NH if ly_do else nh)'),

    ("16. ô sai danh sách thì để trống cột D (mất dấu vết để sửa)", PB,
     '        if nh:\n            vals["D"]', '        if nh and not ly_do:\n            vals["D"]'),

    ("17. không gộp khoảng trắng (xuống dòng lọt vào ô)", PB,
     'cstr(s))\n    return re.sub(r"\\s+", " ", s).strip()',
     'cstr(s))\n    return s.strip()'),

    ("18. không bỏ ký tự điều khiển (\\x07 làm hỏng file)", PB,
     '    s = re.sub(r"[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]", "", cstr(s))\n',
     '    s = cstr(s)\n'),

    ("19. bỏ báo ô không có trong danh sách của mẫu", PB,
     '    if goc not in (danh_sach if danh_sach is not None else _doc_mau()["danh_sach"]):',
     '    if False:'),

    ("20. so danh sách không phân biệt hoa/thường", PB,
     '    if goc not in (danh_sach if danh_sach is not None else _doc_mau()["danh_sach"]):',
     '    if goc.upper() not in {x.upper() for x in (danh_sach if danh_sach is not None '
     'else _doc_mau()["danh_sach"])}:'),

    ("21. bỏ báo phiếu chưa ghi ngân hàng", PB,
     '            canh_bao.append("%s: %s — cột Ngân hàng hưởng để trống" % (nhan, ly_do))',
     '            pass'),

    ("22. đọc danh sách sai cột (mã thay vì chuỗi ngân hàng)", PB,
     '    return {cstr(nh_rows[r].get("C")).strip() for r in nh_rows\n'
     '            if r >= 2 and cstr(nh_rows[r].get("C")).strip()}',
     '    return {cstr(nh_rows[r].get("B")).strip() for r in nh_rows\n'
     '            if r >= 2 and cstr(nh_rows[r].get("B")).strip()}'),

    # ── Đổi ba chuỗi ngân hàng cũ kế toán gửi ─────────────────────────
    ("22b. bỏ đổi ba chuỗi cũ khi xuất (tháng 10 vẫn ra 'NHTMCP DTPT…')", PB,
     "    return _DOI.get(_khoa_doi(nh), nh)", "    return nh"),

    ("22c. đổi lan sang chi nhánh KHÔNG được gửi (so bỏ mã 8 số)", PB,
     '    return re.sub(r"\\s+", "", s).upper()', '    return re.sub(r"\\s+|\\d+$", "", s).upper()'),

    ("22d. so phân biệt hoa/thường (ô gõ chữ thường không đổi)", PB,
     '    return re.sub(r"\\s+", "", s).upper()', '    return re.sub(r"\\s+", "", s)'),

    ("22e. không thống nhất dấu gạch ('–' không đổi)", PB,
     '    s = re.sub(r"[\\u2010-\\u2015\\u2212]", "-", _khong_dau(_nguyen_van(s)))',
     '    s = _khong_dau(_nguyen_van(s))'),

    ("22f. không bỏ dấu tiếng Việt khi so ('HẢI DƯƠNG' không đổi)", PB,
     '    s = re.sub(r"[\\u2010-\\u2015\\u2212]", "-", _khong_dau(_nguyen_van(s)))',
     '    s = re.sub(r"[\\u2010-\\u2015\\u2212]", "-", _nguyen_van(s))'),

    ("22g. không ghi chú chuỗi đã đổi", PB,
     "            da_doi[k] = da_doi.get(k, 0) + 1", "            pass"),

    ("22h. trang không đưa cảnh báo ra Nhật ký", JSF,
     '    cb.forEach(function (m) { log("• " + m, "err"); });\n', ""),

    ("22i. trang không đưa ghi chú chuỗi đã đổi ra Nhật ký", JSF,
     '    gc.forEach(function (m) { log("• " + m, "info"); });\n', ""),

    # ── Báo / chặn ────────────────────────────────────────────────────
    ("23. ghi cả dòng số tiền 0", PB,
     "        if tien <= 0:", "        if tien < 0:"),

    ("24. bỏ báo tài khoản trùng", PB,
     "        if len(ai) > 1:", "        if False:"),

    ("25. bỏ báo thiếu số tài khoản", PB,
     '            canh_bao.append("%s: thiếu số tài khoản" % nhan)', "            pass"),

    ("26. bỏ chặn sức chứa — quá 988 người không bảo tách file", PB,
     '    if len(du_lieu) > m["suc_chua"]:', "    if False:"),

    ("27. bỏ chốt quyền Kế toán tiền lương", PB,
     "    guard_payroll()\n", ""),

    # ── Trang Tính lương ──────────────────────────────────────────────
    ("28. trang gọi sai method", JSF,
     'var BANK_METHOD = "ketoan.api.payroll_bank.xuat_file_chuyen_khoan";',
     'var BANK_METHOD = "ketoan.api.payroll_bank.xuat_file";'),

    ("29. trang không gửi nội dung chuyển tiền", JSF,
     "{ dong: dong, noi_dung: PB.CK_NOIDUNG }", "{ dong: dong }"),

    ("30. trang tải về chuỗi base64 thay vì file", JSF,
     "saveBlob(b64Blob(r.file_b64), fn);", "saveBlob(new Blob([r.file_b64]), fn);"),

    ("31. trang quên dòng Ban lãnh đạo (tổng file lệch tờ tổng hợp)", JSF,
     "    BLD_NGANHANG.forEach(function (b) { data.push([b.ten, b.tk, roundCK(b.tien), b.cn]); });\n",
     ""),

    ("32. 8 dòng Ban lãnh đạo vẫn ghi chi nhánh dạng cũ", JSF,
     'var NH_BIDV = "01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV";',
     'var NH_BIDV = "NHTMCP DTPT VN-CN HAI DUONG - 31202005";'),

    # ── Lệnh đổi dữ liệu ──────────────────────────────────────────────
    ("33. lệnh SQL gõ sai chuỗi đích ('Quoc te' thay vì 'Quoc Te')", SQL,
     "UPDATE `tabSalaryProduct`\n   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'",
     "UPDATE `tabSalaryProduct`\n   SET nganhang = '79314013 - Ngan hang TMCP Quoc te Viet Nam - VIB'"),

    ("34. lệnh SQL quên chi nhánh Thành Đông ở bảng công khoán", SQL,
     "UPDATE `tabSalaryProduct`\n   SET nganhang = '01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV'\n"
     " WHERE BINARY TRIM(nganhang) IN ('NHTMCP DTPT VN-CN HAI DUONG - 31202005',\n"
     "                                 'NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004');",
     "UPDATE `tabSalaryProduct`\n   SET nganhang = '01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV'\n"
     " WHERE BINARY TRIM(nganhang) IN ('NHTMCP DTPT VN-CN HAI DUONG - 31202005');"),

    ("34b. lệnh SQL so lỏng (bỏ dấu cách) — đổi cả chuỗi kế toán KHÔNG gửi", SQL,
     "UPDATE `tabSalaryDay`\n   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'\n"
     " WHERE BINARY TRIM(nganhang) = 'NHTMCP QUOC TE VN-CN HAI DUONG-31314003';",
     "UPDATE `tabSalaryDay`\n   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'\n"
     " WHERE REPLACE(nganhang, ' ', '') = 'NHTMCPQUOCTEVN-CNHAIDUONG-31314003';"),

    ("35. lệnh SQL bỏ bước sao lưu", SQL,
     "CREATE TABLE IF NOT EXISTS `_bk_nganhang_2026_11` AS", "-- (bỏ sao lưu)"),
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
