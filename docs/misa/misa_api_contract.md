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

---

## G. Phase 1 — ĐÃ THI CÔNG (17/08/2026)

Người dùng duyệt gate Phase 0. Phase 1 dựng xong phần **không phụ thuộc tên field response
của MISA**. Giả định đang áp dụng (đổi được, chưa có code nào khóa cứng):

| Câu hỏi §C.0 | Giả định tạm | Đổi ý thì phải sửa gì |
|---|---|---|
| 2 — có AppID chưa | `MISA Settings.appid` **để trống được**; `has_appid()` quyết định có dùng bộ official hay không | không sửa gì, chỉ điền field |
| 3/U4 — hóa đơn có mã CQT | thêm cờ `MISA Settings.use_code_route` (mặc định **tắt** = không mã) | không sửa gì, chỉ tick |
| 4 — ký hiệu hóa đơn | thêm field `inv_series_list` (mỗi dòng 1 ký hiệu) phục vụ `detect_number_gaps` | không sửa gì, chỉ điền |
| 5 — `vn_einvoice_number` | chọn **hướng (a) đồng bộ ngược**; nhưng code ghi ngược nằm ở Phase 3 | đổi sang (b) trước Phase 3 là không tốn gì |

### G.1 Đã ship

- Module mới **`MISA Integration`** (`ketoan/misa_integration/`), thêm vào `modules.txt`.
- 3 DocType: `MISA Settings` (Single) · `MISA Invoice Snapshot` (autoname hash) · `MISA Sync Run`
  (naming series `MISA-SYNC-.YYYY.-`).
- 12 custom field `custom_misa_*` trên Sales Invoice — fieldname ASCII, label tiếng Việt,
  9 field ghi-sau-submit đều `allow_on_submit=1`, `custom_misa_ref_id` cố ý `allow_on_submit=0`.
- Role `MISA Reconciler` + quyền 3 DocType cho Kế toán trưởng và role mới.
- Patch `v0_0_6.misa_integration_setup` (post_model_sync), idempotent.

### G.2 Lệch so với pack — có chủ ý

| Pack yêu cầu | Làm thực tế | Lý do |
|---|---|---|
| Ship Custom Field + Role qua `fixtures/` (§10) | `install.py` + patch `v0_0_6`, dùng `create_custom_fields` / `add_permission` | rủi ro **E1**: trái quy ước app (`hooks.py` ghi rõ *KHÔNG ship DocPerm qua fixtures*), và container không có bench để `export-fixtures` — pack cấm viết fixtures tay |
| `references/validate_shipped_docs.py` (§11) | bộ kiểm tra ở §D.7 + validator DocType JSON viết riêng | file đó không tồn tại trên máy (D.4) |
| `MISA Settings` chỉ Accounts Manager (§9) | thêm **Ke Toan Truong** read+write | trong app này Kế toán trưởng mới là vai chief (`_guard.CHIEF_ROLES`) |

### G.3 Field thêm ngoài spec

`use_code_route` (U4) và `inv_series_list` (Q4) — đều là **cấu hình**, không phải tên field
response đoán mò, nên không vi phạm ràng buộc 13.5.

### G.4 Chưa làm (đúng gate)

`misa_client.py`, `misa_sync.py`, `misa_reconcile.py`, `misa_desk.py`, `scheduler_events`,
`doc_events` → **Phase 2 trở đi, chờ payload/response thật (§C.1)**.

---

## H. Dữ liệu thật đợt 1 — endpoint danh sách hóa đơn (17/08/2026)

Nguồn: DevTools trên `app.meinvoice.vn`, màn hình **danh sách hóa đơn**. Người dùng báo có
**2 request cùng tên `list`** — chúng chia việc:

| Request | Trả về | Ghi chú |
|---|---|---|
| `list` (A) — dữ liệu | `data` = **chuỗi JSON** chứa mảng 30 bản ghi | `recordsTotal` = **0** |
| `list` (B) — đếm | `data` = `""` | `recordsTotal` = `recordsFiltered` = **968** |

