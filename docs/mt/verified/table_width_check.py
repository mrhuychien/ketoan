#!/usr/bin/env python3
"""Kiểm KHÔNG BẢNG NÀO CUỘN NGANG — đo thật bằng Chromium, không đoán bằng mắt.

Cuộn ngang trong một trang vốn đã cuộn dọc là kiểu điều hướng tệ nhất: cột khóa
(tên khách, số hóa đơn) trôi khỏi màn hình đúng lúc người ta đang đọc con số ở
cột cuối, và phải cuộn đi cuộn lại giữa hai đầu để đọc MỘT dòng.

Bộ kiểm này KHÔNG đọc CSS rồi suy luận. Nó:

  1. rút mọi khối `<thead>` thật ra khỏi 74 bảng trong `views/*.js`;
  2. dựng lại từng bảng bằng CHÍNH `shell.css` của app, đổ nội dung dài đúng cỡ
     thật (tên công ty đầy đủ, tiền tỷ 13 ký tự, mã chứng từ);
  3. mở bằng Chromium ở nhiều bề rộng màn hình;
  4. đo `scrollWidth` so với `clientWidth` của từng `.kt-table-wrap`.

Bảng nào `scrollWidth > clientWidth` là bảng đó ĐANG cuộn ngang.

Vì sao phải đo chứ không đọc CSS: bề rộng bảng là kết quả của thuật toán dàn
bảng (min-content của từng ô, `table-layout`, `overflow-wrap`), không phải của
một thuộc tính nào đọc ra được. `overflow-wrap: break-word` và `anywhere` khác
nhau đúng ở chỗ này — chỉ cái sau mới hạ min-content, và chỉ đo mới thấy.

Chạy KHÔNG cần bench, nhưng CẦN playwright + Chromium. Thiếu thì bộ kiểm báo
BỎ QUA (mã thoát 0) chứ không giả vờ đạt — xem `_no_browser`.
"""

import glob
import html as _html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
VIEWS = os.path.join(REPO, "ketoan/public/ketoan/views")
CSS = os.path.join(REPO, "ketoan/public/ketoan/shell.css")

# Bề rộng PHẢI ĐẠT: cỡ màn hình kế toán thật sự ngồi làm việc — laptop 13-15"
# (1280 / 1366) và màn rời (1440+). Ở các cỡ này, KHÔNG bảng nào được cuộn ngang.
WIDTHS_MUST = (1440, 1366, 1280)

# Hẹp hơn: ĐO và báo cáo đích danh, KHÔNG chặn.
#
# Không phải vì dễ dãi, mà vì giới hạn có thật: hai bảng tổng hợp công nợ MT có
# CHÍN cột tiền tỷ. Một số tiền `1.234.567.890` cần ~90px dù font nhỏ tới đâu,
# nên riêng phần số đã ~810px — không lọt 940px còn lại của màn 1024 khi vẫn
# phải chừa chỗ cho tên khách và hai cột đếm.
#
# Ba lối ra, và cả ba đều KHÔNG được tự quyết trong một thay đổi CSS:
#   · cho số tiền xuống dòng      -> rủi ro ĐỌC NHẦM TIỀN, tệ hơn cuộn;
#   · rút gọn thành "1,23 tỷ"     -> đổi độ chính xác hiển thị trên màn kế toán;
#   · bớt cột                     -> bỏ thông tin.
# Nên: giữ lưới an toàn `overflow-x: auto` cho đúng hai bảng đó, và nói ra.
WIDTHS_REPORT = (1024, 768, 414)

# Nội dung dài đúng cỡ thật, để phép đo không dễ dãi.
LONG_NAME = "CÔNG TY TNHH MTV THƯƠNG MẠI VÀ DỊCH VỤ TỔNG HỢP MIỀN TRUNG"
SUB = "CUS-EB-3003172"
MONEY = "1.234.567.890"
COUNT = "1.234"
CODE = "ACC-SINV-2026-04793"
DATE = "31/07/2026"


def _no_browser(msg):
    print("=" * 82)
    print("KIỂM BẢNG KHÔNG CUỘN NGANG")
    print("=" * 82)
    print(f"  ⚠ BỎ QUA — {msg}")
    print("    Cài: pip install playwright  (Chromium đã có sẵn ở /opt/pw-browsers)")
    print("=" * 82)
    print("KẾT QUẢ: BỎ QUA — không có trình duyệt để đo, KHÔNG kết luận gì")
    return 0


