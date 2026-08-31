#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hoan_check — HÀNG HOÀN CHỜ XỬ LÝ: hàng đợi phải ra được, và phải ra ĐÚNG CỬA.

════════════════════════════════════════════════════════════════════════════
BỐN CÁI LỖ MÀ BỘ KIỂM NÀY CANH
════════════════════════════════════════════════════════════════════════════

1. **Lọc theo `trang_thai` bên `vanchuyen`.** Cột đó thuộc ĐIỀU HÀNH và nghĩa
   là *vận chuyển xong*; điều phối bấm "Đã xử lý" ngay khi nhà xe xác nhận hàng
   về. Lọc hàng đợi kế toán theo nó — cách lọc tự nhiên nhất — là việc "chưa
   xuất hóa đơn điều chỉnh" biến mất khỏi màn hình ngay hôm đó, im lặng, và lộ
   ra vài tháng sau lúc siêu thị từ chối thanh toán.

2. **Hàng đợi có dòng không bao giờ ra được.** "Giao lại nguyên lô" thì hóa đơn
   gốc vẫn đúng: không cần chứng từ, và cũng không cần phiếu trả. Bản đầu của
   controller hỏi `credit_note` TRƯỚC nên đúng những dòng đó kẹt vĩnh viễn ở
   "Chưa lập phiếu trả". Một hàng đợi không bao giờ về 0 là hàng đợi người ta
   thôi nhìn, và lúc đó nó nuốt luôn việc thật.

3. **`return_invoice` nối vào đường tiền.** Hàng trả đã bị trừ công nợ MỘT lần
   bằng chính phiếu trả (`mt._returns_join`). Module này đọc `return_invoice` để
   biết "siêu thị tự xuất hóa đơn" — chỉ chứng từ, tuyệt đối không tiền. (Luật
   chung do `return_doc_check` canh; ở đây kiểm đích danh `mt_hoan`.)

4. **Suy "đã lập phiếu trả" bằng EXISTS.** Quan hệ sự cố ↔ phiếu trả là
   NHIỀU-NHIỀU qua hóa đơn: một tờ có thể vừa móp lúc giao vừa bị trả hàng date.
   Suy bằng `EXISTS(return_against = si)` thì lập MỘT phiếu trả là CẢ HAI dòng
   cùng rời hàng đợi, phiếu thứ hai không ai lập nữa.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import ast
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402
from regression_check import code_only, js_body  # noqa: E402

API = os.path.join(rc.REPO, "ketoan", "api")
DT = os.path.join(rc.REPO, "ketoan", "mt", "doctype", "mt_hang_hoan")
JS = os.path.join(rc.REPO, "ketoan", "public", "ketoan", "views", "mt.js")

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


