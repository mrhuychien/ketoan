// views/home.js — trang chủ gọn: VIỆC CẦN XỬ LÝ (nhóm theo nghiệp vụ)
// + dãy nút vào thẳng bàn làm việc của từng vai trò (kèm nút hướng dẫn nhỏ).
import { html, setHTML } from "../lib/dom.js";
import { myWorkspaces, workHome } from "../lib/workspaces.js";
import { api } from "../lib/api.js";

const CTX = window.KETOAN_CONTEXT || {};
const SEV_BADGE = { danger: "red", warning: "yellow", info: "green" };

export async function render({ container }) {
  const list = myWorkspaces();

  if (!list.length) {
    setHTML(container, html`<div class="kt-empty"><i class="fas fa-user-lock"></i>
      <p>Tài khoản của bạn chưa được gán vai trò kế toán nào.<br>Liên hệ quản trị để gán vai trò.</p></div>`);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-house"></i> Xin chào, ${CTX.fullName || CTX.user || ""}</div>
        <div class="kt-sub">Việc cần xử lý hôm nay + bàn làm việc của bạn</div>
      </div>

      <div id="home-tasks" class="kt-mb"><div class="kt-boot"><div class="kt-spinner"></div><p>Đang tổng hợp việc cần xử lý…</p></div></div>

      <div class="kt-view-head" style="margin-top:8px">
        <div class="kt-view-title" style="font-size:15px"><i class="fas fa-briefcase"></i> Bàn làm việc</div>
      </div>
      <div class="kt-home-roles">
        ${list.map(
          (w) => html`<div class="kt-home-role">
            <a class="kt-home-role-main" href="#${workHome(w)}">
              <i class="fas ${w.icon}"></i><span>${w.label}</span>
              <i class="fas fa-arrow-right kt-home-role-go"></i>
            </a>
            <a class="kt-home-role-help" href="#/vt/${w.key}" title="Hướng dẫn & lối tắt — ${w.label}"><i class="fas fa-book-open"></i></a>
          </div>`
        )}
      </div>
    `
  );

  loadTasks(container.querySelector("#home-tasks"));
}

async function loadTasks(host) {
  let d;
  try {
    d = await api.tasks();
  } catch (e) {
    setHTML(host, html`<div class="kt-sub">Không tải được việc cần xử lý: ${e.message}</div>`);
    return;
  }

  if (!d.groups.length) {
    setHTML(host, html`
      <div class="kt-card"><div class="kt-card-body" style="display:flex;align-items:center;gap:12px">
        <i class="fas fa-circle-check" style="font-size:26px;color:var(--kt-success)"></i>
        <div><b>Không có việc tồn đọng.</b><div class="kt-sub">Mọi nghiệp vụ của bạn đang sạch 👍</div></div>
      </div></div>`);
    return;
  }

  setHTML(
    host,
    html`
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-list-check"></i> Việc cần xử lý</div>
          <span class="kt-badge kt-badge--red">${d.total} việc</span>
        </div>
        <div class="kt-card-body">
          <div class="kt-task-groups">
            ${d.groups.map(
              (g) => html`
                <div class="kt-task-group">
                  <div class="kt-task-group-title"><i class="fas ${g.icon}"></i> ${g.group}</div>
                  ${g.items.map((it) => taskRow(it))}
                </div>`
            )}
          </div>
        </div>
      </div>
    `
  );
}

function taskRow(it) {
  const isDesk = !!it.href;
  const href = isDesk ? it.href : "#" + it.route;
  return html`<a class="kt-task-item" href="${href}" target="${isDesk ? "_blank" : ""}">
    <span class="kt-task-label">${it.label}</span>
    <span class="kt-badge kt-badge--${SEV_BADGE[it.severity] || "yellow"}">${it.count}</span>
    <span class="kt-ws-item-go"><i class="fas ${isDesk ? "fa-up-right-from-square" : "fa-chevron-right"}"></i></span>
  </a>`;
}
