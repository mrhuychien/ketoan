"""misa_legacy — chuyển tiếp số hóa đơn nhập tay sang nhóm field MISA.

Bối cảnh: trước khi có tích hợp, kế toán gõ tay số hóa đơn vào
`vn_einvoice_number`. Luồng tự động lại ghi vào `custom_misa_inv_no`. Đối soát
(`misa_reconcile`) chỉ đọc nhóm `custom_misa_*`, nên toàn bộ hóa đơn cũ trông
như "chưa có số" — rơi hết vào rổ "Chỉ có trên phần mềm", còn bản MISA tương ứng
rơi vào rổ "Chỉ có trên MISA". Hai rổ cảnh báo đầy báo động giả.

Module này chép ngược `vn_einvoice_number` → `custom_misa_inv_no` (+ ký hiệu,
ngày, trạng thái) cho hóa đơn cũ.

Ràng buộc:
  · XEM TRƯỚC bắt buộc. Ghi số hóa đơn sai là sai báo cáo thuế.
  · KHÔNG `save()` — chứng từ đã ghi sổ, chỉ `db_set(update_modified=False)`.
  · KHÔNG đè `custom_misa_inv_no` đang có số. Luồng tự động là nguồn đáng tin
    hơn con người gõ tay.
  · KHÔNG chép `vn_einvoice_lookup_code` khi nó là uuid rác của luồng cũ
    (§L.4.1) — mã đó tra cứu ra con số 0.
  · KHÔNG ghi khi số hóa đơn không đọc được hoặc trùng với hóa đơn khác. Dòng
    nào không chắc thì bỏ lại cho người xử lý, không đoán.
"""

import hashlib
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, getdate

from ketoan.api._guard import guard_manager, guard_sales_any, resolve_company
from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)

LEGACY_NO = "vn_einvoice_number"
LEGACY_DATE = "vn_einvoice_date"
LEGACY_LOOKUP = "vn_einvoice_lookup_code"

# Ký hiệu theo TT78: 1 ký tự loại + C/K + 2 số năm + 3 ký tự do NBH đặt (1C25MHG).
# Mẫu cũ TT32 dạng AA/20E có một gạch chéo nên cũng phải lọt.
#
# BẮT BUỘC có ít nhất một chữ cái: '2025-000123' tách ra đầu là '2025', nhận
# nhầm cái đó làm ký hiệu là gán số hóa đơn vào một ký hiệu không tồn tại.
SERIES_PLAUSIBLE = re.compile(r"^(?=[0-9A-Z/]{5,12}$)(?=.*[A-Z])[0-9A-Z]+(/[0-9A-Z]+)?$")

# Mã tra cứu thật của MISA: chữ+số liền, không gạch (vd W1FPIZKNL0VZ).
# uuid của luồng cũ có gạch nối nên rớt ở đây — đúng ý đồ.
LOOKUP_PLAUSIBLE = re.compile(r"^[0-9A-Za-z]{8,24}$")

TRAILING_NUMBER = re.compile(r"(\d+)\s*$")


def _has(field: str) -> bool:
    return bool(frappe.get_meta("Sales Invoice").has_field(field))


def parse_legacy(value, default_series=None):
    """Tách '1C25MHG/0000123' → (ký hiệu, số, lý do bỏ qua).

    Trả về (series, inv_no, reason). reason khác None nghĩa là KHÔNG được ghi.
    """
    raw = norm_text(value)
    if not raw:
        return None, None, "trong"

    m = TRAILING_NUMBER.search(raw)
    if not m:
        # Không có cụm số ở cuối: '1C25MHG', '123 (đã hủy)', 'chưa xuất'…
        # Đoán ở đây là gán nhầm số hóa đơn cho khách khác.
        return None, None, "khong_doc_duoc"

    inv_no = m.group(1)
    head = raw[: m.start()].strip(" /-\\|.,")

    if head:
        # Kiểm và ghi CÙNG MỘT giá trị. Nếu kiểm ở dạng đã bỏ khoảng trắng rồi
        # lại ghi dạng còn khoảng trắng thì cả hai chốt chặn đều vô hiệu:
        # '1C25MHG 123, 124' (ô chứa hai số hóa đơn) sẽ lọt khuôn, ghi ký hiệu
        # rác '1C25MHG 123' và âm thầm vứt mất số 124.
        #
        # SERIES_PLAUSIBLE chỉ nhận [0-9A-Z/] nên mọi ô có khoảng trắng hay dấu
        # phẩy ở phần đầu đều rơi xuống "ký hiệu lạ" — người xem và sửa tay.
        series = norm_series(head)
        if not SERIES_PLAUSIBLE.match(series):
            return series, inv_no, "ky_hieu_la"
        return series, inv_no, None

    series = norm_series(default_series or "")
    if not series:
        return None, inv_no, "thieu_ky_hieu"
    return series, inv_no, None


