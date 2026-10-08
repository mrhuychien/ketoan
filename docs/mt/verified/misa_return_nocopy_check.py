#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm: HÓA ĐƠN TRẢ HÀNG không được chở số hóa đơn của bản gốc.

════════════════════════════════════════════════════════════════════════════
CON BUG BỘ KIỂM NÀY CANH — ĐÃ ĐO TRÊN PRODUCTION 08/10/2026
════════════════════════════════════════════════════════════════════════════

    91 nhóm / 182 chứng từ dùng chung MỘT `custom_misa_ref_id` và MỘT số hóa đơn.
    Phân loại: 92 hóa đơn BÁN + 90 hóa đơn TRẢ HÀNG.

Mỗi nhóm là một hóa đơn gốc và hóa đơn TRẢ HÀNG của chính nó. Nút "Return" của
ERPNext đi qua `get_mapped_doc` → `frappe/model/mapper.py::map_fields`, và hàm
đó loại field khỏi phép chép CHỈ khi `d.no_copy == 1`:

    no_copy_fields = set([d.fieldname for d in source_doc.meta.get("fields")
                          if (d.no_copy == 1 or d.fieldtype in table_fields)] ...)
    for df in target_doc.meta.get("fields"):
        if df.fieldname not in no_copy_fields:
            val = source_doc.get(df.fieldname)
            if val not in (None, ""): target_doc.set(df.fieldname, val)

17/17 field `custom_misa_*` KHÔNG khai `no_copy` (nhóm cũ `vn_einvoice_*` thì
CÓ), nên bản trả hàng chở nguyên RefID + số hóa đơn + cờ đã-đẩy. Mà
`ensure_ref_id` chỉ dọn ở nhánh `amended_from` — bản trả hàng KHÔNG phải bản
sửa đổi, nên cleanup không chạy.

HẬU QUẢ đo được: vòng 2 của `poll_pending` KHÔNG lọc `is_return`, nên nó hỏi
MISA bằng RefID đi vay, nhận về hóa đơn GỐC, rồi `check_amount_drift` so
`abs(m) - abs(e)` giữa tiền gốc và tiền trả hàng ÂM ⇒ lệch khổng lồ ⇒ dán
"Lệch tiền" cho hàng loạt chứng từ bình thường, lặp lại mỗi 30 phút. Đúng kiểu
làm kế toán mất niềm tin vào cảnh báo rồi bỏ qua cả cảnh báo thật.

KHÔNG phải phát hành trùng: `misa_push.py` chặn hẳn `is_return` ở cổng đẩy.

BA CẠM BẪY khi sửa, mỗi cái một mục kiểm:

  1. Lọc bằng SQL `is_return != 1` ⇒ LOẠI LUÔN hàng NULL (NULL != 1 ra NULL,
     không phải TRUE). Cột Check trên bảng có sẵn dữ liệu mang NULL chứ không
     phải 0 — đúng cái bẫy patch v0_0_17 đã phải chữa. Phải lọc ở Python.
  2. Chỉ thêm `no_copy` vào `install.py` mà không có patch ⇒ field ĐÃ TẠO trên
     site không đổi. Phải đặt thẳng bằng `set_value`.
  3. Đặt `no_copy` cho cả field layout (section/column break) ⇒ nhiễu, và danh
     sách trong patch lệch với `install.py` thì sau này không ai biết cái nào đúng.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
    python3 docs/mt/verified/misa_return_nocopy_check.py   # exit 0 = đạt
