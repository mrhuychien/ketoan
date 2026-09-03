# Prompt: đưa cơ chế "ghi số hóa đơn MISA vào Sales Invoice" sang app khác

Copy nguyên khối dưới đây làm prompt. Nó mô tả **cơ chế đã chạy thật** trong app
`ketoan` (`ketoan/api/misa_*.py`), kèm những chốt chặn mà chỉ dữ liệu thật mới
dạy ra được — phần đắt nhất của bản này nằm ở các chốt đó, không nằm ở luồng
chính.

> ⚠ Viết bởi phiên **không có repo `nppsale` trong tay**. Mọi tên field/module là
> của `ketoan`; người áp dụng phải đối chiếu lại với quy ước của app đích.

---

## PROMPT

Tôi cần bạn dựng cơ chế **kéo số hóa đơn điện tử MISA meInvoice về `Sales
Invoice` của ERPNext v16** cho app này. Dưới đây là thiết kế đã chạy thật ở một
app khác cùng hệ thống. Hãy đọc hết trước khi viết dòng code nào, rà lại xem app
này đã có phần nào chưa, rồi mới làm.

### 0. Nguyên tắc bao trùm — vi phạm cái nào là hỏng cả cơ chế

1. **Chứng từ đã ghi sổ chỉ được ghi bằng `frappe.db.set_value(...,
   update_modified=False)`.** TUYỆT ĐỐI không `save()`, không `submit()`,
   không đụng `GL Entry`. `save()` một Sales Invoice `docstatus=1` sẽ chạy lại
   `validate()` và có thể chặn giữa lô.
2. **Cô lập blast radius:** chỉ MỘT module được ghi vào `Sales Invoice`. Module
   đối soát/khớp chỉ ghi vào bảng snapshot của nó.
3. **Không đoán.** Không khớp được thì để trống + gắn nhãn "chưa xác định". Ghi
   sai một số hóa đơn là sai báo cáo thuế, mà nó vẫn trông hợp lý trên màn hình.
4. **Không bao giờ chặn `submit`.** Kế toán phải ghi sổ được kể cả khi tích hợp
   MISA hỏng hoàn toàn. Hook `before_submit` phải bọc `try/except` nuốt lỗi.

### 1. Kiến trúc hai khóa

Số hóa đơn KHÔNG có lúc ghi sổ — MISA cấp sau. Nên cần **khóa nối sinh trước**:

```
before_submit  ->  sinh custom_misa_ref_id = uuid4()   (khóa nối, của mình)
push           ->  gửi ERPNext -> MISA kèm ref_id
(MISA phát hành, cấp số)
poll_pending   ->  GET afterpublishing/{ref_id}  ->  ghi số về Sales Invoice
```

Sai lầm của bản đầu: sinh uuid rồi **vứt đi**, không lưu — sau đó không còn
đường nào hỏi lại MISA "hóa đơn này của tôi được cấp số chưa".

### 2. Custom field cần tạo trên Sales Invoice

Tất cả `read_only = 1`, `no_copy = 1`, gom vào một tab/section riêng.

| fieldname | type | vai trò |
|---|---|---|
| `custom_misa_ref_id` | Data | **khóa nối**, uuid4 sinh trước khi ghi sổ |
| `custom_misa_inv_series` | Data | ký hiệu (`1C25MHG`) |
| `custom_misa_inv_no` | Data | **số hóa đơn** |
| `custom_misa_inv_date` | Date | ngày phát hành (KHÁC `posting_date`) |
| `custom_misa_transaction_id` | Data | mã tra cứu |
| `custom_misa_invoice_code` | Data | mã CQT |
| `custom_misa_link` | Data | URL tra cứu, dựng từ mẫu trong Settings |
| `custom_misa_status` | Select | vòng đời (xem §5) |
| `custom_misa_relation` | Select | quan hệ thay thế/điều chỉnh (xem §5) |
| `custom_misa_org_ref_id` | Data | ref_id hóa đơn gốc (nếu đây là bản thay thế) |
| `custom_misa_org_inv` | Data | ký hiệu+số của hóa đơn bên kia quan hệ |
| `custom_misa_pushed_at` | Datetime | đã đẩy lúc nào |
| `custom_misa_last_checked` | Datetime | hỏi MISA lần cuối lúc nào |
| `custom_misa_note` | Small Text | cảnh báo lệch / ghi chú xử lý |
| `custom_misa_no_locked` | Check | **số do người gán — đồng bộ không được đè** |

