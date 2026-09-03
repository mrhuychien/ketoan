# Prompt: số hóa đơn MISA cho `nppsale` (Next.js 14 + Supabase)

Copy từ `## PROMPT` trở xuống.

Phiên này **đã đọc `mrhuychien/nppsale` @ `c45f82b`** (read-only). App đó **đã có**
tích hợp MISA — `src/lib/misa/*`, `src/app/api/einvoice/*`, migration 072→079.
Nên đây không phải prompt dựng từ đầu, mà là: **một lỗi đang chạy phải sửa
trước**, rồi bốn thứ đang thiếu, đo được từ chính mã nguồn của nó.

Nguồn của các bất biến ở §4: app `ketoan` (Frappe/ERPNext), nơi cùng cơ chế này
đã chạy trên dữ liệu thật và va đủ các cạnh. Chúng **không phụ thuộc stack**.

---

## PROMPT

Bạn đang làm trên `nppsale` (Next.js 14 App Router + Supabase). App đã có tích
hợp MISA meInvoice. Đọc hết dưới đây trước khi sửa dòng nào; mọi khẳng định đều
đã đối chiếu với mã tại `c45f82b`, nhưng repo có thể đã đi tiếp — **kiểm lại
từng chỗ trước khi tin**.

### 1. LỖI ĐANG CHẠY — sửa trước mọi thứ khác

**`invoices.misa_invoice_id` đang kiêm hai vai, và vai sau xóa mất vai trước.**

`publish/route.ts` ghi vào đó **RefID (GUID)** — và ghi rõ trong chú thích:

```ts
// misa_invoice_id luôn lưu RefID (GUID) — đây là khoá build URL admin MISA
const sentRefId = Array.isArray(payload) && payload[0]?.RefID ? payload[0].RefID : null
... misa_invoice_id: sentRefId,
```

`refresh-status/route.ts` đọc nó làm RefID để tra cứu, rồi **ghi đè bằng số hóa
đơn**:

```ts
const refId = invoice.misa_invoice_id || invoice.misa_lookup_code
...
if (invNo && !invNo.startsWith("<")) updates.misa_invoice_id = invNo   // ⚠
```

Hệ quả dây chuyền:

1. Lần refresh **đầu tiên** chạy đúng và ghi `InvNo` đè lên GUID.
2. Lần refresh **thứ hai** gọi `?refID=<số hóa đơn>` → MISA không biết → API trả
   `404 "MISA không trả về dữ liệu HD."` — một câu chỉ người dùng đi soi **MISA**,
   trong khi lỗi nằm ở chính chỗ này.
3. **Không bao giờ biết hóa đơn bị hủy hay bị thay thế trên MISA sau đó** — mất
   khóa là mất luôn đường hỏi.
4. URL admin `app.meinvoice.vn/sainvoice/edit/{RefID}` gãy.
5. Chốt idempotency của `publish` đã phải đi vòng bằng
   `uuidRe.test(misa_invoice_id)` — tức là **có người đã thấy cột này lúc thì
   GUID lúc thì không, và vá ở chỗ dùng thay vì chỗ gây ra**.

**Sửa: hai khóa, hai cột.** Đây là ràng buộc kiến trúc, không phải chuyện đặt tên.

| cột | giữ gì | ai ghi |
|---|---|---|
| `misa_ref_id` | GUID mình sinh, **BẤT BIẾN** | chỉ `publish` |
| `misa_inv_no` | số hóa đơn MISA cấp | chỉ `refresh` |
| `misa_inv_series` | ký hiệu (`1C25MHG`) | chỉ `refresh` |
| `misa_lookup_code` | TransactionID | chỉ `refresh` |

Migration phải **backfill**: `misa_ref_id = misa_invoice_id` cho những dòng còn
đúng khuôn UUID; dòng nào `misa_invoice_id` **không** khớp khuôn UUID thì RefID
đã mất — để `misa_ref_id = NULL`, chép giá trị đó sang `misa_inv_no`, và
**đếm rồi báo ra** số dòng mất khóa. Đừng dọn im lặng: chúng cần phát hành lại
hoặc gán tay, và không ai biết là bao nhiêu tờ thì không ai làm.

### 2. BỐN THỨ ĐANG THIẾU

**2.1 — `PublishStatus >= 1` không phải là "đã ký."**

```ts
if (publishStatus >= 1) nextStatus = "signed"   // ⚠
```

