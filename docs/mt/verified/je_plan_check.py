"""Kiểm tầng SINH BÚT TOÁN (`ketoan/api/mt_je.py`) trên dữ liệu bảng kê thật.

    python3 docs/mt/verified/je_plan_check.py

Cách làm: đọc file mẫu thật bằng chính tầng đọc của app, dựng một `MT Payment
Advice` giả lập từ kết quả đó, rồi cho `_build_plan()` chạy. Nhờ vậy phép kiểm
đo đúng thứ sẽ chạy thật — kể cả những dòng kỳ quặc mà chỉ file thật mới có
(khoản trừ âm của AEON, dòng ghi giảm của Fuji, 443 dòng thanh toán của Co.op).

BA CÂU HỎI QUAN TRỌNG NHẤT:

  1. BÚT TOÁN CÓ CÂN KHÔNG? Tổng Nợ phải bằng tổng Có tới từng đồng. Lệch là
     ERPNext từ chối lúc submit — nhưng lúc đó đã sinh hàng loạt rồi.
  2. TIỀN CÓ BỊ GHI HAI LẦN KHÔNG? Dòng ghi giảm/khác phải KHÔNG sinh bút toán
     (đi đường chứng từ trả hàng), và vân tay phải chặn được lần sinh thứ hai.
  3. TIỀN CÓ BỊ MẤT IM LẶNG KHÔNG? Dòng thanh toán chưa nối hóa đơn bị loại
     khỏi bút toán — phải được BÁO ra kèm số tiền, không biến mất.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import base64
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

COMPANY = "HGC"
CUSTOMER = "KH-TEST"

ACCOUNTS = {
    "Nhận thanh toán": {"debit": "112 - NH - HGC", "tax": None, "credit": "131 - PT - HGC", "rate": 0},
    "Chiết khấu mình xuất": {"debit": "5211 - CK - HGC", "tax": "33311 - VAT - HGC",
                             "credit": "131 - PT - HGC", "rate": 0},
    "Phí chuỗi xuất": {"debit": "6411 - CP - HGC", "tax": "1331 - VATV - HGC",
                       "credit": "131 - PT - HGC", "rate": 0},
}


class _D(dict):
    """`frappe._dict` — dict truy cập được bằng thuộc tính."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class FakeAdvice(_D):
    """`MT Payment Advice` giả lập, đủ cho `_build_plan` đọc."""

    def __init__(self, rows, **kw):
        super().__init__()
        self.name = kw.get("name", "MT-BK-TEST")
        self.chain = kw.get("chain", "LOTTE")
        self.customer = kw.get("customer", CUSTOMER)
        self.company = kw.get("company", COMPANY)
        self.payment_date = kw.get("payment_date", "2026-07-30")
        self.advice_no = kw.get("advice_no", "TEST-001")
        self.file_name = kw.get("file_name", "mau.xls")
        self.reconciled = 1
        self.je_state = None
        self.status = "Đã đối chiếu"
        self.lines = [_LineDoc(r) for r in rows]


class _LineDoc(_D):
    def as_dict(self):
        return dict(self)


