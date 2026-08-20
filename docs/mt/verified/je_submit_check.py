"""Kiểm tầng DUYỆT BÚT TOÁN (`ketoan/api/mt_je.py`, phần MT2-E).

    python3 docs/mt/verified/je_submit_check.py

Đây là chỗ DUY NHẤT của kênh MT mà tiền thật sự vào sổ, nên phép kiểm nhắm đúng
ba cách hỏng đã lường trước — và một cách hỏng thứ tư mà chỉ code mới gây ra:

  1. MỘT CÁI HỎNG KÉO THEO CẢ MẺ. Duyệt 5 cái mà cái thứ 3 nổ thì 4 cái còn lại
     vẫn phải vào sổ, và kết quả phải nói ĐÍCH DANH cái nào hỏng.
  2. GHI SỔ BẢNG KÊ CHƯA ĐỐI CHIẾU MÀ KHÔNG HỎI. Phải trả `needs_confirm` và
     KHÔNG submit gì cả, cho tới khi người xác nhận có ý thức.
  3. ĐỘNG VÀO CHỨNG TỪ KHÔNG PHẢI CỦA MÌNH. Tên gửi từ client phải bị lọc theo
     `custom_mt_source_dt` + công ty + docstatus — không bao giờ submit/xóa
     nhầm chứng từ của phân hệ khác.
  4. XÓA NHẦM BÚT TOÁN ĐÃ GHI SỔ. `delete_draft_*` chỉ được đụng bản nháp.

Chạy KHÔNG cần bench — stub frappe của `regression_check`, có bổ sung.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

COMPANY = "HGC"


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class World:
    """Sổ cái giả lập: bút toán, bảng kê, và cái gì đã thật sự được submit/xóa."""

    def __init__(self):
        # name -> (docstatus, source_dt, company, kind, advice, amount)
        self.jes = {}
        self.advices = {}          # name -> reconciled
        self.submitted = []
        self.deleted = []
        self.explode = set()       # tên JE sẽ nổ khi submit
        self.savepoints = []
        self.rollbacks = []

    def add_je(self, name, advice, kind="Thanh toán", amount=1000.0,
               docstatus=0, source_dt="MT Payment Advice", company=COMPANY):
        self.jes[name] = _D(name=name, docstatus=docstatus, company=company,
                            posting_date="2026-07-30", total_debit=amount,
                            custom_mt_kind=kind, custom_mt_source_dt=source_dt,
                            custom_mt_source_name=advice)
        return name

    def add_advice(self, name, reconciled=1):
        self.advices[name] = reconciled
        return name


def _install(world):
    import frappe

    def _sql(query, values=None, **kw):
        q = " ".join(str(query).split())
        if "tabJournal Entry`" in q and "je.name IN" in q:
            names = (values or {}).get("names") or ()
            return [world.jes[n] for n in names if n in world.jes]
        if "tabJournal Entry" in q and "GROUP BY docstatus" in q:
            adv = (values or {}).get("name")
            out = {}
            for j in world.jes.values():
                if j.custom_mt_source_name == adv and j.docstatus != 2:
                    out[j.docstatus] = out.get(j.docstatus, 0) + 1
            return [_D(docstatus=k, n=v) for k, v in out.items()]
        raise AssertionError("Truy vấn không được giả lập: " + q[:140])

    def _get_value(dt, name, field=None, **kw):
        if dt == "MT Payment Advice" and field == "reconciled":
            return world.advices.get(name, 1)
        if dt == "MT Payment Advice" and field == "je_state":
            return None
        return None

    def _set_value(dt, name, field, value, **kw):
        return None

    class _Doc:
        def __init__(self, name):
            self.name = name

        def submit(self):
            if self.name in world.explode:
                raise ValueError("TK 112 đã khóa kỳ")
            world.jes[self.name].docstatus = 1
            world.submitted.append(self.name)

    def _delete_doc(dt, name, **kw):
        if world.jes[name].docstatus != 0:
            raise ValueError("Không xóa được chứng từ đã ghi sổ")
        world.deleted.append(name)
        world.jes.pop(name)

    frappe.db.sql = _sql
    frappe.db.get_value = _get_value
    frappe.db.set_value = _set_value
    frappe.db.savepoint = lambda sp: world.savepoints.append(sp)
    frappe.db.rollback = lambda **kw: world.rollbacks.append(kw.get("save_point"))
    frappe.db.commit = lambda: None
    frappe.get_doc = lambda dt, name=None, **kw: _Doc(name)
    frappe.delete_doc = _delete_doc
    frappe.get_all = lambda dt, **kw: []
    # Người chạy phép kiểm là KẾ TOÁN TRƯỞNG — `guard_manager` đòi đúng vai trò
    # này. Không cắm role thì mọi lời gọi dừng ở dòng đầu và phép kiểm đo... chốt
    # quyền, chứ không đo logic duyệt (chốt quyền đã có phép kiểm AST riêng).
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import importlib

    import frappe

    w = World()
    _install(w)
    mj = importlib.import_module("ketoan.api.mt_je")

    # Bỏ qua chốt bảng/field và chốt công ty — đã có phép kiểm riêng, ở đây đo
    # đúng logic duyệt.
    mj._require_tables = lambda: None
    mj._company = lambda company=None: COMPANY
    frappe.db.table_exists = lambda dt: True

    # Chốt quyền CÓ chạy thật: kiểm một phát rằng người KHÔNG phải kế toán
    # trưởng bị chặn, rồi mới cắm vai trò để đo phần còn lại.
    frappe.get_roles = lambda *a, **kw: ["Ke Toan MT"]
    denied = False
    try:
        mj.submit_journal_entries(["JV-X"])
    except Exception as e:                                       # noqa: BLE001
        denied = "Kế toán trưởng" in str(e)
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]

    print("=" * 78)
    print("KIỂM TẦNG DUYỆT BÚT TOÁN MT")
    print("=" * 78)
    bad = 0

    print(f"  {'✅' if denied else '❌'} `Ke Toan MT` bấm duyệt -> bị chặn ngay dòng đầu "
          f"(Q4: không nới submit cho kế toán kênh)")
    bad += not denied

    # ── 1. Một cái hỏng KHÔNG kéo theo cả mẻ ──────────────────────────────
    print("-" * 78)
    w.add_advice("BK-1", reconciled=1)
    names = [w.add_je("JV-%d" % i, "BK-1", amount=1000 * i) for i in range(1, 6)]
    w.explode.add("JV-3")
    res = mj.submit_journal_entries(names)
    ok = (len(res["submitted"]) == 4 and len(res["failed"]) == 1
          and res["failed"][0]["name"] == "JV-3"
          and "TK 112 đã khóa kỳ" in res["failed"][0]["error"]
          and sorted(w.submitted) == ["JV-1", "JV-2", "JV-4", "JV-5"]
          and "mt_je_sub_2" in w.rollbacks)
    print(f"  {'✅' if ok else '❌'} 5 bút toán, cái thứ 3 nổ -> 4 cái kia VẪN ghi sổ, "
          f"lỗi báo đích danh JV-3, savepoint được rollback")
    if not ok:
        print(f"       └─ submitted={[x['name'] for x in res['submitted']]} "
              f"failed={res['failed']} rollbacks={w.rollbacks}")
    bad += not ok

    # ── 2. Bảng kê CHƯA đối chiếu -> đòi xác nhận, KHÔNG ghi gì ───────────
    print("-" * 78)
    w = World(); _install(w)
    w.add_advice("BK-X", reconciled=0)
    w.add_advice("BK-OK", reconciled=1)
    n1 = w.add_je("JV-A", "BK-X", amount=5000)
    n2 = w.add_je("JV-B", "BK-OK", amount=7000)
    res = mj.submit_journal_entries([n1, n2])
    ok = (res["needs_confirm"] and not res["submitted"] and not w.submitted
          and len(res["unreconciled"]) == 1
          and res["unreconciled"][0]["name"] == "JV-A")
    print(f"  {'✅' if ok else '❌'} bảng kê chưa tick đối chiếu -> needs_confirm, "
          f"KHÔNG ghi sổ cái nào (kể cả cái hợp lệ đi kèm)")
    if not ok:
        print(f"       └─ {res}")
    bad += not ok

    res = mj.submit_journal_entries([n1, n2], force_unreconciled=1)
    ok = (not res["needs_confirm"] and len(res["submitted"]) == 2
          and sorted(w.submitted) == ["JV-A", "JV-B"])
    print(f"  {'✅' if ok else '❌'} xác nhận có ý thức (force=1) -> ghi sổ cả hai")
    bad += not ok

    # ── 3. Chỉ động vào bút toán CỦA KÊNH MT, đúng công ty, đúng trạng thái ──
    print("-" * 78)
    w = World(); _install(w)
    w.add_advice("BK-2", reconciled=1)
    good = w.add_je("JV-OK", "BK-2")
    w.add_je("JV-NGOAI", "BK-2", source_dt="Purchase Invoice Import")
    w.add_je("JV-CTY-KHAC", "BK-2", company="CONG-TY-KHAC")
    w.add_je("JV-DA-GHI", "BK-2", docstatus=1)
    res = mj.submit_journal_entries([good, "JV-NGOAI", "JV-CTY-KHAC", "JV-DA-GHI", "JV-KHONG-CO"])
    errs = {f["name"]: f["error"] for f in res["failed"]}
    ok = (w.submitted == ["JV-OK"] and len(res["submitted"]) == 1
          and "kênh MT" in errs.get("JV-NGOAI", "")
          and "công ty khác" in errs.get("JV-CTY-KHAC", "")
          and "Trạng thái đã đổi" in errs.get("JV-DA-GHI", "")
          and "Không tìm thấy" in errs.get("JV-KHONG-CO", ""))
    print(f"  {'✅' if ok else '❌'} lọc đúng: chỉ ghi sổ bút toán của kênh MT, đúng công ty, "
          f"còn nháp — 4 cái còn lại bị từ chối kèm lý do")
    if not ok:
        print(f"       └─ submitted={w.submitted} errs={errs}")
    bad += not ok

    # ── 4. Xóa chỉ đụng bản NHÁP ─────────────────────────────────────────
    print("-" * 78)
    w = World(); _install(w)
    w.add_advice("BK-3", reconciled=1)
    d1 = w.add_je("JV-N1", "BK-3")
    w.add_je("JV-DA-GHI-2", "BK-3", docstatus=1)
    res = mj.delete_draft_journal_entries([d1, "JV-DA-GHI-2"])
    ok = (w.deleted == ["JV-N1"] and len(res["deleted"]) == 1
          and any("Trạng thái đã đổi" in f["error"] for f in res["failed"]))
    print(f"  {'✅' if ok else '❌'} xóa CHỈ đụng bản nháp; bút toán đã ghi sổ bị từ chối")
    if not ok:
        print(f"       └─ deleted={w.deleted} res={res}")
    bad += not ok

    # ── 5. Chuẩn hóa danh sách tên gửi lên ───────────────────────────────
    print("-" * 78)
    got = mj._je_names('["A","B","A"]')
    ok = got == ["A", "B"]
    print(f"  {'✅' if ok else '❌'} JSON + bỏ trùng + sắp xếp -> {got}")
    bad += not ok

    for arg, what in (([], "danh sách rỗng"), (["  "], "toàn khoảng trắng"),
                      ("không-phải-json", None)):
        try:
            got = mj._je_names(arg)
            if what:
                print(f"  ❌ {what} -> KHÔNG dừng (được {got})")
                bad += 1
            else:
                # chuỗi thường được coi là danh sách ngăn bởi dấu phẩy — hợp lệ
                ok = got == ["không-phải-json"]
                print(f"  {'✅' if ok else '❌'} chuỗi thường -> coi là một tên, không nổ")
                bad += not ok
        except Exception:
            if what:
                print(f"  ✅ {what} -> dừng")
            else:
                print("  ❌ chuỗi thường lại nổ")
                bad += 1

    try:
        mj._je_names(["JV-%d" % i for i in range(mj.MAX_BATCH + 1)])
        print(f"  ❌ quá {mj.MAX_BATCH} bút toán một lượt -> KHÔNG dừng")
        bad += 1
    except Exception:
        print(f"  ✅ quá {mj.MAX_BATCH} bút toán một lượt -> dừng "
              f"(duyệt cả nghìn cái là không ai soi kịp)")

    # ── 6. je_state tính lại sau khi duyệt ───────────────────────────────
    print("-" * 78)
    w = World(); _install(w)
    w.add_advice("BK-4", reconciled=1)
    a = w.add_je("JV-P1", "BK-4")
    b = w.add_je("JV-P2", "BK-4")
    st0 = mj.compute_je_state("BK-4")
    mj.submit_journal_entries([a])
    st1 = mj.compute_je_state("BK-4")
    mj.submit_journal_entries([b])
    st2 = mj.compute_je_state("BK-4")
    ok = (st0 == "Đã sinh nháp" and st1 == "Đã duyệt một phần" and st2 == "Đã duyệt đủ")
    print(f"  {'✅' if ok else '❌'} je_state: {st0} -> {st1} -> {st2}")
    bad += not ok

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — duyệt từng cái, hỏi trước khi ghi sổ, không đụng nhầm chứng từ"
          if not bad else f"HỎNG {bad} mục")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
