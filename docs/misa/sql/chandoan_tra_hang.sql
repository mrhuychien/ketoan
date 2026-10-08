-- ═══════════════════════════════════════════════════════════════════════
--  chandoan_tra_hang.sql — 479 bản trả hàng thực ra là gì
--
--  CHỈ ĐỌC. Không UPDATE/INSERT/DELETE/CREATE/ALTER, không gọi MISA.
--  Lệnh SET duy nhất là biến PHIÊN group_concat_max_len.
--
--  Chạy (từ thư mục ~/frappe-bench, sau khi git pull app ketoan):
--    bench --site site1.local mariadb < apps/ketoan/docs/misa/sql/chandoan_tra_hang.sql > ~/chandoan.out 2>&1
--    cat ~/chandoan.out
--
--  Phân loại mọi hóa đơn TRẢ HÀNG đã ghi sổ: bản nào đang chở danh tính MISA
--  (RefID / số / ký hiệu) chép từ hóa đơn gốc — tìm gốc qua `return_against`,
--  so với số HIỆN HÀNH của gốc lẫn số CŨ (gốc đã đổi số thay thế) — và đếm
--  trước hậu quả của việc dọn lên MT Hàng Hoàn và bảng kê MISA.
--  Bối cảnh: ketoan/api/misa_return_cleanup.py, patch v0_0_19.
-- ═══════════════════════════════════════════════════════════════════════
SET SESSION group_concat_max_len = 100000;

SELECT '=== Q0 COT/BANG CON THIEU (khac "khong thieu gi" thi bao lai toi) ===' AS `-`;
SELECT IFNULL(GROUP_CONCAT(CONCAT(x.t, '.', x.c) SEPARATOR ', '), 'khong thieu gi') AS thieu
FROM (
    SELECT 'tabSales Invoice' AS t, 'is_return' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'return_against' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_ref_id' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_inv_no' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_inv_series' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_inv_date' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_transaction_id' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_invoice_code' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_link' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_pushed_at' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_last_checked' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_relation' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_org_ref_id' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_org_inv' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_note' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_status' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'custom_misa_no_locked' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'vn_einvoice_number' AS c
    UNION ALL SELECT 'tabSales Invoice' AS t, 'vn_einvoice_date' AS c
    UNION ALL SELECT 'tabMT Hang Hoan' AS t, 'credit_note' AS c
    UNION ALL SELECT 'tabMT Hang Hoan' AS t, 'chung_tu_can' AS c
    UNION ALL SELECT 'tabMT Payment Advice Line' AS t, 'return_invoice' AS c
    UNION ALL SELECT 'tabMISA Invoice Snapshot' AS t, 'sales_invoice' AS c
    UNION ALL SELECT 'tabMISA Invoice Snapshot' AS t, 'match_method' AS c
) x
LEFT JOIN information_schema.COLUMNS ic
  ON ic.TABLE_SCHEMA = DATABASE() AND ic.TABLE_NAME = x.t AND ic.COLUMN_NAME = x.c
WHERE ic.COLUMN_NAME IS NULL;

SELECT '=== Q1 CO no_copy DANG SONG (Return co chep field do khong) ===' AS `-`;
SELECT cf.fieldname,
       cf.no_copy                         AS custom_field,
       ps.value                           AS property_setter_de_len,
       COALESCE(ps.value, cf.no_copy)     AS hieu_luc
FROM `tabCustom Field` cf
LEFT JOIN `tabProperty Setter` ps
  ON ps.doc_type = cf.dt AND ps.field_name = cf.fieldname AND ps.property = 'no_copy'
WHERE cf.dt = 'Sales Invoice'
  AND (cf.fieldname LIKE 'custom\_misa\_%' OR cf.fieldname LIKE 'vn\_einvoice\_%')
ORDER BY hieu_luc, cf.fieldname;

