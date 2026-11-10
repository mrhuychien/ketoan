#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""payroll_bank_check — file "Chuyển khoản ngân hàng" phải là MẪU CỦA NGÂN HÀNG.

Ngân hàng đổi mẫu chi lương (11/2026). Mẫu mới do hệ thống ngân hàng sinh ra,
khóa cấu trúc, có danh sách thả xuống — tức là ngân hàng đọc file theo khuôn
của họ. File xuất ra lấy CHÍNH mẫu đó (`ketoan/mau/ck_luong_ngan_hang.xlsx`)
rồi điền dòng từ dòng 4. Phép kiểm này canh sáu điều, mỗi điều một cách file
bị ngân hàng trả về — hoặc tệ hơn, được nhận mà tiền đi sai:

  1. Mọi phần của mẫu ngoài sheet đầu và bảng chuỗi GIỮ NGUYÊN TỪNG BYTE —
     tên vùng `domesticBanks`… (danh sách thả xuống dựa vào), khóa cấu trúc,
     sheet ẩn `Param`. Dòng chưa điền giữ nguyên như mẫu.
  2. Mỗi ô đúng kiểu mẫu đòi: STT là số; tài khoản, số tiền là CHỮ (ô "@");
     Loại tiền "VND"; tên không dấu IN HOA; nội dung chỉ chữ/số/./-.
  3. "Ngân hàng hưởng" là ĐÚNG MỘT chuỗi trong danh sách của mẫu, dò từ ô
     ngân hàng trên phiếu lương ("<chi nhánh> - <mã 8 số>" của mẫu cũ, hoặc
     tên). Không dò ra / chữ và mã chỉ hai ngân hàng khác nhau ⇒ để TRỐNG và
     báo — không đoán.
  4. Báo đủ: thiếu tài khoản, chưa dò ra ngân hàng, tài khoản trùng; số tiền
     ≤ 0 không ghi. Quá sức chứa của mẫu ⇒ dừng, không cắt bớt người.
  5. Mẫu đổi cột ⇒ dừng, không điền theo vị trí cũ.
  6. Trang Tính lương gửi ĐÚNG dòng nó tính: chạy payroll.js thật trong node,
     tổng file = ô "Lương chuyển khoản" của tờ tổng hợp (`computeAgg`).

Chạy KHÔNG cần bench:
    python3 docs/verified/payroll_bank_check.py   # exit 0 = đạt
