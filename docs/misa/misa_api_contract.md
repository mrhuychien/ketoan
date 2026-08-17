# MISA meInvoice — API Contract & Discovery (Phase 0)

> **Trạng thái: CHƯA ĐỦ ĐỂ SANG PHASE 1.**
> Phần A (khảo sát repo) + Phần D (môi trường) đã xong. Phần B/C — payload & response
> **thật** của MISA — chưa lấy được: network policy của container **chặn** mọi kết nối
> tới `*.meinvoice.vn` (403 CONNECT, xem §D.3). Phải do người dùng lấy từ DevTools/Postman.
>
> Quy tắc cứng của pack: **không đoán tên field response. Chưa có trong file này thì chưa code.**

Ngày khảo sát: 2026-08-17 · Nhánh: `claude/zen-babbage-0vj0eg` · App: `ketoan`

---

## A. Khảo sát app hiện có (ĐÃ XÁC MINH — có file:line)

### A.1 U1 — App đã có code đẩy hóa đơn sang MISA chưa?

**KẾT LUẬN: CHƯA CÓ. App không đẩy hóa đơn, không sinh/lưu RefID.**

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Chuỗi `misa` / `meinvoice` / `e-invoice` | grep toàn repo (py/js/json/md/txt) | **0 hit thật** (chỉ trùng icon `fa-file-invoice`) |
| Gọi API ra ngoài | grep `import requests`, `make_post_request`, `make_get_request`, `urllib.request`, `http.client`, `frappe.integrations` | **0 hit** |
| Sinh UUID / khóa nối | grep `uuid`, `uuid4`, `frappe.generate_hash` | **0 hit** |

→ Nếu doanh nghiệp **đang** đẩy hóa đơn sang MISA thì việc đó xảy ra **ngoài app này**
(app khác trên site, connector của MISA, hoặc nhập tay trên web MISA). **Cần người dùng xác nhận** — xem §C.0 câu 1.

### A.2 Field `vn_einvoice_number` — quy ước hiện hành

Field **không do app này ship** (không có thư mục `fixtures/`); mọi truy cập đều bọc
`frappe.db.has_column` → app coi đây là field có sẵn trên site, có thể vắng mặt.

App **chỉ ĐỌC, không bao giờ GHI** field này. Quy ước: *SI submitted mà `vn_einvoice_number` rỗng = **chưa xuất hóa đơn điện tử***.

| Nơi dùng | File:line | Hiển thị cho kế toán |
|---|---|---|
| Tab "Chưa xuất HĐĐT" (bàn NPP) | `ketoan/api/doitru.py:314-331` | danh sách HĐ chưa xuất + tổng tiền |
| Việc cần xử lý theo khách (360°) | `ketoan/api/receivables.py:439-445` | "Cần xuất hóa đơn điện tử: N hóa đơn" |
| Badge từng dòng sổ cái khách | `ketoan/api/receivables.py:590-633` | "Cần xuất HĐĐT" |
| Việc cần xử lý trang chủ | `ketoan/api/tasks.py:69,107` | "Cần xuất hóa đơn điện tử" |
| Trang Giám sát (KTT) | `ketoan/api/supervision.py` (gọi `get_missing_einvoice`) | chỉ số "Hàng đi chưa xuất HĐĐT" |
| Hướng dẫn nghiệp vụ NPP | `ketoan/public/ketoan/lib/workspaces.js:40` | mô tả quy ước cho kế toán |

**→ Quyết định thiết kế cần chốt (§C.0 câu 5).** Khuyến nghị: **hướng (a)** — `poll_pending`
sau khi lấy được số hóa đơn từ MISA thì ghi `custom_misa_inv_no` **và đồng bộ ngược** vào
`vn_einvoice_number` (chỉ khi field tồn tại và đang rỗng).
*Lợi*: 6 màn hình trên tự đúng, không phải sửa; thay việc điền tay hiện nay bằng tự động.
*Rủi ro*: ai đó điền tay số khác số MISA → phải cảnh báo lệch (bổ sung vào `check_amount_drift`).

### A.3 Điểm cắm module mới

