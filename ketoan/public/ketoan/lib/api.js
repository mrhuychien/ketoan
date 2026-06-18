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

export const api = {
  call: callMethod,
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

  // Alerts
  alerts: (a) => callMethod(NS + "alerts.get_alerts", withCompany(a)),

  // Cashbook
  cashbookOptions: (a) => callMethod(NS + "cashbook.get_form_options", withCompany(a)),
  cashbookCreate: (a) => callMethod(NS + "cashbook.create_entry", withCompany(a)),
};
