#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm luật "số PO trên TỪNG DÒNG HÀNG" khi xuất hóa đơn MISA (ORION VINA).

Yêu cầu: khách hàng ORION VINA — mỗi dòng sản phẩm trên hóa đơn MISA mang
thêm "-PO" + số PO, tức `Description` = "<tên hàng>-PO <số PO>" — CÓ dấu cách
giữa "PO" và số (bản đầu viết liền, kế toán báo khó đọc).

Bộ kiểm dựng PAYLOAD THẬT bằng `misa_push.build_payload` — hai dòng hàng, thuế
GTGT 8%, tổng tiền khớp sổ — để chốt so tiền cũng chạy, không chỉ soi chuỗi.

Năm điều canh, mỗi điều một mục:

  1. ORION VINA: MỌI dòng hàng mang hậu tố, KHÔNG thêm dòng ghi chú PO riêng
     (giống các khách đặc biệt khác: PO nằm một chỗ, không lặp), tiền không đổi.
  2. Khớp theo cả MÃ khách lẫn TÊN khách, không phân biệt hoa/thường: mã
     Customer trên site có thể là tên pháp nhân đầy đủ chứa "ORION VINA".
  3. Khách KHÁC giữ nguyên hành vi cũ: tên hàng không đổi, có dòng ghi chú
     "(Chi tiết theo đơn hàng ...)"; Mega Market / BigC vẫn nối PO vào tên
     người mua như trước.
  4. ORION VINA mà hóa đơn CHƯA có Số PO ⇒ DỪNG trước khi gọi MISA. Hóa đơn
     điện tử đã phát hành thì không thêm PO vào được — chỉ làm hóa đơn thay thế.
  5. Tên hàng đã mang sẵn đúng hậu tố thì không nối lần hai.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
    python3 docs/mt/verified/misa_po_tung_dong_check.py   # exit 0 = đạt
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


