"""Kiểm ĐỘT BIẾN tầng đọc file MT — chứng minh số kiểm tra thật sự CÓ TÁC DỤNG.

    python3 docs/mt/verified/mutation_check.py

`regression_check.py` chứng minh parser hiện tại ra đúng số. Nó KHÔNG chứng minh
được điều quan trọng hơn: nếu mai kia parser bị sửa hỏng thì có ai phát hiện
không. Bộ này cố ý gài từng lỗi TIỀN thật vào mã nguồn (bỏ dòng, cộng trùng, đảo
dấu, đọc lấn khối tổng) rồi đòi hỏi `reconciled` phải xuống False.

Đột biến nào LỌT LƯỚI nghĩa là đang có một đường hỏng câm — tiền lệch mà màn
hình vẫn ghi "đã đối chiếu khớp". Ba lỗ đã tìm ra bằng chính bộ này:

  · parse_fuji bỏ sót CẢ khối hàng trả  -> `net_base` tụt về đúng `gross`, mà
    `gross` lại là một doanh số căn cứ in trong file, nên phép kiểm khớp GIẢ.
    Vá bằng chốt "Số dòng hàng trả đọc được" (đếm theo cột STT, độc lập cột tiền).
  · Dòng tiền thêm SAU khi đã dựng số kiểm tra thì không check nào thấy.
    Vá bằng `_assert_rows_frozen`.
  · (dự phòng) mọi đột biến dưới đây được giữ lại làm mốc hồi quy.

Chạy KHÔNG cần bench — dùng chung bộ stub frappe của `regression_check`.
"""

import base64
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression_check as rc  # noqa: E402

SAMPLES = rc.SAMPLES
SRC_PATH = os.path.join(rc.REPO, "ketoan", "api", "mt_advice.py")

AEON = "chi tiet thanh to\xa0n AEON.xls"     # \xa0 THẬT trong tên file
FUJI = "CHI TIẾT THANH TOÁN FUJI.Xls"

# (nhãn, file, chuỗi, đoạn mã bị thay, đoạn thay thế)
#
# Mỗi đột biến phải là một lỗi TIỀN có thật, không phải lỗi cú pháp: mục tiêu là
# đo sức mạnh của số kiểm tra, không phải đo xem Python có chạy được không.
MUTATIONS = [
    ("AEON bỏ 1 dòng hàng bán", AEON, "aeon",
     '        if slip not in _AE_SLIP_KIND:\n            continue',
     '        if slip not in _AE_SLIP_KIND or r == hr + 1:\n            continue'),

    ("AEON cộng trùng DcCharges vào khoản trừ", AEON, "aeon",
     '    goods = _sum(rows, "signed_amount", {"thanh_toan"})\n'
     '    returns = _sum(rows, "signed_amount", {"ghi_giam"})\n'
     '    fees = _sum(rows, "signed_amount", {"phi"})',
     '    _dcn, _dcg = _ae_sheet(sheets, "DcCharges")\n'
     '    for _r in range(14, len(_dcg or []) + 1):\n'
     '        _v = to_number(_g(_dcg, _r, 6))\n'
     '        if _v is not None:\n'
     '            rows.append(_line(row_kind="phi", signed_amount=-_v,\n'
     '                              source_sheet="dc", source_row=_r))\n'
     '    goods = _sum(rows, "signed_amount", {"thanh_toan"})\n'
     '    returns = _sum(rows, "signed_amount", {"ghi_giam"})\n'
     '    fees = _sum(rows, "signed_amount", {"phi"})'),

    ("AEON đảo dấu dòng khoản trừ âm (-abs thay vì -amt)", AEON, "aeon",
     '                    signed_amount=-amt, payment_date=pay_date,',
     '                    signed_amount=-abs(amt), payment_date=pay_date,'),

    ("AEON đọc lấn vào khối tổng (cộng đôi)", AEON, "aeon",
     '    end = sr or (len(doc) + 1)',
     '    end = len(doc) + 1'),

    ("AEON lấy 'số cuối dòng' làm số kiểm tra (ra số slip)", AEON, "aeon",
     '            amt = to_number(_gv(doc, r, s_amt)) if s_amt else None',
     '            amt = next((to_number(c) for c in reversed(doc[r - 1])\n'
     '                        if to_number(c) is not None), None)'),

    ("Fuji nhân đôi doanh thu (sinh tiền từ cả khối 1)", FUJI, "fuji",
     '                b1[inv] = {',
     '                rows.append(_line(row_kind="thanh_toan", inv_no=inv,\n'
     '                                  signed_amount=amt, source_sheet="b1", source_row=r))\n'
     '                b1[inv] = {'),

    ("Fuji bỏ sót cả khối hàng trả", FUJI, "fuji",
     '        c_amt3 = _ae_col(c3cols, _FJ_H_B3)',
     '        c_amt3 = None'),

    ("Fuji đọc sai cột doanh số căn cứ", FUJI, "fuji",
     '                    cur["base"] = to_number(_gv(grid, r, c_base)) if c_base else None',
     '                    cur["base"] = to_number(_gv(grid, r, c_base)) * 2 if c_base else None'),

    ("Fuji cộng trùng dòng tên + dòng chi tiết chiết khấu", FUJI, "fuji",
     '                    items.append(cur)\n                    cur = None',
     '                    items.append(cur)\n                    items.append(dict(cur))\n'
     '                    cur = None'),

    ("Fuji đọc nhầm ngày nhập kho thành ngày hóa đơn", FUJI, "fuji",
     '        c_idate = _fj_sub(grid, r1, g_hdtc or 1, g_pnk, "NGÀY/THÁNG")',
     '        c_idate = _fj_sub(grid, r1, g_pnk or 1, c_amt1, "NGÀY/THÁNG")'),
]