SELECT '=== Q2 VU TRU + DAT LAI LUAT CU (cot luat_cu_can_tay phai ~= 479) ===' AS `-`;
SELECT
  (SELECT COUNT(*) FROM `tabSales Invoice`
    WHERE docstatus = 1 AND IFNULL(is_return,0) = 1)                       AS tra_hang_ghi_so,
  (SELECT COUNT(*) FROM `tabSales Invoice`
    WHERE docstatus = 1 AND IFNULL(is_return,0) = 1
      AND IFNULL(custom_misa_ref_id,'') <> '')                             AS co_ref_id,
  (SELECT COUNT(*) FROM (
      SELECT name, IFNULL(custom_misa_inv_series,'') <> '' OR IFNULL(custom_misa_inv_no,'') <> '' OR custom_misa_inv_date IS NOT NULL OR IFNULL(custom_misa_transaction_id,'') <> '' OR IFNULL(custom_misa_invoice_code,'') <> '' OR IFNULL(custom_misa_link,'') <> '' OR custom_misa_pushed_at IS NOT NULL OR custom_misa_last_checked IS NOT NULL OR IFNULL(custom_misa_relation,'') <> '' OR IFNULL(custom_misa_org_ref_id,'') <> '' OR IFNULL(custom_misa_org_inv,'') <> '' OR IFNULL(custom_misa_note,'') <> '' OR IFNULL(vn_einvoice_number,'') <> '' OR vn_einvoice_date IS NOT NULL AS lot_cong
      FROM `tabSales Invoice`
      WHERE docstatus = 1 AND IFNULL(is_return,0) = 1
        AND IFNULL(custom_misa_ref_id,'') <> ''
      ORDER BY posting_date DESC, name DESC
      LIMIT 1000) t WHERE t.lot_cong)                                      AS luat_cu_can_tay;

SELECT '=== Q3 PHAN LOAI THEO LUAT MOI (T = se don, H = de nguoi xem, S = khong co gi) ===' AS `-`;

