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

---

## K. ĐÍNH CHÍNH U1 (17/08/2026) — có luồng đẩy đang chạy

Người dùng xác nhận: **hóa đơn đang được đẩy từ ERPNext sang MISA bằng một `Client Script` trên
Sales Invoice.**

Kết luận U1 ở §A.1 **đúng nhưng không đủ**: khảo sát quét *code trong app* (`grep` trên
`ketoan/`), mà `Client Script` và `Server Script` là **bản ghi trong database của site**, không
phải file trong app. Chúng không thể xuất hiện trong bất kỳ lần grep nào.

⇒ Bài học cho mọi khảo sát sau: "app không có" **≠** "site không có". Phải kiểm thêm
`Client Script`, `Server Script`, `Custom Field`, `Property Setter`, `Webhook`, `Scheduled Job Type`
— tất cả đều là dữ liệu, không phải file.

### K.1 Điều này giải thích được

- **`vn_einvoice_number`**: §A.2 ghi nhận app chỉ ĐỌC, không bao giờ GHI, và không do app này
  ship. Giờ rõ: **Client Script kia là bên ghi**. 6 màn hình đang đọc field đó thực chất đang
  đọc kết quả của luồng đẩy hiện hành.
- **`RefID` dạng GUID** (§H.5): có thể do chính Client Script sinh và gửi kèm, chứ không hẳn
  của MISA. Nếu đúng thì tầng khớp theo `ref_id` **dùng được cho cả dữ liệu cũ** — tốt hơn nhiều
  so với đánh giá ở §H.5.
- **Xác thực** (§J.4): Client Script chạy **trong trình duyệt của kế toán**, nơi đã sẵn cookie
  phiên MISA. Đó là lý do luồng hiện tại không cần bearer token. Nhưng cũng có nghĩa là nó
  **chỉ chạy khi có người mở trình duyệt** — không thể chạy theo lịch.

### K.2 Cần đọc script đó trước khi viết bất cứ dòng nào

Đây giờ là hiện vật quan trọng nhất, quan trọng hơn mọi capture còn lại. Nó trả lời một lượt:

| Câu hỏi | Vì sao cần |
|---|---|
| Gọi thẳng MISA từ trình duyệt, hay gọi qua whitelisted method / Server Script? | quyết định (B) làm được ở server hay bắt buộc ở trình duyệt |
| Endpoint đẩy là gì, payload ra sao | không có thì không viết được luồng đẩy |
| `RefID` do ERPNext sinh hay MISA trả về | quyết định tầng khớp 1 (§H.5) |
| Ghi ngược số hóa đơn vào field nào, lúc nào | quyết định §C.0 câu 5 |
| Xác thực bằng gì | mấu chốt của hướng (B) |

**Chưa có script này thì chưa viết `misa_client.py`** — viết ra sẽ trùng hoặc đá nhau với luồng
đang chạy, và ràng buộc 13.4 của pack cấm tự động sửa/hủy hóa đơn.

---

## L. Luồng đẩy hiện hành — đọc từ Client Script thật (17/08/2026)

Nguồn: `Client Script` trên Sales Invoice của site production. **Credential trong script KHÔNG
chép vào đây.**

### L.1 🚨 SỰ CỐ BẢO MẬT — ưu tiên cao nhất, xử lý trước mọi việc khác

Script chứa **username và mật khẩu MISA dạng chữ thường, không mã hóa**, hardcode ngay trong
thân hàm `layToken()`.

`Client Script` được Frappe **gửi xuống trình duyệt của MỌI người dùng có quyền vào Desk**. Bất
kỳ ai trong công ty mở DevTools (hoặc xem `/api/method/frappe.client.get_list?doctype=Client Script`)
đều đọc được mật khẩu tài khoản MISA — tài khoản **phát hành hóa đơn có giá trị pháp lý**.

| Việc | Mức |
|---|---|
| Đổi mật khẩu MISA ngay | **khẩn** |
| Gỡ credential khỏi Client Script | **khẩn** |
| Rà `Client Script` / `Server Script` khác xem còn credential nào không | cao |
| Chuyển credential vào `MISA Settings` (fieldtype `Password`, Frappe mã hóa) | cao |

Đây chính là ràng buộc 13.6 của pack — *"Không để credential ngoài fieldtype `Password`"*.

### L.2 ✅ XÁC THỰC — CÓ bearer token, §J.4 đã kết luận sai bề mặt

MISA có **hai bề mặt khác nhau**, khảo sát trước đó nhầm lẫn chúng:

| Bề mặt | Host | Xác thực | Dùng cho |
|---|---|---|---|
| **API** | `https://app.meinvoice.vn/api/v2/…` | **Bearer token** + header `TaxCode` | luồng đẩy đang chạy |
| Web UI | `https://app3.meinvoice.vn/v3/…` | cookie phiên + anti-forgery + Cloudflare | lưới hóa đơn trên trình duyệt (§J) |

⇒ **Cảnh báo Cloudflare ở §J.4 không áp dụng cho bề mặt API.** Hướng (B) tự động hóa từ server
**làm được sạch sẽ** qua bề mặt API — không cần cookie jar, không đụng Cloudflare, không cần
trình duyệt.

**Lấy token** (đã chạy thật trong production):

