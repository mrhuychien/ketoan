// views/workspace.js — trang 1 NGHIỆP VỤ: Hướng dẫn · KPI trực quan · Thực hiện · Báo cáo · Công cụ.
import { html, setHTML } from "../lib/dom.js";
import { getWorkspace } from "../lib/workspaces.js";
import { api } from "../lib/api.js";
import { formatVNDShort } from "../lib/format.js";

export async function render({ container, params }) {
  const ws = getWorkspace(params.key);
  if (!ws) {
    setHTML(container, html`<div class="kt-empty"><i class="fas fa-compass"></i><p>Không có nghiệp vụ này. <a href="#/">Về trang chủ</a></p></div>`);
    return;
  }

  const actions = ws.sections.find((s) => s.title === "Thực hiện");
  const others = ws.sections.filter((s) => s.title !== "Thực hiện");

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas ${ws.icon}"></i> ${ws.label}</div>
        <div class="kt-sub">${ws.desc}</div>
      </div>

      ${ws.guide && ws.guide.length
        ? html`<div class="kt-card kt-guide kt-mb">
            <div class="kt-card-head kt-guide-head" id="ws-guide-toggle">
              <div class="kt-card-title"><i class="fas fa-book-open"></i> Hướng dẫn nghiệp vụ</div>
              <span class="kt-btn-icon"><i class="fas fa-chevron-down" id="ws-guide-chev"></i></span>
            </div>
            <div class="kt-card-body" id="ws-guide-body">
              <ol class="kt-guide-steps">
                ${ws.guide.map((g) => html`<li>${g}</li>`)}
              </ol>
            </div>
          </div>`
        : ""}

      <div class="kt-stats" id="ws-kpi" style="display:none"></div>

      ${actions
        ? html`<div class="kt-card kt-mb">
            <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-bolt"></i> Thực hiện</div></div>
            <div class="kt-card-body"><div class="kt-ws-actions">
              ${actions.items.map((it) => actionBtn(it))}
            </div></div>
          </div>`
        : ""}

      <div class="kt-ws-sections">
        ${others.map((sec) => sectionCard(sec))}
      </div>
    `
  );

  // Thu gọn/mở hướng dẫn (nhớ trạng thái theo nghiệp vụ).
  const gBody = container.querySelector("#ws-guide-body");
  const gChev = container.querySelector("#ws-guide-chev");
  const gKey = "kt-guide-" + ws.key;
  const applyGuide = (open) => {
    if (!gBody) return;
    gBody.style.display = open ? "" : "none";
    if (gChev) gChev.className = "fas " + (open ? "fa-chevron-up" : "fa-chevron-down");
  };
  if (gBody) {
    applyGuide(localStorage.getItem(gKey) !== "closed");
    container.querySelector("#ws-guide-toggle").addEventListener("click", () => {
      const open = gBody.style.display === "none";
      applyGuide(open);
      try { localStorage.setItem(gKey, open ? "open" : "closed"); } catch (_) {}
    });
  }

  loadKpis(ws.key, container.querySelector("#ws-kpi"));
}

/* ---- KPI trực quan theo nghiệp vụ (best-effort, lỗi thì ẩn) ---- */
async function loadKpis(key, host) {
  if (!host) return;
  let cards = [];
  try {
    if (key === "npp" || key === "mt" || key === "travel") {
      const ch = key === "npp" ? "npp" : key === "mt" ? "mt" : "khac";
      const a = await api.aging(ch);
      const overdue = a.buckets.filter((b) => b.key !== "current").reduce((s, b) => s + b.amount, 0);
      cards.push({ label: "Công nợ kênh", value: formatVNDShort(a.total), cls: "is-grad", go: "#/cong-no/" + ch });
      cards.push({ label: "Nợ quá hạn", value: formatVNDShort(overdue), cls: overdue > 0 ? "neg" : "pos", go: "#/cong-no/" + ch });
      if (key === "npp") {
        try {
          const c = await api.doitruCases();
          const pending = (c.counts.cho_hoadon || 0) + (c.counts.cho_duyet || 0);
          cards.push({ label: "Đối trừ chờ xử lý", value: pending, cls: pending ? "warn" : "pos", go: "#/doi-chieu-npp" });
        } catch (_) {}
        try {
          const e = await api.doitruMissingEinvoice();
          if (e.supported) cards.push({ label: "Chưa xuất HĐĐT", value: e.rows.length, cls: e.rows.length ? "warn" : "pos", go: "#/doi-chieu-npp" });
        } catch (_) {}
      }
    } else if (key === "purchase") {
      const a = await api.apAging();
      const overdue = a.buckets.filter((b) => b.key !== "current").reduce((s, b) => s + b.amount, 0);
      cards.push({ label: "Còn phải trả", value: formatVNDShort(a.total), cls: "is-grad", go: "#/cong-no-ncc" });
      cards.push({ label: "Quá hạn trả", value: formatVNDShort(overdue), cls: overdue > 0 ? "neg" : "pos", go: "#/cong-no-ncc" });
    } else if (key === "gl") {
      const b = await api.balances();
      cards.push({ label: "Tổng số dư quỹ", value: formatVNDShort(b.total), cls: b.total < 0 ? "neg" : "is-grad", go: "#/quy" });
      cards.push({ label: "Số TK tiền", value: b.rows.length, cls: "", go: "#/quy" });
    } else if (key === "chief") {
      const o = await api.overview();
      cards.push({ label: "Tổng công nợ", value: formatVNDShort(o.cards.total_ar), cls: "is-grad", go: "#/cong-no" });
      cards.push({ label: "Nợ quá hạn", value: formatVNDShort(o.cards.overdue), cls: "neg", go: "#/cong-no" });
      if (o.cards.cash_total != null) cards.push({ label: "Số dư quỹ", value: formatVNDShort(o.cards.cash_total), cls: o.cards.cash_total < 0 ? "neg" : "pos", go: "#/quy" });
      cards.push({ label: "Cảnh báo", value: o.alerts.length, cls: o.alerts.length ? "warn" : "pos", go: "#/canh-bao" });
    }
  } catch (_) {
    return; // không có quyền/không dữ liệu → ẩn KPI, không phá trang
  }
  if (!cards.length) return;
  host.style.display = "";
  setHTML(
    host,
    html`${cards.map(
      (c) => html`<div class="kt-stat is-link" data-go="${c.go || ""}">
        <div class="kt-stat-label">${c.label}</div>
        <div class="kt-stat-value ${c.cls || ""}">${c.value}</div>
      </div>`
    )}`
  );
  host.querySelectorAll("[data-go]").forEach((el) =>
    el.addEventListener("click", () => { if (el.dataset.go) location.hash = el.dataset.go; })
  );
}

function actionBtn(it) {
  const isDesk = it.type === "desk";
  const href = isDesk ? it.href : "#" + it.route;
  return html`<a class="kt-ws-action" href="${href}" target="${isDesk ? "_blank" : ""}">
    <i class="fas ${it.icon || "fa-bolt"}"></i><span>${it.label}</span>
    ${isDesk ? html`<i class="fas fa-up-right-from-square kt-ws-action-ext"></i>` : ""}
  </a>`;
}

function sectionCard(sec) {
  return html`
    <div class="kt-card kt-ws-section">
      <div class="kt-card-head"><div class="kt-card-title"><i class="fas ${sec.icon}"></i> ${sec.title}</div></div>
      <div class="kt-card-body">
        <div class="kt-ws-items">
          ${sec.items.length ? sec.items.map((it) => itemLink(it)) : html`<div class="kt-sub">Sắp có…</div>`}
        </div>
      </div>
    </div>`;
}

function itemLink(it) {
  const isDesk = it.type === "desk";
  const href = isDesk ? it.href : "#" + it.route;
  const target = isDesk ? "_blank" : "";
  return html`<a class="kt-ws-item" href="${href}" target="${target}">
    <span class="kt-ws-item-ico"><i class="fas ${it.icon || "fa-arrow-right"}"></i></span>
    <span class="kt-ws-item-label">${it.label}</span>
    <span class="kt-ws-item-go"><i class="fas ${isDesk ? "fa-up-right-from-square" : "fa-chevron-right"}"></i></span>
  </a>`;
}
