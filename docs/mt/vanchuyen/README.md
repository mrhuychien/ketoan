# Thay đổi cho app `vanchuyen`

## ✅ ĐÃ ĐƯA SANG REPO KIA — đừng `git am` lại

Bản vá `0001-VC-HH-hang-quay-ve.patch` **đã nằm trong**
`mrhuychien/vanchuyen`, nhánh `claude/mt2-vanchuyen-hanghoan-gtbyb1`,
commit `11d4e57` (*VC-HH: theo dõi hàng quay về + bồi thường nhà xe, và 3 lý do
kế toán*). Áp lại là dính xung đột chứ không phải áp trùng vô hại.

File `.patch` giữ lại làm dấu vết: phiên dựng nó **không có quyền push** sang
repo đó (proxy chặn — repo không nằm trong authorized set của phiên), nên bản vá
phải cất tạm ở đây để công không mất khi container bị thu hồi. Phiên sau có
quyền và đã đưa sang.

Muốn xem nội dung mà không cần clone:

```bash
git --no-pager show --stat 11d4e57      # trong repo vanchuyen
# hoặc, chỉ đọc:
less docs/mt/vanchuyen/0001-VC-HH-hang-quay-ve.patch
```

## Việc bên site — BẮT BUỘC `migrate` CẢ HAI APP

```bash
bench --site <site> migrate            # cả vanchuyen lẫn ketoan
bench build --app vanchuyen --app ketoan
bench restart
```

## Vì sao phải `bench migrate`, không chỉ `bench build`

Bản vá thêm **DocType con mới** (`Su Co Hang Ve`) và **14 field** vào
`Su Co Van Chuyen`; phía `ketoan` cũng có DocType mới (`MT Hang Hoan`). Cột chỉ
được tạo khi migrate. Và `modified` của DocType JSON **đã được bump** — không
bump thì `bench migrate` coi file là cũ và bỏ qua re-import, cột mới không bao
giờ xuất hiện mà cũng không báo lỗi gì.

## Ăn khớp với repo `ketoan`

| `vanchuyen` ghi | `ketoan` đọc |
|---|---|
| `Su Co Van Chuyen.loai_su_co` (10 giá trị) | cột "Việc" trên màn Hàng hoàn |
| `Su Co Van Chuyen.huong_xu_ly` | **khóa chính** — `Hủy đơn` chỉ tồn tại ở cột này |
| `Su Co Van Chuyen.ngay_phat_sinh` | mốc tính **tuổi việc** (`MT Hang Hoan.ngay_xay_ra`) |
| `Su Co Van Chuyen.hang_ve_trang_thai` · `ngay_hang_ve` | trạng thái hàng vật lý |
| `Su Co Hang Ve.*` (3 số lượng) | chi tiết mã hàng, tiền mất trên đường |
| `Su Co Van Chuyen.stock_entry` | bằng chứng hàng đã nhập lại kho |

`ketoan` **chỉ đọc**, không ghi vào bảng của `vanchuyen`. Ghi bằng
`db.set_value` sẽ bỏ qua `_stamp_si()` và cờ `custom_co_su_co` trên Sales
Invoice kẹt vĩnh viễn. `hoan_check` mục 7 canh đúng chỗ này.

Và `ketoan` **KHÔNG lọc theo `Su Co Van Chuyen.trang_thai`**: cột đó thuộc điều
hành, nghĩa là *vận chuyển xong*, không phải *giấy tờ xong*. Màn Hàng hoàn hiện
nó ra để kế toán biết điều hành đang ở đâu, nhưng không mệnh đề `WHERE` nào đọc
nó — xem `mt_hoan.py` và `hoan_check` mục 4.

Chiều ngược lại KHÔNG có: `ketoan` không đòi hỏi site phải cài `vanchuyen`.
`MT Hang Hoan.su_co` là **Data chứ không phải Link**, và ô "Chưa vào sổ" tự tắt
kèm câu giải thích khi thiếu bảng `Su Co Van Chuyen`.

## Còn thiếu (chưa làm trong bản vá này)

- Ô nhập bảng mã hàng trên portal `#/su-co` — hiện chỉ sửa được trên Desk.
- Quyền `Su Co Van Chuyen` mới cấp `System Manager`; `su_co.py` đi vòng bằng
  guard "có quyền write Sales Invoice" + `ignore_permissions`. Role
  `Điều Phối Vận Chuyển` chỉ có DocPerm trên `Chuyen Xe`, nên người điều phối
  đúng nghĩa **chưa mở được màn sự cố**. Phải cấp DocPerm riêng rồi nới
  `_require()` — chưa làm vì đụng mô hình quyền của cả app.
- Quyền `Stock Entry` cho người lập phiếu nhập lại kho.
