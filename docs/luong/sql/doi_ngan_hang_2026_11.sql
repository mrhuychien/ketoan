-- ════════════════════════════════════════════════════════════════════════
-- Đổi ô "ngân hàng" trên phiếu lương sang ĐÚNG chuỗi trong danh sách
-- "Ngân hàng hưởng" của mẫu chuyển khoản mới của ngân hàng (11/2026).
-- File xuất (Tiền lương › Chuyển khoản ngân hàng) ghi NGUYÊN VĂN ô này vào cột
-- "Ngân hàng hưởng", nên phiếu lương phải ghi đúng chuỗi của danh sách.
--
--   NHTMCP DTPT VN-CN HAI DUONG - 31202005            → 01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV
--   NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004 → 01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV
--   NHTMCP QUOC TE VN-CN HAI DUONG-31314003           → 79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB
--
-- Áp cho MỌI phiếu (nháp, đã duyệt, đã hủy) của SalaryDay (công nhật) và
-- SalaryProduct (công khoán). So khớp bỏ qua dấu cách và hoa/thường ("…-31314003"
-- hay "… - 31314003" đều ăn). Không đụng `modified`.
--
-- Chạy trên máy chủ, trong thư mục frappe-bench:
--     bench --site <tên site> mariadb < apps/ketoan/docs/luong/sql/doi_ngan_hang_2026_11.sql
-- Kết quả in hai bảng TRUOC / SAU. Phần SAU mà còn chuỗi nào KHÔNG phải hai
-- chuỗi mới (trừ ô trống) thì gửi lại để thêm vào lệnh.
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

-- 3. Đổi
UPDATE `tabSalaryDay`
   SET nganhang = '01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV'
 WHERE REPLACE(nganhang, ' ', '') IN ('NHTMCPDTPTVN-CNHAIDUONG-31202005',
                                      'NHTMCPDTPTVN-CNTHANHDONG-HAIDUONG-31202004');
UPDATE `tabSalaryProduct`
   SET nganhang = '01202001 - Ngan hang TMCP Dau tu va Phat trien Viet Nam - BIDV'
 WHERE REPLACE(nganhang, ' ', '') IN ('NHTMCPDTPTVN-CNHAIDUONG-31202005',
                                      'NHTMCPDTPTVN-CNTHANHDONG-HAIDUONG-31202004');
UPDATE `tabSalaryDay`
   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'
 WHERE REPLACE(nganhang, ' ', '') = 'NHTMCPQUOCTEVN-CNHAIDUONG-31314003';
UPDATE `tabSalaryProduct`
   SET nganhang = '79314013 - Ngan hang TMCP Quoc Te Viet Nam - VIB'
 WHERE REPLACE(nganhang, ' ', '') = 'NHTMCPQUOCTEVN-CNHAIDUONG-31314003';

-- 4. Sau khi đổi
SELECT 'SAU' AS luc, 'SalaryDay' AS bang, nganhang, COUNT(*) AS so_phieu
  FROM `tabSalaryDay` GROUP BY nganhang
UNION ALL
SELECT 'SAU', 'SalaryProduct', nganhang, COUNT(*)
  FROM `tabSalaryProduct` GROUP BY nganhang;

-- ── Lùi lại (chỉ khi cần) — bỏ dấu "-- " đầu hai dòng dưới rồi chạy:
-- UPDATE `tabSalaryDay` t JOIN `_bk_nganhang_2026_11` b ON b.dt = 'SalaryDay' AND b.name = t.name SET t.nganhang = b.nganhang;
-- UPDATE `tabSalaryProduct` t JOIN `_bk_nganhang_2026_11` b ON b.dt = 'SalaryProduct' AND b.name = t.name SET t.nganhang = b.nganhang;