def chromium_path():
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                "/opt/pw-browsers/chromium/chrome-linux/chrome"):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[-1]
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Rút bảng thật ra khỏi mã giao diện
# ═══════════════════════════════════════════════════════════════════════════

TH_RE = re.compile(r"<th\b([^>]*)>(.*?)</th>", re.S)
INTERP = re.compile(r"\$\{[^}]*\}", re.S)


def _label(raw):
    """Nhãn cột. Phần `${...}` là giá trị chạy lúc render — thay bằng chữ vừa phải."""
    txt = INTERP.sub("Cột", raw)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = " ".join(txt.split())
    return txt[:28] or "Cột"


def _is_num(attrs):
    return 'class="num"' in attrs or "class='num'" in attrs


def body_kinds(src, start):
    """Ô thứ n của DÒNG THÂN là tiền hay số đếm — đọc từ chính mã render.

    Cột `class="num"` không đồng nghĩa với TIỀN: `Hóa đơn` và `Dòng bảng kê` là
    số ĐẾM, in ra `12` chứ không phải `1.234.567.890`. Tô tiền 13 ký tự vào
    chúng là phép đo tự làm khó mình rồi bắt giao diện gánh — bảng công nợ MT có
    hai cột như thế, đủ để báo tràn 194px không có thật.

    Nên đọc `<td>` tương ứng trong `<tbody>`: gọi `formatVND*` thì là tiền.
    """
    seg = src[start:start + 6000]
    tb = seg.find("<tbody>")
    if tb < 0:
        return []
    seg = seg[tb:]
    end = seg.find("</tbody>")
    if end > 0:
        seg = seg[:end]
    chunks = seg.split("<td")[1:]
    return ["money" if ("formatVND" in c or "formatVNDShort" in c) else "count"
            for c in chunks]


# Tiêu đề dựng thành HẰNG SỐ rồi chèn vào `<thead>${...}</thead>`.
#
# Khuôn này xuất hiện khi hai màn dùng chung một bảng — tách ra để không vẽ hai
# lần rồi lệch nhau. Nhưng bộ đo cũ chỉ dò `<thead>…</thead>` nên nó thấy đúng
# `${einvHead}` và đếm ra 0 cột: BẢNG BIẾN MẤT KHỎI PHÉP ĐO mà không báo gì.
# Đã xảy ra thật với bảng soát HĐĐT (6 cột).
HOISTED = re.compile(r"const\s+(\w+)\s*=\s*html`(.*?)`", re.S)


def _resolve_head(src, inner):
    """`<thead>` chỉ chứa `${tên}` -> tra ra hằng số đó và trả về nội dung thật."""
    m = re.fullmatch(r"\s*\$\{(\w+)\}\s*", inner)
    if not m:
        return inner
    want = m.group(1)
    for name, body in HOISTED.findall(src):
        if name == want:
            return body
    return inner


def extract_tables():
    """[(file, dòng, [(nhãn, kiểu, thuộc_tính)])] cho mọi `<thead>` tìm thấy."""
    out = []
    for path in sorted(glob.glob(os.path.join(VIEWS, "*.js"))):
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r"<thead>(.*?)</thead>", src, re.S):
            kinds = body_kinds(src, m.end())
            cols = []
            for i, (attrs, raw) in enumerate(TH_RE.findall(_resolve_head(src, m.group(1)))):
                lab = _label(raw)
                if not _is_num(attrs):
                    kind = "text"
                elif i < len(kinds):
                    kind = kinds[i]          # đọc từ mã render, không đoán
                else:
                    kind = "money"           # không đọc được -> giả định xấu nhất
                cols.append((lab, kind, attrs))
            if not cols:
                continue
            # Header sinh bằng `.map(...)` chỉ đếm được 1 `<th>` trong mã nhưng
            # render ra nhiều cột. Nhân lên cho sát thực tế (bảng phân quyền có
            # 7 vai trò) — đếm thiếu cột là phép đo tự nới lỏng cho mình.
            if ".map(" in m.group(1) and len(cols) <= 3:
                cols = cols + [(c[0], c[1], c[2]) for c in cols for _ in range(5)]
            out.append((os.path.basename(path),
                        src[:m.start()].count("\n") + 1, cols))
    return out


