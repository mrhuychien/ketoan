# -*- coding: utf-8 -*-
"""Dọn DANH TÍNH MISA ĐI VAY trên các hóa đơn TRẢ HÀNG đã ghi sổ.

════════════════════════════════════════════════════════════════════════════
VIỆC NÀY DỌN CÁI GÌ
════════════════════════════════════════════════════════════════════════════

Nút "Return" của ERPNext đi qua `frappe/model/mapper.py::map_fields`, hàm đó
chỉ loại field khỏi phép chép khi `no_copy == 1`. 17/17 field `custom_misa_*`
trước đây không khai cờ ấy, nên bản trả hàng chở nguyên RefID + ký hiệu + SỐ
HÓA ĐƠN + cờ đã-đẩy của bản gốc. Patch v0_0_19 bịt đường chép cho mai sau;
module này dọn số đã lọt vào rồi.

`misa_push.push_invoice` chặn hẳn `is_return` ở cổng đẩy: một bản trả hàng
KHÔNG BAO GIỜ có hóa đơn MISA riêng dưới RefID của nó. Mọi danh tính MISA
khớp byte với bản gốc trên một bản trả hàng chỉ có thể là đi vay.

════════════════════════════════════════════════════════════════════════════
ĐO TRÊN SITE 08/10/2026 (docs/misa/sql/chandoan_tra_hang.sql)
════════════════════════════════════════════════════════════════════════════

    1030 hóa đơn trả hàng đã ghi sổ.
     106 chép danh tính của chính hóa đơn gốc (`return_against`), trong đó
         90 chở cả SỐ HÓA ĐƠN, 38 đang mang "Lệch tiền" giả.
     640 không có gì để dọn.
     284 có số hóa đơn nhưng KHÔNG chứng minh được là bản chép (không có
         `return_against`, hoặc số riêng khác gốc) — ngoài phạm vi, để yên.

Bản đầu của module này ra 0 dọn / 479 cần người xem, vì hai lỗi luật — giữ
lại ở đây để không ai viết lại đúng hai lỗi đó:

  1. Đòi CẢ 15 field khớp bản gốc, trong đó `custom_misa_last_checked` (máy
     đóng dấu riêng từng chứng từ, có micro-giây) và `custom_misa_note`
     (cảnh báo lệch tiền tính theo tiền RIÊNG từng chứng từ) không bao giờ
     khớp được. Một field lệch là cả chứng từ bị loại.
  2. Chốt "không có gì để dọn" dùng cùng 15 field đó, nên bản trả hàng sạch
     chỉ mang một dấu `last_checked` cũng lọt xuống, rồi bị dán "RefID không
     dùng chung" — 400+ dòng nhiễu che mất mấy dòng thật.

════════════════════════════════════════════════════════════════════════════
BA TẬP FIELD — mỗi tập một cách xử
════════════════════════════════════════════════════════════════════════════

TẬP A — danh tính MISA (`TAP_A`): ký hiệu, số, ngày, transaction_id, mã CQT,
link, đẩy-lúc, quan hệ, org_*. Là BẰNG CHỨNG và là thứ được dọn — mỗi field
có giá trị phải khớp BYTE bản gốc. Khác một ly ⇒ có người đã sửa ⇒ cả chứng từ
sang `can_tay`, không dọn nửa vời.

TIẾNG ỒN — `custom_misa_last_checked`: không phải bằng chứng, dọn kèm.

Ô HIỂN THỊ CŨ `vn_einvoice_*` — KHÔNG phải bằng chứng. Chỉ dọn khi giá trị
BẰNG ĐÚNG giá trị đi vay đang dọn trên chính chứng từ (vd vn_einvoice_number
= custom_misa_inv_no = "00008754"): đó là `_legacy_values` của misa_sync chép
từ số đi vay khi ô còn trống. Còn lại GIỮ NGUYÊN: "8584", "HOÀN",
"7894- HOÀN" là kế toán tự gõ — có cái là số hóa đơn điều chỉnh của chính
bản trả hàng.

`custom_misa_note` — CHỈ NỐI THÊM một dòng, không bao giờ đặt trống. Ô này
`allow_on_submit` mà không `read_only` (install.py): người gõ được vào chứng
từ đã ghi sổ, và nó đang mang cả nhật ký đổi số của `misa_replace`.

════════════════════════════════════════════════════════════════════════════
CỜ KHÓA VÀ TRẠNG THÁI CUỐI — chỉ chặn khi KHÁC bản gốc
════════════════════════════════════════════════════════════════════════════

`custom_misa_no_locked = 1` và `custom_misa_status ∈ {Đã hủy, Đã thay thế}`
trên bản trả hàng chỉ là quyết định của người khi chúng KHÁC bản gốc. Giống
bản gốc thì chúng cũng là đồ đi vay (chép lúc Return, hoặc `poll_pending`
ghi theo RefID đi vay) và được dọn như mọi field khác.

Một ca phải nói rõ: `misa_sync._mark_superseded` tìm "bản gốc" bằng
`get_value({"custom_misa_ref_id": ...})` không sắp xếp. RefID dùng chung thì
nó có thể dán "Đã thay thế" vào BẢN TRẢ HÀNG và để bản gốc thật trông như
còn hiệu lực. Ca đó nằm ở `can_tay` kèm trạng thái của bản gốc; dọn bản trả
hàng xong thì lượt đồng bộ sau tìm ĐÚNG bản gốc.

════════════════════════════════════════════════════════════════════════════
BA NGUYÊN TẮC — đây là ghi vào CHỨNG TỪ ĐÃ GHI SỔ
════════════════════════════════════════════════════════════════════════════

1. Chỉ xoá cái chứng minh được là bản chép (luật ba tập ở trên).
2. Xem trước bắt buộc, xem gì dọn đúng cái ấy: `don()` dựng lại kế hoạch và
   đối VÂN TAY — băm tên chứng từ, giá trị sắp xoá, RefID/trạng thái/cờ khóa
   cũ, `bo_qua` và `cho_phep`. Lệch là DỪNG, không ghi một chữ.
3. Lùi được: giá trị cũ (kể cả ô ghi chú) ghi vào Comment TRƯỚC khi ghi đè;
   `hoan_tac(van_tay)` đọc lại chính các Comment đó.

KHÔNG BAO GIỜ hủy / save / submit Sales Invoice. Mọi phép ghi đi bằng
`set_value(update_modified=False)`.

════════════════════════════════════════════════════════════════════════════
CÁCH CHẠY
════════════════════════════════════════════════════════════════════════════

    bench --site <site> execute ketoan.api.misa_return_cleanup.xem_truoc
    bench --site <site> execute ketoan.api.misa_return_cleanup.don \\
          --kwargs "{'van_tay': '<vân tay>'}"
    bench --site <site> execute ketoan.api.misa_return_cleanup.hoan_tac \\
          --kwargs "{'van_tay': '<vân tay>'}"

Chứng từ trong `can_tay` chỉ được dọn khi người đã xem và liệt tên vào
`cho_phep` (tham số này nằm TRONG vân tay):

    --kwargs "{'cho_phep': ['HD-07141', 'HD-07080']}"
"""

