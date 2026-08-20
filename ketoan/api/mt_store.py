# -*- coding: utf-8 -*-
"""mt_store — master ĐIỂM SIÊU THỊ: dựng từ dữ liệu đã có trên site, và tra cứu.

VÌ SAO tách khỏi `ketoan/api/mt.py`: mt.py đã ~2.500 dòng và lo một việc khác
hẳn (đối chiếu bảng kê với hóa đơn). Master điểm siêu thị có vòng đời riêng,
nguồn dữ liệu riêng và người dùng riêng (kế toán trưởng mở/đóng điểm).
Quy ước của dự án: 1 file = 1 chức năng.

═══════════════════════════════════════════════════════════════════════════════
NGUỒN DỰNG — TỪ DỮ LIỆU TRÊN SITE, KHÔNG SHIP FILE MẪU
═══════════════════════════════════════════════════════════════════════════════

Tất cả đều đọc từ `MT Payment Advice Line` đã nạp trên site. Không ship
`docs/mt/samples/` vào patch: file mẫu là ảnh chụp MỘT kỳ, còn site có dữ liệu
đầy đủ hơn và luôn mới hơn. Đóng băng một thời điểm rồi lệch dần là cách chắc
chắn nhất để master trở thành thứ không ai tin.

KHÔNG hardcode "chuỗi nào có điểm". Đo trên 7 file mẫu thật:

    LOTTE         17 mã + 17 tên
    Saigon Co.op 120 mã + 120 tên (thêm 1 tên KHÔNG có mã — pháp nhân mẹ)
    AEON           6 mã, KHÔNG tên
    Fuji           6 mã (mã kho nhập), KHÔNG tên
    Central Retail 59 TÊN, KHÔNG mã
    WinCommerce    không có gì
    Emart          không có gì

Danh sách này sẽ đổi khi chuỗi đổi mẫu file, nên tầng dựng phải hỏi DỮ LIỆU chứ
đừng hỏi một hằng số. Ba nhánh xử lý, chọn theo chính dữ liệu của từng chuỗi:

  · chuỗi CÓ mã          -> khóa là mã; tên lấy từ dòng có mã đó
  · chuỗi CHỈ có tên     -> mã do mình SINH RA từ tên (bỏ dấu, hoa, '_')
                            Chỉ làm khi chuỗi KHÔNG hề có mã nào, để một vài
                            dòng thiếu mã của chuỗi bình thường không đẻ ra
                            điểm rác trùng với điểm thật.
  · chuỗi CÓ mã, KHÔNG tên -> tên tạm = mã, đánh dấu để người sửa

═══════════════════════════════════════════════════════════════════════════════
XEM TRƯỚC LÀ BẮT BUỘC
═══════════════════════════════════════════════════════════════════════════════

Điểm dựng bằng suy luận (sinh mã từ tên, dò địa chỉ theo cụm trong ngoặc) nên
người PHẢI nhìn trước khi ghi master. `commit_seed` đòi vân tay của đúng bản xem
trước — dữ liệu đổi giữa chừng là dừng, không ghi gì.

TUYỆT ĐỐI KHÔNG ĐÈ bản ghi đã có. Master do người sửa; seed chỉ THÊM cái chưa
có. Đè là xóa mất công sức gán pháp nhân/địa chỉ của kế toán mà không ai hay.
"""

import hashlib
import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import cint, cstr

from ketoan.api._guard import guard_manager, guard_mt
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import norm_text
from ketoan.mt.doctype.mt_store.mt_store import norm_store_code

# Trần số điểm dựng trong một lần. Thật: Co.op 120 + LOTTE 17 + CR 59 + AEON 6
# + Fuji 6 = 208. Để 2.000 là dư 10 lần mà vẫn chặn được ca dữ liệu bẩn sinh ra
# hàng vạn "điểm" từ một cột bị đọc nhầm.
MAX_SEED = 2000