Đo trên hóa đơn thật ở hệ thống kia: `0` = nháp, `3` = **đã cấp mã**. Các giá
trị giữa là *đang phát hành · phát hành lỗi · chờ cấp mã · từ chối cấp mã* —
`>= 1` đang dán nhãn "đã ký" cho hóa đơn **bị từ chối cấp mã**. Và
`order-pipeline.tsx` đọc đúng cờ đó (`misa_status !== "signed"`) để quyết còn
phải xuất hóa đơn nữa không, nên một hóa đơn hỏng sẽ **biến khỏi việc cần làm**.

Đúng: chỉ `3` là đã phát hành. Giá trị lạ thì **không đoán** — lùi về mốc chắc
chắn là **mã CQT** (`InvoiceCode`): có mã ⇒ hợp lệ, chưa có ⇒ `"waiting_code"`.
Và nhớ: đơn vị dùng hóa đơn **không mã** thì không bao giờ có `InvoiceCode` —
phải đọc cờ `company_einvoice_config.misa_is_invoice_with_code` (app đã có sẵn
cột này), không thì mọi hóa đơn của họ đứng vĩnh viễn ở "chờ cấp mã".

**2.2 — Không có trục QUAN HỆ. Đây là rủi ro thuế, không phải thiếu tính năng.**

Code hiện chỉ đọc `InvNo`, `TransactionID`, `PublishStatus`. **Không đọc
`EInvoiceStatus`** — trục cho biết hóa đơn là bản mới / thay thế / điều chỉnh /
**bị thay thế** / bị điều chỉnh:

```
1 = Hóa đơn mới      3 = Hóa đơn thay thế     4 = Hóa đơn điều chỉnh
7 = Bị thay thế      8 = Bị điều chỉnh
```

Hai trục nằm ở **hai field khác nhau**, không phải hai cách đọc một field: đã đo
5 hóa đơn thật — `PublishStatus` giữ nguyên `3` ở cả 5, trong khi
`EInvoiceStatus` chạy 1/3/4/7/8 đúng theo quan hệ.

Bốn hệ quả bắt buộc:

- **"Bị thay thế" ⇒ hết hiệu lực**, bất kể đã cấp mã. **"Bị điều chỉnh" thì
  KHÔNG** — hóa đơn điều chỉnh chỉ cộng phần chênh, bản gốc vẫn còn hiệu lực và
  vẫn phải kê khai. Gộp hai loại là **khai thiếu doanh thu bản gốc**.
- Đọc được `OrgRefID` ⇒ **phải đánh dấu hóa đơn GỐC là "đã thay thế"**. Không
  làm thì hai hóa đơn cùng hiện "đã ký" cho một lần bán ⇒ doanh thu và thuế đầu
  ra khai **gấp đôi**.
- Phải đọc quan hệ từ `EInvoiceStatus`, **đừng chỉ suy ngược từ `OrgRefID`**:
  bản **bị** thay thế không hề mang `Org*` (đã đo — trống sạch), nên hóa đơn hết
  hiệu lực nào mà ta chưa thấy bản thay thế của nó sẽ vĩnh viễn không lộ.
- Hóa đơn **điều chỉnh mang số CHÊNH**, không phải tổng — đừng đem so với
  `invoices.total`.

`misa_status` đang có `CHECK (misa_status IN ('pending','sent','signed','error'))`
và `MisaStatus` ở `src/types/index.ts` — phải nới cả hai, thêm ít nhất
`cancelled` · `replaced` · `waiting_code` · `amount_mismatch`.

**2.3 — Không có vòng quét tự động.** `refresh-status` nhận **một `invoiceId`**
và phải có người bấm. Hóa đơn được ký trên MISA lúc 22h sẽ đứng ở `sent` cho tới
khi ai đó mở đúng tờ đó ra. Cần một vòng quét **hai lượt** — xem §3.

**2.4 — Không so tiền, không lưu ký hiệu/ngày/mã CQT.** Chỉ có `InvNo`. Số hóa
đơn mà thiếu **ký hiệu** thì không định danh được (hai ký hiệu khác nhau dùng
chung dải số là chuyện thường). Thiếu **`InvDate`** thì không biết kỳ thuế —
ngày phát hành khác ngày ghi sổ.

### 3. VIỆC CẦN LÀM

