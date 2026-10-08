#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm `ketoan.api.misa_return_cleanup` — dọn danh tính MISA đi vay trên hóa
đơn trả hàng đã ghi sổ.

════════════════════════════════════════════════════════════════════════════
VÌ SAO BỘ KIỂM NÀY ĐƯỢC VIẾT LẠI
════════════════════════════════════════════════════════════════════════════

Bản trước báo 40/40 ĐẠT và đột biến 12/12 — trong khi công cụ chạy trên site
ra 0 dọn / 479 cần người xem. Dữ liệu mẫu của nó không giống site ở đúng chỗ
quyết định: không bản trả hàng mẫu nào mang `custom_misa_last_checked`, ghi
chú lệch tiền, hay số kế toán gõ tay. Màu xanh đó độc lập với việc công cụ có
làm được gì ngoài đời.

Bản này dựng mẫu THEO HÌNH DẠNG ĐO ĐƯỢC TRÊN SITE (08/10/2026,
docs/misa/sql/chandoan_tra_hang.sql): 106 bản chép từ gốc, 90 có số, 38 mang
"Lệch tiền" giả, ô số cũ có cả số máy chép ("00008754"), số gõ tay rút gọn
("8433") và chữ ("7894- HOÀN"), 34 bản bị cờ khóa / trạng thái cuối.

Mục 11 là chốt hồi quy của chính lỗi 0/479: một bản trả hàng chỉ khác bản
gốc ở dấu giờ kiểm tra lần cuối PHẢI vào kế hoạch dọn.

    python3 docs/mt/verified/misa_return_cleanup_check.py   # exit 0 = đạt
