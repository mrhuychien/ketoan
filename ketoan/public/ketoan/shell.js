// shell.js — khung SPA: header, nav theo vai trò (workspace), hash router.
import { parseHash, matchRoute, navigate } from "./lib/router.js";
import { html, setHTML } from "./lib/dom.js";
import { toast } from "./components/toast.js";
import { myWorkspaces, getWorkspace } from "./lib/workspaces.js";

const CTX = window.KETOAN_CONTEXT || {};
const BASE = "/assets/ketoan/ketoan";
const V = CTX.assetVersion || "";
const withV = (p) => `${BASE}/${p}?v=${V}`;

const CAPS = CTX.caps || {};
const hasCap = (cap) => !cap || !!CAPS[cap];

// route → view. `cap`: capability cần có. `ws`: workspace để highlight nav.
const ROUTES = [
  { pattern: "/", view: "views/home.js", title: "Trang chủ" },
  { pattern: "/vt/:key", view: "views/workspace.js", title: "Workspace" },
  { pattern: "/dashboard", view: "views/dashboard.js", cap: "chief", ws: "chief", title: "Tổng quan" },
  { pattern: "/canh-bao", view: "views/alerts.js", cap: "chief", ws: "chief", title: "Cảnh báo" },
  { pattern: "/cong-no", view: "views/receivables.js", cap: "sales", ws: "sales", title: "Công nợ" },
  { pattern: "/doi-chieu-npp", view: "views/npp.js", cap: "sales", ws: "sales", title: "Đối chiếu NPP" },
  { pattern: "/khach/:id", view: "views/customer.js", cap: "sales", ws: "sales", title: "360° khách" },
  { pattern: "/tien-ich", view: "views/utilities.js", cap: "sales", ws: "sales", title: "Tiện ích" },
  { pattern: "/quy", view: "views/cash.js", cap: "gl", ws: "gl", title: "Sổ quỹ" },
  { pattern: "/nhap-sao-ke", view: "views/bankimport.js", cap: "gl", ws: "gl", title: "Nhập sao kê" },
  { pattern: "/luong", view: "views/payroll.js", cap: "payroll", ws: "payroll", title: "Tính lương" },
];

const NAV_WS = myWorkspaces();

function renderShell() {
  const root = document.getElementById("kt-root");
  setHTML(
    root,
    html`
      <div class="kt-app">
        <header class="kt-header">
          <div class="kt-header-left">
            <a class="kt-logo" href="#/"><i class="fas fa-calculator"></i></a>
            <div class="kt-header-title">
              <h1>Kế toán Tác nghiệp</h1>
              <p>${CTX.company || ""}</p>
            </div>
          </div>
          <div class="kt-header-right">
            <a class="kt-erp-link" href="/app" title="Mở ERPNext Desk"><i class="fas fa-up-right-from-square"></i> Desk</a>
            <div class="kt-user">
              <span class="kt-user-name">${CTX.fullName || CTX.user || ""}</span>
              ${CAPS.chief ? html`<span class="kt-badge kt-badge--gold">Kế toán trưởng</span>` : ""}
            </div>
          </div>
        </header>
        <nav class="kt-nav" id="kt-nav">
          <a class="kt-nav-item" data-nav="home" href="#/"><i class="fas fa-house"></i><span>Trang chủ</span></a>
          ${NAV_WS.map(
            (w) => html`<a class="kt-nav-item" data-nav="${w.key}" href="#/vt/${w.key}"><i class="fas ${w.icon}"></i><span>${w.label}</span></a>`
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
    setHTML(view, html`<div class="kt-empty"><i class="fas fa-compass"></i><p>Không tìm thấy trang. <a href="#/">Về trang chủ</a></p></div>`);
    return;
  }

  // Capability của route; với /vt/:key thì cap chính là key workspace.
  const cap = matched.route.pattern === "/vt/:key" ? matched.params.key : matched.route.cap;
  if (!hasCap(cap)) {
    setActiveNav(null);
    setHTML(view, html`<div class="kt-empty"><i class="fas fa-lock"></i><p>Bạn không có quyền xem chức năng này.<br><a href="#/">Về trang chủ</a></p></div>`);
    return;
  }

  // Highlight nav theo workspace của route.
  const navKey = path === "/" ? "home" : (matched.route.pattern === "/vt/:key" ? matched.params.key : matched.route.ws);
  setActiveNav(navKey || null);
  setHTML(view, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

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
