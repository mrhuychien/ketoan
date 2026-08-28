"""mt_advice_pdf — đọc BẢNG KÊ THANH TOÁN ở dạng PDF thành lưới ô như Excel.

════════════════════════════════════════════════════════════════════════════
VÌ SAO CÓ MODULE NÀY
════════════════════════════════════════════════════════════════════════════

WinCommerce gửi bảng kê thanh toán bằng **PDF**. Trước đây phải có người chuyển
PDF sang Excel rồi mới nạp được — một bước tay nằm giữa chứng từ gốc và sổ sách,
và là bước không ai kiểm được: trình chuyển đổi tách cột sai thì con số vẫn vào
hệ thống trông như bình thường.

Module này bỏ hẳn bước đó: đọc thẳng PDF, trả về ĐÚNG khuôn `[(tên, lưới)]` mà
`read_sheets` của Excel trả về. Nhờ vậy **không một parser nào phải sửa** —
`detect_chain`, `parse_wincommerce`, `preview`, `commit` chạy nguyên như cũ.

════════════════════════════════════════════════════════════════════════════
CÁCH DỰNG LẠI CỘT — ĐO, KHÔNG ĐOÁN
════════════════════════════════════════════════════════════════════════════

PDF không có ô. Nó chỉ có chữ và tọa độ. Dựng lại cột bằng cách:

  1. cắt trang thành KHỐI theo đường kẻ `_____` mà bản in vẽ sẵn;
  2. trong mỗi khối, gom tọa độ ngang của MỌI từ thành các dải; khoảng trống
     giữa hai dải là ranh giới cột. Cột do CHÍNH DỮ LIỆU vẽ ra, không do ta
     đếm trước.

Đo trên file thật (WinCommerce 25.06.2026): 6 dải cách nhau 20-39pt, tách bạch
hoàn toàn. Đó là lý do cách này dùng được — không phải vì nó thông minh.

════════════════════════════════════════════════════════════════════════════
DÒNG TỔNG KHÔNG ĐI CHUNG ĐƯỜNG VỚI DÒNG DỮ LIỆU — VÀ ĐÓ LÀ CHỦ Ý
════════════════════════════════════════════════════════════════════════════

Đo được: dòng `Tổng cộng` in LỆCH PHẢI 34pt so với các dòng dữ liệu (`Tổng` ở
x=54 trong khi số chứng từ ở x=19.9; số tiền tổng ở x=500-555 trong khi tiền
từng dòng ở x=471-521). Ép nó vào cùng mô hình cột của bảng thì ô `0` của cột
Chiết khấu rơi trúng dải của cột Số tiền — HAI con số vào MỘT ô, và cái vào sau
đè cái vào trước.

Nên các DÒNG TỔNG KẾT (`Tổng cộng`, `Số dư mang sang trang sau`) được nhận diện
theo NHÃN IN SẴN và trả ra thành sheet riêng, mỗi dòng một ô chứa nguyên văn.
`parse_wincommerce` đọc chúng bằng regex — đúng cách nó vốn đã đọc chân trang
'Số dư mang sang trang sau'. Không có chỗ nào phải đoán con số nào thuộc cột nào.

════════════════════════════════════════════════════════════════════════════
PHẠM VI ĐÃ XÁC MINH
════════════════════════════════════════════════════════════════════════════

Bản in WinCommerce. ĐÃ đối chiếu: đọc từ PDF và đọc từ bản Excel chuyển đổi ra
**cùng 36 dòng, cùng 245.795.904đ, cùng số chứng từ thanh toán và cùng ngày** —
xem `docs/mt/verified/win_pdf_check.py`.

Chuỗi khác gửi PDF thì tầng này vẫn chạy, nhưng CHƯA ai đối chiếu. Đừng tin nó
cho tới khi có một phép đo tương tự.
"""

import frappe
from frappe import _

from ketoan.api.mt_rebate_pdf import LINE_TOL, is_pdf, read_words  # noqa: F401