"""

import importlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

ok_all = True


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


FIELDS_CO = {
    "custom_misa_inv_series", "custom_misa_inv_no", "custom_misa_inv_date",
    "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
    "custom_misa_pushed_at", "custom_misa_last_checked", "custom_misa_relation",
    "custom_misa_org_ref_id", "custom_misa_org_inv", "custom_misa_note",
    "custom_misa_ref_id", "custom_misa_status", "custom_misa_no_locked",
    "vn_einvoice_number", "vn_einvoice_date", "vn_einvoice_lookup_code",
    "return_against",
}

DRIFT = ("trước thuế: MISA 15,520,050 ≠ ERPNext 1,783,950 (lệch 13,736,100) · "
         "tổng tiền: MISA 16,761,654 ≠ ERPNext 1,926,666 (lệch 14,834,988)")


def _goc(name, ref, so=None, **k):
    d = dict(name=name, docstatus=1, is_return=0, custom_misa_ref_id=ref,
             custom_misa_inv_no=so, custom_misa_inv_series="1C26THG" if so else None,
             custom_misa_status="Đã phát hành" if so else "Chưa đẩy",
             custom_misa_no_locked=0, posting_date="2026-09-01", grand_total=10e6)
    d.update(k)
    return _D(d)


def _tra(name, goc, ref, so=None, **k):
    d = dict(name=name, docstatus=1, is_return=1, return_against=goc,
             custom_misa_ref_id=ref, custom_misa_inv_no=so,
             custom_misa_inv_series="1C26THG" if so else None,
             custom_misa_status="Đã phát hành" if so else "Chưa đẩy",
             custom_misa_no_locked=0, posting_date="2026-09-20", grand_total=-1e6,
             customer="KH")
    d.update(k)
    return _D(d)


def lam_bang():
    """Mỗi cặp G/R là một hình dạng ĐO ĐƯỢC trên site."""
    b = {}

    def them(*ds):
        for d in ds:
            b[d.name] = d

    # R-1 · HÌNH DẠNG PHỔ BIẾN NHẤT: chép đủ, cộng tiếng ồn mà đồng bộ ghi SAU
    # khi chép — last_checked có micro-giây, note lệch tiền giả, "Lệch tiền",
    # và ô số cũ do _legacy_values chép từ chính số đi vay.
    them(_goc("G-1", "ref-1", "00008754", custom_misa_inv_date="2026-09-01",
              custom_misa_transaction_id="TX1", custom_misa_pushed_at="2026-09-01 10:00:00",
              custom_misa_last_checked="2026-10-08 16:00:00.000001",
              vn_einvoice_number="8754"),
         _tra("R-1", "G-1", "ref-1", "00008754", custom_misa_inv_date="2026-09-01",
              custom_misa_transaction_id="TX1", custom_misa_pushed_at="2026-09-01 10:00:00",
              custom_misa_last_checked="2026-10-08 17:02:30.720988",
              custom_misa_note=DRIFT, custom_misa_status="Lệch tiền",
              vn_einvoice_number="00008754", vn_einvoice_date="2026-09-01",
              vn_einvoice_lookup_code="TX1"))
    # R-2 · ô số cũ là CHỮ kế toán gõ ("7894- HOÀN") + ghi chú người viết.
    them(_goc("G-2", "ref-2", "00007894"),
         _tra("R-2", "G-2", "ref-2", "00007894",
              custom_misa_note="kế toán: đã gọi siêu thị, chờ biên bản",
              vn_einvoice_number="7894- HOÀN"))
    # R-3 · ô số cũ là số gõ tay rút gọn ("8433" ≠ "00008433" từng byte).
    them(_goc("G-3", "ref-3", "00008433"),
         _tra("R-3", "G-3", "ref-3", "00008433", vn_einvoice_number="8433"))
    # R-4 · chỉ mượn RefID, chưa mượn số (gốc chưa phát hành lúc chép).
    them(_goc("G-4", "ref-4"),
         _tra("R-4", "G-4", "ref-4", custom_misa_no_locked=None))
    # R-5 · cờ khóa GIỐNG bản gốc ⇒ chép theo, không phải quyết định của người.
    them(_goc("G-5", "ref-5", "00005000", custom_misa_no_locked=1),
         _tra("R-5", "G-5", "ref-5", "00005000", custom_misa_no_locked=1))
    # R-6 · "Đã thay thế" dán NHẦM vào trả hàng (RefID chung), gốc vẫn phát hành.
    them(_goc("G-6", "ref-6", "00006000"),
         _tra("R-6", "G-6", "ref-6", "00006000", custom_misa_status="Đã thay thế"))
    # R-7 · cờ khóa bật RIÊNG trên trả hàng ⇒ có người khóa ⇒ chặn.
    them(_goc("G-7", "ref-7", "00007000"),
         _tra("R-7", "G-7", "ref-7", "00007000", custom_misa_no_locked=1))
    # R-8 · trả hàng KHÔNG có return_against, có số ⇒ ngoài phạm vi.
    them(_tra("R-8", None, "ref-8-rieng", "00004444"))
    # R-9 · số RIÊNG khác gốc (vd số hóa đơn điều chỉnh của chính nó) ⇒ ngoài.
    them(_goc("G-9", "ref-9", "00003000"),
         _tra("R-9", "G-9", "ref-9-rieng", "00008584"))
    # R-10 · RefID riêng, số = số gốc (đường "Chuyển số HĐ cũ") ⇒ ngoài.
    them(_goc("G-10", "ref-10", "00002000"),
         _tra("R-10", "G-10", "ref-10-rieng", "00002000"))
    # R-11 · RefID của gốc nhưng KÝ HIỆU khác ⇒ có người sửa ⇒ cần tay.
    them(_goc("G-11", "ref-11", "00001100"),
         _tra("R-11", "G-11", "ref-11", "00001100", custom_misa_inv_series="1C26XXX"))
    # R-12 · trả hàng SẠCH: RefID riêng, chỉ có tiếng ồn + số gõ tay ⇒ im lặng.
    them(_goc("G-12", "ref-12", "00001200"),
         _tra("R-12", "G-12", "ref-12-rieng",
              custom_misa_last_checked="2026-10-08 17:00:26.133803",
              custom_misa_note="ghi chú", vn_einvoice_number="HOÀN"))
    # R-13 · trả hàng cũ không RefID, không gì cả ⇒ im lặng.
    them(_tra("R-13", None, None))
    # R-14 · gốc ĐÃ HỦY ⇒ chưa gặp ngoài đời ⇒ cần tay, không tự dọn.
    them(_goc("G-14", "ref-14", "00001400", docstatus=2),
         _tra("R-14", "G-14", "ref-14", "00001400"))
    # Bán hàng cũ is_return = NULL — KHÔNG được coi là trả hàng.
    them(_D(name="G-15", docstatus=1, is_return=None, custom_misa_ref_id="ref-15",
            custom_misa_inv_no="00001500", posting_date="2026-08-01"))
    return b


def gan_bo_gia(frappe, bang, nk, mt=None, pa=None):
    frappe.db.has_column = lambda dt, c: c in FIELDS_CO or dt.startswith("MT ")
    frappe.db.table_exists = lambda dt: True
    frappe.db.commit = lambda *a, **k: None

    def _sql(q, p=None, as_dict=False):
        p = p or {}
        # Phân luồng theo HÌNH truy vấn. Bí danh phải dựng lại y như SQL thật,
        # không thì production đọc None và kết luận sai cho MỌI chứng từ.
        if "IFNULL(si.is_return, 0) = 1" in q:
            out = []
            for r in sorted(bang.values(), key=lambda x: (x.get("posting_date") or "",
                                                          x.name), reverse=True):
                if r.get("is_return") == 1 and r.get("docstatus") == 1:
                    x = _D(**r)
                    x["ref_id"] = r.get("custom_misa_ref_id")
                    x["trang_thai"] = r.get("custom_misa_status")
                    x["no_locked"] = r.get("custom_misa_no_locked")
                    x["note"] = r.get("custom_misa_note")
                    out.append(x)
            return out
        if "WHERE si.name IN %(ten)s" in q:
            out = []
            for n in p["ten"]:
                if n in bang:
                    r = bang[n]
                    x = _D(**r)
                    x["ref_id"] = r.get("custom_misa_ref_id")
                    x["trang_thai"] = r.get("custom_misa_status")
                    x["no_locked"] = r.get("custom_misa_no_locked")
                    out.append(x)
            return out
        if "`tabMT Hang Hoan`" in q:
            co_loai_bang_ke = "NOT EXISTS" in q
            return [_D(name=h["name"], credit_note=h["credit_note"],
                       chung_tu_can=h["chung_tu_can"])
                    for h in (mt or [])
                    if h["credit_note"] in p["ten"]
                    and (h["chung_tu_can"] or "") != p["khong_can"]
                    and not (co_loai_bang_ke and h["credit_note"] in (pa or ()))]
        raise AssertionError(f"truy vấn chưa lường tới: {q[:90]}")

    frappe.db.sql = _sql

    def _set_value(dt, name, values, field=None, val=None, update_modified=True):
        nk["ghi"].append({"dt": dt, "name": name, "values": dict(values),
                          "update_modified": update_modified})
        nk["thu_tu"].append(("ghi", name))
        for k, v in values.items():
            bang[name][k] = v

    frappe.db.set_value = _set_value

    class _Doc(_D):
        def insert(self, **kw):
            nk["insert"].append(dict(self))
            nk["thu_tu"].append(("comment", self.get("reference_name")))
            return self

    def _get_doc(d, *a, **k):
        nk["get_doc"].append(d.get("doctype") if isinstance(d, dict) else str(d))
        return _Doc(**d) if isinstance(d, dict) else _Doc()

    frappe.get_doc = _get_doc

    def _get_all(dt, filters=None, fields=None, limit=None, **k):
        if dt == "MISA Invoice Snapshot":
            return []
        if dt != "Comment":
            return []
        kw = (filters or {}).get("content", ("like", ""))[1].strip("%")
        return [_D(name=f"CMT-{i}", reference_name=c["reference_name"], content=c["content"])
                for i, c in enumerate(nk["insert"]) if kw in c.get("content", "")]

    frappe.get_all = _get_all


def moi_nk():
    return {"ghi": [], "insert": [], "get_doc": [], "thu_tu": []}


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    cl = importlib.import_module("ketoan.api.misa_return_cleanup")
    importlib.import_module("ketoan.api._guard").guard_manager = lambda *a, **k: None

    MT = [
        {"name": "HH-1", "credit_note": "R-1", "chung_tu_can": "Hóa đơn thay thế"},
        {"name": "HH-2", "credit_note": "R-2", "chung_tu_can": "Không cần chứng từ"},
        {"name": "HH-3", "credit_note": "R-3", "chung_tu_can": "Hóa đơn điều chỉnh"},
    ]
    PA = ("R-3",)   # bảng kê siêu thị đã trỏ về R-3 ⇒ không lật

    print("=" * 78)
    print("misa_return_cleanup_check — dọn danh tính MISA đi vay trên trả hàng")
    print("=" * 78)

    bang = lam_bang()
    nk = moi_nk()
    gan_bo_gia(frappe, bang, nk, MT, PA)
    kh = cl.xem_truoc()
    viec = sorted(v["si"] for v in kh["viec"])
    xoa = {v["si"]: v["xoa"] for v in kh["viec"]}
    tay = {c["si"]: c for c in kh["can_tay"]}
    ngoai = {k: v["so"] for k, v in kh["ngoai_pham_vi"].items()}

    # ── 1. Thành phần kế hoạch ────────────────────────────────────────
    print("-" * 78)
    print("── 1. Kế hoạch đúng những bản CHÉP TỪ GỐC, không hơn không kém ─────")
    check("kế hoạch = R-1..R-5 (chép đủ / số gõ tay / chỉ RefID / khóa chép theo)",
          viec == ["R-1", "R-2", "R-3", "R-4", "R-5"], str(viec))
    check("trong đó 4 bản có số hóa đơn", kh["trong_do_co_so_hd"] == 4,
          str(kh["trong_do_co_so_hd"]))
    check("XEM TRƯỚC KHÔNG GHI GÌ", not nk["ghi"] and not nk["insert"],
          f"{len(nk['ghi'])} ghi, {len(nk['insert'])} insert")
    check("đã quét đủ 14 bản trả hàng ghi sổ, không bị cắt",
          kh["tong_quet"] == 14 and kh["bi_cat"] is False,
          f"{kh['tong_quet']} / bi_cat={kh['bi_cat']}")
    check("bán hàng cũ is_return = NULL không bị coi là trả hàng",
          "G-15" not in viec and "G-15" not in tay)

    # ── 2. Ngoài phạm vi: KHÔNG dọn, KHÔNG nhồi vào danh sách cần tay ───
    print("-" * 78)
    print("── 2. Ngoài phạm vi: đếm gọn, không dọn, không thành nhiễu ─────────")
    g = lambda k: ngoai.get(cl.NGOAI[k], 0)  # noqa: E731
    check("R-8 không có return_against ⇒ 'không có gốc'", g("khong_goc") == 1, str(ngoai))
    check("R-9 số riêng khác gốc ⇒ 'số riêng'", g("so_rieng") == 1)
    check("R-10 RefID riêng, số = gốc ⇒ 'ref riêng số gốc'", g("ref_rieng_so_goc") == 1)
    check("không bản nào ngoài phạm vi lọt vào can_tay",
          not ({"R-8", "R-9", "R-10"} & set(tay)), str(sorted(tay)))
    check("R-12 / R-13 SẠCH ⇒ im lặng, không ở đâu cả",
          not ({"R-12", "R-13"} & (set(viec) | set(tay)))
          and g("ref_rieng_khac") == 0, str(ngoai))

    # ── 3. Ô số cũ: chỉ dọn cái BẰNG ĐÚNG số đi vay ────────────────────
    print("-" * 78)
    print("── 3. vn_einvoice_*: dọn số máy chép, GIỮ số kế toán gõ tay ───────")
    check("R-1: ô số cũ '00008754' = số đi vay ⇒ dọn",
          xoa.get("R-1", {}).get("vn_einvoice_number") == "00008754")
    check("R-1: ngày và mã tra cứu cũ = giá trị đi vay ⇒ dọn",
          "vn_einvoice_date" in xoa.get("R-1", {})
          and "vn_einvoice_lookup_code" in xoa.get("R-1", {}))
    check("R-2: '7894- HOÀN' là chữ người gõ ⇒ GIỮ",
          "vn_einvoice_number" not in xoa.get("R-2", {"vn_einvoice_number": 1}))
    check("R-3: '8433' gõ tay rút gọn (khác byte '00008433') ⇒ GIỮ",
          "vn_einvoice_number" not in xoa.get("R-3", {"vn_einvoice_number": 1}))
    check("R-1: dấu giờ kiểm tra lần cuối được dọn kèm",
          "custom_misa_last_checked" in xoa.get("R-1", {}))
    check("không bao giờ đưa ô ghi chú vào danh sách xoá",
          all("custom_misa_note" not in x for x in xoa.values()))

    # ── 4. Cờ khóa / trạng thái cuối: chỉ chặn khi KHÁC gốc ─────────────
    print("-" * 78)
    print("── 4. Cờ khóa và trạng thái cuối chỉ chặn khi KHÁC bản gốc ─────────")
    check("R-5: khóa GIỐNG gốc ⇒ chép theo ⇒ vẫn dọn", "R-5" in viec)
    check("R-6: 'Đã thay thế' trong khi gốc 'Đã phát hành' ⇒ cần tay",
          "R-6" in tay and "Đã thay thế" in tay["R-6"]["ly_do"])
    check("R-6: nói rõ có thể dán NHẦM và bày trạng thái bản gốc",
          "NHẦM" in tay.get("R-6", {}).get("ly_do", "")
          and tay.get("R-6", {}).get("ban_goc", {}).get("trang_thai") == "Đã phát hành")
    check("R-7: khóa riêng trên trả hàng ⇒ cần tay", "R-7" in tay)
    check("R-11: ký hiệu khác gốc ⇒ cần tay, kèm giá trị của gốc",
          "R-11" in tay and tay["R-11"].get("cua_goc", {}).get(
              "custom_misa_inv_series") == "1C26THG")
    check("R-14: gốc đã hủy ⇒ cần tay, không tự dọn", "R-14" in tay)

    # ── 5. Hậu quả lên MT Hàng Hoàn ────────────────────────────────────
    print("-" * 78)
    print("── 5. Đếm TRƯỚC dòng MT Hàng Hoàn sẽ lật ───────────────────────────")
    lat = sorted(h["name"] for h in kh["mt_hang_hoan_se_lat"])
    check("chỉ HH-1 lật (HH-2 không cần chứng từ, HH-3 đã có bảng kê)",
          lat == ["HH-1"], str(lat))

    # ── 6. Vân tay ─────────────────────────────────────────────────────
    print("-" * 78)
    print("── 6. Vân tay sai ⇒ không ghi; vân tay phủ đủ thứ sẽ bị ghi đè ─────")
    try:
        cl.don(van_tay="vantay-bua")
        check("vân tay sai thì NỔ", False, "chạy qua")
    except Exception as e:  # noqa: BLE001
        check("vân tay sai thì NỔ", "KHÔNG khớp" in str(e), str(e)[:50])
    check("và không ghi gì", not nk["ghi"] and not nk["insert"])
    try:
        cl.don(van_tay="")
        check("thiếu vân tay thì NỔ", False, "chạy qua")
    except Exception as e:  # noqa: BLE001
        check("thiếu vân tay thì NỔ", "Thiếu vân tay" in str(e))

    vt = kh["van_tay"]
    # Hai dòng dưới đúng vì KẾ HOẠCH đổi (thêm/bớt chứng từ), không phải vì
    # tham số được băm — xem ghi chú ở bộ đột biến.
    check("cho_phep mở thêm chứng từ ⇒ kế hoạch khác ⇒ vân tay khác",
          cl.xem_truoc(cho_phep=["R-6"])["van_tay"] != vt)
    check("bo_qua bớt chứng từ ⇒ kế hoạch khác ⇒ vân tay khác",
          cl.xem_truoc(bo_qua=["R-1"])["van_tay"] != vt)
    luu = bang["R-1"]["custom_misa_status"]
    bang["R-1"]["custom_misa_status"] = "Đã phát hành"
    check("đổi TRẠNG THÁI cũ (sẽ bị ghi đè) là đổi vân tay",
          cl.xem_truoc()["van_tay"] != vt)
    bang["R-1"]["custom_misa_status"] = luu
    bang["R-4"]["custom_misa_no_locked"] = 1
    bang["G-4"]["custom_misa_no_locked"] = 1
    check("đổi CỜ KHÓA cũ (sẽ bị ghi đè) là đổi vân tay",
          cl.xem_truoc()["van_tay"] != vt)
    bang["R-4"]["custom_misa_no_locked"] = None
    bang["G-4"]["custom_misa_no_locked"] = 0
    luu = bang["R-2"]["custom_misa_inv_no"]
    bang["R-2"]["custom_misa_inv_no"] = bang["G-2"]["custom_misa_inv_no"] = "00007895"
    check("đổi GIÁ TRỊ sắp xoá là đổi vân tay", cl.xem_truoc()["van_tay"] != vt)
    bang["R-2"]["custom_misa_inv_no"] = bang["G-2"]["custom_misa_inv_no"] = luu
    check("dữ liệu trở lại thì vân tay trở lại", cl.xem_truoc()["van_tay"] == vt)
    check("vẫn chưa ghi gì sau mọi lượt xem", not nk["ghi"] and not nk["insert"])

    # ── 7. Dọn thật ────────────────────────────────────────────────────
    print("-" * 78)
    print("── 7. Dọn thật ─────────────────────────────────────────────────────")
    kq = cl.don(van_tay=vt)
    check("báo dọn 5 chứng từ, không lỗi", kq["da_don"] == 5 and not kq["loi"], str(kq)[:80])
    r1 = bang["R-1"]
    check("R-1: số, ký hiệu, ngày, txn, đẩy-lúc đi vay đều sạch",
          all(r1.get(f) is None for f in (
              "custom_misa_inv_no", "custom_misa_inv_series", "custom_misa_inv_date",
              "custom_misa_transaction_id", "custom_misa_pushed_at")))
    check("R-1: ô số cũ máy chép sạch", r1.get("vn_einvoice_number") is None)
    check("R-1: RefID MỚI, không trùng gốc",
          r1["custom_misa_ref_id"] and r1["custom_misa_ref_id"] != "ref-1")
    check("R-1: 'Lệch tiền' giả về 'Chưa đẩy'", r1["custom_misa_status"] == "Chưa đẩy")
    check("R-4: cờ khóa NULL về 0 (không phải None)", bang["R-4"]["custom_misa_no_locked"] == 0,
          repr(bang["R-4"]["custom_misa_no_locked"]))
    check("R-2: số gõ tay '7894- HOÀN' VẪN NGUYÊN",
          bang["R-2"]["vn_einvoice_number"] == "7894- HOÀN")
    check("R-3: số gõ tay '8433' VẪN NGUYÊN", bang["R-3"]["vn_einvoice_number"] == "8433")
    n2 = bang["R-2"]["custom_misa_note"] or ""
    check("R-2: ghi chú người viết GIỮ NGUYÊN ở đầu, chỉ NỐI THÊM một dòng",
          n2.startswith("kế toán: đã gọi siêu thị, chờ biên bản\n") and n2.count("\n") == 1,
          n2[:60])
    check("R-1: dòng nối thêm giải thích ghi chú lệch tiền phía trên",
          DRIFT in (r1["custom_misa_note"] or "")
          and "lệch tiền phía trên" in (r1["custom_misa_note"] or ""))
    check("BẢN GỐC không bị đụng tới",
          bang["G-1"]["custom_misa_inv_no"] == "00008754"
          and bang["G-1"]["custom_misa_ref_id"] == "ref-1")
    check("ngoài phạm vi + cần tay không bị đụng tới",
          bang["R-6"]["custom_misa_inv_no"] == "00006000"
          and bang["R-8"]["custom_misa_inv_no"] == "00004444"
          and bang["R-9"]["custom_misa_inv_no"] == "00008584")
    check("mọi phép ghi đều update_modified=False",
          nk["ghi"] and all(x["update_modified"] is False for x in nk["ghi"]))
    tt = [x for x in nk["thu_tu"] if x[1] == "R-1"]
    check("Comment ghi TRƯỚC phép ghi đè", tt[:2] == [("comment", "R-1"), ("ghi", "R-1")],
          str(tt))
    cmt = next((json.loads(c["content"]) for c in nk["insert"]
                if c["reference_name"] == "R-1"), {})
    check("Comment giữ số cũ, RefID cũ, trạng thái cũ, ghi chú cũ",
          cmt.get("cu", {}).get("custom_misa_inv_no") == "00008754"
          and cmt.get("ref_id_cu") == "ref-1" and cmt.get("trang_thai_cu") == "Lệch tiền"
          and cmt.get("note_cu") == DRIFT)

    # ── 8. Mở khóa CÓ CHỦ Ý bằng cho_phep ─────────────────────────────
    print("-" * 78)
    print("── 8. Người đã xem thì mở được, và chỉ đúng chứng từ đã liệt ──────")
    kh8 = cl.xem_truoc(cho_phep=["R-6"])
    v8 = {v["si"] for v in kh8["viec"]}
    check("cho_phep=['R-6'] ⇒ R-6 vào kế hoạch, R-7 vẫn chặn",
          "R-6" in v8 and "R-7" not in v8 and "R-7" in {c["si"] for c in kh8["can_tay"]},
          str(sorted(v8)))
    kq8 = cl.don(van_tay=kh8["van_tay"], cho_phep=["R-6"])
    check("dọn được R-6 với đúng vân tay + đúng cho_phep",
          kq8["da_don"] == 1 and bang["R-6"]["custom_misa_inv_no"] is None, str(kq8)[:60])

    # ── 9. Lùi ─────────────────────────────────────────────────────────
    print("-" * 78)
    print("── 9. hoan_tac trả về nguyên trạng, kể cả ghi chú ─────────────────")
    nk["insert"].append({"reference_name": "G-1", "content": json.dumps(
        {"moc": "app.khac", "van_tay": vt, "ref_id_cu": "ref-GIA",
         "cu": {"custom_misa_inv_no": "99999999"}})})
    ht = cl.hoan_tac(van_tay=vt)
    r1 = bang["R-1"]
    check("lùi đúng 5 chứng từ của lượt đó", ht["da_tra_lai"] == 5, str(ht)[:60])
    check("R-1 về số, RefID, trạng thái cũ",
          r1["custom_misa_inv_no"] == "00008754" and r1["custom_misa_ref_id"] == "ref-1"
          and r1["custom_misa_status"] == "Lệch tiền")
    check("R-1 về ô số cũ + dấu giờ cũ",
          r1["vn_einvoice_number"] == "00008754"
          and r1["custom_misa_last_checked"] == "2026-10-08 17:02:30.720988")
    check("R-1 ghi chú về NGUYÊN VĂN cũ (bỏ dòng đã nối)", r1["custom_misa_note"] == DRIFT)
    check("Comment của nguồn khác cùng chuỗi vân tay KHÔNG được đem ra lùi",
          bang["G-1"]["custom_misa_inv_no"] == "00008754"
          and bang["G-1"]["custom_misa_ref_id"] == "ref-1")
    check("R-6 (lượt dọn khác vân tay) không bị lượt lùi này đụng",
          bang["R-6"]["custom_misa_inv_no"] is None)

    # ── 10. Không bao giờ hủy / save / submit Sales Invoice ───────────
    print("-" * 78)
    print("── 10. Không đường nào hủy / save / submit Sales Invoice ───────────")
    check("get_doc chỉ từng tạo Comment", set(nk["get_doc"]) <= {"Comment"},
          str(set(nk["get_doc"])))
    src = open(os.path.join(rc.REPO, "ketoan/api/misa_return_cleanup.py"),
               encoding="utf-8").read()
    ma = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    ma = re.sub(r'""".*?"""', "", ma, flags=re.S)
    for xau in (".cancel(", ".submit(", ".save(", "delete_doc", "db_set("):
        check(f"mã nguồn không có `{xau}`", xau not in ma)
    check("mọi set_value đều khai update_modified=False",
          ma.count("set_value(") == ma.count("update_modified=False"),
          f"{ma.count('set_value(')} / {ma.count('update_modified=False')}")

    # ── 11. Chốt hồi quy của chính lỗi 0/479 ──────────────────────────
    print("-" * 78)
    print("── 11. Hồi quy 0/479: chỉ lệch tiếng ồn vẫn PHẢI vào kế hoạch ─────")
    b2 = {"G-X": _goc("G-X", "ref-x", "00007000",
                      custom_misa_last_checked="2026-10-08 16:00:00.000001"),
          "R-X": _tra("R-X", "G-X", "ref-x", "00007000",
                      custom_misa_last_checked="2026-10-08 17:00:26.133803",
                      custom_misa_note=DRIFT, vn_einvoice_number="00007000")}
    gan_bo_gia(frappe, b2, moi_nk())
    k2 = cl.xem_truoc()
    check("bản chỉ lệch last_checked + note ⇒ VÀO kế hoạch, không vào cần tay",
          [v["si"] for v in k2["viec"]] == ["R-X"] and not k2["can_tay"],
          f"viec={[v['si'] for v in k2['viec']]} can_tay={len(k2['can_tay'])}")

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — dọn đúng bản chép từ gốc, giữ số kế toán gõ tay và ghi "
              "chú, chặn cờ/trạng thái do người đặt, vân tay sai thì không ghi, lùi được.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
