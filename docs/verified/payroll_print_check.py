#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""payroll_print_check — "In bảng lương" phải ra ĐÚNG BỐN TRANG, ĐÚNG THỨ TỰ.

════════════════════════════════════════════════════════════════════════════
TỜ NÀY ĐỂ GIÁM ĐỐC KÝ
════════════════════════════════════════════════════════════════════════════

Thứ tự trang là một yêu cầu nghiệp vụ, không phải chuyện thẩm mỹ: người ký mở
ra phải thấy con số tổng trước, rồi mới tới từng bộ phận.

    trang 1  TỔNG HỢP LƯƠNG
    trang 2  BẢNG LƯƠNG BỘ PHẬN CÔNG NHẬT
    trang 3  BẢNG LƯƠNG BỘ PHẬN CÔNG KHOÁN
    trang 4  BẢNG LƯƠNG BAN LÃNH ĐẠO

Ba chốt chặn phép kiểm này canh — mỗi cái là một cách tờ trình nói dối:

  1. **Hai ô "Tổng" của trang 1 phải bằng nhau.** Chia theo BỘ PHẬN và chia
     theo HÌNH THỨC CHI là hai lát cắt của cùng một khoản tiền. Lệch mà im
     lặng thì người ký không có cách nào biết bên nào đúng.
  2. **Tổng trang 4 phải bằng ô "Lương Ban lãnh đạo" của trang 1.** Hai trang
     của CÙNG một tờ trình nói hai con số là hỏng cả tờ.
  3. **Số trên giấy phải là số của `computeAgg`**, không phải một phép cộng
     chép lại. Bản Excel "tonghop" đọc cùng hàm đó; hai đường tính riêng sẽ
     lệch ngay kỳ đầu có người vào/ra.

⚠ Ban lãnh đạo: app CHỈ có dữ liệu gộp — `BLD_NGANHANG` (từng khoản chuyển
khoản) và `BLD_BUTRU` (phần tiền mặt của 4 người). Hai danh sách khớp ở TỔNG
(133.900.000 + 32.100.000 = 166.000.000) nhưng KHÔNG khớp theo từng người
(NGUYEN THI NGA: chuyển khoản 15.500.000, trong khi dòng bù trừ ghi lương
chuyển khoản 31.000.000). Vì vậy trang 4 CỐ Ý không dựng bảng "thực nhận từng
người": bảng đó sẽ cộng ra đúng 166 triệu mà sai với từng cá nhân.

Chạy KHÔNG cần bench (nạp thẳng payroll.js bằng node, thay import bằng bộ giả):
    python3 docs/verified/payroll_print_check.py   # exit 0 = đạt
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
JS = os.path.join(REPO, "ketoan/public/ketoan/views/payroll.js")

ok_all = True


def check(label, cond, detail=""):
    global ok_all
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  ({detail})" if detail else ""))
    if not cond:
        ok_all = False
    return cond


NHAT = [
    {"employee_name": "Nguyễn Văn A", "luongcoban": 5000000, "congngay": 26, "lamthem": 4,
     "luongngaycong": 5000000, "luonglamthem": 400000, "anca": 600000, "chuyencan": 300000,
     "hotrongaycong": 200000, "hotro": 150000, "baohiem": 500000,
     "luongthucnhan": 6150000, "luongck": 5000000},
    {"employee_name": "Trần Thị B", "luongcoban": 4800000, "congngay": 25, "lamthem": 0,
     "luongngaycong": 4600000, "luonglamthem": 0, "anca": 575000, "chuyencan": 300000,
     "hotrongaycong": 0, "hotro": 100000, "baohiem": 0,
     "luongthucnhan": 5575000, "luongck": 0},
]
KHOAN = [
    {"employee_name": "Lê Văn C", "luongsanpham": 8000000, "anca": 600000, "hotro": 200000,
     "hotrongaycong": 0, "chuyencan": 300000, "baohiem": 600000,
     "luongthucnhan": 8500000, "luongck": 0},
    {"employee_name": "Phạm Thị D", "luongsanpham": 7000000, "anca": 600000, "hotro": 0,
     "hotrongaycong": 0, "chuyencan": 0, "baohiem": 0,
     "luongthucnhan": 7600000, "luongck": 0},
]


