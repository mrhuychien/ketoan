"""thu_hoi_phan_bo — HÀM THUẦN của thu hồi hàng: chia số đã kiểm vào dòng hóa đơn gốc,
và suy trạng thái phiếu kiểm. KHÔNG import frappe — `docs/verified/thu_hoi_check.py`
chạy thẳng trên các hàm này, không cần bench.

════════════════════════════════════════════════════════════════════════════
VÌ SAO DÒNG TRẢ PHẢI GIỮ ĐÚNG ĐVT CỦA DÒNG GỐC
════════════════════════════════════════════════════════════════════════════

Đọc từ ERPNext v16 thật (`erpnext/controllers/sales_and_purchase_return.py`,
`validate_quantity`):

    fields = ["stock_qty"]
    if doctype == "Sales Invoice" and not doc.update_stock:
        fields = ["qty"]

Hóa đơn trả về của app này để `update_stock = 0` — đúng quy ước Client Script
(`update_stock: !is_return`) và đúng cách kho đang làm (hàng trả vào kho bằng phiếu
kho riêng sau khi lọc). Khi đó ERPNext so **`qty` THEO ĐVT CỦA DÒNG** với `qty`
của dòng gốc nó trỏ tới (`sales_invoice_item`). Dòng gốc "10 Thùng" mà dòng trả
ghi "70 Hộp" là so 70 với 10: chặn nhầm một lần trả hợp lệ, và sau khi ghi sổ thì
sổ "đã trả" của ERPNext cộng hộp với thùng — lần trả sau tính sai trần.

Nên dòng trả NỐI vào dòng gốc luôn mang đúng ĐVT + hệ số của dòng gốc. Luật tách:

  1. phần CHẴN đơn vị của dòng gốc (chẵn thùng)     → dòng NỐI, ĐVT gốc;
  2. phần lẻ → dòng NỐI số lẻ CHỈ KHI biểu diễn ĐÚNG ở độ chính xác của ô `qty` và
     ĐVT cho phép số lẻ (24 hộp/thùng: 6 hộp = 0,25 thùng → được; 70/30 → không);
  3. còn lại → dòng KHÔNG NỐI, ĐVT kho. ERPNext chỉ cảnh báo "Returned Item … does
     not exist" (không chặn), và trần trả của dòng đó do app này tự giữ.

KHÔNG BAO GIỜ làm tròn số lượng cho vừa: hóa đơn trả về là chứng từ có giá trị pháp
lý, lệch 100đ là lệch với số siêu thị trừ khi thanh toán, và lệch đó không ai đi tìm.

════════════════════════════════════════════════════════════════════════════
TRẦN TRẢ ĐẾM CẢ BẢN NHÁP
════════════════════════════════════════════════════════════════════════════

ERPNext chỉ đếm phiếu trả ĐÃ GHI SỔ (`get_already_returned_items`: docstatus = 1).
Hai bản nháp cùng trả vào một hóa đơn gốc thì cả hai đều thấy đủ trần, và chỉ lộ ra
lúc ghi sổ bản thứ hai. Ở đây đếm mọi phiếu trả `docstatus < 2`.
"""

import math

EPS = 1e-6

DANG_KIEM = "Đang kiểm"
DA_KIEM = "Đã kiểm hàng"
DA_NHAP = "Đã nhập chứng từ"
XONG = "Xong"
CHANG_KE_TOAN = (DANG_KIEM, DA_KIEM, DA_NHAP, XONG)


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def chinh_xac(q, precision, chi_so_nguyen=False):
    """`q` (theo ĐVT của dòng) có ghi ĐÚNG được vào ô số lượng không.

    Số nguyên luôn được. Số lẻ chỉ được khi ĐVT cho phép lẻ VÀ `q` đúng y sau khi
    làm tròn tới `precision` chữ số — 0,25 thì được, 0,041666… thì không.
    """
    if abs(q - round(q)) < EPS:
        return True
    if chi_so_nguyen:
        return False
    return abs(round(q, int(precision)) - q) < 1e-9


