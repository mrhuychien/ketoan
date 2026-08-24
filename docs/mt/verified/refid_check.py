#!/usr/bin/env python3
"""Kiểm đường CẤP LẠI RefID cho hóa đơn cũ.

Hóa đơn ghi sổ TRƯỚC khi cài app không đi qua hook `before_submit` nên không có
`custom_misa_ref_id`, và bị `build_payload` chặn ngay khi bấm xuất hóa đơn.

Chỗ này hỏng theo hai kiểu, và bộ kiểm soi cả hai:

  1. **Ngõ cụt** — câu báo lỗi bảo kế toán "chạy backfill_ref_id", một việc
     KHÔNG có nút nào trên portal. Người dùng đọc xong vẫn đứng yên.
  2. **Phát hành trùng** — cấp RefID mới cho hóa đơn CŨ ĐÃ phát hành rồi đẩy
     lại là tạo hóa đơn thứ hai có giá trị pháp lý cho cùng một chứng từ.
     Không rút lại được.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.db.commit = lambda *a, **kw: None
    frappe.db.has_column = lambda dt, c: True

    push = importlib.import_module("ketoan.api.misa_push")
    sync = importlib.import_module("ketoan.api.misa_sync")

    print("=" * 82)
    print("KIỂM ĐƯỜNG CẤP LẠI RefID CHO HÓA ĐƠN CŨ")
    print("=" * 82)
    bad = 0

    # ── 1. Thiếu RefID -> chặn, và chỉ được chỗ BẤM ──────────────────────
    si = _D(name="HD-04793", custom_misa_ref_id="", items=[])
    try:
        push.build_payload(si, _D())
        print("  ❌ hóa đơn thiếu RefID -> VẪN dựng payload")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        msg = str(e)
        ok = "HD-04793" in msg
        print(f"  {'✅' if ok else '❌'} hóa đơn thiếu RefID -> chặn, nêu đích danh hóa đơn")
        bad += not ok

        ok = "Hóa đơn VAT" in msg and "Cấp RefID cho hóa đơn cũ" in msg
        print(f"  {'✅' if ok else '❌'} câu báo lỗi chỉ được CHỖ BẤM trên portal, không chỉ "
              f"nói tên hàm cho kế toán tự xoay")
        bad += not ok

        ok = "KHÔNG phát hành lại" in msg
        print(f"  {'✅' if ok else '❌'} nói luôn việc đó KHÔNG phát hành lại hóa đơn nào — "
              f"đó là câu hỏi đầu tiên trong đầu người bấm")
        bad += not ok

    # ── 2. Backfill chỉ đụng hóa đơn ĐÃ ghi sổ và ĐANG thiếu ─────────────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/misa_sync.py"), encoding="utf-8").read()
    body = re.split(r"\n(?=\S)", src.split("def backfill_ref_id")[1])[0]
    ok = '"docstatus": 1' in body and '"custom_misa_ref_id": ("is", "not set")' in body
    print(f"  {'✅' if ok else '❌'} chỉ cấp cho hóa đơn ĐÃ ghi sổ và ĐANG thiếu — không "
          f"đụng hóa đơn đã có RefID")
    bad += not ok

    ok = "set_value" in body and "update_modified=False" in body
    print(f"  {'✅' if ok else '❌'} ghi bằng `db_set(update_modified=False)`, không `save()` "
          f"chứng từ đã ghi sổ")
    bad += not ok

    # ── 3. LƯỚI CHẶN PHÁT HÀNH TRÙNG — chỗ chết người nhất ──────────────
    print("-" * 82)
    psrc = open(os.path.join(rc.REPO, "ketoan/api/misa_push.py"), encoding="utf-8").read()
    pbody = re.split(r"\n(?=\S)", psrc.split("def push_invoice")[1])[0]

    for flag in ("custom_misa_pushed_at", "vn_einvoice_lookup_code", "custom_misa_inv_no"):
        ok = flag in pbody
        print(f"  {'✅' if ok else '❌'} chặn đẩy trùng có đọc cờ `{flag}`")
        bad += not ok

    ok = "for_update=True" in pbody
    print(f"  {'✅' if ok else '❌'} đọc cờ DƯỚI KHÓA HÀNG — không khóa thì auto-push và nút "
          f"bấm tay cùng vượt qua rồi cùng POST")
    bad += not ok

    i_lock = pbody.index("for_update=True")
    i_check = pbody.index("fresh.get(\"custom_misa_pushed_at\")")
    ok = i_lock < i_check
    print(f"  {'✅' if ok else '❌'} đọc lại cờ SAU khi có khóa — đọc trước khóa là đọc giá "
          f"trị đã cũ")
    bad += not ok

    ok = 'si.get("is_return")' in pbody
    print(f"  {'✅' if ok else '❌'} hóa đơn trả hàng KHÔNG đi đường đẩy thẳng — phải là hóa "
          f"đơn điều chỉnh/thay thế trên MISA")
    bad += not ok

    # ── 4. RefID cấp lại KHÔNG được dùng để đối soát hóa đơn cũ ──────────
    print("-" * 82)
    ok = "KHÔNG khớp ngược được với MISA" in body
    print(f"  {'✅' if ok else '❌'} nói rõ RefID cấp lại KHÔNG khớp ngược được với MISA — "
          f"hóa đơn cũ phải đối soát bằng MST + ngày + tiền")
    bad += not ok

    # ── 5. Màn hình có bày con số ra, không đợi người gặp lỗi ────────────
    print("-" * 82)
    vsrc = open(os.path.join(rc.REPO, "ketoan/api/misa_vat.py"), encoding="utf-8").read()
    ok = "missing_ref_id" in vsrc
    print(f"  {'✅' if ok else '❌'} màn hình Hóa đơn VAT đếm sẵn số hóa đơn còn thiếu RefID")
    bad += not ok

    ok = "_missing_ref_id() if is_chief()" in vsrc
    print(f"  {'✅' if ok else '❌'} chỉ đếm cho kế toán trưởng — người khác không bấm được "
          f"thì đếm cũng vô nghĩa")
    bad += not ok

    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/vat.js"), encoding="utf-8").read()
    ok = "vat-refid" in js and "vatBackfillRefId" in js
    print(f"  {'✅' if ok else '❌'} có NÚT thật trên màn hình, không chỉ là con số")
    bad += not ok

    ok = "KHÔNG" in js and "phát hành lại" in js
    print(f"  {'✅' if ok else '❌'} hỏi xác nhận trước khi chạy, nói rõ không phát hành lại")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — hóa đơn cũ cấp lại RefID được từ portal, và không đường nào làm "
          "hóa đơn đã phát hành bị phát hành lần hai")
    return 0


if __name__ == "__main__":
    sys.exit(main())