def run_js(src_override=None, extra_js=None):
    """Nạp payroll.js trong node (bỏ import/export, cắm bộ giả DOM) rồi in JSON."""
    src = src_override if src_override is not None else open(JS, encoding="utf-8").read()
    src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
    src = re.sub(r"^export ", "", src, flags=re.M)
    harness = (
        "const api={call:async()=>({})};\n"
        "const document={getElementById:()=>null,"
        "createElement:()=>({style:{},addEventListener(){}}),"
        "head:{appendChild(){}},body:{appendChild(){}},querySelectorAll:()=>[]};\n"
        "const window={};\n"
        + src
        + "\nconst NHAT=" + json.dumps(NHAT, ensure_ascii=False)
        + ";\nconst KHOAN=" + json.dumps(KHOAN, ensure_ascii=False) + ";\n"
        "const bl = PB.buildPrintHTML('bangluong', NHAT, KHOAN, 9, 2026);\n"
        "const pl = PB.buildPrintHTML('phatluong', NHAT, KHOAN, 9, 2026);\n"
        "function titles(h){return h.split('<section>').slice(1)"
        ".map(s=>(s.match(/<div class=\"ti\">([^<]*)<\\/div>/)||[,''])[1]);}\n"
        "const extra = (" + (extra_js or "() => ({})") + ")(PB);\n"
        "console.log(JSON.stringify({bl, pl, blTitles:titles(bl), plTitles:titles(pl),"
        " agg: PB.computeAgg(NHAT, KHOAN), extra}));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as f:
        f.write(harness)
        tmp = f.name
    try:
        r = subprocess.run(["node", tmp], capture_output=True, text=True)
    finally:
        os.unlink(tmp)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip().splitlines()[-1] if r.stderr else "node lỗi")
    return json.loads(r.stdout)


def money_in(section, label):
    """Số tiền ở dòng có nhãn `label` (ô cuối của dòng đó)."""
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", section, re.S):
        if label in re.sub(r"<[^>]+>", "", row):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if cells:
                raw = re.sub(r"<[^>]+>", "", cells[-1]).strip()
                neg = raw.startswith("(")
                n = re.sub(r"[^\d]", "", raw)
                return -int(n) if (neg and n) else (int(n) if n else 0)
    return None


