// views/mt.js — Công nợ MT (kênh siêu thị hiện đại).
//
// Ba tab: Quản lý thanh toán · Quản lý chiết khấu · Công nợ chung của chuỗi.
//
// ĐIỀU PHẢI NÓI RÕ TRÊN MÀN HÌNH, KHÔNG ĐƯỢC GIẤU:
// Mọi con số "đã thu / còn lại" ở đây tính từ BẢNG KÊ THANH TOÁN của chuỗi, KHÔNG
// phải outstanding_amount của ERPNext. Hệ thống cố ý KHÔNG tự tạo Payment Entry /
// Journal Entry từ file nhập — con người đọc bảng kê rồi mới quyết định hạch toán.
// Nếu kế toán tưởng đây là số dư sổ cái thì sẽ đối chiếu nhầm với sổ cái và kết
// luận sai. Vì vậy câu cảnh báo đó nằm ngay dưới tiêu đề, không nằm trong tooltip.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatVNDShort, formatDate, isoDate } from "../lib/format.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

const q = encodeURIComponent;

// ═══════════════════════════════════════════════════════════════════════════
// BÀN LÀM VIỆC XẾP THEO CHUỖI, KHÔNG THEO CHỨC NĂNG
//
// Bản cũ có bảy tab ngang: thanh toán · chiết khấu · công nợ chuỗi · bút toán ·
// bảng kê CK · hồ sơ Win · đến hạn. Mỗi tab đúng về mặt chức năng, nhưng kế
// toán MT không làm việc theo chức năng — họ làm theo CHUỖI: hôm nay xử LOTTE
// cho xong, mai tới Central Retail. Bảy tab buộc họ tự ghép bảy màn hình lại
// trong đầu mới thấy "chuỗi này còn thiếu gì".
//
// Bản này hai tầng:
//   · Tầng 0 — BẢNG CHUỖI: mỗi chuỗi một thẻ, hiện còn bao nhiêu việc.
//   · Tầng 1 — BÀN LÀM VIỆC: vào một chuỗi, các bước xếp theo ĐÚNG thứ tự
//     vòng đời tháng của SOP §1.
//
// Hai màn hình LIÊN CHUỖI được giữ lại vì chúng là việc liên chuỗi thật:
// duyệt bút toán hàng loạt, và công nợ đến hạn (việc hàng tuần, SOP §5).
// ═══════════════════════════════════════════════════════════════════════════

// `need` = cờ năng lực ở `mt_hub.get_board` phải bật thì bước mới hiện.
// Ẩn bước chuỗi KHÔNG có là điều đúng: hiện bước "lập bảng kê chiết khấu" cho
// Saigon Co.op là mời kế toán xuất một hóa đơn mình không được phép xuất
// (Co.op trừ 17,75% tại nguồn và CO.OP xuất hóa đơn).
// THỨ TỰ = VÒNG ĐỜI THÁNG, và số bước in ra ngay trên tab.
//
// Bản cũ render B3 · B1 · B2 · B4 · B4 · B5 — đúng chức năng, sai trình tự.
// Người mới vào không đọc được nên làm cái nào trước, còn người quen thì vẫn
// phải quét cả hàng để tìm bước mình cần vì vị trí không nói lên thứ tự.
//
// `no` là số bước của vòng đời (B1 xuất hóa đơn → B6 công nợ đến hạn). Hai tab
// KHÔNG mang số — "Hàng hoàn" và "Hồ sơ nộp" — vì chúng là việc TREO BÊN vòng
// đời chứ không phải một chặng mọi chuỗi đều đi qua: hồ sơ nộp chỉ Win có, còn
// hàng hoàn chỉ phát sinh khi có hàng quay về. Đánh số cho chúng là nói dối về
// một trình tự không tồn tại.
//
// `need` = cờ năng lực ở `mt_hub.get_board` phải bật thì bước mới hiện.
// Ẩn bước chuỗi KHÔNG có là điều đúng: hiện bước "lập bảng kê chiết khấu" cho
// Saigon Co.op là mời kế toán xuất một hóa đơn mình không được phép xuất
// (Co.op trừ 17,75% tại nguồn và CO.OP xuất hóa đơn).
const STEPS = [
  { key: "cho-xuat-hd", no: "1", label: "Chờ xuất hóa đơn", icon: "fa-truck",
    need: "has_dossier", count: [],
    hint: "Hàng ĐÃ GIAO nhưng CHƯA xuất hóa đơn — Win chỉ cho xuất sau khi có phiếu nhập kho của họ. Đây CHƯA phải công nợ, nên không nằm trong số còn nợ." },
  // SỔ THEO DÕI — chỗ LÀM VIỆC quen thuộc, không phải một báo cáo. Nó thay
  // cuốn Excel kế toán vẫn mở suốt ngày.
  { key: "so-theo-doi", no: "2", label: "Sổ theo dõi hóa đơn", icon: "fa-book-open",
    need: null, count: [],
    hint: "Một dòng mỗi hóa đơn: hàng đã đi → hóa đơn MISA → tiền về → còn lại. Bấm một dòng để xem đợt thanh toán nào trả nó và đợt đó bị trừ những gì." },
  { key: "hang-hoan", no: "", label: "Hàng hoàn chờ xử lý", icon: "fa-rotate-left",
    need: null, count: ["hoan_chua_vao_so", "hoan_open"],
    hint: "Mỗi LẦN HÀNG QUAY VỀ một dòng: nhận phiếu sự cố bên vận chuyển vào sổ → lập phiếu trả hàng ERPNext → hóa đơn thay thế/điều chỉnh. Một hóa đơn có thể có hai lần hàng về, và mỗi lần cần một phiếu trả riêng." },
  { key: "chiet-khau", no: "3", label: "Chiết khấu mình xuất", icon: "fa-file-signature",
    need: "we_issue_discount", count: ["sheets_draft", "sheets_await_invoice"],
    hint: "Nạp file doanh số/TBCK → lập bảng kê BKCK → chốt lấy số → xuất hóa đơn CK trên MISA → ghi số về → sinh bút toán." },
  { key: "ho-so", no: "", label: "Hồ sơ nộp", icon: "fa-folder-open",
    need: "has_dossier", count: ["dossiers_draft"],
    hint: "Bảng kê Excel + PDF đặt ĐÚNG TÊN. Win không xử lý thanh toán khi hồ sơ sai tên." },
  { key: "thanh-toan", no: "4", label: "Đối soát thanh toán", icon: "fa-money-check-dollar",
    need: null, count: ["advices_unreconciled", "lines_unmatched", "lines_review"],
    hint: "Nạp bảng kê của chuỗi → hệ khớp từng dòng với hóa đơn → xử lý dòng chưa khớp và dòng cần review." },
  { key: "but-toan", no: "5", label: "Bút toán", icon: "fa-file-invoice-dollar",
    need: null, count: ["draft_je"],
    hint: "Sinh bút toán NHÁP từ bảng kê rồi duyệt từng cái. Hệ thống không bao giờ tự ghi sổ." },
  { key: "cong-no", no: "6", label: "Công nợ đến hạn", icon: "fa-clock",
    need: null, count: [],
    hint: "Hóa đơn của chuỗi này còn nợ, xếp theo tuổi nợ tính từ hạn khai trên khách." },
];

// Màn hình liên chuỗi — KHÔNG thuộc chuỗi nào.
const GLOBAL_VIEWS = [
  { key: "g-but-toan", label: "Duyệt bút toán toàn kênh", icon: "fa-stamp",
    hint: "Duyệt/xóa bút toán nháp của MỌI chuỗi trong một lần." },
  { key: "g-cong-no", label: "Công nợ đến hạn toàn kênh", icon: "fa-clock",
    hint: "Việc hàng tuần của SOP §5: nhắc/đòi hóa đơn sắp và quá hạn trên cả kênh." },
  // Một chuỗi có thể có NHIỀU pháp nhân (Central Retail 2 EB, Saigon Co.op ~8
  // đơn vị, LOTTE tách chi nhánh). Số gộp theo chuỗi không đi đòi được — phải
  // xuống tới từng pháp nhân mới biết gọi cho ai.
  // Câu hỏi KHÁC câu hỏi của thẻ hai cuốn sổ: màn kia chỉ nhìn phần CÒN NỢ,
  // màn này nhìn MỌI hóa đơn bán — hóa đơn đã thu đủ tiền mà trống ô số HĐĐT
  // vẫn là lỗ hổng chứng từ. Hai con số không bao giờ bằng nhau, và đó là đúng.
  { key: "g-soat-hddt", label: "Soát HĐ bỏ sót số HĐĐT", icon: "fa-magnifying-glass-dollar",
    hint: "Hóa đơn CŨ HƠN tờ mới nhất đã điền số HĐĐT mà vẫn trống — tức đã đi qua rồi mà không xuất. Khác với hàng vừa giao chưa tới lượt." },
  // Hàng hoàn là việc LIÊN CHUỖI thật: phiếu sự cố về theo chuyến xe, không về
  // theo chuỗi, và kế toán xử cả nắm một lượt chứ không mở bảy bàn làm việc.
  { key: "g-hang-hoan", label: "Hàng hoàn chờ xử lý", icon: "fa-rotate-left",
    hint: "Lần hàng quay về mà giấy tờ chưa xong. Ô 'Chưa vào sổ' là phiếu sự cố bên vận chuyển chưa ai nhận — việc duy nhất ở đây còn nằm ngoài tầm nhìn của kế toán." },
  { key: "g-khach", label: "Công nợ theo khách hàng", icon: "fa-building",
    hint: "Xuống từng pháp nhân của mỗi chuỗi. Một chuỗi thường có nhiều pháp nhân xuất hóa đơn riêng." },
  // Việc MỘT LẦN, làm trước tất cả: chuyển sổ theo dõi Excel sang phần mềm.
  { key: "g-so-du", label: "Số dư đầu kỳ", icon: "fa-file-import",
    hint: "Nhập danh sách hóa đơn CÒN NỢ tại ngày chuyển giao. Mỗi chuỗi làm MỘT LẦN. Chốt xong, hóa đơn trước ngày đó mà không có trong danh sách coi như đã thanh toán." },
];

// Rổ tuổi nợ — khóa phải trùng `mt_debt.BUCKETS`. Nhãn hiển thị lấy từ backend.
const DUE_TONE = {
  chua_den_han: "green",
  qua_han_1_15: "yellow",
  qua_han_16_30: "yellow",
  qua_han_31_60: "red",
  qua_han_60: "red",
  chua_khai_han: "gray",
};


// Danh sách chuỗi siêu thị đến TỪ BACKEND (`get_overview.chain_options`), khai
// gốc ở ketoan/install.py: MT_CHAINS.
//
// VÌ SAO không khai lại ở đây: đã có ba nơi phải khớp nhau (install.py, mt.py,
// DocType JSON) và bản sao thứ tư trong JS là bản chắc chắn bị quên nhất — thêm
// AEON ở Python mà quên ở đây thì kế toán không chọn được chuỗi để nạp lại khi
// tự nhận diện trượt, và họ sẽ tưởng file hỏng.
//
// `state.chainOptions` được nạp trong render(); mảng dưới đây CHỈ là lưới an
// toàn cho trường hợp backend cũ chưa trả field này — không phải nguồn thật.
const CHAINS_FALLBACK = ["WinCommerce", "Central Retail", "LOTTE", "Emart", "Saigon Co.op"];

const chainsOf = (state) =>
  (state && state.chainOptions && state.chainOptions.length)
    ? state.chainOptions
    : CHAINS_FALLBACK;

// Chuỗi CÓ trong danh sách nhưng CHƯA có tầng đọc bảng kê (ví dụ Mega Market:
// gán khách được, nạp file thì chưa). Đánh dấu ngay trên ô chọn để kế toán
// không mất công thử rồi nhận lỗi.
const chainOptionHTML = (state, selected) =>
  chainsOf(state).map((c) => {
    const noParser = state && state.chainParsers && state.chainParsers.length
      && !state.chainParsers.includes(c);
    return html`<option value="${c}" ${selected === c ? "selected" : ""}>${c}${noParser ? " (chưa đọc được file)" : ""}</option>`;
  });

// Nhãn row_kind (tiếng Việt, đúng options DocType) → màu badge.
// 'Ghi giảm' tô đỏ vì nó làm GIẢM tiền về; 'Khác' tô xám vì máy KHÔNG hiểu loại
// dòng đó — xám là lời mời người xem phân loại tay, không phải "bình thường".
const KIND_TONE = {
  "Thanh toán": "green",
  "Chiết khấu": "yellow",
  "Phí": "yellow",
  "Ghi giảm": "red",
  "Khác": "gray",
};

const STATUS_TONE = { "Nháp": "gray", "Đã đối chiếu": "yellow", "Đã ghi nhận": "green" };

const CONF_TONE = { "Chắc chắn": "green", "Cần review": "yellow", "Không khớp": "red" };

// `isoDate`, KHÔNG phải `toISOString()`: xem lib/format.js. Cả màn này chạy ở
// UTC+7, nên bản cũ trả về hôm qua suốt 7 tiếng đầu mỗi ngày.
const todayISO = () => isoDate();
const monthsAgo = (n) => { const d = new Date(); d.setMonth(d.getMonth() - n); return isoDate(d); };

export async function render({ container, query }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  const state = {
    // TẦNG: "bang" = bảng chuỗi · "chuoi" = bàn làm việc của một chuỗi ·
    // "toan-kenh" = màn hình liên chuỗi.
    view: query?.chain ? "chuoi" : (query?.g ? "toan-kenh" : "bang"),
    chain: query?.chain || "",
    step: query?.step || "",
    global: query?.g || "",

    bucket: PAY_VIEWS.some((b) => b.key === query?.bucket) ? query.bucket : "chua_thanh_toan",
    from: query?.from || monthsAgo(3),
    to: query?.to || todayISO(),
    customer: query?.customer || "",
    chainView: query?.view === "chuoi" ? "chuoi" : "khach",
    search: "",
    page: 1,
    canManage: false,
    jeState: query?.je_state || "",
    jeView: query?.je_view === "duyet" ? "duyet" : "bang-ke",
    jePicked: new Set(),
    jeKind: query?.je_kind || "",
    bkckStatus: query?.bkck_status || "",
    winStatus: query?.win_status || "",
    jeDocstatus: query?.je_docstatus === "1" ? "1" : "0",
    openName: query?.open || "",
    openOnly: "",
    dueBucket: "tat_ca",
    dueAsOf: "",
    // Trục HÓA ĐƠN ĐIỆN TỬ trên màn Công nợ đến hạn: "" · "da" · "chua".
    // Đọc lại được từ URL để cái link kế toán gửi cho nhau còn mở ra đúng
    // danh sách — bộ lọc chỉ sống trong bộ nhớ là bộ lọc không chia sẻ được.
    dueEinv: ["da", "chua"].includes(query?.due_einv) ? query.due_einv : "",
    // Chuỗi đang lọc ở màn "Soát HĐ bỏ sót số HĐĐT" — ô RIÊNG, không dùng chung
    // `state.chain` (thứ quyết định tầng điều hướng) cũng không dùng chung
    // `dueChain` của màn công nợ.
    gapChain: query?.gap_chain || "",
    // Hàng hoàn — ô hàng đợi và chuỗi đang lọc. Ô RIÊNG: `state.chain` quyết
    // định tầng điều hướng, dùng chung là bấm lọc chuỗi thì nhảy màn.
    hoanBucket: query?.hoan_bucket || "",
    hoanChain: query?.hoan_chain || "",
    // Sổ theo dõi hóa đơn — bộ lọc riêng, không dùng chung với màn nào.
    ledStatus: "",
    ledQ: "",
    ledPage: 1,
    ledOpen: "",
    // Bộ lọc của danh sách soát HĐĐT. RIÊNG cho mỗi màn: bước Chờ xuất hóa đơn
    // của Win và màn soát toàn kênh là hai chỗ làm việc khác nhau, dùng chung
    // một ô là lọc bên này thì bên kia đổi theo mà không ai bấm gì.
    einvFilter: {},
    wpEinvFilter: {},
    // Tùy chọn cho ô lọc, nạp một lần theo chuỗi đang xem.
    einvOpts: null,
    einvOptsFor: null,
    // Trục HĐĐT trên danh sách hóa đơn (`mt.get_invoices`) — khác màn, khác ô.
    einvoice: "",
    // Cỡ trang và cách xếp của bảng hóa đơn. Mặc định xếp theo TUỔI NỢ giảm
    // dần — đó là thứ tự đi đòi; backend khai khóa ở `mt.SORTS`.
    pageSize: 20,
    sort: "tuoi",
    picked: new Set(),
    pickedKey: "",
    // Hàng đợi việc của chuỗi, nạp một lần cho mỗi (chuỗi, khoảng ngày).
    wl: null,
    wlKey: "",
    wlFocus: "",
    board: null,
  };

  await paint(container, state);
}

// Vẽ lại toàn bộ màn hình theo `state.view`. Gọi lại sau mỗi lần đổi tầng.
async function paint(container, state) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let board;
  try {
    board = await api.mtBoard({ from_date: state.from, to_date: state.to });
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  state.board = board;
  state.canManage = !!board.can_manage;
  state.chainOptions = (board.chains || []).map((c) => c.chain);
  state.chainParsers = (board.chains || []).filter((c) => c.can_read_payment).map((c) => c.chain);

  if (state.view === "chuoi") {
    const hit = (board.chains || []).find((c) => c.chain === state.chain);
    if (!hit) { state.view = "bang"; state.chain = ""; }
  }

  if (state.view === "bang") {
    setHTML(container, boardShell(state, board));
    bindBoard(container, state);
    return;
  }
  if (state.view === "toan-kenh") {
    setHTML(container, globalShell(state, board));
    bindShellCommon(container, state);
    await loadTab(container, state);
    return;
  }
  setHTML(container, chainShell(state, board));
  bindShellCommon(container, state);
  // Thanh việc nạp SONG SONG với nội dung tab, không chặn: nó là lối tắt, còn
  // bàn làm việc là thứ người ta vào để xem.
  ensureWorklist(state).then((wl) => {
    const slot = container.querySelector("#mt-worklist");
    if (!slot) return;
    setHTML(slot, worklistBar(state, wl));
    bindWorklistBar(container, state);
  });
  await loadTab(container, state);
  // Cuốn sổ thứ ba nạp SAU và KHÔNG chặn: nó quét `tabGL Entry`, nặng hơn hẳn
  // phần còn lại. `await` nó trước `loadTab` là bắt cả bàn làm việc chờ theo.
  loadChainGl(container, state);
}

function syncHash(state) {
  const p = [`from=${state.from}`, `to=${state.to}`];
  if (state.view === "chuoi") { p.push(`chain=${q(state.chain)}`, `step=${state.step}`); }
  else if (state.view === "toan-kenh") {
    p.push(`g=${state.global}`);
    if (state.global === "g-so-du" && state.openName) p.push(`open=${q(state.openName)}`);
  }
  // Bộ lọc HĐĐT vào URL: nó là thứ kế toán bấm rồi F5, hoặc gửi link cho nhau.
  // Không mang theo thì F5 ra một danh sách KHÁC mà đầu trang vẫn ghi cùng tiêu đề.
  if (state.dueEinv) p.push(`due_einv=${state.dueEinv}`);
  if (state.global === "g-soat-hddt" && state.gapChain) p.push(`gap_chain=${q(state.gapChain)}`);
  // Ô hàng đợi vào URL cùng lý do: kế toán bấm "Chưa vào sổ" rồi F5, hoặc gửi
  // link cho người khác. Không mang theo thì mở ra một danh sách KHÁC mà tiêu
  // đề vẫn y nguyên.
  const onHoan = state.global === "g-hang-hoan" || state.step === "hang-hoan";
  if (onHoan && state.hoanBucket) p.push(`hoan_bucket=${state.hoanBucket}`);
  if (state.global === "g-hang-hoan" && state.hoanChain) p.push(`hoan_chain=${q(state.hoanChain)}`);
  history.replaceState(null, "", `#/cong-no-mt?${p.join("&")}`);
}

// ── Thanh ngày, dùng chung mọi tầng ────────────────────────────────────────
// Ba mốc kế toán MT thật sự dùng. Hai ô ngày vẫn còn nguyên — preset chỉ là
// lối tắt, không thay thế: kỳ thanh toán của chuỗi không bao giờ trùng tháng
// dương lịch, nên bịt hai ô ngày lại là khóa mất đúng thứ họ cần nhất.
const DATE_PRESETS = [
  { key: "thang", label: "Tháng này" },
  { key: "quy", label: "Quý này" },
  { key: "ba-thang", label: "3 tháng" },
];

function presetRange(key) {
  const now = new Date();
  const iso = isoDate;
  if (key === "thang") {
    return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), todayISO()];
  }
  if (key === "quy") {
    return [iso(new Date(now.getFullYear(), Math.floor(now.getMonth() / 3) * 3, 1)), todayISO()];
  }
  return [monthsAgo(3), todayISO()];
}

// Preset nào đang khớp khoảng ngày hiện tại. Không khớp cái nào -> không tô
// cái nào: tô bừa một cái là nói với người dùng rằng khoảng đang xem là khoảng
// đó, trong khi họ vừa gõ tay một khoảng khác.
function activePreset(state) {
  for (const p of DATE_PRESETS) {
    const [f, t] = presetRange(p.key);
    if (f === state.from && t === state.to) return p.key;
  }
  return "";
}

function dateBar(state) {
  const on = activePreset(state);
  return html`
    <span class="ktmt-preset">
      ${DATE_PRESETS.map((p) => html`<button data-preset="${p.key}"
        class="${on === p.key ? "is-on" : ""}">${p.label}</button>`)}
    </span>
    <input type="date" class="kt-input kt-input--sm" id="mt-from" value="${state.from}">
    <span class="kt-sub">→</span>
    <input type="date" class="kt-input kt-input--sm" id="mt-to" value="${state.to}">`;
}

const BASIS_NOTE = html`
  <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
    <div class="kt-card-body kt-sub">
      <b>Số ở đây tính từ BẢNG KÊ CỦA CHUỖI, không phải số dư sổ cái.</b>
      Kênh MT cố ý <b>không</b> tạo Payment Entry — bút toán do người duyệt.
      Vì vậy <code>outstanding_amount</code> của ERPNext chưa trừ tiền chuỗi đã trả.
    </div>
  </div>`;

// ═══════════════════════════════════════════════════════════════════════════
// TẦNG 0 — BẢNG CHUỖI
// ═══════════════════════════════════════════════════════════════════════════

function boardShell(state, board) {
  const t = board.totals || {};
  const chains = board.chains || [];
  return html`
    <div class="kt-view-head">
      <div>
        <div class="kt-view-title"><i class="fas fa-store"></i> Kênh siêu thị (MT)</div>
        <div class="kt-sub">Chọn một chuỗi để làm. Mỗi chuỗi có vòng đời tháng riêng.</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${dateBar(state)}</div>
    </div>

    <div class="kt-stats kt-mb">
      ${(() => {
        // Việc dồn vào ĐÚNG MỘT chuỗi thì ô đếm này là một lối vào, không phải
        // một con số để nhìn: bấm là vào thẳng chuỗi đó. Từ hai chuỗi trở lên
        // thì không có "chuỗi đó" nào để mà vào — giữ nguyên là ô đếm.
        const busy = chains.filter((c) => c.todo);
        const one = busy.length === 1 ? busy[0] : null;
        return html`<div class="kt-stat ${one ? "is-link" : ""}"
            ${one ? html`data-gochain="${one.chain}"` : ""}>
          <div class="kt-stat-label"><i class="fas fa-list-check"></i> Việc đang chờ</div>
          <div style="display:flex;align-items:baseline;gap:8px">
            <div class="kt-stat-value ${t.todo ? "warn" : ""}">${t.todo || 0}</div>
            ${one ? html`<b style="font-size:12px;color:var(--kt-primary)">→ ${one.chain}</b>` : ""}
          </div>
          <div class="kt-stat-sub">${one
            ? "tất cả nằm trên 1 chuỗi — bấm để vào thẳng"
            : `trên ${busy.length} chuỗi`}</div>
        </div>`;
      })()}
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-file-invoice-dollar"></i> Bút toán nháp</div>
        <div class="kt-stat-value ${t.draft_je ? "warn" : ""}">${t.draft_je || 0}</div>
        <div class="kt-stat-sub">chờ người duyệt — hệ không tự ghi sổ</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-hourglass-half"></i> Chuỗi còn nợ</div>
        <div class="kt-stat-value">${formatVNDShort(t.debt)}</div>
        <div class="kt-stat-sub">tính đến ${formatDate(board.as_of)}</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-clock"></i> Trong đó quá hạn</div>
        <div class="kt-stat-value ${t.debt_overdue ? "danger" : ""}">${formatVNDShort(t.debt_overdue)}</div>
        <div class="kt-stat-sub">theo hạn khai trên từng khách</div>
      </div>
    </div>

    ${twoBooks(t, board)}

    ${BASIS_NOTE}

    ${board.orphan_advices
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body">
            <div style="font-weight:600;color:var(--kt-danger)">
              <i class="fas fa-triangle-exclamation"></i>
              ${board.orphan_advices} bảng kê KHÔNG điền công ty
            </div>
            <div class="kt-sub" style="margin-top:6px">
              Chúng không được tính vào công ty nào nên biến khỏi mọi thẻ chuỗi ở dưới —
              tiền trong đó đang mất hút. Mở
              <a target="_blank" href="/app/mt-payment-advice?company=">MT Payment Advice</a>
              điền công ty cho từng cái.
            </div>
          </div></div>`
      : ""}

    ${(board.unassigned_debt && board.unassigned_debt.debt_invoices)
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
            <i class="fas fa-triangle-exclamation" style="color:var(--kt-warning);font-size:20px"></i>
            <div style="flex-grow:1;min-width:220px">
              <div style="font-weight:700;color:#0f172a">
                ${formatVNDShort(board.unassigned_debt.debt)} đang treo ở khách chưa khai chuỗi</div>
              <div class="kt-sub" style="margin-top:2px">
                ${board.unassigned_debt.debt_invoices} hóa đơn — chừng nào chưa gán chuỗi thì không
                chuỗi nào “xong” thật, và tiền này không nằm trong thẻ chuỗi nào.</div>
            </div>
            <button class="kt-btn kt-btn--sm" data-setup="assign">Gán chuỗi cho khách</button>
          </div></div>`
      : ""}

    ${(board.unassigned_debt && board.unassigned_debt.todo)
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body">
            <div style="font-weight:600;color:var(--kt-warning)">
              <i class="fas fa-rotate-left"></i>
              ${board.unassigned_debt.todo} việc hàng hoàn của khách CHƯA GÁN CHUỖI
            </div>
            <div class="kt-sub" style="margin-top:6px">
              Không thẻ chuỗi nào ở dưới đếm chúng — thẻ chỉ chạy qua danh sách chuỗi đã
              khai. Màn <b>Hàng hoàn chờ xử lý</b> thì có, vì nó không lọc chuỗi; nên nếu
              không nói ra ở đây thì hai màn hình sẽ ra hai con số cho cùng một tập.
              ${board.unassigned_debt.hoan_chua_vao_so
                ? html`<b>${board.unassigned_debt.hoan_chua_vao_so}</b> trong đó còn chưa
                    vào sổ kế toán.`
                : ""}
              Gán chuỗi cho khách ở <b>Công nợ theo khách hàng</b> để việc về đúng thẻ.
            </div>
            <button class="kt-btn kt-btn--outline kt-btn--sm" data-global="g-hang-hoan"
                    style="margin-top:8px">
              <i class="fas fa-rotate-left"></i> Mở màn Hàng hoàn
            </button>
          </div></div>`
      : ""}

    ${chainSplit(state, chains)}

    ${globalWork(state, board)}
  `;
}

// Một thẻ chuỗi. Chỉ liệt kê VIỆC PHẢI LÀM, không liệt kê hiện trạng: thẻ nào
// cũng đầy số thì không thẻ nào nổi lên được.
// ── CHUỖI CẦN LÀM vs CHUỖI ĐÃ XONG ────────────────────────────────────────
//
// Bản cũ vẽ TÁM thẻ lớn bằng nhau, và bảy trong tám chỉ để nói "không còn việc
// nào trong khoảng đang xem". Bảy thẻ đó chiếm hai phần ba màn hình đầu tiên
// để trả lời một câu không ai hỏi, còn chuỗi DUY NHẤT có việc thì nằm lẫn giữa
// chúng, cùng cỡ, cùng màu.
//
// Chuỗi hết việc VẪN phải hiện — biến mất khỏi màn hình thì không phân biệt
// được với "chuỗi này chưa bao giờ có dữ liệu" — nhưng một dòng là đủ, vì câu
// hỏi về chúng chỉ còn là "còn nợ bao nhiêu".
function chainSplit(state, chains) {
  const busy = chains.filter((c) => c.todo);
  const done = chains.filter((c) => !c.todo);
  const nTodo = busy.reduce((a, c) => a + (c.todo || 0), 0);
  return html`
    ${busy.length
      ? html`<div style="display:flex;align-items:center;gap:10px;margin:0 0 10px 2px">
            <div style="font-size:14px;font-weight:800;color:#0f172a">Chuỗi cần làm</div>
            <span class="ktmt-chip ktmt-chip--rose" style="cursor:default">${busy.length} chuỗi · ${nTodo} việc</span>
          </div>
          <div class="kt-ws-sections kt-mb">${busy.map((c) => chainCard(c))}</div>`
      : html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-success)">
          <div class="kt-card-body">
            <b style="color:var(--kt-success)"><i class="fas fa-check"></i> Không chuỗi nào còn việc</b>
            <div class="kt-sub" style="margin-top:4px">trong khoảng đang xem. Các chuỗi vẫn còn nợ —
              xem dải bên dưới, hoặc đổi khoảng ngày để soát kỳ khác.</div>
          </div></div>`}

    ${done.length
      ? html`<div style="display:flex;align-items:center;gap:10px;margin:0 0 10px 2px">
            <div style="font-size:14px;font-weight:800;color:#0f172a">Chuỗi đã xong việc</div>
            <span class="ktmt-chip" style="color:var(--kt-success);background:#f0fdf4;cursor:default">${done.length} chuỗi</span>
          </div>
          <div class="kt-card kt-mb" style="padding:6px 0">
            <div class="ktmt-donegrid">${done.map((c) => html`
              <div class="ktmt-doneitem" data-gochain="${c.chain}">
                <i class="fas fa-check"></i>
                <b>${c.chain}</b>
                <span class="kt-sub">${formatVNDShort(c.debt)}${c.debt_overdue
                  ? html` · qh <b style="color:var(--kt-danger)">${formatVNDShort(c.debt_overdue)}</b>`
                  : ""}</span>
              </div>`)}</div>
          </div>`
      : ""}`;
}

// ── VIỆC TOÀN KÊNH — chia nhóm thay vì một tường chín nút ─────────────────
//
// Chín nút phẳng cùng cỡ cùng màu thì không cái nào nổi lên, và ba loại việc
// rất khác nhau bị trộn: việc HẰNG NGÀY (duyệt bút toán, đòi nợ), việc KHAI
// BÁO (gán chuỗi, điểm siêu thị, hạn thanh toán, tài khoản hạch toán) và một
// việc CHỈ LÀM MỘT LẦN (số dư đầu kỳ) — cái cuối nguy hiểm nhất nếu ai đó mở
// lại sau khi đã chốt, nên nó đứng riêng và viền đứt.
function globalWork(state, board) {
  const ua = board.unassigned_debt || null;
  const daily = GLOBAL_VIEWS.filter((g) => g.key !== "g-so-du");
  const once = GLOBAL_VIEWS.filter((g) => g.key === "g-so-du");
  return html`<div class="kt-card kt-mb"><div class="kt-card-body">
    <div style="font-size:14px;font-weight:800;color:#0f172a;margin-bottom:3px">
      <i class="fas fa-layer-group"></i> Việc trên toàn kênh</div>
    <div class="kt-sub" style="margin-bottom:14px">Làm một lượt cho mọi chuỗi, không tách theo chuỗi.</div>
    <div class="ktmt-groups">
      <div>
        <div class="ktmt-kicker" style="margin-bottom:9px">Hằng ngày / hằng tuần</div>
        <div style="display:flex;flex-direction:column;gap:7px">
          ${daily.map((g) => html`<button class="ktmt-linkbtn" data-global="${g.key}"
            title="${g.hint}"><i class="fas ${g.icon}"></i> ${g.label}</button>`)}
          <button class="ktmt-linkbtn" data-goroute="/cong-no/mt"
            title="Công nợ kênh MT + tuổi nợ — màn chung của mọi kênh">
            <i class="fas fa-file-invoice-dollar"></i> Công nợ kênh MT (màn chung)</button>
          <button class="ktmt-linkbtn" data-goroute="/hoa-don-vat"
            title="Đối soát hóa đơn VAT với MISA">
            <i class="fas fa-receipt"></i> Hóa đơn VAT</button>
        </div>
      </div>
      <div>
        <div class="ktmt-kicker" style="margin-bottom:9px">Khai báo &amp; danh mục</div>
        <div style="display:flex;flex-direction:column;gap:7px">
          <button class="ktmt-linkbtn" data-setup="assign"><i class="fas fa-link"></i> Gán chuỗi cho khách
            ${ua && ua.debt_invoices
              ? html`<span class="ktmt-linkbtn-tag">${ua.debt_invoices}</span>`
              : ""}</button>
          <button class="ktmt-linkbtn" data-setup="stores"><i class="fas fa-shop"></i> Điểm siêu thị</button>
          ${state.canManage
            ? html`<button class="ktmt-linkbtn" data-setup="terms">
                  <i class="fas fa-calendar-day"></i> Hạn thanh toán</button>
                <button class="ktmt-linkbtn" data-setup="accounts">
                  <i class="fas fa-sliders"></i> Tài khoản hạch toán</button>`
            : ""}
        </div>
      </div>
      <div>
        <div class="ktmt-kicker" style="margin-bottom:9px">Chỉ làm một lần</div>
        <div style="display:flex;flex-direction:column;gap:7px">
          ${once.map((g) => html`<button class="ktmt-linkbtn ktmt-linkbtn--once"
            data-global="${g.key}" title="${g.hint}"><i class="fas ${g.icon}"></i> ${g.label}</button>`)}
        </div>
        <div class="kt-sub" style="margin-top:9px;line-height:1.7">Làm MỘT LẦN lúc chuyển từ Excel
          sang phần mềm. Chốt xong, hóa đơn trước ngày đó mà không có trong danh sách coi như đã
          thanh toán — nên mở lại là đụng vào một kết luận đã ký.</div>
      </div>
    </div>
  </div></div>`;
}

function chainCard(c) {
  const jobs = [];
  if (c.advices_unreconciled) jobs.push({ n: c.advices_unreconciled, t: "bảng kê chưa đối chiếu", tone: "danger" });
  if (c.lines_unmatched) jobs.push({ n: c.lines_unmatched, t: "dòng tiền chưa nối hóa đơn", tone: "danger" });
  if (c.lines_review) jobs.push({ n: c.lines_review, t: "dòng cần người xác nhận", tone: "warning" });
  if (c.draft_je) jobs.push({ n: c.draft_je, t: "bút toán nháp chờ duyệt", tone: "warning" });
  if (c.sheets_draft) jobs.push({ n: c.sheets_draft, t: "bảng kê chiết khấu chưa chốt", tone: "warning" });
  if (c.sheets_await_invoice) jobs.push({ n: c.sheets_await_invoice, t: "bảng kê chờ ghi số hóa đơn CK", tone: "warning" });
  if (c.dossiers_draft) jobs.push({ n: c.dossiers_draft, t: "hồ sơ Win chưa nộp", tone: "warning" });
  // Hai dòng RIÊNG, không gộp: "chưa vào sổ" là việc còn nằm bên app vận chuyển,
  // "chưa xong giấy tờ" là việc đã nằm trên bàn kế toán. Gộp lại thì kế toán
  // không biết nên đi nhận việc hay đi lập chứng từ.
  if (c.hoan_chua_vao_so) jobs.push({ n: c.hoan_chua_vao_so, t: "lần hàng về chưa vào sổ", tone: "danger" });
  if (c.hoan_open) jobs.push({ n: c.hoan_open, t: "lần hàng về chưa xong giấy tờ", tone: "warning" });

  return html`
    <div class="kt-card kt-chain-card" data-chain="${c.chain}" style="cursor:pointer">
      <div class="kt-card-body">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="font-weight:600;font-size:15px">${c.chain}</div>
          <span class="kt-badge kt-badge--${c.todo ? "yellow" : "green"}" style="margin-left:auto">
            ${c.todo ? `${c.todo} việc` : "xong"}
          </span>
        </div>

        <div class="kt-sub" style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
          ${c.we_issue_discount ? html`<span class="kt-badge kt-badge--gray">mình xuất HĐ chiết khấu</span>` : ""}
          ${c.has_dossier ? html`<span class="kt-badge kt-badge--gray">có hồ sơ nộp</span>` : ""}
          ${!c.can_read_payment ? html`<span class="kt-badge kt-badge--gray">chưa đọc được file thanh toán</span>` : ""}
          ${!c.n_customers ? html`<span class="kt-badge kt-badge--red">chưa gán khách hàng</span>` : ""}
        </div>

        ${jobs.length
          ? html`<div style="margin-top:10px">
              ${jobs.map((j) => html`<div class="kt-sub" style="margin-top:3px">
                <b style="color:var(--kt-${j.tone})">${j.n}</b> ${j.t}
              </div>`)}
            </div>`
          : html`<div class="kt-sub" style="margin-top:10px">Không còn việc nào trong khoảng đang xem.</div>`}

        <div class="kt-sub" style="margin-top:10px;padding-top:8px;border-top:1px solid var(--kt-border);
                    display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap">
          <div style="flex-grow:1;min-width:0">
          Còn nợ <b>${formatVNDShort(c.debt)}</b>
          ${c.debt_overdue
            ? html` · quá hạn <b style="color:var(--kt-danger)">${formatVNDShort(c.debt_overdue)}</b>`
            : ""}
          ${c.debt_unknown_term
            ? html` · <span style="color:var(--kt-warning)">${c.debt_unknown_term} HĐ chưa khai hạn</span>`
            : ""}
          ${c.debt_einv_known && c.debt_no_einv
            ? html`<div style="margin-top:4px">
                Chưa xuất HĐĐT
                <b style="color:var(--kt-danger)">${formatVNDShort(c.debt_no_einv)}</b>
                · ${c.debt_no_einv_count} HĐ${c.debt_no_einv_oldest
                  ? html` · từ ${formatDate(c.debt_no_einv_oldest)}`
                  : ""}
                ${c.einv_deadline && c.einv_deadline.breached
                  ? html`<span class="kt-badge kt-badge--red" style="margin-left:6px">
                      quá hạn ngày ${c.einv_deadline.day}</span>`
                  : ""}
              </div>`
            : ""}
          </div>
          ${c.todo
            ? html`<button class="kt-btn kt-btn--sm" data-gochain="${c.chain}"
                style="align-self:center">Vào làm →</button>`
            : ""}
        </div>
      </div>
    </div>`;
}

function bindBoard(container, state) {
  const da = container.querySelector("#tb-open-da");
  if (da) da.addEventListener("click", () => openDueEinv(container, state, "", "da"));
  const tb = container.querySelector("#tb-open");
  if (tb) tb.addEventListener("click", () => openDueEinv(container, state, "", "chua"));
  container.querySelectorAll("tr.tb-chain").forEach((tr) => {
    tr.addEventListener("click", () =>
      openDueEinv(container, state, tr.dataset.chain, "chua"));
  });

  bindDates(container, state);
  // MỘT đường vào chuỗi, ba chỗ bấm: cả thẻ chuỗi, nút "Vào làm →", và dòng
  // trong dải "đã xong". Ba handler riêng thì sớm muộn một chỗ quên xóa bộ lọc
  // của chuỗi trước, và người dùng vào chuỗi mới mà thấy danh sách chuỗi cũ.
  const goChain = (chain) => {
    if (!chain) return;
    state.chain = chain;
    state.view = "chuoi";
    state.step = "";
    state.page = 1;
    state.customer = "";   // bộ lọc khách của chuỗi trước không còn nghĩa
    state.search = "";
    state.picked = new Set();
    state.wl = null;       // hàng đợi việc là của CHUỖI — không mang theo
    state.wlKey = "";
    syncHash(state);
    paint(container, state);
  };
  container.querySelectorAll(".kt-chain-card").forEach((el) => {
    el.addEventListener("click", () => goChain(el.dataset.chain));
  });
  container.querySelectorAll("[data-gochain]").forEach((el) => {
    el.addEventListener("click", (e) => {
      // Nút nằm TRONG thẻ chuỗi — chặn nổi bọt, không thì một cú bấm chạy hai
      // lần và `paint` vẽ lại giữa chừng.
      e.stopPropagation();
      goChain(el.dataset.gochain);
    });
  });
  container.querySelectorAll("button[data-global]").forEach((b) => {
    b.addEventListener("click", () => {
      state.global = b.dataset.global;
      state.view = "toan-kenh";
      state.chain = "";
      state.page = 1;
      syncHash(state);
      paint(container, state);
    });
  });
  container.querySelectorAll("[data-goroute]").forEach((b) => {
    b.addEventListener("click", () => { location.hash = "#" + b.dataset.goroute; });
  });
  bindSetup(container, state);
}

// Mở danh sách hóa đơn đứng sau một con số của thẻ "hai cuốn sổ".
//
// ⚠ ĐI TỚI MÀN "CÔNG NỢ ĐẾN HẠN", KHÔNG PHẢI DANH SÁCH HÓA ĐƠN.
//
// Bản đầu (MT2-X) mở rổ 'chưa thu đủ' của `mt.get_invoices`, và điều đó SAI:
//
//   · con số trên thẻ  — `mt_debt._fetch`   : si.posting_date <= as_of
//                                             (KHÔNG chặn dưới — nợ là SỐ DƯ)
//   · danh sách bấm ra — `mt._invoice_page` : si.posting_date BETWEEN fd AND td
//                                             (mặc định của portal: 3 THÁNG GẦN ĐÂY)
//
// Thẻ đếm 65 hóa đơn từ mọi thời kỳ, bấm vào chỉ ra những tờ trong 3 tháng gần
// nhất. Hóa đơn cũ — đúng thứ đọng lâu nhất, nguy hiểm nhất — chính là thứ bị
// giấu. Số trên thẻ và danh sách bấm ra không bao giờ bằng nhau.
//
// Màn "Công nợ đến hạn" gọi CHÍNH `mt_debt._fetch` cho cả tổng lẫn danh sách,
// nên hai bên khớp THEO CẤU TẠO chứ không nhờ hai câu SQL tình cờ giống nhau.
function openDueEinv(container, state, chain, mode) {
  state.dueEinv = mode;
  state.dueBucket = "tat_ca";
  state.page = 1;
  // Bảng chuỗi luôn tính đến HÔM NAY (`mt_hub.get_board` không nhận `as_of` từ
  // portal). Màn công nợ thì nhớ ngày kế toán đã chọn lần trước. Không xóa nó
  // ở đây là bấm vào một con số tính đến hôm nay rồi rơi vào danh sách tính đến
  // một ngày nào đó trong quá khứ — lệch mà không chỗ nào nói.
  state.dueAsOf = "";
  if (chain) {
    state.chain = chain;
    state.view = "chuoi";
    state.step = "cong-no";
    state.customer = "";
    state.search = "";
  } else {
    state.view = "toan-kenh";
    state.global = "g-cong-no";
    state.chain = "";
    state.dueChain = "";
  }
  syncHash(state);
  paint(container, state);
}

// Các màn thiết lập đều là modal — không đổi tầng, nên không paint lại.
function bindSetup(container, state) {
  container.querySelectorAll("button[data-setup]").forEach((b) => {
    b.addEventListener("click", () => {
      const k = b.dataset.setup;
      if (k === "stores") return openStores(container, state);
      if (k === "assign") return openChainAssign(container, state);
      if (k === "accounts") return openAccountMap();
      if (k === "terms") return openCreditTerms(container, state);
    });
  });
}

function bindDates(container, state) {
  const from = container.querySelector("#mt-from");
  const to = container.querySelector("#mt-to");
  const onDate = () => {
    state.from = from.value;
    state.to = to.value;
    state.page = 1;
    syncHash(state);
    paint(container, state);
  };
  if (from) from.addEventListener("change", onDate);
  if (to) to.addEventListener("change", onDate);

  container.querySelectorAll(".ktmt-preset button[data-preset]").forEach((b) => {
    b.addEventListener("click", () => {
      const [f, t] = presetRange(b.dataset.preset);
      state.from = f;
      state.to = t;
      state.page = 1;
      // Khoảng ngày đổi -> hàng đợi việc cũ nói về một kỳ khác.
      state.wl = null;
      state.wlKey = "";
      syncHash(state);
      paint(container, state);
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// TẦNG 1 — BÀN LÀM VIỆC CỦA MỘT CHUỖI
// ═══════════════════════════════════════════════════════════════════════════

// Bước nào hiện cho chuỗi này. Ẩn bước chuỗi không có, nhưng nói LÝ DO ở dưới.
function stepsFor(c) {
  return STEPS.filter((s) => !s.need || c[s.need]);
}

function chainShell(state, board) {
  const c = (board.chains || []).find((x) => x.chain === state.chain) || {};
  const steps = stepsFor(c);
  if (!steps.some((s) => s.key === state.step)) state.step = steps[0] ? steps[0].key : "thanh-toan";
  const cur = steps.find((s) => s.key === state.step) || STEPS[2];

  return html`
    <div class="kt-view-head">
      <div>
        <div class="kt-view-title">
          <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-back" style="margin-right:10px">
            <i class="fas fa-arrow-left"></i> Mọi chuỗi
          </button>
          <i class="fas fa-store"></i> ${state.chain}
        </div>
        <div class="kt-sub">
          ${c.todo ? `${c.todo} việc ở mọi bước` : "Không còn việc nào trong khoảng đang xem"} ·
          còn nợ ${formatVNDShort(c.debt)}${c.debt_overdue ? ` · quá hạn ${formatVNDShort(c.debt_overdue)}` : ""}
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        ${dateBar(state)}
        ${state.canManage && c.can_read_payment
          ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-import">
              <i class="fas fa-file-import"></i> Nạp bảng kê thanh toán
            </button>`
          : ""}
      </div>
    </div>

    <div id="mt-worklist"></div>

    ${twoBooksChain(c)}

    ${!c.n_customers
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body">
            <div style="font-weight:600;color:var(--kt-danger)">
              <i class="fas fa-user-slash"></i>
              Chưa có khách hàng nào thuộc chuỗi ${state.chain}
            </div>
            <div class="kt-sub" style="margin-top:6px">
              Mọi danh sách dưới đây sẽ TRỐNG — không phải vì kỳ này không có gì, mà vì
              hệ thống chưa biết khách nào thuộc chuỗi này. Về trang chuỗi rồi bấm
              <b>Gán chuỗi cho khách</b>.
            </div>
          </div></div>`
      : ""}

    ${!c.can_read_payment
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            Chưa có tầng đọc file thanh toán cho <b>${state.chain}</b> — chưa có file mẫu thật
            để viết, và đọc bừa bằng parser chuỗi khác là sai tiền. Dữ liệu đã nạp trước đó vẫn
            xem được ở đây; chỉ chưa nạp file mới được.
          </div></div>`
      : ""}

    <div class="ktmt-steps" id="mt-steps">
      ${steps.map((s) => {
        const n = (s.count || []).reduce((a, k) => a + (c[k] || 0), 0);
        return html`<button data-step="${s.key}" class="ktmt-step ${state.step === s.key ? "is-on" : ""}">
          ${s.no ? html`<span class="ktmt-step-no">B${s.no}</span>` : ""}${s.label}
          ${n ? html`<span class="ktmt-step-todo">${n}</span>` : ""}
        </button>`;
      })}
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <i class="fas ${cur.icon} kt-sub"></i>
      <span class="kt-sub" id="mt-hint">${cur.hint}</span>
      <input class="kt-input kt-input--sm" id="mt-search" placeholder="Tìm số hóa đơn / khách / siêu thị…"
        style="margin-left:auto;min-width:220px">
    </div></div>

    <div id="mt-body"></div>
  `;
}

// ═══════════════════════════════════════════════════════════════════════════
// TẦNG 1' — MÀN HÌNH LIÊN CHUỖI
// ═══════════════════════════════════════════════════════════════════════════

function globalShell(state, board) {
  const g = GLOBAL_VIEWS.find((x) => x.key === state.global) || GLOBAL_VIEWS[0];
  state.global = g.key;
  return html`
    <div class="kt-view-head">
      <div>
        <div class="kt-view-title">
          <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-back" style="margin-right:10px">
            <i class="fas fa-arrow-left"></i> Mọi chuỗi
          </button>
          <i class="fas ${g.icon}"></i> ${g.label}
        </div>
        <div class="kt-sub">Toàn kênh MT — không lọc theo chuỗi.</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${dateBar(state)}</div>
    </div>

    ${BASIS_NOTE}

    <div class="kt-segment kt-mb" id="mt-globals">
      ${GLOBAL_VIEWS.map((x) => html`<button data-global="${x.key}"
        class="${state.global === x.key ? "is-active" : ""}">${x.label}</button>`)}
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <i class="fas fa-circle-info kt-sub"></i>
      <span class="kt-sub">${g.hint}</span>
      <input class="kt-input kt-input--sm" id="mt-search" placeholder="Tìm số hóa đơn / khách / siêu thị…"
        style="margin-left:auto;min-width:220px">
    </div></div>

    <div id="mt-body"></div>
  `;
}

// ── Ràng buộc dùng chung cho hai tầng có `#mt-body` ────────────────────────
function bindShellCommon(container, state) {
  bindDates(container, state);

  // Thẻ hai cuốn sổ của chuỗi — mở đúng danh sách của CHÍNH chuỗi đang xem.
  // Ở tầng này `paint()` là đường đổi màn hợp lệ, `openDueEinv` lo việc đó.
  const cbd = container.querySelector("#cb-open-da");
  if (cbd) cbd.addEventListener("click",
    () => openDueEinv(container, state, state.chain, "da"));
  const cbc = container.querySelector("#cb-open");
  if (cbc) cbc.addEventListener("click",
    () => openDueEinv(container, state, state.chain, "chua"));

  const back = container.querySelector("#mt-back");
  if (back) back.addEventListener("click", () => {
    state.view = "bang";
    state.wl = null;
    state.wlKey = "";
    state.chain = "";
    state.global = "";
    state.page = 1;
    state.customer = "";
    state.search = "";
    syncHash(state);
    paint(container, state);
  });

  const steps = container.querySelector("#mt-steps");
  if (steps) steps.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-step]");
    if (!btn || btn.dataset.step === state.step) return;
    state.step = btn.dataset.step;
    state.page = 1;
    state.search = "";
    syncHash(state);
    paint(container, state);
  });

  const globals = container.querySelector("#mt-globals");
  if (globals) globals.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-global]");
    if (!btn || btn.dataset.global === state.global) return;
    state.global = btn.dataset.global;
    state.page = 1;
    state.search = "";
    syncHash(state);
    paint(container, state);
  });

  let timer = null;
  const s = container.querySelector("#mt-search");
  if (s) s.addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    state.page = 1;   // lọc lại phải về trang đầu, không thì rơi vào trang trống
    clearTimeout(timer);
    timer = setTimeout(() => loadTab(container, state), 350);
  });

  const imp = container.querySelector("#mt-import");
  if (imp) imp.addEventListener("click", () => pickFile(container, state));
}

// ── Nạp nội dung theo bước đang mở ─────────────────────────────────────────
//
// Mọi loader bên dưới đều đã đọc `state.chain`, nên vào bàn làm việc của một
// chuỗi là chúng tự lọc — không phải sửa loader nào.
async function loadTab(container, state) {
  const body = container.querySelector("#mt-body");
  if (!body) return;
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  if (state.view === "toan-kenh") {
    if (state.global === "g-cong-no") return loadDueDebt(container, state);
    if (state.global === "g-soat-hddt") return loadEinvGaps(container, state);
    if (state.global === "g-hang-hoan") return loadHangHoan(container, state);
    if (state.global === "g-khach") return loadChains(container, state);
    if (state.global === "g-so-du") {
      return state.openName
        ? loadOpeningDoc(container, state)
        : loadOpeningBoard(container, state);
    }
    return loadJeApproval(container, state);
  }

  if (state.step === "chiet-khau") return loadBkck(container, state);
  if (state.step === "hang-hoan") return loadHangHoan(container, state);
  if (state.step === "cho-xuat-hd") return loadWinPending(container, state);
  if (state.step === "ho-so") return loadWinDossiers(container, state);
  if (state.step === "so-theo-doi") return loadLedger(container, state);
  if (state.step === "cong-no") return loadDueDebt(container, state);
  if (state.step === "but-toan") {
    return state.jeView === "duyet"
      ? loadJeApproval(container, state)
      : loadJournals(container, state);
  }

  // Bước "Đối soát thanh toán": hai cách nhìn cùng một bảng kê.
  //   · Hóa đơn & tiền về — hóa đơn bán ra và tiền chuỗi đã trả cho từng cái.
  //   · Khoản chuỗi trừ lại — chiết khấu/phí/ghi giảm, phần lớn KHÔNG gắn hóa đơn.
  // Bản cũ để hai cái này thành hai TAB NGANG riêng ("Quản lý thanh toán" và
  // "Quản lý chiết khấu") nên trông như hai nghiệp vụ khác nhau, trong khi
  // chúng là hai mặt của cùng một file.
  const bucket = state.bucket === "chiet_khau" ? "chiet_khau" : state.bucket;
  let res;
  try {
    res = await api.mtInvoices(bucket, {
      from_date: state.from, to_date: state.to, search: state.search,
      page: state.page, page_size: state.pageSize, chain: state.chain || undefined,
      customer: state.customer || undefined,
      einvoice: state.einvoice || undefined,
      sort: state.sort || undefined,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  // Đổi bộ lọc có thể làm trang đang xem rơi ra ngoài phạm vi. Hiện trang trống
  // rồi báo "không có dòng nào" là nói dối người dùng.
  if (!res.rows.length && (res.total || 0) > 0 && state.page > 1) {
    state.page = res.pages || 1;
    return loadTab(container, state);
  }

  // Panel việc CHỈ có nghĩa trong bàn làm việc của một chuỗi: hàng đợi là của
  // một chuỗi, còn ở màn liên chuỗi thì "13 việc" không trỏ vào ai.
  const wl = state.view === "chuoi" ? await ensureWorklist(state) : null;

  const cnt = res.counts || {};
  const head = html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      ${PAY_VIEWS.map((v) => html`<button
        class="ktmt-chip ${state.bucket === v.key ? "is-on ktmt-chip--indigo" : "ktmt-chip--plain"}"
        data-payview="${v.key}">${v.label}${cnt[v.key] == null ? "" : html` · <b>${cnt[v.key]}</b>`}</button>`)}
      ${state.canManage && res.source === "erp"
        ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-export" style="margin-left:auto">
            <i class="fas fa-download"></i> Xuất Excel</button>`
        : ""}
    </div></div>

    ${state.einvoice
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <span><b>Đang lọc:</b> ${state.einvoice === "chua"
              ? "hóa đơn CHƯA xuất hóa đơn điện tử — đã ghi sổ nhưng chưa đòi được"
              : "hóa đơn ĐÃ xuất hóa đơn điện tử — phần đòi được"}</span>
            <span class="kt-sub">${res.total || 0} hóa đơn</span>
            <button class="kt-btn kt-btn--outline kt-btn--sm" id="einv-clear"
                    style="margin-left:auto">Bỏ lọc</button>
          </div></div>`
      : ""}`;

  const main = bucket === "chiet_khau"
    ? html`${customerFilterBar(state)}${deductionTable(state, res)}`
    : html`${customerFilterBar(state)}${invoiceTable(state, res)}`;

  // HAI CỘT chỉ khi có hàng đợi để bày. Ở màn liên chuỗi hoặc khi chuỗi hết
  // việc thì một cột trống 380px chỉ để nói "không còn gì" là ăn mất một phần
  // ba bề ngang của bảng.
  const split = wl && wl.total;
  setHTML(body, html`${head}${split
    ? html`<div class="ktmt-split">
        <div>${queuePanel(state, wl)}</div>
        <div>${main}</div>
      </div>`
    : main}`);

  if (bucket !== "chiet_khau") bindRelink(container, state);
  if (split) bindQueuePanel(container, state);
  bindInvoiceTable(container, state, res);

  container.querySelectorAll("button[data-payview]").forEach((b) => {
    b.addEventListener("click", () => {
      state.bucket = b.dataset.payview;
      // Bỏ lọc HĐĐT khi đổi rổ: giữ lại là kế toán đọc "rổ đã thu đủ" mà thật
      // ra đang xem một lát cắt của nó, không có gì trên màn hình nói ra điều đó.
      state.einvoice = "";
      state.page = 1;
      state.picked = new Set();
      loadTab(container, state);
    });
  });
  // Bộ lọc đang bật PHẢI hiện ra và PHẢI tắt được ngay tại chỗ. Một danh sách bị
  // lọc ngầm là con đường ngắn nhất để kế toán đọc ra một con số không phải con
  // số của rổ đang chọn.
  const ec = container.querySelector("#einv-clear");
  if (ec) ec.addEventListener("click", () => {
    state.einvoice = "";
    state.page = 1;
    loadTab(container, state);
  });
  const ex = container.querySelector("#mt-export");
  if (ex) ex.addEventListener("click", async () => {
    ex.disabled = true;
    try {
      await api.mtInvoicesExport(bucket, {
        from_date: state.from, to_date: state.to, search: state.search,
        chain: state.chain || undefined, customer: state.customer || undefined,
        einvoice: state.einvoice || undefined, sort: state.sort || undefined,
      });
    } catch (e) { toast(e.message, "error"); } finally { ex.disabled = false; }
  });
  bindCustomerFilter(container, state);
  bindPager(container, state);
}

// ── HAI CUỐN SỔ, ĐẶT CẠNH NHAU ──────────────────────────────
// ERPNext ghi công nợ NGAY khi Sales Invoice được ghi sổ. Kế toán thì theo dõi
// trên Excel theo ĐẦU HÓA ĐƠN ĐIỆN TỬ, vì siêu thị chỉ trả tiền cho hóa đơn đã
// phát hành. Hai con số khác nhau, và chênh lệch KHÔNG phải sai sót — đó là
// hàng đã giao, đã ghi sổ, chưa xuất hóa đơn điện tử.
//
// Không dựng màn công nợ thứ hai: đó là đường thẳng tới hai nguồn sự thật rồi
// có ngày hai màn lệch nhau mà không ai biết tin cái nào. Đây là MỘT con số
// được bổ đôi — hai vế luôn cộng lại bằng "Chuỗi còn nợ" ở trên.
//
// TÁCH THEO CHUỖI vì việc đi đòi làm theo chuỗi, không làm trên số gộp: biết
// "toàn kênh chưa xuất 375tr" thì chưa gọi cho ai được, biết "WinCommerce
// 210tr, đọng từ tháng 3" thì gọi được ngay.
//
// Mọi con số ở đây bấm vào MỞ ĐƯỢC danh sách đúng tập hóa đơn đã đếm — xem chú
// thích của `openDueEinv`.
function twoBooks(t, board) {
  // "Chưa biết" KHÔNG được hiển thị thành 0. Site chưa có ô số hóa đơn điện tử
  // nào thì mọi phép chia đều vô nghĩa; hiện "0đ chưa xuất" là nói với kế toán
  // rằng đã xuất hết, mà sự thật là không có gì để mà biết.
  if (!t.debt_einv_known) {
    return html`
      <div class="kt-card kt-mb"><div class="kt-card-body kt-sub">
        <i class="fas fa-circle-question"></i>
        Chưa tách được công nợ theo <b>đầu hóa đơn điện tử</b>: site chưa có ô số HĐĐT
        (<code>custom_misa_inv_no</code> hoặc <code>vn_einvoice_number</code>) trên Sales Invoice.
        Chạy <code>bench migrate</code> rồi con số sẽ tự hiện — không phải "đã xuất hết".
      </div></div>`;
  }

  const chua = t.debt_no_einv || 0;
  const roi = t.debt_einv || 0;

  // Chuỗi nào còn nợ chưa xuất HĐĐT nhiều nhất lên trước. Chuỗi hết sạch xếp
  // cuối nhưng VẪN hiện — biến mất khỏi bảng thì không phân biệt được với
  // "chuỗi này chưa bao giờ có dữ liệu".
  //
  // Nhóm "chưa gán chuỗi" là MỘT DÒNG NGANG HÀNG, vì `totals` đã cộng nó. Để nó
  // ra ngoài bảng thì các dòng không cộng lại bằng con số ghi ngay trên đầu.
  // Nhóm "chưa gán chuỗi" KHÔNG còn nằm lẫn như một dòng chuỗi: nó không phải
  // một chuỗi, và để chung thì mắt đọc nó như chuỗi thứ chín. Nó lên DẢI CẢNH
  // BÁO phía trên (có nút xử) và xuống TFOOT như một dòng tổng phụ — nhờ vậy
  // `Tổng kênh MT` vẫn khớp `totals.debt`, đúng lý do nó được cộng vào tổng.
  const ua = board.unassigned_debt && board.unassigned_debt.debt_invoices
    ? board.unassigned_debt : null;
  const rows = (board.chains || [])
    .sort((a, b) => (b.debt_no_einv || 0) - (a.debt_no_einv || 0)
                    || (b.debt || 0) - (a.debt || 0));
  const sum = (k) => rows.reduce((a, c) => a + (c[k] || 0), 0);

  return html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:10px">
        <b>Hai cách theo dõi công nợ — đặt cạnh nhau</b>
        <span class="kt-sub">cộng lại đúng bằng ${formatVND(t.debt)} ở trên</span>
      </div>
      <div class="kt-grid-2">
        <div class="kt-stat is-link" id="tb-open-da" style="cursor:pointer">
          <div class="kt-stat-label"><i class="fas fa-file-invoice"></i> Đòi được — đã xuất HĐĐT</div>
          <div class="kt-stat-value pos">${formatVNDShort(roi)}</div>
          <div class="kt-stat-sub">${t.debt_einv_count || 0} hóa đơn · ${formatVND(roi)}
            · đây là cột kế toán theo dõi trên Excel</div>
          ${t.debt_einv_dead_count
            ? html`<div class="kt-stat-sub" style="color:var(--kt-warning);margin-top:4px">
                <i class="fas fa-triangle-exclamation"></i>
                trong đó <b>${t.debt_einv_dead_count} hóa đơn · ${formatVND(t.debt_einv_dead)}</b>
                mang số HĐĐT đã <b>hủy/bị thay thế</b> trên MISA — siêu thị không trả theo số đã
                chết, phải phát hành lại mới đòi được
              </div>`
            : ""}
        </div>
        <div class="kt-stat is-link" id="tb-open" style="cursor:pointer">
          <div class="kt-stat-label"><i class="fas fa-triangle-exclamation"></i> Chưa đòi được — CHƯA xuất HĐĐT</div>
          <div class="kt-stat-value ${chua ? "neg" : ""}">${formatVNDShort(chua)}</div>
          <div class="kt-stat-sub">${t.debt_no_einv_count || 0} hóa đơn · ${formatVND(chua)}${
            t.debt_no_einv_oldest
              ? html` · cũ nhất <b>${formatDate(t.debt_no_einv_oldest)}</b>`
              : ""}${chua ? " — bấm để mở danh sách" : ""}</div>
        </div>
      </div>

      ${rows.length
        ? html`<div class="kt-table-wrap" style="margin-top:12px"><table class="kt-table ktmt-table">
            <thead><tr>
              <th class="kt-col-mid">Chuỗi</th>
              <th class="num">Còn nợ</th>
              <th class="num">Đòi được<div class="kt-sub">đã xuất HĐĐT</div></th>
              <th class="num">Chưa đòi được<div class="kt-sub">chưa xuất HĐĐT</div></th>
              <th class="num">Việc</th>
            </tr></thead>
            <tbody>${rows.map((c) => twoBooksRow(c))}</tbody>
            <tfoot>
              <tr>
                <td><b>Cộng ${rows.length} chuỗi</b></td>
                <td class="num">${formatVND(sum("debt"))}</td>
                <td class="num" style="color:var(--kt-success)">${formatVND(sum("debt_einv"))}</td>
                <td class="num" style="color:var(--kt-danger)">${formatVND(sum("debt_no_einv"))}</td>
                <td class="num">${sum("todo") || html`<span class="kt-sub">—</span>`}</td>
              </tr>
              ${ua ? html`<tr>
                <td style="color:#92400e">Khách chưa khai chuỗi</td>
                <td class="num" style="color:#92400e">${formatVND(ua.debt)}</td>
                <td class="num" style="color:#92400e">${formatVND(ua.debt_einv || 0)}
                  <span class="kt-sub">· ${ua.debt_einv_count || 0} HĐ</span></td>
                <td class="num" style="color:#92400e">${formatVND(ua.debt_no_einv || 0)}
                  <span class="kt-sub">· ${ua.debt_no_einv_count || 0} HĐ</span></td>
                <td class="num" style="color:#92400e">${ua.todo || html`<span class="kt-sub">—</span>`}</td>
              </tr>` : ""}
              <tr style="background:var(--kt-bg-soft)">
                <td><b>Tổng kênh MT</b></td>
                <td class="num"><b>${formatVND(t.debt)}</b></td>
                <td class="num" style="color:var(--kt-success)"><b>${formatVND(t.debt_einv || 0)}</b></td>
                <td class="num" style="color:var(--kt-danger)"><b>${formatVND(t.debt_no_einv || 0)}</b></td>
                <td class="num"><b>${t.todo || 0}</b></td>
              </tr>
            </tfoot>
          </table></div>`
        : ""}

      <div class="kt-sub" style="margin-top:10px">
        Sổ ERPNext ghi nợ ngay khi hóa đơn được ghi sổ. Siêu thị chỉ trả cho hóa đơn
        <b>đã phát hành</b>, nên phần chưa xuất HĐĐT tuy đã là doanh thu nhưng chưa đòi
        được. Chênh lệch này không phải sai sót — nó là <b>việc phải làm</b>: xuất nốt hóa đơn.
      </div>
      <div class="kt-sub" style="margin-top:8px">
        Con số trên chỉ tính phần <b>còn nợ</b>. Hóa đơn đã thu đủ tiền mà vẫn trống ô số HĐĐT
        thì không hiện ở đây — nó là lỗ hổng chứng từ, soi ở
        <a href="#/cong-no-mt?g=g-soat-hddt">Soát HĐ bỏ sót số HĐĐT</a>.
      </div>
    </div></div>`;
}

// Một dòng của bảng tách theo chuỗi.
//
// Ô "chưa đòi được" mang cả ba thứ quyết định thứ tự làm: BAO NHIÊU TIỀN, BAO
// NHIÊU TỜ, và ĐỌNG TỪ BAO GIỜ. Ngày cũ nhất là thứ hay bị bỏ quên nhất mà lại
// nói nhiều nhất — 2 triệu đọng từ tháng 3 nguy hơn 20 triệu của tuần trước.
function twoBooksRow(c) {
  const chua = c.debt_no_einv || 0;
  const roi = c.debt_einv || 0;

  // Chuỗi KHÔNG CÒN NỢ khác hẳn chuỗi KHÔNG BIẾT. Trước đây hai cái này dùng
  // chung một nhánh nên site sạch nợ bị báo "chưa có ô số HĐĐT, chạy bench
  // migrate" — đi bảo kế toán sửa một thứ không hỏng.
  if (!c.debt) {
    return html`<tr>
      <td class="kt-col-mid">${c.chain || html`<span class="kt-sub">(chưa gán chuỗi)</span>`}</td>
      <td class="num kt-sub" colspan="3">không còn nợ</td>
      <td class="num">${c.todo
        ? html`<span class="ktmt-state ktmt-state--qua-han">${c.todo}</span>`
        : html`<span class="kt-sub">—</span>`}</td>
    </tr>`;
  }
  return html`<tr class="tb-chain" data-chain="${c.chain}" style="cursor:pointer"
        title="${c.chain
          ? `bấm để mở danh sách hóa đơn chưa xuất HĐĐT của ${c.chain}`
          : "bấm để mở công nợ toàn kênh — nhóm này hiện thành dòng (chưa gán chuỗi)"}">
    <td class="kt-col-mid">${c.chain
      ? c.chain
      : html`<span style="color:var(--kt-warning)">(chưa gán chuỗi)</span>
          <div class="kt-sub">${c.debt_invoices} HĐ của khách chưa khai chuỗi —
            bấm <b>Gán chuỗi cho khách</b> ở cuối trang</div>`}</td>
    <td class="num">${formatVND(c.debt)}</td>
    <td class="num">${c.debt_einv_known
      ? html`<span style="color:var(--kt-success)">${formatVND(roi)}</span>
          <div class="kt-sub">${c.debt_einv_count || 0} HĐ${c.debt_einv_dead_count
            ? html` · <span style="color:var(--kt-warning)"
                title="số HĐĐT đã hủy hoặc bị thay thế trên MISA — phải phát hành lại mới đòi được"
              >${c.debt_einv_dead_count} số đã chết</span>`
            : ""}</div>`
      : html`<span class="kt-sub">chưa biết</span>`}</td>
    <td class="num">${!c.debt_einv_known
      ? html`<span class="kt-sub">chưa biết</span>`
      : chua
        ? html`<b style="color:var(--kt-danger)">${formatVND(chua)}</b>
            <div class="kt-sub">${c.debt_no_einv_count || 0} HĐ${
              c.debt_no_einv_oldest ? html` · từ ${formatDate(c.debt_no_einv_oldest)}` : ""}</div>
            ${deadlineNote(c)}`
        : html`<span class="kt-sub">—</span>`}</td>
    <td class="num">${c.todo
      ? html`<span class="ktmt-state ktmt-state--qua-han">${c.todo}</span>`
      : html`<span class="kt-sub">—</span>`}</td>
  </tr>`;
}

// ── HAI CUỐN SỔ, ĐẶT CẠNH NHAU — BẢN CỦA MỘT CHUỖI ────────────────────────
//
// Cùng phép chia của thẻ toàn kênh, nhưng đứng ngay trong bàn làm việc của
// chuỗi, vì việc đi đòi và việc xuất nốt hóa đơn đều làm THEO CHUỖI. Bắt kế
// toán quay về bảng tổng để đọc con số của chuỗi mình đang làm là bắt họ nhớ
// một con số qua hai màn hình.
//
// Hai vế LUÔN cộng lại bằng "còn nợ" của chính chuỗi này — đó là điều kiện để
// hai con số cạnh nhau không biến thành hai nguồn sự thật. Câu tổng in ngay
// trên đầu để kiểm được bằng mắt.
// ⚠ CHÚ THÍCH GIẢI THÍCH ĐỂ NGOÀI TEMPLATE, KHÔNG ĐỂ TRONG `<!-- -->`.
// Chú thích HTML nằm trong template literal vẫn là NỘI DUNG chuỗi: một dấu
// backtick trong đó (ví dụ nhắc tên bảng `tabGL Entry`) ĐÓNG luôn template và
// cả file gãy cú pháp — portal trắng màn hình. Đã dính đúng lỗi này khi viết ô
// sổ cái bên dưới; `portal_js_check` bắt được trước khi đẩy.
//
// Ô `#cb-gl` (cuốn sổ thứ ba) để RỖNG ở đây và nạp riêng bằng `loadChainGl`:
// nó quét bảng GL Entry, nặng hơn hẳn hai ô trên vốn đã có sẵn trong get_board.
function twoBooksChain(c) {
  if (!c.debt_einv_known) {
    // Không vẽ 0đ khi chưa biết. 0đ đọc thành "đã xuất hết".
    if (!c.debt) return "";
    return html`
      <div class="kt-card kt-mb"><div class="kt-card-body kt-sub">
        <i class="fas fa-circle-question"></i>
        Chưa tách được công nợ theo <b>đầu hóa đơn điện tử</b> cho chuỗi này —
        site chưa có ô số HĐĐT trên Sales Invoice. Chạy <code>bench migrate</code>
        rồi con số sẽ tự hiện; đây <b>không</b> phải "đã xuất hết".
      </div></div>`;
  }

  const chua = c.debt_no_einv || 0;
  const roi = c.debt_einv || 0;
  return html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:10px">
        <b>Hai cách theo dõi công nợ của ${c.chain}</b>
        <span class="kt-sub">hai vế cộng lại đúng bằng ${formatVND(c.debt)} còn nợ</span>
      </div>
      <div class="kt-grid-2">
        <div class="kt-stat is-link" id="cb-open-da" style="cursor:pointer">
          <div class="kt-stat-label"><i class="fas fa-file-invoice"></i>
            Sổ kế toán theo dõi — ĐÃ xuất HĐĐT</div>
          <div class="kt-stat-value pos">${formatVNDShort(roi)}</div>
          <div class="kt-stat-sub">${c.debt_einv_count || 0} hóa đơn · ${formatVND(roi)}
            · đây là cột kế toán theo dõi trên Excel${roi ? " — bấm để mở danh sách" : ""}</div>
          ${c.debt_einv_dead_count
            ? html`<div class="kt-stat-sub" style="color:var(--kt-warning);margin-top:4px">
                <i class="fas fa-triangle-exclamation"></i>
                trong đó <b>${c.debt_einv_dead_count} HĐ · ${formatVND(c.debt_einv_dead)}</b>
                mang số đã <b>hủy/bị thay thế</b> trên MISA — phải phát hành lại mới đòi được
              </div>`
            : ""}
        </div>
        <div class="kt-stat is-link" id="cb-open" style="cursor:pointer">
          <div class="kt-stat-label"><i class="fas fa-triangle-exclamation"></i>
            Sổ ERPNext ghi thêm — CHƯA xuất HĐĐT</div>
          <div class="kt-stat-value ${chua ? "neg" : ""}">${formatVNDShort(chua)}</div>
          <div class="kt-stat-sub">${c.debt_no_einv_count || 0} hóa đơn · ${formatVND(chua)}${
            c.debt_no_einv_oldest
              ? html` · cũ nhất <b>${formatDate(c.debt_no_einv_oldest)}</b>`
              : ""}${chua ? " — bấm để mở danh sách" : ""}</div>
          ${deadlineNote(c)}
        </div>
      </div>
      <div class="kt-sub" style="margin-top:10px">
        ERPNext ghi nợ ngay khi hóa đơn được ghi sổ; ${c.chain} chỉ trả cho hóa đơn
        <b>đã phát hành</b>. Nên vế phải là doanh thu đã có nhưng <b>chưa đòi được</b> —
        không phải sai sót, mà là việc phải làm: xuất nốt hóa đơn.
        ${chua ? html`Bấm vào vế phải để mở đúng danh sách của ${c.chain}.` : ""}
      </div>

      <div id="cb-gl" style="margin-top:14px">
        <div class="kt-sub"><i class="fas fa-circle-notch fa-spin"></i>
          đang đọc sổ cái TK 131…</div>
      </div>
    </div></div>`;
}

// ── CUỐN SỔ THỨ BA: SỔ CÁI TK 131 ─────────────────────────────────────────
//
// Hai ô trên đến từ BẢNG KÊ CHUỖI; ô này đến từ BÚT TOÁN. Kênh MT cố ý không
// tạo Payment Entry, nên sổ cái luôn tụt lại sau đúng bằng phần tiền đã khớp
// mà chưa ai ghi sổ. LỆCH LÀ BÌNH THƯỜNG — câu hỏi là lệch nằm ở đâu.
//
// Vì vậy không in mỗi con số lệch: in thẳng CẦU NỐI bốn khoản cộng lại đúng
// chỗ lệch, cộng danh sách nguyên nhân đo được. "Lệch 412 triệu" mà không nói
// nằm ở đâu thì kế toán hoặc bỏ qua, hoặc sửa bừa một bên cho khớp.
async function loadChainGl(container, state) {
  const box = container.querySelector("#cb-gl");
  if (!box) return;
  let d;
  try {
    d = await api.mtGlBridge({ chain: state.chain });
  } catch (e) {
    setHTML(box, html`<div class="kt-sub" style="color:var(--kt-danger)">
      Không đọc được sổ cái: ${e.message}</div>`);
    return;
  }
  const r = (d.chains || [])[0];
  if (!r) { setHTML(box, ""); return; }
  setHTML(box, glBridgeCard(r, d));
  const t = box.querySelector("#cb-gl-toggle");
  if (t) t.addEventListener("click", () => {
    const p = box.querySelector("#cb-gl-detail");
    const open = p.style.display !== "none";
    p.style.display = open ? "none" : "";
    t.textContent = open ? "Vì sao lệch ▾" : "Thu gọn ▴";
  });
  // "Đi xử lý" đưa thẳng tới bước làm được việc đó. Nêu nguyên nhân mà không
  // mở ra được chỗ xử lý thì nó chỉ là một lời than.
  box.querySelectorAll("button[data-step]").forEach((b) => {
    b.addEventListener("click", () => {
      state.step = b.dataset.step;
      state.page = 1;
      syncHash(state);
      paint(container, state);
    });
  });
}

function glBridgeCard(r, d) {
  const tone = Math.abs(r.diff) < 1 ? "" : (r.diff > 0 ? "warn" : "neg");
  return html`
    <div style="border-top:1px solid var(--kt-border);padding-top:12px">
      <div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap">
        <div class="kt-stat-label" style="margin:0">
          <i class="fas fa-book"></i> Sổ cái TK 131 — số dư thật trên sổ</div>
        <b style="font-size:20px">${formatVND(r.gl_total)}</b>
        <span class="kt-sub">so với rổ hóa đơn ${formatVND(r.basket_open)} →
          <b class="${tone}">lệch ${r.diff >= 0 ? "+" : "−"}${formatVND(Math.abs(r.diff))}</b></span>
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="cb-gl-toggle"
                style="margin-left:auto">Vì sao lệch ▾</button>
      </div>

      ${!r.balanced
        ? html`<div class="kt-sub" style="color:var(--kt-danger);margin-top:6px">
            <i class="fas fa-bug"></i> Cầu nối còn dư ${formatVND(r.residual)} — đây là
            <b>lỗi code</b>, không phải sai số cho phép. Báo lại để sửa; đừng dùng con số này.
          </div>`
        : ""}

      <div id="cb-gl-detail" style="display:none;margin-top:12px">
        <div class="kt-sub" style="margin-bottom:8px">${d.note}</div>
        <div class="kt-table-wrap"><table class="kt-table">
          <thead><tr><th class="kt-col-wide">Khoản mục</th><th class="num">Số tiền</th></tr></thead>
          <tbody>
            ${r.items.map((i) => html`<tr>
              <td class="kt-col-wide">${i.label}<div class="kt-sub">${i.why}</div></td>
              <td class="num">${formatVND(i.amount)}</td>
            </tr>`)}
            <tr style="border-top:2px solid var(--kt-border)">
              <td class="kt-col-wide"><b>Cộng lại = chỗ lệch</b>
                <div class="kt-sub">bốn khoản trên lấy từ cùng một tập dữ liệu nên phải
                  cộng đúng bằng chỗ lệch — dư một đồng là lỗi code</div></td>
              <td class="num"><b>${formatVND(r.diff)}</b></td>
            </tr>
          </tbody>
        </table></div>

        ${(r.causes || []).length
          ? html`<div style="margin-top:14px">
              <div style="font-weight:600;margin-bottom:6px">Nguyên nhân đo được</div>
              <div class="kt-sub" style="margin-bottom:8px">
                Đây là <b>nghi can có số</b>, không phải phân rã của chỗ lệch — chúng chồng
                lấn nhau và <b>không</b> cộng lại thành con số trên.
              </div>
              ${r.causes.map((x) => html`
                <div class="kt-card" style="margin-bottom:8px"><div class="kt-card-body">
                  <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
                    <b>${x.label}</b>
                    <b style="color:var(--kt-danger)">${formatVND(x.amount)}</b>
                    ${x.count ? html`<span class="kt-sub">${x.count} chứng từ</span>` : ""}
                    <button class="kt-btn kt-btn--outline kt-btn--sm" data-step="${x.step}"
                            style="margin-left:auto">Đi xử lý</button>
                  </div>
                  <div class="kt-sub" style="margin-top:6px">${x.why}</div>
                  <div class="kt-sub" style="margin-top:4px"><b>Việc phải làm:</b> ${x.action}</div>
                </div></div>`)}
            </div>`
          : html`<div class="kt-sub" style="margin-top:12px">
              Không có nguyên nhân nào <b>đo được</b> đang mở. Phần lệch còn lại nằm ở các
              khoản mục trong bảng trên.
            </div>`}
      </div>
    </div>`;
}

// Hạn xuất hóa đơn RIÊNG của chuỗi. Chỉ hiện cho chuỗi thật sự có hạn khai
// trong `mt_hub.EINV_DEADLINE` (hiện chỉ Emart, nguồn SOP §5).
//
// Bảy chuỗi còn lại KHÔNG hiện gì — chúng không có hạn quy định, và vẽ một dòng
// "còn hạn" cho chúng là dạy kế toán đọc lướt qua cả cột.
function deadlineNote(c) {
  const d = c.einv_deadline;
  if (!d) return "";
  return d.breached
    ? html`<div class="kt-sub" style="color:var(--kt-danger);font-weight:600">
        <i class="fas fa-calendar-xmark"></i> QUÁ HẠN — ${c.chain} chốt ngày ${d.day}
        hàng tháng cho hóa đơn tháng trước</div>`
    : html`<div class="kt-sub" style="color:var(--kt-warning)">
        <i class="fas fa-calendar-day"></i> hạn ngày ${d.day} tháng sau</div>`;
}


// Bốn cách nhìn của bước "Đối soát thanh toán" — khóa đúng như `mt.get_invoices`.
// Ba rổ đầu là HÓA ĐƠN, rổ cuối là DÒNG BẢNG KÊ: khoản chuỗi trừ lại phần lớn
// không gắn với hóa đơn nào (phí hỗ trợ, chiết khấu tháng, NET OFF) nên không
// đếm thành hóa đơn được. Cùng một file, hai mặt.
// MẶC ĐỊNH là `chua_thanh_toan` — xem `state.bucket` ở `render()`. Rổ "Tất cả"
// là nơi hóa đơn đã thu đủ nằm lẫn với việc còn phải làm; mở màn ra mà thấy
// 194 dòng trong đó 87 dòng không còn gì để làm thì việc thật bị pha loãng.
const PAY_VIEWS = [
  { key: "chua_thanh_toan", label: "Chưa thu đủ" },
  { key: "da_thanh_toan", label: "Đã thu đủ" },
  { key: "tat_ca", label: "Tất cả" },
  { key: "chiet_khau", label: "Khoản chuỗi trừ lại" },
];


// số dòng đang hiển thị — đọc nhầm hai con số này là đếm sót.
function pager(res, unit) {
  const total = res.total || 0;
  const pages = res.pages || 1;
  const page = res.page || 1;
  const from = (page - 1) * (res.page_size || 20) + 1;
  const to = from + (res.rows.length - 1);

  const btn = (p, label, disabled, active) => html`<button
    class="kt-btn kt-btn--sm ${active ? "" : "kt-btn--outline"}"
    data-page="${p}" ${disabled ? "disabled" : ""}>${label}</button>`;

  // Cửa sổ 5 trang quanh trang hiện tại — kênh MT có hàng nghìn hóa đơn/tháng,
  // in hết số trang là vỡ hàng.
  let lo = Math.max(1, page - 2);
  const hi = Math.min(pages, lo + 4);
  lo = Math.max(1, hi - 4);
  const nums = [];
  for (let p = lo; p <= hi; p++) nums.push(p);

  return html`
    <div class="kt-pager" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:10px">
      <span class="kt-sub">${from}–${to} / ${total} ${unit}</span>
      ${pages > 1 ? html`<span style="margin-left:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        ${btn(1, html`<i class="fas fa-angles-left"></i>`, page <= 1, false)}
        ${btn(page - 1, html`<i class="fas fa-angle-left"></i>`, page <= 1, false)}
        ${lo > 1 ? html`<span class="kt-sub">…</span>` : ""}
        ${nums.map((p) => btn(p, String(p), false, p === page))}
        ${hi < pages ? html`<span class="kt-sub">…</span>` : ""}
        ${btn(page + 1, html`<i class="fas fa-angle-right"></i>`, page >= pages, false)}
        ${btn(pages, html`<i class="fas fa-angles-right"></i>`, page >= pages, false)}
      </span>` : ""}
    </div>`;
}

function bindPager(container, state) {
  container.querySelectorAll(".kt-pager button[data-page]").forEach((b) => {
    b.addEventListener("click", () => {
      const p = parseInt(b.dataset.page, 10);
      if (!p || p === state.page) return;
      state.page = p;
      loadTab(container, state);
      const body = container.querySelector("#mt-body");
      if (body) body.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

// Bảng hóa đơn của bước "Đối soát thanh toán".
// KHÔNG tự vẽ thanh chọn rổ ở đây: `loadTab` đã vẽ MỘT thanh chung cho cả bốn
// rổ (kể cả "Khoản chuỗi trừ lại"). Bản cũ vẽ ở cả hai chỗ nên trên màn hình
// có hai thanh chọn chồng nhau, mỗi thanh biết một phần sự thật.
// Ô chọn theo TRANG. Giữ qua trang thì thanh ghi "3 hóa đơn" trong khi màn hình
// không hiện tờ nào đang được chọn, và hành động hàng loạt chạy lên những tờ
// người dùng không nhìn thấy. Trang/rổ đổi -> bỏ chọn.
//
// ⚠ Phải chốt Ở ĐÂY, trước khi vẽ. Bản cũ chốt trong `bindInvoiceTable`, tức là
// SAU khi `invoiceRow` đã đọc rổ cũ để đặt `checked`: đổi trang là màn hình hiện
// vài ô ĐÃ TÍCH trong khi bộ đếm nói "0 hóa đơn" và hai nút mờ đi. Người dùng
// thấy ba ô tích và một nút không bấm được, không có gì giải thích.
function pickedFor(state, res) {
  const key = `${res.bucket}|${res.page}|${res.sort}|${res.total}`;
  if (state.pickedKey !== key) {
    state.picked = new Set();
    state.pickedKey = key;
  }
  return state.picked;
}

function invoiceTable(state, res) {
  const tol = res.tolerance || 0;
  const t = res.totals || null;
  const picked = pickedFor(state, res);
  const allOn = res.rows.length > 0 && res.rows.every((r) => picked.has(r.name));
  return html`
    <div class="kt-card">
      ${!res.rows.length
        ? html`<div class="kt-card-body"><div class="kt-empty"><i class="fas fa-circle-check"></i>
            <p>Không có hóa đơn nào trong rổ này.</p></div></div>`
        : html`
          <div class="ktmt-bulkbar">
            <input type="checkbox" id="inv-all" title="Chọn cả trang" ${allOn ? "checked" : ""}>
            <span>Chọn để <b id="inv-n">${picked.size || 0}</b> hóa đơn —
              <button class="kt-btn kt-btn--outline kt-btn--sm" id="inv-bulk-bk" disabled>Gán vào bảng kê</button>
              <button class="kt-btn kt-btn--outline kt-btn--sm" id="inv-bulk-paid" disabled>Đánh dấu đã thu</button>
            </span>
            <span style="margin-left:auto">Sắp xếp:
              <select class="kt-input kt-input--sm" id="inv-sort" style="width:auto;display:inline-block">
                ${(res.sorts || []).map((x) => html`<option value="${x.key}"
                  ${res.sort === x.key ? "selected" : ""}>${x.label}</option>`)}
              </select></span>
          </div>
          <div class="kt-table-wrap"><table class="kt-table ktmt-table">
            <thead><tr>
              <th class="kt-col-role"></th>
              <th>Hóa đơn</th><th>Ngày</th><th class="kt-col-wide">Khách</th>
              <th>Ký hiệu · Số HĐ</th>
              <th class="num">Tổng tiền</th><th class="num">Đã nhận</th><th class="num">Còn lại</th>
              <th class="num">Tuổi nợ</th><th>Trạng thái</th>
            </tr></thead>
            <tbody>${res.rows.map((r) => invoiceRow(r, tol, state.canManage, picked))}</tbody>
            ${t ? invoiceFoot(t) : ""}
          </table></div>
          <div class="kt-card-body" style="padding-top:0">
            ${pageSizeBar(state, res)}
            ${pager(res, "hóa đơn")}
          </div>`}
    </div>`;
}

// Dòng CỘNG của cả bộ lọc, không phải của trang đang xem — xem `_invoice_page`.
// Ô "quá hạn" nói thêm số tờ CHƯA KHAI HẠN: chúng không nằm trong quá hạn mà
// cũng không nằm trong chưa-đến-hạn, nên nếu không nói ra thì con số quá hạn
// trông như đã bao trọn cả rổ.
function invoiceFoot(t) {
  return html`<tfoot><tr>
    <td></td>
    <td colspan="4"><b>Cộng ${t.count} hóa đơn của bộ lọc</b></td>
    <td class="num">${formatVND(t.invoiced)}</td>
    <td class="num">${formatVND(t.paid)}</td>
    <td class="num"><b>${formatVND(t.remaining)}</b></td>
    <td class="num">${t.overdue
      ? html`<span style="color:var(--kt-danger)">qh ${formatVNDShort(t.overdue)}</span>`
      : html`<span class="kt-sub">—</span>`}</td>
    <td>${t.no_term
      ? html`<span class="kt-sub" title="Không tính được tuổi nợ vì khách chưa khai hạn thanh toán">${t.no_term} tờ chưa khai hạn</span>`
      : ""}</td>
  </tr>
  ${t.returns ? html`<tr><td></td><td colspan="9" class="kt-sub">
    Trong đó <b>${t.returns} phiếu trả hàng</b> (${formatVNDShort(t.returns_amt)}) —
    có trong danh sách, <b>không</b> nằm trong ba cột cộng ở trên: một lần bán đã bị
    hủy thì không còn là khoản phải thu.
  </td></tr>` : ""}
  </tfoot>`;
}

const PAGE_SIZES = [20, 50, 100, 200];

function pageSizeBar(state, res) {
  return html`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px">
    <span class="kt-sub">Số dòng mỗi trang</span>
    <select class="kt-input kt-input--sm" id="inv-size" style="width:auto">
      ${PAGE_SIZES.map((n) => html`<option value="${n}"
        ${(res.page_size || 20) === n ? "selected" : ""}>${n}</option>`)}
    </select>
  </div>`;
}

const STATE_CLASS = {
  "Quá hạn": "ktmt-state--qua-han",
  "Phát hành lại": "ktmt-state--phat-hanh-lai",
  "Cần xác nhận": "ktmt-state--can-xac-nhan",
  "Chờ bảng kê": "ktmt-state--cho-bang-ke",
  "Đã khớp": "ktmt-state--da-khop",
};

// Tuổi nợ. "Chưa khai hạn" KHÔNG được vẽ thành 0 ngày — 0 đọc là "đến hạn hôm
// nay", một kết luận về việc chưa ai khai. Số âm là CÒN bao nhiêu ngày nữa.
function ageCell(r) {
  const d = r.days_overdue;
  if (d === null || d === undefined) {
    return html`<span class="kt-sub" title="Khách chưa khai hạn thanh toán">chưa khai hạn</span>`;
  }
  if (d > 0) {
    const tone = d >= 30 ? "danger" : "warning";
    return html`<b style="color:var(--kt-${tone})">${d} ngày</b>`;
  }
  return html`<span class="kt-sub">còn ${-d} ngày</span>`;
}

function invoiceRow(r, tol, canManage, picked) {
  const total = Math.abs(r.grand_total || 0);
  const paid = r.paid || 0;
  const remaining = r.remaining || 0;
  // "Đã trả đủ" chỉ khi phần còn thiếu nằm trong sai số 1 đồng do backend công bố.
  // Nới rộng sai số ở giao diện là tự tay dán nhãn "đủ" cho hóa đơn còn thiếu tiền.
  const done = paid > 0 && remaining <= tol;
  const over = paid - total > tol;
  // `paid` là số RÒNG (đã trả − đã đòi lại). Một hóa đơn Co.op bị đòi lại trọn
  // vẹn hiện "Đã nhận —", y hệt một hóa đơn chưa ai trả đồng nào — hai tình
  // huống hoàn toàn khác nhau, và tình huống thứ hai không cần đi hỏi ai.
  const clawed = r.clawed_back || 0;
  const st = r.status || "";

  return html`<tr>
    <td class="kt-col-role"><input type="checkbox" class="inv-pick" data-si="${r.name}"
      ${picked && picked.has(r.name) ? "checked" : ""}></td>
    <td><a target="_blank" href="/desk/sales-invoice/${q(r.name)}">${r.name}</a>
      ${r.is_return ? html` <span class="kt-badge kt-badge--yellow">trả hàng</span>` : ""}</td>
    <td>${formatDate(r.posting_date)}</td>
    <td class="kt-cell-wrap">${r.customer_name || r.customer}</td>
    <td>${r.inv_series || "—"}${r.inv_no ? html` · <b>${r.inv_no}</b>` : ""}</td>
    <td class="num">${formatVND(total)}</td>
    <td class="num">${paid ? formatVND(paid) : html`<span class="kt-sub">—</span>`}
      ${clawed ? html`<div class="kt-sub" title="Chuỗi đã trả rồi đòi lại ở một bảng kê sau. Cột này là số RÒNG."
        >gộp ${formatVNDShort(r.paid_gross)} · đòi lại ${formatVNDShort(clawed)}</div>` : ""}
      ${over ? html`<div><span class="kt-badge kt-badge--red">trả vượt</span></div>` : ""}</td>
    <td class="num">${done
      ? html`<span class="kt-badge kt-badge--green">đủ</span>`
      : html`<b>${formatVND(remaining)}</b>`}</td>
    <td class="num">${ageCell(r)}</td>
    <td>${st
      ? html`<span class="ktmt-state ${STATE_CLASS[st] || ""}">${st}${
          r.status_ref ? ` ${r.status_ref}` : ""}</span>`
      : html`<span class="kt-sub">—</span>`}
      ${(r.payments || []).length ? paymentCell(r, canManage) : ""}</td>
  </tr>`;
}

function bindInvoiceTable(container, state, res) {
  // Rổ chọn đã được `pickedFor` chốt lúc vẽ — ở đây KHÔNG chốt lại, vì chốt lại
  // sau khi HTML đã đọc rổ cũ là đúng cái lệch "ô tích mà bộ đếm nói 0".
  const picked = state.picked || (state.picked = new Set());
  const boxes = [...container.querySelectorAll("input.inv-pick")];
  const nEl = container.querySelector("#inv-n");
  const all = container.querySelector("#inv-all");
  const bulkBtns = ["#inv-bulk-bk", "#inv-bulk-paid"]
    .map((id) => container.querySelector(id)).filter(Boolean);   // chỉ để bật/tắt
  const sync = () => {
    if (nEl) nEl.textContent = String(picked.size);
    bulkBtns.forEach((b) => { b.disabled = !picked.size; });
    // Ô "cả trang" phải theo các ô con, nếu không nó còn tích trong khi người
    // dùng vừa bỏ tích một dòng — và cú bấm tiếp theo lên nó sẽ BỎ chọn hết
    // thay vì chọn hết, ngược hẳn với cái nó đang hiện.
    if (all) {
      const on = boxes.filter((cb) => cb.checked).length;
      all.checked = boxes.length > 0 && on === boxes.length;
      all.indeterminate = on > 0 && on < boxes.length;
    }
  };
  boxes.forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) picked.add(cb.dataset.si); else picked.delete(cb.dataset.si);
      sync();
    });
  });
  if (all) all.addEventListener("change", () => {
    boxes.forEach((cb) => {
      cb.checked = all.checked;
      if (all.checked) picked.add(cb.dataset.si); else picked.delete(cb.dataset.si);
    });
    sync();
  });
  sync();

  // "GÁN VÀO BẢNG KÊ" đi chiều NGƯỢC với màn đối soát: cầm vài hóa đơn còn nợ
  // rồi tìm dòng tiền của chúng trên các bảng kê ĐÃ NẠP. Hóa đơn không có dòng
  // nào khớp thì không nối gì cả — nó vẫn còn nợ, vì nó thật sự còn nợ.
  const bk = container.querySelector("#inv-bulk-bk");
  if (bk) bk.addEventListener("click", () => {
    if (!picked.size) return;
    openReverseMatch(container, state, [...picked]);
  });

  // "ĐÁNH DẤU ĐÃ THU" CỐ Ý KHÔNG LÀM ĐƯỢC, và nút phải nói ra vì sao thay vì
  // im lặng không phản ứng.
  //
  // Kênh MT không tạo Payment Entry — mọi khoản trừ công nợ đi bằng BÚT TOÁN
  // do người duyệt (SOP §1, và cả tầng `mt_je` dựng quanh luật đó). Một cái
  // tick trừ được công nợ là trừ tiền mà không có chứng từ nào đứng sau, và
  // nó sẽ trừ đúng những tờ khó đòi nhất — những tờ người ta muốn cho khuất
  // mắt. Nên đây là chỗ DUY NHẤT trong màn này không có đường tắt.
  const mp = container.querySelector("#inv-bulk-paid");
  if (mp) mp.addEventListener("click", () => {
    toast("Trừ công nợ phải đi bằng BÚT TOÁN ở bước Bút toán, không bằng một cái tick: "
      + "kênh MT không tạo Payment Entry, nên đánh dấu đã thu ở đây là trừ tiền mà "
      + "không có chứng từ nào đứng sau.", "warning");
  });

  const sortSel = container.querySelector("#inv-sort");
  if (sortSel) sortSel.addEventListener("change", () => {
    state.sort = sortSel.value;
    state.page = 1;
    loadTab(container, state);
  });
  const sizeSel = container.querySelector("#inv-size");
  if (sizeSel) sizeSel.addEventListener("change", () => {
    state.pageSize = parseInt(sizeSel.value, 10) || 20;
    state.page = 1;
    loadTab(container, state);
  });
}

// Một hóa đơn có thể được chuỗi trả LÀM NHIỀU LẦN (Co.op tách 8 kỳ trong một file,
// LOTTE 2 ngày thanh toán). Liệt kê từng lần chứ không gộp — gộp là mất dấu vết
// và kế toán không biết tiền về từ bảng kê nào.
function paymentCell(r, canManage) {
  const lines = r.payments || [];
  if (!lines.length) return html`<span class="kt-sub">chưa có bảng kê nào</span>`;
  return html`<div style="display:flex;flex-direction:column;gap:4px">
    ${lines.map((ln) => html`<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <span class="kt-badge kt-badge--${STATUS_TONE[ln.status] || "gray"}">${ln.chain || "—"}</span>
      <span class="kt-sub">${formatDate(ln.payment_date)}${ln.advice_no ? " · " + ln.advice_no : ""}</span>
      <b>${formatVND(Math.abs(ln.total_amount || 0))}</b>
      ${ln.match_confidence && ln.match_confidence !== "Chắc chắn"
        ? html`<span class="kt-badge kt-badge--${CONF_TONE[ln.match_confidence] || "gray"}">${ln.match_confidence}</span>`
        : ""}
      <a class="kt-btn-icon" target="_blank" title="Mở bảng kê"
        href="/desk/mt-payment-advice/${q(ln.advice)}"><i class="fas fa-up-right-from-square"></i></a>
      ${canManage
        ? html`<button class="kt-btn-icon" data-relink="${ln.line}" data-si="${r.name}"
            title="Chốt tay / gỡ liên kết dòng này"><i class="fas fa-link"></i></button>`
        : ""}
    </div>`)}
  </div>`;
}


// ── Tab 2: Quản lý chiết khấu (dòng khấu trừ, KHÔNG phải hóa đơn) ───────────
function deductionTable(state, res) {
  return html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <label class="kt-label" style="margin:0">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${chainOptionHTML(state, state.chain)}
      </select>
      <span class="kt-sub">
        Đây là các khoản chuỗi <b>trừ lại</b> khi thanh toán. Chúng KHÔNG được nối vào hóa đơn bán ra —
        dòng chiết khấu của Central Retail có mang ký hiệu hóa đơn của chính mình nhưng không phải
        thanh toán cho hóa đơn đó.
      </span>
    </div></div>

    <div class="kt-card"><div class="kt-card-body">
      ${!res.rows.length
        ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có khoản khấu trừ nào trong khoảng này.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Ngày TT</th><th>Chuỗi</th><th>Loại</th><th>Siêu thị</th>
              <th>Số chứng từ</th><th>Diễn giải</th>
              <th class="num">Trước thuế</th><th class="num">Thuế</th><th class="num">Số tiền</th>
              <th>Bảng kê</th>
            </tr></thead>
            <tbody>${res.rows.map((r) => html`<tr>
              <td>${formatDate(r.payment_date)}</td>
              <td>${r.chain || "—"}</td>
              <td><span class="kt-badge kt-badge--${KIND_TONE[r.row_kind] || "gray"}">${r.row_kind || "—"}</span></td>
              <td class="kt-cell-wrap">${r.store_name || r.store_code || "—"}</td>
              <td>${r.doc_no || "—"}</td>
              <td class="kt-cell-wrap">${r.description || "—"}</td>
              <td class="num">${r.amount_before_vat == null ? html`<span class="kt-sub">—</span>` : formatVND(r.amount_before_vat)}</td>
              <td class="num">${r.vat_amount == null ? html`<span class="kt-sub">—</span>` : formatVND(r.vat_amount)}</td>
              <td class="num"><b>${formatVND(r.total_amount)}</b></td>
              <td><a target="_blank" href="/desk/mt-payment-advice/${q(r.advice)}">${r.advice_no || r.advice}</a>
                ${r.status ? html` <span class="kt-badge kt-badge--${STATUS_TONE[r.status] || "gray"}">${r.status}</span>` : ""}</td>
            </tr>`)}</tbody>
          </table></div>
          <div class="kt-sub" style="margin-top:8px">
            Cột "Trước thuế" và "Thuế" để trống khi file của chuỗi chỉ có MỘT cột tiền —
            hệ thống không chia 1,1 hay 1,08 để suy ra, vì đó là bịa số.
          </div>
          ${pager(res, "dòng khấu trừ")}`}
    </div></div>`;
}

// Ô chọn chuỗi CHỈ có nghĩa ở màn hình liên chuỗi. Trong bàn làm việc của một
// chuỗi, chuỗi đã cố định bởi điều hướng — để ô này ở đó thì người dùng đổi
// chuỗi trong ô mà tiêu đề màn hình vẫn ghi chuỗi cũ, hai chỗ nói hai đằng.
function bindChainFilter(container, state) {
  const sel = container.querySelector("#mt-chain");
  if (!sel) return;
  if (state.view === "chuoi") {
    const wrap = sel.closest("label") || sel;
    wrap.style.display = "none";
    return;
  }
  sel.addEventListener("change", () => {
    state.chain = sel.value;
    state.page = 1;
    loadTab(container, state);
  });
}

// ── Tab 3: Công nợ chung của chuỗi ─────────────────────────────────────────
async function loadChains(container, state) {
  if (state.chainView === "khach") return loadCustomers(container, state);
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtChainSummary({ from_date: state.from, to_date: state.to });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const chains = res.chains || [];
  const t = res.totals || {};

  setHTML(body, html`
    ${(res.ambiguous_customers || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">
            <i class="fas fa-triangle-exclamation"></i>
            ${res.ambiguous_customers.length} khách hàng đang bị gán cho NHIỀU chuỗi
          </b>
          <div class="kt-sub" style="margin-top:6px">
            Hệ thống không tự chọn giùm — công nợ của những khách này rơi vào nhóm "Chưa gán chuỗi".
            Sửa trường Khách hàng trên các bảng kê tương ứng cho thống nhất.
          </div>
          <div class="kt-table-wrap" style="margin-top:8px"><table class="kt-table">
            <tbody>${res.ambiguous_customers.map((x) => html`<tr>
              <td><a target="_blank" href="/desk/customer/${q(x.customer)}">${x.customer}</a></td>
              <td>${(x.chains || []).map((c) => html`<span class="kt-badge kt-badge--yellow">${c}</span> `)}</td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`
      : ""}

    <div class="kt-card"><div class="kt-card-body">
      ${!chains.length
        ? html`<div class="kt-empty"><i class="fas fa-store-slash"></i><p>Chưa có phát sinh nào của kênh MT trong khoảng này.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Chuỗi</th><th class="num">Hóa đơn</th>
              <th class="num">Đã xuất</th><th class="num">Trả hàng</th>
              <th class="num">Đã thu</th><th class="num">Còn lại</th>
              <th class="num">Tiền hàng trong kỳ</th><th class="num">Chiết khấu</th>
              <th class="num">Phí</th><th class="num">Khác</th>
              <th class="num">Thực nhận</th><th class="num">Dòng bảng kê</th>
            </tr></thead>
            <tbody>
              ${chains.map((c) => html`<tr>
                <td><b>${c.chain}</b>
                  ${(c.customers || []).length
                    ? html`<div class="kt-sub">${c.customers.length} khách hàng</div>`
                    : ""}</td>
                <td class="num">${c.invoice_count}${c.unpaid_count
                  ? html` <span class="kt-badge kt-badge--yellow">${c.unpaid_count} chưa đủ</span>`
                  : ""}</td>
                <td class="num">${formatVND(c.invoiced)}</td>
                <td class="num">${c.returns ? formatVND(c.returns) : html`<span class="kt-sub">—</span>`}</td>
                <td class="num">${formatVND(c.collected)}</td>
                <td class="num"><b>${formatVND(c.outstanding)}</b></td>
                <td class="num">${formatVND(c.received_in_period)}</td>
                <td class="num">${formatVND(c.discount)}</td>
                <td class="num">${formatVND(c.fee)}</td>
                <td class="num">${formatVND(c.other)}</td>
                <td class="num"><b>${formatVND(c.net_received_est)}</b></td>
                <td class="num">${c.advice_lines}</td>
              </tr>`)}
              <tr>
                <td><b>TỔNG</b></td>
                <td class="num"><b>${t.invoice_count || 0}</b></td>
                <td class="num"><b>${formatVND(t.invoiced)}</b></td>
                <td class="num"><b>${formatVND(t.returns)}</b></td>
                <td class="num"><b>${formatVND(t.collected)}</b></td>
                <td class="num"><b>${formatVND(t.outstanding)}</b></td>
                <td class="num"><b>${formatVND(t.received_in_period)}</b></td>
                <td class="num"><b>${formatVND(t.discount)}</b></td>
                <td class="num"><b>${formatVND(t.fee)}</b></td>
                <td class="num"><b>${formatVND(t.other)}</b></td>
                <td class="num"><b>${formatVND(t.net_received_est)}</b></td>
                <td class="num"><b>${t.advice_lines || 0}</b></td>
              </tr>
            </tbody>
          </table></div>
          <div class="kt-sub" style="margin-top:8px">
            <b>Hai trục thời gian khác nhau, cố ý không gộp:</b>
            "Đã xuất / Đã thu / Còn lại" tính theo hóa đơn <b>ghi sổ trong kỳ</b> (tiền của chúng thu lúc nào cũng tính) —
            đó là công nợ. Bốn cột sau tính theo <b>ngày thanh toán của bảng kê</b> — đó là dòng tiền.
            Cộng hai nhóm vào nhau sẽ ra con số không có nghĩa kế toán nào.
            <br><b>"Tiền hàng trong kỳ" là tổng GỘP các dòng hóa đơn, chưa trừ gì.</b>
            Cột <b>"Thực nhận"</b> mới là số xấp xỉ khớp được với sao kê ngân hàng:
            tiền hàng trừ chiết khấu, phí và các khoản ghi giảm. Đọc nhầm hai cột này là
            lệch đúng bằng phần chuỗi đã trừ lại (với Co.op tháng mẫu là hơn 2,2 tỉ đồng).
          </div>`}
    </div></div>`);
}

// ── Chốt tay liên kết dòng bảng kê ↔ hóa đơn ───────────────────────────────
function bindRelink(container, state) {
  container.querySelectorAll("button[data-relink]").forEach((btn) => {
    btn.addEventListener("click", () => openRelinkModal(container, state, btn.dataset.relink, btn.dataset.si));
  });
}

// `onDone` cho người gọi tự quyết nạp lại CÁI GÌ. Mở từ bảng thì nạp lại bảng;
// mở từ trong modal đối soát thì nạp lại modal đó — nạp lại nền trong khi modal
// vẫn mở là sửa một màn hình người dùng không nhìn thấy, còn màn họ đang nhìn
// giữ nguyên số cũ.
function openRelinkModal(container, state, line, currentSI, onDone) {
  const modal = openModal({
    title: "Chốt tay liên kết dòng bảng kê",
    icon: "fa-link",
    maxWidth: 760,
    body: html`
      <p class="kt-sub">
        Dòng này đang nối với <b>${currentSI || "(chưa nối)"}</b>.
        Chỉ dòng loại <b>Thanh toán</b> mới được nối hóa đơn — dòng chiết khấu / phí bị backend chặn.
        Việc chốt tay chỉ đổi liên kết, <b>không</b> sinh chứng từ kế toán nào.
      </p>
      <label class="kt-label">Tìm hóa đơn ERPNext</label>
      <input class="kt-input" id="mr-search" placeholder="Số hóa đơn hoặc tên khách…" autocomplete="off">
      <div id="mr-results" style="max-height:260px;overflow:auto;margin-top:8px"></div>
      <label class="kt-label" style="margin-top:12px">Ghi chú (lý do chốt tay)</label>
      <input class="kt-input" id="mr-note" placeholder="vd: khớp theo bảng đối chiếu chuỗi ngày…">
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:12px">
        <button class="kt-btn kt-btn--outline" id="mr-unlink"><i class="fas fa-link-slash"></i> Gỡ liên kết</button>
      </div>
    `,
  });

  const note = () => modal.body.querySelector("#mr-note").value.trim();

  const apply = async (si, btn) => {
    if (btn) btn.disabled = true;
    try {
      await api.mtRelinkLine(line, si || null, note());
      toast(si ? "Đã chốt liên kết" : "Đã gỡ liên kết", "success");
      // Nối/gỡ đổi đúng những con số hàng đợi đang đếm. Quên chỗ này thì thanh
      // trên đầu giữ số của lúc mở màn, và nó là con số người ta tin nhất.
      invalidateWorklist(state);
      modal.close();
      if (onDone) onDone(); else loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      if (btn) btn.disabled = false;
    }
  };

  modal.body.querySelector("#mr-unlink").addEventListener("click", (e) => apply(null, e.currentTarget));

  const box = modal.body.querySelector("#mr-results");
  let timer = null;
  modal.body.querySelector("#mr-search").addEventListener("input", (e) => {
    const txt = e.target.value.trim();
    clearTimeout(timer);
    if (txt.length < 2) { setHTML(box, ""); return; }
    timer = setTimeout(async () => {
      setHTML(box, html`<div class="kt-sub">Đang tìm…</div>`);
      try {
        // Dùng chung API tìm hóa đơn của luồng MISA: cùng một tập Sales Invoice đã
        // ghi sổ, và kế toán MT có quyền gọi (guard_sales_any).
        const rows = await api.vatSearchInvoices(txt);
        if (!rows.length) { setHTML(box, html`<div class="kt-sub">Không tìm thấy.</div>`); return; }
        setHTML(box, html`<table class="kt-table"><tbody>${rows.map((r) => html`<tr>
          <td>${r.name}</td>
          <td>${formatDate(r.posting_date)}</td>
          <td class="kt-cell-wrap">${r.customer_name}</td>
          <td class="num">${formatVND(r.grand_total)}</td>
          <td>${r.inv_no ? html`<span class="kt-badge kt-badge--gray">HĐ ${r.inv_no}</span>` : ""}</td>
          <td class="num"><button class="kt-btn kt-btn--sm" data-pick="${r.name}">Chọn</button></td>
        </tr>`)}</tbody></table>`);
        box.querySelectorAll("button[data-pick]").forEach((b) => {
          b.addEventListener("click", () => apply(b.dataset.pick, b));
        });
      } catch (err) { setHTML(box, html`<div class="kt-sub">${err.message}</div>`); }
    }, 350);
  });
}

// ── Nạp bảng kê thanh toán của chuỗi ───────────────────────────────────────
// LUÔN xem trước rồi mới nạp. Mỗi chuỗi một khuôn file khác nhau, ba quy ước dấu
// khác nhau; nạp mù là ghi nhận sai loại dòng hoặc nhân đôi tiền mà không ai thấy.
function pickFile(container, state) {
  const input = document.createElement("input");
  input.type = "file";
  // `.pdf` vì WinCommerce gửi bảng kê thanh toán bằng PDF, và `read_sheets_any`
  // của `mt_advice_pdf` đọc thẳng nó từ MT2-W. Ô này thì không ai mở ra sửa,
  // nên suốt từ đó tới giờ hộp thoại chọn file LỌC MẤT đúng cái file duy nhất
  // chuỗi ấy gửi: cả tầng đọc PDF nằm đó mà không có đường nào bấm tới.
  //
  // Liệt kê cả `.PDF` viết hoa như `pickBkckFile`: backend nhận dạng bằng chữ
  // ký byte nên chữ hoa không sao, nhưng hộp thoại của trình duyệt thì so đuôi.
  input.accept = ".xlsx,.xls,.xlsm,.pdf,.PDF";
  input.onchange = () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => openAdviceModal(container, state, reader.result, file.name);
    reader.readAsDataURL(file);
  };
  input.click();
}

function openAdviceModal(container, state, content, filename) {
  const modal = openModal({
    title: "Nạp bảng kê thanh toán — " + filename,
    icon: "fa-file-import",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  // chain rỗng = để hệ thống tự nhận. Không nhận ra thì backend THROW chứ không
  // đoán bừa — chọn nhầm parser là đọc sai cột tiền mà kết quả vẫn trông hợp lý.
  showAdvicePreview(container, state, modal, content, filename, "");
}

async function showAdvicePreview(container, state, modal, content, filename, chain) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  let p;
  try {
    p = await api.mtAdvicePreview({ content, filename, chain: chain || undefined });
  } catch (e) {
    // Thường gặp nhất: không nhận ra chuỗi. Cho chọn tay rồi thử lại, KHÔNG tự đoán.
    setHTML(modal.body, html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
        <b style="color:var(--kt-danger)">Không đọc được file</b>
        <div class="kt-sub" style="margin-top:6px;white-space:pre-wrap">${e.message}</div>
      </div></div>
      <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div>
          <label class="kt-label">Chọn chuỗi rồi thử lại</label>
          <select class="kt-input kt-input--sm" id="ma-chain">
            <option value="">— tự nhận —</option>
            ${chainOptionHTML(state, chain)}
          </select>
        </div>
        <button class="kt-btn kt-btn--outline" id="ma-retry"><i class="fas fa-rotate"></i> Đọc lại</button>
      </div>`);
    modal.body.querySelector("#ma-retry").addEventListener("click", () => {
      showAdvicePreview(container, state, modal, content, filename,
        modal.body.querySelector("#ma-chain").value);
    });
    return;
  }

  const advices = p.advices || [];
  const g = p.grand_totals || {};
  const dup = p.duplicates || [];
  const problems = advices.flatMap((a) => (a.problems || []).map((x) => ({ ...x, _adv: a })));
  const badDeclared = advices.filter((a) => a.declared_diff != null && Math.abs(a.declared_diff) > 3);
  const totalLines = advices.reduce((s, a) => s + (a.line_count || 0), 0);
  const totalMatched = advices.reduce((s, a) => s + (a.matched || 0), 0);
  const totalPayLines = advices.reduce((s, a) => s + (a.payment_lines || 0), 0);
  const totalReview = advices.reduce((s, a) => s + (a.need_review || 0), 0);
  const totalUnknown = advices.reduce((s, a) => s + (a.unknown_kind || 0), 0);

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span>Chuỗi nhận ra: <b>${p.chain}</b></span>
      <span class="kt-badge kt-badge--gray">${p.advice_count} kỳ thanh toán trong file</span>
      ${p.skipped_rows ? html`<span class="kt-badge kt-badge--gray">${p.skipped_rows} dòng rác đã loại</span>` : ""}
      <span class="kt-sub" style="margin-left:auto">
        Một file có thể chứa NHIỀU kỳ (Co.op 8 kỳ, LOTTE 2 ngày) → mỗi kỳ thành một bản ghi riêng.
      </span>
    </div></div>

    ${dup.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-copy"></i> Bảng kê này đã được nạp rồi</b>
          <div class="kt-sub" style="margin-top:6px">
            ${dup.join(", ")} — nạp lại là <b>cộng đôi</b> tiền đã thu và mọi hóa đơn của kỳ đó
            lập tức trông như đã trả gấp đôi. Muốn nạp lại thì xóa bản cũ trước.
          </div>
        </div></div>`
      : ""}

    ${badDeclared.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-scale-unbalanced"></i>
            ${badDeclared.length} kỳ lệch số kiểm tra của chính file</b>
          <div class="kt-sub" style="margin-top:6px">
            Số kiểm tra do chuỗi in trong file là chân lý. Lệch ±1..3đ là do chuỗi làm tròn ở cấp
            dòng và cấp nhóm độc lập nhau (đã đo trên file Co.op thật) — chấp nhận được.
            Lệch lớn hơn nghĩa là đọc sót hoặc đọc thừa dòng tiền: <b>đừng nạp</b> cho tới khi làm rõ.
          </div>
        </div></div>`
      : ""}

    ${(p.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>Cảnh báo từ tầng đọc file</b>
          <ul class="kt-sub" style="margin:6px 0 0 18px">
            ${p.warnings.map((w) => html`<li>${w}</li>`)}
          </ul>
        </div></div>`
      : ""}

    ${riskBlocks(advices)}

    <div class="kt-stats kt-mb">
      <div class="kt-stat"><div class="kt-stat-label">Dòng đọc được</div>
        <div class="kt-stat-value">${totalLines}</div>
        <div class="kt-stat-sub">${totalPayLines} dòng thanh toán</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Khớp được hóa đơn</div>
        <div class="kt-stat-value ${totalMatched < totalPayLines ? "warn" : ""}">${totalMatched}/${totalPayLines}</div>
        <div class="kt-stat-sub">${totalReview} dòng cần review</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Tổng thanh toán</div>
        <div class="kt-stat-value">${formatVNDShort(g.total_payment)}</div>
        <div class="kt-stat-sub">${formatVND(g.total_payment)}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Chuỗi trừ lại</div>
        <div class="kt-stat-value">${formatVNDShort((g.total_discount || 0) + (g.total_fee || 0) + (g.total_other || 0))}</div>
        <div class="kt-stat-sub">CK ${formatVNDShort(g.total_discount)} · phí ${formatVNDShort(g.total_fee)} · khác ${formatVNDShort(g.total_other)}</div></div>
    </div>

    ${totalUnknown
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body kt-sub">
          <b>${totalUnknown} dòng máy không hiểu loại</b> — chúng được xếp vào "Khác" chứ không bị bỏ im lặng
          (bỏ im lặng là mất tiền khỏi tổng mà không ai thấy). Sau khi nạp phải phân loại tay.
        </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="font-weight:600;margin-bottom:6px">Từng kỳ thanh toán trong file — kiểm giúp trước khi nạp</div>
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr>
          <th>Ngày TT</th><th>Số chứng từ</th><th>Nguồn</th>
          <th class="num">Dòng</th><th class="num">Khớp</th><th class="num">Chưa khớp</th><th class="num">Cần review</th>
          <th class="num">Thanh toán</th><th class="num">Số kiểm tra</th><th class="num">Lệch</th><th>Trạng thái</th>
        </tr></thead>
        <tbody>${advices.map((a) => html`<tr>
          <td>${formatDate(a.payment_date)}</td>
          <td>${a.advice_no || "—"}</td>
          <td class="kt-sub">${a.source_sheet || "—"}</td>
          <td class="num">${a.line_count}</td>
          <td class="num">${a.matched}</td>
          <td class="num ${a.unmatched ? "warn" : ""}">${a.unmatched}</td>
          <td class="num ${a.need_review ? "warn" : ""}">${a.need_review}</td>
          <td class="num">${formatVND(a.totals ? a.totals.total_payment : 0)}</td>
          <td class="num">${a.declared_total_payment == null
            ? html`<span class="kt-sub">file không có</span>`
            : formatVND(a.declared_total_payment)}</td>
          <td class="num">${a.declared_diff == null
            ? html`<span class="kt-sub">—</span>`
            : (Math.abs(a.declared_diff) <= 3
                ? html`<span class="kt-badge kt-badge--green">${formatVND(a.declared_diff)}</span>`
                : html`<span class="kt-badge kt-badge--red">${formatVND(a.declared_diff)}</span>`)}</td>
          <td>${a.existing
            ? html`<span class="kt-badge kt-badge--red">đã nạp: ${a.existing}</span>`
            : html`<span class="kt-badge kt-badge--green">mới</span>`}
            ${(a.repeated_invoices || []).length
              ? html` <span class="kt-badge kt-badge--yellow">${a.repeated_invoices.length} HĐ bị nối nhiều dòng</span>`
              : ""}</td>
        </tr>`)}</tbody>
      </table></div>
    </div></div>

    ${problems.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>${problems.length} dòng thanh toán chưa nối được hóa đơn</b>
          <div class="kt-sub" style="margin:6px 0">
            Vẫn nạp được — tiền được ghi nhận, chỉ là chưa biết của hóa đơn nào. Sau khi nạp thì
            chốt tay ở tab "Quản lý thanh toán". Máy KHÔNG nối bừa: nối nhầm là đánh dấu đã trả
            cho hóa đơn của khách khác.
          </div>
          <details><summary class="kt-sub" style="cursor:pointer">Xem ${Math.min(problems.length, 50)} dòng đầu</summary>
            <div class="kt-table-wrap" style="max-height:260px;overflow:auto;margin-top:6px"><table class="kt-table">
              <thead><tr><th>Dòng</th><th>Ký hiệu</th><th>Số HĐ</th><th>Ngày HĐ</th>
                <th>Siêu thị</th><th class="num">Số tiền</th><th>Lý do</th></tr></thead>
              <tbody>${problems.slice(0, 50).map((x) => html`<tr>
                <td class="kt-sub">${x.source_row || "—"}</td>
                <td>${x.inv_series || "—"}</td>
                <td>${x.inv_no || "—"}</td>
                <td>${formatDate(x.inv_date)}</td>
                <td class="kt-cell-wrap">${x.store_name || x.store_code || "—"}</td>
                <td class="num">${formatVND(x.total_amount)}</td>
                <td><code>${x.match_method || "—"}</code></td>
              </tr>`)}</tbody>
            </table></div>
          </details>
        </div></div>`
      : ""}

    ${customerBlock(advices)}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <label class="kt-label">Khách hàng (áp cho MỌI kỳ trong file)</label>
      <select class="kt-input" id="ma-customer">
        <option value="">— dùng kết quả nhận diện ở trên —</option>
      </select>
      <div class="kt-sub" style="margin-top:6px">
        Chọn ở đây là <b>đè</b> kết quả tự nhận diện, áp cho <b>tất cả</b> các kỳ trong file.
        File nhiều kỳ thuộc nhiều pháp nhân (Co.op) thì <b>đừng</b> chọn: để máy nhận diện
        theo từng kỳ. Chọn xong thì <b>chuỗi của khách tự gán luôn</b> theo chuỗi của file —
        không phải vào đâu gán lại.
      </div>
      <label class="kt-label" style="margin-top:12px">Ghi chú</label>
      <input class="kt-input" id="ma-note" placeholder="vd: bảng kê chuỗi gửi qua email ngày…">
    </div></div>

    <div style="display:flex;gap:10px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
      ${!p.can_commit
        ? html`<span class="kt-sub">Chỉ kế toán trưởng mới được nạp.</span>`
        : ""}
      <button class="kt-btn kt-btn--outline" id="ma-cancel">Hủy</button>
      <button class="kt-btn" id="ma-go" ${(!p.can_commit || dup.length || !p.advice_count) ? "disabled" : ""}>
        <i class="fas fa-download"></i> Ghi nhận ${p.advice_count} bảng kê
      </button>
    </div>

    <div class="kt-sub" style="margin-top:8px;text-align:right">
      Ghi nhận = lưu bảng kê + đánh dấu. <b>Không</b> tạo Payment Entry / Journal Entry nào.
    </div>
  `);

  modal.body.querySelector("#ma-cancel").addEventListener("click", () => modal.close());
  fillCustomerSelect(modal, p);

  const go = modal.body.querySelector("#ma-go");
  if (go) go.addEventListener("click", async () => {
    if (!confirm(`Ghi nhận ${p.advice_count} bảng kê của chuỗi ${p.chain}? Hệ thống sẽ KHÔNG tự hạch toán.`)) return;
    go.disabled = true;
    go.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang ghi nhận…';
    try {
      const r = await api.mtAdviceCommit({
        content,
        filename,
        chain: p.chain,
        // Vân tay của ĐÚNG kế hoạch vừa hiện trên màn hình. Giữa lúc xem trước và
        // lúc bấm nạp, một hóa đơn mới ghi sổ có thể làm kết quả khớp đổi — backend
        // so vân tay, lệch một dòng cũng dừng và không ghi gì.
        expected_hash: p.plan_hash,
        customer: modal.body.querySelector("#ma-customer").value.trim() || undefined,
        note: modal.body.querySelector("#ma-note").value.trim() || undefined,
      });
      // Cảnh báo SAU KHI GHI là kênh duy nhất báo cho người nạp biết tiền vừa
      // được ghi vào hóa đơn của khách khác, hoặc chỉ mục hóa đơn bị cắt cụt.
      // Trước đây chúng bị vứt ngay: `toast(r.message)` rồi `location.reload()`
      // xóa sạch màn hình — kế toán chỉ thấy một dòng xanh "đã ghi nhận".
      const post = [...(r.warnings || []),
        ...(r.lines_on_other_customer || []).map(
          (x) => `Dòng ${x.source_row || "?"} · HĐ ${x.inv_series || ""} ${x.inv_no || ""} `
               + `đã nối vào ${x.sales_invoice || "?"} của khách ${x.si_customer_name || x.si_customer || "?"}`)];
      if (!post.length) {
        toast(r.message || `Đã ghi nhận ${r.advice_count} bảng kê`, "success");
        modal.close();
        location.reload();
        return;
      }
      // Có cảnh báo thì KHÔNG tự đóng và KHÔNG reload — bắt người đọc rồi tự đóng.
      setHTML(modal.body, html`
        <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-success)"><div class="kt-card-body">
          <b><i class="fas fa-circle-check"></i> ${r.message || `Đã ghi nhận ${r.advice_count} bảng kê`}</b>
        </div></div>
        <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">Đã ghi nhận NHƯNG có ${post.length} điểm cần kiểm ngay</b>
          <div class="kt-sub" style="margin:6px 0">
            Dữ liệu đã được ghi. Những dòng dưới đây có thể đã gán tiền sang hóa đơn của khách
            khác — mở bảng kê trên Desk để sửa liên kết nếu sai.
          </div>
          <ul class="kt-sub" style="margin:6px 0 0 18px">${post.map((w) => html`<li>${w}</li>`)}</ul>
        </div></div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <a class="kt-btn kt-btn--outline" target="_blank" href="/desk/mt-payment-advice">Mở trên Desk</a>
          <button class="kt-btn" id="ma-done">Tôi đã đọc</button>
        </div>`);
      modal.body.querySelector("#ma-done").addEventListener("click", () => {
        modal.close();
        location.reload();
      });
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
      go.innerHTML = "Thử lại";
    }
  });
}


// ── Ba lưới an toàn của màn xem trước ───────────────────────────────────────
// Backend dựng sẵn amount_mismatches / overpaid_invoices / cross_chain nhưng
// trước đây màn xem trước KHÔNG đọc tới, nên cảnh báo sinh ra rồi vứt ngay
// trong cùng một tick — kế toán chỉ thấy một dòng "khớp N/N" màu xanh.
//
// Đây đúng là ba chiều nối nhầm hóa đơn nguy hiểm nhất, và cả ba đều KHÔNG làm
// số kiểm tra của file lệch một đồng nào, nên không có lưới nào khác bắt được.
function riskRows(list, cols) {
  return html`<div class="kt-table-wrap" style="max-height:240px;overflow:auto;margin-top:6px">
    <table class="kt-table"><thead><tr>
      <th>Dòng</th><th>Hóa đơn trên bảng kê</th><th>Nối vào</th><th>Khách</th>
      ${cols.map((c) => html`<th class="num">${c.label}</th>`)}
    </tr></thead><tbody>
      ${list.map((x) => html`<tr>
        <td>${x.source_row || "—"}</td>
        <td>${x.inv_series || ""} <b>${x.inv_no || "—"}</b></td>
        <td>${x.sales_invoice
          ? html`<a target="_blank" href="/desk/sales-invoice/${encodeURIComponent(x.sales_invoice)}">${x.sales_invoice}</a>`
          : html`<span class="kt-sub">chưa nối</span>`}</td>
        <td class="kt-cell-wrap">${x.si_customer_name || x.si_customer || "—"}</td>
        ${cols.map((c) => html`<td class="num">${c.get(x)}</td>`)}
      </tr>`)}
    </tbody></table></div>`;
}

function riskBlocks(advices) {
  const gather = (k) => (advices || []).flatMap((a) => a[k] || []);
  const mism = gather("amount_mismatches");
  const over = gather("overpaid_invoices");
  const cross = gather("cross_chain");
  const trunc = (advices || []).some((a) => a.index_truncated);

  return html`
    ${trunc
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-scissors"></i> Chỉ mục hóa đơn bị cắt cụt</b>
          <div class="kt-sub" style="margin-top:6px">
            Số hóa đơn trong khoảng vượt trần tra cứu, nên một số dòng có thể KHÔNG khớp được
            dù hóa đơn có thật. Thu hẹp khoảng ngày rồi nạp lại — đừng kết luận "chưa xuất hóa đơn".
          </div>
        </div></div>`
      : ""}

    ${cross.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-shuffle"></i>
            ${cross.length} dòng nối vào hóa đơn của CHUỖI KHÁC hoặc hóa đơn đã hủy/đã thay thế</b>
          <div class="kt-sub" style="margin:6px 0">
            Mọi chuỗi dùng chung dải ký hiệu, nên đọc lệch một chữ số là tiền của chuỗi này
            được ghi vào hóa đơn của chuỗi kia — hai bên lệch công nợ ngược chiều nhau.
            Những dòng này đã bị hạ xuống <b>Cần review</b>, kiểm trước khi nạp.
          </div>
          ${riskRows(cross, [{ label: "Tiền", get: (x) => formatVND(x.total_amount) }])}
        </div></div>`
      : ""}

    ${over.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-arrow-up-right-dots"></i>
            ${over.length} hóa đơn bị trả VƯỢT giá trị</b>
          <div class="kt-sub" style="margin:6px 0">
            Tổng tiền phân bổ vào hóa đơn đã vượt giá trị của nó. Thường là nối nhầm, hoặc kỳ
            này đã được nạp ở một bản ghi khác rồi.
          </div>
          ${riskRows(over, [
            { label: "Đã trả trước", get: (x) => formatVND(x.paid_before) },
            { label: "Vượt", get: (x) => formatVND(x.over) }])}
        </div></div>`
      : ""}

    ${mism.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b><i class="fas fa-scale-unbalanced"></i> ${mism.length} dòng khớp được nhưng LỆCH tiền</b>
          <div class="kt-sub" style="margin:6px 0">
            Không chặn nạp — chuỗi có quyền trả từng phần, nhiều kỳ mới đủ. Nhưng lệch cũng là
            dấu hiệu nối nhầm hóa đơn, nên phải nhìn thấy.
          </div>
          ${riskRows(mism, [
            { label: "Bảng kê", get: (x) => formatVND(x.total_amount) },
            { label: "Hóa đơn", get: (x) => formatVND(x.si_grand_total) },
            { label: "Lệch", get: (x) => formatVND(x.diff) }])}
        </div></div>`
      : ""}
  `;
}


// ── Nhận diện khách hàng theo TỪNG KỲ ──────────────────────────────────────
// Không đọc mã trong file: cái bảng kê in ra là định danh của CHÍNH TA
// (LOTTE Vendor CD 007466, Emart VENDOR CODE 100968, Co.op Mã cung cấp 012556
// đều là Hoàng Giang). Máy suy từ SỔ CỦA MÌNH — hóa đơn nào khớp được thì
// Sales Invoice.customer chính là người đã mua.
const DET_TONE = {
  "Chắc chắn": "green",
  "Cần xác nhận": "yellow",
  "Nhiều khách": "red",
  "Không xác định": "gray",
};

const DET_WHY = {
  hoa_don_da_khop: "mọi hóa đơn khớp được đều của khách này",
  hoa_don_da_khop_ap_dao: "khách này chiếm phần lớn tiền của kỳ",
  nhieu_khach_trong_mot_ky: "kỳ này trả cho NHIỀU khách — máy không chọn hộ",
  lich_su_bang_ke_cua_chuoi: "suy từ các bảng kê trước của chuỗi, chưa có hóa đơn nào khớp",
  lich_su_chuoi_co_nhieu_khach: "chuỗi này trước giờ gán cho nhiều khách khác nhau",
  khong_co_can_cu: "không khớp được hóa đơn nào và chuỗi chưa có lịch sử",
};

function customerBlock(advices) {
  const list = advices || [];
  if (!list.length) return "";
  const sure = list.filter((a) => a.detected_confidence === "Chắc chắn").length;
  const bad = list.filter((a) => a.detected_confidence === "Nhiều khách"
                              || a.detected_confidence === "Không xác định");

  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${bad.length ? "warning" : "success"})">
      <div class="kt-card-body">
        <b><i class="fas fa-user-check"></i> Nhận diện khách hàng — ${sure}/${list.length} kỳ chắc chắn</b>
        <div class="kt-sub" style="margin:6px 0">
          Máy suy từ <b>hóa đơn đã khớp trong sổ của mình</b>, không đọc mã trong file:
          mã "nhà cung cấp" mà bảng kê in ra là mã của <b>chính công ty ta</b> bên hệ thống chuỗi,
          không phải mã khách. Chỉ kỳ nào <b>Chắc chắn</b> mới được điền tự động.
        </div>
        <div class="kt-table-wrap"><table class="kt-table">
          <thead><tr><th>Kỳ thanh toán</th><th>Khách hàng</th><th>Mức tin</th><th>Căn cứ</th></tr></thead>
          <tbody>${list.map((a) => html`<tr>
            <td>${formatDate(a.payment_date) || html`<span class="kt-sub">chưa rõ ngày</span>`}
              ${a.advice_no ? html`<div class="kt-sub">${a.advice_no}</div>` : ""}</td>
            <td>${a.detected_customer
              ? html`<b>${a.detected_customer}</b>${(a.customer_candidates || [])[0]
                  && (a.customer_candidates[0].customer_name)
                  ? html`<div class="kt-sub">${a.customer_candidates[0].customer_name}</div>` : ""}`
              : html`<span class="kt-sub">— sẽ để trống, sửa sau trên Desk —</span>`}</td>
            <td><span class="kt-badge kt-badge--${DET_TONE[a.detected_confidence] || "gray"}">
              ${a.detected_confidence || "?"}</span></td>
            <td class="kt-sub">${DET_WHY[a.detected_evidence] || a.detected_evidence || ""}
              ${(a.customer_candidates || []).length > 1
                ? html`<div>${a.customer_candidates.slice(0, 4).map((c) => html`
                    <span class="kt-badge kt-badge--gray">${c.customer} ${Math.round((c.share || 0) * 100)}%</span> `)}</div>`
                : ""}</td>
          </tr>`)}</tbody>
        </table></div>
        ${bad.length
          ? html`<div class="kt-sub" style="margin-top:8px">
              <b>${bad.length} kỳ máy không kết luận được.</b> Những kỳ đó sẽ được ghi nhận với
              khách hàng <b>để trống</b> — công nợ rơi vào nhóm "Chưa gán chuỗi" cho tới khi kế toán
              mở bảng kê trên Desk và điền. Máy cố ý không chọn đại: một kỳ trả cho nhiều pháp nhân
              (Co.op có 120 siêu thị thành viên) mà gán một khách là dồn công nợ sai chỗ.
            </div>`
          : ""}
      </div></div>`;
}


// ── Tab 3 (chế độ mặc định): công nợ chi tiết TRÊN ĐẦU TỪNG KHÁCH ──────────
// Cấp chuỗi chỉ để nhìn tổng. Đi đòi nợ thì phải theo pháp nhân — riêng Co.op
// có tới 120 siêu thị thành viên, con số cấp chuỗi không dùng được vào việc gì.
function viewSwitch(state) {
  const btn = (v, label, icon) => html`<button
    class="kt-btn kt-btn--sm ${state.chainView === v ? "" : "kt-btn--outline"}"
    data-view="${v}"><i class="fas ${icon}"></i> ${label}</button>`;
  return html`<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
    ${btn("khach", "Theo khách hàng", "fa-user")}
    ${btn("chuoi", "Theo chuỗi", "fa-store")}
  </div>`;
}

async function loadCustomers(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtCustomerSummary({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined, search: state.search || undefined,
      page: state.page,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];
  const t = res.totals || {};

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${viewSwitch(state)}
      <label class="kt-label" style="margin:0 0 0 8px">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${(res.chains || []).map((c) => html`<option value="${c}" ${state.chain === c ? "selected" : ""}>${c}</option>`)}
      </select>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-assign-chain">
        <i class="fas fa-diagram-project"></i> Sửa chuỗi của khách
      </button>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-stores">
        <i class="fas fa-store"></i> Điểm siêu thị
      </button>
      <input class="kt-input kt-input--sm" id="mt-cus-search" placeholder="Tìm khách hàng…"
             value="${state.search}" style="margin-left:auto;min-width:220px">
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-store-slash"></i><p>Chưa có phát sinh nào của kênh MT trong khoảng này.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Khách hàng</th><th>Chuỗi</th><th class="num">Hóa đơn</th>
              <th class="num">Đã xuất</th><th class="num">Trả hàng</th>
              <th class="num">Đã thu</th><th class="num">Còn lại</th>
              <th class="num">Tiền hàng trong kỳ</th><th class="num">Chiết khấu</th>
              <th class="num">Phí</th><th class="num">Khác</th>
              <th class="num">Thực nhận</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><b>${r.customer_name || r.customer}</b>
                  ${r.customer_name ? html`<div class="kt-sub">${r.customer}</div>` : ""}</td>
                <td>${r.chain === "Chưa gán chuỗi"
                  ? html`<span class="kt-badge kt-badge--yellow">${r.chain}</span>`
                  : html`<span class="kt-sub">${r.chain}</span>`}</td>
                <td class="num">${r.invoice_count}${r.unpaid_count
                  ? html` <span class="kt-badge kt-badge--yellow">${r.unpaid_count} chưa đủ</span>`
                  : ""}</td>
                <td class="num">${formatVND(r.invoiced)}</td>
                <td class="num">${r.returns ? formatVND(r.returns) : html`<span class="kt-sub">—</span>`}</td>
                <td class="num">${formatVND(r.collected)}</td>
                <td class="num"><b>${formatVND(r.outstanding)}</b></td>
                <td class="num">${formatVND(r.received_in_period)}</td>
                <td class="num">${formatVND(r.discount)}</td>
                <td class="num">${formatVND(r.fee)}</td>
                <td class="num">${formatVND(r.other)}</td>
                <td class="num"><b>${formatVND(r.net_received_est)}</b></td>
                <td class="num" style="white-space:nowrap">
                  ${r.customer && r.customer !== "Chưa gán khách"
                    ? html`<button class="kt-btn-icon" data-drill-inv="${r.customer}" data-drill-chain="${r.chain}"
                             title="Mở bàn làm việc của chuỗi, lọc sẵn khách này"><i class="fas fa-file-invoice"></i></button>
                           <button class="kt-btn-icon" data-drill-ded="${r.customer}" data-drill-chain="${r.chain}"
                             title="Xem khoản chuỗi trừ lại của khách này"><i class="fas fa-percent"></i></button>`
                    : ""}
                </td>
              </tr>`)}
              <tr>
                <td><b>TỔNG</b></td><td></td>
                <td class="num"><b>${t.invoice_count || 0}</b></td>
                <td class="num"><b>${formatVND(t.invoiced)}</b></td>
                <td class="num"><b>${formatVND(t.returns)}</b></td>
                <td class="num"><b>${formatVND(t.collected)}</b></td>
                <td class="num"><b>${formatVND(t.outstanding)}</b></td>
                <td class="num"><b>${formatVND(t.received_in_period)}</b></td>
                <td class="num"><b>${formatVND(t.discount)}</b></td>
                <td class="num"><b>${formatVND(t.fee)}</b></td>
                <td class="num"><b>${formatVND(t.other)}</b></td>
                <td class="num"><b>${formatVND(t.net_received_est)}</b></td>
                <td></td>
              </tr>
            </tbody>
          </table></div>
          ${pager(res, "khách hàng")}
          <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  bindViewSwitch(container, state);
  bindDrill(container, state);
  const asg = container.querySelector("#mt-assign-chain");
  if (asg) asg.addEventListener("click", () => openChainAssign(container, state));
  const stores = container.querySelector("#mt-stores");
  if (stores) stores.addEventListener("click", () => openStores(container, state));

  const box = container.querySelector("#mt-cus-search");
  if (box) {
    let timer = null;
    box.addEventListener("input", (e) => {
      state.search = e.target.value.trim();
      state.page = 1;
      clearTimeout(timer);
      timer = setTimeout(() => loadTab(container, state), 350);
    });
  }
}

function bindViewSwitch(container, state) {
  container.querySelectorAll("button[data-view]").forEach((b) => {
    b.addEventListener("click", () => {
      if (state.chainView === b.dataset.view) return;
      state.chainView = b.dataset.view;
      state.page = 1;
      loadTab(container, state);
    });
  });
}

// Bấm từ dòng khách sang đúng danh sách của khách đó — đây là thao tác chính
// khi đối chiếu: nhìn số tổng thấy lệch thì mở ngay chi tiết của khách đó.
function bindDrill(container, state) {
  // Bấm từ dòng khách -> vào BÀN LÀM VIỆC CỦA CHUỖI chứa khách đó, mở bước
  // "Đối soát thanh toán", lọc sẵn khách. Hai nút chỉ khác nhau ở RỔ.
  //
  // Phải mang theo CHUỖI: màn hình này chạy được ở cả tầng liên chuỗi. Chỉ đổi
  // `state.step` mà không đổi tầng thì `loadTab` vẫn rẽ vào nhánh liên chuỗi và
  // cú bấm không có tác dụng gì — im lặng.
  const go = (bucket, btn, customer) => {
    const chain = btn.dataset.drillChain;
    state.customer = customer;
    state.bucket = bucket;
    state.step = "thanh-toan";
    state.page = 1;
    state.search = "";
    const known = chain && (state.chainOptions || []).includes(chain);
    if (known) {
      state.view = "chuoi";
      state.chain = chain;
      syncHash(state);
      return paint(container, state);
    }
    // Khách CHƯA GÁN CHUỖI thì không có bàn làm việc nào để mở. Nói ra thay vì
    // để cú bấm không có tác dụng gì.
    if (state.view !== "chuoi") {
      state.customer = "";
      toast("Khách này chưa được gán chuỗi siêu thị — gán chuỗi rồi mới mở được "
            + "bàn làm việc. Dùng nút 'Gán chuỗi cho khách' ở trang chuỗi.", "error");
      return;
    }
    return loadTab(container, state);
  };
  container.querySelectorAll("button[data-drill-inv]").forEach((b) =>
    b.addEventListener("click", () => go("tat_ca", b, b.dataset.drillInv)));
  container.querySelectorAll("button[data-drill-ded]").forEach((b) =>
    b.addEventListener("click", () => go("chiet_khau", b, b.dataset.drillDed)));
}


// Thanh báo "đang xem của riêng khách X". Lọc mà không hiện là nguy hiểm: kế
// toán nhìn một danh sách đã bị lọc rồi tưởng đó là toàn bộ kênh MT.
function customerFilterBar(state) {
  if (!state.customer) return "";
  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
      <div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <i class="fas fa-filter"></i>
        <span>Đang lọc theo khách hàng <b>${state.customer}</b> — danh sách dưới đây
          <b>không phải</b> toàn bộ kênh MT.</span>
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-clear-cus" style="margin-left:auto">
          <i class="fas fa-xmark"></i> Bỏ lọc
        </button>
      </div></div>`;
}

function bindCustomerFilter(container, state) {
  const btn = container.querySelector("#mt-clear-cus");
  if (!btn) return;
  btn.addEventListener("click", () => {
    state.customer = "";
    state.page = 1;
    loadTab(container, state);
  });
}


// ── Gán chuỗi cho khách hàng ───────────────────────────────────────────────
// Đây là chỗ gán CHÍNH THỨC. Trước đó chuỗi chỉ suy được từ bảng kê đã nạp —
// vòng luẩn quẩn: khách mới ký hợp đồng, chưa có đồng thanh toán nào, thì không
// gán được; mà không gán thì công nợ của họ rơi vào rổ "Chưa gán chuỗi".
async function openChainAssign(container, state) {
  const modal = openModal({
    title: "Gán chuỗi siêu thị cho khách hàng",
    icon: "fa-diagram-project",
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderChainAssign(container, state, modal, 1);
}

async function renderChainAssign(container, state, modal, onlyUnassigned) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtChainAssignment({ only_unassigned: onlyUnassigned ? 1 : 0 });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(modal.body, html`
    ${!res.has_field
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">Site chưa có field gán chuỗi.</b>
          <div class="kt-sub">Quản trị chạy <code>bench --site TÊN_SITE migrate</code> rồi mở lại.</div>
        </div></div>`
      : ""}

    <p class="kt-sub">
      <b>Bình thường không cần vào đây.</b> Nạp bảng kê và chọn khách là chuỗi tự gán theo
      chuỗi của file. Màn này chỉ để <b>sửa</b> khi gán sai, khi khách đổi chuỗi, hoặc khi
      muốn gán trước cho khách mới ký hợp đồng mà chưa có bảng kê nào.
    </p>

    <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
      <label style="display:flex;gap:6px;align-items:center;cursor:pointer">
        <input type="checkbox" id="ca-only" ${onlyUnassigned ? "checked" : ""}>
        <span class="kt-sub">Chỉ hiện khách chưa chốt</span>
      </label>
      <span class="kt-sub" style="margin-left:auto">${rows.length} khách</span>
    </div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i>
          <p>Mọi khách hàng kênh MT đều đã được gán chuỗi.</p></div>`
      : html`<div class="kt-table-wrap" style="max-height:420px;overflow:auto">
          <table class="kt-table">
            <thead><tr><th>Khách hàng</th><th>Nguồn</th><th>Chuỗi</th></tr></thead>
            <tbody>${rows.map((r) => html`<tr>
              <td><b>${r.customer_name || r.customer}</b>
                ${r.customer_name ? html`<div class="kt-sub">${r.customer}</div>` : ""}</td>
              <td>${r.source === "khai_bao"
                ? html`<span class="kt-badge kt-badge--green">đã chốt</span>`
                : r.source === "suy_tu_bang_ke"
                  ? html`<span class="kt-badge kt-badge--yellow">máy suy từ bảng kê</span>`
                  : html`<span class="kt-badge kt-badge--gray">chưa gán</span>`}</td>
              <td><select class="kt-input kt-input--sm" data-assign="${r.customer}"
                    ${res.can_assign && res.has_field ? "" : "disabled"}>
                <option value="">— chưa gán —</option>
                ${(res.chains || []).map((c) => html`<option value="${c}" ${r.chain === c ? "selected" : ""}>${c}</option>`)}
              </select></td>
            </tr>`)}</tbody>
          </table></div>`}

    <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    ${!res.can_assign
      ? html`<div class="kt-sub" style="margin-top:6px">Chỉ kế toán trưởng mới được gán.</div>`
      : ""}
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:12px">
      <button class="kt-btn kt-btn--outline" id="ca-close">Đóng</button>
    </div>
  `);

  modal.body.querySelector("#ca-close").addEventListener("click", () => {
    modal.close();
    loadTab(container, state);   // số liệu đổi theo chuỗi vừa gán
  });
  modal.body.querySelector("#ca-only").addEventListener("change", (e) =>
    renderChainAssign(container, state, modal, e.target.checked ? 1 : 0));

  modal.body.querySelectorAll("select[data-assign]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const prev = sel.dataset.prev || "";
      sel.disabled = true;
      try {
        const r = await api.mtSetCustomerChain(sel.dataset.assign, sel.value || undefined);
        toast(r.message, "success");
        sel.dataset.prev = sel.value;
        const cell = sel.closest("tr").querySelector("td:nth-child(2)");
        if (cell) setHTML(cell, sel.value
          ? html`<span class="kt-badge kt-badge--green">đã chốt</span>`
          : html`<span class="kt-badge kt-badge--gray">chưa gán</span>`);
      } catch (e) {
        toast(e.message, "error");
        sel.value = prev;   // trả về giá trị cũ, đừng để màn hình nói dối
      }
      sel.disabled = false;
    });
  });
}


// Đổ danh sách khách kênh MT vào ô chọn của màn nạp bảng kê.
//
// Trước đây chỗ này là ô gõ mã trần ("CUS-0001") — bắt kế toán thuộc lòng mã
// khách, mà không ai thuộc. Danh sách nạp sau khi khung đã hiện: chậm mạng thì
// cùng lắm ô chọn trống một nhịp, không chặn cả màn xem trước.
async function fillCustomerSelect(modal, p) {
  const sel = modal.body.querySelector("#ma-customer");
  if (!sel) return;
  let res;
  try {
    res = await api.mtCustomers({ chain: p.chain || undefined });
  } catch (_) {
    return;   // giữ nguyên "dùng kết quả nhận diện" — vẫn nạp được
  }
  const rows = res.rows || [];
  if (!rows.length) return;

  // Khách đã thuộc đúng chuỗi của file lên nhóm trên, còn lại nhóm dưới — chọn
  // nhầm sang khách của chuỗi khác là ghi tiền sai chỗ.
  const same = rows.filter((r) => r.same_chain);
  const other = rows.filter((r) => !r.same_chain);
  const opt = (r) => html`<option value="${r.customer}">${r.customer_name || r.customer}${
    r.chain ? ` · ${r.chain}` : " · chưa gán chuỗi"}</option>`;

  setHTML(sel, html`
    <option value="">— dùng kết quả nhận diện ở trên —</option>
    ${same.length ? html`<optgroup label="Thuộc chuỗi ${p.chain}">${same.map(opt)}</optgroup>` : ""}
    ${other.length ? html`<optgroup label="${same.length ? "Khách khác của kênh MT" : "Khách kênh MT"}">
      ${other.map(opt)}</optgroup>` : ""}
  `);
}


// ── Điểm siêu thị (master) ─────────────────────────────────────────────────
//
// VÌ SAO cần màn hình riêng: mã điểm trên bảng kê chỉ là một chuỗi ký tự, còn
// cái kế toán thật sự cần là "điểm này thuộc PHÁP NHÂN nào" (đi đòi nợ theo pháp
// nhân, không theo chuỗi — riêng Co.op có ~120 siêu thị thành viên) và "xuất hóa
// đơn cho điểm này thì lấy địa chỉ/MST ở đâu".
//
// Điểm được DỰNG TỪ CÁC BẢNG KÊ ĐÃ NẠP, không từ file mẫu: file mẫu là ảnh chụp
// một kỳ, còn site luôn mới hơn.

const STORE_STATUS_TONE = { moi: "green", da_co: "gray", lech: "yellow" };

async function openStores(container, state) {
  const modal = openModal({
    title: "Điểm siêu thị",
    icon: "fa-store",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  const st = { chain: state.chain || "", search: "", page: 1, active: "" };
  await renderStores(container, state, modal, st);
}

async function renderStores(container, state, modal, st) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtStores({ chain: st.chain || undefined, search: st.search || undefined,
                               active: st.active === "" ? undefined : st.active,
                               page: st.page, page_size: 50 });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <label class="kt-label" style="margin:0">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="ms-chain">
        <option value="">Tất cả</option>
        ${(res.chains || []).map((c) => html`<option value="${c}" ${st.chain === c ? "selected" : ""}>${c}</option>`)}
      </select>
      <select class="kt-input kt-input--sm" id="ms-active">
        <option value="" ${st.active === "" ? "selected" : ""}>Mọi trạng thái</option>
        <option value="1" ${st.active === "1" ? "selected" : ""}>Đang hoạt động</option>
        <option value="0" ${st.active === "0" ? "selected" : ""}>Đã đóng</option>
      </select>
      <input class="kt-input kt-input--sm" id="ms-search" placeholder="Tìm mã / tên điểm / khách…"
             value="${st.search}" style="min-width:220px">
      ${state.canManage
        ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="ms-seed" style="margin-left:auto">
            <i class="fas fa-wand-magic-sparkles"></i> Dựng từ bảng kê đã nạp
          </button>`
        : ""}
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-store-slash"></i>
          <p>Chưa có điểm siêu thị nào${st.search || st.chain ? " khớp bộ lọc" : ""}.</p>
          ${state.canManage && !st.search && !st.chain
            ? html`<div class="kt-sub">Bấm <b>Dựng từ bảng kê đã nạp</b> để hệ thống lấy mã điểm
                từ các bảng kê đã có trên site. Chuỗi chưa nạp bảng kê nào thì chưa dựng được điểm nào.</div>`
            : ""}
        </div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Chuỗi</th><th>Mã điểm</th><th>Tên điểm</th><th>Khách hàng</th>
              <th>Địa chỉ xuất HĐ</th><th>Mã NCC</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><span class="kt-badge kt-badge--gray">${r.chain}</span></td>
                <td><code>${r.store_code}</code></td>
                <td>${r.store_name}
                  ${!r.active ? html` <span class="kt-badge kt-badge--red">đã đóng</span>` : ""}</td>
                <td>${r.customer
                  ? html`${r.customer_name || r.customer}`
                  : html`<span class="kt-badge kt-badge--yellow">chưa gán pháp nhân</span>`}</td>
                <td class="kt-sub">${r.address || "—"}</td>
                <td class="kt-sub">${r.vendor_code || "—"}</td>
                <td>${state.canManage
                  ? html`<button class="kt-btn kt-btn--outline kt-btn--sm ms-edit" data-name="${r.name}">
                      <i class="fas fa-pen"></i></button>`
                  : ""}</td>
              </tr>`)}
            </tbody>
          </table></div>
          ${storePager(res)}
          <div class="kt-sub" style="margin-top:8px">
            Điểm <b>chưa gán pháp nhân</b> vẫn hiện công nợ theo chuỗi, nhưng không đi đòi nợ
            theo pháp nhân được và không xuất được bảng kê chiết khấu có MST người mua.
          </div>
        </div></div>`}
  `);

  const rerender = () => renderStores(container, state, modal, st);
  const ch = modal.body.querySelector("#ms-chain");
  if (ch) ch.addEventListener("change", (e) => { st.chain = e.target.value; st.page = 1; rerender(); });
  const ac = modal.body.querySelector("#ms-active");
  if (ac) ac.addEventListener("change", (e) => { st.active = e.target.value; st.page = 1; rerender(); });
  const sb = modal.body.querySelector("#ms-search");
  if (sb) {
    let timer = null;
    sb.addEventListener("input", (e) => {
      st.search = e.target.value.trim();
      st.page = 1;
      clearTimeout(timer);
      timer = setTimeout(rerender, 350);
    });
  }
  modal.body.querySelectorAll(".ms-page").forEach((b) => {
    b.addEventListener("click", () => { st.page = Number(b.dataset.page); rerender(); });
  });
  modal.body.querySelectorAll(".ms-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const row = rows.find((r) => r.name === b.dataset.name);
      if (row) openStoreEdit(container, state, modal, st, row);
    });
  });
  const seed = modal.body.querySelector("#ms-seed");
  if (seed) seed.addEventListener("click", () => openStoreSeed(container, state, modal, st));
}

function storePager(res) {
  if (!res || (res.pages || 1) <= 1) return "";
  const p = res.page || 1;
  return html`
    <div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:10px">
      <span class="kt-sub">${res.total} điểm · trang ${p}/${res.pages}</span>
      <button class="kt-btn kt-btn--outline kt-btn--sm ms-page" data-page="${p - 1}"
              ${p <= 1 ? "disabled" : ""}><i class="fas fa-chevron-left"></i></button>
      <button class="kt-btn kt-btn--outline kt-btn--sm ms-page" data-page="${p + 1}"
              ${p >= res.pages ? "disabled" : ""}><i class="fas fa-chevron-right"></i></button>
    </div>`;
}

// ── Sửa một điểm ───────────────────────────────────────────────────────────
async function openStoreEdit(container, state, parent, st, row) {
  const modal = openModal({
    title: `${row.chain} · ${row.store_code}`,
    icon: "fa-pen",
    maxWidth: 620,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let customers = [];
  try {
    customers = (await api.mtCustomers({ chain: row.chain })).rows || [];
  } catch (_) { /* vẫn sửa được các field khác */ }

  setHTML(modal.body, html`
    <div style="display:grid;gap:12px">
      <div>
        <label class="kt-label">Tên điểm</label>
        <input class="kt-input" id="se-name" value="${row.store_name || ""}">
      </div>
      <div>
        <label class="kt-label">Khách hàng (pháp nhân xuất hóa đơn)</label>
        <select class="kt-input" id="se-customer">
          <option value="">— chưa gán —</option>
          ${customers.map((c) => html`<option value="${c.customer}" ${row.customer === c.customer ? "selected" : ""}>${
            c.customer_name || c.customer}${c.chain ? ` · ${c.chain}` : ""}</option>`)}
        </select>
        <div class="kt-sub" style="margin-top:4px">
          Gán sai pháp nhân là cả kỳ công nợ chạy sang khách khác — và không tổng nào phát hiện ra.
        </div>
      </div>
      <div>
        <label class="kt-label">Địa chỉ xuất hóa đơn</label>
        <select class="kt-input" id="se-address">
          <option value="">— chưa gán —</option>
          ${row.address ? html`<option value="${row.address}" selected>${row.address}</option>` : ""}
        </select>
        <div class="kt-sub" style="margin-top:4px">
          Chỉ liệt kê địa chỉ của đúng khách đã chọn. Dùng địa chỉ của pháp nhân khác là
          in hóa đơn sai MST người mua.
        </div>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <div style="flex:1;min-width:180px">
          <label class="kt-label">MST riêng của điểm</label>
          <input class="kt-input" id="se-tax" value="${row.tax_id || ""}"
                 placeholder="để trống nếu dùng MST của địa chỉ">
        </div>
        <div style="flex:1;min-width:180px">
          <label class="kt-label">Mã NCC của mình tại chuỗi</label>
          <input class="kt-input" id="se-vendor" value="${row.vendor_code || ""}">
        </div>
      </div>
      <label style="display:flex;gap:8px;align-items:center">
        <input type="checkbox" id="se-active" ${row.active ? "checked" : ""}>
        <span>Đang hoạt động</span>
      </label>
      <div>
        <label class="kt-label">Ghi chú</label>
        <textarea class="kt-input" id="se-note" rows="2">${row.note || ""}</textarea>
      </div>
      ${row.seeded_from ? html`<div class="kt-sub">Nguồn dựng: ${row.seeded_from}</div>` : ""}
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="kt-btn kt-btn--outline" id="se-cancel">Hủy</button>
        <button class="kt-btn kt-btn--primary" id="se-save"><i class="fas fa-check"></i> Lưu</button>
      </div>
      <div id="se-msg"></div>
    </div>`);

  const cusSel = modal.body.querySelector("#se-customer");
  const addrSel = modal.body.querySelector("#se-address");

  async function loadAddresses() {
    const cus = cusSel.value;
    if (!cus) {
      setHTML(addrSel, html`<option value="">— chọn khách hàng trước —</option>`);
      return;
    }
    let list = [];
    try { list = await api.mtStoreAddresses("", cus); } catch (_) { /* để trống */ }
    setHTML(addrSel, html`
      <option value="">— chưa gán —</option>
      ${list.map((a) => html`<option value="${a.name}" ${row.address === a.name ? "selected" : ""}>${
        a.address_title || a.name}${a.tax_id ? ` · MST ${a.tax_id}` : ""}</option>`)}`);
  }
  cusSel.addEventListener("change", loadAddresses);
  if (row.customer) await loadAddresses();

  modal.body.querySelector("#se-cancel").addEventListener("click", () => modal.close());
  modal.body.querySelector("#se-save").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#se-save");
    btn.disabled = true;
    try {
      await api.mtStoreSave({
        name: row.name,
        store_name: modal.body.querySelector("#se-name").value.trim(),
        // Gửi CHUỖI RỖNG (không phải null) khi muốn gỡ: backend hiểu rỗng là
        // "cố ý xóa", còn thiếu field là "giữ nguyên".
        customer: cusSel.value,
        address: addrSel.value,
        tax_id: modal.body.querySelector("#se-tax").value.trim(),
        vendor_code: modal.body.querySelector("#se-vendor").value.trim(),
        active: modal.body.querySelector("#se-active").checked ? 1 : 0,
        note: modal.body.querySelector("#se-note").value,
      });
      toast("Đã lưu điểm " + row.store_code, "success");
      modal.close();
      await renderStores(container, state, parent, st);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#se-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <div class="kt-sub" style="white-space:pre-wrap">${e.message}</div>
        </div></div>`);
    }
  });
}

// ── Dựng master từ bảng kê đã nạp ──────────────────────────────────────────
//
// XEM TRƯỚC LÀ BẮT BUỘC. Điểm dựng bằng suy luận (Central Retail không in mã nên
// mã do hệ thống sinh từ tên; địa chỉ dò theo cụm trong ngoặc cuối), nên người
// phải nhìn trước khi ghi master. Backend đòi vân tay của đúng bản vừa xem.
async function openStoreSeed(container, state, parent, st) {
  const modal = openModal({
    title: "Dựng điểm siêu thị từ bảng kê đã nạp",
    icon: "fa-wand-magic-sparkles",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let res;
  try {
    res = await api.mtStoreSeedPreview({});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const s = res.summary || {};
  const stores = res.stores || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="kt-badge kt-badge--green">${s.moi || 0} sẽ tạo mới</span>
        <span class="kt-badge kt-badge--gray">${s.da_co || 0} đã có — bỏ qua</span>
        ${s.lech ? html`<span class="kt-badge kt-badge--yellow">${s.lech} lệch — KHÔNG đè</span>` : ""}
        ${s.thieu_khach ? html`<span class="kt-badge kt-badge--yellow">${s.thieu_khach} chưa rõ pháp nhân</span>` : ""}
      </div>
      <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    </div></div>

    ${(res.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          ${res.warnings.map((w) => html`<div class="kt-sub">• ${w}</div>`)}
        </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap" style="max-height:380px;overflow:auto"><table class="kt-table">
        <thead><tr>
          <th>Chuỗi</th><th>Mã điểm</th><th>Tên điểm</th><th>Khách hàng</th>
          <th class="num">Dòng</th><th>Trạng thái</th>
        </tr></thead>
        <tbody>
          ${stores.map((p) => html`<tr>
            <td><span class="kt-badge kt-badge--gray">${p.chain}</span></td>
            <td><code>${p.store_code}</code>
              ${p.code_synthesized
                ? html` <span class="kt-badge kt-badge--yellow" title="Chuỗi không in mã điểm — mã này do hệ thống sinh từ tên">mã tự sinh</span>`
                : ""}</td>
            <td>${p.store_name}</td>
            <td>${p.customer || html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${p.n_lines}</td>
            <td>
              <span class="kt-badge kt-badge--${STORE_STATUS_TONE[p.status] || "gray"}">${p.status_label}</span>
              ${(p.issues || []).map((i) => html`<div class="kt-sub">• ${i}</div>`)}
            </td>
          </tr>`)}
        </tbody>
      </table></div>
    </div></div>

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center">
      <button class="kt-btn kt-btn--outline" id="ss-cancel">Đóng</button>
      <button class="kt-btn kt-btn--primary" id="ss-commit" ${!s.moi ? "disabled" : ""}>
        <i class="fas fa-check"></i> Tạo ${s.moi || 0} điểm
      </button>
    </div>
    <div id="ss-msg"></div>`);

  modal.body.querySelector("#ss-cancel").addEventListener("click", () => modal.close());
  const btn = modal.body.querySelector("#ss-commit");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      // `expected_hash` là vân tay của ĐÚNG bản vừa xem — backend từ chối nếu
      // dữ liệu đã đổi (bảng kê mới nạp, điểm vừa tạo tay) giữa xem và tạo.
      const out = await api.mtStoreSeedCommit({ expected_hash: res.plan_hash });
      toast(out.message || `Đã tạo ${out.created} điểm`, "success");
      if ((out.failed || []).length) {
        setHTML(modal.body.querySelector("#ss-msg"), html`
          <div class="kt-card" style="border-left:4px solid var(--kt-warning);margin-top:10px">
            <div class="kt-card-body">
              <b>${out.failed.length} điểm KHÔNG tạo được</b>
              ${out.failed.map((f) => html`<div class="kt-sub">• ${f.chain} ${f.store_code}: ${f.error}</div>`)}
            </div></div>`);
      } else {
        modal.close();
      }
      await renderStores(container, state, parent, st);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#ss-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}


// ── Tab 4: Bút toán ────────────────────────────────────────────────────────
//
// RÀNG BUỘC P0 — "KHÔNG GHI SỔ": màn hình này chỉ sinh Journal Entry ở trạng
// thái NHÁP. Không có nút nào ghi sổ ở đây; duyệt là việc riêng, có guard riêng.
//
// Tài khoản hạch toán lấy từ cấu hình (MT Account Map), KHÔNG hardcode: số hiệu
// là 112/5211/6411 nhưng TÀI KHOẢN CON cụ thể khác nhau theo công ty.

const JE_STATE_TONE = {
  "Chưa sinh": "gray",
  "Đã sinh nháp": "yellow",
  "Đã duyệt một phần": "yellow",
  "Đã duyệt đủ": "green",
};

async function loadJournals(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtJeAdvices({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined,
      je_state: state.jeState || undefined,
      search: state.search || undefined,
      page: state.page, page_size: 20,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${jeViewSwitch(state)}
      <label class="kt-label" style="margin:0 0 0 8px">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${chainOptionHTML(state, state.chain)}
      </select>
      <label class="kt-label" style="margin:0 0 0 8px">Bút toán</label>
      <select class="kt-input kt-input--sm" id="je-state">
        <option value="">Mọi trạng thái</option>
        ${(res.je_states || []).map((s) => html`<option value="${s}" ${state.jeState === s ? "selected" : ""}>${s}</option>`)}
      </select>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="je-accmap" style="margin-left:auto">
        <i class="fas fa-sliders"></i> Cấu hình tài khoản
      </button>
    </div></div>

    ${!res.can_create
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>Chưa cấu hình tài khoản hạch toán cho kênh MT.</b>
          <div class="kt-sub" style="margin-top:4px">
            Bấm <b>Cấu hình tài khoản</b> để xem và điền. Hệ thống <b>không</b> lấy tài khoản
            mặc định đoán — sinh bút toán vào sai tài khoản còn tệ hơn không sinh.
          </div>
        </div></div>`
      : ""}

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-file-invoice"></i>
          <p>Chưa có bảng kê nào trong khoảng ngày này.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Bảng kê</th><th>Chuỗi</th><th>Khách hàng</th><th>Ngày TT</th>
              <th class="num">Thanh toán</th><th class="num">Chiết khấu</th><th class="num">Phí</th>
              <th>Bút toán</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((a) => html`<tr>
                <td><code>${a.name}</code>
                  ${a.advice_no ? html`<div class="kt-sub">${a.advice_no}</div>` : ""}</td>
                <td><span class="kt-badge kt-badge--gray">${a.chain || "—"}</span></td>
                <td>${a.customer_name || a.customer || html`<span class="kt-badge kt-badge--yellow">chưa gán khách</span>`}</td>
                <td>${a.payment_date ? formatDate(a.payment_date) : html`<span class="kt-badge kt-badge--red">thiếu ngày</span>`}</td>
                <td class="num">${formatVND(Math.abs(a.total_payment || 0))}</td>
                <td class="num">${formatVND(Math.abs(a.total_discount || 0))}</td>
                <td class="num">${formatVND(Math.abs(a.total_fee || 0))}</td>
                <td>
                  <span class="kt-badge kt-badge--${JE_STATE_TONE[a.je_state] || "gray"}">${a.je_state}</span>
                  ${a.je_draft ? html`<div class="kt-sub">${a.je_draft} nháp${a.je_submitted ? ` · ${a.je_submitted} đã duyệt` : ""}</div>`
                    : (a.je_submitted ? html`<div class="kt-sub">${a.je_submitted} đã duyệt</div>` : "")}
                </td>
                <td><button class="kt-btn kt-btn--outline kt-btn--sm je-open" data-advice="${a.name}">
                  <i class="fas fa-eye"></i> Xem bút toán</button></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "bảng kê")}
          <div class="kt-sub" style="margin-top:8px">
            Bút toán sinh ra ở trạng thái <b>Nháp</b>. Hệ thống không bao giờ tự ghi sổ.
            Bảng kê <b>thiếu ngày thanh toán</b> (Fuji không in ngày trong file) phải điền ngày trước —
            bút toán không có ngày sẽ rơi vào sai kỳ kế toán.
          </div>
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  const js = container.querySelector("#je-state");
  if (js) js.addEventListener("change", (e) => {
    state.jeState = e.target.value;
    state.page = 1;
    loadTab(container, state);
  });
  const am = container.querySelector("#je-accmap");
  if (am) am.addEventListener("click", () => openAccountMap());
  bindJeViewSwitch(container, state);
  container.querySelectorAll(".je-open").forEach((b) => {
    b.addEventListener("click", () => openJePreview(container, state, b.dataset.advice));
  });
}

// ── Cấu hình tài khoản (chỉ xem — sửa trên Desk) ───────────────────────────
async function openAccountMap() {
  const modal = openModal({
    title: "Tài khoản hạch toán kênh MT",
    icon: "fa-sliders",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await api.mtJeAccountMap({});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];
  const acc = (name, no, label) => name
    ? html`<div><code>${no || "?"}</code> ${label || name}</div>`
    : html`<span class="kt-badge kt-badge--red">chưa khai</span>`;

  setHTML(modal.body, html`
    ${(res.incomplete || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">${res.incomplete.length} dòng còn thiếu tài khoản.</b>
          <div class="kt-sub">Sinh bút toán sẽ DỪNG ở những sự kiện đó — hệ thống không lấy tài khoản đoán.</div>
        </div></div>`
      : ""}
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Sự kiện</th><th>Chuỗi</th><th>TK Nợ chính</th><th>TK Nợ thuế</th><th>TK Có</th><th></th></tr></thead>
        <tbody>
          ${rows.map((r) => html`<tr>
            <td>${r.event}${!r.active ? html` <span class="kt-badge kt-badge--gray">tắt</span>` : ""}</td>
            <td>${r.chain || html`<span class="kt-sub">mặc định (mọi chuỗi)</span>`}</td>
            <td>${acc(r.debit_account, r.debit_no, r.debit_name)}</td>
            <td>${r.tax_account
              ? acc(r.tax_account, r.tax_no, r.tax_name)
              : html`<span class="kt-sub">không tách thuế</span>`}</td>
            <td>${acc(r.credit_account, r.credit_no, r.credit_name)}</td>
            <td><a class="kt-btn kt-btn--outline kt-btn--sm" href="/app/mt-account-map/${r.name}" target="_blank">
              <i class="fas fa-pen"></i></a></td>
          </tr>`)}
        </tbody>
      </table></div>
      <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    </div></div>`);
}

// ── Xem trước bút toán của một bảng kê ─────────────────────────────────────
async function openJePreview(container, state, advice) {
  const modal = openModal({
    title: "Bút toán từ bảng kê " + advice,
    icon: "fa-file-invoice-dollar",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderJePreview(container, state, modal, advice);
}

async function renderJePreview(container, state, modal, advice) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtJePreview(advice, {});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-card" style="border-left:4px solid var(--kt-danger)">
      <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div></div>`);
    return;
  }
  const entries = res.entries || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="kt-badge kt-badge--gray">${res.chain || "—"}</span>
        ${res.customer ? html`<span class="kt-sub">${res.customer}</span>` : ""}
        ${res.payment_date ? html`<span class="kt-sub">· ngày ${formatDate(res.payment_date)}</span>` : ""}
        <span class="kt-badge kt-badge--${JE_STATE_TONE[res.je_state] || "gray"}">${res.je_state}</span>
        ${!res.reconciled ? html`<span class="kt-badge kt-badge--yellow">chưa tick đối chiếu khớp</span>` : ""}
      </div>
      <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    </div></div>

    ${(res.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          ${res.warnings.map((w) => html`<div class="kt-sub">• ${w}</div>`)}
        </div></div>`
      : ""}

    ${(res.not_posted || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>Khoản KHÔNG sinh bút toán</b>
          ${res.not_posted.map((n) => html`<div class="kt-sub" style="margin-top:6px">
            • <b>${n.row_kind}</b> — ${n.n_rows} dòng, ${formatVND(n.amount)}
            ${n.mixed_signs
              ? html`<br><b>Nhóm có cả khoản trừ lẫn khoản hoàn:</b> số trên là RÒNG;
                     cộng độ lớn từng dòng ra ${formatVND(n.amount_gross)}.`
              : ""}
            <br>${n.reason}
            ${n.misclassified
              ? html`<div style="margin-top:6px;padding:8px;border-left:3px solid var(--kt-danger);background:#fff7ed">
                  <b style="color:var(--kt-danger)">${n.misclassified.n} dòng ở đây trông KHÔNG phải hàng trả —
                  ${formatVND(n.misclassified.amount)}.</b>
                  Cột "số chứng từ" của chúng là <b>${n.misclassified.names.join(" · ")}</b> —
                  đó là TÊN khoản trừ, không phải số chứng từ trả hàng. Bảng kê này nạp bằng
                  bản đọc file cũ nên khoản đó bị xếp nhầm và không vào sổ.
                  <b>Nạp lại bảng kê</b> để nó vào đúng nhóm phí / chiết khấu và sinh bút toán.
                </div>`
              : ""}</div>`)}
        </div></div>`
      : ""}

    ${!entries.length
      ? html`<div class="kt-empty"><i class="fas fa-ban"></i><p>Bảng kê này không sinh được bút toán nào.</p></div>`
      : entries.map((e) => jeCard(e))}

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;margin-top:10px">
      <button class="kt-btn kt-btn--outline" id="jp-close">Đóng</button>
      ${state.canManage
        ? html`<button class="kt-btn kt-btn--primary" id="jp-create" ${!res.can_create ? "disabled" : ""}>
            <i class="fas fa-file-circle-plus"></i> Sinh ${entries.filter((e) => !e.duplicate).length} bút toán nháp
          </button>`
        : html`<span class="kt-sub">Chỉ Kế toán trưởng mới sinh được bút toán.</span>`}
    </div>
    <div id="jp-msg"></div>`);

  modal.body.querySelector("#jp-close").addEventListener("click", () => modal.close());
  const btn = modal.body.querySelector("#jp-create");
  if (btn) btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      // `expected_hash` là vân tay của ĐÚNG bản vừa xem — backend từ chối nếu
      // liên kết hóa đơn hoặc cấu hình tài khoản đã đổi giữa xem và sinh.
      const out = await api.mtJeCreate(advice, { expected_hash: res.plan_hash });
      toast(out.message || `Đã sinh ${(out.created || []).length} bút toán nháp`, "success");
      await renderJePreview(container, state, modal, advice);
      await loadTab(container, state);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#jp-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}

function jeCard(e) {
  const a = e.accounts || {};
  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${e.duplicate ? "warning" : "primary"})">
      <div class="kt-card-body">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <b>${e.kind}</b>
          <span class="kt-badge kt-badge--gray">${e.event}</span>
          <span class="kt-sub">ngày ${formatDate(e.posting_date)}</span>
          <b style="margin-left:auto">${formatVND(e.total)}</b>
        </div>
        ${e.duplicate
          ? html`<div class="kt-sub" style="margin-top:6px">
              <span class="kt-badge kt-badge--yellow">đã sinh rồi</span>
              Bút toán <code>${e.duplicate}</code> mang cùng vân tay — sẽ <b>không</b> sinh lại.
              Sinh lại rồi duyệt cả hai là trừ công nợ khách gấp đôi.
            </div>`
          : ""}
        ${a.is_default_row
          ? html`<div class="kt-sub" style="margin-top:4px">Dùng dòng cấu hình <b>mặc định</b> (không có dòng riêng cho chuỗi ${a.chain || "này"}).</div>`
          : ""}
        ${e.note_no_reference
          ? html`<div class="kt-sub" style="margin-top:6px;color:var(--kt-warning)"><b>${e.note_no_reference}</b></div>`
          : ""}
        ${e.mixed_signs
          ? html`<div class="kt-sub" style="margin-top:4px">
              Nhóm này có cả dòng <b>trừ</b> lẫn dòng <b>hoàn lại</b>. Bút toán ghi số
              <b>ròng</b> ${formatVND(e.total)} — đúng bằng số chuỗi thật sự trừ. Cộng độ lớn
              từng dòng sẽ ra ${formatVND(e.amount_gross)}, tức ghi khống
              ${formatVND(e.amount_gross - e.total)}đ.
            </div>`
          : ""}

        <div class="kt-table-wrap" style="margin-top:10px;max-height:260px;overflow:auto">
          <table class="kt-table">
            <thead><tr><th>Tài khoản</th><th>Đối tượng</th><th>Hóa đơn</th><th class="num">Nợ</th><th class="num">Có</th></tr></thead>
            <tbody>
              ${(e.debit_lines || []).map((l) => html`<tr>
                <td><code>${l.account}</code></td>
                <td class="kt-sub">${l.label || ""}</td>
                <td></td>
                <td class="num">${formatVND(l.amount)}</td>
                <td></td>
              </tr>`)}
              ${(e.credit_lines || []).map((l) => html`<tr>
                <td><code>${l.account}</code></td>
                <td>${l.party_name || l.party || ""}</td>
                <td><span class="kt-sub">tổng ${l.n_rows} dòng bảng kê</span></td>
                <td></td>
                <td class="num">${formatVND(l.amount)}</td>
              </tr>`)}
            </tbody>
          </table>
        </div>

        ${e.n_invoices != null
          ? html`<div class="kt-sub" style="margin-top:8px">
              Kỳ này gạch được <b>${e.n_invoices}</b> hóa đơn${e.n_unmatched
                ? html`, còn <b style="color:var(--kt-warning)">${e.n_unmatched} dòng chưa gạch</b>
                       — tiền VẪN vào bút toán (ghi tổng), xử lý việc gạch ở tab
                       <b>Quản lý thanh toán</b>.`
                : "."}
            </div>`
          : ""}
        ${e.n_review
          ? html`<div class="kt-sub" style="margin-top:4px">
              ${e.n_review} dòng nối hóa đơn ở mức <b>Cần review</b> — không ảnh hưởng số tiền
              bút toán, nhưng phải soi tay ở màn gạch hóa đơn.
            </div>`
          : ""}
        <details style="margin-top:8px">
          <summary class="kt-sub" style="cursor:pointer">Diễn giải ghi vào bút toán</summary>
          <pre class="kt-sub" style="white-space:pre-wrap;margin:6px 0 0">${e.remark}</pre>
        </details>
      </div>
    </div>`;
}


// ── Tab 4b: Duyệt bút toán ─────────────────────────────────────────────────
//
// ĐÂY LÀ CHỖ DUY NHẤT trong toàn bộ kênh MT mà tiền thật sự vào sổ. Mọi thứ
// trước đó — nạp bảng kê, khớp hóa đơn, sinh bút toán — đều là NHÁP và xóa được.
//
// Nút duyệt CHỈ hiện với người thật sự duyệt được (kế toán trưởng). Hiện cho
// người khác chỉ tạo một cú bấm để nhận lỗi quyền.

function jeViewSwitch(state) {
  const b = (key, label, icon) => html`<button
    class="kt-btn kt-btn--sm ${state.jeView === key ? "" : "kt-btn--outline"}"
    data-jeview="${key}"><i class="fas ${icon}"></i> ${label}</button>`;
  return html`<span style="display:inline-flex;gap:6px">
    ${b("bang-ke", "Theo bảng kê", "fa-file-invoice")}
    ${b("duyet", "Chờ duyệt", "fa-stamp")}
  </span>`;
}

function bindJeViewSwitch(container, state) {
  container.querySelectorAll("[data-jeview]").forEach((b) => {
    b.addEventListener("click", () => {
      if (state.jeView === b.dataset.jeview) return;
      state.jeView = b.dataset.jeview;
      state.page = 1;
      state.jePicked = new Set();   // chọn của màn này không mang sang màn kia
      loadTab(container, state);
    });
  });
}

async function loadJeApproval(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtJeDrafts({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined,
      kind: state.jeKind || undefined,
      docstatus: state.jeDocstatus === "1" ? 1 : 0,
      search: state.search || undefined,
      page: state.page, page_size: 20,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];
  const posted = state.jeDocstatus === "1";
  // Chỉ giữ lại lựa chọn của những dòng còn trên trang — tránh duyệt nhầm một
  // bút toán đã trôi khỏi bộ lọc.
  const onPage = new Set(rows.map((r) => r.name));
  state.jePicked = new Set([...state.jePicked].filter((n) => onPage.has(n)));

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${jeViewSwitch(state)}
      <label class="kt-label" style="margin:0 0 0 8px">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${chainOptionHTML(state, state.chain)}
      </select>
      <select class="kt-input kt-input--sm" id="je-kind">
        <option value="">Mọi loại</option>
        ${(res.kinds || []).map((k) => html`<option value="${k}" ${state.jeKind === k ? "selected" : ""}>${k}</option>`)}
      </select>
      <select class="kt-input kt-input--sm" id="je-docstatus">
        <option value="0" ${!posted ? "selected" : ""}>Nháp — chờ duyệt</option>
        <option value="1" ${posted ? "selected" : ""}>Đã ghi sổ</option>
      </select>
      <span class="kt-sub" style="margin-left:auto">
        ${res.total} bút toán · ${formatVND(res.total_amount)}
      </span>
    </div></div>

    ${!posted
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body kt-sub">
          <b>Duyệt là GHI SỔ.</b> ${res.note || ""}
        </div></div>`
      : ""}

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-stamp"></i>
          <p>${posted ? "Chưa có bút toán MT nào đã ghi sổ trong khoảng này."
                      : "Không còn bút toán nháp nào chờ duyệt."}</p>
          ${!posted ? html`<div class="kt-sub">Sinh bút toán ở màn <b>Theo bảng kê</b>.</div>` : ""}
        </div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          ${!posted && res.can_submit
            ? html`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
                <label style="display:flex;gap:6px;align-items:center">
                  <input type="checkbox" id="je-all"> <span class="kt-sub">Chọn cả trang</span>
                </label>
                <span class="kt-sub" id="je-count"></span>
                <button class="kt-btn kt-btn--outline kt-btn--sm" id="je-del" style="margin-left:auto" disabled>
                  <i class="fas fa-trash"></i> Xóa nháp
                </button>
                <button class="kt-btn kt-btn--primary kt-btn--sm" id="je-sub" disabled>
                  <i class="fas fa-stamp"></i> Duyệt (ghi sổ)
                </button>
              </div>`
            : ""}
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              ${!posted && res.can_submit ? html`<th style="width:32px"></th>` : ""}
              <th>Bút toán</th><th>Loại</th><th>Chuỗi</th><th>Khách hàng</th>
              <th>Ngày</th><th class="num">Số tiền</th><th>Bảng kê</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                ${!posted && res.can_submit
                  ? html`<td><input type="checkbox" class="je-pick" data-name="${r.name}"
                           ${state.jePicked.has(r.name) ? "checked" : ""}></td>`
                  : ""}
                <td><code>${r.name}</code></td>
                <td><span class="kt-badge kt-badge--${KIND_TONE[r.kind] || "gray"}">${r.kind || "—"}</span></td>
                <td><span class="kt-badge kt-badge--gray">${r.chain || "—"}</span></td>
                <td>${r.customer_name || r.customer || "—"}</td>
                <td>${formatDate(r.posting_date)}</td>
                <td class="num">${formatVND(r.amount)}</td>
                <td><code class="kt-sub">${r.advice || "—"}</code>
                  ${!r.reconciled
                    ? html`<div><span class="kt-badge kt-badge--yellow">chưa đối chiếu</span></div>`
                    : ""}</td>
                <td><button class="kt-btn kt-btn--outline kt-btn--sm je-detail" data-name="${r.name}">
                  <i class="fas fa-eye"></i></button></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "bút toán")}
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  bindJeViewSwitch(container, state);

  const kind = container.querySelector("#je-kind");
  if (kind) kind.addEventListener("change", (e) => {
    state.jeKind = e.target.value; state.page = 1; loadTab(container, state);
  });
  const ds = container.querySelector("#je-docstatus");
  if (ds) ds.addEventListener("change", (e) => {
    state.jeDocstatus = e.target.value;
    state.page = 1;
    state.jePicked = new Set();
    loadTab(container, state);
  });
  container.querySelectorAll(".je-detail").forEach((b) => {
    b.addEventListener("click", () => openJeDetail(container, state, b.dataset.name));
  });

  const refreshPicked = () => {
    const n = state.jePicked.size;
    const cnt = container.querySelector("#je-count");
    if (cnt) cnt.textContent = n ? `${n} bút toán đang chọn` : "";
    const sub = container.querySelector("#je-sub");
    const del = container.querySelector("#je-del");
    if (sub) sub.disabled = !n;
    if (del) del.disabled = !n;
  };
  container.querySelectorAll(".je-pick").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) state.jePicked.add(cb.dataset.name);
      else state.jePicked.delete(cb.dataset.name);
      refreshPicked();
    });
  });
  const all = container.querySelector("#je-all");
  if (all) all.addEventListener("change", () => {
    container.querySelectorAll(".je-pick").forEach((cb) => {
      cb.checked = all.checked;
      if (all.checked) state.jePicked.add(cb.dataset.name);
      else state.jePicked.delete(cb.dataset.name);
    });
    refreshPicked();
  });
  refreshPicked();

  const sub = container.querySelector("#je-sub");
  if (sub) sub.addEventListener("click", () => doSubmitJes(container, state, rows));
  const del = container.querySelector("#je-del");
  if (del) del.addEventListener("click", () => doDeleteJes(container, state, rows));
}

// ── Duyệt hàng loạt ────────────────────────────────────────────────────────
async function doSubmitJes(container, state, rows, force) {
  const names = [...state.jePicked];
  if (!names.length) return;
  const picked = rows.filter((r) => state.jePicked.has(r.name));
  const total = picked.reduce((s, r) => s + (r.amount || 0), 0);

  const modal = openModal({
    title: "Duyệt bút toán — ghi sổ",
    icon: "fa-stamp",
    maxWidth: 720,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let res;
  try {
    res = await api.mtJeSubmit(names, force ? { force_unreconciled: 1 } : {});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-card" style="border-left:4px solid var(--kt-danger)">
      <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div></div>`);
    return;
  }

  // Backend TỪ CHỐI ghi sổ khi bảng kê nguồn chưa tick đối chiếu — đây là lần
  // xác nhận có ý thức, không phải một hộp thoại cho có.
  if (res.needs_confirm) {
    setHTML(modal.body, html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
        <b>${res.message}</b>
        <div class="kt-sub" style="margin-top:8px">
          Duyệt là ghi sổ. Hủy một bút toán đã ghi để lại vết trong sổ cái mà kiểm toán sẽ hỏi —
          bút toán nháp thì xóa sạch được.
        </div>
      </div></div>
      <div class="kt-card kt-mb"><div class="kt-card-body">
        <div class="kt-table-wrap" style="max-height:280px;overflow:auto"><table class="kt-table">
          <thead><tr><th>Bút toán</th><th>Loại</th><th>Bảng kê</th><th class="num">Số tiền</th></tr></thead>
          <tbody>${(res.unreconciled || []).map((u) => html`<tr>
            <td><code>${u.name}</code></td><td>${u.kind}</td>
            <td><code class="kt-sub">${u.advice}</code></td>
            <td class="num">${formatVND(u.amount)}</td>
          </tr>`)}</tbody>
        </table></div>
      </div></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="kt-btn kt-btn--outline" id="jc-cancel">Để tôi soi lại</button>
        <button class="kt-btn kt-btn--danger" id="jc-force">
          <i class="fas fa-stamp"></i> Vẫn duyệt ${names.length} bút toán (${formatVND(total)})
        </button>
      </div>`);
    modal.body.querySelector("#jc-cancel").addEventListener("click", () => modal.close());
    modal.body.querySelector("#jc-force").addEventListener("click", () => {
      modal.close();
      doSubmitJes(container, state, rows, true);
    });
    return;
  }

  setHTML(modal.body, jeBatchResult(res.message, res.submitted || [], res.failed || [], "đã ghi sổ"));
  modal.body.querySelector("#jr-close").addEventListener("click", () => modal.close());
  toast(res.message, (res.failed || []).length ? "error" : "success");
  state.jePicked = new Set();
  await loadTab(container, state);
}

async function doDeleteJes(container, state, rows) {
  const names = [...state.jePicked];
  if (!names.length) return;
  const modal = openModal({
    title: "Xóa bút toán nháp",
    icon: "fa-trash",
    maxWidth: 640,
    body: html`
      <div class="kt-card kt-mb"><div class="kt-card-body">
        Xóa <b>${names.length}</b> bút toán <b>nháp</b>. Chưa ghi sổ nên xóa sạch, không để lại vết.
        <div class="kt-sub" style="margin-top:6px">
          Sinh lại được ngay sau khi sửa bảng kê — vân tay chống trùng chỉ chặn khi bản nháp cũ còn đó.
        </div>
      </div></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="kt-btn kt-btn--outline" id="jd-cancel">Hủy</button>
        <button class="kt-btn kt-btn--danger" id="jd-ok"><i class="fas fa-trash"></i> Xóa</button>
      </div>
      <div id="jd-msg"></div>`,
  });
  modal.body.querySelector("#jd-cancel").addEventListener("click", () => modal.close());
  modal.body.querySelector("#jd-ok").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#jd-ok");
    btn.disabled = true;
    try {
      const res = await api.mtJeDeleteDrafts(names);
      setHTML(modal.body, jeBatchResult(res.message,
        (res.deleted || []).map((n) => ({ name: n })), res.failed || [], "đã xóa"));
      modal.body.querySelector("#jr-close").addEventListener("click", () => modal.close());
      toast(res.message, (res.failed || []).length ? "error" : "success");
      state.jePicked = new Set();
      await loadTab(container, state);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#jd-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}

// Kết quả TỪNG BÚT TOÁN — không gộp thành một chữ "xong". Duyệt 20 cái mà 3 cái
// hỏng thì kế toán phải biết ĐÍCH DANH ba cái nào.
function jeBatchResult(message, done, failed, verb) {
  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${failed.length ? "warning" : "success"})">
      <div class="kt-card-body"><b>${message}</b></div>
    </div>
    ${done.length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:6px">${done.length} bút toán ${verb}</div>
          <div class="kt-table-wrap" style="max-height:220px;overflow:auto"><table class="kt-table">
            <tbody>${done.map((d) => html`<tr>
              <td><code>${d.name}</code></td>
              <td>${d.kind || ""}</td>
              <td class="num">${d.amount != null ? formatVND(d.amount) : ""}</td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`
      : ""}
    ${failed.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">${failed.length} bút toán KHÔNG xử lý được</b>
          ${failed.map((f) => html`<div class="kt-sub" style="margin-top:6px">
            • <code>${f.name}</code>: ${f.error}</div>`)}
        </div></div>`
      : ""}
    <div style="display:flex;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="jr-close">Đóng</button>
    </div>`;
}

// ── Soi một bút toán trước khi duyệt ───────────────────────────────────────
async function openJeDetail(container, state, name) {
  const modal = openModal({
    title: "Bút toán " + name,
    icon: "fa-file-invoice-dollar",
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await api.mtJeDetail(name);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const d = res.doc || {};
  const draft = Number(d.docstatus) === 0;

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <span class="kt-badge kt-badge--${KIND_TONE[d.kind] || "gray"}">${d.kind || "—"}</span>
        <span class="kt-badge kt-badge--gray">${d.chain || "—"}</span>
        <span class="kt-badge kt-badge--${draft ? "yellow" : "green"}">${draft ? "Nháp — chưa ghi sổ" : "Đã ghi sổ"}</span>
        ${!d.reconciled ? html`<span class="kt-badge kt-badge--yellow">bảng kê chưa tick đối chiếu</span>` : ""}
        <span class="kt-sub">ngày ${formatDate(d.posting_date)}</span>
        <b style="margin-left:auto">${formatVND(d.total_debit)}</b>
      </div>
      <div class="kt-sub" style="margin-top:6px">
        Bảng kê nguồn <code>${d.advice || "—"}</code>${d.advice_no ? ` · ${d.advice_no}` : ""}
        ${d.file_name ? ` · file ${d.file_name}` : ""}
      </div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Tài khoản</th><th>Đối tượng</th><th class="num">Nợ</th><th class="num">Có</th></tr></thead>
        <tbody>
          ${(res.lines || []).map((l) => html`<tr>
            <td><code>${l.account_number || ""}</code> ${l.account_name || l.account}</td>
            <td>${l.party || ""}</td>
            <td class="num">${l.debit ? formatVND(l.debit) : ""}</td>
            <td class="num">${l.credit ? formatVND(l.credit) : ""}</td>
          </tr>`)}
        </tbody>
      </table></div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-sub" style="margin-bottom:6px">Diễn giải</div>
      <pre class="kt-sub" style="white-space:pre-wrap;margin:0">${res.remark || "(trống)"}</pre>
    </div></div>

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center">
      <a class="kt-btn kt-btn--outline kt-btn--sm" href="${res.desk_url}" target="_blank">
        <i class="fas fa-arrow-up-right-from-square"></i> Mở trên Desk</a>
      <button class="kt-btn kt-btn--outline" id="jd2-close">Đóng</button>
      ${draft && res.can_submit
        ? html`<button class="kt-btn kt-btn--primary" id="jd2-sub"><i class="fas fa-stamp"></i> Duyệt bút toán này</button>`
        : ""}
    </div>`);

  modal.body.querySelector("#jd2-close").addEventListener("click", () => modal.close());
  const sub = modal.body.querySelector("#jd2-sub");
  if (sub) sub.addEventListener("click", async () => {
    modal.close();
    state.jePicked = new Set([name]);
    await doSubmitJes(container, state, [{ name, amount: d.total_debit }]);
  });
}


// ── Tab 5: Bảng kê chiết khấu (BKCK) ───────────────────────────────────────
//
// Chiều MÌNH XUẤT HÓA ĐƠN — ngược với tab 'Quản lý chiết khấu' (khoản chuỗi trừ
// lại). Năm bước §3 SOP: nạp file doanh số → lập bảng kê → CHỐT lấy số →
// xuất hóa đơn CK trên MISA rồi ghi số về → sinh bút toán.
//
// BẢNG KÊ LÀ CHỨNG TỪ HAI BÊN KÝ và dẫn tới một hóa đơn GTGT. Số bảng kê chỉ
// được cấp khi CHỐT — nháp bị xóa mà đã ăn số là dãy thủng lỗ.

const BKCK_TONE = { "Nháp": "gray", "Đã chốt": "yellow", "Đã xuất hóa đơn": "green" };

async function loadBkck(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtDiscountSheets({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined,
      status: state.bkckStatus || undefined,
      search: state.search || undefined,
      page: state.page, page_size: 20,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <label class="kt-label" style="margin:0">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${(res.chains || []).map((c) => html`<option value="${c}" ${state.chain === c ? "selected" : ""}>${c}</option>`)}
      </select>
      <select class="kt-input kt-input--sm" id="bk-status">
        <option value="">Mọi trạng thái</option>
        ${(res.statuses || []).map((x) => html`<option value="${x}" ${state.bkckStatus === x ? "selected" : ""}>${x}</option>`)}
      </select>
      <span class="kt-sub">${res.total} bảng kê · chiết khấu ${formatVND(res.total_amount)}</span>
      ${res.can_manage
        ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="bk-new" style="margin-left:auto">
            <i class="fas fa-file-import"></i> Nạp file doanh số → lập bảng kê
          </button>`
        : ""}
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-file-signature"></i>
          <p>Chưa có bảng kê chiết khấu nào trong khoảng này.</p>
          ${res.can_manage
            ? html`<div class="kt-sub">Bấm <b>Nạp file doanh số</b> — hệ thống đọc file của chuỗi,
                   gộp theo pháp nhân/chi nhánh và dựng bảng kê cho từng bên mua.</div>`
            : ""}
        </div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Số bảng kê</th><th>Chuỗi</th><th>Bên mua</th><th>Kỳ</th>
              <th class="num">Doanh số</th><th class="num">Chiết khấu</th>
              <th>HĐ chiết khấu</th><th>Trạng thái</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td>${r.sheet_no
                  ? html`<code>${r.sheet_no}</code>`
                  : html`<span class="kt-sub">chưa cấp số</span>`}
                  <div class="kt-sub">${formatDate(r.sheet_date)} · ${r.n_lines} HĐ</div></td>
                <td><span class="kt-badge kt-badge--gray">${r.chain}</span></td>
                <td>${r.buyer_name || r.customer}
                  ${r.buyer_tax_id ? html`<div class="kt-sub">MST ${r.buyer_tax_id}</div>` : ""}</td>
                <td>${r.period_label || "—"}</td>
                <td class="num">${formatVND(r.total_base)}</td>
                <td class="num"><b>${formatVND(r.discount_gross)}</b>
                  <div class="kt-sub">${r.rate ? `${r.rate}%` : r.mode}</div></td>
                <td>${r.discount_invoice_no
                  ? html`<code>${r.discount_invoice_series || ""} ${r.discount_invoice_no}</code>`
                  : html`<span class="kt-sub">—</span>`}</td>
                <td><span class="kt-badge kt-badge--${BKCK_TONE[r.status] || "gray"}">${r.status}</span>
                  <div class="kt-sub">${r.je_state}</div></td>
                <td><button class="kt-btn kt-btn--outline kt-btn--sm bk-open" data-name="${r.name}">
                  <i class="fas fa-eye"></i></button></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "bảng kê")}
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  const st = container.querySelector("#bk-status");
  if (st) st.addEventListener("change", (e) => {
    state.bkckStatus = e.target.value; state.page = 1; loadTab(container, state);
  });
  const nw = container.querySelector("#bk-new");
  if (nw) nw.addEventListener("click", () => pickBkckFile(container, state));
  container.querySelectorAll(".bk-open").forEach((b) => {
    b.addEventListener("click", () => openBkckDetail(container, state, b.dataset.name));
  });
}

// ── Nạp file doanh số → xem trước → lập ────────────────────────────────────
function pickBkckFile(container, state) {
  const inp = document.createElement("input");
  inp.type = "file";
  // `.pdf` cho Rebate Settlement của Emart — chuỗi duy nhất gửi PDF. Backend
  // nhận dạng bằng CHỮ KÝ BYTE nên đuôi viết hoa `.PDF` vẫn vào đúng nhánh;
  // liệt kê ở đây chỉ để hộp thoại chọn file không lọc mất nó.
  inp.accept = ".xlsx,.xls,.xlsm,.pdf,.PDF";
  inp.addEventListener("change", () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const fr = new FileReader();
    fr.onload = () => {
      const b64 = String(fr.result).split(",").pop();
      openBkckPreview(container, state, b64, f.name);
    };
    fr.readAsDataURL(f);
  });
  inp.click();
}

async function openBkckPreview(container, state, content, filename, chain, period, sheetDate) {
  const modal = openModal({
    title: "Lập bảng kê chiết khấu từ " + filename,
    icon: "fa-file-signature",
    maxWidth: 1040,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderBkckPreview(container, state, modal, content, filename, chain, period, sheetDate);
}

async function renderBkckPreview(container, state, modal, content, filename, chain, period, sheetDate) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  const today = todayISO();
  let res;
  try {
    res = await api.mtDiscountPreview({
      content, chain: chain || undefined, filename,
      period_label: period || undefined, sheet_date: sheetDate || today,
    });
  } catch (e) {
    setHTML(modal.body, html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
        <b style="color:var(--kt-danger)">Không lập được bảng kê</b>
        <div class="kt-sub" style="margin-top:6px;white-space:pre-wrap">${e.message}</div>
      </div></div>
      <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div><label class="kt-label">Chọn chuỗi rồi thử lại</label>
          <select class="kt-input kt-input--sm" id="bp-chain">
            <option value="">— tự nhận —</option>
            <option value="Central Retail">Central Retail</option>
            <option value="LOTTE">LOTTE</option>
            <option value="Mega Market">Mega Market</option>
          </select></div>
        <button class="kt-btn kt-btn--outline" id="bp-retry"><i class="fas fa-rotate"></i> Đọc lại</button>
      </div>`);
    modal.body.querySelector("#bp-retry").addEventListener("click", () => {
      renderBkckPreview(container, state, modal, content, filename,
        modal.body.querySelector("#bp-chain").value, period, sheetDate);
    });
    return;
  }

  const sheets = res.sheets || [];
  const bt = res.basis_totals || {};

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="kt-badge kt-badge--gray">${res.chain}</span>
        <span class="kt-sub">${res.mode_label}${res.file_rate ? ` · ${res.file_rate}% (từ file)` : ""}</span>
        <span class="kt-sub">· ${bt.n_rows} dòng doanh số · cơ sở ${formatVND(bt.base_amount)}</span>
        ${res.reconciled
          ? html`<span class="kt-badge kt-badge--green">số kiểm tra khớp</span>`
          : html`<span class="kt-badge kt-badge--yellow">file không có số kiểm tra</span>`}
      </div>
      <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-top:10px">
        <div><label class="kt-label">Kỳ (in trên bảng kê)</label>
          <input class="kt-input kt-input--sm" id="bp-period" placeholder="07.2026" value="${period || ""}"></div>
        <div><label class="kt-label">Ngày bảng kê</label>
          <input type="date" class="kt-input kt-input--sm" id="bp-date" value="${sheetDate || today}"></div>
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="bp-refresh">
          <i class="fas fa-rotate"></i> Áp dụng</button>
      </div>
    </div></div>

    ${(res.excluded || []).length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <b>Khoản KHÔNG vào bảng kê</b>
          ${res.excluded.map((x) => html`<div class="kt-sub">• <b>${x.row_kind}</b> —
            ${x.n_rows} dòng, ${formatVND(x.amount)}</div>`)}
          <div class="kt-sub" style="margin-top:6px">
            Nhóm phí/hỗ trợ do chuỗi xuất hóa đơn, và hàng chưa nhận — cả hai đều không
            thuộc phần mình xuất chiết khấu.
          </div>
        </div></div>`
      : ""}

    ${(res.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          ${res.warnings.map((w) => html`<div class="kt-sub">• ${w}</div>`)}
        </div></div>`
      : ""}

    ${(res.blocked || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">${res.blocked.length} nhóm CHƯA lập được bảng kê</b>
          ${res.blocked.map((b) => html`<div class="kt-sub" style="margin-top:6px">
            • <code>${b.key}</code> ${b.group_label || ""} — ${b.n_rows} dòng,
            ${formatVND(b.base_amount)}<br>${b.reason}</div>`)}
        </div></div>`
      : ""}

    ${!sheets.length
      ? html`<div class="kt-empty"><i class="fas fa-ban"></i><p>Không dựng được bảng kê nào.</p></div>`
      : html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-table-wrap" style="max-height:340px;overflow:auto"><table class="kt-table">
            <thead><tr>
              <th>Bên mua</th><th>MST</th><th class="num">HĐ</th><th class="num">Doanh số</th>
              <th class="num">Chiết khấu</th><th>Cách tính</th><th>Đối chiếu</th>
            </tr></thead>
            <tbody>${sheets.map((p) => html`<tr>
              <td>${p.buyer_name}
                ${p.group_label ? html`<div class="kt-sub">${p.group_label}</div>` : ""}</td>
              <td>${p.buyer_tax_id || html`<span class="kt-badge kt-badge--red">thiếu MST</span>`}</td>
              <td class="num">${p.n_lines}</td>
              <td class="num">${formatVND(p.total_base)}</td>
              <td class="num"><b>${formatVND(p.discount_gross)}</b></td>
              <td class="kt-sub">${p.mode}${p.rate ? ` ${p.rate}%` : ""}
                <div>tỷ lệ từ ${p.rate_source}</div>
                ${p.term_is_default ? html`<div>điều khoản mặc định của chuỗi</div>` : ""}</td>
              <td class="kt-sub">${p.n_matched}/${p.n_lines} khớp HĐ
                ${p.n_mismatch ? html`<div style="color:var(--kt-warning)">${p.n_mismatch} lệch tiền</div>` : ""}
                ${p.existing ? html`<div style="color:var(--kt-danger)">đã có: ${p.existing}</div>` : ""}</td>
            </tr>`)}</tbody>
          </table></div>
          <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
        </div></div>`}

    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="bp-close">Đóng</button>
      <button class="kt-btn kt-btn--primary" id="bp-commit" ${!res.can_commit ? "disabled" : ""}>
        <i class="fas fa-check"></i> Lập ${sheets.length} bảng kê nháp
      </button>
    </div>
    <div id="bp-msg"></div>`);

  const reload = () => renderBkckPreview(container, state, modal, content, filename, chain,
    modal.body.querySelector("#bp-period").value.trim(),
    modal.body.querySelector("#bp-date").value);
  modal.body.querySelector("#bp-refresh").addEventListener("click", reload);
  modal.body.querySelector("#bp-close").addEventListener("click", () => modal.close());

  const btn = modal.body.querySelector("#bp-commit");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const out = await api.mtDiscountCommit({
        content, chain: chain || undefined, filename,
        period_label: modal.body.querySelector("#bp-period").value.trim() || undefined,
        sheet_date: modal.body.querySelector("#bp-date").value,
        expected_hash: res.plan_hash,
      });
      toast(out.message, "success");
      modal.close();
      await loadTab(container, state);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#bp-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}

// ── Một bảng kê: soi, chốt, ghi số hóa đơn, sinh bút toán ──────────────────
async function openBkckDetail(container, state, name) {
  const modal = openModal({
    title: "Bảng kê chiết khấu",
    icon: "fa-file-signature",
    maxWidth: 960,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderBkckDetail(container, state, modal, name);
}

async function renderBkckDetail(container, state, modal, name) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtDiscountSheet(name);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const d = res.doc || {};
  const lines = res.lines || [];
  const draft = d.status === "Nháp";
  const can = res.can_manage;

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        ${d.sheet_no
          ? html`<b><code>${d.sheet_no}</code></b>`
          : html`<span class="kt-badge kt-badge--gray">chưa cấp số</span>`}
        <span class="kt-badge kt-badge--${BKCK_TONE[d.status] || "gray"}">${d.status}</span>
        <span class="kt-badge kt-badge--gray">${d.chain}</span>
        ${d.period_label ? html`<span class="kt-sub">kỳ ${d.period_label}</span>` : ""}
        <span class="kt-sub">· ngày ${formatDate(d.sheet_date)}</span>
        <b style="margin-left:auto">CK ${formatVND(d.discount_gross)}</b>
      </div>
      <div class="kt-sub" style="margin-top:8px">
        <b>Bên mua:</b> ${d.buyer_name || d.customer}
        ${d.buyer_tax_id ? ` · MST ${d.buyer_tax_id}` : html` · <span style="color:var(--kt-danger)">THIẾU MST</span>`}
        ${d.buyer_address ? html`<br>${d.buyer_address}` : ""}
      </div>
      <div class="kt-sub" style="margin-top:4px">
        ${d.mode}${d.rate ? ` ${d.rate}%` : ""} · thuế ${d.vat_rate}% ·
        doanh số ${formatVND(d.total_base)} → chiết khấu ${formatVND(d.discount_base)}
        + thuế ${formatVND(d.discount_vat)}
      </div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap" style="max-height:300px;overflow:auto"><table class="kt-table">
        <thead><tr><th>Số HĐ</th><th>Ký hiệu</th><th>Ngày</th>
          <th class="num">Trước thuế</th><th class="num">Thuế</th><th class="num">Tổng</th>
          <th>Ghi chú</th><th>Đối chiếu</th></tr></thead>
        <tbody>${lines.map((l) => html`<tr>
          <td>${l.inv_no}</td><td>${l.inv_series || ""}</td>
          <td>${l.inv_date ? formatDate(l.inv_date) : ""}</td>
          <td class="num">${formatVND(l.amount_before_vat)}</td>
          <td class="num">${formatVND(l.vat_amount)}</td>
          <td class="num">${formatVND(l.total_amount)}</td>
          <td class="kt-sub">${l.note || ""}</td>
          <td class="kt-sub">${l.sales_invoice || l.match_note || ""}</td>
        </tr>`)}</tbody>
      </table></div>
    </div></div>

    ${!draft
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:6px">Hóa đơn chiết khấu đã xuất trên MISA</div>
          <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
            <div><label class="kt-label">Ký hiệu</label>
              <input class="kt-input kt-input--sm" id="bd-series" value="${d.discount_invoice_series || ""}" style="width:120px"></div>
            <div><label class="kt-label">Số hóa đơn</label>
              <input class="kt-input kt-input--sm" id="bd-no" value="${d.discount_invoice_no || ""}" style="width:150px"></div>
            <div><label class="kt-label">Ngày</label>
              <input type="date" class="kt-input kt-input--sm" id="bd-date" value="${d.discount_invoice_date || ""}"></div>
            ${can ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="bd-save-inv">
              <i class="fas fa-check"></i> Ghi số hóa đơn</button>` : ""}
          </div>
        </div></div>`
      : ""}

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
      ${!draft ? html`<a class="kt-btn kt-btn--outline kt-btn--sm" href="${res.print_url}" target="_blank">
        <i class="fas fa-print"></i> In bảng kê</a>` : ""}
      <a class="kt-btn kt-btn--outline kt-btn--sm" href="/app/mt-discount-sheet/${d.name}" target="_blank">
        <i class="fas fa-arrow-up-right-from-square"></i> Desk</a>
      <button class="kt-btn kt-btn--outline" id="bd-close">Đóng</button>
      ${draft && can
        ? html`<button class="kt-btn kt-btn--primary" id="bd-final">
            <i class="fas fa-stamp"></i> Chốt &amp; cấp số</button>`
        : ""}
      ${!draft && can
        ? html`<button class="kt-btn kt-btn--primary" id="bd-je">
            <i class="fas fa-file-invoice-dollar"></i> Sinh bút toán</button>`
        : ""}
    </div>
    <div id="bd-msg"></div>`);

  const msg = (e, tone) => setHTML(modal.body.querySelector("#bd-msg"), html`
    <div class="kt-card" style="border-left:4px solid var(--kt-${tone});margin-top:10px">
      <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e}</div></div>
    </div>`);

  modal.body.querySelector("#bd-close").addEventListener("click", () => modal.close());

  const fin = modal.body.querySelector("#bd-final");
  if (fin) fin.addEventListener("click", async () => {
    fin.disabled = true;
    try {
      const out = await api.mtDiscountFinalize(name, d.sheet_date);
      toast(out.message, "success");
      await renderBkckDetail(container, state, modal, name);
      await loadTab(container, state);
    } catch (e) { fin.disabled = false; msg(e.message, "danger"); }
  });

  const sv = modal.body.querySelector("#bd-save-inv");
  if (sv) sv.addEventListener("click", async () => {
    sv.disabled = true;
    try {
      const out = await api.mtDiscountSetInvoice({
        name,
        invoice_no: modal.body.querySelector("#bd-no").value.trim(),
        invoice_series: modal.body.querySelector("#bd-series").value.trim(),
        invoice_date: modal.body.querySelector("#bd-date").value || undefined,
      });
      toast(out.message, "success");
      await renderBkckDetail(container, state, modal, name);
      await loadTab(container, state);
    } catch (e) { sv.disabled = false; msg(e.message, "danger"); }
  });

  const je = modal.body.querySelector("#bd-je");
  if (je) je.addEventListener("click", async () => {
    je.disabled = true;
    try {
      const pv = await api.mtDiscountJePreview(name);
      const e0 = (pv.entries || [])[0] || {};
      if (e0.duplicate) {
        msg(`Bút toán ${e0.duplicate} đã sinh cho bảng kê này — không sinh lại.`, "warning");
        je.disabled = false;
        return;
      }
      const out = await api.mtDiscountJeCreate({ name, expected_hash: pv.plan_hash });
      toast(out.message, "success");
      await renderBkckDetail(container, state, modal, name);
      await loadTab(container, state);
    } catch (e) { je.disabled = false; msg(e.message, "danger"); }
  });
}


// ── Tab 6: Hồ sơ thanh toán WinCommerce ────────────────────────────────────
//
// Win chỉ xử lý thanh toán khi nhận đủ bảng kê + file PDF hóa đơn ĐẶT ĐÚNG TÊN
// (YYYYMMDD_<mã NCC>_<stt>_PF). Sai tên là hồ sơ bị trả về và cả đợt trượt kỳ
// thanh toán — nên tên file do hệ thống sinh, không để gõ tay.
//
// MỘT HÓA ĐƠN CHỈ NỘP MỘT LẦN: hóa đơn đã nằm trong hồ sơ khác không được đề
// xuất lại, và DocType chặn thêm một lớp nữa.

const WIN_TONE = { "Nháp": "yellow", "Đã nộp": "green" };

async function loadWinDossiers(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtWinDossiers({
      from_date: state.from, to_date: state.to,
      status: state.winStatus || undefined,
      search: state.search || undefined,
      page: state.page, page_size: 20,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <select class="kt-input kt-input--sm" id="hw-status">
        <option value="">Mọi trạng thái</option>
        ${(res.statuses || []).map((x) => html`<option value="${x}" ${state.winStatus === x ? "selected" : ""}>${x}</option>`)}
      </select>
      <span class="kt-sub">${res.total} hồ sơ · ${formatVND(res.total_amount)}</span>
      ${res.can_manage
        ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="hw-new" style="margin-left:auto">
            <i class="fas fa-folder-plus"></i> Lập hồ sơ mới
          </button>`
        : ""}
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-folder-open"></i>
          <p>Chưa có hồ sơ Winmart nào trong khoảng này.</p>
          ${res.can_manage
            ? html`<div class="kt-sub">Bấm <b>Lập hồ sơ mới</b> — hệ thống gom hóa đơn Win
                   chưa nộp hồ sơ nào và sinh tên file PDF chuẩn.</div>`
            : ""}
        </div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Tên file PDF</th><th>Ngày nộp</th><th>Khách hàng</th>
              <th class="num">Số HĐ</th><th class="num">Trước VAT</th>
              <th class="num">Tổng thanh toán</th><th>Trạng thái</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><code>${r.file_prefix}</code>
                  <div class="kt-sub">HĐ ${formatDate(r.period_from)} → ${formatDate(r.period_to)}</div></td>
                <td>${formatDate(r.submit_date)}</td>
                <td>${r.customer_name || r.customer}</td>
                <td class="num">${r.n_lines}</td>
                <td class="num">${formatVND(r.total_before_vat)}</td>
                <td class="num"><b>${formatVND(r.total_amount)}</b></td>
                <td><span class="kt-badge kt-badge--${WIN_TONE[r.status] || "gray"}">${r.status}</span></td>
                <td><button class="kt-btn kt-btn--outline kt-btn--sm hw-open" data-name="${r.name}">
                  <i class="fas fa-eye"></i></button></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "hồ sơ")}
        </div></div>`}
  `);

  bindPager(container, state);
  const st = container.querySelector("#hw-status");
  if (st) st.addEventListener("change", (e) => {
    state.winStatus = e.target.value; state.page = 1; loadTab(container, state);
  });
  const nw = container.querySelector("#hw-new");
  if (nw) nw.addEventListener("click", () => openWinPreview(container, state, res.default_vendor_code));
  container.querySelectorAll(".hw-open").forEach((b) => {
    b.addEventListener("click", () => openWinDetail(container, state, b.dataset.name));
  });
}

// ── Lập hồ sơ: xem trước → lập ─────────────────────────────────────────────
async function openWinPreview(container, state, vendorCode) {
  const modal = openModal({
    title: "Lập hồ sơ thanh toán WinCommerce",
    icon: "fa-folder-plus",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  const st = {
    from: state.from, to: state.to,
    submit: todayISO(),
    no: 1, vendor: vendorCode || "",
  };
  await renderWinPreview(container, state, modal, st);
}

async function renderWinPreview(container, state, modal, st) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtWinPreview({
      from_date: st.from, to_date: st.to, submit_date: st.submit,
      dossier_no: st.no, vendor_code: st.vendor || undefined,
    });
  } catch (e) {
    setHTML(modal.body, html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
        <div class="kt-sub" style="white-space:pre-wrap">${e.message}</div>
      </div></div>
      <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div><label class="kt-label">Mã NCC tại Win</label>
          <input class="kt-input kt-input--sm" id="hp-vendor" value="${st.vendor}" placeholder="2007766"></div>
        <button class="kt-btn kt-btn--outline" id="hp-retry"><i class="fas fa-rotate"></i> Thử lại</button>
      </div>`);
    modal.body.querySelector("#hp-retry").addEventListener("click", () => {
      st.vendor = modal.body.querySelector("#hp-vendor").value.trim();
      renderWinPreview(container, state, modal, st);
    });
    return;
  }
  const lines = res.sample || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div><label class="kt-label">Hóa đơn từ</label>
          <input type="date" class="kt-input kt-input--sm" id="hp-from" value="${st.from}"></div>
        <div><label class="kt-label">đến</label>
          <input type="date" class="kt-input kt-input--sm" id="hp-to" value="${st.to}"></div>
        <div><label class="kt-label">Ngày nộp</label>
          <input type="date" class="kt-input kt-input--sm" id="hp-submit" value="${st.submit}"></div>
        <div><label class="kt-label">STT hồ sơ</label>
          <input type="number" min="1" class="kt-input kt-input--sm" id="hp-no" value="${st.no}" style="width:80px"></div>
        <div><label class="kt-label">Mã NCC</label>
          <input class="kt-input kt-input--sm" id="hp-vendor" value="${res.vendor_code}" style="width:110px"></div>
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="hp-refresh">
          <i class="fas fa-rotate"></i> Áp dụng</button>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <span class="kt-sub">Tên file PDF phải đặt:</span>
        <b><code>${res.file_prefix}</code></b>
        <span class="kt-sub">· ${res.n_lines} hóa đơn · ${formatVND(res.total_amount)}</span>
      </div>
      <div class="kt-sub" style="margin-top:6px">${res.note || ""}</div>
    </div></div>

    ${(res.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          ${res.warnings.map((w) => html`<div class="kt-sub">• ${w}</div>`)}
        </div></div>`
      : ""}

    ${!lines.length
      ? html`<div class="kt-empty"><i class="fas fa-inbox"></i>
          <p>Không có hóa đơn Winmart nào chưa nộp hồ sơ trong khoảng này.</p></div>`
      : html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-table-wrap" style="max-height:340px;overflow:auto"><table class="kt-table">
            <thead><tr>${(res.columns || []).map((c) => html`<th>${c}</th>`)}</tr></thead>
            <tbody>${lines.map((l) => html`<tr>
              <td>${l.stt}</td>
              <td>${res.vendor_code}</td>
              <td>${l.po_vcm || html`<span class="kt-badge kt-badge--yellow">thiếu PO</span>`}</td>
              <td>${l.inv_series || ""}</td>
              <td>${l.inv_no}</td>
              <td>${formatDate(l.inv_date)}</td>
              <td class="num">${formatVND(l.amount_before_vat)}</td>
              <td class="num">${formatVND(l.vat_amount)}</td>
              <td class="num">${formatVND(l.total_amount)}</td>
              <td class="kt-sub"><code>${l.pdf_name}</code></td>
            </tr>`)}</tbody>
          </table></div>
          ${res.n_lines > lines.length
            ? html`<div class="kt-sub" style="margin-top:6px">…và ${res.n_lines - lines.length} hóa đơn nữa</div>`
            : ""}
        </div></div>`}

    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="hp-close">Đóng</button>
      <button class="kt-btn kt-btn--primary" id="hp-commit" ${!res.can_commit ? "disabled" : ""}>
        <i class="fas fa-check"></i> Lập hồ sơ ${res.n_lines} hóa đơn
      </button>
    </div>
    <div id="hp-msg"></div>`);

  modal.body.querySelector("#hp-close").addEventListener("click", () => modal.close());
  modal.body.querySelector("#hp-refresh").addEventListener("click", () => {
    st.from = modal.body.querySelector("#hp-from").value;
    st.to = modal.body.querySelector("#hp-to").value;
    st.submit = modal.body.querySelector("#hp-submit").value;
    st.no = Number(modal.body.querySelector("#hp-no").value) || 1;
    st.vendor = modal.body.querySelector("#hp-vendor").value.trim();
    renderWinPreview(container, state, modal, st);
  });

  const btn = modal.body.querySelector("#hp-commit");
  if (btn) btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const out = await api.mtWinCommit({
        from_date: st.from, to_date: st.to, submit_date: st.submit,
        dossier_no: st.no, vendor_code: res.vendor_code,
        expected_hash: res.plan_hash,
      });
      toast(out.message, "success");
      modal.close();
      await loadTab(container, state);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#hp-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}

// ── Một hồ sơ: xem, xuất Excel, đánh dấu đã nộp ────────────────────────────
async function openWinDetail(container, state, name) {
  const modal = openModal({
    title: "Hồ sơ thanh toán Winmart",
    icon: "fa-folder-open",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderWinDetail(container, state, modal, name);
}

async function renderWinDetail(container, state, modal, name) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtWinDossier(name);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const d = res.doc || {};
  const lines = res.lines || [];
  const draft = d.status === "Nháp";

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <b><code>${d.file_prefix}</code></b>
        <span class="kt-badge kt-badge--${WIN_TONE[d.status] || "gray"}">${d.status}</span>
        <span class="kt-sub">nộp ${formatDate(d.submit_date)} · mã NCC ${d.vendor_code}</span>
        <b style="margin-left:auto">${formatVND(d.total_amount)}</b>
      </div>
      <div class="kt-sub" style="margin-top:8px">
        <b>File PDF hóa đơn nộp kèm phải đặt tên đúng <code>${d.file_prefix}</code></b> —
        sai tên là Win trả hồ sơ và cả đợt trượt kỳ thanh toán.
      </div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap" style="max-height:320px;overflow:auto"><table class="kt-table">
        <thead><tr>${(res.columns || []).map((c) => html`<th>${c}</th>`)}</tr></thead>
        <tbody>${lines.map((l) => html`<tr>
          <td>${l.stt}</td><td>${d.vendor_code}</td>
          <td>${l.po_vcm || html`<span class="kt-badge kt-badge--yellow">thiếu PO</span>`}</td>
          <td>${l.inv_series || ""}</td><td>${l.inv_no}</td>
          <td>${formatDate(l.inv_date)}</td>
          <td class="num">${formatVND(l.amount_before_vat)}</td>
          <td class="num">${formatVND(l.vat_amount)}</td>
          <td class="num">${formatVND(l.total_amount)}</td>
          <td class="kt-sub"><code>${l.pdf_name}</code></td>
        </tr>`)}</tbody>
      </table></div>
    </div></div>

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
      <a class="kt-btn kt-btn--outline kt-btn--sm" href="/app/mt-win-dossier/${d.name}" target="_blank">
        <i class="fas fa-arrow-up-right-from-square"></i> Desk</a>
      <button class="kt-btn kt-btn--outline" id="hd-close">Đóng</button>
      <button class="kt-btn kt-btn--outline" id="hd-export">
        <i class="fas fa-file-excel"></i> Xuất Excel nộp Win</button>
      ${draft && res.can_manage
        ? html`<button class="kt-btn kt-btn--primary" id="hd-submit">
            <i class="fas fa-paper-plane"></i> Đánh dấu đã nộp</button>`
        : ""}
    </div>
    <div id="hd-msg"></div>`);

  modal.body.querySelector("#hd-close").addEventListener("click", () => modal.close());
  modal.body.querySelector("#hd-export").addEventListener("click", async () => {
    try {
      await api.mtWinExport(name);
    } catch (e) {
      setHTML(modal.body.querySelector("#hd-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub">${e.message}</div></div></div>`);
    }
  });
  const sb = modal.body.querySelector("#hd-submit");
  if (sb) sb.addEventListener("click", async () => {
    sb.disabled = true;
    try {
      const out = await api.mtWinSubmitted(name);
      toast(out.message, "success");
      await renderWinDetail(container, state, modal, name);
      await loadTab(container, state);
    } catch (e) {
      sb.disabled = false;
      setHTML(modal.body.querySelector("#hd-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub">${e.message}</div></div></div>`);
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB — CÔNG NỢ ĐẾN HẠN (SOP §5, việc hàng tuần)
//
// Màn hình này quyết định GỌI ĐIỆN ĐÒI AI, nên hai thứ phải hiện ngay, không
// giấu trong tooltip:
//   1. Số còn nợ tính từ BẢNG KÊ CHUỖI, không phải số dư TK 131 trên sổ cái.
//   2. Khách CHƯA KHAI HẠN có bao nhiêu tiền treo. Nợ của họ không bao giờ vào
//      rổ quá hạn, nên nếu không đếm riêng thì nó im lặng biến mất.
// ═══════════════════════════════════════════════════════════════════════════

// Trong bàn làm việc, chuỗi do ĐIỀU HƯỚNG quyết định — không để bộ lọc cũ của
// màn hình toàn kênh lọc ngầm dữ liệu của chuỗi đang mở.
const dueChainOf = (state) =>
  (state.view === "chuoi" ? state.chain : state.dueChain) || undefined;

// Trục HÓA ĐƠN ĐIỆN TỬ trên màn Công nợ đến hạn.
//
// Bộ lọc này áp cho CẢ tổng hợp lẫn danh sách (`get_due_summary` và
// `get_due_invoices` gọi chung `_filter_einvoice`), nên mọi con số trên màn —
// kể cả "Còn nợ" ở đầu trang và các rổ tuổi nợ — đều nói về đúng tập đang xem.
// Vì thế phải NÓI RA là đang lọc: một màn hình bị lọc ngầm là cách chắc chắn
// nhất để kế toán chép nhầm một con số vào báo cáo.
function dueEinvBar(state, sum, list) {
  const cur = state.dueEinv || "";
  const asked = !!cur;
  const applied = !!(list && list.einvoice_applied);

  if (asked && !applied) {
    return html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
        <div class="kt-card-body">
          <div style="font-weight:600;color:var(--kt-danger)">
            <i class="fas fa-filter-circle-xmark"></i> KHÔNG lọc được theo hóa đơn điện tử
          </div>
          <div class="kt-sub" style="margin-top:6px">
            Site chưa có ô số HĐĐT trên Sales Invoice nên không biết tờ nào đã xuất.
            Danh sách dưới đây là <b>toàn bộ</b> hóa đơn còn nợ, không phải phần đã lọc.
            <button class="kt-btn kt-btn--outline kt-btn--sm" id="dd-einv-clear"
                    style="margin-left:8px">Bỏ lọc</button>
          </div>
        </div></div>`;
  }
  if (!sum.einv_known) return "";

  const be = sum.by_einvoice || {};
  const issued = be.issued || {};
  const pending = be.pending || {};
  return html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="kt-sub">Theo đầu hóa đơn điện tử:</span>
        <button class="kt-btn kt-btn--sm ${cur ? "kt-btn--outline" : ""}" data-einv="">Tất cả</button>
        <button class="kt-btn kt-btn--sm ${cur === "da" ? "" : "kt-btn--outline"}" data-einv="da">
          Đã xuất — đòi được</button>
        <button class="kt-btn kt-btn--sm ${cur === "chua" ? "" : "kt-btn--outline"}" data-einv="chua">
          Chưa xuất — chưa đòi được</button>
      </div>
      ${cur
        ? html`<div class="kt-sub" style="margin-top:8px;color:var(--kt-warning)">
            <i class="fas fa-filter"></i>
            Đang lọc: chỉ hóa đơn <b>${cur === "chua" ? "CHƯA" : "ĐÃ"} xuất hóa đơn điện tử</b>.
            Mọi con số trên màn này — kể cả <b>Còn nợ</b> ở đầu trang và các rổ tuổi nợ —
            đều là của riêng phần đang lọc.
          </div>`
        : html`<div class="kt-sub" style="margin-top:8px">
            Đòi được <b style="color:var(--kt-success)">${formatVND(issued.amount || 0)}</b>
            / ${issued.count || 0} HĐ ·
            chưa đòi được <b style="color:var(--kt-danger)">${formatVND(pending.amount || 0)}</b>
            / ${pending.count || 0} HĐ${pending.oldest
              ? html` · tờ cũ nhất ${formatDate(pending.oldest)}`
              : ""}.
            Hai vế cộng lại đúng bằng ${formatVND(sum.total)} ở trên.
          </div>`}
    </div></div>`;
}

async function loadDueDebt(container, state) {
  const body = container.querySelector("#mt-body");
  let sum;
  try {
    sum = await api.mtDueSummary({ as_of: state.dueAsOf || undefined,
                                   chain: dueChainOf(state),
                                   search: state.search || undefined,
                                   einvoice: state.dueEinv || undefined });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  state.dueAsOf = sum.as_of;
  state.dueBucket = state.dueBucket || "tat_ca";

  let list;
  try {
    list = await api.mtDueInvoices({
      as_of: state.dueAsOf, chain: dueChainOf(state),
      search: state.search || undefined,
      bucket: state.dueBucket, page: state.page, page_size: 50,
      einvoice: state.dueEinv || undefined,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = list.rows || [];

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <label class="kt-sub">Tính đến ngày</label>
        <input type="date" class="kt-input kt-input--sm" id="dd-asof" value="${sum.as_of}">
        <span class="kt-sub">·</span>
        <span>Còn nợ <b>${formatVND(sum.total)}</b> / ${sum.total_count} HĐ</span>
        <span class="kt-sub">·</span>
        <span>Quá hạn <b style="color:var(--kt-danger)">${formatVND(sum.overdue)}</b>
              / ${sum.overdue_count} HĐ</span>
        ${state.view !== "chuoi" && state.dueChain
          ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="dd-clear-chain">
              <i class="fas fa-xmark"></i> chỉ chuỗi ${state.dueChain}
            </button>`
          : ""}
        ${sum.orphan_return_count
          ? html`<span class="kt-badge kt-badge--yellow"
                   title="Phiếu trả hàng không khai 'trả cho hóa đơn nào' thì không trừ được vào hóa đơn gốc — công nợ đang cao hơn thực tế đúng bằng số này. Mở phiếu, điền Return Against rồi số tự đúng.">
              ${sum.orphan_return_count} phiếu trả hàng chưa khai HĐ gốc ·
              ${formatVNDShort(sum.orphan_return_amount)}
            </span>`
          : ""}
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="dd-terms" style="margin-left:auto">
          <i class="fas fa-sliders"></i> Khai hạn thanh toán
        </button>
      </div>
      <div class="kt-sub" style="margin-top:8px">${sum.basis_note}</div>
      ${sum.unknown_term_count
        ? html`<div class="kt-sub" style="margin-top:6px;color:var(--kt-warning)">
            <i class="fas fa-triangle-exclamation"></i>
            ${sum.unknown_term_count} hóa đơn (${formatVND(sum.unknown_term_amount)})
            thuộc khách CHƯA KHAI HẠN — chúng không bao giờ vào rổ quá hạn.
            Bấm <b>Khai hạn thanh toán</b> để điền.
          </div>`
        : ""}
      ${sum.due_conflicts
        ? html`<div class="kt-sub" style="margin-top:6px;color:var(--kt-warning)">
            <i class="fas fa-code-compare"></i>
            ${sum.due_conflicts} hóa đơn có hạn khai trên khách KHÁC với hạn ghi trên
            hóa đơn. Màn hình lấy hạn khai trên khách; kiểm lại xem chỗ nào sai.
          </div>`
        : ""}
    </div></div>

    ${dueEinvBar(state, sum, list)}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="kt-btn kt-btn--sm ${state.dueBucket === "tat_ca" ? "" : "kt-btn--outline"}"
                data-bucket="tat_ca">Tất cả · ${formatVNDShort(sum.total)}</button>
        ${(sum.buckets || []).map((b) => html`
          <button class="kt-btn kt-btn--sm ${state.dueBucket === b.key ? "" : "kt-btn--outline"}"
                  data-bucket="${b.key}">
            ${b.label} · ${b.count} · ${formatVNDShort(b.amount)}
          </button>`)}
      </div>
    </div></div>

    ${(sum.chains || []).length > 1
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th class="kt-col-mid">Chuỗi</th><th class="num">Số HĐ</th>
              <th class="num">Còn nợ</th><th class="num">Trong đó quá hạn</th>
              ${sum.einv_known
                ? html`<th class="num">Đòi được<div class="kt-sub">đã xuất HĐĐT</div></th>
                       <th class="num">Chưa đòi được<div class="kt-sub">chưa xuất HĐĐT</div></th>`
                : ""}
              <th class="num">HĐ chưa khai hạn</th></tr></thead>
            <tbody>${sum.chains.map((c) => html`<tr class="dd-chain" data-chain="${c.chain}"
                  style="cursor:pointer" title="bấm để chỉ xem chuỗi này">
              <td class="kt-col-mid">${c.chain || html`<span class="kt-sub">(chưa gán chuỗi)</span>`}</td>
              <td class="num">${c.count}</td>
              <td class="num">${formatVND(c.amount)}</td>
              <td class="num">${c.overdue ? html`<b style="color:var(--kt-danger)">${formatVND(c.overdue)}</b>` : "—"}</td>
              ${sum.einv_known
                ? html`<td class="num">${c.einv_known
                        ? html`<span style="color:var(--kt-success)">${formatVND(c.einv_issued)}</span>
                               <div class="kt-sub">${c.einv_issued_n || 0} HĐ</div>`
                        : html`<span class="kt-sub">—</span>`}</td>
                       <td class="num">${c.einv_known && c.einv_pending
                        ? html`<b style="color:var(--kt-danger)">${formatVND(c.einv_pending)}</b>
                               <div class="kt-sub">${c.einv_pending_n || 0} HĐ${
                                 c.einv_pending_oldest ? html` · từ ${formatDate(c.einv_pending_oldest)}` : ""}</div>`
                        : html`<span class="kt-sub">—</span>`}</td>`
                : ""}
              <td class="num">${c.unknown_term || "—"}</td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`
      : ""}

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-clock"></i>
          <p>Không có hóa đơn nào trong rổ này.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Hóa đơn</th><th>Khách hàng</th><th>Ngày HĐ</th>
              <th>Đến hạn</th><th class="num">Trễ (ngày)</th>
              <th class="num">Tổng HĐ</th><th class="num">Còn nợ</th><th>Rổ</th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><a href="/app/sales-invoice/${r.name}" target="_blank">${r.name}</a></td>
                <td>${r.customer_name || r.customer}
                  ${r.chain ? html`<div class="kt-sub">${r.chain}</div>` : ""}</td>
                <td>${formatDate(r.posting_date)}</td>
                <td>${r.due_date ? formatDate(r.due_date) : html`<span class="kt-sub">chưa khai</span>`}
                  ${r.due_conflict ? html`<i class="fas fa-code-compare" title="hạn khai trên khách khác hạn trên hóa đơn"></i>` : ""}
                  ${r.due_source === "hoa_don" ? html`<div class="kt-sub">theo hóa đơn</div>` : ""}</td>
                <td class="num">${r.days_overdue === null || r.days_overdue === undefined
                  ? "—"
                  : (r.days_overdue > 0
                      ? html`<b style="color:var(--kt-danger)">${r.days_overdue}</b>`
                      : html`<span class="kt-sub">${r.days_overdue}</span>`)}</td>
                <td class="num">${formatVND(r.grand_total)}
                  ${r.returned
                    ? html`<div class="kt-sub" title="đã làm phiếu trả hàng trên ERPNext — đã trừ khỏi số còn nợ">
                        − trả lại ${formatVNDShort(r.returned)}</div>`
                    : ""}</td>
                <td class="num"><b>${formatVND(r.remaining)}</b>
                  ${r.paid_review
                    ? html`<div class="kt-sub" title="dòng bảng kê máy đoán, chưa ai chốt — chưa trừ vào nợ">
                        chờ chốt ${formatVNDShort(r.paid_review)}</div>`
                    : ""}</td>
                <td><span class="kt-badge kt-badge--${DUE_TONE[r.bucket] || "gray"}">${r.bucket_label}</span></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(list, "hóa đơn")}
        </div></div>`}
  `);

  bindPager(container, state);
  container.querySelector("#dd-asof").addEventListener("change", (e) => {
    state.dueAsOf = e.target.value; state.page = 1; loadTab(container, state);
  });
  container.querySelectorAll("button[data-bucket]").forEach((b) => {
    b.addEventListener("click", () => {
      state.dueBucket = b.dataset.bucket; state.page = 1; loadTab(container, state);
    });
  });
  container.querySelectorAll("button[data-einv]").forEach((b) => {
    b.addEventListener("click", () => {
      state.dueEinv = b.dataset.einv; state.page = 1;
      syncHash(state); loadTab(container, state);
    });
  });
  const ec = container.querySelector("#dd-einv-clear");
  if (ec) ec.addEventListener("click", () => {
    state.dueEinv = ""; state.page = 1; syncHash(state); loadTab(container, state);
  });
  const cc = container.querySelector("#dd-clear-chain");
  if (cc) cc.addEventListener("click", () => {
    state.dueChain = ""; state.page = 1; loadTab(container, state);
  });
  container.querySelectorAll("tr.dd-chain").forEach((tr) => {
    tr.addEventListener("click", () => {
      if (state.view === "chuoi") return;   // đã ở trong một chuỗi rồi
      // Chuỗi rỗng = khách chưa gán chuỗi; lọc theo nó thì backend bỏ qua bộ lọc
      // và trả về TOÀN BỘ — im lặng sai. Chặn ngay ở đây.
      if (!tr.dataset.chain) return;
      state.dueChain = tr.dataset.chain; state.page = 1; loadTab(container, state);
    });
  });
  container.querySelector("#dd-terms")
    .addEventListener("click", () => openCreditTerms(container, state));
}

// ═══════════════════════════════════════════════════════════════════════════
// MÀN — SOÁT HÓA ĐƠN BỎ SÓT SỐ HÓA ĐƠN ĐIỆN TỬ
//
// KHÔNG phải con số của thẻ "hai cuốn sổ". Thẻ kia chỉ nhìn phần CÒN NỢ; màn
// này nhìn MỌI hóa đơn bán, vì hóa đơn đã thu đủ tiền mà trống ô số HĐĐT vẫn
// là một lỗ hổng chứng từ. Hai con số không bao giờ bằng nhau — màn hình phải
// nói ra điều đó, không thì có ngày ai đó đem hai màn đi đối chiếu.
//
// Cả màn xoay quanh MỘT phép chia: bỏ sót ≠ chưa tới lượt. Và vì phép chia đó
// dựa trên một PHỎNG ĐOÁN (xuất hóa đơn theo thứ tự thời gian), cái mốc luôn
// được in ra để người đọc tự thấy con số tin được tới đâu.
// ═══════════════════════════════════════════════════════════════════════════

function frontierLine(f, chain) {
  if (!f) {
    return html`<span class="kt-sub">chưa hóa đơn nào của ${chain || "kênh"} có số HĐĐT —
      không có mốc nên KHÔNG chấm bỏ sót cho ai</span>`;
  }
  return html`<span class="kt-sub">mốc: <a href="/app/sales-invoice/${f.name}"
      target="_blank">${f.name}</a> ngày <b>${formatDate(f.posting_date)}</b>${
      f.inv_no ? html` · số ${f.inv_series ? f.inv_series + " " : ""}${f.inv_no}` : ""}</span>`;
}

async function loadEinvGaps(container, state) {
  const body = container.querySelector("#mt-body");
  let d;
  try {
    await ensureEinvOpts(state, state.gapChain);
    d = await api.mtEinvGaps({ chain: state.gapChain || undefined,
                               page: state.page, page_size: 50,
                               ...(state.einvFilter || {}) });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  if (!d.supported) {
    setHTML(body, html`<div class="kt-empty"><i class="fas fa-plug-circle-xmark"></i>
      <p>${d.note}</p></div>`);
    return;
  }

  const rows = d.rows || [];
  setHTML(body, html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
      <div class="kt-card-body kt-sub">
        <b>Đây KHÔNG phải con số của thẻ "hai cuốn sổ".</b>
        Thẻ kia chỉ nhìn phần <b>còn nợ</b>; màn này nhìn <b>mọi hóa đơn bán</b>, vì hóa đơn
        đã thu đủ tiền mà trống ô số HĐĐT vẫn là lỗ hổng chứng từ. Hai con số không bao giờ
        bằng nhau — đừng đem đối chiếu.
      </div></div>

    <div class="kt-stats kt-mb">
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-triangle-exclamation"></i> BỎ SÓT — đã đi qua mà không xuất</div>
        <div class="kt-stat-value ${d.missed.count ? "neg" : "pos"}">${d.missed.count}</div>
        <div class="kt-stat-sub">${formatVND(d.missed.amount)} · cũ hơn tờ mới nhất đã điền số</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-hourglass-half"></i> Chưa tới lượt</div>
        <div class="kt-stat-value">${d.backlog.count}</div>
        <div class="kt-stat-sub">${formatVND(d.backlog.amount)} · mới hơn mốc — bình thường,
          không phải việc phải soát</div>
      </div>
      ${d.returns_missing.count
        ? html`<div class="kt-stat">
            <div class="kt-stat-label"><i class="fas fa-rotate-left"></i> Phiếu trả hàng trống số</div>
            <div class="kt-stat-value warn">${d.returns_missing.count}</div>
            <div class="kt-stat-sub">${formatVND(d.returns_missing.amount)} · KHÔNG nằm trong hai
              ô bên trái — hóa đơn điều chỉnh/thay thế MISA đi theo luật khác</div>
          </div>`
        : ""}
    </div>

    ${state.gapChain
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body"
              style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <span>Đang xem <b>${state.gapChain}</b></span>
          ${frontierLine(d.frontier, state.gapChain)}
          <button class="kt-btn kt-btn--outline kt-btn--sm" id="gap-clear"
                  style="margin-left:auto">Xem mọi chuỗi</button>
        </div></div>`
      : (d.chains || []).length
        ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
            <div class="kt-sub" style="margin-bottom:8px">
              <b>Mốc tính RIÊNG từng chuỗi.</b> Mỗi chuỗi có nhịp xuất hóa đơn riêng —
              lấy một mốc chung thì chuỗi xuất chậm nhất bị chấm bỏ sót toàn bộ, còn chuỗi
              xuất nhanh không bao giờ lộ lỗ hổng nào.
            </div>
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr><th class="kt-col-mid">Chuỗi</th>
                <th class="num">Bỏ sót</th><th class="num">Chưa tới lượt</th>
                <th class="kt-col-wide">Đã điền tới đâu</th></tr></thead>
              <tbody>${d.chains.map((c) => html`<tr class="gap-chain" data-chain="${c.chain}"
                    style="cursor:${c.chain ? "pointer" : "default"}">
                <td class="kt-col-mid">${c.chain
                  || html`<span style="color:var(--kt-warning)">(chưa gán chuỗi)</span>`}</td>
                <td class="num">${c.missed.count
                  ? html`<b style="color:var(--kt-danger)">${c.missed.count}</b>
                      <div class="kt-sub">${formatVND(c.missed.amount)}</div>`
                  : html`<span class="kt-sub">—</span>`}</td>
                <td class="num">${c.backlog.count || html`<span class="kt-sub">—</span>`}
                  ${c.backlog.count ? html`<div class="kt-sub">${formatVND(c.backlog.amount)}</div>` : ""}</td>
                <td class="kt-col-wide">${frontierLine(c.frontier, c.chain)}</td>
              </tr>`)}</tbody>
            </table></div>
          </div></div>`
        : ""}

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i>
          <p>Không có hóa đơn nào bị bỏ sót số HĐĐT${state.gapChain ? ` ở ${state.gapChain}` : ""}.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:8px">Bỏ sót lâu nhất lên trước — đó là thứ tự đi soát.</div>
          ${einvFilterBar(d.filters || {}, state.einvOpts)}
          ${einvFilterNote(d)}
          <div class="kt-table-wrap"><table class="kt-table">
            <thead>${einvHead}</thead>
            <tbody>${rows.map((r) => einvRow(r, state.canManage, true))}</tbody>
          </table></div>
          ${pager(d, "hóa đơn")}
          ${skippedBar(d)}
        </div></div>`}
  `);

  bindPager(container, state);
  bindEinvSkip(container, container, state, () => loadTab(container, state));
  bindEinvFilter(container, state, (f) => {
    state.einvFilter = f;
    state.page = 1;
    loadTab(container, state);
  });
  const gc = container.querySelector("#gap-clear");
  if (gc) gc.addEventListener("click", () => {
    state.gapChain = ""; state.einvFilter = {};
    state.einvOpts = null; state.einvOptsFor = null;
    state.page = 1; loadTab(container, state);
  });
  container.querySelectorAll("tr.gap-chain").forEach((tr) => {
    tr.addEventListener("click", () => {
      // Chuỗi rỗng = khách chưa gán chuỗi. Lọc theo nó thì backend bỏ qua bộ
      // lọc và trả về TOÀN BỘ — im lặng sai. Chặn ngay ở đây.
      if (!tr.dataset.chain) return;
      // Đổi chuỗi thì tùy chọn ô lọc CŨ không còn đúng, và bộ lọc đang bật có
      // thể trỏ vào pháp nhân của chuỗi khác -> danh sách trống mà không hiểu vì sao.
      state.gapChain = tr.dataset.chain;
      state.einvFilter = {};
      state.einvOpts = null;
      state.einvOptsFor = null;
      state.page = 1;
      loadTab(container, state);
    });
  });
}

// Nạp tùy chọn ô lọc MỘT LẦN cho mỗi chuỗi. Gọi lại mỗi lần vẽ là một truy vấn
// quét toàn bộ hóa đơn cho một cái combobox không đổi.
async function ensureEinvOpts(state, chain) {
  const key = chain || "";
  if (state.einvOptsFor === key && state.einvOpts) return state.einvOpts;
  try {
    state.einvOpts = await api.mtEinvFilterOptions(chain || undefined);
    state.einvOptsFor = key;
  } catch (_e) {
    // Ô lọc thiếu lựa chọn thì vẫn tìm được bằng ô chữ — không chặn cả màn.
    state.einvOpts = { customers: [], stores: [] };
  }
  return state.einvOpts;
}

// ═══════════════════════════════════════════════════════════════════════════
// SỔ THEO DÕI HÓA ĐƠN — cuốn Excel kế toán vẫn giữ, dựng lại trong phần mềm
//
// Một dòng mỗi hóa đơn, các cột đi từ TRÁI SANG PHẢI theo đời của tờ hóa đơn:
//
//     hàng đã đi  →  hóa đơn MISA  →  trả hàng  →  phải thu  →  đã nhận  →  còn lại
//
// Đây là chỗ LÀM VIỆC, không phải báo cáo. Nên nó ưu tiên: liếc mắt biết tờ nào
// đang ở đâu (cột trạng thái), và bấm một cái là ra đời của tờ đó.
//
// ⚠ Cột "Còn lại" cộng lại là công nợ CỦA CÁC TỜ TRONG KỲ ĐANG XEM, không phải
// số dư công nợ — số dư nằm ở màn Công nợ đến hạn. Câu đó in trên màn, vì hai
// con số gần giống nhau mà khác nghĩa là chỗ dễ chép nhầm vào báo cáo nhất.
// ═══════════════════════════════════════════════════════════════════════════

// Tick CHIẾT KHẤU — bốn trạng thái, bốn nghĩa khác nhau.
//
// "Chưa biết" (chưa đợt nào trả tờ này) KHÁC "Không" (đợt đã trả, không có
// khoản trừ nào). Gộp lại thì hóa đơn chưa thanh toán hiện dấu "không có chiết
// khấu", và kế toán đọc thành đã kiểm rồi.
//
// Không hiện SỐ TIỀN ở đây: khoản trừ bị trừ trên TỔNG ĐỢT, chia cho từng tờ là
// bịa. Muốn xem số thì bấm Chi tiết — nó bày ở đúng tầng đợt.
const DISCOUNT_MARK = {
  co: html`<span style="color:var(--kt-success)" title="có khoản trừ gắn đích danh tờ này">
      <i class="fas fa-square-check"></i></span>`,
  theo_dot: html`<span style="color:var(--kt-warning)" title="đợt trả tờ này có khoản trừ, nhưng của cả đợt">
      <i class="fas fa-square-minus"></i></span>`,
  khong: html`<span class="kt-sub" title="đợt trả tờ này không có khoản trừ nào">
      <i class="far fa-square"></i></span>`,
  chua: html`<span class="kt-sub" title="chưa đợt nào trả tờ này — chưa biết">—</span>`,
};

const LED_TONE = {
  chua_xuat_hddt: "red",
  chua_thu: "yellow",
  thu_mot_phan: "yellow",
  da_thu_du: "green",
};

async function loadLedger(container, state) {
  const body = container.querySelector("#mt-body");
  let d;
  try {
    d = await api.mtLedger({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined,
      customer: state.customer || undefined,
      status: state.ledStatus || undefined,
      q: state.ledQ || undefined,
      page: state.ledPage || 1, page_size: 50,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const t = d.totals || {};
  const bs = d.by_status || {};
  const rows = d.rows || [];

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <input class="kt-input kt-input--sm" id="led-q" style="min-width:260px"
               placeholder="Tìm số HĐ MISA / chứng từ / PO / khách / điểm giao…"
               value="${d.q || ""}">
        <button class="kt-btn kt-btn--sm" id="led-go"><i class="fas fa-magnifying-glass"></i> Tìm</button>
        ${d.q ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="led-clear">Bỏ tìm</button>` : ""}
        <span class="kt-sub" style="margin-left:auto">${t.count} hóa đơn ·
          ngày HĐ ${formatDate(d.from_date)} → ${formatDate(d.to_date)}</span>
      </div>
      <div class="kt-sub" style="margin-top:8px">${d.note}</div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <button class="kt-btn kt-btn--sm ${d.status ? "kt-btn--outline" : ""}"
              data-led="">Tất cả · ${t.count}</button>
      ${Object.keys(d.status_label).map((k) => html`
        <button class="kt-btn kt-btn--sm ${d.status === k ? "" : "kt-btn--outline"}"
                data-led="${k}">${d.status_label[k]} · ${(bs[k] || {}).count || 0}</button>`)}
    </div></div>

    <div class="kt-stats kt-mb">
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-file-invoice"></i> Tiền hóa đơn trong kỳ</div>
        <div class="kt-stat-value">${formatVNDShort(t.grand_total)}</div>
        <div class="kt-stat-sub">${formatVND(t.grand_total)}</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-rotate-left"></i> Hàng trả lại</div>
        <div class="kt-stat-value ${t.returned ? "warn" : ""}">${formatVNDShort(t.returned)}</div>
        <div class="kt-stat-sub">phải thu còn ${formatVND(t.net_due)}</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-hand-holding-dollar"></i> Đã nhận</div>
        <div class="kt-stat-value pos">${formatVNDShort(t.paid)}</div>
        <div class="kt-stat-sub">${formatVND(t.paid)}</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-hourglass-half"></i> Còn lại của kỳ này</div>
        <div class="kt-stat-value ${t.remaining ? "neg" : ""}">${formatVNDShort(t.remaining)}</div>
        <div class="kt-stat-sub">KHÔNG phải số dư công nợ</div>
      </div>
    </div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-book-open"></i>
          <p>Không có hóa đơn nào trong kỳ và bộ lọc đang chọn.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th class="kt-col-mid">Hóa đơn MISA</th>
              <th class="kt-col-wide">Hàng / chứng từ ERPNext</th>
              <th class="num">Tiền HĐ</th>
              <th class="num">Trả hàng</th>
              <th class="num">Phải thu</th>
              <th class="num">Đã nhận</th>
              <th class="num">Còn lại</th>
              <th>CK</th>
              <th>Đợt thanh toán</th>
              <th>Trạng thái</th>
            </tr></thead>
            <tbody>${rows.map((r) => ledgerRow(r, state))}</tbody>
          </table></div>
          ${pager(d, "hóa đơn")}
        </div></div>`}
  `);

  const go = () => {
    state.ledQ = (container.querySelector("#led-q") || {}).value || "";
    state.ledPage = 1;
    loadTab(container, state);
  };
  const gb = container.querySelector("#led-go");
  if (gb) gb.addEventListener("click", go);
  const qi = container.querySelector("#led-q");
  if (qi) qi.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  const cl = container.querySelector("#led-clear");
  if (cl) cl.addEventListener("click", () => {
    state.ledQ = ""; state.ledPage = 1; loadTab(container, state);
  });
  container.querySelectorAll("button[data-led]").forEach((b) => {
    b.addEventListener("click", () => {
      state.ledStatus = b.dataset.led; state.ledPage = 1; loadTab(container, state);
    });
  });
  container.querySelectorAll("button[data-trace]").forEach((b) => {
    b.addEventListener("click", () => openTrace(b.dataset.trace));
  });
  // Phân trang RIÊNG: sổ này dùng `ledPage`, không chung `state.page` với các
  // bước khác — chung là lật trang ở đây thì bước kia cũng nhảy theo.
  container.querySelectorAll("button[data-page]").forEach((b) => {
    b.addEventListener("click", () => {
      state.ledPage = parseInt(b.dataset.page, 10) || 1;
      loadTab(container, state);
    });
  });
}

function ledgerRow(r, state) {
  const adv = r.advices || [];
  return html`<tr>
    <td class="kt-col-mid">${r.misa_no
      ? html`<b>${r.misa_series ? r.misa_series + " " : ""}${r.misa_no}</b>`
      : html`<span style="color:var(--kt-danger)">chưa có số</span>`}
      <div class="kt-sub">${formatDate(r.posting_date)}</div>
      ${r.misa_status ? html`<div class="kt-sub">${r.misa_status}</div>` : ""}</td>
    <td class="kt-col-wide">
      <a href="/app/sales-invoice/${r.name}" target="_blank">${r.name}</a>
      <div class="kt-sub">${r.customer_name || r.customer}</div>
      ${r.po_no ? html`<div class="kt-sub">PO <code>${r.po_no}</code></div>` : ""}
      ${r.ship_to ? html`<div class="kt-sub"><i class="fas fa-location-dot"></i> ${r.ship_to}</div>` : ""}</td>
    <td class="num">${formatVND(r.grand_total)}</td>
    <td class="num">${r.returned
      ? html`<span style="color:var(--kt-warning)">−${formatVND(r.returned)}</span>
          <div class="kt-sub">${r.n_returns} phiếu</div>
          ${r.returns_no_misa
            ? html`<div class="kt-sub" style="color:var(--kt-danger)"
                     title="Phiếu trả đã ghi trên ERPNext nhưng chưa có hóa đơn thay thế / điều chỉnh nào trên MISA. Bấm Chi tiết để xem.">
                <i class="fas fa-triangle-exclamation"></i> ${r.returns_no_misa} chưa có HĐ</div>`
            : ""}`
      : html`<span class="kt-sub">—</span>`}</td>
    <td class="num"><b>${formatVND(r.net_due)}</b></td>
    <td class="num">${r.paid_net
      ? html`<span style="color:var(--kt-success)">${formatVND(r.paid_net)}</span>`
      : html`<span class="kt-sub">—</span>`}
      ${r.paid_review
        ? html`<div class="kt-sub" style="color:var(--kt-warning)"
                 title="dòng bảng kê máy đoán, chưa ai chốt — CHƯA trừ vào nợ">
            chờ chốt ${formatVNDShort(r.paid_review)}</div>`
        : ""}</td>
    <td class="num">${r.remaining
      ? html`<b style="color:var(--kt-danger)">${formatVND(r.remaining)}</b>`
      : html`<span class="kt-sub">—</span>`}</td>
    <td class="kt-col-role" title="${r.discount_note || ""}">${DISCOUNT_MARK[r.discount] || ""}</td>
    <td>${adv.length
      ? adv.map((a) => html`<div class="kt-sub">
          <a href="/app/mt-payment-advice/${a.advice}" target="_blank">${a.advice_no || a.advice}</a>
          ${a.payment_date ? html` · ${formatDate(a.payment_date)}` : ""}</div>`)
      : html`<span class="kt-sub">—</span>`}</td>
    <td><span class="kt-badge kt-badge--${LED_TONE[r.status] || "gray"}">${r.status_label}</span>
      <div style="margin-top:4px">
        <button class="kt-btn kt-btn--outline kt-btn--sm" data-trace="${r.name}">Chi tiết</button>
      </div></td>
  </tr>`;
}

// Đời của MỘT tờ hóa đơn. Đây là cái kế toán mở khi chuỗi gọi hỏi về một tờ.
async function openTrace(name) {
  const modal = openModal({
    title: `Đời của hóa đơn ${name}`,
    icon: "fa-timeline",
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let d;
  try {
    d = await api.mtLedgerTrace(name);
  } catch (e) {
    return setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
  }
  setHTML(modal.body, html`
    ${d.returns.length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div style="font-weight:600;margin-bottom:6px">
            <i class="fas fa-rotate-left"></i> Hóa đơn xuất trả —
            ${formatVND(d.returned_total)}</div>
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Phiếu trả</th><th>Ngày</th><th class="num">Số tiền</th>
              <th class="kt-col-wide">Chứng từ MISA đi kèm</th></tr></thead>
            <tbody>${d.returns.map((r) => html`<tr>
              <td><a href="/app/sales-invoice/${r.name}" target="_blank">${r.name}</a></td>
              <td>${formatDate(r.posting_date)}</td>
              <td class="num">${formatVND(r.amount)}</td>
              <td class="kt-col-wide">${r.misa_missing
                ? html`<b style="color:var(--kt-danger)">CHƯA CÓ</b>
                    <div class="kt-sub">phiếu trả đã ghi trên ERPNext, nhưng chưa có
                      hóa đơn thay thế / điều chỉnh của mình, cũng chưa trỏ được sang
                      hóa đơn trả do siêu thị xuất trên bảng kê</div>`
                : r.chain_inv_no
                ? html`<b>Siêu thị xuất</b>
                    <div class="kt-sub">HĐ ${r.chain_inv_no} · bảng kê
                      <a href="/app/mt-payment-advice/${r.chain_advice}"
                         target="_blank">${r.chain_advice}</a></div>`
                : html`${r.misa_relation || "—"}
                    ${r.misa_no ? html`<div class="kt-sub">
                      ${r.misa_series ? r.misa_series + " " : ""}${r.misa_no}</div>` : ""}
                    ${r.misa_status ? html`<div class="kt-sub">${r.misa_status}</div>` : ""}`}</td>
            </tr>`)}</tbody>
          </table></div>
          <div class="kt-sub" style="margin-top:10px;white-space:pre-line">${d.return_note}</div>
        </div></div>`
      : ""}

    ${!d.batches.length
      ? html`<div class="kt-empty"><i class="fas fa-money-check-dollar"></i>
          <p>Chưa có đợt thanh toán nào trả cho hóa đơn này.</p></div>`
      : d.batches.map((b) => html`
          <div class="kt-card kt-mb"><div class="kt-card-body">
            <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
              <b><a href="/app/mt-payment-advice/${b.advice}" target="_blank">
                ${b.advice_no || b.advice}</a></b>
              ${b.payment_date ? html`<span class="kt-sub">${formatDate(b.payment_date)}</span>` : ""}
              <span class="kt-badge kt-badge--${STATUS_TONE[b.status] || "gray"}">${b.status}</span>
              ${b.je_state ? html`<span class="kt-sub">bút toán: ${b.je_state}</span>` : ""}
              <b style="margin-left:auto;color:var(--kt-success)">
                trả cho tờ này ${formatVND(b.paid_this_invoice)}</b>
            </div>

            ${b.deductions.length
              ? html`<div style="margin-top:10px">
                  <div class="kt-sub" style="margin-bottom:6px">
                    Đợt này bị trừ <b>${formatVND(b.deduction_total)}</b> —
                    ${d.deduction_note}
                  </div>
                  <div class="kt-table-wrap"><table class="kt-table">
                    <thead><tr><th>Loại</th><th class="kt-col-wide">Diễn giải</th>
                      <th>Chứng từ</th><th class="num">Số tiền</th></tr></thead>
                    <tbody>${b.deductions.map((x) => html`<tr>
                      <td><span class="kt-badge kt-badge--${KIND_TONE[x.kind] || "gray"}">${x.kind}</span></td>
                      <td class="kt-col-wide">${x.description || html`<span class="kt-sub">—</span>`}</td>
                      <td>${x.doc_no || html`<span class="kt-sub">—</span>`}</td>
                      <td class="num">${formatVND(x.amount)}</td>
                    </tr>`)}</tbody>
                  </table></div>
                </div>`
              : html`<div class="kt-sub" style="margin-top:8px">Đợt này không có khoản trừ nào.</div>`}
          </div></div>`)}
  `);
}

// ── BỘ LỌC + CỘT của danh sách soát HĐĐT ──────────────────────────────────
//
// Dùng chung cho CẢ HAI màn (bước Chờ xuất hóa đơn của Win, và màn soát toàn
// kênh). Vẽ hai lần là sớm muộn một bên quên hiện dòng "đang lọc" — và một
// danh sách bị lọc ngầm là con đường ngắn nhất để đọc ra một con số không phải
// con số của nhóm đang chọn.
//
// ⚠ BỘ LỌC KHÔNG ĐỔI MỐC. Backend lọc SAU khi dựng mốc (`_apply_filters`), nên
// lọc theo ngày không làm một hóa đơn bình thường bỗng thành "bỏ sót".
function einvFilterBar(f, opts) {
  const o = opts || { customers: [], stores: [] };
  return html`
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
      <input class="kt-input kt-input--sm" id="ef-q" style="min-width:220px"
             placeholder="Tìm số HĐ / số PO / khách / điểm giao…" value="${f.q || ""}">
      <select class="kt-input kt-input--sm" id="ef-customer">
        <option value="">Mọi pháp nhân</option>
        ${o.customers.map((c) => html`<option value="${c.value}"
          ${f.customer === c.value ? "selected" : ""}>${c.label}</option>`)}
      </select>
      <select class="kt-input kt-input--sm" id="ef-store">
        <option value="">Mọi điểm giao</option>
        ${o.stores.map((c) => html`<option value="${c.value}"
          ${f.store === c.value ? "selected" : ""}>${c.label}</option>`)}
      </select>
      <span class="kt-sub">ngày HĐ</span>
      <input type="date" class="kt-input kt-input--sm" id="ef-from" value="${f.from_date || ""}">
      <span class="kt-sub">→</span>
      <input type="date" class="kt-input kt-input--sm" id="ef-to" value="${f.to_date || ""}">
      <button class="kt-btn kt-btn--sm" id="ef-go"><i class="fas fa-filter"></i> Lọc</button>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="ef-clear">Bỏ lọc</button>
    </div>`;
}

// Đang lọc thì NÓI RA, và nói luôn đang giấu bao nhiêu dòng.
function einvFilterNote(d) {
  if (!d.filtered) return "";
  const hidden = (d.total_unfiltered || 0) - (d.total || 0);
  return html`
    <div class="kt-sub" style="color:var(--kt-warning);margin-bottom:8px">
      <i class="fas fa-filter"></i>
      <b>Đang lọc</b> — hiện ${d.total} / ${d.total_unfiltered} dòng của nhóm đang chọn${
        hidden > 0 ? html`, <b>${hidden} dòng bị bộ lọc giấu đi</b>` : ""}.
      Bộ lọc <b>không</b> đổi cách chia bỏ sót / chưa tới lượt.
    </div>`;
}

const einvHead = html`<tr>
  <th>Hóa đơn</th><th>Số PO</th><th class="kt-col-wide">Bên mua / điểm giao</th>
  <th>Ngày HĐ</th><th class="num">Tổng HĐ</th><th></th></tr>`;

function einvRow(r, canManage, withChain) {
  return html`<tr>
    <td><a href="/app/sales-invoice/${r.name}" target="_blank">${r.name}</a></td>
    <td>${r.po_no ? html`<code>${r.po_no}</code>` : html`<span class="kt-sub">—</span>`}</td>
    <td class="kt-col-wide">${r.customer_name || r.customer}
      ${withChain && r.chain ? html`<div class="kt-sub">${r.chain}</div>` : ""}
      ${withChain && !r.chain
        ? html`<div class="kt-sub" style="color:var(--kt-warning)">chưa gán chuỗi</div>` : ""}
      ${r.store_name || r.store_code
        ? html`<div class="kt-sub"><i class="fas fa-location-dot"></i>
            ${r.store_code ? r.store_code + " — " : ""}${r.store_name || ""}</div>`
        : (r.ship_to
            ? html`<div class="kt-sub"><i class="fas fa-location-dot"></i> ${r.ship_to}</div>`
            : html`<div class="kt-sub" style="color:var(--kt-warning)">chưa khai địa chỉ giao</div>`)}</td>
    <td>${formatDate(r.posting_date)}</td>
    <td class="num">${formatVND(r.grand_total)}</td>
    <td>${canManage
      ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" data-skip="${r.name}"
                title="Loại tờ này khỏi danh sách soát. KHÔNG đụng công nợ.">
          Bỏ qua</button>`
      : ""}</td>
  </tr>`;
}

// Ràng buộc thanh lọc. `apply` nhận object bộ lọc mới và tự nạp lại.
function bindEinvFilter(box, state, apply) {
  const read = () => ({
    q: (box.querySelector("#ef-q") || {}).value || "",
    customer: (box.querySelector("#ef-customer") || {}).value || "",
    store: (box.querySelector("#ef-store") || {}).value || "",
    from_date: (box.querySelector("#ef-from") || {}).value || "",
    to_date: (box.querySelector("#ef-to") || {}).value || "",
  });
  const go = box.querySelector("#ef-go");
  if (go) go.addEventListener("click", () => apply(read()));
  const cl = box.querySelector("#ef-clear");
  if (cl) cl.addEventListener("click", () => apply({}));
  const q = box.querySelector("#ef-q");
  // Enter trong ô tìm = bấm Lọc. Bắt người ta rời tay khỏi bàn phím để bấm một
  // cái nút ngay cạnh là ma sát không có lý do.
  if (q) q.addEventListener("keydown", (e) => { if (e.key === "Enter") apply(read()); });
}

// ── BỎ QUA khỏi danh sách soát HĐĐT ───────────────────────────────────────
//
// ⚠ CHỈ ẨN DÒNG KHỎI DANH SÁCH NÀY. Không đụng công nợ, doanh thu hay sổ cái
// 131. Câu đó được in ra trên chính hộp thoại, không giấu trong tooltip: người
// bấm phải biết mình đang làm gì và KHÔNG làm gì.
//
// Ẩn dòng mà không nói đã ẩn bao nhiêu là biến danh sách thành thứ không kiểm
// chứng được — hôm nay 0 việc có thể vì xong hết, cũng có thể vì ai đó bỏ qua
// sạch. Vì vậy `skippedBar` LUÔN hiện khi có tờ bị bỏ qua, và mở ra xem được.
function skippedBar(d) {
  const s = d.skipped || {};
  if (!s.count) return "";
  return html`
    <div class="kt-sub" style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <i class="fas fa-eye-slash"></i>
      <span><b>${s.count} hóa đơn (${formatVND(s.amount)}) đang bị bỏ qua</b> —
        không hiện trong danh sách trên. Công nợ và sổ cái vẫn tính đủ chúng.</span>
      <button class="kt-btn kt-btn--outline kt-btn--sm" data-skipped-open="1">Xem lại</button>
    </div>`;
}

function bindEinvSkip(box, container, state, reload) {
  box.querySelectorAll("button[data-skip]").forEach((b) => {
    b.addEventListener("click", () => openSkipModal(b.dataset.skip, reload));
  });
  const so = box.querySelector("button[data-skipped-open]");
  if (so) so.addEventListener("click", () => openSkippedList(state, reload));
}

function openSkipModal(name, reload) {
  const modal = openModal({
    title: `Bỏ qua hóa đơn ${name}`,
    icon: "fa-eye-slash",
    maxWidth: 560,
    body: html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
        <div class="kt-card-body kt-sub">
          Việc này <b>chỉ ẩn hóa đơn khỏi danh sách soát HĐĐT</b>. Nó
          <b>KHÔNG</b> làm hóa đơn hết là doanh thu, <b>KHÔNG</b> trừ khỏi công nợ, và
          <b>KHÔNG</b> đụng sổ cái 131. Mở lại được bất cứ lúc nào.
        </div></div>
      <label class="kt-sub">Lý do bỏ qua <b style="color:var(--kt-danger)">(bắt buộc)</b></label>
      <textarea class="kt-input" id="sk-note" rows="3"
        placeholder="Ví dụ: hóa đơn nội bộ, không phát hành HĐĐT · đã hủy ngoài hệ ngày …"></textarea>
      <div class="kt-sub" style="margin-top:6px">
        Sáu tháng sau không ai dựng lại được một quyết định không ghi lý do — và cũng
        không ai dám mở lại nó.
      </div>
      <div style="display:flex;gap:8px;margin-top:14px">
        <button class="kt-btn kt-btn--outline" id="sk-cancel">Thôi</button>
        <button class="kt-btn kt-btn--primary" id="sk-go" style="margin-left:auto">
          <i class="fas fa-eye-slash"></i> Bỏ qua hóa đơn này</button>
      </div>`,
  });
  modal.body.querySelector("#sk-cancel").addEventListener("click", () => modal.close());
  const go = modal.body.querySelector("#sk-go");
  go.addEventListener("click", async () => {
    const note = modal.body.querySelector("#sk-note").value.trim();
    go.disabled = true;
    try {
      const out = await api.mtEinvSkip({ sales_invoice: name, skip: 1, note });
      toast(out.message, "success");
      modal.close();
      reload();
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
    }
  });
}

async function openSkippedList(state, reload) {
  const modal = openModal({
    title: "Hóa đơn đang bị bỏ qua",
    icon: "fa-eye-slash",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  const draw = async () => {
    let d;
    try {
      d = await api.mtEinvSkipped({ chain: state.chain || state.gapChain || undefined });
    } catch (e) {
      return setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    }
    const rows = d.rows || [];
    setHTML(modal.body, html`
      ${!rows.length
        ? html`<div class="kt-empty"><p>Không có hóa đơn nào đang bị bỏ qua.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Hóa đơn</th><th class="kt-col-wide">Lý do</th>
              <th>Người bỏ qua</th><th class="num">Tổng HĐ</th><th></th></tr></thead>
            <tbody>${rows.map((r) => html`<tr>
              <td><a href="/app/sales-invoice/${r.name}" target="_blank">${r.name}</a>
                <div class="kt-sub">${formatDate(r.posting_date)}</div></td>
              <td class="kt-col-wide">${r.skip_note || html`<span class="kt-sub">(trống)</span>`}</td>
              <td>${r.skip_by || "—"}
                ${r.skip_on ? html`<div class="kt-sub">${formatDate(r.skip_on.slice(0, 10))}</div>` : ""}</td>
              <td class="num">${formatVND(r.grand_total)}</td>
              <td>${state.canManage
                ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" data-unskip="${r.name}">
                    Đưa trở lại</button>`
                : ""}</td>
            </tr>`)}</tbody>
          </table></div>`}
    `);
    modal.body.querySelectorAll("button[data-unskip]").forEach((b) => {
      b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          const out = await api.mtEinvSkip({ sales_invoice: b.dataset.unskip, skip: 0 });
          toast(out.message, "success");
          await draw();
          reload();
        } catch (e) {
          toast(e.message, "error");
          b.disabled = false;
        }
      });
    });
  };
  await draw();
}

// ── Khai hạn thanh toán từng khách ─────────────────────────────────────────
//
// KHÔNG có nút "áp hạn theo chuỗi cho tất cả". Central Retail có hai pháp nhân
// EB hạn khác nhau 10 ngày mà cùng mang một tên chuỗi — một nút như vậy sẽ gán
// sai hạn cho một trong hai, và sai âm thầm.
async function openCreditTerms(container, state) {
  const modal = openModal({
    title: "Hạn thanh toán từng khách (kênh MT)",
    icon: "fa-sliders",
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderCreditTerms(container, state, modal);
}

async function renderCreditTerms(container, state, modal) {
  let res;
  try {
    res = await api.mtCreditTerms();
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  if (!res.has_field) {
    setHTML(modal.body, html`<div class="kt-empty"><p>${res.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(modal.body, html`
    <div class="kt-sub" style="margin-bottom:10px">
      Số ngày kể từ ngày hóa đơn. Để <b>0</b> nghĩa là <b>chưa khai</b> — hệ thống
      KHÔNG tự đoán 45 ngày, hóa đơn của khách đó nằm rổ riêng.
      Gợi ý theo SOP: Win 60 · LOTTE 45 · Co.op 45 · AEON 30 ·
      Central Retail A030 = 30 / A040 = 40 (hai pháp nhân khác nhau, phải khai riêng).
    </div>
    ${res.missing_with_invoices
      ? html`<div class="kt-sub" style="margin-bottom:10px;color:var(--kt-warning)">
          <i class="fas fa-triangle-exclamation"></i>
          ${res.missing_with_invoices} khách ĐANG CÓ hóa đơn mà chưa khai hạn.
        </div>`
      : ""}
    <div class="kt-table-wrap" style="max-height:52vh;overflow:auto">
      <table class="kt-table">
        <thead><tr><th>Khách hàng</th><th>Chuỗi</th>
          <th class="num">Số HĐ</th><th class="num">Hạn (ngày)</th><th></th></tr></thead>
        <tbody>
          ${rows.map((r) => html`<tr>
            <td>${r.customer_name || r.customer}</td>
            <td>${r.chain || html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${r.n_invoices}</td>
            <td class="num"><input type="number" min="0" max="365"
                  class="kt-input kt-input--sm ct-days" style="width:90px;text-align:right"
                  data-customer="${r.customer}" value="${r.credit_days || ""}"
                  placeholder="chưa khai"></td>
            <td><button class="kt-btn kt-btn--success kt-btn--sm ct-save"
                        data-customer="${r.customer}">
              <i class="fas fa-check"></i></button></td>
          </tr>`)}
        </tbody>
      </table>
    </div>
  `);

  modal.body.querySelectorAll(".ct-save").forEach((b) => {
    b.addEventListener("click", async () => {
      const cus = b.dataset.customer;
      const inp = modal.body.querySelector(`.ct-days[data-customer="${cus}"]`);
      b.disabled = true;
      try {
        const r = await api.mtSaveCreditDays(cus, parseInt(inp.value, 10) || 0);
        toast(r.message, "success");
        loadTab(container, state);
      } catch (e) {
        toast(e.message, "error");
      } finally {
        b.disabled = false;
      }
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// BƯỚC — CHỜ XUẤT HÓA ĐƠN (chỉ WinCommerce)
//
// Win chỉ cho xuất hóa đơn SAU KHI họ nhận hàng và có phiếu nhập kho (SOP §2.2).
// Khoảng giữa "đã giao" và "đã xuất hóa đơn" trước nay không hệ nào theo dõi.
//
// PHẢI NÓI RÕ TRÊN MÀN HÌNH: đây CHƯA phải công nợ. File Excel cũ đang cộng
// 46.665.180đ loại này vào cột `Số còn nợ` — chưa xuất hóa đơn thì chưa phải
// khoản phải thu, cộng vào là thổi phồng công nợ.
// ═══════════════════════════════════════════════════════════════════════════

const WP_TONE = {
  "Đang giao": "yellow",
  "Đã nhận - chờ xuất HĐ": "green",
  "Đã xuất hóa đơn": "gray",
  "Hủy": "gray",
};

// ── HAI NGHĨA CỦA "CHỜ XUẤT HÓA ĐƠN" ──────────────────────────────────────
//
// Kế toán hỏi: "chỉ cần liệt kê hóa đơn trên ERPNext chưa điền số MISA là được
// mà?" — đúng, và đó là NGHĨA THỨ NHẤT. Bản đầu của bước này chỉ dựng nghĩa thứ
// hai, thứ phải nhập tay, nên màn hình trống trong khi câu trả lời đã nằm sẵn
// trong ERPNext.
//
//   A. Hóa đơn ĐÃ ghi sổ, CHƯA có số HĐĐT   — nguồn: ERPNext. Không cần nhập gì.
//   B. Đợt giao CHƯA có hóa đơn (PO/phiếu nhập kho) — nguồn: `MT Win Pending`.
//
// Hai tập KHÔNG giao nhau: A đã có Sales Invoice, B thì chưa. Cả hai đều thật,
// nhưng A phải đứng TRƯỚC vì nó có dữ liệu ngay và là việc hằng ngày.
async function loadWinPending(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtWinPending({
      status: state.wpStatus || undefined,
      search: state.search || undefined,
      page: state.page, page_size: 50,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(body, html`
    <div id="wp-einv" class="kt-mb">
      <div class="kt-sub"><i class="fas fa-circle-notch fa-spin"></i>
        đang đọc hóa đơn chưa có số HĐĐT…</div>
    </div>

    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
      <div class="kt-card-body">
        <div style="font-weight:600;margin-bottom:4px">
          <i class="fas fa-truck"></i> Đợt giao CHƯA có hóa đơn trên ERPNext
        </div>
        <div class="kt-sub">${res.note}</div>
        <div class="kt-sub" style="margin-top:6px">
          Khác hẳn danh sách trên: ở trên là hóa đơn <b>đã ghi sổ</b> mà chưa phát hành HĐĐT;
          ở đây là đợt giao <b>chưa có hóa đơn nào</b>. Hai tập không giao nhau.
        </div>
      </div>
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <select class="kt-input kt-input--sm" id="wp-status">
        <option value="">Đang chờ (mặc định)</option>
        ${(res.statuses || []).map((x) => html`<option value="${x}" ${state.wpStatus === x ? "selected" : ""}>${x}</option>`)}
      </select>
      <span class="kt-sub">${res.total} đợt giao · ${formatVND(res.amount)}
        ${res.n_received ? html` · <b>${res.n_received} đã có phiếu nhập kho, xuất hóa đơn được</b>` : ""}</span>
      <span style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap">
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="wp-grn">
          <i class="fas fa-file-pdf"></i> Đối soát phiếu nhập kho
        </button>
      </span>
      ${res.can_manage
        ? html`<span style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="kt-btn kt-btn--outline kt-btn--sm" id="wp-seed-open">
              <i class="fas fa-file-circle-check"></i> Khởi tạo từ số dư đã chốt
            </button>
            <button class="kt-btn kt-btn--outline kt-btn--sm" id="wp-seed">
              <i class="fas fa-file-import"></i> Khởi tạo từ file công nợ
            </button>
            <button class="kt-btn kt-btn--primary kt-btn--sm" id="wp-new">
              <i class="fas fa-plus"></i> Thêm đợt giao
            </button>
          </span>`
        : ""}
    </div></div>

    ${!rows.length
      ? (res.n_all
          ? html`<div class="kt-empty"><i class="fas fa-truck"></i>
              <p>Không có đợt giao nào đang chờ xuất hóa đơn.</p>
              <p class="kt-sub">${res.n_all} đợt giao đã nhập trước đó không nằm trong bộ lọc
                đang chọn — đổi ô trạng thái để xem.</p></div>`
          // BẢNG RỖNG HOÀN TOÀN ≠ HẾT VIỆC.
          //
          // Danh sách này KHÔNG tự sinh từ đâu cả: không hook, không scheduler.
          // Nó chỉ có dữ liệu khi người nhập tay hoặc khởi tạo từ số dư/file.
          // Câu "không có đợt giao nào đang chờ" đọc thành "xong rồi", trong khi
          // sự thật là chưa ai nhập gì — và đó chính là câu hỏi kế toán đang có
          // khi nhìn màn hình này.
          : html`<div class="kt-empty"><i class="fas fa-truck"></i>
              <p><b>Chưa có đợt giao nào được nhập.</b></p>
              <p class="kt-sub" style="max-width:640px;margin:0 auto">
                Danh sách này <b>không tự sinh</b> từ ERPNext hay từ hệ Win — nó chỉ có dữ
                liệu khi có người nhập. Ba đường:
              </p>
              <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:12px">
                ${res.can_manage
                  ? html`<button class="kt-btn kt-btn--primary kt-btn--sm" id="wp-empty-open">
                        <i class="fas fa-file-circle-check"></i> Khởi tạo từ số dư đã chốt
                      </button>
                      <button class="kt-btn kt-btn--outline kt-btn--sm" id="wp-empty-file">
                        <i class="fas fa-file-import"></i> Khởi tạo từ file công nợ
                      </button>
                      <button class="kt-btn kt-btn--outline kt-btn--sm" id="wp-empty-new">
                        <i class="fas fa-plus"></i> Thêm từng đợt
                      </button>`
                  : html`<span class="kt-sub">Cần quyền trưởng phòng để khởi tạo.</span>`}
              </div>
              <p class="kt-sub" style="margin-top:12px">
                Nút <b>Khởi tạo từ số dư đã chốt</b> chỉ chạy được khi bản số dư đầu kỳ
                WinCommerce đã ở trạng thái <b>Đã chốt</b>.
              </p></div>`)
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>PO VCM</th><th>Bên mua</th><th>Ngày giao</th>
              <th class="num">Tiền dự kiến</th><th>Phiếu nhập kho Win</th>
              <th class="num">Tiền theo phiếu</th><th>Trạng thái</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><code>${r.po_no}</code>
                  ${r.source === "Số dư đầu kỳ" ? html`<div class="kt-sub">từ số dư đầu kỳ</div>` : ""}</td>
                <td>${r.customer
                  ? (r.customer_name || r.customer)
                  : html`<span class="kt-badge kt-badge--red">chưa chọn bên mua</span>`}</td>
                <td>${r.delivery_date ? formatDate(r.delivery_date) : html`<span class="kt-sub">—</span>`}</td>
                <td class="num">${formatVND(r.total_amount)}</td>
                <td>${r.grn_no
                  ? html`<code>${r.grn_no}</code>${r.grn_date ? html`<div class="kt-sub">${formatDate(r.grn_date)}</div>` : ""}`
                  : html`<span class="kt-sub">chưa có</span>`}</td>
                <td class="num">${r.grn_amount
                  ? html`${formatVND(r.grn_amount)}${Math.abs((r.grn_amount || 0) - (r.total_amount || 0)) > 1
                      ? html`<div class="kt-sub" style="color:var(--kt-warning)">lệch ${formatVNDShort((r.grn_amount || 0) - (r.total_amount || 0))}</div>`
                      : ""}`
                  : html`<span class="kt-sub">—</span>`}</td>
                <td><span class="kt-badge kt-badge--${WP_TONE[r.status] || "gray"}">${r.status}</span></td>
                <td>${res.can_manage
                  ? html`<button class="kt-btn kt-btn--outline kt-btn--sm wp-edit" data-name="${r.name}">
                      <i class="fas fa-pen"></i></button>`
                  : ""}</td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "đợt giao")}
        </div></div>`}
  `);

  bindPager(container, state);
  const st = container.querySelector("#wp-status");
  if (st) st.addEventListener("change", (e) => {
    state.wpStatus = e.target.value; state.page = 1; loadTab(container, state);
  });
  const nw = container.querySelector("#wp-new");
  if (nw) nw.addEventListener("click", () => openWinPendingEdit(container, state, null));
  const sd = container.querySelector("#wp-seed");
  if (sd) sd.addEventListener("click", () => pickWinPendingSeed(container, state));
  const so = container.querySelector("#wp-seed-open");
  if (so) so.addEventListener("click", () => pickWinPendingFromOpening(container, state));
  // Nút trong màn trống — cùng handler, để không có hai đường làm hai việc khác nhau.
  const eo = container.querySelector("#wp-empty-open");
  if (eo) eo.addEventListener("click", () => pickWinPendingFromOpening(container, state));
  const ef = container.querySelector("#wp-empty-file");
  if (ef) ef.addEventListener("click", () => pickWinPendingSeed(container, state));
  const en = container.querySelector("#wp-empty-new");
  if (en) en.addEventListener("click", () => openWinPendingEdit(container, state, null));
  const gr = container.querySelector("#wp-grn");
  if (gr) gr.addEventListener("click", () => pickWinGrn(container, state));
  // Nạp SAU và KHÔNG chặn: quét toàn bộ hóa đơn của chuỗi, nặng hơn danh sách
  // đợt giao vốn chỉ đọc một bảng nhỏ.
  loadWinEinv(container, state);
}

// Danh sách A: hóa đơn ĐÃ ghi sổ trên ERPNext mà CHƯA điền số HĐĐT.
//
// Không cần nhập tay gì — dữ liệu có sẵn. Vẫn giữ phép chia quanh MỐC của
// `mt_einv` vì nó có ích ngay ở đây: tờ CŨ HƠN mốc là bất thường (đã đi qua mà
// không xuất), tờ mới hơn là hàng đang chờ tới lượt. Trộn hai loại vào một danh
// sách là chôn việc thật giữa việc bình thường.
async function loadWinEinv(container, state) {
  const box = container.querySelector("#wp-einv");
  if (!box) return;
  const chain = state.chain || "WinCommerce";
  let d;
  try {
    await ensureEinvOpts(state, chain);
    d = await api.mtEinvGaps({ chain, scope: state.wpEinvScope || "tat_ca",
                               page: state.wpEinvPage || 1, page_size: 50,
                               ...(state.wpEinvFilter || {}) });
  } catch (e) {
    setHTML(box, html`<div class="kt-card"><div class="kt-card-body kt-sub"
      style="color:var(--kt-danger)">Không đọc được danh sách hóa đơn: ${e.message}</div></div>`);
    return;
  }
  if (!d.supported) {
    setHTML(box, html`<div class="kt-card"><div class="kt-card-body kt-sub">${d.note}</div></div>`);
    return;
  }

  const scope = state.wpEinvScope || "tat_ca";
  const rows = d.rows || [];
  setHTML(box, html`
    <div class="kt-card"><div class="kt-card-body">
      <div style="font-weight:600;margin-bottom:4px">
        <i class="fas fa-file-invoice"></i> Hóa đơn ĐÃ ghi sổ, CHƯA có số hóa đơn điện tử
      </div>
      <div class="kt-sub" style="margin-bottom:10px">
        Lấy thẳng từ ERPNext — không phải nhập tay. Đây là phần đã là doanh thu và đã vào
        công nợ, nhưng ${chain} chưa trả được vì hóa đơn chưa phát hành.
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
        <button class="kt-btn kt-btn--sm ${scope === "tat_ca" ? "" : "kt-btn--outline"}"
                data-wpe="tat_ca">Tất cả · ${d.missed.count + d.backlog.count}</button>
        <button class="kt-btn kt-btn--sm ${scope === "bo_sot" ? "" : "kt-btn--outline"}"
                data-wpe="bo_sot">Bỏ sót · ${d.missed.count}</button>
        <button class="kt-btn kt-btn--sm ${scope === "chua_toi_luot" ? "" : "kt-btn--outline"}"
                data-wpe="chua_toi_luot">Chưa tới lượt · ${d.backlog.count}</button>
        <span class="kt-sub" style="margin-left:auto">${frontierLine(d.frontier, chain)}</span>
      </div>

      ${einvFilterBar(d.filters || {}, state.einvOpts)}
      ${einvFilterNote(d)}

      ${d.missed.count
        ? html`<div class="kt-sub" style="color:var(--kt-danger);margin-bottom:8px">
            <i class="fas fa-triangle-exclamation"></i>
            <b>${d.missed.count} tờ (${formatVND(d.missed.amount)}) CŨ HƠN mốc</b> — đã đi qua
            rồi mà không xuất. Đó là phần bất thường, không phải hàng đang chờ tới lượt.
          </div>`
        : ""}

      ${!rows.length
        ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i>
            <p>Không có hóa đơn nào của ${chain} thiếu số HĐĐT trong nhóm đang chọn.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead>${einvHead}</thead>
            <tbody>${rows.map((r) => einvRow(r, state.canManage, false))}</tbody>
          </table></div>
          ${pager(d, "hóa đơn")}`}

      ${skippedBar(d)}

      ${d.returns_missing.count
        ? html`<div class="kt-sub" style="margin-top:10px;color:var(--kt-warning)">
            <i class="fas fa-rotate-left"></i>
            ${d.returns_missing.count} phiếu trả hàng (${formatVND(d.returns_missing.amount)})
            cũng trống số HĐĐT — KHÔNG nằm trong danh sách trên, vì hóa đơn điều chỉnh/thay thế
            trên MISA đi theo luật khác.
          </div>`
        : ""}
    </div></div>`);

  bindEinvSkip(box, container, state, () => loadWinEinv(container, state));
  bindEinvFilter(box, state, (f) => {
    state.wpEinvFilter = f;
    state.wpEinvPage = 1;
    loadWinEinv(container, state);
  });
  box.querySelectorAll("button[data-wpe]").forEach((b) => {
    b.addEventListener("click", () => {
      state.wpEinvScope = b.dataset.wpe;
      state.wpEinvPage = 1;
      loadWinEinv(container, state);
    });
  });
  // Phân trang RIÊNG của danh sách này — dùng chung `state.page` với danh sách
  // đợt giao bên dưới là bấm sang trang 2 ở đây thì bảng kia cũng nhảy theo.
  box.querySelectorAll("button[data-page]").forEach((b) => {
    b.addEventListener("click", () => {
      state.wpEinvPage = parseInt(b.dataset.page, 10) || 1;
      loadWinEinv(container, state);
    });
  });
  container.querySelectorAll(".wp-edit").forEach((b) => {
    const row = rows.find((r) => r.name === b.dataset.name);
    b.addEventListener("click", () => openWinPendingEdit(container, state, row));
  });
}

// ── Thêm / sửa một đợt giao ────────────────────────────────────────────────
async function openWinPendingEdit(container, state, row) {
  const modal = openModal({
    title: row ? `Đợt giao PO ${row.po_no}` : "Thêm đợt giao",
    icon: "fa-truck",
    maxWidth: 700,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let cus = { rows: [], message: "" };
  try { cus = await api.mtWinCustomers(); } catch (e) { cus = { rows: [], message: e.message }; }
  const r = row || {};

  setHTML(modal.body, html`
    ${cus.message ? html`<div class="kt-sub" style="color:var(--kt-warning);margin-bottom:10px">${cus.message}</div>` : ""}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <label>Số PO VCM
        <input class="kt-input" id="wp-po" value="${r.po_no || ""}" ${row ? "readonly" : ""}>
        ${row ? html`<div class="kt-sub">PO là khóa của đợt giao — không sửa được.</div>` : ""}
      </label>
      <label>Bên mua (chi nhánh Win)
        <select class="kt-input" id="wp-cus">
          <option value="">— chọn —</option>
          ${(cus.rows || []).map((c) => html`<option value="${c.name}" ${r.customer === c.name ? "selected" : ""}>${c.customer_name || c.name}</option>`)}
        </select>
      </label>
      <label>Ngày giao hàng
        <input type="date" class="kt-input" id="wp-date" value="${r.delivery_date || ""}"></label>
      <label>Trạng thái
        <select class="kt-input" id="wp-st">
          ${["Đang giao", "Đã nhận - chờ xuất HĐ", "Đã xuất hóa đơn", "Hủy"].map((x) =>
            html`<option value="${x}" ${(r.status || "Đang giao") === x ? "selected" : ""}>${x}</option>`)}
        </select></label>
      <label>Tiền trước VAT (dự kiến)
        <input type="number" class="kt-input" id="wp-net" value="${r.amount_before_vat || ""}"></label>
      <label>Tiền VAT (dự kiến)
        <input type="number" class="kt-input" id="wp-vat" value="${r.vat_amount || ""}"></label>
      <label>Số phiếu nhập kho Win
        <input class="kt-input" id="wp-grn" value="${r.grn_no || ""}"></label>
      <label>Ngày nhập kho
        <input type="date" class="kt-input" id="wp-grnd" value="${r.grn_date || ""}"></label>
      <label>Tiền theo phiếu nhập kho
        <input type="number" class="kt-input" id="wp-grna" value="${r.grn_amount || ""}">
        <div class="kt-sub">Lệch với tiền dự kiến thì xuất hóa đơn theo SỐ THỰC NHẬN,
          phần chênh làm xuất trả.</div></label>
      <label>Hóa đơn đã xuất
        <input class="kt-input" id="wp-si" value="${r.sales_invoice || ""}"
          placeholder="mã Sales Invoice"></label>
    </div>
    <label style="display:block;margin-top:10px">Ghi chú
      <textarea class="kt-input" id="wp-note" rows="3">${r.note || ""}</textarea></label>

    <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
      <button class="kt-btn kt-btn--success" id="wp-save"><i class="fas fa-check"></i> Lưu</button>
      ${row && row.status !== "Đã xuất hóa đơn"
        ? html`<button class="kt-btn kt-btn--danger kt-btn--sm" id="wp-del" style="margin-left:auto">
            <i class="fas fa-trash"></i> Xóa
          </button>`
        : ""}
    </div>
  `);

  const val = (id) => modal.body.querySelector(id).value.trim();
  modal.body.querySelector("#wp-save").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#wp-save");
    btn.disabled = true;
    try {
      const out = await api.mtWinPendingSave({
        name: row ? row.name : undefined,
        po_no: val("#wp-po"), customer: val("#wp-cus"),
        delivery_date: val("#wp-date"), status: val("#wp-st"),
        amount_before_vat: val("#wp-net") || 0, vat_amount: val("#wp-vat") || 0,
        grn_no: val("#wp-grn"), grn_date: val("#wp-grnd"),
        grn_amount: val("#wp-grna") || 0,
        sales_invoice: val("#wp-si"), note: val("#wp-note"),
      });
      toast(out.message, "success");
      modal.close();
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      btn.disabled = false;
    }
  });
  const del = modal.body.querySelector("#wp-del");
  if (del) del.addEventListener("click", async () => {
    del.disabled = true;
    try {
      const out = await api.mtWinPendingDelete(row.name);
      toast(out.message, "success");
      modal.close();
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      del.disabled = false;
    }
  });
}

// ── Khởi tạo danh sách từ file theo dõi công nợ Win ────────────────────────
function pickWinPendingSeed(container, state) {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".xlsx,.xls,.xlsm";
  inp.addEventListener("change", () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const fr = new FileReader();
    fr.onload = () => openWinPendingSeed(container, state, String(fr.result).split(",").pop());
    fr.readAsDataURL(f);
  });
  inp.click();
}

async function openWinPendingSeed(container, state, content) {
  return runWinPendingSeed(container, state, {
    title: "Khởi tạo đợt giao từ file công nợ WinCommerce",
    icon: "fa-file-import",
    preview: () => api.mtWinPendingSeedPreview(content),
    commit: (h) => api.mtWinPendingSeedCommit({ content, expected_hash: h }),
  });
}

// Khởi tạo từ SỐ DƯ ĐẦU KỲ ĐÃ CHỐT — không phải nạp lại file.
//
// Bản số dư Win đã nạp và chốt một lần rồi. Bắt kế toán đi tìm lại đúng file
// Excel cũ là mời một lỗi rất khó thấy: nạp nhầm bản sửa sau, hoặc nhầm kỳ —
// và `MT Win Pending` không giữ liên kết ngược về file nên không chỗ nào đối
// chiếu được. Bản đã chốt là nguồn đã qua kiểm.
async function pickWinPendingFromOpening(container, state) {
  let list;
  try {
    list = await api.mtOpenings();
  } catch (e) {
    return toast(e.message, "error");
  }
  // `list_openings` trả MỘT dòng cho mỗi chuỗi, và tên bản ghi nằm trong `doc`
  // (null khi chuỗi chưa nạp lần nào) — không phải ở cấp ngoài.
  const win = (list.rows || []).find((r) => r.chain === "WinCommerce");
  if (!win || !win.doc) {
    return toast("Chưa nạp số dư đầu kỳ WinCommerce lần nào. Làm ở màn "
      + "Số dư đầu kỳ trước, hoặc dùng nút khởi tạo từ file.", "error");
  }
  if (win.status !== "Đã chốt") {
    // Chặn ở đây CHỨ KHÔNG chỉ dựa vào backend: báo ngay tại chỗ bấm thì kế
    // toán biết phải đi chốt, thay vì nhận một lỗi giữa hộp thoại xem trước.
    return toast(`Bản số dư WinCommerce đang ở trạng thái "${win.status || "Nháp"}". `
      + "Chỉ dựng đợt giao từ bản ĐÃ CHỐT — bản nháp còn sửa được, chốt lại khác đi "
      + "thì các PO vừa tạo không còn căn cứ nào.", "error");
  }
  return openWinPendingFromOpening(container, state, win.doc.name);
}

async function openWinPendingFromOpening(container, state, opening) {
  return runWinPendingSeed(container, state, {
    title: `Khởi tạo đợt giao từ số dư đã chốt ${opening}`,
    icon: "fa-file-circle-check",
    preview: () => api.mtWinPendingSeedFromOpeningPreview(opening),
    commit: (h) => api.mtWinPendingSeedFromOpeningCommit({ opening, expected_hash: h }),
  });
}

// Khung chung cho CẢ HAI đường khởi tạo. Vẽ hai lần là sớm muộn một bên quên
// hiện phần "dòng bị chặn" — tức là ghi ít hơn người duyệt tưởng, im lặng.
async function runWinPendingSeed(container, state, opt) {
  const modal = openModal({
    title: opt.title,
    icon: opt.icon,
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await opt.preview();
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }

  setHTML(modal.body, html`
    <div class="kt-sub" style="margin-bottom:12px">${res.note}</div>
    ${res.blocked.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            <b>${res.blocked.length} dòng bị chặn</b> — ${res.blocked.map((b) => b.reason).filter((v, i, a) => a.indexOf(v) === i).join(" · ")}
          </div></div>`
      : ""}
    ${!res.n
      ? html`<div class="kt-empty"><p>Không có dòng nào để khởi tạo.</p></div>`
      : html`<div class="kt-table-wrap" style="max-height:44vh;overflow:auto">
          <table class="kt-table">
            <thead><tr><th>PO VCM</th><th>Bên mua ghi trong file</th>
              <th class="num">Trước VAT</th><th class="num">VAT</th><th class="num">Tổng</th></tr></thead>
            <tbody>${res.rows.map((r) => html`<tr>
              <td><code>${r.po_no || "—"}</code></td>
              <td>${r.party || html`<span class="kt-sub">—</span>`}</td>
              <td class="num">${formatVND(r.amount_before_vat)}</td>
              <td class="num">${formatVND(r.vat_amount)}</td>
              <td class="num"><b>${formatVND(r.total_amount)}</b></td>
            </tr>`)}</tbody>
          </table></div>
        <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
          <span><b>${res.n} đợt giao · ${formatVND(res.total_amount)}</b></span>
          <button class="kt-btn kt-btn--success" id="wp-seed-go" style="margin-left:auto">
            <i class="fas fa-check"></i> Tạo ${res.n} đợt giao
          </button>
        </div>`}
  `);

  const go = modal.body.querySelector("#wp-seed-go");
  if (go) go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      const out = await opt.commit(res.plan_hash);
      toast(out.message, (out.failed || []).length ? "error" : "success");
      if (out.warning) toast(out.warning, "error");
      modal.close();
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
    }
  });
}

// ── Đối soát phiếu nhập kho Winmart (PDF) ─────────────────────────────────
// SOP §2.2: chỉ xuất hóa đơn sau khi có phiếu nhập kho trên hệ Win và khớp
// PO + hàng hóa. Trước màn này kế toán mở PDF đọc bằng mắt rồi so tay.
const GRN_TONE = {
  khop: "green",
  lech_sl: "yellow",
  thieu_tren_hd: "red",
  thua_tren_hd: "red",
};

function pickWinGrn(container, state) {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".pdf";
  inp.addEventListener("change", () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const fr = new FileReader();
    fr.onload = () => openWinGrn(container, state, String(fr.result).split(",").pop());
    fr.readAsDataURL(f);
  });
  inp.click();
}

async function openWinGrn(container, state, content) {
  const modal = openModal({
    title: "Đối soát phiếu nhập kho Winmart",
    icon: "fa-file-pdf",
    maxWidth: 940,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await api.mtWinGrnPreview(content);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }

  const g = res.grn || {};
  const m = res.match || {};
  const lines = m.lines || [];
  const c = m.counts || {};
  const pd = res.pending;
  // "Chưa có hóa đơn mang PO này" KHÔNG phải lỗi — Win chỉ cho xuất hóa đơn sau
  // khi có phiếu, nên đó thường là đúng quy trình.
  const noInvoice = !m.blocked && !(m.invoices || []).length;

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px">
      <div><div class="kt-sub">Số phiếu</div><b><code>${g.grn_no || "—"}</code></b></div>
      <div><div class="kt-sub">Số đơn hàng (PO)</div><b><code>${g.po_no || "—"}</code></b></div>
      <div><div class="kt-sub">Ngày thực hiện</div><b>${g.grn_date ? formatDate(g.grn_date) : "—"}</b></div>
      <div><div class="kt-sub">Cửa hàng / kho</div><b>${g.store || "—"}</b></div>
      <div><div class="kt-sub">Dòng hàng</div><b>${g.n_lines} dòng · ${g.total_qty} đơn vị</b></div>
    </div></div>

    ${m.blocked
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body kt-sub">${m.reason}</div></div>`
      : ""}
    ${noInvoice
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
          <div class="kt-card-body kt-sub">${m.reason}</div></div>`
      : ""}
    ${(m.warnings || []).map((w) => html`<div class="kt-card kt-mb"
        style="border-left:4px solid var(--kt-warning)">
        <div class="kt-card-body kt-sub">${w}</div></div>`)}

    ${(m.invoices || []).length
      ? html`<div class="kt-sub" style="margin-bottom:8px">Hóa đơn mang PO
          <code>${g.po_no}</code>:
          ${m.invoices.map((i) => html`<a href="/app/sales-invoice/${i.name}" target="_blank">${i.name}</a>
            <span class="kt-badge kt-badge--${i.docstatus === 1 ? "green" : "yellow"}">${i.docstatus === 1 ? "đã ghi sổ" : "nháp"}</span> `)}
        </div>`
      : ""}

    ${!lines.length
      ? html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>STT</th><th>Mã hàng Win</th><th>Tên hàng</th>
              <th class="num">Số lượng</th><th>ĐVT</th></tr></thead>
            <tbody>${(g.lines || []).map((l) => html`<tr>
              <td>${l.stt}</td><td><code>${l.item_code}</code></td>
              <td>${l.item_name}</td><td class="num">${l.qty}</td><td>${l.uom}</td>
            </tr>`)}</tbody>
          </table></div></div></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
            <span class="kt-badge kt-badge--green">${c.khop || 0} khớp</span>
            <span class="kt-badge kt-badge--yellow">${c.lech_sl || 0} lệch số lượng</span>
            <span class="kt-badge kt-badge--red">${c.thieu_tren_hd || 0} phiếu có, hóa đơn không</span>
            <span class="kt-badge kt-badge--red">${c.thua_tren_hd || 0} hóa đơn có, phiếu không</span>
          </div>
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Mã hàng Win</th><th>Tên hàng</th>
              <th class="num">SL phiếu</th><th class="num">SL hóa đơn</th>
              <th class="num">Chênh</th><th>Kết luận</th></tr></thead>
            <tbody>${lines.map((l) => html`<tr>
              <td><code>${l.ma_win}</code>${l.item_code ? html`<div class="kt-sub">${l.item_code}</div>` : ""}</td>
              <td>${l.name || html`<span class="kt-sub">—</span>`}</td>
              <td class="num">${l.qty_grn === null ? html`<span class="kt-sub">—</span>` : l.qty_grn}</td>
              <td class="num">${l.qty_si === null ? html`<span class="kt-sub">—</span>` : l.qty_si}</td>
              <td class="num">${l.diff ? html`<b>${l.diff > 0 ? "+" : ""}${l.diff}</b>` : "0"}</td>
              <td><span class="kt-badge kt-badge--${GRN_TONE[l.status] || "gray"}">${l.status_label}</span></td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`}

    <div class="kt-sub" style="margin-top:12px">${res.note}</div>

    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
      ${pd
        ? html`<span class="kt-sub">Đợt giao đang theo dõi: PO <code>${pd.po_no}</code> ·
            ${pd.status}${pd.grn_no ? html` · đã gắn phiếu <code>${pd.grn_no}</code>` : ""}</span>`
        : html`<span class="kt-sub">Chưa có đợt giao nào trong danh sách chờ mang PO này.</span>`}
      ${pd && !pd.grn_no && res.can_attach
        ? html`<button class="kt-btn kt-btn--success" id="grn-attach" style="margin-left:auto">
            <i class="fas fa-link"></i> Ghi phiếu ${g.grn_no} vào đợt giao
          </button>`
        : ""}
    </div>
  `);

  const at = modal.body.querySelector("#grn-attach");
  if (at) at.addEventListener("click", async () => {
    at.disabled = true;
    try {
      const out = await api.mtWinGrnAttach({ content, expected_hash: res.plan_hash });
      toast(out.message, "success");
      modal.close();
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      at.disabled = false;
    }
  });
}

// ── Số dư đầu kỳ: bảng chuỗi ──────────────────────────────────────────────
// Việc MỘT LẦN cho mỗi chuỗi. Ba trạng thái, và chỉ trạng thái cuối mới đụng
// tới công nợ:
//   chưa nhập  ->  Nháp (đã nhập, chưa bật luật)  ->  Đã chốt (bật luật).
const OB_TONE = { "": "gray", "Nháp": "yellow", "Đã chốt": "green" };

async function loadOpeningBoard(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtOpenings();
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  // Vế sổ cái nạp RIÊNG và được phép hỏng: nó đọc GL Entry, nặng hơn hẳn phần
  // còn lại. Gộp vào một lời gọi thì một truy vấn sổ cái chậm/lỗi làm trắng cả
  // bảng số dư đầu kỳ — màn hình chính mất vì một cột phụ.
  let glRes = null;
  try {
    glRes = await api.mtOpeningGlCompare();
  } catch (e) {
    glRes = { error: e.message };
  }
  const glOf = {};
  (glRes && glRes.rows ? glRes.rows : []).forEach((g) => { glOf[g.chain] = g; });

  setHTML(body, html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
      <div class="kt-card-body kt-sub">${res.note}</div>
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
      <span class="kt-sub">Đã chốt <b>${res.n_done}/${rows.length}</b> chuỗi</span>
      <span class="kt-sub">Công nợ mang sang: <b>${formatVND(res.total_carried)}</b></span>
      ${glRes && !glRes.error
        ? html`<span class="kt-sub">Sổ cái tại ngày chốt: <b>${formatVND(glRes.total_gl)}</b></span>
               <span class="kt-sub">Lệch: <b style="${Math.abs(glRes.total_diff) > 1 ? "color:var(--kt-danger)" : ""}"
                 >${formatVND(glRes.total_diff)}</b>${glRes.n_off ? ` · ${glRes.n_off} chuỗi lệch` : ""}</span>`
        : ""}
      ${!res.can_manage ? html`<span class="kt-sub">Chỉ kế toán trưởng mới nhập/chốt được.</span>` : ""}
    </div></div>

    ${glRes && glRes.error
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub"><b>Chưa lấy được số dư sổ cái.</b> ${glRes.error}
          — hai cột bên phải để trống, phần còn lại vẫn dùng bình thường.</div></div>`
      : ""}
    ${glRes && !glRes.error
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body kt-sub">${glRes.note}</div></div>`
      : ""}

    <div class="kt-card"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr>
          <th>Chuỗi</th><th>Trạng thái</th><th>Ngày chốt</th>
          <th class="num">Nợ ròng</th><th class="num">Đơn chưa xuất HĐ</th>
          <th class="num">Mang sang</th>
          <th class="num">Sổ cái ERPNext</th><th class="num">Lệch</th>
          <th class="num">Dòng treo</th><th></th>
        </tr></thead>
        <tbody>
          ${rows.map((r) => html`<tr>
            <td><b>${r.chain}</b>
              ${!r.n_customers ? html`<div class="kt-sub" style="color:var(--kt-warning)">chưa gán khách hàng nào</div>` : ""}</td>
            <td><span class="kt-badge kt-badge--${OB_TONE[r.status] || "gray"}">${r.status || "chưa nhập"}</span></td>
            <td>${r.doc ? formatDate(r.doc.cutover_date) : html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${r.doc ? formatVND(r.doc.opening_debt) : html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${r.doc && r.doc.no_invoice_amount
              ? html`<span class="kt-sub">${formatVND(r.doc.no_invoice_amount)}</span>` : html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${r.doc ? html`<b>${formatVND(r.doc.debt_carried)}</b>` : html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${glOf[r.chain] && glOf[r.chain].has_doc
              ? formatVND(glOf[r.chain].gl) : html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${glOf[r.chain] && glOf[r.chain].has_doc
              ? html`<b class="${Math.abs(glOf[r.chain].diff) > 1 ? "danger" : ""}"
                  >${formatVND(glOf[r.chain].diff)}</b>`
              : html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${r.doc && r.doc.n_unmatched
              ? html`<span class="kt-badge kt-badge--red">${r.doc.n_unmatched}</span>`
              : html`<span class="kt-sub">${r.doc ? "0" : "—"}</span>`}</td>
            <td>${r.doc
              ? html`<button class="kt-btn kt-btn--outline kt-btn--sm ob-open" data-name="${r.doc.name}">
                  <i class="fas fa-folder-open"></i> Mở</button>
                <button class="kt-btn kt-btn--outline kt-btn--sm ob-gl" data-name="${r.doc.name}"
                        title="Chỗ lệch giữa file Excel và sổ cái nằm ở đâu">
                  <i class="fas fa-scale-balanced"></i> Đối chiếu</button>`
              : (res.can_manage
                ? html`<button class="kt-btn kt-btn--primary kt-btn--sm ob-import" data-chain="${r.chain}">
                    <i class="fas fa-file-import"></i> Nhập file</button>`
                : html`<span class="kt-sub">chưa nhập</span>`)}</td>
          </tr>`)}
        </tbody>
      </table></div>
    </div></div>
  `);

  container.querySelectorAll(".ob-open").forEach((b) => {
    b.addEventListener("click", () => {
      state.openName = b.dataset.name; state.openOnly = ""; state.page = 1;
      loadTab(container, state);
    });
  });
  container.querySelectorAll(".ob-gl").forEach((b) => {
    b.addEventListener("click", () => openGlBridge(b.dataset.name));
  });
  container.querySelectorAll(".ob-import").forEach((b) => {
    b.addEventListener("click", () => pickOpeningFile(container, state, b.dataset.chain));
  });
}

// ── Đối chiếu Excel ↔ sổ cái ERPNext cho MỘT chuỗi ────────────────────────
// Không bày hai con số rồi in "lệch X" — kế toán không làm gì được với một con
// số như thế. Bày CẦU NỐI: bốn khoản mục cộng lại phải ra đúng chỗ lệch.
async function openGlBridge(name) {
  const modal = openModal({
    title: "Đối chiếu số dư đầu kỳ ↔ sổ cái ERPNext",
    icon: "fa-scale-balanced",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let d;
  try {
    d = await api.mtOpeningGlDetail({ name });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  setHTML(modal.body, glBridgeBody(d));
  modal.body.querySelector("#gl-close").addEventListener("click", () => modal.close());
}

function glBridgeBody(d) {
  const x = d.excel;
  const e = d.erp;
  const off = Math.abs(d.diff) > 1;

  return html`
    <div class="kt-sub" style="margin-bottom:10px">
      <b>${d.chain}</b> · ngày chốt ${formatDate(d.cutover_date)} ·
      trạng thái ${d.status}${d.finalized ? " (luật tất toán ĐANG bật)" : ""}
    </div>

    <div class="kt-stats kt-mb">
      <div class="kt-stat"><div class="kt-stat-label">Excel: công nợ mang sang</div>
        <div class="kt-stat-value">${formatVNDShort(x.debt_carried)}</div>
        <div class="kt-stat-sub">${formatVND(x.debt_carried)}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Sổ cái ERPNext tại ngày chốt</div>
        <div class="kt-stat-value">${formatVNDShort(e.gl)}</div>
        <div class="kt-stat-sub">TK phải thu · chưa áp luật tất toán</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Lệch (sổ cái − Excel)</div>
        <div class="kt-stat-value ${off ? "neg" : "pos"}">${formatVNDShort(d.diff)}</div>
        <div class="kt-stat-sub">${formatVND(d.diff)}</div></div>
    </div>

    ${!d.balanced
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-bug"></i> Cầu nối không cộng đủ — còn dư ${formatVND(d.residual)}</b>
          <div class="kt-sub" style="margin-top:4px">Bốn khoản mục dưới đây phải cộng lại ĐÚNG bằng chỗ lệch.
          Còn dư là LỖI CODE, không phải sai số cho phép — đừng dùng bảng này để kết luận cho tới khi sửa xong.</div>
        </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <b>Chỗ lệch nằm ở đâu</b>
      <div class="kt-table-wrap" style="margin-top:6px"><table class="kt-table">
        <tbody>
          ${(d.items || []).map((it) => html`<tr>
            <td>${it.label}<div class="kt-sub">${it.hint}</div></td>
            <td class="num" style="white-space:nowrap"><b>${formatVND(it.amount)}</b></td>
          </tr>`)}
          <tr style="border-top:2px solid var(--kt-border)">
            <td><b>Cộng lại</b></td>
            <td class="num"><b class="${off ? "danger" : ""}">${formatVND(d.diff)}</b></td>
          </tr>
        </tbody>
      </table></div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <b>Vế Excel — từ số in trong file xuống số đem so</b>
      <div class="kt-table-wrap" style="margin-top:6px"><table class="kt-table"><tbody>
        <tr><td>Nợ gộp (sheet chính, đã đối chiếu dòng TỔNG CỘNG của file)</td>
            <td class="num">${formatVND(x.opening_debt_gross)}</td></tr>
        <tr><td class="kt-sub">− ghi giảm chưa cấn trừ</td>
            <td class="num kt-sub">${formatVND(x.deduction_open)}</td></tr>
        <tr><td>= nợ ròng đầu kỳ</td><td class="num">${formatVND(x.opening_debt)}</td></tr>
        <tr><td class="kt-sub">− đơn đã giao CHƯA xuất hóa đơn (chưa có bút toán nên sổ cái không thể có)</td>
            <td class="num kt-sub">${formatVND(x.no_invoice_amount)}</td></tr>
        <tr style="border-top:2px solid var(--kt-border)">
            <td><b>= công nợ mang sang — SỐ ĐEM SO</b></td>
            <td class="num"><b>${formatVND(x.debt_carried)}</b></td></tr>
        <tr><td class="kt-sub">trong đó đã nối được hóa đơn (${x.n_matched} dòng)</td>
            <td class="num kt-sub">${formatVND(x.matched)}</td></tr>
        <tr><td class="kt-sub">trước go-live (${x.n_pre_golive} dòng) · bỏ qua (${x.n_skipped} dòng)</td>
            <td class="num kt-sub">${formatVND(x.pre_golive + x.skipped)}</td></tr>
        ${!x.file_consistent
          ? html`<tr><td><b class="danger">Số của chính file không tự khớp — lệch ${formatVND(x.file_gap)}</b>
                <div class="kt-sub">Tổng các dòng còn nợ không ra dòng TỔNG CỘNG in trong file. Lúc nhập đã
                đối chiếu khớp, nên khác 0 bây giờ nghĩa là dữ liệu đã bị sửa sau khi nhập — cầu nối phía
                trên chỉ đúng tới mức con số gốc còn đúng.</div></td>
              <td class="num"><b class="danger">${formatVND(x.file_gap)}</b></td></tr>`
          : ""}
        <tr><td class="${x.unmatched ? "" : "kt-sub"}">
              ${x.unmatched ? html`<b style="color:var(--kt-danger)">CHƯA nối được hóa đơn nào (${x.n_unmatched} dòng)</b>
                <div class="kt-sub">Tiền thật đang không có chứng từ nào giữ lại. Chốt bây giờ là mất khỏi công nợ.</div>`
                : html`chưa nối được hóa đơn nào (0 dòng)`}</td>
            <td class="num"><b class="${x.unmatched ? "danger" : ""}">${formatVND(x.unmatched)}</b></td></tr>
      </tbody></table></div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <b>Vế ERPNext — sổ cái so với rổ hóa đơn</b>
      <div class="kt-table-wrap" style="margin-top:6px"><table class="kt-table"><tbody>
        <tr><td>Số dư TK phải thu trên sổ cái</td><td class="num">${formatVND(e.gl)}</td></tr>
        <tr><td>Rổ hóa đơn còn nợ tại ngày chốt (${e.n_listed + e.n_not_listed} hóa đơn)</td>
            <td class="num">${formatVND(e.invoice_basket)}</td></tr>
        <tr><td class="kt-sub">· có tên trong file (${e.n_listed} hóa đơn)</td>
            <td class="num kt-sub">${formatVND(e.listed)}</td></tr>
        <tr><td class="kt-sub">· KHÔNG có trong file (${e.n_not_listed} hóa đơn) — chốt là mất khỏi công nợ</td>
            <td class="num kt-sub">${formatVND(e.not_listed)}</td></tr>
      </tbody></table></div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <b>Từng pháp nhân của chuỗi</b>
      <div class="kt-sub" style="margin:4px 0">Một chuỗi nhiều mã khách; chỗ lệch gần như luôn nằm gọn ở một pháp nhân.</div>
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Khách hàng</th><th class="num">Sổ cái</th>
          <th class="num">HĐ có trong file</th><th class="num">HĐ ngoài file</th></tr></thead>
        <tbody>${(d.by_customer || []).map((c) => html`<tr>
          <td>${c.customer_name}<div class="kt-sub">${c.customer}</div></td>
          <td class="num">${formatVND(c.gl)}</td>
          <td class="num">${formatVND(c.listed)} <span class="kt-sub">(${c.n_listed})</span></td>
          <td class="num">${formatVND(c.not_listed)} <span class="kt-sub">(${c.n_not_listed})</span></td>
        </tr>`)}</tbody>
      </table></div>
    </div></div>

    <div style="display:flex;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="gl-close">Đóng</button>
    </div>
  `;
}

function pickOpeningFile(container, state, chain) {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".xlsx,.xls,.xlsm";
  inp.addEventListener("change", () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const fr = new FileReader();
    fr.onload = () => openOpeningImport(container, state, chain, String(fr.result).split(",").pop());
    fr.readAsDataURL(f);
  });
  inp.click();
}

// ── Nhập file: hỏi hai mốc ngày TRƯỚC, rồi mới đọc ────────────────────────
// Hai mốc này quyết định toàn bộ cách phân nhóm, nên không đoán hộ: `golive`
// chia "hóa đơn ERPNext có" với "nợ độc lập", `cutover` là mốc bật luật.
async function openOpeningImport(container, state, chain, content) {
  const modal = openModal({
    title: `Nhập số dư đầu kỳ — ${chain}`,
    icon: "fa-file-import",
    maxWidth: 960,
    body: html`
      <div class="kt-sub" style="margin-bottom:12px">
        Hai mốc ngày quyết định cách chia nhóm. Khai xong mới đọc file.
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <label>Ngày chốt số dư
          <input type="date" class="kt-input" id="ob-cut" value="${todayISO()}">
          <div class="kt-sub">Mốc chuyển giao. Hóa đơn của chuỗi trước mốc này mà không có trong danh sách -> coi như đã trả.</div>
        </label>
        <label>ERPNext có dữ liệu từ
          <input type="date" class="kt-input" id="ob-golive" value="2026-05-01">
          <div class="kt-sub">Trước mốc này ERPNext không có hóa đơn nào, nên dòng nợ trước đó là nợ đầu kỳ độc lập.</div>
        </label>
      </div>
      <div style="display:flex;margin-top:14px">
        <button class="kt-btn kt-btn--primary" id="ob-read" style="margin-left:auto">
          <i class="fas fa-magnifying-glass"></i> Đọc file
        </button>
      </div>`,
  });

  modal.body.querySelector("#ob-read").addEventListener("click", async () => {
    const cutover = modal.body.querySelector("#ob-cut").value;
    const golive = modal.body.querySelector("#ob-golive").value;
    setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
    let res;
    try {
      res = await api.mtOpeningPreview({ content, chain, golive, cutover });
    } catch (e) {
      setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
      return;
    }
    renderOpeningPreview(container, state, modal, { content, chain, golive, cutover }, res);
  });
}

function renderOpeningPreview(container, state, modal, args, res) {
  const t = res.totals || {};
  const kinds = t.by_kind || [];

  setHTML(modal.body, html`
    ${res.blocked
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body kt-sub">Chuỗi ${res.chain} đã có bản số dư
            (<b>${res.existing.name}</b>, ${res.existing.status}). Số dư đầu kỳ chỉ nhập
            MỘT LẦN — nhập lần hai là cộng đôi công nợ.</div></div>`
      : ""}
    ${res.chain_detected && res.chain_detected !== res.chain
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">Bố cục file trông giống chuỗi
            <b>${res.chain_detected}</b> chứ không phải ${res.chain}. Kiểm lại trước khi ghi.</div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">
      <div><div class="kt-sub">Nợ gộp (sheet chính)</div><b>${formatVND(t.opening_debt_gross)}</b></div>
      <div><div class="kt-sub">− Ghi giảm chưa cấn trừ</div><b>${formatVND(t.deduction_open)}</b></div>
      <div><div class="kt-sub">= Nợ ròng</div><b>${formatVND(t.opening_debt)}</b></div>
      <div><div class="kt-sub">Dòng còn nợ</div><b>${res.n}</b></div>
      <div><div class="kt-sub">Nối được hóa đơn</div><b>${res.n_matched}</b>
        ${res.n_unmatched ? html`<div class="kt-sub" style="color:var(--kt-warning)">${res.n_unmatched} dòng chưa nối</div>` : ""}</div>
      ${res.n_replaced
        ? html`<div><div class="kt-sub">Có hóa đơn thay thế</div>
            <b>${res.n_replaced}</b> · ${formatVND(res.amount_replaced)}
            ${res.n_replaced_missing
              ? html`<div class="kt-sub" style="color:var(--kt-danger)">${res.n_replaced_missing} dòng ERPNext chưa có số mới</div>`
              : ""}</div>`
        : ""}
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Nhóm</th><th class="num">Số dòng</th><th class="num">Tiền</th></tr></thead>
        <tbody>${kinds.map((k) => html`<tr>
          <td>${k.label}</td><td class="num">${k.n}</td><td class="num">${formatVND(k.amount)}</td>
        </tr>`)}</tbody>
      </table></div>
    </div></div>

    ${(res.warnings || []).map((w) => html`<div class="kt-card kt-mb"
        style="border-left:4px solid var(--kt-warning)">
        <div class="kt-card-body kt-sub">${w}</div></div>`)}

    ${res.unmatched_sample && res.unmatched_sample.length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:8px">
            <b>${res.n_unmatched} dòng chưa nối được hóa đơn</b> — nhập vào vẫn được, nhưng
            phải xử lý hết thì mới CHỐT được.</div>
          <div class="kt-table-wrap" style="max-height:28vh;overflow:auto">
            <table class="kt-table">
              <thead><tr><th>Dòng</th><th>Số HĐ</th><th>Ngày</th><th class="num">Còn nợ</th><th>Vì sao</th></tr></thead>
              <tbody>${res.unmatched_sample.map((r) => html`<tr>
                <td>${r.source_row}</td><td><code>${r.inv_no || "—"}</code></td>
                <td>${r.inv_date ? formatDate(r.inv_date) : "—"}</td>
                <td class="num">${formatVND(r.remaining)}</td>
                <td><code class="kt-sub">${r.match_method}</code></td>
              </tr>`)}</tbody>
            </table></div>
        </div></div>`
      : ""}

    <div class="kt-sub">${res.note}</div>
    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
      <span class="kt-sub">Ngày chốt <b>${formatDate(args.cutover)}</b> · ERPNext từ <b>${formatDate(args.golive)}</b></span>
      ${!res.blocked
        ? html`<button class="kt-btn kt-btn--success" id="ob-go" style="margin-left:auto">
            <i class="fas fa-check"></i> Nhập ${res.n} dòng (trạng thái Nháp)
          </button>`
        : ""}
    </div>
  `);

  const go = modal.body.querySelector("#ob-go");
  if (go) go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      const out = await api.mtOpeningCommit({ ...args, expected_hash: res.plan_hash });
      toast(out.message, "success");
      modal.close();
      state.openName = out.name; state.openOnly = ""; state.page = 1;
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
    }
  });
}

// ── Một bản số dư: xử lý dòng treo rồi chốt ───────────────────────────────
const OB_FILTERS = [
  { key: "", label: "Tất cả dòng" },
  { key: "treo", label: "Còn treo" },
  { key: "review", label: "Máy đoán — cần review" },
  { key: "co_hoa_don", label: "Phải khớp ERPNext" },
  { key: "truoc_golive", label: "Trước go-live" },
  { key: "chua_co_hoa_don", label: "Chưa có số hóa đơn" },
];

const OB_CONF_TONE = { "Chắc chắn": "green", "Cần review": "yellow", "Không khớp": "red" };

async function loadOpeningDoc(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtOpeningGet({
      name: state.openName, only: state.openOnly || undefined,
      page: state.page, page_size: 50,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="ob-back">Quay lại</button></div>`);
    const b = container.querySelector("#ob-back");
    if (b) b.addEventListener("click", () => { state.openName = ""; loadTab(container, state); });
    return;
  }
  const d = res.doc;
  const rows = res.rows || [];
  const final = d.status === "Đã chốt";

  setHTML(body, html`
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="ob-back">
        <i class="fas fa-arrow-left"></i> Mọi chuỗi</button>
      <b>${d.chain}</b>
      <span class="kt-badge kt-badge--${OB_TONE[d.status] || "gray"}">${d.status}</span>
      <span class="kt-sub">chốt ngày ${formatDate(d.cutover_date)} · ERPNext từ ${formatDate(d.golive_date)}</span>
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px">
      <div><div class="kt-sub">Nợ gộp</div><b>${formatVND(d.opening_debt_gross)}</b></div>
      <div><div class="kt-sub">− Ghi giảm chưa cấn trừ</div><b>${formatVND(d.deduction_open)}</b></div>
      <div><div class="kt-sub">− Đơn chưa xuất hóa đơn</div><b>${formatVND(d.no_invoice_amount)}</b>
        <div class="kt-sub">theo dõi ở danh sách đợt giao, không phải phải thu</div></div>
      <div><div class="kt-sub">= CÔNG NỢ MANG SANG</div><b>${formatVND(d.debt_carried)}</b></div>
      <div><div class="kt-sub">Dòng còn nợ</div><b>${d.n_rows}</b>
        <div class="kt-sub">${d.n_matched} nối được · ${d.n_unmatched} treo</div></div>
      ${final ? html`<div><div class="kt-sub">Hóa đơn đã tất toán</div><b>${d.n_settled}</b></div>` : ""}
    </div></div>

    ${d.n_unmatched
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body kt-sub">
            <b>${d.n_unmatched} dòng chưa nối được hóa đơn ERPNext.</b> Chốt khi còn dòng ở đây
            là để đúng những hóa đơn đó rơi vào vế "không có trong danh sách" và bị coi là
            đã thanh toán — nợ thật biến mất. Nối hóa đơn cho từng dòng, hoặc đánh dấu
            "Bỏ qua" nếu đã xem và xác nhận không có hóa đơn tương ứng.
          </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <select class="kt-input kt-input--sm" id="ob-only">
        ${OB_FILTERS.map((f) => html`<option value="${f.key}" ${state.openOnly === f.key ? "selected" : ""}>${f.label}</option>`)}
      </select>
      <span class="kt-sub">${res.total} dòng</span>
      ${res.can_manage
        ? html`<span style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap">
            ${final
              ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="ob-reopen">
                  <i class="fas fa-lock-open"></i> Mở lại về Nháp</button>`
              : html`
                  <button class="kt-btn kt-btn--danger kt-btn--sm" id="ob-del">
                    <i class="fas fa-trash"></i> Xóa bản này</button>
                  <button class="kt-btn kt-btn--success kt-btn--sm" id="ob-final">
                    <i class="fas fa-stamp"></i> Xem tác động &amp; chốt</button>`}
          </span>`
        : ""}
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có dòng nào trong bộ lọc này.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Dòng</th><th>Số HĐ</th><th>Ngày</th><th>Bên mua trong file</th>
              <th class="num">Còn nợ</th><th>Nhóm</th><th>Hóa đơn ERPNext</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td>${r.source_row}</td>
                <td><code>${r.inv_no || "—"}</code></td>
                <td>${r.inv_date ? formatDate(r.inv_date) : html`<span class="kt-sub">—</span>`}</td>
                <td class="kt-sub">${r.party || "—"}</td>
                <td class="num">${formatVND(r.remaining)}</td>
                <td><span class="kt-sub">${res.kind_label[r.kind] || r.kind}</span></td>
                <td>${r.sales_invoice
                  ? html`<a href="/app/sales-invoice/${r.sales_invoice}" target="_blank">${r.sales_invoice}</a>
                      <div><span class="kt-badge kt-badge--${OB_CONF_TONE[r.match_confidence] || "gray"}">${r.match_confidence}</span></div>`
                  : (r.resolution
                    ? html`<span class="kt-badge kt-badge--gray">${r.resolution}</span>`
                    : html`<code class="kt-sub">${r.match_method}</code>`)}</td>
                <td>${res.can_manage && !final && r.kind === "co_hoa_don"
                  ? html`<button class="kt-btn kt-btn--outline kt-btn--sm ob-pick" data-row="${r.row}">
                      <i class="fas fa-link"></i></button>`
                  : ""}</td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "dòng")}
        </div></div>`}
  `);

  bindPager(container, state);
  const back = container.querySelector("#ob-back");
  if (back) back.addEventListener("click", () => {
    state.openName = ""; state.page = 1; loadTab(container, state);
  });
  const only = container.querySelector("#ob-only");
  if (only) only.addEventListener("change", (e) => {
    state.openOnly = e.target.value; state.page = 1; loadTab(container, state);
  });
  container.querySelectorAll(".ob-pick").forEach((b) => {
    const row = rows.find((r) => String(r.row) === b.dataset.row);
    b.addEventListener("click", () => openOpeningPick(container, state, d, row));
  });

  const fin = container.querySelector("#ob-final");
  if (fin) fin.addEventListener("click", () => openOpeningFinalize(container, state, d));
  const reo = container.querySelector("#ob-reopen");
  if (reo) reo.addEventListener("click", async () => {
    try {
      const out = await api.mtOpeningReopen(d.name);
      toast(out.message, "success");
      loadTab(container, state);
    } catch (e) { toast(e.message, "error"); }
  });
  const del = container.querySelector("#ob-del");
  if (del) del.addEventListener("click", async () => {
    if (!confirm(`Xóa bản số dư đầu kỳ của ${d.chain}? Toàn bộ ${d.n_rows} dòng sẽ mất.`)) return;
    try {
      const out = await api.mtOpeningDelete(d.name);
      toast(out.message, "success");
      state.openName = ""; loadTab(container, state);
    } catch (e) { toast(e.message, "error"); }
  });
}

// ── Chọn hóa đơn cho một dòng treo ────────────────────────────────────────
async function openOpeningPick(container, state, doc, row) {
  const modal = openModal({
    title: `Dòng ${row.source_row} — hóa đơn ${row.inv_no || "(không số)"}`,
    icon: "fa-link",
    maxWidth: 820,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let box = null;

  async function draw(q) {
    let res;
    try {
      res = await api.mtOpeningSearchInvoices({ name: doc.name, row: row.row, q });
    } catch (e) {
      setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
      return;
    }
    setHTML(modal.body, html`
      <div class="kt-sub" style="margin-bottom:10px">
        File ghi: số <b>${row.inv_no || "—"}</b>${row.inv_replaced_by
          ? html` <span class="kt-badge kt-badge--red">đã xóa bỏ</span> → thay thế <b>${row.inv_replaced_by}</b>`
          : ""}${row.inv_date ? html` · ngày <b>${formatDate(row.inv_date)}</b>` : ""}
        · tổng <b>${formatVND(row.gross)}</b> · còn nợ <b>${formatVND(row.remaining)}</b>.
        Máy dừng ở <code>${row.match_method}</code>.
      </div>
      ${res.message ? html`<div class="kt-sub" style="color:var(--kt-warning);margin-bottom:10px">${res.message}</div>` : ""}
      ${res.note_replaced
        ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${res.has_live_no ? "warning" : "danger"})">
            <div class="kt-card-body kt-sub" style="white-space:pre-line">${res.note_replaced}</div></div>`
        : ""}
      ${res.note ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
          <div class="kt-card-body kt-sub">${res.note}</div></div>` : ""}

      ${(res.line.n_matched_docs || 0)
        ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
            <div class="kt-sub" style="margin-bottom:8px">Đã nối ${res.line.n_matched_docs} chứng từ:</div>
            <div class="kt-table-wrap"><table class="kt-table">
              <tbody>
                ${(res.matches || []).map((m) => html`<tr>
                  <td><a href="/app/sales-invoice/${m.sales_invoice}" target="_blank">${m.sales_invoice}</a>
                    <div class="kt-sub">${m.role}${m.si_posting_date ? ` · ${formatDate(m.si_posting_date)}` : ""}</div>
                    ${m.si_is_return && !m.return_against
                      ? html`<div class="kt-sub" style="color:var(--kt-danger)">
                          chưa khai Return Against — KHÔNG tự trừ vào hóa đơn nào</div>`
                      : ""}</td>
                  <td class="num"><b>${m.si_amount < 0 ? "−" : "+"}${formatVND(Math.abs(m.si_amount))}</b></td>
                  <td><button class="kt-btn kt-btn--outline kt-btn--sm ob-unlink" data-si="${m.sales_invoice}">
                    <i class="fas fa-link-slash"></i></button></td>
                </tr>`)}
                <tr>
                  <td><b>Cộng các chứng từ</b><div class="kt-sub">file ghi ${formatVND(res.line.gross)}</div></td>
                  <td class="num"><b>${formatVND(res.line.match_amount)}</b></td>
                  <td>${Math.abs(res.line.match_diff || 0) < 1
                    ? html`<span class="kt-badge kt-badge--green">khớp</span>`
                    : html`<span class="kt-badge kt-badge--red">lệch ${formatVNDShort(res.line.match_diff)}</span>`}</td>
                </tr>
              </tbody>
            </table></div>
          </div></div>`
        : ""}
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <input class="kt-input kt-input--sm" id="ob-q" placeholder="Tìm theo SỐ hóa đơn, mã chứng từ, hoặc tên khách" value="${q || ""}">
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="ob-find"><i class="fas fa-magnifying-glass"></i></button>
      </div>
      <div class="kt-sub" style="margin-bottom:8px">
        Chỉ hiện hóa đơn của chuỗi ${res.chain}, xếp cái GẦN NHẤT lên trên.
      </div>
      ${!(res.rows || []).length
        ? html`<div class="kt-empty"><p>Chuỗi ${res.chain} không có hóa đơn nào khớp bộ lọc.</p></div>`
        : html`<div class="kt-table-wrap" style="max-height:40vh;overflow:auto">
            <table class="kt-table">
              <thead><tr>
                <th>Số HĐ</th><th>Ngày</th><th>Khách</th>
                <th class="num">Tổng</th><th class="num">Còn phải thu</th><th>Vì sao gợi ý</th><th></th>
              </tr></thead>
              <tbody>${res.rows.map((r) => html`<tr>
                <td>${r.inv_no
                    ? html`<code>${r.inv_no}</code>` : html`<span class="kt-sub">—</span>`}
                  <div class="kt-sub">${r.name}</div></td>
                <td>${formatDate(r.posting_date)}</td>
                <td>${r.customer_name || r.customer}</td>
                <td class="num">
                  <b style="${r.is_return ? "color:var(--kt-danger)" : ""}">${r.signed < 0 ? "−" : "+"}${formatVND(Math.abs(r.signed))}</b>
                  ${r.is_return ? html`<div class="kt-sub">hóa đơn trả về</div>` : ""}
                  ${r.returned
                    ? html`<div class="kt-sub">− trả lại ${formatVNDShort(r.returned)}</div>`
                    : ""}</td>
                <td class="num">${r.is_return
                  ? html`<span class="kt-sub">—</span>`
                  : html`<b>${formatVND(r.net_due)}</b>`}</td>
                <td>${(r.why || []).map((w) => html`<span class="kt-badge kt-badge--${
                  w.indexOf("XÓA BỎ") >= 0 ? (res.has_live_no ? "gray" : "yellow") : "green"}">${w}</span> `)}
                  ${r.is_dead_no && !res.has_live_no
                    ? html`<div class="kt-sub"><b>chọn tờ này để giữ nợ lại</b></div>`
                    : ""}</td>
                <td>${r.linked
                  ? html`<span class="kt-badge kt-badge--gray">đã nối dòng này</span>`
                  : (r.taken
                    ? html`<span class="kt-sub">đã nối dòng khác</span>`
                    : html`<button class="kt-btn kt-btn--success kt-btn--sm ob-take" data-si="${r.name}">Chọn</button>`)}</td>
              </tr>`)}</tbody>
            </table></div>`}
      <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
        ${(res.line.n_matched_docs || 0)
          ? html`<button class="kt-btn kt-btn--success kt-btn--sm" id="ob-done">
              <i class="fas fa-check"></i> Xong dòng này</button>`
          : html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="ob-skip">
              <i class="fas fa-forward"></i> Bỏ qua dòng này</button>`}
      </div>
      <div class="kt-sub" style="margin-top:8px">
        Nối được NHIỀU chứng từ cho một dòng — bấm "Chọn" lần lượt từng cái, phép cộng ở
        trên phải ra đúng số trong file thì mới chốt được.
        <b>"Bỏ qua"</b> = đã xem và xác nhận dòng này không có chứng từ ERPNext tương ứng.
        Nó cho phép chốt và KHÔNG giữ hóa đơn nào lại — nghĩa là hóa đơn tương ứng (nếu
        có tồn tại) sẽ bị coi là <b>đã thanh toán</b> khi chốt. Chỉ bỏ qua khi chắc.
      </div>
    `);

    const find = modal.body.querySelector("#ob-find");
    box = modal.body.querySelector("#ob-q");
    if (find) find.addEventListener("click", () => draw(box.value));
    if (box) box.addEventListener("keydown", (e) => { if (e.key === "Enter") draw(box.value); });

    // Nối THÊM chứ không thay: một hóa đơn MISA ứng được với nhiều chứng từ.
    // Ở lại trong modal để còn nối tiếp cái thứ hai và nhìn phép cộng.
    async function relink(fn, payload, close) {
      try {
        const out = await fn({ name: doc.name, row: row.row, ...payload });
        toast(out.message, "success");
        if (out.warning) toast(out.warning, "error");
        row = { ...row, ...out.line };
        if (close) { modal.close(); loadTab(container, state); } else { draw(box ? box.value : ""); }
      } catch (e) { toast(e.message, "error"); }
    }
    modal.body.querySelectorAll(".ob-take").forEach((b) => {
      b.addEventListener("click", () => relink(api.mtOpeningAddMatch, { sales_invoice: b.dataset.si }));
    });
    modal.body.querySelectorAll(".ob-unlink").forEach((b) => {
      b.addEventListener("click", () => relink(api.mtOpeningRemoveMatch, { sales_invoice: b.dataset.si }));
    });
    const done = modal.body.querySelector("#ob-done");
    if (done) done.addEventListener("click", () => { modal.close(); loadTab(container, state); });
    const skip = modal.body.querySelector("#ob-skip");
    if (skip) skip.addEventListener("click", () =>
      relink(api.mtOpeningSetLine, { resolution: "Bỏ qua" }, true));
  }

  draw("");
}

// ── Chốt: cho xem đúng cái sắp biến mất ───────────────────────────────────
async function openOpeningFinalize(container, state, doc) {
  const modal = openModal({
    title: `Chốt số dư đầu kỳ — ${doc.chain}`,
    icon: "fa-stamp",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await api.mtOpeningFinalizePreview(doc.name);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px">
      <div><div class="kt-sub">Hóa đơn RỜI khỏi công nợ</div>
        <b style="font-size:1.2em">${res.n_settled}</b>
        <div class="kt-sub">${formatVND(res.amount_settled)}</div></div>
      <div><div class="kt-sub">Hóa đơn Ở LẠI (có trong danh sách)</div>
        <b style="font-size:1.2em">${res.n_kept}</b>
        <div class="kt-sub">${formatVND(res.amount_kept)}</div></div>
      <div><div class="kt-sub">Dòng còn treo</div>
        <b style="font-size:1.2em;color:${res.n_unresolved ? "var(--kt-danger)" : "inherit"}">${res.n_unresolved}</b></div>
    </div></div>

    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
      <div class="kt-card-body kt-sub">${res.note}</div></div>

    ${res.n_unresolved
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body kt-sub">
            Còn <b>${res.n_unresolved} dòng</b> chưa nối được hóa đơn — chưa chốt được.
            Xử lý hết ở bộ lọc "Còn treo" rồi quay lại.
          </div></div>`
      : ""}

    ${res.n_stale
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body kt-sub">
            <b>${res.n_stale} chứng từ đã nối nay KHÔNG còn hiệu lực</b> (bị hủy hoặc đã
            sửa đổi). Chúng không giữ được hóa đơn nào lại nữa — mọi truy vấn nợ đòi
            chứng từ đã ghi sổ. Nối lại sang chứng từ mới TRƯỚC khi chốt, nếu không
            khoản nợ đó bị coi là đã thanh toán.
            ${(res.stale_matches || []).slice(0, 6).map((x) => html`<div class="kt-sub">
              · <code>${x.sales_invoice}</code> — ${x.reason}</div>`)}
          </div></div>`
      : ""}

    ${Math.abs(res.amount_kept_diff || 0) > 1
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            Số giữ lại theo <b>file</b> là ${formatVND(res.amount_kept)}, nhưng theo
            <b>ERPNext</b> (đúng công thức nợ) là ${formatVND(res.amount_kept_erp)} —
            lệch <b>${formatVND(res.amount_kept_diff)}</b>.
            <div style="margin-top:6px">Nợ mang sang thật lấy theo số ERPNext. Lệch lớn
            thường là giữ nhầm tờ: tờ đã xóa bỏ thay vì tờ thay thế.</div>
          </div></div>`
      : ""}

    ${res.n_amount_off
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            <b>${res.n_amount_off} dòng</b> có tổng các chứng từ đã nối KHÁC số trong file
            (chênh ${formatVND(res.amount_off_total)}). Hay gặp nhất: nối hóa đơn đi mà
            chưa nối hóa đơn trả về.
            <div style="margin-top:6px">Việc này <b>KHÔNG làm sai đồng nào</b> — số nợ lấy
            từ chính ERPNext, không lấy từ file — nên vẫn chốt được. Nhưng hồ sơ đối chiếu
            sẽ thiếu vế. Nối nốt thì hơn.</div>
            ${(res.amount_off || []).slice(0, 5).map((l) => html`<div class="kt-sub">
              · dòng ${l.source_row} · HĐ ${l.inv_no || "—"} · file ${formatVND(l.gross)}
              · đã nối ${formatVND(l.match_amount)} · lệch ${formatVND(l.match_diff)}</div>`)}
          </div></div>`
      : ""}

    ${(res.sample || []).length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:8px">
            ${res.n_settled} hóa đơn sẽ được coi là đã thanh toán (hiện ${Math.min(res.sample.length, res.n_settled)} cái gần nhất):
          </div>
          <div class="kt-table-wrap" style="max-height:34vh;overflow:auto">
            <table class="kt-table">
              <thead><tr><th>Hóa đơn</th><th>Ngày</th><th>Khách</th><th class="num">Tổng</th></tr></thead>
              <tbody>${res.sample.map((r) => html`<tr>
                <td><code>${r.name}</code></td>
                <td>${formatDate(r.posting_date)}</td>
                <td>${r.customer_name}</td>
                <td class="num">${formatVND(r.grand_total)}</td>
              </tr>`)}</tbody>
            </table></div>
        </div></div>`
      : html`<div class="kt-card kt-mb"><div class="kt-card-body kt-sub">
          Không có hóa đơn ERPNext nào rơi vào diện tất toán — hoặc chuỗi chưa gán khách
          hàng, hoặc mọi hóa đơn trước ngày chốt đều đã có tên trong danh sách còn nợ.
        </div></div>`}

    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
      <span class="kt-sub">Chốt xong vẫn mở lại được — luật này là cách ĐỌC, không phải bút toán.</span>
      ${res.ready && res.can_manage
        ? html`<button class="kt-btn kt-btn--success" id="ob-final-go" style="margin-left:auto">
            <i class="fas fa-stamp"></i> Chốt số dư đầu kỳ ${doc.chain}
          </button>`
        : ""}
    </div>
  `);

  const go = modal.body.querySelector("#ob-final-go");
  if (go) go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      const out = await api.mtOpeningFinalize({ name: doc.name, expected_hash: res.plan_hash });
      toast(out.message, "success");
      modal.close();
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// HÀNG HOÀN CHỜ XỬ LÝ
//
// Đơn vị của màn này là MỘT LẦN HÀNG QUAY VỀ, không phải một tờ hóa đơn. Sổ
// theo dõi đã đếm "phiếu trả chưa có chứng từ" rồi; cái nó không đếm được là
// lần hàng về mà CHƯA AI LẬP PHIẾU TRẢ — chưa có phiếu thì không có gì để đếm,
// và việc đó vô hình với mọi màn hình khác.
//
// Ô "Chưa vào sổ" đứng ĐẦU vì nó là ô duy nhất mà việc còn nằm bên app vận
// chuyển, ngoài tầm nhìn của kế toán.
// ═══════════════════════════════════════════════════════════════════════════

const HOAN_BUCKETS = [
  { key: "chua_vao_so", label: "Chưa vào sổ", icon: "fa-inbox", tone: "neg",
    sub: "phiếu sự cố bên vận chuyển chưa ai nhận" },
  { key: "chua_phieu_tra", label: "Chưa lập phiếu trả", icon: "fa-file-circle-xmark", tone: "neg",
    sub: "công nợ vẫn đang đòi đủ tiền hóa đơn gốc" },
  { key: "chua_chung_tu", label: "Chưa có chứng từ thuế", icon: "fa-file-invoice", tone: "warn",
    sub: "đã có phiếu trả, chưa có hóa đơn thay thế/điều chỉnh" },
  { key: "xong", label: "Đã đủ chứng từ", icon: "fa-circle-check", tone: "pos",
    sub: "gồm cả kết luận 'không cần chứng từ'" },
];

const HOAN_CT_TONE = {
  "Hóa đơn thay thế": "yellow",
  "Hóa đơn điều chỉnh": "yellow",
  "Siêu thị xuất hóa đơn trả": "gray",
  "Không cần chứng từ": "green",
};

const HOAN_HANG_TONE = {
  "Chưa về": "red", "Đang về": "yellow", "Đã về sân": "gray", "Đã lọc xong": "green",
};

// Tuổi việc — TÍNH TỪ NGÀY XẢY RA, và "chưa biết" KHÔNG được vẽ thành 0 ngày.
// Phiếu sự cố cũ chưa khai ngày xảy ra thì tuổi là không biết; in "0 ngày" là
// nói với kế toán rằng việc vừa mới phát sinh.
function hoanAge(r) {
  if (r.tuoi === null || r.tuoi === undefined) {
    return html`<span class="kt-sub" title="Phiếu chưa khai ngày xảy ra">chưa rõ tuổi</span>`;
  }
  const tone = r.tuoi >= 30 ? "danger" : (r.tuoi >= 14 ? "warning" : "muted");
  return html`<span class="kt-sub" style="color:var(--kt-${tone})">${r.tuoi} ngày</span>`;
}

function hoanViec(r) {
  return html`
    ${r.loai_su_co || html`<span class="kt-sub">—</span>`}
    ${r.huong_xu_ly ? html`<div class="kt-sub">→ ${r.huong_xu_ly}</div>` : ""}
    ${(r.da_doi || []).length
      ? html`<div class="kt-sub" style="color:var(--kt-warning)">
          <i class="fas fa-triangle-exclamation"></i>
          điều hành đã sửa ${r.da_doi.map((c) => c.field).join(", ")}
        </div>`
      : ""}`;
}

function hoanStats(d) {
  const c = d.counts || {};
  return html`<div class="kt-stats kt-mb">
    ${HOAN_BUCKETS.map((b) => html`<div class="kt-stat is-link hoan-tile" data-bucket="${b.key}"
        style="${d.bucket === b.key ? "border-color:var(--kt-primary)" : ""}">
      <div class="kt-stat-label"><i class="fas ${b.icon}"></i> ${b.label}</div>
      <div class="kt-stat-value ${c[b.key] ? b.tone : ""}">${c[b.key] || 0}</div>
      <div class="kt-stat-sub">${b.sub}</div>
    </div>`)}
  </div>`;
}

const hoanHeadUngVien = html`<tr>
  <th class="kt-col-mid">Ngày xảy ra</th>
  <th class="kt-col-mid">Phiếu sự cố</th>
  <th class="kt-col-mid">Hóa đơn gốc</th>
  <th class="kt-col-wide">Khách hàng</th>
  <th class="kt-col-wide">Việc</th>
  <th class="kt-col-mid">Hàng</th>
  <th class="kt-col-role"></th>
</tr>`;

const hoanHeadSo = html`<tr>
  <th class="kt-col-mid">Ngày xảy ra</th>
  <th class="kt-col-mid">Hóa đơn gốc</th>
  <th class="kt-col-wide">Khách hàng</th>
  <th class="kt-col-wide">Việc</th>
  <th class="kt-col-mid">Chứng từ cần</th>
  <th class="kt-col-wide">Phiếu trả</th>
  <th class="kt-col-mid">Hàng</th>
</tr>`;

function hoanRowUngVien(r) {
  return html`<tr>
    <td class="kt-col-mid">${r.ngay_xay_ra ? formatDate(r.ngay_xay_ra) : "—"}
      <div>${hoanAge(r)}</div></td>
    <td class="kt-col-mid">${r.su_co}
      ${r.trang_thai ? html`<div class="kt-sub">điều hành: ${r.trang_thai}</div>` : ""}</td>
    <td class="kt-col-mid">${r.sales_invoice}
      ${r.po_no ? html`<div class="kt-sub">PO ${r.po_no}</div>` : ""}</td>
    <td class="kt-col-wide">${r.customer_name || r.customer}
      <div class="kt-sub">${formatVNDShort(r.grand_total)}</div></td>
    <td class="kt-col-wide">${hoanViec(r)}</td>
    <td class="kt-col-mid">${r.trang_thai_hang
      ? html`<span class="kt-badge kt-badge--${HOAN_HANG_TONE[r.trang_thai_hang] || "gray"}">${r.trang_thai_hang}</span>`
      : html`<span class="kt-sub">—</span>`}
      ${r.tong_mat_duong
        ? html`<div class="kt-sub" style="color:var(--kt-danger)">mất đường ${formatVNDShort(r.tong_mat_duong)}</div>`
        : ""}</td>
    <td class="kt-col-role">
      <button class="kt-btn kt-btn--sm hoan-take" data-su-co="${r.su_co}"
        title="Nhận lần hàng về này vào sổ kế toán">Nhận</button>
      <div style="margin-top:4px">
        <button class="kt-btn kt-btn--outline kt-btn--sm hoan-skip" data-su-co="${r.su_co}"
          title="Hóa đơn gốc vẫn đúng — không chứng từ nào phải làm">Không cần</button>
      </div>
    </td>
  </tr>`;
}

function hoanRowSo(r) {
  const t = r.chung_tu_sieu_thi;
  return html`<tr class="hoan-row" data-name="${r.name}" style="cursor:pointer">
    <td class="kt-col-mid">${r.ngay_xay_ra ? formatDate(r.ngay_xay_ra) : "—"}
      <div>${hoanAge(r)}</div></td>
    <td class="kt-col-mid">${r.sales_invoice}
      ${r.po_no ? html`<div class="kt-sub">PO ${r.po_no}</div>` : ""}</td>
    <td class="kt-col-wide">${r.customer_name || r.customer}
      <div class="kt-sub">${r.chain || "chưa gán chuỗi"}</div></td>
    <td class="kt-col-wide">${hoanViec(r)}</td>
    <td class="kt-col-mid">${r.chung_tu_can
      ? html`<span class="kt-badge kt-badge--${HOAN_CT_TONE[r.chung_tu_can] || "gray"}">${r.chung_tu_can}</span>`
      : html`<span class="kt-sub" style="color:var(--kt-warning)">chưa chốt</span>`}</td>
    <td class="kt-col-wide">${r.credit_note
      ? html`${r.credit_note}
          <div class="kt-sub">${formatVNDShort(r.cn_amount)}${r.cn_date ? ` · ${formatDate(r.cn_date)}` : ""}</div>
          ${r.misa_no
            ? html`<div class="kt-sub" style="color:var(--kt-success)">HĐ ${r.misa_no}${t ? " · siêu thị xuất" : ""}</div>`
            : html`<div class="kt-sub" style="color:var(--kt-danger)">chưa có chứng từ thuế</div>`}`
      : html`<span class="kt-sub" style="color:var(--kt-danger)">chưa lập</span>`}</td>
    <td class="kt-col-mid">${r.trang_thai_hang
      ? html`<span class="kt-badge kt-badge--${HOAN_HANG_TONE[r.trang_thai_hang] || "gray"}">${r.trang_thai_hang}</span>`
      : html`<span class="kt-sub">—</span>`}
      ${r.tt_lech
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-border)">
          <div class="kt-card-body kt-sub">Trạng thái ở đây <b>suy lại lúc đọc</b> từ chứng
            từ hiện có, nên nó có thể khác cột đã lưu trên Desk — số hóa đơn MISA và dòng
            ghi giảm của bảng kê thường về SAU lần lưu cuối. Bấm Lưu một lần là cột kia
            đuổi kịp.</div></div>`
      : ""}

    ${r.su_co && !r.su_co_con
        ? html`<div class="kt-sub" style="color:var(--kt-warning)">mất phiếu sự cố</div>`
        : ""}</td>
  </tr>`;
}

async function loadHangHoan(container, state) {
  const body = container.querySelector("#mt-body");
  // Ở bàn làm việc của một chuỗi thì chuỗi ĐÃ được chọn — dùng luôn, không để
  // người dùng chọn lại một lần nữa rồi tự hỏi hai ô chuỗi khác nhau chỗ nào.
  const inChain = state.view === "chuoi";
  const chain = inChain ? state.chain : state.hoanChain;
  let d;
  try {
    d = await api.mtHoan({
      bucket: state.hoanBucket || undefined, chain: chain || undefined,
      search: state.search || undefined, page: state.page, page_size: 50,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  state.hoanBucket = d.bucket;

  // Nhận dòng cuối của trang 2 thì trang 2 hết dòng, và màn hình sẽ in
  // "mọi phiếu sự cố đều đã vào sổ" ngay dưới một cái thẻ đang ghi 50. Cùng
  // cái kẹp mà danh sách hóa đơn đã dùng — việc bấm xong một dòng không được
  // biến thành một câu kết luận sai về cả hàng đợi.
  if (!(d.rows || []).length && (d.total || 0) > 0 && state.page > 1) {
    state.page = d.pages || 1;
    return loadHangHoan(container, state);
  }

  const rows = d.rows || [];
  const ungVien = d.bucket === "chua_vao_so";

  setHTML(body, html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
      <div class="kt-card-body kt-sub">
        <b>Một dòng = một LẦN HÀNG QUAY VỀ, không phải một tờ hóa đơn.</b>
        Một hóa đơn có thể vừa móp lúc giao vừa bị trả hàng date — hai lần, hai phiếu trả,
        hai việc. Trạng thái giấy tờ ở đây do <b>máy suy từ chứng từ có thật</b>, không ai gõ,
        và cố ý KHÔNG đọc cột trạng thái bên điều hành: điều hành đóng phiếu ngay khi nhà xe
        xác nhận hàng về, còn hóa đơn điều chỉnh thì chưa ai xuất.
      </div></div>

    ${hoanStats(d)}

    <div class="kt-card kt-mb"><div class="kt-card-body"
        style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${inChain
        ? html`<span class="kt-sub">Đang xem <b>${state.chain}</b></span>`
        : html`<label class="kt-sub">Chuỗi
            <select class="kt-input kt-input--sm" id="hoan-chain">
              <option value="">— mọi chuỗi —</option>
              ${chainOptionHTML(state, state.hoanChain)}
            </select></label>`}
      ${d.bucket === "cho_xu_ly"
        ? html`<span class="kt-sub">Đang xem cả hai ô việc — bấm một thẻ ở trên để tách riêng.</span>`
        : html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="hoan-all">
            <i class="fas fa-list"></i> Xem cả hai ô việc
          </button>`}
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="hoan-new" style="margin-left:auto">
        <i class="fas fa-plus"></i> Lập dòng từ hóa đơn
      </button>
    </div></div>

    ${!d.vanchuyen && d.bucket === "chua_vao_so"
      ? html`<div class="kt-empty"><i class="fas fa-plug-circle-xmark"></i><p>${d.note}</p></div>`
      : !rows.length
        ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i>
            <p>${d.bucket === "chua_vao_so"
              ? "Mọi phiếu sự cố trên hóa đơn MT đều đã vào sổ."
              : d.bucket === "xong"
                ? "Chưa có lần hàng về nào đủ chứng từ."
                : "Không còn lần hàng về nào chờ xử lý."}</p></div>`
        : html`<div class="kt-card"><div class="kt-card-body">
            <div class="kt-sub" style="margin-bottom:8px">
              Việc CŨ NHẤT lên trước — tuổi tính từ <b>ngày xảy ra</b>, không phải ngày nhập
              phiếu. Nhà xe báo trễ vài ngày là thường, và tính từ ngày nhập giấu mất đúng
              phần chậm đó.
            </div>
            <div class="kt-table-wrap"><table class="kt-table">
              <thead>${ungVien ? hoanHeadUngVien : hoanHeadSo}</thead>
              <tbody>${rows.map((r) => (ungVien ? hoanRowUngVien(r) : hoanRowSo(r)))}</tbody>
            </table></div>
            ${pager(d, "lần hàng về")}
          </div></div>`}
  `);

  bindPager(container, state);
  bindHoan(container, state, d);
}

function bindHoan(container, state, d) {
  const reload = () => loadTab(container, state);

  container.querySelectorAll(".hoan-tile").forEach((el) => {
    el.addEventListener("click", () => {
      state.hoanBucket = el.dataset.bucket;
      state.page = 1;
      syncHash(state);
      reload();
    });
  });

  const ch = container.querySelector("#hoan-chain");
  if (ch) ch.addEventListener("change", () => {
    state.hoanChain = ch.value;
    state.page = 1;
    syncHash(state);
    reload();
  });

  container.querySelectorAll(".hoan-take").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const out = await api.mtHoanCreate({ su_co: b.dataset.suCo });
        toast("Đã nhận vào sổ — " + out.trang_thai_giay, "success");
        reload();
      } catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
  });

  // "Không cần chứng từ" KHÔNG phải một cái cờ bỏ qua: nó là một KẾT LUẬN, và
  // nó vẫn để lại một dòng sổ ghi ai kết luận, lúc nào. Bỏ qua bằng cờ thì làm
  // được đúng việc ẩn dòng, nhưng mất phần trả lời cho người soát sau.
  container.querySelectorAll(".hoan-skip").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api.mtHoanCreate({
          su_co: b.dataset.suCo, chung_tu_can: "Không cần chứng từ",
        });
        toast("Đã ghi kết luận: không cần chứng từ", "success");
        reload();
      } catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
  });

  container.querySelectorAll("tr.hoan-row").forEach((tr) => {
    tr.addEventListener("click", () => openHoanDetail(container, state, tr.dataset.name));
  });

  const all = container.querySelector("#hoan-all");
  if (all) all.addEventListener("click", () => {
    state.hoanBucket = "cho_xu_ly";
    state.page = 1;
    syncHash(state);
    reload();
  });

  const nw = container.querySelector("#hoan-new");
  if (nw) nw.addEventListener("click", () => openHoanNew(container, state, d));
}

// ── Lập dòng THẲNG TỪ HÓA ĐƠN ─────────────────────────────────────────────
//
// Không phải lần hàng về nào cũng có phiếu sự cố vận chuyển: hàng date siêu thị
// trả lại là giao dịch MỚI, thường không đi qua chuyến xe nào có sự cố. Bắt
// buộc phải có phiếu sự cố là đóng cửa với đúng một nửa nghiệp vụ.
function openHoanNew(container, state, d) {
  const modal = openModal({
    title: "Lập dòng hàng hoàn từ hóa đơn",
    icon: "fa-rotate-left",
    maxWidth: 560,
    body: html`
      <div class="kt-sub" style="margin-bottom:12px">
        Dùng khi lần hàng về KHÔNG có phiếu sự cố vận chuyển — hàng date / thời vụ siêu thị
        trả lại chẳng hạn. Có phiếu sự cố thì bấm <b>Nhận</b> ở ô "Chưa vào sổ" để dòng sổ
        nối được sang bên vận chuyển.
      </div>
      <label style="display:block">Hóa đơn gốc (Sales Invoice)
        <input class="kt-input" id="hn-si" placeholder="ACC-SINV-…"></label>
      <label style="display:block;margin-top:10px">Ngày xảy ra
        <input type="date" class="kt-input" id="hn-date">
        <div class="kt-sub">Ngày siêu thị trả hàng, không phải hôm nay. Tuổi việc tính từ ô này.</div>
      </label>
      <label style="display:block;margin-top:10px">Chứng từ thuế cần làm
        <select class="kt-input" id="hn-ct">
          <option value="">— chốt sau —</option>
          ${(d.chung_tu_options || []).map((x) => html`<option value="${x}">${x}</option>`)}
        </select></label>
      <label style="display:block;margin-top:10px">Ghi chú
        <textarea class="kt-input" id="hn-note" rows="2"></textarea></label>
      <div style="display:flex;gap:8px;margin-top:14px">
        <button class="kt-btn kt-btn--success" id="hn-save"><i class="fas fa-check"></i> Lập dòng</button>
      </div>`,
  });
  const val = (id) => modal.body.querySelector(id).value.trim();
  modal.body.querySelector("#hn-save").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#hn-save");
    btn.disabled = true;
    try {
      await api.mtHoanCreate({
        sales_invoice: val("#hn-si"), ngay_xay_ra: val("#hn-date") || undefined,
        chung_tu_can: val("#hn-ct") || undefined, ghi_chu: val("#hn-note") || undefined,
      });
      toast("Đã lập dòng hàng hoàn", "success");
      modal.close();
      loadTab(container, state);
    } catch (e) { toast(e.message, "error"); btn.disabled = false; }
  });
}

// ── Chi tiết một lần hàng về ──────────────────────────────────────────────
async function openHoanDetail(container, state, name) {
  const modal = openModal({
    title: "Lần hàng quay về",
    icon: "fa-rotate-left",
    maxWidth: 820,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let r;
  try { r = await api.mtHoanGet(name); }
  catch (e) { setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`); return; }

  const items = r.items || [];
  const cands = r.phieu_tra_ung_vien || [];

  setHTML(modal.body, html`
    <div class="kt-sub" style="margin-bottom:10px">
      ${r.sales_invoice} · ${r.customer_name || r.customer}
      ${r.chain ? ` · ${r.chain}` : ""}${r.po_no ? ` · PO ${r.po_no}` : ""}
      ${r.su_co ? html` · phiếu sự cố <b>${r.su_co}</b>${r.su_co_trang_thai ? ` (điều hành: ${r.su_co_trang_thai})` : ""}` : ""}
    </div>

    ${(r.da_doi || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            <b>Điều hành đã sửa phiếu sự cố sau khi dòng này vào sổ.</b>
            Màn hình đang hiện giá trị MỚI; bản chép trên sổ vẫn là bản cũ:
            ${r.da_doi.map((c) => html`<div>· ${c.field}: <s>${c.cu || "(trống)"}</s> → <b>${c.moi || "(trống)"}</b></div>`)}
            <button class="kt-btn kt-btn--outline kt-btn--sm" id="hd-sync" style="margin-top:8px">
              <i class="fas fa-rotate"></i> Chép lại vào sổ
            </button>
          </div></div>`
      : ""}

    ${r.tt_lech
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-border)">
          <div class="kt-card-body kt-sub">Trạng thái ở đây <b>suy lại lúc đọc</b> từ chứng
            từ hiện có, nên nó có thể khác cột đã lưu trên Desk — số hóa đơn MISA và dòng
            ghi giảm của bảng kê thường về SAU lần lưu cuối. Bấm Lưu một lần là cột kia
            đuổi kịp.</div></div>`
      : ""}

    ${r.su_co && !r.su_co_con
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">Không còn đọc được phiếu sự cố <b>${r.su_co}</b>
            (đã xóa bên vận chuyển, hoặc site chưa cài app đó). Dòng sổ giữ bản chép cũ —
            việc giấy tờ vẫn là việc.</div></div>`
      : ""}

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <label>Chứng từ thuế cần làm
        <select class="kt-input" id="hd-ct">
          <option value="">— chưa chốt —</option>
          ${(r.chung_tu_options || []).map((x) =>
            html`<option value="${x}" ${r.chung_tu_can === x ? "selected" : ""}>${x}</option>`)}
        </select>
        ${(r.le_cua_chuoi || []).length
          ? html`<div class="kt-sub">Chuỗi này trước giờ:
              ${r.le_cua_chuoi.map((x) => `${x.quan_he} ${x.n} lần`).join(" · ")}</div>`
          : ""}
      </label>
      <label>Phiếu trả hàng (đã ghi sổ)
        <select class="kt-input" id="hd-cn">
          <option value="">— chưa lập —</option>
          ${cands.map((c) => html`<option value="${c.name}" ${r.credit_note === c.name ? "selected" : ""}
            ${c.da_dung ? "disabled" : ""}>${c.name} · ${formatVND(c.amount)}${c.da_dung ? ` (đã dùng ở ${c.dung_o})` : ""}${c.hop_le === false ? " — KHÔNG còn hợp lệ" : ""}</option>`)}
        </select>
        ${cands.some((c) => c.la_hien_tai && c.hop_le === false)
          ? html`<div class="kt-sub" style="color:var(--kt-danger)">
              Phiếu trả đang nối <b>${r.credit_note}</b> không còn hợp lệ — đã hủy, hoặc
              không còn trả cho hóa đơn này. Chọn phiếu thay thế rồi Lưu; bỏ trống là gỡ
              hẳn, và dòng quay lại "Chưa lập phiếu trả".</div>`
          : ""}
        ${!cands.length
          ? html`<div class="kt-sub" style="color:var(--kt-warning)">Hóa đơn gốc chưa có phiếu
              trả nào ĐÃ GHI SỔ. Lập phiếu trả trên ERPNext (khai Return Against), ghi sổ,
              rồi quay lại đây.</div>`
          : ""}
      </label>
      <label>Trạng thái hàng vật lý
        <select class="kt-input" id="hd-hang" ${r.khoa_hang ? "disabled" : ""}>
          <option value="">—</option>
          ${(r.trang_thai_hang_options || []).map((x) =>
            html`<option value="${x}" ${r.trang_thai_hang === x ? "selected" : ""}>${x}</option>`)}
        </select>
        ${r.khoa_hang
          ? html`<div class="kt-sub">Điều phối và thủ kho giữ ô này trên phiếu sự cố
              <b>${r.su_co}</b> — màn này đọc thẳng sang. Sửa ở đây thì lần mở sau nó quay
              về giá trị bên đó.</div>`
          : ""}
      </label>
      <label>Ngày hàng về sân
        <input type="date" class="kt-input" id="hd-ngay" value="${r.ngay_hang_ve || ""}"
          ${r.khoa_hang ? "disabled" : ""}></label>
    </div>

    <label style="display:block;margin-top:10px">Ghi chú
      <textarea class="kt-input" id="hd-note" rows="2">${r.ghi_chu || ""}</textarea></label>

    <div class="kt-sub" style="margin-top:10px;white-space:pre-line;border-left:3px solid var(--kt-border);padding-left:10px">${r.chung_tu_note}</div>

    ${items.length
      ? html`<div style="margin-top:14px">
          <div class="kt-sub" style="margin-bottom:6px">
            <b>Mã hàng — số của điều phối và thủ kho, đọc thẳng bên vận chuyển.</b>
            App này KHÔNG chép lại: hai trong ba số lượng chỉ họ biết.
          </div>
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th class="kt-col-wide">Mã hàng</th><th class="num">SL trả</th>
              <th class="num">SL về sân</th><th class="num">SL dùng được</th>
              <th class="num">Mất trên đường</th></tr></thead>
            <tbody>${items.map((it) => html`<tr>
              <td class="kt-col-wide">${it.item_name || it.item_code}
                <div class="kt-sub">${it.item_code}</div></td>
              <td class="num">${it.sl_tra || 0}</td>
              <td class="num">${it.sl_ve || 0}</td>
              <td class="num">${it.sl_nhap_lai || 0}</td>
              <td class="num">${it.tien_mat_duong ? formatVND(it.tien_mat_duong) : "—"}</td>
            </tr>`)}</tbody>
          </table></div>
          ${r.tong_mat_duong
            ? html`<div class="kt-sub" style="margin-top:6px">Tổng mất trên đường
                <b style="color:var(--kt-danger)">${formatVND(r.tong_mat_duong)}</b> —
                việc đòi nhà xe theo dõi bên app vận chuyển, KHÔNG sinh bút toán ở đây.</div>`
            : ""}
        </div>`
      : ""}

    <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
      <button class="kt-btn kt-btn--success" id="hd-save"><i class="fas fa-check"></i> Lưu</button>
      <span class="kt-sub" style="align-self:center">Trạng thái giấy tờ do máy suy lại sau khi lưu —
        hiện là <b>${r.trang_thai_giay}</b>.</span>
      ${r.can_manage && !r.credit_note
        ? html`<button class="kt-btn kt-btn--danger kt-btn--sm" id="hd-del" style="margin-left:auto">
            <i class="fas fa-trash"></i> Xóa dòng
          </button>`
        : ""}
    </div>
  `);

  const val = (id) => modal.body.querySelector(id).value.trim();
  modal.body.querySelector("#hd-save").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#hd-save");
    btn.disabled = true;
    try {
      const out = await api.mtHoanSave({
        name, chung_tu_can: val("#hd-ct"), credit_note: val("#hd-cn"),
        ghi_chu: val("#hd-note"),
        ...(r.khoa_hang
          ? {}
          : { trang_thai_hang: val("#hd-hang"), ngay_hang_ve: val("#hd-ngay") }),
      });
      toast("Đã lưu — " + out.trang_thai_giay, "success");
      modal.close();
      loadTab(container, state);
    } catch (e) { toast(e.message, "error"); btn.disabled = false; }
  });

  const sync = modal.body.querySelector("#hd-sync");
  if (sync) sync.addEventListener("click", async () => {
    sync.disabled = true;
    try {
      await api.mtHoanSync(name);
      toast("Đã chép lại từ phiếu sự cố", "success");
      modal.close();
      loadTab(container, state);
    } catch (e) { toast(e.message, "error"); sync.disabled = false; }
  });

  const del = modal.body.querySelector("#hd-del");
  if (del) del.addEventListener("click", async () => {
    del.disabled = true;
    try {
      await api.mtHoanDelete(name);
      toast("Đã xóa dòng", "success");
      modal.close();
      loadTab(container, state);
    } catch (e) { toast(e.message, "error"); del.disabled = false; }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// THANH VIỆC CẦN LÀM + PANEL "CẦN BẠN XỬ LÝ"
//
// Badge trên tab ghi 13. Mở tab ra là 194 hóa đơn, và 13 việc thật nằm lẫn
// trong đó không có gì đánh dấu. Con số 13 chỉ tồn tại ở màn "Mọi chuỗi" rồi
// biến mất đúng lúc người dùng vào chuỗi để làm.
//
// Hai chỗ sửa: một THANH dính trên đầu nói còn bao nhiêu việc và bấm được vào
// từng nhóm, và một PANEL bên trái liệt kê đúng những dòng đó kèm nút hành
// động. Số trên thanh, số trên badge và số dòng trong panel lấy từ CÙNG một
// endpoint (`mt_hub.get_chain_worklist`) — ba con số tự cộng lấy ở ba nơi thì
// sớm muộn cũng lệch, và lệch một lần là hết tin cả ba.
// ═══════════════════════════════════════════════════════════════════════════

const WL_TONE = { amber: "ktmt-chip--amber", rose: "ktmt-chip--rose", indigo: "ktmt-chip--indigo" };
const WL_GROUP_TONE = {
  amber: "ktmt-queue-group--amber", rose: "ktmt-queue-group--rose",
  indigo: "ktmt-queue-group--indigo",
};

// Nạp MỘT LẦN cho mỗi (chuỗi, khoảng ngày). Panel và thanh dùng chung kết quả:
// gọi hai lần là hai ảnh chụp ở hai thời điểm, và chúng có quyền khác nhau.
async function ensureWorklist(state) {
  const key = `${state.chain}|${state.from}|${state.to}`;
  if (state.wlKey === key && state.wl) return state.wl;
  // ⚠ Phải nhớ cả CHUYẾN ĐANG BAY, không chỉ kết quả. `paint` gọi hàm này cho
  // thanh trên đầu rồi gọi `loadTab` ngay, mà `loadTab` cũng gọi nó cho panel;
  // cả hai xuất phát trước khi chuyến đầu về, nên bản cũ bắn HAI request và
  // thanh với panel đọc hai ảnh chụp ở hai thời điểm — nối một dòng đúng lúc
  // đó là hai con số lệch nhau ngay trên cùng một màn hình.
  if (state.wlKey === key && state.wlPending) return state.wlPending;
  state.wlKey = key;
  const gen = (state.wlGen = (state.wlGen || 0) + 1);
  state.wlPending = (async () => {
    let wl = null;
    try {
      wl = await api.mtChainWorklist(state.chain, { from_date: state.from, to_date: state.to });
    } catch (_e) {
      // Thanh việc hỏng KHÔNG được chặn cả bàn làm việc: phần còn lại vẫn dùng
      // được, chỉ mất một lối tắt.
      wl = null;
    }
    // Về muộn hơn một lần `invalidateWorklist` thì VỨT: ghi đè bằng số chụp
    // TRƯỚC cú nối là bày lại đúng con số vừa cũ đi.
    if (state.wlGen === gen) {
      state.wl = wl;
      state.wlPending = null;
    }
    return wl;
  })();
  return state.wlPending;
}

function worklistBar(state, wl) {
  if (!wl) return "";
  if (!wl.total) {
    return html`<div class="ktmt-worklist ktmt-worklist--done">
      <div class="ktmt-worklist-icon"><i class="fas fa-check"></i></div>
      <div>
        <div class="ktmt-worklist-title">Không còn việc nào ở bước đối soát</div>
        <div class="ktmt-worklist-hint">trong khoảng đang xem — đổi khoảng ngày để soát lại kỳ khác</div>
      </div>
    </div>`;
  }
  return html`<div class="ktmt-worklist">
    <div class="ktmt-worklist-icon"><i class="fas fa-triangle-exclamation"></i></div>
    <div>
      <div class="ktmt-worklist-title">${wl.total} việc ở bước Đối soát thanh toán</div>
      <div class="ktmt-worklist-hint">bấm một mục để nhảy thẳng vào danh sách đã lọc</div>
    </div>
    <div style="display:flex;gap:8px;flex-grow:1;flex-wrap:wrap">
      ${(wl.groups || []).filter((g) => g.count).map((g) => html`<button
        class="ktmt-chip ${WL_TONE[g.tone] || "ktmt-chip--plain"}" data-wl="${g.key}"
        title="Mở bước Đối soát thanh toán và cuộn tới nhóm này">
        <b>${g.count}</b> ${g.label.toLowerCase()}
      </button>`)}
    </div>
    <button class="ktmt-chip ktmt-chip--plain" data-wl="open">Mở hàng đợi →</button>
  </div>`;
}

function bindWorklistBar(container, state) {
  container.querySelectorAll("#mt-worklist button[data-wl]").forEach((b) => {
    b.addEventListener("click", () => {
      state.step = "thanh-toan";
      state.wlFocus = b.dataset.wl === "open" ? "" : b.dataset.wl;
      state.page = 1;
      syncHash(state);
      paint(container, state);
    });
  });
}

// ── Panel "Cần bạn xử lý" ─────────────────────────────────────────────────
function queuePanel(state, wl) {
  if (!wl) {
    return html`<div class="kt-card"><div class="kt-card-body kt-sub">
      Không đọc được hàng đợi việc của chuỗi này. Danh sách hóa đơn bên phải vẫn dùng
      bình thường.</div></div>`;
  }
  const groups = (wl.groups || []).filter((g) => g.count);
  return html`<div class="kt-card">
    <div class="ktmt-queue-head">
      <div style="font-size:13px;font-weight:700;color:#0f172a">Cần bạn xử lý</div>
      <div class="kt-sub" style="margin-top:2px">${wl.total
        ? `${wl.total} việc · làm hết là chuỗi này “xong”`
        : "không còn việc nào trong khoảng đang xem"}</div>
    </div>
    ${!groups.length
      ? html`<div class="kt-empty" style="padding:28px 16px">
          <i class="fas fa-circle-check"></i><p>Hết việc ở bước này.</p></div>`
      : groups.map((g) => html`
          <div class="ktmt-queue-group ${WL_GROUP_TONE[g.tone] || ""}"
               id="wl-${g.key}">${g.label} · ${g.count}</div>
          ${g.rows.map((r) => queueItem(g, r))}
          ${g.more
            ? html`<div class="ktmt-queue-more">+ ${g.more} dòng nữa — mở bảng kê để xem hết</div>`
            : ""}
        `)}
  </div>`;
}

function queueItem(g, r) {
  if (g.key === "bang_ke_chua_doi_chieu") {
    return html`<div class="ktmt-queue-item">
      <div class="ktmt-queue-main">
        <div class="ktmt-queue-line1">${r.advice_no}${r.payment_date ? ` · ${formatDate(r.payment_date)}` : ""}</div>
        <div class="ktmt-queue-line2">${r.n_lines} dòng · ${formatVNDShort(r.amount)}${
          r.n_unmatched ? ` · ${r.n_unmatched} chưa nối` : " · đã nối hết"}</div>
      </div>
      <button class="kt-btn kt-btn--sm" data-recon="${r.advice}">Đối chiếu</button>
    </div>`;
  }
  if (g.key === "dong_tien_chua_noi") {
    return html`<div class="ktmt-queue-item">
      <div class="ktmt-queue-main">
        <div class="ktmt-queue-line1">${formatVND(r.amount)}${r.payment_date ? ` · ${formatDate(r.payment_date)}` : ""}</div>
        <div class="ktmt-queue-line2">${r.store_name || r.description || "—"}${
          r.advice_no ? ` · ${r.advice_no}` : ""}</div>
      </div>
      <button class="kt-btn kt-btn--outline kt-btn--sm" data-recon="${r.advice}">Nối</button>
    </div>`;
  }
  return html`<div class="ktmt-queue-item">
    <div class="ktmt-queue-main">
      <div class="ktmt-queue-line1">${r.sales_invoice || r.inv_no || formatVND(r.amount)}</div>
      <div class="ktmt-queue-line2">${r.confidence || "—"}${
        r.advice_no ? ` · ${r.advice_no}` : ""} · ${formatVND(r.amount)}</div>
    </div>
    <button class="kt-btn kt-btn--outline kt-btn--sm" data-recon="${r.advice}">Xem</button>
  </div>`;
}

function bindQueuePanel(container, state) {
  container.querySelectorAll("button[data-recon]").forEach((b) => {
    b.addEventListener("click", () => openReconcile(container, state, b.dataset.recon));
  });
  if (state.wlFocus) {
    const el = container.querySelector("#wl-" + state.wlFocus);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    state.wlFocus = "";
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MÀN ĐỐI SOÁT MỘT BẢNG KÊ — ba vế trên cùng một hàng
//
// ⚠ MỖI BẢN GHI LÀ MỘT HÀNG GRID GỒM ĐÚNG BA Ô CON, không phải ba cột độc lập
// đặt cạnh nhau. Ba cột rời thì một ô phải cao gấp ba ô trái là ba vế lệch
// hàng ngay, và người đọc ghép dòng bảng kê của bản ghi này với hóa đơn của
// bản ghi khác — sai tiền vì một lỗi dàn trang. Grid cấp cha (`.ktmt-rec`)
// giữ ba ô của cùng một bản ghi luôn nằm cùng hàng dù ô nào cao bao nhiêu.
// ═══════════════════════════════════════════════════════════════════════════

const REC_FILTERS = [
  { key: "chua_noi", label: "Chưa nối" },
  { key: "lech_tien", label: "Lệch tiền" },
  { key: "da_khop", label: "Đã khớp" },
];

async function openReconcile(container, state, advice) {
  // `dirty` để KHÔNG nạp lại khi người ta chỉ mở ra xem rồi đóng: nạp lại vô cớ
  // là cuộn trang về đầu và mất chỗ đang đọc.
  const st = { advice, filter: "", page: 1, dirty: false };
  const modal = openModal({
    title: "Đối soát bảng kê",
    icon: "fa-scale-balanced",
    maxWidth: 1080,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
    // Nối/gỡ/chốt trong modal đổi cả hàng đợi lẫn bảng phía sau. Không nạp lại
    // thì đóng modal ra là màn hình vẫn ghi "12 dòng chưa nối" cho một bảng kê
    // vừa nối xong — số cũ trông y hệt số mới, nên không ai nghi ngờ.
    onClose: () => {
      if (!st.dirty) return;
      invalidateWorklist(state);
      loadTab(container, state);
    },
  });
  await renderReconcile(container, state, modal, st);
}

async function renderReconcile(container, state, modal, st) {
  let d;
  try {
    d = await api.mtRecon(st.advice, { filter: st.filter || undefined, page: st.page, page_size: 25 });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }

  const pct = d.lines ? Math.round((d.matched / d.lines) * 100) : 0;
  setHTML(modal.body, html`
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:12px">
      <div style="flex-grow:1;min-width:220px">
        <div style="font-size:15px;font-weight:800;color:#0f172a">${d.advice_no}</div>
        <div class="kt-sub">${d.chain || "—"}${d.payment_date ? ` · ngày trả ${formatDate(d.payment_date)}` : ""}
          · ${d.lines} dòng · ${formatVND(d.total_payment)}${d.file_name ? ` · ${d.file_name}` : ""}</div>
      </div>
      <div style="text-align:right">
        <div class="ktmt-kicker">Tiến độ khớp</div>
        <div style="font-size:18px;font-weight:800;color:var(--kt-success)">${d.matched} / ${d.lines}</div>
      </div>
      <div style="width:200px">
        <div class="ktmt-bar">
          <div class="ktmt-bar-done" style="width:${pct}%"></div>
          <div class="ktmt-bar-left"></div>
        </div>
        <div class="kt-sub" style="margin-top:6px">${d.counts.chua_noi
          ? `còn ${d.counts.chua_noi} dòng chưa nối được hóa đơn`
          : "mọi dòng đã nối được hóa đơn"}</div>
      </div>
    </div>

    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
      ${REC_FILTERS.map((f) => html`<button class="ktmt-chip ${
        st.filter === f.key ? "is-on ktmt-chip--indigo" : "ktmt-chip--plain"
      }" data-recf="${f.key}">${f.label} · <b>${d.counts[f.key] || 0}</b></button>`)}
      ${st.filter ? html`<button class="ktmt-chip ktmt-chip--plain" data-recf="">Xem hết</button>` : ""}
      ${d.can_manage && d.auto_ready
        ? html`<button class="kt-btn kt-btn--success kt-btn--sm" id="rec-bulk" style="margin-left:auto">
            <i class="fas fa-wand-magic-sparkles"></i> Nhận hết ${d.auto_ready} gợi ý khớp 100%
          </button>`
        : ""}
    </div>

    ${d.pool_truncated
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub"><b>Rổ hóa đơn ứng viên đã chạm trần
          ${d.pool_cap} tờ và bị cắt bớt.</b> Dòng nào ở dưới ghi "không có hóa đơn nào
          khớp" thì có thể là do CẮT chứ không phải do dữ liệu — thu hẹp khoảng ngày của
          bảng kê, hoặc chọn hóa đơn bằng tay.</div></div>`
      : ""}

    ${!d.rows.length
      ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i>
          <p>Không có dòng nào trong bộ lọc này.</p></div>`
      : html`<div class="kt-card" style="padding:0"><div class="ktmt-rec">
          <div class="ktmt-rec-head ktmt-rec-head--l"><span class="ktmt-kicker"
            style="color:#92400e">Dòng trên bảng kê của ${d.chain || "chuỗi"}</span></div>
          <div class="ktmt-rec-head ktmt-rec-head--m"><span class="ktmt-kicker">Khớp</span></div>
          <div class="ktmt-rec-head ktmt-rec-head--r"><span class="ktmt-kicker"
            style="color:#3730a3">Hóa đơn trên ERPNext</span></div>
          ${d.rows.map((r) => reconRow(d, r))}
        </div></div>
        ${pager(d, "dòng")}`}

    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:14px;
                padding-top:12px;border-top:1px solid var(--kt-border)">
      <div class="kt-sub" style="flex-grow:1;min-width:240px">Chốt xong sẽ sinh
        <b>bút toán NHÁP</b> — hệ thống không tự ghi sổ, vẫn chờ người duyệt ở bước Bút toán.</div>
      ${d.can_manage
        ? html`<button class="kt-btn" id="rec-commit">
            <i class="fas fa-stamp"></i> Chốt bảng kê &amp; sinh bút toán nháp</button>`
        : html`<span class="kt-sub">Chỉ kế toán trưởng mới chốt được bảng kê.</span>`}
    </div>
  `);

  bindReconcile(container, state, modal, st, d);
}

function reconRow(d, r) {
  const hit = r.state === "chua_noi" && r.auto;
  const cls = hit ? " ktmt-rec-hit" : "";
  return html`
    <div class="ktmt-rec-l${cls}">
      <div class="ktmt-rec-amount">${formatVND(r.amount)}</div>
      <div class="ktmt-rec-sub">${r.payment_date ? formatDate(r.payment_date) : "—"}
        ${r.store_name ? ` · ${r.store_name}` : ""}${r.doc_no ? ` · ${r.doc_no}` : ""}</div>
      ${recStmtInv(r)}
    </div>
    <div class="ktmt-rec-m${cls}">
      ${reconGap(r)}
      ${reconAction(d, r)}
    </div>
    <div class="ktmt-rec-r${cls}">${reconRight(d, r)}</div>`;
}

// SỐ HÓA ĐƠN ĐIỆN TỬ CHUỖI GHI TRÊN BẢNG KÊ — câu hỏi đầu tiên của người đối
// soát ("khoản này trả cho tờ nào"), và trước đây phải mở từng dòng ra mới thấy.
// Chuỗi không ghi số thì KHÔNG vẽ dòng trống: một nhãn "HĐĐT —" trông như một
// thiếu sót cần đi tìm, trong khi có chuỗi vốn không ghi số bao giờ.
function recStmtInv(r) {
  if (!r.inv_no && !r.inv_series) return "";
  return html`<div class="ktmt-rec-sub"><i class="fas fa-file-invoice"></i>
    HĐĐT ${r.inv_series || "—"}${r.inv_no ? html` · <b>${r.inv_no}</b>` : ""}
    ${r.inv_date ? ` · ${formatDate(r.inv_date)}` : ""}</div>`;
}

// Cờ khớp số HĐĐT. `null` = một phía chưa có số -> KHÔNG vẽ gì: đó là chưa
// biết, không phải lệch, và một dấu ✗ ở đó là bắt kế toán đi kiểm một tờ không
// sai. Backend so bằng `norm_inv_no`, cùng hàm máy dùng để khớp tự động, nên
// `0000006990` và `00006990` là MỘT.
function recInvFlag(r) {
  if (r.inv_match === true) {
    return html`<span class="kt-badge kt-badge--green" title="Số HĐĐT trên bảng kê trùng số trên hóa đơn ERPNext">số HĐĐT khớp</span>`;
  }
  if (r.inv_match === false) {
    return html`<span class="kt-badge kt-badge--yellow"
      title="Bảng kê ghi ${r.inv_no} — hóa đơn ERPNext ghi ${(r.invoice && r.invoice.inv_no) || "(trống)"}">số HĐĐT khác</span>`;
  }
  return "";
}

function reconGap(r) {
  if (r.state === "chua_noi") {
    return r.auto
      ? html`<span style="font-size:11px;font-weight:700;color:var(--kt-success)">lệch 0 ₫</span>`
      : html`<span style="font-size:11px;font-weight:700;color:#b45309">chưa có</span>`;
  }
  if (!r.gap) return html`<span style="font-size:11px;font-weight:700;color:var(--kt-success)">lệch 0 ₫</span>`;
  return html`<span style="font-size:11px;font-weight:700;color:var(--kt-danger)">${
    r.gap > 0 ? "+" : "−"}${formatVND(Math.abs(r.gap))}</span>`;
}

function reconAction(d, r) {
  if (!d.can_manage) return "";
  if (r.state === "chua_noi") {
    return r.auto
      ? html`<button class="kt-btn kt-btn--success kt-btn--sm" data-reclink="${r.line}"
          data-si="${r.auto.sales_invoice}">Nối ✓</button>`
      : html`<button class="kt-btn kt-btn--outline kt-btn--sm" data-recfind="${r.line}">Tìm HĐ</button>`;
  }
  if (r.state === "lech_tien") {
    return html`<button class="kt-btn kt-btn--danger kt-btn--sm" data-recvar="${r.line}">Giải trình</button>`;
  }
  return html`<button class="kt-btn kt-btn--outline kt-btn--sm" data-recunlink="${r.line}"
    title="Gỡ liên kết dòng này">Gỡ</button>`;
}

// HÓA ĐƠN ĐI + HÓA ĐƠN TRẢ VỀ.
//
// Quy trình thật của kênh MT: một lần bán, sau khi điều chỉnh, thành HAI chứng
// từ ERPNext — hóa đơn gốc và phiếu trả (`return_against`). Chuỗi trả đúng phần
// RÒNG, nên con số đậm ở trên là phần còn phải thu, KHÔNG phải mặt hóa đơn.
//
// Khối này bày ra phép trừ, và gọi ĐÍCH DANH từng phiếu trả: "trừ 20.000.000"
// thì không tra được, "trừ ACC-SRET-9 20.000.000" thì mở ra xem được ngay.
function recReturns(si) {
  if (!si || !si.returned) return "";
  return html`<div class="ktmt-rec-sub" style="margin-top:4px;padding-left:8px;border-left:2px solid var(--kt-warning)">
    Hóa đơn ghi <b>${formatVND(si.gross)}</b>, đã trả về
    <b>${formatVND(si.returned)}</b>${(si.returns || []).length ? html` — ${
      (si.returns || []).map((x, i) => html`${i ? ", " : ""}<a target="_blank"
        href="/desk/sales-invoice/${q(x.name)}">${x.name}</a> ${formatVNDShort(x.amount)}`)}` : ""}.
    Còn phải thu <b>${formatVND(si.amount)}</b> — đó là số chuỗi phải trả, và là
    số mức lệch bên trái so vào.
  </div>`;
}

function reconRight(d, r) {
  if (r.state === "chua_noi") {
    if (!r.candidates.length) {
      return html`<div style="font-size:12px;font-weight:700;color:#b45309">Không có hóa đơn nào khớp số tiền</div>
        <div class="ktmt-rec-sub">Chuỗi chưa gán khách, hoặc hóa đơn chưa ghi sổ. Bấm <b>Tìm HĐ</b> để chọn tay.</div>`;
    }
    return html`
      ${r.auto ? "" : html`<div style="font-size:12px;font-weight:700;color:#b45309">Chưa đủ chắc để nhận tự động</div>`}
      <div class="ktmt-rec-sub">${r.candidates.map((c) => html`
        <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-top:4px">
          <a target="_blank" href="/desk/sales-invoice/${q(c.sales_invoice)}"><b>${c.sales_invoice}</b></a>
          <span>${formatVND(c.amount)}</span>
          ${c.returned ? html`<span class="kt-sub"
            title="Hóa đơn ghi ${formatVND(c.gross)}, đã trừ ${formatVND(c.returned)} hàng trả về"
            >(${formatVNDShort(c.gross)} − ${formatVNDShort(c.returned)} trả về)</span>` : ""}
          <span class="kt-sub">${c.posting_date ? formatDate(c.posting_date) : ""}${
            c.ship_to ? ` · ${c.ship_to}` : ""}</span>
          <span class="kt-badge kt-badge--${c.level === "chac_chan" ? "green" : (c.level === "khac_diem" ? "yellow" : "gray")}">${c.level_label}</span>
          ${d.can_manage ? html`<button class="kt-btn kt-btn--outline kt-btn--sm"
            data-reclink="${r.line}" data-si="${c.sales_invoice}">Chọn</button>` : ""}
        </div>`)}</div>`;
  }
  const si = r.invoice;
  return html`
    <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
      <a target="_blank" href="/desk/sales-invoice/${q(r.sales_invoice)}"><b>${r.sales_invoice}</b></a>
      ${si ? html`<b>${formatVND(si.amount)}</b>` : html`<span class="kt-sub">không đọc được hóa đơn</span>`}
      ${recInvFlag(r)}
    </div>
    ${si ? html`<div class="ktmt-rec-sub">${si.posting_date ? formatDate(si.posting_date) : ""}
      ${si.inv_series ? ` · ${si.inv_series}` : ""}${si.inv_no ? ` · ${si.inv_no}` : ""}
      ${si.ship_to ? ` · ${si.ship_to}` : ""}</div>` : ""}
    ${recReturns(si)}
    ${r.one_of_many
      ? html`<div class="ktmt-rec-sub">Hóa đơn này được trả làm nhiều lần —
          tổng đã trả <b>${formatVND(r.paid_total)}</b>. Mức lệch bên trái tính trên
          CẢ hóa đơn, không phải trên riêng dòng này.</div>`
      : ""}
    ${r.variance_kind
      ? html`<div class="ktmt-rec-sub" style="color:#b45309">
          Đã ghi nhận <b>${r.variance_kind}</b> ${formatVND(Math.abs(r.variance_amount))}${
            r.variance_note ? ` — ${r.variance_note}` : ""}.
          <b>Khoản này VẪN còn trên công nợ</b> cho tới khi có bút toán.</div>`
      : (r.state === "lech_tien"
        ? html`<div class="ktmt-rec-sub" style="color:var(--kt-danger)">Chuỗi trả ${
            (r.gap || 0) < 0 ? "thiếu" : "vượt"} ${formatVND(Math.abs(r.gap || 0))}
            — chọn khoản trừ để ghi nhận</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:7px">
            ${(d.variance_kinds || []).map((k) => html`<button class="ktmt-chip ktmt-chip--plain"
              data-recvar="${r.line}" data-kind="${k}">${k}</button>`)}
          </div>`
        : "")}`;
}

function bindReconcile(container, state, modal, st, d) {
  const reload = () => renderReconcile(container, state, modal, st);

  modal.body.querySelectorAll("button[data-recf]").forEach((b) => {
    b.addEventListener("click", () => {
      st.filter = b.dataset.recf;
      st.page = 1;
      reload();
    });
  });
  modal.body.querySelectorAll(".kt-pager button[data-page]").forEach((b) => {
    b.addEventListener("click", () => {
      const p = parseInt(b.dataset.page, 10);
      if (!p || p === st.page) return;
      st.page = p;
      reload();
    });
  });

  modal.body.querySelectorAll("button[data-reclink]").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api.mtReconLink(b.dataset.reclink, b.dataset.si);
        toast("Đã nối " + b.dataset.si, "success");
        st.dirty = true;
        invalidateWorklist(state);
        reload();
      } catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
  });
  modal.body.querySelectorAll("button[data-recunlink]").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api.mtReconLink(b.dataset.recunlink, "");
        toast("Đã gỡ liên kết", "success");
        st.dirty = true;
        invalidateWorklist(state);
        reload();
      } catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
  });
  modal.body.querySelectorAll("button[data-recvar]").forEach((b) => {
    b.addEventListener("click", async () => {
      const kind = b.dataset.kind;
      if (!kind) {
        // Nút "Giải trình" ở ô giữa chỉ cuộn tới hàng chip loại khoản trừ —
        // không tự chọn hộ: chọn loại khoản trừ là một kết luận kế toán.
        const chip = modal.body.querySelector(`button[data-recvar="${b.dataset.recvar}"][data-kind]`);
        if (chip) chip.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      b.disabled = true;
      try {
        const out = await api.mtReconExplain(b.dataset.recvar, kind);
        toast(out.message || "Đã ghi nhận", "success");
        st.dirty = true;
        reload();
      } catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
  });
  modal.body.querySelectorAll("button[data-recfind]").forEach((b) => {
    b.addEventListener("click", () => {
      // Chọn tay đi qua ĐÚNG modal cũ (`openRelinkModal`), không dựng một ô
      // tìm kiếm thứ hai: modal đó đã mang sẵn cảnh báo "hóa đơn này đã có
      // dòng khác trỏ tới" và luật chỉ-dòng-Thanh-toán-mới-nối.
      openRelinkModal(container, state, b.dataset.recfind, "", () => {
        st.dirty = true;
        reload();
      });
    });
  });

  const bulk = modal.body.querySelector("#rec-bulk");
  if (bulk) bulk.addEventListener("click", async () => {
    bulk.disabled = true;
    try {
      const out = await api.mtReconBulk(st.advice);
      const soft = (out.failed && out.failed.length) || (out.clashed && out.clashed.length);
      toast(out.message, soft ? "warning" : "success");
      st.dirty = true;
      invalidateWorklist(state);
      reload();
    } catch (e) { toast(e.message, "error"); bulk.disabled = false; }
  });

  const commit = modal.body.querySelector("#rec-commit");
  if (commit) commit.addEventListener("click", async () => {
    commit.disabled = true;
    try {
      const out = await api.mtReconCommit(st.advice);
      toast(out.message, out.unlinked ? "warning" : "success");
      st.dirty = true;
      invalidateWorklist(state);
      modal.close();
      // Bản xem trước đi qua ĐÚNG modal bút toán cũ — nó là chỗ đã có đủ cảnh
      // báo về tài khoản thiếu, dòng không ghi sổ được và vân tay kế hoạch.
      openJePreviewFor(container, state, st.advice, out);
    } catch (e) { toast(e.message, "error"); commit.disabled = false; }
  });
}

// Sau khi chốt bảng kê thì mở ĐÚNG modal bút toán cũ. Không dựng bản xem trước
// thứ hai ở đây: modal kia mới là chỗ có vân tay kế hoạch, cảnh báo thiếu tài
// khoản, và danh sách dòng không ghi sổ được — ba thứ quyết định bút toán có
// đúng hay không, và không nhìn thấy được từ màn đối soát.
function openJePreviewFor(container, state, advice, _out) {
  // `commit_statement` đã đánh dấu đã đối chiếu VÀ đã báo số dòng còn bỏ lại,
  // nên ở đây chỉ còn việc mở modal bút toán cũ. Báo lần thứ hai là hai toast
  // chồng nhau nói cùng một điều.
  invalidateWorklist(state);
  openJePreview(container, state, advice);
}

// Hàng đợi việc đã CŨ sau mỗi lần nối/gỡ — không xóa thì thanh trên đầu vẫn ghi
// con số của lúc mở màn.
function invalidateWorklist(state) {
  state.wl = null;
  state.wlKey = "";
  state.wlPending = null;
  state.wlGen = (state.wlGen || 0) + 1;   // chuyến đang bay về sẽ bị vứt
}

// ═══════════════════════════════════════════════════════════════════════════
// NỐI NGƯỢC: TỪ HÓA ĐƠN ĐÃ CHỌN TÌM DÒNG BẢNG KÊ
//
// Màn đối soát đi từ BẢNG KÊ. Đây là chiều ngược lại, và nó là chiều kế toán
// hay dùng hơn: nhìn danh sách còn nợ, thấy vài tờ đáng lẽ đã được trả, muốn
// biết tiền của chúng nằm ở dòng nào.
//
// ⚠ ĐÂY KHÔNG PHẢI "ĐÁNH DẤU ĐÃ THU". Nó chỉ nối hóa đơn với một dòng tiền CÓ
// THẬT trên một bảng kê ĐÃ NẠP; hóa đơn không có dòng nào khớp thì vẫn còn nợ.
// Câu đó in ngay trên đầu modal chứ không nằm trong tooltip.
// ═══════════════════════════════════════════════════════════════════════════

async function openReverseMatch(container, state, invoices) {
  const modal = openModal({
    title: `Tìm dòng bảng kê cho ${invoices.length} hóa đơn`,
    icon: "fa-link",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderReverseMatch(container, state, modal, invoices);
}

async function renderReverseMatch(container, state, modal, invoices) {
  let d;
  try {
    d = await api.mtReconForInvoices(invoices);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = d.rows || [];
  const hit = rows.filter((r) => r.candidates.length);

  setHTML(modal.body, html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
      <div class="kt-card-body kt-sub">${d.note}</div></div>

    ${!hit.length
      ? html`<div class="kt-empty"><i class="fas fa-magnifying-glass"></i>
          <p>Không hóa đơn nào trong ${rows.length} tờ đã chọn tìm được dòng tiền chưa nối
            khớp số tiền. Chúng vẫn còn nợ.</p></div>`
      : html`<div class="kt-table-wrap"><table class="kt-table">
          <thead><tr>
            <th>Hóa đơn</th><th class="num" title="Đã trừ hàng trả về — đúng số chuỗi phải trả">Còn phải thu</th>
            <th class="kt-col-wide">Dòng bảng kê khớp</th><th class="kt-col-role"></th>
          </tr></thead>
          <tbody>${hit.map((r) => html`<tr>
            <td><a target="_blank" href="/desk/sales-invoice/${q(r.sales_invoice)}">${r.sales_invoice}</a>
              <div class="kt-sub">${r.posting_date ? formatDate(r.posting_date) : ""}</div></td>
            <td class="num">${formatVND(r.amount)}
              ${r.returned ? html`<div class="kt-sub"
                title="Hóa đơn ghi ${formatVND(r.gross)}, đã trừ ${formatVND(r.returned)} hàng trả về"
                >${formatVNDShort(r.gross)} − ${formatVNDShort(r.returned)} trả về</div>` : ""}</td>
            <td class="kt-col-wide">${r.candidates.map((c) => html`
              <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px">
                <b>${c.advice_no}</b>
                <span class="kt-sub">${c.payment_date ? formatDate(c.payment_date) : ""}${
                  c.store_name ? ` · ${c.store_name}` : ""}</span>
                <span class="kt-badge kt-badge--${c.level === "chac_chan" ? "green" : "yellow"}">${c.level_label}</span>
                ${d.can_manage
                  ? html`<button class="kt-btn kt-btn--outline kt-btn--sm"
                      data-rmlink="${c.line}" data-si="${r.sales_invoice}">Nối</button>`
                  : ""}
              </div>`)}</td>
            <td class="kt-col-role">${r.auto && d.can_manage
              ? html`<button class="kt-btn kt-btn--success kt-btn--sm"
                  data-rmlink="${r.auto.line}" data-si="${r.sales_invoice}">Nối ✓</button>`
              : ""}</td>
          </tr>`)}</tbody>
        </table></div>
        ${rows.length - hit.length
          ? html`<div class="kt-sub" style="margin-top:8px">${rows.length - hit.length} hóa đơn
              còn lại không có dòng tiền nào khớp — chúng vẫn còn nợ.</div>`
          : ""}`}
  `);

  modal.body.querySelectorAll("button[data-rmlink]").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api.mtReconLink(b.dataset.rmlink, b.dataset.si);
        toast("Đã nối " + b.dataset.si, "success");
        invalidateWorklist(state);
        await renderReverseMatch(container, state, modal, invoices);
        loadTab(container, state);
      } catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
  });
}
