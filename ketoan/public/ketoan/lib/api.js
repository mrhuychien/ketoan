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
  tasks: (a) => callMethod(NS + "tasks.get_tasks", withCompany(a)),

  // Receivables (channel: npp | mt | khac | tat-ca)
  arSummary: (channel, a) => callMethod(NS + "receivables.get_ar_summary", withCompany({ channel: channel || "tat-ca", ...a })),
  aging: (channel, a) => callMethod(NS + "receivables.get_aging", withCompany({ channel: channel || "tat-ca", ...a })),
  customerDetail: (customer, a) => callMethod(NS + "receivables.get_customer_detail", withCompany({ customer, ...a })),
  customerLedger: (customer, a) => callMethod(NS + "receivables.get_customer_ledger", withCompany({ customer, ...a })),

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
