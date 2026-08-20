"""Kiểm KẾT LUẬN "không khớp tự động dòng Ghi giảm" — đo trên cả 7 file mẫu thật.

    python3 docs/mt/verified/clawback_check.py

Đây là hạng mục mở cuối cùng của MT-2, và nó KHÔNG được đóng bằng cách viết
thêm code — nó được đóng bằng một phép đo chứng minh rằng viết code là SAI.

════════════════════════════════════════════════════════════════════════════
CÂU HỎI
════════════════════════════════════════════════════════════════════════════

Dòng `Ghi giảm` trên bảng kê chuỗi có mang số hóa đơn. Có nên tự động nối nó
sang Sales Invoice của mình, để hóa đơn bị chuỗi đòi lại tiền quay về rổ nợ?

════════════════════════════════════════════════════════════════════════════
PHÉP ĐO TRẢ LỜI: KHÔNG
════════════════════════════════════════════════════════════════════════════

Số hóa đơn trên dòng ghi giảm là hóa đơn CỦA CHUỖI xuất cho mình, không phải
hóa đơn bán ra của mình. Nhận ra bằng KÝ HIỆU:

  · hóa đơn của mình  -> `…THG…`  (Thực phẩm Hoàng Giang), ví dụ `1C26THG`
  · hóa đơn của chuỗi -> `K26TRT` (Central Retail) · `1K25TCH`, `1K25TAN`
                         (Co.op) · `K26TBD`, `K26TDH` (AEON)

Và phép đo quyết định: **không một dòng ghi giảm nào mang số hóa đơn trùng với
một dòng thanh toán trong cùng file** — trên cả ba chuỗi có số hóa đơn ở dòng
ghi giảm. Nối tự động là gán tiền của hóa đơn chuỗi vào hóa đơn của mình.

Phép kiểm này CHẠY LẠI phép đo mỗi lần, nên nếu kỳ sau chuỗi đổi cách ghi thì
nó đổi màu — kết luận không bị đóng băng thành niềm tin.

════════════════════════════════════════════════════════════════════════════
HAI CHỐT CHẶN PHẢI CÒN NGUYÊN
════════════════════════════════════════════════════════════════════════════

`relink_line` và `MTPaymentAdviceLine.validate()` đều phải chặn. Một cái sập là
kế toán chốt tay được một liên kết sai mà không có gì kêu.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

KIND_PAYMENT = "thanh_toan"
KIND_DEDUCT = "ghi_giam"

# Ký hiệu hóa đơn BÁN RA của mình. TT78: <mẫu số><C|K><2 số năm><3 ký tự người
# bán tự đặt>. Ba ký tự cuối của mình là `THG`.
OUR_TAG = "THG"


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


def _key(row):
    """Khóa so hóa đơn: 6 ký tự cuối của ký hiệu + số đã bỏ số 0 đầu."""
    return (str(row.get("inv_series") or "").upper()[-6:],
            str(row.get("inv_no") or "").lstrip("0"))


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    ma = importlib.import_module("ketoan.api.mt_advice")

    print("=" * 78)
    print("KIỂM KẾT LUẬN: KHÔNG KHỚP TỰ ĐỘNG DÒNG GHI GIẢM")
    print("=" * 78)
    bad = 0

    # ── 1. Đo trên mọi file mẫu ──────────────────────────────────────────
    n_ded = n_inv = n_overlap = n_ours = 0
    seen_chains = []
    for fname in sorted(os.listdir(rc.SAMPLES)):
        path = os.path.join(rc.SAMPLES, fname)
        if not os.path.isfile(path):
            continue
        try:
            res = ma.read_payment_advice(base64.b64encode(open(path, "rb").read()).decode())
        except Exception:                                          # noqa: BLE001
            continue                                               # không phải file thanh toán
        rows = res["rows"]
        ded = [r for r in rows if r["row_kind"] == KIND_DEDUCT]
        if not ded:
            continue
        pay = {_key(r) for r in rows if r["row_kind"] == KIND_PAYMENT and r.get("inv_no")}
        with_inv = [r for r in ded if r.get("inv_no")]
        overlap = [r for r in with_inv if _key(r) in pay]
        ours = [r for r in with_inv if OUR_TAG in str(r.get("inv_series") or "").upper()]

        n_ded += len(ded)
        n_inv += len(with_inv)
        n_overlap += len(overlap)
        n_ours += len(ours)
        seen_chains.append(res["chain"])

        series = sorted({str(r.get("inv_series") or "?").upper() for r in with_inv})
        print(f"  {res['chain']:16s} ghi giảm {len(ded):4d} · có số HĐ {len(with_inv):4d} · "
              f"trùng HĐ thanh toán {len(overlap):2d} · ký hiệu {', '.join(series[:4]) or '—'}")

    ok = len(seen_chains) >= 5
    print(f"  {'✅' if ok else '❌'} đọc được dòng ghi giảm ở {len(seen_chains)} chuỗi "
          f"({n_ded} dòng, {n_inv} dòng mang số hóa đơn)")
    bad += not ok

    print("-" * 78)
    ok = n_overlap == 0
    print(f"  {'✅' if ok else '❌'} {n_overlap} dòng ghi giảm trùng hóa đơn với một dòng "
          f"thanh toán -> chuỗi KHÔNG đòi lại tiền trên hóa đơn của mình")
    bad += not ok

    ok = n_ours == 0
    print(f"  {'✅' if ok else '❌'} {n_ours} dòng ghi giảm mang ký hiệu `{OUR_TAG}` của mình "
          f"-> số hóa đơn trên dòng ghi giảm là hóa đơn CỦA CHUỖI")
    bad += not ok

    if n_overlap or n_ours:
        print("       └─ PHÉP ĐO ĐÃ ĐỔI. Kết luận 'không khớp tự động' dựa trên hai số")
        print("          này; số đổi thì phải xem lại kết luận, không sửa phép kiểm.")

    # ── 2. Hai chốt chặn phải còn nguyên ─────────────────────────────────
    print("-" * 78)
    line_mod = importlib.import_module(
        "ketoan.mt.doctype.mt_payment_advice_line.mt_payment_advice_line")

    doc = _D(idx=1, row_kind="Ghi giảm", sales_invoice="SI-0001",
             inv_series="K26TRT", inv_no="21246", inv_no_norm="21246",
             store_code=None, store_name=None, doc_no=None, match_method="tay")
    try:
        line_mod.MTPaymentAdviceLine.validate(doc)
        print("  ❌ validate() của dòng: ghi giảm nối được Sales Invoice")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "KHÔNG được nối" in str(e)
        print(f"  {'✅' if ok else '❌'} validate() chặn: dòng 'Ghi giảm' không nối được "
              f"Sales Invoice")
        bad += not ok

    mt = importlib.import_module("ketoan.api.mt")
    frappe.db.table_exists = lambda dt: True
    frappe.db.get_value = lambda dt, name, fields=None, **k: _D(
        name="LINE-1", parent="ADV-1", parenttype="MT Payment Advice",
        row_kind="Ghi giảm", inv_series="K26TRT", inv_no="21246",
        total_amount=-4810590.0, sales_invoice=None)
    try:
        mt.relink_line("LINE-1", sales_invoice="SI-0001")
        print("  ❌ relink_line: chốt tay nối được dòng ghi giảm")
        bad += 1
    except Exception as e:                                         # noqa: BLE001
        ok = "không được nối" in str(e)
        print(f"  {'✅' if ok else '❌'} relink_line chặn: chốt tay cũng không nối được "
              f"dòng ghi giảm")
        bad += not ok

    # ── 3. `paid` và `clawed_back` không đếm chung một dòng ──────────────
    print("-" * 78)
    sql = mt._paid_subquery()
    flat = " ".join(sql.split())
    # Cả hai vế của `paid` phải kèm điều kiện row_kind = thanh toán.
    paid_part = flat.split("AS paid,")[0]
    review_part = flat.split("AS paid,")[1].split("AS paid_review,")[0]
    ok = "kind_payment" in paid_part and "kind_payment" in review_part
    print(f"  {'✅' if ok else '❌'} `paid` và `paid_review` lọc `row_kind = Thanh toán` "
          f"-> nới chặn ở validate cũng không làm hai cột triệt tiêu nhau")
    bad += not ok

    claw_part = flat.split("AS paid_review,")[1].split("AS clawed_back,")[0]
    ok = "kind_deduct" in claw_part
    print(f"  {'✅' if ok else '❌'} `clawed_back` lọc `row_kind = Ghi giảm` — công thức "
          f"đã đúng sẵn, ngày nào chốt tay được thì chạy đúng ngay")
    bad += not ok

    print("=" * 78)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — số hóa đơn trên dòng ghi giảm là của CHUỖI, không của "
          "mình; khớp tự động là SAI, không phải 'chưa làm'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