def _lookup_value(v, known_txn):
    """Mã tra cứu chỉ được chép khi trông như mã THẬT và MISA XÁC NHẬN có.

    `custom_misa_transaction_id` là khóa khớp tầng 2 với độ tin "Chắc chắn"
    (misa_reconcile._match_one). Một mã nội bộ kiểu 'SO2024000123' cũng lọt
    khuôn chữ+số, chép vào là tạo ra một liên kết SAI mà máy tự tin.
    """
    s = norm_text(v)
    if not s or not LOOKUP_PLAUSIBLE.match(s):
        return None
    return s if s in known_txn else None


def _source_rows(company, year=None, limit=100000):
    """Hóa đơn đã ghi sổ có số nhập tay mà nhóm MISA còn trống.

    Lấy dư 1 dòng để biết có bị cắt hay không — cắt âm thầm ở đây nghĩa là báo
    "đã chép hết" trong khi còn hàng nghìn hóa đơn chưa đụng tới.
    """
    # `col > ''` giữ được index; IFNULL(col,'') != '' thì không.
    conds = ["si.docstatus = 1", "si.company = %(company)s",
             f"si.{LEGACY_NO} > ''",
             "IFNULL(si.custom_misa_inv_no, '') = ''"]
    params = {"limit": cint(limit) + 1, "company": company}
    if year:
        # BETWEEN dùng được index posting_date; YEAR(posting_date)=x thì không.
        conds.append("si.posting_date BETWEEN %(y_from)s AND %(y_to)s")
        params["y_from"] = f"{cint(year)}-01-01"
        params["y_to"] = f"{cint(year)}-12-31"

    date_col = f"si.{LEGACY_DATE}" if _has(LEGACY_DATE) else "NULL"
    lookup_col = f"si.{LEGACY_LOOKUP}" if _has(LEGACY_LOOKUP) else "NULL"

    return frappe.db.sql(
        f"""
        SELECT si.name, si.posting_date, si.customer_name, si.grand_total,
               si.{LEGACY_NO} AS legacy_no,
               {date_col} AS legacy_date,
               {lookup_col} AS legacy_lookup,
               si.custom_misa_transaction_id AS txn
        FROM `tabSales Invoice` si
        WHERE {' AND '.join(conds)}
        ORDER BY si.posting_date, si.name
        LIMIT %(limit)s
        """,
        params, as_dict=True,
    )


def _taken_index():
    """(ký hiệu, số chuẩn hóa) đã thuộc về hóa đơn nào — để không cấp trùng.

    Trả về thêm chỉ mục CHỈ THEO SỐ: luồng đồng bộ có thể đã ghi số mà bỏ trống
    ký hiệu (misa_sync ghi `InvSeries or ''`). Khóa ('', '123') không bao giờ
    đụng ('1C25MHG', '123'), nên nếu chỉ so khóa đủ cặp thì hai hóa đơn đã ghi
    sổ cùng mang số 123 mà không ai biết.
    """
    rows = frappe.db.sql(
        """
        SELECT name, custom_misa_inv_series AS s, custom_misa_inv_no AS n
        FROM `tabSales Invoice`
        WHERE custom_misa_inv_no > ''
        """, as_dict=True)
    full, no_series = {}, {}
    for r in rows:
        num = norm_inv_no(r.n)
        full[(norm_series(r.s), num)] = r.name
        if not norm_series(r.s):
            no_series[num] = r.name
    return full, no_series