class _D(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    # `si.items` là BẢNG DÒNG HÀNG; `_D` là dict nên `si.items` sẽ ra `dict.items`
    # nếu không chặn tên này lại (xem misa_buyer_guard_check.py).
    @property
    def items(self):
        return self.get("_rows") or []


class _Settings(_D):
    def series_list(self):
        return ["1C26THG"]


SETTINGS = _Settings(company_id="1", organization_unit_id="ou-1", inv_template_no="1",
                     invoice_template_id="tpl-1", misa_user_id="u-1")


def _row(code, ten, qty, gia):
    return _D(item_code=code, item_name=ten, qty=qty, net_rate=gia, uom="Thùng",
              conversion_factor=1, stock_qty=qty, item_tax_rate=None)


def _si(**kw):
    """Sales Invoice giả đủ để build_payload đi hết: 2 dòng, thuế 8%, tiền khớp."""
    rows = [_row("CP360", "Bánh Chocopie 360g", 10, 50000),
            _row("OS80", "Bánh Ostar 80g", 5, 20000)]
    base = dict(
        name="HD-TEST", custom_misa_ref_id="ref-0001", _rows=rows,
        customer="ORION VINA", customer_name="ORION VINA", custom_po_="4500123456",
        custom_tên_người_mua="Phòng mua hàng", custom_tên_đơn_vị="Công ty TNHH Orion Vina",
        custom_mã_số_thuế="0301234567", posting_date="2026-11-05",
        net_total=600000.0, grand_total=648000.0,
        taxes=[{"charge_type": "On Net Total", "account_head": "VAT 8 - HGC",
                "tax_amount": 48000.0}],
    )
    base.update(kw)
    return _D(**base)


def _dung(si):
    """(payload, lỗi) — đúng một trong hai khác None."""
    push = importlib.import_module("ketoan.api.misa_push")
    try:
        return push.build_payload(si, SETTINGS), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def _mo_ta(p):
    return [l.get("Description") for l in (p or {}).get("InvoiceDetails", [])]


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: False   # không có MT Store ⇒ không đòi MST theo điểm

    print("=" * 78)
    print("misa_po_tung_dong_check — số PO trên từng dòng hàng (ORION VINA)")
    print("=" * 78)

    # ── 1. ORION VINA ────────────────────────────────────────────────
    print("-" * 78)
    print("── 1. ORION VINA: mọi dòng hàng mang '-PO <số PO>', không dòng ghi chú ─")
    p, loi = _dung(_si())
    check("dựng được payload", p is not None, loi or "")
    mt = _mo_ta(p)
    check("mọi dòng hàng = '<tên hàng>-PO 4500123456' (có dấu cách trước số PO)",
          mt == ["Bánh Chocopie 360g-PO 4500123456", "Bánh Ostar 80g-PO 4500123456"], str(mt))
    check("KHÔNG thêm dòng ghi chú '(Chi tiết theo đơn hàng ...)'",
          p is not None and len(p["InvoiceDetails"]) == 2
          and not any("Chi tiết theo đơn hàng" in (d or "") for d in mt), str(len(mt)))
    check("tiền không đổi: trước thuế 600.000, thuế 48.000, tổng 648.000",
          p is not None and p["TotalSaleAmount"] == 600000 and p["TotalVATAmount"] == 48000
          and p["TotalAmount"] == 648000,
          "" if p is None else f"{p['TotalSaleAmount']}/{p['TotalVATAmount']}/{p['TotalAmount']}")
    check("tên người mua giữ nguyên (không nối PO lần nữa ở đó)",
          p is not None and p["ContactName"] == "Phòng mua hàng", "" if p is None else p["ContactName"])

    # ── 2. Khớp mã khách / tên khách / hoa thường ─────────────────────
    print("-" * 78)
    print("── 2. Khớp theo mã HOẶC tên khách, không phân biệt hoa/thường ─────")
    p2, _ = _dung(_si(customer="KH-0123", customer_name="CÔNG TY TNHH ORION VINA"))
    check("mã khách 'KH-0123' + tên 'CÔNG TY TNHH ORION VINA' ⇒ áp luật",
          _mo_ta(p2)[:1] == ["Bánh Chocopie 360g-PO 4500123456"], str(_mo_ta(p2)[:1]))
    p3, _ = _dung(_si(customer="orion  vina", customer_name=""))
    check("mã khách viết thường, thừa khoảng trắng 'orion  vina' ⇒ áp luật",
          _mo_ta(p3)[:1] == ["Bánh Chocopie 360g-PO 4500123456"], str(_mo_ta(p3)[:1]))

    # ── 3. Khách khác giữ nguyên hành vi cũ ──────────────────────────
    print("-" * 78)
    print("── 3. Khách KHÁC: hành vi cũ không đổi ─────────────────────────────")
    p4, loi4 = _dung(_si(customer="Coopmart", customer_name="Saigon Co.op"))
    m4 = _mo_ta(p4)
    check("Coopmart: tên hàng KHÔNG mang hậu tố",
          m4[:2] == ["Bánh Chocopie 360g", "Bánh Ostar 80g"], str(m4[:2]) or loi4)
    check("Coopmart: vẫn có dòng ghi chú '(Chi tiết theo đơn hàng 4500123456)'",
          m4[2:] == ["(Chi tiết theo đơn hàng 4500123456)"], str(m4[2:]))
    p5, _ = _dung(_si(customer="Mega Market", customer_name="MM Mega Market"))
    check("Mega Market: PO vẫn nối vào tên người mua, tên hàng không đổi",
          p5 is not None and p5["ContactName"] == "Phòng mua hàngPO4500123456"
          and _mo_ta(p5) == ["Bánh Chocopie 360g", "Bánh Ostar 80g"],
          "" if p5 is None else f"{p5['ContactName']} | {_mo_ta(p5)}")
    p6, _ = _dung(_si(customer="BigC", customer_name="BigC"))
    check("BigC: PO vẫn nối ', <PO>' vào tên người mua",
          p6 is not None and p6["ContactName"] == "Phòng mua hàng, 4500123456")
    p7, _ = _dung(_si(customer="Coopmart", customer_name="Saigon Co.op", custom_po_=""))
    check("khách khác KHÔNG có PO: không chặn, không dòng ghi chú",
          p7 is not None and _mo_ta(p7) == ["Bánh Chocopie 360g", "Bánh Ostar 80g"])

    # ── 4. ORION VINA thiếu Số PO ⇒ dừng trước khi gọi MISA ──────────
    print("-" * 78)
    print("── 4. ORION VINA chưa có Số PO ⇒ DỪNG, không phát hành ────────────")
    p8, loi8 = _dung(_si(custom_po_=""))
    check("không dựng payload (không có gì để gửi MISA)", p8 is None)
    check("câu báo nói rõ thiếu Số PO và cách sửa",
          loi8 is not None and "Số PO" in loi8 and "TỪNG DÒNG HÀNG" in loi8, (loi8 or "")[:70])
    p9, loi9 = _dung(_si(custom_po_="   "))
    check("Số PO chỉ có khoảng trắng cũng là thiếu", p9 is None and "Số PO" in (loi9 or ""))

    # ── 5. Không nối hai lần ──────────────────────────────────────────
    print("-" * 78)
    print("── 5. Tên hàng đã có sẵn hậu tố thì không nối lần hai ─────────────")
    s10 = _si()
    s10["_rows"][0]["item_name"] = "Bánh Chocopie 360g-PO 4500123456"
    p10, _ = _dung(s10)
    check("không thành '...-PO 4500123456-PO 4500123456'",
          _mo_ta(p10)[:1] == ["Bánh Chocopie 360g-PO 4500123456"], str(_mo_ta(p10)[:1]))

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — ORION VINA mang '-PO <số PO>' trên từng dòng hàng, khách "
              "khác giữ nguyên, thiếu PO thì dừng trước khi gọi MISA.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
