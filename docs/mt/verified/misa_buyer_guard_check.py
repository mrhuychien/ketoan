#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm CHỐT KHỐI NGƯỜI MUA trước khi đẩy MISA, và cờ khóa khi sửa đổi.

════════════════════════════════════════════════════════════════════════════
CON BUG BỘ KIỂM NÀY CANH
════════════════════════════════════════════════════════════════════════════

Sáu ô người mua trên Sales Invoice (MST / tên đơn vị / địa chỉ / tên người mua
/ hình thức thanh toán / email) đều `fetch_from shipping_address_name.*`, và
KHÔNG ô nào có `allow_on_submit`. Hệ quả, đo được từ chính mã Frappe:

    base_document.py:1070   `if not docname: continue`
        -> ô địa chỉ TRỐNG thì BỎ QUA fetch, IM LẶNG, không một lời nào
    base_document.py:1155   `if self.is_new() or not self.docstatus.is_submitted()
                             or _df.allow_on_submit`
        -> ĐÃ GHI SỔ thì KHÔNG BAO GIỜ fetch lại

Nên hóa đơn tạo từ Nhập đơn tự động (nhồi chuỗi thô Gemini vào ô Link đó) ra
đời với cả khối người mua trống. MISA không phát hành được hóa đơn GTGT không
có tên người mua — nhưng lúc biết thì hóa đơn ĐÃ ghi sổ, và không còn đường sửa
tại chỗ. Cách duy nhất là HỦY hóa đơn.

VÀ ĐÓ MỚI LÀ CHỖ MẤT TIỀN THẬT: hủy một hóa đơn CÓ THỂ đã tới MISA (phản hồi
đẩy không đọc được, hoặc timeout) thì bản gốc rơi khỏi cả hai vòng quét
(`misa_sync.py` lọc `docstatus: 1`) và thành hóa đơn MỒ CÔI bên MISA, trong khi
bản sửa đổi mang RefID mới sinh ra hóa đơn thứ hai. HAI hóa đơn điện tử có giá
trị pháp lý cho MỘT lần bán. `SOP_ke_toan_MT_RVHG.md:63` đã ghi thành văn
"KHÔNG hủy, KHÔNG amend" — tức app đang buộc kế toán làm đúng việc SOP cấm.

Vì vậy chốt phải DỪNG Ở `build_payload`, TRƯỚC mọi lệnh gọi HTTP.

HAI CẠM BẪY khi viết chốt này, mỗi cái một mục kiểm:

  1. Đòi MST cho MỌI hóa đơn ⇒ CHẶN OAN bán lẻ. Cá nhân không có mã số thuế,
     và hóa đơn cho họ vẫn hợp lệ. Chốt chỉ đòi MST khi điểm giao là ĐIỂM SIÊU
     THỊ (có dòng trong `MT Store`).
  2. Đòi `custom_tên_đơn_vị` cứng ⇒ chặn oan hóa đơn chỉ có tên người mua.
     Chốt nhận MỘT TRONG HAI ô tên là đủ.

Mục 5 canh một lỗ khác cùng họ: nhánh amend của `ensure_ref_id` phải đặt
`custom_misa_no_locked` về **0**, KHÔNG phải None — vòng quét thứ 2 lọc
`= 0` nên NULL là rơi khỏi bộ lọc, đúng cái patch v0_0_17 đã phải chữa một lần.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
    python3 docs/mt/verified/misa_buyer_guard_check.py   # exit 0 = đạt
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402

STORE_ADDR = set()   # địa chỉ được coi là ĐIỂM SIÊU THỊ (có dòng MT Store)
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

    # `doc.set(f, v)` của Frappe Document — bộ giả thiếu nó thì `ensure_ref_id`
    # nuốt TypeError bằng `except` trần của chính nó và phép kiểm thấy "không
    # dọn gì" mà tưởng mã sản xuất hỏng.
    def set(self, k, v):
        self[k] = v

    # `si.items` của Sales Invoice là BẢNG DÒNG HÀNG, nhưng `_D` là dict nên
    # `si.items` trả về `dict.items` — `__getattr__` chỉ chạy khi tra attribute
    # THẤT BẠI. Phải chặn tên này lại, không thì build_payload nổ TypeError
    # trước khi tới chốt cần kiểm.
    @property
    def items(self):
        return self.get("_rows") or []