WITH r AS (
  SELECT r.name, r.posting_date, r.return_against,
         r.custom_misa_ref_id AS ref_id, r.custom_misa_inv_no AS inv_no,
         r.custom_misa_status AS st, IFNULL(r.custom_misa_no_locked, 0) AS locked,
         r.vn_einvoice_number AS vn_no,
         g.name AS g_name, g.docstatus AS g_ds,
         -- RefID của trả hàng = RefID HIỆN HÀNH của bản gốc
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_ref_id) AS ref_cur,
         -- ... hoặc = RefID CŨ của bản gốc (gốc đã bị đổi số thay thế, misa_replace)
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_org_ref_id) AS ref_org,
         (IFNULL(r.custom_misa_inv_no,'') = '') AS no_trong,
         (IFNULL(r.custom_misa_inv_no,'') <> ''
            AND BINARY r.custom_misa_inv_no <=> BINARY g.custom_misa_inv_no) AS no_cur,
         -- org_inv được ghi bằng " ".join(ký hiệu, số) đã strip — so cùng khuôn
         (IFNULL(r.custom_misa_inv_no,'') <> '' AND IFNULL(g.custom_misa_org_inv,'') <> ''
            AND BINARY CONCAT_WS(' ', NULLIF(TRIM(r.custom_misa_inv_series),''),
                                 TRIM(r.custom_misa_inv_no))
                <=> BINARY g.custom_misa_org_inv) AS no_org,
         -- Tập A (danh tính MISA) trên trả hàng có gì không
         (IFNULL(r.custom_misa_inv_series,'') <> '' OR IFNULL(r.custom_misa_inv_no,'') <> ''
          OR r.custom_misa_inv_date IS NOT NULL OR IFNULL(r.custom_misa_transaction_id,'') <> ''
          OR IFNULL(r.custom_misa_invoice_code,'') <> '' OR IFNULL(r.custom_misa_link,'') <> ''
          OR r.custom_misa_pushed_at IS NOT NULL OR IFNULL(r.custom_misa_relation,'') <> ''
          OR IFNULL(r.custom_misa_org_ref_id,'') <> '' OR IFNULL(r.custom_misa_org_inv,'') <> '') AS a_co,
         -- MỌI field Tập A đang có giá trị trên trả hàng đều khớp BYTE bản gốc hiện hành
         (    (IFNULL(r.custom_misa_inv_series,'') = ''
               OR BINARY r.custom_misa_inv_series <=> BINARY g.custom_misa_inv_series)
          AND (r.custom_misa_inv_date IS NULL OR r.custom_misa_inv_date <=> g.custom_misa_inv_date)
          AND (IFNULL(r.custom_misa_transaction_id,'') = ''
               OR BINARY r.custom_misa_transaction_id <=> BINARY g.custom_misa_transaction_id)
          AND (IFNULL(r.custom_misa_invoice_code,'') = ''
               OR BINARY r.custom_misa_invoice_code <=> BINARY g.custom_misa_invoice_code)
          AND (IFNULL(r.custom_misa_link,'') = ''
               OR BINARY r.custom_misa_link <=> BINARY g.custom_misa_link)
          AND (r.custom_misa_pushed_at IS NULL OR r.custom_misa_pushed_at <=> g.custom_misa_pushed_at)
          AND (IFNULL(r.custom_misa_relation,'') = ''
               OR BINARY r.custom_misa_relation <=> BINARY g.custom_misa_relation)
          AND (IFNULL(r.custom_misa_org_ref_id,'') = ''
               OR BINARY r.custom_misa_org_ref_id <=> BINARY g.custom_misa_org_ref_id)
          AND (IFNULL(r.custom_misa_org_inv,'') = ''
               OR BINARY r.custom_misa_org_inv <=> BINARY g.custom_misa_org_inv)) AS khop_het
  FROM `tabSales Invoice` r
  LEFT JOIN `tabSales Invoice` g ON g.name = r.return_against
  WHERE r.docstatus = 1 AND IFNULL(r.is_return, 0) = 1
), pl AS (
  SELECT r.*,
    CASE
      WHEN g_name IS NULL AND NOT a_co                         THEN 'S  sach (khong goc, khong co gi)'
      WHEN g_name IS NULL                                      THEN 'H1 khong tim thay ban goc'
      WHEN NOT a_co AND NOT ref_cur AND NOT ref_org            THEN 'S  sach'
      WHEN NOT no_trong AND NOT no_cur AND NOT no_org          THEN 'H2 so rieng, khac ban goc'
      WHEN (no_cur OR no_org) AND NOT ref_cur AND NOT ref_org  THEN 'H3 RefID rieng ma so = goc'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het AND g_ds = 2
                                                               THEN 'T3 chep tu goc DA HUY'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het       THEN 'T1 chep tu goc'
      WHEN ref_org AND (no_trong OR no_org)                    THEN 'T2 chep so CU cua goc da thay'
      ELSE                                                          'H4 khop mot phan'
    END AS loai,
    (locked = 1 OR st IN ('Đã hủy', 'Đã thay thế')) AS chan_cung
  FROM r
)
SELECT loai,
       COUNT(*)                                        AS so_ban,
       SUM(chan_cung)                                  AS bi_chan_cung,
       SUM(st = 'Lệch tiền')                           AS dang_lech_tien,
       SUM(IFNULL(inv_no,'') <> '')                    AS co_so_hd,
       GROUP_CONCAT(name ORDER BY posting_date DESC SEPARATOR ' ' LIMIT 6) AS vi_du
FROM pl
GROUP BY loai
ORDER BY loai;

SELECT '=== Q4 O SO CU (vn_einvoice_number) TREN CAC BAN SE DON ===' AS `-`;

