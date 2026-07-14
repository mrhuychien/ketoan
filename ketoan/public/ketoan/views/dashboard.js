// views/dashboard.js — "hôm nay": KPI + tuổi nợ + quỹ + cảnh báo tóm tắt.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatVNDShort, escapeHtml } from "../lib/format.js";

const SEV = { danger: "red", warning: "yellow", info: "green" };
const BAR = { current: "var(--kt-success)", b1: "#a3e635", b2: "var(--kt-warning)", b3: "#fb923c", over: "var(--kt-danger)" };
const CAN_CASH = !!(window.KETOAN_CONTEXT || {}).canViewCash;

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try {
    d = await api.overview();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const c = d.cards;
  const maxAging = Math.max(1, ...d.aging.map((b) => b.amount));

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas fa-gauge-high"></i> Tổng quan hôm nay</div>
          <div class="kt-sub">Cập nhật ${escapeHtml(d.as_of)} · ${escapeHtml(d.company)}</div>
        </div>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/vt/chief"><i class="fas fa-book-open"></i> Hướng dẫn &amp; lối tắt</a>
      </div>

      <div class="kt-stats">
        <div class="kt-stat is-link" data-go="#/cong-no">
          <div class="kt-stat-label"><i class="fas fa-file-invoice-dollar"></i> Tổng công nợ</div>
          <div class="kt-stat-value is-grad">${formatVND(c.total_ar)}</div>
        </div>
        <div class="kt-stat is-link" data-go="#/cong-no">
          <div class="kt-stat-label"><i class="fas fa-clock"></i> Nợ quá hạn</div>
          <div class="kt-stat-value neg">${formatVND(c.overdue)}</div>
        </div>
        <div class="kt-stat is-link" data-go="#/canh-bao">
          <div class="kt-stat-label"><i class="fas fa-user-shield"></i> Khách vượt hạn mức</div>
          <div class="kt-stat-value warn">${c.over_limit_customers}</div>
        </div>
        ${CAN_CASH
          ? html`<div class="kt-stat is-link" data-go="#/quy">
              <div class="kt-stat-label"><i class="fas fa-wallet"></i> Số dư quỹ</div>
              <div class="kt-stat-value ${c.cash_total < 0 ? "neg" : "pos"}">${formatVND(c.cash_total)}</div>
            </div>`
          : ""}
        <div class="kt-stat is-link" data-go="#/canh-bao">
          <div class="kt-stat-label"><i class="fas fa-link-slash"></i> Khoản thu treo</div>
          <div class="kt-stat-value ${c.unallocated_payment > 0 ? "warn" : ""}">${formatVND(c.unallocated_payment)}</div>
        </div>
        <div class="kt-stat">
          <div class="kt-stat-label"><i class="fas fa-stopwatch"></i> DSO (ước tính)</div>
          <div class="kt-stat-value">${c.dso == null ? "—" : c.dso + " ngày"}</div>
        </div>
      </div>

      <div class="${CAN_CASH ? "kt-grid-2" : ""}">
        <div class="kt-card">
          <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-layer-group"></i> Tuổi nợ</div>
            <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/cong-no">Chi tiết</a></div>
          <div class="kt-card-body">
            <div class="kt-aging">
              ${d.aging.map(
                (b) => html`<div class="kt-aging-row">
                  <span>${b.label}</span>
                  <div class="kt-aging-track"><div class="kt-aging-fill" style="width:${Math.round((b.amount / maxAging) * 100)}%;background:${BAR[b.key] || "var(--kt-primary)"}"></div></div>
                  <span class="kt-aging-amt">${formatVNDShort(b.amount)}</span>
                </div>`
              )}
            </div>
          </div>
        </div>

        ${CAN_CASH
          ? html`<div class="kt-card">
              <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-money-bill-transfer"></i> Quỹ tiền</div>
                <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/quy">Sổ quỹ</a></div>
              <div class="kt-card-body">
                ${d.cash_accounts.length
                  ? html`<div class="kt-table-wrap"><table class="kt-table"><tbody>
                      ${d.cash_accounts.map(
                        (a) => html`<tr><td>${a.account_name || a.account}</td><td class="num ${a.balance < 0 ? "danger" : "pos"}">${formatVND(a.balance)}</td></tr>`
                      )}
                    </tbody></table></div>`
                  : html`<div class="kt-empty"><i class="fas fa-wallet"></i><p>Chưa có tài khoản tiền</p></div>`}
              </div>
            </div>`
          : ""}
      </div>

      <div class="kt-card kt-mb" style="margin-top:16px">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-triangle-exclamation"></i> Cảnh báo (${d.alerts.length})</div>
          <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/canh-bao">Xem tất cả</a></div>
        <div class="kt-card-body">
          ${d.alerts.length
            ? d.alerts.map(
                (a) => html`<div class="kt-alert kt-alert--${a.severity}">
                  <div class="kt-alert-head">
                    <div class="kt-alert-title"><span class="kt-light kt-light--${SEV[a.severity] || "yellow"}"></span> ${a.title}</div>
                    <span class="kt-badge kt-badge--${a.severity === "danger" ? "red" : a.severity === "warning" ? "yellow" : "green"}">${a.count} mục · ${formatVNDShort(a.amount)}</span>
                  </div>
                  <div class="kt-alert-hint">${a.hint || ""}</div>
                </div>`
              )
            : html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có cảnh báo. Mọi thứ ổn 👍</p></div>`}
        </div>
      </div>
    `
  );

  container.querySelectorAll("[data-go]").forEach((el) => {
    el.addEventListener("click", () => { location.hash = el.dataset.go; });
  });
}
