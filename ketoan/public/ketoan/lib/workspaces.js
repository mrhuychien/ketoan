// workspaces.js — cấu hình nghiệp vụ theo vai trò kế toán.
// `home`: trang LÀM VIỆC chính của vai trò — nav & trang chủ trỏ thẳng vào đây.
// guide + sections (Thực hiện / Báo cáo / Công cụ) hiển thị ở trang tham khảo
// /vt/:key ("Hướng dẫn & lối tắt") — mỗi đích chỉ xuất hiện 1 lần, link vào tab
// thì mang ?tab= để rơi đúng màn hình.
// item.type: "desk" (href ra /app), "route" (route nội bộ #/...).

const CTX = window.KETOAN_CONTEXT || {};

// URL Sổ cái (General Ledger) với filter chuẩn: company + 30 ngày gần nhất
// + Categorize by Voucher (Consolidated) + dimensions + default book entries.
function glUrl() {
  const fmt = (d) => d.toISOString().slice(0, 10);
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 30);
  const p = new URLSearchParams({
    company: CTX.company || "",
    from_date: fmt(from),
    to_date: fmt(to),
    categorize_by: "Categorize by Voucher (Consolidated)",
    include_dimensions: "1",
    include_default_book_entries: "1",
  });
  return "/app/query-report/General%20Ledger?" + p.toString();
}