class _Meta:
    def __init__(self, fields):
        self._f = set(fields)

    def has_field(self, f):
        return f in self._f


def _si(**kw):
    """Sales Invoice giả, đủ cho build_payload đi tới chốt khối người mua."""
    base = dict(
        name="HD-TEST", custom_misa_ref_id="ref-0001", _rows=[],
        customer="Coopmart", net_total=0.0, grand_total=0.0, taxes=[],
        posting_date="2026-10-08",
    )
    base.update(kw)
    return _D(**base)


def _goi(si):
    """Gọi build_payload, trả câu lỗi (hoặc None nếu không throw ở chốt nào)."""
    push = importlib.import_module("ketoan.api.misa_push")
    try:
        push.build_payload(si, _D())
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.commit = lambda *a, **kw: None
    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: dt == "MT Store"
    frappe.db.exists = lambda dt, flt=None: (
        dt == "MT Store" and isinstance(flt, dict) and flt.get("address") in STORE_ADDR
    )

    print("=" * 78)
    print("misa_buyer_guard_check — chốt khối người mua + cờ khóa khi sửa đổi")
    print("=" * 78)

    # ── 1. Trống tên người mua -> CHẶN, và nói đúng việc phải làm ──────
    print("-" * 78)
    print("── 1. Hóa đơn trống TÊN người mua -> chặn trước khi gọi HTTP ───────")
    msg = _goi(_si())
    check("trống cả hai ô tên -> throw", bool(msg))
    if msg:
        check("nêu đích danh hóa đơn", "HD-TEST" in msg, msg[:60])
        check("chỉ đúng nguyên nhân: ô Địa chỉ giao hàng",
              "Địa chỉ giao hàng" in msg)
        check("nói rõ ghi sổ rồi thì PHẢI HỦY mới sửa được "
              "(đừng để kế toán tưởng sửa tay được)",
              "hủy" in msg.lower())
        check("và dặn lần sau chọn địa chỉ trên bản NHÁP", "NHÁP" in msg)

    # ── 2. KHÔNG chặn oan: chỉ cần MỘT trong hai ô tên ────────────────
    print("-" * 78)
    print("── 2. Chỉ cần MỘT ô tên là qua chốt (không đòi đủ cả hai) ──────────")
    BUYER = "chưa có TÊN NGƯỜI MUA"
    for nhan, kw in (("chỉ có tên đơn vị", {"custom_tên_đơn_vị": "CTY TNHH ABC"}),
                     ("chỉ có tên người mua", {"custom_tên_người_mua": "Nguyễn Văn A"})):
        m = _goi(_si(**kw))
        check(f"{nhan} -> KHÔNG dừng ở chốt người mua",
              not (m and BUYER in m), (m or "")[:60])

    # ── 3. Khách lẻ không MST -> KHÔNG được chặn ──────────────────────
    #
    # Cạm bẫy 1. Dữ liệu thật trên site có hàng loạt "Khách lẻ Bạch Đằng",
    # "Trạm dừng nghỉ…" với MST trống — cá nhân không có mã số thuế, hóa đơn
    # cho họ vẫn hợp lệ. Đòi MST cho mọi hóa đơn là chặn oan cả mảng bán lẻ.
    print("-" * 78)
    print("── 3. Khách lẻ (có tên, KHÔNG MST, không điểm siêu thị) -> qua ─────")
    STORE_ADDR.clear()
    m = _goi(_si(custom_tên_người_mua="Khách lẻ Bạch Đằng"))
    check("không throw vì thiếu MST", not (m and "MÃ SỐ THUẾ" in m), (m or "")[:70])
    m = _goi(_si(custom_tên_người_mua="Khách lẻ", shipping_address_name="Bach Dang-Shipping"))
    check("có địa chỉ nhưng KHÔNG phải điểm siêu thị -> cũng không đòi MST",
          not (m and "MÃ SỐ THUẾ" in m), (m or "")[:70])

    # ── 4. Điểm SIÊU THỊ mà trống MST -> CHẶN ─────────────────────────
    print("-" * 78)
    print("── 4. Điểm siêu thị mà trống MST -> chặn, chỉ rõ sửa ở Địa chỉ ─────")
    STORE_ADDR.clear()
    STORE_ADDR.add("Co.opMart Ha Dong-Shipping")
    m = _goi(_si(custom_tên_đơn_vị="Co.opMart Hà Đông",
                 shipping_address_name="Co.opMart Ha Dong-Shipping"))
    check("điểm siêu thị + MST trống -> throw", bool(m and "MÃ SỐ THUẾ" in m), (m or "")[:70])
    if m:
        check("nêu đích danh địa chỉ phải sửa",
              "Co.opMart Ha Dong-Shipping" in m, m[:90])
    m = _goi(_si(custom_tên_đơn_vị="Co.opMart Hà Đông", custom_mã_số_thuế="0301175691",
                 shipping_address_name="Co.opMart Ha Dong-Shipping"))
    check("điểm siêu thị + CÓ MST -> qua chốt",
          not (m and ("MÃ SỐ THUẾ" in m or BUYER in m)), (m or "")[:70])

    # ── 5. Sửa đổi phải đặt cờ khóa về 0, KHÔNG phải None ─────────────
    print("-" * 78)
    print("── 5. Nhánh amend: custom_misa_no_locked về 0 (NULL là rơi bộ lọc) ─")
    sync = importlib.import_module("ketoan.api.misa_sync")
    FIELDS = ["custom_misa_ref_id", "custom_misa_status", "custom_misa_inv_no",
              "custom_misa_no_locked", "custom_misa_pushed_at", "amended_from"]
    doc = _D(amended_from="HD-00001", custom_misa_ref_id="ref-cu",
             custom_misa_inv_no="00006958", custom_misa_pushed_at="2026-10-01 10:00:00",
             custom_misa_no_locked=1)
    doc.meta = _Meta(FIELDS)
    sync.ensure_ref_id(doc)
    check("cờ khóa về 0", doc.custom_misa_no_locked == 0, repr(doc.custom_misa_no_locked))
    check("và KHÔNG phải None (vòng quét 2 lọc `= 0`, NULL là rơi khỏi bộ lọc)",
          doc.custom_misa_no_locked is not None)
    check("số hóa đơn của bản đã hủy bị dọn", doc.custom_misa_inv_no is None,
          repr(doc.custom_misa_inv_no))
    check("cờ đã-đẩy bị dọn", doc.custom_misa_pushed_at is None)
    check("RefID được cấp MỚI, không giữ của bản đã hủy",
          doc.custom_misa_ref_id and doc.custom_misa_ref_id != "ref-cu",
          str(doc.custom_misa_ref_id)[:20])

    # Hóa đơn THƯỜNG (không amend) thì KHÔNG được đụng tới cờ khóa — đó là cờ
    # người gán tay, xóa nó là mở đường cho vòng quét ghi số chết đè lên.
    doc2 = _D(custom_misa_ref_id="ref-dang-dung", custom_misa_no_locked=1)
    doc2.meta = _Meta(FIELDS)
    sync.ensure_ref_id(doc2)
    check("hóa đơn KHÔNG amend -> giữ nguyên cờ khóa người đã gán",
          doc2.custom_misa_no_locked == 1, repr(doc2.custom_misa_no_locked))
    check("và giữ nguyên RefID đang dùng",
          doc2.custom_misa_ref_id == "ref-dang-dung", str(doc2.custom_misa_ref_id))

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — chốt dừng trước khi gọi MISA, không chặn oan bán lẻ, "
              "và bản sửa đổi không thừa hưởng cờ khóa.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