def _snapshot_index():
    """Số hóa đơn + mã tra cứu có mặt bên MISA — chép xong là nối được ngay."""
    rows = frappe.db.sql(
        """SELECT inv_series AS s, inv_no_norm AS n, transaction_id AS t
           FROM `tabMISA Invoice Snapshot`""", as_dict=True)
    keys = {(norm_series(r.s), cstr(r.n)) for r in rows if cstr(r.n)}
    txns = {norm_text(r.t) for r in rows if norm_text(r.t)}
    return keys, txns


REASON_LABEL = {
    "khong_doc_duoc": "Không đọc được số hóa đơn",
    "ky_hieu_la": "Phần đầu không giống ký hiệu hóa đơn",
    "thieu_ky_hieu": "Không có ký hiệu (chọn ký hiệu mặc định để nạp)",
    "trung_so": "Số này đã thuộc về hóa đơn khác",
    "ngay_hong": "Ngày hóa đơn cũ không đọc được",
}


def _legacy_date(value):
    """Ngày hóa đơn cũ → đối tượng date, hoặc None.

    `vn_einvoice_date` KHÔNG do app này tạo (không có trong install.py) nên
    không đảm bảo là fieldtype Date — nơi khác trong repo đều phải dò
    `has_column` trước khi đụng. Nếu nó là Data và kế toán gõ '05/12/2024' hay
    'chưa có', đưa thẳng chuỗi đó vào cột Date sẽ nổ giữa vòng lặp, SAU khi đã
    commit một phần — lô ghi dở, không biết dừng ở đâu.
    """
    if value in (None, ""):
        return None
    try:
        return getdate(value)
    except Exception:
        return False   # có giá trị nhưng hỏng — khác hẳn với "không có"


def _plan(company, year=None, default_series=None, limit=100000):
    """Dựng kế hoạch chép. Không ghi gì — dùng chung cho xem trước và nạp thật."""
    limit = cint(limit) or 100000
    rows = _source_rows(company, year=year, limit=limit)
    truncated = len(rows) > limit
    rows = rows[:limit]

    taken, taken_no_series = _taken_index()
    snap_keys, snap_txns = _snapshot_index()

    ok, skipped = [], []
    by_year = defaultdict(lambda: {"total": 0, "ok": 0, "skipped": 0, "series": defaultdict(int)})
    seen = {}   # bắt trùng ngay trong chính lô này

    for r in rows:
        y = getdate(r.posting_date).year if r.posting_date else 0
        bucket = by_year[y]
        bucket["total"] += 1

        series, inv_no, reason = parse_legacy(r.legacy_no, default_series)
        num = norm_inv_no(inv_no or "")
        key = (norm_series(series or ""), num)
        owner = taken.get(key) or seen.get(key) or taken_no_series.get(num)

        if not reason and owner and owner != r.name:
            reason = "trung_so"

        d = _legacy_date(r.legacy_date)
        if not reason and d is False:
            reason = "ngay_hong"

        item = {
            "name": r.name,
            "posting_date": cstr(r.posting_date),
            "customer_name": r.customer_name,
            "grand_total": r.grand_total,
            "legacy_no": r.legacy_no,
            "inv_series": series,
            "inv_no": inv_no,
            # Không có ngày phát hành thì để TRỐNG. Lấy posting_date thay thế là
            # bịa ngày hóa đơn: hóa đơn ghi sổ 31/03 phát hành 02/04 sẽ bị khai
            # sai kỳ thuế. Nguyên tắc của module: không chắc thì không đoán.
            "inv_date": cstr(d) if d else "",
            "lookup": _lookup_value(r.legacy_lookup, snap_txns) if not norm_text(r.txn) else None,
            "on_misa": key in snap_keys,
            "conflict_with": owner if owner != r.name else None,
        }

        if reason:
            item["reason"] = reason
            item["reason_label"] = REASON_LABEL.get(reason, reason)
            skipped.append(item)
            bucket["skipped"] += 1
        else:
            seen[key] = r.name
            ok.append(item)
            bucket["ok"] += 1
            bucket["series"][series] += 1

    years = [
        {"year": y, "total": v["total"], "ok": v["ok"], "skipped": v["skipped"],
         "series": sorted(v["series"].items(), key=lambda x: -x[1])}
        for y, v in sorted(by_year.items())
    ]
    return ok, skipped, years, truncated


