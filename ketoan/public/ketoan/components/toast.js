// toast.js — thông báo nổi góc dưới.
let el = null;

function ensure() {
  if (!el) {
    el = document.createElement("div");
    el.className = "kt-toast";
    document.body.appendChild(el);
  }
  return el;
}

export function toast(msg, type = "success") {
  const t = ensure();
  t.textContent = msg;
  t.className = "kt-toast kt-toast--" + type + " is-show";
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("is-show"), 3500);
}
