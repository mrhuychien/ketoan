# SOP Kế toán Kênh Siêu thị (MT) — Công ty CP Hoàng Giang

> Bản 1.0 · Soạn 20/08/2026 (các quyết định mở đã chốt cùng ngày) · Áp dụng cho: 1 kế toán phụ trách toàn bộ kênh MT
> Nguồn: buổi làm việc với kế toán 20/08/2026 + 17 file chứng từ thật + app `ketoan` (portal `/ketoan`)

---

## 0. Nguyên tắc chung

**Hệ thống và vai trò từng hệ:**

| Hệ | Vai trò |
|---|---|
| ERPNext v16 (+ app `ketoan`, portal `/ketoan`) | System of record. Mọi phát sinh, đối soát, bút toán ghi tại đây. Thay thế toàn bộ file Excel theo dõi ngoài. |
| MISA meInvoice | Phát hành hóa đơn điện tử (hàng, điều chỉnh, chiết khấu). Số hóa đơn tự đổ về ERPNext qua MISA Invoice Snapshot. |
| Portal của chuỗi (Win, AEON…) | Nguồn phiếu nhập kho / chứng từ chuỗi. |
| Email | Kênh nhận file doanh số, TBCK, chi tiết thanh toán; gửi hóa đơn CK (Lotte). |

**Quy ước cứng:**

1. **Khóa khớp** = ký hiệu + số hóa đơn MISA, đã chuẩn hóa. `C26THG` và `1C26THG` là MỘT ký hiệu (chuỗi ghi tùy tiện). Khóa phụ: số PO, mã store, cặp ngày + tiền (riêng Emart vì không cấp ký hiệu).
2. **Customer = chuỗi** (1 Customer/chuỗi). Điểm siêu thị = Address (`shipping_address_name`) kèm thông tin xuất hóa đơn của từng điểm (MST chi nhánh với Lotte).
3. **Hạn thanh toán cấu hình theo Customer**, tính từ **ngày hóa đơn**. Mặc định 45 ngày; Winmart 60. Lưu ý số thực tế trong chứng từ chuỗi: Central Retail A030/A040 (30/40 ngày, tùy pháp nhân), AEON E30 — không hardcode 45.
4. **Mọi bút toán tiền = Journal Entry (JE)**, kể cả ghi nhận thanh toán (không dùng Payment Entry). JE sinh ra ở trạng thái **Draft** từ portal, kế toán **duyệt từng cái hoặc hàng loạt** ngay trên portal. Dòng Có/Nợ 131 luôn reference đúng Sales Invoice để trừ outstanding.
5. **Riêng hàng trả/móp lỗi** đi bằng chứng từ trả hàng của ERPNext (có tác động kho), không ghi JE tay.
6. **Bảng kê chiết khấu** đánh số theo MỘT dãy chung toàn MT: `số/BKCK/HG-MT`, tăng liên tục qua năm, không reset (tham chiếu thực tế: 155 → 11/2025 … 300 → 7/2026). Trên ERPNext: app gợi ý số kế tiếp (số lớn nhất + 1), kế toán sửa được — không phải khai báo gì. Giữ số bảng kê riêng, không dùng số hóa đơn MISA thay thế: hóa đơn phải dẫn chiếu "kèm theo bảng kê số …, ngày …" ngay tại thời điểm xuất, khi chưa có số hóa đơn.

---

## 1. Vòng đời tháng — 5 bước chung mọi chuỗi

1. **Xuất hóa đơn bán** — theo PO/đơn giao (hệ PO tự động đã có). Riêng Winmart: chỉ xuất sau khi phiếu nhập kho khớp (xem 2.2).
2. **Móp lỗi / trả lại** — làm chứng từ trả hàng trên ERPNext (Central Retail: giữ cùng số PO) → xuất **hóa đơn điều chỉnh** trên MISA → snapshot tự cập nhật; kiểm tra hóa đơn gốc đã gắn hóa đơn điều chỉnh.
3. **Chiết khấu** — nhận file doanh số/TBCK → đối chiếu → lập **bảng kê BKCK** → xuất **hóa đơn CK** trên MISA → JE (chi tiết mục 3).
4. **Đối soát thanh toán** — nhận file chi tiết thanh toán → nạp vào portal `/ketoan` (màn MT) → hệ tự khớp từng dòng → xử lý ngoại lệ → duyệt JE (thanh toán + các khoản trừ) → hóa đơn được đánh dấu đã thanh toán.
5. **Công nợ đến hạn** — theo dõi report công nợ MT; nhắc các hóa đơn sắp/quá hạn theo term của từng Customer.