def _plan_hash(ok):
    """Vân tay của đúng kế hoạch người vừa xem.

    `commit` dựng lại kế hoạch từ đầu, nên giữa lúc xem trước và lúc bấm nạp,
    một người khác sửa `vn_einvoice_number` là số đó được ghi mà chẳng ai nhìn
    thấy. So vân tay thì lệch một dòng cũng dừng lại.
    """
    h = hashlib.sha1()
    for x in ok:
        h.update(f"{x['name']}|{x['inv_series']}|{x['inv_no']}|{x['inv_date']}\n".encode())
    return h.hexdigest()


def _check_series(default_series):
    """Ký hiệu mặc định do client gửi lên — ghi cho CẢ LÔ nên phải soi kỹ."""
    v = norm_series(default_series or "")
    if not v:
        return ""
    if not SERIES_PLAUSIBLE.match(v):
        frappe.throw(_("Ký hiệu {0} không đúng khuôn ký hiệu hóa đơn").format(v))
    known = series_options()
    if known and v not in known:
        frappe.throw(_(
            "Ký hiệu {0} không có trong danh sách ký hiệu đang dùng ({1}). "
            "Khai thêm ở MISA Settings nếu đúng là ký hiệu của công ty."
        ).format(v, ", ".join(known)))
    return v


@frappe.whitelist()
def preview(company=None, year=None, default_series=None, limit=100000):
    """Xem trước: sẽ chép bao nhiêu, bỏ bao nhiêu, vì sao bỏ.

    KHÔNG ghi bất cứ thứ gì. Bắt buộc chạy trước `commit`.
    """
    guard_sales_any()
    if not _has("custom_misa_inv_no") or not _has(LEGACY_NO):
        return {"supported": False, "note": _("Site chưa có đủ field để chuyển tiếp")}

    company = resolve_company(company)
    if not company:
        frappe.throw(_("Chưa xác định được công ty"))
    default_series = _check_series(default_series)

    ok, skipped, years, truncated = _plan(company, year, default_series, limit)
    return {
        "supported": True,
        "company": company,
        "can_run": _is_chief(),
        "default_series_options": series_options(),
        "total": len(ok) + len(skipped),
        "ok": len(ok),
        "skipped": len(skipped),
        "truncated": truncated,
        "on_misa": sum(1 for x in ok if x["on_misa"]),
        "with_lookup": sum(1 for x in ok if x["lookup"]),
        "no_date": sum(1 for x in ok if not x["inv_date"]),
        "years": years,
        "plan_hash": _plan_hash(ok),
        "sample": ok[:20],
        "problems": skipped[:100],
        "problem_counts": _count_reasons(skipped),
    }


def _count_reasons(skipped):
    c = defaultdict(int)
    for x in skipped:
        c[x["reason"]] += 1
    return [{"reason": k, "label": REASON_LABEL.get(k, k), "count": v}
            for k, v in sorted(c.items(), key=lambda x: -x[1])]


def _is_chief():
    from ketoan.api._guard import is_chief
    return is_chief()


def series_options():
    """Ký hiệu đang dùng, khai trong MISA Settings — mỗi dòng một ký hiệu."""
    try:
        raw = frappe.db.get_single_value("MISA Settings", "inv_series_list") or ""
    except Exception:
        raw = ""
    out = []
    for line in cstr(raw).splitlines():
        v = norm_series(line)
        if v and v not in out:
            out.append(v)
    return out


