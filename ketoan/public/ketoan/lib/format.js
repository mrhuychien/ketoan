// format.js — định dạng tiền tệ/ngày + escape. Tập trung 1 chỗ (frappe-portal-spa).

export function formatNumber(n) {
  if (n == null || isNaN(n)) return "0";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(Math.round(n));
}

export function formatVND(n) {
  return formatNumber(n) + " ₫";
}

// Thẻ lớn: "1,6 tỷ" / "33 tr" / "120 k"
export function formatVNDShort(n) {
  const v = Math.abs(Number(n) || 0);
  const sign = n < 0 ? "-" : "";
  if (v >= 1e9) return sign + (v / 1e9).toFixed(v >= 1e10 ? 0 : 1).replace(".", ",") + " tỷ";
  if (v >= 1e6) return sign + Math.round(v / 1e6) + " tr";
  if (v >= 1e3) return sign + Math.round(v / 1e3) + " k";
  return sign + formatNumber(v);
}

export function formatDate(s) {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleDateString("vi-VN");
}

export function escapeHtml(s) {
  return (s == null ? "" : String(s))
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function daysLabel(d) {
  if (d == null) return "";
  if (d <= 0) return "trong hạn";
  return "quá " + d + " ngày";
}