---

## 2. Chi tiết theo chuỗi

### 2.1 Central Retail (BigC/GO! — pháp nhân EB, tối thiểu 2 mã: 3003172, 3006634)

- **Xuất HĐ**: theo PO.
- **Móp lỗi**: trả hàng ERPNext **cùng số PO** → HĐ điều chỉnh MISA → cập nhật sổ.
- **Chiết khấu**: nhận file doanh số qua mail (cột `RB_GROUP / RB_RATE / IM_VALUE / RB_VALUE`, ~1.800 dòng/tháng, có dòng âm cho hàng trả — trừ thẳng vào cơ sở tính CK).
  - **Mình chỉ xuất nhóm `Discount for store`** (chiết khấu doanh số).
  - Các nhóm phí (`Fee for EBS`, `Fee for store`, `Support for store`) do **EB xuất hóa đơn** — sẽ xuất hiện thành dòng `D1` trong file thanh toán → hạch toán JE phí (mục 4).
  - Lập **1 bảng kê BKCK / pháp nhân EB / tháng** (dòng = từng hóa đơn + tiền CK, cột Ghi chú = số PO) → xuất **1 hóa đơn CK tổng** trên MISA.
- **Thanh toán**: file SAP — `K1` = hàng hóa, `D1` = phí + dòng `TRA HANG`, `KS`; bỏ dòng `Overall Result` và `Terms of Pmnt = Result`. Số HĐ ở cột `Reference` dạng `C26THG|4675`.
- **Hạn**: theo pháp nhân (A030 = 30 ngày, A040 = 40 ngày) — cấu hình đúng trên Customer.

### 2.2 WinCommerce (Winmart)

- **Xuất HĐ**: CHỈ sau khi có phiếu nhập kho trên hệ Win (đang kéo tự động) và khớp **PO + hàng hóa** với đơn trên ERPNext. Lệch số lượng → làm xuất trả phần chênh trên ERPNext, xuất hóa đơn theo số thực nhận.
- **Hồ sơ thanh toán** (1 mẫu duy nhất): bảng kê gồm `Code` (mã NCC 2007766), `PO VCM`, ký hiệu, số HĐ, ngày, tiền trước VAT, VAT, tổng, và cột **Tên File PDF** theo chuẩn `YYYYMMDD_2007766_<stt>` — file PDF hóa đơn nộp kèm phải đặt tên đúng chuẩn này.
- **Chiết khấu**: mình xuất hóa đơn CK (quy trình BKCK, mục 3).
- **Thanh toán**: file nhiều Table; dữ liệu ở Table 5/7/8, bỏ dòng `**********`; mỗi dòng có `Số đối soát` (mã đợt); số HĐ dạng `1C26THG#1730`.
- **Hạn**: 60 ngày từ ngày hóa đơn.

### 2.3 LOTTE

- **TBCK hàng tháng** (kiêm biên bản bù trừ công nợ): đối chiếu `Pur Amt` từng siêu thị với file doanh số line-level (cột `Pur fg` = `nhập` / `hàng trả lại`; `Fill in date` = `NOT RECEIVE` là hàng chưa nhận) và với hóa đơn trên ERPNext + MISA. Lệch → truy hàng trả lại / móp lỗi trước khi xuất.
- **Chỉ xuất các khoản `Invoice by = S`** (CHIET KHAU CO BAN). Khoản `L` (PHI BAN HANG, PHI DICH VU KHAC) do **Lotte xuất** → treo chờ khớp trong file thanh toán → JE phí.
- **BKCK riêng từng chi nhánh** (bên mua = MST chi nhánh, thông tin lấy từ Address của store) → xuất **1 hóa đơn CK / chi nhánh** → gửi về `hoadonchietkhau@lotte.vn`. Thắc mắc TBCK: `thongbaochietkhau@lotte.vn`.
  - Đối chiếu mẫu đã kiểm chứng: TBCK 3/2026 West Lake CK cơ bản 1.777.200 = BKCK số 229 = HĐ CK; BKCK 300 (7/2026) 5.546.000 = HĐ 00006958.