```
POST {base}/api/v2/oauth
Header: TaxCode: <MST công ty>
Body  : form-urlencoded — grant_type=password & username=… & password=…
→ response.access_token        (dùng làm "Bearer {access_token}")
```

**Gọi API sau đó**: header `Authorization: Bearer …` + `TaxCode: <MST>` + `Content-Type: application/json`.

> Chưa quan sát được `expires_in` (script không đọc). Client sẽ cache thận trọng và tự lấy lại
> token khi gặp 401.

### L.3 Endpoint đẩy hóa đơn

```
POST {base}/api/v2/v3sainvoice/code
Body: MẢNG JSON  [ { …1 hóa đơn… } ]
```

Đuôi `/code` — lần thứ ba xác nhận **hóa đơn có mã CQT** (§H.4, §J.1).

Tham số cấu hình đang hardcode trong script, cần đưa vào `MISA Settings`:
`CompanyID`, `OrganizationUnitID`, `InvTemplateNo`, `InvoiceTemplateID`, `UserID`, `InvSeries`.

`OrganizationUnitID` trong script **trùng khớp** giá trị quan sát ở §H.2 → xác nhận chéo rằng
hóa đơn trong bảng dữ liệu đúng là do luồng này đẩy lên.

### L.4 🐞 Bốn lỗi trong luồng đang chạy

**L.4.1 — RefID bị vứt mất (nghiêm trọng nhất về đối soát)**

Script sinh `RefID = uuidv4()` cho hóa đơn, gửi sang MISA, rồi **không lưu lại**. Sau đó ghi:

```js
frappe.db.set_value(..., 'vn_einvoice_lookup_code', result.some_unique_id || uuidv4());
```

`some_unique_id` **không phải field nào của MISA** — nó là tên giữ chỗ. Biểu thức luôn rơi vào
nhánh `|| uuidv4()`, tức là ghi **một uuid ngẫu nhiên hoàn toàn mới, chưa từng gửi cho MISA**.

⇒ `vn_einvoice_lookup_code` hiện là **rác**, không tra cứu được gì. RefID thật đã mất vĩnh viễn
với mọi hóa đơn cũ.

⇒ Đính chính §H.5: RefID trong dữ liệu MISA **đúng là do ERPNext sinh** — nên tầng khớp 1 sẽ
hoạt động **cho hóa đơn đẩy từ sau khi sửa lỗi này**. Hóa đơn cũ vẫn phải khớp bằng tầng 4
(MST + ngày + tiền) vì ERPNext không giữ cả RefID lẫn số hóa đơn.

**L.4.2 — `vn_einvoice_number` không bao giờ được ghi**

`after_save` kiểm `!frm.doc.vn_einvoice_number` để chặn đẩy trùng, nhưng **không có dòng code
nào trong toàn bộ script gán giá trị cho field này**. Nó rỗng vĩnh viễn.

⇒ Giải thích trọn vẹn §A.2: 6 màn hình của app đọc `vn_einvoice_number` và luôn thấy rỗng.
⇒ Chốt §C.0 câu 5 theo **hướng (a) đồng bộ ngược** — điền field này là 6 màn hình sống lại ngay.

**L.4.3 — Thuế suất hardcode 8%**

`VATRate: 8.0`, `VATAmount: amount * 0.08`, `TotalAmount: totalAmount * 1.08` — **cứng ở mọi
dòng, mọi hóa đơn**, bỏ qua hoàn toàn bảng `taxes` của Sales Invoice.

⇒ Hóa đơn nào không phải 8% là **phát hành sai thuế**. Rủi ro thuế thật.
⇒ Cũng giải thích vì sao không thể tin tổng tiền MISA để đối soát cho tới khi sửa.

**L.4.4 — Ký hiệu hóa đơn cũ**

Script gửi `InvSeries: "1C24THG"`, trong khi dữ liệu thật đang phát hành **`1C26THG`** (§H.2).
Giá trị gửi lên đang bị MISA bỏ qua (lấy theo mẫu hóa đơn), nhưng đây là bom hẹn giờ.

### L.5 Custom field sẵn có trên Sales Invoice (49 field)

Đã đối chiếu toàn bộ: **không field nào trùng tiền tố `custom_misa_`** → 12 field Phase 1 an toàn.

Nhóm hóa đơn điện tử sẵn có: `vn_einvoice_section`, `vn_einvoice_col`, `vn_einvoice_number`,
`vn_einvoice_date`, `vn_einvoice_lookup_code`, `vn_einvoice_status`.

Quy ước: nhóm `vn_einvoice_*` là **mặt hiển thị cho kế toán** (6 màn hình app đang đọc); nhóm
`custom_misa_*` là **dữ liệu kỹ thuật của đồng bộ**. Luồng ghi ngược sẽ điền cả hai.

> Ghi chú: 30/49 custom field của site đặt tên **có dấu tiếng Việt** (`custom_thể_tích_lô`…),
> trái ràng buộc 13.8 của pack. Không sửa — ngoài phạm vi, và đổi tên field đang chạy là phá.

### L.6 Gate Phase 2 — MỞ

Đã có đủ để viết `misa_client.py`: endpoint lấy token, dạng body, header bắt buộc, tên field
`access_token`, cách gắn bearer, và endpoint đẩy. Không còn phải đoán.

---