STATUS_NEW = "moi"          # chưa có -> sẽ tạo
STATUS_EXISTS = "da_co"     # đã có, mọi thứ khớp -> bỏ qua
STATUS_DIFF = "lech"        # đã có nhưng tên/khách khác -> BÁO, không đè

STATUS_LABEL = {
    STATUS_NEW: "Sẽ tạo mới",
    STATUS_EXISTS: "Đã có — bỏ qua",
    STATUS_DIFF: "Đã có nhưng dữ liệu lệch — KHÔNG đè",
}


def _require_tables():
    """DocType đã thành BẢNG chưa. Chưa migrate thì báo đúng việc cần làm."""
    for dt in ("MT Payment Advice", "MT Payment Advice Line", "MT Store"):
        if not frappe.db.table_exists(dt):
            frappe.throw(_(
                "Chức năng Điểm siêu thị chưa được cài trên site này (thiếu bảng {0}). "
                "Quản trị chạy: bench --site TÊN_SITE migrate"
            ).format(dt))


def _company(company=None):
    """Công ty của màn hình. Dùng CHUNG chốt quyền với `mt._company`.

    VÌ SAO không cài lại: `mt._company` kiểm bằng User Permission chứ không bằng
    `has_permission("Company")`, và đó là kết luận đã phải sửa một lần rồi (vai
    trò portal không được cấp DocType `Company` nên has_permission khóa sạch màn
    hình của người dùng hợp lệ). Hai bản sao của một chốt quyền thì bản thứ hai
    chắc chắn lệch.

    LƯU Ý: `MT Store` KHÔNG có field `company` — một siêu thị là một siêu thị,
    không phụ thuộc pháp nhân bán hàng, giống hệt `Customer` của ERPNext. Công ty
    ở đây chỉ dùng để (a) chốt quyền và (b) lọc bảng kê nguồn khi dựng master.
    """
    from ketoan.api.mt import _company as _mt_company
    return _mt_company(company)


# ─────────────────────────────────────────────────────────────────────────
# Chuẩn hóa
# ─────────────────────────────────────────────────────────────────────────

