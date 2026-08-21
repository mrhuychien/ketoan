"""Kiểm TẦNG ĐIỀU HƯỚNG mới của portal MT (`mt_hub.py` ↔ `views/mt.js`).

    python3 docs/mt/verified/ui_board_check.py

Giao diện mới có hai tầng: BẢNG CHUỖI (mỗi chuỗi một thẻ) rồi BÀN LÀM VIỆC của
một chuỗi (các bước theo vòng đời tháng, SOP §1). Cái nối hai bên là một hợp
đồng dữ liệu mỏng — và nó hỏng theo một kiểu KHÔNG BAO GIỜ ném lỗi:

  · JS đọc `c.we_issue_discount` để quyết định có hiện bước "Chiết khấu mình
    xuất" hay không. Đổi tên cờ đó ở Python thì `c[...]` ra `undefined`, bước
    im lặng BIẾN MẤT khỏi mọi chuỗi. Không lỗi, không cảnh báo — kế toán chỉ
    thấy portal "mất tính năng".
  · Số việc trên thẻ cộng từ các khóa như `lines_unmatched`. Khóa sai thì thẻ
    hiện "xong" trong khi còn nguyên việc.
  · Một bước có nút bấm mà `loadTab` không xử -> bấm vào không có gì xảy ra.

Bốn phép dưới đây đối chiếu thẳng hai file với nhau, cộng một phép chạy THẬT
`get_board` trên stub để bắt lỗi cú pháp SQL và khóa trả về thiếu.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

JS = "ketoan/public/ketoan/views/mt.js"
COMPANY = "HGC"


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


def _js():
    return open(os.path.join(rc.REPO, JS), encoding="utf-8").read()


def _block(src, name):
    """Nội dung mảng `const NAME = [ … ];` ở cấp module."""
    m = re.search(r"^const " + name + r" = \[(.*?)^\];", src, re.S | re.M)
    if not m:
        raise AssertionError("không thấy khối %s trong mt.js" % name)
    return m.group(1)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.db.table_exists = lambda dt: True
    frappe.db.has_column = lambda dt, col: True
    frappe.db.sql = lambda *a, **k: []
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    # `_mt_clause` đọc nhóm khách hàng từ Ketoan Portal Settings. Bộ kiểm khác
    # né được vì chúng thay thẳng `_fetch`; ở đây phải chạy THẬT câu SQL nên
    # cần cả Settings.
    frappe.get_cached_doc = lambda *a, **k: _D(
        npp_customer_group="NPP", mt_customer_group="MT", default_company=COMPANY)

    hub = importlib.import_module("ketoan.api.mt_hub")
    hub._company = lambda company=None: COMPANY

    src = _js()
    steps_src = _block(src, "STEPS")
    globals_src = _block(src, "GLOBAL_VIEWS")

    print("=" * 78)
    print("KIỂM ĐIỀU HƯỚNG PORTAL MT (bảng chuỗi ↔ bàn làm việc)")
    print("=" * 78)
    bad = 0

    # ── 1. `get_board` chạy thật, trả đủ chuỗi và đủ khóa ────────────────
    board = hub.get_board()
    chains = board["chains"]
    from ketoan.install import MT_CHAINS

    ok = [c["chain"] for c in chains] and set(c["chain"] for c in chains) == set(MT_CHAINS)
    print(f"  {'✅' if ok else '❌'} bảng chuỗi trả đủ {len(chains)}/{len(MT_CHAINS)} chuỗi "
          f"khai trong install.MT_CHAINS")
    bad += not ok

    row_keys = set(chains[0]) if chains else set()

    # ── 2. Mọi cờ `need` của JS phải có thật trong payload ───────────────
    print("-" * 78)
    needs = set(re.findall(r'need:\s*"(\w+)"', steps_src))
    miss = sorted(n for n in needs if n not in row_keys)
    ok = not miss
    print(f"  {'✅' if ok else '❌'} {len(needs)} cờ năng lực JS dùng để ẩn/hiện bước đều có "
          f"trong `get_board`")
    for n in miss:
        print(f"       └─ `{n}` KHÔNG có -> bước dùng cờ này biến mất khỏi MỌI chuỗi")
    bad += not ok

    # Ba cờ phải luôn tồn tại — chúng quyết định chuỗi hiện những bước nào.
    for flag in ("we_issue_discount", "has_dossier", "can_read_payment"):
        ok = flag in row_keys
        print(f"  {'✅' if ok else '❌'} có cờ `{flag}`")
        bad += not ok

    # ── 3. Mọi khóa đếm việc của JS phải có thật ─────────────────────────
    print("-" * 78)
    counts = set()
    for blob in re.findall(r"count:\s*\[([^\]]*)\]", steps_src):
        counts |= set(re.findall(r'"(\w+)"', blob))
    # thẻ chuỗi trên bảng cũng đọc thẳng nhiều khóa
    card = re.search(r"function chainCard\(c\) \{(.*?)\n\}", src, re.S)
    card_keys = set(re.findall(r"\bc\.(\w+)\b", card.group(1))) if card else set()

    miss = sorted((counts | card_keys) - row_keys)
    ok = not miss
    print(f"  {'✅' if ok else '❌'} {len(counts | card_keys)} khóa JS đọc từ mỗi dòng chuỗi "
          f"đều có thật")
    for k in miss:
        print(f"       └─ `{k}` KHÔNG có -> hiện undefined / đếm hụt việc")
    bad += not ok

    # ── 4. Mọi bước và mọi màn liên chuỗi đều được `loadTab` xử ──────────
    print("-" * 78)
    load = re.search(r"async function loadTab\(container, state\) \{(.*?)\n\}\n", src, re.S)
    body = load.group(1) if load else ""
    step_keys = re.findall(r'\{\s*key:\s*"([\w-]+)"', steps_src)
    global_keys = re.findall(r'\{\s*key:\s*"([\w-]+)"', globals_src)

    # Bước "thanh-toan" là nhánh MẶC ĐỊNH (rơi xuống cuối hàm), không cần if.
    unhandled = [k for k in step_keys
                 if k != "thanh-toan" and ('"%s"' % k) not in body]
    ok = not unhandled
    print(f"  {'✅' if ok else '❌'} {len(step_keys)} bước đều được loadTab xử "
          f"(`thanh-toan` là nhánh mặc định)")
    for k in unhandled:
        print(f"       └─ bước `{k}` có nút bấm mà không nhánh nào xử -> bấm không ra gì")
    bad += bool(unhandled)

    unhandled = [k for k in global_keys if k != "g-but-toan" and ('"%s"' % k) not in body]
    ok = not unhandled
    print(f"  {'✅' if ok else '❌'} {len(global_keys)} màn liên chuỗi đều được loadTab xử "
          f"(`g-but-toan` là nhánh mặc định)")
    for k in unhandled:
        print(f"       └─ `{k}` không nhánh nào xử")
    bad += bool(unhandled)

    # ── 5. Ẩn bước phải ĐÚNG nghiệp vụ, không ẩn bừa ─────────────────────
    print("-" * 78)
    by_chain = {c["chain"]: c for c in chains}

    # Saigon Co.op: chiết khấu 17,75% trừ TẠI NGUỒN và CO.OP xuất hóa đơn.
    # Hiện bước "Chiết khấu mình xuất" cho Co.op là mời kế toán xuất một hóa đơn
    # mình KHÔNG được phép xuất.
    ok = by_chain["Saigon Co.op"]["we_issue_discount"] is False
    print(f"  {'✅' if ok else '❌'} Saigon Co.op KHÔNG hiện bước 'Chiết khấu mình xuất' "
          f"(Co.op xuất hóa đơn, mình không)")
    bad += not ok

    for chain in ("Central Retail", "LOTTE", "Emart", "Mega Market"):
        ok = by_chain[chain]["we_issue_discount"] is True
        print(f"  {'✅' if ok else '❌'} {chain} CÓ bước 'Chiết khấu mình xuất'")
        bad += not ok

    ok = (by_chain["WinCommerce"]["has_dossier"] is True
          and sum(1 for c in chains if c["has_dossier"]) == 1)
    print(f"  {'✅' if ok else '❌'} ĐÚNG MỘT chuỗi có bước 'Hồ sơ nộp' — WinCommerce")
    bad += not ok

    ok = (by_chain["Mega Market"]["can_read_payment"] is False
          and by_chain["LOTTE"]["can_read_payment"] is True)
    print(f"  {'✅' if ok else '❌'} Mega Market báo CHƯA đọc được file thanh toán, "
          f"LOTTE thì đọc được")
    bad += not ok

    # ── 6. Số việc = việc PHẢI LÀM, không phải hiện trạng ────────────────
    print("-" * 78)
    hub_src = open(os.path.join(rc.REPO, "ketoan/api/mt_hub.py"), encoding="utf-8").read()
    todo = re.search(r"todo = \((.*?)\)\n", hub_src, re.S)
    expr = todo.group(1) if todo else ""
    # `advices` (số bảng kê đã nạp) và `debt` (tiền còn nợ) là HIỆN TRẠNG.
    # Cộng chúng vào "việc cần làm" thì con số lúc nào cũng to và mất hết nghĩa.
    leaks = [k for k in ('"n"', "debt", "advices\"") if k in expr]
    ok = not leaks
    print(f"  {'✅' if ok else '❌'} 'việc cần làm' KHÔNG cộng hiện trạng "
          f"(số bảng kê đã nạp / tiền còn nợ) vào")
    bad += not ok

    ok = all(c["todo"] == 0 for c in chains)
    print(f"  {'✅' if ok else '❌'} database rỗng -> mọi chuỗi 0 việc, không chuỗi nào "
          f"báo việc ma")
    bad += not ok

    # ── 7. `get_chain` từ chối chuỗi bịa ─────────────────────────────────
    print("-" * 78)
    try:
        hub.get_chain("Chuỗi Bịa")
        print("  ❌ chuỗi không tồn tại -> KHÔNG dừng")
        bad += 1
    except Exception as e:  # noqa: BLE001
        ok = "Không có chuỗi" in str(e)
        print(f"  {'✅' if ok else '❌'} mở bàn làm việc của chuỗi bịa -> dừng")
        bad += not ok

    desk = hub.get_chain("Saigon Co.op")
    hidden = [s for s in desk["steps"] if s["portal"] and not s["show"]]
    ok = len(hidden) == 1 and hidden[0]["key"] == "chiet_khau" and hidden[0]["reason"]
    print(f"  {'✅' if ok else '❌'} bước bị ẩn của Co.op có kèm LÝ DO, không ẩn câm")
    if hidden:
        print(f"       └─ {hidden[0]['reason'][:70]}…")
    bad += not ok

    print("=" * 78)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — hai tầng khớp hợp đồng, bước ẩn/hiện đúng nghiệp vụ "
          "từng chuỗi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