def _advice_lines_from_sample(chain_key, fname, si_prefix="SI-", unmatched=0):
    """Đọc file mẫu -> danh sách dòng như `MT Payment Advice Line` sau khi nạp.

    Gán `sales_invoice` giả cho các dòng thanh toán (trừ `unmatched` dòng cuối,
    cố ý để trống để đo nhánh 'chưa nối được hóa đơn').
    """
    import importlib

    ma = importlib.import_module("ketoan.api.mt_advice")
    raw = open(os.path.join(rc.SAMPLES, fname), "rb").read()
    res = ma.read_payment_advice(base64.b64encode(raw).decode(), chain_key)

    pay_seen = 0
    n_pay = sum(1 for r in res["rows"] if r["row_kind"] == "Thanh toán"
                or r["row_kind_label"] == "Thanh toán")
    out = []
    for r in res["rows"]:
        kind = r["row_kind_label"]
        si = None
        conf = None
        if kind == "Thanh toán":
            pay_seen += 1
            if pay_seen <= n_pay - unmatched:
                si = si_prefix + str(r.get("inv_no") or pay_seen)
                conf = "Chắc chắn"
        out.append(_D(
            row_kind=kind,
            row_subtype=r.get("row_subtype"),
            inv_series=r.get("inv_series"),
            inv_no=r.get("inv_no"),
            doc_no=r.get("doc_no"),
            description=r.get("description"),
            # `mt._map_rows` lưu `signed_amount` (GIỮ DẤU) vào field `total_amount`
            # của dòng DocType. Nạp bản ĐỘ LỚN vào đây là phép kiểm chạy trên dữ
            # liệu KHÁC dữ liệu thật, và đúng chỗ nguy hiểm nhất: 8 dòng khoản
            # trừ ÂM của AEON sẽ biến mất.
            total_amount=(r.get("signed_amount")
                          if r.get("signed_amount") is not None else r.get("total_amount")),
            vat_amount=r.get("vat_amount"),
            amount_before_vat=r.get("amount_before_vat"),
            sales_invoice=si,
            match_confidence=conf,
            match_method="test",
            source_row=r.get("source_row"),
        ))
    return out


def _install_stub(existing_je=(), account_rows=None):
    """Cắm frappe.db / get_all / get_doc cho tầng sinh bút toán."""
    import frappe

    accounts = ACCOUNTS if account_rows is None else account_rows

    def _sql(query, values=None, **kw):
        q = " ".join(str(query).split())
        if "tabSales Invoice" in q:
            names = (values or {}).get("names") or ()
            return [_D(name=n, customer=CUSTOMER, customer_name="Khách thử",
                       grand_total=10 ** 9, outstanding_amount=10 ** 9, docstatus=1)
                    for n in names]
        if "tabJournal Entry" in q:
            return []
        raise AssertionError("Truy vấn không được giả lập: " + q[:140])

    def _get_all(dt, filters=None, **kw):
        if dt == "MT Account Map":
            ev = (filters or {}).get("event")
            a = accounts.get(ev)
            if not a:
                return []
            return [_D(name="MT-ACC-%s" % ev, chain="", debit_account=a["debit"],
                       tax_account=a["tax"], credit_account=a["credit"],
                       tax_rate=a.get("rate") or 0)]
        return []

    def _get_value(dt, name, field=None, **kw):
        if dt == "Journal Entry" and isinstance(name, dict):
            return dict(existing_je).get(name.get("custom_mt_fingerprint"))
        if dt == "Customer":
            return "Khách thử"
        return None

    frappe.db.sql = _sql
    frappe.db.get_value = _get_value
    frappe.get_all = _get_all


