# Blueprint — Số hóa workflow Kế toán NPP (bản chốt)

> Trạng thái: **ĐÃ DUYỆT** (user chỉnh: không DocType mới — bám chứng từ gốc).

## Nguyên tắc
Trạng thái vòng đời nằm ngay trên chứng từ ERPNext, suy ra từ `docstatus` + đính kèm:

| Trạng thái | Điều kiện |
|---|---|
| **Chờ hóa đơn NPP** | Chứng từ NHÁP, chưa có file đính kèm |
| **Chờ KTT duyệt** | Chứng từ NHÁP, ĐÃ đính kèm hóa đơn NPP |
| **Đã trừ công nợ** | Đã submit |

## 3 luồng đã chốt
1. **Trả hàng**: tạo **Sales Invoice trả về (is_return) NHÁP** (từ hóa đơn gốc) → chờ NPP
   xuất hóa đơn → **đính kèm** hóa đơn vào SI nháp → **KTT kiểm soát → submit** → trừ công nợ.
2. **Chiết khấu**: giữ flow hiện tại **tạo JE nháp ngay** (marker [CK2-...]) → NPP xuất hóa đơn
   → **đính kèm vào JE nháp** → **KTT duyệt → submit** → trừ công nợ.
3. **Hàng đi**: quy ước — Sales Invoice **chưa điền `vn_einvoice_number`** = **chưa xuất
   hóa đơn điện tử** → cảnh báo/báo cáo trong bàn NPP.

## Hạng mục build
- `api/doitru.py` (guard_npp; duyệt = guard_manager):
  `get_cases` (SI return + JE chiết khấu, kèm số file đính kèm + trạng thái suy ra) ·
  `get_return_sources` + `create_return` (make_return_doc từ hóa đơn gốc → nháp) ·
  `upload_invoice_attachment` (đính hóa đơn NPP vào chứng từ nháp) ·
  `approve_case` (KTT: kiểm có đính kèm rồi submit) ·
  `get_missing_einvoice` (SI submitted, khách NPP, `vn_einvoice_number` rỗng).
- UI: trang Đối chiếu NPP thêm **tab "Đối trừ"** (bảng hồ sơ + tạo trả hàng + upload +
  nút Duyệt cho KTT) và khối **"Chưa xuất HĐĐT"**.
- 360° khách: khối hồ sơ đính kèm Customer (xem + upload) — nhánh Quản lý KH.