# Khoảng trống ngang tối thiểu để coi là RANH GIỚI CỘT.
#
# Đo trên file thật: khoảng cách nhỏ nhất giữa hai dải cột là 20.8pt (giữa 'Số
# hóa đơn' và 'Ngày hóa đơn'), trong khi khoảng cách giữa hai TỪ trong cùng một ô
# lớn nhất là ~2.8pt. 8pt nằm giữa hai con số đó, cách xa cả hai đầu.
COL_GAP = 8.0

# Dòng kẻ của bản in: `_____...` ngăn khối, `*****` ngăn dòng.
RULE_CHARS = {"_"}
STAR_CHARS = {"*"}

# Nhãn của DÒNG TỔNG KẾT. Đọc theo nhãn in sẵn, không theo vị trí.
SUMMARY_LABELS = (
    "Tổng cộng",
    "Số dư mang sang trang sau",
    "Số dư mang sang từ trang trước",
)


def _is_rule(text) -> bool:
    t = (text or "").replace(" ", "")
    return len(t) >= 10 and set(t) <= RULE_CHARS


def _is_star(text) -> bool:
    t = (text or "").replace(" ", "")
    return len(t) >= 3 and set(t) == STAR_CHARS


def _to_lines(words):
    """Từ -> dòng, mỗi dòng đã sắp theo tọa độ ngang.

    `read_words` trả về theo thứ tự dòng rồi cột, nhưng các từ trong cùng một
    dòng in có thể lệch nhau vài phần mười điểm nên rơi vào hai khóa khác nhau.
    Gom lại theo `LINE_TOL` rồi SẮP LẠI THEO x — bỏ bước sắp này là chữ trong
    dòng đảo lộn ('CỔ PHẦN ... CÔNG TY'), và mọi phép dò nhãn trên dòng đó trượt.
    """
    buckets = {}
    for w in words:
        buckets.setdefault(round(w["y"] / LINE_TOL), []).append(w)
    out = []
    for key in sorted(buckets, reverse=True):        # y gốc ở ĐÁY trang -> giảm dần
        line = sorted(buckets[key], key=lambda w: w["x0"])
        out.append(line)
    return out


def _columns(lines):
    """Ranh giới cột, dựng từ tọa độ ngang của CHÍNH các từ trong khối.

    Gộp mọi khoảng [x0, x1] chồng nhau hoặc cách nhau dưới `COL_GAP` thành một
    dải; mỗi dải là một cột. Cột do dữ liệu vẽ ra chứ không do ta đếm trước —
    đó là điều kiện để đọc được cả bảng có cột rỗng chen giữa.
    """
    spans = sorted((w["x0"], w["x1"]) for line in lines for w in line)
    if not spans:
        return []
    cols = [list(spans[0])]
    for x0, x1 in spans[1:]:
        if x0 - cols[-1][1] < COL_GAP:
            cols[-1][1] = max(cols[-1][1], x1)
        else:
            cols.append([x0, x1])
    return cols


def _col_of(word, cols):
    """Cột của một từ: dải nào CHỒNG LẤN nhiều nhất; không chồng ai thì gần nhất."""
    best, best_ov = 0, -1.0
    for i, (a, b) in enumerate(cols):
        ov = min(word["x1"], b) - max(word["x0"], a)
        if ov > best_ov:
            best, best_ov = i, ov
    return best


def _grid(lines, cols):
    """Khối -> lưới ô. Nhiều từ cùng cột thì nối bằng khoảng trắng, theo thứ tự in."""
    grid = []
    for line in lines:
        row = [None] * len(cols)
        for w in line:
            j = _col_of(w, cols)
            row[j] = (row[j] + " " + w["text"]) if row[j] else w["text"]
        grid.append(row)
    return grid


def _line_text(line) -> str:
    return " ".join(w["text"] for w in line)


def _summary_label(line):
    t = _line_text(line)
    for lab in SUMMARY_LABELS:
        if t.startswith(lab):
            return lab
    return None


_NUMISH = str.maketrans("", "", ".,%-+()")


