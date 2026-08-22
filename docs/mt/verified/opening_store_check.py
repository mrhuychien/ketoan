#!/usr/bin/env python3
"""Kiểm tầng CẤT số dư đầu kỳ + luật tất toán (MT2-K4).

Đây là chỗ nguy hiểm nhất của cả app: một luật ĐỌC làm hóa đơn biến mất khỏi
công nợ. Nên bộ kiểm này soi đúng những cách nó có thể mất tiền:

  1. Nối dòng sang hóa đơn — nhận đúng một ứng viên, và KHÔNG nhận khi còn hai.
  2. Không bao giờ nối chéo chuỗi.
  3. Một hóa đơn chỉ được giữ lại MỘT lần.
  4. Chuỗi CHƯA gán khách -> bản chốt không che hóa đơn nào (rỗng là rỗng).
  5. Chưa có bản chốt nào -> luật trả `0`, không giấu gì.
  6. Bản `Nháp` KHÔNG bật luật.
  7. Chốt khi còn dòng treo -> CHẶN.
  8. Nhập lần hai cho cùng chuỗi -> CHẶN.
  9. Xóa bản đã chốt -> CHẶN.
 10. `debt_carried` tách đúng phần đơn chưa xuất hóa đơn.
 11. Luật đi vào ĐÚNG các màn hình công nợ, và KHÔNG đi vào rổ 'tất cả'.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import base64
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

COMPANY = "HGC"


class _D(dict):
    """dict truy cập được bằng thuộc tính — thay cho `frappe._dict`."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            return None

    def __setattr__(self, k, v):
        self[k] = v