WITH r AS (
  SELECT r.name, r.posting_date, r.return_against,
         r.custom_misa_ref_id AS ref_id, r.custom_misa_inv_no AS inv_no,
         r.custom_misa_status AS st, IFNULL(r.custom_misa_no_locked, 0) AS locked,
         r.vn_einvoice_number AS vn_no,
         g.name AS g_name, g.docstatus AS g_ds,
         -- RefID của trả hàng = RefID HIỆN HÀNH của bản gốc
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_ref_id) AS ref_cur,
         -- ... hoặc = RefID CŨ của bản gốc (gốc đã bị đổi số thay thế, misa_replace)
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_org_ref_id) AS ref_org,
         (IFNULL(r.custom_misa_inv_no,'') = '') AS no_trong,
         (IFNULL(r.custom_misa_inv_no,'') <> ''
            AND BINARY r.custom_misa_inv_no <=> BINARY g.custom_misa_inv_no) AS no_cur,
         -- org_inv được ghi bằng " ".join(ký hiệu, số) đã strip — so cùng khuôn
         (IFNULL(r.custom_misa_inv_no,'') <> '' AND IFNULL(g.custom_misa_org_inv,'') <> ''
            AND BINARY CONCAT_WS(' ', NULLIF(TRIM(r.custom_misa_inv_series),''),
                                 TRIM(r.custom_misa_inv_no))
                <=> BINARY g.custom_misa_org_inv) AS no_org,
         -- Tập A (danh tính MISA) trên trả hàng có gì không
         (IFNULL(r.custom_misa_inv_series,'') <> '' OR IFNULL(r.custom_misa_inv_no,'') <> ''
          OR r.custom_misa_inv_date IS NOT NULL OR IFNULL(r.custom_misa_transaction_id,'') <> ''
          OR IFNULL(r.custom_misa_invoice_code,'') <> '' OR IFNULL(r.custom_misa_link,'') <> ''
          OR r.custom_misa_pushed_at IS NOT NULL OR IFNULL(r.custom_misa_relation,'') <> ''
          OR IFNULL(r.custom_misa_org_ref_id,'') <> '' OR IFNULL(r.custom_misa_org_inv,'') <> '') AS a_co,
         -- MỌI field Tập A đang có giá trị trên trả hàng đều khớp BYTE bản gốc hiện hành
         (    (IFNULL(r.custom_misa_inv_series,'') = ''
               OR BINARY r.custom_misa_inv_series <=> BINARY g.custom_misa_inv_series)
          AND (r.custom_misa_inv_date IS NULL OR r.custom_misa_inv_date <=> g.custom_misa_inv_date)
          AND (IFNULL(r.custom_misa_transaction_id,'') = ''
               OR BINARY r.custom_misa_transaction_id <=> BINARY g.custom_misa_transaction_id)
          AND (IFNULL(r.custom_misa_invoice_code,'') = ''
               OR BINARY r.custom_misa_invoice_code <=> BINARY g.custom_misa_invoice_code)
          AND (IFNULL(r.custom_misa_link,'') = ''
               OR BINARY r.custom_misa_link <=> BINARY g.custom_misa_link)
          AND (r.custom_misa_pushed_at IS NULL OR r.custom_misa_pushed_at <=> g.custom_misa_pushed_at)
          AND (IFNULL(r.custom_misa_relation,'') = ''
               OR BINARY r.custom_misa_relation <=> BINARY g.custom_misa_relation)
          AND (IFNULL(r.custom_misa_org_ref_id,'') = ''
               OR BINARY r.custom_misa_org_ref_id <=> BINARY g.custom_misa_org_ref_id)
          AND (IFNULL(r.custom_misa_org_inv,'') = ''
               OR BINARY r.custom_misa_org_inv <=> BINARY g.custom_misa_org_inv)) AS khop_het
  FROM `tabSales Invoice` r
  LEFT JOIN `tabSales Invoice` g ON g.name = r.return_against
  WHERE r.docstatus = 1 AND IFNULL(r.is_return, 0) = 1
), pl AS (
  SELECT r.*,
    CASE
      WHEN g_name IS NULL AND NOT a_co                         THEN 'S  sach (khong goc, khong co gi)'
      WHEN g_name IS NULL                                      THEN 'H1 khong tim thay ban goc'
      WHEN NOT a_co AND NOT ref_cur AND NOT ref_org            THEN 'S  sach'
      WHEN NOT no_trong AND NOT no_cur AND NOT no_org          THEN 'H2 so rieng, khac ban goc'
      WHEN (no_cur OR no_org) AND NOT ref_cur AND NOT ref_org  THEN 'H3 RefID rieng ma so = goc'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het AND g_ds = 2
                                                               THEN 'T3 chep tu goc DA HUY'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het       THEN 'T1 chep tu goc'
      WHEN ref_org AND (no_trong OR no_org)                    THEN 'T2 chep so CU cua goc da thay'
      ELSE                                                          'H4 khop mot phan'
    END AS loai,
    (locked = 1 OR st IN ('Đã hủy', 'Đã thay thế')) AS chan_cung
  FROM r
)
SELECT CASE
         WHEN IFNULL(vn_no,'') = ''              THEN 'a trong'
         WHEN BINARY vn_no = BINARY inv_no       THEN 'b trung so dang vay (may ghi)'
         WHEN vn_no REGEXP '[^0-9]'              THEN 'c co chu/dau (NGUOI go, giu)'
         ELSE                                         'd so khac (co the nguoi go, giu)'
       END AS o_so_cu,
       COUNT(*) AS so_ban,
       GROUP_CONCAT(CONCAT(name, '=', IFNULL(vn_no,'')) ORDER BY posting_date DESC
                    SEPARATOR ' ' LIMIT 6) AS vi_du
