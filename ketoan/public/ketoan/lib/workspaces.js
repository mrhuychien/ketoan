// workspaces.js — cấu hình 5 workspace theo vai trò kế toán.
// Mỗi workspace 3 mục: Tác nghiệp (deep-link Desk) / Báo cáo / Công cụ.
// item.type: "desk" (href ra /app), "route" (route nội bộ #/...).

export const WORKSPACES = [
  {
    key: "npp",
    label: "Kế toán NPP",
    icon: "fa-handshake",
    desc: "Kênh nhà phân phối: đối chiếu công nợ, chính sách thu, chiết khấu",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
        { label: "Lập hóa đơn bán", icon: "fa-file-invoice", type: "desk", href: "/app/sales-invoice/new" },
        { label: "Phiếu thu tiền", icon: "fa-money-bill-wave", type: "desk", href: "/app/payment-entry/new" },
        { label: "Khách hàng NPP", icon: "fa-users", type: "desk", href: "/app/customer?customer_group=NPP" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Đối chiếu công nợ NPP (chính sách thường/Tết)", icon: "fa-handshake", type: "route", route: "/doi-chieu-npp" },
        { label: "Công nợ kênh NPP + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no/npp" },
        { label: "Accounts Receivable", icon: "fa-table", type: "desk", href: "/app/accounts-receivable" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Chiết khấu 2% theo doanh số tháng", icon: "fa-percent", type: "route", route: "/doi-chieu-npp" },
        { label: "Nhắc nợ Zalo / đến hạn", icon: "fa-comment-dots", type: "route", route: "/doi-chieu-npp" },
        { label: "Xuất biên bản đối chiếu (PDF)", icon: "fa-file-pdf", type: "route", route: "/cong-no/npp" },
        { label: "Tìm khách → 360°", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
      ]},
    ],
  },
  {
    key: "mt",
    label: "Kế toán MT",
    icon: "fa-store",
    desc: "Kênh MT (siêu thị/hiện đại): công nợ, đối chiếu, thu tiền",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
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
        { label: "Xuất biên bản đối chiếu (PDF)", icon: "fa-file-pdf", type: "route", route: "/cong-no/mt" },
        { label: "Tìm khách → 360°", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
      ]},
    ],
  },
  {
    key: "travel",
    label: "Kế toán Du lịch, Khác",
    icon: "fa-umbrella-beach",
    desc: "Kênh du lịch & khách lẻ/khác: công nợ, thu tiền",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
        { label: "Lập hóa đơn bán", icon: "fa-file-invoice", type: "desk", href: "/app/sales-invoice/new" },
        { label: "Phiếu thu tiền", icon: "fa-money-bill-wave", type: "desk", href: "/app/payment-entry/new" },
        { label: "Khách hàng", icon: "fa-users", type: "desk", href: "/app/customer" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Công nợ kênh Du lịch, Khác + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no/khac" },
        { label: "Accounts Receivable", icon: "fa-table", type: "desk", href: "/app/accounts-receivable" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Xuất biên bản đối chiếu (PDF)", icon: "fa-file-pdf", type: "route", route: "/cong-no/khac" },
        { label: "Tìm khách → 360°", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
      ]},
    ],
  },
  {
    key: "purchase",
    label: "Kế toán mua hàng",
    icon: "fa-truck-field",
    desc: "Công nợ phải trả, hóa đơn NCC, thanh toán mua hàng",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
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
        { label: "Lịch thanh toán đến hạn", icon: "fa-calendar-days", type: "route", route: "/cong-no-ncc" },
        { label: "Kiểm soát: trùng HĐ NCC + khớp 3 chiều", icon: "fa-shield-halved", type: "route", route: "/cong-no-ncc" },
        { label: "Hóa đơn NCC chờ thanh toán (Desk)", icon: "fa-clock", type: "desk", href: "/app/purchase-invoice?status=Unpaid" },
      ]},
    ],
  },
  {
    key: "payroll",
    label: "Kế toán tiền lương",
    icon: "fa-money-check-dollar",
    desc: "Tính lương, duyệt phiếu lương, xuất bảng lương",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
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
    desc: "Quỹ tiền mặt & ngân hàng, bút toán, sổ cái",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
        { label: "Bút toán (Journal Entry)", icon: "fa-pen-to-square", type: "desk", href: "/app/journal-entry/new" },
        { label: "Nhập sổ quỹ nhanh", icon: "fa-money-bill-wave", type: "route", route: "/quy" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Sổ quỹ & dòng tiền", icon: "fa-wallet", type: "route", route: "/quy" },
        { label: "Sổ cái (General Ledger)", icon: "fa-book", type: "desk", href: "/app/general-ledger" },
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
    desc: "Tổng quan toàn phòng, cảnh báo, cấu hình",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
        { label: "Bàn Kế toán NPP", icon: "fa-handshake", type: "route", route: "/vt/npp" },
        { label: "Bàn Kế toán MT", icon: "fa-store", type: "route", route: "/vt/mt" },
        { label: "Bàn Kế toán Du lịch, Khác", icon: "fa-umbrella-beach", type: "route", route: "/vt/travel" },
        { label: "Bàn mua hàng", icon: "fa-truck-field", type: "route", route: "/vt/purchase" },
        { label: "Bàn tiền lương", icon: "fa-money-check-dollar", type: "route", route: "/vt/payroll" },
        { label: "Bàn hạch toán", icon: "fa-book", type: "route", route: "/vt/gl" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Dashboard tổng hợp", icon: "fa-gauge-high", type: "route", route: "/dashboard" },
        { label: "Công nợ phải thu toàn bộ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no" },
        { label: "Trung tâm cảnh báo", icon: "fa-triangle-exclamation", type: "route", route: "/canh-bao" },
        { label: "Sổ cái", icon: "fa-book", type: "desk", href: "/app/general-ledger" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Cấu hình portal (Settings)", icon: "fa-gear", type: "desk", href: "/app/ketoan-portal-settings" },
        { label: "Vai trò người dùng", icon: "fa-user-shield", type: "desk", href: "/app/user" },
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
