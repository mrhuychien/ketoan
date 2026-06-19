// shell.js — khung SPA: header, điều hướng, hash router, nạp view code-split.
import { parseHash, matchRoute, navigate } from "./lib/router.js";
import { html, setHTML } from "./lib/dom.js";
import { toast } from "./components/toast.js";

const CTX = window.KETOAN_CONTEXT || {};
const BASE = "/assets/ketoan/ketoan";
const V = CTX.assetVersion || "";
const withV = (p) => `${BASE}/${p}?v=${V}`;

// route → file view (KHÔNG cho vào import map; mang ?v= khi dynamic import).
const ROUTES = [
  { pattern: "/", view: "views/dashboard.js", nav: "dashboard", title: "Tổng quan" },
  { pattern: "/cong-no", view: "views/receivables.js", nav: "cong-no", title: "Công nợ" },
  { pattern: "/doi-chieu-npp", view: "views/npp.js", nav: "npp", title: "Đối chiếu NPP" },
  { pattern: "/khach/:id", view: "views/customer.js", nav: "cong-no", title: "360° khách" },
  { pattern: "/quy", view: "views/cash.js", nav: "quy", title: "Sổ quỹ", cap: "cash" },
  { pattern: "/canh-bao", view: "views/alerts.js", nav: "canh-bao", title: "Cảnh báo" },
  { pattern: "/tien-ich", view: "views/utilities.js", nav: "tien-ich", title: "Tiện ích" },
];

const CAN_CASH = !!CTX.canViewCash;

const NAV_ITEMS = [
  { key: "dashboard", path: "/", icon: "fa-gauge-high", label: "Tổng quan" },
  { key: "cong-no", path: "/cong-no", icon: "fa-file-invoice-dollar", label: "Công nợ" },
  { key: "npp", path: "/doi-chieu-npp", icon: "fa-handshake", label: "Đối chiếu NPP" },
  { key: "quy", path: "/quy", icon: "fa-wallet", label: "Sổ quỹ", cap: "cash" },
  { key: "canh-bao", path: "/canh-bao", icon: "fa-triangle-exclamation", label: "Cảnh báo" },
  { key: "tien-ich", path: "/tien-ich", icon: "fa-bolt", label: "Tiện ích" },
].filter((n) => n.cap !== "cash" || CAN_CASH);

function renderShell() {
  const root = document.getElementById("kt-root");
  setHTML(
    root,
    html`
      <div class="kt-app">
        <header class="kt-header">
          <div class="kt-header-left">
            <div class="kt-logo"><i class="fas fa-coins"></i></div>
            <div class="kt-header-title">
              <h1>Kế toán Tác nghiệp</h1>
              <p>Bàn làm việc Công nợ &amp; Quỹ · ${CTX.company || ""}</p>
            </div>
          </div>
          <div class="kt-header-right">
            <a class="kt-erp-link" href="/app" title="Mở ERPNext Desk"><i class="fas fa-up-right-from-square"></i> Desk</a>
            <div class="kt-user">
              <span class="kt-user-name">${CTX.fullName || CTX.user || ""}</span>
              ${CTX.isManager ? html`<span class="kt-badge kt-badge--gold">Kế toán trưởng</span>` : ""}
            </div>
          </div>
        </header>
        <nav class="kt-nav" id="kt-nav">
          ${NAV_ITEMS.map(
            (n) => html`<a class="kt-nav-item" data-nav="${n.key}" href="#${n.path}"><i class="fas ${n.icon}"></i><span>${n.label}</span></a>`
          )}
        </nav>
        <main class="kt-main" id="kt-view"><div class="kt-boot"><div class="kt-spinner"></div></div></main>
      </div>
    `
  );
}

function setActiveNav(navKey) {
  document.querySelectorAll(".kt-nav-item").forEach((a) => {
    a.classList.toggle("is-active", a.dataset.nav === navKey);
  });
}

let currentCleanup = null;

async function route() {
  const { path, query } = parseHash();
  const matched = matchRoute(ROUTES, path);
  const view = document.getElementById("kt-view");
  if (!view) return;

  if (!matched) {
    setHTML(view, html`<div class="kt-empty"><i class="fas fa-compass"></i><p>Không tìm thấy trang. <a href="#/">Về tổng quan</a></p></div>`);
    return;
  }

  // Chặn truy cập màn quỹ nếu không có quyền (vd kế toán công nợ).
  if (matched.route.cap === "cash" && !CAN_CASH) {
    setActiveNav(null);
    setHTML(view, html`<div class="kt-empty"><i class="fas fa-lock"></i><p>Bạn không có quyền xem nghiệp vụ quỹ/tiền.<br><a href="#/">Về tổng quan</a></p></div>`);
    return;
  }

  setActiveNav(matched.route.nav);
  setHTML(view, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  // dọn view trước (vd destroy chart)
  if (typeof currentCleanup === "function") {
    try { currentCleanup(); } catch (_) {}
    currentCleanup = null;
  }

  try {
    const mod = await import(withV(matched.route.view));
    const cleanup = await mod.render({ container: view, params: matched.params, query });
    if (typeof cleanup === "function") currentCleanup = cleanup;
  } catch (err) {
    console.error("[ketoan] load view failed", err);
    setHTML(view, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>Lỗi tải màn hình: ${err.message || err}</p></div>`);
    toast("Lỗi tải màn hình", "error");
  }
}

function boot() {
  renderShell();
  window.addEventListener("hashchange", route);
  if (!location.hash) navigate("/");
  route();
}

boot();