Nếu app đã có ô số hóa đơn nhập tay (ví dụ `vn_einvoice_number`), **giữ nguyên**
và coi nó là *mặt hiển thị*, còn nhóm `custom_misa_*` là *dữ liệu kỹ thuật*.
Xem §7 để đồng bộ hai nhóm mà không đè nhau.

### 3. `ensure_ref_id` — hook `Sales Invoice.before_submit`

```python
def ensure_ref_id(doc, method=None):
    try:
        if not doc.meta.has_field("custom_misa_ref_id"):
            return                      # chưa migrate -> im lặng bỏ qua
        if doc.get("amended_from"):
            # XÓA SẠCH nhóm MISA rồi cấp ref_id MỚI.
            ...
            doc.custom_misa_ref_id = str(uuid.uuid4())
            doc.custom_misa_status = "Chưa đẩy"
            return
        if (doc.get("custom_misa_ref_id") or "").strip():
            return
        doc.custom_misa_ref_id = str(uuid.uuid4())
    except Exception:
        pass        # KHÔNG BAO GIỜ chặn submit
```

⚠ **Nhánh `amended_from` là bắt buộc, và đừng trông vào `no_copy`:**
`frappe.model.copy_doc` **bỏ qua cờ `no_copy` khi amend**. Không dọn thì bản sửa
đổi mang theo nguyên `ref_id` + số hóa đơn + `pushed_at` của bản ĐÃ HỦY ⇒
`push` trả về "đã xuất rồi", bản sửa đổi **vĩnh viễn không được phát hành**,
trong khi màn hình vẫn hiện số hóa đơn của bản đã hủy.

Cần thêm hai method vá dữ liệu cũ: `count_missing_ref_id()` và
`backfill_ref_id(limit)` cho hóa đơn ghi sổ trước khi có tích hợp.

### 4. `poll_pending` — vòng kéo số về

**PHẢI có HAI vòng quét, không phải một.**

```python
# Vòng 1 — chưa có số: hỏi xem MISA cấp chưa
filters = {"docstatus": 1,
           "custom_misa_ref_id": ("is", "set"),
           "custom_misa_inv_no": ("is", "not set"),
           "posting_date": (">=", since)}

# Vòng 2 — ĐÃ có số nhưng chưa ở trạng thái cuối
filters = {"docstatus": 1,
           "custom_misa_ref_id": ("is", "set"),
           "custom_misa_inv_no": ("is", "set"),
           "custom_misa_status": ("not in", ["Đã hủy", "Đã thay thế"]),
           "posting_date": (">=", since)}
if frappe.db.has_column("Sales Invoice", "custom_misa_no_locked"):
    filters["custom_misa_no_locked"] = 0
```

⚠ Thiếu **vòng 2** thì hóa đơn bị HỦY hoặc bị THAY THẾ trên MISA *sau khi đã cấp
số* không bao giờ bị phát hiện — bộ lọc vòng 1 loại chúng ra, nên hai nhánh xử
lý đó thành **code chết**. Sổ vẫn ghi một hóa đơn hợp lệ trong khi bên MISA nó
đã bị hủy. Đây là rủi ro thuế thật, không phải chuyện giao diện.

⚠ `custom_misa_no_locked` trong vòng 2: chứng từ đã được người gán số hóa đơn
thay thế thì `ref_id` trên đó vẫn trỏ hóa đơn **đã chết** — vòng 2 sẽ ghi số
chết đè lên số người vừa gán, lặng lẽ, mỗi lần đồng bộ.

⚠ Dùng `frappe.db.has_column` chứ không phải `meta.has_field` khi lọc: site chưa
chạy patch mà lọc theo cột chưa tồn tại là gãy nguyên job.

Với mỗi hóa đơn: `GET afterpublishing/{ref_id}`, rồi:

- API không biết hóa đơn → nếu đã có số thì **chỉ** cập nhật `last_checked`
  (đừng hạ trạng thái đang đúng — có thể lỗi tạm); nếu chưa có số thì đặt
  `"Đã đẩy (nháp)"` **chỉ khi thật sự đã đẩy** (`pushed_at` có giá trị), ngược
  lại `"Chưa đẩy"`. Ghi bừa "đã đẩy" là khẳng định sai về nghĩa vụ thuế.
- Số hóa đơn rỗng hoặc bắt đầu bằng `<` (MISA giữ chỗ `<Chưa cấp số>`) → coi như
  chưa có số.
- Có số → ghi cả cụm, so tiền, cập nhật trạng thái.
- **Luôn** cập nhật `custom_misa_last_checked`, kể cả khi chưa có số.
- `commit()` mỗi 50 dòng; gom lỗi vào `error_log` chứ không dừng cả job.

Ghi lại mỗi lượt chạy vào một DocType `MISA Sync Run` (job_type, trigger_type,
from/to date, fetched/updated/matched/mismatched, error_log, status) — không có
nó thì không ai biết job có chạy không và chạy ra sao.

### 5. HAI TRỤC TRẠNG THÁI — nằm ở HAI field khác nhau

Đây là chỗ bản đầu suy sai và phải đo lại trên hóa đơn thật mới vỡ ra:

| trục | field API | ý nghĩa |
|---|---|---|
| **giá trị pháp lý** | `PublishStatus` | `0` = nháp · `3` = đã cấp mã |
| **quan hệ** | `EInvoiceStatus` | `1` mới · `3` thay thế · `4` điều chỉnh · `7` bị thay thế · `8` bị điều chỉnh |

Bằng chứng: 5 hóa đơn đọc sẵn trạng thái "Đã cấp mã" trên màn hình MISA đều giữ
`PublishStatus = 3`, trong khi `EInvoiceStatus` chạy 1/3/4/7/8 đúng theo quan hệ.
**Đừng suy trạng thái phát hành từ `EInvoiceStatus`.**

Bốn hệ quả bắt buộc phải cài:

1. **"Bị thay thế" ⇒ hết hiệu lực**, bất kể từng được cấp mã. **"Bị điều chỉnh"
   thì KHÔNG** — hóa đơn điều chỉnh chỉ cộng phần chênh, bản gốc vẫn còn hiệu
   lực và vẫn phải kê khai. Gộp hai loại này là khai thiếu doanh thu bản gốc.
2. **Hóa đơn điều chỉnh mang số CHÊNH, không phải tổng.** Đem so với
   `grand_total` là ra "Lệch tiền" **giả** cho mọi hóa đơn điều chỉnh. Phải bỏ
   qua phép so tiền và **nói ra trên màn hình vì sao bỏ qua** — im lặng thì kế
   toán tưởng đã đối chiếu xong.
3. **Hóa đơn thay thế khai lại TOÀN BỘ.** Bên ERPNext phần hàng bị từ chối đi
   bằng một **hóa đơn trả về** (`is_return=1`, `return_against` trỏ bản gốc),
   nên vế ERPNext đem so phải là **(hóa đơn − trả về)**. Dùng CHUNG một hàm
   `erp_totals(si, relation)` cho mọi màn hình, để hai chỗ không bao giờ nói hai
   con số khác nhau về cùng một hóa đơn.
4. **Đọc được `OrgRefID` ⇒ phải đánh dấu hóa đơn GỐC là "Đã thay thế".** Không
   làm thì hai hóa đơn cùng hiện "Đã phát hành" cho một lần bán ⇒ doanh thu và
   thuế đầu ra khai **gấp đôi**.
   ⚠ Và phải đọc trục quan hệ từ `EInvoiceStatus` chứ đừng chỉ suy ngược từ
   `OrgRefID`: bản **bị** thay thế không hề mang `Org*` (đã đo trên hóa đơn
   thật — trống sạch), nên hóa đơn hết hiệu lực nào mà ta chưa thấy bản thay thế
   của nó sẽ vĩnh viễn không bị phát hiện.

Trạng thái lạ (đang phát hành / phát hành lỗi / từ chối cấp mã…) thì **không
đoán** — lùi về mốc chắc chắn là mã CQT. Và nhớ: đơn vị dùng hóa đơn **không
mã** thì không bao giờ có mã đó, phải đọc cờ `use_code_route` trong Settings,
không thì mọi hóa đơn của họ đứng vĩnh viễn ở "Chờ cấp mã".