import hashlib
import json
import uuid

import frappe
from frappe import _
from frappe.utils import cint, cstr, now_datetime

MOC = "ketoan.misa_return_cleanup"

# TẬP A — danh tính MISA. Bằng chứng chép VÀ là thứ được dọn.
TAP_A = (
    "custom_misa_inv_series", "custom_misa_inv_no", "custom_misa_inv_date",
    "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
    "custom_misa_pushed_at", "custom_misa_relation", "custom_misa_org_ref_id",
    "custom_misa_org_inv",
)

# Tiếng ồn: máy ghi riêng từng chứng từ — dọn kèm, KHÔNG dùng làm bằng chứng.
TIENG_ON = ("custom_misa_last_checked",)

# Ô hiển thị cũ → field đi vay mà nó phải BẰNG ĐÚNG thì mới được dọn.
O_CU_THEO = {
    "vn_einvoice_number": "custom_misa_inv_no",
    "vn_einvoice_date": "custom_misa_inv_date",
    "vn_einvoice_lookup_code": "custom_misa_transaction_id",
}

TRANG_THAI_CUOI = ("Đã hủy", "Đã thay thế")
KHONG_CAN_CT = "Không cần chứng từ"

# Nhóm ngoài phạm vi: có danh tính MISA nhưng KHÔNG chứng minh được là bản chép.
NGOAI = {
    "khong_goc": "không có hóa đơn gốc (return_against trống hoặc không tồn tại)",
    "so_rieng": "số hóa đơn riêng, khác cả số hiện hành lẫn số cũ của gốc",
    "ref_rieng_so_goc": "RefID riêng nhưng số = số của gốc (thường do "
                        "'Chuyển số HĐ cũ' chép số kế toán gõ tay)",
    "ref_rieng_khac": "RefID riêng, không có số, có field MISA khác",
}


