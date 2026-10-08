# -*- coding: utf-8 -*-
"""Dọn SỐ HÓA ĐƠN ĐI VAY trên các hóa đơn TRẢ HÀNG đã ghi sổ.

════════════════════════════════════════════════════════════════════════════
VIỆC NÀY DỌN CÁI GÌ
════════════════════════════════════════════════════════════════════════════

Nút "Return" của ERPNext đi qua `frappe/model/mapper.py::map_fields`, hàm đó
chỉ loại field khỏi phép chép khi `no_copy == 1`. 17/17 field `custom_misa_*`
trước đây không khai cờ ấy, nên bản trả hàng chở nguyên RefID + ký hiệu + SỐ
HÓA ĐƠN + cờ đã-đẩy của bản gốc. Patch v0_0_19 bịt đường chép cho mai sau;
module này dọn số đã lọt vào rồi.

ĐO TRÊN SITE 08/10/2026: 91 nhóm / 182 chứng từ dùng chung một RefID và một số
hóa đơn — 92 hóa đơn BÁN + 90 hóa đơn TRẢ HÀNG. 70/91 nhóm có cả
`custom_misa_pushed_at` giống nhau, tức field bị CHÉP chứ không phải hai lần
đẩy khác nhau.

KHÔNG phải phát hành trùng: `misa_push.push_invoice` chặn hẳn `is_return` ở
cổng đẩy, nên không hóa đơn nào bị cấp hai lần và không lần bán nào chưa được
xuất. Thiệt hại là bản trả hàng HIỆN số của bản gốc trên chứng từ và trên
bảng kê.

════════════════════════════════════════════════════════════════════════════
BA NGUYÊN TẮC — đây là ghi vào CHỨNG TỪ ĐÃ GHI SỔ
════════════════════════════════════════════════════════════════════════════

1. CHỈ XOÁ CÁI CHỨNG MINH ĐƯỢC LÀ BẢN CHÉP. Một field chỉ bị dọn khi giá trị
   của nó GIỐNG HỆT bản gốc cùng RefID. Khác một ly ⇒ coi như người đã sửa
   tay ⇒ CẢ CHỨNG TỪ bị đẩy sang danh sách `can_tay`, không tự động dọn.
   Đoán hộ kế toán ở đây là sửa số hóa đơn của người ta.

2. XEM TRƯỚC LÀ BẮT BUỘC, VÀ XEM CÁI GÌ THÌ DỌN ĐÚNG CÁI ẤY. `xem_truoc`
   trả về một VÂN TAY của đúng kế hoạch đã bày ra. `don()` dựng lại kế hoạch
   và đối vân tay: dữ liệu đổi giữa lúc xem và lúc dọn ⇒ DỪNG, không dọn
   theo một kế hoạch chưa ai đọc.

3. LÙI ĐƯỢC. Mỗi chứng từ được dọn đều có một Comment ghi NGUYÊN giá trị cũ
   dạng JSON kèm vân tay của lượt dọn. `hoan_tac(van_tay)` đọc lại chính các
   Comment đó mà trả về.

KHÔNG BAO GIỜ hủy Sales Invoice. Mọi phép ghi đi bằng
`frappe.db.set_value(update_modified=False)` — `save()` trên chứng từ đã ghi
sổ chạy lại validate và có thể gãy giữa lô.

════════════════════════════════════════════════════════════════════════════
CÁCH CHẠY
════════════════════════════════════════════════════════════════════════════

    bench --site <site> execute ketoan.api.misa_return_cleanup.xem_truoc
    # đọc kỹ, lấy `van_tay`, rồi:
    bench --site <site> execute ketoan.api.misa_return_cleanup.don \\
          --kwargs "{'van_tay': '<vân tay>'}"
    # cần lùi:
    bench --site <site> execute ketoan.api.misa_return_cleanup.hoan_tac \\
          --kwargs "{'van_tay': '<vân tay>'}"

Hai nhóm ĐÃ BIẾT là phải người xem (dò MISA 08/10/2026): nhóm
HD-07410/HD-07411 — nhiều hóa đơn MISA cùng khớp tiền; và một nhóm "loại B"
(hai chứng từ cùng RefID mà KHÔNG phải cặp bán/trả hàng). Nhóm thứ hai tự
rơi vào `can_tay` theo luật §1. Nhóm đầu, nếu kế hoạch có nhắc tới, truyền
qua `bo_qua=["HD-07410", "HD-07411"]` — tham số này nằm TRONG vân tay.
"""

