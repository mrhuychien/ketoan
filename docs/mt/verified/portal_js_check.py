#!/usr/bin/env python3
"""Kiểm MỌI file JS của portal NẠP ĐƯỢC — parse đúng kiểu trình duyệt nạp.

════════════════════════════════════════════════════════════════════════════
VÌ SAO CÓ BỘ KIỂM NÀY
════════════════════════════════════════════════════════════════════════════

Một lỗi cú pháp đã lọt ra tới người dùng: template literal thiếu dấu backtick
đóng trong `views/mt.js`. Kế toán mở portal và nhận đúng một dòng:

    Lỗi tải màn hình: Unexpected identifier '$'

Cả màn hình trắng. Không phải một nút hỏng — CẢ portal không nạp được, vì một
module ES gãy cú pháp thì không có gì trong nó chạy.

Và nó lọt qua được bước kiểm vì bước kiểm SAI:

    node --check views/mt.js        ->  ĐẠT      (sai)
    cp views/mt.js x.mjs; node --check x.mjs  ->  BÁO LỖI đúng dòng

`node --check` trên đuôi `.js` coi file là CommonJS. Trình duyệt nạp portal bằng
`<script type="module">`, tức là ES module. Hai bộ phân tích cú pháp khác nhau,
và cái khác biệt đó đủ để nuốt một template literal không đóng.

Nên bộ kiểm này ép đuôi `.mjs` — kiểm ĐÚNG cách file sẽ được nạp.

════════════════════════════════════════════════════════════════════════════
KIỂM CẢ ĐƯỜNG NHẬP MODULE
════════════════════════════════════════════════════════════════════════════

Cú pháp đúng mà `import` trỏ vào file không tồn tại thì portal cũng trắng y hệt,
và lỗi hiện ra còn khó lần hơn (404 trong tab Network chứ không phải Console).
Kiểm luôn ở đây vì cùng một hậu quả: màn hình không nạp được.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PORTAL = os.path.join(REPO, "ketoan/public/ketoan")

IMPORT_RE = re.compile(r"""^\s*(?:import|export)\b[^'"]*from\s+['"]([^'"]+)['"]""", re.M)


def main():
    print("=" * 82)
    print("KIỂM PORTAL JS NẠP ĐƯỢC")
    print("=" * 82)

    node = shutil.which("node")
    if not node:
        print("  ⚠ BỎ QUA — máy không có `node` để phân tích cú pháp")
        print("=" * 82)
        print("KẾT QUẢ: BỎ QUA — không kiểm được, KHÔNG kết luận gì")
        return 0

    files = sorted(glob.glob(os.path.join(PORTAL, "**", "*.js"), recursive=True))
    if not files:
        print("  ❌ không tìm thấy file JS nào của portal")
        return 1

    bad = 0
    print(f"  {len(files)} file JS dưới ketoan/public/ketoan")

    # ── 1. Cú pháp, parse ĐÚNG kiểu ES module ───────────────────────────
    print("-" * 82)
    broken = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            mjs = os.path.join(tmp, "m.mjs")
            shutil.copyfile(f, mjs)
            r = subprocess.run([node, "--check", mjs], capture_output=True, text=True)
            if r.returncode != 0:
                err = (r.stderr or "").strip().splitlines()
                # Dòng đầu của node là đường dẫn tạm — vô nghĩa với người đọc.
                msg = next((l for l in err if "Error" in l or "^" not in l), err[0] if err else "")
                broken.append((os.path.relpath(f, REPO), msg.strip()[:90]))
    ok = not broken
    print(f"  {'✅' if ok else '❌'} mọi file parse được như ES module "
          f"(`.mjs`, KHÔNG phải `node --check *.js` — xem chú thích đầu file)")
    for path, msg in broken[:10]:
        print(f"       {path}: {msg}")
    bad += len(broken)

    # ── 2. Mọi `import` trỏ tới file có thật ────────────────────────────
    print("-" * 82)
    missing = []
    for f in files:
        src = open(f, encoding="utf-8").read()
        for spec in IMPORT_RE.findall(src):
            if not spec.startswith("."):
                continue                      # gói ngoài, không phải file của mình
            target = os.path.normpath(os.path.join(os.path.dirname(f), spec))
            if not os.path.exists(target):
                missing.append((os.path.relpath(f, REPO), spec))
    ok = not missing
    print(f"  {'✅' if ok else '❌'} mọi `import` tương đối trỏ tới file có thật "
          f"— import gãy cũng làm trắng màn hình, mà lỗi chỉ hiện ở tab Network")
    for path, spec in missing[:10]:
        print(f"       {path}: import '{spec}' không tồn tại")
    bad += len(missing)

    # ── 3. Điểm vào + IMPORT MAP của trang ──────────────────────────────
    #
    # `www/ketoan.html` khai một import map liệt kê đích danh từng module. Đổi
    # tên hay dời một file mà quên sửa map thì trình duyệt nạp 404 và portal
    # trắng y hệt lỗi cú pháp — nhưng lỗi chỉ hiện ở tab Network, không ở Console.
    print("-" * 82)
    entry = os.path.join(PORTAL, "shell.js")
    ok = os.path.exists(entry)
    print(f"  {'✅' if ok else '❌'} còn điểm vào `shell.js` (thứ `ketoan.html` nạp bằng "
          f"`<script type=\"module\">`)")
    bad += not ok

    html_path = os.path.join(REPO, "ketoan/www/ketoan.html")
    if os.path.exists(html_path):
        html = open(html_path, encoding="utf-8").read()
        # Đường trong map dạng "{{ base }}/lib/api.js" -> lấy phần sau `base`.
        mapped = sorted(set(re.findall(r'\{\{\s*base\s*\}\}/([\w./-]+\.js)', html)))
        gone = [m for m in mapped if not os.path.exists(os.path.join(PORTAL, m))]
        ok = bool(mapped) and not gone
        print(f"  {'✅' if ok else '❌'} {len(mapped)} module khai trong import map của "
              f"`ketoan.html` đều có thật {'' if ok else '— thiếu: ' + ', '.join(gone)}")
        bad += not ok
    else:
        print("  ⚠ không thấy ketoan/www/ketoan.html — bỏ qua phép kiểm import map")

    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: HỎNG {bad} chỗ — portal sẽ KHÔNG nạp được")
        return 1
    print("KẾT QUẢ: ĐẠT — mọi module của portal parse được đúng cách trình duyệt nạp, "
          "và không đường nhập nào gãy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
