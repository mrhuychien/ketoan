-- ════════════════════════════════════════════════════════════════════════
-- Đổi ô "ngân hàng" trên phiếu lương sang ĐÚNG chuỗi trong danh sách
-- "Ngân hàng hưởng" của mẫu chuyển khoản mới của ngân hàng (11/2026).
-- KHÔNG BẮT BUỘC: file xuất (Tiền lương › Chuyển khoản ngân hàng) đã tự đổi ba
-- chuỗi dưới đây sang chuỗi mới (ketoan/api/payroll_bank.py, DOI_NGAN_HANG). Chạy
-- lệnh này khi muốn chính phiếu lương cũng mang chuỗi mới.
--
--   NHTMCP DTPT VN-CN HAI DUONG - 31202005            → 01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV
--   NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004 → 01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV
--   NHTMCP QUOC TE VN-CN HAI DUONG-31314003           → 79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB
--
-- CHỈ đổi ô ghi ĐÚNG ba chuỗi trên (khớp từng chữ; chỉ bỏ khoảng trắng thừa ở hai
-- đầu) — mọi giá trị khác giữ nguyên. Áp cho phiếu nháp, đã duyệt, đã hủy của
-- SalaryDay (công nhật) và SalaryProduct (công khoán). Không đụng `modified`.
--
-- Chạy trên máy chủ, trong thư mục frappe-bench:
--     bench --site <tên site> mariadb < apps/ketoan/docs/luong/sql/doi_ngan_hang_2026_11.sql
-- Kết quả in hai bảng TRUOC / SAU. Ô nào ở bảng SAU vẫn còn dạng cũ của ba chuỗi
-- trên (gõ khác dấu cách, khác hoa/thường) là chưa đổi — xem rồi quyết.
-- Lùi lại: xem cuối file.
-- ════════════════════════════════════════════════════════════════════════

-- 0. Ô "ngân hàng" trên phiếu là loại gì? Nếu fieldtype = Select (danh sách chọn)
--    hoặc có fetch_from (tự lấy từ hồ sơ nhân viên…) thì gửi lại kết quả này: phải
--    sửa cả danh sách chọn / nơi gốc, không thì phiếu mới vẫn ra chuỗi cũ.
SELECT parent AS doctype, fieldname, fieldtype, options, fetch_from
  FROM `tabDocField`
 WHERE parent IN ('SalaryDay', 'SalaryProduct') AND fieldname = 'nganhang'
UNION ALL
SELECT dt, fieldname, fieldtype, options, fetch_from
  FROM `tabCustom Field`
 WHERE dt IN ('SalaryDay', 'SalaryProduct') AND fieldname = 'nganhang';

-- 1. Sao lưu ô cũ. Chạy lại lần hai không ghi đè bản sao lưu đầu tiên.
CREATE TABLE IF NOT EXISTS `_bk_nganhang_2026_11` AS
    SELECT 'SalaryDay' AS dt, name, nganhang FROM `tabSalaryDay`
    UNION ALL
    SELECT 'SalaryProduct', name, nganhang FROM `tabSalaryProduct`;

-- 2. Trước khi đổi
SELECT 'TRUOC' AS luc, 'SalaryDay' AS bang, nganhang, COUNT(*) AS so_phieu
  FROM `tabSalaryDay` GROUP BY nganhang
UNION ALL
SELECT 'TRUOC', 'SalaryProduct', nganhang, COUNT(*)
  FROM `tabSalaryProduct` GROUP BY nganhang;

-- 3. Đổi — CHỈ ô ghi ĐÚNG một trong ba chuỗi kế toán gửi (BINARY: khớp từng
--    chữ, phân biệt hoa/thường; chỉ bỏ khoảng trắng thừa ở hai đầu). Chuỗi khác,
--    dù gần giống, KHÔNG đổi — sẽ hiện ở bảng SAU.
UPDATE `tabSalaryDay`
   SET nganhang = '01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV'
 WHERE BINARY TRIM(nganhang) IN ('NHTMCP DTPT VN-CN HAI DUONG - 31202005',
                                 'NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004');
UPDATE `tabSalaryProduct`
   SET nganhang = '01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV'
 WHERE BINARY TRIM(nganhang) IN ('NHTMCP DTPT VN-CN HAI DUONG - 31202005',
                                 'NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004');
UPDATE `tabSalaryDay`
   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'
 WHERE BINARY TRIM(nganhang) = 'NHTMCP QUOC TE VN-CN HAI DUONG-31314003';
UPDATE `tabSalaryProduct`
   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'
 WHERE BINARY TRIM(nganhang) = 'NHTMCP QUOC TE VN-CN HAI DUONG-31314003';

-- 4. Sau khi đổi
SELECT 'SAU' AS luc, 'SalaryDay' AS bang, nganhang, COUNT(*) AS so_phieu
  FROM `tabSalaryDay` GROUP BY nganhang
UNION ALL
SELECT 'SAU', 'SalaryProduct', nganhang, COUNT(*)
  FROM `tabSalaryProduct` GROUP BY nganhang;

-- ── Lùi lại (chỉ khi cần) — bỏ dấu "-- " đầu hai dòng dưới rồi chạy:
-- UPDATE `tabSalaryDay` t JOIN `_bk_nganhang_2026_11` b ON b.dt = 'SalaryDay' AND b.name = t.name SET t.nganhang = b.nganhang;
-- UPDATE `tabSalaryProduct` t JOIN `_bk_nganhang_2026_11` b ON b.dt = 'SalaryProduct' AND b.name = t.name SET t.nganhang = b.nganhang;
