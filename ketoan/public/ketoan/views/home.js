// views/home.js — trang chủ: chọn "bàn làm việc" theo vai trò.
import { html, setHTML } from "../lib/dom.js";
import { navigate } from "../lib/router.js";
import { myWorkspaces } from "../lib/workspaces.js";

const CTX = window.KETOAN_CONTEXT || {};

export async function render({ container }) {
  const list = myWorkspaces();

  if (!list.length) {
    setHTML(container, html`<div class="kt-empty"><i class="fas fa-user-lock"></i>
      <p>Tài khoản của bạn chưa được gán vai trò kế toán nào.<br>Liên hệ quản trị để gán vai trò (Kế toán bán hàng / mua hàng / tiền lương / hạch toán / trưởng).</p></div>`);
    return;
  }

  // Chỉ 1 vai trò → vào thẳng.
  if (list.length === 1) {
    navigate("/vt/" + list[0].key);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-house"></i> Xin chào, ${CTX.fullName || CTX.user || ""}</div>
        <div class="kt-sub">Chọn bàn làm việc theo vai trò</div>
      </div>
      <div class="kt-ws-grid">
        ${list.map(
          (w) => html`<a class="kt-ws-card" href="#/vt/${w.key}">
            <div class="kt-ws-ico"><i class="fas ${w.icon}"></i></div>
            <div class="kt-ws-name">${w.label}</div>
            <div class="kt-ws-desc">${w.desc}</div>
            <div class="kt-ws-go"><i class="fas fa-arrow-right"></i></div>
          </a>`
        )}
      </div>
    `
  );
}
