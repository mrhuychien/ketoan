"""Parser ĐÃ CHẠY THẬT trên file mẫu của chuỗi central_retail — bản tham chiếu.

verified = True
sheet = 'Sheet1 (workbook chỉ có 1 sheet, visible, không có dòng/cột ẩn, không merged cell, không autofilter, không công thức)'
header_row = 1

columns:
  inv_series -> 'Reference (phần trước dấu |)'
  inv_no -> 'Reference (phần sau dấu |)'
  inv_date -> 'Doc. Date'
  store_name -> "Assignment (CHỈ đúng với dòng Doc.Type=K1; với D1/KS cột này chứa mã tài khoản kiểu '3003172.9999.' chứ không phải siêu thị)"
  store_code -> 'KHÔNG CÓ trong file — không được đoán'
  doc_no -> 'Clearing Doc. (số chứng từ bù trừ của Central Retail, 1000031683 / 1000032558)'
  amount_before_vat -> 'KHÔNG CÓ — file chỉ có một cột tiền duy nhất'
  vat_amount -> 'KHÔNG CÓ — cấm tự suy ra 10%'
  total_amount -> 'Amount'
  payment_date -> "Clearing Date (KHÔNG phải 'Pmnt Date')"
  description -> 'Text'
  row_type_col -> 'Doc.Type'
  account -> 'Account (3003172 / 3006634 — hai tài khoản nhà cung cấp trong cùng 1 file)'
  terms_of_pmnt -> "Terms of Pmnt (A040/A030 = điều khoản theo tài khoản; '#' = dòng phí/chiết khấu; 'Result' = dòng tổng)"
  entry_date -> 'Entry Date (chưa dùng)'
  due_date -> 'Pmnt Date (ngày ĐẾN HẠN từng hóa đơn — không phải ngày trả)'

invoice_parse: Reference = '<KÝ HIỆU>|<SỐ>', tách bằng partition('|'). Ký hiệu chuẩn hóa bằng cách BỎ CHỮ SỐ DẠNG HÓA ĐƠN Ở ĐẦU: re.sub(r'^\d+','',series). Ví dụ thật trong chính file này: 'C26THG|4675' -> (C26THG, 4675); '1C26THG|4674' -> (1C26THG, 4674) chuẩn hóa còn C26THG — CÙNG một dải hóa đơn (xác nhận §E hợp đồng, 4 dòng K1 mang tiền tố '1': r44 DONG NAI|4674, r47 DONG NAI|4517, r136 DONG NAI|4981, r178 DA NANG|5144 — tiền tố '1' KHÔNG tương quan với siêu thị nào, hoàn toàn ngẫu nhiên). Ký hiệu của BÊN CHUỖI, không phải hóa đơn của mình: 'K26TEB|74986' (hóa đơn phí Central Retail phát hành), 'K26TRT|21246' (phiếu trả hàng). Có 1 dòng Reference KHÔNG có dấu '|': 'CK T07.2026' (r97, Doc.Type=KS) -> inv_series=None, inv_no=None. Không có Reference nào trùng lặp trong file (0 duplicate).
date_parse: Mọi ô ngày (Doc. Date, Entry Date, Pmnt Date, Clearing Date) đều đã là datetime.datetime thật trong openpyxl -> chỉ cần .date().isoformat(). Không gặp serial number, không gặp text ngày. Parser vẫn có fallback strptime cho '%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y%m%d'.
amount_parse: Cột 'Amount' đã là số float trong openpyxl, mọi giá trị đều là SỐ NGUYÊN VND (kiểm tra: không có giá trị nào lẻ phần thập phân). Không có dấu phẩy ngăn cách, không có dạng ngoặc đơn âm, không có công thức trong file. Parser vẫn giữ nhánh xử lý chuỗi (bỏ ',', bỏ khoảng trắng, '(1.234)' -> âm) để phòng file kỳ sau xuất khác. Dấu gốc được giữ nguyên ở khóa raw_amount để đối chiếu dòng tổng; total_amount là trị tuyệt đối để so với grand_total của Sales Invoice.
payment_dates: ['2026-08-05']

row_types:
  {"kind": "thanh_toan", "label": "Hàng hóa (hóa đơn bán ra)", "rule": "Doc.Type = 'K1' VÀ ký hiệu trong Reference KHÔNG bắt đầu bằng 'K26TRT'", "sign": "ÂM trong file", "count": 184}
  {"kind": "ghi_giam", "label": "Trả hàng (TRA HANG)", "rule": "Doc.Type = 'K1' NHƯNG Reference có ký hiệu 'K26TRT' (vd K26TRT|21246), Text = 'TRA HANG - 110'", "sign": "DƯƠNG trong file — K1 mà dương, phá vỡ giả định 'K1 luôn âm'", "count": 2}
  {"kind": "phi", "label": "Phí dịch vụ / phí dịch vụ EBS / phí hỗ trợ", "rule": "Doc.Type = 'D1', Reference ký hiệu 'K26TEB' (chứng từ do Central Retail phát hành, KHÔNG phải hóa đơn của mình)", "sign": "DƯƠNG", "count": 6}
  {"kind": "chiet_khau", "label": "Chiết khấu (EBS chiet khau / CK tháng)", "rule": "Doc.Type = 'KS'", "sign": "DƯƠNG", "count": 2}
  {"kind": "bo_qua", "label": "Dòng tổng theo Clearing Doc.", "rule": "Terms of Pmnt = 'Result' (Doc.Type rỗng). Có 2 dòng — MỘT DÒNG CHO MỖI Clearing Doc., không phải chỉ 1 dòng r3 như hồ sơ cũ ghi", "sign": "ÂM", "count": 2}
  {"kind": "bo_qua", "label": "Dòng tổng toàn file", "rule": "Account = 'Overall Result' (mọi cột khác rỗng, chỉ có Amount)", "sign": "ÂM", "count": 1}

totals:
  tong_so_dong_file = 198
  dong_header = 1
  dong_du_lieu = 197
  kiem_tra_cong_so_dong = 184 + 2 + 6 + 2 + 2 + 1 = 197 ✓ (khớp tuyệt đối, không sót dòng nào)
  thanh_toan_hang_hoa_raw = -721996632
  tra_hang_raw = 5119605
  phi_raw = 134708790
  chiet_khau_raw = 27240347
  tong_chi_tiet_194_dong_raw = -554927890
  so_kiem_tra_trong_file_Overall_Result = -554927890
  so_kiem_tra_Result_1000031683 = -460442354
  so_kiem_tra_Result_1000032558 = -94485536
  tong_2_dong_Result = -554927890
  chenh_lech_chi_tiet_vs_Overall_Result = 0
  chenh_lech_theo_tung_clearing_doc = 1000031683: 0 ; 1000032558: 0
  khop = True
  so_tien_thuc_nhan_dien_giai = 721.996.632 (hàng) - 134.708.790 (phí) - 27.240.347 (chiết khấu) - 5.119.605 (trả hàng) = 554.927.890 VND
  so_hoa_don_ban_ra_duoc_thanh_toan = 184
  so_sieu_thi_xuat_hien = 59
  ngay_thanh_toan_duy_nhat = 2026-08-05 (khớp tên file 05.08)

BẪY:
  - BẪY TIỀN NẶNG NHẤT — 'Pmnt Date' KHÔNG phải ngày thanh toán. Cột này có 24 giá trị khác nhau (06/07 đến 01/09/2026), trong đó có 2 ngày NẰM SAU ngày trả thực tế (25/08/2026 và 01/09/2026). Đó là ngày ĐẾN HẠN của từng hóa đơn. Ngày trả thật là 'Clearing Date' = 2026-08-05 duy nhất cho cả file, khớp tên file '05.08'. Lấy nhầm cột là ghi sai kỳ thanh toán và tạo bút toán ở tháng chưa tới.
  - BẪY — Doc.Type='K1' KHÔNG đồng nghĩa 'hàng hóa, số âm'. Có 2 dòng K1 mang số DƯƠNG (r94, r95): Reference 'K26TRT|21246' / 'K26TRT|21900', Text 'TRA HANG - 110' / 'TRA HANG - 114' = HÀNG TRẢ LẠI, phải ghi giảm. Phân loại chỉ bằng Doc.Type sẽ cộng 5.119.605 vào tiền hàng (sai 2 lần con số này = 10.239.210). Phải kiểm thêm ký hiệu K26TRT. Đồng thời vẫn cấm phân loại bằng dấu theo §B hợp đồng.
  - BẪY — Doc.Type='KS' (chiết khấu) HOÀN TOÀN THIẾU trong hợp đồng hiện tại (§C chỉ ghi K1 và D1). Có 2 dòng KS, tổng 27.240.347 VND. Nếu code chỉ nhận K1/D1 thì 27 triệu này rơi vào nhánh 'không nhận diện' và tổng sẽ lệch.
  - BẪY — dòng KS r96 có Reference '1C26THG|5656', tức MANG KÝ HIỆU HÓA ĐƠN BÁN RA CỦA MÌNH nhưng KHÔNG phải thanh toán hóa đơn đó, mà là chiết khấu 1.916.203. Nếu khớp Reference -> Sales Invoice một cách mù quáng sẽ đánh dấu hóa đơn 5656 là ĐÃ THANH TOÁN trong khi thực tế chưa. Phải chặn: chỉ dòng row_kind='thanh_toan' mới được khớp sang Sales Invoice.
  - BẪY — file có HAI dòng 'Result', không phải một. Hồ sơ cũ ghi 'dòng Terms of Pmnt = Result (r3)' như thể chỉ có 1. Thực tế mỗi Clearing Doc. có 1 dòng Result riêng: r3 (1000031683 = -460.442.354) và r129 (1000032558 = -94.485.536). Bỏ theo vị trí dòng cứng r3 sẽ cộng nhầm -94.485.536 vào chi tiết.
  - BẪY — file chứa HAI tài khoản nhà cung cấp (Account 3003172 với 126 dòng và 3006634 với 70 dòng), tương ứng hai Clearing Doc. và hai điều khoản thanh toán khác nhau (A040 vs A030). Đây là hai lần bù trừ riêng biệt trong cùng một file. Không được coi cả file là một chứng từ thanh toán duy nhất.
  - BẪY — 'Terms of Pmnt' vừa là điều khoản thanh toán (A040/A030/'#') vừa là cờ đánh dấu dòng tổng ('Result'). Một cột hai vai trò. Nếu map cột này thành field điều khoản rồi lọc dòng tổng ở chỗ khác thì dễ sót.
  - BẪY — cột 'Assignment' KHÔNG đồng nhất kiểu dữ liệu. Với dòng K1 là TÊN siêu thị (chuỗi, 59 giá trị: 'VINH', 'go! PHU MY', 'GARDEN MALL'...). Với dòng D1/KS là mã tài khoản: '3003172.9999.', '3006634.9999.', '3003172..9999' (chú ý HAI dấu chấm — không nhất quán ngay trong file), và r96 là số nguyên int 3003172 chứ không phải chuỗi. str() thẳng ra '3003172' còn openpyxl trả int -> so sánh chuỗi sẽ trượt.
  - BẪY — Text cùng nội dung nhưng khác dấu tiếng Việt: 'Hàng hóa quầy 0410.3006634' (63 dòng) và 'Hang hoa quay 0410.3006634' (3 dòng, không dấu). Không được phân loại dòng bằng cách so khớp Text.
  - BẪY — Text phí có HAI khoảng trắng liền: 'Phí dịch vụ  EBS Tháng 07.2026 Quầy 0410'. Phải chuẩn hóa khoảng trắng trước khi so sánh.
  - BẪY — file KHÔNG có cột VAT, KHÔNG có tiền trước thuế, KHÔNG có mã siêu thị. Chỉ có một cột 'Amount' duy nhất. Tuyệt đối không tự chia 1.1 hay nhân 10% để suy amount_before_vat/vat_amount — đó là bịa số tiền.
  - BẪY — chuỗi phí 'K26TEB' và trả hàng 'K26TRT' rất giống nhau (khác 1 ký tự), lại cùng tiền tố 'K26T'. So khớp bằng startswith('K26T') sẽ gộp nhầm phí với trả hàng.
  - BẪY — Reference có thể KHÔNG chứa dấu '|' ('CK T07.2026'). ref.split('|')[1] sẽ nổ IndexError; phải dùng partition và kiểm tra.

CHƯA XÁC MINH:
  - Ý nghĩa nghiệp vụ của 'Terms of Pmnt' A040 vs A030 — chỉ quan sát được A040 gắn với Account 3003172, A030 gắn với Account 3006634, và '#' gắn với mọi dòng phí/chiết khấu. Chưa biết đó là số ngày công nợ hay điều gì khác.
  - Ý nghĩa của 'Account' 3003172 vs 3006634 — cả hai đều là 'quầy 0410' theo cột Text. Chưa biết đây là hai mã nhà cung cấp, hai pháp nhân, hay hai nhóm hàng. Chưa có ánh xạ sang Customer của ERPNext.
  - Ý nghĩa hậu tố '.9999' trong Assignment của dòng phí ('3003172.9999.') và biến thể '3003172..9999' của dòng chiết khấu.
  - Ký hiệu 'K26TEB' và 'K26TRT' là chứng từ do Central Retail phát hành. Chưa xác minh chúng có tương ứng với Purchase Invoice / Credit Note nào bên mình không, và có phải nhập liệu tay không.
  - Số '110' và '114' trong Text 'TRA HANG - 110' / 'TRA HANG - 114' là gì (số phiếu trả? mã lý do?).
  - Ánh xạ 59 tên siêu thị trong cột Assignment sang mã kho / Cost Center / Territory của ERPNext — file KHÔNG cung cấp mã, chỉ có tên viết hoa không dấu, và có cả tiền tố 'go!' cho định dạng GO!.
  - Có kỳ nào Doc.Type xuất hiện giá trị khác K1/D1/KS không (parser đã có nhánh 'doctype_la' để đánh dấu thay vì đoán, nhưng chưa gặp mẫu thật).
  - Có kỳ nào một file chứa nhiều 'Clearing Date' khác nhau không (file này chỉ có 1 ngày duy nhất; LOTTE đã có tiền lệ nhiều ngày thanh toán theo §H hợp đồng, nên không được giả định Central Retail luôn 1 ngày).
  - Chưa xác minh 4 file chuỗi còn lại (WinCommerce, LOTTE, Emart, Co.op) — nhiệm vụ này chỉ soi central_retail.
"""