def _strip_tones(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


_NON_CODE_RE = re.compile(r"[^A-Z0-9]+")


def code_from_name(name) -> str:
    """Tên điểm -> mã SINH RA: bỏ dấu, HOA, mọi thứ không phải chữ/số thành '_'.

    Dùng cho chuỗi KHÔNG in mã điểm (Central Retail). Mã sinh ra phải ỔN ĐỊNH —
    chạy seed lần hai trên cùng dữ liệu phải ra đúng mã cũ, nếu không thì lần
    nào cũng đẻ thêm một bộ điểm trùng.

    'AN LAC'            -> 'AN_LAC'
    'Gò Vấp (khu B)'    -> 'GO_VAP_KHU_B'
    """
    t = _NON_CODE_RE.sub("_", _strip_tones(name).upper()).strip("_")
    return t


_PAREN_RE = re.compile(r"\(([^()]*)\)")


def name_in_last_parens(text):
    """Lấy nội dung cặp ngoặc CUỐI CÙNG. Không có ngoặc -> None.

    Lấy ngoặc CUỐI chứ không phải ngoặc đầu: tên địa chỉ trong ERPNext hay có
    ngoặc phụ ở giữa ('Cty CP ABC (chi nhánh) - Kho (BAC GIANG)'), và cái mình
    cần là cụm định danh điểm nằm ở đuôi.

    Không có ngoặc -> trả None và người gọi BỎ QUA dòng đó. Lấy cả tên địa chỉ
    làm tên điểm là đẻ ra một rừng điểm rác trùng nhau.
    """
    found = _PAREN_RE.findall(cstr(text))
    if not found:
        return None
    inner = norm_text(found[-1])
    return inner or None


def _match_key(name) -> str:
    """Khóa so tên điểm giữa bảng kê và địa chỉ ERPNext: bỏ dấu, HOA, gộp trắng."""
    return " ".join(_strip_tones(name).upper().split())


# ─────────────────────────────────────────────────────────────────────────
# Đọc dữ liệu nguồn
# ─────────────────────────────────────────────────────────────────────────

def _advice_stores(company):
    """(chuỗi, mã, tên) phân biệt từ CÁC DÒNG BẢNG KÊ đã nạp, kèm khách hàng.

    Dùng SQL thô thay vì ORM: cần GROUP BY hai bảng cha-con với đếm số lần xuất
    hiện để chọn tên phổ biến nhất khi một mã có nhiều tên. `frappe.get_all`
    không diễn đạt được phép này mà không nạp cả trăm nghìn dòng con lên RAM.
    """
    return frappe.db.sql("""
        SELECT a.chain                        AS chain,
               IFNULL(l.store_code, '')       AS store_code,
               IFNULL(l.store_name, '')       AS store_name,
               IFNULL(a.customer, '')         AS customer,
               COUNT(*)                       AS n
        FROM `tabMT Payment Advice Line` l
        INNER JOIN `tabMT Payment Advice` a ON a.name = l.parent
        WHERE l.parenttype = 'MT Payment Advice'
          AND a.company = %(company)s
          AND IFNULL(a.chain, '') != ''
          AND (IFNULL(l.store_code, '') != '' OR IFNULL(l.store_name, '') != '')
        GROUP BY a.chain, l.store_code, l.store_name, a.customer
    """, {"company": company}, as_dict=True)


def _address_index():
    """Chỉ mục 'tên trong ngoặc CUỐI của tên địa chỉ' -> [(address, customer)].

    Nguồn TỐT HƠN file chuỗi cho Central Retail: lấy từ chính ERPNext, có sẵn
    link Customer, và là dữ liệu mình kiểm soát.

    Trả về DANH SÁCH ứng viên chứ không phải một giá trị: trùng tên là chuyện có
    thật, và ở đó phải để người chọn chứ không nối bừa.
    """
    rows = frappe.db.sql("""
        SELECT a.name AS address, a.address_title AS title,
               IFNULL(dl.link_name, '') AS customer
        FROM `tabAddress` a
        LEFT JOIN `tabDynamic Link` dl
               ON dl.parenttype = 'Address' AND dl.parent = a.name
              AND dl.link_doctype = 'Customer'
        WHERE a.name LIKE %(p)s OR IFNULL(a.address_title, '') LIKE %(p)s
    """, {"p": "%(%"}, as_dict=True)

    idx = {}
    for r in rows:
        inner = name_in_last_parens(r.title) or name_in_last_parens(r.address)
        if not inner:
            continue
        idx.setdefault(_match_key(inner), []).append((r.address, r.customer or ""))
    return idx


def _existing_stores():
    """Master hiện có: (chuỗi, mã) -> bản ghi."""
    out = {}
    for r in frappe.get_all("MT Store",
                            fields=["name", "chain", "store_code", "store_name",
                                    "customer", "address", "active"],
                            limit_page_length=0):
        out[(r.chain, norm_store_code(r.store_code))] = r
    return out


# ─────────────────────────────────────────────────────────────────────────
# Dựng kế hoạch
# ─────────────────────────────────────────────────────────────────────────

def _build_plan(company):
    """Kế hoạch dựng master. THUẦN ĐỌC — không ghi gì.

    Trả (plan, warnings). `plan` đã sắp xếp ổn định để vân tay không đổi giữa
    hai lần xem trước trên cùng dữ liệu.
    """
    rows = _advice_stores(company)
    warnings = []

    # Chuỗi nào CÓ mã điểm? Quyết định bằng dữ liệu, không bằng hằng số.
    has_code = set()
    for r in rows:
        if norm_store_code(r.store_code):
            has_code.add(r.chain)

    # (chuỗi, mã) -> {tên: số lần}, {khách: số lần}
    agg = {}
    for r in rows:
        code = norm_store_code(r.store_code)
        name = norm_text(r.store_name)
        if not code:
            # Chuỗi này CÓ mã ở chỗ khác -> dòng thiếu mã là dòng tổng/dòng lạ,
            # bỏ qua. Sinh mã từ tên ở đây sẽ đẻ ra điểm rác TRÙNG với điểm thật.
            if r.chain in has_code:
                if name:
                    warnings.append(
                        "%s: tên '%s' không kèm mã điểm trong khi chuỗi này CÓ mã — "
                        "bỏ qua (nhiều khả năng là dòng pháp nhân mẹ, không phải điểm)."
                        % (r.chain, name[:60]))
                continue
            if not name:
                continue
            code = code_from_name(name)
            if not code:
                warnings.append("%s: tên '%s' không sinh được mã — bỏ qua."
                                % (r.chain, name[:60]))
                continue
        key = (r.chain, code)
        e = agg.setdefault(key, {"names": {}, "customers": {}, "n": 0,
                                 "synth": r.chain not in has_code})
        e["n"] += cint(r.n)
        if name:
            e["names"][name] = e["names"].get(name, 0) + cint(r.n)
        if r.customer:
            e["customers"][r.customer] = e["customers"].get(r.customer, 0) + cint(r.n)

    if len(agg) > MAX_SEED:
        frappe.throw(_(
            "Dựng ra {0} điểm siêu thị — vượt trần {1}. Gần như chắc chắn một cột "
            "đã bị đọc nhầm thành mã điểm. KHÔNG ghi gì; kiểm lại bảng kê đã nạp."
        ).format(len(agg), MAX_SEED))

    addr_idx = _address_index()
    existing = _existing_stores()

    plan = []
    for (chain, code), e in sorted(agg.items()):
        issues = []

        # Tên: chọn bản phổ biến nhất. Nhiều tên cho một mã là dấu hiệu chuỗi đổi
        # tên điểm giữa kỳ — chọn hộ nhưng PHẢI nói ra, không chọn im lặng.
        names = sorted(e["names"].items(), key=lambda kv: (-kv[1], kv[0]))
        if len(names) > 1:
            issues.append("mã này có %d tên khác nhau: %s"
                          % (len(names), " · ".join(n for n, _c in names[:3])))
        if names:
            store_name = names[0][0]
        else:
            # Chuỗi in mã mà không in tên (AEON, Fuji). Tên tạm = mã, và nói rõ.
            store_name = code
            issues.append("bảng kê KHÔNG có tên điểm — tạm dùng mã làm tên, kế toán sửa lại")

        # Khách hàng: chỉ nhận khi MỌI bảng kê chứa điểm này cùng trỏ một khách.
        # Nhiều khách = không tự chọn: gán sai pháp nhân là cả kỳ công nợ chạy
        # sang khách khác, và không tổng nào phát hiện ra.
        customers = sorted(e["customers"].items(), key=lambda kv: (-kv[1], kv[0]))
        customer = customers[0][0] if len(customers) == 1 else ""
        if len(customers) > 1:
            issues.append("điểm này xuất hiện ở bảng kê của %d khách khác nhau: %s "
                          "— để trống, kế toán chọn"
                          % (len(customers), " · ".join(c for c, _n in customers[:3])))

        # Địa chỉ: chỉ nối khi có ĐÚNG MỘT ứng viên khớp tên trong ngoặc cuối.
        address = ""
        cands = addr_idx.get(_match_key(store_name)) or []
        if len(cands) == 1:
            address, addr_cus = cands[0]
            if customer and addr_cus and addr_cus != customer:
                # Địa chỉ thuộc pháp nhân khác -> không nối. Buyer info sai là
                # hóa đơn sai MST người mua.
                issues.append("địa chỉ '%s' thuộc khách %s, không phải %s — không nối"
                              % (address, addr_cus, customer))
                address = ""
            elif not customer and addr_cus:
                customer = addr_cus
        elif len(cands) > 1:
            issues.append("có %d địa chỉ cùng tên trong ngoặc — không nối, kế toán chọn"
                          % len(cands))

        old = existing.get((chain, code))
        if old is None:
            status = STATUS_NEW
        elif (norm_text(old.store_name) == store_name
              and cstr(old.customer or "") == cstr(customer or "")):
            status = STATUS_EXISTS
        else:
            status = STATUS_DIFF
            issues.append("bản ghi hiện có: tên '%s', khách '%s' — seed KHÔNG đè"
                          % (old.store_name, old.customer or "(trống)"))

        plan.append({
            "chain": chain,
            "store_code": code,
            "store_name": store_name,
            "customer": customer,
            "address": address,
            "n_lines": e["n"],
            # Mã do mình sinh ra từ tên chứ không phải chuỗi in — người xem phải
            # biết để không đi tìm mã này trong file của chuỗi.
            "code_synthesized": bool(e["synth"]),
            "status": status,
            "status_label": STATUS_LABEL[status],
            "existing": old.name if old else None,
            "issues": issues,
        })
    return plan, warnings


def _plan_hash(plan):
    """Vân tay của ĐÚNG kế hoạch người vừa xem.

    Giữa lúc xem trước và lúc bấm tạo, một bảng kê mới nạp (hoặc một điểm vừa
    được tạo tay) làm kế hoạch đổi mà không ai nhìn thấy. So vân tay thì lệch
    một dòng cũng dừng lại.
    """
    h = hashlib.sha1()
    for p in plan:
        h.update("S|{}|{}|{}|{}|{}|{}\n".format(
            p["chain"], p["store_code"], p["store_name"],
            p["customer"] or "", p["address"] or "", p["status"]).encode())
    return h.hexdigest()


def _summary(plan):
    n = {STATUS_NEW: 0, STATUS_EXISTS: 0, STATUS_DIFF: 0}
    for p in plan:
        n[p["status"]] += 1
    by_chain = {}
    for p in plan:
        c = by_chain.setdefault(p["chain"], {"chain": p["chain"], "total": 0,
                                             "moi": 0, "da_co": 0, "lech": 0,
                                             "thieu_khach": 0})
        c["total"] += 1
        c[p["status"]] += 1
        if not p["customer"]:
            c["thieu_khach"] += 1
    return {
        "total": len(plan),
        "moi": n[STATUS_NEW],
        "da_co": n[STATUS_EXISTS],
        "lech": n[STATUS_DIFF],
        "thieu_khach": sum(1 for p in plan if not p["customer"]),
        "co_van_de": sum(1 for p in plan if p["issues"]),
        "by_chain": sorted(by_chain.values(), key=lambda x: -x["total"]),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Whitelisted
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def preview_seed(company=None):
    """XEM TRƯỚC danh sách điểm siêu thị dựng được. KHÔNG ghi bất cứ thứ gì.

    Bắt buộc chạy trước `commit_seed` — trả về `plan_hash` mà commit đòi.
    """
    guard_mt()
    _require_tables()
    company = _company(company)

    plan, warnings = _build_plan(company)
    return {
        "company": company,
        "plan_hash": _plan_hash(plan),
        "summary": _summary(plan),
        "stores": plan,
        "warnings": warnings,
        "note": _(
            "Điểm được dựng từ CÁC BẢNG KÊ ĐÃ NẠP trên site, không phải từ file mẫu. "
            "Chuỗi chưa nạp bảng kê nào thì chưa dựng được điểm nào. "
            "Seed chỉ THÊM điểm chưa có — không bao giờ đè bản ghi kế toán đã sửa."
        ),
    }


@frappe.whitelist()
def commit_seed(expected_hash=None, company=None):
    """Tạo `MT Store` cho các điểm CHƯA CÓ. Không đè, không xóa, không sửa.

    Đòi vân tay của bản xem trước: dữ liệu đổi giữa chừng là dừng, không ghi gì.
    """
    guard_manager()
    _require_tables()
    company = _company(company)

    plan, warnings = _build_plan(company)
    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới tạo được"))
    if _plan_hash(plan) != expected_hash:
        frappe.throw(_(
            "Dữ liệu đã đổi kể từ lúc xem trước (có bảng kê mới nạp, hoặc điểm vừa "
            "được tạo tay). Xem lại rồi tạo — không ghi gì cả."
        ))

    created, failed = [], []
    for i, p in enumerate(plan):
        if p["status"] != STATUS_NEW:
            continue
        # SAVEPOINT cho từng điểm. Không có nó thì một `insert()` nổ giữa chừng
        # để lại transaction bẩn, và mọi điểm SAU đó cũng hỏng theo — try/except
        # trông như đã cô lập lỗi trong khi thực ra chưa.
        sp = "mt_store_%d" % i
        try:
            frappe.db.savepoint(sp)
            doc = frappe.new_doc("MT Store")
            doc.chain = p["chain"]
            doc.store_code = p["store_code"]
            doc.store_name = p["store_name"]
            doc.customer = p["customer"] or None
            doc.address = p["address"] or None
            doc.active = 1
            doc.seeded_from = "Bảng kê đã nạp (%d dòng)" % cint(p["n_lines"])
            if p["issues"]:
                doc.note = "\n".join("• " + i for i in p["issues"])
            doc.insert()
            created.append(doc.name)
        except Exception as e:                                   # noqa: BLE001
            # MỘT điểm hỏng KHÔNG được làm hỏng cả mẻ: 208 điểm mà dừng ở điểm
            # thứ 3 thì kế toán phải dò tay 205 điểm còn lại.
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:                                    # noqa: BLE001
                pass
            frappe.log_error(frappe.get_traceback(), "mt_store.commit_seed")
            failed.append({"chain": p["chain"], "store_code": p["store_code"],
                           "error": cstr(e)[:200]})

    frappe.db.commit()
    return {
        "created": len(created),
        "names": created[:200],
        "failed": failed,
        "skipped_existing": sum(1 for p in plan if p["status"] == STATUS_EXISTS),
        "skipped_diff": sum(1 for p in plan if p["status"] == STATUS_DIFF),
        "warnings": warnings,
        "message": _("Đã tạo {0} điểm siêu thị. Bỏ qua {1} điểm đã có.").format(
            len(created), sum(1 for p in plan if p["status"] != STATUS_NEW)),
    }


@frappe.whitelist()
def list_stores(chain=None, customer=None, search=None, active=None,
                page=1, page_size=50, company=None):
    """Danh sách điểm siêu thị, có lọc + chia trang."""
    guard_mt()
    _require_tables()
    _company(company)   # gọi để CHỐT QUYỀN; master không lọc theo công ty (xem _company)

    page = max(1, cint(page) or 1)
    page_size = min(200, max(1, cint(page_size) or 50))

    where = ["1 = 1"]
    params = {}
    if chain:
        where.append("s.chain = %(chain)s")
        params["chain"] = chain
    if customer:
        where.append("s.customer = %(customer)s")
        params["customer"] = customer
    if active not in (None, ""):
        where.append("s.active = %(active)s")
        params["active"] = cint(active)
    if search:
        where.append("(s.store_code LIKE %(q)s OR s.store_name LIKE %(q)s "
                     "OR s.vendor_code LIKE %(q)s OR s.customer LIKE %(q)s)")
        params["q"] = "%" + cstr(search).strip() + "%"
    clause = " AND ".join(where)

    total = cint(frappe.db.sql(
        "SELECT COUNT(*) FROM `tabMT Store` s WHERE " + clause, params)[0][0])

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = frappe.db.sql("""
        SELECT s.name, s.chain, s.store_code, s.store_name, s.customer,
               s.address, s.tax_id, s.vendor_code, s.active, s.seeded_from, s.note,
               cus.customer_name
        FROM `tabMT Store` s
        LEFT JOIN `tabCustomer` cus ON cus.name = s.customer
        WHERE {clause}
        ORDER BY s.chain, s.store_code
        LIMIT %(limit)s OFFSET %(offset)s
    """.format(clause=clause), params, as_dict=True)

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 1,
        "chains": _chain_options(),
    }


def _chain_options():
    from ketoan.api.mt import CHAIN_OPTIONS
    return list(CHAIN_OPTIONS)


@frappe.whitelist()
def save_store(name=None, chain=None, store_code=None, store_name=None,
               customer=None, address=None, tax_id=None, vendor_code=None,
               active=None, note=None):
    """Tạo/sửa MỘT điểm. Đi qua Document nên `validate()` của DocType vẫn chạy.

    VÌ SAO không cho `Ke Toan MT` ghi thẳng trên Desk mà bắt đi đường này: mở/đóng
    điểm là việc thưa nhưng sai thì ĐỊNH TUYẾN TIỀN SAI — điểm gắn nhầm pháp nhân
    là cả kỳ công nợ chạy sang khách khác. Guard ở đây là kế toán trưởng.
    """
    guard_manager()
    _require_tables()

    doc = frappe.get_doc("MT Store", name) if name else frappe.new_doc("MT Store")
    if not name:
        doc.chain = chain
        doc.store_code = store_code
        doc.seeded_from = "Nhập tay"
    elif chain and chain != doc.chain:
        # Đổi chuỗi của một điểm đã có là đổi KHÓA TỰ NHIÊN. Không cấm, nhưng
        # phải đi qua validate để không đụng khóa của điểm khác.
        doc.chain = chain
    if store_name is not None:
        doc.store_name = store_name
    if store_code is not None and name:
        doc.store_code = store_code
    # `None` = client KHÔNG gửi field -> giữ nguyên. Chuỗi rỗng = client CỐ Ý xóa.
    # Không phân biệt hai ca này thì một lần gọi thiếu tham số sẽ âm thầm gỡ pháp
    # nhân của điểm — và công nợ của điểm đó biến mất khỏi mọi báo cáo theo khách.
    if customer is not None:
        doc.customer = customer or None
    if address is not None:
        doc.address = address or None
    if tax_id is not None:
        doc.tax_id = tax_id
    if vendor_code is not None:
        doc.vendor_code = vendor_code
    if active is not None:
        doc.active = cint(active)
    if note is not None:
        doc.note = note

    doc.save()
    frappe.db.commit()
    return {"name": doc.name, "chain": doc.chain, "store_code": doc.store_code,
            "store_name": doc.store_name, "customer": doc.customer,
            "address": doc.address, "active": cint(doc.active)}


@frappe.whitelist()
def search_addresses(txt=None, customer=None, limit=20):
    """Gợi ý địa chỉ để gán cho điểm. Chỉ đọc.

    Lọc theo khách khi có: gán nhầm địa chỉ của pháp nhân khác là in hóa đơn sai
    MST người mua, nên đừng mời người dùng chọn thứ họ không được phép chọn.
    """
    guard_mt()
    # KHÔNG `_require_tables()`: hàm này chỉ đọc `tabAddress` — bảng lõi luôn có.
    # Đòi bảng MT ở đây là dựng một rào chắn giả cho một việc không liên quan.
    limit = min(50, max(1, cint(limit) or 20))
    where = ["1 = 1"]
    params = {"limit": limit}
    if txt:
        where.append("(a.name LIKE %(q)s OR IFNULL(a.address_title, '') LIKE %(q)s)")
        params["q"] = "%" + cstr(txt).strip() + "%"
    if customer:
        where.append("EXISTS (SELECT 1 FROM `tabDynamic Link` dl "
                     "WHERE dl.parenttype = 'Address' AND dl.parent = a.name "
                     "AND dl.link_doctype = 'Customer' AND dl.link_name = %(cus)s)")
        params["cus"] = customer
    rows = frappe.db.sql("""
        SELECT a.name, a.address_title, a.city, a.gstin AS tax_id
        FROM `tabAddress` a
        WHERE {clause}
        ORDER BY a.name
        LIMIT %(limit)s
    """.format(clause=" AND ".join(where)), params, as_dict=True)
    return rows