- **Thanh toán**: file theo store, trộn HĐ hàng (2 cột `Tax No` + `Invoice No`) + dòng trừ (CK/phí, tiền âm) + dòng `NET OFF REGULAR` (dòng cân đối, không phải hóa đơn — đối chiếu bản chất trước khi ghi JE); bỏ dòng `SUB SUM`. **Một file có thể chứa nhiều `Payment Date` → tách theo từng ngày thanh toán.**
- **Hạn**: 45 ngày.

### 2.4 Saigon Co.op (Coopmart)

- **Mình không xuất hóa đơn CK.** Chiết khấu **17,75% trừ tại nguồn trên từng hóa đơn** ngay trong bảng kê thanh toán — khoản này do **Co.op xuất hóa đơn** cho mình, hạch toán như phí chuỗi xuất (mục 4).
- Mỗi pháp nhân Co.op (chi nhánh Liên hiệp, các công ty TNHH thành viên — ~8 đơn vị) gửi **1 bảng kê riêng** (1 sheet/bảng kê, có số chứng từ + ngày TT riêng).
- **Bẫy đọc file**: cột `THANH TOÁN` chỉ điền ở dòng đầu mỗi nhóm và là tiền CẢ NHÓM; số HĐ NCC gõ tay (dạng `'P0007272`) — hệ khớp bằng số + ngày + tiền, các dòng "cần review" phải kiểm tay. Dùng 3 số kiểm ở header (Tổng Tiền / Tổng CK / Tổng Thanh Toán) để chốt.
- **JE**: phí 17,75% (căn cứ hóa đơn Co.op) + thanh toán, theo từng bảng kê. **Hạn**: 45 ngày.

### 2.5 Emart (THISO Retail)

- **DEADLINE CỨNG: xuất hết hóa đơn hàng giao trong tháng TRƯỚC NGÀY 5 tháng sau** (hàng FMCG; tươi sống trước ngày 3). Trễ = Emart không xử lý thanh toán đúng hạn.
- **Rebate Settlement** cuối tháng: `Rebate` (Monthly Discount 3%, Settlement Type = Vendor Tax Invoice) → **mình xuất** theo quy trình BKCK. Các dòng `Fee` (~8% cộng lại, Settlement Type = E-mart Tax Invoice) → **Emart xuất hóa đơn** → JE phí. **Không phản hồi trong 5 ngày = coi như đồng ý số liệu.**
- **Thanh toán**: 1 file 3 khối — `I0` chiết khấu, `I1` phí hỗ trợ (có số hóa đơn Emart), `RE` hóa đơn hàng của mình; bỏ các dòng cộng (`chiết khấu`, `phí hỗ trợ`). Emart **không cấp ký hiệu** hóa đơn → mọi dòng khớp bằng số + ngày + tiền và mặc định "cần review".

### 2.6 AEON

- **Hạn**: E30. File thanh toán là workbook nhiều sheet: `Doc` (hóa đơn, dạng `1-C26THG-00004246`, kèm store + ngày giao/trả), `Costdet` (phí — có số hóa đơn AEON `1-K26T…` xuất cho mình), `DcCharges` (phí DC 3,5%/2,6% theo từng phiếu giao), `Costsumm/Rebsumm` (bảng mã khoản trừ), dòng `Deduction` + `Net Payment` để chốt.
- Phí AEON xuất → JE phí. Chiết khấu doanh số (nếu phát sinh) → quy trình BKCK.

### 2.7 Fuji (Fujimart — BRG/Sumitomo)