"""

import importlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

ok_all = True
SI_ROWS = []     # các dòng get_all("Sales Invoice") trả về
DA_HOI = []      # RefID nào thực sự bị đem đi hỏi MISA


def check(label, cond, detail=""):
    global ok_all
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def set(self, k, v):
        self[k] = v


class _Meta:
    def __init__(self, fields):
        self._f = set(fields)

    def has_field(self, f):
        return f in self._f


MISA_FIELDS = [
    "custom_misa_status", "custom_misa_inv_series", "custom_misa_inv_no",
    "custom_misa_inv_date", "custom_misa_transaction_id", "custom_misa_invoice_code",
    "custom_misa_link", "custom_misa_ref_id", "custom_misa_relation",
    "custom_misa_org_ref_id", "custom_misa_org_inv", "custom_misa_pushed_at",
    "custom_misa_last_checked", "custom_misa_note", "custom_misa_no_locked",
]
LAYOUT_FIELDS = ["custom_misa_section", "custom_misa_column_break"]



# ══════════════════════════════════════════════════════════════════════════
# Rổ "Trả hàng" của trang Hóa đơn VAT
# ══════════════════════════════════════════════════════════════════════════
#
# Dọn ~90 bản trả hàng đang chở số đi vay sẽ ĐẨY chúng từ rổ "Đã liên kết"
# sang rổ "Chỉ có trên phần mềm" — tức sáng hôm sau kế toán thấy 90 hóa đơn
# "bán mà chưa xuất", một tồn giả do chính việc dọn tạo ra. Nên rổ phải tách
# TRƯỚC khi dọn.
#
# KHÔNG quét chữ trong file: ở đây lấy mệnh đề WHERE mà production THẬT SỰ
# gửi xuống MariaDB, dịch sang Python, rồi xem 4 chứng từ mẫu rơi vào rổ nào.
# Quét chữ thì đổi `= 0` thành `= 1` vẫn đạt.

import re as _re

_DK = _re.compile(
    r"IFNULL\(\s*(?:si\.)?(\w+)\s*,\s*(0|'')\s*\)\s*(=|!=)\s*(0|1|'')")

_BO_QUA = (
    "docstatus = 1", "si.docstatus = 1",
    "company = %(company)s", "si.company = %(company)s",
    "posting_date BETWEEN %(fd)s AND %(td)s",
    "si.posting_date BETWEEN %(fd)s AND %(td)s",
)


def _dich_where(where):
    """SQL → danh sách hàm vị từ. Mệnh đề lạ ⇒ NỔ, không im lặng cho qua."""
    # `BETWEEN a AND b` phải bỏ TRƯỚC khi tách theo AND, không thì chính chữ
    # AND bên trong nó cắt mệnh đề ra làm hai nửa vô nghĩa.
    where = _re.sub(r"\S*posting_date\s+BETWEEN\s+\S+\s+AND\s+\S+", "", where)
    vt = []
    for m in [x.strip() for x in _re.split(r"\bAND\b", where) if x.strip()]:
        m = m.strip("() \n")
        if m in _BO_QUA:
            continue
        g = _DK.fullmatch(m)
        if not g:
            raise AssertionError(f"mệnh đề chưa dịch được: {m!r}")
        field, mac_dinh, op, mong = g.groups()
        md = 0 if mac_dinh == "0" else ""
        mg = 0 if mong == "0" else (1 if mong == "1" else "")

        def f(r, field=field, md=md, op=op, mg=mg):
            v = r.get(field)
            if v is None:
                v = md
            v = int(v) if isinstance(mg, int) else str(v)
            return (v == mg) if op == "=" else (v != mg)

        vt.append(f)
    return vt


MAU = [
    # bán thường, đã có số  → linked
    _D(name="A-BAN-CO-SO", is_return=0, custom_misa_inv_no="00008040", grand_total=10.8e6),
    # TRẢ HÀNG chở số ĐI VAY của bản gốc → phải ra rổ trả hàng, KHÔNG phải linked
    _D(name="B-TRA-SO-VAY", is_return=1, custom_misa_inv_no="00008040", grand_total=-1.08e6),
    # hàng CŨ: is_return = NULL, chưa có số → erp_only (không được rụng vì NULL)
    _D(name="C-CU-NULL", is_return=None, custom_misa_inv_no=None, grand_total=5.4e6),
    # trả hàng đã dọn sạch → rổ trả hàng, KHÔNG phải "bán mà chưa xuất"
    _D(name="D-TRA-DA-DON", is_return=1, custom_misa_inv_no=None, grand_total=-2e6),
]


def _loc(where):
    vt = _dich_where(where)
    return [r["name"] for r in MAU if all(f(r) for f in vt)]


def section7(frappe, check):
    print("-" * 78)
    print("── 7. Trang Hóa đơn VAT: trả hàng ra rổ riêng, không tạo tồn giả ───")
    vat = importlib.import_module("ketoan.api.misa_vat")

    # ── 7a. Ba rổ phía ERPNext: soi mệnh đề WHERE THẬT của _si_rows ──
    bat = {}

    def _sql(q, p=None, as_dict=False):
        if "tabSales Invoice" in q and "COUNT(*)" in q:
            w = q.split("WHERE", 1)[1].split("ORDER BY")[0].split("LIMIT")[0]
            bat["where"] = w
            return [[0]]
        return []

    frappe.db.sql = _sql
    ro = {}
    for mode in ("linked", "erp_only", "tra_hang"):
        vat._si_rows("CTY", "2026-01-01", "2026-12-31", mode, None, 20)
        try:
            ro[mode] = _loc(bat["where"])
        except AssertionError as e:
            check(f"dịch được mệnh đề WHERE của rổ {mode}", False, str(e)[:70])
            ro[mode] = None

    check("rổ 'Đã liên kết' CHỈ có hóa đơn bán đã có số",
          ro.get("linked") == ["A-BAN-CO-SO"], str(ro.get("linked")))
    check("rổ 'Chỉ có trên phần mềm' KHÔNG chứa bản trả hàng nào",
          ro.get("erp_only") == ["C-CU-NULL"], str(ro.get("erp_only")))
    check("và hàng CŨ is_return=NULL VẪN vào rổ đó — không rụng vì NULL",
          ro.get("erp_only") is not None and "C-CU-NULL" in ro["erp_only"])
    check("rổ 'Trả hàng' gom cả bản chở số đi vay và bản đã dọn",
          ro.get("tra_hang") == ["B-TRA-SO-VAY", "D-TRA-DA-DON"], str(ro.get("tra_hang")))
    check("mỗi chứng từ vào ĐÚNG MỘT rổ, không trùng không lọt",
          ro.get("linked") is not None and
          sorted(ro["linked"] + ro["erp_only"] + ro["tra_hang"]) ==
          sorted(r["name"] for r in MAU),
          str(ro))

    # ── 7b. get_overview: đếm thật trên 4 chứng từ mẫu ──
    dem = {}

    def _sql_ov(q, p=None, as_dict=False):
        if "tabSales Invoice" not in q:
            return [_D(cnt=0, amt=0.0)]
        if "custom_misa_status" in q:          # si_mismatch — có NOT EXISTS
            dem["sm_where"] = q
            return [_D(cnt=0)]
        w = q.split("WHERE", 1)[1]
        ten = _loc(w)
        return [_D(cnt=len(ten), amt=sum(abs(r["grand_total"]) for r in MAU
                                         if r["name"] in ten))]

    frappe.db.sql = _sql_ov
    frappe.db.count = lambda *a, **k: 0
    frappe.get_all = lambda *a, **k: []
    vat.guard_sales_any = lambda *a, **k: None
    vat.is_chief = lambda *a, **k: False
    try:
        ov = vat.get_overview(company="CTY", from_date="2026-01-01", to_date="2026-12-31")
    except Exception as e:  # noqa: BLE001
        check("chạy được get_overview với bộ giả", False, f"{type(e).__name__}: {e}"[:80])
        return
    b = ov["buckets"]

    check("overview: rổ 'Đã liên kết' đếm 1 (chỉ hóa đơn bán)",
          b["linked"]["count"] == 1, str(b["linked"]))
    check("overview: TỔNG TIỀN rổ đó không cộng thêm trị tuyệt đối tiền trả hàng",
          abs(b["linked"]["amount"] - 10.8e6) < 1, str(b["linked"]["amount"]))
    check("overview: rổ 'Chỉ có trên phần mềm' đếm 1, không phải 3",
          b["erp_only"]["count"] == 1, str(b["erp_only"]))
    check("overview: có rổ 'Trả hàng' và đếm đúng 2",
          b.get("tra_hang", {}).get("count") == 2, str(b.get("tra_hang")))
    # Truy vấn này có `NOT EXISTS (...)` nên không dịch sang vị từ được —
    # chỗ duy nhất trong mục 7 phải soi chữ, và nói thẳng ra là vậy.
    sm_ok = "IFNULL(si.is_return, 0) = 0" in dem.get("sm_where", "")
    check("overview: đếm 'Lệch tiền' phía ERPNext cũng loại trả hàng (soi chữ)",
          sm_ok, "" if sm_ok else
          ("chua loai" if "sm_where" in dem else "khong thay truy van"))

    # ── 7c. Rổ mới phải có mặt ở danh sách hợp lệ VÀ trên màn hình ──
    check("tra_hang nằm trong BUCKETS (get_invoices không chặn)",
          "tra_hang" in vat.BUCKETS, str(vat.BUCKETS))
    js = io.open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/vat.js"),
                 encoding="utf-8").read()
    check("màn hình có thẻ/tab cho rổ tra_hang",
          'key: "tra_hang"' in js)
    check("bảng rổ trả hàng bày cột Số HĐ (chỗ nhìn ra số đi vay)",
          'tab === "tra_hang"' in js and 'const linked = tab === "linked" || tab === "tra_hang"' in js)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.commit = lambda *a, **kw: None
    frappe.db.has_column = lambda dt, c: True

    sync = importlib.import_module("ketoan.api.misa_sync")

    print("=" * 78)
    print("misa_return_nocopy_check — bản trả hàng không chở số của bản gốc")
    print("=" * 78)

    # ── 1. no_copy khai đủ trong install.py, và ĐÚNG 15 field ─────────
    print("-" * 78)
    print("── 1. install.py: no_copy cho 15 field dữ liệu, KHÔNG cho field layout ──")
    src = io.open(os.path.join(rc.REPO, "ketoan/install.py"), encoding="utf-8").read()
    blocks = dict(
        (fn, body) for fn, body in re.findall(
            r'\{\s*(?:#[^\n]*\n\s*)*"fieldname":\s*"(custom_misa_[^"]+)"(.*?)\n        \}',
            src, re.S))
    thieu = [f for f in MISA_FIELDS if '"no_copy": 1' not in blocks.get(f, "")]
    check("cả 15 field dữ liệu đều có no_copy", not thieu, ", ".join(thieu)[:70])
    du = [f for f in LAYOUT_FIELDS if '"no_copy": 1' in blocks.get(f, "")]
    check("KHÔNG đặt no_copy cho field layout", not du, ", ".join(du))
    check("danh sách field trong repo đúng 17 cái (không thừa field lạ)",
          len(blocks) == 17, str(len(blocks)))

    # ── 2. Patch phải ĐẶT THẲNG, và danh sách KHỚP install.py ─────────
    print("-" * 78)
    print("── 2. Patch v0_0_19 đặt thẳng bằng set_value, danh sách khớp install.py ──")
    pf = os.path.join(rc.REPO, "ketoan/patches/v0_0_19/misa_no_copy.py")
    check("patch tồn tại", os.path.exists(pf))
    if os.path.exists(pf):
        psrc = io.open(pf, encoding="utf-8").read()
        check("đăng ký trong patches.txt",
              "ketoan.patches.v0_0_19.misa_no_copy" in
              io.open(os.path.join(rc.REPO, "ketoan/patches.txt"), encoding="utf-8").read())
        # Phải GHI THẲNG — không trông vào create_custom_fields tự cập nhật.
        check("đặt thẳng no_copy bằng set_value trên Custom Field",
              'set_value("Custom Field"' in psrc and '"no_copy", 1' in psrc)
        check("và xoá cache Sales Invoice sau khi đổi",
              'clear_cache(doctype="Sales Invoice")' in psrc)
        # Danh sách trong patch phải KHỚP install.py, không thì hai chỗ nói hai
        # điều và sau này không ai biết cái nào đúng.
        #
        # ĐỌC BIẾN THẬT, không quét chữ: regex trên mã nguồn vẫn tìm thấy tên
        # field nằm trong một dòng ĐÃ BỊ COMMENT — đo được bằng đột biến số 4.
        pm = importlib.import_module("ketoan.patches.v0_0_19.misa_no_copy")
        trong_patch = set(pm.FIELDS)
        check("danh sách field trong patch KHỚP 15 field của install.py",
              trong_patch == set(MISA_FIELDS),
              f"patch {len(trong_patch)}: thieu "
              f"{sorted(set(MISA_FIELDS) - trong_patch)}"[:70])

    # ── 3. ensure_ref_id: bản TRẢ HÀNG phải dọn sạch + cấp RefID mới ──
    print("-" * 78)
    print("── 3. ensure_ref_id: hóa đơn TRẢ HÀNG dọn sạch nhóm field MISA ─────")
    FIELDS = MISA_FIELDS + ["amended_from", "is_return", "vn_einvoice_number"]
    d = _D(is_return=1, custom_misa_ref_id="ref-cua-ban-goc",
           custom_misa_inv_no="00008040", custom_misa_inv_series="1C26THG",
           custom_misa_pushed_at="2026-09-01 10:00:00",
           custom_misa_status="Đã phát hành", custom_misa_no_locked=1,
           vn_einvoice_number="00008040")
    d.meta = _Meta(FIELDS)
    sync.ensure_ref_id(d)
    check("số hóa đơn của bản gốc bị dọn", d.custom_misa_inv_no is None,
          repr(d.custom_misa_inv_no))
    check("ký hiệu bị dọn", d.custom_misa_inv_series is None)
    check("cờ đã-đẩy bị dọn", d.custom_misa_pushed_at is None)
    check("ô số cũ (vn_einvoice_number) cũng bị dọn", d.vn_einvoice_number is None)
    check("RefID được cấp MỚI, không giữ của bản gốc",
          d.custom_misa_ref_id and d.custom_misa_ref_id != "ref-cua-ban-goc",
          str(d.custom_misa_ref_id)[:18])
    check("trạng thái về 'Chưa đẩy'", d.custom_misa_status == "Chưa đẩy",
          str(d.custom_misa_status))
    check("cờ khóa về 0 (không phải None — vòng 2 lọc `= 0`)",
          d.custom_misa_no_locked == 0, repr(d.custom_misa_no_locked))

    # ── 4. Hóa đơn THƯỜNG không bị đụng tới ───────────────────────────
    print("-" * 78)
    print("── 4. Hóa đơn bán THƯỜNG: không dọn gì, giữ nguyên RefID ───────────")
    d2 = _D(custom_misa_ref_id="ref-dang-dung", custom_misa_inv_no="00009999",
            custom_misa_no_locked=1, custom_misa_status="Đã phát hành")
    d2.meta = _Meta(FIELDS)
    sync.ensure_ref_id(d2)
    check("giữ nguyên RefID", d2.custom_misa_ref_id == "ref-dang-dung")
    check("giữ nguyên số hóa đơn", d2.custom_misa_inv_no == "00009999")
    check("giữ nguyên cờ khóa người đã gán", d2.custom_misa_no_locked == 1)

    # ── 5. poll_pending BỎ QUA trả hàng, và NÓI RA số bị bỏ ───────────
    #
    # Canh CHỖ DÙNG: khẳng định "có biến so_tra_hang" vẫn đúng y nguyên kể cả
    # khi bộ lọc đã bị gỡ. Ở đây chạy thật `_poll_pending` và xem RefID nào
    # THỰC SỰ bị đem đi hỏi MISA.
    print("-" * 78)
    print("── 5. poll_pending: trả hàng KHÔNG bị đem đi hỏi MISA ──────────────")

    del SI_ROWS[:]
    SI_ROWS.extend([
        _D(name="HD-GOC", custom_misa_ref_id="ref-A", is_return=0,
           net_total=10e6, total_taxes_and_charges=8e5, grand_total=10.8e6,
           custom_misa_pushed_at="x", custom_misa_inv_no="00008040"),
        _D(name="HD-TRA", custom_misa_ref_id="ref-A", is_return=1,
           net_total=-1e6, total_taxes_and_charges=-8e4, grand_total=-1.08e6,
           custom_misa_pushed_at="x", custom_misa_inv_no="00008040"),
        # Hàng CŨ: is_return = NULL. PHẢI VẪN ĐƯỢC QUÉT.
        _D(name="HD-CU", custom_misa_ref_id="ref-B", is_return=None,
           net_total=5e6, total_taxes_and_charges=4e5, grand_total=5.4e6,
           custom_misa_pushed_at="x", custom_misa_inv_no="00007000"),
    ])

    def _get_all(dt, **k):
        return list(SI_ROWS) if dt == "Sales Invoice" else []

    frappe.get_all = _get_all

    # `_poll_pending` TRẢ VỀ TÊN bản ghi `MISA Sync Run`, không trả về `stat`.
    # Các con số đi ra ngoài bằng `setattr(run, k, v)` rồi `run.save()`. Nên bộ
    # giả phải GIỮ LẠI chính cái doc đó mà soi, và phải có `save` — thiếu `save`
    # thì `__getattr__` trả None và hàm nổ `'NoneType' object is not callable`
    # ở tận dòng cuối, sau khi đã chạy đúng hết phần mình đang canh.
    class _Run(_D):
        def insert(self, **kw):
            return self

        def db_set(self, *a, **k):
            return None

        def save(self, *a, **k):
            return self

    RUN = {}

    def _get_doc(d):
        r = _Run(name="RUN-1", **{k: v for k, v in d.items() if k != "doctype"})
        RUN["doc"] = r
        return r

    frappe.get_doc = _get_doc
    sync.get_settings = lambda: _D(amount_tolerance=1.0, use_code_route=1)

    del DA_HOI[:]

    def _call(path, **k):
        DA_HOI.append(path)
        raise sync.MISAError("test", "bo kiem khong goi MISA that")

    sync.call = _call
    sync.invoice_path = lambda tail, settings: tail

    run = None
    try:
        sync._poll_pending(limit=50, lookback_days=60)
        run = RUN.get("doc")
    except Exception as e:  # noqa: BLE001
        check("chạy được _poll_pending với bộ giả", False, f"{type(e).__name__}: {e}")

    if run is not None:
        hoi = " ".join(DA_HOI)
        check("hóa đơn GỐC bị đem đi hỏi MISA", "ref-A" in hoi, hoi[:70])
        check("hàng CŨ (is_return = NULL) VẪN bị quét — không lọt bẫy NULL",
              "ref-B" in hoi, hoi[:70])
        check("đúng 2 lượt hỏi (gốc + hàng cũ), KHÔNG hỏi cho bản trả hàng",
              len(DA_HOI) == 2, f"{len(DA_HOI)} luot: {hoi[:60]}")
        check("và GHI RA số bản trả hàng đã bỏ qua trên MISA Sync Run",
              run.get("skipped_return") == 1, repr(run.get("skipped_return")))

    # ── 6. Con số bỏ qua phải CÓ Ô ĐỂ ĐỰNG trên doctype ───────────────
    #
    # `setattr(run, "skipped_return", 1)` trên một Document Frappe KHÔNG nổ khi
    # doctype không có field đó — `save()` lặng lẽ bỏ qua thuộc tính lạ. Tức mục
    # 5 vẫn ĐẠT trong khi con số không bao giờ tới mắt ai. Phải canh cả cái ô.
    print("-" * 78)
    print("── 6. MISA Sync Run có ô 'skipped_return' để con số không rơi mất ──")
    import json
    dj = json.load(io.open(os.path.join(
        rc.REPO, "ketoan/misa_integration/doctype/misa_sync_run/misa_sync_run.json"),
        encoding="utf-8"))
    fns = [f["fieldname"] for f in dj["fields"]]
    check("doctype khai field skipped_return", "skipped_return" in fns)
    check("field_order khớp danh sách fields (không thì Frappe bỏ field ra khỏi form)",
          dj.get("field_order") == fns)
    f = next((x for x in dj["fields"] if x["fieldname"] == "skipped_return"), {})
    check("là Int và read_only", f.get("fieldtype") == "Int" and f.get("read_only") == 1,
          f"{f.get('fieldtype')}/{f.get('read_only')}")
    # Frappe chỉ nạp lại doctype khi file đổi; mốc `modified` cũ hơn bản trên
    # site là field mới không bao giờ xuất hiện sau `bench migrate`.
    check("mốc modified của doctype đã được dời lên (>= 2026-10-08)",
          str(dj.get("modified", ""))[:10] >= "2026-10-08", str(dj.get("modified"))[:10])

    section7(frappe, check)

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — bản trả hàng không chở số của bản gốc, không bị đem đi "
              "hỏi MISA, và hàng cũ is_return=NULL vẫn được quét.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