def main():
    print("=" * 78)
    print("payroll_print_check — In bảng lương: 4 trang, đúng thứ tự, số khớp")
    print("=" * 78)

    try:
        d = run_js()
    except Exception as e:  # noqa: BLE001
        check("nạp và chạy được payroll.js trong node", False, str(e)[:90])
        print("=" * 78)
        print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
        return 1

    # ── 1. Bốn trang, đúng thứ tự ──────────────────────────────────────
    print("-" * 78)
    print("── 1. Thứ tự trang — người ký thấy TỔNG trước, rồi mới tới bộ phận ──")
    t = d["blTitles"]
    check("ra ĐÚNG 4 trang", len(t) == 4, f"{len(t)} trang")
    want = ["TỔNG HỢP LƯƠNG", "BẢNG LƯƠNG BỘ PHẬN CÔNG NHẬT",
            "BẢNG LƯƠNG BỘ PHẬN CÔNG KHOÁN", "BẢNG LƯƠNG BAN LÃNH ĐẠO"]
    for i, w in enumerate(want):
        got = t[i] if i < len(t) else "(không có)"
        check(f"trang {i + 1} là “{w}”", got.startswith(w), got)
    check("mỗi trang đều mang tháng/năm của kỳ",
          all("THÁNG 09/2026" in x for x in t), " · ".join(t)[:70])
    check("mỗi trang đều có tên công ty",
          d["bl"].count("CÔNG TY CỔ PHẦN HOÀNG GIANG") == 4)

    # ── 2. Số trên giấy = số của computeAgg ────────────────────────────
    print("-" * 78)
    print("── 2. Trang 1 in ĐÚNG số của `computeAgg`, không phải phép cộng khác ")
    secs = d["bl"].split("<section>")[1:]
    p1 = secs[0]
    a = d["agg"]
    pairs = [("Bộ phận Công nhật", "tong_nhat"), ("Bộ phận Sản Xuất", "tong_khoan"),
             ("Lương Ban lãnh đạo", "tong_bld"), ("Lương chuyển khoản", "tong_ck"),
             ("Tiền mặt công nhật", "tm_nhat"), ("Tiền mặt công khoán", "tm_khoan"),
             ("Tiền mặt bù trừ", "tm_butru")]
    for label, key in pairs:
        got, want_v = money_in(p1, label), round(a[key])
        check(f"“{label}” = {want_v:,}", got == want_v, f"in ra {got}")

    # ── 3. Hai ô "Tổng" của trang 1 phải bằng nhau ─────────────────────
    print("-" * 78)
    print("── 3. Hai lát cắt của CÙNG một khoản tiền phải ra cùng một số ──────")
    tots = [int(re.sub(r"[^\d]", "", x)) for x in
            re.findall(r'<tr class="tot">.*?<td class="n b">([^<]*)</td>', p1, re.S)]
    check("trang 1 có đúng 2 dòng Tổng", len(tots) == 2, str(tots))
    if len(tots) == 2:
        check("tổng theo BỘ PHẬN = tổng theo HÌNH THỨC CHI",
              tots[0] == tots[1], f"{tots[0]:,} vs {tots[1]:,}")
        check("và bằng tổng cộng từ `computeAgg`",
              tots[0] == round(a["tong_nhat"] + a["tong_khoan"] + a["tong_bld"]),
              f"{tots[0]:,}")
    check("KHÔNG có cảnh báo lệch trên trang 1 (số liệu mẫu phải khớp)",
          "class=\"warn\"" not in p1)
    check("trang 1 có khối ký duyệt (ngày ký tháng SAU kỳ lương)",
          "Giám đốc duyệt" in p1 and "tháng 10 năm 2026" in p1)

    # ── 4. Trang 4 phải khớp ô Ban lãnh đạo của trang 1 ────────────────
    print("-" * 78)
    print("── 4. Trang 4 nói CÙNG con số với ô “Lương Ban lãnh đạo” ở trang 1 ──")
    p4 = secs[3]
    bld_p1 = money_in(p1, "Lương Ban lãnh đạo")
    # Dòng tổng của trang 4 là một <div>, không phải <tr> — `money_in` chỉ quét
    # hàng bảng nên phải bóc riêng, đừng để nó trả None rồi so None == số.
    m4 = re.search(r"Tổng lương Ban lãnh đạo:\s*<b>([^<]*)</b>", p4)
    bld_p4 = int(re.sub(r"[^\d]", "", m4.group(1))) if m4 else None
    check("tổng trang 4 = ô Ban lãnh đạo trang 1", bld_p4 == bld_p1,
          f"trang 4 {bld_p4} vs trang 1 {bld_p1}")
    check("trang 4 tách rõ HAI phần: chuyển khoản và bù trừ",
          "1. Phần chuyển khoản" in p4 and "2. Phần bù trừ" in p4)
    check("và nói ra phép cộng, không bắt người đọc tự dò",
          "chuyển khoản" in p4 and "bù trừ" in p4 and "133,900,000" in p4)
    # Không dựng bảng "thực nhận từng người" — hai danh sách nguồn không khớp
    # theo người, bảng đó sẽ cộng đúng mà sai từng cá nhân.
    check("KHÔNG có cột “Tổng thu nhập” từng người ở trang 4 (dữ liệu không có)",
          "Tổng thu nhập" not in p4)
    check("KHÔNG có cảnh báo lệch trên trang 4", "class=\"warn\"" not in p4)

    # ── 4b. CHUÔNG CÓ KÊU KHÔNG — ép số liệu lệch rồi xem ─────────────
    #
    # Mục 3 và 4 mới chỉ khẳng định "không có cảnh báo" trên số liệu ĐẸP — câu
    # đó vẫn đúng y nguyên kể cả khi hai chốt cảnh báo đã bị gỡ sạch. Muốn biết
    # chốt còn sống thì phải ép nó kêu.
    print("-" * 78)
    print("── 4b. Ép lệch số — hai chốt cảnh báo phải KÊU, không im ───────────")
    try:
        # Trang 1: `agg` mà hai lát cắt KHÔNG cộng ra cùng một số.
        bad = run_js(extra_js="""(PB) => {
          const good = {tong_nhat:1000, tong_khoan:2000, tong_bld:3000,
                        tong_ck:4000, tm_nhat:1000, tm_khoan:500, tm_butru:500};
          const skew = Object.assign({}, good, {tm_butru: 500 + 777});
          return { good: PB.htmlTonghop(good, 9, 2026), skew: PB.htmlTonghop(skew, 9, 2026) };
        }""")["extra"]
        check("số liệu CÂN -> không kêu oan", 'class="warn"' not in bad["good"])
        check("số liệu LỆCH -> trang 1 kêu ngay trên giấy", 'class="warn"' in bad["skew"])
        check("và nói ra lệch bao nhiêu, không chỉ 'có lệch'", "777" in bad["skew"])
    except Exception as e:  # noqa: BLE001
        check("gọi được `htmlTonghop` với số liệu lệch", False, str(e)[:80])

    try:
        # Trang 4: đổi hằng số tổng Ban lãnh đạo -> hai trang nói hai con số.
        src2 = open(JS, encoding="utf-8").read().replace(
            "var BANLANHDAO_TONG = 166000000;", "var BANLANHDAO_TONG = 170000000;", 1)
        # `split` để lại phần tử rỗng ở đầu -> trang 4 là index 4, không phải 3.
        p4b = run_js(src_override=src2)["bl"].split("<section>")[1:][3]
        check("hằng số tổng Ban lãnh đạo lệch -> trang 4 kêu",
              'class="warn"' in p4b)
        check("và chỉ đích danh số của trang Tổng hợp để đối chiếu",
              "170,000,000" in p4b)
    except Exception as e:  # noqa: BLE001
        check("chạy được bản đổi hằng số Ban lãnh đạo", False, str(e)[:80])

    # ── 5. Hồi quy: “In phát lương” không bị đụng ──────────────────────
    print("-" * 78)
    print("── 5. Hồi quy — nhánh “In phát lương” giữ nguyên 3 trang cũ ────────")
    pt = d["plTitles"]
    check("“In phát lương” vẫn ra 3 trang", len(pt) == 3, f"{len(pt)} trang")
    check("và vẫn là tiền mặt công nhật → tiền mặt công khoán → bù trừ",
          len(pt) == 3
          and pt[0].startswith("BẢNG THANH TOÁN TIỀN MẶT (CÔNG NHẬT)")
          and pt[1].startswith("BẢNG THANH TOÁN TIỀN MẶT (CÔNG KHOÁN)")
          and pt[2].startswith("BẢNG BÙ TRỪ LƯƠNG"), " · ".join(pt)[:70])
    check("“In phát lương” KHÔNG kèm trang tổng hợp hay ban lãnh đạo",
          not any("TỔNG HỢP" in x or "BAN LÃNH ĐẠO" in x for x in pt))

    # ── 6. CSS: bảng hẹp không bị kéo hết khổ ngang ────────────────────
    print("-" * 78)
    print("── 6. Bảng hẹp phải có bề rộng riêng, không kéo hết khổ A4 ngang ───")
    src = open(JS, encoding="utf-8").read()
    css = re.search(r"var PRINT_CSS = '(.*?)';", src, re.S)
    css = css.group(1) if css else ""
    check("`table.narrow` có bề rộng riêng", "table.narrow{width:" in css)
    check("`table.mid` có bề rộng riêng", "table.mid{width:" in css)
    check("mỗi <section> vẫn là một trang in", "section + section{page-break-before:always;}" in css)
    check("trang 1 dùng bảng hẹp", 'class="narrow"' in p1)

    print("=" * 78)
    if ok_all:
        print("KẾT QUẢ: ĐẠT — 4 trang đúng thứ tự, số trên giấy khớp `computeAgg`, "
              "và hai trang không nói hai con số.")
        return 0
    print("KẾT QUẢ: CÓ MỤC KHÔNG ĐẠT ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
