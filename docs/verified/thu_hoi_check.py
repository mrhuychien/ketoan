#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""thu_hoi_check — THU HỒI HÀNG bên kế toán: hóa đơn trả về đúng ĐVT, trạng thái không nói dối.

════════════════════════════════════════════════════════════════════════════
NHỮNG CÁI LỖ BỘ KIỂM NÀY CANH
════════════════════════════════════════════════════════════════════════════

1. **Dòng trả sai đơn vị / làm tròn.** ERPNext v16 so `qty` THEO ĐVT CỦA DÒNG khi
   hóa đơn trả về `update_stock = 0`. Dòng gốc "10 Thùng" mà dòng trả nối vào ghi
   "70 Hộp" là so 70 với 10. Và làm tròn 70/30 = 2,333 thùng là lệch tiền với số
   siêu thị trừ. `phan_bo` phải: chẵn thùng → dòng nối; lẻ đúng y → dòng nối số lẻ;
   còn lại → dòng KHÔNG nối ĐVT kho. Tổng luôn ĐÚNG y số cần trả.
2. **Trần trả bỏ sót.** Phải trừ mọi lần trả trước của hóa đơn gốc — cả dòng không
   nối, cả bản NHÁP (ERPNext chỉ đếm bản đã ghi sổ).
3. **Trạng thái nói dối.** "Xong" khi phiếu trả THỪA so với số kiểm là ghi giảm công
   nợ nhiều hơn hàng thật về; chưa chốt mà có phiếu trả cũng không phải "đã kiểm".
4. **Sửa số sau khi chốt** (cả Desk) — phiếu trả dựng trên số đã chốt.
5. **Tin hệ số quy đổi client gửi** — "2 thùng" với hệ số 999 không được thành 1998 hộp.
6. **Ghi vào bảng của vanchuyen** — ketoan chỉ đọc `Lo Thu Hoi`.
7. **Hook chặn ghi sổ** — `dong_bo_trang_thai` phải nuốt lỗi và không `save()`.
8. **Lập hóa đơn trả về bỏ qua quyền người bấm** — `si.insert()` không ignore_permissions.
9. **Màn kiểm hàng hiện số khai** — đếm MÙ, so sau khi chốt.
10. **Mọi whitelisted method có guard ở dòng đầu**, import map đủ module dùng chung.
11. **Lô bên vận chuyển đã HỦY vẫn bị đếm "đang mở" / vẫn mở được phiếu kiểm** — và nút
    "Bắt đầu kiểm" chạy đua với nút "Hủy yêu cầu" (phải đọc lô bằng KHÓA).
12. **Lô HỦY TẠI CHỖ lạc chặng / bị bắt đếm mù**: chưa có phiếu phải đứng ở "Đã kiểm hàng"
    (nhận đủ theo phiếu), phiếu `theo_phieu` đang chép không lùi về "Đang kiểm" (cờ bật cả
    khi phiếu tạo tay trên Desk), và màn nhập phải THẤY mail / biên bản để chép (lô thường
    thì vẫn đếm mù).
13. **Ảnh phiếu trả về thành cửa sau**: chỉ nhận ẢNH THẬT (chữ ký đầu file, không tin đuôi —
    proxy mở inline theo đuôi), gắn PHIẾU KIỂM (không gắn lô bên vanchuyen), private, chốt rồi
    thì khóa; không xóa được file của phiếu khác / của lô. "Chờ nhập số" = phiếu chưa chốt có ảnh.
14. **Hóa đơn trả về không theo hóa đơn gốc sai giá / sai thứ tự chia**: đơn giá = lần bán gần
    nhất cho ĐÚNG khách (ưu tiên đúng điểm giao) theo ĐVT kho; không `return_against`; cập nhật
    thì bản NỐI hóa đơn gốc chia trước, bản tự do nhận phần còn lại và GIỮ giá người soát sửa.

Chạy KHÔNG cần bench — stub frappe của `docs/mt/verified/regression_check`:
    python3 docs/verified/thu_hoi_check.py   # exit 0 = đạt
