// views/roles.js — Phân quyền vai trò kế toán cho user (chỉ Kế toán trưởng).
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { toast } from "../components/toast.js";

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let data;
  try {
    data = await api.call("ketoan.api.users.get_users", {});
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const roles = data.roles;
  const state = { search: "" };

  function draw() {
    const q = state.search.toLowerCase().trim();
    const users = !q
      ? data.users
      : data.users.filter((u) => (u.full_name || "").toLowerCase().includes(q) || u.name.toLowerCase().includes(q));

    setHTML(
      container,
      html`
        <div class="kt-view-head">
          <div class="kt-view-title"><i class="fas fa-user-shield"></i> Phân quyền vai trò kế toán</div>
          <div class="kt-sub">Tick vai trò cho từng tài khoản rồi bấm Lưu. 1 tài khoản chọn được nhiều vai trò.</div>
        </div>

        <div class="kt-card">
          <div class="kt-card-head">
            <div class="kt-card-title"><i class="fas fa-users"></i> ${users.length} tài khoản</div>
            <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="rl-search" placeholder="Tìm tài khoản..." value="${state.search}"></div>
          </div>
          <div class="kt-card-body">
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr>
                <th>Tài khoản</th>
                ${roles.map((r) => html`<th style="text-align:center;white-space:normal;min-width:86px">${r.label}</th>`)}
                <th></th>
              </tr></thead>
              <tbody>
                ${users.map(
                  (u) => html`<tr data-user="${u.name}">
                    <td><b>${u.full_name || u.name}</b><br><span class="kt-sub">${u.name}</span></td>
                    ${roles.map(
                      (r) => html`<td style="text-align:center">
                        <input type="checkbox" class="rl-cb" data-user="${u.name}" value="${r.role}" ${u.roles.includes(r.role) ? "checked" : ""}>
                      </td>`
                    )}
                    <td class="num"><button class="kt-btn kt-btn--primary kt-btn--sm rl-save" data-user="${u.name}" disabled>Lưu</button></td>
                  </tr>`
                )}
              </tbody>
            </table></div>
            ${users.length === 0 ? html`<div class="kt-empty"><i class="fas fa-user-slash"></i><p>Không thấy tài khoản</p></div>` : ""}
            <p class="kt-sub" style="margin-top:10px">Chỉ thao tác trên 7 vai trò kế toán của portal — các role hệ thống khác không bị ảnh hưởng. Tài khoản quản trị (System Manager) chỉ System Manager sửa được.</p>
          </div>
        </div>
      `
    );

    const search = container.querySelector("#rl-search");
    let timer = null;
    search.addEventListener("input", () => {
      state.search = search.value;
      clearTimeout(timer);
      timer = setTimeout(draw, 200);
    });

    // Bật nút Lưu của dòng khi có thay đổi.
    container.querySelectorAll(".rl-cb").forEach((cb) =>
      cb.addEventListener("change", () => {
        const btn = container.querySelector(`.rl-save[data-user="${cb.dataset.user}"]`);
        if (btn) btn.disabled = false;
      })
    );

    container.querySelectorAll(".rl-save").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const user = btn.dataset.user;
        const picked = [...container.querySelectorAll(`.rl-cb[data-user="${user}"]:checked`)].map((c) => c.value);
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        try {
          const res = await api.call("ketoan.api.users.set_roles", { user, roles: JSON.stringify(picked) });
          const u = data.users.find((x) => x.name === user);
          if (u) u.roles = res.roles;
          toast(`Đã lưu quyền cho ${user}`, "success");
          btn.innerHTML = "Lưu";
        } catch (e) {
          toast(e.message, "error");
          btn.disabled = false;
          btn.innerHTML = "Lưu";
        }
      })
    );
  }

  draw();
}