| Hạng mục | Hiện trạng | Việc phải làm cho MISA |
|---|---|---|
| `ketoan/modules.txt` | 1 dòng: `Ketoan` | thêm dòng `MISA Integration` → thư mục `ketoan/misa_integration/` (**bắt buộc** có `__init__.py`) |
| `ketoan/hooks.py` | chỉ có `after_install`, `jinja`; ghi chú *"P0 read-only → KHÔNG doc_events"* | thêm `scheduler_events`, `doc_events` (Sales Invoice `before_submit`) |
| `fixtures` | **không có** thư mục `fixtures/`, hooks không khai `fixtures` | xem A.4 |
| `ketoan/patches.txt` | đủ 2 header; mới nhất `v0_0_5.sales_tax_price_perms` | patch mới đặt `ketoan/patches/v0_0_6/` |
| DocType mẫu | `ketoan/ketoan/doctype/ketoan_bank_map_rule/` (json + py) | dùng làm khuôn: `engine: InnoDB`, `field_order`, `permissions` **ship thẳng trong .json**, `module: Ketoan` → đổi thành `MISA Integration` |
| Guard | `ketoan/api/_guard.py` — 7 role portal, `CHIEF_ROLES = {Ke Toan Truong, Accounts Manager, System Manager}` | xem A.5 |
| `ketoan/install.py` | tạo Role + cấp quyền bằng `add_permission`/`update_permission_property`, idempotent | thêm role + custom field theo cùng cơ chế |

### A.4 Xung đột house-style với pack — fixtures

`hooks.py` ghi rõ: *"**KHÔNG ship DocPerm qua fixtures** (hash name, đổi giữa site) → cấp bằng
`add_permission` trong `after_install`"*. App **chưa từng** ship fixture nào.

Pack lại yêu cầu `fixtures/custom_field.json` + `fixtures/role.json` và chạy `bench export-fixtures`.

**Khuyến nghị (nhất quán với app, và container không có bench để export):**

| Đối tượng | Pack | Đề xuất cho app này |
|---|---|---|
| Role `MISA Reconciler` | `fixtures/role.json` | tạo trong `install.py` (giống `create_portal_roles`) + patch `v0_0_6` |
| Custom Field `custom_misa_*` | `fixtures/custom_field.json` | `frappe.custom.doctype.custom_field.custom_field.create_custom_fields()` trong `install.py` + patch — idempotent, không cần export từ site |
| DocPerm của 3 DocType mới | fixtures | ship thẳng trong `.json` của DocType (đúng như `ketoan_bank_map_rule.json` đang làm) |

### A.5 Guard — tái dùng thay vì viết mới

Pack đề xuất `_guard()` dùng `frappe.has_role("Accounts Manager")`. App đã có hệ guard riêng
(`ketoan/api/_guard.py`), trong đó `CHIEF_ROLES` **đã gồm** `Accounts Manager` và `System Manager`.

**Đề xuất**: thêm vào `_guard.py`:
```python
ROLE_MISA = "MISA Reconciler"

def guard_misa() -> None:
    """Đối soát MISA: kế toán trưởng, kế toán hạch toán, hoặc MISA Reconciler."""
    _throw_login()
    if not (is_chief() or has_role(ROLE_GL) or ROLE_MISA in _roles()):
        frappe.throw(_("Không có quyền truy cập đối soát MISA"), frappe.PermissionError)
```
Mọi whitelisted method trong `misa_desk.py` gọi `guard_misa()` ở **dòng đầu** (đúng house style).

---

## B. Endpoint theo tài liệu MISA (CHƯA kiểm chứng bằng gọi thật)

> Nguồn: coder pack do người dùng cung cấp. **Chưa gọi được lần nào** từ môi trường này (§D.3).
> Mọi dòng dưới đây phải được xác nhận lại bằng response thật trước khi code map field.

### B.1 Bộ Open API chính thức — `https://api.meinvoice.vn/api/v3` (test: `testapi.meinvoice.vn`)

