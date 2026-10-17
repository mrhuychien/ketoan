# Ketoan — Portal Kế toán Tác nghiệp

Custom app cho **Frappe/ERPNext v16**. Là **lớp tác nghiệp** ngồi trên ERPNext
(system of record): tổ chức quanh **hàng đợi công việc + cảnh báo**, đọc dữ liệu
thật và **deep-link bấm thẳng xuống Desk** để thao tác. **Human-in-loop** — portal
phát hiện · phân tích · gợi ý; người quyết định và ấn nút.

> Xây theo phong cách **NPP** (nextcode + frappe-portal-spa + frappe-sales-analytics
> + frappe-app-shipping-gotchas). Blueprint: [`docs/blueprint/00_blueprint_p0.md`](docs/blueprint/00_blueprint_p0.md).

## P0 — Bàn làm việc Công nợ & Quỹ

- **Dashboard hôm nay**: tổng nợ, quá hạn theo rổ, #NPP vượt hạn mức, số dư quỹ, khoản thu treo.
- **Công nợ phải thu**: bảng kê theo khách + tuổi nợ (aging) + DSO.
- **360° khách hàng**: hóa đơn outstanding, hạn mức, khoản thu chưa khớp.
- **Sổ quỹ & dòng tiền**: số dư TK tiền mặt/tiền gửi, thu/chi theo ngày, list giao dịch.
- **Cảnh báo**: vượt hạn mức · quá hạn >30/>60/>90 · khoản thu chưa khớp · quỹ tiền mặt âm.
- **Tiện ích**: tìm khách → 360°; **nhập sổ quỹ** nhanh (tạo Journal Entry DRAFT, kèm QR VietQR).

UI là **SPA portal no-build** (vanilla JS, hash router, ES module code-split) phục vụ tại
`/ketoan`. Backend là **whitelisted method Python có guard** (không Server Script rải rác).

## Theo dõi thu hồi — hàng siêu thị xuất trả về công ty

Nối tiếp app **vanchuyen**: bên đó tạo yêu cầu xuất trả (`Lo Thu Hoi`) và chạy 3 chặng
vận chuyển *Tạo yêu cầu → Đã lấy hàng → Đã nhận hàng*; kế toán nhận tiếp từ chặng
**Đã nhận hàng** với DocType riêng `Kiem Hang Thu Hoi` (tên = mã lô):
*Đang kiểm → Đã kiểm hàng → Đã nhập chứng từ → Xong*. Blueprint:
[`docs/thu-hoi/blueprint-thu-hoi.md`](docs/thu-hoi/blueprint-thu-hoi.md).

- **Tab "Thu hồi"** (`#/thu-hoi`): mọi lô bên vận chuyển + chặng gộp, lọc theo chặng,
  tìm lô / khách / điểm / số phiếu siêu thị; bảng trên máy tính, thẻ trên điện thoại.
- **Kiểm hàng trên điện thoại** (`#/kiem-hang/<lô>`, dựng theo màn Ghi hộp app sx): quét
  mã vạch (camera / súng quét / gõ tay) hoặc chọn mã → bàn số phím to có tab Thùng/Hộp →
  lưu ngay từng lần; quét lại mã đã có là cộng thêm; chạm số để sửa, ✕ để xóa.
  **Đếm mù**: số siêu thị khai chỉ hiện sau khi chốt.
- **Hóa đơn trả về**: sau khi chốt, chọn hóa đơn gốc (gợi ý cùng khách, ưu tiên cùng điểm
  giao) → lập **Sales Invoice trả về (nháp)** bằng `make_return_doc`, `update_stock = 0`,
  không vượt số còn được trả của từng dòng gốc; "Cập nhật" dựng lại các bản nháp theo
  số kiểm mới, xóa được bản nháp. Ghi sổ (submit) làm trên Desk.
- **Trạng thái tự đi**: hook `Sales Invoice` (insert/update/submit/cancel/trash) tính lại
  chặng của phiếu kiểm — đủ số và mọi hóa đơn đã ghi sổ thì **Xong**. Không lập hóa đơn
  (hàng hủy, đổi hàng…) thì chỉ Kế toán trưởng kết luận được, có ghi lý do.
- Quyền: kế toán bán hàng (NPP / MT / Du lịch) + KTT; lập hóa đơn dùng **quyền tạo Sales
  Invoice của chính người bấm**. Ketoan chỉ **đọc** bảng của vanchuyen (đọc mềm — chưa cài
  vanchuyen thì tab rỗng, không lỗi), không bao giờ ghi.
- Kiểm không cần bench: `python3 docs/verified/thu_hoi_check.py`.

## Cài đặt

```bash
# trong frappe-bench/
bench get-app ketoan <repo-url>
bench --site <site> install-app ketoan
bench --site <site> migrate
bench build --app ketoan
bench restart
```

Mở portal tại: `https://<site>/ketoan`

### Vai trò (workspace) — 1 user chọn nhiều
Nav portal tổ chức theo **vai trò**; mỗi vai trò 1 trang riêng gồm 3 mục
*Tác nghiệp (deep-link Desk) · Báo cáo · Công cụ*, cô lập theo vai trò:

| Role | Bàn làm việc |
|---|---|
| `Ke Toan Ban Hang` | Công nợ phải thu, đối chiếu NPP, thu tiền khách |
| `Ke Toan Mua Hang` | Công nợ phải trả, hóa đơn/thanh toán NCC |
| `Ke Toan Tien Luong` | Tính lương (quét·duyệt·xuất Excel·in PDF) |
| `Ke Toan Hach Toan` | Quỹ tiền mặt/ngân hàng, bút toán, nhập sao kê |
| `Ke Toan Truong` | Tổng quan toàn phòng, cảnh báo, cấu hình (xem tất cả) |

5 role tạo tự động khi `install-app`/`migrate` (xem `ketoan/install.py`). Kế toán trưởng
(+ Accounts Manager/System Manager) đi qua mọi guard. Cấu hình tại **Ketoan Portal Settings**.

## Cấu trúc

```
ketoan/
├── hooks.py            # app config, jinja, after_install
├── install.py          # tạo roles + cấp quyền (idempotent)
├── utils.py            # jinja helpers (format_vnd)
├── api/                # whitelisted methods (read-only + cashbook)
├── ketoan/doctype/ketoan_portal_settings/
├── patches/v0_0_1/
├── public/ketoan/      # SPA: shell, lib, components, views  -> /assets/ketoan/
└── www/ketoan.{html,py}
```
