#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm `ketoan.api.misa_return_cleanup` — công cụ DỌN SỐ ĐI VAY trên hóa đơn
trả hàng đã ghi sổ.

Đây là thứ GHI VÀO CHỨNG TỪ ĐÃ GHI SỔ, nên bộ kiểm đòi đúng ba nguyên tắc đã
hứa, và đòi ở CHỖ DÙNG chứ không ở chỗ định nghĩa:

  1. chỉ xoá cái chứng minh được là bản chép (giống hệt bản gốc cùng RefID);
  2. vân tay không khớp ⇒ KHÔNG ghi một chữ nào;
  3. lùi được — giá trị cũ ghi vào Comment TRƯỚC khi ghi đè.

Và một điều tuyệt đối: KHÔNG BAO GIỜ hủy / save / submit một Sales Invoice.
Mục 6 ghi lại mọi doctype từng đi qua `frappe.get_doc` để chứng minh điều đó.

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


# ── Bộ giả: 1 bảng Sales Invoice trong bộ nhớ ────────────────────────────────
#
# HD-1xx = hóa đơn bán (bản gốc). HD-2xx = bản trả hàng của nó.
def lam_bang():
    return {
        # (a) cặp SẠCH SẼ để dọn: trả hàng giống hệt bản gốc
        "HD-101": _D(name="HD-101", is_return=0, custom_misa_ref_id="ref-A",
                     custom_misa_inv_no="00008040", custom_misa_inv_series="1C26THG",
                     custom_misa_pushed_at="2026-09-01 10:00:00",
                     vn_einvoice_number="00008040", custom_misa_note="đẩy tự động",
                     custom_misa_status="Đã phát hành", custom_misa_no_locked=0,
                     posting_date="2026-09-01", customer="KH-A", grand_total=10.8e6,
                     return_against=None, docstatus=1),
        "HD-201": _D(name="HD-201", is_return=1, custom_misa_ref_id="ref-A",
                     custom_misa_inv_no="00008040", custom_misa_inv_series="1C26THG",
                     custom_misa_pushed_at="2026-09-01 10:00:00",
                     vn_einvoice_number="00008040", custom_misa_note="đẩy tự động",
                     custom_misa_status="Đã phát hành", custom_misa_no_locked=0,
                     posting_date="2026-09-20", customer="KH-A", grand_total=-1.08e6,
                     return_against="HD-101", docstatus=1),

        # (b) trả hàng CÓ MỘT FIELD KHÁC bản gốc — người đã sửa tay ⇒ chớ đụng
        "HD-102": _D(name="HD-102", is_return=0, custom_misa_ref_id="ref-B",
                     custom_misa_inv_no="00009000", custom_misa_inv_series="1C26THG",
                     custom_misa_status="Đã phát hành", custom_misa_no_locked=0,
                     posting_date="2026-09-02", customer="KH-B", grand_total=5e6,
                     docstatus=1),
        "HD-202": _D(name="HD-202", is_return=1, custom_misa_ref_id="ref-B",
                     custom_misa_inv_no="00009999",   # ← KHÁC: đã có người gán tay
                     custom_misa_inv_series="1C26THG",
                     custom_misa_status="Đã phát hành", custom_misa_no_locked=0,
                     posting_date="2026-09-21", customer="KH-B", grand_total=-1e6,
                     docstatus=1),

        # (c) trả hàng có RefID RIÊNG — không chứng minh được là bản chép
        "HD-203": _D(name="HD-203", is_return=1, custom_misa_ref_id="ref-rieng",
                     custom_misa_inv_no="00007777",
                     custom_misa_status="Đã phát hành", custom_misa_no_locked=0,
                     posting_date="2026-09-22", customer="KH-C", grand_total=-2e6,
                     docstatus=1),

        # (d) RefID dùng chung với HAI hóa đơn bán — cấu trúc lạ
        "HD-104": _D(name="HD-104", is_return=0, custom_misa_ref_id="ref-D",
                     custom_misa_inv_no="00006000", custom_misa_no_locked=0,
                     posting_date="2026-09-03", customer="KH-D", grand_total=3e6,
                     docstatus=1),
        "HD-105": _D(name="HD-105", is_return=0, custom_misa_ref_id="ref-D",
                     custom_misa_inv_no="00006000", custom_misa_no_locked=0,
                     posting_date="2026-09-03", customer="KH-D", grand_total=3e6,
                     docstatus=1),
        "HD-204": _D(name="HD-204", is_return=1, custom_misa_ref_id="ref-D",
                     custom_misa_inv_no="00006000", custom_misa_no_locked=0,
                     posting_date="2026-09-23", customer="KH-D", grand_total=-1e6,
                     docstatus=1),

        # (e) trả hàng ĐÃ SẠCH — không có gì để dọn, không được sinh việc
        "HD-106": _D(name="HD-106", is_return=0, custom_misa_ref_id="ref-E",
                     custom_misa_inv_no="00005000", custom_misa_no_locked=0,
                     posting_date="2026-09-04", customer="KH-E", grand_total=2e6,
                     docstatus=1),
        "HD-205": _D(name="HD-205", is_return=1, custom_misa_ref_id="ref-E2",
                     custom_misa_inv_no=None, custom_misa_no_locked=0,
                     posting_date="2026-09-24", customer="KH-E", grand_total=-5e5,
                     docstatus=1),
    }


