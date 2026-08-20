// api.js — wrap gọi whitelisted method của app. Dùng fetch + CSRF từ context,
// không phụ thuộc frappe JS có mặt trên website page.

const CTX = window.KETOAN_CONTEXT || {};

async function callMethod(method, args = {}) {
  const res = await fetch("/api/method/" + method, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Frappe-CSRF-Token": CTX.csrfToken || (window.frappe && window.frappe.csrf_token) || "",
      "Accept": "application/json",
    },
    credentials: "same-origin",
    body: JSON.stringify(args || {}),
  });

  let data = null;
  try { data = await res.json(); } catch (_) { /* non-JSON */ }

  if (!res.ok) {
    const msg = extractError(data) || ("Lỗi máy chủ (" + res.status + ")");
    throw new Error(msg);
  }
  return data ? data.message : null;
}

function extractError(data) {
  if (!data) return null;
  try {
    if (data._server_messages) {
      const arr = JSON.parse(data._server_messages);
      if (arr.length) {
        const m = JSON.parse(arr[0]);
        return m.message || arr[0];
      }
    }
  } catch (_) { /* ignore */ }
  if (data.exception) return String(data.exception).split(":").slice(1).join(":").trim() || data.exception;
  return data.message || null;
}

const NS = "ketoan.api.";
const withCompany = (a = {}) => ({ company: CTX.company, ...a });