| Mục | Giá trị |
|---|---|
| Header | `Content-Type: application/json`, `Authorization: Bearer <token>`, `CompanyTaxCode: <MST>` |
| Token | `POST /api/integration/auth/token` — body `{appid, taxcode, username, password}` |
| Wrapper | `{"Success": bool, "Data": "<chuỗi JSON lồng>", "ErrorCode": str, "Errors": []}` |
| Trạng thái HĐ | `POST /api/v3/itg/invoicepublished/invoicestatus` — body = list mã tra cứu |
| Batch tối đa | **50 mã / request** |
| Field trả về | `TransactionID`, `PublishStatus`, `ReferenceType`, `InvoiceCode`, `SendTaxStatus`, `IsSentEmail`, `IsDelete`, `DeletedDate`, `DeletedReason`, `ReceivedStatus` |

⚠ `Data` là **chuỗi JSON lồng**; tài liệu MISA có ví dụ trả nhiều bản ghi mà **thiếu `[]` bao ngoài**
→ `parse_nested_data()` phải parse phòng thủ, bọc `[]` khi cần, `log_error` thay vì raise.

### B.2 Bộ web app — `https://app.meinvoice.vn/api/v2` (KHÔNG cần AppID)

| Mục | Giá trị |
|---|---|
| Token | `POST /api/v2/oauth` — header `taxcode`, body **form** `grant_type=password&username=&password=` |
| HĐ sau phát hành | `GET v3sainvoice/afterpublishing/{refID}` · bản có mã: `GET code/v3sainvoice/afterpublishing/{refID}` |
| Danh sách HĐ | `GET\|POST v3sainvoice/paging` — `start, length, sort, fromDate, toDate, publishStatus, sendToTaxStatus, invoiceStatus, paymentStatus, searchKey` |
| Bảng kê đã sử dụng | `POST v3report/ipusedamount/paging` |
| Tài nguyên còn lại | `GET resource/GetTotalUsedInvoiceQuantityByInvTemplate?invTemplateNo=&invSeries=` |

⚠ Màn hình "Hóa đơn" trên MISA **chỉ hiện** hóa đơn lập trực tiếp trên meInvoice; hóa đơn đẩy từ
phần mềm tích hợp **chỉ lên ở Báo cáo → Bảng kê** → `v3report/ipusedamount/paging` là nguồn **duy nhất**
thấy được toàn bộ.

⚠ Tên field **không nhất quán giữa hai bộ API** (chỗ `InvNo`, chỗ `InvoiceNumber`) — cấm map theo trí nhớ.

---

## C. CẦN NGƯỜI DÙNG CUNG CẤP (gate của Phase 0)

### C.0 Câu hỏi chốt (trả lời ngắn là đủ)

| # | Câu hỏi | Vì sao cần |
|---|---|---|
| 1 | Hiện hóa đơn được đẩy sang MISA bằng cách nào? (app khác trên site / connector MISA / nhập tay hoàn toàn) | quyết định có phải build luôn phần **đẩy**, hay chỉ build **poll + đối soát** |
| 2 | **U7** — đã đăng ký tích hợp và có **AppID** chưa? | có → dùng được bộ official (§B.1); chưa → chỉ dùng bộ web app, thiết kế client để cắm official sau |
| 3 | **U4** — công ty dùng hóa đơn **có mã CQT** hay **không mã**? | quyết định route `code/v3sainvoice/...` hay `v3sainvoice/...` |
| 4 | MST công ty + danh sách **ký hiệu hóa đơn** đang dùng (vd `1C26MHG`) | tham số bắt buộc mọi request + `detect_number_gaps` chạy theo từng ký hiệu |
| 5 | Chốt hướng xử lý `vn_einvoice_number` (§A.2): **(a)** đồng bộ ngược ↔ **(b)** giữ 2 field độc lập | ảnh hưởng 6 màn hình đang chạy |
| 6 | **U6** — callback MISA có bắn khi phát hành **thủ công trên web** không? (hỏi bộ phận tích hợp MISA) | có → giảm tần suất poll; không → giữ cron 30 phút |
| 7 | Site đích để chạy: `test.rongvanghoanggia.com` trước rồi mới `a.rongvanghoanggia.com`? | thứ tự triển khai |

