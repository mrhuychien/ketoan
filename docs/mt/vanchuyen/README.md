# Thay đổi cho app `vanchuyen` — chờ đưa sang repo kia

Phiên làm việc dựng phần này **không có quyền push** sang
`mrhuychien/vanchuyen` (proxy chặn: repo không nằm trong authorized set của
phiên). Nên bản vá cất tạm ở đây để công không mất khi container bị thu hồi.

## Cách đưa vào

```bash
git clone https://github.com/mrhuychien/vanchuyen.git
cd vanchuyen
git am /đường/dẫn/ketoan/docs/mt/vanchuyen/0001-VC-HH-hang-quay-ve.patch
# hoặc:  git apply --3way <file>
```

Rồi bên site:

```bash
bench --site <site> migrate      # BẮT BUỘC: có DocType mới + cột mới
bench build --app vanchuyen
bench restart
```

## Vì sao phải `bench migrate`, không chỉ `bench build`

Bản vá thêm **DocType con mới** (`Su Co Hang Ve`) và **14 field** vào
`Su Co Van Chuyen`. Cột chỉ được tạo khi migrate. Và `modified` của DocType
JSON **đã được bump** — không bump thì `bench migrate` coi file là cũ và bỏ
qua re-import, cột mới không bao giờ xuất hiện mà cũng không báo lỗi gì.

## Ăn khớp với repo `ketoan`

| `vanchuyen` ghi | `ketoan` đọc |
|---|---|
| `Su Co Van Chuyen.loai_su_co` (10 giá trị) | khóa của bảng chứng từ, cùng `huong_xu_ly` |
| `Su Co Van Chuyen.huong_xu_ly` | **khóa chính** — `Hủy đơn` chỉ tồn tại ở cột này |
| `Su Co Van Chuyen.ngay_phat_sinh` | mốc tính **tuổi việc** |
| `Su Co Hang Ve.*` (3 số lượng) | chi tiết mã hàng, tiền mất trên đường |
| `Su Co Van Chuyen.stock_entry` | bằng chứng hàng đã nhập lại kho |

`ketoan` **chỉ đọc**, không ghi vào bảng của `vanchuyen`. Ghi bằng
`db.set_value` sẽ bỏ qua `_stamp_si()` và cờ `custom_co_su_co` trên Sales
Invoice kẹt vĩnh viễn.

## Còn thiếu (chưa làm trong bản vá này)

- Ô nhập bảng mã hàng trên portal `#/su-co` — hiện chỉ sửa được trên Desk.
- Quyền `Su Co Van Chuyen` mới cấp `System Manager`; `su_co.py` đi vòng bằng
  guard "có quyền write Sales Invoice" + `ignore_permissions`. Role
  `Điều Phối Vận Chuyển` chỉ có DocPerm trên `Chuyen Xe`, nên người điều phối
  đúng nghĩa **chưa mở được màn sự cố**. Phải cấp DocPerm riêng rồi nới
  `_require()` — chưa làm vì đụng mô hình quyền của cả app.
- Quyền `Stock Entry` cho người lập phiếu nhập lại kho.
