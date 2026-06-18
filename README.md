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

### Roles
- `Ke Toan Cong No` — kế toán công nợ (xem công nợ/quỹ, cảnh báo, nhập sổ quỹ).
- `Ke Toan Truong` — full quyền (thêm mua hàng & tài chính, cấu hình ngưỡng).

Hai role được tạo tự động khi `install-app` (xem `ketoan/install.py`). Cấu hình ngưỡng
cảnh báo tại **Ketoan Portal Settings** (Single).

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