> ⚠️ **Bẫy phân trang**: response chứa dữ liệu KHÔNG mang tổng số. Vòng lặp phân trang phải
> dừng khi **mảng rỗng**, tuyệt đối không dựa vào `recordsTotal` của response A.

### H.1 Wrapper — CHỮ THƯỜNG, khác tài liệu bộ official

```json
{"SerializeConfig": null, "data": "<CHUỖI JSON>", "summary": null, "newdata": "",
 "dataError": null, "success": true, "recordsTotal": 0, "recordsFiltered": 0,
 "content": null, "error": null, "dataAdditional": null, "errorCode": [], "resultToken": null}
```

Bộ official (§B.1) tài liệu ghi `{Success, Data, ErrorCode, Errors}` — **viết hoa**. Bộ web app
dùng `{success, data, errorCode, error}` — **viết thường**. `misa_client` phải đọc được cả hai
(tra key không phân biệt hoa thường), không hardcode một kiểu.

`data` là **chuỗi JSON lồng** → xác nhận cảnh báo của pack: phải `json.loads` hai lần, và parse
phòng thủ (log_error thay vì raise khi hỏng).

### H.2 Field map — ĐÃ XÁC MINH trên 30 bản ghi thật

| Field MISA | Kiểu | Mẫu | → ERPNext | Ghi chú |
|---|---|---|---|---|
| `RefID` | str | `9ff87316-257a-4cc2-b25b-dfd049cf8ac6` | `snapshot.ref_id` | GUID **của MISA** — xem H.5 |
| `InvSeries` | str | `1C26THG` | `snapshot.inv_series` | ký hiệu thật đang dùng |
| `InvNo` | str | `00007140` | `snapshot.inv_no` | **8 chữ số**, zero-pad → `inv_no_norm` = `7140` |
| `InvDate` | str | `2026-08-17T00:00:00` | `snapshot.inv_date` | ISO datetime → cắt 10 ký tự đầu |
| `TransactionID` | str | `GJF2I1_8DELM` | `snapshot.transaction_id` | 12 ký tự, có `_` |
| `InvoiceCode` | str | 34 ký tự HEX | `snapshot.invoice_code` | **mã CQT** — xem H.4 |
| `AccountObjectTaxCode` | str | `0301175691-044` | `snapshot.buyer_tax_code` | 10 / 12 / 14 ký tự |
| `AccountObjectName` | str | | `snapshot.buyer_name` | |
| `TotalAmount` | float | `22026600.000000` | `snapshot.total_amount` | **có giá trị ÂM** |
| `TotalAmountOC` | float | | — | bằng `TotalAmount` ở cả 30 dòng (VND) |
| `PublishStatus` | int | `3` | `snapshot.publish_status` | |
| `SendToTaxStatus` | int | `2` | `snapshot.send_tax_status` | |
| `EInvoiceStatus` | int | `1/3/4/7` | *(chưa có field)* | **quan trọng** — xem H.6 |
| `SendInvoiceStatus` | int | `3/4` | *(chưa có field)* | gửi mail cho khách, không phải gửi CQT |
| `CurrencyCode` | str | `VND` | — | |
| `ContactName` | str | | — | tên điểm giao / mã PO |
| `ReceiverEmail` | str | | — | **VẮNG MẶT ở 2/30 dòng** |
| `OrganizationUnitID` | str | GUID | — | 1 giá trị duy nhất = đơn vị phát hành |
| `InvoiceType` `PaymentStatus` `BusinessArea` `SortOrder` | int | `1` `0` `0` `0` | — | hằng số ở mẫu này |
| `ApproveStep` | int | `-3` | — | hằng số ở mẫu này |
| `EditVersion` | int | `4/6/7/10` | — | số lần sửa |
| `IsTemplatePetrol` `IsTradeDiscountInvoice` | bool | `false` | — | |
| `AccountObjectCode` `ListNo` | str | `""` | — | rỗng toàn bộ |