- File đối chiếu 2 phần: bảng **HĐTC ↔ số phiếu nhập kho + mã kho** (khớp từng cặp), và bảng tổng theo hóa đơn. Khoản trừ `Hỗ trợ vận chuyển 3%`: **Fuji xuất hóa đơn** → JE phí (mục 4).

### 2.8 Mega Market

- File doanh số theo hóa đơn (`1C26THG_00004450`) + ngày nhận hàng + **cut-off cuối tháng** → tính CK → quy trình BKCK.

### 2.9 Các chuỗi khác

Theo đúng pattern chung 5 bước; hạn mặc định 45 ngày; cơ chế CK xác định theo chứng từ chuỗi gửi (mình xuất theo BKCK, hay chuỗi xuất phí, hay trừ tại nguồn).

---

## 3. Quy trình chiết khấu — bảng kê BKCK (chuẩn chung)

1. **Nhận và nạp** file doanh số / TBCK / Rebate Settlement vào phần đệm trên portal (giai đoạn chuyển tiếp: vẫn thao tác Excel theo mẫu cũ).
2. **Đối chiếu**: doanh số chuỗi báo ↔ hóa đơn ERPNext ↔ MISA snapshot. Lệch → truy hàng trả lại, móp lỗi, hóa đơn điều chỉnh. (Lotte bắt buộc rà từng store trước khi xuất.)
3. **Lập bảng kê**: lấy **số kế tiếp** dãy `/BKCK/HG-MT`. Central Retail: gộp 1 bảng kê/pháp nhân. Lotte: tách 1 bảng kê/chi nhánh. Mẫu in giữ đúng format hiện hành (Số hóa đơn · Ký hiệu · Ngày · Tiền trước thuế · Thuế GTGT · Tổng · Ghi chú/PO).
4. **Xuất hóa đơn CK trên MISA**: 1 dòng duy nhất *"Chiết khấu … tháng MM.YYYY kèm theo bảng kê số NNN/BKCK/HG-MT ngày …"*, ĐVT `Tháng`, SL 1, tổng tiền **âm**, thuế 8%, hình thức thanh toán **Đối trừ công nợ**. Bên mua đúng pháp nhân/chi nhánh trên bảng kê.
5. **Hoàn tất**: ghi số hóa đơn CK vào bảng kê (snapshot sẽ tự vớt về), gửi hóa đơn cho chuỗi nếu yêu cầu (Lotte qua email), sinh **JE chiết khấu** → duyệt.

---

## 4. Bút toán chuẩn (JE — sinh Draft từ portal, duyệt từng cái/hàng loạt)

> Số hiệu TK **đã chốt 20/08/2026**: chiết khấu **5211** · phí **6411** · ngân hàng **112** (kèm 33311 / 1331 / 131 tương ứng). Account cụ thể (TK con ngân hàng nào) chọn trong phần cấu hình của app, không hardcode trong code.

| Sự kiện | Nợ | Có | Reference |
|---|---|---|---|
| Hóa đơn CK mình xuất (BKCK) | 5211 + 33311 | 131 | HĐ CK / BKCK; phân bổ theo các SI trong bảng kê |
| Phí/CK do chuỗi xuất HĐ cho mình (D1 Central Retail, I1 Emart, khoản L Lotte, phí AEON, Fuji 3%, Co.op 17,75%) | 6411 + 1331 | 131 | Số hóa đơn của chuỗi + đợt thanh toán |
| Khoản trừ chưa rõ chứng từ (nếu phát sinh) | *treo, không ghi JE* — hỏi chuỗi lấy hóa đơn/biên bản trước | | |
| Nhận thanh toán | 112 | 131 | **Từng dòng Có 131 reference đúng Sales Invoice** để trừ outstanding |
| Dòng NET OFF (Lotte) | Theo bản chất từng kỳ — đối chiếu trước khi ghi | | Đợt thanh toán |
| Hàng trả / móp lỗi | *(không JE tay)* — chứng từ trả hàng ERPNext + HĐ điều chỉnh MISA | | Cùng số PO (Central Retail) |

---

## 5. Lịch tháng (checklist)