FROM pl
WHERE loai LIKE 'T%' AND NOT chan_cung
GROUP BY 1 ORDER BY 1;

SELECT '=== Q5 MT HANG HOAN SE LAT ve "Chua co chung tu thue" sau khi don ===' AS `-`;

WITH r AS (
  SELECT r.name, r.posting_date, r.return_against,
         r.custom_misa_ref_id AS ref_id, r.custom_misa_inv_no AS inv_no,
         r.custom_misa_status AS st, IFNULL(r.custom_misa_no_locked, 0) AS locked,
         r.vn_einvoice_number AS vn_no,
         g.name AS g_name, g.docstatus AS g_ds,
         -- RefID của trả hàng = RefID HIỆN HÀNH của bản gốc
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_ref_id) AS ref_cur,
         -- ... hoặc = RefID CŨ của bản gốc (gốc đã bị đổi số thay thế, misa_replace)
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_org_ref_id) AS ref_org,
         (IFNULL(r.custom_misa_inv_no,'') = '') AS no_trong,
         (IFNULL(r.custom_misa_inv_no,'') <> ''
            AND BINARY r.custom_misa_inv_no <=> BINARY g.custom_misa_inv_no) AS no_cur,
         -- org_inv được ghi bằng " ".join(ký hiệu, số) đã strip — so cùng khuôn
         (IFNULL(r.custom_misa_inv_no,'') <> '' AND IFNULL(g.custom_misa_org_inv,'') <> ''
            AND BINARY CONCAT_WS(' ', NULLIF(TRIM(r.custom_misa_inv_series),''),
                                 TRIM(r.custom_misa_inv_no))
                <=> BINARY g.custom_misa_org_inv) AS no_org,
         -- Tập A (danh tính MISA) trên trả hàng có gì không
         (IFNULL(r.custom_misa_inv_series,'') <> '' OR IFNULL(r.custom_misa_inv_no,'') <> ''
          OR r.custom_misa_inv_date IS NOT NULL OR IFNULL(r.custom_misa_transaction_id,'') <> ''
          OR IFNULL(r.custom_misa_invoice_code,'') <> '' OR IFNULL(r.custom_misa_link,'') <> ''
          OR r.custom_misa_pushed_at IS NOT NULL OR IFNULL(r.custom_misa_relation,'') <> ''
          OR IFNULL(r.custom_misa_org_ref_id,'') <> '' OR IFNULL(r.custom_misa_org_inv,'') <> '') AS a_co,
         -- MỌI field Tập A đang có giá trị trên trả hàng đều khớp BYTE bản gốc hiện hành
         (    (IFNULL(r.custom_misa_inv_series,'') = ''
               OR BINARY r.custom_misa_inv_series <=> BINARY g.custom_misa_inv_series)
          AND (r.custom_misa_inv_date IS NULL OR r.custom_misa_inv_date <=> g.custom_misa_inv_date)
          AND (IFNULL(r.custom_misa_transaction_id,'') = ''
               OR BINARY r.custom_misa_transaction_id <=> BINARY g.custom_misa_transaction_id)
          AND (IFNULL(r.custom_misa_invoice_code,'') = ''
               OR BINARY r.custom_misa_invoice_code <=> BINARY g.custom_misa_invoice_code)
          AND (IFNULL(r.custom_misa_link,'') = ''
               OR BINARY r.custom_misa_link <=> BINARY g.custom_misa_link)
          AND (r.custom_misa_pushed_at IS NULL OR r.custom_misa_pushed_at <=> g.custom_misa_pushed_at)
          AND (IFNULL(r.custom_misa_relation,'') = ''
               OR BINARY r.custom_misa_relation <=> BINARY g.custom_misa_relation)
          AND (IFNULL(r.custom_misa_org_ref_id,'') = ''
               OR BINARY r.custom_misa_org_ref_id <=> BINARY g.custom_misa_org_ref_id)
          AND (IFNULL(r.custom_misa_org_inv,'') = ''
               OR BINARY r.custom_misa_org_inv <=> BINARY g.custom_misa_org_inv)) AS khop_het
  FROM `tabSales Invoice` r
  LEFT JOIN `tabSales Invoice` g ON g.name = r.return_against
  WHERE r.docstatus = 1 AND IFNULL(r.is_return, 0) = 1
), pl AS (
  SELECT r.*,
    CASE
      WHEN g_name IS NULL AND NOT a_co                         THEN 'S  sach (khong goc, khong co gi)'
      WHEN g_name IS NULL                                      THEN 'H1 khong tim thay ban goc'
      WHEN NOT a_co AND NOT ref_cur AND NOT ref_org            THEN 'S  sach'
      WHEN NOT no_trong AND NOT no_cur AND NOT no_org          THEN 'H2 so rieng, khac ban goc'
      WHEN (no_cur OR no_org) AND NOT ref_cur AND NOT ref_org  THEN 'H3 RefID rieng ma so = goc'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het AND g_ds = 2
                                                               THEN 'T3 chep tu goc DA HUY'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het       THEN 'T1 chep tu goc'
      WHEN ref_org AND (no_trong OR no_org)                    THEN 'T2 chep so CU cua goc da thay'
      ELSE                                                          'H4 khop mot phan'
    END AS loai,
    (locked = 1 OR st IN ('Đã hủy', 'Đã thay thế')) AS chan_cung
  FROM r
)
SELECT IFNULL(NULLIF(h.chung_tu_can,''), '(trong)') AS chung_tu_can,
       COUNT(*) AS so_dong_se_lat,
       GROUP_CONCAT(CONCAT(h.name, '<-', h.credit_note) SEPARATOR ' ' LIMIT 6) AS vi_du