**KHÔNG có trong endpoint này**: `TotalAmountWithoutVAT`, `TotalVATAmount`,
`TotalVATAmountOC`, `TotalVATAmountView`, `TotalVATAmountViewOC` — có mặt nhưng **bằng `0.0` ở
cả 30 dòng**, tức là endpoint danh sách không trả tách thuế.

> ⚠️ Hệ quả: **so tiền 3 vế** (trước thuế / thuế / tổng) mà pack §6.3 bắt buộc **không thực hiện
> được** từ endpoint này. Chỉ so được `total_amount`. Muốn đủ 3 vế phải lấy được response của
> `afterpublishing/{refID}` (U3, chưa có).

### H.3 Định dạng đã đo

| Thứ | Kết quả đo trên 30 dòng |
|---|---|
| `InvNo` | luôn 8 chữ số, toàn số. Dải 7111–7140 **liên tục, không thiếu số** |
| `InvoiceCode` | luôn 34 ký tự, `[0-9A-F]`, không dòng nào rỗng |
| `AccountObjectTaxCode` | độ dài 10 / 12 / 14. 12 số = hộ KD, cá nhân. 14 = MST + đuôi chi nhánh |
| đuôi chi nhánh quan sát được | `-001` `-005` `-031` `-044` |
| số bản ghi 1 trang | **30** (mặc định của web app) |
| khóa tự nhiên `(InvSeries, inv_no_norm)` | **duy nhất** trên toàn mẫu ✅ |

Hàm `norm_inv_no` / `norm_series` của Phase 1 đã test lại trên 30 bản ghi thật: **đúng 30/30**.

### H.4 U4 ĐÃ TRẢ LỜI — hóa đơn **CÓ MÃ** cơ quan thuế

`InvoiceCode` có giá trị 34 ký tự hex ở **cả 30/30 dòng**, không dòng nào rỗng.

⇒ `MISA Settings.use_code_route` phải **BẬT**. Mọi route hóa đơn dùng tiền tố `code/`:
`GET code/v3sainvoice/afterpublishing/{refID}`.

### H.5 RefID — giả định của pack cần điều chỉnh

Pack §7 giả định **ERPNext sinh `uuid4()`** rồi gửi kèm khi đẩy, nên tầng match 1 dựa vào
`snapshot.ref_id == si.custom_misa_ref_id`. Nhưng dữ liệu thật cho thấy **mọi hóa đơn đã có
RefID dạng GUID do MISA quản lý**.

⇒ Với **toàn bộ hóa đơn hiện có**, tầng match 1 sẽ **không bao giờ trúng**. Đối soát dữ liệu cũ
phải dựa **tầng 3 (ký hiệu + số hóa đơn)** — mà H.3 đã chứng minh khóa này duy nhất, nên tầng 3
đủ mạnh. Tầng 1 chỉ có nghĩa cho hóa đơn ERPNext đẩy sang **sau khi** dựng luồng đẩy.

Câu §C.0-1 (hiện đẩy sang MISA bằng cách nào) vì thế vẫn cần trả lời.

### H.6 Enum — giá trị quan sát được, **ý nghĩa CHƯA xác nhận**

| Enum | Giá trị (số dòng) | Suy đoán — **chưa dùng để code** |
|---|---|---|
| `PublishStatus` | `3` (30/30) | mẫu chỉ lọc hóa đơn đã phát hành nên không thấy giá trị khác |
| `SendToTaxStatus` | `2` (30/30) | như trên |
| `SendInvoiceStatus` | `3` (17), `4` (13) | trạng thái gửi mail cho khách |
| `EInvoiceStatus` | `1` (27), `3` (1), `4` (1), `7` (1) | **cần xác nhận gấp** |
| `InvoiceType` | `1` (30/30) | |

3 dòng có `EInvoiceStatus` khác `1`:

| Số HĐ | EInvoiceStatus | Tiền | Nghi ngờ |
|---|---|---|---|
| 00007131 | 3 | +106.951.590 | bị thay thế? bị điều chỉnh? |
| 00007126 | 4 | **−786.240** | hóa đơn điều chỉnh giảm / trả hàng |
| 00007119 | 7 | +107.566.650 | ? |

⚠️ Ba trạng thái này quyết định `match_status` = `Đã hủy` / `Đã thay thế`. **Sai ở đây là sai báo
cáo thuế** — không suy diễn, phải đối chiếu bằng mắt trên MISA (xem I.2).

### H.7 Hệ quả kỹ thuật bắt buộc

1. **Đọc field phải dùng `.get()`** — `ReceiverEmail` vắng mặt ở 2/30 dòng, index trực tiếp là `KeyError`.
2. **Tiền có thể ÂM** — mọi so sánh tiền phải xử dấu; nhiều khả năng khớp với `Sales Invoice.is_return=1` bên ERPNext.
3. **Phân trang dừng theo mảng rỗng**, không theo `recordsTotal` (H).
4. **Wrapper tra key không phân biệt hoa/thường** (H.1).
5. **So MST theo 2 vòng**: khớp đủ chuỗi trước (`0301175691-044`); chỉ strip đuôi chi nhánh ở vòng ngoài — mẫu đã có 4 chi nhánh khác nhau, strip sớm là nhập nhằng.

---

## I. Còn thiếu để mở Phase 2

### I.1 Phần request của chính 2 cái `list` này

Đã có response, **chưa có** phần gửi lên — mà không có nó thì không gọi được API:

| Cần | Lấy ở đâu |
|---|---|
| **Request URL** đầy đủ | DevTools → click request → tab **Headers** → dòng `Request URL` |
| **Request Headers** | chuột phải request → **Copy request headers** (che `Authorization`, `Cookie`) |
| **Payload** | tab **Payload** → chuột phải → **Copy value** |

Payload quan trọng nhất: tên tham số phân trang (`start`/`length`? `page`/`pageSize`?) và tham
số lọc ngày (`fromDate`/`toDate`?). Chưa biết thì không kéo được theo tháng.

### I.2 Ý nghĩa `EInvoiceStatus` (H.6)

Cách xác nhận nhanh, không cần DevTools: trên MISA mở 3 hóa đơn **00007131**, **00007126**,
**00007119**, xem cột/nhãn trạng thái hiển thị là gì → ghi lại.

### I.3 Response `afterpublishing/{refID}` (U3)

Cần để có tách thuế (trước thuế / thuế / tổng). Thiếu thì `check_amount_drift` chỉ so được tổng —
đúng cảnh báo của pack: *lệch thuế suất mà tổng vẫn trùng là tình huống có thật*.

### I.4 Request `oauth` (U5)

Chưa biết lấy token thế nào và token sống bao lâu (`expires_in`).

---

**Gate Phase 2 vẫn ĐÓNG.** Có H.2 là biết đọc response, nhưng chưa biết **gọi** — thiếu I.1.

---

## J. Request thật của endpoint danh sách (17/08/2026)

> Cookie và `__RequestVerificationToken` do người dùng gửi **KHÔNG được lưu ở đây** và không
> commit vào repo. Chỉ ghi lại cấu trúc.

### J.1 Định danh endpoint

| | |
|---|---|
| Method | `POST` |
| URL | `https://app3.meinvoice.vn/v3/sainvoicewithcode/list` |
| Content-Type | **`application/x-www-form-urlencoded; charset=UTF-8`** |

Ba điểm khác hẳn giả định ban đầu (§B.2):

1. Host là **`app3.meinvoice.vn`**, không phải `app.meinvoice.vn`. `MISA Settings.base_url_webapp`
   mặc định đang **sai**, phải đổi.