def phan_bo(can, dong_goc, da_tra_dong=None, da_tra_mat_hang=None, precision=3, uom_nguyen=()):
    """Chia số CẦN TRẢ vào các dòng của MỘT hóa đơn gốc.

    can              {item_code: SL cần trả theo ĐVT kho, dương}
    dong_goc         [{name, item_code, qty, conversion_factor, uom}] dòng hóa đơn gốc, theo idx
    da_tra_dong      {tên dòng gốc: qty ĐÃ TRẢ theo ĐVT của dòng} — phiếu trả NỐI dòng đó, kể cả nháp
    da_tra_mat_hang  {item_code: SL ĐVT kho đã trả} — MỌI phiếu trả của hóa đơn này, kể cả nháp,
                     kể cả dòng không nối
    precision        số chữ số thập phân của ô `qty`
    uom_nguyen       tập ĐVT bắt buộc số nguyên (UOM.must_be_whole_number)

    Trả (dong_tra, con_thieu):
      dong_tra   [{"src", "item_code", "noi": True,  "qty": theo ĐVT dòng gốc, "stock_qty"}]
                 [{"src", "item_code", "noi": False, "stock_qty"}]   ← dòng ĐVT kho, không nối
      con_thieu  {item_code: SL ĐVT kho hóa đơn này không nhận được}
    """
    da_tra_dong = da_tra_dong or {}
    da_tra_mat_hang = da_tra_mat_hang or {}
    uom_nguyen = set(uom_nguyen or ())
    dong_tra, con_thieu = [], {}

    for item, need in can.items():
        need = _f(need)
        if need <= EPS:
            continue
        rows = [r for r in dong_goc if r.get("item_code") == item and _f(r.get("qty")) > EPS]
        if not rows:
            con_thieu[item] = need
            continue

        def cf(r):
            return _f(r.get("conversion_factor")) or 1.0

        # Trần của MẶT HÀNG trên hóa đơn này, theo ĐVT kho — gồm cả lần trả không nối.
        tran_mat_hang = sum(_f(r.get("qty")) * cf(r) for r in rows) - _f(da_tra_mat_hang.get(item))
        a = min(need, max(tran_mat_hang, 0.0))
        if need - a > EPS:
            con_thieu[item] = need - a
        if a <= EPS:
            continue
        # Trần của từng DÒNG, theo ĐVT của dòng — đúng phép so của ERPNext.
        tran = {r["name"]: max(_f(r.get("qty")) - _f(da_tra_dong.get(r["name"])), 0.0) for r in rows}
        # Dòng hệ số lớn trước (thùng trước hộp); cùng hệ số thì giữ thứ tự idx.
        thu_tu = sorted(rows, key=lambda r: -cf(r))

        # 1. Phần chẵn đơn vị của dòng gốc.
        for r in thu_tu:
            if a <= EPS:
                break
            c = cf(r)
            k = min(math.floor((a + EPS) / c), math.floor(tran[r["name"]] + EPS))
            if k > 0:
                dong_tra.append({"src": r["name"], "item_code": item, "noi": True,
                                 "qty": float(k), "stock_qty": k * c})
                a -= k * c
                tran[r["name"]] -= k

        # 2. Phần lẻ — nối được khi ghi đúng y.
        if a > EPS:
            for r in thu_tu:
                c = cf(r)
                q = a / c
                if tran[r["name"]] + EPS >= q and chinh_xac(q, precision, r.get("uom") in uom_nguyen):
                    dong_tra.append({"src": r["name"], "item_code": item, "noi": True,
                                     "qty": round(q, int(precision)), "stock_qty": a})
                    tran[r["name"]] -= q
                    a = 0.0
                    break

        # 3. Còn lại — dòng ĐVT kho, không nối. Giá lấy theo dòng gốc đầu của mã.
        if a > EPS:
            dong_tra.append({"src": rows[0]["name"], "item_code": item, "noi": False, "stock_qty": a})

    return dong_tra, con_thieu


def tong_theo_ma(hoa_don):
    """{item_code: SL ĐVT kho} cộng qua các phiếu trả [{"items": {item: sl}}]."""
    out = {}
    for h in hoa_don or []:
        for it, q in (h.get("items") or {}).items():
            out[it] = out.get(it, 0.0) + _f(q)
    return out


def con_can(can, hoa_don):
    """Phần ĐÃ KIỂM mà chưa có phiếu trả nào nhận: {item: SL ĐVT kho > 0}."""
    da = tong_theo_ma(hoa_don)
    out = {}
    for it, q in (can or {}).items():
        r = _f(q) - da.get(it, 0.0)
        if r > EPS:
            out[it] = r
    return out


def suy_trang_thai(da_chot, khong_lap_hd, can, hoa_don):
    """Trạng thái phiếu kiểm — SUY TỪ CHỨNG TỪ CÓ THẬT, không ai gõ.

    can      {item: SL đã kiểm, ĐVT kho}
    hoa_don  [{"name", "docstatus", "items": {item: SL ĐVT kho, dương}}] — phiếu trả gắn
             phiếu kiểm này, docstatus < 2

    Trả (trạng thái, lệch) với lệch = {item: SL trên phiếu trả − SL đã kiểm}, chỉ mục ≠ 0.

    "Đã nhập chứng từ" đòi phiếu trả phủ ĐÚNG từng mặt hàng — thiếu là còn việc, mà THỪA
    cũng là việc (kiểm lại bớt đi sau khi đã lập phiếu trả): báo "xong" lúc đó là ghi
    giảm công nợ nhiều hơn số hàng thật về kho.
    """
    if not da_chot:
        return DANG_KIEM, {}
    if khong_lap_hd:
        return XONG, {}
    da = tong_theo_ma(hoa_don)
    lech = {}
    for it in set(can or {}) | set(da):
        d = da.get(it, 0.0) - _f((can or {}).get(it))
        if abs(d) > EPS:
            lech[it] = d
    if not hoa_don or lech:
        return DA_KIEM, lech
    if all(int(h.get("docstatus") or 0) == 1 for h in hoa_don):
        return XONG, {}
    return DA_NHAP, {}


def gop_chi_tiet(cu, moi):
    """Cộng hai bảng chi tiết ĐVT [{uom, sl, he_so}] theo uom (quét thêm cùng mã)."""
    out = {}
    for c in (cu or []) + (moi or []):
        u = c.get("uom")
        if not u:
            continue
        o = out.setdefault(u, {"uom": u, "sl": 0.0, "he_so": _f(c.get("he_so")) or 1.0})
        o["sl"] += _f(c.get("sl"))
    return sorted(out.values(), key=lambda x: -x["he_so"])


def mo_ta_chi_tiet(ct):
    """"2 Thùng + 3 Hộp" — rỗng khi chỉ có một ĐVT (tổng đã nói đủ)."""
    ds = [c for c in (ct or []) if _f(c.get("sl")) > EPS]
    if len(ds) <= 1:
        return ""

    def so(x):
        return str(int(x)) if abs(x - round(x)) < EPS else ("%g" % x)

    return " + ".join(f"{so(_f(c['sl']))} {c['uom']}" for c in ds)
