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

    # Định nghĩa mà không gọi thì luật không bao giờ chạy — và cả ba khẳng định
    # phía trên gọi THẲNG method, nên chúng không thấy được điều đó. Gỡ ba lời
    # gọi khỏi validate() thì trạng thái không bao giờ được suy, phiếu nháp nối
    # được, và hàng đợi không bao giờ vơi; bộ kiểm vẫn xanh nếu thiếu mục này.
    ctl_v = func_bodies(os.path.join(DT, "mt_hang_hoan.py")).get("validate", "")
    for m in ("_check_one_row_per_su_co", "_check_credit_note",
              "_derive_paper_status"):
        check(f"`{m}` được GỌI trong validate()", f"self.{m}()" in ctl_v)

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

    # Bộ giả GHI LẠI bộ lọc. Nuốt tham số thì phép kiểm chỉ chứng minh
    # "trả về khác None -> ném", không thấy được bộ lọc hỏi đúng bảng nào và
    # có TỰ LOẠI MÌNH ra hay không.
    calls = []

    def rec_get_value(dt, filters=None, *a, **k):
        calls.append((dt, filters))
        return rec_get_value.ret

    rec_get_value.ret = "MT-HH-00007"
    frappe.db.get_value = rec_get_value

    calls.clear()
    check("phiếu sự cố đã có dòng -> chặn dòng thứ hai",
          _throws_dup(ctl, Doc(su_co="SC-1", name="MT-HH-00001")))
    dt, flt_ = calls[-1] if calls else (None, None)
    check("hỏi đúng bảng `MT Hang Hoan`", dt == "MT Hang Hoan", str(dt))
    check("lọc theo `su_co`", isinstance(flt_, dict) and flt_.get("su_co") == "SC-1",
          str(flt_))
    # Thiếu vế này thì mọi lần LƯU LẠI một dòng cũ đều tự tìm thấy chính nó và
    # ném trùng — cả hàng đợi đông cứng, không ai sửa được dòng nào.
    check("và TỰ LOẠI dòng đang kiểm ra khỏi bộ lọc",
          isinstance(flt_, dict) and flt_.get("name") == ["!=", "MT-HH-00001"],
          str(flt_))
    rec_get_value.ret = None
    check("phiếu sự cố chưa có dòng nào -> qua",
          not _throws_dup(ctl, Doc(su_co="SC-1")))
    # Dòng LẬP TAY (hàng date siêu thị trả, không qua sự cố vận chuyển) để trống
    # ô này — nhiều dòng cùng trống là bình thường, chặn nó là đóng cửa với đúng
    # một nửa nghiệp vụ.
    rec_get_value.ret = "MT-HH-00007"
    check("dòng KHÔNG gắn phiếu sự cố -> không bị chặn",
          not _throws_dup(ctl, Doc(su_co=None)))

    # ── 4. KHÔNG lọc theo trạng thái bên điều hành ──────────────────────
    print("-" * 82)
    print("── 4. Không mệnh đề lọc nào đọc `trang_thai` của vanchuyen ──────────")

    src = code_only(os.path.join(API, "mt_hoan.py"))
    bodies = func_bodies(os.path.join(API, "mt_hoan.py"))

    # ĐỌC ĐƯỢC, LỌC THÌ KHÔNG. Kiểm bằng VỊ TRÍ so với mệnh đề `FROM`, không
    # bằng từ khóa WHERE/AND: mệnh đề lọc hay được ghép bằng `where.append(...)`
    # nên chẳng có chữ WHERE nào cùng dòng, và một phép kiểm dò từ khóa đã bỏ
    # lọt đúng kiểu đó khi thử phá.
    READERS = {"_su_co_rows", "_ung_vien_rows"}
    holders = sorted(n for n, b in bodies.items() if "sc.trang_thai" in b)
    check("chỉ hàm ĐỌC được nhắc `sc.trang_thai`", set(holders) <= READERS,
          ", ".join(holders) or "không hàm nào")
    check("và VẪN đọc để hiện ra (kế toán cần biết điều hành ở đâu)",
          set(holders) == READERS, ", ".join(holders))
    def _chi_trong_select(body, needle):
        """Mọi lần nhắc `needle` đều nằm trong DANH SÁCH SELECT của câu của nó.

        Không cắt ở `FROM` đầu tiên: một hàm thường có hai câu (đếm + lấy dòng),
        và cắt như vậy thì câu thứ hai luôn nằm ở "phần đuôi" dù nó hoàn toàn
        hợp lệ. Với mỗi lần nhắc, hỏi đúng câu chứa nó: `SELECT` gần nhất phía
        trước có đứng sau `FROM` gần nhất phía trước không.
        """
        i = body.find(needle)
        while i >= 0:
            head = body[:i]
            if head.rfind("SELECT") <= head.rfind("FROM "):
                return False
            i = body.find(needle, i + 1)
        return True

    for n in holders:
        check(f"{n}(): `sc.trang_thai` chỉ nằm trong danh sách SELECT",
              _chi_trong_select(bodies[n], "sc.trang_thai"))
    # Và không hàm nào SO SÁNH nó, dù viết hoa hay thường, dù cách dòng thế nào.
    cmp_hits = re.findall(r"sc\.trang_thai\s*(?:!=|=|<>|\s+in\s|\s+not\s)",
                          src, re.I)
    check("không phép so sánh nào trên `sc.trang_thai`", not cmp_hits,
          "; ".join(cmp_hits) or "sạch")

    for fn in ("_ung_vien_sql", "_count_ung_vien", "_so_rows", "_counts",
               "board_counts"):
        b = bodies.get(fn, "")
        check(f"{fn}() không nhắc `trang_thai` của vanchuyen",
              "sc.trang_thai" not in b)

    # ── 5. Ứng viên loại theo PHIẾU SỰ CỐ, không theo hóa đơn ────────────
    print("-" * 82)
    print("── 5. Một hóa đơn, hai lần hàng về -> hai việc ──────────────────────")

    uv = bodies.get("_ung_vien_sql", "")
    check("`NOT EXISTS` so theo `h.su_co = sc.name`", "h.su_co = sc.name" in uv)
    check("KHÔNG loại theo `h.sales_invoice`", "h.sales_invoice" not in uv)
    # Suy bằng EXISTS(return_against) là đúng cái lỗ số 4. Hỏi TỪNG HÀM chọn
    # việc, không dò 200 ký tự quanh lần nhắc đầu tiên — `return_against` có mặt
    # hợp lệ ở `_phieu_tra_ung_vien` nên phép dò kiểu đó bị ghim ở đó và không
    # bao giờ nhìn thấy phần còn lại của module.
    QUEUE_FUNCS = ("_ung_vien_sql", "_count_ung_vien", "_ung_vien_rows",
                   "_counts", "_so_rows", "board_counts", "_trang_thai_expr",
                   "_ct_thue_expr")
    dirty = [n for n in QUEUE_FUNCS if "return_against" in bodies.get(n, "")]
    check("không hàm CHỌN VIỆC nào suy bằng `return_against`", not dirty,
          ", ".join(dirty) or "sạch")
    # Và `_phieu_tra_ung_vien` — nơi được phép dùng — chỉ dùng nó để LIỆT KÊ ứng
    # viên của MỘT hóa đơn, không để kết luận dòng nào đã xong.
    check("`return_against` chỉ còn ở hàm liệt kê ứng viên",
          sorted(n for n, b in bodies.items() if "return_against" in b)
          == ["_phieu_tra_ung_vien"],
          ", ".join(sorted(n for n, b in bodies.items() if "return_against" in b)))
    check("chỉ lấy hóa đơn ĐÃ GHI SỔ", "si.docstatus = 1" in uv)
    check("và lọc kênh MT", "_mt_clause" in uv)

    # ── 6. `return_invoice` — chứng từ, KHÔNG tiền ──────────────────────
    print("-" * 82)
    print("── 6. `return_invoice` chỉ nằm ở hàm KHÔNG cộng tiền ────────────────")

    MONEY_MARK = ("SUM(", "total_amount", "signed_amount", "paid", "clawed_back")
    # Hai hàm ĐƯỢC PHÉP: một hàm đọc số chứng từ, một hàm dựng mệnh đề "đã có
    # chứng từ chưa". Danh sách đóng — hàm thứ ba xuất hiện là phải nghĩ lại,
    # không phải nới danh sách cho xong.
    ALLOWED = {"_chung_tu_sieu_thi", "_ct_thue_expr"}
    holders = sorted(n for n, b in bodies.items() if "return_invoice" in b)
    check("chỉ hai hàm ĐƯỢC PHÉP nhắc `return_invoice`",
          set(holders) <= ALLOWED, ", ".join(holders) or "không hàm nào")
    check("và cả hai đều CÓ MẶT (gỡ mất là luật không còn chạy)",
          ALLOWED <= set(bodies), ", ".join(sorted(ALLOWED - set(bodies))) or "đủ")
    for n in sorted(ALLOWED & set(bodies)):
        b = bodies[n]
        check(f"{n}() KHÔNG mang dấu hiệu cộng tiền",
              not [m for m in MONEY_MARK if m in b],
              ", ".join(m for m in MONEY_MARK if m in b) or "sạch")
    b = bodies.get("_chung_tu_sieu_thi", "")
    check("bỏ bảng kê đã hủy (docstatus < 2)", "docstatus < 2" in b)
    check("chịu được site chưa migrate", "table_exists" in b and "has_column" in b)
    check("mệnh đề SQL cũng bỏ bảng kê đã hủy",
          "docstatus < 2" in bodies.get("_ct_thue_expr", ""))
    # Site chưa có ô nào để hỏi -> "chưa biết" phải rơi vào nhánh CHƯA CÓ.
    # Trả "1" ở đó là mọi dòng nhảy sang "Đã đủ chứng từ" trong im lặng.
    check("site chưa có ô nào -> mệnh đề trả `0`, không phải `1`",
          'return "(" + " OR ".join(parts) + ")" if parts else "0"'
          in bodies.get("_ct_thue_expr", ""))

    # ── 7. Không tự tạo dòng sổ, không ghi sang app kia ──────────────────
    print("-" * 82)
    print("── 7. Máy liệt kê, NGƯỜI bấm nhận — và không đụng bảng app kia ──────")

    hooks = code_only(os.path.join(rc.REPO, "ketoan", "hooks.py"))
    check("hooks.py KHÔNG có doc_events trên `Su Co Van Chuyen`",
          "Su Co Van Chuyen" not in hooks)
    # Ghi bằng `db.set_value` sang bảng vanchuyen thì bỏ qua `_stamp_si()` bên đó
    # và cờ `custom_co_su_co` trên Sales Invoice kẹt vĩnh viễn.
    #
    # KHÔNG dò "có nhắc tên bảng không": tên bảng khai MỘT LẦN ở hằng `SU_CO`
    # cấp module, nên `frappe.db.set_value(SU_CO, ...)` không chứa chuỗi nào
    # nhìn thấy được. Và một vòng lặp "nếu có set_value thì kiểm" sẽ KHÔNG
    # KHẲNG ĐỊNH GÌ khi không hàm nào có — im lặng đọc thành đạt.
    #
    # Luật thật đơn giản hơn: module này KHÔNG ghi bằng `db.set_value` ở đâu cả.
    # Mọi lần ghi đi qua `Document.save()` để `validate()` còn chạy.
    setters = sorted(n for n, b in bodies.items() if "set_value" in b)
    check("KHÔNG hàm nào dùng `db.set_value` (mọi lần ghi đi qua Document.save)",
          not setters, ", ".join(setters) or "sạch")
    for const in ("SU_CO", "SU_CO_ITEM"):
        users = sorted(n for n, b in bodies.items()
                       if f"set_value({const}" in b or f'set_value("{const}' in b)
        check(f"và không ai ghi vào bảng `{const}` của app kia", not users,
              ", ".join(users) or "sạch")
    writers = [n for n, b in bodies.items()
               if (".insert()" in b or ".save()" in b or "delete_doc" in b)]
    check("chỉ 4 hàm được GHI (create/save/sync/delete)",
          set(writers) == {"create_hoan", "save_hoan", "sync_hoan", "delete_hoan"},
          ", ".join(sorted(writers)))
    # "Ở DÒNG ĐẦU" phải kiểm bằng AST. Dò chuỗi thì một guard nằm trong nhánh
    # `if not su_co:` — tức cửa mà màn hình thật sự dùng lại KHÔNG có guard —
    # vẫn đạt, và endpoint mở toang cho mọi user đã đăng nhập.
    api_tree = ast.parse(open(os.path.join(API, "mt_hoan.py"), encoding="utf-8").read())
    first_stmt = {}
    for node in api_tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [b for b in node.body
                if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
        first_stmt[node.name] = body[0] if body else None

    def _la_guard(stmt):
        return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id.startswith("guard_"))

    for n in sorted(writers) + ["list_hoan", "get_hoan"]:
        check(f"{n}(): CÂU LỆNH ĐẦU TIÊN là lời gọi guard",
              _la_guard(first_stmt.get(n)),
              type(first_stmt.get(n)).__name__)
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
    # Vế "hoặc có gọi _customer_in_clause" làm khẳng định này luôn đúng khi dòng
    # trên đã đạt — tức nó không kiểm gì. Hỏi thẳng cái nguy hiểm: nối GIÁ TRỊ
    # vào SQL. Hỏi trên CẢ module, vì hàm mới ai đó viết sau cũng dính.
    QUOTE_MARK = ("'%s'", '"%s"', "'\" +", "' + ")
    quoted = sorted(n for n, b in bodies.items()
                    if any(m in b for m in QUOTE_MARK))
    check("không hàm nào nhét giá trị đã bọc nháy vào SQL", not quoted,
          ", ".join(quoted) or "sạch")
    check("`_chain_filter` không tự ghép chuỗi", ".join(" not in cf)
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

    # ── 11b. Mọi truy vấn Sales Invoice PHẢI buộc công ty ───────────────
    #
    # `frappe.db.sql` thô KHÔNG đi qua User Permission — chốt chặn duy nhất là
    # mệnh đề công ty do `_company()` trả về. Và "khách của chuỗi này" KHÔNG
    # phải một ranh giới công ty: khách hàng dùng chung giữa các pháp nhân.
    print("-" * 82)
    print("── 11b. SQL thô không đi qua permission — phải tự buộc công ty ──────")

    for fn in ("_le_cua_chuoi", "_phieu_tra_ung_vien", "_counts", "_so_rows",
               "board_counts"):
        b = bodies.get(fn, "")
        if "tabSales Invoice" not in b:
            continue
        check(f"{fn}() buộc công ty trên `tabSales Invoice`",
              "company = %(company)s" in b or "h.company = %(company)s" in b)
    check("_ung_vien_sql() buộc công ty",
          "si.company = %(company)s" in bodies.get("_ung_vien_sql", ""))

    # ── 11c. Điều hành XÓA một giá trị cũng là một thay đổi ─────────────
    #
    # Ghi đè chỉ khi giá trị mới KHÁC RỖNG thì cảnh báo "đã đổi" bật vĩnh viễn:
    # nó so bản chép cũ với giá trị rỗng mới, thấy khác, kêu — mà màn hình vẫn
    # hiện bản chép cũ, và `sync_hoan` cũng không xóa được nên không bao giờ tắt.
    print("-" * 82)
    print("── 11c. Xóa một giá trị bên điều hành cũng phải theo sang ───────────")

    live = {"SC-9": frappe._dict(
        name="SC-9", sales_invoice="SI-9", loai_su_co="Hàng date / thời vụ",
        trang_thai="Đang xử lý", ngay_phat_sinh="2026-08-05",
        huong_xu_ly=None, hang_ve_trang_thai=None, ngay_hang_ve=None,
        stock_entry=None, tong_mat_duong=0.0)}
    orig_rows = hoan._su_co_rows
    hoan._su_co_rows = lambda names: {n: live[n] for n in names if n in live}
    try:
        out = hoan._decorate([frappe._dict(
            name="MT-HH-9", su_co="SC-9", sales_invoice="SI-9", credit_note=None,
            loai_su_co="Hàng date / thời vụ", huong_xu_ly="Hoàn toàn bộ",
            ngay_xay_ra="2026-08-05", trang_thai_hang=None, ngay_hang_ve=None,
            grand_total=0.0, cn_amount=0.0)])[0]
    finally:
        hoan._su_co_rows = orig_rows
    check("giá trị bị xóa bên điều hành -> màn hình cũng trống",
          not out.get("huong_xu_ly"), repr(out.get("huong_xu_ly")))
    check("và vẫn NÓI RA là đã đổi",
          any(x["field"] == "huong_xu_ly" for x in out.get("da_doi") or []),
          str(out.get("da_doi")))
    # Và `sync_hoan` phải XÓA được, không chỉ ghi đè: bỏ qua giá trị rỗng thì
    # bản chép không bao giờ đuổi kịp, "Chép lại vào sổ" thành nút không làm gì,
    # và cảnh báo "đã đổi" không bao giờ tắt. Kiểm bằng cách GỌI THẲNG, không
    # bằng dò chuỗi — dò chuỗi ở đây đã báo động giả một lần.
    dsync = Doc(su_co="SC-9", huong_xu_ly="Hoàn toàn bộ", loai_su_co="X",
                ngay_xay_ra="2026-08-05", trang_thai_hang="Đã về sân",
                ngay_hang_ve=None, po_no="PO-1", hang_ve_ghi_chu="cũ",
                ngay_bao=None)
    hoan._stamp_from_su_co(dsync, live["SC-9"])
    check("`sync_hoan` XÓA được ô mà điều hành đã bỏ trống",
          not dsync.huong_xu_ly, repr(dsync.huong_xu_ly))
    check("và vẫn chép giá trị có thật",
          dsync.loai_su_co == "Hàng date / thời vụ", repr(dsync.loai_su_co))

    # ── 11d. Một phiếu trả -> một dòng sổ ───────────────────────────────
    print("-" * 82)
    print("── 11d. Hai dòng KHÔNG được cùng nhận một phiếu trả ─────────────────")

    ctl_bodies = func_bodies(os.path.join(DT, "mt_hang_hoan.py"))
    check("controller có `_check_one_row_per_credit_note`",
          "_check_one_row_per_credit_note" in ctl_bodies)
    check("và được GỌI trong validate() (định nghĩa mà không gọi thì luật không chạy)",
          "self._check_one_row_per_credit_note()" in ctl_bodies.get("validate", ""))
    calls2 = []

    def rec2(dt, filters=None, *a, **k):
        calls2.append((dt, filters))
        return rec2.ret

    rec2.ret = "MT-HH-00002"
    frappe.db.get_value = rec2
    check("phiếu trả đã thuộc dòng khác -> chặn",
          _throws_dup_cn(ctl, Doc(credit_note="RET-1", name="MT-HH-00001")))
    dt2, f2 = calls2[-1] if calls2 else (None, None)
    check("hỏi đúng bảng, lọc theo `credit_note`",
          dt2 == "MT Hang Hoan" and isinstance(f2, dict)
          and f2.get("credit_note") == "RET-1", f"{dt2} / {f2}")
    check("và TỰ LOẠI dòng đang kiểm ra khỏi bộ lọc",
          isinstance(f2, dict) and f2.get("name") == ["!=", "MT-HH-00001"], str(f2))
    rec2.ret = None
    check("phiếu trả chưa ai nhận -> qua",
          not _throws_dup_cn(ctl, Doc(credit_note="RET-1")))
    rec2.ret = "MT-HH-00002"
    check("dòng chưa có phiếu trả -> không bị chặn",
          not _throws_dup_cn(ctl, Doc(credit_note=None)))

    # ── 11e. Nhóm CHƯA GÁN CHUỖI không bị bảng chuỗi nuốt ───────────────
    #
    # `get_board` chỉ chạy qua `MT_CHAINS`, nên khách chưa khai `custom_mt_chain`
    # rơi vào khóa rỗng và không thẻ nào đếm. Màn hàng hoàn thì KHÔNG lọc chuỗi
    # nên nó đếm — hai màn hình, hai con số, cùng một tập.
    print("-" * 82)
    print("── 11e. Việc của khách chưa gán chuỗi vẫn phải hiện ra ──────────────")

    check("mt_hub đưa việc hàng hoàn vào dòng `unassigned`",
          'uh = hoan.get("")' in hub and '"hoan_chua_vao_so": cint(uh' in hub)
    check("và cộng vào `totals.todo`", "+ unassigned_todo" in hub)
    check("dòng đó hiện ra cả khi KHÔNG còn nợ đồng nào",
          "has_unassigned" in hub and "unassigned_todo" in hub)
    # Dò chuỗi tới đây là đủ để đạt dù `unassigned_todo` bị gán bằng 0 — lúc đó
    # việc của khách chưa gán chuỗi lại biến mất y như trước. Hỏi bằng AST xem
    # nó thật sự CỘNG hai ô đếm.
    hub_tree = ast.parse(open(os.path.join(API, "mt_hub.py"), encoding="utf-8").read())
    rhs = None
    for node in ast.walk(hub_tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "unassigned_todo"):
            rhs = node.value
    keys = {n.value for n in ast.walk(rhs)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)} if rhs else set()
    check("`unassigned_todo` là phép CỘNG hai ô đếm, không phải hằng số",
          isinstance(rhs, ast.BinOp)
          and {"hoan_open", "hoan_chua_vao_so"} <= keys,
          type(rhs).__name__ + " " + str(sorted(keys)))
    board_js = js_body(open(JS, encoding="utf-8").read(), "boardShell")
    check("bảng chuỗi NÓI RA nhóm chưa gán chuỗi có việc hàng hoàn",
          "unassigned_debt.todo" in board_js and "CHƯA GÁN CHUỖI" in board_js)
    card_js = js_body(open(JS, encoding="utf-8").read(), "chainCard")
    check("thẻ chuỗi đếm việc hàng hoàn (không thì `todo` to lên mà không nói vì sao)",
          "c.hoan_chua_vao_so" in card_js and "c.hoan_open" in card_js)

    # ── 11f. Trạng thái giấy tờ SUY LÚC ĐỌC, không đọc cột đã đông cứng ─
    #
    # Cột `h.trang_thai_giay` chỉ được tính trong validate(), tức chỉ khi có
    # người bấm lưu. Hai sự kiện quyết định nó thì đến SAU và không đi qua bảng
    # này: số hóa đơn MISA ghi lên phiếu trả, và dòng ghi giảm của bảng kê trỏ
    # về phiếu trả. Lọc theo cột đã lưu là dòng đã xong nằm lại hàng đợi mãi mãi
    # mà không ai bấm gì để nó thoát.
    print("-" * 82)
    print("── 11f. Trạng thái suy lúc đọc — việc xong phải RA được ─────────────")

    for fn in ("_counts", "_so_rows", "board_counts"):
        b = bodies.get(fn, "")
        check(f"{fn}() dùng `_trang_thai_expr`", "_trang_thai_expr" in b)
        # Và cột đã đông cứng chỉ được phép xuất hiện dưới dạng ẢNH CHỤP có
        # nhãn (`AS tt_luu`). Mọi cách nhắc khác đều là đọc lại cột đó để lọc
        # hoặc để gộp — đúng thứ hàm `_trang_thai_expr` sinh ra để thay thế.
        hits = [i for i in range(len(b)) if b.startswith("h.trang_thai_giay", i)]
        lac = [i for i in hits
               if not b[i:].startswith("h.trang_thai_giay AS tt_luu")]
        check(f"{fn}(): `h.trang_thai_giay` chỉ còn là ảnh chụp `AS tt_luu`",
              not lac, f"{len(lac)} lần nhắc khác")
    check("danh sách trả về SỐ CHỨNG TỪ sống, không phải ảnh chụp `h.misa_no`",
          'd["misa_no"] = cstr(r.get("cn_misa_no")' in bodies.get("_decorate", ""))
    check("và NÓI RA khi ảnh chụp trên Desk lệch với sự thật",
          '"tt_lech"' in bodies.get("_decorate", ""))
    det_js2 = js_body(open(JS, encoding="utf-8").read(), "openHoanDetail")
    check("màn hình bày ra chỗ lệch đó", "r.tt_lech" in det_js2)

    # ── 11g. Đổi phiếu trả thì số chứng từ phải đổi theo ────────────────
    print("-" * 82)
    print("── 11g. Đổi phiếu trả không được giữ số chứng từ của phiếu cũ ───────")

    frappe.db.get_value = lambda *a, **k: "SO-CUA-PHIEU-MOI"
    d = Doc(credit_note="RET-B", misa_no="SO-CUA-PHIEU-CU")
    ctl.MTHangHoan._derive_paper_status(d)
    check("số chứng từ SUY LẠI theo phiếu trả đang nối",
          d.misa_no == "SO-CUA-PHIEU-MOI", repr(d.misa_no))
    frappe.db.get_value = lambda *a, **k: None
    d = Doc(credit_note="RET-B", misa_no="SO-CUA-PHIEU-CU")
    ctl.MTHangHoan._derive_paper_status(d)
    check("phiếu mới chưa có chứng từ -> dòng QUAY LẠI hàng đợi",
          not d.misa_no and d.trang_thai_giay == ctl.GIAY_CHUA_CT,
          f"{d.misa_no!r} / {d.trang_thai_giay}")

    # ── 11h. Ô chọn phiếu trả không được tự xóa liên kết đang có ────────
    #
    # Phiếu trả bị hủy để amend rơi khỏi bộ lọc `docstatus = 1`; không dòng nào
    # `selected` thì trình duyệt chọn dòng đầu ("— chưa lập —"), và lần Lưu tiếp
    # theo xóa trắng phiếu trả cùng số chứng từ — người dùng chỉ định sửa ghi chú.
    print("-" * 82)
    print("── 11h. Phiếu trả đang nối luôn có mặt trong ô chọn ─────────────────")

    ptv = bodies.get("_phieu_tra_ung_vien", "")
    check("truy vấn GIỮ phiếu đang nối kể cả khi nó hết hợp lệ",
          "keep_cur" in ptv and "r.name = %(cur)s" in ptv)
    check("và đánh dấu nó KHÔNG hợp lệ thay vì giấu",
          '"hop_le"' in ptv and '"la_hien_tai"' in ptv)
    check("màn hình cảnh báo trước khi người dùng bấm Lưu",
          "hop_le === false" in det_js2 and "không còn hợp lệ" in det_js2)

    # ── 11i. Bấm xong một dòng không được sinh ra kết luận sai ──────────
    load_js = js_body(open(JS, encoding="utf-8").read(), "loadHangHoan")
    check("trang rơi ra ngoài phạm vi thì kẹp về trang cuối, không in 'hết việc'",
          "state.page > 1" in load_js and "d.pages" in load_js)

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
        """Bộ giả nhận diện câu truy vấn theo ĐẦU DANH SÁCH SELECT.

        KHÔNG nhận theo mệnh đề FROM: `_trang_thai_expr` nhúng một `EXISTS
        (SELECT 1 FROM \`tabMT Payment Advice Line\` ...)` vào chính câu đọc sổ,
        nên "FROM đầu tiên" của câu đó là bảng kê chứ không phải bảng sổ. Bộ giả
        trả nhầm dữ liệu cho nhau thì bộ kiểm báo hỏng vì lỗi của chính nó.
        """
        ql = " ".join(q.split()).upper()
        seen.append((" ".join(q.split()), dict(params or {})))

        if ql.startswith("SELECT COUNT(*) FROM `TABSU CO VAN CHUYEN`"):
            return [[3]]
        if ql.startswith("SELECT COUNT(*) FROM `TABMT HANG HOAN`"):
            return [[1]]
        if ql.startswith("SELECT CASE WHEN") and "AS TT, COUNT(*)" in ql:
            return [frappe._dict(tt=ctl.GIAY_CHUA_TRA, n=2),
                    frappe._dict(tt=ctl.GIAY_CHUA_CT, n=1)]
        if ql.startswith("SELECT H.CUSTOMER"):
            return []
        if ql.startswith("SELECT L.RETURN_INVOICE"):
            return []
        if ql.startswith("SELECT SC.NAME, SC.SALES_INVOICE"):
            return [frappe._dict(
                name="SC-1", sales_invoice="SI-1", loai_su_co="Hư hỏng, móp méo",
                trang_thai="Đã xử lý", ngay_phat_sinh="2026-08-01",
                creation="2026-08-03", huong_xu_ly="Hoàn toàn bộ", po="PO-9",
                tinh=None, mo_ta=None, hang_ve_trang_thai="Đã về sân",
                ngay_du_kien_ve=None, ngay_hang_ve=None, stock_entry=None,
                tong_mat_duong=120000.0, boi_thuong_trang_thai=None,
                boi_thuong_so_tien=0.0)]
        if ql.startswith("SELECT SC.NAME AS SU_CO"):
            return [frappe._dict(
                su_co="SC-1", sales_invoice="SI-1", loai_su_co="Hư hỏng, móp méo",
                trang_thai="Đã xử lý", ngay_xay_ra="2026-08-01",
                ngay_bao="2026-08-03", huong_xu_ly="Hoàn toàn bộ",
                trang_thai_hang="Đã về sân", ngay_hang_ve=None,
                tong_mat_duong=120000.0, customer="KH-1",
                customer_name="LOTTE Mart", posting_date="2026-07-20",
                grand_total=5893696.0, po_no="PO-9")]
        if ql.startswith("SELECT H.NAME, H.SU_CO"):
            # Bản chép trên sổ nói "Giao lại"; điều hành đã đổi thành "Hoàn toàn
            # bộ". Màn hình phải hiện cái MỚI và nói ra chỗ đã đổi.
            return [frappe._dict(
                name="MT-HH-00001", su_co="SC-1", sales_invoice="SI-1",
                customer="KH-1", customer_name="LOTTE Mart", chain="LOTTE",
                po_no="PO-9", ngay_xay_ra="2026-08-01", ngay_bao="2026-08-03",
                loai_su_co="Hư hỏng, móp méo", huong_xu_ly="Giao lại",
                chung_tu_can=None, ghi_chu=None,
                trang_thai_giay=ctl.GIAY_CHUA_TRA, tt_luu=ctl.GIAY_CHUA_TRA,
                credit_note=None, misa_no_luu=None, ngay_xong_giay=None,
                trang_thai_hang="Chưa về", ngay_hang_ve=None,
                posting_date="2026-07-20", grand_total=5893696.0,
                cn_misa_relation=None, cn_misa_no=None, cn_amount=0.0,
                cn_date=None)]
        if "COUNT(*)" in ql and not as_dict:
            return [[0]]
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


def _throws_dup_cn(ctl, doc):
    try:
        ctl.MTHangHoan._check_one_row_per_credit_note(doc)
        return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