# Đột biến trên CHỈ đổi ngày, không đổi đồng nào — số kiểm tra tiền không thể
# bắt được, và đó là đúng bản chất. Ghi rõ ra đây để không ai tưởng là lỗ hổng.
KNOWN_UNCAUGHT = {"Fuji đọc nhầm ngày nhập kho thành ngày hóa đơn"}


def _load(src):
    m = types.ModuleType("mt_advice_mut")
    m.__file__ = "mt_advice_mut.py"
    exec(compile(src, "mt_advice_mut.py", "exec"), m.__dict__)
    return m


def main():
    rc._stub_frappe()
    sys.path.insert(0, rc.REPO)
    src0 = open(SRC_PATH, encoding="utf-8").read()

    print("=" * 78)
    print("KIỂM ĐỘT BIẾN — số kiểm tra có bắt được lỗi tiền không?")
    print("=" * 78)

    bad = 0
    # Đối chứng: mã gốc phải KHỚP, nếu không thì mọi kết luận bên dưới vô nghĩa.
    base_mod = _load(src0)
    for fname, chain in ((AEON, "aeon"), (FUJI, "fuji")):
        raw = open(os.path.join(SAMPLES, fname), "rb").read()
        res = base_mod.read_payment_advice(base64.b64encode(raw).decode(), chain)
        ok = bool(res.get("reconciled"))
        print(f"  {'✅' if ok else '❌'} ĐỐI CHỨNG {chain:6} mã gốc reconciled={ok}")
        bad += not ok

    print("-" * 78)
    for label, fname, chain, old, new in MUTATIONS:
        if src0.count(old) != 1:
            print(f"  ❌ {label[:56]:58} -> đoạn mã cần đột biến không còn "
                  f"(thấy {src0.count(old)} lần) — CẬP NHẬT BỘ KIỂM")
            bad += 1
            continue
        raw = open(os.path.join(SAMPLES, fname), "rb").read()
        try:
            mod = _load(src0.replace(old, new, 1))
            res = mod.read_payment_advice(base64.b64encode(raw).decode(), chain)
        except Exception as e:  # noqa: BLE001 — throw cũng là "bị bắt"
            print(f"  ✅ {label[:56]:58} -> THROW {type(e).__name__}")
            continue
        caught = not res.get("reconciled")
        expect_uncaught = label in KNOWN_UNCAUGHT
        if caught:
            n = sum(1 for c in res["checks"] if not c["ok"])
            mark = "✅" if not expect_uncaught else "⚠"
            print(f"  {mark} {label[:56]:58} -> BỊ BẮT ({n} số kiểm tra lệch)")
            if expect_uncaught:
                print("       └─ đã ghi là KHÔNG bắt được — cập nhật KNOWN_UNCAUGHT")
        elif expect_uncaught:
            print(f"  ➖ {label[:56]:58} -> lọt lưới ĐÃ BIẾT (không đổi đồng nào)")
        else:
            print(f"  ❌ {label[:56]:58} -> LỌT LƯỚI — tiền lệch mà vẫn reconciled=True")
            bad += 1

    print("=" * 78)
    print("KẾT QUẢ:", "ĐẠT — mọi lỗi tiền cố ý đều bị chặn" if not bad
          else f"HỎNG {bad} mục")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