def build_html(tables, css):
    parts = ["<meta charset='utf-8'><style>", css, "</style>",
             "<div class='kt-app'><div class='kt-main'>"]
    for i, (fname, line, cols) in enumerate(tables):
        ths = "".join(
            f"<th{attrs}>{_html.escape(lab)}</th>" for lab, _k, attrs in cols)
        rows = []
        for r in range(3):
            tds = []
            for j, (lab, kind, attrs) in enumerate(cols):
                cls = ' class="num"' if kind != "text" else ""
                if kind == "money":
                    val = MONEY
                elif kind == "count":
                    val = COUNT
                elif j == 0:
                    val = (f"<b>{_html.escape(LONG_NAME)}</b>"
                           f"<div class='kt-sub'>{SUB}</div>")
                elif j == 1:
                    val = CODE
                else:
                    val = DATE if j % 3 else "Đã phát hành · cần đối chiếu"
                tds.append(f"<td{cls}>{val}</td>")
            rows.append("<tr>" + "".join(tds) + "</tr>")
        parts.append(
            f"<div class='kt-card kt-mb' data-id='{i}' data-src='{fname}:{line}'>"
            f"<div class='kt-card-body'><div class='kt-table-wrap'>"
            f"<table class='kt-table'><thead><tr>{ths}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div></div></div>")
    parts.append("</div></div>")
    return "".join(parts)


MEASURE = """() => {
  const out = [];
  document.querySelectorAll('.kt-card[data-src]').forEach((card) => {
    const w = card.querySelector('.kt-table-wrap');
    const over = w.scrollWidth - w.clientWidth;
    out.push({ src: card.dataset.src,
               cols: w.querySelectorAll('thead th').length,
               over: over });
  });
  return { tables: out,
           page: document.documentElement.scrollWidth - document.documentElement.clientWidth };
}"""


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _no_browser("chưa cài `playwright`")
    exe = chromium_path()
    if not exe:
        return _no_browser("không tìm thấy Chromium ở /opt/pw-browsers")

    tables = extract_tables()
    css = open(CSS, encoding="utf-8").read()
    page_html = build_html(tables, css)

    print("=" * 82)
    print("KIỂM BẢNG KHÔNG CUỘN NGANG — đo bằng Chromium trên chính shell.css")
    print("=" * 82)
    print(f"  {len(tables)} bảng rút từ views/*.js · cột nhiều nhất: "
          f"{max(len(c) for _f, _l, c in tables)}")
    bad = 0
    worst_report = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe)
        page = browser.new_page()
        page.set_content(page_html, wait_until="load")

        for w in WIDTHS_MUST + WIDTHS_REPORT:
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(60)
            res = page.evaluate(MEASURE)
            over = [t for t in res["tables"] if t["over"] > 1]
            must = w in WIDTHS_MUST
            print("-" * 82)
            if not over and res["page"] <= 1:
                print(f"  ✅ {w}px — {len(res['tables'])}/{len(res['tables'])} bảng nằm gọn, "
                      f"trang không cuộn ngang")
            else:
                mark = "❌" if must else "⚠"
                tail = ", trang cuộn ngang %dpx" % res["page"] if res["page"] > 1 else ""
                print(f"  {mark} {w}px — {len(over)} bảng tràn{tail}")
                for t in sorted(over, key=lambda x: -x["over"])[:8]:
                    print(f"       {t['src']:<24} {t['cols']:2d} cột  tràn {t['over']:4d}px")
                if must:
                    bad += len(over) + (1 if res["page"] > 1 else 0)
                else:
                    worst_report.append((w, len(over)))
        browser.close()

    if worst_report:
        print("-" * 82)
        print("  ⚠ Dưới 1280px vẫn còn bảng cuộn ngang — CỐ Ý, xem chú thích WIDTHS_REPORT:")
        for w, n in worst_report:
            print(f"       {w:>4}px: {n} bảng")
        print("    Số tiền giữ nguyên vẹn quan trọng hơn: bẻ đôi `1.234.567.890` giữa hai")
        print("    dòng là rủi ro đọc nhầm tiền, tệ hơn hẳn một thanh cuộn.")

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG — {bad} chỗ cuộn ngang ở cỡ màn hình phải đạt")
        return 1
    print("KẾT QUẢ: ĐẠT — không bảng nào cuộn ngang trên mọi cỡ màn hình làm việc "
          "(1440 · 1366 · 1280), trang cũng không cuộn ngang")
    return 0


if __name__ == "__main__":
    sys.exit(main())