# -*- coding: utf-8 -*-
"""Đọc bảng kê thanh toán chuỗi Central Retail (EB/GO!) — file .xlsx 1 sheet.

Đã CHẠY THẬT trên /root/.claude/uploads/.../365cb77c-HOANG_GIANG_05.08_EB.xlsx
(198 dòng, 12 cột). Tổng chi tiết khớp tuyệt đối với dòng 'Overall Result'
và với từng dòng 'Result' theo Clearing Doc. (chênh lệch = 0).

Chỉ ĐỌC + phân loại. Không tạo/sửa/hủy chứng từ kế toán nào.
"""
import re
import datetime
import openpyxl

# Header thật ở DÒNG 1. Vẫn dò theo TÊN cột chứ không hardcode vị trí, vì file
# do SAP xuất và thứ tự cột có thể đổi giữa các kỳ.
_HEADERS = [
    "Account", "Clearing Doc.", "Terms of Pmnt", "Assignment", "Reference",
    "Doc.Type", "Doc. Date", "Entry Date", "Pmnt Date", "Text",
    "Clearing Date", "Amount",
]

# Doc.Type -> loại dòng. BẮT BUỘC phân loại bằng cột này, TUYỆT ĐỐI không bằng
# dấu của Amount: trong chính file này có 2 dòng Doc.Type=K1 mang số DƯƠNG
# (hàng trả lại). Lấy dấu làm căn cứ là ghi nhận ngược chiều tiền.
_DOCTYPE_KIND = {
    "K1": "thanh_toan",   # hàng hóa — hóa đơn bán ra của mình, Amount âm
    "D1": "phi",          # phí dịch vụ / phí hỗ trợ — chuỗi trừ lại, dương
    "KS": "chiet_khau",   # chiết khấu — chuỗi trừ lại, dương
}

