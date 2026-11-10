#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""payroll_bank_check — file "Chuyển khoản ngân hàng" phải là MẪU CỦA NGÂN HÀNG.

Ngân hàng đổi mẫu chi lương (11/2026). Mẫu mới do hệ thống ngân hàng sinh ra,
khóa cấu trúc, có danh sách thả xuống — tức là ngân hàng đọc file theo khuôn
của họ. File xuất ra lấy CHÍNH mẫu đó (`ketoan/mau/ck_luong_ngan_hang.xlsx`)
rồi điền dòng từ dòng 4. Phép kiểm này canh bảy điều, mỗi điều một cách file
bị ngân hàng trả về — hoặc tệ hơn, được nhận mà tiền đi sai:

  1. Mọi phần của mẫu ngoài sheet đầu và bảng chuỗi GIỮ NGUYÊN TỪNG BYTE —
     tên vùng `domesticBanks`… (danh sách thả xuống dựa vào), khóa cấu trúc,
     sheet ẩn `Param`. Dòng chưa điền giữ nguyên như mẫu.
  2. Mỗi ô đúng kiểu mẫu đòi: STT là số; tài khoản, số tiền là CHỮ (ô "@");
     Loại tiền "VND"; tên không dấu IN HOA; nội dung chỉ chữ/số/./-.
  3. "Ngân hàng hưởng" lấy từ ô ngân hàng trên phiếu lương. Ba chi nhánh
     dạng cũ kế toán gửi ("NHTMCP DTPT VN-CN HAI DUONG - 31202005"…) tự ra
     chuỗi trong danh sách của mẫu ("01202001 - … - BIDV", "79314013 - … -
     VIB") — kể cả gõ khác dấu cách/hoa thường/dấu gạch — mà KHÔNG lan sang
     chi nhánh khác; ô khác ghi nguyên văn (chỉ gộp khoảng trắng, bỏ ký tự
     điều khiển — thứ làm hỏng file).
  4. Báo đủ: thiếu tài khoản, ô ngân hàng trống / không đúng chuỗi trong danh
     sách, tài khoản trùng; số tiền ≤ 0 không ghi. Quá sức chứa ⇒ dừng.
  5. Mẫu đổi cột ⇒ dừng, không điền theo vị trí cũ.
  6. Trang Tính lương gửi ĐÚNG dòng nó tính: chạy payroll.js thật trong node,
     tổng file = ô "Lương chuyển khoản" của tờ tổng hợp (`computeAgg`); 8 dòng
     Ban lãnh đạo ghi cứng đã mang chuỗi BIDV của danh sách.
  7. Lệnh đổi dữ liệu `docs/luong/sql/doi_ngan_hang_2026_11.sql` chỉ ghi chuỗi
     CÓ trong danh sách của mẫu — gõ sai một chữ là cả bảng lương bị báo.

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


# Hai chuỗi kế toán chọn (11/2026) — đúng như trong danh sách của mẫu.
BIDV = "01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV"
VIB = "79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB"
CU = "NHTMCP DTPT VN-CN HAI DUONG - 31202005"      # dạng mẫu cũ — xuất ra BIDV
LA = "NHTMCP DTPT VN-CN HAI DUONG - 31202006"      # chi nhánh kế toán KHÔNG gửi
SQL = os.path.join(REPO, "docs/luong/sql/doi_ngan_hang_2026_11.sql")

DONG = [
    # tên chủ TK, số TK, số tiền, ô ngân hàng trên phiếu lương
    ["NGUYEN THI NGA", "8848292453", 15500000, BIDV],
    ["Nguyễn Văn Ánh", "8848 292.999", 6150000, "Vietcombank Hải Dương"],
    ["Trần Thị Bé", "", 5575000, "NHTMCP QUOC TE VN-CN HAI DUONG-31314003"],
    ["Lê Văn Cường", "123456789", 0, BIDV],
    ["Phạm Thị D & Co. (HD)", "12-34.56", 7600000, "NH A&B <CN 1>"],
    ["Đỗ Đức Đạt", "8848292453", 1000000, "  nhtmcp dtpt vn-cn thanh đong–hai dương -\n 31202004 "],
    ["Hoàng Thị E", 4681729200, 2000000.4, "NHTMCP DTPT VN-CN HAI DUONG\x07 - 31202006"],
    ["Vũ Văn F", "0011223344", -50000, BIDV],
    ["Trịnh Văn G", "5566778899", 3000000, ""],
    ["Hồ Văn H", "6677889900", 4000000, CU],
]
COT_D = [BIDV, "Vietcombank Hải Dương", VIB, "NH A&B <CN 1>", BIDV, LA, None, BIDV]
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
    check("ghi 8/10 dòng (2 dòng số tiền ≤ 0 bỏ qua)", n == 8 and len(info["bo_qua"]) == 2, str(n))
    check("STT là SỐ 1..8", [x[0] for x in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
          and all(k[0] == "n" for k in kieu))
    check("tên: không dấu, IN HOA, chỉ chữ/số/&/-/.",
          [x[1] for x in rows] == ["NGUYEN THI NGA", "NGUYEN VAN ANH", "TRAN THI BE",
                                   "PHAM THI D & CO. HD", "DO DUC DAT", "HOANG THI E", "TRINH VAN G",
                                   "HO VAN H"],
          str([x[1] for x in rows]))
    check("tài khoản là CHỮ, bỏ dấu cách/chấm/gạch; ô thiếu để trống",
          [x[2] for x in rows] == ["8848292453", "8848292999", None, "123456",
                                   "8848292453", "4681729200", "5566778899", "6677889900"]
          and all(kieu[i][2] == "s" for i in (0, 1, 3, 4, 5, 6, 7)), str([x[2] for x in rows]))
    check("số tiền là CHỮ chỉ gồm chữ số (ô '@' của mẫu), làm tròn đồng",
          [x[4] for x in rows] == ["15500000", "6150000", "5575000", "7600000", "1000000",
                                   "2000000", "3000000", "4000000"]
          and all(k[4] == "s" for k in kieu), str([x[4] for x in rows]))
    check("Loại tiền = 'VND' mọi dòng", all(x[5] == "VND" for x in rows))
    check("nội dung: bỏ dấu, bỏ ký tự ngoài chữ/số/./- ('CK LUONG T09 2026')",
          all(x[6] == "CK LUONG T09 2026" for x in rows), str(rows[0][6]))
    check("cột H..O (giấy tờ, chi nhánh, mã GD, bổ sung) để trống",
          all(v is None for x in rows for v in x[7:]))
    ten_ok = all(re.fullmatch(r"[A-Z0-9&.\- ]{1,70}", x[1] or "") for x in rows)
    check("tên ≤ 70 ký tự hợp lệ", ten_ok)

    # ── 3. Ngân hàng hưởng ─────────────────────────────────────────────
    muc("3. 'Ngân hàng hưởng': ba chuỗi cũ kế toán gửi ⇒ chuỗi mới; còn lại nguyên văn")
    ds = {wt["DS ngân hàng hưởng_Bank list"].cell(r, 3).value
          for r in range(2, wt["DS ngân hàng hưởng_Bank list"].max_row + 1)}
    cot_d = [x[3] for x in rows]
    check("hai chuỗi kế toán chọn (BIDV, VIB) có ĐÚNG trong danh sách của mẫu",
          BIDV in ds and VIB in ds)
    check(f"phiếu ghi “{CU}” (tháng 10 còn nguyên) ⇒ cột D ra chuỗi BIDV của danh sách",
          cot_d[7] == BIDV, str(cot_d[7]))
    check("“NHTMCP QUOC TE VN-CN HAI DUONG-31314003” ⇒ chuỗi VIB của danh sách", cot_d[2] == VIB)
    check("gõ khác (chữ thường, có dấu, gạch '–', xuống dòng) của chi nhánh Thành Đông ⇒ BIDV",
          cot_d[4] == BIDV, str(cot_d[4]))
    check("mọi dòng đúng như chờ (đổi 3 chuỗi cũ; còn lại nguyên văn, gộp khoảng trắng, bỏ ký tự điều khiển)",
          cot_d == COT_D, str(cot_d))
    check(f"chi nhánh kế toán KHÔNG gửi (“{LA}”) ⇒ giữ NGUYÊN VĂN, không đoán",
          cot_d[5] == LA and cot_d[1] == "Vietcombank Hải Dương")
    for text, mong in [(CU, BIDV), ("NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004", BIDV),
                       ("NHTMCP QUOC TE VN-CN HAI DUONG-31314003", VIB),
                       ("NHTMCP QUOC TE VN-CN HAI DUONG - 31314003", VIB),
                       ("NHTMCP DTPT VN-CN HẢI DƯƠNG - 31202005", BIDV),
                       (LA, LA), ("NHTMCP DTPT VN-CN HAI DUONG - 312020051", "NHTMCP DTPT VN-CN HAI DUONG - 312020051"),
                       ("NHTMCP QUOC TE VN-CN HAI DUONG-31314004", "NHTMCP QUOC TE VN-CN HAI DUONG-31314004"),
                       (BIDV, BIDV), ("", ""), (None, "")]:
        ra = pb.doi_ngan_hang(text)
        check(f"đổi “{(text or '')[:44]}” ⇒ “{mong[:30]}…”", ra == mong, ra)
    check("Nhật ký ghi rõ chuỗi nào đã đổi, bao nhiêu người",
          sorted(info["ghi_chu"]) == sorted([
              f"cột Ngân hàng hưởng: phiếu ghi “{CU}” → xuất “{BIDV}” (1 người)",
              f"cột Ngân hàng hưởng: phiếu ghi “NHTMCP QUOC TE VN-CN HAI DUONG-31314003” → xuất “{VIB}” (1 người)",
              f"cột Ngân hàng hưởng: phiếu ghi “nhtmcp dtpt vn-cn thanh đong–hai dương - 31202004” → xuất “{BIDV}” (1 người)"]),
          str(info["ghi_chu"])[:90])
    check("cột D là ô CHỮ", all(kieu[i][3] == "s" for i in (0, 1, 2, 3, 4, 5, 7)))
    check("ô ngân hàng trống ⇒ cột D trống", cot_d[6] is None)
    check("'&', '<', '>' trong ô ngân hàng không làm hỏng file", cot_d[3] == "NH A&B <CN 1>")

    for text in [BIDV, VIB, "01203001 - Ngan hang TMCP Ngoai thuong Viet Nam - Vietcombank",
                 "  " + BIDV.replace(" - ", "  -  ") + " "]:
        ly = pb.kiem_ngan_hang(text)
        check(f"soi “{text.strip()[:48]}…” ⇒ ổn", ly == "", ly)
    for text, mong in [(CU, "không có trong danh sách"),
                       ("NHTMCP QUOC TE VN-CN HAI DUONG-31314003", "không có trong danh sách"),
                       ("BIDV", "không có trong danh sách"),
                       (BIDV.upper(), "không có trong danh sách"),     # ngân hàng so đúng chữ
                       ("", "chưa ghi ngân hàng"), (None, "chưa ghi ngân hàng")]:
        ly = pb.kiem_ngan_hang(text)
        check(f"soi “{(text or '')[:48]}” ⇒ báo “{mong}”", mong in ly, ly)

    # ── 4. Báo đủ ──────────────────────────────────────────────────────
    muc("4. Báo đủ chỗ cần sửa; số tiền ≤ 0 không ghi; quá sức chứa thì dừng")
    cb = "\n".join(info["canh_bao"])
    check("báo thiếu số tài khoản (3. TRAN THI BE)", "3. TRAN THI BE: thiếu số tài khoản" in cb)
    khong_co = "không có trong danh sách Ngân hàng hưởng của mẫu"
    check("báo ô ngân hàng không đúng chuỗi trong danh sách, nêu chữ trên phiếu (2, 4, 6)",
          f"2. NGUYEN VAN ANH: ô ngân hàng “Vietcombank Hải Dương” {khong_co}" in cb
          and f"4. PHAM THI D & CO. HD: ô ngân hàng “NH A&B <CN 1>” {khong_co}" in cb
          and f"6. HOANG THI E: ô ngân hàng “{LA}” {khong_co}" in cb)
    check("báo phiếu chưa ghi ngân hàng (7. TRINH VAN G)",
          "7. TRINH VAN G: phiếu lương chưa ghi ngân hàng" in cb)
    check("dòng đúng chuỗi / đã đổi (1, 3, 5, 8) KHÔNG bị báo ngân hàng",
          not any(x.startswith(("1. NGUYEN THI NGA: ô ngân hàng", "3. TRAN THI BE: ô ngân hàng",
                                "5. DO DUC DAT: ô ngân hàng", "8. HO VAN H: ô ngân hàng"))
                  for x in info["canh_bao"]))
    check("báo tài khoản 8848292453 trùng (1 và 5)",
          "số tài khoản 8848292453 xuất hiện 2 lần (1. NGUYEN THI NGA; 5. DO DUC DAT)" in cb)
    check("số tiền 0 và âm KHÔNG ghi, có báo",
          any("LE VAN CUONG" in x for x in info["bo_qua"]) and any("VU VAN F" in x for x in info["bo_qua"]))
    check("tổng tiền = cộng cột số tiền (44.825.000)",
          info["tong_tien"] == 44825000 == sum(int(x[4]) for x in rows), str(info["tong_tien"]))
    d2, i2 = pb.dung_file([["Nguyen Van A " * 8, "1", 1, BIDV]], "CK")
    b4 = openpyxl.load_workbook(io.BytesIO(d2)).worksheets[0].cell(4, 2).value or ""
    check("tên dài quá 70 ⇒ cắt còn ≤ 70 + báo",
          0 < len(b4) <= 70 and any("cắt bớt" in x for x in i2["canh_bao"]), f"{len(b4)} ký tự")
    d3, _ = pb.dung_file([["A", "1", 1, BIDV]] * 988, "CK")
    w3 = openpyxl.load_workbook(io.BytesIO(d3)).worksheets[0]
    check("đủ 988 dòng (sức chứa của mẫu) ⇒ ghi tới dòng 991",
          w3.cell(991, 1).value == 988 and w3.cell(991, 5).value == "1")
    try:
        pb.dung_file([["A", "1", 1, BIDV]] * 989, "CK")
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
        lg = js.get("logs") or []

        def co(chu, kieu):
            return any(chu in x and f"lpay-m-{kieu}" in x for x in lg)
        check("Nhật ký trên trang hiện cảnh báo (đỏ), dòng bỏ qua và ghi chú chuỗi đã đổi",
              co("CB-canh-bao", "err") and co("BQ-bo-qua", "info") and co("GC-da-doi", "info"),
              str(lg)[:90])
        dj, ij = pb.dung_file(js["dong"], "CK LUONG")
        wj = openpyxl.load_workbook(io.BytesIO(dj)).worksheets[0]
        check("tổng file = ô 'Lương chuyển khoản' của tờ tổng hợp (computeAgg.tong_ck)",
              ij["tong_tien"] == round(js["tong_ck"]), f"{ij['tong_tien']} / {js['tong_ck']}")
        check("cột D của file = ô ngân hàng trang gửi, chuỗi cũ đã đổi (phiếu khoán còn ghi Thành Đông ⇒ BIDV)",
              [wj.cell(4 + i, 4).value for i in range(len(js["dong"]))]
              == [pb.doi_ngan_hang(x[3]) for x in js["dong"]]
              and wj.cell(6, 4).value == BIDV, str(wj.cell(6, 4).value))
        check("8 dòng Ban lãnh đạo (ghi cứng trong payroll.js) mang chuỗi BIDV của danh sách",
              [x[3] for x in js["dong"][-8:]] == [BIDV] * 8, str({x[3] for x in js["dong"][-8:]}))
        check("không cảnh báo nào cho bộ dữ liệu sạch", ij["canh_bao"] == [], str(ij["canh_bao"])[:90])

    # ── 7. Lệnh đổi dữ liệu ────────────────────────────────────────────
    muc("7. Lệnh SQL đổi ô ngân hàng chỉ ghi chuỗi CÓ trong danh sách của mẫu")
    sql = open(SQL, encoding="utf-8").read()
    sach = "\n".join(x for x in sql.splitlines() if not x.strip().startswith("--"))  # bỏ chú thích
    lenh = [x for x in sach.split(";") if "UPDATE" in x]
    dich = re.findall(r"SET nganhang = '([^']*)'", "".join(lenh))
    check("4 lệnh UPDATE (2 bảng × 2 ngân hàng), mỗi lệnh ghi một chuỗi",
          len(lenh) == 4 and len(dich) == 4, f"{len(lenh)} lệnh / {len(dich)} chuỗi")
    check("mọi chuỗi đích đều CÓ trong danh sách Ngân hàng hưởng của mẫu",
          bool(dich) and all(d in ds for d in dich), str(sorted(set(dich))))
    cap = {}
    for x in lenh:
        bang = re.search(r"UPDATE `(tab\w+)`", x).group(1)
        d = re.search(r"SET nganhang = '([^']*)'", x).group(1)
        for nguon in re.findall(r"'([^']+)'", x.split("WHERE", 1)[1]):
            cap[(bang, nguon)] = d
    # Ba chuỗi đúng như kế toán gửi (11/2026) — "chỉ đổi các trường ngân hàng có
    # thông tin như anh gửi".
    mong = {(b, c): d for b in ("tabSalaryDay", "tabSalaryProduct")
            for c, d in ((CU, BIDV), ("NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004", BIDV),
                         ("NHTMCP QUOC TE VN-CN HAI DUONG-31314003", VIB))}
    check("CẢ HAI bảng (công nhật, công khoán) đổi đúng ba chuỗi kế toán gửi: "
          "2 chi nhánh BIDV → BIDV, VIB Hải Dương → VIB", cap == mong,
          str(sorted(set(mong) ^ set(cap)))[:90])
    check("CHỈ khớp đúng chuỗi (BINARY TRIM = …), không so lỏng bỏ dấu cách/hoa thường",
          all("WHERE BINARY TRIM(nganhang) " in x for x in lenh)
          and not re.search(r"REPLACE\(|LIKE|REGEXP|UPPER\(|LOWER\(", sach))
    bk = sql.find("CREATE TABLE IF NOT EXISTS `_bk_nganhang_2026_11`")
    check("có sao lưu TRƯỚC khi đổi + lệnh lùi lại",
          0 <= bk < sql.find("UPDATE `tabSalaryDay`") and "JOIN `_bk_nganhang_2026_11`" in sql)

    # Bộ đột biến tắt bước này cho nhanh (35 lần × vài giây); chạy tay thì có.
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
                  "1,NGUYEN THI NGA,8848292453,%s,15500000,VND,CK LUONG T09 2026" % BIDV in csv,
                  csv.splitlines()[3][:80] if len(csv.splitlines()) > 3 else "(không đọc được)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("  (bỏ qua: máy không có LibreOffice)")

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — file là mẫu của ngân hàng, chỉ điền dòng; ba chuỗi ngân hàng cũ ra "
              "chuỗi mới, còn lại nguyên văn, không đúng danh sách thì báo; tổng khớp tờ tổng hợp.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


NHAT = [
    {"employee_name": "Nguyễn Văn A", "baohiem": 500000, "luongthucnhan": 6150000, "luongck": 5000000,
     "chutaikhoan": "NGUYEN VAN A", "taikhoan": "1234567890",
     "nganhang": "01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV"},
    {"employee_name": "Trần Thị B", "baohiem": 0, "luongthucnhan": 5575000, "luongck": 0},
]
KHOAN = [
    {"employee_name": "Lê Văn C", "baohiem": 600000, "luongthucnhan": 8500000, "luongck": 0,
     "chutaikhoan": "", "taikhoan": "0987654321",
     "nganhang": "01203001 - Ngan hang TMCP Ngoai thuong Viet Nam - Vietcombank"},
    {"employee_name": "Phạm Thị D", "baohiem": 300000, "luongthucnhan": 7600000, "luongck": 0,
     "chutaikhoan": "PHAM THI D", "taikhoan": "1122334455",
     "nganhang": "NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004"},
    {"employee_name": "Đinh Văn E", "baohiem": 0, "luongthucnhan": 7000000, "luongck": 0},
]


def run_js():
    """Nạp payroll.js trong node; gọi buildFile('nganhang') và exportBank với api giả."""
    src = open(JS, encoding="utf-8").read()
    src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
    src = re.sub(r"^export ", "", src, flags=re.M)
    sent = base64.b64encode(b"PK-fake-xlsx").decode()
    harness = (
        "let CALL=null, SAVED=null; const LOGS=[];\n"
        "const api={call:async(method,args)=>{CALL={method,args:JSON.parse(JSON.stringify(args))};"
        "return {file_b64:" + json.dumps(sent) + ",so_dong:1,tong_tien:1,"
        "canh_bao:['CB-canh-bao'],bo_qua:['BQ-bo-qua'],ghi_chu:['GC-da-doi']};}};\n"
        "const document={getElementById:()=>null,"
        "createElement:()=>({style:{},addEventListener(){},click(){},remove(){}}),"
        "head:{appendChild(){}},body:{appendChild(){}},querySelectorAll:()=>[]};\n"
        "const window={};\n"
        "globalThis.URL.createObjectURL=(b)=>{SAVED=b;return 'blob:x';};globalThis.URL.revokeObjectURL=()=>{};\n"
        + src
        + "\nconst NHAT=" + json.dumps(NHAT, ensure_ascii=False)
        + ";\nconst KHOAN=" + json.dumps(KHOAN, ensure_ascii=False) + ";\n"
        "(async()=>{\n"
        "logBox={appendChild(li){LOGS.push(li.innerHTML);},scrollTop:0,scrollHeight:0};\n"
        "const out = PB.buildFile('nganhang', NHAT, KHOAN, 9, 2026);\n"
        "await exportBank(out.dong, 'x.xlsx');\n"
        "const buf = Buffer.from(await SAVED.arrayBuffer()).toString('base64');\n"
        "console.log(JSON.stringify({dong: out.dong, call: CALL, saved: buf, sent_b64: " + json.dumps(sent)
        + ", tong_ck: PB.computeAgg(NHAT, KHOAN).tong_ck, has_wb: !!out.wb, logs: LOGS}));\n"
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