### 6. So tiền ba vế

So `net_total` · `total_taxes_and_charges` · `grand_total`, dung sai lấy từ
Settings (mặc định 1đ). Lệch thì đặt trạng thái `"Lệch tiền"` **và tạo `ToDo`**
— một cảnh báo không ai được giao thì không phải cảnh báo.

⚠ **Chỉ so vế nào API THẬT SỰ trả số.** Endpoint *danh sách* của MISA không tách
thuế: `TotalAmountWithoutVAT` và `TotalVATAmount` về `0.0` ở cả 30/30 bản ghi
thật. So số 0 đó với `net_total` thật thì **mọi hóa đơn khớp đều bị gắn "Lệch
tiền"** — rổ cảnh báo đầy báo động giả, kế toán mất niềm tin rồi bỏ qua cả cảnh
báo thật. Riêng tổng tiền thì luôn có nên luôn so, và một mình nó đã đủ bắt lệch.

Tách **VẤN ĐỀ** (lệch tiền, xung đột số) khỏi **THÔNG TIN** (đây là hóa đơn điều
chỉnh nên không so tiền). Gộp chung thì hóa đơn điều chỉnh — vốn hoàn toàn bình
thường — bị đếm vào ô "lệch" và sinh ToDo giả.

### 7. Đồng bộ ngược sang ô số hóa đơn nhập tay

Nếu app có sẵn ô nhập tay mà nhiều màn hình đang đọc:

- **Chỉ ghi khi ô đó đang TRỐNG.** Không đè số kế toán đã điền.
- Nhưng **cũng không được im lặng**: khác nhau thì ghi vào `custom_misa_note`
  một dòng `"Số hóa đơn lệch: sổ ghi X, MISA cấp Y"` và nâng trạng thái lên
  `"Lệch tiền"`. Im lặng thì các màn hình kia tiếp tục hiện số sai.
- Ô "mã tra cứu" cũ thường là **uuid rác** của luồng cũ (tra cứu ra 0 kết quả) —
  cái này thì được đè bằng mã thật.

### 8. Link tra cứu — đừng gán `None`

Dựng URL từ mẫu khai trong Settings. **Chỉ ghi khi dựng được**: gán `None` vào
payload là **xóa trắng link tốt đang có** ở lượt quét sau, mà API có lúc trả
thiếu `TransactionID` (hóa đơn đang "Chờ cấp mã").

### 9. Đối soát hai chiều — DocType snapshot riêng

Kéo danh sách hóa đơn từ MISA về một DocType `MISA Invoice Snapshot` (ref_id,
transaction_id, inv_series, inv_no, **inv_no_norm**, inv_date, buyer_tax_code,
total_amount, amount_before_vat, vat_amount, is_deleted, einvoice_status,
sales_invoice, match_method, match_confidence, match_status, origin).

Không có bảng này thì **hóa đơn phát hành thẳng trên MISA (không qua ERPNext)
là vô hình** — đúng loại hóa đơn ngoài sổ mà kiểm toán sẽ hỏi.

**Khớp bốn tầng, dừng ở tầng đầu tiên trúng:**

| tầng | khóa | độ tin |
|---|---|---|
| 1 | `ref_id` | Chắc chắn |
| 2 | `transaction_id` | Chắc chắn |
| 3 | (ký hiệu chuẩn hóa, số chuẩn hóa) | Chắc chắn |
| 4 | (MST gốc, ngày, tiền làm tròn) | **Cần review** |

⚠ Tầng 4 **chỉ nhận khi DUY NHẤT một hóa đơn trùng cả ba vế**. Nhiều hóa đơn
cùng MST/ngày/tiền là chuyện thường; đoán bừa là sai báo cáo thuế.

⚠ Module khớp **chỉ ghi vào snapshot, không bao giờ ghi ngược vào Sales
Invoice** (nguyên tắc §0.2).

⚠ **Không đè bản ghi người đã chốt tay** (`match_method == 'thu_cong'`).

**Chuẩn hóa — hai hàm, khai một chỗ, dùng chung mọi nơi:**