| Thời điểm | Việc |
|---|---|
| Ngày 1–5 | **Xuất nốt toàn bộ HĐ hàng tháng trước cho Emart (deadline ngày 5)**. Chốt Mega theo cut-off. |
| Khi nhận TBCK Lotte | Rà từng store → BKCK/chi nhánh → HĐ CK → gửi `hoadonchietkhau@lotte.vn` → JE. Có lệch: phản hồi sớm (Emart settlement: trong 5 ngày). |
| Khi nhận doanh số Central Retail | Lọc nhóm `Discount for store` → BKCK/pháp nhân → HĐ CK → JE. |
| Khi nhận bất kỳ file thanh toán | Nạp portal `/ketoan` ngay → xử lý ngoại lệ khớp → duyệt JE → hóa đơn tự đánh dấu đã thanh toán. |
| Mỗi đợt giao Winmart | Kiểm phiếu nhập kho khớp PO + hàng trước khi xuất HĐ; lệch → xuất trả phần chênh. |
| Mỗi đợt nộp hồ sơ Winmart | Sinh bảng kê + đặt tên file PDF đúng chuẩn `YYYYMMDD_2007766_<stt>`. |
| Hàng tuần | Xem report **Công nợ MT đến hạn** (theo term từng Customer); nhắc/đòi các HĐ quá hạn. |

---

## 6. Xử lý ngoại lệ khớp

| Trạng thái | Cách xử lý |
|---|---|
| **Khớp** | Không cần đụng — duyệt JE. |
| **Lệch tiền** | Kiểm HĐ điều chỉnh/thay thế trên snapshot; kiểm hàng trả cùng PO; kiểm chuỗi trừ CK/phí gộp vào dòng. Vẫn lệch → liên hệ đầu mối chuỗi. |
| **Không tìm thấy** | Kiểm chuẩn hóa số HĐ (ký hiệu thiếu số 1, số 0 thừa); kiểm HĐ xuất trực tiếp trên MISA chưa có SI; kiểm nhầm kỳ. |
| **Cần review / Trùng** | Bắt buộc kiểm tay (Emart và Co.op mặc định rơi vào đây do không có ký hiệu / gõ tay). |

Đầu mối: Lotte `thongbaochietkhau@lotte.vn` · `hoadonchietkhau@lotte.vn`; Emart: kiểm soát hóa đơn / hợp đồng CK / thanh toán theo thông tin trên Rebate Settlement.

---

## 7. Trạng thái hệ thống (thời điểm soạn) và ghi chú chuyển tiếp

**Đã chạy trên portal `/ketoan`**: nạp file thanh toán 5 chuỗi (WinCommerce, Central Retail, LOTTE, Emart, Saigon Co.op) vào `MT Payment Advice`, tự nhận diện chuỗi + khớp hóa đơn; MISA Invoice Snapshot đồng bộ số hóa đơn.

**Đã bổ sung trong MT-2 (20/08/2026)**: parser AEON + Fuji; master điểm bán `MT Store`; cấu hình tài khoản `MT Account Map` + sinh/duyệt JE trên portal (luôn ở trạng thái Nháp, người duyệt mới ghi sổ); chiều chiết khấu từ file doanh số/TBCK (kể cả **Rebate Settlement PDF của Emart**) → bảng kê BKCK → chốt cấp số → in → ghi số HĐ CK → JE; hồ sơ thanh toán Winmart (xuất Excel + tên file PDF chuẩn `_PF`); report **Công nợ MT đến hạn** theo hạn khai trên từng Customer.

**Cần khai sau khi migrate**: `MT Account Map` (số hiệu TK từng công ty), `MT Discount Term` (tỷ lệ + cách tính từng chuỗi — LOTTE 10% tỷ lệ×tổng · Central Retail 3,35% cộng dòng · Mega 2% · **Emart 3% tỷ lệ×tổng**), và **hạn thanh toán** trên từng Customer (`Hạn thanh toán MT (ngày)` — để trống là *chưa khai*, hệ thống không đoán 45 ngày).

**Chưa có — vẫn thao tác tay**: parser thanh toán Mega Market (chưa có file mẫu thật); khớp tự động dòng `Ghi giảm` với hóa đơn.
