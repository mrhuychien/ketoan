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
Phải là ĐÚNG MỘT chuỗi trong danh sách của mẫu, ví dụ
"01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV". Ô "ngân
hàng" trên phiếu lương là chữ tự do theo mẫu CŨ ("<tên chi nhánh> - <mã 8
số>"), nên dò theo thứ tự:
  1. có mã 8 số → mã ngân hàng trong danh sách; hoặc mã CHI NHÁNH trong sheet
     chi nhánh của mẫu → ngân hàng của chi nhánh đó; hoặc 3 số giữa (mã tổ
     chức tín dụng) khớp đúng MỘT ngân hàng;
  2. không có mã → tên: tiền tố dài nhất trong (tên viết tắt "BIDV",
     "Vietcombank"…; tên đầy đủ; tên CITAD "NHTMCP DTPT VN"…), chỉ nhận khi
     ra đúng MỘT ngân hàng. Dò theo tên thì báo lại để kế toán liếc qua.
Không dò ra thì để TRỐNG ô đó và báo tên người: cột bắt buộc còn trống thì
ngân hàng không nhận file — không có chuyện tiền đi nhầm ngân hàng trong im
lặng. Cột "Chi nhánh ngân hàng hưởng" để trống: theo hướng dẫn của mẫu, chuyển
tới SỐ TÀI KHOẢN chỉ cần chọn ngân hàng.

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

# Tên gọi tắt hay gặp mà danh sách của mẫu không có.
BI_DANH = {
    "VCB": "VIETCOMBANK", "CTG": "VIETINBANK", "VTB": "VIETINBANK",
    "VIETTINBANK": "VIETINBANK", "TCB": "TECHCOMBANK", "MBBANK": "MB",
    "VPB": "VPBANK", "TPB": "TPBANK", "STB": "SACOMBANK", "HDB": "HD BANK",
}

# Đuôi chỉ là ĐỊA DANH ("… - Taipei Fubon - Binh Duong", "… - SMBC - TP HCM"):
# đưa vào bảng dò là chữ "Bình Dương" trên phiếu lương khớp nhầm một ngân hàng
# Đài Loan.
DIA_DANH = {("BINH", "DUONG"), ("TPHCM",), ("TP", "HCM"), ("HCM",), ("HA", "NOI"),
            ("HANOI",), ("HN",)}
# Chữ đầu tên mà người ta thêm/bớt tùy ý: "Ngân hàng TMCP Quân đội" = "Quân đội".
_DAU_TEN = {"NGAN", "HANG", "NH", "TMCP", "TM", "CP", "TNHH", "MTV"}

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


def _tu(s):
    """Dãy từ IN HOA không dấu — khóa so tên ngân hàng."""
    return tuple(re.findall(r"[A-Z0-9]+", _khong_dau(s).upper()))


def _loi(tu):
    """Bỏ chữ đầu chung chung: ("NGAN","HANG","TMCP","QUAN","DOI") → ("QUAN","DOI")."""
    i = 0
    while i < len(tu) and tu[i] in _DAU_TEN:
        i += 1
    return tu[i:]


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


def _mot(tap):
    """Phần tử duy nhất của tập, hoặc None nếu rỗng/nhiều."""
    tap = set(tap or ())
    return next(iter(tap)) if len(tap) == 1 else None


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
    """Các bảng dò ngân hàng, dựng từ CHÍNH sheet danh sách của mẫu."""
    theo_ma, theo_tctd = {}, {}
    for r in sorted(nh_rows):
        if r < 2:
            continue
        ma, hien = cstr(nh_rows[r].get("B")).strip(), cstr(nh_rows[r].get("C")).strip()
        if re.fullmatch(r"\d{8}", ma) and hien:
            theo_ma.setdefault(ma, set()).add(hien)
            theo_tctd.setdefault(ma[2:5], set()).add(hien)

    chi_nhanh, ten = {}, {}

    def them(k, hien, ca_loi=True):
        for x in ((k, _loi(k)) if ca_loi else (k,)):
            if x and x not in DIA_DANH:
                ten.setdefault(x, set()).update(hien)

    for ds in theo_ma.values():
        for hien in ds:
            phan = hien.split(" - ")
            if len(phan) >= 2:
                them(_tu(phan[1]), {hien})                 # tên đầy đủ
            if len(phan) >= 3:
                them(_tu(phan[-1]), {hien}, False)         # tên viết tắt
    for r in sorted(cn_rows):
        if r < 2:
            continue
        ma_nh = cstr(cn_rows[r].get("B")).strip()
        m = re.match(r"(\d{8})\b", cstr(cn_rows[r].get("D")).strip())
        if m and ma_nh:
            chi_nhanh.setdefault(m.group(1), ma_nh)
        if ma_nh in theo_ma:
            them(_tu(cn_rows[r].get("C")), theo_ma[ma_nh])  # tên CITAD
    gon = {}
    for k, ds in ten.items():
        gon.setdefault("".join(k), set()).update(ds)
    return {"theo_ma": theo_ma, "theo_tctd": theo_tctd, "chi_nhanh": chi_nhanh,
            "ten": ten, "ten_gon": gon,
            "danh_sach": sorted({h for ds in theo_ma.values() for h in ds})}


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


# ── dò ngân hàng ─────────────────────────────────────────────────────────

