#!/usr/bin/env python3
"""Kiểm đường ĐỔI SỐ HÓA ĐƠN SANG BẢN THAY THẾ (MT2-S).

Nghiệp vụ: hàng đi, hóa đơn đã ký, đến kho siêu thị mới phát hiện bẹp méo và
không nhận đủ. MISA phát hành HÓA ĐƠN THAY THẾ mang số mới, số cũ chết. Chứng
từ ERPNext vẫn giữ số chết nên không khớp được với bảng kê thanh toán (vốn gọi
theo số mới) — hóa đơn nằm lại rổ "chưa thanh toán" vĩnh viễn.

Đây là đường GHI LÊN CHỨNG TỪ ĐÃ GHI SỔ. Bộ kiểm soi năm kiểu hỏng, mỗi kiểu
đều mất tiền thật:

  1. **Ghi đè ngược.** Vòng quét 2 của `poll_pending` hỏi MISA theo `ref_id`
     đang có trên chứng từ. Nếu ref_id vẫn trỏ hóa đơn ĐÃ CHẾT thì MISA trả số
     cũ và số vừa gán bị ghi đè — lặng lẽ, mỗi lần đồng bộ.
  2. **Hai chứng từ cùng một số.** Số hóa đơn là khóa mà tiền về đi theo; trùng
     số là một lần trả tiền tất toán hai chứng từ.
  3. **Mất dấu số cũ.** Xóa số cũ đi là mất khả năng giải trình với cơ quan thuế
     về chính hóa đơn đã hủy đó.
  4. **Lệch tiền giả.** Bản thay thế khai lại TOÀN BỘ hóa đơn đã sửa, trong khi
     phần hàng bị từ chối bên ERPNext đi bằng hóa đơn trả về. So vế chưa trừ trả
     về là mọi hóa đơn thay thế đứng "Lệch tiền" mãi mãi và đẻ ToDo mỗi lượt.
  5. **Nối nhầm bản MISA.** Gán số của một hóa đơn đã xóa bỏ / đã bị thay thế
     tiếp / đang thuộc chứng từ khác.

Chạy KHÔNG cần bench — stub frappe của `regression_check`. Không câu SQL nào
chạy thật, không DocType nào bị đụng.
"""

import ast
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


# Field custom_misa_* + vn_einvoice_* mà site đã migrate sẽ có.
SI_FIELDS = {
    "name", "docstatus", "company", "customer", "customer_name", "posting_date",
    "is_return", "return_against", "net_total", "total_taxes_and_charges", "grand_total",
    "custom_misa_inv_no", "custom_misa_inv_series", "custom_misa_inv_date",
    "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
    "custom_misa_ref_id", "custom_misa_status", "custom_misa_relation",
    "custom_misa_org_inv", "custom_misa_org_ref_id", "custom_misa_no_locked",
    "custom_misa_note", "vn_einvoice_number", "vn_einvoice_date",
}

# ── thế giới giả ───────────────────────────────────────────────────────────
# HD-04793 mang số 5449 (đã chết). Siêu thị không nhận đủ 1.000.000 nên có một
# hóa đơn trả về; MISA phát hành bản thay thế số 6537 = 4.893.696.
BASE_SI = _D(
    name="HD-04793", docstatus=1, company="HGC", customer="WIN", customer_name="WinCommerce",
    posting_date="2026-05-12", is_return=0, return_against=None,
    net_total=5357905, total_taxes_and_charges=535791, grand_total=5893696,
    custom_misa_inv_no="00005449", custom_misa_inv_series="1C26THG",
    custom_misa_ref_id="ref-cu-5449", custom_misa_status="Đã phát hành",
    custom_misa_relation="Hóa đơn mới", custom_misa_note="",
    vn_einvoice_number="00005449", custom_misa_no_locked=0,
)

SNAP_6537 = _D(
    name="SNAP-6537", inv_series="1C26THG", inv_no="00006537", inv_no_norm="6537",
    inv_date="2026-05-20", ref_id="ref-moi-6537", transaction_id="W1FPIZKNL0VZ",
    invoice_code="M2-26-XXX", einvoice_status="3", is_deleted=0,
    amount_before_vat=4448815, vat_amount=444881, total_amount=4893696,
    sales_invoice=None,
)