```python
def norm_inv_no(s):     # '00000123' -> '123'; giữ nguyên nếu toàn 0 / không phải số
def norm_series(s):     # '1C25MHG' == 'C25MHG'  (re.sub(r'^\d+', '', s.upper()))
def base_taxcode(v):    # '0301175691-044' -> '0301175691'  (MST chi nhánh)
```

Cùng một file thật dùng lẫn `1C25MHG` (35 dòng) và `C25MHG` (10 dòng) cho cùng
dải số. Không chuẩn hóa là mất 10 dòng, im lặng.

### 10. Chép số hóa đơn nhập tay sang nhóm MISA (nếu có dữ liệu cũ)

Hóa đơn cũ chỉ có số ở ô nhập tay sẽ rơi hết vào rổ "chỉ có trên phần mềm", bản
MISA tương ứng rơi vào rổ "chỉ có trên MISA" — hai rổ cảnh báo đầy báo động giả.
Cần một job chép ngược, với **năm chốt chặn**:

1. **XEM TRƯỚC bắt buộc**, và `commit` phải mang **vân tay của đúng kế hoạch vừa
   xem** (sha1 của `name|series|no|date` từng dòng). Giữa lúc xem và lúc bấm
   nạp, người khác sửa một ô là số đó được ghi mà chẳng ai thấy.
2. **Không đè** `custom_misa_inv_no` đang có số — luồng tự động đáng tin hơn.
3. **Không cấp trùng số.** Phải có chỉ mục cả `(ký hiệu, số)` **và chỉ theo số**:
   luồng đồng bộ có thể đã ghi số mà bỏ trống ký hiệu, nên khóa `('', '123')`
   không bao giờ đụng `('1C25MHG', '123')` — chỉ so khóa đủ cặp thì hai hóa đơn
   cùng mang số 123 mà không ai biết. Bắt trùng **ngay trong chính lô** nữa.
4. **Tách chuỗi thì kiểm và ghi CÙNG MỘT giá trị đã chuẩn hóa.** Kiểm ở dạng đã
   bỏ khoảng trắng rồi ghi dạng còn khoảng trắng là vô hiệu cả hai chốt: ô chứa
   hai số `'1C25MHG 123, 124'` lọt khuôn, ghi ký hiệu rác và **âm thầm vứt mất
   số 124**. Khuôn ký hiệu phải **bắt buộc có ít nhất một chữ cái**, nếu không
   `'2025-000123'` sẽ nhận nhầm `2025` làm ký hiệu.
5. **Không đoán ngày.** Không có ngày phát hành thì để TRỐNG — lấy
   `posting_date` thay là bịa: hóa đơn ghi sổ 31/03 phát hành 02/04 sẽ khai sai
   kỳ thuế. Và ô ngày cũ có thể là fieldtype `Data` chứa `'chưa có'` — parse
   hỏng giữa vòng lặp là lô ghi dở, không biết dừng ở đâu.

Dòng nào không chắc thì **bỏ lại kèm lý do đọc được** (`REASON_LABEL`), không
đoán. Và ô ghi chú đang mang cảnh báo đối soát thật + chữ kế toán tự gõ — chỉ
ghi khi đang trống.

### 11. Lịch chạy

`scheduler_events` gọi `poll_pending` trong **khung giờ khai trong Settings**
(công tắc bật/tắt + giờ bắt đầu/kết thúc), không chạy 24/7. Method whitelisted
phải qua guard quyền (`guard_manager`), không để ai gọi cũng được.

### 12. Cần làm gì

1. Rà app này xem đã có phần nào (custom field, hook, doctype, job).
2. Nêu ĐÚNG những chỗ khác biệt với thiết kế trên trước khi code — đừng chép mù.
3. Viết custom field + hook + `poll_pending` + `MISA Sync Run` trước; snapshot và
   đối soát hai chiều sau; job chép dữ liệu cũ sau cùng.
4. Với **mỗi** chốt chặn ⚠ ở trên, viết một phép kiểm chạy được không cần bench
   (stub `frappe`), rồi **thử phá**: sửa mã sản xuất cho hỏng đúng chốt đó và
   xác nhận phép kiểm ĐỎ. Chốt nào phá mà vẫn xanh thì phép kiểm đó đang nói dối.
5. Không tự chạy `bench migrate` / không tự submit gì. Báo lại lệnh cần chạy.
