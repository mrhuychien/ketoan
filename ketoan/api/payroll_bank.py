# -*- coding: utf-8 -*-
"""Xuất file CHUYỂN KHOẢN LƯƠNG theo đúng MẪU CỦA NGÂN HÀNG.

Ngân hàng đổi mẫu chi lương (11/2026). Mẫu mới là file "bulk payment" do hệ
thống của ngân hàng sinh ra: 6 sheet, sheet đầu "Mẫu file_File Template", tiêu
đề ở dòng 3, dữ liệu từ dòng 4; cột "Ngân hàng hưởng" là DANH SÁCH THẢ XUỐNG;
cột số tiền là ô CHỮ (định dạng "@"); cấu trúc sổ bị KHÓA (lockStructure). Tức
là phía ngân hàng đọc file theo đúng khuôn của họ.

Vì vậy file xuất ra KHÔNG dựng lại từ đầu: lấy chính file mẫu của ngân hàng
(`ketoan/mau/ck_luong_ngan_hang.xlsx`, giữ nguyên từng byte như ngân hàng
phát) rồi chỉ điền giá trị vào các ô đã kẻ sẵn từ dòng 4 của sheet đầu. Chỉ
HAI phần trong file đổi: `xl/worksheets/sheet1.xml` (các ô được điền) và
`xl/sharedStrings.xml` (chuỗi mới nối vào cuối). Năm sheet còn lại, danh sách
thả xuống, tên vùng `domesticBanks`/`transferCcys`/`branch_bank_*`, khóa cấu
trúc, định dạng — giữ nguyên từng byte.

Không ghi bằng openpyxl/ExcelJS: cả hai làm rơi tên vùng dạng công thức
(`OFFSET(...)`) mà danh sách thả xuống dựa vào. Đã đo: ExcelJS 4.4.0 đọc rồi
ghi lại mẫu này thì chỉ còn `_xlnm._FilterDatabase` — cột "Ngân hàng hưởng"
mất danh sách chọn.

── Cột "Ngân hàng hưởng" ──────────────────────────────────────────────────
Ghi NGUYÊN VĂN ô ngân hàng trên phiếu lương — kế toán yêu cầu (11/2026):
"điền đúng NHTMCP DTPT VN-CN HAI DUONG - 31202005", tức dạng "<tên chi
nhánh> - <mã 8 số>" như mẫu cũ, KHÔNG đổi sang chuỗi trong danh sách thả
xuống của mẫu mới ("01202001 - Ngan hang TMCP … - BIDV"). Chỉ gộp khoảng
trắng thừa và bỏ ký tự điều khiển (thứ làm hỏng file).
Chữ không sửa, nhưng có SOI để báo cho người sửa phiếu lương: ô trống, không
có mã 8 số, mã không có trong danh sách ngân hàng/chi nhánh của mẫu.
Cột "Chi nhánh ngân hàng hưởng" để trống: theo hướng dẫn của mẫu, chuyển tới
SỐ TÀI KHOẢN chỉ cần ngân hàng.

Ngân hàng đổi mẫu lần sau: thay file trong `ketoan/mau/` rồi chạy
`python3 docs/verified/payroll_bank_check.py` — bộ kiểm so cấu trúc với mẫu,
và hàm này tự dừng nếu tiêu đề dòng 3 không còn đúng thứ tự cột cũ.
"""

import base64
import io
import json
import math
import os
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import frappe
from frappe import _
from frappe.utils import cstr, flt

from ketoan.api._guard import guard_payroll

MAU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "mau", "ck_luong_ngan_hang.xlsx")

SHEET_MAU = "Mẫu file_File Template"
SHEET_NH = "DS ngân hàng hưởng_Bank list"
SHEET_CN = "DS chi nhánh_Branch list"

DONG_TIEU_DE = 3
DONG_DAU = 4

# Chữ đầu của tiêu đề dòng 3. Mẫu đổi thứ tự cột mà vẫn điền theo vị trí cũ là
# tên người vào ô tài khoản — nên khớp tiêu đề trước khi điền.
TIEU_DE = (
    ("A", "STT"),
    ("B", "Tên người hưởng"),
    ("C", "Tài khoản hưởng"),
    ("D", "Ngân hàng hưởng"),
    ("E", "Số tiền"),
    ("F", "Loại tiền"),
    ("G", "Nội dung"),
)