# Ký hiệu chứng từ của BÊN CHUỖI (không phải hóa đơn bán ra của mình).
# K26TEB = hóa đơn phí do Central Retail phát hành.
# K26TRT = phiếu trả hàng. Dòng trả hàng vẫn mang Doc.Type=K1 nhưng số DƯƠNG,
# nên phải nhận diện thêm bằng ký hiệu, nếu không sẽ cộng nhầm vào tiền hàng.
_SERIES_RETURN = "K26TRT"
_SERIES_CHAIN_FEE = "K26TEB"


def _norm(s):
    # gộp khoảng trắng: Text phí thật có HAI dấu cách liền nhau
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _to_date(v):
    """Ô ngày trong file thật đã là datetime; vẫn phòng text/serial kỳ sau."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    s = _norm(v)
    for f in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    return None


def _to_amount(v):
    """Giữ nguyên giá trị số của ô để còn đối chiếu với dòng tổng trong file.
    File thật: mọi Amount đều là số nguyên VND, không có công thức."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _norm(v).replace(",", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def _split_reference(ref):
    """Reference dạng 'C26THG|4675' -> (series, so, series_chuan_hoa).

    Bẫy đã gặp trong file thật:
      - Cùng một dải hóa đơn xuất hiện cả 'C26THG|4675' và '1C26THG|4674'.
        Chữ số đứng TRƯỚC ký hiệu là chữ số dạng hóa đơn, phải bỏ khi khớp,
        nếu không sẽ coi là hai ký hiệu khác nhau và không khớp được hóa đơn.
      - Có dòng Reference KHÔNG có dấu '|' ('CK T07.2026'). Dùng
        ref.split('|')[1] sẽ nổ IndexError.
    """
    ref = _norm(ref)
    if not ref or "|" not in ref:
        return None, None, None
    series, _, no = ref.partition("|")
    series = series.strip()
    no = no.strip()
    # bỏ chữ số dạng hóa đơn ở ĐẦU ký hiệu: '1C26THG' và 'C26THG' là MỘT
    series_norm = re.sub(r"^\d+", "", series) or None
    return (series or None), (no or None), series_norm