def _theo_ma(ma, bang):
    """(hiển thị | None, lý do) từ các mã 8 số — mẫu cũ ghi mã ở CUỐI chuỗi."""
    for code in reversed(ma):
        ds = bang["theo_ma"].get(code)
        if ds:
            d = _mot(ds)
            if d:
                return d, ""
            return None, "mã %s ứng với %d dòng trong danh sách của mẫu" % (code, len(ds))
        ma_nh = bang["chi_nhanh"].get(code)
        if ma_nh:
            ds = bang["theo_ma"].get(ma_nh)
            d = _mot(ds)
            if d:
                return d, ""
            return None, "mã chi nhánh %s thuộc ngân hàng %s — %s" % (
                code, ma_nh, "ứng với nhiều dòng trong danh sách của mẫu" if ds
                else "không có trong danh sách của mẫu")
        d = _mot(bang["theo_tctd"].get(code[2:5]))
        if d:
            return d, ""
    return None, "mã %s không có trong danh sách ngân hàng/chi nhánh của mẫu" % ", ".join(ma)


def _theo_ten(tu, bang):
    """(hiển thị | None, lý do) từ chữ — tiền tố DÀI NHẤT, chỉ nhận khi ra MỘT."""
    # Từ sát chữ gốc tới chuẩn hóa nhiều nhất; lượt nào khớp (một hay nhiều)
    # là dừng ở lượt đó — không để lượt sau "chữa" một kết quả mơ hồ.
    lan = []
    for t in (tu, (_tu(BI_DANH[tu[0]]) + tu[1:]) if tu and tu[0] in BI_DANH else tu):
        for x in (t, _loi(t)):
            if x and x not in lan:
                lan.append(x)
    for t in lan:
        dai = 0
        ds = set()
        for k, hien in bang["ten"].items():
            if len(k) >= dai and t[:len(k)] == k:
                if len(k) > dai:
                    dai, ds = len(k), set()
                ds |= hien
        if not dai:
            ds = set(bang["ten_gon"].get(t[0], ()))   # "HDBank" = "HD BANK"
        if len(ds) == 1:
            return next(iter(ds)), ""
        if len(ds) > 1:
            return None, "tên khớp %d ngân hàng trong danh sách" % len(ds)
    return None, "không nhận ra ngân hàng"


def tim_ngan_hang(text, bang):
    """(chuỗi trong danh sách | None, cách dò "ma"/"ten"/"", lý do khi không ra).

    Có mã 8 số thì theo MÃ; phần chữ còn lại mà chỉ đích danh một ngân hàng
    KHÁC (khác mã tổ chức tín dụng — 3 số giữa) thì không đoán bên nào đúng:
    trả None để người sửa phiếu lương.
    """
    goc = _khong_dau(text)
    tu = _tu(goc)
    if not tu:
        return None, "", "phiếu lương chưa ghi ngân hàng"
    ma = re.findall(r"(?<!\d)\d{8}(?!\d)", goc)
    if ma:
        d, ly_do = _theo_ma(ma, bang)
        if not d:
            return None, "", ly_do
        chu = tuple(t for t in tu if not t.isdigit())
        d_ten = _theo_ten(chu, bang)[0] if chu else None
        if d_ten and d_ten[2:5] != d[2:5]:
            return None, "", "chữ trên phiếu chỉ “%s” nhưng mã chỉ “%s” — hai ngân hàng khác nhau" % (d_ten, d)
        return d, "ma", ""
    d, ly_do = _theo_ten(tu, bang)
    return (d, "ten", "") if d else (None, "", ly_do)


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
    chưa dò ra ngân hàng VẪN ghi, ô đó để trống hoặc giữ nguyên, và báo — ngân
    hàng sẽ không nhận file cho tới khi sửa, nên không ai bị sót lương trong im
    lặng.
    """
    if not isinstance(dong, (list, tuple)):
        frappe.throw(_("Dữ liệu chuyển khoản không hợp lệ."))
    m = _doc_mau(path)
    bang = m["bang"]
    nd = _lam_sach_noi_dung(noi_dung) or NOI_DUNG_MAC_DINH

    du_lieu, canh_bao, bo_qua = {}, [], []
    theo_ten, theo_tk = {}, {}
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
        hien, cach, ly_do = tim_ngan_hang(nh_goc, bang)
        if not hien:
            canh_bao.append("%s: chưa xác định được Ngân hàng hưởng từ “%s” (%s) — mở file, chọn "
                            "ngân hàng ở cột D trước khi tải lên" % (nhan, cstr(nh_goc).strip(), ly_do))
        elif cach == "ten":
            k = cstr(nh_goc).strip()
            theo_ten.setdefault(k, [hien, 0])[1] += 1

        vals = {"A": ("n", stt), "E": ("s", str(tien)), "F": ("s", TIEN_TE), "G": ("s", nd)}
        if ten:
            vals["B"] = ("s", ten)
        if tk:
            vals["C"] = ("s", tk)
        if hien:
            vals["D"] = ("s", hien)
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

    ghi_chu = ["dò theo TÊN: “%s” → %s (%d người) — liếc lại cho chắc" % (k, v[0], v[1])
               for k, v in sorted(theo_ten.items())]
    return out.getvalue(), {"so_dong": len(du_lieu), "tong_tien": tong,
                            "canh_bao": canh_bao, "bo_qua": bo_qua, "ghi_chu": ghi_chu}


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