TIEN_TE = "VND"
NOI_DUNG_MAC_DINH = "CK LUONG"
MAX_TEN, MAX_TK, MAX_TIEN, MAX_ND = 70, 35, 16, 190

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Dòng KHÔNG tự đóng (dòng `<row .../>` không có ô kẻ sẵn để giữ định dạng).
_RE_DONG = re.compile(r'(<row r="(\d+)"[^>]*?(?<!/)>)(.*?)(</row>)', re.S)
_RE_O = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)


# ── chữ ──────────────────────────────────────────────────────────────────

def _khong_dau(s):
    s = cstr(s).replace("đ", "d").replace("Đ", "D").replace("ð", "d").replace("Ð", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _gon(s):
    return re.sub(r"\s+", " ", s).strip()


def _lam_sach_ten(s):
    """Tên người hưởng: không dấu, IN HOA, chỉ chữ/số/&/-/. (luật của mẫu)."""
    return _gon(re.sub(r"[^A-Z0-9&.\- ]+", " ", _khong_dau(s).upper()))


def _lam_sach_noi_dung(s):
    """Nội dung chuyển tiền: không dấu, chỉ chữ/số/./- (luật của mẫu)."""
    return _gon(re.sub(r"[^A-Za-z0-9.\- ]+", " ", _khong_dau(s)))[:MAX_ND].strip()


def _lam_sach_tk(v):
    """(số tài khoản, có ký tự lạ?) — bỏ dấu cách/chấm/gạch người ta hay gõ."""
    if isinstance(v, bool) or v is None:
        s = ""
    elif isinstance(v, int):
        s = str(v)
    elif isinstance(v, float):
        s = str(int(v)) if v == int(v) else repr(v)
    else:
        s = cstr(v)
    s = re.sub(r"[\s.\-,_']+", "", _khong_dau(s))
    return s, bool(re.search(r"[^A-Za-z0-9]", s))


def _so(n):
    return "{:,}".format(n).replace(",", ".")


def _nguyen_van(s):
    """Chữ như người gõ — chỉ gộp khoảng trắng (cả xuống dòng, cách cứng) và bỏ
    ký tự điều khiển: một ký tự \\x0b lọt vào là cả file XML hỏng."""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cstr(s))
    return re.sub(r"\s+", " ", s).strip()


# ── đọc mẫu ──────────────────────────────────────────────────────────────

def _doc_sst(xml):
    """(danh sách chuỗi theo chỉ số, {chuỗi thường: chỉ số đầu tiên})."""
    out, thuong = [], {}
    for i, si in enumerate(ET.fromstring(xml).findall(_NS + "si")):
        t, runs = si.find(_NS + "t"), si.findall(_NS + "r")
        if t is not None and not runs:
            out.append(t.text or "")
            thuong.setdefault(t.text or "", i)
        else:
            out.append("".join(x.text or "" for r in runs for x in r.findall(_NS + "t")))
    return out, thuong


def _doc_sheet(xml, sst):
    """{số dòng: {cột: giá trị chữ}}."""
    rows = {}
    for row in ET.fromstring(xml).iter(_NS + "row"):
        cells = {}
        for c in row.findall(_NS + "c"):
            m = re.match(r"([A-Z]+)", c.get("r") or "")
            if not m:
                continue
            v, t = c.find(_NS + "v"), c.get("t")
            if t == "s":
                val = sst[int(v.text)] if v is not None and v.text else ""
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(_NS + "t"))
            else:
                val = v.text if v is not None and v.text is not None else ""
            cells[m.group(1)] = val
        rows[int(row.get("r"))] = cells
    return rows


