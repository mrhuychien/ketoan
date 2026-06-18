// router.js — hash router hỗ trợ :param và ?query. 1 route → 1 view file.

export function parseHash() {
  let h = (location.hash || "#/").replace(/^#/, "");
  if (!h.startsWith("/")) h = "/" + h;
  const [path, qs] = h.split("?");
  const query = {};
  if (qs) {
    new URLSearchParams(qs).forEach((val, key) => { query[key] = val; });
  }
  return { path: path.replace(/\/+$/, "") || "/", query };
}

// Khớp pattern dạng "/khach/:id" với path thực.
export function matchRoute(routes, path) {
  for (const route of routes) {
    const pp = route.pattern.split("/").filter(Boolean);
    const sp = path.split("/").filter(Boolean);
    if (pp.length !== sp.length) continue;
    const params = {};
    let ok = true;
    for (let i = 0; i < pp.length; i++) {
      if (pp[i].startsWith(":")) params[pp[i].slice(1)] = decodeURIComponent(sp[i]);
      else if (pp[i] !== sp[i]) { ok = false; break; }
    }
    if (ok) return { route, params };
  }
  return null;
}

export function navigate(path) {
  location.hash = path.startsWith("#") ? path : "#" + path;
}

// Cập nhật query trên URL mà KHÔNG re-render (đồng bộ lựa chọn trong-view).
export function replaceQuery(path, query) {
  const qs = new URLSearchParams(query).toString();
  const h = "#" + path + (qs ? "?" + qs : "");
  history.replaceState(null, "", h);
}