def parse_central_retail(path, sheet=None):
    """Đọc file bảng kê Central Retail -> list[dict]."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]

    rows = [r for r in ws.iter_rows(values_only=True)]
    if not rows:
        return []

    # --- dò header ---
    hdr_idx = None
    for i, r in enumerate(rows[:20]):
        cells = [_norm(c) for c in r]
        if "Reference" in cells and "Doc.Type" in cells and "Amount" in cells:
            hdr_idx = i
            break
    if hdr_idx is None:
        raise ValueError("Không tìm thấy dòng header (cần Reference/Doc.Type/Amount)")
    hdr = [_norm(c) for c in rows[hdr_idx]]
    col = {}
    for name in _HEADERS:
        col[name] = hdr.index(name) if name in hdr else None
    for must in ("Reference", "Doc.Type", "Amount", "Clearing Date"):
        if col[must] is None:
            raise ValueError("Thiếu cột bắt buộc: %s" % must)

    def cell(r, name):
        i = col[name]
        return None if i is None else (r[i] if i < len(r) else None)

    out = []
    for n, r in enumerate(rows[hdr_idx + 1:], start=hdr_idx + 2):
        if all(c is None for c in r):
            continue
        account = _norm(cell(r, "Account"))
        terms = _norm(cell(r, "Terms of Pmnt"))
        doctype = _norm(cell(r, "Doc.Type"))
        amount = _to_amount(cell(r, "Amount"))
        ref = _norm(cell(r, "Reference"))
        assignment = _norm(cell(r, "Assignment"))
        text = _norm(cell(r, "Text"))

        # --- DÒNG TỔNG: bỏ khỏi phần chi tiết nhưng GIỮ LẠI để đối chiếu ---
        # 'Overall Result' = tổng toàn file (1 dòng).
        # Terms of Pmnt = 'Result' = tổng theo TỪNG Clearing Doc. — file này có
        # HAI dòng (r3 và r129), không phải một. Bỏ theo vị trí dòng cứng r3 sẽ
        # cộng nhầm -94.485.536 vào chi tiết.
        if account == "Overall Result":
            out.append(_mk(n, "bo_qua", "tong_toan_file", r, col, cell,
                           amount=amount))
            continue
        if terms == "Result":
            out.append(_mk(n, "bo_qua", "tong_theo_clearing_doc", r, col, cell,
                           amount=amount, account=account, terms=terms))
            continue

        series, no, series_norm = _split_reference(ref)
        kind = _DOCTYPE_KIND.get(doctype)
        if kind is None:
            # Doc.Type lạ: KHÔNG đoán. Đánh dấu để người xem, không tự xử lý.
            kind = "bo_qua"
            sub = "doctype_la:%s" % (doctype or "rong")
        elif kind == "thanh_toan" and (series or "").upper().startswith(_SERIES_RETURN):
            # Trả hàng: Doc.Type vẫn K1 nhưng là GHI GIẢM và số DƯƠNG.
            kind = "ghi_giam"
            sub = "tra_hang"
        elif kind == "phi":
            sub = "phi_dich_vu"
        elif kind == "chiet_khau":
            # CẢNH BÁO: dòng KS có thể mang ký hiệu hóa đơn bán ra của mình
            # ('1C26THG|5656') mà KHÔNG phải thanh toán hóa đơn đó. Chỉ dòng
            # row_kind='thanh_toan' mới được phép khớp sang Sales Invoice.
            sub = "chiet_khau"
        else:
            sub = "hang_hoa"

        out.append(_mk(n, kind, sub, r, col, cell, amount=amount,
                       series=series, no=no, series_norm=series_norm,
                       assignment=assignment, text=text, doctype=doctype,
                       account=account, terms=terms))
    wb.close()
    return out


def _mk(rownum, kind, sub, r, col, cell, amount=None, series=None, no=None,
        series_norm=None, assignment=None, text=None, doctype=None,
        account=None, terms=None):
    # payment_date = 'Clearing Date' (ngày chuỗi thực trả, đồng nhất cả file,
    # khớp tên file 05.08). KHÔNG dùng 'Pmnt Date': đó là ngày ĐẾN HẠN của từng
    # hóa đơn, file thật có 24 giá trị khác nhau và có cả ngày TƯƠNG LAI
    # (25/08, 01/09) so với ngày trả 05/08. Lấy nhầm là ghi sai kỳ thanh toán.
    return {
        "row_kind": kind,
        "row_subtype": sub,
        "row_no": rownum,
        "inv_series": series,
        "inv_series_norm": series_norm,   # đã bỏ chữ số dạng hóa đơn ở đầu
        "inv_no": no,
        "inv_date": _to_date(cell(r, "Doc. Date")),
        "store_code": None,               # file KHÔNG có mã siêu thị — không đoán
        "store_name": assignment if kind in ("thanh_toan", "ghi_giam") else None,
        "doc_no": _norm(cell(r, "Clearing Doc.")) or None,
        "amount_before_vat": None,        # file KHÔNG tách VAT — cấm tự suy 10%
        "vat_amount": None,
        "total_amount": None if amount is None else abs(amount),
        "raw_amount": amount,             # giữ dấu gốc để đối chiếu dòng tổng
        "payment_date": _to_date(cell(r, "Clearing Date")),
        "due_date": _to_date(cell(r, "Pmnt Date")),
        "description": text,
        "account": account,
        "doc_type": doctype,
        "terms_of_pmnt": terms,
        "assignment_raw": assignment,
    }


# ---- KẾT QUẢ CHẠY THẬT (đã verify) ----
# rows parsed: 197
#   thanh_toan/hang_hoa : n=184  sum_raw = -721,996,632
#   ghi_giam/tra_hang   : n=2    sum_raw =    5,119,605
#   phi/phi_dich_vu     : n=6    sum_raw =  134,708,790
#   chiet_khau          : n=2    sum_raw =   27,240,347
#   bo_qua (tổng)       : n=3
#   -> tổng 194 dòng chi tiết = -554,927,890
#   -> 'Overall Result' trong file = -554,927,890   => CHÊNH LỆCH 0
#   -> Result 1000031683: file -460,442,354 / chi tiết -460,442,354 => 0
#   -> Result 1000032558: file  -94,485,536 / chi tiết  -94,485,536 => 0
