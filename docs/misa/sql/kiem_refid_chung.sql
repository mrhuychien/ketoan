-- ═══════════════════════════════════════════════════════════════════════
--  kiem_refid_chung.sql — còn chứng từ nào DÙNG CHUNG RefID / CHUNG SỐ không
--
--  CHỈ ĐỌC. Không UPDATE/INSERT/DELETE/CREATE/ALTER, không gọi MISA.
--
--  Chạy (từ ~/frappe-bench, sau khi git pull app ketoan):
--    bench --site site1.local mariadb < apps/ketoan/docs/misa/sql/kiem_refid_chung.sql > ~/refid.out 2>&1
--    cat ~/refid.out
--
--  VÌ SAO DÙNG CHUNG RefID LÀ SAI SỐ — đọc từ misa_sync._poll_pending:
--  vòng 1 hỏi MISA `afterpublishing/{RefID}` cho MỌI hóa đơn ghi sổ có RefID
--  mà chưa có số, KHÔNG xét đã đẩy hay chưa. Hai chứng từ chung một RefID: đẩy
--  bản này thì lượt đồng bộ sau ghi SỐ CỦA NÓ sang bản kia.
--
--  Đã dọn: 106 hóa đơn trả hàng (vân tay 0015644464455fc84c70b186d328a925).
--  File này đo phần CÒN LẠI, kể cả hóa đơn bán với nhau.
-- ═══════════════════════════════════════════════════════════════════════
SET SESSION group_concat_max_len = 100000;

SELECT '=== Q1 NHOM DUNG CHUNG RefID, THEO MUC NGUY HIEM ===' AS `-`;
WITH g AS (
  SELECT custom_misa_ref_id AS r,
         COUNT(*)                                                         AS n,
         SUM(docstatus IN (0, 1))                                         AS song,
         SUM(docstatus = 1 AND IFNULL(custom_misa_inv_no, '') <> '')      AS song_co_so,
         SUM(IFNULL(custom_misa_inv_no, '') <> '')                        AS co_so,
         SUM(docstatus IN (0, 1) AND IFNULL(custom_misa_inv_no, '') = '') AS song_chua_so,
         SUM(IFNULL(is_return, 0) = 1)                                    AS tra_hang,
         SUM(custom_misa_pushed_at IS NOT NULL)                           AS da_day
  FROM `tabSales Invoice`
  WHERE IFNULL(custom_misa_ref_id, '') <> ''
  GROUP BY custom_misa_ref_id
  HAVING n > 1
)
SELECT CASE
         WHEN song_co_so >= 2                 THEN 'A. DA SAI SO: >=2 ban ghi so cung mang so'
         WHEN co_so >= 1 AND song_chua_so >= 1 THEN 'B. SAP SAI SO: da co ban co so, ban khac chua'
         WHEN co_so = 0 AND song >= 2         THEN 'C. SE SAI KHI DAY: chua ban nao co so'
         ELSE                                      'D. vo hai: <=1 ban con song, khong ai co so'
       END AS muc,
       COUNT(*) AS so_nhom, SUM(n) AS so_chung_tu,
       SUM(tra_hang) AS trong_do_tra_hang, SUM(da_day) AS ban_da_day
FROM g
GROUP BY muc ORDER BY muc;

SELECT '=== Q2 CHI TIET NHOM A / B / C (toi da 40 nhom) ===' AS `-`;
WITH g AS (
  SELECT custom_misa_ref_id AS r, COUNT(*) AS n,
         SUM(docstatus IN (0, 1)) AS song,
         SUM(docstatus = 1 AND IFNULL(custom_misa_inv_no, '') <> '') AS song_co_so,
         SUM(IFNULL(custom_misa_inv_no, '') <> '') AS co_so,
         SUM(docstatus IN (0, 1) AND IFNULL(custom_misa_inv_no, '') = '') AS song_chua_so
  FROM `tabSales Invoice`
  WHERE IFNULL(custom_misa_ref_id, '') <> ''
  GROUP BY custom_misa_ref_id HAVING n > 1
), nguy AS (
  SELECT r, n,
         CASE WHEN song_co_so >= 2 THEN 'A'
              WHEN co_so >= 1 AND song_chua_so >= 1 THEN 'B'
              WHEN co_so = 0 AND song >= 2 THEN 'C' END AS muc
  FROM g
)
SELECT nguy.muc, LEFT(nguy.r, 8) AS refid, nguy.n,
       GROUP_CONCAT(CONCAT(si.name,
                           ' [', CASE si.docstatus WHEN 0 THEN 'nhap' WHEN 1 THEN 'ghi so' ELSE 'huy' END,
                           IF(IFNULL(si.is_return, 0) = 1, ', tra hang', ''),
                           IF(si.custom_misa_pushed_at IS NOT NULL, ', DA DAY', ''),
                           IF(IFNULL(si.amended_from, '') <> '', CONCAT(', sua tu ', si.amended_from), ''),
                           '] so=', IFNULL(NULLIF(si.custom_misa_inv_no, ''), '-'),
                           ' tien=', ROUND(si.grand_total),
                           ' PO=', IFNULL(NULLIF(si.custom_po_, ''), '-'))
                    ORDER BY si.creation SEPARATOR '  |  ') AS cac_chung_tu
FROM nguy
JOIN `tabSales Invoice` si ON si.custom_misa_ref_id = nguy.r
WHERE nguy.muc IS NOT NULL
GROUP BY nguy.muc, nguy.r, nguy.n
ORDER BY nguy.muc, nguy.n DESC, nguy.r
LIMIT 40;

SELECT '=== Q3 HOA DON BAN GHI SO CUNG MOT SO (khong ke RefID) ===' AS `-`;
-- So chuẩn hóa như norm_inv_no: bỏ số 0 đầu, để "8433" đụng "00008433".
SELECT IFNULL(NULLIF(TRIM(custom_misa_inv_series), ''), '(trong)') AS ky_hieu,
       TRIM(LEADING '0' FROM TRIM(custom_misa_inv_no)) AS so,
       COUNT(*) AS so_hoa_don,
       GROUP_CONCAT(CONCAT(name, ' ', ROUND(grand_total)) ORDER BY creation SEPARATOR '  |  ') AS cac_hoa_don
FROM `tabSales Invoice`
WHERE docstatus = 1 AND IFNULL(is_return, 0) = 0
  AND IFNULL(custom_misa_inv_no, '') <> ''
GROUP BY ky_hieu, so
HAVING so_hoa_don > 1
ORDER BY so_hoa_don DESC, so
LIMIT 40;