2. Path là **`sainvoicewithcode`** — lần thứ hai xác nhận **hóa đơn CÓ MÃ CQT** (§H.4).
3. Body là **form-urlencoded**, **không phải JSON**. `misa_client.call_webapp` phải gửi `data=`
   chứ không `json=`.

### J.2 Header cần thiết

| Header | Giá trị | Vai trò |
|---|---|---|
| `CompanyTaxCode` | MST công ty | = `MISA Settings.taxcode` |
| `Content-Type` | `application/x-www-form-urlencoded; charset=UTF-8` | bắt buộc |
| `X-Requested-With` | `XMLHttpRequest` | ASP.NET phân biệt AJAX |
| `__RequestVerificationToken` | token chống CSRF | **phải khớp cookie cùng tên** |
| `__InvType` | `5` | loại hóa đơn của màn hình |
| `__SysVersion` | `41` | phiên bản hệ thống |
| `Origin` / `Referer` | `https://app3.meinvoice.vn` / `.../v3/hoa-don` | Cloudflare kiểm |
| `Cookie` | phiên đăng nhập | **xem J.4** |

### J.3 Payload — form-urlencoded

| Tham số | Giá trị mẫu | Ghi chú |
|---|---|---|
| `start` | `0` | **offset phân trang** |
| `length` | `30` | **kích thước trang** |
| `pagingType` | `0` | |
| `draw` | `2` | bộ đếm kiểu DataTables, gửi số tăng dần là được |
| `fromDate` | `"2026-07-19T00:00:00.000Z"` | ⚠️ giá trị **có kèm dấu nháy kép** trong chuỗi |
| `toDate` | `"2026-08-17T23:59:59.000Z"` | như trên |
| `publishStatus` | `6` | ⚠️ **xem J.5** |
| `sendEmailStatus` `sendToTaxStatus` | `-1` | −1 = tất cả |
| `filterInvoiceStatus` | `0` | |
| `invoiceSummaryStatus` | `-2` | |
| `searchField` | `AccountObjectCode,AccountObjectName` | |
| `gridSort` | ``​`PublishStatus` ASC,`InvDate` DESC, `InvNo` DESC, `SortOrder` ASC`` | sắp xếp, dùng dấu backtick |
| `columns` | 33 tên cột, ngăn bằng dấu phẩy | **xem J.6 — quan trọng** |
| `filter` | mảng JSON điều kiện lọc | trùng nghĩa với `publishStatus` |
| `searchKey` `keyValue` `buyerSignature` `filterPaymentStatus` `lstOrganizationUnit` `invTemplate` `approveSteps` `sort` | rỗng | |
| `filterCustomField` | `false` | |

⇒ Phân trang: **`start` + `length`**, đúng như pack dự đoán. Kéo cả tháng = tăng `start` thêm
`length` mỗi vòng, **dừng khi mảng rỗng** (§H).

### J.4 🚨 XÁC THỰC — không có Bearer token

**Không có header `Authorization` nào.** Bộ web app này xác thực bằng:

1. **Cookie phiên ASP.NET** (`ASP.NET_SessionId`, `_mstoken`, `TaxCode`, `LastUserID`…)
2. **Anti-forgery double-submit**: `__RequestVerificationToken` phải có **đồng thời** ở header
   và ở cookie, và hai giá trị phải là một cặp hợp lệ do server phát.
3. **`cf_clearance` — cookie của Cloudflare**, chỉ cấp sau khi vượt kiểm tra trình duyệt.

Điều này **phủ định giả định §B.2** rằng có `POST /api/v2/oauth` trả bearer token. Hệ quả:

| Hệ quả | Mức |
|---|---|
| `misa_client.get_token(scope="webapp")` theo thiết kế pack **không áp dụng được** | **cao** |
| Muốn tự động hóa phải: login bằng form → giữ cookie jar → bóc `__RequestVerificationToken` từ HTML → kèm vào mọi request | **cao** |
| `cf_clearance` gắn với User-Agent + IP + JA3 của trình duyệt thật. Server Frappe gọi bằng `requests` **rất dễ bị Cloudflare chặn**, và chặn lúc nào là ngoài tầm kiểm soát | **rất cao** |
| Phiên hết hạn / MISA đổi `__SysVersion` là luồng chết im lặng | **cao** |