## M. U3 ĐÃ XÁC MINH — chi tiết hóa đơn sau phát hành (17/08/2026)

Chạy `misa_probe.run` trên site thật. **Server tự lấy được token qua bề mặt API** — xác nhận
§L.2, không cần trình duyệt, không đụng Cloudflare.

```
GET {base}/api/v2/code/v3sainvoice/afterpublishing/{RefID}
→ object 194 field, kèm InvoiceDetails[] 74 field mỗi dòng
```

Bỏ tiền tố `code/` → trả **mảng rỗng**. Lần thứ tư xác nhận hóa đơn CÓ MÃ CQT: route `code/`
là **bắt buộc**, không phải tùy chọn.

### M.1 ✅ Có tách thuế — gỡ được nút thắt §H.2

| Field | Mẫu | → ERPNext đối chiếu |
|---|---|---|
| `TotalAmountWithoutVAT` | `20395000.0` | `Sales Invoice.net_total` |
| `TotalVATAmount` | `1631600.0` | `total_taxes_and_charges` |
| `TotalAmount` | `22026600.0` | `grand_total` |
| `TotalSaleAmount` `TotalDiscountAmount` | `20395000.0` `0.0` | trước/sau chiết khấu |
| `VATRate` · `IsMoreVATRate` | `8.0` · `False` | cờ nhiều thuế suất |

⇒ **So tiền 3 vế mà pack §6.3 yêu cầu nay làm được đầy đủ.**

### M.2 Field khóa — dùng cho `poll_pending`

| Field MISA | Mẫu | → ERPNext |
|---|---|---|
| `RefID` | GUID | khóa nối, khớp đúng cái gửi đi |
| `InvNo` | `00007140` | `custom_misa_inv_no` + `vn_einvoice_number` |
| `InvSeries` | `1C26THG` | `custom_misa_inv_series` |
| `InvDate` | `2026-08-17T00:00:00+07:00` | `custom_misa_inv_date` + `vn_einvoice_date` |
| `TransactionID` | `GJF2I1_8DELM` | `custom_misa_transaction_id` + `vn_einvoice_lookup_code` |
| `InvoiceCode` | 34 ký tự hex | `custom_misa_invoice_code` |
| `PublishingTime` | `2026-08-17T14:17:50+07:00` | thời điểm phát hành thật |

> ⚠️ `InvDate` ở đây có **offset múi giờ** (`+07:00`), còn ở endpoint danh sách thì **không**
> (§H.2). Phải cắt 10 ký tự đầu, không dùng thư viện parse tự đoán.

### M.3 Vòng đời hóa đơn — hủy / thay thế

| Field | Mẫu | Ý nghĩa |
|---|---|---|
| `IsInvoiceDeleted` | `False` | **cờ hủy** — dùng cho `match_status='Đã hủy'` |
| `DeletedDate` `DeletedReason` | `None` | |
| `OrgRefID` `OrgInvNo` `OrgInvSeries` `OrgInvDate` `OrgTransactionID` `OrgInvoiceCode` | rỗng | **hóa đơn GỐC** mà bản này thay thế |
| `TypeChangeInvoice` `ChangeReason` | `None` | loại và lý do thay thế/điều chỉnh |
| `OrgInvoiceType` | `0` | |
| `ErrorInvoiceStatus` `ErrorAnnouncementID` | `0` `None` | thông báo sai sót gửi CQT |
| `MessageCode` | `TCTA8E79…` | mã phản hồi của CQT |

⇒ Cách nhận biết đúng, **không suy đoán từ `EInvoiceStatus`**:
`IsInvoiceDeleted=True` → **Đã hủy**; `OrgRefID` có giá trị → bản này **thay thế** hóa đơn `OrgRefID`.

### M.4 Tham số phát hành thật — có chỗ lệch với Client Script

| Tham số | MISA trả về | Client Script gửi | |
|---|---|---|---|
| `CompanyID` | `156217` | `156217` | khớp |
| `OrganizationUnitID` | `a5834b4e-…` | `a5834b4e-…` | khớp |
| `InvTemplateNo` | `1` | `1` | khớp |
| `UserID` | `23dd8700-…` | `23dd8700-…` | khớp |
| `InvSeries` | **`1C26THG`** | `1C24THG` | ❌ script gửi ký hiệu 2024 |
| `InvoiceTemplateID` | **`de202fcb-510f-4248-a54f-4c560920facd`** | `04b080d7-04fa-4375-b644-ec987b489b4d` | ❌ lệch hoàn toàn |

MISA đang bỏ qua hai giá trị sai này và lấy theo mẫu hóa đơn đang hiệu lực. Khi viết luồng đẩy
mới phải dùng **giá trị MISA trả về**, không chép lại từ script.

Thêm: `SourceType=6`, `PublisherID=b7839dba-…`, `IsTaxReduction43=True`,
`IsInheritFromOldTemplate=True`, `ModifiedBy` là email người thao tác trên MISA.

### M.5 `InvoiceDetails[]` — 74 field/dòng

Dùng được ngay: `RefDetailID`, `InventoryItemCode`, `Description`, `UnitName`, `Quantity`,
`UnitPrice`, `Amount`/`AmountOC`, `VATRate`, `VATAmount`/`VATAmountOC`, `DiscountRate`,
`DiscountAmount`, `SortOrder`, `InventoryItemType`.