### C.1 Dữ liệu mẫu cần lấy từ DevTools (U2, U3, U5)

Cách lấy: đăng nhập `app.meinvoice.vn` → **F12** → tab **Network** → lọc `Fetch/XHR` → thao tác
tương ứng → click request → copy **Request Headers**, **Payload**, **Response**.
**Redact** trước khi dán: MST → `0100XXXXXX`, tên khách → `KH-A`, số tiền có thể giữ.

| # | Thao tác trên MISA | Cần copy |
|---|---|---|
| U2 | Báo cáo → **Bảng kê hóa đơn đã sử dụng** → chọn 1 tháng → xem | request `v3report/ipusedamount/paging`: URL đầy đủ, headers, payload, **response 2–3 bản ghi** |
| U3 | Mở **1 hóa đơn đã phát hành** (xem chi tiết) | request `v3sainvoice/afterpublishing/{refID}` (hoặc `code/...`): response đầy đủ **1 hóa đơn** |
| U5 | Bất kỳ request nào ở trên | **toàn bộ** Request Headers (để biết ngoài `Authorization` còn cần `taxcode`, `companyid`, `x-…` gì) |
| — | Đăng nhập lại (đăng xuất rồi vào lại) | request `oauth`: dạng body form + response token (che token) |

### C.2 Bảng cần điền sau khi có dữ liệu thật

**(1) Map field** — điền khi có response U2/U3:

| Field MISA (tên **thật**) | Nguồn (endpoint) | → fieldname ERPNext | Kiểu | Ghi chú |
|---|---|---|---|---|
| _(chờ)_ | | `custom_misa_inv_no` | Data | |
| _(chờ)_ | | `custom_misa_inv_series` | Data | |
| _(chờ)_ | | `custom_misa_inv_date` | Date | định dạng ngày MISA trả? |
| _(chờ)_ | | `custom_misa_transaction_id` | Data | |
| _(chờ)_ | | `custom_misa_invoice_code` | Data | |
| _(chờ)_ | | `MISA Invoice Snapshot.total_amount` | Currency | |
| _(chờ)_ | | `.amount_before_vat` | Currency | |
| _(chờ)_ | | `.vat_amount` | Currency | |
| _(chờ)_ | | `.buyer_tax_code` | Data | |

**(2) Enum thật** — quan sát từ dữ liệu, **không suy diễn**:

| Enum | Giá trị quan sát được | Ý nghĩa |
|---|---|---|
| `PublishStatus` | _(chờ)_ | |
| `SendTaxStatus` | _(chờ)_ | |
| `ReferenceType` | _(chờ)_ | pack giả định 0 gốc / 1 thay thế / 2 điều chỉnh — **phải xác nhận** |
| `invoiceStatus` | _(chờ)_ | |

---

## D. Môi trường thi công (ĐÃ ĐO THẬT trong container)

| # | Hạng mục | Kết quả |
|---|---|---|
| D.1 | `bench`, `~/frappe-bench`, `import frappe` | **KHÔNG có** — container chỉ chứa source app |
| D.2 | Python | 3.11.15 · `requests` 2.33.1 có sẵn |
| D.3 | Mạng tới MISA | **BỊ CHẶN** — `api.meinvoice.vn`, `testapi.meinvoice.vn`, `app.meinvoice.vn` đều trả `000`; proxy log: `gateway answered 403 to CONNECT (policy denial)` |
| D.4 | `references/validate_shipped_docs.py` | **KHÔNG tồn tại** trên máy |
| D.5 | Git | nhánh `claude/zen-babbage-0vj0eg`, cây sạch |

### Việc chia theo nơi thực hiện

| Claude làm được trong container | Người dùng phải làm (site thật / trình duyệt) |
|---|---|
| Viết DocType JSON + controller, `misa_client.py`, `misa_sync.py`, `misa_reconcile.py`, `misa_desk.py`, Report, patch | Lấy response mẫu MISA từ DevTools (§C.1) |
| Kiểm tra cú pháp: `py_compile`, `node --check`, parse JSON, kiểm `__init__.py` | `bench migrate`, `bench build`, `bench restart` |
| Viết unit test logic thuần (matching, normalize, gap detection) chạy không cần frappe | Nhập credential vào **MISA Settings** (fieldtype Password) |
| Commit / push theo nhánh | Gọi thử API thật, verify tay 5 hóa đơn |