def func_bodies(path):
    """{tên hàm: mã nguồn KHÔNG kể docstring}.

    Docstring giải thích luật thường phải NHẮC TÊN thứ đang bị cấm — đếm cả
    docstring là báo động giả, và cách duy nhất để xanh lại là bớt giải thích.
    """
    s = open(path, encoding="utf-8").read()
    out = {}
    for node in ast.walk(ast.parse(s)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seg = ast.get_source_segment(s, node) or ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            seg = seg.replace(node.body[0].value.value, "")
        out[node.name] = seg
    return out


class Doc:
    """Bản giả của `Document` — đủ để gọi thẳng `validate()` của controller."""

    def __init__(self, **kw):
        self.name = kw.pop("name", "MT-HH-00001")
        self.su_co = None
        self.sales_invoice = None
        self.credit_note = None
        self.chung_tu_can = None
        self.misa_no = None
        self.trang_thai_giay = None
        self.ngay_xong_giay = None
        for k, v in kw.items():
            setattr(self, k, v)

    def set(self, k, v):
        setattr(self, k, v)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: True
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    ctl = importlib.import_module("ketoan.mt.doctype.mt_hang_hoan.mt_hang_hoan")
    hoan = importlib.import_module("ketoan.api.mt_hoan")

    print("=" * 82)
    print("KIỂM HÀNG HOÀN CHỜ XỬ LÝ")
    print("=" * 82)

    # ── 1. Trạng thái giấy tờ — MÁY SUY, và ba nhánh ra ba kết quả ───────
    print("── 1. Trạng thái giấy tờ suy đúng, và dòng nào cũng RA ĐƯỢC ─────────")

    d = Doc()
    ctl.MTHangHoan._derive_paper_status(d)
    check("chưa có phiếu trả -> 'Chưa lập phiếu trả'",
          d.trang_thai_giay == ctl.GIAY_CHUA_TRA, d.trang_thai_giay)

    # Có phiếu trả nhưng KHÔNG số chứng từ nào — cả hai phía đều rỗng.
    frappe.db.get_value = lambda *a, **k: None
    d = Doc(credit_note="RET-1")
    ctl.MTHangHoan._derive_paper_status(d)
    check("có phiếu trả, chưa chứng từ thuế -> 'Chưa có chứng từ thuế'",
          d.trang_thai_giay == ctl.GIAY_CHUA_CT, d.trang_thai_giay)

    frappe.db.get_value = lambda *a, **k: "HD-123"
    d = Doc(credit_note="RET-1")
    ctl.MTHangHoan._derive_paper_status(d)
    check("có cả hai -> 'Đã đủ chứng từ'",
          d.trang_thai_giay == ctl.GIAY_XONG and d.misa_no == "HD-123",
          f"{d.trang_thai_giay} / {d.misa_no}")
    check("và ĐÓNG NGÀY khi đủ", bool(d.ngay_xong_giay))

    # LỖ SỐ 2. Giao lại nguyên lô: không cần chứng từ, và cũng KHÔNG cần phiếu
    # trả. Hỏi `credit_note` trước là giam dòng này vĩnh viễn.
    print("-" * 82)
    frappe.db.get_value = lambda *a, **k: None
    d = Doc(chung_tu_can=ctl.CT_KHONG_CAN)
    ctl.MTHangHoan._derive_paper_status(d)
    check("'Không cần chứng từ' KHÔNG kèm phiếu trả vẫn ra khỏi hàng đợi",
          d.trang_thai_giay == ctl.GIAY_XONG, d.trang_thai_giay)
    check("và KHÔNG bịa ra số chứng từ nào", not d.misa_no)

    # Đổi ý: đang "không cần" quay lại "phải làm" thì việc phải quay lại hàng đợi.
    d = Doc(chung_tu_can=None, credit_note="RET-1", ngay_xong_giay="2026-08-01")
    ctl.MTHangHoan._derive_paper_status(d)
    check("bỏ kết luận 'không cần' thì việc QUAY LẠI hàng đợi",
          d.trang_thai_giay == ctl.GIAY_CHUA_CT and not d.ngay_xong_giay,
          f"{d.trang_thai_giay} / {d.ngay_xong_giay}")

    # ── 2. Phiếu trả phải là phiếu trả, ĐÃ GHI SỔ, và đúng hóa đơn ───────
    print("-" * 82)
    print("── 2. Nối phiếu trả: bốn chốt chặn ──────────────────────────────────")

    def cn(**kw):
        base = {"is_return": 1, "return_against": "SI-1", "docstatus": 1}
        base.update(kw)
        frappe.db.get_value = lambda *a, **k: frappe._dict(base)

    def throws(doc):
        try:
            ctl.MTHangHoan._check_credit_note(doc)
            return False
        except Exception:
            return True

    cn(is_return=0)
    check("chứng từ KHÔNG phải phiếu trả -> chặn",
          throws(Doc(credit_note="X", sales_invoice="SI-1")))

    # Phiếu NHÁP: `mt._returns_join` chỉ cộng `docstatus = 1`, nên nối phiếu nháp
    # là sổ này báo "đã lập phiếu trả" trong khi công nợ vẫn đòi đủ tiền tờ gốc.
    cn(docstatus=0)
    check("phiếu trả CHƯA GHI SỔ -> chặn (công nợ chỉ trừ phiếu đã ghi sổ)",
          throws(Doc(credit_note="X", sales_invoice="SI-1")))
    cn(docstatus=2)
    check("phiếu trả ĐÃ HỦY -> chặn",
          throws(Doc(credit_note="X", sales_invoice="SI-1")))

    cn(return_against=None)
    check("phiếu trả chưa khai Return Against -> chặn",
          throws(Doc(credit_note="X", sales_invoice="SI-1")))

    cn(return_against="SI-9")
    check("phiếu trả của hóa đơn KHÁC -> chặn",
          throws(Doc(credit_note="X", sales_invoice="SI-1")))

    cn()
    check("phiếu trả đúng, đã ghi sổ -> qua",
          not throws(Doc(credit_note="X", sales_invoice="SI-1")))

    # ── 3. Một phiếu sự cố -> MỘT dòng sổ ───────────────────────────────
    print("-" * 82)
    print("── 3. Nhận hai lần không thành hai việc ─────────────────────────────")

    frappe.db.get_value = lambda *a, **k: "MT-HH-00007"
    check("phiếu sự cố đã có dòng -> chặn dòng thứ hai",
          _throws_dup(ctl, Doc(su_co="SC-1")))
    frappe.db.get_value = lambda *a, **k: None
    check("phiếu sự cố chưa có dòng nào -> qua",
          not _throws_dup(ctl, Doc(su_co="SC-1")))
    # Dòng LẬP TAY (hàng date siêu thị trả, không qua sự cố vận chuyển) để trống
    # ô này — nhiều dòng cùng trống là bình thường, chặn nó là đóng cửa với đúng
    # một nửa nghiệp vụ.
    frappe.db.get_value = lambda *a, **k: "MT-HH-00007"
    check("dòng KHÔNG gắn phiếu sự cố -> không bị chặn",
          not _throws_dup(ctl, Doc(su_co=None)))

    # ── 4. KHÔNG lọc theo trạng thái bên điều hành ──────────────────────
    print("-" * 82)
    print("── 4. Không mệnh đề lọc nào đọc `trang_thai` của vanchuyen ──────────")

    src = code_only(os.path.join(API, "mt_hoan.py"))
    # Đọc để HIỆN thì được (`sc.trang_thai` trong SELECT); lọc thì không.
    bad = re.findall(r"(?:WHERE|AND|HAVING)[^\n]*\bsc\.trang_thai\b", src)
    check("không `WHERE/AND ... sc.trang_thai`", not bad, "; ".join(bad) or "sạch")
    bad2 = re.findall(r"\bsc\.trang_thai\s*(?:=|!=|IN|NOT)\b", src)
    check("không so sánh `sc.trang_thai` ở bất kỳ đâu", not bad2,
          "; ".join(bad2) or "sạch")
    check("nhưng VẪN đọc để hiện ra (kế toán cần biết điều hành ở đâu)",
          "sc.trang_thai" in src)

    bodies = func_bodies(os.path.join(API, "mt_hoan.py"))
    for fn in ("_ung_vien_sql", "_so_rows", "_counts", "board_counts"):
        b = bodies.get(fn, "")
        check(f"{fn}() không nhắc `trang_thai` của vanchuyen",
              "sc.trang_thai" not in b and "hang_ve_trang_thai\"]" not in b)

    # ── 5. Ứng viên loại theo PHIẾU SỰ CỐ, không theo hóa đơn ────────────
    print("-" * 82)
    print("── 5. Một hóa đơn, hai lần hàng về -> hai việc ──────────────────────")

    uv = bodies.get("_ung_vien_sql", "")
    check("`NOT EXISTS` so theo `h.su_co = sc.name`", "h.su_co = sc.name" in uv)
    check("KHÔNG loại theo `h.sales_invoice`", "h.sales_invoice" not in uv)
    # Suy bằng EXISTS(return_against) là đúng cái lỗ số 4 — không được có ở đâu.
    check("KHÔNG suy 'đã lập phiếu trả' bằng EXISTS(return_against)",
          "return_against" not in src or "EXISTS" not in src.split("return_against")[0][-200:])
    check("chỉ lấy hóa đơn ĐÃ GHI SỔ", "si.docstatus = 1" in uv)
    check("và lọc kênh MT", "_mt_clause" in uv)

    # ── 6. `return_invoice` — chứng từ, KHÔNG tiền ──────────────────────
    print("-" * 82)
    print("── 6. `return_invoice` chỉ nằm ở hàm KHÔNG cộng tiền ────────────────")

    MONEY_MARK = ("SUM(", "total_amount", "signed_amount", "paid", "clawed_back")
    holders = [n for n, b in bodies.items() if "return_invoice" in b]
    check("đúng MỘT hàm đọc `return_invoice`", len(holders) == 1,
          ", ".join(holders) or "không hàm nào")
    check("và đó là `_chung_tu_sieu_thi`", holders == ["_chung_tu_sieu_thi"],
          ", ".join(holders))
    b = bodies.get("_chung_tu_sieu_thi", "")
    check("hàm đó KHÔNG mang dấu hiệu cộng tiền",
          not [m for m in MONEY_MARK if m in b],
          ", ".join(m for m in MONEY_MARK if m in b) or "sạch")
    check("bỏ bảng kê đã hủy (docstatus < 2)", "docstatus < 2" in b)
    check("chịu được site chưa migrate", "table_exists" in b and "has_column" in b)

    # ── 7. Không tự tạo dòng sổ, không ghi sang app kia ──────────────────
    print("-" * 82)
    print("── 7. Máy liệt kê, NGƯỜI bấm nhận — và không đụng bảng app kia ──────")

    hooks = code_only(os.path.join(rc.REPO, "ketoan", "hooks.py"))
    check("hooks.py KHÔNG có doc_events trên `Su Co Van Chuyen`",
          "Su Co Van Chuyen" not in hooks)
    # Ghi bằng `db.set_value` sang bảng vanchuyen thì bỏ qua `_stamp_si()` bên đó
    # và cờ `custom_co_su_co` trên Sales Invoice kẹt vĩnh viễn.
    for fn, b in bodies.items():
        if "set_value" in b:
            check(f"{fn}() không `db.set_value` vào bảng vanchuyen",
                  "Su Co" not in b)
    writers = [n for n, b in bodies.items()
               if (".insert()" in b or ".save()" in b or "delete_doc" in b)]
    check("chỉ 4 hàm được GHI (create/save/sync/delete)",
          set(writers) == {"create_hoan", "save_hoan", "sync_hoan", "delete_hoan"},
          ", ".join(sorted(writers)))
    for n in writers:
        check(f"{n}() gọi guard ở dòng đầu",
              "guard_mt()" in bodies[n] or "guard_manager()" in bodies[n])
        check(f"{n}() kiểm công ty của dòng sổ", "_company(" in bodies[n])

    # `save_hoan` phải đi qua Document.save(): ghi thẳng cột là bỏ qua phần MÁY
    # SUY trong validate(), và dòng đứng nguyên trạng thái cũ.
    check("save_hoan() KHÔNG dùng db.set_value", "set_value" not in bodies["save_hoan"])

    # HAI NGƯỜI GHI MỘT CỘT là lỗi im lặng nhất trong nhóm này: kế toán sửa
    # trạng thái hàng, lưu xong thấy đúng, mở lại thấy giá trị cũ — vì danh sách
    # đọc sống từ phiếu sự cố và ghi đè. Chặn kèm câu chỉ chỗ sửa, đừng nhận rồi
    # nuốt.
    sh = bodies.get("save_hoan", "")
    check("save_hoan() KHÓA hai ô hàng vật lý khi dòng có phiếu sự cố còn sống",
          "khoa_hang" in sh and "_su_co_rows" in sh and "frappe.throw" in sh)
    check("và danh sách nói cho màn hình biết ô nào bị khóa",
          '"khoa_hang"' in bodies.get("_decorate", ""))
    det_js = js_body(open(JS, encoding="utf-8").read(), "openHoanDetail")
    check("màn hình TẮT sẵn hai ô đó, không đợi backend ném lỗi",
          "r.khoa_hang" in det_js and "disabled" in det_js)
    check("và KHÔNG gửi hai ô bị khóa lên (gửi là hỏng cả lượt lưu)",
          "r.khoa_hang" in det_js.split("mtHoanSave")[-1][:400])

    # ── 8. Tuổi việc tính từ NGÀY XẢY RA ────────────────────────────────
    print("-" * 82)
    print("── 8. Tuổi việc, và 'chưa biết' không được vẽ thành 0 ───────────────")

    check("`_tuoi(None)` trả None, không phải 0", hoan._tuoi(None) is None)
    check("`_tuoi` đếm từ ngày đưa vào",
          hoan._tuoi("2026-08-01", as_of="2026-08-31") == 30,
          str(hoan._tuoi("2026-08-01", as_of="2026-08-31")))
    dec = bodies.get("_decorate", "")
    check("danh sách lấy tuổi từ `ngay_xay_ra`", 'ngay_xay_ra' in dec and '_tuoi(' in dec)
    check("KHÔNG lấy tuổi từ ngày nhập phiếu", "creation" not in dec)

    # ── 9. Chuỗi rỗng là RỖNG, không phải 'mọi chuỗi' ───────────────────
    print("-" * 82)
    print("── 9. Bộ lọc chuỗi dùng chung MỘT quy tắc ───────────────────────────")

    cf = bodies.get("_chain_filter", "")
    check("dùng `_customer_in_clause` (rỗng -> `1 = 0`)",
          "_customer_in_clause" in cf and "chain_customers" in cf)
    check("không tự dựng mệnh đề IN bằng nối chuỗi",
          "join" not in cf.lower() or "_customer_in_clause" in cf)
    p = {}
    check("chuỗi rỗng -> không lọc gì (`1 = 1`)", hoan._chain_filter("", p) == "1 = 1")

    # ── 10. Màn hình nói ra điều nó đang làm ────────────────────────────
    print("-" * 82)
    print("── 10. Màn hình bày ra đủ bốn ô và nói rõ đơn vị đếm ────────────────")

    js = open(JS, encoding="utf-8").read()
    load = js_body(js, "loadHangHoan")
    check("có màn `loadHangHoan`", bool(load))
    check("nói rõ đơn vị là LẦN HÀNG QUAY VỀ, không phải tờ hóa đơn",
          "LẦN HÀNG QUAY VỀ" in load)
    check("nói rõ KHÔNG đọc trạng thái bên điều hành", "điều hành" in load)
    check("ô 'Chưa vào sổ' có trong bảng ô",
          '"chua_vao_so"' in js and "Chưa vào sổ" in js)
    check("site chưa cài vanchuyen thì NÓI VÌ SAO ô đó trống",
          "d.vanchuyen" in load and "d.note" in load)
    age = js_body(js, "hoanAge")
    check("tuổi 'chưa biết' KHÔNG vẽ thành 0 ngày",
          "chưa rõ tuổi" in age and "undefined" in age)
    det = js_body(js, "openHoanDetail")
    check("chi tiết hiện bảng mã hàng đọc bên vanchuyen",
          "r.items" in det and "vận chuyển" in det)
    check("chi tiết nói rõ hai kịch bản trả hàng", "chung_tu_note" in det)
    check("chỉ cho chọn phiếu trả ĐÃ GHI SỔ", "đã ghi sổ" in det.lower())
    check("phiếu trả đã dùng ở dòng khác thì KHÓA, không giấu",
          "da_dung" in det and "disabled" in det)

    # ── 11. Bảng chuỗi đếm cùng một tập với màn hình ────────────────────
    print("-" * 82)
    print("── 11. Thẻ chuỗi và màn hình nói về CÙNG một tập ────────────────────")

    hub = code_only(os.path.join(API, "mt_hub.py"))
    check("mt_hub đếm bằng `mt_hoan.board_counts`, không viết lại SQL",
          "mt_hoan.board_counts" in hub and "MT Hang Hoan" not in hub)
    bc = bodies.get("board_counts", "")
    check("gom chuỗi qua `_customer_chain_map`, không qua cột `chain` đã chép",
          "_customer_chain_map" in bc or "mapping" in bc)
    check("và KHÔNG đọc `h.chain`", "h.chain" not in bc)
    check("site chưa migrate thì trả rỗng, KHÔNG ném lỗi ra bảng chuỗi",
          "table_exists" in bc and "return out" in bc)
    check("bước 'Móp lỗi / trả lại' không còn ghi là ngoài portal",
          '"key": "tra_hang", "label": "Móp lỗi / trả lại", "portal": True' in hub)

    # ── 12. CHẠY THẬT `list_hoan` — SQL dựng được, hình dạng đúng ───────
    #
    # Chín mục trên soi MÃ NGUỒN. Soi mã nguồn không bao giờ bắt được một lỗi
    # f-string hay một tham số ràng buộc thiếu — thứ chỉ nổ khi câu SQL được
    # dựng thật. Nên mục này GỌI THẲNG endpoint với một `db.sql` giả ghi lại
    # mọi câu truy vấn.
    print("-" * 82)
    print("── 12. Gọi thật `list_hoan` — không câu SQL nào gãy ─────────────────")

    seen = []

    def fake_sql(q, params=None, as_dict=False, **kw):
        seen.append((" ".join(q.split()), dict(params or {})))
        ql = q.upper()
        if "COUNT(*)" in ql and not as_dict:
            return [[3]]
        if "GROUP BY H.CUSTOMER" in ql or "GROUP BY SI.CUSTOMER" in ql:
            return []
        if "GROUP BY H.TRANG_THAI_GIAY" in ql:
            return [frappe._dict(tt=ctl.GIAY_CHUA_TRA, n=2),
                    frappe._dict(tt=ctl.GIAY_CHUA_CT, n=1)]
        if "TABMT PAYMENT ADVICE" in ql:
            return []
        if "TABSU CO VAN CHUYEN" in ql:
            return [frappe._dict(
                su_co="SC-1", name="SC-1", sales_invoice="SI-1",
                loai_su_co="Hư hỏng, móp méo", trang_thai="Đã xử lý",
                ngay_xay_ra="2026-08-01", ngay_phat_sinh="2026-08-01",
                ngay_bao="2026-08-03", huong_xu_ly="Hoàn toàn bộ",
                trang_thai_hang="Đã về sân", hang_ve_trang_thai="Đã về sân",
                ngay_hang_ve=None, tong_mat_duong=120000.0, stock_entry=None,
                customer="KH-1", customer_name="LOTTE Mart",
                posting_date="2026-07-20", grand_total=5893696.0, po_no="PO-9")]
        if "TABMT HANG HOAN" in ql:
            return [frappe._dict(
                name="MT-HH-00001", su_co="SC-1", sales_invoice="SI-1",
                customer="KH-1", customer_name="LOTTE Mart", chain="LOTTE",
                po_no="PO-9", ngay_xay_ra="2026-08-01", ngay_bao="2026-08-03",
                loai_su_co="Hư hỏng, móp méo", huong_xu_ly="Giao lại",
                chung_tu_can=None, ghi_chu=None,
                trang_thai_giay=ctl.GIAY_CHUA_TRA, credit_note=None,
                misa_no=None, ngay_xong_giay=None,
                trang_thai_hang="Chưa về", ngay_hang_ve=None,
                posting_date="2026-07-20", grand_total=5893696.0,
                cn_misa_relation=None, cn_misa_no=None, cn_amount=0.0, cn_date=None)]
        return []

    frappe.db.sql = fake_sql
    frappe.db.get_single_value = lambda *a, **k: "HG"

    try:
        out = hoan.list_hoan(company="HG")
        ran = True
    except Exception as e:  # noqa: BLE001
        ran = False
        out = {}
        print(f"     {type(e).__name__}: {e}")
    check("`list_hoan()` chạy được, không nổ SQL", ran)
    if ran:
        for k in ("bucket", "rows", "total", "pages", "counts", "vanchuyen",
                  "chung_tu_options", "trang_thai_hang_options", "note"):
            check(f"trả về khóa `{k}`", k in out)
        check("mặc định là ô 'cho_xu_ly' (cả hai ô việc)",
              out.get("bucket") == "cho_xu_ly", str(out.get("bucket")))
        c = out.get("counts") or {}
        check("đếm ĐỦ BỐN ô, kể cả ô đang không xem",
              all(k in c for k in ("chua_vao_so", "chua_phieu_tra",
                                   "chua_chung_tu", "xong")))
        check("`cho_xu_ly` = chưa lập phiếu trả + chưa chứng từ",
              c.get("cho_xu_ly") == c.get("chua_phieu_tra", 0) + c.get("chua_chung_tu", 0),
              str(c))
        # ĐỌC SỐNG: `huong_xu_ly` trên dòng sổ là "Giao lại", bên vanchuyen đã
        # đổi thành "Hoàn toàn bộ" — màn hình phải hiện cái MỚI và NÓI RA.
        r0 = (out.get("rows") or [{}])[0]
        check("hiện giá trị SỐNG bên vanchuyen, không phải bản chép",
              r0.get("huong_xu_ly") == "Hoàn toàn bộ", str(r0.get("huong_xu_ly")))
        check("và NÓI RA chỗ điều hành đã sửa",
              any(x.get("field") == "huong_xu_ly" for x in (r0.get("da_doi") or [])),
              str(r0.get("da_doi")))
        check("dòng có phiếu sự cố -> khóa hai ô hàng vật lý",
              r0.get("khoa_hang") is True)

    # Mọi câu SQL phải dùng THAM SỐ RÀNG BUỘC, không nối chuỗi giá trị vào.
    bad_sql = [q for q, _p in seen if "'%s'" % "HG" in q or " = HG" in q]
    check("không câu nào nối thẳng giá trị vào SQL", not bad_sql,
          (bad_sql[0][:60] if bad_sql else "sạch"))
    # `IN ()` rỗng là lỗi cú pháp MariaDB — mọi mệnh đề IN phải có tham số.
    check("không `IN ()` rỗng", not [q for q, _p in seen if "IN ()" in q])

    # Ô "Chưa vào sổ" khi site CHƯA cài vanchuyen: không nổ, và NÓI VÌ SAO trống.
    frappe.db.table_exists = lambda dt: dt != "Su Co Van Chuyen"
    out2 = hoan.list_hoan(company="HG", bucket="chua_vao_so")
    check("site chưa cài vanchuyen -> vẫn mở được màn", out2.get("rows") == [])
    check("và trả kèm câu giải thích, không im lặng", bool(out2.get("note")))
    check("vẫn trả tùy chọn để modal lập dòng dùng được",
          bool(out2.get("chung_tu_options")))
    frappe.db.table_exists = lambda dt: True

    print()
    print("=" * 82)
    print("KẾT QUẢ:", "ĐẠT — hàng đợi ra được đúng cửa, không lọc nhầm cột của điều hành, "
          "và `return_invoice` không chạm đường tiền" if ok_all
          else "CÓ MỤC KHÔNG ĐẠT ❌")
    return 0 if ok_all else 1


def _throws_dup(ctl, doc):
    try:
        ctl.MTHangHoan._check_one_row_per_su_co(doc)
        return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