Mẫu dòng đầu: `H24 X` · `Bánh đậu xanh H24 300g` · `Hộp` · SL 30 · đơn giá 28.000 ·
thành tiền 840.000 · VAT 8% = 67.200.

⇒ `VATRate` nằm **ở từng dòng**, MISA hỗ trợ nhiều thuế suất trong một hóa đơn (`IsMoreVATRate`).
Việc Client Script cứng 8% cho mọi dòng (§L.4.3) là sai *thiết kế*, không phải giới hạn của MISA.

### M.6 Ba endpoint còn lại — chưa dùng được

| Endpoint | Kết quả | Chẩn đoán |
|---|---|---|
| `code/v3sainvoice/paging` | mảng rỗng | thiếu tham số. Lưới thật gửi ~25 tham số (§J.3), mới thử 4 |
| `v3report/ipusedamount/paging` | `ArgumentNullException` tại `SerializeUtil.DeserializeObject` | thiếu tham số **`paramReport`** dạng chuỗi JSON |
| `resource/GetTotalUsedInvoiceQuantityByInvTemplate` | `NullReferenceException` | `invSeries` rỗng vì chưa khai `inv_series_list` |

Không chặn gì: `afterpublishing` đã đủ cho `poll_pending`. Ba cái này phục vụ dò hóa đơn mồ côi
(Phase 4–6), để sau.

---

## N. Link tra cứu hóa đơn — ĐÃ XÁC MINH (17/08/2026)

Nguồn: link MISA gửi kèm email hóa đơn cho khách hàng.

```
https://www.meinvoice.vn/tra-cuu/?sc={TransactionID}
```

| Tham số | Vai trò |
|---|---|
| `sc` | **mã tra cứu** = field `TransactionID` (§M.2). Bắt buộc |
| `m` `n` | email + tên người mua — chỉ điền sẵn ô tra cứu |
| `c` `b` `d` `t` `r` | cờ hiển thị |

Chỉ giữ `sc` là mở đúng hóa đơn. Đã kiểm: hàm dựng URL cho ra **trùng khớp
tuyệt đối** với link thật.

### N.1 Trang quản trị KHÔNG có link sâu

`app3.meinvoice.vn/v3/hoa-don` mở hóa đơn bằng cửa sổ nổi, URL không đổi ⇒ không
có đường dẫn riêng cho từng hóa đơn trên trang quản trị.

⇒ Link tra cứu công khai chính là đường dẫn chi tiết hóa đơn duy nhất dùng được,
nên `custom_misa_link` lưu link này (`primary`). Nút "Mở trên trang quản trị"
chỉ mở danh sách — giữ lại phòng khi MISA bổ sung link sâu sau này.

---

## O. Endpoint danh sách — nguyên nhân thật (18/08/2026)

`diagnose_vat` trên site thật cho lỗi từ chính tầng SQL của MISA:

```
MySqlConnector.MySqlException: Unknown column 'InvoiceSummaryStatus' in 'where clause'
```

⇒ Endpoint **không hề chặn**. Request đi tới tận nơi rồi mới vỡ: MISA dựng câu SQL
từ tham số client gửi lên, và `invoiceSummaryStatus` trỏ vào một cột **không tồn tại
trong bảng hóa đơn CÓ MÃ**. Lưới trên `app3` gửi được tham số này vì nó chạy trên
bảng khác.

Đính chính §M.6: kết luận "trả mảng rỗng" là do lần dò đó nuốt lỗi. Endpoint dùng
được, chỉ là bộ tham số chép từ lưới web **không dùng nguyên si được** cho route
`code/`.

### O.1 Cách xử — tự gỡ tham số thay vì chép cứng

Không thể biết trước bảng hóa đơn có mã thiếu những cột nào, và MISA có thể đổi
bất cứ lúc nào. Nên `_paging_call` đọc tên cột trong thông báo lỗi, gỡ đúng tham
số tương ứng rồi gọi lại (tối đa 6 lần), và nhớ trong cả lượt phân trang để trang
sau không gửi lại. Tham số đã gỡ được ghi vào `error_log` của `MISA Sync Run`.

Lỗi KHÔNG phải `Unknown column` thì ném ra bình thường — không nuốt.

`invoiceSummaryStatus` đã gỡ sẵn khỏi `PAGING_BASE` vì đã biết chắc.

### O.2 Đính chính con số

`kéo=2` trong nhật ký là của `poll_pending` (hỏi số hóa đơn cho SI đã đẩy), KHÔNG
phải kéo danh sách. Snapshot vẫn 0 — endpoint danh sách chưa từng chạy thành công
lần nào. Lo ngại "968 so với 3" ở lượt trước là đọc nhầm nhật ký.

---

## P. ĐÃ GIẢI — endpoint danh sách chạy được (18/08/2026)

`find_list_endpoint` quét 12 đường dẫn × 6 biến thể tham số trên site thật.

### P.1 Thủ phạm: DẤU NHÁY KÉP quanh giá trị ngày

| Biến thể trên `code/v3sainvoice/paging` | Kết quả |
|---|---|
| `fromDate="2026-07-18T00:00:00.000Z"` (CÓ nháy) | **0 dòng** |
| `fromDate=2026-07-18T00:00:00.000Z` (không nháy) | **5 dòng · recordsTotal 1260** ✅ |
| `fromDate=2026-07-18` (ngày trần) | **5 dòng · 1260** ✅ |
| không gửi ngày | 0 dòng |