import hashlib
import json
import uuid

import frappe
from frappe import _
from frappe.utils import cstr

MOC = "ketoan.misa_return_cleanup"

# Field bị dọn khi (và chỉ khi) giá trị giống hệt bản gốc cùng RefID.
FIELD_CHEP = (
    "custom_misa_inv_series", "custom_misa_inv_no", "custom_misa_inv_date",
    "custom_misa_transaction_id", "custom_misa_invoice_code", "custom_misa_link",
    "custom_misa_pushed_at", "custom_misa_last_checked", "custom_misa_relation",
    "custom_misa_org_ref_id", "custom_misa_org_inv", "custom_misa_note",
    "vn_einvoice_number", "vn_einvoice_date", "vn_einvoice_lookup_code",
)


def _co(field):
    return frappe.get_meta("Sales Invoice").has_field(field)


def _fields_co_that():
    return [f for f in FIELD_CHEP if _co(f)]


def _van_tay(ke_hoach, bo_qua):
    """Vân tay của ĐÚNG kế hoạch đã bày ra — tên chứng từ, field, giá trị cũ.

    Băm cả `bo_qua`: bỏ qua chứng từ nào cũng là một phần của kế hoạch người
    đã đọc, đổi danh sách đó là đổi việc sẽ làm.
    """
    loi = json.dumps(
        {"bo_qua": sorted(bo_qua), "viec": [
            {"si": r["si"],
             "xoa": {k: cstr(v) for k, v in sorted(r["cu"].items())}}
            for r in sorted(ke_hoach, key=lambda x: x["si"])
        ]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(loi.encode("utf-8")).hexdigest()[:32]


def _dung_ke_hoach(bo_qua, limit):
    """Dựng kế hoạch từ dữ liệu HIỆN TẠI. Không ghi gì."""
    bo_qua = set(bo_qua or [])
    fields = _fields_co_that()

    # Bản trả hàng đã ghi sổ, CÓ RefID. `IFNULL(is_return, 0) = 1` chứ không
    # `is_return = 1`: cột Check của Frappe là NULLABLE trừ khi field khai
    # `not_nullable`, và phép so sánh trần với NULL ra NULL chứ không ra FALSE.
    # Ở vế `= 1` thì NULL rụng ra là ĐÚNG (NULL không bao giờ là trả hàng), còn
    # ở vế `= 0` bên dưới thì rụng là SAI — nên bọc cả hai, khỏi phải nhớ vế nào
    # an toàn.
    cot = ", ".join(f"si.`{f}`" for f in fields)
    tra = frappe.db.sql(f"""
        SELECT si.name, si.custom_misa_ref_id AS ref_id, si.custom_misa_status AS trang_thai,
               si.custom_misa_no_locked AS no_locked, si.posting_date, si.customer,
               si.grand_total, si.return_against{(", " + cot) if cot else ""}
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 1
          AND IFNULL(si.custom_misa_ref_id, '') != ''
        ORDER BY si.posting_date DESC, si.name DESC
        LIMIT %(limit)s
    """, {"limit": int(limit or 1000)}, as_dict=True)

    ke_hoach, can_tay = [], []
    for r in tra:
        if r.name in bo_qua:
            can_tay.append({"si": r.name, "ly_do": "người vận hành yêu cầu bỏ qua"})
            continue

        # KHÔNG CÓ GÌ ĐỂ DỌN THÌ IM LẶNG BỎ QUA — xét trước mọi phép xét khác.
        #
        # Sau patch v0_0_19 mọi bản trả hàng MỚI đều có RefID riêng và không có
        # số. Nếu hỏi "RefID có dùng chung không" trước, thì mỗi bản trả hàng
        # bình thường của tương lai đều rơi vào danh sách `can_tay` với lý do
        # "không chứng minh được là bản chép" — tức danh sách cần người xem
        # phình lên bằng toàn bộ hóa đơn trả hàng, và cái gì cũng cần xem thì
        # chẳng ai xem cái gì.
        if all(r.get(f) in (None, "") for f in fields):
            continue

        goc = frappe.db.sql(f"""
            SELECT si.name{(", " + cot) if cot else ""}
            FROM `tabSales Invoice` si
            WHERE si.custom_misa_ref_id = %(ref)s
              AND IFNULL(si.is_return, 0) = 0
              AND si.docstatus < 2
        """, {"ref": r.ref_id}, as_dict=True)

        if not goc:
            # RefID không ai dùng chung ⇒ KHÔNG chứng minh được là bản chép.
            # Có thể là bản trả hàng đã được cấp RefID riêng (đúng), hoặc một
            # tình huống khác hẳn. Không đụng.
            can_tay.append({"si": r.name, "ref_id": r.ref_id,
                            "ly_do": "RefID không dùng chung với hóa đơn bán nào "
                                     "— không chứng minh được là bản chép"})
            continue
        if len(goc) > 1:
            can_tay.append({"si": r.name, "ref_id": r.ref_id,
                            "ly_do": f"RefID dùng chung với {len(goc)} hóa đơn bán "
                                     f"({', '.join(g.name for g in goc)}) — cấu trúc lạ",
                            })
            continue

        g = goc[0]
        cu, khac = {}, []
        for f in fields:
            vt, vg = r.get(f), g.get(f)
            if vt in (None, ""):
                continue                      # vốn đã trống, không có gì dọn
            if cstr(vt) == cstr(vg):
                cu[f] = vt                    # GIỐNG HỆT bản gốc ⇒ là bản chép
            else:
                khac.append(f)

        if khac:
            # Có field mang giá trị KHÁC bản gốc ⇒ đã có người sửa tay ở đây.
            # Dọn một phần là để lại chứng từ nửa dọn nửa không, khó dò hơn cả
            # lúc chưa dọn. Để nguyên, đưa người xem.
            can_tay.append({
                "si": r.name, "ref_id": r.ref_id, "goc": g.name,
                "ly_do": "có field khác bản gốc (nghi đã sửa tay): " + ", ".join(khac),
                "khac": {f: cstr(r.get(f)) for f in khac},
            })
            continue
        if not cu:
            continue                           # sạch rồi

        ke_hoach.append({
            "si": r.name, "goc": g.name, "ref_id": r.ref_id,
            "posting_date": cstr(r.posting_date), "customer": r.customer,
            "grand_total": r.grand_total,
            "trang_thai_cu": r.trang_thai, "no_locked_cu": r.no_locked,
            "cu": cu,
        })

    return ke_hoach, can_tay, sorted(bo_qua)


def _snapshot_tro_vao(ten_si):
    """Bảng kê MISA nào đang trỏ vào các chứng từ này.

    Dọn số trên chứng từ mà snapshot vẫn trỏ vào nó là để lại một mối nối sai ở
    chỗ khác. KHÔNG tự sửa — chỉ bày ra, vì sửa mối nối đối soát là quyết định
    của kế toán.
    """
    if not ten_si or not frappe.db.table_exists("MISA Invoice Snapshot"):
        return []
    return frappe.get_all(
        "MISA Invoice Snapshot",
        filters={"sales_invoice": ("in", list(ten_si))},
        fields=["name", "inv_series", "inv_no", "sales_invoice", "match_status"],
        limit=500,
    )


@frappe.whitelist()
def xem_truoc(limit=1000, bo_qua=None):
    """XEM TRƯỚC — không ghi một chữ nào. Trả về kế hoạch + vân tay của nó."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    if isinstance(bo_qua, str):
        bo_qua = [x.strip() for x in bo_qua.split(",") if x.strip()]
    ke_hoach, can_tay, bq = _dung_ke_hoach(bo_qua, limit)
    return {
        "van_tay": _van_tay(ke_hoach, bq),
        "bo_qua": bq,
        "so_dinh_don": len(ke_hoach),
        "so_can_tay": len(can_tay),
        "viec": ke_hoach,
        "can_tay": can_tay,
        "snapshot_tro_vao": _snapshot_tro_vao([r["si"] for r in ke_hoach]),
        "nhac": "Chạy `don(van_tay=...)` với đúng vân tay này. Dữ liệu đổi giữa "
                "hai lượt thì `don` sẽ DỪNG và đòi xem lại.",
    }


@frappe.whitelist()
def don(van_tay, limit=1000, bo_qua=None):
    """DỌN THẬT. Chỉ chạy khi vân tay khớp kế hoạch dựng lại từ dữ liệu hiện tại."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    if not cstr(van_tay).strip():
        frappe.throw(_("Thiếu vân tay. Chạy `xem_truoc` trước và đọc kế hoạch."))
    if isinstance(bo_qua, str):
        bo_qua = [x.strip() for x in bo_qua.split(",") if x.strip()]

    ke_hoach, can_tay, bq = _dung_ke_hoach(bo_qua, limit)
    thuc = _van_tay(ke_hoach, bq)
    if thuc != cstr(van_tay).strip():
        frappe.throw(_(
            "Vân tay KHÔNG khớp — dữ liệu đã đổi kể từ lúc xem trước, hoặc tham số "
            "khác lúc xem. Kế hoạch bây giờ có vân tay {0} ({1} chứng từ). Chạy lại "
            "`xem_truoc`, đọc, rồi dùng vân tay mới. Không dọn gì cả."
        ).format(thuc, len(ke_hoach)))

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
                    "ref_id_cu": r["ref_id"], "ref_id_moi": moi,
                    "trang_thai_cu": r["trang_thai_cu"],
                    "no_locked_cu": r["no_locked_cu"],
                    "cu": {k: cstr(v) for k, v in r["cu"].items()},
                }, ensure_ascii=False, default=cstr),
            }).insert(ignore_permissions=True)

            gia_tri = {f: None for f in r["cu"]}
            gia_tri["custom_misa_ref_id"] = moi
            if _co("custom_misa_status"):
                gia_tri["custom_misa_status"] = "Chưa đẩy"
            # 0 chứ KHÔNG phải None: vòng quét 2 của poll_pending lọc
            # `custom_misa_no_locked = 0`, NULL rơi khỏi bộ lọc (bẫy v0_0_17).
            if _co("custom_misa_no_locked"):
                gia_tri["custom_misa_no_locked"] = 0
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
        "nhac": "Lùi được bằng `hoan_tac(van_tay='{0}')`.".format(van_tay),
    }


@frappe.whitelist()
def hoan_tac(van_tay):
    """Trả các chứng từ của MỘT lượt dọn về nguyên giá trị cũ."""
    from ketoan.api._guard import guard_manager

    guard_manager()
    van_tay = cstr(van_tay).strip()
    if not van_tay:
        frappe.throw(_("Thiếu vân tay của lượt dọn cần lùi."))

    rows = frappe.get_all(
        "Comment",
        filters={"comment_type": "Info", "reference_doctype": "Sales Invoice",
                 "content": ("like", f"%{van_tay}%")},
        fields=["name", "reference_name", "content"], limit=2000,
    )
    tra, loi = [], []
    for c in rows:
        try:
            d = json.loads(c.content)
        except Exception:
            continue
        if d.get("moc") != MOC or d.get("van_tay") != van_tay:
            continue
        try:
            gia_tri = dict(d.get("cu") or {})
            gia_tri["custom_misa_ref_id"] = d.get("ref_id_cu")
            if _co("custom_misa_status"):
                gia_tri["custom_misa_status"] = d.get("trang_thai_cu")
            if _co("custom_misa_no_locked"):
                gia_tri["custom_misa_no_locked"] = d.get("no_locked_cu") or 0
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