### Thay thế gate validator (D.4)

`references/validate_shipped_docs.py` không có → Phase 1 dùng bộ kiểm tra hiện hành của app:

```bash
python3 -m py_compile $(find ketoan -name "*.py")           # cú pháp Python
python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('ketoan/**/*.json',recursive=True)]"
while read -r m; do d=$(echo "$m" | tr 'A-Z ' 'a-z_'); \
  [ -f "ketoan/$d/__init__.py" ] || echo "THIẾU: ketoan/$d/__init__.py"; done < ketoan/modules.txt
python3 -c "import configparser;c=configparser.ConfigParser(allow_no_value=True,delimiters=('\t',));\
  c.read_string(open('ketoan/patches.txt').read());assert {'pre_model_sync','post_model_sync'}<=set(c.sections())"
```

---

## E. Rủi ro đã nhận diện (đọc code thật)

| # | Rủi ro | Mức | Xử lý đề xuất |
|---|---|---|---|
| E1 | Pack ship Role/Custom Field qua fixtures — trái house style app, và container không có bench để `export-fixtures` | **cao** | dùng `install.py` + patch `v0_0_6` (§A.4) |
| E2 | `before_submit` sinh `ref_id` sẽ chạy cho **cả SI trả hàng** (`is_return=1`) do `doitru.create_return` tạo | **cao** | loại trừ `is_return` khỏi luồng đẩy MISA, hoặc gắn cờ riêng — hóa đơn trả về có quy trình HĐĐT khác |
| E3 | Cron 30 phút + job kéo bảng kê 1 tháng chạy trên site production | vừa | bắt buộc `frappe.enqueue(queue="long", timeout=1800)`; kiểm `enable_auto_sync` ở dòng đầu mọi `scheduled_*`; xác nhận scheduler của site đang bật |
| E4 | Ghi đè `vn_einvoice_number` nếu kế toán đã điền tay số khác | vừa | chỉ ghi khi đang rỗng; khác số → set `custom_misa_status='Lệch tiền'`/tạo ToDo, **không** ghi đè |
| E5 | Module mới `MISA Integration` trùng tiền tố file với `ketoan/api/misa_*.py` | thấp | giữ đúng layout pack: DocType trong `ketoan/misa_integration/`, logic trong `ketoan/api/misa_*.py` |
| E6 | Credential lọt vào `error_log` | **cao** | `misa_client` không log body của request token; `MISAError` chỉ mang `code`/`message` đã lọc |
| E7 | App có `si.save()` trên SI đã submit? | — | **đã kiểm: không có** (app chỉ dùng `db_set` / `doc.submit()`) |

---

## F. Kết luận Phase 0

- ✅ **U1 đã trả lời**: app chưa có tích hợp MISA nào — build mới hoàn toàn, không sợ trùng/ghi đè.
- ✅ Điểm cắm, house style, guard, patch chain, khuôn DocType: đã xác định (§A.3–A.5).
- ✅ Môi trường: đã đo, biết rõ việc nào làm được ở đâu (§D).
- ❌ **U2, U3, U5 (payload/response thật)**: chưa lấy được — container bị chặn mạng tới MISA.
- ❌ **U4, U6, U7** + 4 câu hỏi thiết kế: chờ người dùng trả lời (§C.0).

**Chưa mở gate sang Phase 1.** Theo đúng ràng buộc của pack (mục 13.5): *không đoán tên field
response — chưa có trong contract thì chưa code.*

**Có thể làm ngay mà không cần chờ MISA** (nếu người dùng muốn chạy song song): Phase 1 —
DocType `MISA Settings` / `MISA Invoice Snapshot` / `MISA Sync Run`, custom field `custom_misa_*`,
role + patch. Ba thứ này chỉ phụ thuộc quyết định §C.0 câu 2/5, **không** phụ thuộc tên field response.