FROM `tabMT Hang Hoan` h
JOIN pl ON pl.name = h.credit_note
WHERE pl.loai LIKE 'T%' AND NOT pl.chan_cung
  AND IFNULL(pl.inv_no,'') <> ''
  AND NOT (IFNULL(h.chung_tu_can,'') = 'Không cần chứng từ')
  AND NOT EXISTS (
      SELECT 1 FROM `tabMT Payment Advice Line` l
      JOIN `tabMT Payment Advice` a ON a.name = l.parent
      WHERE l.return_invoice = h.credit_note AND a.docstatus < 2)
GROUP BY 1 ORDER BY 2 DESC;

SELECT '=== Q6 BANG KE MISA DANG NOI VAO PHIEU TRA HANG ===' AS `-`;

WITH r AS (
  SELECT r.name, r.posting_date, r.return_against,
         r.custom_misa_ref_id AS ref_id, r.custom_misa_inv_no AS inv_no,
         r.custom_misa_status AS st, IFNULL(r.custom_misa_no_locked, 0) AS locked,
         r.vn_einvoice_number AS vn_no,
         g.name AS g_name, g.docstatus AS g_ds,
         -- RefID của trả hàng = RefID HIỆN HÀNH của bản gốc
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_ref_id) AS ref_cur,
         -- ... hoặc = RefID CŨ của bản gốc (gốc đã bị đổi số thay thế, misa_replace)
         (IFNULL(r.custom_misa_ref_id,'') <> ''
            AND BINARY r.custom_misa_ref_id <=> BINARY g.custom_misa_org_ref_id) AS ref_org,
         (IFNULL(r.custom_misa_inv_no,'') = '') AS no_trong,
         (IFNULL(r.custom_misa_inv_no,'') <> ''
            AND BINARY r.custom_misa_inv_no <=> BINARY g.custom_misa_inv_no) AS no_cur,
         -- org_inv được ghi bằng " ".join(ký hiệu, số) đã strip — so cùng khuôn
         (IFNULL(r.custom_misa_inv_no,'') <> '' AND IFNULL(g.custom_misa_org_inv,'') <> ''
            AND BINARY CONCAT_WS(' ', NULLIF(TRIM(r.custom_misa_inv_series),''),
                                 TRIM(r.custom_misa_inv_no))
                <=> BINARY g.custom_misa_org_inv) AS no_org,
         -- Tập A (danh tính MISA) trên trả hàng có gì không
         (IFNULL(r.custom_misa_inv_series,'') <> '' OR IFNULL(r.custom_misa_inv_no,'') <> ''
          OR r.custom_misa_inv_date IS NOT NULL OR IFNULL(r.custom_misa_transaction_id,'') <> ''
          OR IFNULL(r.custom_misa_invoice_code,'') <> '' OR IFNULL(r.custom_misa_link,'') <> ''
          OR r.custom_misa_pushed_at IS NOT NULL OR IFNULL(r.custom_misa_relation,'') <> ''
          OR IFNULL(r.custom_misa_org_ref_id,'') <> '' OR IFNULL(r.custom_misa_org_inv,'') <> '') AS a_co,
         -- MỌI field Tập A đang có giá trị trên trả hàng đều khớp BYTE bản gốc hiện hành
         (    (IFNULL(r.custom_misa_inv_series,'') = ''
               OR BINARY r.custom_misa_inv_series <=> BINARY g.custom_misa_inv_series)
          AND (r.custom_misa_inv_date IS NULL OR r.custom_misa_inv_date <=> g.custom_misa_inv_date)
          AND (IFNULL(r.custom_misa_transaction_id,'') = ''
               OR BINARY r.custom_misa_transaction_id <=> BINARY g.custom_misa_transaction_id)
          AND (IFNULL(r.custom_misa_invoice_code,'') = ''
               OR BINARY r.custom_misa_invoice_code <=> BINARY g.custom_misa_invoice_code)
          AND (IFNULL(r.custom_misa_link,'') = ''
               OR BINARY r.custom_misa_link <=> BINARY g.custom_misa_link)
          AND (r.custom_misa_pushed_at IS NULL OR r.custom_misa_pushed_at <=> g.custom_misa_pushed_at)
          AND (IFNULL(r.custom_misa_relation,'') = ''
               OR BINARY r.custom_misa_relation <=> BINARY g.custom_misa_relation)
          AND (IFNULL(r.custom_misa_org_ref_id,'') = ''
               OR BINARY r.custom_misa_org_ref_id <=> BINARY g.custom_misa_org_ref_id)
          AND (IFNULL(r.custom_misa_org_inv,'') = ''
               OR BINARY r.custom_misa_org_inv <=> BINARY g.custom_misa_org_inv)) AS khop_het
  FROM `tabSales Invoice` r
  LEFT JOIN `tabSales Invoice` g ON g.name = r.return_against
  WHERE r.docstatus = 1 AND IFNULL(r.is_return, 0) = 1
), pl AS (
  SELECT r.*,
    CASE
      WHEN g_name IS NULL AND NOT a_co                         THEN 'S  sach (khong goc, khong co gi)'
      WHEN g_name IS NULL                                      THEN 'H1 khong tim thay ban goc'
      WHEN NOT a_co AND NOT ref_cur AND NOT ref_org            THEN 'S  sach'
      WHEN NOT no_trong AND NOT no_cur AND NOT no_org          THEN 'H2 so rieng, khac ban goc'
      WHEN (no_cur OR no_org) AND NOT ref_cur AND NOT ref_org  THEN 'H3 RefID rieng ma so = goc'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het AND g_ds = 2
                                                               THEN 'T3 chep tu goc DA HUY'
      WHEN ref_cur AND (no_trong OR no_cur) AND khop_het       THEN 'T1 chep tu goc'
      WHEN ref_org AND (no_trong OR no_org)                    THEN 'T2 chep so CU cua goc da thay'
      ELSE                                                          'H4 khop mot phan'
    END AS loai,
    (locked = 1 OR st IN ('Đã hủy', 'Đã thay thế')) AS chan_cung
  FROM r
)
SELECT pl.loai, IFNULL(s.match_method,'(trong)') AS cach_noi, COUNT(*) AS so_snapshot,
       GROUP_CONCAT(CONCAT(s.name, '->', s.sales_invoice) SEPARATOR ' ' LIMIT 6) AS vi_du
FROM `tabMISA Invoice Snapshot` s
JOIN pl ON pl.name = s.sales_invoice
GROUP BY 1, 2 ORDER BY 1, 2;