Đây đúng là điều pack cảnh báo ở ràng buộc 13.7 — *"bộ web app không ổn định, phải cô lập"* —
nhưng thực tế còn nặng hơn: **không chỉ không ổn định mà có thể không tự động hóa được**.

### J.5 Bẫy: `publishStatus` lúc lọc ≠ `PublishStatus` trong bản ghi

Request lọc `publishStatus=6`, `DisplayText` là `"Phát hành"`. Nhưng **30/30 bản ghi trả về mang
`PublishStatus: 3`**.

⇒ Giá trị enum dùng để **lọc** và giá trị enum trong **dữ liệu** là hai bảng mã khác nhau. Cấm
lấy `6` đem so với field `publish_status` của snapshot. Chưa xác minh được bảng mã nào là nào →
chưa code phần này.

### J.6 `columns` do client quyết định — cơ hội gỡ nút thắt tách thuế

`columns` là **tham số gửi lên**, liệt kê đúng các cột lưới đang hiển thị. Ngoài 33 cột ở mẫu,
response còn kèm sẵn `TotalAmountWithoutVAT`, `TotalVATAmount`, `TotalVATAmountOC`,
`TotalVATAmountView`, `TotalVATAmountViewOC` nhưng **đều bằng 0.0** — vì chúng **không nằm trong
`columns`**.

**Giả thuyết**: thêm `TotalAmountWithoutVAT` và `TotalVATAmount` vào `columns` thì server sẽ trả
giá trị thật ⇒ **so tiền 3 vế làm được ngay từ endpoint danh sách**, không cần
`afterpublishing/{refID}`.

Cách kiểm chứng **không cần lập trình**: trên lưới hóa đơn của MISA, mở phần **chọn cột hiển
thị**, tick thêm **"Tiền chưa thuế"** và **"Tiền thuế"**, rồi bấm tìm kiếm lại và chụp lại
response. Nếu hai field đó có số → giả thuyết đúng.

Cột đáng chú ý khác đã lộ tên qua `columns` (chưa thấy giá trị): `BuyerSignatureStatus`,
`SendExplanationStatus`, `CustomData`, `ListDate`, `ReceiverMobile`.

### J.7 Khuyến nghị kiến trúc — cần người dùng chốt

Vì J.4, có ba hướng:

| Hướng | Được | Mất |
|---|---|---|
| **(A) Đăng ký AppID, dùng Open API chính thức** `api.meinvoice.vn/api/v3` | bearer token, có tài liệu, ổn định, không đụng Cloudflare | phải làm thủ tục với MISA |
| **(B) Tự động hóa bộ web app bằng cookie jar** | làm được ngay, không cần xin gì | Cloudflare chặn lúc nào không biết; mỗi lần MISA đổi `__SysVersion`/anti-forgery là chết; phải giữ mật khẩu để tự đăng nhập lại |
| **(C) Nhập khẩu thủ công** — kế toán xuất Excel/CSV từ MISA rồi tải lên portal, hệ thống upsert snapshot + đối soát | không phụ thuộc API, chạy được ngay, rủi ro bằng 0 | mỗi kỳ tốn 2 phút thao tác tay |

**Đề xuất: (A) là đích, (C) là cầu tạm.** (C) dùng lại nguyên vẹn `MISA Invoice Snapshot` và toàn
bộ tầng đối soát của Phase 5–6 — khi có AppID thì chỉ thay tầng nạp dữ liệu, không phải viết lại.
(B) chỉ nên làm nếu chấp nhận nó sẽ hỏng.

**Gate Phase 2 vẫn ĐÓNG** — chờ chốt hướng ở J.7.
