#!/usr/bin/env python3
"""Kiểm CLIENT SCRIPT Sales Invoice — chạy thật trong Chromium, không đọc mắt thường.

════════════════════════════════════════════════════════════════════════════
LOẠI LỖI BỘ KIỂM NÀY TỒN TẠI ĐỂ CHẶN
════════════════════════════════════════════════════════════════════════════

Frappe chạy các handler `refresh` NỐI TIẾP BẰNG PROMISE. Một ngoại lệ thoát ra
khỏi handler nào là promise reject, và **mọi thứ đứng sau trong chuỗi không
chạy** — kể cả phần dựng thanh công cụ của ERPNext.

Hậu quả đã xảy ra thật trên production:

    const btn = frm.add_custom_button(...);      // trả về ĐỐI TƯỢNG jQUERY
    if (btn) btn.setAttribute("data-misa-push", "1");   // -> TypeError

Kế toán mất hẳn nhóm nút **Create** (Payment · Return/Credit Note · Payment
Request …) trên form hóa đơn. Không một thông báo nào; lỗi chỉ nằm trong Console.

Và nó chỉ nổ trên MỘT SỐ hóa đơn — đúng những hóa đơn thỏa điều kiện hiện nút
"Đẩy hóa đơn sang MISA" (đã ghi sổ · không phải trả hàng · CHƯA đẩy MISA). Hóa
đơn đã đẩy rồi thì không dựng nút đó nên không nổ. Triệu chứng "chỉ vài hóa đơn
bị" là loại khó lần nhất, và là lý do phải có bộ kiểm chạy máy thay vì đọc code.

════════════════════════════════════════════════════════════════════════════
CÁCH KIỂM
════════════════════════════════════════════════════════════════════════════

Nạp CHÍNH file client script vào Chromium cùng một bộ giả `frappe` tối thiểu,
rồi gọi `refresh` trên 8 hình dạng chứng từ khác nhau.

Bộ giả cố ý KHẮT KHE: `add_custom_button` trả về một đối tượng chỉ có API của
jQuery (`attr` / `prop` / `toggleClass` / `css`), KHÔNG có `setAttribute`. Đúng
như jQuery thật. Nên code cũ ném lỗi ở đây, code mới thì không — bộ kiểm có
răng, không phải hình thức.

Chạy KHÔNG cần bench. Cần playwright + Chromium; thiếu thì báo BỎ QUA (mã thoát
0) chứ không giả vờ đạt.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPT = os.path.join(REPO, "ketoan/misa_integration/client_script_sales_invoice.js")


def _no_browser(msg):
    print("=" * 82)
    print("KIỂM CLIENT SCRIPT SALES INVOICE")
    print("=" * 82)
    print(f"  ⚠ BỎ QUA — {msg}")
    print("    Cài: pip install playwright  (Chromium đã có sẵn ở /opt/pw-browsers)")
    print("=" * 82)
    print("KẾT QUẢ: BỎ QUA — không có trình duyệt để chạy, KHÔNG kết luận gì")
    return 0


def chromium_path():
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                "/opt/pw-browsers/chromium/chrome-linux/chrome"):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[-1]
    return None


# ── bộ giả frappe ─────────────────────────────────────────────────────────
# Giữ ĐÚNG mức khắt khe của bản thật ở những chỗ đã từng gây lỗi:
#   · `add_custom_button` trả về đối tượng kiểu jQuery, KHÔNG có `setAttribute`;
#   · `$(sel)` trả về đối tượng nối chuỗi được, cũng không có API của DOM.
STUB = r"""
window.__calls = [];
window.__buttons = [];

function $jq(nodes) {
  return {
    _nodes: nodes || [],
    attr(k, v) { this._nodes.forEach(n => n.attrs[k] = v); return this; },
    prop(k, v) { this._nodes.forEach(n => n.props[k] = v); return this; },
    toggleClass(c, on) { this._nodes.forEach(n => n.classes[c] = !!on); return this; },
    addClass(c) { return this.toggleClass(c, true); },
    css(k, v) { this._nodes.forEach(n => n.css[k] = v); return this; },
    get length() { return this._nodes.length; },
  };
}

window.$ = (sel) => {
  if (typeof sel !== "string") return $jq([]);
  const m = sel.match(/^\[([\w-]+)\]$/);
  if (m) return $jq(window.__buttons.filter(b => m[1] in b.attrs));
  return $jq([]);
};

window.locals = {};