def _balance(entry):
    d = sum(l["amount"] for l in entry["debit_lines"])
    c = sum(l["amount"] for l in entry["credit_lines"])
    return round(d, 2), round(c, 2)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    _install_stub()
    mj = importlib.import_module("ketoan.api.mt_je")

    print("=" * 78)
    print("KIỂM TẦNG SINH BÚT TOÁN MT")
    print("=" * 78)
    bad = 0

    CASES = [
        ("lotte", "Chi tiết thanh toán Lotte.xls", "LOTTE"),
        ("central_retail", "Chi tiết thanh toán BigC.xlsx", "Central Retail"),
        ("aeon", "chi tiet thanh to\xa0n AEON.xls", "AEON"),
        ("fuji", "CHI TIẾT THANH TOÁN FUJI.Xls", "Fuji"),
        ("coop", "Chi tiết thanh toán Coopmart.xlsx", "Saigon Co.op"),
    ]

    for key, fname, chain in CASES:
        lines = _advice_lines_from_sample(key, fname)
        doc = FakeAdvice(lines, chain=chain)
        plan, warnings, not_posted = mj._build_plan(doc)

        errs = []
        # 1. MỌI bút toán phải CÂN tới từng đồng.
        for e in plan:
            d, c = _balance(e)
            if abs(d - c) > 0.005:
                errs.append(f"{e['kind']}: Nợ {d:,.0f} ≠ Có {c:,.0f}")

        # 2. Bút toán thanh toán: mỗi dòng Có phải có reference Sales Invoice.
        pay = next((e for e in plan if e["kind"] == "Thanh toán"), None)
        if pay:
            miss = [l for l in pay["credit_lines"] if not l.get("reference_name")]
            if miss:
                errs.append(f"bút toán thanh toán có {len(miss)} dòng 131 KHÔNG gắn hóa đơn")

        # 3. Bút toán khoản trừ: ĐÚNG MỘT dòng Có, KHÔNG reference.
        for e in plan:
            if e["kind"] == "Thanh toán":
                continue
            if len(e["credit_lines"]) != 1:
                errs.append(f"{e['kind']}: {len(e['credit_lines'])} dòng Có (phải gộp 1)")
            elif e["credit_lines"][0].get("reference_name"):
                errs.append(f"{e['kind']}: dòng gộp lại gắn hóa đơn")

        # 4. KHÔNG ĐƯỢC THẤT LẠC TIỀN — kiểm theo TỪNG loại dòng, đúng quy ước
        #    của loại đó. Cộng gộp một con số chung sẽ che mất lỗi dấu.
        by_kind = collections.defaultdict(list)
        for l in lines:
            by_kind[l["row_kind"]].append(l)

        #    Thanh toán: cộng ĐỘ LỚN từng dòng (mỗi dòng một hóa đơn riêng).
        want_pay = sum(abs(float(l["total_amount"] or 0)) for l in by_kind["Thanh toán"])
        got_pay = sum(e["total"] for e in plan if e["kind"] == "Thanh toán")
        got_pay += sum(s["amount"] for e in plan for s in e["skipped_rows"])
        if abs(want_pay - got_pay) > 0.5:
            errs.append(f"thanh toán thất lạc: {want_pay:,.0f} vs {got_pay:,.0f}")

        #    Khoản trừ: TRỊ TUYỆT ĐỐI CỦA TỔNG ĐẠI SỐ. Đây là chỗ AEON từng sai
        #    598.208đ vì cộng độ lớn từng dòng (8 dòng hoàn lại bị đảo dấu).
        for kind, je_kind in (("Chiết khấu", "Chiết khấu"), ("Phí", "Phí")):
            rows_k = by_kind.get(kind) or []
            if not rows_k:
                continue
            want = abs(sum(float(l["total_amount"] or 0) for l in rows_k))
            got = sum(e["total"] for e in plan if e["kind"] == je_kind)
            if abs(want - got) > 0.5:
                errs.append(f"{kind}: mong {want:,.0f} (|tổng đại số|) nhưng bút toán "
                            f"ghi {got:,.0f}")
            gross = sum(abs(float(l["total_amount"] or 0)) for l in rows_k)
            if abs(gross - want) > 0.5 and abs(got - gross) < 0.5:
                errs.append(f"{kind}: bút toán đang cộng ĐỘ LỚN từng dòng ({gross:,.0f}) "
                            f"thay vì tổng đại số ({want:,.0f}) — ghi khống "
                            f"{gross - want:,.0f}đ")

        mark = "✅" if not errs else "❌"
        kinds = " · ".join(f"{e['kind']} {e['total']:,.0f}" for e in plan)
        print(f"  {mark} {chain:16} {len(plan)} bút toán — {kinds}")
        if not_posted:
            for n in not_posted:
                print(f"       ↳ KHÔNG ghi: {n['row_kind']} {n['n_rows']} dòng, {n['amount']:,.0f}")
        for e in errs:
            print(f"       └─ {e}")
        bad += bool(errs)

    # ── Nhóm có cả khoản TRỪ lẫn khoản HOÀN phải được GẮN CỜ ──────────────
    #
    # Ba nhóm như vậy trên file thật, và chênh lệch giữa 'cộng độ lớn' với
    # 'tổng đại số' là tiền GHI KHỐNG nếu làm sai:
    #     Co.op Chiết khấu  324.362.876đ   (126 dòng âm trong 443)
    #     AEON  Phí             598.208đ   (8 dòng âm)
    #     LOTTE Ghi giảm     11.059.478đ   (không sinh bút toán, nhưng phải báo)
    print("-" * 78)
    for key, fname, chain, kind, want_net, want_gross in (
            ("coop", "Chi tiết thanh toán Coopmart.xlsx", "Saigon Co.op",
             "Chiết khấu", 1338010941, 1662373817),
            ("aeon", "chi tiet thanh to\xa0n AEON.xls", "AEON",
             "Phí", 10424817, 11023025)):
        plan, _w, _n = mj._build_plan(FakeAdvice(
            _advice_lines_from_sample(key, fname), chain=chain))
        e = next((x for x in plan if x["kind"] == kind), None)
        ok = (e and abs(e["total"] - want_net) < 0.5 and e.get("mixed_signs")
              and abs((e.get("amount_gross") or 0) - want_gross) < 0.5)
        print(f"  {'✅' if ok else '❌'} {chain} · {kind}: ghi số RÒNG {want_net:,} "
              f"(không phải {want_gross:,}) + gắn cờ dấu lẫn lộn")
        if not ok and e:
            print(f"       └─ total={e['total']:,.0f} mixed={e.get('mixed_signs')} "
                  f"gross={e.get('amount_gross')}")
        bad += not ok

    plan, _w, not_posted = mj._build_plan(FakeAdvice(
        _advice_lines_from_sample("lotte", "Chi tiết thanh toán Lotte.xls"), chain="LOTTE"))
    n = next((x for x in not_posted if x["row_kind"] == "Ghi giảm"), None)
    ok = n and abs(n["amount"] - 809335) < 0.5 and n.get("mixed_signs")
    print(f"  {'✅' if ok else '❌'} LOTTE · Ghi giảm không sinh bút toán: báo số RÒNG "
          f"809.335 + gắn cờ (cộng độ lớn ra 11.868.813)")
    bad += not ok

    # ── Dòng thanh toán chưa nối hóa đơn: bị LOẠI nhưng phải BÁO ──────────
    print("-" * 78)
    lines = _advice_lines_from_sample("lotte", "Chi tiết thanh toán Lotte.xls", unmatched=3)
    doc = FakeAdvice(lines, chain="LOTTE")
    plan, warnings, _np = mj._build_plan(doc)
    pay = next((e for e in plan if e["kind"] == "Thanh toán"), None)
    d, c = _balance(pay)
    ok = (len(pay["skipped_rows"]) == 3 and abs(d - c) < 0.005
          and any("CHƯA nối được hóa đơn" in w for w in warnings)
          and "CHƯA GHI 3 dòng" in pay["remark"])
    print(f"  {'✅' if ok else '❌'} 3 dòng chưa nối hóa đơn: bị loại khỏi bút toán, "
          f"bút toán VẪN cân, và được báo ở cả cảnh báo lẫn diễn giải")
    if not ok:
        print(f"       └─ skipped={len(pay['skipped_rows'])} Nợ={d:,.0f} Có={c:,.0f} "
              f"warnings={warnings}")
    bad += not ok

    # ── Vân tay: ổn định, và bắt được bản đã sinh ─────────────────────────
    doc2 = FakeAdvice(_advice_lines_from_sample("lotte", "Chi tiết thanh toán Lotte.xls"),
                      chain="LOTTE")
    p1, _w, _n = mj._build_plan(doc2)
    p2, _w, _n = mj._build_plan(doc2)
    ok = ([e["fingerprint"] for e in p1] == [e["fingerprint"] for e in p2]
          and mj._plan_hash(p1) == mj._plan_hash(p2))
    print(f"  {'✅' if ok else '❌'} vân tay + vân tay kế hoạch ỔN ĐỊNH giữa hai lần dựng")
    bad += not ok

    _install_stub(existing_je={p1[0]["fingerprint"]: "ACC-JV-0001"})
    p3, _w, _n = mj._build_plan(doc2)
    ok = p3[0]["duplicate"] == "ACC-JV-0001" and not p3[1]["duplicate"]
    print(f"  {'✅' if ok else '❌'} bút toán đã sinh rồi -> báo trùng, KHÔNG sinh lại "
          f"(chốt chống trừ công nợ gấp đôi)")
    bad += not ok
    _install_stub()

    # ── Tách thuế ────────────────────────────────────────────────────────
    print("-" * 78)
    base, tax, note = mj._split_tax(1100, [{"vat_amount": 100}], 0)
    ok = (base, tax) == (1000, 100) and "file in tách" in note
    print(f"  {'✅' if ok else '❌'} file CÓ tách thuế -> dùng đúng số của file ({base:,.0f}+{tax:,.0f})")
    bad += not ok

    base, tax, note = mj._split_tax(1100, [{}], 10)
    ok = abs(base - 1000) < 0.01 and abs(tax - 100) < 0.01 and "thuế suất" in note
    print(f"  {'✅' if ok else '❌'} file KHÔNG tách + kế toán khai 10% -> tách theo khai báo")
    bad += not ok

    base, tax, note = mj._split_tax(1100, [{}], 0)
    ok = (base, tax, note) == (1100, 0.0, "")
    print(f"  {'✅' if ok else '❌'} không có cả hai -> KHÔNG tự suy ra thuế (dồn TK Nợ chính)")
    bad += not ok

    # ── Các nhánh phải DỪNG ──────────────────────────────────────────────
    print("-" * 78)

    def _throws(fn, what):
        nonlocal bad
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"  ✅ {what}")
            return str(e)
        print(f"  ❌ {what} — KHÔNG dừng, đây là đường ghi sổ sai")
        bad += 1
        return ""

    _throws(lambda: mj._build_plan(FakeAdvice(
        _advice_lines_from_sample("fuji", "CHI TIẾT THANH TOÁN FUJI.Xls"),
        chain="Fuji", payment_date=None)),
        "bảng kê THIẾU ngày thanh toán -> dừng (bút toán sẽ rơi sai kỳ)")

    _throws(lambda: mj._build_plan(FakeAdvice(
        _advice_lines_from_sample("aeon", "chi tiet thanh to\xa0n AEON.xls"),
        chain="AEON", customer=None)),
        "bảng kê THIẾU khách hàng -> dừng ở bút toán khoản trừ (dòng 131 không có party)")

    _install_stub(account_rows={"Nhận thanh toán": ACCOUNTS["Nhận thanh toán"]})
    _throws(lambda: mj._build_plan(FakeAdvice(
        _advice_lines_from_sample("aeon", "chi tiet thanh to\xa0n AEON.xls"), chain="AEON")),
        "CHƯA cấu hình tài khoản cho sự kiện -> dừng, không lấy TK đoán")

    # Có tiền thuế mà chưa khai TK thuế -> dừng (không ghi thuế vào chi phí).
    no_tax = {k: dict(v, tax=None, rate=10 if k == "Phí chuỗi xuất" else 0)
              for k, v in ACCOUNTS.items()}
    _install_stub(account_rows=no_tax)
    _throws(lambda: mj._build_plan(FakeAdvice(
        _advice_lines_from_sample("aeon", "chi tiet thanh to\xa0n AEON.xls"), chain="AEON")),
        "có tiền thuế nhưng CHƯA khai TK thuế -> dừng (không ghi VAT vào chi phí)")
    _install_stub()

    # ── Không dòng nào nối được hóa đơn -> không sinh bút toán thanh toán ──
    lines = _advice_lines_from_sample("lotte", "Chi tiết thanh toán Lotte.xls", unmatched=10 ** 6)
    plan, warnings, _n = mj._build_plan(FakeAdvice(lines, chain="LOTTE"))
    ok = (not any(e["kind"] == "Thanh toán" for e in plan)
          and any("KHÔNG dòng thanh toán nào nối được" in w for w in warnings))
    print(f"  {'✅' if ok else '❌'} không dòng nào nối được hóa đơn -> KHÔNG sinh bút toán "
          f"thanh toán + cảnh báo")
    bad += not ok

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — bút toán cân, không ghi trùng, không mất tiền im lặng"
          if not bad else f"HỎNG {bad} mục")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
