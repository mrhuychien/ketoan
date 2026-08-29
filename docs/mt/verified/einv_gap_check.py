#!/usr/bin/env python3
"""Kiểm màn SOÁT HÓA ĐƠN BỎ SÓT SỐ HÓA ĐƠN ĐIỆN TỬ.

════════════════════════════════════════════════════════════════════════════
PHÉP CHIA LÀ TOÀN BỘ GIÁ TRỊ CỦA MÀN NÀY
════════════════════════════════════════════════════════════════════════════

Danh sách phẳng "mọi hóa đơn trống ô số HĐĐT" gần như vô dụng: phần lớn là
hàng vừa giao, chưa tới lượt xuất. Việc thật nằm lẫn trong hàng trăm dòng bình
thường, và kế toán bỏ luôn cả màn hình.

Cả màn xoay quanh MỘT phép chia, quanh MỐC = hóa đơn mới nhất ĐÃ điền số:

    cũ hơn mốc mà trống  ->  BỎ SÓT      (đã đi qua rồi mà không xuất)
    mới hơn mốc mà trống ->  CHƯA TỚI LƯỢT

Chia sai theo hướng nào cũng hỏng: kêu oan thì kế toán tắt cảnh báo, bỏ lọt thì
lỗ hổng chứng từ nằm im. Bộ kiểm này khóa phép chia đó ở mọi hình dạng dữ liệu.

════════════════════════════════════════════════════════════════════════════
BA CHỐT CHẶN KHÁC
════════════════════════════════════════════════════════════════════════════

1. MỐC TÍNH RIÊNG TỪNG CHUỖI. Mỗi chuỗi có nhịp xuất riêng — mốc chung thì
   chuỗi chậm nhất bị chấm bỏ sót toàn bộ, chuỗi nhanh không bao giờ lộ gì.

2. CHƯA CÓ MỐC THÌ KHÔNG CHẤM AI. Chuỗi chưa hóa đơn nào có số là "chưa bắt
   đầu", không phải "sai sót hàng loạt".

3. KHÔNG PHẢI CON SỐ CỦA THẺ HAI CUỐN SỔ. Màn kia chỉ nhìn phần CÒN NỢ; màn
   này nhìn MỌI hóa đơn bán. Hai con số không bao giờ bằng nhau, nên màn hình
   phải NÓI RA — không thì có ngày ai đó đem hai màn đi đối chiếu.

Chạy KHÔNG cần bench — stub frappe của `regression_check`.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regression_check as rc  # noqa: E402


def inv(name, date, has_e, chain="WinCommerce", amount=10.0, customer=None):
    return {"name": name, "posting_date": date, "has_einvoice": has_e,
            "grand_total": amount, "chain": chain,
            "customer": customer or ("K-" + chain.replace(" ", "")),
            "customer_name": chain}


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    import frappe

    frappe.db.has_column = lambda dt, c: True
    frappe.db.table_exists = lambda dt: True
    frappe.get_roles = lambda *a, **kw: ["Ke Toan Truong"]
    frappe.get_meta = lambda dt: type("M", (), {"has_field": staticmethod(lambda f: True)})()

    me = importlib.import_module("ketoan.api.mt_einv")

    print("=" * 82)
    print("KIỂM SOÁT HÓA ĐƠN BỎ SÓT SỐ HĐĐT")
    print("=" * 82)
    bad = 0

    # ── 1. Phép chia quanh MỐC ──────────────────────────────────────────
    rows = [inv("SI-01", "2026-03-01", 1), inv("SI-02", "2026-03-05", 0),
            inv("SI-03", "2026-04-01", 1), inv("SI-04", "2026-04-10", 0),
            inv("SI-05", "2026-05-01", 0)]
    f, m, b = me._split(rows)
    ok = f["name"] == "SI-03" and [x["name"] for x in m] == ["SI-02"] \
        and [x["name"] for x in b] == ["SI-04", "SI-05"]
    print(f"  {'✅' if ok else '❌'} mốc = tờ ĐÃ ĐIỀN mới nhất (SI-03); cũ hơn nó mà trống là "
          f"BỎ SÓT (SI-02), mới hơn là chưa tới lượt")
    bad += not ok

    # ── 2. Cùng ngày — chỉ tờ đứng TRƯỚC mốc mới bị chấm ────────────────
    #
    # So bằng CẢ (ngày, tên). Chỉ so ngày thì sai cả hai hướng: hoặc chấm oan
    # tờ đứng sau, hoặc bỏ lọt tờ đứng trước.
    print("-" * 82)
    rows = [inv("SI-A", "2026-04-01", 0), inv("SI-B", "2026-04-01", 1),
            inv("SI-C", "2026-04-01", 0)]
    f, m, b = me._split(rows)
    ok = [x["name"] for x in m] == ["SI-A"] and [x["name"] for x in b] == ["SI-C"]
    print(f"  {'✅' if ok else '❌'} cùng ngày: chỉ tờ đứng TRƯỚC mốc bị chấm bỏ sót "
          f"(bỏ sót={[x['name'] for x in m]}, chưa tới={[x['name'] for x in b]})")
    bad += not ok

    # ── 3. Chưa có mốc -> KHÔNG chấm ai ─────────────────────────────────
    print("-" * 82)
    f, m, b = me._split([inv("SI-X", "2026-01-01", 0), inv("SI-Y", "2026-02-01", 0)])
    ok = f is None and not m and len(b) == 2
    print(f"  {'✅' if ok else '❌'} chưa hóa đơn nào có số -> không mốc, KHÔNG chấm bỏ sót cho ai. "
          f"Chấm cả rổ là biến 'chưa bắt đầu' thành 'sai sót hàng loạt'")
    bad += not ok

    f, m, b = me._split([inv("SI-1", "2026-01-01", 1), inv("SI-2", "2026-02-01", 1)])
    ok = f["name"] == "SI-2" and not m and not b
    print(f"  {'✅' if ok else '❌'} xuất hết -> không kêu gì")
    bad += not ok

    f, m, b = me._split([])
    ok = f is None and not m and not b
    print(f"  {'✅' if ok else '❌'} rỗng -> rỗng, không nổ")
    bad += not ok

    # ── 4. MỐC TÍNH RIÊNG TỪNG CHUỖI ────────────────────────────────────
    #
    # Win xuất tới 04/2026, LOTTE mới tới 01/2026. Lấy mốc CHUNG (04/2026) thì
    # hóa đơn 02/2026 của LOTTE bị chấm bỏ sót oan — nó chỉ đang chậm nhịp.
    print("-" * 82)
    FIX = [
        inv("W-1", "2026-01-10", 1, "WinCommerce"),
        inv("W-2", "2026-02-10", 0, "WinCommerce"),          # BỎ SÓT thật
        inv("W-3", "2026-04-01", 1, "WinCommerce"),
        inv("W-4", "2026-05-01", 0, "WinCommerce"),          # chưa tới lượt
        inv("L-1", "2026-01-05", 1, "LOTTE"),
        inv("L-2", "2026-02-20", 0, "LOTTE"),                # chưa tới lượt của LOTTE
    ]
    me._scan = lambda company, chain=None: ("EXPR", [dict(r) for r in FIX])
    me._returns_missing = lambda company, chain=None: {"count": 0, "amount": 0.0}
    me._count_skipped = lambda company, chain=None: {"count": 0, "amount": 0.0,
                                                     "supported": True}
    me._company = lambda company=None: "HGC"
    mtmod = importlib.import_module("ketoan.api.mt")
    mtmod._customer_chain_map = lambda: (
        {"K-WinCommerce": "WinCommerce", "K-LOTTE": "LOTTE"}, [])
    me._customer_chain_map = mtmod._customer_chain_map

    d = me.get_gaps()
    names = [r["name"] for r in d["rows"]]
    ok = names == ["W-2"]
    print(f"  {'✅' if ok else '❌'} mốc riêng từng chuỗi -> chỉ W-2 bỏ sót; L-2 (02/2026) KHÔNG "
          f"bị chấm dù cũ hơn mốc của Win. Thực tế: {names}")
    bad += not ok

    by = {c["chain"]: c for c in d["chains"]}
    ok = (by["WinCommerce"]["frontier"]["name"] == "W-3"
          and by["LOTTE"]["frontier"]["name"] == "L-1")
    print(f"  {'✅' if ok else '❌'} mỗi chuỗi in ra MỐC của riêng nó — con số dựng trên phỏng "
          f"đoán thì phỏng đoán phải hiện, không giấu")
    bad += not ok

    ok = d["missed"]["count"] == 1 and d["backlog"]["count"] == 2
    print(f"  {'✅' if ok else '❌'} tổng: 1 bỏ sót / 2 chưa tới lượt "
          f"({d['missed']['count']} / {d['backlog']['count']})")
    bad += not ok

    ok = d["missed"]["count"] + d["backlog"]["count"] == sum(
        1 for r in FIX if not r["has_einvoice"])
    print(f"  {'✅' if ok else '❌'} hai vế cộng lại = MỌI hóa đơn trống số — không tờ nào rơi "
          f"ra ngoài cả hai nhóm")
    bad += not ok

    # ── 5. Lọc theo một chuỗi -> mốc của chính chuỗi đó ─────────────────
    print("-" * 82)
    me._scan = lambda company, chain=None: (
        "EXPR", [dict(r) for r in FIX if r["chain"] == (chain or r["chain"])])
    d1 = me.get_gaps(chain="LOTTE")
    ok = d1["frontier"] and d1["frontier"]["name"] == "L-1" and not d1["rows"]
    print(f"  {'✅' if ok else '❌'} vào LOTTE -> mốc L-1, không tờ nào bỏ sót "
          f"(đúng: LOTTE chỉ đang chậm nhịp)")
    bad += not ok

    # ── 5b. `scope` — LIỆT KÊ tập nào, nhưng ĐẾM thì luôn đủ cả ba ──────
    #
    # Bước "Chờ xuất hóa đơn" của Win cần đúng tập `chua_toi_luot`: hàng đã ghi
    # sổ, chưa phát hành HĐĐT. Nó có sẵn trong ERPNext — không phải nhập tay như
    # `MT Win Pending` (thứ theo dõi đợt giao CHƯA có hóa đơn, tập khác hẳn).
    print("-" * 82)
    me._scan = lambda company, chain=None: ("EXPR", [dict(r) for r in FIX])
    got = {}
    for sc in ("bo_sot", "chua_toi_luot", "tat_ca"):
        d3 = me.get_gaps(scope=sc)
        got[sc] = sorted(r["name"] for r in d3["rows"])
    ok = (got["bo_sot"] == ["W-2"] and got["chua_toi_luot"] == ["L-2", "W-4"]
          and got["tat_ca"] == ["L-2", "W-2", "W-4"])
    print(f"  {'✅' if ok else '❌'} ba phạm vi liệt kê đúng tập của nó: {got}")
    bad += not ok

    d3 = me.get_gaps(scope="chua_toi_luot")
    ok = d3["missed"]["count"] == 1 and d3["backlog"]["count"] == 2
    print(f"  {'✅' if ok else '❌'} đổi phạm vi KHÔNG làm biến mất con số tổng — vẫn đếm đủ cả "
          f"hai nhóm ({d3['missed']['count']} bỏ sót / {d3['backlog']['count']} chưa tới lượt)")
    bad += not ok

    ok = sorted(got["tat_ca"]) == sorted(got["bo_sot"] + got["chua_toi_luot"])
    print(f"  {'✅' if ok else '❌'} `tat_ca` đúng bằng hai tập kia cộng lại, không trùng không sót")
    bad += not ok

    # Phải chặn bằng THÔNG BÁO RÕ, không phải bằng một `KeyError` tình cờ.
    # Gỡ mệnh đề kiểm mà vẫn "nổ" thì phép kiểm cũ vẫn xanh, còn người dùng
    # nhận một lỗi 500 không đọc được.
    try:
        me.get_gaps(scope="bịa")
        ok, msg = False, "(không chặn)"
    except Exception as e:
        msg = str(e)
        # Phải là THÔNG BÁO ĐỌC ĐƯỢC, không phải một `KeyError` tình cờ.
        # `KeyError("bịa")` cũng chứa chữ "bịa" — dò tên giá trị là chưa đủ.
        ok = "Phạm vi không hợp lệ" in msg and "bịa" in msg
    print(f"  {'✅' if ok else '❌'} phạm vi lạ -> CHẶN kèm thông báo nói RA giá trị sai "
          f"({msg[:60]!r}). Im lặng lấy mặc định là màn hình tưởng đang xem một tập, "
          f"thật ra xem tập khác")
    bad += not ok

    # ── 5c. BỎ QUA — ranh giới của nó ───────────────────────────────────
    #
    # Bỏ qua CHỈ ẩn dòng khỏi danh sách này. Nếu có ngày tầng công nợ hay tầng
    # sổ cái đọc cờ đó, nó thành đường tắt để GIẤU CÔNG NỢ — và đó là chuyện
    # khác hẳn, phải bàn lại từ đầu. Bộ kiểm khóa ranh giới ấy.
    print("-" * 82)
    esrc = rc.code_only(os.path.join(rc.REPO, "ketoan/api/mt_einv.py"))
    leak = [f for f in ("mt_debt.py", "mt_gl_bridge.py", "mt_hub.py", "mt.py")
            if "custom_mt_einv_skip" in rc.code_only(
                os.path.join(rc.REPO, "ketoan/api", f))]
    ok = not leak
    print(f"  {'✅' if ok else '❌'} cờ bỏ qua KHÔNG rò sang tầng công nợ / sổ cái / tổng quan "
          f"— bỏ qua một hóa đơn không được làm nó hết nợ{'' if ok else ' — rò: ' + str(leak)}")
    bad += not ok

    ok = "guard_manager()" in esrc
    print(f"  {'✅' if ok else '❌'} ghi (bỏ qua) cần quyền TRƯỞNG, không phải ai xem cũng bấm được")
    bad += not ok

    seg_sk = esrc.split("def set_skip")[1].split("\n@frappe")[0]
    ok = "db_set(" in seg_sk and "update_modified=False" in seg_sk and ".save(" not in seg_sk
    print(f"  {'✅' if ok else '❌'} ghi bằng `db_set(..., update_modified=False)`, KHÔNG `save()` "
          f"trên chứng từ đã ghi sổ")
    bad += not ok

    # GỌI THẬT, không dò chữ.
    #
    # Bản đầu khẳng định `"MIN_NOTE" in seg` — và nó VẪN ĐẠT khi mệnh đề kiểm đã
    # bị gỡ, vì tên hằng còn nằm trong câu thông báo ngay bên dưới. Dò chữ chỉ
    # chứng minh CÓ NHẮC TỚI, không chứng minh CÓ CHẶN.
    frappe.db.exists = lambda dt, nm=None: True
    frappe.db.get_value = lambda dt, nm, flds, as_dict=False: (
        frappe._dict({"company": "HGC", "docstatus": 1, "is_return": 0})
        if as_dict else 1)
    frappe.db.has_column = lambda dt, c: True
    frappe.db.commit = lambda: None

    class _FakeSI:
        """Chứng từ giả — chỉ đủ để bắt `db_set`, không giả vờ là Sales Invoice."""

        def __init__(self):
            self.written = {}

        def db_set(self, k, v, update_modified=True):
            # Bắt luôn ở đây: `update_modified=True` trên chứng từ đã ghi sổ là
            # đụng `modified`, tức làm mọi phiên đang mở form bị TimestampMismatch.
            assert update_modified is False, "db_set phải dùng update_modified=False"
            self.written[k] = v

    fake = _FakeSI()
    frappe.get_doc = lambda dt, nm: fake
    for note, want_block in (("", True), ("   ", True), ("abc", True),
                             ("hóa đơn nội bộ", False)):
        try:
            me.set_skip("SI-1", skip=1, note=note)
            blocked, msg = False, ""
        except Exception as e:
            blocked, msg = True, str(e)
        if blocked != want_block:
            bad += 1
            print(f"     ❌ lý do {note!r} -> chặn={blocked}, mong {want_block} ({msg[:50]})")
            break
    else:
        print(f"  ✅ LÝ DO bắt buộc khi bỏ qua (trống · toàn khoảng trắng · quá ngắn đều bị "
              f"chặn) — bỏ qua không lý do thì sáu tháng sau không ai dựng lại được quyết "
              f"định, cũng không ai dám mở lại")

    # MỞ LẠI thì KHÔNG đòi lý do — đòi là dựng một rào cản để người ta thôi mở.
    try:
        me.set_skip("SI-1", skip=0)
        ok = True
    except Exception as e:
        ok, _m = False, str(e)
    print(f"  {'✅' if ok else '❌'} nhưng MỞ LẠI thì không đòi lý do — đòi là dựng rào cản để "
          f"người ta thôi mở, và bỏ qua thành một chiều")
    bad += not ok

    ok = "docstatus" in seg_sk
    print(f"  {'✅' if ok else '❌'} chỉ bỏ qua được hóa đơn ĐÃ GHI SỔ — hóa đơn nháp/đã hủy không "
          f"nằm trong danh sách, đánh dấu nó là ghi một dấu vô nghĩa lên chứng từ")
    bad += not ok

    ok = "def list_skipped" in esrc
    print(f"  {'✅' if ok else '❌'} có chỗ XEM LẠI và mở ra — bỏ qua mà không xem lại được thì nó "
          f"là thùng rác một chiều")
    bad += not ok

    ok = '"skipped": _count_skipped' in esrc
    print(f"  {'✅' if ok else '❌'} và LUÔN đếm số tờ đang bị bỏ qua — ẩn dòng mà không nói ẩn "
          f"bao nhiêu thì '0 việc' không phân biệt được với 'ai đó bỏ qua sạch'")
    bad += not ok

    # Cờ phải lọc ở CẢ HAI câu quét. Chỉ lọc câu chính thì tờ bị bỏ qua vẫn
    # tham gia dựng MỐC, tức một tờ người ta cố ý loại vẫn quyết định tờ nào bị
    # chấm là bỏ sót.
    # Đếm CHỖ DÙNG trong ĐÚNG hai hàm quét, không đếm cả dòng khai.
    #
    # Bản đầu đếm `_skip_clause()` trên cả file và đòi `>= 2` — nhưng dòng
    # `def _skip_clause():` cũng khớp, nên gỡ một chỗ dùng vẫn còn 2 và phép
    # kiểm vẫn xanh. Lại đúng kiểu "thấy định nghĩa tưởng là chỗ dùng".
    miss = [fn for fn in ("_scan", "_returns_missing")
            if "_skip_clause()" not in esrc.split("def %s" % fn)[1].split("\ndef ")[0]]
    ok = not miss
    print(f"  {'✅' if ok else '❌'} cờ lọc trong CẢ `_scan` LẪN `_returns_missing` — thiếu ở "
          f"`_scan` thì tờ đã bỏ qua vẫn tham gia dựng MỐC"
          f"{'' if ok else ' — thiếu: ' + str(miss)}")
    bad += not ok

    # Patch: THÊM FIELD MỚI = THÊM PATCH MỚI.
    ptxt = open(os.path.join(rc.REPO, "ketoan/patches.txt"), encoding="utf-8").read()
    ok = "v0_0_18.mt_einv_skip" in ptxt and os.path.exists(
        os.path.join(rc.REPO, "ketoan/patches/v0_0_18/mt_einv_skip.py"))
    print(f"  {'✅' if ok else '❌'} có patch riêng khai field mới (THÊM FIELD = THÊM PATCH)")
    bad += not ok

    isrc = open(os.path.join(rc.REPO, "ketoan/install.py"), encoding="utf-8").read()
    # Đếm chỗ KHAI (`"fieldname":`), không đếm mọi lần tên ô xuất hiện.
    # `depends_on` / `insert_after` trỏ về nó là đúng và cần — đếm cả chúng là
    # phép kiểm bắt lỗi ở chỗ không có lỗi.
    n_decl = isrc.count('"fieldname": "custom_mt_einv_skip"')
    seg_si = isrc.split('"Sales Invoice": [')[1].split("\n}")[0]
    n_aos = seg_si.count('"allow_on_submit": 1')
    ok = n_decl == 1 and n_aos == 4
    print(f"  {'✅' if ok else '❌'} field khai ĐÚNG MỘT LẦN ({n_decl}), và CẢ BỐN ô đều có "
          f"`allow_on_submit` ({n_aos}/4) — thiếu là ghi lên hóa đơn đã submit sẽ nổ")
    bad += not ok

    psrc = open(os.path.join(rc.REPO, "ketoan/patches/v0_0_18/mt_einv_skip.py"),
                encoding="utf-8").read()
    ok = "IS NULL" in psrc
    print(f"  {'✅' if ok else '❌'} patch chuẩn hóa NULL về 0 — cột Check thêm vào bảng có sẵn dữ "
          f"liệu được điền NULL, và NULL không bằng 0 trong bộ lọc Desk")
    bad += not ok

    # ── 6. Site chưa có ô số HĐĐT -> nói ra, KHÔNG trả danh sách rỗng ───
    print("-" * 82)
    me._scan = lambda company, chain=None: (None, [])
    d2 = me.get_gaps()
    ok = d2["supported"] is False and d2["note"] and not d2["rows"]
    print(f"  {'✅' if ok else '❌'} chưa có ô số HĐĐT -> `supported=False` kèm lý do. Trả danh "
          f"sách rỗng câm là kế toán đọc thành 'không sót tờ nào'")
    bad += not ok

    # ── 7. Không dựng định nghĩa "đã xuất HĐĐT" lần thứ hai ─────────────
    print("-" * 82)
    src = open(os.path.join(rc.REPO, "ketoan/api/mt_einv.py"), encoding="utf-8").read()
    body = src.split('"""', 2)[-1]
    ok = "einvoice_issued_expr" in body and "vn_einvoice_number" not in body
    print(f"  {'✅' if ok else '❌'} dùng CHUNG `einvoice_issued_expr` của `mt.py`, không chép "
          f"luật 'đã xuất HĐĐT' lần thứ hai")
    bad += not ok

    ok = "guard_mt()" in body and "_require_tables()" in body
    print(f"  {'✅' if ok else '❌'} whitelisted method có guard")
    bad += not ok

    # ── 8. Giao diện PHẢI nói nó khác thẻ hai cuốn sổ ────────────────────
    print("-" * 82)
    js = open(os.path.join(rc.REPO, "ketoan/public/ketoan/views/mt.js"), encoding="utf-8").read()
    ok = "loadEinvGaps" in js and "g-soat-hddt" in js
    print(f"  {'✅' if ok else '❌'} portal có màn soát và tuyến vào nó")
    bad += not ok

    ok = 'KHÔNG phải con số của thẻ "hai cuốn sổ"' in js
    print(f"  {'✅' if ok else '❌'} màn hình NÓI RA nó khác thẻ hai cuốn sổ — hai con số không "
          f"bao giờ bằng nhau, không nói thì có ngày ai đó đem đối chiếu")
    bad += not ok

    ok = "frontierLine" in js
    print(f"  {'✅' if ok else '❌'} và in ra MỐC, để người đọc tự thấy con số tin được tới đâu")
    bad += not ok

    # Bước "Chờ xuất hóa đơn" của Win phải bày CẢ HAI nghĩa, và nghĩa có sẵn
    # dữ liệu phải đứng TRƯỚC — bản đầu chỉ dựng nghĩa phải nhập tay nên màn
    # hình trống trong khi câu trả lời đã nằm sẵn trong ERPNext.
    print("-" * 82)
    ok = rc.js_calls(js, "loadWinPending", "loadWinEinv") and 'id="wp-einv"' in js
    print(f"  {'✅' if ok else '❌'} bước 'Chờ xuất hóa đơn' của Win có liệt kê hóa đơn ERPNext "
          f"chưa điền số HĐĐT")
    bad += not ok

    seg = js.split("async function loadWinPending")[1].split("\nasync function ")[0]
    i_einv = seg.find('id="wp-einv"')
    i_pend = seg.find("Đợt giao CHƯA có hóa đơn")
    ok = 0 <= i_einv < i_pend
    print(f"  {'✅' if ok else '❌'} và nó đứng TRƯỚC danh sách đợt giao nhập tay — cái có sẵn dữ "
          f"liệu phải hiện trước cái phải nhập")
    bad += not ok

    ok = "state.wpEinvPage" in js and "state.wpEinvScope" in js
    print(f"  {'✅' if ok else '❌'} phân trang và phạm vi dùng ô RIÊNG, không chung `state.page` "
          f"với danh sách đợt giao (chung là bấm bên này bảng kia nhảy theo)")
    bad += not ok

    ok = "Hai tập không giao nhau" in js
    print(f"  {'✅' if ok else '❌'} và màn hình nói rõ hai danh sách KHÁC nhau ở chỗ nào")
    bad += not ok

    print("-" * 82)
    ok = rc.js_calls(js, "loadWinEinv", "bindEinvSkip") and "data-skip=" in js
    print(f"  {'✅' if ok else '❌'} danh sách có nút BỎ QUA từng dòng")
    bad += not ok

    ok = rc.js_calls(js, "openSkipModal", "openModal") and "KHÔNG</b> trừ khỏi công nợ" in js
    print(f"  {'✅' if ok else '❌'} hộp thoại NÓI RA việc này không đụng công nợ/doanh thu/sổ cái "
          f"— in trên màn, không giấu trong tooltip")
    bad += not ok

    ok = "skippedBar" in js and rc.js_calls(js, "skippedBar", "formatVND")
    print(f"  {'✅' if ok else '❌'} và luôn hiện 'đang bỏ qua N hóa đơn' kèm nút xem lại")
    bad += not ok

    ok = "data-unskip" in js
    print(f"  {'✅' if ok else '❌'} mở lại được ngay trong màn xem lại")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — bỏ sót tách khỏi chưa-tới-lượt, mốc tính riêng từng chuỗi và "
          "luôn hiện, chưa có mốc thì không chấm ai")
    return 0


if __name__ == "__main__":
    sys.exit(main())
