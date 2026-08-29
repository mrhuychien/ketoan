#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""return_doc_check — `return_invoice` NỐI CHỨNG TỪ, KHÔNG NỐI TIỀN.

════════════════════════════════════════════════════════════════════════════
CÁI LỖ MÀ PHÉP KIỂM NÀY CANH
════════════════════════════════════════════════════════════════════════════

Hàng trả lại được trừ khỏi công nợ ĐÚNG MỘT LẦN, bằng chính phiếu trả hàng
trên ERPNext (`mt._returns_join`, từ MT2-N).

Bảng kê thanh toán của chuỗi CŨNG có dòng ghi giảm cho lần trả hàng đó. Nếu
dòng ghi giảm ấy nối được vào đường tiền thì cùng một lần trả hàng bị trừ HAI
LẦN khỏi công nợ. `mt_advice` đã chặn ở ba chỗ (`_match_row`, `relink_line`,
`_paid_join`) và ghi hẳn cảnh báo trong mã.

MT2-AK thêm ô `return_invoice` để dòng ghi giảm trỏ về phiếu trả — nhưng CHỈ
để đối chiếu chứng từ (chứng minh "siêu thị đã xuất hóa đơn trả"), tuyệt đối
không phải để tính tiền. Ô mới này chính là con đường mở lại cái lỗ cũ.

Nên phép kiểm ở đây KHÔNG kiểm tính năng — nó canh cái lỗ.

════════════════════════════════════════════════════════════════════════════
VÌ SAO KHÔNG DÒ BẰNG grep THÔNG THƯỜNG
════════════════════════════════════════════════════════════════════════════

`"return_invoice" in src` là vô dụng: ô này ĐƯỢC PHÉP xuất hiện — ở
`_chain_return_docs`, ở controller, ở JSON. Câu hỏi không phải "có xuất hiện
không" mà là "xuất hiện ở HÀM NÀO". Nên phải soi THÂN HÀM: mọi hàm có tên/nội
dung mang tính TIỀN đều không được nhắc tới nó.

