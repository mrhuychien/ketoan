#!/usr/bin/env python3
"""Kiểm CẦU NỐI SỔ CÁI 131 ↔ RỔ HÓA ĐƠN MT.

════════════════════════════════════════════════════════════════════════════
CHỐT CHẶN SỐ MỘT: BỐN KHOẢN PHẢI CỘNG LẠI ĐÚNG CHỖ LỆCH
════════════════════════════════════════════════════════════════════════════

In ra "lệch 412 triệu" là không dùng được — kế toán không biết 412 triệu đó nằm
ở đâu nên hoặc bỏ qua, hoặc sửa bừa một bên cho khớp. Giá trị của màn hình nằm
HẾT ở chỗ cầu nối khép kín:

    Sổ cái 131 (C) − Rổ hóa đơn (B)
      = (1) sổ cái lệch so với chính hóa đơn   C_hd − Σ(gộp − trả lại)
      + (2) hóa đơn không còn trong rổ         Σ_tất cả − Σ_còn nợ
      + (3) tiền bảng kê đã trừ khỏi rổ        Σ đã trả (trên HĐ còn nợ)
      + (4) bút toán ghi thẳng vào 131         C_khác

Đẳng thức này phải đúng VỀ ĐẠI SỐ với MỌI bộ số, kể cả số âm, số 0, số rất lớn.
Còn dư một đồng là LỖI CODE, không phải "sai số cho phép". Bộ kiểm quét một dải
hình dạng rộng chứ không thử một bộ số đẹp rồi kết luận.

════════════════════════════════════════════════════════════════════════════
CHỐT CHẶN SỐ HAI: CÙNG MỘT ĐỊNH NGHĨA "CÒN NỢ"
════════════════════════════════════════════════════════════════════════════

Vế `B` ở đây phải là ĐÚNG con số mà `mt_debt` hiện trên thẻ hai cuốn sổ. Lệch
một chữ trong mệnh đề "còn nợ" là hai màn hình nói về hai tập hóa đơn khác
nhau, và cầu nối khép kín một cách vô nghĩa.

════════════════════════════════════════════════════════════════════════════
CHỐT CHẶN SỐ BA: NGUYÊN NHÂN ≠ PHÂN RÃ
════════════════════════════════════════════════════════════════════════════

Danh sách nguyên nhân là NGHI CAN có số, chồng lấn nhau, KHÔNG cộng lại thành
chỗ lệch. Trộn nó vào cầu nối là mời người đọc cộng nhầm.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import importlib
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: True
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    gb = importlib.import_module("ketoan.api.mt_gl_bridge")

    print("=" * 82)
    print("KIỂM CẦU NỐI SỔ CÁI 131 ↔ RỔ HÓA ĐƠN MT")
    print("=" * 82)
    bad = 0

    # ── 1. ĐẲNG THỨC KHÉP KÍN TRÊN MỌI HÌNH DẠNG ────────────────────────
    #
    # Quét tổ hợp chứ không thử một bộ số đẹp. Có cả số âm (khách trả trước,
    # ghi giảm vượt), số 0 (chuỗi chưa phát sinh) và số rất lớn (tràn float).
    VALS = [0.0, 1.0, -1.0, 1234567.89, -987654.32, 4_875_610_561.0, 0.01]
    gb.chain_customers = lambda chain: ["K1"]
    gb._causes = lambda *a, **k: []

    n_case, worst = 0, 0.0
    for si, other, all_net, open_net, open_paid in itertools.product(VALS, repeat=5):
        gb.gl_split = (lambda s, o: (lambda company, customers, as_of: {
            "si": s, "other": o, "total": round(s + o, 2)}))(si, other)
        gb._invoice_side = (lambda a, o, p: (lambda company, customers, as_of: {
            "all_net": a, "open_net": o, "open_paid": p, "open_count": 3}))(
                all_net, open_net, open_paid)
        r = gb.build("HGC", "WinCommerce", "2026-08-28")
        n_case += 1
        # TỰ CỘNG LẠI, không hỏi cờ `balanced` và cũng không dùng `residual`
        # do chính module trả về: cả hai đều là thứ code có thể nói dối. Phép
        # kiểm phải tính độc lập từ `items` và `diff`.
        resid = round(r["diff"] - sum(i["amount"] for i in r["items"]), 2)
        worst = max(worst, abs(resid))
        if abs(resid) > gb.EPS:
            r = dict(r, residual=resid)
            print(f"     ❌ si={si} other={other} all={all_net} open={open_net} "
                  f"paid={open_paid} -> dư {r['residual']}")
            bad += 1
            break
    ok = bad == 0
    print(f"  {'✅' if ok else '❌'} {n_case} tổ hợp (âm · 0 · tỷ đồng · lẻ xu): bốn khoản cộng "
          f"lại ĐÚNG chỗ lệch, dư lớn nhất {worst}")

    # ── 2. Từng khoản đúng NGHĨA của nó, không chỉ đúng tổng ────────────
    #
    # Đẳng thức khép kín vẫn có thể đúng khi hai khoản bị hoán chỗ cho nhau.
    # Nên phải kiểm từng khoản trên một bộ số mà mỗi khoản ra một giá trị khác.
    print("-" * 82)
    gb.gl_split = lambda company, customers, as_of: {
        "si": 1000.0, "other": -300.0, "total": 700.0}
    gb._invoice_side = lambda company, customers, as_of: {
        "all_net": 900.0, "open_net": 500.0, "open_paid": 120.0, "open_count": 2}
    r = gb.build("HGC", "WinCommerce", "2026-08-28")
    want = {
        "so_cai_ngoai_hoa_don": 100.0,     # 1000 − 900
        "hoa_don_ngoai_ro": 400.0,         # 900 − 500
        "tien_bang_ke_da_tru": 120.0,      # đã trả trên HĐ còn nợ
        "but_toan_vao_131": -300.0,        # phần không từ hóa đơn
    }
    got = {i["key"]: i["amount"] for i in r["items"]}
    ok = got == want
    print(f"  {'✅' if ok else '❌'} từng khoản đúng nghĩa (không phải chỉ đúng tổng): {got}")
    bad += not ok

    ok = r["basket_open"] == 380.0 and r["gl_total"] == 700.0 and r["diff"] == 320.0
    print(f"  {'✅' if ok else '❌'} rổ còn nợ {r['basket_open']} · sổ cái {r['gl_total']} · "
          f"lệch {r['diff']} (= 500 − 120 và 1000 − 300)")
    bad += not ok

    # Cờ `balanced` phải SUY TỪ `residual`, không được là hằng.
    #
    # Bộ kiểm tự cộng lại nên hardcode `balanced: True` không lừa được nó — NHƯNG
    # MÀN HÌNH thì đọc đúng cờ đó để cảnh báo "cầu nối còn dư, đừng dùng con số".
    # Cờ nói dối là cảnh báo im lặng biến mất đúng lúc cần nhất.
    bsrc = rc.code_only(os.path.join(rc.REPO, "ketoan/api/mt_gl_bridge.py"))
    ok = '"balanced": abs(residual)' in bsrc
    print(f"  {'✅' if ok else '❌'} cờ `balanced` suy từ `residual`, không phải hằng — màn hình "
          f"dựa vào nó để bảo người dùng đừng tin con số")
    bad += not ok

    ok = round(sum(got.values()), 2) == r["diff"]
    print(f"  {'✅' if ok else '❌'} và bốn khoản cộng lại = chỗ lệch ({sum(got.values())} = "
          f"{r['diff']})")
    bad += not ok

    # ── 3. CÙNG định nghĩa "còn nợ" với `mt_debt` ────────────────────────
    #
    # Phép kiểm VĂN BẢN, cố ý: dữ liệu giả không bao giờ lộ ra chuyện hai câu
    # SQL dùng hai mệnh đề khác nhau, mà đó là cách hỏng nguy hiểm nhất — cầu
    # nối vẫn khép kín, chỉ là khép kín quanh một tập hóa đơn KHÁC.
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/mt_gl_bridge.py"), encoding="utf-8").read()
    dsrc = open(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"), encoding="utf-8").read()
    # ĐẾM CODE, KHÔNG ĐẾM VĂN — xem `regression_check.code_only`.
    body = rc.code_only(os.path.join(rc.REPO, "ketoan/api/mt_gl_bridge.py"))
    core = "(IFNULL(p.paid, 0) - IFNULL(p.clawed_back, 0))"
    ok = core in src and core in dsrc
    print(f"  {'✅' if ok else '❌'} công thức 'đã trả' giống hệt `mt_debt` (`paid − clawed_back`)")
    bad += not ok

    # Soi TRONG mệnh đề "còn nợ", không chỉ dò tên hàm trong file.
    #
    # Bản đầu chỉ khẳng định chuỗi `opening_open_clause` có mặt — và nó VẪN ĐẠT
    # khi mệnh đề đã bị gỡ khỏi câu SQL, vì dòng gán biến vẫn còn. Dò tên hàm
    # chỉ chứng minh hàm ĐƯỢC GỌI, không chứng minh kết quả ĐƯỢC DÙNG.
    is_open = src.split("is_open = (")[1].split(")\n", 1)[0]
    ok = "{opening}" in is_open and "opening_open_clause" in dsrc
    print(f"  {'✅' if ok else '❌'} mệnh đề 'còn nợ' CÓ áp luật tất toán số dư đầu kỳ — không áp "
          f"thì rổ ở đây to hơn rổ trên thẻ hai cuốn sổ")
    bad += not ok

    ok = "_mt_clause" in src and "chain_customers" in src
    print(f"  {'✅' if ok else '❌'} cùng quy tắc 'khách nào thuộc chuỗi nào' và 'khách nào là MT'")
    bad += not ok

    ok = "outstanding_amount" not in body
    print(f"  {'✅' if ok else '❌'} KHÔNG dùng `outstanding_amount` — kênh MT không tạo Payment "
          f"Entry nên nó luôn bằng grand_total")
    bad += not ok

    # ── 4. KHÔNG quy tiền về từng hóa đơn ───────────────────────────────
    #
    # `mt_je` cố ý không gắn `reference_name`, nên `against_voucher` rỗng. Gộp
    # theo nó là dồn hết vào một rổ vô nghĩa; đoán FIFO là chỉ tay vào một hóa
    # đơn đã thu đủ mà bảo "còn nợ".
    print("-" * 82)
    ok = "against_voucher" not in body
    print(f"  {'✅' if ok else '❌'} không gộp theo `against_voucher` — bút toán MT ghi TỔNG, "
          f"không gắn reference, nên cột đó rỗng")
    bad += not ok

    jsrc = open(os.path.join(rc.REPO, "ketoan/api/mt_je.py"), encoding="utf-8").read()
    ok = "KHÔNG gắn `reference_type`/`reference_name`" in jsrc
    print(f"  {'✅' if ok else '❌'} và tiền đề đó VẪN đúng trong `mt_je` — nếu sau này bút toán "
          f"có gắn reference thì cầu nối này nên dựng lại ở mức từng hóa đơn")
    bad += not ok

    # ── 5. NGUYÊN NHÂN tách khỏi CẦU NỐI ────────────────────────────────
    print("-" * 82)
    me = importlib.import_module("ketoan.api.mt_gl_bridge")
    ok = "causes" in r and "items" in r and r["causes"] is not None
    print(f"  {'✅' if ok else '❌'} nguyên nhân trả về ở khóa RIÊNG (`causes`), không trộn vào "
          f"`items` — trộn là mời người đọc cộng nhầm")
    bad += not ok

    seg = src.split("def _causes")[1].split("\ndef ")[0]
    ok = "KHÔNG phải phân rã" in seg
    print(f"  {'✅' if ok else '❌'} và code nói rõ nó KHÔNG phải phân rã của chỗ lệch")
    bad += not ok

    ok = "je_state" in seg and "Đã duyệt đủ" in seg
    print(f"  {'✅' if ok else '❌'} nguyên nhân số một ĐO ĐƯỢC: tiền bảng kê đã khớp mà bút toán "
          f"chưa ghi sổ đủ (`je_state`)")
    bad += not ok

    # ── 6. Guard + chỉ đọc ──────────────────────────────────────────────
    print("-" * 82)
    ok = "guard_mt()" in body and "_require_tables()" in body
    print(f"  {'✅' if ok else '❌'} whitelisted method có guard")
    bad += not ok

    for verb in ("db_set", ".save(", ".insert(", ".submit(", "db.set_value"):
        if verb in body:
            print(f"  ❌ module CHỈ ĐỌC mà có `{verb}`")
            bad += 1
            break
    else:
        print(f"  ✅ module CHỈ ĐỌC — không ghi field, không sinh chứng từ")

    # ── 7. Giao diện ────────────────────────────────────────────────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    ok = "loadChainGl" in js and "mtGlBridge" in js
    print(f"  {'✅' if ok else '❌'} bàn làm việc của chuỗi có đọc sổ cái 131")

    bad += not ok
    # Nạp SAU và KHÔNG chặn: quét bảng GL Entry nặng hơn hẳn phần còn lại.
    #
    # Soi TRONG hàm `paint` — bản đầu cắt theo lần `await loadTab(...)` CUỐI
    # CÙNG của cả file và rơi trúng một modal ở tận cuối, tức đo nhầm chỗ.
    ok = rc.js_calls(js, "paint", "loadChainGl") and "await loadChainGl" not in js
    print(f"  {'✅' if ok else '❌'} và nạp SAU, KHÔNG `await` — `await` nó là bắt cả bàn làm "
          f"việc chờ một truy vấn sổ cái")
    bad += not ok

    ok = "glBridgeCard" in js and "Cộng lại = chỗ lệch" in js
    print(f"  {'✅' if ok else '❌'} in ra CẦU NỐI kèm dòng tổng, không chỉ in con số lệch")
    bad += not ok

    ok = "không phải phân rã của chỗ lệch" in js or "không</b> cộng lại thành" in js
    print(f"  {'✅' if ok else '❌'} và nói rõ nguyên nhân KHÔNG cộng lại thành chỗ lệch")
    bad += not ok

    ok = "r.balanced" in js and "lỗi code" in js
    print(f"  {'✅' if ok else '❌'} cầu nối dư một đồng -> nói thẳng là LỖI CODE và bảo đừng "
          f"dùng con số, thay vì im lặng hiện số sai")
    bad += not ok

    ok = 'data-step="${x.step}"' in js
    print(f"  {'✅' if ok else '❌'} mỗi nguyên nhân có nút ĐI XỬ LÝ — nêu nguyên nhân mà không "
          f"mở ra được chỗ xử lý thì chỉ là một lời than")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — cầu nối khép kín trên mọi hình dạng số, cùng định nghĩa 'còn nợ' "
          "với thẻ hai cuốn sổ, nguyên nhân tách khỏi phân rã")
    return 0


if __name__ == "__main__":
    sys.exit(main())