window.frappe = {
  ui: { form: { handlers: {}, on(dt, h) {
    frappe.ui.form.handlers[dt] = frappe.ui.form.handlers[dt] || {};
    for (const k in h) {
      (frappe.ui.form.handlers[dt][k] = frappe.ui.form.handlers[dt][k] || []).push(h[k]);
    }
  } } },
  call: (o) => { window.__calls.push(o && o.method); return Promise.resolve({ message: {} }); },
  db: {
    get_list: () => Promise.resolve([]),
    get_value: () => Promise.resolve({ message: {} }),
    get_doc: () => Promise.resolve({}),
  },
  model: { set_value: () => Promise.resolve(), get_value: () => null },
  msgprint: () => {},
  show_alert: () => {},
  throw: (m) => { throw new Error(m); },
  utils: { escape_html: (s) => String(s == null ? "" : s) },
  datetime: { get_today: () => "2026-08-27", nowdate: () => "2026-08-27" },
  format: (v) => String(v),
  boot: { sysdefaults: {} },
};

// `frm` giả. `add_custom_button` bắt chước jQuery THẬT: trả về đối tượng jQuery,
// KHÔNG phải DOM element — đó chính là chỗ code cũ đã ngã.
window.makeFrm = (doc) => ({
  doc: doc,
  fields_dict: {},
  __btns: [],
  add_custom_button(label, fn, group) {
    const node = { label, group: group || null, attrs: {}, props: {}, classes: {}, css: {} };
    window.__buttons.push(node);
    this.__btns.push(node);
    return $jq([node]);
  },
  set_value: () => Promise.resolve(),
  set_df_property: () => {},
  refresh_field: () => {},
  reload_doc: () => {},
  get_field: () => ({ $wrapper: $jq([]) }),
  page: { set_inner_btn_group_as_primary: () => {} },
});
"""

# 8 hình dạng chứng từ — phủ mọi nhánh `if` trong `misaButtons`.
CASES = [
    ("nháp, chưa có gì",
     {"docstatus": 0, "is_return": 0}),
    ("đã ghi sổ, CHƯA đẩy MISA  ← ca đã làm mất nút Create",
     {"docstatus": 1, "is_return": 0}),
    ("đã ghi sổ, chưa đẩy, có ref_id",
     {"docstatus": 1, "is_return": 0, "custom_misa_ref_id": "uuid-1"}),
    ("đã đẩy MISA (có pushed_at)",
     {"docstatus": 1, "is_return": 0, "custom_misa_pushed_at": "2026-08-01 09:00:00",
      "custom_misa_ref_id": "uuid-1"}),
    ("hóa đơn cũ (có vn_einvoice_lookup_code)",
     {"docstatus": 1, "is_return": 0, "vn_einvoice_lookup_code": "W1FPIZKNL0VZ"}),
    ("hóa đơn TRẢ HÀNG",
     {"docstatus": 1, "is_return": 1, "return_against": "HD-04793"}),
    ("đã phát hành, có mã tra cứu + link",
     {"docstatus": 1, "is_return": 0, "custom_misa_transaction_id": "W1FPIZKNL0VZ",
      "custom_misa_link": "https://x", "custom_misa_pushed_at": "2026-08-01 09:00:00",
      "custom_misa_ref_id": "uuid-1"}),
    ("đã hủy",
     {"docstatus": 2, "is_return": 0}),
]

RUN = r"""(payload) => {
  const out = [];
  const handlers = (frappe.ui.form.handlers["Sales Invoice"] || {}).refresh || [];
  for (const c of payload.cases) {
    window.__buttons = [];
    const doc = Object.assign(
      { name: "HD-05439", items: [], taxes: [], docstatus: 0, is_return: 0 }, c.doc);
    const frm = window.makeFrm(doc);
    let threw = null;
    try { handlers.forEach(h => h(frm)); }
    catch (e) { threw = String(e && e.message || e); }
    out.push({
      label: c.label,
      threw: threw,
      n_handlers: handlers.length,
      buttons: frm.__btns.map(b => b.label),
      push_attr: frm.__btns.filter(b => "data-misa-push" in b.attrs).length,
    });
  }
  return out;
}"""

# Bơm một lỗi vào GIỮA `misaButtons` rồi chạy lại: `refresh` vẫn phải trả về
# bình thường. Đây mới là phép kiểm hợp đồng "MISA hỏng không kéo form theo".
BREAK = r"""() => {
  const handlers = (frappe.ui.form.handlers["Sales Invoice"] || {}).refresh || [];
  const frm = window.makeFrm({ name: "HD-05439", items: [], docstatus: 1, is_return: 0 });
  frm.add_custom_button = () => { throw new TypeError("lỗi cố ý bơm vào"); };
  try { handlers.forEach(h => h(frm)); return { escaped: false }; }
  catch (e) { return { escaped: true, message: String(e && e.message || e) }; }
}"""


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _no_browser("chưa cài `playwright`")
    exe = chromium_path()
    if not exe:
        return _no_browser("không tìm thấy Chromium ở /opt/pw-browsers")

    src = open(SCRIPT, encoding="utf-8").read()
    page_html = ("<meta charset='utf-8'><script>" + STUB + "</script>"
                 + "<script>" + src + "</script>")

    print("=" * 82)
    print("KIỂM CLIENT SCRIPT SALES INVOICE — chạy thật trong Chromium")
    print("=" * 82)
    bad = 0
    errors = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe)
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_content(page_html, wait_until="load")

        if errors:
            print("  ❌ nạp file đã ném lỗi ngay: " + " · ".join(errors[:3]))
            browser.close()
            print("=" * 82)
            print("KẾT QUẢ: HỎNG — file không nạp nổi")
            return 1
        print("  ✅ nạp được, không lỗi cú pháp")

        n_handlers = page.evaluate(
            "() => ((frappe.ui.form.handlers['Sales Invoice'] || {}).refresh || []).length")
        ok = n_handlers >= 1
        print(f"  {'✅' if ok else '❌'} đăng ký được {n_handlers} handler `refresh`")
        bad += not ok

        rows = page.evaluate(RUN, {"cases": [{"label": l, "doc": d} for l, d in CASES]})
        print("-" * 82)
        for r in rows:
            ok = r["threw"] is None
            tail = "" if ok else f"  -> {r['threw']}"
            print(f"  {'✅' if ok else '❌'} refresh không ném lỗi — {r['label']}{tail}")
            bad += not ok

        # Nút đẩy phải CÓ THẬT ở ca chưa đẩy, và KHÔNG có ở ca đã đẩy.
        print("-" * 82)
        by = {r["label"]: r for r in rows}
        chua = by["đã ghi sổ, CHƯA đẩy MISA  ← ca đã làm mất nút Create"]
        ok = "Đẩy hóa đơn sang MISA" in chua["buttons"]
        print(f"  {'✅' if ok else '❌'} hóa đơn chưa đẩy -> CÓ nút 'Đẩy hóa đơn sang MISA'")
        bad += not ok

        ok = chua["push_attr"] == 1
        print(f"  {'✅' if ok else '❌'} và thuộc tính `data-misa-push` được gán THẬT vào nút "
              f"(chỗ code cũ ngã)")
        bad += not ok

        da = by["đã đẩy MISA (có pushed_at)"]
        ok = "Đẩy hóa đơn sang MISA" not in da["buttons"]
        print(f"  {'✅' if ok else '❌'} hóa đơn đã đẩy -> KHÔNG dựng nút đẩy nữa "
              f"(vì thế lỗi cũ chỉ nổ ở 'một số hóa đơn')")
        bad += not ok

        tra = by["hóa đơn TRẢ HÀNG"]
        ok = "Đẩy hóa đơn sang MISA" not in tra["buttons"]
        print(f"  {'✅' if ok else '❌'} hóa đơn trả hàng -> KHÔNG đẩy thẳng "
              f"(phải là hóa đơn thay thế/điều chỉnh trên MISA)")
        bad += not ok

        # Hợp đồng quan trọng nhất.
        print("-" * 82)
        res = page.evaluate(BREAK)
        ok = not res["escaped"]
        print(f"  {'✅' if ok else '❌'} bơm lỗi cố ý vào giữa phần MISA -> ngoại lệ KHÔNG thoát "
              f"ra khỏi `refresh`")
        bad += not ok
        if not ok:
            print(f"       thoát ra: {res.get('message')}")
        print("       (thoát ra là gãy chuỗi promise của Frappe -> mất nhóm nút Create)")

        browser.close()

    # Chốt bằng mã nguồn: cấm hẳn lối cũ quay lại.
    print("-" * 82)
    ok = "setAttribute" not in src.split("// ---")[0] and \
        "btn.setAttribute" not in src
    print(f"  {'✅' if ok else '❌'} không còn `btn.setAttribute` trên giá trị trả về của "
          f"`add_custom_button`")
    bad += not ok

    ok = "try {" in src and "misaButtons" in src
    print(f"  {'✅' if ok else '❌'} phần MISA nằm trong try/catch, tách khỏi handler")
    bad += not ok

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} phép")
        return 1
    print("KẾT QUẢ: ĐẠT — refresh không ném lỗi ở mọi hình dạng chứng từ, và lỗi trong "
          "phần MISA không kéo theo thanh công cụ của ERPNext")
    return 0


if __name__ == "__main__":
    sys.exit(main())