def _bang_ngan_hang(nh_rows, cn_rows):
    """Mã ngân hàng (sheet danh sách ngân hàng) + mã chi nhánh → mã ngân hàng
    (sheet chi nhánh), lấy từ CHÍNH file mẫu — để soi mã trên phiếu lương."""
    ma_ngan_hang = set()
    for r in sorted(nh_rows):
        ma = cstr(nh_rows[r].get("B")).strip()
        if r >= 2 and re.fullmatch(r"\d{8}", ma):
            ma_ngan_hang.add(ma)
    chi_nhanh = {}
    for r in sorted(cn_rows):
        ma_nh = cstr(cn_rows[r].get("B")).strip()
        m = re.match(r"(\d{8})\b", cstr(cn_rows[r].get("D")).strip())
        if r >= 2 and m and ma_nh:
            chi_nhanh.setdefault(m.group(1), ma_nh)
    return {"ma_ngan_hang": ma_ngan_hang, "chi_nhanh": chi_nhanh}


_CACHE = {}


def _doc_mau(path=None):
    path = path or MAU
    if not os.path.exists(path):
        frappe.throw(_("Thiếu file mẫu chuyển khoản của ngân hàng: {0}").format(path))
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    if _CACHE.get("key") == key:
        return _CACHE["val"]
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = list(ET.fromstring(z.read("xl/_rels/workbook.xml.rels")))

        def duong(target):
            return target.lstrip("/") if target.startswith("/") else "xl/" + target

        dich = {r.get("Id"): r.get("Target") for r in rels}
        sheet = {s.get("name"): duong(dich.get(s.get(_NS_R + "id"), ""))
                 for s in wb.iter(_NS + "sheet")}
        sst_path = next((duong(r.get("Target")) for r in rels
                         if cstr(r.get("Type")).endswith("/sharedStrings")), None)
        for ten in (SHEET_MAU, SHEET_NH, SHEET_CN):
            if ten not in sheet:
                frappe.throw(_("Mẫu ngân hàng không còn sheet “{0}” — mẫu đã đổi, "
                               "cần cập nhật code xuất file.").format(ten))
        if not sst_path:
            frappe.throw(_("Mẫu ngân hàng không có bảng chuỗi dùng chung — mẫu lạ."))
        sst_xml = z.read(sst_path).decode("utf-8")
        sheet_xml = z.read(sheet[SHEET_MAU]).decode("utf-8")
        sst, thuong = _doc_sst(sst_xml)
        bang = _bang_ngan_hang(_doc_sheet(z.read(sheet[SHEET_NH]), sst),
                               _doc_sheet(z.read(sheet[SHEET_CN]), sst))

    tieu_de = _doc_sheet(sheet_xml, sst).get(DONG_TIEU_DE, {})
    for cot, dau in TIEU_DE:
        if not cstr(tieu_de.get(cot)).strip().startswith(dau):
            frappe.throw(_("Mẫu ngân hàng đã đổi cột: ô {0}{1} là “{2}”, chờ “{3}…”. "
                           "Cần cập nhật code xuất file.").format(
                cot, DONG_TIEU_DE, _gon(cstr(tieu_de.get(cot)))[:40], dau))
    san = [int(m.group(2)) for m in _RE_DONG.finditer(sheet_xml) if int(m.group(2)) >= DONG_DAU]
    suc_chua = 0
    while DONG_DAU + suc_chua in san:
        suc_chua += 1
    val = {"path": path, "sheet_path": sheet[SHEET_MAU], "sst_path": sst_path,
           "sheet_xml": sheet_xml, "sst_xml": sst_xml, "sst_n": len(sst),
           "thuong": thuong, "bang": bang, "suc_chua": suc_chua}
    _CACHE.update(key=key, val=val)
    return val


# ── soi ô ngân hàng ──────────────────────────────────────────────────────

def kiem_ngan_hang(text, bang=None):
    """Lý do ô ngân hàng trên phiếu lương cần xem lại, hoặc "" nếu ổn.

    Chỉ để BÁO — chữ vẫn ghi nguyên văn. Ổn = có mã 8 số và mã đó là mã chi
    nhánh hoặc mã ngân hàng trong danh sách của mẫu ngân hàng.
    """
    goc = _nguyen_van(text)
    if not goc:
        return "phiếu lương chưa ghi ngân hàng"
    ma = re.findall(r"(?<!\d)\d{8}(?!\d)", goc)
    if not ma:
        return "không có mã 8 số (dạng “<tên chi nhánh> - <mã 8 số>”)"
    bang = bang or _doc_mau()["bang"]
    la = [x for x in ma if x not in bang["chi_nhanh"] and x not in bang["ma_ngan_hang"]]
    if la:
        return "mã %s không có trong danh sách chi nhánh/ngân hàng của mẫu ngân hàng" % ", ".join(la)
    return ""


