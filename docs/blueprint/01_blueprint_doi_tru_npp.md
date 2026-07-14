# Blueprint — Số hóa workflow Kế toán NPP (đối trừ công nợ + hồ sơ)

> Trạng thái: **CHỜ DUYỆT**. Nguồn: mind map workflow Kế toán NPP (5 nhánh).
> Quyết định đã chốt: Trả hàng = **Credit Note**, Chiết khấu = **JE**; chiết khấu
> **chờ hóa đơn NPP** mới hạch toán; **kế toán NPP tự xác nhận** nhận đủ hàng;
> hồ sơ khách = **đính kèm trên Customer** (không DocType riêng).

## Đối chiếu 5 nhánh → hạng mục build

| Nhánh | Số hóa |
|---|---|
| 1. Hàng trả lại | **Hồ sơ đối trừ** loại "Trả hàng": Chờ nhận hàng → Chờ HĐ NPP → Đã nhận HĐ → Đã trừ nợ (Credit Note nháp) |
| 2. Hàng đi → xuất HĐ | Cảnh báo **DN chưa xuất hóa đơn** trong bàn NPP |
| 3. Chiết khấu, KM | Đổi flow: đủ điều kiện → **tạo hồ sơ đối trừ** (Chờ HĐ NPP) → nhập số HĐ → **JE nháp** (giữ marker chống trùng) |
| 4. Thanh toán | Đã có (đến hạn/quá hạn, Payment Entry, nhắc nợ) — không đổi |
| 5. Quản lý KH | Khối **Hồ sơ đính kèm** trong 360° khách: list file của Customer + upload |

## DocType mới: `Ketoan Doi Tru NPP` (hồ sơ đối trừ công nợ)

- Naming: `DT-.YYYY.-.#####`. Không submittable — vòng đời bằng `status`.
- Fields (ASCII): `loai` (Select: Tra Hang / Chiet Khau KM) · `customer` (Link, lọc nhóm NPP)
  · `ngay_tao` (Date) · `gia_tri` (Currency) · `dien_giai` (Small Text)
  · `status` (Select: Cho Nhan Hang / Cho Hoa Don / Da Nhan Hoa Don / Da Tru Cong No / Huy)
  · `da_nhan_du_hang` (Check) + `ngay_nhan_hang` (Date)
  · `so_hd_npp` (Data) + `ngay_hd_npp` (Date) — hóa đơn NPP xuất lại (scan đính kèm attachment)
  · `thang_ck` (Data YYYY-MM, chỉ chiết khấu — mang marker chống trùng)
  · `ref_doctype`/`ref_name` (link chứng từ trừ nợ: Sales Invoice return hoặc Journal Entry)
- Permissions: Ke Toan NPP (r/w/c), Ke Toan Truong (full), System Manager.

## Luồng trạng thái

**Trả hàng:** tạo hồ sơ (Cho Nhan Hang) → kế toán tick "đã nhận đủ hàng" (Cho Hoa Don)
→ nhập số HĐ NPP + đính scan (Da Nhan Hoa Don) → bấm "Tạo Credit Note (nháp)"
(Sales Invoice `is_return=1`, remarks ghi số HĐ NPP + mã hồ sơ; kho/hàng do Credit Note
update_stock hoặc kho xử lý riêng) → hạch toán/trưởng submit → hệ thống stamp
(Da Tru Cong No, ref → Credit Note).

**Chiết khấu (flow mới):** tab Chiết khấu giữ phần kiểm tra đủ điều kiện; nút đổi thành
"**Tạo hồ sơ đối trừ**" (Cho Hoa Don, giá trị = tiền CK, thang_ck) — KHÔNG tạo JE ngay.
Khi nhận HĐ NPP: nhập số HĐ → "Tạo bút toán" (JE nháp Nợ 6412/Có 131, remark kèm
marker [CK2-...] + số HĐ NPP) → Da Tru Cong No. Chống trùng: 1 NPP/tháng 1 hồ sơ CK.

## API (guard_npp, trừ ghi chú)

- `doitru.get_list(status?, loai?)` · `doitru.create_case` · `doitru.update_case`
  (tick nhận hàng, nhập số HĐ — chuyển status tương ứng)
- `doitru.make_credit_note(case)` → SI return DRAFT · `doitru.make_journal_entry(case)` → JE DRAFT
- `doitru.get_unbilled_dn()` — Delivery Note đã submit chưa billed (cảnh báo nhánh Hàng đi)
- `customerdocs.list/upload` (guard_sales_any) — file đính kèm Customer cho 360°

## UI (bàn Kế toán NPP)

- Trang Đối chiếu NPP thêm **tab "Đối trừ"**: bảng hồ sơ theo trạng thái (pill filter),
  nút "+ Hồ sơ trả hàng", thao tác theo trạng thái ngay trên dòng; badge cảnh báo
  hồ sơ treo > 7 ngày (config `doitru_stale_days` trong Settings).
- Tab "Chiết khấu": nút đổi thành tạo hồ sơ; cột trạng thái đọc từ hồ sơ.
- Bàn NPP thêm mục Báo cáo: "DN chưa xuất hóa đơn".
- 360° khách: khối "Hồ sơ khách hàng" (attachments + upload).

## Ngoài phạm vi đợt này
Kho tự xác nhận (tài khoản thủ kho), ký số/OCR hóa đơn NPP, hợp đồng có nhắc hết hạn
(nâng lên DocType khi cần), tự đối chiếu hóa đơn NPP với HĐĐT.