def main():
    rc._stub_frappe()
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
    import frappe

    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.session = _D(user="ketoan@hgc.vn")
    frappe.db.table_exists = lambda dt: True
    frappe.db.has_column = lambda dt, col: True
    frappe.db.commit = lambda *a, **kw: None
    frappe.db.savepoint = lambda *a, **kw: None
    frappe.db.rollback = lambda *a, **kw: None

    st = importlib.import_module("ketoan.api.mt_opening_store")
    mt = importlib.import_module("ketoan.api.mt")
    ob = importlib.import_module(
        "ketoan.mt.doctype.mt_opening_balance.mt_opening_balance")
    st._company = lambda company=None: COMPANY
    mt._company = lambda company=None: COMPANY

    print("=" * 82)
    print("KIỂM CẤT SỐ DƯ ĐẦU KỲ + LUẬT TẤT TOÁN")
    print("=" * 82)
    bad = 0

    # ── 1. Nối dòng: nhận một, từ chối hai ───────────────────────────────
    def idx_of(invoices):
        from collections import defaultdict
        by_no, info = defaultdict(list), {}
        for si in invoices:
            info[si["name"]] = _D(si)
            by_no[si["no"]].append(si["name"])
        return {"by_no": by_no, "by_exact": {}, "by_key": {}, "info": info}

    SI_A = {"name": "SI-A", "no": "3333", "customer": "KH-1", "posting_date": "2026-06-01",
            "grand_total": 1000.0, "snap_dead": 0, "snap_deleted": 0}
    SI_B = {"name": "SI-B", "no": "3333", "customer": "KH-2", "posting_date": "2026-07-01",
            "grand_total": 2000.0, "snap_dead": 0, "snap_deleted": 0}
    SI_X = {"name": "SI-X", "no": "3333", "customer": "KH-9", "posting_date": "2026-06-01",
            "grand_total": 1000.0, "snap_dead": 0, "snap_deleted": 0}

    cus_chain = {"KH-1": "AEON", "KH-2": "AEON", "KH-9": "LOTTE"}
    allowed = {"KH-1", "KH-2"}

    row = {"inv_no": "00003333", "inv_date": "2026-06-01", "gross": 1000.0}
    si, method, conf = st._resolve_row(row, idx_of([SI_A]), "AEON", cus_chain, allowed)
    ok = si == "SI-A" and conf == st.CONF_REVIEW
    print(f"  {'✅' if ok else '❌'} một ứng viên trong chuỗi -> nối `SI-A`, để "
          f"'{conf}' (máy đoán, người chốt)")
    bad += not ok

    si, method, conf = st._resolve_row(row, idx_of([SI_A, SI_B]), "AEON", cus_chain, allowed)
    ok = si == "SI-A" and method == "so_ngay"
    print(f"  {'✅' if ok else '❌'} hai hóa đơn trùng số -> thu hẹp bằng NGÀY, ra `{si}` "
          f"({method})")
    bad += not ok

    row2 = {"inv_no": "00003333", "inv_date": None, "gross": 0}
    si, method, conf = st._resolve_row(row2, idx_of([SI_A, SI_B]), "AEON", cus_chain, allowed)
    ok = si is None and method.startswith("con_2")
    print(f"  {'✅' if ok else '❌'} hai ứng viên, không ngày không tiền -> KHÔNG nối "
          f"({method}) — thà treo còn hơn giữ nhầm")
    bad += not ok

    # ── 2. Không nối chéo chuỗi ─────────────────────────────────────────
    print("-" * 82)
    si, method, conf = st._resolve_row(row, idx_of([SI_X]), "AEON", cus_chain, allowed)
    ok = si is None and method == "so_co_nhung_khac_chuoi" and conf == st.CONF_NONE
    print(f"  {'✅' if ok else '❌'} số trùng nhưng hóa đơn của chuỗi LOTTE -> KHÔNG nối "
          f"({method})")
    bad += not ok

    # ── 2b. Hóa đơn ĐÃ ĐIỀU CHỈNH vẫn phải nối được ─────────────────────
    #
    # Quy trình thật: giao hàng -> hàng móp/lỗi -> điều chỉnh hóa đơn MISA ->
    # trả lại trên ERPNext. `misa_sync._mark_superseded` đặt hóa đơn GỐC thành
    # 'Đã thay thế'. Ở BẢNG KÊ THANH TOÁN, loại nó là đúng. Ở SỐ DƯ ĐẦU KỲ thì
    # loại nó là để chính khoản nợ đó biến mất lúc chốt.
    dead = dict(SI_A, name="SI-D", snap_dead=1)
    si, method, conf = st._resolve_row(row, idx_of([dead]), "AEON", cus_chain, allowed)
    ok = si == "SI-D" and method.endswith("_da_dieu_chinh")
    print(f"  {'✅' if ok else '❌'} hóa đơn đã điều chỉnh VẪN nối được ({method}) — loại "
          f"nó là để khoản nợ đó biến mất khi chốt")
    bad += not ok

    live = dict(SI_A, name="SI-L")
    si, method, _c = st._resolve_row(row, idx_of([dead, live]), "AEON", cus_chain, allowed)
    ok = si == "SI-L" and not method.endswith("_da_dieu_chinh")
    print(f"  {'✅' if ok else '❌'} có cả hóa đơn còn hiệu lực -> ưu tiên nó (`{si}`), hóa "
          f"đơn đã điều chỉnh chỉ là phương án cuối")
    bad += not ok

    si, method, _c = st._resolve_row(
        row, idx_of([dict(SI_X, snap_dead=1)]), "AEON", cus_chain, allowed)
    ok = si is None and method == "so_co_nhung_khac_chuoi"
    print(f"  {'✅' if ok else '❌'} KHÁC CHUỖI thì vẫn loại hẳn — nới cho 'đã điều chỉnh' "
          f"không được nới luôn cho nối chéo chuỗi")
    bad += not ok

    # ── 2c. So tiền: thử cả TRƯỚC và SAU khi trả lại ────────────────────
    # File công nợ của chuỗi có thể ghi số sau điều chỉnh, còn ERPNext giữ số
    # gốc. Chỉ so một mốc là trượt đúng nhóm hóa đơn dễ sai tiền nhất.
    part = dict(SI_A, name="SI-P", grand_total=1000.0, returned=200.0)
    other = dict(SI_A, name="SI-O", grand_total=5000.0, posting_date="2026-06-01")
    r_after = {"inv_no": "00003333", "inv_date": "2026-06-01", "gross": 800.0}
    si, method, _c = st._resolve_row(r_after, idx_of([part, other]), "AEON",
                                     cus_chain, allowed)
    ok = si == "SI-P" and method.startswith("so_ngay_tien")
    print(f"  {'✅' if ok else '❌'} file ghi 800 (sau trả lại 200) mà hóa đơn ghi 1.000 "
          f"-> vẫn nối đúng `{si}`")
    bad += not ok

    r_before = {"inv_no": "00003333", "inv_date": "2026-06-01", "gross": 1000.0}
    si, _m, _c = st._resolve_row(r_before, idx_of([part, other]), "AEON",
                                 cus_chain, allowed)
    ok = si == "SI-P"
    print(f"  {'✅' if ok else '❌'} file ghi 1.000 (số gốc) -> cũng nối đúng `{si}`")
    bad += not ok

    # ── 2d. Ô TÌM ỨNG VIÊN phải tìm đúng chỗ ────────────────────────────
    #
    # Lỗi đã gặp trên site thật: ô tìm lấy số hóa đơn của dòng (`00005449`) rồi
    # so với `si.name LIKE`. `si.name` là mã chứng từ ERPNext
    # (`ACC-SINV-2026-00123`), KHÔNG BAO GIỜ chứa số hóa đơn -> màn hình luôn ra
    # "Không có hóa đơn nào khớp" với MỌI dòng treo. Cả đường nối tay chết, mà
    # nhìn thì tưởng đúng là không có hóa đơn nào.
    print("-" * 82)
    src_st = open(os.path.join(rc.REPO, "ketoan/api/mt_opening_store.py"),
                  encoding="utf-8").read()
    body = re.split(r"\n(?=\S)", src_st.split("def search_invoices")[1])[0]

    ok = "SI_NO_FIELD" in body
    print(f"  {'✅' if ok else '❌'} ô tìm ứng viên tìm theo SỐ HÓA ĐƠN "
          f"(`{mt.SI_NO_FIELD}`), không chỉ theo mã chứng từ ERPNext")
    bad += not ok

    ok = "si.name LIKE %(kw)s" in body and 'kw = cstr(q or "").strip()' in body \
        and 'or cstr(l.inv_no' not in body
    print(f"  {'✅' if ok else '❌'} KHÔNG tự nhồi số hóa đơn vào ô tìm rồi lọc cứng — để "
          f"trống thì liệt kê ứng viên, không trả màn hình rỗng")
    bad += not ok

    ok = "_amount_hits" in body and '"trùng số hóa đơn"' in body
    print(f"  {'✅' if ok else '❌'} nói rõ VÌ SAO từng ứng viên được gợi ý (trùng số / "
          f"trùng tiền / trùng ngày)")
    bad += not ok

    ok = "rt.returned" in body and "net_due" in body
    print(f"  {'✅' if ok else '❌'} mỗi ứng viên hiện cả phần ĐÃ TRẢ LẠI và số CÒN PHẢI "
          f"THU — đúng ca 1 hóa đơn MISA ↔ 2 chứng từ ERPNext")
    bad += not ok

    ok = "Nối thêm phiếu trả hàng nữa là trừ hai lần" in body
    print(f"  {'✅' if ok else '❌'} nói thẳng chỉ chọn HÓA ĐƠN GỐC, không nối phiếu trả "
          f"hàng — nối cả hai là trừ hai lần")
    bad += not ok

    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"),
              encoding="utf-8").read()
    ok = "r.net_due" in js and "r.why" in js
    print(f"  {'✅' if ok else '❌'} màn hình có hiện hai thứ đó, không chỉ nằm trong payload")
    bad += not ok

    # ── 3. Một hóa đơn chỉ giữ lại MỘT lần ──────────────────────────────
    print("-" * 82)
    mt._customer_chain_map = lambda: (cus_chain, {})
    mt.chain_customers = lambda ch: sorted(c for c, x in cus_chain.items() if x == ch)
    st.chain_customers = mt.chain_customers
    st._si_index = lambda company, dates: idx_of([SI_A])

    rows = [
        {"kind": ob.KIND_IN_ERP, "inv_no": "00003333", "inv_date": "2026-06-01",
         "gross": 1000.0, "source_row": 10},
        {"kind": ob.KIND_IN_ERP, "inv_no": "00003333", "inv_date": "2026-06-01",
         "gross": 1000.0, "source_row": 11},
    ]
    out, _idx = st._resolve(rows, "AEON", COMPANY)
    ok = out[0]["sales_invoice"] == "SI-A" and out[1]["sales_invoice"] is None \
        and "trung_hoa_don" in out[1]["match_method"]
    print(f"  {'✅' if ok else '❌'} hai dòng cùng trỏ một hóa đơn -> dòng sau KHÔNG nối, "
          f"nói rõ ({out[1]['match_method']})")
    bad += not ok

    # ── 4/5/6. Luật tất toán: nguồn duy nhất ────────────────────────────
    print("-" * 82)
    finals = []
    ob.finalized_for = lambda company: list(finals)
    mt.finalized_for = ob.finalized_for

    p = {}
    expr = mt.opening_settled_expr(p, COMPANY)
    ok = expr == "0"
    print(f"  {'✅' if ok else '❌'} chưa có bản chốt nào -> luật trả `{expr}`, không giấu "
          f"hóa đơn nào")
    bad += not ok

    finals.append(_D(name="OB-1", chain="AEON", cutover_date="2026-07-31"))
    p = {}
    expr = mt.opening_settled_expr(p, COMPANY)
    ok = ("obd0" in p and p["obd0"] == "2026-07-31" and p["obp0"] == "OB-1"
          and "KH-1" in p.values() and "KH-2" in p.values()
          and "MT Opening Invoice" in expr and "NOT EXISTS" in expr)
    print(f"  {'✅' if ok else '❌'} có bản chốt -> điều kiện dựng bằng THAM SỐ ràng buộc "
          f"({len([k for k in p if k.startswith('ob0c')])} khách của chuỗi, mốc {p.get('obd0')})")
    bad += not ok

    finals[:] = [_D(name="OB-2", chain="Emart", cutover_date="2026-07-31")]
    p = {}
    expr = mt.opening_settled_expr(p, COMPANY)
    ok = "1 = 0" in expr
    print(f"  {'✅' if ok else '❌'} chuỗi đã chốt mà CHƯA gán khách nào -> `1 = 0`, bản "
          f"chốt không che hóa đơn nào (rỗng là rỗng)")
    bad += not ok

    # Bản Nháp không bao giờ lọt vào `finalized_for` — kiểm ngay câu SQL của nó.
    src = open(os.path.join(rc.REPO, "ketoan/mt/doctype/mt_opening_balance",
                            "mt_opening_balance.py"), encoding="utf-8").read()
    body = src[src.index("def finalized_for"):]
    ok = "status = %(final)s" in body and "STATUS_FINAL" in body
    print(f"  {'✅' if ok else '❌'} luật CHỈ đọc bản '{ob.STATUS_FINAL}' — bản "
          f"'{ob.STATUS_DRAFT}' không bật gì")
    bad += not ok

    # ── 7. Luật đi vào đúng màn hình ────────────────────────────────────
    print("-" * 82)
    finals[:] = [_D(name="OB-1", chain="AEON", cutover_date="2026-07-31")]
    p = {}
    w_unpaid = mt._bucket_where("chua_thanh_toan", p, COMPANY)
    w_all = mt._bucket_where("tat_ca", {}, COMPANY)
    w_paid = mt._bucket_where("da_thanh_toan", {}, COMPANY)
    ok = "MT Opening Invoice" in w_unpaid and "MT Opening Invoice" not in w_all \
        and "MT Opening Invoice" not in w_paid
    print(f"  {'✅' if ok else '❌'} rổ 'chưa thanh toán' áp luật; rổ 'tất cả' và 'đã "
          f"thanh toán' KHÔNG — vẫn tra lại được hóa đơn cũ")
    bad += not ok

    dbt = open(os.path.join(rc.REPO, "ketoan/api/mt_debt.py"), encoding="utf-8").read()
    ok = "opening_open_clause" in dbt
    print(f"  {'✅' if ok else '❌'} màn hình Công nợ đến hạn gọi CÙNG một hàm luật "
          f"(`opening_open_clause`), không dựng lại điều kiện riêng")
    bad += not ok

    mtsrc = open(os.path.join(rc.REPO, "ketoan/api/mt.py"), encoding="utf-8").read()
    n_def = len(re.findall(r"^def opening_settled_expr", mtsrc, re.M))
    n_sql = len(re.findall(r"tabMT Opening Invoice", mtsrc))
    ok = n_def == 1 and n_sql == 1
    print(f"  {'✅' if ok else '❌'} luật diễn đạt ĐÚNG MỘT LẦN trong mt.py "
          f"({n_def} định nghĩa, {n_sql} câu SQL nhắc bảng)")
    bad += not ok

    ok = bool(re.search(r"AS outstanding", mtsrc)) and \
        len(re.findall(r"NOT \{settled\}", mtsrc)) == 2
    print(f"  {'✅' if ok else '❌'} bảng công nợ theo KHÁCH cũng áp luật ở cả hai cột nợ "
          f"(`outstanding`, `unpaid_count`) — hai màn hình không ra hai số khác nhau")
    bad += not ok

    # Câu SQL thật sự dựng được: f-string ghép đúng, ngoặc cân, tham số ràng buộc.
    # Đây là phép duy nhất chứng minh mệnh đề không vỡ khi nhét vào truy vấn.
    caught = []

    def _spy(q, v=None, **kw):
        caught.append(q)
        return [_D(cnt=0, amount=0, remaining=0, collected=0, pending_review=0,
                   n=0, row_kind=None)]

    keep_sql, keep_group = frappe.db.sql, mt.channel_group_clause
    frappe.db.sql = _spy
    mt.channel_group_clause = lambda *a, **kw: "1=1"
    mt._require_tables = lambda: None
    try:
        mt.get_overview(company=COMPANY, from_date="2026-01-01", to_date="2026-12-31")
    except Exception:                                              # noqa: BLE001, S110
        pass                     # chỉ cần các câu SQL đã dựng xong
    frappe.db.sql, mt.channel_group_clause = keep_sql, keep_group

    hit = [" ".join(x.split()) for x in caught if "MT Opening Invoice" in x]
    ok = (len(hit) == 1 and hit[0].count("(") == hit[0].count(")")
          and "%(obd0)s" in hit[0] and "%(ob0c0)s" in hit[0])
    print(f"  {'✅' if ok else '❌'} câu SQL của Tổng quan dựng được: đúng {len(hit)}/"
          f"{len(caught)} câu mang luật, ngoặc cân, mọi giá trị đi qua tham số ràng buộc")
    bad += not ok

    # ── 8. Chặn của DocType ─────────────────────────────────────────────
    print("-" * 82)

    # Document giả LÀ controller thật + dict truy cập bằng thuộc tính. Kế thừa
    # thật chứ không gán `__class__`: gán `__class__` giữa hai layout khác nhau
    # cho ra một vật thể nửa vời, và khi đó phép kiểm hỏng vì lý do KHÁC với thứ
    # đang muốn kiểm.
    class _Doc(ob.MTOpeningBalance, _D):
        pass

    def mk(**kw):
        base = dict(company=COMPANY, chain="AEON", status=ob.STATUS_DRAFT,
                    cutover_date="2026-07-31", golive_date="2026-05-01",
                    name="OB-1", opening_debt_gross=1000.0, lines=[], deductions=[])
        base.update(kw)
        return _Doc(**base)

    # nhập lần hai
    frappe.db.sql = lambda q, v=None, **kw: [["OB-CU"]] if "MT Opening Balance" in q else []
    doc = mk()
    try:
        doc._check_one_per_chain()
        print("  ❌ chuỗi đã có bản số dư -> VẪN cho nhập lần hai")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "MỘT LẦN" in str(e) and "cộng đôi" in str(e)
        print(f"  {'✅' if ok else '❌'} chuỗi đã có bản số dư -> chặn nhập lần hai "
              f"(cộng đôi ~5 tỷ)")
        bad += not ok

    frappe.db.sql = lambda q, v=None, **kw: []

    # ngày chốt sớm hơn go-live
    doc = mk(cutover_date="2026-04-01")
    try:
        doc._check_dates()
        print("  ❌ ngày chốt < ngày go-live -> KHÔNG chặn")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "sớm hơn" in str(e)
        print(f"  {'✅' if ok else '❌'} ngày chốt sớm hơn ngày ERPNext có dữ liệu -> chặn")
        bad += not ok

    # ── 9. Chốt khi còn dòng treo -> chặn ───────────────────────────────
    print("-" * 82)
    def L(**kw):
        base = dict(idx=1, sales_invoice=None, resolution=None, remaining=0.0,
                    inv_no=None, kind=ob.KIND_IN_ERP)
        base.update(kw)
        return _D(**base)
    doc = mk(status=ob.STATUS_FINAL, lines=[
        L(idx=1, kind=ob.KIND_IN_ERP, inv_no="00003333", remaining=1000.0),
    ])
    try:
        doc.validate()
        print("  ❌ còn dòng treo -> VẪN cho chốt")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "chưa nối được hóa đơn" in str(e) and "00003333" in str(e)
        print(f"  {'✅' if ok else '❌'} chốt khi còn dòng chưa nối -> chặn, nêu đích danh "
              f"số hóa đơn treo")
        bad += not ok

    doc = mk(status=ob.STATUS_FINAL, lines=[
        L(idx=1, kind=ob.KIND_IN_ERP, inv_no="00003333", remaining=1000.0,
          resolution=ob.RESOLUTION_SKIP),
    ])
    doc.validate()
    ok = doc.n_unmatched == 0
    print(f"  {'✅' if ok else '❌'} người đánh dấu '{ob.RESOLUTION_SKIP}' -> chốt được, "
          f"và dòng đó KHÔNG giữ hóa đơn nào lại")
    bad += not ok

    doc = mk(status=ob.STATUS_FINAL, lines=[
        L(idx=1, kind=ob.KIND_IN_ERP, remaining=100.0, sales_invoice="SI-A"),
        L(idx=2, kind=ob.KIND_IN_ERP, remaining=200.0, sales_invoice="SI-A"),
    ])
    try:
        doc.validate()
        print("  ❌ hai dòng nối cùng một hóa đơn -> VẪN cho chốt")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "SI-A" in str(e) and "MỘT lần" in str(e)
        print(f"  {'✅' if ok else '❌'} hai dòng nối cùng hóa đơn -> chặn chốt")
        bad += not ok

    # ── 10. Xóa bản đã chốt -> chặn ─────────────────────────────────────
    print("-" * 82)
    doc = mk(status=ob.STATUS_FINAL)
    try:
        doc.on_trash()
        print("  ❌ xóa bản đã chốt -> KHÔNG chặn")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "đã CHỐT" in str(e)
        print(f"  {'✅' if ok else '❌'} xóa bản đã chốt -> chặn (mọi hóa đơn quay lại rổ "
              f"nợ cùng lúc)")
        bad += not ok

    doc = mk(status=ob.STATUS_DRAFT)
    doc.on_trash()
    print("  ✅ xóa bản còn Nháp -> cho phép")

    # ── 11. Tách đơn chưa xuất hóa đơn khỏi công nợ mang sang ───────────
    print("-" * 82)
    doc = mk(opening_debt_gross=5_059_095_894.0, lines=[
        L(idx=1, kind=ob.KIND_NO_INVOICE, remaining=46_665_180.0),
        L(idx=2, kind=ob.KIND_IN_ERP, remaining=1000.0, sales_invoice="SI-A"),
    ], deductions=[_D(remaining=183_968_726.0)])
    doc.validate()
    ok = (doc.opening_debt == 4_875_127_168.0
          and doc.no_invoice_amount == 46_665_180.0
          and doc.debt_carried == 4_828_461_988.0)
    print(f"  {'✅' if ok else '❌'} nợ gộp {doc.opening_debt_gross:,.0f} − ghi giảm "
          f"{doc.deduction_open:,.0f} = {doc.opening_debt:,.0f}")
    print(f"  {'✅' if ok else '❌'} − đơn chưa xuất HĐ {doc.no_invoice_amount:,.0f} "
          f"-> MANG SANG {doc.debt_carried:,.0f}")
    bad += (not ok) * 2

    # ── 12. Đọc file thật -> đếm dòng khớp con số đã công bố ────────────
    print("-" * 82)
    mo = importlib.import_module("ketoan.api.mt_opening")
    D = os.path.join(rc.REPO, "docs/mt/samples/congno")
    tot_open = 0
    if os.path.isdir(D):
        for f in sorted(os.listdir(D)):
            raw = open(os.path.join(D, f), "rb").read()
            res = mo.read_opening(base64.b64encode(raw).decode(), golive="2026-05-01")
            tot_open += len(res["open_rows"])
        ok = tot_open == 1167
        print(f"  {'✅' if ok else '❌'} bảy file thật ra {tot_open} dòng CÒN NỢ "
              f"(đã công bố: 1.167)")
        bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — nối dòng không nhận bừa, luật tất toán chỉ có MỘT nguồn và chỉ "
          "chạy khi đã chốt, mọi đường mất tiền đều bị chặn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