Lưới web `app3` gửi giá trị **kèm nháy kép bên trong chuỗi** vì tầng của nó tự
bóc. Bề mặt `/api/v2` model-bind thẳng vào `DateTime`, chuỗi có nháy parse hỏng,
rơi về khoảng rỗng — và **không ném lỗi**, chỉ trả 0 dòng.

Chép nguyên quirk của một tầng sang tầng khác mà không kiểm là gốc của cả chuỗi
"0 bản ghi" ở §M.6 và §O.

### P.2 Hợp đồng đã chốt

```
POST {base}/api/v2/code/v3sainvoice/paging     ·  form-urlencoded
    start      = 0
    length     = 100
    fromDate   = YYYY-MM-DDT00:00:00.000Z      ← KHÔNG nháy kép
    toDate     = YYYY-MM-DDT23:59:59.000Z      ← KHÔNG nháy kép
→ {"data": "<chuỗi JSON mảng>", "recordsTotal": <tổng thật>, "success": true}
```

- **Ngày là BẮT BUỘC.** Thiếu ngày → 0 dòng.
- **Tiền tố `code/` là BẮT BUỘC.** `v3sainvoice/paging` trả 0 kể cả khi có ngày.
- **Bộ tối giản là đủ.** 17 tham số chép từ lưới web đều không cần.
- **`recordsTotal` ở endpoint này CÓ giá trị thật** (1260) — khác lưới web luôn
  trả 0. Chốt chặn "kéo thiếu" ở §O nhờ vậy mới hoạt động.

### P.3 Bản đồ đường dẫn — đã dò hết

| Đường dẫn | Kết quả |
|---|---|
| `code/v3sainvoice/paging` | ✅ **dùng cái này** |
| `v3sainvoice/paging` · `code/v3sainvoice/list` · `v3sainvoice/list` | tồn tại, luôn 0 dòng |
| `sainvoicewithcode/list` và 4 biến thể cùng nhóm | **404** — tên của lưới web không tồn tại trên API |
| `v3sainvoice/getpaging` · `v3sainvoice/search` | **405** — có route nhưng không nhận POST |

⇒ Đóng lại nhánh "tên route phản chiếu lưới web" bằng bằng chứng, không phải phỏng đoán.

### P.4 Lưới an toàn

`columns` chưa được kiểm chứng cùng biến thể chạy được, nên `_paging_call` thử bộ
đầy đủ trước; trả rỗng thì tự lùi về **bộ tối giản đã xác minh** rồi ghi log. Thà
lấy được dữ liệu với ít cột còn hơn im lặng trả rỗng.

---

## Q — Chuyển tiếp số hóa đơn nhập tay (`vn_einvoice_number` → `custom_misa_inv_no`)

### Q.1 Vấn đề

Trước tích hợp, kế toán gõ tay số hóa đơn vào `vn_einvoice_number` (§A.2). Luồng
tự động lại ghi vào `custom_misa_inv_no`. Toàn bộ đối soát (`misa_reconcile`,
`misa_vat`) chỉ đọc nhóm `custom_misa_*` ⇒ **mọi hóa đơn cũ trông như chưa xuất**:
rơi vào rổ "Chỉ có trên phần mềm", còn bản MISA tương ứng rơi vào rổ "Chỉ có trên
MISA". Hai rổ cảnh báo đầy báo động giả.

### Q.2 Cách xử lý — `ketoan/api/misa_legacy.py`

Xem trước bắt buộc (`preview`, cho kế toán bán hàng) rồi mới ghi (`commit`, chỉ
kế toán trưởng). Ghi bằng `db_set(update_modified=False)`, **không** `save()`.

Chép: `custom_misa_inv_series`, `custom_misa_inv_no`, `custom_misa_inv_date`
(lấy `vn_einvoice_date`, không có thì `posting_date`), `custom_misa_status =
'Đã phát hành'`.

### Q.3 Tách ký hiệu khỏi số

Lấy **cụm số ở cuối chuỗi** làm số hóa đơn, phần đầu làm ký hiệu.

| Giá trị đang có | → ký hiệu | → số | Ghi |
|---|---|---|---|
| `1C25MHG/0000123` | `1C25MHG` | `0000123` | ✅ |
| `AA/20E 0001234` | `AA/20E` | `0001234` | ✅ mẫu TT32 cũ |
| `0000123` | ký hiệu mặc định chọn ở màn hình | `0000123` | ✅ |
| `2025-000123` | — | — | ❌ `2025` không có chữ cái → không phải ký hiệu |
| `1C25MHG` | — | — | ❌ không có số ở cuối |
| `123 (đã hủy)` | — | — | ❌ không đọc được |

Ký hiệu hợp lệ phải **có ít nhất một chữ cái**, 5–12 ký tự, cho phép một gạch
chéo. Không đoán: dòng nào không chắc thì bỏ lại cho người sửa tay.

### Q.4 Bốn chốt chặn

1. Chỉ ghi khi `custom_misa_inv_no` **đang trống** — luồng tự động đáng tin hơn.
2. Trùng `(ký hiệu, số)` với hóa đơn khác → bỏ qua, liệt kê tên hóa đơn đang giữ
   số đó. Hai hóa đơn cùng số là sai báo cáo thuế.