FIELDS_CO = (
    "custom_misa_inv_series", "custom_misa_inv_no", "custom_misa_inv_date",
    "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
    "custom_misa_pushed_at", "custom_misa_last_checked", "custom_misa_relation",
    "custom_misa_org_ref_id", "custom_misa_org_inv", "custom_misa_note",
    "vn_einvoice_number", "vn_einvoice_date", "vn_einvoice_lookup_code",
    "custom_misa_ref_id", "custom_misa_status", "custom_misa_no_locked",
)


def gan_bo_gia(frappe, bang, nhat_ky):
    """Nối bộ giả vào frappe. `nhat_ky` thu mọi phép GHI và mọi get_doc."""

    frappe.db.has_column = lambda dt, c: c in FIELDS_CO
    frappe.db.table_exists = lambda dt: True
    frappe.db.commit = lambda *a, **k: None

    def _sql(q, p=None, as_dict=False):
        p = p or {}
        # Phân luồng theo HÌNH truy vấn, không theo chữ: vế `= 1` là lấy bản
        # trả hàng, vế `= 0` là tìm bản gốc theo RefID.
        if "IFNULL(si.is_return, 0) = 1" in q:
            # SQL thật đặt bí danh `AS ref_id / AS trang_thai / AS no_locked`.
            # Bộ giả trả về dict thô là production đọc `r.ref_id` ra None rồi
            # kết luận "RefID không dùng chung" cho MỌI chứng từ — bộ giả sai
            # nguy hiểm hơn không có bộ giả.
            out = []
            for r in bang.values():
                if r.get("is_return") == 1 and r.get("docstatus") == 1 \
                        and (r.get("custom_misa_ref_id") or ""):
                    x = _D(**r)
                    x["ref_id"] = r.get("custom_misa_ref_id")
                    x["trang_thai"] = r.get("custom_misa_status")
                    x["no_locked"] = r.get("custom_misa_no_locked")
                    out.append(x)
            return out
        if "IFNULL(si.is_return, 0) = 0" in q:
            return [r for r in bang.values()
                    if not r.get("is_return")
                    and r.get("custom_misa_ref_id") == p.get("ref")
                    and r.get("docstatus", 1) < 2]
        raise AssertionError(f"truy vấn chưa lường tới: {q[:90]}")

    frappe.db.sql = _sql

    def _set_value(dt, name, values, field=None, val=None, update_modified=True):
        nhat_ky["ghi"].append({"dt": dt, "name": name, "values": dict(values),
                               "update_modified": update_modified})
        nhat_ky["thu_tu"].append(("ghi", name))
        for k, v in values.items():
            bang[name][k] = v

    frappe.db.set_value = _set_value

    class _Doc(_D):
        def insert(self, **kw):
            nhat_ky["insert"].append(dict(self))
            nhat_ky["thu_tu"].append(("comment", self.get("reference_name")))
            return self

    def _get_doc(d, *a, **k):
        nhat_ky["get_doc"].append(d.get("doctype") if isinstance(d, dict) else str(d))
        return _Doc(**d) if isinstance(d, dict) else _Doc()

    frappe.get_doc = _get_doc

    def _get_all(dt, filters=None, fields=None, limit=None, **k):
        if dt != "Comment":
            return []
        kw = (filters or {}).get("content", ("like", ""))[1].strip("%")
        return [_D(name=f"CMT-{i}", reference_name=c["reference_name"],
                   content=c["content"])
                for i, c in enumerate(nhat_ky["insert"]) if kw in c.get("content", "")]

    frappe.get_all = _get_all


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    cl = importlib.import_module("ketoan.api.misa_return_cleanup")
    # Guard được import BÊN TRONG từng hàm (`from ... import guard_manager`),
    # nên phải vá ở chính module `_guard`, không phải ở `cl`.
    importlib.import_module("ketoan.api._guard").guard_manager = lambda *a, **k: None

    print("=" * 78)
    print("misa_return_cleanup_check — dọn số đi vay trên hóa đơn trả hàng")
    print("=" * 78)

    # ── 1. Kế hoạch: chỉ gồm cái chứng minh được là bản chép ───────────
    print("-" * 78)
    print("── 1. Kế hoạch chỉ nhận chứng từ CHỨNG MINH ĐƯỢC là bản chép ───────")
    bang = lam_bang()
    nk = {"ghi": [], "insert": [], "get_doc": [], "thu_tu": []}
    gan_bo_gia(frappe, bang, nk)

    kh = cl.xem_truoc()
    dinh = [v["si"] for v in kh["viec"]]
    ly_do = {c["si"]: c.get("ly_do", "") for c in kh["can_tay"]}

    check("đúng MỘT chứng từ vào kế hoạch dọn", dinh == ["HD-201"], str(dinh))
    check("HD-202 (số KHÁC bản gốc, nghi sửa tay) KHÔNG bị dọn",
          "HD-202" not in dinh and "sửa tay" in ly_do.get("HD-202", ""),
          ly_do.get("HD-202", "KHÔNG có trong can_tay")[:60])
    check("HD-203 (RefID riêng) KHÔNG bị dọn",
          "HD-203" not in dinh and "không dùng chung" in ly_do.get("HD-203", ""),
          ly_do.get("HD-203", "")[:60])
    check("HD-204 (RefID chung với 2 hóa đơn bán) KHÔNG bị dọn",
          "HD-204" not in dinh and "cấu trúc lạ" in ly_do.get("HD-204", ""),
          ly_do.get("HD-204", "")[:60])
    check("HD-205 (đã sạch) không sinh việc và cũng không báo cần tay",
          "HD-205" not in dinh and "HD-205" not in ly_do)
    check("XEM TRƯỚC KHÔNG GHI GÌ — không một phép set_value, không một insert",
          not nk["ghi"] and not nk["insert"],
          f"{len(nk['ghi'])} ghi, {len(nk['insert'])} insert")

    cu = kh["viec"][0]["cu"] if kh["viec"] else {}
    check("chỉ liệt field ĐANG CÓ giá trị giống bản gốc, không liệt field rỗng",
          set(cu) == {"custom_misa_inv_series", "custom_misa_inv_no",
                      "custom_misa_pushed_at", "vn_einvoice_number",
                      "custom_misa_note"},
          str(sorted(cu)))

    # ── 2. Vân tay sai ⇒ KHÔNG ghi gì ─────────────────────────────────
    print("-" * 78)
    print("── 2. Vân tay không khớp ⇒ DỪNG, không ghi một chữ ─────────────────")
    try:
        cl.don(van_tay="vantay-bua-bai")
        check("vân tay sai thì NỔ, không dọn", False, "chạy qua không lỗi")
    except Exception as e:  # noqa: BLE001
        check("vân tay sai thì NỔ, không dọn", "KHÔNG khớp" in str(e), str(e)[:60])
    check("và không hề ghi gì sau lần thử đó",
          not nk["ghi"] and not nk["insert"],
          f"{len(nk['ghi'])} ghi")
    try:
        cl.don(van_tay="")
        check("thiếu vân tay thì NỔ", False, "chạy qua không lỗi")
    except Exception as e:  # noqa: BLE001
        check("thiếu vân tay thì NỔ", "Thiếu vân tay" in str(e), str(e)[:50])

    # Vân tay phải ĐỔI khi `bo_qua` đổi — bỏ qua ai cũng là phần của kế hoạch.
    vt_bo = cl.xem_truoc(bo_qua=["HD-201"])["van_tay"]
    check("đổi danh sách bỏ qua là đổi vân tay",
          vt_bo != kh["van_tay"], f"{vt_bo[:10]} vs {kh['van_tay'][:10]}")

    # Vân tay phải phủ cả GIÁ TRỊ sẽ xoá, không chỉ tên chứng từ: dọn theo một
    # kế hoạch mà số liệu đã đổi là dọn cái chưa ai đọc.
    luu = bang["HD-201"]["custom_misa_inv_no"]
    bang["HD-201"]["custom_misa_inv_no"] = "00008041"
    bang["HD-101"]["custom_misa_inv_no"] = "00008041"
    vt_doi = cl.xem_truoc()["van_tay"]
    bang["HD-201"]["custom_misa_inv_no"] = luu
    bang["HD-101"]["custom_misa_inv_no"] = luu
    check("đổi GIÁ TRỊ sắp xoá cũng đổi vân tay (không chỉ băm tên chứng từ)",
          vt_doi != kh["van_tay"], f"{vt_doi[:10]} vs {kh['van_tay'][:10]}")
    check("và vân tay trở lại như cũ khi dữ liệu trở lại như cũ",
          cl.xem_truoc()["van_tay"] == kh["van_tay"])

    # ── 3. Dọn thật: xoá ĐÚNG field đã bày, cấp RefID mới ─────────────
    print("-" * 78)
    print("── 3. Dọn thật: xoá đúng field đã bày ra, RefID mới, cờ về 0 ───────")
    kq = cl.don(van_tay=kh["van_tay"])
    check("báo dọn 1 chứng từ, không lỗi", kq["da_don"] == 1 and not kq["loi"], str(kq))

    d = bang["HD-201"]
    check("số hóa đơn đi vay đã sạch", d["custom_misa_inv_no"] is None,
          repr(d["custom_misa_inv_no"]))
    check("ký hiệu, cờ đã-đẩy, ô số cũ đều sạch",
          d["custom_misa_inv_series"] is None and d["custom_misa_pushed_at"] is None
          and d["vn_einvoice_number"] is None)
    check("RefID được cấp MỚI, không còn trùng bản gốc",
          d["custom_misa_ref_id"] and d["custom_misa_ref_id"] != "ref-A",
          str(d["custom_misa_ref_id"])[:18])
    check("trạng thái về 'Chưa đẩy'", d["custom_misa_status"] == "Chưa đẩy",
          str(d["custom_misa_status"]))
    check("cờ khóa = 0, KHÔNG phải None (vòng 2 poll_pending lọc `= 0`)",
          d["custom_misa_no_locked"] == 0, repr(d["custom_misa_no_locked"]))
    check("BẢN GỐC không bị đụng tới một chữ",
          bang["HD-101"]["custom_misa_inv_no"] == "00008040"
          and bang["HD-101"]["custom_misa_ref_id"] == "ref-A")
    check("HD-202 vẫn nguyên — không dọn nửa vời",
          bang["HD-202"]["custom_misa_inv_no"] == "00009999")
    check("mọi phép ghi đều update_modified=False (chứng từ đã ghi sổ)",
          all(g["update_modified"] is False for g in nk["ghi"]),
          str([g["update_modified"] for g in nk["ghi"]]))

    # ── 4. Lưu giá trị cũ TRƯỚC khi ghi đè ────────────────────────────
    print("-" * 78)
    print("── 4. Comment ghi giá trị cũ, và ghi TRƯỚC khi ghi đè ──────────────")
    check("có đúng 1 Comment được tạo", len(nk["insert"]) == 1, str(len(nk["insert"])))
    cmt = json.loads(nk["insert"][0]["content"]) if nk["insert"] else {}
    check("Comment gắn vào đúng chứng từ",
          nk["insert"] and nk["insert"][0]["reference_name"] == "HD-201")
    check("Comment giữ NGUYÊN số hóa đơn cũ để lùi được",
          cmt.get("cu", {}).get("custom_misa_inv_no") == "00008040",
          str(cmt.get("cu", {}).get("custom_misa_inv_no")))
    check("Comment giữ RefID cũ và vân tay của lượt dọn",
          cmt.get("ref_id_cu") == "ref-A" and cmt.get("van_tay") == kh["van_tay"])
    # TRƯỚC, không phải sau: mất điện giữa lô mà giá trị cũ chưa kịp lưu thì
    # chứng từ đã bị xoá số và không còn gì để lùi.
    tt = [x for x in nk["thu_tu"] if x[1] == "HD-201"]
    check("Comment được ghi TRƯỚC phép ghi đè, không phải sau",
          tt[:2] == [("comment", "HD-201"), ("ghi", "HD-201")], str(tt))

    # ── 5. Lùi được, về đúng giá trị cũ ───────────────────────────────
    print("-" * 78)
    print("── 5. hoan_tac: trả về đúng giá trị trước khi dọn ──────────────────")
    ht = cl.hoan_tac(van_tay=kh["van_tay"])
    d = bang["HD-201"]
    check("báo đã trả lại 1 chứng từ", ht["da_tra_lai"] == 1, str(ht))
    check("số hóa đơn về đúng giá trị cũ", d["custom_misa_inv_no"] == "00008040",
          str(d["custom_misa_inv_no"]))
    check("RefID về đúng ref cũ", d["custom_misa_ref_id"] == "ref-A",
          str(d["custom_misa_ref_id"]))
    check("trạng thái về đúng trạng thái cũ",
          d["custom_misa_status"] == "Đã phát hành", str(d["custom_misa_status"]))
    ht2 = cl.hoan_tac(van_tay="vantay-khong-ton-tai")
    check("lùi theo vân tay lạ thì không trả lại gì", ht2["da_tra_lai"] == 0, str(ht2))

    # Comment của NGUỒN KHÁC tình cờ chứa cùng chuỗi vân tay: bộ lọc `content
    # LIKE %...%` sẽ vớt nó lên, nên phải có chốt `moc` ở tầng mã.
    nk["insert"].append({
        "reference_name": "HD-101",
        "content": json.dumps({"moc": "app.khac", "van_tay": kh["van_tay"],
                               "ref_id_cu": "ref-GIA",
                               "cu": {"custom_misa_inv_no": "99999999"}},
                              ensure_ascii=False)})
    ht3 = cl.hoan_tac(van_tay=kh["van_tay"])
    check("Comment của nguồn khác (sai `moc`) KHÔNG được đem ra lùi",
          bang["HD-101"]["custom_misa_inv_no"] == "00008040"
          and bang["HD-101"]["custom_misa_ref_id"] == "ref-A",
          f"{bang['HD-101']['custom_misa_inv_no']} / {bang['HD-101']['custom_misa_ref_id']}")
    check("và lượt lùi đó chỉ nhận đúng chứng từ của mình",
          ht3["da_tra_lai"] == 1, str(ht3["da_tra_lai"]))

    # ── 6. KHÔNG BAO GIỜ hủy / save / submit Sales Invoice ────────────
    print("-" * 78)
    print("── 6. Không một đường nào hủy / save / submit Sales Invoice ────────")
    check("get_doc chỉ từng được gọi cho Comment, không cho Sales Invoice",
          set(nk["get_doc"]) <= {"Comment"}, str(set(nk["get_doc"])))
    src = open(os.path.join(rc.REPO, "ketoan/api/misa_return_cleanup.py"),
               encoding="utf-8").read()
    ma = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    ma = re.sub(r'""".*?"""', "", ma, flags=re.S)
    for xau in (".cancel(", ".submit(", ".save(", "delete_doc", "db_set("):
        check(f"mã nguồn không có `{xau}`", xau not in ma)
    check("mọi set_value đều khai update_modified=False trong mã",
          ma.count("set_value(") == ma.count("update_modified=False"),
          f"{ma.count('set_value(')} set_value / "
          f"{ma.count('update_modified=False')} update_modified")

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — dọn đúng cái chứng minh được là bản chép, vân tay "
              "sai thì không ghi gì, và lùi được về nguyên trạng.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