**3.1 Migration** (`supabase/migrations/0xx_einvoice_refid_split.sql`)

Tách `misa_ref_id` khỏi `misa_invoice_id`; thêm `misa_inv_no`, `misa_inv_series`,
`misa_inv_date` (date), `misa_invoice_code`, `misa_relation`,
`misa_org_ref_id`, `misa_last_checked_at`, `misa_note`,
`misa_no_locked` (boolean default false). Nới CHECK của `misa_status`. Backfill
như §1. Đặt `UNIQUE (org_id, misa_inv_series, misa_inv_no)` **partial** trên
`misa_inv_no IS NOT NULL` — hai hóa đơn cùng số là lỗi phải chặn ở tầng DB.
Nhớ RLS: bảng này đang bật RLS, cột mới không tự có policy nhưng phải kiểm lại
`GRANT`.

**3.2 Vòng quét — `POST /api/einvoice/sync` + cron**

App chưa có hạ tầng cron (không có `vercel.json`, `.github/workflows` chỉ có
`verify.yml`). Chọn **một** rồi khai rõ: Vercel Cron (`vercel.json` →
`/api/cron/einvoice-sync`) hoặc `pg_cron` + `pg_net` trên Supabase. Route phải
xác thực bằng `CRON_SECRET` (header), **không** dùng session người dùng.

**PHẢI có HAI lượt quét, không phải một:**

```sql
-- Lượt 1 — chưa có số: hỏi xem MISA cấp chưa
WHERE misa_ref_id IS NOT NULL AND misa_inv_no IS NULL
  AND issued_at >= now() - interval '60 days'

-- Lượt 2 — ĐÃ có số nhưng chưa ở trạng thái cuối
WHERE misa_ref_id IS NOT NULL AND misa_inv_no IS NOT NULL
  AND misa_status NOT IN ('cancelled', 'replaced')
  AND misa_no_locked = false
  AND issued_at >= now() - interval '60 days'
ORDER BY misa_last_checked_at NULLS FIRST
```

⚠ Thiếu **lượt 2** thì hóa đơn bị hủy hoặc bị thay thế trên MISA *sau khi đã cấp
số* không bao giờ bị phát hiện — bộ lọc lượt 1 loại chúng ra, nên cả hai nhánh
xử lý đó thành **code chết**. Sổ vẫn ghi một hóa đơn hợp lệ trong khi bên MISA
nó đã bị hủy.

⚠ `misa_no_locked`: hóa đơn mà người đã **gán tay** số thay thế thì `misa_ref_id`
trên đó vẫn trỏ hóa đơn **đã chết** — lượt 2 sẽ ghi số chết đè lên số người vừa
gán, lặng lẽ, mỗi lần chạy.

Trong vòng lặp:

- MISA không trả gì: **đã có số** ⇒ chỉ cập nhật `misa_last_checked_at`, **đừng
  hạ trạng thái đang đúng** (có thể lỗi tạm). **Chưa có số** ⇒ để nguyên `sent`.
- `InvNo` rỗng hoặc bắt đầu bằng `<` (MISA giữ chỗ `<Chưa cấp số>`) ⇒ coi như
  chưa có số. Code hiện đã bắt `startsWith("<")` — giữ.
- **Luôn** cập nhật `misa_last_checked_at`, kể cả khi chưa có số.
- Lỗi một hóa đơn **không được kéo theo cả lượt**: gom vào mảng, trả về, ghi
  `einvoice_logs` (bảng đã có).
- Giới hạn mỗi lượt (vd 200 tờ) — Vercel function có trần thời gian.

**3.3 So tiền ba vế**, dung sai 1đ, lệch thì `misa_status = 'amount_mismatch'`
và ghi `misa_note`. ⚠ **Chỉ so vế nào MISA THẬT SỰ trả số**: endpoint *danh
sách* của MISA không tách thuế (`TotalAmountWithoutVAT`/`TotalVATAmount` về
`0.0` ở cả 30/30 bản ghi thật đo được ở hệ thống kia). So số 0 đó với `subtotal`
thì **mọi** hóa đơn khớp đều bị gắn lệch — rổ cảnh báo đầy báo động giả, rồi
không ai nhìn cả cảnh báo thật. Tổng tiền thì luôn có nên luôn so, và một mình
nó đã đủ bắt lệch.

### 4. BẤT BIẾN — đúng bất kể stack