"""

import ast
import importlib
import json
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "docs", "mt", "verified"))
import regression_check as rc  # noqa: E402

API = os.path.join(REPO, "ketoan", "api")
PUB = os.path.join(REPO, "ketoan", "public", "ketoan")

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


def raises(fn):
    try:
        fn()
        return None
    except Exception as e:  # noqa: BLE001
        return str(e) or type(e).__name__


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# 1–3. HÀM THUẦN
# ════════════════════════════════════════════════════════════════════════════
def kiem_ham_thuan(pb):
    print("-" * 78)
    print("── 1. phan_bo: giữ ĐVT dòng gốc, không bao giờ làm tròn ─────────────────")

    THUNG = {"name": "R1", "item_code": "BDX", "qty": 10, "conversion_factor": 24, "uom": "Thùng"}
    HOP = {"name": "R2", "item_code": "BDX", "qty": 30, "conversion_factor": 1, "uom": "Hộp"}

    def tong(plan):
        return sum(x["stock_qty"] for x in plan)

    plan, thieu = pb.phan_bo({"BDX": 70}, [THUNG], {}, {}, 3, ())
    noi = [x for x in plan if x["noi"]]
    roi = [x for x in plan if not x["noi"]]
    check("70 hộp vào dòng '10 Thùng' (24/thùng): 2 thùng NỐI + 22 hộp KHÔNG NỐI",
          len(noi) == 1 and noi[0]["qty"] == 2 and len(roi) == 1 and roi[0]["stock_qty"] == 22, json.dumps(plan))
    check("tổng ĐÚNG y 70, không thiếu, không làm tròn", tong(plan) == 70 and not thieu)
    check("dòng nối mang qty theo ĐVT dòng gốc (2 thùng), stock_qty = qty × hệ số",
          all(x["stock_qty"] == x["qty"] * 24 for x in noi))

    plan, _ = pb.phan_bo({"BDX": 6}, [THUNG], {}, {}, 3, ())
    check("6 hộp = 0,25 thùng ghi ĐÚNG y -> một dòng NỐI số lẻ",
          len(plan) == 1 and plan[0]["noi"] and plan[0]["qty"] == 0.25, json.dumps(plan))
    plan, _ = pb.phan_bo({"BDX": 6}, [THUNG], {}, {}, 3, ("Thùng",))
    check("ĐVT Thùng bắt buộc số nguyên -> 6 hộp đi dòng KHÔNG NỐI",
          len(plan) == 1 and not plan[0]["noi"] and plan[0]["stock_qty"] == 6, json.dumps(plan))
    plan, _ = pb.phan_bo({"BDX": 7}, [dict(THUNG, conversion_factor=30, qty=10)], {}, {}, 3, ())
    check("7/30 thùng = 0,2333… KHÔNG làm tròn -> dòng không nối 7 hộp",
          len(plan) == 1 and not plan[0]["noi"] and plan[0]["stock_qty"] == 7, json.dumps(plan))

    plan, _ = pb.phan_bo({"BDX": 70}, [dict(HOP, qty=100)], {}, {}, 3, ())
    check("dòng gốc theo ĐVT kho (hộp) -> 70 hộp NỐI trọn",
          len(plan) == 1 and plan[0]["noi"] and plan[0]["qty"] == 70)
    plan, _ = pb.phan_bo({"BDX": 60}, [dict(THUNG, qty=2), HOP], {}, {}, 3, ())
    check("hai dòng gốc thùng + hộp: 2 thùng (48) + 12 hộp, đều NỐI",
          all(x["noi"] for x in plan) and tong(plan) == 60 and {x["src"] for x in plan} == {"R1", "R2"},
          json.dumps(plan))

    print("-" * 78)
    print("── 2. Trần trả: trừ mọi lần trả trước — dòng không nối, bản nháp ───────")
    plan, thieu = pb.phan_bo({"BDX": 30}, [THUNG], {}, {"BDX": 230}, 3, ())
    check("đã trả 230/240 hộp (mọi phiếu, kể cả không nối) -> chỉ nhận 10, thiếu 20",
          tong(plan) == 10 and abs(thieu.get("BDX", 0) - 20) < 1e-9, f"{tong(plan)} / {thieu}")
    plan, thieu = pb.phan_bo({"BDX": 48}, [THUNG], {"R1": 9}, {"BDX": 216}, 3, ())
    check("dòng gốc đã trả 9/10 thùng -> chỉ 1 thùng NỐI được",
          sum(x.get("qty", 0) for x in plan if x["noi"]) == 1 and tong(plan) == 24 and thieu.get("BDX") == 24,
          json.dumps(plan))
    # Ca trần DÒNG là chốt chặn thật (trần mặt hàng còn dư): dòng thùng đã trả 9/10 thùng,
    # dòng hộp chưa trả gì. Bỏ trần dòng thì máy dồn 2 thùng vào dòng chỉ còn 1 — ERPNext
    # ném "Cannot return more than 1" đúng lúc ghi sổ.
    plan, thieu = pb.phan_bo({"BDX": 48}, [THUNG, HOP], {"R1": 9}, {"BDX": 216}, 3, ())
    theo = {x["src"]: x for x in plan}
    check("dòng thùng còn 1 thùng -> 1 thùng NỐI + 24 hộp sang dòng hộp, không vượt trần dòng",
          theo.get("R1", {}).get("qty") == 1 and theo.get("R2", {}).get("qty") == 24 and not thieu,
          json.dumps(plan))
    plan, thieu = pb.phan_bo({"KHAC": 5}, [THUNG], {}, {}, 3, ())
    check("mã không có trên hóa đơn gốc -> không dòng nào, thiếu trọn", not plan and thieu == {"KHAC": 5})

    src = read(os.path.join(API, "thu_hoi.py"))
    body = rc.code_only(os.path.join(API, "thu_hoi.py")) if hasattr(rc, "code_only") else src
    m = re.search(r"def _ke_hoach_nhieu\(.*?\n(?=def )", src, re.S)
    kh = m.group(0) if m else ""
    check("_ke_hoach_nhieu đếm phiếu trả docstatus < 2 (CẢ bản nháp)", "r.docstatus < 2" in kh)
    check("_ke_hoach_nhieu đếm cả dòng KHÔNG NỐI vào trần mặt hàng",
          "da_ma[t.item_code]" in kh and "if t.sales_invoice_item:" in kh)
    del body

    print("-" * 78)
    print("── 3. suy_trang_thai: không báo Xong khi phiếu trả lệch số kiểm ────────")
    can = {"A": 10, "B": 5}
    hd_nhap = [{"name": "R-1", "docstatus": 0, "items": {"A": 10, "B": 5}}]
    hd_so = [{"name": "R-1", "docstatus": 1, "items": {"A": 10, "B": 5}}]
    S = pb.suy_trang_thai
    check("chưa chốt -> Đang kiểm (kể cả đã có phiếu trả)", S(0, 0, can, hd_so)[0] == pb.DANG_KIEM)
    check("chốt, chưa phiếu trả -> Đã kiểm hàng", S(1, 0, can, [])[0] == pb.DA_KIEM)
    check("chốt, phiếu trả nháp phủ đúng -> Đã nhập chứng từ", S(1, 0, can, hd_nhap)[0] == pb.DA_NHAP)
    check("chốt, phủ đúng, đã ghi sổ hết -> Xong", S(1, 0, can, hd_so)[0] == pb.XONG)
    tt, lech = S(1, 0, can, [{"name": "R", "docstatus": 1, "items": {"A": 10, "B": 3}}])
    check("phiếu trả THIẾU -> Đã kiểm hàng + lệch âm", tt == pb.DA_KIEM and lech == {"B": -2}, str(lech))
    tt, lech = S(1, 0, can, [{"name": "R", "docstatus": 1, "items": {"A": 12, "B": 5}}])
    check("phiếu trả THỪA (ghi giảm nhiều hơn hàng về) -> KHÔNG Xong", tt == pb.DA_KIEM and lech == {"A": 2}, str(lech))
    tt, lech = S(1, 0, can, [{"name": "R", "docstatus": 1, "items": {"A": 10, "B": 5, "C": 1}}])
    check("phiếu trả có mã KHÔNG kiểm -> KHÔNG Xong", tt == pb.DA_KIEM and "C" in lech)
    check("KTT kết luận không lập -> Xong", S(1, 1, can, [])[0] == pb.XONG)
    check("con_can: phần đã kiểm chưa có phiếu trả",
          pb.con_can(can, [{"items": {"A": 4}}]) == {"A": 6, "B": 5})
    check("gộp chi tiết khi quét thêm cùng mã: 2 thùng + 1 thùng 3 hộp = 3 thùng 3 hộp",
          pb.mo_ta_chi_tiet(pb.gop_chi_tiet([{"uom": "Thùng", "sl": 2, "he_so": 24}],
                                            [{"uom": "Thùng", "sl": 1, "he_so": 24}, {"uom": "Hộp", "sl": 3, "he_so": 1}]))
          == "3 Thùng + 3 Hộp")


# ════════════════════════════════════════════════════════════════════════════
# 4–5, 7. CONTROLLER + API trên bộ giả frappe
# ════════════════════════════════════════════════════════════════════════════
class FakeRow(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v

    def as_dict(self):
        return dict(self)


def kiem_tren_bo_gia():
    fr = rc._stub_frappe()
    u = sys.modules["frappe.utils"]
    u.date_diff = lambda a, b: 0
    u.get_fullname = lambda user=None: "Người kiểm"
    fr.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
    # Guard THẬT chạy trên phiên giả: kế toán MT (không phải KTT) — đúng người dùng màn này.
    fr.get_roles = lambda *a, **k: ["Ke Toan MT"]

    ITEMS = {"BDX": {"item_name": "Bánh đậu xanh 170g", "stock_uom": "Hộp"}}
    UOMS = [{"parent": "BDX", "uom": "Thùng", "conversion_factor": 24}, {"parent": "BDX", "uom": "Hộp", "conversion_factor": 1}]
    WROTE = []

    class Doc:
        doctype = "Kiem Hang Thu Hoi"

        def __init__(self, **kw):
            self.__dict__.update(kw)

        def get(self, k, default=None):
            return self.__dict__.get(k, default)

        def get_doc_before_save(self):
            return self.__dict__.get("_before")

        def append(self, f, d):
            r = FakeRow(d)
            r.setdefault("name", "row-%d" % (len(self.items) + 1))
            self.items.append(r)
            return r

        def set(self, f, v):
            setattr(self, f, v)

        def save(self):
            self.validate()

        class meta:  # noqa: N801
            @staticmethod
            def get_label(f):
                return f

    sys.modules["frappe.model.document"].Document = Doc

    FILES = {}

    class DB(type(fr.db)):
        def get_value(self, dt, name=None, fields=None, **k):
            if dt == "Item":
                it = ITEMS.get(name)
                return fr._dict(it) if it else None
            if dt == "File":
                f = FILES.get(name)
                return fr._dict(f) if f else None
            return None

        def has_column(self, *a, **k):
            return True

        def sql(self, *a, **k):
            return []

        def set_value(self, *a, **k):
            WROTE.append((a, k))

        def exists(self, dt, *a, **k):
            return dt in ("Item", "Kiem Hang Thu Hoi")

    fr.db = DB()

    def get_all(dt, filters=None, fields=None, **k):
        if dt == "Item":
            return [fr._dict(name=n, item_name=v["item_name"], stock_uom=v["stock_uom"]) for n, v in ITEMS.items()]
        if dt == "UOM Conversion Detail":
            return [fr._dict(r) for r in UOMS]
        return []

    fr.get_all = get_all
    sys.path.insert(0, REPO)
    ctl = importlib.import_module("ketoan.ketoan.doctype.kiem_hang_thu_hoi.kiem_hang_thu_hoi")
    api = importlib.import_module("ketoan.api.thu_hoi")
    pb = importlib.import_module("ketoan.api.thu_hoi_phan_bo")

    print("-" * 78)
    print("── 4. Chốt rồi thì khóa số; một mã một dòng ─────────────────────────────")

    def phieu(**kw):
        base = dict(name="TH-1", lo_thu_hoi="TH-1", company="C", customer="COOP", shipping_address_name="A",
                    da_chot=0, khong_lap_hd=0, items=[FakeRow(name="r1", item_code="BDX", qty=10, idx=1)],
                    xong_luc=None, modified="2026-10-17 10:00:00")
        base.update(kw)
        return ctl.KiemHangThuHoi(**base)

    before = phieu(da_chot=1)
    d = phieu(da_chot=1, _before=before, items=[FakeRow(name="r1", item_code="BDX", qty=12, idx=1)])
    check("đã chốt mà đổi số -> chặn", raises(d.validate) is not None)
    d = phieu(da_chot=1, _before=before)
    check("đã chốt, không đổi số (ghi chú) -> qua", raises(d.validate) is None)
    d = phieu(da_chot=0, _before=before, items=[FakeRow(name="r1", item_code="BDX", qty=12, idx=1)])
    check("mở lại (da_chot 1 -> 0) rồi sửa -> qua", raises(d.validate) is None)
    d = phieu(_before=phieu(), customer="BIGC")
    check("đổi khách sau khi mở phiếu -> chặn", raises(d.validate) is not None)
    d = phieu(items=[FakeRow(name="r1", item_code="BDX", qty=1, idx=1), FakeRow(name="r2", item_code="BDX", qty=2, idx=2)])
    check("hai dòng cùng mã -> chặn", raises(d.validate) is not None)
    d = phieu(da_chot=1, items=[])
    check("chốt phiếu rỗng (không phải KTT kết luận) -> chặn", raises(d.validate) is not None)
    d = phieu(da_chot=1, items=[], khong_lap_hd=1)
    check("KTT kết luận không lập, phiếu rỗng -> qua, trạng thái Xong",
          raises(d.validate) is None and d.trang_thai == pb.XONG)

    print("-" * 78)
    print("── 5. them_dong: CỘNG vào dòng cũ, hệ số do SERVER tra ────────────────")
    P = {"doc": phieu(items=[])}
    fr.get_doc = lambda dt, name=None, for_update=False, **k: P["doc"]
    r = api.them_dong("TH-1", "BDX", 0, json.dumps([{"uom": "Thùng", "sl": 2, "he_so": 999}]), "8936")
    check("2 thùng với he_so client 999 -> lưu 48 hộp (server tra 24)",
          P["doc"].items[0].qty == 48 and json.loads(P["doc"].items[0].chi_tiet)[0]["he_so"] == 24,
          str(P["doc"].items[0].qty))
    api.them_dong("TH-1", "BDX", 0, json.dumps([{"uom": "Hộp", "sl": 3}]), None)
    check("quét thêm cùng mã 3 hộp -> CỘNG vào dòng cũ: 51, '2 Thùng + 3 Hộp'",
          len(P["doc"].items) == 1 and P["doc"].items[0].qty == 51 and P["doc"].items[0].mo_ta_dvt == "2 Thùng + 3 Hộp",
          f"{P['doc'].items[0].qty} · {P['doc'].items[0].mo_ta_dvt}")
    check("phiếu trả về tổng mới cho màn hình", r and r["tong_sl"] == 48)
    check("ĐVT chưa khai quy đổi -> chặn",
          raises(lambda: api.them_dong("TH-1", "BDX", 0, json.dumps([{"uom": "Lốc", "sl": 1}]))) is not None)
    P["doc"].da_chot = 1
    check("phiếu đã chốt -> them_dong chặn", raises(lambda: api.them_dong("TH-1", "BDX", 5)) is not None)
    P["doc"].da_chot = 0
    check("sua_dong về 0 -> chặn (xóa là bấm ✕)",
          raises(lambda: api.sua_dong("TH-1", P["doc"].items[0].name, 0)) is not None)

    print("-" * 78)
    print("── 6. Dòng phiếu trả dựng từ make_return_doc ───────────────────────────")
    mapped = {"R1": FakeRow(item_code="BDX", qty=-10, uom="Thùng", stock_uom="Hộp", conversion_factor=24,
                            rate=240000, price_list_rate=250000, base_rate=240000, sales_invoice_item="R1",
                            batch_no="LO-1", income_account="511 - DT", name="x", idx=1)}
    plan = [{"src": "R1", "item_code": "BDX", "noi": True, "qty": 2, "stock_qty": 48},
            {"src": "R1", "item_code": "BDX", "noi": False, "stock_qty": 22}]
    rows = api._dong_tra(mapped, plan, "5213 - Hàng bán bị trả lại")
    a, b = rows
    check("dòng nối: giữ ĐVT Thùng, qty -2, nối dòng gốc",
          a["uom"] == "Thùng" and a["qty"] == -2 and a["sales_invoice_item"] == "R1")
    check("dòng không nối: ĐVT kho, hệ số 1, -22, đơn giá ÷ 24, BỎ nối",
          b["uom"] == "Hộp" and b["conversion_factor"] == 1 and b["qty"] == -22 and b["rate"] == 10000
          and b["sales_invoice_item"] is None, json.dumps(b, ensure_ascii=False, default=str)[:200])
    check("tiền đúng y: 2×240.000 + 22×10.000 = 700.000",
          -a["qty"] * a["rate"] + -b["qty"] * b["rate"] == 700000)
    check("TK 5213 + bỏ tham chiếu lô (update_stock = 0)",
          a["income_account"].startswith("5213") and a["batch_no"] is None and b["batch_no"] is None)
    check("không chép name/idx của dòng map sang dòng mới", "name" not in a and "idx" not in a)

    print("-" * 78)
    print("── 7. Hook Sales Invoice không bao giờ chặn ghi sổ ──────────────────────")
    WROTE.clear()

    def no(*a, **k):
        raise RuntimeError("DB hỏng")

    fr.get_doc = no
    si = FakeRow(custom_kiem_hang_thu_hoi="TH-1", is_return=1, name="RET-1")
    check("lỗi bên trong hook bị nuốt (không ném ra giao dịch ghi sổ)",
          raises(lambda: api.dong_bo_trang_thai(si, "on_submit")) is None)
    fr.get_doc = lambda *a, **k: phieu(da_chot=1)
    api.dong_bo_trang_thai(si, "on_submit")
    check("hook ghi bằng db.set_value(update_modified=False)",
          WROTE and WROTE[-1][1].get("update_modified") is False)
    WROTE.clear()
    api.dong_bo_trang_thai(FakeRow(custom_kiem_hang_thu_hoi=None, is_return=1, name="X"), "on_update")
    check("hóa đơn không gắn phiếu kiểm -> hook không làm gì", not WROTE)

    print("-" * 78)
    print("── 7b. File đính kèm của lô qua proxy: chỉ ảnh / PDF mở trong tab ───────")
    fr.local.response = fr._dict()
    fr.get_doc = lambda *a, **k: fr._dict(get_content=lambda: b"noi-dung")

    def kieu(ten, dt="Lo Thu Hoi"):
        FILES["F1"] = {"attached_to_doctype": dt, "file_name": ten}
        fr.local.response.clear()
        api.xem_dinh_kem("F1")
        return fr.local.response.get("display_content_as")

    check("PDF / ảnh: inline (mở trong tab)", kieu("phieu.pdf") == "inline" and kieu("anh.PNG") == "inline")
    check("Excel / Word / mail: attachment (tải về)",
          kieu("ds.xlsx") == "attachment" and kieu("bb.docx") == "attachment" and kieu("mail.eml") == "attachment")
    check("file .html / .svg gắn vào lô: KHÔNG BAO GIỜ inline (script chạy trên tên miền site)",
          kieu("x.html") == "attachment" and kieu("logo.svg") == "attachment")
    check("file gắn vào DocType khác -> từ chối", raises(lambda: kieu("p.pdf", dt="Sales Invoice")) is not None)

    print("-" * 78)
    print("── 7c. Ứng viên hóa đơn gốc: ĐÚNG khách + điểm giao, liệt kê HẾT ────────")
    SQL = []
    TONG = {"n": 2}

    def sql(q, p=None, as_dict=False, **k):
        SQL.append((q, dict(p or {})))
        if "custom_kiem_hang_thu_hoi" in q:          # hoa_don_tra: lô chưa có phiếu trả nào
            return []
        if "COUNT(*)" in q:
            return [[TONG["n"]]]
        if "LEFT JOIN `tabAddress` a" in q:            # trang ứng viên
            chung = dict(customer="COOP", customer_name="Saigon Co.op", shipping_address_name="ADDR-HD",
                         ten_diem="Co.opMart Hà Đông", address_title="CM HĐ", address_line1="1 Quang Trung",
                         city="Hà Nội", cung_diem=1)
            return [fr._dict(chung, name="SI-A", posting_date="2026-09-01", grand_total=4800000,
                             outstanding_amount=0, po="PO-1", so_hddt="0001234"),
                    fr._dict(chung, name="SI-B", posting_date="2026-08-01", grand_total=900000,
                             outstanding_amount=900000, po=None, so_hddt=None)]
        if "SUM(ABS(grand_total))" in q:              # đã trả về trước đó
            return [fr._dict(goc="SI-A", tien=240000)]
        if "FROM `tabSales Invoice Item`" in q and "WHERE parent IN" in q:   # dòng gốc có mã cần trả
            return [fr._dict(parent="SI-A", name="R1", item_code="BDX", qty=10, conversion_factor=24,
                             uom="Thùng", rate=240000, idx=1)]
        return []

    fr.db.sql = sql
    fr.db.table_exists = lambda *a, **k: True
    fr.get_precision = lambda *a, **k: 3
    fr.get_doc = lambda *a, **k: phieu(da_chot=1, customer_name="Saigon Co.op", ten_diem="Co.opMart Hà Đông",
                                       items=[FakeRow(name="r1", item_code="BDX", qty=50, idx=1)])

    def trang():
        return next(q for q, _p in reversed(SQL) if "LEFT JOIN `tabAddress` a" in q)

    r = api.ung_vien_hoa_don("TH-1")
    q = trang()
    check("lọc ĐÚNG khách + ĐÚNG điểm giao của lô (không cần có mã đã kiểm)",
          "si.customer = %(cu)s" in q and "si.shipping_address_name = %(addr)s" in q and "EXISTS" not in q)
    check("liệt kê hết: 50 tờ một trang, mới nhất trước",
          "LIMIT %(lim)s OFFSET %(off)s" in q and "ORDER BY si.posting_date DESC" in q
          and SQL[-1][1].get("lim", 50) == 50 and api.UNG_VIEN_TRANG == 50)
    a, b = (r["rows"] + [{}, {}])[:2]
    check("tờ nhận được mã cần trả: mở nút lập, nhận BDX 50", a.get("lap_duoc") is True and a.get("nhan") == {"BDX": 50},
          str(a.get("nhan")))
    check("tờ KHÔNG có mã cần trả: VẪN liệt kê, khóa nút + nói lý do",
          len(r["rows"]) == 2 and b.get("lap_duoc") is False and "không có mã nào đang cần trả" in b.get("ly_do_khoa", ""),
          str(b.get("ly_do_khoa")))
    check("đủ thông tin: khách, điểm giao, số tiền, còn nợ, đã trả về, số HĐĐT, PO",
          all(a.get(k) not in (None, "") for k in ("customer_name", "ten_diem", "address_line1", "grand_total", "po"))
          and a.get("da_tra") == 240000 and a.get("so_hddt") == "0001234")
    check("đầu bảng: khách + điểm đang lọc", r.get("khach", {}).get("customer_name") == "Saigon Co.op"
          and r.get("diem", {}).get("ten") == "Co.opMart Hà Đông" and r.get("total") == 2 and r.get("has_more") is False)
    api.ung_vien_hoa_don("TH-1", moi_diem=1)
    check("'Xem mọi điểm của khách' (moi_diem=1): bỏ lọc điểm, vẫn lọc khách",
          "si.shipping_address_name = %(addr)s" not in trang() and "si.customer = %(cu)s" in trang())
    api.ung_vien_hoa_don("TH-1", tim="0001")
    check("tìm theo số hóa đơn / PO / số HĐĐT", "si.name LIKE %(q)s" in trang() and "custom_misa_inv_no` LIKE %(q)s" in trang())
    TONG["n"] = 120
    r2 = api.ung_vien_hoa_don("TH-1", page=2)
    p2 = next(pp for qq, pp in reversed(SQL) if "LEFT JOIN `tabAddress` a" in qq)
    check("phân trang: trang 2 bỏ qua 50 tờ đầu, còn nữa thì has_more", p2.get("off") == 50 and r2["has_more"] is True)

    print("-" * 78)
    print("── 7d. Lô bên vận chuyển ĐÃ HỦY: không 'đang mở', không kiểm hàng ─────")
    SQL.clear()
    ROWS = [dict(name="TH-H", chang="Đã hủy", trang_thai="Đã hủy", ngay_yeu_cau="2026-10-01"),
            dict(name="TH-M", chang="Đã nhận hàng", trang_thai="Đã nhận hàng", ngay_yeu_cau="2026-10-01")]
    LO_HUY = dict(name="TH-H", trang_thai="Đã hủy", ly_do_huy="Siêu thị rút yêu cầu", customer="COOP",
                  customer_name="Saigon Co.op", shipping_address_name="ADDR-HD", ten_diem="Co.opMart Hà Đông")

    def sql_huy(q, p=None, as_dict=False, **k):
        SQL.append((q, dict(p or {})))
        if "ORDER BY FIELD" in q:                     # trang danh sách
            return [fr._dict(r) for r in ROWS]
        if "COUNT(*)" in q and "GROUP BY" not in q:
            return [[len(ROWS)]]
        if "FROM `tabLo Thu Hoi` l WHERE l.name" in q:  # _lo
            return [fr._dict(LO_HUY)]
        return []

    fr.db.sql = sql_huy
    fr.db.exists = lambda dt, *a, **k: dt == "Item"   # lô này CHƯA có phiếu kiểm
    r = api.list_thu_hoi()
    q, pr = next((q, pr) for q, pr in reversed(SQL) if "ORDER BY FIELD" in q)
    check("'Đang mở' bỏ cả 'Xong' lẫn 'Đã hủy'", "NOT IN (%(xong)s, %(huy)s)" in q and pr.get("huy") == "Đã hủy")
    thu_tu = [pr[f"c{i}"] for i in range(10) if f"c{i}" in pr]
    check("xếp danh sách: lô 'Đã hủy' nằm CUỐI (có trong FIELD, sau 'Xong')",
          thu_tu[-2:] == ["Xong", "Đã hủy"] and f"%(c{len(thu_tu) - 1})s" in q, str(thu_tu))
    check("lô hủy không tính tuổi (không thành 'lô treo lâu')",
          r["rows"][0]["tuoi"] is None and r["rows"][1]["tuoi"] == 0, str([x["tuoi"] for x in r["rows"]]))
    api.list_thu_hoi(chang="Đã hủy")
    q, pr = next((q, pr) for q, pr in reversed(SQL) if "ORDER BY FIELD" in q)
    check("lọc riêng pill 'Đã hủy' được", "= %(chang)s" in q and pr.get("chang") == "Đã hủy")
    e = raises(lambda: api.bat_dau_kiem("TH-H"))
    check("Bắt đầu kiểm lô đã hủy -> chặn, nói rõ HỦY + lý do (không bảo 'bấm Đã nhận hàng')",
          e is not None and "HỦY" in e and "Siêu thị rút yêu cầu" in e and "bấm 'Đã nhận hàng'" not in e, e)
    lq = [q for q, _p in SQL if "FROM `tabLo Thu Hoi` l WHERE l.name" in q]
    check("Bắt đầu kiểm đọc lô bằng KHÓA (FOR UPDATE) — không chạy đua với nút Hủy bên vận chuyển",
          lq and lq[-1].rstrip().endswith("FOR UPDATE"))
    api._lo("TH-H")
    lq = [q for q, _p in SQL if "FROM `tabLo Thu Hoi` l WHERE l.name" in q]
    check("đọc lô để XEM thì không khóa (màn lô, danh sách không giữ khóa hàng của vanchuyen)",
          not lq[-1].rstrip().endswith("FOR UPDATE"))
    TT = {"v": "Đã hủy"}
    fr.db.sql = lambda q, p=None, **k: [["%s" % TT["v"]]] if "SELECT trang_thai FROM `tabLo Thu Hoi`" in q else []
    e = raises(phieu(lo_thu_hoi="TH-H").before_insert)
    check("controller phiếu kiểm: lô đã HỦY -> không mở phiếu, kể cả tạo tay trên Desk",
          e is not None and "HỦY" in e, e)
    TT["v"] = "Đã nhận hàng"
    check("controller phiếu kiểm: lô đã nhận hàng -> mở bình thường", raises(phieu(lo_thu_hoi="TH-M").before_insert) is None)
    check("chữ 'Đã hủy' khai MỘT chỗ (thu_hoi_phan_bo), api + controller cùng dùng",
          api.DA_HUY is pb.DA_HUY and ctl.DA_HUY is pb.DA_HUY)

    print("-" * 78)
    print("── 7e. Danh mục kiểm hàng: CHỈ Hàng truyền thống + Hàng Tết (cả nhóm con) ─")
    SQL.clear()
    GA = []
    IG = {"rows": []}

    def sql_kiem(q, p=None, as_dict=False, **k):
        SQL.append((q, dict(p or {})))
        if "FROM `tabItem Group` g" in q:
            return [fr._dict(r) for r in IG["rows"]]
        if "FROM `tabLo Thu Hoi` l WHERE l.name" in q:
            return [fr._dict(LO_HUY, trang_thai="Đã nhận hàng")]
        return []

    def get_all_kiem(dt, filters=None, fields=None, **k):
        GA.append((dt, dict(filters or {})))
        if dt == "Item":
            if "name" in (filters or {}):            # _danh_muc(codes): đúng các mã xin
                return [fr._dict(name=n, item_name="Hàng lẻ " + n, stock_uom="Hộp") for n in filters["name"][1]]
            return [fr._dict(name="BDX", item_name="Bánh đậu xanh 170g", stock_uom="Hộp")]
        return []

    fr.db.sql = sql_kiem
    fr.get_all = get_all_kiem
    fr.get_doc = lambda *a, **k: phieu(lo_thu_hoi="TH-M", items=[FakeRow(name="r1", item_code="LE-1", qty=3, idx=1)])
    IG["rows"] = [dict(goc="Hàng truyền thống", name="Hàng truyền thống"),
                  dict(goc="Hàng truyền thống", name="Bánh trung thu"), dict(goc="Hàng Tết", name="Hàng Tết")]
    b = api.boot_kiem("TH-M")
    loc = next((fl for dt, fl in GA if dt == "Item" and "item_group" in fl), {})
    check("danh mục chỉ lấy Item thuộc 2 nhóm + MỌI nhóm con",
          loc.get("item_group") == ["in", ["Bánh trung thu", "Hàng Tết", "Hàng truyền thống"]], str(loc))
    qg, pg = next(((q, pp) for q, pp in SQL if "FROM `tabItem Group` g" in q), ("", {}))
    check("bung nhánh con theo cây lft/rgt; cây hỏng (rgt <= lft) chỉ lấy đúng nhóm gốc",
          "c.lft > g.lft AND c.rgt < g.rgt" in qg and "g.rgt > g.lft" in qg and pg.get("g") == api.NHOM_KIEM)
    check("mã đã kiểm trên phiếu mà NGOÀI nhóm vẫn ở danh mục (sửa / cộng thêm được)",
          {d["item"] for d in b["danh_muc"]} == {"BDX", "LE-1"}, str([d["item"] for d in b["danh_muc"]]))
    check("trả nhóm tìm thấy, không báo thiếu", b["nhom_kiem"] == ["Hàng Tết", "Hàng truyền thống"] and b["thieu_nhom"] == [])
    IG["rows"] = [dict(goc="Hàng truyền thống", name="Hàng truyền thống")]
    b = api.boot_kiem("TH-M")
    check("site thiếu nhóm 'Hàng Tết' -> báo ĐÚNG tên nhóm thiếu", b["thieu_nhom"] == ["Hàng Tết"], str(b["thieu_nhom"]))
    IG["rows"] = []
    GA.clear()
    b = api.boot_kiem("TH-M")
    check("không thấy nhóm nào -> màn KHÔNG trống: tìm trong mọi mã hàng bán + báo thiếu cả hai",
          any(dt == "Item" and "item_group" not in fl and "name" not in fl for dt, fl in GA)
          and b["thieu_nhom"] == list(api.NHOM_KIEM) and len(b["danh_muc"]) >= 1)

    print("-" * 78)
    print("── 7f. HỦY TẠI CHỖ: đi tắt tới 'Đã kiểm hàng' (nhận đủ theo phiếu) ───────")
    tt = pb.suy_trang_thai
    check("phiếu theo phiếu đang chép (chưa chốt) = 'Đã kiểm hàng', KHÔNG lùi về 'Đang kiểm'",
          tt(0, 0, {"BDX": 3}, [], theo_phieu=True)[0] == "Đã kiểm hàng" and tt(0, 0, {"BDX": 3}, [])[0] == "Đang kiểm")
    check("phiếu theo phiếu chốt + hóa đơn nháp phủ đủ -> 'Đã nhập chứng từ' như lô thường",
          tt(1, 0, {"BDX": 3}, [{"name": "R", "docstatus": 0, "items": {"BDX": 3}}], theo_phieu=True)[0] == "Đã nhập chứng từ")
    check("controller truyền cờ theo_phieu vào phép suy",
          "theo_phieu=cint(doc.get(\"theo_phieu\"))" in read(os.path.join(REPO, "ketoan", "ketoan", "doctype",
                                                                      "kiem_hang_thu_hoi", "kiem_hang_thu_hoi.py")))
    check("chặng tổng: lô hủy tại chỗ CHƯA có phiếu = 'Đã kiểm hàng' (SQL + màn chi tiết cùng luật)",
          "l.trang_thai = %(htc)s THEN %(da_kiem)s" in api._expr()
          and api._chang_lo({"trang_thai": "Hủy tại chỗ"}) == "Đã kiểm hàng"
          and api._chang_lo({"trang_thai": "Hủy tại chỗ"}, "Xong") == "Xong"
          and api._chang_lo({"trang_thai": "Đã nhận hàng"}) == "Đã nhận hàng")
    SQL.clear()
    fr.db.sql = sql_huy  # bộ giả của 7d: trang danh sách + COUNT
    api.list_thu_hoi()
    _q, pr = next((q, pp) for q, pp in reversed(SQL) if "ORDER BY FIELD" in q)
    check("danh sách truyền đủ tham số cho luật hủy tại chỗ", pr.get("htc") == "Hủy tại chỗ" and pr.get("da_kiem") == "Đã kiểm hàng")
    MOI = []

    class PhieuMoi(dict):
        __getattr__ = dict.get

        def __setattr__(self, k, v):
            self[k] = v

        def insert(self):
            MOI.append(dict(self))

    goc_th, goc_nd, goc_cty = api.get_thu_hoi, fr.new_doc, api._company
    api.get_thu_hoi = lambda n: {"lo": n}
    api._company = lambda *a, **k: "HGC"
    fr.new_doc = lambda dt: PhieuMoi()
    fr.db.exists = lambda dt, *a, **k: dt == "Item"
    LO_TT = {"v": "Hủy tại chỗ"}
    fr.db.sql = lambda q, p=None, **k: ([fr._dict(LO_HUY, trang_thai=LO_TT["v"], chi_tiet_hang="BDX 3 hộp")]
                                         if "FROM `tabLo Thu Hoi` l WHERE l.name" in q else [])
    e = raises(lambda: api.bat_dau_kiem("TH-H"))
    check("Bắt đầu cho lô hủy tại chỗ: mở phiếu THEO PHIẾU (theo_phieu = 1), không đòi 'Đã nhận hàng'",
          e is None and MOI and MOI[-1].get("theo_phieu") == 1, e or str(MOI))
    LO_TT["v"] = "Đã nhận hàng"
    api.bat_dau_kiem("TH-H")
    check("lô thu về kho: phiếu kiểm thường (theo_phieu = 0)", MOI[-1].get("theo_phieu") == 0)
    LO_TT["v"] = "Tạo yêu cầu"
    check("lô thu về kho chưa nhận hàng: vẫn chặn như cũ", raises(lambda: api.bat_dau_kiem("TH-H")) is not None)
    sql_lo = fr.db.sql
    fr.db.sql = lambda q, p=None, **k: ([[LO_TT["v"]]] if "SELECT trang_thai FROM `tabLo Thu Hoi`" in q
                                         else sql_lo(q, p, **k))
    LO_TT["v"] = "Hủy tại chỗ"
    d_htc = phieu(lo_thu_hoi="TH-H")
    d_htc.before_insert()
    LO_TT["v"] = "Đã nhận hàng"
    d_thuong = phieu(lo_thu_hoi="TH-M")
    d_thuong.before_insert()
    check("phiếu tạo tay trên Desk cho lô hủy tại chỗ: TỰ bật theo_phieu (không rơi về đếm mù / 'Đang kiểm'); lô thường để nguyên",
          d_htc.get("theo_phieu") == 1 and not d_thuong.get("theo_phieu"), str((d_htc.get("theo_phieu"), d_thuong.get("theo_phieu"))))
    fr.db.sql = sql_lo
    api.get_thu_hoi, fr.new_doc, api._company = goc_th, goc_nd, goc_cty
    LO_TT["v"] = "Hủy tại chỗ"
    g = api.get_thu_hoi("TH-H")
    check("màn lô: lô hủy tại chỗ chưa phiếu -> chặng 'Đã kiểm hàng' + mở được nút nhập theo phiếu",
          g["chang"] == "Đã kiểm hàng" and g["flags"]["bat_dau"] is True, str((g["chang"], g["flags"].get("bat_dau"))))
    fr.get_all = lambda dt, *a, **k: ([fr._dict(name="F1", file_name="bien-ban-huy.pdf", creation="2026-10-18")]
                                       if dt == "File" else [])
    for co_tp, nhan in ((1, "phiếu theo phiếu"), (0, "phiếu kiểm thường")):
        fr.get_doc = lambda *a, **k: phieu(lo_thu_hoi="TH-H", theo_phieu=co_tp, items=[])
        b = api.boot_kiem("TH-H")
        if co_tp:
            check("màn nhập THEO PHIẾU: thấy mail dán + biên bản đính kèm để chép (không đếm mù)",
                  b["lo"].get("chi_tiet_hang") == "BDX 3 hộp" and [f["file_name"] for f in b["files"]] == ["bien-ban-huy.pdf"])
        else:
            check("màn kiểm thường vẫn ĐẾM MÙ: không mail dán, không file", "chi_tiet_hang" not in b["lo"] and b["files"] == [])

    print("-" * 78)
    print("── 7g. ẢNH PHIẾU: ghi số lên phiếu trả về, chụp lại, ngồi máy nhập sau ─────")
    import base64
    DTK = "Kiem Hang Thu Hoi"
    JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    HTML = b"<html><script>alert(1)</script></html>"
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    LUU, XOA, ANH = [], [], []
    PH = {"doc": phieu(name="TH-A", lo_thu_hoi="TH-A", items=[])}

    class FakeFile(dict):
        __getattr__ = dict.get

        def save(self, ignore_permissions=False):
            LUU.append(dict(self, _ip=ignore_permissions))

    def gd(dt=None, name=None, for_update=False, **k):
        if isinstance(dt, dict):
            return FakeFile(dt)
        if dt == "File":
            return fr._dict(get_content=lambda: b"noi-dung")
        return PH["doc"]

    def ga(dt, filters=None, fields=None, **k):
        if dt == "File":
            return [fr._dict(r) for r in ANH if r["attached_to_doctype"] == filters["attached_to_doctype"]
                    and r["attached_to_name"] == filters["attached_to_name"]]
        return []

    DEM = {"n": 0}
    fr.get_doc = gd
    fr.get_all = ga
    fr.generate_hash = lambda *a, **k: "abc123"
    fr.db.count = lambda dt, filters=None, **k: DEM["n"]
    fr.delete_doc = lambda dt, name, **k: XOA.append((dt, name, k))
    api.them_anh_phieu("TH-A", "data:image/jpeg;base64," + b64(JPG), "IMG_0042.HEIC")
    f = LUU[-1] if LUU else {}
    check("ảnh gắn vào PHIẾU KIỂM (không gắn lô bên vanchuyen), PRIVATE, đúng nội dung đã gửi",
          f.get("attached_to_doctype") == DTK and f.get("attached_to_name") == "TH-A" and f.get("is_private") == 1
          and f.get("content") == JPG, str({k: v for k, v in f.items() if k != "content"}))
    check("tên file do server đặt, đuôi theo CHỮ KÝ đầu file (.jpg dù máy gửi tên .HEIC)",
          f.get("file_name") == "anh-phieu-TH-A-abc123.jpg", f.get("file_name"))
    check("lưu File sau guard + đúng phiếu chưa chốt (ignore_permissions chỉ ở đó)", f.get("_ip") is True)
    n = len(LUU)
    e = raises(lambda: api.them_anh_phieu("TH-A", b64(HTML), "anh.jpg"))
    check("file .html đổi tên .jpg -> TỪ CHỐI (proxy mở inline theo đuôi = script trên tên miền site)",
          e is not None and "không phải ảnh" in e and len(LUU) == n, e)
    check("nội dung không phải base64 -> báo ảnh hỏng, không lưu",
          "hỏng" in (raises(lambda: api.them_anh_phieu("TH-A", "@@@!!", "x.jpg")) or "") and len(LUU) == n)
    goc_max = api.ANH_TOI_DA
    api.ANH_TOI_DA = 10
    check("ảnh quá trần dung lượng -> từ chối", "quá lớn" in (raises(lambda: api.them_anh_phieu("TH-A", b64(JPG))) or ""))
    api.ANH_TOI_DA = goc_max
    DEM["n"] = api.ANH_TOI_DA_SO
    check("phiếu đã đủ trần số ảnh -> từ chối, bảo xóa ảnh nhầm", "xóa bớt" in (raises(lambda: api.them_anh_phieu("TH-A", b64(JPG))) or ""))
    DEM["n"] = 0
    FILES["F-A"] = {"attached_to_doctype": DTK, "attached_to_name": "TH-A", "file_name": "anh-phieu-TH-A-abc123.jpg"}
    FILES["F-B"] = {"attached_to_doctype": DTK, "attached_to_name": "TH-B", "file_name": "anh-phieu-TH-B.jpg"}
    FILES["F-L"] = {"attached_to_doctype": "Lo Thu Hoi", "attached_to_name": "TH-A", "file_name": "phieu.pdf"}
    api.xoa_anh_phieu("TH-A", "F-A")
    check("xóa ảnh chụp nhầm của đúng phiếu", XOA and XOA[-1][:2] == ("File", "F-A") and XOA[-1][2].get("ignore_permissions") is True)
    n = len(XOA)
    check("KHÔNG xóa được ảnh của phiếu khác / file của lô bên vận chuyển qua cửa này",
          raises(lambda: api.xoa_anh_phieu("TH-A", "F-B")) is not None
          and raises(lambda: api.xoa_anh_phieu("TH-A", "F-L")) is not None and len(XOA) == n)
    PH["doc"].da_chot = 1
    check("phiếu đã CHỐT: không thêm / xóa ảnh (chốt là khóa; cần thì Mở lại)",
          raises(lambda: api.them_anh_phieu("TH-A", b64(JPG))) is not None
          and raises(lambda: api.xoa_anh_phieu("TH-A", "F-A")) is not None and len(XOA) == n)
    PH["doc"].da_chot = 0
    fr.local.response = fr._dict()
    api.xem_dinh_kem("F-A")
    check("proxy mở ảnh phiếu của phiếu kiểm (inline); file gắn DocType khác vẫn bị từ chối (7b)",
          fr.local.response.get("display_content_as") == "inline")

    ANH[:] = [dict(name="F-A", file_name="anh-phieu-TH-A-abc123.jpg", creation="2026-10-22 09:00:00", owner="kho@x",
                   attached_to_doctype=DTK, attached_to_name="TH-A"),
              dict(name="F-L", file_name="phieu.pdf", creation="2026-10-20 08:00:00", owner="dh@x",
                   attached_to_doctype="Lo Thu Hoi", attached_to_name="TH-A")]
    fr.db.sql = lambda q, p=None, **k: ([fr._dict(LO_HUY, name="TH-A", trang_thai="Đã nhận hàng")]
                                         if "FROM `tabLo Thu Hoi` l WHERE l.name" in q else [])
    fr.db.exists = lambda dt, *a, **k: dt in ("Item", DTK)
    g = api.get_thu_hoi("TH-A")
    check("màn lô: ảnh phiếu (của PHIẾU KIỂM) tách khỏi file của lô; phiếu chưa chốt có ảnh = 'chờ nhập số'",
          [x["name"] for x in g.get("anh_phieu", [])] == ["F-A"] and [x["name"] for x in g["files"]] == ["F-L"]
          and g["flags"].get("cho_nhap") is True and "xem_dinh_kem?file=F-A" in g["anh_phieu"][0]["url"]
          and g["anh_phieu"][0].get("boi") == "Người kiểm", str(g.get("anh_phieu")))
    b = api.boot_kiem("TH-A")
    check("màn kiểm hàng nhận ảnh phiếu — ngồi máy nhập theo ảnh", [x["name"] for x in b.get("anh_phieu", [])] == ["F-A"])
    PH["doc"].da_chot = 1
    g = api.get_thu_hoi("TH-A")
    check("chốt rồi: ảnh còn lại làm chứng từ, hết 'chờ nhập số'", g["flags"].get("cho_nhap") is False and len(g["anh_phieu"]) == 1)
    PH["doc"].da_chot = 0

    SQL.clear()

    def sql_ds(q, p=None, as_dict=False, **k):
        SQL.append((q, dict(p or {})))
        if "ORDER BY FIELD" in q:
            chung = dict(chang="Đang kiểm", trang_thai="Đã nhận hàng", ngay_yeu_cau="2026-10-20")
            return [fr._dict(chung, name="TH-A", phieu="TH-A", da_chot=0), fr._dict(chung, name="TH-B", phieu="TH-B", da_chot=0),
                    fr._dict(chung, name="TH-C", phieu=None, da_chot=None, chang="Đã nhận hàng"),
                    fr._dict(chung, name="TH-D", phieu="TH-D", da_chot=1, chang="Đã kiểm hàng")]
        if "FROM `tabFile`" in q and "GROUP BY attached_to_name" in q:
            return [fr._dict(n="TH-A", c=2), fr._dict(n="TH-D", c=1)]
        if "COUNT(*)" in q and "GROUP BY" not in q:
            return [[1]]
        return []

    fr.db.sql = sql_ds
    r = api.list_thu_hoi()
    a, b, c, d = r["rows"]
    check("danh sách: phiếu CHƯA chốt có ảnh -> 'chờ nhập số' + số ảnh; không ảnh / chưa có phiếu / đã chốt -> không",
          a.get("cho_nhap") is True and a.get("so_anh") == 2 and b.get("cho_nhap") is False
          and c.get("cho_nhap") is False and d.get("cho_nhap") is False and d.get("so_anh") == 1,
          str([(x["name"], x.get("cho_nhap"), x.get("so_anh")) for x in r["rows"]]))
    qa = next((q for q, _p in SQL if "FROM `tabFile`" in q and "GROUP BY attached_to_name" in q), "")
    check("số ảnh cả trang: MỘT truy vấn, chỉ file gắn PHIẾU KIỂM",
          len([1 for q, _p in SQL if "GROUP BY attached_to_name" in q]) == 1
          and next(pp for q, pp in SQL if q == qa).get("dt") == DTK)
    q_dem = next((q for q, _p in SQL if "COUNT(*)" in q and "EXISTS (SELECT 1 FROM `tabFile` f" in q), "")
    check("pill 'Chờ nhập số' đếm trên CÙNG bộ tìm: phiếu chưa chốt + có file gắn phiếu kiểm",
          "IFNULL(k.da_chot, 0) = 0" in q_dem and "f.attached_to_name = k.name" in q_dem and r.get("cho_nhap") == 1)
    api.list_thu_hoi(chang="cho_nhap")
    q, pr = next((q, pr) for q, pr in reversed(SQL) if "ORDER BY FIELD" in q)
    check("lọc pill 'Chờ nhập số'", "EXISTS (SELECT 1 FROM `tabFile` f" in q and pr.get("dt") == DTK)

    print("-" * 78)
    print("── 7h. Hóa đơn trả về KHÔNG cần hóa đơn gốc: một tờ, giá bán gần nhất ─────")
    SQL.clear()
    GIA = [fr._dict(item_code="BDX", rate=240000, conversion_factor=24, si="HD-9", posting_date="2026-09-01",
                    taxes_and_charges="VAT 8 - HGC"),
           fr._dict(item_code="KEO", rate=50000, conversion_factor=1, si="HD-7", posting_date="2026-08-01",
                    taxes_and_charges="VAT 10 - HGC")]
    HDT = []  # hoa_don_tra: (name, docstatus, item_code, sl)

    def sql_gia(q, p=None, as_dict=False, **k):
        SQL.append((q, dict(p or {})))
        if "ROW_NUMBER() OVER" in q:
            return [r for r in GIA if r.item_code in p["items"]]
        if "`custom_kiem_hang_thu_hoi` = %(k)s" in q:
            return [fr._dict(name=n, docstatus=ds, creation=n, item_code=it, sl=sl) for n, ds, it, sl in HDT]
        return []

    fr.db.sql = sql_gia
    goc_gv = fr.db.get_value

    def gv(dt, name=None, fields=None, **k):
        if dt == "Account":
            return "5213 - Hàng bán bị trả lại - HGC"
        if dt == "Sales Taxes and Charges Template":
            return "VAT mặc định - HGC"
        return goc_gv(dt, name, fields, **k)

    fr.db.get_value = gv
    g = api._gia_ban_gan_nhat("HGC", "COOP", "ADDR-HD", ["BDX", "KEO", "MOI"])
    q, pr = SQL[-1]
    check("giá bán gần nhất: MỖI mã một dòng mới nhất, ưu tiên ĐÚNG điểm giao, chỉ hóa đơn bán ĐÃ GHI SỔ của đúng khách + công ty",
          "PARTITION BY it.item_code" in q and "(IFNULL(si.shipping_address_name, '') = %(addr)s) DESC" in q
          and "si.posting_date DESC" in q and "si.docstatus = 1" in q and "si.is_return = 0" in q
          and "si.customer = %(cu)s" in q and "si.company = %(c)s" in q and "is_free_item" in q
          and pr.get("addr") == "ADDR-HD" and pr.get("cu") == "COOP" and pr.get("c") == "HGC")
    check("đơn giá theo ĐVT KHO = đơn giá dòng ÷ hệ số (240.000/thùng 24 hộp -> 10.000/hộp); mã chưa từng bán -> không có",
          g.get("BDX", {}).get("rate") == 10000 and g.get("KEO", {}).get("rate") == 50000 and "MOI" not in g, str(g))
    check("mẫu thuế: theo hóa đơn MỚI NHẤT vừa cho giá; không có giá nào -> mẫu mặc định công ty",
          api._mau_thue("HGC", g) == "VAT 8 - HGC" and api._mau_thue("HGC", {}) == "VAT mặc định - HGC")
    dvt = {"BDX": "Hộp", "KEO": "Gói", "MOI": "Hộp"}
    rows = api._dong_tra_tu_do({"BDX": 50, "KEO": 3, "MOI": 2}, dvt, g, "5213 - X")
    by = {x["item_code"]: x for x in rows}
    check("dòng: mỗi mã một dòng, ĐVT KHO, hệ số 1, số ÂM đúng số đã kiểm (không quy ra thùng)",
          by["BDX"]["qty"] == -50 and by["BDX"]["stock_qty"] == -50 and by["BDX"]["uom"] == "Hộp"
          and by["BDX"]["conversion_factor"] == 1 and by["KEO"]["uom"] == "Gói", json.dumps(by["BDX"], ensure_ascii=False))
    check("đơn giá = giá bán gần nhất (ĐVT kho); mã chưa từng bán -> để TRỐNG cho ERPNext lấy theo bảng giá",
          by["BDX"]["rate"] == 10000 and by["BDX"]["price_list_rate"] == 10000 and "rate" not in by["MOI"])
    check("không dòng nào nối hóa đơn / dòng gốc; TK 5213",
          all(not x.get("sales_invoice_item") and x.get("income_account") == "5213 - X" for x in rows))
    rows = api._dong_tra_tu_do({"BDX": 26}, dvt, g, None, giu={"BDX": 9500})
    check("cập nhật: GIỮ đơn giá người soát đã sửa trên bản nháp (9.500), không lấy lại giá bán gần nhất",
          rows[0]["rate"] == 9500 and rows[0]["qty"] == -26)

    class FakeSI:
        def __init__(self, **kw):
            self.items, self.calls = [], []
            self.name, self.return_against, self.docstatus, self.is_return = "RET-T1", None, 0, 1
            self.__dict__.update(kw)

        def get(self, k, d=None):
            return getattr(self, k, d)

        def set(self, k, v):
            setattr(self, k, v)

        def append(self, f, d):
            r = FakeRow(d)
            self.items.append(r)
            return r

        def set_missing_values(self):
            self.calls.append("set_missing_values")

        def insert(self, **k):
            self.calls.append(("insert", k))

        def save(self, **k):
            self.calls.append(("save", k))
            LUU_SI.append(self.name)

    LUU_SI = []
    SI = {}

    def nd(dt):
        SI["si"] = FakeSI()
        return SI["si"]

    goc_th, goc_nd = api.get_thu_hoi, fr.new_doc
    api.get_thu_hoi = lambda n: {"lo": n}
    fr.new_doc = nd
    fr.db.exists = lambda dt, *a, **k: dt in ("Item", DTK, "Print Heading")
    PH["doc"] = phieu(name="TH-A", lo_thu_hoi="TH-A", da_chot=1, company="HGC", customer="COOP",
                      shipping_address_name="ADDR-HD",
                      items=[FakeRow(name="r1", item_code="BDX", qty=50, stock_uom="Hộp", idx=1),
                             FakeRow(name="r2", item_code="MOI", qty=2, stock_uom="Hộp", idx=2)])
    fr.get_doc = lambda *a, **k: PH["doc"]
    r = api.tao_hoa_don_tra("TH-A")
    si = SI.get("si") or FakeSI()
    check("không truyền hóa đơn gốc -> MỘT tờ trả về: is_return, KHÔNG return_against, update_stock 0, quy tắc giá không đè",
          si.get("is_return") == 1 and not si.get("return_against") and si.get("update_stock") == 0
          and si.get("ignore_pricing_rule") == 1 and si.get("company") == "HGC" and si.get("customer") == "COOP")
    check("gắn phiếu kiểm (trạng thái tự đi) + điểm giao của lô + mẫu thuế theo hóa đơn vừa cho giá + tiêu đề 'Credit Note'",
          si.get("custom_kiem_hang_thu_hoi") == "TH-A" and si.get("shipping_address_name") == "ADDR-HD"
          and si.get("taxes_and_charges") == "VAT 8 - HGC" and si.get("select_print_heading") == "Credit Note")
    by = {x.item_code: x for x in si.items}
    check("đủ MỌI mã còn phải trả, số âm theo ĐVT kho, giá bán gần nhất, TK 5213",
          set(by) == {"BDX", "MOI"} and by["BDX"].qty == -50 and by["BDX"].rate == 10000 and by["MOI"].qty == -2
          and by["BDX"].income_account.startswith("5213"))
    check("set_missing_values (chép dòng thuế từ mẫu) chạy TRƯỚC insert; insert KHÔNG ignore_permissions",
          si.calls[:2] == ["set_missing_values", ("insert", {})], str(si.calls))
    check("trả về: cờ tu_do + mã chưa có đơn giá để màn hình nhắc điền trên Desk",
          r.get("tu_do") is True and r.get("thieu_gia") == ["MOI"] and r.get("gia_ban_gan_nhat") == 1, str(r))
    e = raises(lambda: api.tao_hoa_don_tra("TH-A", "HD-X"))
    check("CÓ hóa đơn gốc -> vẫn đi đường cũ (kiểm hóa đơn gốc đã ghi sổ, cùng khách)",
          e is not None and "HD-X không phải hóa đơn bán đã ghi sổ" in e, e)
    PH["doc"].da_chot = 0
    check("chưa chốt phiếu -> không lập", raises(lambda: api.tao_hoa_don_tra("TH-A")) is not None)
    PH["doc"].da_chot = 1
    HDT[:] = [("RET-OLD", 1, "BDX", 50), ("RET-OLD", 1, "MOI", 2)]
    check("đã đủ hóa đơn trả về -> không lập thêm", "đã có đủ" in (raises(lambda: api.tao_hoa_don_tra("TH-A")) or ""))

    # Cập nhật sau khi mở lại + sửa số: bản NỐI hóa đơn gốc chia trước, bản tự do nhận phần còn lại.
    TD = FakeSI(name="R-TD", custom_kiem_hang_thu_hoi="TH-A",
                items=[FakeRow(item_code="BDX", rate=9500, conversion_factor=1, qty=-50)])
    NOI = FakeSI(name="R-NOI", return_against="HD-9", custom_kiem_hang_thu_hoi="TH-A",
                 items=[FakeRow(item_code="BDX", rate=240000, conversion_factor=24, qty=-1)])
    DRAFT = {"R-TD": TD, "R-NOI": NOI}
    HDT[:] = [("R-TD", 0, "BDX", 50), ("R-NOI", 0, "BDX", 24)]   # R-TD lập TRƯỚC
    PH["doc"] = phieu(name="TH-A", lo_thu_hoi="TH-A", da_chot=1, company="HGC", customer="COOP",
                      shipping_address_name="ADDR-HD", items=[FakeRow(name="r1", item_code="BDX", qty=50, stock_uom="Hộp", idx=1)])
    fr.get_doc = lambda dt, name=None, **k: DRAFT[name] if dt == "Sales Invoice" else PH["doc"]
    goc_kh = api._ke_hoach_nhieu
    api._ke_hoach_nhieu = lambda inv, can, bo_qua=None: {inv[0]: (
        [{"src": "L1", "item_code": "BDX", "noi": True, "qty": 1, "stock_qty": 24}] if can.get("BDX", 0) >= 24 else [], {}, [])}
    m = types.ModuleType("erpnext.controllers.sales_and_purchase_return")
    m.make_return_doc = lambda dt, src: FakeSI(items=[FakeRow(sales_invoice_item="L1", item_code="BDX", uom="Thùng",
                                                               stock_uom="Hộp", conversion_factor=24, rate=240000)])
    for mod in ("erpnext", "erpnext.controllers"):
        sys.modules.setdefault(mod, types.ModuleType(mod))
    sys.modules["erpnext.controllers.sales_and_purchase_return"] = m
    XOA.clear()
    api.cap_nhat_hoa_don("TH-A")
    check("cập nhật: bản NỐI hóa đơn gốc chia TRƯỚC dù lập sau; bản tự do nhận phần còn lại (50 − 24 = 26)",
          LUU_SI[-2:] == ["R-NOI", "R-TD"] and [x.qty for x in TD.items] == [-26], str((LUU_SI, [x.qty for x in TD.items])))
    check("bản tự do giữ đơn giá người soát đã sửa (9.500)", [x.rate for x in TD.items] == [9500])
    PH["doc"].items[0].qty = 24
    TD.items = [FakeRow(item_code="BDX", rate=9500, conversion_factor=1, qty=-26)]
    api.cap_nhat_hoa_don("TH-A")
    check("số kiểm còn 24 = bản nối nhận hết -> bản tự do HẾT việc thì XÓA (bản nối giữ nguyên)",
          ("Sales Invoice", "R-TD") in [x[:2] for x in XOA] and ("Sales Invoice", "R-NOI") not in [x[:2] for x in XOA])
    api._ke_hoach_nhieu, api.get_thu_hoi, fr.new_doc, fr.db.get_value = goc_kh, goc_th, goc_nd, goc_gv


# ════════════════════════════════════════════════════════════════════════════
# 6, 8–10. TĨNH
# ════════════════════════════════════════════════════════════════════════════
def _fn(tree, name):
    return next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)


def kiem_tinh():
    src = read(os.path.join(API, "thu_hoi.py"))
    tree = ast.parse(src)

    print("-" * 78)
    print("── 8. Guard ở dòng đầu mọi whitelisted method ──────────────────────────")
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        wl = any("whitelist" in ast.unparse(d) for d in n.decorator_list)
        if not wl:
            continue
        stmts = [s for s in n.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
        first = ast.unparse(stmts[0]) if stmts else ""
        check(f"{n.name}: dòng đầu là guard", first.startswith(("guard_sales_any()", "guard_manager()")), first[:60])

    print("-" * 78)
    print("── 9. Không ghi bảng vanchuyen · tôn trọng quyền tạo hóa đơn ─────────────")
    bad = re.findall(r"""(set_value|delete_doc|get_doc)\(\s*(LO|LO_HANG|["']Lo Thu Hoi)""", src)
    check("không set_value / delete_doc / get_doc vào Lo Thu Hoi", not bad, str(bad))
    check("không UPDATE / INSERT / DELETE SQL trên bảng lô",
          not re.search(r"(UPDATE|INSERT INTO|DELETE FROM)\s+`tab\{?(LO|Lo Thu Hoi)", src))
    tao = _fn(tree, "tao_hoa_don_tra")
    ins = [c for c in ast.walk(tao) if isinstance(c, ast.Call) and ast.unparse(c.func) == "si.insert"]
    check("tao_hoa_don_tra: si.insert() KHÔNG ignore_permissions",
          ins and not any(k.arg == "ignore_permissions" for c in ins for k in c.keywords))
    t = ast.unparse(tao)
    check("tao_hoa_don_tra: update_stock = 0 + gắn custom_kiem_hang_thu_hoi + return_against từ make_return_doc",
          "si.update_stock = 0" in t and "si.set(SI_FIELD" in t and "make_return_doc('Sales Invoice', sales_invoice)" in t)
    tu = ast.unparse(_fn(tree, "_dung_tra_tu_do"))
    check("hóa đơn trả về không theo hóa đơn gốc: KHÔNG return_against, update_stock = 0, gắn phiếu kiểm, "
          "chép thuế (set_missing_values) — insert nằm ở tao_hoa_don_tra, không ignore_permissions (trên)",
          "return_against" not in tu and "si.update_stock = 0" in tu and "si.set(SI_FIELD" in tu
          and "si.set_missing_values()" in tu and "si.insert" not in tu)
    hook = ast.unparse(_fn(tree, "dong_bo_trang_thai"))
    check("dong_bo_trang_thai: try/except Exception, không .save()",
          "except Exception" in hook and ".save(" not in hook)
    hooks = read(os.path.join(REPO, "ketoan", "hooks.py"))
    for ev in ("after_insert", "on_update", "on_submit", "on_cancel", "on_trash"):
        check(f"hooks.py: Sales Invoice {ev} -> thu_hoi.dong_bo_trang_thai",
              re.search(rf'"{ev}":\s*"ketoan\.api\.thu_hoi\.dong_bo_trang_thai"', hooks) is not None)
    inst = read(os.path.join(REPO, "ketoan", "install.py"))
    check("install: custom field Link no_copy + gọi trong after_install",
          '"custom_kiem_hang_thu_hoi"' in inst and '"no_copy": 1' in inst and "    setup_thu_hoi_fields()" in inst)
    check("patches.txt có v0_0_20.thu_hoi_setup",
          "ketoan.patches.v0_0_20.thu_hoi_setup" in read(os.path.join(REPO, "ketoan", "patches.txt")))

    print("-" * 78)
    print("── 10. Màn kiểm hàng đếm MÙ · import map đủ module ─────────────────────")
    kh = read(os.path.join(PUB, "views", "kiemhang.js"))
    a = kh.index("function phieuSieuThi(")
    ngoai = kh[:a] + kh[kh.index("\n  }\n", a):]
    check("kiemhang.js chỉ đọc mail dán (có số khai) trong phieuSieuThi(), chỉ vẽ cho phiếu theo phiếu (hủy tại chỗ)",
          "B.khai" not in kh and "tong_sl_khai" not in kh and "chi_tiet_hang" not in ngoai
          and '${tp ? phieuSieuThi() : ""}' in kh and "const tp = !!(B.phieu && B.phieu.theo_phieu);" in kh)
    boot = _fn(tree, "boot_kiem")
    ret = [n.value for n in ast.walk(boot) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    keys = {k.value for d in ret for k in d.keys if isinstance(k, ast.Constant)}
    check("boot_kiem: payload màn kiểm KHÔNG mang số khai (không key 'khai')", ret and "khai" not in keys, str(sorted(keys)))
    check("boot_kiem: lô gửi xuống bỏ giá trị khai + mail dán — TRỪ phiếu theo phiếu (mục 7f chạy thật)",
          "theo_phieu or k not in _SO_KHAI" in ast.unparse(boot) and '_SO_KHAI = ("gia_tri_khai", "chi_tiet_hang")' in src)
    th = read(os.path.join(PUB, "views", "thuhoi.js"))
    check("màn lô chỉ hiện tổng khai khi đã chốt (và lô có bảng khai cũ)",
          "ph.da_chot && D.co_khai ? html`<div><div class=\"kt-sub\">Siêu thị khai" in th)
    page = read(os.path.join(REPO, "ketoan", "www", "ketoan.html"))
    for sub in ("lib", "components"):
        for fn in sorted(os.listdir(os.path.join(PUB, sub))):
            if fn.endswith(".js"):
                check(f"import map có {sub}/{fn}", f'"{{{{ base }}}}/{sub}/{fn}": "{{{{ base }}}}/{sub}/{fn}?v={{{{ v }}}}"' in page)
    shell = read(os.path.join(PUB, "shell.js"))
    for pat, view in (("/thu-hoi", "thuhoi.js"), ("/thu-hoi/:id", "thuhoi.js"), ("/kiem-hang/:id", "kiemhang.js")):
        check(f"route {pat} -> views/{view} (cap thuhoi)",
              f'pattern: "{pat}", view: "views/{view}", cap: "thuhoi"' in shell and os.path.exists(os.path.join(PUB, "views", view)))
    guard = read(os.path.join(API, "_guard.py"))
    check("capability thuhoi = salesany", 'caps["thuhoi"] = caps["salesany"]' in guard)
    check("www/ketoan.py đưa thuhoi vào thứ tự workspace", '"thuhoi"' in read(os.path.join(REPO, "ketoan", "www", "ketoan.py")))

    print("-" * 78)
    print("── 11. Cột đọc sang bảng lô của vanchuyen ──────────────────────────────")
    m = importlib.import_module("ketoan.api.thu_hoi")
    cu = {"ten_lai_xe", "sdt_lai_xe", "xe", "tong_sl_khai"}
    check("không đọc cột lái xe / xe / tổng khai cũ (lô giờ do đơn vị vận chuyển ngoài lấy)",
          not (cu & set(m._LO_COLS)), str(cu & set(m._LO_COLS)))
    check("đọc đơn vị thu hồi + mã vận đơn + mail dán",
          {"don_vi_thu_hoi", "ma_van_don", "chi_tiet_hang"} <= set(m._LO_COLS))
    ds = ast.unparse(_fn(tree, "list_thu_hoi"))
    check("danh sách KHÔNG kéo mail dán (Long Text) cho cả trang — dùng _LO_COLS_DS",
          "chi_tiet_hang" not in m._LO_COLS_DS and "for c in _LO_COLS_DS" in ds and "for c in _LO_COLS)" not in ds)
    check("tìm lô theo mã vận đơn", "_lo_col('ma_van_don')" in ds)
    # Gõ sai tên cột thì `_lo_col` trả NULL → màn hình TRỐNG, không báo lỗi. So với JSON thật
    # của vanchuyen khi repo đó nằm cạnh (máy dev / CI chung); không có thì bỏ qua mục này.
    vc = os.path.join(REPO, "..", "vanchuyen", "vanchuyen", "van_chuyen", "doctype", "lo_thu_hoi", "lo_thu_hoi.json")
    check("đọc dấu hủy của lô (lý do, ai, lúc nào, chặng trước khi hủy)",
          {"ly_do_huy", "huy_boi", "huy_luc", "huy_tu"} <= set(m._LO_COLS))
    if os.path.exists(vc):
        vf = {f["fieldname"]: f for f in json.load(open(vc, encoding="utf-8"))["fields"]}
        thieu = [c for c in m._LO_COLS if c not in vf]
        check("mọi cột ketoan đọc đều CÓ trong Lo Thu Hoi của vanchuyen (repo cạnh bên)", not thieu, str(thieu))
        check("chữ 'Đã hủy' ketoan so KHỚP đúng option trạng thái của vanchuyen",
              m.DA_HUY in vf["trang_thai"]["options"].split("\n"), vf["trang_thai"]["options"])
        check("chữ 'Hủy tại chỗ' ketoan so KHỚP đúng option trạng thái của vanchuyen",
              m.HUY_TAI_CHO in vf["trang_thai"]["options"].split("\n"), vf["trang_thai"]["options"])
    else:
        print("  ⚠ bỏ qua so cột với vanchuyen — không thấy repo ../vanchuyen")


def main():
    print("=" * 78)
    print("thu_hoi_check — hóa đơn trả về đúng ĐVT, trạng thái không nói dối")
    print("=" * 78)
    sys.path.insert(0, REPO)
    pb = importlib.import_module("ketoan.api.thu_hoi_phan_bo")
    kiem_ham_thuan(pb)
    kiem_tren_bo_gia()
    kiem_tinh()
    print("=" * 78)
    print("ĐẠT" if ok_all else "CÓ MỤC ĐỎ")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
