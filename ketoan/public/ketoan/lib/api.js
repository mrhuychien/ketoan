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

  // Receivables
  arSummary: (a) => callMethod(NS + "receivables.get_ar_summary", withCompany(a)),
  aging: (a) => callMethod(NS + "receivables.get_aging", withCompany(a)),
  customerDetail: (customer, a) => callMethod(NS + "receivables.get_customer_detail", withCompany({ customer, ...a })),
  dso: (a) => callMethod(NS + "receivables.get_dso", withCompany(a)),

  // Cash
  balances: (a) => callMethod(NS + "cash.get_balances", withCompany(a)),
  cashflow: (a) => callMethod(NS + "cash.get_cashflow", withCompany(a)),
  transactions: (a) => callMethod(NS + "cash.get_transactions", withCompany(a)),

  // NPP reconciliation
  nppDebts: (a) => callMethod(NS + "npp.get_debts", withCompany(a)),
  nppDiscountEligible: (month, a) => callMethod(NS + "npp.get_discount_eligible", withCompany({ month, ...a })),
  nppCreateDiscount: (customers, month, a) => callMethod(NS + "npp.create_discount_entries", withCompany({ customers: JSON.stringify(customers), month, ...a })),
  nppExportBulk: (customers, from_date, to_date) => downloadPost(NS + "npp.export_reconciliation_bulk", withCompany({ customers: JSON.stringify(customers), from_date, to_date })),

  // Alerts
  alerts: (a) => callMethod(NS + "alerts.get_alerts", withCompany(a)),

  // Cashbook
  cashbookOptions: (a) => callMethod(NS + "cashbook.get_form_options", withCompany(a)),
  cashbookCreate: (a) => callMethod(NS + "cashbook.create_entry", withCompany(a)),
};