1. **Khóa nối phải sinh TRƯỚC và BẤT BIẾN.** Số hóa đơn về sau; ai ghi đè lên
   khóa là cắt đường hỏi lại.
2. **Không đoán.** Không chắc thì để trống + gắn nhãn "chưa xác định". Sai một
   số hóa đơn là sai báo cáo thuế, mà nó vẫn trông hợp lý trên màn hình.
3. **Không đè số người nhập tay** — nhưng **cũng không im lặng**: khác nhau thì
   ghi `misa_note` "sổ ghi X, MISA cấp Y" và nâng trạng thái lên lệch.
4. **Đừng gán `null` vào cột đang có giá trị tốt.** MISA có lúc trả thiếu
   `TransactionID` (hóa đơn "chờ cấp mã"); ghi đè `null` là **xóa trắng** mã tra
   cứu đang đúng ở lượt quét sau. Chỉ đưa vào object `updates` những khóa có giá
   trị — code hiện đã làm đúng kiểu này, giữ nguyên.
5. **Tách VẤN ĐỀ khỏi THÔNG TIN.** Gộp chung thì hóa đơn điều chỉnh — vốn hoàn
   toàn bình thường — bị đếm vào ô "lệch" và sinh cảnh báo giả.
6. **Chuẩn hóa khi so, giữ nguyên khi lưu.** `'00000123' == '123'`;
   `'1C25MHG' == 'C25MHG'` (bỏ số ở đầu ký hiệu). Cùng một file thật dùng lẫn
   hai dạng cho cùng dải số — không chuẩn hóa là mất dòng, im lặng.
7. **Thao tác hàng loạt phải XEM TRƯỚC**, và lệnh ghi mang **vân tay của đúng
   kế hoạch vừa xem**. Giữa lúc xem và lúc bấm, người khác sửa một ô là số đó
   được ghi mà chẳng ai thấy.

### 5. CÁCH LÀM

1. Đọc `src/lib/misa/client.ts`, `mapper.ts`, `src/app/api/einvoice/*`,
   migration 072→079 — rồi **nói lại cho tôi những chỗ mô tả trên đã lệch với
   repo hiện tại**. Đừng chép mù.
2. Sửa §1 trước, một PR riêng, có migration + backfill + số liệu "bao nhiêu dòng
   mất khóa".
3. §2, §3 sau.
4. Với **mỗi** ⚠ ở trên, viết một test `vitest` (repo đã có `vitest.config.ts`,
   `npm test`), rồi **thử phá**: sửa mã sản xuất cho hỏng đúng chốt đó và xác
   nhận test **ĐỎ**. Chốt nào phá mà test vẫn xanh thì test đó đang nói dối —
   sửa test, đừng bỏ qua.
5. `npm run verify` (typecheck + lint + test + build) phải xanh trước khi báo
   xong.
6. Không tự chạy migration lên Supabase production. Báo lại lệnh cần chạy.

---

## Phụ lục — bản Frappe/ERPNext của cùng cơ chế

App `ketoan` cài cơ chế này trên Frappe. Đọc để lấy chi tiết, đừng chép cấu trúc:

| việc | file |
|---|---|
| sinh RefID ở `before_submit`, dọn khi amend | `ketoan/api/misa_sync.py::ensure_ref_id` |
| vòng quét hai lượt, hai trục trạng thái, so tiền | `ketoan/api/misa_sync.py::_poll_pending` |
| khớp bốn tầng ref_id → txn → ký hiệu+số → MST/ngày/tiền | `ketoan/api/misa_reconcile.py::_match_one` |
| chép số nhập tay, 5 chốt chặn | `ketoan/api/misa_legacy.py` |
| chuẩn hóa số/ký hiệu | `ketoan/misa_integration/doctype/misa_invoice_snapshot/` |
| hợp đồng API MISA đã xác minh | `docs/misa/misa_api_contract.md` |

Hai thứ `nppsale` **chưa có mà nên có sau**: bảng **snapshot** hóa đơn kéo từ
MISA về (không có nó thì hóa đơn phát hành thẳng trên MISA — đúng loại hóa đơn
ngoài sổ kiểm toán sẽ hỏi — là **vô hình**), và **khớp bốn tầng** để đối soát hai
chiều. Tầng 4 (MST + ngày + tiền) chỉ được nhận khi **duy nhất một** hóa đơn
trùng cả ba vế, và luôn gắn "cần review".