class World:
    """Cơ sở dữ liệu giả, khai bằng dữ liệu chứ không bằng mock từng lời gọi."""

    def __init__(self, si=None, snaps=None, others=None, returned=1000000.0, n_returns=1):
        self.si = _D(dict(si or BASE_SI))
        self.snaps = [_D(dict(s)) for s in (snaps if snaps is not None else [SNAP_6537])]
        self.others = [_D(dict(o)) for o in (others or [])]
        self.returned = returned
        self.n_returns = n_returns
        self.writes = []          # (doctype, name, values, update_modified)
        self.saved = []           # bất kỳ .save() nào — phải RỖNG

    # -- các lời gọi frappe mà tầng này dùng ------------------------------
    def get_value(self, doctype, name, fields=None, as_dict=False, **kw):
        if doctype == "MISA Invoice Snapshot":
            # `relink_snapshot` tra bản ghi rồi mới ghi. Không phục vụ ở đây thì
            # nhánh nối thành công không bao giờ được chạy trong bộ kiểm.
            if isinstance(name, dict):
                return None            # tra "SI này đã nối bản nào khác chưa"
            target = next((s for s in self.snaps if s.name == name), None)
            if not target:
                return None
            if isinstance(fields, str):
                return target.get(fields)
            return _D({f: target.get(f) for f in (fields or [])})
        if doctype != "Sales Invoice":
            return None
        target = self.si if name == self.si.name else \
            next((o for o in self.others if o.name == name), None)
        if not target:
            return None
        if isinstance(fields, str):
            return target.get(fields)
        return _D({f: target.get(f) for f in (fields or [])})

    def get_all(self, doctype, filters=None, fields=None, **kw):
        if doctype != "MISA Invoice Snapshot":
            return []
        f = filters or {}
        if "inv_no_norm" in f:
            return [s for s in self.snaps if s.inv_no_norm == f["inv_no_norm"]]
        if "sales_invoice" in f:
            return [s for s in self.snaps if s.sales_invoice == f["sales_invoice"]]
        return []

    def sql(self, query, params=None, as_dict=False, **kw):
        p = params or {}
        if "r.is_return = 1" in query:
            return [_D(n=self.n_returns, net_total=self.returned * 0.909091,
                       total_taxes_and_charges=self.returned * 0.090909,
                       grand_total=self.returned)]
        if "custom_misa_inv_no" in query and "TRIM(LEADING" in query:
            out = []
            for o in self.others:
                no = str(o.get("custom_misa_inv_no") or "").lstrip("0")
                if no == p.get("no") and o.name != p.get("me"):
                    out.append(_D(name=o.name, customer_name=o.customer_name,
                                  posting_date=o.posting_date, grand_total=o.grand_total,
                                  inv_series=o.custom_misa_inv_series,
                                  inv_no=o.custom_misa_inv_no, docstatus=o.docstatus))
            return out
        return []

    def set_value(self, doctype, name, values, update_modified=True, **kw):
        self.writes.append((doctype, name, dict(values) if isinstance(values, dict)
                            else {values: kw}, update_modified))


def install(world):
    import frappe

    frappe.db.get_value = world.get_value
    frappe.db.set_value = world.set_value
    frappe.db.sql = world.sql
    frappe.get_all = world.get_all
    frappe.db.table_exists = lambda *a, **k: True
    frappe.db.exists = lambda *a, **k: True
    frappe.db.count = lambda *a, **k: 0
    frappe.db.commit = lambda *a, **k: None
    frappe.db.has_column = lambda dt, c: c in SI_FIELDS
    frappe.get_meta = lambda dt="Sales Invoice": _D(has_field=lambda f: f in SI_FIELDS)
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    # MISA Settings giả: chỉ cần ngưỡng lệch tiền cho `relink_snapshot`.
    frappe.get_single = lambda dt: _D(amount_tolerance=1.0, base_url_webapp=None,
                                      use_code_route=0)
    frappe.get_cached_doc = frappe.get_single
    return frappe


def fields_of(plan):
    return {c["field"]: c for c in plan["changes"]}