@frappe.whitelist()
def commit(company=None, year=None, default_series=None, limit=100000, rematch=1,
           expected_hash=None):
    """Chép thật. Chỉ ghi những dòng `preview` xếp vào nhóm nạp được.

    `expected_hash` là vân tay kế hoạch lấy từ `preview` — bắt buộc. Không có
    nó thì "xem trước bắt buộc" chỉ là lời hứa suông.
    """
    guard_manager()
    if not _has("custom_misa_inv_no") or not _has(LEGACY_NO):
        frappe.throw(_("Site chưa có đủ field để chuyển tiếp"))

    company = resolve_company(company)
    if not company:
        frappe.throw(_("Chưa xác định được công ty"))
    default_series = _check_series(default_series)

    ok, skipped, years, truncated = _plan(company, year, default_series, limit)
    if not ok:
        return {"written": 0, "skipped": len(skipped), "years": years,
                "message": _("Không có hóa đơn nào đủ điều kiện chép")}

    if not expected_hash:
        frappe.throw(_("Phải xem trước rồi mới nạp được"))
    if _plan_hash(ok) != expected_hash:
        frappe.throw(_(
            "Dữ liệu đã đổi kể từ lúc xem trước (có người vừa sửa số hóa đơn). "
            "Xem lại rồi nạp — không ghi gì cả."
        ))

    has_txn = _has("custom_misa_transaction_id")
    has_status = _has("custom_misa_status")
    has_note = _has("custom_misa_note")
    note_text = _("Số hóa đơn chuyển từ {0} (nhập tay)").format(LEGACY_NO)

    written = 0
    dates = []
    for i, x in enumerate(ok):
        values = {
            "custom_misa_inv_series": x["inv_series"],
            "custom_misa_inv_no": x["inv_no"],
        }
        if x["inv_date"]:
            values["custom_misa_inv_date"] = x["inv_date"]
            dates.append(getdate(x["inv_date"]))
        if has_status:
            values["custom_misa_status"] = "Đã phát hành"
        if has_txn and x["lookup"]:
            values["custom_misa_transaction_id"] = x["lookup"]
        if has_note:
            # Ô ghi chú đang mang cảnh báo đối soát của misa_sync/misa_push và
            # cả chữ kế toán tự gõ. Đè lên là xóa mất cảnh báo thật.
            old = frappe.db.get_value("Sales Invoice", x["name"], "custom_misa_note")
            if not norm_text(old):
                values["custom_misa_note"] = note_text

        # Chứng từ đã ghi sổ: chỉ db_set, không save. Xem docstring module.
        frappe.db.set_value("Sales Invoice", x["name"], values, update_modified=False)
        written += 1
        if (i + 1) % 200 == 0:
            frappe.db.commit()

    frappe.db.commit()

    # Chép xong mới nối được với bản MISA — nhưng đối soát phải chạy lại thì
    # rổ mới đổi. Chạy nền vì một năm có thể hơn chục nghìn bản ghi.
    #
    # relink=0, KHÔNG phải 1. relink=1 khớp lại cả snapshot đã nối đúng, mà
    # `_si_index` chỉ nạp Sales Invoice theo posting_date trong đúng khoảng
    # này — hóa đơn ghi sổ ngoài khoảng sẽ vắng mặt, snapshot đang nối đúng với
    # nó bị gỡ thành "Chỉ có trên MISA". Đợt chép nhằm dọn báo động giả lại đẻ
    # ra báo động giả mới. Snapshot của mấy hóa đơn vừa chép vốn đang chưa nối
    # nên relink=0 đã quét tới, không cần đụng phần còn lại.
    #
    # Vẫn nới khoảng ±35 ngày: ngày phát hành và ngày ghi sổ lệch nhau vài ngày
    # là chuyện thường, mà hai đầu của `match_snapshots` lọc theo hai cột khác
    # nhau (snapshot theo inv_date, Sales Invoice theo posting_date).
    queued = False
    rng = None
    if dates:
        from frappe.utils import add_days
        rng = [cstr(add_days(min(dates), -35)), cstr(add_days(max(dates), 35))]
        if cint(rematch):
            frappe.enqueue(
                "ketoan.api.misa_reconcile.match_snapshots",
                queue="long", timeout=1800,
                from_date=rng[0], to_date=rng[1], relink=0,
            )
            queued = True

    return {
        "written": written,
        "skipped": len(skipped),
        "truncated": truncated,
        "years": years,
        "rematch_queued": queued,
        "range": rng,
        "message": _("Đã chép {0} số hóa đơn, bỏ qua {1}").format(written, len(skipped)),
    }