3. `vn_einvoice_lookup_code` **chỉ** được chép sang `custom_misa_transaction_id`
   khi khớp khuôn mã tra cứu thật (chữ+số liền, 8–24 ký tự). uuid rác của luồng
   cũ (§L.4.1) có gạch nối nên rớt — đúng ý đồ.
4. Xem trước tách theo **năm** kèm phân bố ký hiệu đọc được, để chạy riêng từng
   năm với ký hiệu mặc định đúng của năm đó.

Chép xong `commit` xếp `match_snapshots(relink=1)` chạy nền cho đúng khoảng ngày
vừa động tới — không chạy lại đối soát thì rổ không đổi.

---

## R — Trạng thái hóa đơn MISA ↔ ERPNext

### R.1 Màn hình MISA có HAI ô chọn, là HAI TRỤC khác nhau

| Ô chọn | Trả lời câu hỏi | Field MISA |
|---|---|---|
| Chưa phát hành · Đang phát hành · Phát hành lỗi · Chờ cấp mã · Đã cấp mã · Từ chối cấp mã · TĐ không hợp lệ | hóa đơn **có giá trị pháp lý chưa** | `EInvoiceStatus` / `PublishStatus` (enum **chưa xác minh**) |
| Hóa đơn mới · thay thế · điều chỉnh · đã bị hủy · đã bị thay thế · đã bị điều chỉnh | hóa đơn **còn hiệu lực hay đã bị bản khác thay** | `OrgRefID`, `TypeChangeInvoice`, `IsInvoiceDeleted` |

Hai trục **độc lập**: một hóa đơn thay thế vẫn phải đi hết vòng cấp mã của
chính nó. Gộp vào một field là mất thông tin — nên ERPNext tách làm hai:
`custom_misa_status` (trục 1) và `custom_misa_relation` (trục 2).

### R.2 Lỗi đã sửa — dán nhãn ngược

Bản cũ: `OrgRefID` có giá trị → đặt `custom_misa_status = 'Đã thay thế'` cho
chính hóa đơn đang xét.

Sai chiều. §M.3 nói rõ: `OrgRefID` có giá trị nghĩa là **bản này thay thế hóa
đơn `OrgRefID`** — bản đang xét là bản MỚI, còn hiệu lực. Hậu quả:

- hóa đơn **sống** bị đánh dấu như đã chết, lại còn bị vòng quét thứ 2 loại ra
  nên không bao giờ được chấm lại;
- hóa đơn **chết thật** (bản gốc) không ai đụng tới, vẫn hiện "Đã phát hành";
- hai hóa đơn cùng hiện hợp lệ cho một lần bán ⇒ **khai trùng doanh thu và
  thuế đầu ra**.

Nay: bản đang xét nhận `relation='Hóa đơn thay thế/điều chỉnh'` và giữ nguyên
trục 1; `_mark_superseded` tìm ngược Sales Invoice theo `OrgRefID` để đặt
`'Đã thay thế'` cho **bản gốc**, kèm ToDo nếu bản gốc vẫn đang ghi sổ.

### R.3 "Đã phát hành" phải chờ mã CQT

Có số hóa đơn mới chỉ là MISA đã đánh số. Hợp lệ hay không do **cơ quan thuế
cấp mã** quyết định. Bản cũ gọi mọi hóa đơn có số là "Đã phát hành" ⇒ hóa đơn
đang *Chờ cấp mã* hoặc bị *Từ chối cấp mã* vẫn hiện như đã phát hành hợp lệ.

Mốc dùng được ngay, **không cần enum**: `InvoiceCode` (mã CQT, 34 ký tự HEX,
§H.3/§M.2). Rỗng ⇒ `'Chờ cấp mã'` + ToDo. Chỉ áp dụng khi `use_code_route` bật
— đơn vị dùng hóa đơn KHÔNG mã thì không bao giờ có mã này.

⚠️ Mốc này **không tách được** *Chờ cấp mã* với *Từ chối cấp mã* / *TĐ không hợp
lệ* — cả ba đều là "chưa có mã". Tách được phải có enum (R.5).

### R.4 Bảng ánh xạ

| MISA | ERPNext `custom_misa_status` | Việc kế toán phải làm |
|---|---|---|
| Chưa phát hành | `Đã đẩy (nháp)` / `Chưa đẩy` | phát hành trên MISA |
| Đang phát hành | *(chưa tách)* → `Chờ cấp mã` | đợi, hệ thống tự hỏi lại |
| Phát hành lỗi | `Phát hành lỗi` | sửa dữ liệu rồi đẩy lại |
| Chờ cấp mã | `Chờ cấp mã` | **chưa được giao hóa đơn cho khách** |
| Đã cấp mã | `Đã phát hành` | — |
| Từ chối cấp mã | *(chưa tách)* → `Chờ cấp mã` | **gấp**: sửa và phát hành lại |
| TĐ không hợp lệ | *(chưa tách)* → `Chờ cấp mã` | **gấp**: sai định dạng gửi CQT |