# ── ghi file ─────────────────────────────────────────────────────────────

def _dien_sheet(sheet_xml, du_lieu, chi_so):
    """Điền {dòng: {cột: ("n"|"s", giá trị)}} vào các ô kẻ sẵn của mẫu."""
    da_dien = set()

    def dong(m):
        r = int(m.group(2))
        vals = du_lieu.get(r)
        if not vals:
            return m.group(0)
        trung = set()

        def o(mc):
            col = mc.group(1)
            if int(mc.group(2)) != r or col not in vals:
                return mc.group(0)
            trung.add(col)
            attrs = re.sub(r'\s+t="[^"]*"', "", mc.group(3))
            kind, v = vals[col]
            if kind == "n":
                return '<c r="%s%d"%s><v>%d</v></c>' % (col, r, attrs, v)
            return '<c r="%s%d"%s t="s"><v>%d</v></c>' % (col, r, attrs, chi_so(v))

        than = _RE_O.sub(o, m.group(3))
        if trung != set(vals):
            frappe.throw(_("Mẫu ngân hàng thiếu ô kẻ sẵn ở dòng {0} — mẫu lạ.").format(r))
        da_dien.add(r)
        return m.group(1) + than + m.group(4)

    out = _RE_DONG.sub(dong, sheet_xml)
    if da_dien != set(du_lieu):
        frappe.throw(_("Mẫu ngân hàng thiếu dòng kẻ sẵn: {0}").format(
            sorted(set(du_lieu) - da_dien)[:5]))
    return out


def _them_sst(sst_xml, moi, so_tham_chieu):
    """Nối chuỗi mới vào cuối bảng chuỗi, cập nhật count/uniqueCount."""
    them = "".join(
        '<si><t%s>%s</t></si>' % (' xml:space="preserve"' if s != s.strip() else "", escape(s))
        for s in moi)
    i = sst_xml.rindex("</sst>")
    out = sst_xml[:i] + them + sst_xml[i:]

    def dem(m):
        return '%s="%d"' % (m.group(1), int(m.group(2)) + (so_tham_chieu if m.group(1) == "count" else len(moi)))

    head_end = out.index(">", out.index("<sst"))
    return re.sub(r'\b(count|uniqueCount)="(\d+)"', dem, out[:head_end]) + out[head_end:]


