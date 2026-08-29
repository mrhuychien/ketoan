#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""po_field_check — SỐ PO CHỈ ĐƯỢC ĐỌC TỪ MỘT Ô.

════════════════════════════════════════════════════════════════════════════
VÌ SAO CÓ PHÉP KIỂM NÀY
════════════════════════════════════════════════════════════════════════════

Trên Sales Invoice có HAI ô mang số PO, và app đang đọc cả hai:

    custom_po_   ô của SITE   <- misa_push, mt_win, mt_win_grn, app vanchuyen
    po_no        ô CHUẨN      <- mt_einv, mt_ledger

Nghe thì `po_no` hợp lý hơn — nó là ô chuẩn của ERPNext. Nhưng đọc Client
Script thì thấy ngược lại:

    dòng 313:  custom_po_: so_po      <- người nhập điền ô này
    dòng 474:  po_no: so_po           <- chép sang
    dòng 488:  po_no: "THU HỘ COD"    <- GHI ĐÈ với đơn có thu hộ COD

Nên với đơn COD, `po_no` KHÔNG còn là số PO: nó là chữ "THU HỘ COD". Màn hình
nào đọc `po_no` sẽ in chữ đó vào cột PO, và không có gì báo là sai — số PO vẫn
"có giá trị", chỉ là giá trị sai. Kiểu hỏng im lặng nhất.

`custom_po_` là ô thật (chủ dự án đã xác nhận), và cũng là ô mà app `vanchuyen`
đọc — nên nó là khóa nghiệp vụ nối hai app.

════════════════════════════════════════════════════════════════════════════
PHÉP KIỂM NÀY KIỂM GÌ
════════════════════════════════════════════════════════════════════════════

1. `mt.SI_PO_FIELD` tồn tại và bằng `custom_po_`.
2. `mt.po_column()` KHÔNG lùi về `po_no` khi site thiếu ô — trả `NULL`.
3. Không module nào đọc `si.po_no` / `"po_no"` từ Sales Invoice nữa.
   (`MT Win Pending.po_no` là ô của DocType MÌNH, không dính dáng — phải phân
   biệt được, nếu không phép kiểm báo động giả và sẽ bị gỡ.)
4. Mọi nơi cần ô PO đều đi qua `SI_PO_FIELD` / `po_column()`.