Chạy: python3 docs/mt/verified/return_doc_check.py
"""

import ast
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
API = os.path.join(ROOT, "ketoan", "api")
DT = os.path.join(ROOT, "ketoan", "mt", "doctype", "mt_payment_advice_line")

sys.path.insert(0, os.path.dirname(__file__))
from regression_check import code_only, js_body  # noqa: E402

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


def src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def func_bodies(path):
    """{tên hàm: mã nguồn hàm KHÔNG kể docstring}. Docstring giải thích luật
    thường phải NHẮC TÊN ô đang bị cấm — đếm cả docstring là báo động giả."""
    s = src(path)
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


print("── 1. Ô đã có, và mô tả nói rõ nó không phải đường tiền ──────────────")

j = json.load(open(os.path.join(DT, "mt_payment_advice_line.json"), encoding="utf-8"))
fld = next((f for f in j["fields"] if f["fieldname"] == "return_invoice"), None)
check("JSON có ô `return_invoice`", bool(fld))
check("kiểu Link -> Sales Invoice",
      bool(fld) and fld["fieldtype"] == "Link" and fld["options"] == "Sales Invoice")
check("mô tả cảnh báo đây KHÔNG phải đường tiền",
      bool(fld) and "không phải đường tính tiền" in fld.get("description", "").lower()
      .replace("tuyệt đối không phải đường tính tiền", "không phải đường tính tiền"))
check("nằm trong field_order", "return_invoice" in j.get("field_order", []))


print("\n── 2. Controller ràng buộc đúng chỗ ──────────────────────────────────")

ctl = os.path.join(DT, "mt_payment_advice_line.py")
bodies = func_bodies(ctl)
check("có `_validate_return_invoice`", "_validate_return_invoice" in bodies)
vb = bodies.get("_validate_return_invoice", "")
check("chỉ cho dòng 'Ghi giảm'", "ROW_KIND_DEDUCT" in vb)
check("bắt buộc là phiếu trả (is_return)", '"is_return"' in vb)
# Gọi ở validate() chứ không chỉ ĐỊNH NGHĨA — định nghĩa mà không gọi thì luật
# không bao giờ chạy, và đó đúng là kiểu hỏng mà bộ kiểm này hay bỏ lọt.
check("được GỌI trong validate()", "self._validate_return_invoice()" in bodies.get("validate", ""))

# Và luật cũ phải còn nguyên: dòng ghi giảm vẫn KHÔNG được nối `sales_invoice`.
check("luật cũ còn: chỉ 'Thanh toán' mới nối `sales_invoice`",
      "ROW_KIND_PAYMENT" in bodies.get("validate", "")
      and "self.sales_invoice and self.row_kind" in bodies.get("validate", ""))


print("\n── 3. KHÔNG hàm TIỀN nào chạm tới `return_invoice` ───────────────────")

# Danh sách hàm tính tiền của tầng công nợ. Thêm hàm tiền mới thì thêm vào đây —
# và nếu ai quên thêm, mục 3b bên dưới vẫn quét toàn bộ theo từ khóa.
MONEY_FUNCS = {
    "mt.py": ("_paid_join", "_returns_join", "_debt_joins", "_match_row", "relink_line"),
    "mt_ledger.py": ("_rows", "_status"),
    "mt_debt.py": ("_fetch",),
}
for fn, names in MONEY_FUNCS.items():
    b = func_bodies(os.path.join(API, fn))
    for name in names:
        if name not in b:
            continue
        check(f"{fn}::{name}() không nhắc `return_invoice`",
              "return_invoice" not in b[name])

# 3b. Quét RỘNG: bất kỳ hàm nào có dấu hiệu cộng tiền mà lại nhắc `return_invoice`.
# Bắt được cả hàm mới chưa kịp khai ở trên.
MONEY_MARK = ("SUM(", "total_amount", "signed_amount", "paid", "clawed_back")
suspects = []
for fn in sorted(os.listdir(API)):
    if not fn.endswith(".py"):
        continue
    for name, body in func_bodies(os.path.join(API, fn)).items():
        if "return_invoice" not in body:
            continue
        if name == "_chain_return_docs":   # hàm ĐỌC chứng từ, đã kiểm riêng ở mục 4
            continue
        if any(m in body for m in MONEY_MARK):
            suspects.append(f"{fn}::{name}")
check("không hàm nào vừa cộng tiền vừa đọc `return_invoice`", not suspects,
      ", ".join(suspects) or "sạch")


print("\n── 4. Hàm đọc chứng từ KHÔNG được cộng tiền ──────────────────────────")

led = func_bodies(os.path.join(API, "mt_ledger.py"))
crd = led.get("_chain_return_docs", "")
check("có `_chain_return_docs`", bool(crd))
# Đây là chỗ dễ trượt tay nhất: đang đọc dòng bảng kê, thêm `total_amount` vào
# SELECT rồi cộng lên là mở lại đúng cái lỗ trừ-hai-lần.
check("không SELECT `total_amount`", "total_amount" not in crd)
check("không SUM gì cả", "SUM(" not in crd.upper())
check("chịu được site chưa migrate", "has_column" in crd and "table_exists" in crd)
check("bỏ bảng kê đã hủy (docstatus < 2)", "docstatus < 2" in crd)

ret = led.get("_attach_returns", "")
check("`_attach_returns` hỏi CẢ HAI phía chứng từ",
      "ours" in ret and "theirs" in ret and "not (ours or theirs)" in ret)


print("\n── 5. Màn hình bày ra được nhánh 'siêu thị xuất' ─────────────────────")

js = src(os.path.join(ROOT, "ketoan", "public", "ketoan", "views", "mt.js"))
# Soi THÂN hàm dựng modal, không soi cả file: chuỗi có mặt ở đâu đó trong 6000
# dòng không chứng minh được nó nằm trong bảng phiếu trả.
trace = js_body(js, "ledgerTrace") or js
check("modal truy vết hiện `chain_inv_no`", "r.chain_inv_no" in trace)
check("có nhãn 'Siêu thị xuất'", "Siêu thị xuất" in trace)
check("mở được bảng kê nguồn", "r.chain_advice" in trace)
# Cảnh báo CHƯA CÓ vẫn phải còn, và phải nói cả nhánh mới — nếu không kế toán
# đọc xong vẫn không biết phải làm gì để tắt nó.
check("cảnh báo CHƯA CÓ còn nguyên", "CHƯA CÓ" in trace)
check("cảnh báo nhắc luôn đường bảng kê", "bảng kê" in trace)


print()
print("KẾT LUẬN:", "TẤT CẢ ĐẠT ✅" if ok_all else "CÓ MỤC KHÔNG ĐẠT ❌")
sys.exit(0 if ok_all else 1)