"""

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
JS = os.path.join(REPO, "ketoan/public/ketoan/views/payroll.js")
MAU = os.path.join(REPO, "ketoan/mau/ck_luong_ngan_hang.xlsx")
sys.path.insert(0, os.path.join(REPO, "docs/mt/verified"))

import regression_check as rc  # noqa: E402

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


def muc(t):
    print("-" * 78)
    print("── " + t + " " + "─" * max(0, 70 - len(t)))


BIDV = "01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV"
VCB = "01203001 - Ngan hang TMCP Ngoai thuong Viet Nam - Vietcombank"
VIB_CN = "01314001 - NHTMCP QUOC TE VN - NHTMCP QUOC TE VN"
MB = "01311001 - Ngan hang TMCP Quan Doi - MB"
HDB = "79321001 - Ngan hang Phat trien TP.HCM - HD BANK"

DONG = [
    # tên chủ TK, số TK, số tiền, ô ngân hàng trên phiếu lương
    ["NGUYEN THI NGA", "8848292453", 15500000, "NHTMCP DTPT VN-CN HAI DUONG - 31202005"],
    ["Nguyễn Văn Ánh", "8848 292.999", 6150000, "Vietcombank Hải Dương"],
    ["Trần Thị Bé", "", 5575000, "BIDV"],
    ["Lê Văn Cường", "123456789", 0, "BIDV"],
    ["Phạm Thị D & Co. (HD)", "12-34.56", 7600000, "không biết"],
    ["Đỗ Đức Đạt", "8848292453", 1000000, "31202004"],
    ["Hoàng Thị E", 4681729200, 2000000.4, "BIDV - 31203004"],
    ["Vũ Văn F", "0011223344", -50000, "BIDV"],
]
NOI_DUNG = "CK LƯƠNG T09/2026"


def doc_xml(z, name):
    import xml.etree.ElementTree as ET
    return ET.fromstring(z.read(name))


def dong_xml(xml, r):
    m = re.search(r'<row r="%d"[^>]*>.*?</row>' % r, xml, re.S)
    return m.group(0) if m else None


def main():
    fr = rc._stub_frappe()
    sys.path.insert(0, REPO)
    import importlib
    import openpyxl

    pb = importlib.import_module("ketoan.api.payroll_bank")

    print("=" * 78)
    print("payroll_bank_check — Chuyển khoản lương theo đúng mẫu của ngân hàng")
    print("=" * 78)

    data, info = pb.dung_file(DONG, NOI_DUNG)
    zt, zo = zipfile.ZipFile(MAU), zipfile.ZipFile(io.BytesIO(data))
    wb = openpyxl.load_workbook(io.BytesIO(data))
    wt = openpyxl.load_workbook(MAU)
    ws = wb.worksheets[0]

    # ── 1. Giữ nguyên mẫu ──────────────────────────────────────────────
    muc("1. Ngoài sheet đầu + bảng chuỗi, file GIỮ NGUYÊN TỪNG BYTE của mẫu")
    ten_t = [i.filename for i in zt.infolist()]
    check("cùng các phần, cùng thứ tự trong gói", ten_t == [i.filename for i in zo.infolist()])
    khac = [n for n in ten_t if zt.read(n) != zo.read(n)]
    check("chỉ `sheet1.xml` và `sharedStrings.xml` đổi",
          sorted(khac) == ["xl/sharedStrings.xml", "xl/worksheets/sheet1.xml"], str(khac))
    check("tên sheet + thứ tự như mẫu", wb.sheetnames == wt.sheetnames, str(wb.sheetnames))
    check("sheet `Param` vẫn ẩn", wb["Param"].sheet_state == "hidden")
    check("tên vùng danh sách thả xuống còn đủ (domesticBanks, transferCcys, branch_bank_*)",
          set(wb.defined_names.keys()) >= {"domesticBanks", "transferCcys",
                                           "branch_bank_code", "branch_bank_name"},
          str(list(wb.defined_names.keys())))
    dv = {str(d.sqref): (d.formula1 or "").strip() for d in ws.data_validations.dataValidation}
    check("ô D/F/K vẫn là danh sách chọn như mẫu",
          dv.get("D4:D991") == "domesticBanks" and dv.get("F4:F991") == "transferCcys"
          and dv.get("K4:K991", "").startswith("OFFSET(branch_bank_name"), str(dv)[:90])
    check("cấu trúc sổ vẫn khóa", bool(wb.security and wb.security.lockStructure))
    sx_t = zt.read("xl/worksheets/sheet1.xml").decode()
    sx_o = zo.read("xl/worksheets/sheet1.xml").decode()
    n = info["so_dong"]
    check("dòng 1–3 (ghi chú + tiêu đề) nguyên văn",
          all(dong_xml(sx_t, r) == dong_xml(sx_o, r) for r in (1, 2, 3)))
    check("dòng chưa điền (sau dòng cuối) nguyên văn như mẫu",
          all(dong_xml(sx_t, r) == dong_xml(sx_o, r) for r in range(4 + n, 992)))
    check("phần sau dữ liệu (khóa ô, lọc, danh sách chọn, lề in) nguyên văn",
          sx_t[sx_t.index("</sheetData>"):] == sx_o[sx_o.index("</sheetData>"):])

    # ── 2. Kiểu từng ô ──────────────────────────────────────────────────
    muc("2. Đúng kiểu ô mẫu đòi — STT số; tài khoản, số tiền là CHỮ")
    rows = [[ws.cell(r, c).value for c in range(1, 16)] for r in range(4, 4 + n)]
    kieu = [[ws.cell(r, c).data_type for c in range(1, 8)] for r in range(4, 4 + n)]
    check("ghi 6/8 dòng (2 dòng số tiền ≤ 0 bỏ qua)", n == 6 and len(info["bo_qua"]) == 2, str(n))
    check("STT là SỐ 1..6", [x[0] for x in rows] == [1, 2, 3, 4, 5, 6]
          and all(k[0] == "n" for k in kieu))
    check("tên: không dấu, IN HOA, chỉ chữ/số/&/-/.",
          [x[1] for x in rows] == ["NGUYEN THI NGA", "NGUYEN VAN ANH", "TRAN THI BE",
                                   "PHAM THI D & CO. HD", "DO DUC DAT", "HOANG THI E"],
          str([x[1] for x in rows]))
    check("tài khoản là CHỮ, bỏ dấu cách/chấm/gạch; ô thiếu để trống",
          [x[2] for x in rows] == ["8848292453", "8848292999", None, "123456",
                                   "8848292453", "4681729200"]
          and all(kieu[i][2] == "s" for i in (0, 1, 3, 4, 5)), str([x[2] for x in rows]))
    check("số tiền là CHỮ chỉ gồm chữ số (ô '@' của mẫu), làm tròn đồng",
          [x[4] for x in rows] == ["15500000", "6150000", "5575000", "7600000", "1000000", "2000000"]
          and all(k[4] == "s" for k in kieu), str([x[4] for x in rows]))
    check("Loại tiền = 'VND' mọi dòng", all(x[5] == "VND" for x in rows))
    check("nội dung: bỏ dấu, bỏ ký tự ngoài chữ/số/./- ('CK LUONG T09 2026')",
          all(x[6] == "CK LUONG T09 2026" for x in rows), str(rows[0][6]))
    check("cột H..O (giấy tờ, chi nhánh, mã GD, bổ sung) để trống",
          all(v is None for x in rows for v in x[7:]))
    ten_ok = all(re.fullmatch(r"[A-Z0-9&.\- ]{1,70}", x[1] or "") for x in rows)
    check("tên ≤ 70 ký tự hợp lệ", ten_ok)

    # ── 3. Ngân hàng hưởng ─────────────────────────────────────────────
    muc("3. 'Ngân hàng hưởng' = ĐÚNG MỘT chuỗi trong danh sách của mẫu")
    ds = {wt["DS ngân hàng hưởng_Bank list"].cell(r, 3).value
          for r in range(2, wt["DS ngân hàng hưởng_Bank list"].max_row + 1)}
    cot_d = [x[3] for x in rows]
    check("mọi ô đã điền đều nằm trong danh sách", all(d in ds for d in cot_d if d))
    check("theo mã chi nhánh 31202005 / mã 31202004 ⇒ BIDV",
          cot_d[0] == BIDV and cot_d[4] == BIDV, str(cot_d))
    check("theo tên 'Vietcombank Hải Dương' ⇒ Vietcombank, 'BIDV' ⇒ BIDV",
          cot_d[1] == VCB and cot_d[2] == BIDV)
    check("không nhận ra ('không biết') ⇒ để TRỐNG, không đoán", cot_d[3] is None)
    check("chữ 'BIDV' mà mã 31203004 là chi nhánh Vietcombank ⇒ TRỐNG", cot_d[5] is None)

    bang = pb._doc_mau()["bang"]
    ca = [
        ("NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004", BIDV, "ma"),
        ("01202001", BIDV, "ma"),
        ("31202099", BIDV, "ma"),        # chi nhánh lạ: 3 số giữa = BIDV
        ("NHTMCP QUOC TE VN CN HAI DUONG - 31314003", VIB_CN, "ma"),  # 3 số giữa mơ hồ, sheet chi nhánh chỉ rõ
        ("CN HAI DUONG - 31202005", BIDV, "ma"),
        ("NHTMCP DTPT VN-CN HAI DUONG", BIDV, "ten"),
        ("Ngân hàng BIDV", BIDV, "ten"),
        ("VCB", VCB, "ten"),
        ("MBBank", MB, "ten"),
        ("Ngân hàng TMCP Quân đội", MB, "ten"),
        ("HDBank", HDB, "ten"),
    ]
    for text, mong, cach in ca:
        d, c, _ = pb.tim_ngan_hang(text, bang)
        check(f"“{text}” ⇒ {mong.split(' - ')[-1]} (theo {cach})", d == mong and c == cach, f"{d} / {c}")
    for text, ly in [("Vietcombank - 31202005", "hai ngân hàng khác nhau"),
                     ("99999999", "không có trong danh sách"),
                     ("NH NHA NUOC - 31101001", "ứng với 2 dòng"),
                     ("Ngân hàng TMCP Sài Gòn", "khớp 2 ngân hàng"),
                     ("NH NHA NUOC CN HAI DUONG", "khớp"),
                     ("Bình Dương", "không nhận ra"),
                     ("", "chưa ghi ngân hàng"), (None, "chưa ghi ngân hàng")]:
        d, c, ld = pb.tim_ngan_hang(text, bang)
        check(f"“{text}” ⇒ KHÔNG đoán ({ly})", d is None and ly in ld, f"{d} / {ld}")

    # ── 4. Báo đủ ──────────────────────────────────────────────────────
    muc("4. Báo đủ chỗ cần sửa; số tiền ≤ 0 không ghi; quá sức chứa thì dừng")
    cb = "\n".join(info["canh_bao"])
    check("báo thiếu số tài khoản (3. TRAN THI BE)", "3. TRAN THI BE: thiếu số tài khoản" in cb)
    check("báo chưa dò ra ngân hàng, nêu chữ gốc trên phiếu",
          "4. PHAM THI D & CO. HD: chưa xác định được Ngân hàng hưởng từ “không biết”" in cb)
    check("báo chữ và mã chỉ hai ngân hàng khác nhau (6. HOANG THI E)",
          "6. HOANG THI E: chưa xác định" in cb and "hai ngân hàng khác nhau" in cb)
    check("báo tài khoản 8848292453 trùng (1 và 5)",
          "số tài khoản 8848292453 xuất hiện 2 lần (1. NGUYEN THI NGA; 5. DO DUC DAT)" in cb)
    check("số tiền 0 và âm KHÔNG ghi, có báo",
          any("LE VAN CUONG" in x for x in info["bo_qua"]) and any("VU VAN F" in x for x in info["bo_qua"]))
    check("dò theo tên thì ghi chú để liếc lại",
          any("Vietcombank Hải Dương" in x for x in info["ghi_chu"]))
    check("tổng tiền = cộng cột số tiền (37.825.000)",
          info["tong_tien"] == 37825000 == sum(int(x[4]) for x in rows), str(info["tong_tien"]))
    d2, i2 = pb.dung_file([["Nguyen Van A " * 8, "1", 1, "BIDV"]], "CK")
    b4 = openpyxl.load_workbook(io.BytesIO(d2)).worksheets[0].cell(4, 2).value or ""
    check("tên dài quá 70 ⇒ cắt còn ≤ 70 + báo",
          0 < len(b4) <= 70 and any("cắt bớt" in x for x in i2["canh_bao"]), f"{len(b4)} ký tự")
    d3, _ = pb.dung_file([["A", "1", 1, "BIDV"]] * 988, "CK")
    w3 = openpyxl.load_workbook(io.BytesIO(d3)).worksheets[0]
    check("đủ 988 dòng (sức chứa của mẫu) ⇒ ghi tới dòng 991",
          w3.cell(991, 1).value == 988 and w3.cell(991, 5).value == "1")
    try:
        pb.dung_file([["A", "1", 1, "BIDV"]] * 989, "CK")
        loi = ""
    except Exception as e:  # noqa: BLE001
        loi = str(e)
    check("989 dòng ⇒ DỪNG, bảo tách file (không cắt bớt người)", "tách thành nhiều file" in loi, loi[:60])

    sst = zo.read("xl/sharedStrings.xml").decode()
    head = re.search(r"<sst[^>]*>", sst).group(0)
    so_si = sst.count("<si>")
    check("bảng chuỗi: uniqueCount = số chuỗi thật", f'uniqueCount="{so_si}"' in head, head[:60])
    so_ref = sx_o.count(' t="s"><v>') - sx_t.count(' t="s"><v>')
    goc = int(re.search(r'count="(\d+)"', re.search(r"<sst[^>]*>", zt.read("xl/sharedStrings.xml").decode()).group(0)).group(1))
    check("bảng chuỗi: count tăng đúng số ô chữ vừa ghi",
          f'count="{goc + so_ref}"' in head, f"{head[:40]} / +{so_ref}")

    # ── 5. Mẫu đổi cột ⇒ dừng ──────────────────────────────────────────
    muc("5. Mẫu đổi thứ tự cột ⇒ DỪNG, không điền theo vị trí cũ")
    tmp = tempfile.mkdtemp()
    try:
        lech = os.path.join(tmp, "mau_lech.xlsx")
        with zipfile.ZipFile(MAU) as zi, zipfile.ZipFile(lech, "w", zipfile.ZIP_DEFLATED) as zw:
            for it in zi.infolist():
                b = zi.read(it.filename)
                if it.filename == "xl/worksheets/sheet1.xml":
                    s = b.decode()
                    s = s.replace('<c r="B3" s="13" t="s"><v>5</v>', '<c r="B3" s="13" t="s"><v>@@</v>', 1)
                    s = s.replace('<c r="C3" s="14" t="s"><v>6</v>', '<c r="C3" s="14" t="s"><v>5</v>', 1)
                    s = s.replace('<v>@@</v>', '<v>6</v>', 1)
                    b = s.encode()
                zw.writestr(it, b)
        try:
            pb.dung_file(DONG, "CK", path=lech)
            loi = ""
        except Exception as e:  # noqa: BLE001
            loi = str(e)
        check("đổi chỗ cột B/C trong mẫu ⇒ báo 'đã đổi cột'", "đã đổi cột" in loi, loi[:70])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── 6. Đường gọi thật ──────────────────────────────────────────────
    muc("6. Trang Tính lương gửi đúng dòng; hàm whitelisted có chốt quyền")
    try:
        fr.get_roles = lambda *a, **k: []
        pb.xuat_file_chuyen_khoan(dong=DONG)
        bi_chan = False
    except Exception as e:  # noqa: BLE001
        bi_chan = "Kế toán tiền lương" in str(e)
    check("không có vai trò Kế toán tiền lương ⇒ bị chặn", bi_chan)
    fr.get_roles = lambda *a, **k: ["Ke Toan Tien Luong"]
    r = pb.xuat_file_chuyen_khoan(dong=json.dumps(DONG), noi_dung=NOI_DUNG)
    check("có vai trò ⇒ trả base64 đúng file, kèm cảnh báo",
          base64.b64decode(r["file_b64"]) == data and r["canh_bao"] == info["canh_bao"])

    js = run_js()
    if js is None:
        check("chạy payroll.js trong node", False, "node lỗi")
    else:
        check("payroll.js gọi đúng method + gửi nội dung CK_NOIDUNG",
              js["call"]["method"] == "ketoan.api.payroll_bank.xuat_file_chuyen_khoan"
              and js["call"]["args"].get("noi_dung") == "CK LUONG", str(js["call"])[:90])
        check("dòng gửi đi = dòng `buildFile('nganhang')` tính (công nhật + khoán có BH + Ban lãnh đạo)",
              js["call"]["args"].get("dong") == js["dong"] and len(js["dong"]) == 11, str(len(js["dong"])))
        check("file tải về là đúng bytes máy chủ trả", js["saved"] == js["sent_b64"])
        _, ij = pb.dung_file(js["dong"], "CK LUONG")
        check("tổng file = ô 'Lương chuyển khoản' của tờ tổng hợp (computeAgg.tong_ck)",
              ij["tong_tien"] == round(js["tong_ck"]), f"{ij['tong_tien']} / {js['tong_ck']}")
        check("8 dòng Ban lãnh đạo (ghi cứng trong payroll.js) đều ra BIDV theo MÃ chi nhánh",
              all(pb.tim_ngan_hang(x[3], bang)[:2] == (BIDV, "ma") for x in js["dong"][-8:]),
              str([x[3][-8:] for x in js["dong"][-8:]]))
        check("không cảnh báo nào cho bộ dữ liệu sạch", ij["canh_bao"] == [], str(ij["canh_bao"])[:90])

    # Bộ đột biến tắt bước này cho nhanh (28 lần × vài giây); chạy tay thì có.
    so = None if os.environ.get("PAYROLL_BANK_NO_SOFFICE") else (
        shutil.which("soffice") or shutil.which("libreoffice"))
    if so:
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "ck.xlsx")
            open(p, "wb").write(data)
            subprocess.run([so, "--headless", "--convert-to", "csv", "--outdir", tmp, p],
                           capture_output=True, timeout=180)
            csv = open(os.path.join(tmp, "ck.csv"), encoding="utf-8", errors="replace").read() \
                if os.path.exists(os.path.join(tmp, "ck.csv")) else ""
            check("LibreOffice mở được file, dòng 4 đọc ra đúng",
                  '1,NGUYEN THI NGA,8848292453,' in csv and BIDV in csv and ",15500000,VND,CK LUONG T09 2026" in csv,
                  csv.splitlines()[3][:80] if len(csv.splitlines()) > 3 else "(không đọc được)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("  (bỏ qua: máy không có LibreOffice)")

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — file là mẫu của ngân hàng, chỉ điền dòng; ngân hàng hưởng đúng danh "
              "sách hoặc để trống kèm báo; tổng khớp tờ tổng hợp.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


NHAT = [
    {"employee_name": "Nguyễn Văn A", "baohiem": 500000, "luongthucnhan": 6150000, "luongck": 5000000,
     "chutaikhoan": "NGUYEN VAN A", "taikhoan": "1234567890",
     "nganhang": "NHTMCP DTPT VN-CN HAI DUONG - 31202005"},
    {"employee_name": "Trần Thị B", "baohiem": 0, "luongthucnhan": 5575000, "luongck": 0},
]
KHOAN = [
    {"employee_name": "Lê Văn C", "baohiem": 600000, "luongthucnhan": 8500000, "luongck": 0,
     "chutaikhoan": "", "taikhoan": "0987654321", "nganhang": "Vietcombank Hải Dương"},
    {"employee_name": "Phạm Thị D", "baohiem": 300000, "luongthucnhan": 7600000, "luongck": 0,
     "chutaikhoan": "PHAM THI D", "taikhoan": "1122334455", "nganhang": "BIDV"},
    {"employee_name": "Đinh Văn E", "baohiem": 0, "luongthucnhan": 7000000, "luongck": 0},
]


def run_js():
    """Nạp payroll.js trong node; gọi buildFile('nganhang') và exportBank với api giả."""
    src = open(JS, encoding="utf-8").read()
    src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
    src = re.sub(r"^export ", "", src, flags=re.M)
    sent = base64.b64encode(b"PK-fake-xlsx").decode()
    harness = (
        "let CALL=null, SAVED=null;\n"
        "const api={call:async(method,args)=>{CALL={method,args:JSON.parse(JSON.stringify(args))};"
        "return {file_b64:" + json.dumps(sent) + ",so_dong:1,tong_tien:1,canh_bao:[],bo_qua:[],ghi_chu:[]};}};\n"
        "const document={getElementById:()=>null,"
        "createElement:()=>({style:{},addEventListener(){},click(){},remove(){}}),"
        "head:{appendChild(){}},body:{appendChild(){}},querySelectorAll:()=>[]};\n"
        "const window={};\n"
        "globalThis.URL.createObjectURL=(b)=>{SAVED=b;return 'blob:x';};globalThis.URL.revokeObjectURL=()=>{};\n"
        + src
        + "\nconst NHAT=" + json.dumps(NHAT, ensure_ascii=False)
        + ";\nconst KHOAN=" + json.dumps(KHOAN, ensure_ascii=False) + ";\n"
        "(async()=>{\n"
        "const out = PB.buildFile('nganhang', NHAT, KHOAN, 9, 2026);\n"
        "await exportBank(out.dong, 'x.xlsx');\n"
        "const buf = Buffer.from(await SAVED.arrayBuffer()).toString('base64');\n"
        "console.log(JSON.stringify({dong: out.dong, call: CALL, saved: buf, sent_b64: " + json.dumps(sent)
        + ", tong_ck: PB.computeAgg(NHAT, KHOAN).tong_ck, has_wb: !!out.wb}));\n"
        "})().catch(e=>{console.error(e);process.exit(1);});\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as f:
        f.write(harness)
        tmp = f.name
    try:
        r = subprocess.run(["node", tmp], capture_output=True, text=True)
    finally:
        os.unlink(tmp)
    if r.returncode != 0:
        print((r.stderr or "")[-600:])
        return None
    return json.loads(r.stdout)


if __name__ == "__main__":
    sys.exit(main())