// POST tải file (PDF…) về máy. Method set frappe.local.response.type='download'.
async function downloadPost(method, args = {}) {
  const res = await fetch("/api/method/" + method, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Frappe-CSRF-Token": CTX.csrfToken || (window.frappe && window.frappe.csrf_token) || "",
    },
    credentials: "same-origin",
    body: JSON.stringify(args || {}),
  });
  if (!res.ok) {
    let msg = "Lỗi máy chủ (" + res.status + ")";
    try { msg = extractError(await res.json()) || msg; } catch (_) {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const name = m ? decodeURIComponent(m[1]) : "download.pdf";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const api = {
  call: callMethod,
  downloadPost,
  context: CTX,

  // Dashboard
  overview: (a) => callMethod(NS + "dashboard.get_overview", withCompany(a)),
  supervision: (a) => callMethod(NS + "supervision.get_overview", withCompany(a)),
  tasks: (a) => callMethod(NS + "tasks.get_tasks", withCompany(a)),

  // Receivables (channel: npp | mt | khac | tat-ca)
  arSummary: (channel, a) => callMethod(NS + "receivables.get_ar_summary", withCompany({ channel: channel || "tat-ca", ...a })),
  aging: (channel, a) => callMethod(NS + "receivables.get_aging", withCompany({ channel: channel || "tat-ca", ...a })),
  customerDetail: (customer, a) => callMethod(NS + "receivables.get_customer_detail", withCompany({ customer, ...a })),
  customerLedger: (customer, a) => callMethod(NS + "receivables.get_customer_ledger", withCompany({ customer, ...a })),
  sellingPriceWatch: (channel, a) => callMethod(NS + "prices.get_selling_price_watch", withCompany({ channel: channel || "tat-ca", ...a })),

  // Cash
  balances: (a) => callMethod(NS + "cash.get_balances", withCompany(a)),
  cashflow: (a) => callMethod(NS + "cash.get_cashflow", withCompany(a)),
  transactions: (a) => callMethod(NS + "cash.get_transactions", withCompany(a)),
  glAccounts: () => callMethod(NS + "cash.get_ledger_accounts", withCompany()),
  glLedger: (account, a) => callMethod(NS + "cash.get_account_ledger", withCompany({ account, ...a })),

  // Payables (mua hàng)
  apSummary: (a) => callMethod(NS + "payables.get_ap_summary", withCompany(a)),
  apAging: (a) => callMethod(NS + "payables.get_aging", withCompany(a)),
  apDueSchedule: (a) => callMethod(NS + "payables.get_due_schedule", withCompany(a)),
  supplierDetail: (supplier, a) => callMethod(NS + "payables.get_supplier_detail", withCompany({ supplier, ...a })),
  apControls: (a) => callMethod(NS + "payables.get_controls", withCompany(a)),
  supplierFiles: (supplier) => callMethod(NS + "payables.get_supplier_files", { supplier }),
  supplierFileUpload: (supplier, filename, content) => callMethod(NS + "payables.upload_supplier_file", { supplier, filename, content }),
  apPriceWatch: (a) => callMethod(NS + "prices.get_price_watch", withCompany(a)),
  apPriceHistory: (item_code, a) => callMethod(NS + "prices.get_price_history", withCompany({ item_code, ...a })),

  // NPP reconciliation
  nppDebts: (a) => callMethod(NS + "npp.get_debts", withCompany(a)),
  nppDiscountEligible: (month, a) => callMethod(NS + "npp.get_discount_eligible", withCompany({ month, ...a })),
  nppCreateDiscount: (customers, month, a) => callMethod(NS + "npp.create_discount_entries", withCompany({ customers: JSON.stringify(customers), month, ...a })),
  nppExportBulk: (customers, from_date, to_date) => downloadPost(NS + "npp.export_reconciliation_bulk", withCompany({ customers: JSON.stringify(customers), from_date, to_date })),
  nppExportRecon: (customer, from_date, to_date) => downloadPost(NS + "npp.export_reconciliation", withCompany({ customer, from_date, to_date })),

  // Đối trừ công nợ NPP
  doitruCases: (a) => callMethod(NS + "doitru.get_cases", withCompany(a)),
  doitruReturnSources: (customer) => callMethod(NS + "doitru.get_return_sources", withCompany({ customer })),
  doitruCreateReturn: (invoice) => callMethod(NS + "doitru.create_return", withCompany({ invoice })),
  doitruUpload: (doctype, name, filename, content) => callMethod(NS + "doitru.upload_invoice_attachment", { doctype, name, filename, content }),
  doitruApprove: (doctype, name) => callMethod(NS + "doitru.approve_case", { doctype, name }),
  doitruMissingEinvoice: (a) => callMethod(NS + "doitru.get_missing_einvoice", withCompany(a)),
  doitruJeOptions: () => callMethod(NS + "doitru.get_je_options", withCompany()),
  doitruCreateJe: (a) => callMethod(NS + "doitru.create_je", withCompany(a)),
  customerFiles: (customer) => callMethod(NS + "doitru.get_customer_files", { customer }),
  customerFileUpload: (customer, filename, content) => callMethod(NS + "doitru.upload_customer_file", { customer, filename, content }),

  // Hóa đơn VAT (đối soát MISA)
  vatOverview: (a) => callMethod(NS + "misa_vat.get_overview", withCompany(a)),
  vatInvoices: (bucket, a) => callMethod(NS + "misa_vat.get_invoices", withCompany({ bucket, ...a })),
  vatSearchInvoices: (txt) => callMethod(NS + "misa_vat.search_invoices", withCompany({ txt })),
  vatSync: (a) => callMethod(NS + "misa_vat.sync_now", withCompany(a)),
  vatRelink: (snapshot, sales_invoice, note) => callMethod(NS + "misa_reconcile.relink_snapshot", { snapshot, sales_invoice, note }),
  vatMarkOrigin: (snapshot, origin, note) => callMethod(NS + "misa_reconcile.mark_origin", { snapshot, origin, note }),
  vatImportPreview: (content) => callMethod(NS + "misa_import.preview", { content }),
  vatImportCommit: (content) => callMethod(NS + "misa_import.commit", { content }),
  vatLegacyPreview: (a) => callMethod(NS + "misa_legacy.preview", withCompany(a)),
  vatLegacyCommit: (a) => callMethod(NS + "misa_legacy.commit", withCompany(a)),
  // `expected_hash` đi kèm trong `a` — backend từ chối nạp nếu thiếu.

  // Công nợ MT (siêu thị hiện đại) + bảng kê thanh toán của chuỗi
  // LƯU Ý: mọi con số "đã thu / còn lại" ở kênh này tính từ BẢNG KÊ CHUỖI, không
  // phải outstanding_amount của ERPNext — hệ thống cố ý không tự tạo Payment Entry.
  mtOverview: (a) => callMethod(NS + "mt.get_overview", withCompany(a)),
  mtInvoices: (bucket, a) => callMethod(NS + "mt.get_invoices", withCompany({ bucket, ...a })),
  mtChainSummary: (a) => callMethod(NS + "mt.get_chain_summary", withCompany(a)),
  // Công nợ chi tiết TRÊN ĐẦU TỪNG KHÁCH — cấp chuỗi chỉ để nhìn tổng, đi đòi
  // nợ thì phải theo pháp nhân (riêng Co.op có 120 siêu thị thành viên).
  mtCustomerSummary: (a) => callMethod(NS + "mt.get_customer_summary", withCompany(a)),
  // Gán chuỗi cho khách — chỗ gán CHÍNH THỨC. Suy từ bảng kê đã nạp là vòng
  // luẩn quẩn: khách mới ký hợp đồng chưa có bảng kê nào thì không gán được.
  mtCustomers: (a) => callMethod(NS + "mt.get_mt_customers", withCompany(a)),
  mtChainAssignment: (a) => callMethod(NS + "mt.get_chain_assignment", withCompany(a)),
  mtSetCustomerChain: (customer, chain) => callMethod(NS + "mt.set_customer_chain", { customer, chain }),
  // Xem trước BẮT BUỘC chạy trước khi nạp — nó trả `plan_hash` mà commit đòi.
  mtAdvicePreview: (a) => callMethod(NS + "mt.preview_advice", withCompany(a)),
  mtAdviceCommit: (a) => callMethod(NS + "mt.commit_advice", withCompany(a)),
  // `expected_hash` đi kèm trong `a` — backend từ chối nạp nếu thiếu hoặc lệch.
  mtRelinkLine: (line, sales_invoice, note) => callMethod(NS + "mt.relink_line", { line, sales_invoice, note }),

  // Điểm siêu thị (master) — trả lời hai câu: điểm này thuộc PHÁP NHÂN nào, và
  // xuất hóa đơn cho điểm này thì lấy địa chỉ/MST ở đâu. Riêng Co.op có ~120
  // siêu thị thành viên nên không thể quản theo chuỗi.
  mtStores: (a) => callMethod(NS + "mt_store.list_stores", withCompany(a)),
  // Dựng từ CÁC BẢNG KÊ ĐÃ NẠP trên site, không từ file mẫu. Xem trước BẮT BUỘC
  // (mã của Central Retail do hệ thống sinh từ tên, người phải nhìn trước).
  mtStoreSeedPreview: (a) => callMethod(NS + "mt_store.preview_seed", withCompany(a)),
  mtStoreSeedCommit: (a) => callMethod(NS + "mt_store.commit_seed", withCompany(a)),
  // `expected_hash` đi kèm trong `a` — backend từ chối tạo nếu thiếu hoặc lệch.
  mtStoreSave: (a) => callMethod(NS + "mt_store.save_store", a),
  mtStoreAddresses: (txt, customer) => callMethod(NS + "mt_store.search_addresses", { txt, customer }),

  // Bút toán kênh MT — sinh Journal Entry NHÁP từ bảng kê. Hệ thống KHÔNG bao
  // giờ tự ghi sổ: không có tham số nào bật submit tự động.
  mtJeAdvices: (a) => callMethod(NS + "mt_je.list_advices", withCompany(a)),
  mtJeAccountMap: (a) => callMethod(NS + "mt_je.get_account_map", withCompany(a)),
  // Xem trước BẮT BUỘC — nó trả `plan_hash` mà lệnh sinh đòi.
  mtJePreview: (advice, a) => callMethod(NS + "mt_je.preview_journal_entries", withCompany({ advice, ...a })),
  mtJeCreate: (advice, a) => callMethod(NS + "mt_je.create_journal_entries", withCompany({ advice, ...a })),
  // `expected_hash` đi kèm trong `a` — backend từ chối sinh nếu thiếu hoặc lệch.

  // Duyệt bút toán — chỗ DUY NHẤT của kênh MT mà tiền thật sự vào sổ.
  mtJeDrafts: (a) => callMethod(NS + "mt_je.list_draft_journal_entries", withCompany(a)),
  mtJeDetail: (name) => callMethod(NS + "mt_je.get_journal_entry", withCompany({ name })),
  // `force_unreconciled=1` là XÁC NHẬN CÓ Ý THỨC khi bảng kê chưa tick đối chiếu.
  // Không có cờ này thì backend trả `needs_confirm` chứ không ghi sổ.
  mtJeSubmit: (names, a) => callMethod(NS + "mt_je.submit_journal_entries",
                                       withCompany({ names: JSON.stringify(names), ...a })),
  mtJeDeleteDrafts: (names) => callMethod(NS + "mt_je.delete_draft_journal_entries",
                                          withCompany({ names: JSON.stringify(names) })),

  // Chiều CHIẾT KHẤU — mình xuất hóa đơn CK theo quy trình BKCK (§3 SOP).
  // Đọc file doanh số của chuỗi -> lập bảng kê -> chốt (cấp số) -> ghi số hóa
  // đơn đã xuất trên MISA -> sinh bút toán.
  mtDiscountRead: (content, chain) => callMethod(NS + "mt_discount_read.preview", { content, chain }),
  mtDiscountPreview: (a) => callMethod(NS + "mt_discount.preview_sheets", withCompany(a)),
  mtDiscountCommit: (a) => callMethod(NS + "mt_discount.commit_sheets", withCompany(a)),
  // `expected_hash` đi kèm trong `a` — backend từ chối lập nếu thiếu hoặc lệch.
  mtDiscountSheets: (a) => callMethod(NS + "mt_discount.list_sheets", withCompany(a)),
  mtDiscountSheet: (name) => callMethod(NS + "mt_discount.get_sheet", withCompany({ name })),
  // CHỐT mới cấp số NNN/BKCK/HG-MT — nháp bị xóa mà đã ăn số là dãy thủng lỗ.
  mtDiscountFinalize: (name, sheet_date) => callMethod(NS + "mt_discount.finalize_sheet",
                                                       withCompany({ name, sheet_date })),
  mtDiscountSetInvoice: (a) => callMethod(NS + "mt_discount.set_invoice", withCompany(a)),
  mtDiscountJePreview: (name) => callMethod(NS + "mt_discount.preview_journal_entry",
                                            withCompany({ name })),
  mtDiscountJeCreate: (a) => callMethod(NS + "mt_discount.create_journal_entry", withCompany(a)),

  // Hồ sơ thanh toán WinCommerce — Win chỉ xử lý khi file PDF đặt ĐÚNG TÊN
  // (YYYYMMDD_<mã NCC>_<stt>_PF). Sai tên là hồ sơ bị trả, cả đợt trượt kỳ.
  mtWinDossiers: (a) => callMethod(NS + "mt_win.list_dossiers", withCompany(a)),
  mtWinPreview: (a) => callMethod(NS + "mt_win.preview_dossier", withCompany(a)),
  mtWinCommit: (a) => callMethod(NS + "mt_win.commit_dossier", withCompany(a)),
  // `expected_hash` đi kèm trong `a` — backend từ chối lập nếu thiếu hoặc lệch.
  mtWinDossier: (name) => callMethod(NS + "mt_win.get_dossier", withCompany({ name })),
  mtWinSubmitted: (name) => callMethod(NS + "mt_win.mark_submitted", withCompany({ name })),
  mtWinExport: (name) => downloadPost(NS + "mt_win.export_dossier", withCompany({ name })),

  // Alerts
  alerts: (a) => callMethod(NS + "alerts.get_alerts", withCompany(a)),

  // Phân quyền user (chief)
  usersList: () => callMethod(NS + "users.get_users", {}),
  usersSetRoles: (user, roles) => callMethod(NS + "users.set_roles", { user, roles: JSON.stringify(roles) }),

  // Cashbook
  cashbookOptions: (a) => callMethod(NS + "cashbook.get_form_options", withCompany(a)),
  cashbookCreate: (a) => callMethod(NS + "cashbook.create_entry", withCompany(a)),

  // Bank statement import
  bankImportOptions: (a) => callMethod(NS + "bankimport.get_import_options", withCompany(a)),
  bankParse: (content, a) => callMethod(NS + "bankimport.parse_statement", withCompany({ content, ...a })),
  bankImport: (rows, bank_account, a) => callMethod(NS + "bankimport.import_transactions", withCompany({ rows: JSON.stringify(rows), bank_account, ...a })),
  bankGetRules: (a) => callMethod(NS + "bankimport.get_rules", withCompany(a)),
  bankSearchParty: (party_type, txt) => callMethod(NS + "bankimport.search_party", { party_type, txt: txt || "", limit: 50 }),
  bankSaveRule: (a) => callMethod(NS + "bankimport.save_rule", withCompany(a)),
  bankDeleteRule: (name) => callMethod(NS + "bankimport.delete_rule", { name }),
};