| MISA | ERPNext `custom_misa_relation` | Việc kế toán phải làm |
|---|---|---|
| Hóa đơn mới | `Hóa đơn mới` | — |
| Hóa đơn thay thế / điều chỉnh | `Hóa đơn thay thế/điều chỉnh` | bản này còn hiệu lực |
| Đã bị thay thế / điều chỉnh | `Bị thay thế/điều chỉnh` + trục 1 = `Đã thay thế` | bản gốc còn `docstatus=1` ⇒ kiểm khai trùng |
| Đã bị hủy | trục 1 = `Đã hủy` (`IsInvoiceDeleted`) | hủy/điều chỉnh chứng từ bên ERPNext |

### R.5 Còn thiếu — CHƯA được code

1. **Enum `EInvoiceStatus`** — chưa biết số nào ứng với mục nào. Ba mục nguy
   hiểm nhất (*Từ chối cấp mã*, *TĐ không hợp lệ*, *Phát hành lỗi*) hiện gộp
   chung vào `Chờ cấp mã`.

   ❌ **Lối lọc đã thử và ĐÃ LOẠI.** `find_status_enum` gửi tham số `filter`
   dạng `comboboxenum` giống lưới web, chạy 18/08/2026 trên khoảng
   2026-01-01 → 2026-08-18:

   | giá trị lọc | tổng khai |
   |---|---|
   | (không lọc) | 7787 |
   | 0 … 9 (mọi giá trị) | 7787 |

   Giá trị **8 và 9 không hề có trong ô chọn** mà vẫn ra đúng 7787. ⇒ Bề mặt
   `/api/v2` **BỎ QUA** tham số `filter`. Không suy ra được gì về enum từ đây —
   và đừng đọc bảng trên thành "trạng thái nào cũng có 7787 hóa đơn".

   ✅ **Lối đang dùng — đối chiếu dữ liệu thật, không cần lọc:**

   ```
   bench --site <site> execute ketoan.api.misa_probe.cross_status \
       --kwargs "{'from_date': '2026-01-01', 'pages': 5}"
   ```

   Kéo hóa đơn thật về rồi lập bảng chéo `EInvoiceStatus` × (có mã CQT chưa) ×
   (đã cấp số chưa) × `PublishStatus`/`SendToTaxStatus`, kèm **số hóa đơn mẫu**
   cho từng giá trị enum. Mở MISA tra đúng những số đó, đọc trạng thái màn hình
   hiện — đó là bằng chứng trực tiếp. Ghi vào đây rồi mới được code.

2. **Enum `TypeChangeInvoice`** — tách *thay thế* với *điều chỉnh*. Khác biệt
   thật về thuế: hóa đơn **thay thế** xóa hiệu lực bản gốc; hóa đơn **điều
   chỉnh** giữ bản gốc còn hiệu lực và chỉ cộng thêm phần chênh. Chưa tách được
   thì **không** được tự kết luận bản gốc hết hiệu lực — hiện `_mark_superseded`
   chỉ đặt trạng thái + giao việc, không đụng chứng từ (ràng buộc 13.4).

3. **So tiền cho hóa đơn điều chỉnh** — bản điều chỉnh mang số CHÊNH, không
   phải tổng. So với `grand_total` của Sales Invoice sẽ luôn ra "Lệch tiền".
   Chưa tách được loại thì chưa sửa được chỗ này.

### R.7 ✅ BẢNG ENUM — ĐÃ XÁC MINH (18/08/2026)

Nguồn: người dùng đọc trạng thái của 5 hóa đơn thật trên màn hình MISA, rồi
`misa_probe.inspect_invoices` lấy giá trị API của đúng 5 hóa đơn đó.

| InvNo | Màn hình MISA hiện | `EInvoiceStatus` | `PublishStatus` | `OrgRefID` |
|---|---|---|---|---|
| 00006689 | Hóa đơn mới · Đã cấp mã | **1** | 3 | — |
| 00006654 | Hóa đơn thay thế · Đã cấp mã | **3** | 3 | ✓ → 00006392 |
| 00005589 | Hóa đơn điều chỉnh · Đã cấp mã | **4** | 3 | ✓ → 00004882 |
| 00006679 | Đã bị thay thế · Đã cấp mã | **7** | 3 | — |
| 00004486 | Đã bị điều chỉnh · Đã cấp mã | **8** | 3 | — |

**Phát hiện quyết định: `EInvoiceStatus` KHÔNG phải trạng thái phát hành — nó
là TRỤC QUAN HỆ.** Cả 5 hóa đơn đều *Đã cấp mã* (`PublishStatus` giữ nguyên 3)
trong khi `EInvoiceStatus` chạy 1/3/4/7/8 đúng theo quan hệ thay thế/điều chỉnh.