def _is_label_block(block) -> bool:
    """Khối chỉ toàn CHỮ — tức là một dòng tiêu đề bị đường kẻ tách ra ở giữa.

    Bản in kẻ ngang CẢ TRÊN LẪN DƯỚI hàng tiêu đề:

        ___________________________________
        Số chứng từ  Số hóa đơn  ...  Số tiền
        ___________________________________
        5102066548   1C26THG#1730  ...

    Cắt khối theo đường kẻ mà không nối lại thì tiêu đề thành MỘT sheet và dữ
    liệu thành sheet KHÁC — `_wc_find_header` không thấy tiêu đề trên sheet dữ
    liệu nên bỏ qua sạch 36 dòng. Đã xảy ra đúng như vậy ở lần chạy đầu; số kiểm
    tra của file bắt được (0đ so với 245.795.904đ), nhưng không nên trông vào
    lưới an toàn cho một lỗi biết trước.
    """
    for line in block:
        for w in line:
            t = w["text"].translate(_NUMISH)
            if t and t.isdigit():
                return False
    return True


def _blocks(lines):
    """Cắt trang thành khối theo đường kẻ `____`. Bỏ hẳn dòng `****`.

    Khối chỉ toàn chữ được NỐI vào khối ngay sau nó — xem `_is_label_block`.
    """
    raw, cur = [], []
    for line in lines:
        t = _line_text(line)
        if _is_rule(t):
            if cur:
                raw.append(cur)
            cur = []
            continue
        if _is_star(t):
            continue          # đường kẻ giữa hai dòng dữ liệu, không phải dữ liệu
        cur.append(line)
    if cur:
        raw.append(cur)

    out, pending = [], []
    for block in raw:
        if _is_label_block(block):
            # Chưa biết nó là tiêu đề của bảng nào cho tới khi thấy khối sau.
            pending.extend(block)
            continue
        out.append(pending + block)
        pending = []
    if pending:
        out.append(pending)          # tiêu đề cuối trang, không có bảng theo sau
    return out


def pdf_to_sheets(raw: bytes):
    """PDF bytes -> `[(tên sheet, lưới)]`, đúng khuôn `mt_advice.read_sheets` trả về.

    Mỗi KHỐI in thành một sheet, đặt tên `Trang N.M` để dòng cảnh báo của parser
    còn chỉ được đúng chỗ trên bản in giấy mà kế toán đang cầm.
    """
    pages = read_words(raw)
    sheets = []
    for pno, words in enumerate(pages, start=1):
        lines = _to_lines(words)
        for bno, block in enumerate(_blocks(lines), start=1):
            name = "Trang %d.%d" % (pno, bno)

            # Dòng tổng kết tách ra sheet RIÊNG, giữ nguyên văn trong MỘT ô.
            # Xem chú thích đầu module: ép chúng vào mô hình cột của bảng là hai
            # con số rơi vào một ô.
            body = [l for l in block if not _summary_label(l)]
            for k, l in enumerate([l for l in block if _summary_label(l)], start=1):
                sheets.append(("%s tổng %d" % (name, k), [[_line_text(l)]]))

            if not body:
                continue
            cols = _columns(body)
            if not cols:
                continue
            sheets.append((name, _grid(body, cols)))
    return sheets


def read_sheets_any(content, allow_wide=False):
    """Cửa VÀO DUY NHẤT: nhận base64 của Excel HOẶC PDF, trả cùng một khuôn.

    Nhận diện bằng CHỮ KÝ BYTE `%PDF`, không bằng đuôi tên file — chuỗi siêu thị
    đã từng gửi `.Xls` viết hoa và tên file có khoảng trắng không ngắt. Đuôi tên
    là thứ người gõ, chữ ký byte là thứ máy ghi.
    """
    from ketoan.api.mt_advice import decode_upload, read_sheets

    raw = decode_upload(content)
    if not is_pdf(raw):
        return read_sheets(content, allow_wide=allow_wide)

    sheets = pdf_to_sheets(raw)
    if not sheets:
        frappe.throw(_(
            "Không đọc được nội dung nào từ file PDF. File quét ảnh (scan) thì tầng này "
            "không đọc được — cần bản PDF gốc do hệ thống siêu thị xuất ra."))
    return sheets