def has(msgs, *needles):
    """Có câu nào chứa ĐỦ các mảnh này không."""
    return any(all(n in m for n in needles) for m in msgs)


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    install(World())

    mr = importlib.import_module("ketoan.api.misa_replace")
    sync = importlib.import_module("ketoan.api.misa_sync")

    print("=" * 82)
    print("KIỂM ĐƯỜNG ĐỔI SỐ HÓA ĐƠN SANG BẢN THAY THẾ")
    print("=" * 82)
    bad = 0

    # ── 1. Đường chuẩn: có bản thay thế trong bảng kê ────────────────────
    w = World()
    install(w)
    p = mr.preview("HD-04793", "6537")
    ch = fields_of(p)

    ok = p["ok"] and not p["blocks"]
    print(f"  {'✅' if ok else '❌'} có bản thay thế trong bảng kê -> đổi được"
          f"{'' if ok else ' — ' + ' · '.join(p['blocks'])}")
    bad += not ok

    ok = ch.get("custom_misa_inv_no", {}).get("new") == "6537" and \
        ch["custom_misa_inv_no"]["old"] == "00005449"
    print(f"  {'✅' if ok else '❌'} số hóa đơn 5449 -> 6537")
    bad += not ok

    ok = ch.get("custom_misa_org_inv", {}).get("new") == "1C26THG 5449"
    print(f"  {'✅' if ok else '❌'} SỐ CŨ KHÔNG BỊ XÓA — chuyển sang ô 'Hóa đơn gốc' "
          f"(mất dấu là mất đường giải trình thuế)")
    bad += not ok

    ok = ch.get("custom_misa_ref_id", {}).get("new") == "ref-moi-6537" and \
        ch.get("custom_misa_org_ref_id", {}).get("new") == "ref-cu-5449"
    print(f"  {'✅' if ok else '❌'} RefID chuyển sang bản ĐANG SỐNG, ref_id cũ giữ lại")
    bad += not ok

    ok = p["locked"] == 0 and p["mode"] == "theo_bang_ke"
    print(f"  {'✅' if ok else '❌'} biết RefID bản mới -> KHÔNG khóa đồng bộ (chứng từ vẫn "
          f"được theo dõi hủy/thay thế)")
    bad += not ok

    ok = ch.get("vn_einvoice_number", {}).get("new") == "6537"
    print(f"  {'✅' if ok else '❌'} cập nhật cả ô hiển thị `vn_einvoice_number` — để nguyên số "
          f"chết ở đó thì 6 màn hình vẫn hiện số cũ và đồng bộ báo 'Số hóa đơn lệch' mãi")
    bad += not ok

    ok = ch.get("custom_misa_relation", {}).get("new") == "Hóa đơn thay thế"
    print(f"  {'✅' if ok else '❌'} đánh dấu quan hệ 'Hóa đơn thay thế'")
    bad += not ok

    m = p["money"]
    ok = abs(m["erp_net"] - 4893696) < 1 and abs(m["misa"] - 4893696) < 1 and abs(m["diff"]) < 1
    print(f"  {'✅' if ok else '❌'} tiền so theo (hóa đơn − trả về) = {m['erp_net']:,.0f} và "
          f"khớp bản MISA — phép trừ bày ra chứ không giấu")
    bad += not ok

    # ── 2. Không có bản thay thế trong bảng kê -> BẮT BUỘC khóa ──────────
    print("-" * 82)
    w = World(snaps=[])
    install(w)
    p2 = mr.preview("HD-04793", "6537")
    ok = p2["ok"] and p2["locked"] == 1 and p2["mode"] == "gan_tay"
    print(f"  {'✅' if ok else '❌'} chưa biết RefID bản mới -> vẫn đổi được nhưng KHÓA đồng bộ")
    bad += not ok

    ok = fields_of(p2).get("custom_misa_no_locked", {}).get("new") == "1"
    print(f"  {'✅' if ok else '❌'} cờ khóa được ghi thật, không chỉ hiện trên màn hình")
    bad += not ok

    ok = has(p2["warnings"], "ghi đè số cũ trở lại")
    print(f"  {'✅' if ok else '❌'} nói THẲNG vì sao phải khóa: không khóa thì lần đồng bộ sau "
          f"ghi đè số cũ trở lại")
    bad += not ok

    ok = has(p2["warnings"], "Đồng bộ MISA")
    print(f"  {'✅' if ok else '❌'} chỉ đường về cách tốt hơn (kéo bảng kê trước), không để "
          f"người dùng mặc định chọn đường khóa")
    bad += not ok

    ok = has(p2["warnings"], "không còn tự phát hiện hóa đơn bị hủy")
    print(f"  {'✅' if ok else '❌'} nói rõ CÁI GIÁ của khóa, không bán khóa như bữa trưa miễn phí")
    bad += not ok

    # ── 3. Trùng số — chỗ mất tiền trực tiếp nhất ────────────────────────
    print("-" * 82)
    other = _D(dict(BASE_SI), name="HD-09999", customer_name="LOTTE",
               custom_misa_inv_no="00006537", custom_misa_inv_series="1C26THG")
    install(World(others=[other]))
    p3 = mr.preview("HD-04793", "6537")
    ok = not p3["ok"] and has(p3["blocks"], "HD-09999", "tất toán cả hai")
    print(f"  {'✅' if ok else '❌'} chứng từ khác đang mang cùng số + cùng ký hiệu -> CHẶN")
    bad += not ok

    other2 = _D(dict(other), name="HD-08888", custom_misa_inv_series="1C25THG")
    install(World(others=[other2]))
    p4 = mr.preview("HD-04793", "6537")
    ok = p4["ok"] and has(p4["warnings"], "HD-08888", "khác ký hiệu")
    print(f"  {'✅' if ok else '❌'} cùng số nhưng KHÁC ký hiệu -> cảnh báo chứ không chặn "
          f"(MISA đánh số lại từ đầu mỗi ký hiệu)")
    bad += not ok

    # ── 4. Bản MISA không được phép nối vào ──────────────────────────────
    print("-" * 82)
    for label, patch, needle in (
        ("đã xóa bỏ trên MISA", {"is_deleted": 1}, "ĐÃ XÓA BỎ"),
        ("chính nó cũng đã bị thay thế", {"einvoice_status": "7"}, "bản đang sống"),
        ("đang thuộc chứng từ khác", {"sales_invoice": "HD-07777"}, "HD-07777"),
    ):
        install(World(snaps=[_D(dict(SNAP_6537), **patch)]))
        pp = mr.preview("HD-04793", "6537")
        ok = not pp["ok"] and has(pp["blocks"], needle)
        print(f"  {'✅' if ok else '❌'} bản MISA {label} -> CHẶN")
        bad += not ok

    two = [_D(dict(SNAP_6537)),
           _D(dict(SNAP_6537), name="SNAP-B", inv_series="1C25THG")]
    install(World(snaps=two))
    p5 = mr.preview("HD-04793", "6537")
    ok = not p5["ok"] and has(p5["blocks"], "Nhập thêm ký hiệu")
    print(f"  {'✅' if ok else '❌'} hai bản MISA cùng số khác ký hiệu -> CHẶN, đòi ký hiệu "
          f"chứ không chọn hộ")
    bad += not ok

    install(World(snaps=two))
    p6 = mr.preview("HD-04793", "6537", "1C26THG")
    ok = p6["ok"]
    print(f"  {'✅' if ok else '❌'} khai thêm ký hiệu -> chỉ đúng một bản, đi tiếp được")
    bad += not ok

    # ── 5. Không có gì để đổi thì đừng ghi ───────────────────────────────
    print("-" * 82)
    same = _D(dict(BASE_SI), custom_misa_inv_no="6537", custom_misa_ref_id="ref-moi-6537",
              custom_misa_relation="Hóa đơn thay thế", custom_misa_org_inv="1C26THG 5449",
              vn_einvoice_number="6537", custom_misa_inv_date="2026-05-20",
              custom_misa_transaction_id="W1FPIZKNL0VZ", custom_misa_invoice_code="M2-26-XXX",
              vn_einvoice_date="2026-05-20")
    install(World(si=same, snaps=[_D(dict(SNAP_6537), sales_invoice="HD-04793")]))
    p7 = mr.preview("HD-04793", "6537")
    ok = not p7["ok"] and has(p7["blocks"], "không có gì để cập nhật")
    print(f"  {'✅' if ok else '❌'} đã đúng số rồi -> chặn, không ghi lại một dòng nhật ký rỗng")
    bad += not ok

    # Chạy lại lần hai KHÔNG được đẩy chính số mới vào ô "Hóa đơn gốc": lúc đó
    # `old_no` chính là số mới, ghi vào là XÓA MẤT dấu vết số đã chết — thứ duy
    # nhất còn dùng để giải trình với cơ quan thuế về hóa đơn đã hủy.
    ok = "custom_misa_org_inv" not in fields_of(p7)
    print(f"  {'✅' if ok else '❌'} chạy lại lần hai KHÔNG ghi đè ô 'Hóa đơn gốc' bằng chính "
          f"số mới")
    bad += not ok

    # ── 6. Vân tay kế hoạch — xem trước là BẮT BUỘC ──────────────────────
    print("-" * 82)
    w = World()
    install(w)
    p8 = mr.preview("HD-04793", "6537")
    try:
        mr.apply("HD-04793", "6537")
        print("  ❌ ghi được mà KHÔNG xem trước")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "xem trước" in str(e)
        print(f"  {'✅' if ok else '❌'} không có vân tay -> chặn, xem trước là bắt buộc")
        bad += not ok

    try:
        mr.apply("HD-04793", "6537", expected_hash="sai")
        print("  ❌ vân tay SAI vẫn ghi")
        bad += 1
    except Exception as e:                                          # noqa: BLE001
        ok = "không ghi gì cả" in str(e)
        print(f"  {'✅' if ok else '❌'} vân tay lệch -> dừng, không ghi gì cả")
        bad += not ok

    install(World(snaps=[]))
    p9 = mr.preview("HD-04793", "6537")
    ok = p9["plan_hash"] != p8["plan_hash"]
    print(f"  {'✅' if ok else '❌'} kế hoạch đổi (mất bản MISA) -> vân tay đổi theo")
    bad += not ok

    # ── 7. Ghi thật: db_set, không save(), có nhật ký ────────────────────
    print("-" * 82)
    w = World()
    install(w)
    p10 = mr.preview("HD-04793", "6537")
    r = mr.apply("HD-04793", "6537", expected_hash=p10["plan_hash"], reason="BB 12/2026")

    si_writes = [x for x in w.writes if x[0] == "Sales Invoice"]
    ok = len(si_writes) == 1 and si_writes[0][3] is False
    print(f"  {'✅' if ok else '❌'} ghi bằng db_set(update_modified=False) — KHÔNG save() chứng "
          f"từ đã ghi sổ")
    bad += not ok

    vals = si_writes[0][2] if si_writes else {}
    ok = vals.get("custom_misa_inv_no") == "6537" and vals.get("custom_misa_org_inv") == "1C26THG 5449"
    print(f"  {'✅' if ok else '❌'} ghi đúng số mới và giữ số cũ")
    bad += not ok

    note = str(vals.get("custom_misa_note") or "")
    ok = "5449" in note and "6537" in note and "BB 12/2026" in note
    print(f"  {'✅' if ok else '❌'} nhật ký ghi đủ: số cũ, số mới, lý do người nhập")
    bad += not ok

    ok = "5449" in r["message"] and "6537" in r["message"]
    print(f"  {'✅' if ok else '❌'} câu trả về nói rõ đã đổi từ số nào sang số nào")
    bad += not ok

    # Bản MISA CŨ phải được gỡ khỏi chứng từ, nếu không `relink_snapshot` từ chối
    # nối bản mới và bản thay thế nằm lại rổ "Chỉ có trên MISA".
    w = World(snaps=[_D(dict(SNAP_6537)),
                     _D(dict(SNAP_6537), name="SNAP-5449", inv_no="00005449",
                        inv_no_norm="5449", ref_id="ref-cu-5449", sales_invoice="HD-04793")])
    install(w)
    p11 = mr.preview("HD-04793", "6537")
    ok = has(p11["warnings"], "sẽ được GỠ ra")
    print(f"  {'✅' if ok else '❌'} xem trước báo bản MISA cũ sẽ bị gỡ khỏi chứng từ")
    bad += not ok

    r11 = mr.apply("HD-04793", "6537", expected_hash=p11["plan_hash"])
    snap_writes = [x for x in w.writes if x[0] == "MISA Invoice Snapshot"]

    ok = r11["snapshot"].get("linked") == "SNAP-6537" and not r11["snapshot"].get("error")
    print(f"  {'✅' if ok else '❌'} bản MISA thay thế được NỐI vào chứng từ — không nối thì nó "
          f"nằm lại rổ 'Chỉ có trên MISA' ngay sau khi vừa xử lý xong")
    bad += not ok

    # Đi qua `relink_snapshot` -> `_status` -> `erp_totals` thật. Đây là bằng
    # chứng đầu-cuối cho phép trừ hóa đơn trả về: không trừ thì cặp này bị gắn
    # "Lệch tiền" đúng vào lúc kế toán vừa xử lý xong.
    linked_w = [x for x in snap_writes if x[1] == "SNAP-6537"]
    ok = bool(linked_w) and linked_w[-1][2].get("match_status") == "Khớp"
    print(f"  {'✅' if ok else '❌'} sau khi nối, rổ đối soát xếp cặp này là KHỚP chứ không "
          f"'Lệch tiền' (5.893.696 − 1.000.000 = 4.893.696 = bản MISA)")
    bad += not ok
    unlinked = [x for x in snap_writes if x[1] == "SNAP-5449"]
    ok = bool(unlinked) and unlinked[0][2].get("sales_invoice") is None
    print(f"  {'✅' if ok else '❌'} bản MISA cũ được GỠ trước khi nối bản mới (nối trước là "
          f"hỏng cả hai: cũ vẫn nối, mới vẫn nằm rổ 'Chỉ có trên MISA')")
    bad += not ok

    ok = bool(unlinked) and unlinked[0][2].get("match_method") is None \
        and unlinked[0][2].get("match_confidence") is None
    print(f"  {'✅' if ok else '❌'} gỡ liên kết thì dọn luôn cách khớp/độ tin cậy cũ")
    bad += not ok

    # ── 8. poll_pending KHÔNG được ghi đè số đã khóa ─────────────────────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/misa_sync.py"), encoding="utf-8").read()
    body = src.split("def _poll_pending")[1]
    ok = 'watch_filters["custom_misa_no_locked"] = 0' in body
    print(f"  {'✅' if ok else '❌'} vòng quét 2 loại chứng từ đang khóa — ĐÂY là cái bẫy chính: "
          f"không loại thì mỗi lượt đồng bộ ghi số chết đè lên số người vừa gán")
    bad += not ok

    i_has = body.index('has_column("Sales Invoice", "custom_misa_no_locked")')
    i_use = body.index('watch_filters["custom_misa_no_locked"] = 0')
    ok = i_has < i_use
    print(f"  {'✅' if ok else '❌'} lọc theo cột mới chỉ khi cột ĐÃ tồn tại — site chưa chạy "
          f"patch thì lọc theo cột chưa có là gãy nguyên job đồng bộ")
    bad += not ok

    # ── 9. So tiền: chỉ trừ trả về cho HÓA ĐƠN THAY THẾ ──────────────────
    print("-" * 82)
    install(World())
    si = _D(name="HD-04793", net_total=5357905, total_taxes_and_charges=535791,
            grand_total=5893696)

    e1 = sync.erp_totals(si, "Hóa đơn thay thế")
    ok = abs(e1["grand_total"] - 4893696) < 1
    print(f"  {'✅' if ok else '❌'} hóa đơn THAY THẾ -> vế ERPNext trừ hóa đơn trả về "
          f"({e1['grand_total']:,.0f})")
    bad += not ok

    for rel in ("Hóa đơn mới", "Hóa đơn điều chỉnh", "Bị thay thế", None):
        e2 = sync.erp_totals(si, rel)
        ok = abs(e2["grand_total"] - 5893696) < 1
        print(f"  {'✅' if ok else '❌'} quan hệ '{rel}' -> KHÔNG trừ trả về (bản MISA vẫn giữ "
              f"tổng cũ, trừ vào là tạo lệch giả)")
        bad += not ok

    misa = {"TotalAmount": 4893696, "TotalAmountWithoutVAT": 4448815, "TotalVATAmount": 444881}
    ok = not sync.check_amount_drift(si, misa, 1.0, e1)
    print(f"  {'✅' if ok else '❌'} so 3 vế theo số đã trừ -> KHỚP, không đẻ 'Lệch tiền' giả")
    bad += not ok

    ok = bool(sync.check_amount_drift(si, misa, 1.0))
    print(f"  {'✅' if ok else '❌'} so theo số CHƯA trừ -> lệch (chứng minh phép trừ là thứ "
          f"quyết định, không phải nới lỏng ngưỡng)")
    bad += not ok

    # `_status` quyết bằng `einvoice_status`. Cả hai chỗ gọi phải THẬT SỰ nạp
    # cột đó: `.get()` trả None nên thiếu cột không báo lỗi, chỉ lặng lẽ biến
    # nhánh "Đã thay thế" và nhánh miễn so tiền cho hóa đơn điều chỉnh thành
    # code chết — và mọi bản nối tay bị gắn "Lệch tiền".
    csrc = open(os.path.join(rc.REPO, "ketoan/api/misa_reconcile.py"), encoding="utf-8").read()
    for fn in ("match_snapshots", "relink_snapshot"):
        seg = re.split(r"\n(?=@frappe\.whitelist|def )", csrc.split("def " + fn)[1])[0]
        ok = '"einvoice_status"' in seg
        print(f"  {'✅' if ok else '❌'} {fn}() nạp cột `einvoice_status` cho `_status`")
        bad += not ok

    # ── 10. Guard ở DÒNG ĐẦU mọi whitelisted method ──────────────────────
    print("-" * 82)
    rsrc = open(os.path.join(rc.REPO, "ketoan/api/misa_replace.py"), encoding="utf-8").read()
    tree = ast.parse(rsrc)
    n_wl = 0
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "whitelist"
                   for d in node.decorator_list):
            continue
        n_wl += 1
        first = node.body[1] if isinstance(node.body[0], ast.Expr) and \
            isinstance(getattr(node.body[0], "value", None), ast.Constant) else node.body[0]
        got = isinstance(first, ast.Expr) and isinstance(first.value, ast.Call) and \
            getattr(first.value.func, "id", "") == "guard_manager"
        print(f"  {'✅' if got else '❌'} {node.name}() gọi guard_manager() ở dòng đầu")
        bad += not got
    ok = n_wl >= 4
    print(f"  {'✅' if ok else '❌'} soi được {n_wl} whitelisted method (đủ 4: preview/apply/"
          f"search/list_locked)")
    bad += not ok

    ok = ".save(" not in rsrc
    print(f"  {'✅' if ok else '❌'} không có lời gọi .save() nào trong module")
    bad += not ok

    # ── 11. Field mới đi kèm patch mới ───────────────────────────────────
    print("-" * 82)
    inst = open(os.path.join(rc.REPO, "ketoan/install.py"), encoding="utf-8").read()
    ok = '"fieldname": "custom_misa_no_locked"' in inst and \
        re.search(r'"custom_misa_no_locked".*?"allow_on_submit": 1', inst, re.S) is not None
    print(f"  {'✅' if ok else '❌'} field khai trong install.py và allow_on_submit")
    bad += not ok

    patches = open(os.path.join(rc.REPO, "ketoan/patches.txt"), encoding="utf-8").read()
    ok = "v0_0_17.misa_no_locked" in patches
    print(f"  {'✅' if ok else '❌'} có patch riêng (THÊM FIELD MỚI = THÊM PATCH MỚI)")
    bad += not ok

    psrc = open(os.path.join(rc.REPO, "ketoan/patches/v0_0_17/misa_no_locked.py"),
                encoding="utf-8").read()
    ok = "IS NULL" in psrc and "custom_misa_no_locked = 0" in psrc
    print(f"  {'✅' if ok else '❌'} patch điền 0 cho dòng cũ — cột Check mới là NULL, mà NULL "
          f"không bằng 0 nên MỌI hóa đơn cũ sẽ rơi khỏi vòng quét 2")
    bad += not ok

    # ── 12. Có đường bấm trên portal, và người dùng thấy hệ quả ──────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/vat.js"), encoding="utf-8").read()
    ajs = open(os.path.join(rc.REPO, "ketoan/public/ketoan/lib/api.js"), encoding="utf-8").read()
    for name in ("vatReplacePreview", "vatReplaceApply", "vatReplaceSearch", "vatLockedList"):
        ok = name in ajs and name in js
        print(f"  {'✅' if ok else '❌'} api.js khai `{name}` và màn hình có dùng")
        bad += not ok

    ok = "expected_hash: p.plan_hash" in js
    print(f"  {'✅' if ok else '❌'} màn hình gửi kèm vân tay kế hoạch vừa hiện")
    bad += not ok

    ok = "ĐÃ GHI SỔ" in js and "không có nút hoàn tác" in js
    print(f"  {'✅' if ok else '❌'} hỏi xác nhận, nói rõ đây là chứng từ đã ghi sổ và không "
          f"hoàn tác được")
    bad += not ok

    ok = "showLocked" in js
    print(f"  {'✅' if ok else '❌'} bày danh sách chứng từ đang khóa — khóa mà không ai nhìn "
          f"thấy thì không bao giờ được gỡ")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — số thay thế gán được lên chứng từ đã ghi sổ, số cũ không mất, "
          "đồng bộ không ghi đè ngược, và không hai chứng từ nào cùng một số")
    return 0


if __name__ == "__main__":
    sys.exit(main())