⇒ **Bác bỏ** suy đoán ở §H.6 ("`EInvoiceStatus` cần xác nhận gấp… bị thay thế?
bị điều chỉnh?"). Mẫu 30 dòng ở đó đọc từ lưới web đã lọc sẵn nên lệch.

```
EINVOICE_RELATION = {1: mới, 3: thay thế, 4: điều chỉnh,
                     7: bị thay thế, 8: bị điều chỉnh}
PublishStatus     = {0: chưa phát hành, 3: đã cấp mã}
```

`PublishStatus=0` lấy từ `cross_status`: 500/500 dòng nháp (`<Chưa cấp số>`).

**Hai hệ quả bắt buộc về thuế**

1. `7` (bị thay thế) ⇒ **hết hiệu lực** → `custom_misa_status='Đã thay thế'`.
   `8` (bị điều chỉnh) ⇒ bản gốc **VẪN còn hiệu lực**, hóa đơn điều chỉnh chỉ
   cộng thêm phần chênh. Gộp 7 với 8 là khai thiếu doanh thu của chính bản gốc.
2. `4` (hóa đơn điều chỉnh) mang số **CHÊNH**, không phải tổng ⇒ **bỏ so tiền**
   với `grand_total`, nếu không mọi hóa đơn điều chỉnh đều thành "Lệch tiền" giả.
   Vẫn ghi chú rõ lý do bỏ so, không im lặng.

**Org\* chỉ nằm trên bản MỚI.** 6679 và 4486 (hai bản *bị* tác động) trống
sạch `OrgRefID`/`OrgInvNo`. Nên `EInvoiceStatus` là nguồn duy nhất phát hiện
được hóa đơn hết hiệu lực khi ta chưa thấy bản thay thế của nó — suy ngược từ
`OrgRefID` là không đủ.

`TypeChangeInvoice` **None ở cả 5** → không dùng được để tách thay thế với điều
chỉnh. Chính `EInvoiceStatus` mới là thứ tách được. `ChangeReason` chỉ có ở bản
điều chỉnh (5589: "Hóa đơn không giao được hàng").

**Còn chưa xác minh**: `EInvoiceStatus` 2/5/6 (mục *Hóa đơn đã bị hủy* của ô
chọn nằm ở đâu chưa rõ — hiện đã có `IsInvoiceDeleted` lo việc này) và
`PublishStatus` 1/2/4/5 (*đang phát hành*, *phát hành lỗi*, *chờ cấp mã*, *từ
chối cấp mã*, *TĐ không hợp lệ*). Gặp giá trị lạ thì code **không đoán** — lùi
về mốc mã CQT: có `InvoiceCode` là đã cấp mã, không có là `Chờ cấp mã`.

### R.6 Số đo khối lượng thật (18/08/2026)

`recordsTotal` trên khoảng 2026-01-01 → 2026-08-18: **7787 hóa đơn** (~8 tháng)
⇒ khoảng **12.000/năm**.

Hệ quả: `MAX_PAGES = 100` (10.000 hóa đơn/lượt) không đủ cho một lượt kéo cả
năm — đã nới lên **300**. Chốt chặn "KÉO THIẾU" ở cuối `pull_invoices` vẫn giữ
nguyên, nó so `recordsTotal` với số ghi được nên chạm trần là báo đỏ chứ không
im lặng.

Con số 1260 ở §P là của khoảng ngày HẸP hơn — không mâu thuẫn.

---

## S — Lịch chạy đồng bộ tự động

### S.1 Khung giờ

Xuất và ký hóa đơn chỉ diễn ra trong giờ hành chính **7:30 – 17:30**, nên job
theo lịch chạy **30 phút/lần trong khung đó**, ngoài ra không chạy.

```python
scheduler_events = {"cron": {
    "30 7 * * *":      [...],   # 7:30
    "0,30 8-17 * * *": [...],   # 8:00, 8:30, … 17:00, 17:30
}}
```

21 lần/ngày, cách đều 30 phút, không lần nào rơi ngoài khung. Viết gọn thành
`0,30 7-17` thì dư một lượt 7:00 nên tách làm hai dòng cho khớp đúng yêu cầu.

### S.2 Vì sao kiểm khung giờ HAI lần

Cron ở `hooks.py` là lớp 1; `misa_sync.in_sync_window()` đọc MISA Settings là
lớp 2. Giữ cả hai vì chúng chặn hai kiểu hỏng khác nhau:

| Hỏng gì | Lớp nào chặn |
|---|---|
| Muốn đổi khung giờ | Settings — kế toán tự sửa, không cần deploy |
| Múi giờ khai sai ở System Settings | không lớp nào — xem S.3 |
| Ai đó gọi thẳng `scheduled_poll_pending` | lớp 2 |

Khung giờ để **trống** ⇒ KHÔNG chặn. Thà chạy dư còn hơn im lặng không chạy rồi
không ai biết vì sao số hóa đơn không về.

### S.3 Bẫy múi giờ

Cron của Frappe tính theo **múi giờ khai ở System Settings**, không phải giờ
máy chủ. Khai lệch thì cả khung 7:30–17:30 chạy sai giờ mà **không có gì báo** —
job vẫn đủ 21 lượt, chỉ là chạy lúc không ai xuất hóa đơn. Lớp 2 cũng dùng
`now_datetime()` nên cùng cơ sở, không phát hiện chéo được.

Kiểm bằng:

```
bench --site <site> execute ketoan.api.misa_probe.check_schedule
```

In ra múi giờ, giờ site đang thấy, khung giờ khai, và mốc cron nào rơi ngoài
khung. "Giờ site đang thấy" lệch giờ Việt Nam ⇒ sửa Time Zone trong System
Settings.

### S.4 Ngoài giờ KHÔNG mất dữ liệu

Hóa đơn ký lúc 17:45 không bị bỏ sót — lượt 7:30 sáng hôm sau quét lại, vì
`poll_pending` nhìn lùi `lookback_days` (mặc định 60 ngày). Ngoài giờ chỉ là
**chậm**, không phải **mất**.