export const WORKSPACES = [
  {
    key: "npp",
    label: "Kế toán NPP",
    icon: "fa-handshake",
    home: "/doi-chieu-npp",
    desc: "Kênh nhà phân phối: đối chiếu công nợ, chính sách thu, chiết khấu",
    guide: [
      "Hàng đi: lập Sales Invoice cho NPP; điền số hóa đơn điện tử (vn_einvoice_number). Chưa điền = chưa xuất HĐ — theo dõi ở tab 'Chưa xuất HĐĐT'.",
      "Thu tiền: ghi nhận bằng Payment Entry; theo dõi khoản đến hạn/quá hạn ở tab 'Đến hạn' (ngày 5 & 20; mùa Tết cho nợ 50% HĐ từ 1/11) và nhắc nợ Zalo.",
      "Trả hàng: tab 'Trả hàng' bấm '+ Trả hàng' tạo hóa đơn trả về NHÁP → chờ NPP xuất hóa đơn → đính kèm vào chứng từ → KTT duyệt để trừ công nợ.",
      "Bút toán JE (chiết khấu, thưởng, hỗ trợ...): chiết khấu tạo từ tab 'Chiết khấu', JE khác tạo trong Desk → theo dõi ở tab 'Bút toán JE' → đính kèm hóa đơn NPP → KTT duyệt.",
      "Hồ sơ NPP: hợp đồng, phụ lục thương mại, ĐKKD upload trong 360° khách (khối Hồ sơ khách hàng).",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Hóa đơn bán hàng (Sales Invoice)", icon: "fa-file-invoice", type: "desk", href: "/app/sales-invoice" },
        { label: "Sổ cái (General Ledger, 30 ngày)", icon: "fa-book", type: "desk", href: glUrl() },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Công nợ kênh NPP + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no/npp" },
        { label: "Accounts Receivable", icon: "fa-table", type: "desk", href: "/app/accounts-receivable" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Chiết khấu theo doanh số tháng", icon: "fa-percent", type: "route", route: "/doi-chieu-npp?tab=discount" },
        { label: "Nhắc nợ Zalo / đến hạn", icon: "fa-comment-dots", type: "route", route: "/doi-chieu-npp?tab=due" },
        { label: "Xuất biên bản đối chiếu (PDF)", icon: "fa-file-pdf", type: "route", route: "/doi-chieu-npp?tab=debt" },
        { label: "Tìm khách → 360°", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
      ]},
    ],
  },
  {
    key: "mt",
    label: "Kế toán MT",
    icon: "fa-store",
    home: "/cong-no/mt",
    desc: "Kênh MT (siêu thị/hiện đại): công nợ, đối chiếu, thu tiền",
    guide: [
      "Hàng đi: lập Sales Invoice cho khách MT; điền số hóa đơn điện tử khi phát hành.",
      "Thu tiền: Payment Entry gắn khách; theo dõi công nợ + tuổi nợ kênh MT.",
      "Đối chiếu: tìm khách trong Tiện ích → vào 360° khách → Xuất đối chiếu (PDF) gửi siêu thị định kỳ.",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Lập hóa đơn bán", icon: "fa-file-invoice", type: "desk", href: "/app/sales-invoice/new" },
        { label: "Phiếu thu tiền", icon: "fa-money-bill-wave", type: "desk", href: "/app/payment-entry/new" },
        { label: "Khách hàng MT", icon: "fa-users", type: "desk", href: "/app/customer?customer_group=MT" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Công nợ kênh MT + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no/mt" },
        { label: "Accounts Receivable", icon: "fa-table", type: "desk", href: "/app/accounts-receivable" },
        { label: "Sales Register", icon: "fa-table", type: "desk", href: "/app/query-report/Sales Register" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Tìm khách → 360° · xuất đối chiếu PDF", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
      ]},
    ],
  },
  {
    key: "travel",
    label: "Kế toán Du lịch, Khác",
    icon: "fa-umbrella-beach",
    home: "/cong-no/khac",
    desc: "Kênh du lịch & khách lẻ/khác: công nợ, thu tiền",
    guide: [
      "Hàng đi: lập Sales Invoice; điền số hóa đơn điện tử khi phát hành.",
      "Thu tiền: Payment Entry gắn khách; theo dõi công nợ + tuổi nợ kênh.",
      "Đối chiếu: tìm khách trong Tiện ích → vào 360° khách → Xuất đối chiếu (PDF) khi khách yêu cầu.",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Lập hóa đơn bán", icon: "fa-file-invoice", type: "desk", href: "/app/sales-invoice/new" },
        { label: "Phiếu thu tiền", icon: "fa-money-bill-wave", type: "desk", href: "/app/payment-entry/new" },
        { label: "Khách hàng", icon: "fa-users", type: "desk", href: "/app/customer" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Công nợ kênh Du lịch, Khác + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no/khac" },
        { label: "Accounts Receivable", icon: "fa-table", type: "desk", href: "/app/accounts-receivable" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Tìm khách → 360° · xuất đối chiếu PDF", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
      ]},
    ],
  },
  {
    key: "purchase",
    label: "Kế toán mua hàng",
    icon: "fa-truck-field",
    home: "/cong-no-ncc",
    desc: "Công nợ phải trả, hóa đơn NCC, thanh toán mua hàng",
    guide: [
      "Nhận hóa đơn NCC → tạo Purchase Invoice, LUÔN điền số hóa đơn NCC (bill_no) để hệ thống dò trùng.",
      "Khớp 3 chiều PO – nhập kho – hóa đơn: kiểm tra hóa đơn thiếu liên kết Purchase Receipt ở tab 'Kiểm soát'.",
      "Lịch thanh toán: tab 'Đến hạn' xem khoản quá hạn/sắp đến hạn → bấm lập phiếu chi ngay trên dòng.",
      "Theo dõi cảnh báo trùng hóa đơn NCC (cùng NCC + cùng số HĐ) — lỗi nhập hoặc gian lận.",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Hóa đơn mua (Purchase Invoice)", icon: "fa-file-invoice", type: "desk", href: "/app/purchase-invoice/new" },
        { label: "Phiếu chi thanh toán", icon: "fa-money-bill-transfer", type: "desk", href: "/app/payment-entry/new" },
        { label: "Nhà cung cấp", icon: "fa-industry", type: "desk", href: "/app/supplier" },
        { label: "Đơn mua hàng (PO)", icon: "fa-file-lines", type: "desk", href: "/app/purchase-order" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Công nợ phải trả + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no-ncc" },
        { label: "Accounts Payable (Desk)", icon: "fa-table", type: "desk", href: "/app/accounts-payable" },
        { label: "Purchase Register", icon: "fa-table", type: "desk", href: "/app/query-report/Purchase Register" },
        { label: "Sổ chi tiết NCC", icon: "fa-book", type: "desk", href: "/app/general-ledger?party_type=Supplier" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Lịch thanh toán đến hạn", icon: "fa-calendar-days", type: "route", route: "/cong-no-ncc?tab=due" },
        { label: "Kiểm soát: trùng HĐ NCC + khớp 3 chiều", icon: "fa-shield-halved", type: "route", route: "/cong-no-ncc?tab=control" },
        { label: "Hóa đơn NCC chờ thanh toán (Desk)", icon: "fa-clock", type: "desk", href: "/app/purchase-invoice?status=Unpaid" },
      ]},
    ],
  },
  {
    key: "payroll",
    label: "Kế toán tiền lương",
    icon: "fa-money-check-dollar",
    home: "/luong",
    desc: "Tính lương, duyệt phiếu lương, xuất bảng lương",
    guide: [
      "Trong kỳ: nhập phiếu công nhật (SalaryDay) và công khoán (SalaryProduct) dạng nháp.",
      "Cuối kỳ: mở 'Tính lương tháng' → chọn kỳ → Quét phiếu → duyệt (submit) phiếu nháp.",
      "Xuất 7 file Excel (tổng hợp, chuyển khoản NH, tiền mặt, bù trừ, bảng tổng hợp) và in bảng lương / phát lương PDF.",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Phiếu công nhật (SalaryDay)", icon: "fa-calendar-day", type: "desk", href: "/app/salaryday/new" },
        { label: "Phiếu công khoán (SalaryProduct)", icon: "fa-boxes-stacked", type: "desk", href: "/app/salaryproduct/new" },
        { label: "Payroll Entry", icon: "fa-file-invoice-dollar", type: "desk", href: "/app/payroll-entry" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Phiếu công nhật", icon: "fa-table", type: "desk", href: "/app/salaryday" },
        { label: "Phiếu công khoán", icon: "fa-table", type: "desk", href: "/app/salaryproduct" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Tính lương tháng (quét · duyệt · xuất Excel · in PDF)", icon: "fa-calculator", type: "route", route: "/luong" },
      ]},
    ],
  },
  {
    key: "gl",
    label: "Kế toán hạch toán",
    icon: "fa-book",
    home: "/quy",
    desc: "Quỹ tiền mặt & ngân hàng, bút toán, sổ cái",
    guide: [
      "Nhập sổ quỹ: phiếu thu/chi tiền mặt tạo NHÁP từ portal (kèm QR VietQR nếu chuyển khoản).",
      "Nhập sao kê ngân hàng (.xlsx): upload → hệ thống lọc trùng + gợi ý TK đối ứng theo quy tắc map → tạo bút toán Bank Entry nháp.",
      "Duyệt: kiểm tra và submit các Journal Entry nháp (kể cả JE nháp do kênh bán hàng tạo).",
      "Theo dõi sổ quỹ & dòng tiền; đối chiếu số dư với sao kê cuối kỳ.",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Bút toán (Journal Entry)", icon: "fa-pen-to-square", type: "desk", href: "/app/journal-entry/new" },
        { label: "Sổ quỹ & nhập phiếu thu chi", icon: "fa-wallet", type: "route", route: "/quy" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Sổ cái (General Ledger, 30 ngày)", icon: "fa-book", type: "desk", href: glUrl() },
        { label: "Bảng cân đối (Trial Balance)", icon: "fa-scale-balanced", type: "desk", href: "/app/query-report/Trial Balance" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Nhập sao kê ngân hàng", icon: "fa-file-import", type: "route", route: "/nhap-sao-ke" },
        { label: "Quy tắc map sao kê", icon: "fa-sliders", type: "desk", href: "/app/ketoan-bank-map-rule" },
      ]},
    ],
  },
  {
    key: "chief",
    label: "Kế toán trưởng",
    icon: "fa-user-tie",
    home: "/dashboard",
    desc: "Tổng quan toàn phòng, duyệt hồ sơ, cảnh báo, cấu hình",
    guide: [
      "Mỗi sáng: xem Dashboard tổng hợp + Trung tâm cảnh báo (vượt hạn mức, quá hạn, khoản thu treo, quỹ âm).",
      "Duyệt hồ sơ đối trừ 'Chờ KTT duyệt' (trả hàng/chiết khấu đã đính kèm hóa đơn NPP) — submit để trừ công nợ.",
      "Phân quyền vai trò kế toán cho tài khoản (1 người nhiều vai trò).",
      "Cấu hình ngưỡng: tuổi nợ, chiết khấu, nhóm khách kênh... trong Ketoan Portal Settings.",
      "Bàn làm việc của từng vai trò nằm ngay trên thanh điều hướng — bấm là vào thẳng.",
    ],
    sections: [
      { title: "Thực hiện", icon: "fa-bolt", items: [
        { label: "Duyệt trả hàng NPP (chờ KTT)", icon: "fa-rotate-left", type: "route", route: "/doi-chieu-npp?tab=trahang" },
        { label: "Duyệt bút toán JE (chờ KTT)", icon: "fa-stamp", type: "route", route: "/doi-chieu-npp?tab=butoan" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Dashboard tổng hợp", icon: "fa-gauge-high", type: "route", route: "/dashboard" },
        { label: "Công nợ phải thu toàn bộ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no" },
        { label: "Trung tâm cảnh báo", icon: "fa-triangle-exclamation", type: "route", route: "/canh-bao" },
        { label: "Sổ cái (General Ledger, 30 ngày)", icon: "fa-book", type: "desk", href: glUrl() },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Phân quyền vai trò kế toán", icon: "fa-user-shield", type: "route", route: "/phan-quyen" },
        { label: "Cấu hình portal (Settings)", icon: "fa-gear", type: "desk", href: "/app/ketoan-portal-settings" },
        { label: "Quản lý user (Desk)", icon: "fa-users-gear", type: "desk", href: "/app/user" },
      ]},
    ],
  },
];

export function getWorkspace(key) {
  return WORKSPACES.find((w) => w.key === key) || null;
}

// Danh sách workspace user được thấy (từ KETOAN_CONTEXT.workspaces).
export function myWorkspaces() {
  const allowed = (window.KETOAN_CONTEXT && window.KETOAN_CONTEXT.workspaces) || [];
  return WORKSPACES.filter((w) => allowed.includes(w.key));
}

// Trang làm việc chính của 1 workspace (fallback về trang tham khảo /vt/:key).
export function workHome(w) {
  return w.home || "/vt/" + w.key;
}