def _co(field):
    return frappe.get_meta("Sales Invoice").has_field(field)


def _co_gia_tri(v):
    return v not in (None, "")


def _danh_sach(v):
    """Tham số danh sách đi qua `bench execute --kwargs` hoặc HTTP đều được."""
    if not v:
        return []
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("["):
            v = json.loads(v)
        else:
            v = v.split(",")
    return sorted({cstr(x).strip() for x in v if cstr(x).strip()})


def _van_tay(ke_hoach, bo_qua, cho_phep):
    """Vân tay của ĐÚNG kế hoạch đã bày ra.

    Băm cả RefID / trạng thái / cờ khóa CŨ: `don()` ghi đè ba field đó, nên ai
    đổi chúng giữa lúc xem và lúc dọn thì kế hoạch đã khác cái người đã đọc.
    """
    loi = json.dumps(
        {"bo_qua": bo_qua, "cho_phep": cho_phep, "viec": [
            {"si": r["si"], "goc": r["goc"],
             "ref": cstr(r["ref_id_cu"]),
             "tt": cstr(r["trang_thai_cu"]),
             "khoa": cint(r["no_locked_cu"]),
             "xoa": {k: cstr(v) for k, v in sorted(r["cu"].items())}}
            for r in sorted(ke_hoach, key=lambda x: x["si"])
        ]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(loi.encode("utf-8")).hexdigest()[:32]


def _theo_lo(ten, co):
    for i in range(0, len(ten), co):
        yield ten[i:i + co]


def _dung_ke_hoach(bo_qua, cho_phep, limit):
    """Dựng kế hoạch từ dữ liệu HIỆN TẠI. Không ghi gì."""
    bo_qua, cho_phep = set(bo_qua), set(cho_phep)
    tap_a = [f for f in TAP_A if _co(f)]
    tieng_on = [f for f in TIENG_ON if _co(f)]
    o_cu = {k: v for k, v in O_CU_THEO.items() if _co(k) and _co(v)}
    co_khoa = _co("custom_misa_no_locked")
    cot = tap_a + tieng_on + list(o_cu)

    # Không có LIMIT trong câu SQL thì không có chuyện kế hoạch là một LÁT CẮT
    # mà ai cũng đọc thành "toàn bộ". Cắt ở Python để còn biết là đã cắt.
    tra = frappe.db.sql(f"""
        SELECT si.name, si.return_against, si.posting_date, si.customer, si.grand_total,
               si.custom_misa_ref_id AS ref_id, si.custom_misa_status AS trang_thai,
               {"si.custom_misa_no_locked" if co_khoa else "0"} AS no_locked,
               si.custom_misa_note AS note
               {"".join(f", si.`{f}`" for f in cot)}
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND IFNULL(si.is_return, 0) = 1
        ORDER BY si.posting_date DESC, si.name DESC
    """, as_dict=True)
    tong = len(tra)
    gioi_han = cint(limit) or 5000
    bi_cat = tong > gioi_han
    tra = tra[:gioi_han]

    goc = {}
    ten_goc = sorted({r.return_against for r in tra if r.return_against})
    for lo in _theo_lo(ten_goc, 500):
        for g in frappe.db.sql(f"""
            SELECT si.name, si.docstatus, si.custom_misa_ref_id AS ref_id,
                   si.custom_misa_status AS trang_thai,
                   {"si.custom_misa_no_locked" if co_khoa else "0"} AS no_locked
                   {"".join(f", si.`{f}`" for f in tap_a)}
            FROM `tabSales Invoice` si
            WHERE si.name IN %(ten)s
        """, {"ten": tuple(lo)}, as_dict=True):
            goc[g.name] = g

    ke_hoach, can_tay = [], []
    ngoai = {k: {"so": 0, "vi_du": []} for k in NGOAI}

    def _ngoai(k, r):
        ngoai[k]["so"] += 1
        if len(ngoai[k]["vi_du"]) < 8:
            ngoai[k]["vi_du"].append(
                r.name + (f"={r.custom_misa_inv_no}" if r.get("custom_misa_inv_no") else ""))

    for r in tra:
        a = {f: r.get(f) for f in tap_a if _co_gia_tri(r.get(f))}
        g = goc.get(r.return_against) if r.return_against else None
        ref_muon = bool(g) and _co_gia_tri(r.ref_id) and cstr(r.ref_id) == cstr(g.ref_id)

        # KHÔNG CÓ GÌ ĐỂ DỌN — xét TRƯỚC mọi phép xét khác, và chỉ trên tập A +
        # RefID. Xét trên tiếng ồn là đúng cái lỗi đã đẩy 400+ bản sạch vào
        # danh sách cần người xem.
        if not a and not ref_muon:
            continue

        if r.name in bo_qua:
            can_tay.append({"si": r.name, "ly_do": "người vận hành yêu cầu bỏ qua"})
            continue

        if not g:
            _ngoai("khong_goc", r)
            continue

        if not ref_muon:
            if _co_gia_tri(r.ref_id) and cstr(r.ref_id) == cstr(g.get("custom_misa_org_ref_id")):
                # Mượn danh tính CŨ của một bản gốc đã đổi số thay thế. Đo trên
                # site: 0 ca. Không tự dọn một ca chưa từng thấy ngoài đời.
                can_tay.append({
                    "si": r.name, "goc": g.name,
                    "ly_do": "RefID = RefID CŨ của bản gốc (gốc đã đổi số thay thế) — "
                             "chưa từng gặp trên site, cần người xem"})
            elif _co_gia_tri(r.get("custom_misa_inv_no")):
                so = cstr(r.custom_misa_inv_no)
                so_goc = (cstr(g.get("custom_misa_inv_no")),
                          cstr(g.get("custom_misa_org_inv")).split(" ")[-1])
                _ngoai("ref_rieng_so_goc" if so in so_goc else "so_rieng", r)
            else:
                _ngoai("ref_rieng_khac", r)
            continue

        khac = {f: cstr(v) for f, v in a.items() if cstr(v) != cstr(g.get(f))}
        if khac:
            can_tay.append({
                "si": r.name, "goc": g.name,
                "ly_do": "RefID của gốc nhưng có field MISA KHÁC gốc (nghi đã sửa tay): "
                         + ", ".join(khac),
                "khac": khac, "cua_goc": {f: cstr(g.get(f)) for f in khac}})
            continue

        if cint(g.docstatus) == 2:
            can_tay.append({"si": r.name, "goc": g.name,
                            "ly_do": "bản gốc ĐÃ HỦY — chưa từng gặp trên site, cần người xem"})
            continue

        chan = []
        if cint(r.no_locked) and not cint(g.no_locked):
            chan.append("cờ khóa bật riêng trên bản trả hàng (bản gốc không khóa)")
        if r.trang_thai in TRANG_THAI_CUOI and cstr(r.trang_thai) != cstr(g.trang_thai):
            chan.append(
                f"trạng thái '{r.trang_thai}' trong khi bản gốc '{cstr(g.trang_thai)}'"
                + (" — nhiều khả năng đồng bộ dán NHẦM vào bản trả hàng vì RefID dùng "
                   "chung; bản gốc chưa bị đánh dấu" if r.trang_thai == "Đã thay thế" else ""))
        if chan and r.name not in cho_phep:
            can_tay.append({
                "si": r.name, "goc": g.name, "ly_do": "; ".join(chan),
                "tra_hang": {"trang_thai": cstr(r.trang_thai), "no_locked": cint(r.no_locked)},
                "ban_goc": {"trang_thai": cstr(g.trang_thai), "no_locked": cint(g.no_locked)},
                "so_di_vay": cstr(r.get("custom_misa_inv_no")),
                "mo_khoa": "đã xem và muốn dọn: thêm tên vào cho_phep"})
            continue

        cu = dict(a)
        for f in tieng_on:
            if _co_gia_tri(r.get(f)):
                cu[f] = r.get(f)
        for f, nguon in o_cu.items():
            # Chỉ dọn khi BẰNG ĐÚNG giá trị đi vay đang dọn trên chính chứng từ.
            if _co_gia_tri(r.get(f)) and nguon in a and cstr(r.get(f)) == cstr(a[nguon]):
                cu[f] = r.get(f)

        ke_hoach.append({
            "si": r.name, "goc": g.name,
            "posting_date": cstr(r.posting_date), "customer": r.customer,
            "grand_total": r.grand_total,
            "ref_id_cu": r.ref_id, "trang_thai_cu": r.trang_thai,
            "no_locked_cu": cint(r.no_locked), "note_cu": r.note,
            "da_mo_khoa": bool(chan),
            "cu": cu,
        })

    return ke_hoach, can_tay, ngoai, {"tong_quet": tong, "bi_cat": bi_cat}


def _snapshot_tro_vao(ten_si):
    """Bảng kê MISA đang trỏ vào các chứng từ sắp dọn — bày ra, KHÔNG tự sửa."""
    if not ten_si or not frappe.db.table_exists("MISA Invoice Snapshot"):
        return []
    return frappe.get_all(
        "MISA Invoice Snapshot",
        filters={"sales_invoice": ("in", list(ten_si))},
        fields=["name", "inv_series", "inv_no", "sales_invoice", "match_status"],
        limit=500,
    )


def _mt_se_lat(ten_si):
    """Dòng MT Hàng Hoàn sẽ chuyển về "Chưa có chứng từ thuế" sau khi dọn.

    `mt_hoan._ct_thue_expr` coi phiếu trả CÓ `custom_misa_inv_no` là đã có chứng
    từ thuế. Số đi vay đang làm dòng đó trông như xong; dọn đi là nó hiện lại
    đúng tình trạng thật. Đếm TRƯỚC để không ai bị bất ngờ.
    """
    if not ten_si or not frappe.db.table_exists("MT Hang Hoan"):
        return []
    co_bang_ke = (frappe.db.table_exists("MT Payment Advice Line")
                  and frappe.db.has_column("MT Payment Advice Line", "return_invoice"))
    return frappe.db.sql(f"""
        SELECT h.name, h.credit_note, h.chung_tu_can
        FROM `tabMT Hang Hoan` h
        WHERE h.credit_note IN %(ten)s
          AND NOT (IFNULL(h.chung_tu_can, '') = %(khong_can)s)
          {'''AND NOT EXISTS (
              SELECT 1 FROM `tabMT Payment Advice Line` l
              INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
              WHERE l.return_invoice = h.credit_note AND a.docstatus < 2)''' if co_bang_ke else ""}
    """, {"ten": tuple(ten_si), "khong_can": KHONG_CAN_CT}, as_dict=True)


@frappe.whitelist()
def xem_truoc(limit=5000, bo_qua=None, cho_phep=None):
    """XEM TRƯỚC — không ghi một chữ nào. Trả về kế hoạch + vân tay của nó."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    bo_qua, cho_phep = _danh_sach(bo_qua), _danh_sach(cho_phep)
    ke_hoach, can_tay, ngoai, quet = _dung_ke_hoach(bo_qua, cho_phep, limit)
    van_tay = _van_tay(ke_hoach, bo_qua, cho_phep)
    co_so = [r["si"] for r in ke_hoach if _co_gia_tri(r["cu"].get("custom_misa_inv_no"))]
    return {
        "van_tay": van_tay,
        "so_dinh_don": len(ke_hoach),
        "trong_do_co_so_hd": len(co_so),
        "so_can_tay": len(can_tay),
        **quet,
        "bo_qua": bo_qua,
        "cho_phep": cho_phep,
        "mt_hang_hoan_se_lat": _mt_se_lat(co_so),
        "snapshot_tro_vao": _snapshot_tro_vao([r["si"] for r in ke_hoach]),
        "can_tay": can_tay,
        "ngoai_pham_vi": {NGOAI[k]: v for k, v in ngoai.items() if v["so"]},
        "viec": [{"si": r["si"], "goc": r["goc"],
                  "xoa": {k: cstr(v) for k, v in r["cu"].items()}} for r in ke_hoach],
        "nhac": "Chạy `don(van_tay=...)` với ĐÚNG vân tay này và ĐÚNG bo_qua/cho_phep "
                "đã dùng ở đây. Dữ liệu đổi giữa hai lượt thì `don` sẽ DỪNG.",
    }


def _dong_ghi_chu(r, van_tay):
    so = " ".join(x for x in (cstr(r["cu"].get("custom_misa_inv_series")),
                              cstr(r["cu"].get("custom_misa_inv_no"))) if x)
    return _(
        "[{0}] {1} dọn danh tính MISA đi vay của {2}{3} — bản trả hàng không có hóa "
        "đơn MISA riêng; ghi chú lệch tiền phía trên (nếu có) là do hỏi MISA bằng "
        "RefID của hóa đơn gốc · vân tay {4}"
    ).format(cstr(now_datetime())[:16], frappe.session.user, r["goc"],
             f" ({so})" if so else "", van_tay[:8])


@frappe.whitelist()
def don(van_tay, limit=5000, bo_qua=None, cho_phep=None):
    """DỌN THẬT. Chỉ chạy khi vân tay khớp kế hoạch dựng lại từ dữ liệu hiện tại."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    van_tay = cstr(van_tay).strip()
    if not van_tay:
        frappe.throw(_("Thiếu vân tay. Chạy `xem_truoc` trước và đọc kế hoạch."))
    bo_qua, cho_phep = _danh_sach(bo_qua), _danh_sach(cho_phep)

    ke_hoach, can_tay, _ngoai, quet = _dung_ke_hoach(bo_qua, cho_phep, limit)
    thuc = _van_tay(ke_hoach, bo_qua, cho_phep)
    if thuc != van_tay:
        frappe.throw(_(
            "Vân tay KHÔNG khớp — dữ liệu đã đổi kể từ lúc xem trước, hoặc tham số "
            "(bo_qua / cho_phep / limit) khác lúc xem. Kế hoạch bây giờ có vân tay {0} "
            "({1} chứng từ). Chạy lại `xem_truoc`, đọc, rồi dùng vân tay mới. Không dọn gì cả."
        ).format(thuc, len(ke_hoach)))

    co_trang_thai = _co("custom_misa_status")
    co_khoa = _co("custom_misa_no_locked")
    co_note = _co("custom_misa_note")
    da_don, loi = [], []
    for r in ke_hoach:
        try:
            moi = str(uuid.uuid4())
            # Comment TRƯỚC khi ghi: mất điện giữa lô thì còn vết để lùi. Ngược
            # lại là ghi xong mới lưu giá trị cũ — đúng lúc cần nhất thì không có.
            frappe.get_doc({
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "Sales Invoice",
                "reference_name": r["si"],
                "content": json.dumps({
                    "moc": MOC, "van_tay": van_tay, "goc": r["goc"],
                    "ref_id_cu": r["ref_id_cu"], "ref_id_moi": moi,
                    "trang_thai_cu": r["trang_thai_cu"],
                    "no_locked_cu": r["no_locked_cu"],
                    "note_cu": r["note_cu"],
                    "cu": {k: cstr(v) for k, v in r["cu"].items()},
                }, ensure_ascii=False, default=cstr),
            }).insert(ignore_permissions=True)

            gia_tri = {f: None for f in r["cu"]}
            gia_tri["custom_misa_ref_id"] = moi
            if co_trang_thai:
                gia_tri["custom_misa_status"] = "Chưa đẩy"
            # 0 chứ KHÔNG phải None: vòng quét 2 của poll_pending lọc
            # `custom_misa_no_locked = 0`, NULL rơi khỏi bộ lọc (bẫy v0_0_17).
            if co_khoa:
                gia_tri["custom_misa_no_locked"] = 0
            if co_note:
                # NỐI, không đè: ô này mang cả chữ người gõ và nhật ký đổi số.
                cu_note = cstr(r["note_cu"] or "").rstrip()
                dong = _dong_ghi_chu(r, van_tay)
                gia_tri["custom_misa_note"] = (cu_note + "\n" + dong) if cu_note else dong
            frappe.db.set_value("Sales Invoice", r["si"], gia_tri, update_modified=False)
            da_don.append(r["si"])
            if len(da_don) % 25 == 0:
                frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{MOC}.don {r['si']}")
            loi.append(r["si"])
    frappe.db.commit()

    return {
        "van_tay": van_tay,
        "da_don": len(da_don),
        "loi": loi,
        "con_can_tay": len(can_tay),
        **quet,
        "nhac": "Lùi được bằng `hoan_tac(van_tay='{0}')`.".format(van_tay),
    }


@frappe.whitelist()
def hoan_tac(van_tay):
    """Trả các chứng từ của MỘT lượt dọn về nguyên giá trị cũ, kể cả ô ghi chú."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    van_tay = cstr(van_tay).strip()
    if not van_tay:
        frappe.throw(_("Thiếu vân tay của lượt dọn cần lùi."))

    rows = frappe.get_all(
        "Comment",
        filters={"comment_type": "Info", "reference_doctype": "Sales Invoice",
                 "content": ("like", f"%{van_tay}%")},
        fields=["name", "reference_name", "content"], limit=5000,
    )
    tra, loi = [], []
    for c in rows:
        try:
            d = json.loads(c.content)
        except Exception:
            continue
        # Bộ lọc LIKE vớt cả Comment của nguồn khác tình cờ chứa cùng chuỗi —
        # chốt `moc` + vân tay ở tầng mã mới là chốt thật.
        if d.get("moc") != MOC or d.get("van_tay") != van_tay:
            continue
        try:
            gia_tri = dict(d.get("cu") or {})
            gia_tri["custom_misa_ref_id"] = d.get("ref_id_cu")
            if _co("custom_misa_status"):
                gia_tri["custom_misa_status"] = d.get("trang_thai_cu")
            if _co("custom_misa_no_locked"):
                gia_tri["custom_misa_no_locked"] = cint(d.get("no_locked_cu"))
            if _co("custom_misa_note"):
                gia_tri["custom_misa_note"] = d.get("note_cu")
            gia_tri = {k: v for k, v in gia_tri.items() if _co(k)}
            frappe.db.set_value("Sales Invoice", c.reference_name, gia_tri,
                                update_modified=False)
            tra.append(c.reference_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{MOC}.hoan_tac {c.reference_name}")
            loi.append(c.reference_name)
    frappe.db.commit()
    return {"van_tay": van_tay, "da_tra_lai": len(tra), "loi": loi,
            "nhac": "Comment ghi giá trị cũ vẫn để nguyên trên timeline chứng từ."}