Chạy: python3 docs/mt/verified/po_field_check.py
"""

import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
API = os.path.join(ROOT, "ketoan", "api")

sys.path.insert(0, os.path.dirname(__file__))
from regression_check import code_only  # noqa: E402

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


def read(name):
    with open(os.path.join(API, name), encoding="utf-8") as f:
        return f.read()


print("── 1. MỘT NGUỒN cho tên ô ────────────────────────────────────────────")

mt = read("mt.py")
m = re.search(r'^SI_PO_FIELD\s*=\s*"([^"]+)"', mt, re.M)
check("mt.py khai SI_PO_FIELD", bool(m))
check("SI_PO_FIELD = 'custom_po_'", bool(m) and m.group(1) == "custom_po_",
      m.group(1) if m else "không có")

check("mt.py có po_column()", "def po_column(" in mt)

# Thân hàm `po_column` không được nhắc `po_no`: nhắc tức là có đường lùi về ô
# hỏng. Đọc THÂN HÀM, không đọc cả file — docstring của module khác cũng nói
# tới `po_no` một cách chính đáng.
body = ""
tree = ast.parse(mt)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "po_column":
        body = ast.get_source_segment(mt, node) or ""
        # bỏ docstring: phần GIẢI THÍCH được phép nói "không lùi về po_no"
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            doc = node.body[0].value.value
            if isinstance(doc, str):
                body = body.replace(doc, "")
check("po_column() không có đường lùi về `po_no`", '"po_no"' not in body and "po_no" not in body,
      "thân hàm sạch" if "po_no" not in body else "CÓ nhắc po_no")
check("po_column() trả NULL khi site thiếu ô", '"NULL"' in body)


print("\n── 2. Không module nào còn đọc `po_no` của Sales Invoice ─────────────")

# `MT Win Pending` có ô `po_no` CỦA CHÍNH NÓ. Những chỗ đó hợp lệ, phải loại ra
# nếu không phép kiểm báo động giả — và một phép kiểm hay báo động giả thì sớm
# muộn cũng bị ai đó gỡ đi.
SI_PO_NO = (
    re.compile(r"si\.po_no"),                 # SQL: si.po_no
    re.compile(r'_col\(\s*"po_no"\s*\)'),     # _col("po_no") -> cột Sales Invoice
    re.compile(r'col\(\s*"po_no"\s*\)'),
)
PENDING_FILES = ("mt_win_pending.py",)

bad = []
for fn in sorted(os.listdir(API)):
    if not fn.endswith(".py") or fn in PENDING_FILES:
        continue
    src = code_only(os.path.join(API, fn))
    for rx in SI_PO_NO:
        for hit in rx.finditer(src):
            bad.append(f"{fn}: {hit.group(0)}")
check("không còn chỗ nào đọc `si.po_no`", not bad, "; ".join(bad[:4]) or "sạch")

# Và ô của MT Win Pending thì VẪN PHẢI CÒN — nếu phép kiểm trên hăng quá mà xóa
# luôn cả ô đó thì màn đợt giao Win mất số PO.
pend = read("mt_win_pending.py")
check("MT Win Pending giữ ô `po_no` của chính nó", "doc.po_no" in pend)


print("\n── 3. Mọi nơi cần PO đều đi qua nguồn chung ──────────────────────────")

for fn, how in (("mt_einv.py", "po_column"),
                ("mt_ledger.py", "po_column"),
                ("mt_win_grn.py", "SI_PO_FIELD"),
                ("misa_push.py", "SI_PO_FIELD")):
    src = code_only(os.path.join(API, fn))
    check(f"{fn} dùng {how}", how in src)

# mt_win.py gọi qua hàm bọc riêng nhưng vẫn phải lấy tên ô từ mt.py.
win = code_only(os.path.join(API, "mt_win.py"))
check("mt_win.py lấy tên ô từ mt.SI_PO_FIELD", "SI_PO_FIELD" in win)
check("mt_win.py không còn gõ thẳng 'custom_po_'", '"custom_po_"' not in win)

# Chuỗi 'custom_po_' chỉ được xuất hiện ĐÚNG MỘT LẦN trong toàn bộ api/, ở
# mt.py. Đây là phép đếm dễ hỏng nhất trong file này nên nói rõ: docstring KHÔNG
# được tính (nhiều module giải thích ô này một cách chính đáng), nên dùng
# `code_only`.
hits = []
for fn in sorted(os.listdir(API)):
    if not fn.endswith(".py"):
        continue
    if '"custom_po_"' in code_only(os.path.join(API, fn)):
        hits.append(fn)
check("chuỗi 'custom_po_' chỉ nằm ở mt.py", hits == ["mt.py"], ", ".join(hits) or "không nơi nào")


print("\n── 4. Client Script vẫn là nguồn của cả hai ô ────────────────────────")

# Nếu ai đó sửa Client Script cho `po_no` hết bị ghi đè, lý do của cả file này
# biến mất — và lúc đó nên bàn lại chứ không phải im lặng giữ nguyên.
cs_path = os.path.join(ROOT, "ketoan", "misa_integration", "client_script_sales_invoice.js")
cs = open(cs_path, encoding="utf-8").read()
check("Client Script vẫn điền custom_po_", "custom_po_: so_po" in cs)
check("Client Script vẫn ghi đè po_no bằng 'THU HỘ COD'",
      'po_no: "THU HỘ COD"' in cs,
      "còn ghi đè -> po_no vẫn không tin được")


print()
print("KẾT LUẬN:", "TẤT CẢ ĐẠT ✅" if ok_all else "CÓ MỤC KHÔNG ĐẠT ❌")
sys.exit(0 if ok_all else 1)