def dung_file(dong, noi_dung=None, path=None):
    """(bytes xlsx, thông tin) từ các dòng [tên, tài khoản, số tiền, ngân hàng].

    Dòng số tiền ≤ 0 không ghi (không có gì để chuyển). Dòng thiếu tài khoản /
    ô ngân hàng có vấn đề VẪN ghi (ô trống để trống, chữ giữ nguyên) và báo —
    không ai bị sót lương trong im lặng.
    """
    if not isinstance(dong, (list, tuple)):
        frappe.throw(_("Dữ liệu chuyển khoản không hợp lệ."))
    m = _doc_mau(path)
    nd = _lam_sach_noi_dung(noi_dung) or NOI_DUNG_MAC_DINH

    du_lieu, canh_bao, bo_qua = {}, [], []
    theo_tk = {}
    tong = 0
    for x in dong:
        x = list(x) if isinstance(x, (list, tuple)) else []
        ten_goc, tk_goc, tien_goc, nh_goc = (x + [None] * 4)[:4]
        tien = int(math.floor(flt(tien_goc) + 0.5))   # làm tròn như Math.round của trang
        ten = _lam_sach_ten(ten_goc)
        if tien <= 0:
            bo_qua.append("%s: số tiền %s — không ghi vào file" % (ten or "(không tên)", _so(tien)))
            continue
        if len(str(tien)) > MAX_TIEN:
            frappe.throw(_("Số tiền của {0} quá {1} chữ số.").format(ten, MAX_TIEN))
        stt = len(du_lieu) + 1
        r = DONG_DAU + stt - 1
        nhan = "%d. %s" % (stt, ten or "(không tên)")
        if not ten:
            canh_bao.append("%s: thiếu tên người hưởng" % nhan)
        elif len(ten) > MAX_TEN:
            ten = ten[:MAX_TEN].strip()
            canh_bao.append("%s: tên dài quá %d ký tự, đã cắt bớt" % (nhan, MAX_TEN))
        tk, la = _lam_sach_tk(tk_goc)
        if not tk:
            canh_bao.append("%s: thiếu số tài khoản" % nhan)
        elif la or len(tk) > MAX_TK:
            canh_bao.append("%s: số tài khoản “%s” có ký tự lạ hoặc dài quá %d ký tự — sửa trên phiếu lương"
                            % (nhan, tk, MAX_TK))
        if tk:
            theo_tk.setdefault(tk, []).append(nhan)
        nh = _nguyen_van(nh_goc)
        ly_do = kiem_ngan_hang(nh, m["bang"])
        if not nh:
            canh_bao.append("%s: %s — cột Ngân hàng hưởng để trống" % (nhan, ly_do))
        elif ly_do:
            canh_bao.append("%s: ô ngân hàng “%s” %s — kiểm lại phiếu lương" % (nhan, nh, ly_do))

        vals = {"A": ("n", stt), "E": ("s", str(tien)), "F": ("s", TIEN_TE), "G": ("s", nd)}
        if ten:
            vals["B"] = ("s", ten)
        if tk:
            vals["C"] = ("s", tk)
        if nh:
            vals["D"] = ("s", nh)                  # NGUYÊN VĂN phiếu lương
        du_lieu[r] = vals
        tong += tien

    if len(du_lieu) > m["suc_chua"]:
        frappe.throw(_("Mẫu ngân hàng chỉ có {0} dòng, danh sách có {1} người — tách thành nhiều file.")
                     .format(m["suc_chua"], len(du_lieu)))
    for tk, ai in theo_tk.items():
        if len(ai) > 1:
            canh_bao.append("số tài khoản %s xuất hiện %d lần (%s) — kiểm lại kẻo chuyển hai lần"
                            % (tk, len(ai), "; ".join(ai)))

    moi, idx_moi = [], {}
    so_tham_chieu = 0

    def chi_so(s):
        nonlocal so_tham_chieu
        so_tham_chieu += 1
        if s in m["thuong"]:
            return m["thuong"][s]
        if s not in idx_moi:
            idx_moi[s] = m["sst_n"] + len(moi)
            moi.append(s)
        return idx_moi[s]

    sheet_xml = _dien_sheet(m["sheet_xml"], du_lieu, chi_so)
    sst_xml = _them_sst(m["sst_xml"], moi, so_tham_chieu)

    out = io.BytesIO()
    with zipfile.ZipFile(m["path"]) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == m["sheet_path"]:
                data = sheet_xml.encode("utf-8")
            elif info.filename == m["sst_path"]:
                data = sst_xml.encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.create_system = info.create_system
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)

    return out.getvalue(), {"so_dong": len(du_lieu), "tong_tien": tong,
                            "canh_bao": canh_bao, "bo_qua": bo_qua}


@frappe.whitelist()
def xuat_file_chuyen_khoan(dong=None, noi_dung=None):
    """File chuyển khoản lương theo mẫu ngân hàng — trả base64 + cảnh báo.

    `dong`: danh sách [tên chủ tài khoản, số tài khoản, số tiền, ngân hàng] do
    trang Tính lương tính (cùng nguồn với bảng tổng hợp), hàm này chỉ ĐỊNH
    DẠNG theo mẫu — không đọc thêm gì từ CSDL.
    """
    guard_payroll()
    if isinstance(dong, str):
        dong = json.loads(dong or "[]")
    data, info = dung_file(dong or [], noi_dung)
    info["file_b64"] = base64.b64encode(data).decode("ascii")
    return info
