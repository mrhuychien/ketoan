// workspaces.js — cấu hình 5 workspace theo vai trò kế toán.
// Mỗi workspace 3 mục: Tác nghiệp (deep-link Desk) / Báo cáo / Công cụ.
// item.type: "desk" (href ra /app), "route" (route nội bộ #/...).

export const WORKSPACES = [
  {
    key: "sales",
    label: "Kế toán bán hàng",
    icon: "fa-cart-shopping",
    desc: "Công nợ phải thu, đối chiếu NPP, thu tiền khách hàng",
    sections: [
      { title: "Tác nghiệp", icon: "fa-bolt", items: [
        { label: "Lập hóa đơn bán", icon: "fa-file-invoice", type: "desk", href: "/app/sales-invoice/new" },
        { label: "Phiếu thu tiền", icon: "fa-money-bill-wave", type: "desk", href: "/app/payment-entry/new" },
        { label: "Khách hàng", icon: "fa-users", type: "desk", href: "/app/customer" },
        { label: "Đơn bán hàng", icon: "fa-file-lines", type: "desk", href: "/app/sales-order" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Công nợ phải thu + tuổi nợ", icon: "fa-file-invoice-dollar", type: "route", route: "/cong-no" },
        { label: "Đối chiếu công nợ NPP", icon: "fa-handshake", type: "route", route: "/doi-chieu-npp" },
        { label: "Accounts Receivable", icon: "fa-table", type: "desk", href: "/app/accounts-receivable" },
        { label: "Sales Register", icon: "fa-table", type: "desk", href: "/app/query-report/Sales Register" },
      ]},
      { title: "Công cụ", icon: "fa-screwdriver-wrench", items: [
        { label: "Tìm khách → 360°", icon: "fa-magnifying-glass", type: "route", route: "/tien-ich" },
        { label: "Chiết khấu / nhắc nợ NPP", icon: "fa-percent", type: "route", route: "/doi-chieu-npp" },
        { label: "Xuất đối chiếu công nợ (PDF)", icon: "fa-file-pdf", type: "route", route: "/cong-no" },
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
        { label: "Bàn bán hàng", icon: "fa-cart-shopping", type: "route", route: "/vt/sales" },
        { label: "Bàn mua hàng", icon: "fa-truck-field", type: "route", route: "/vt/purchase" },
        { label: "Bàn tiền lương", icon: "fa-money-check-dollar", type: "route", route: "/vt/payroll" },
        { label: "Bàn hạch toán", icon: "fa-book", type: "route", route: "/vt/gl" },
      ]},
      { title: "Báo cáo", icon: "fa-chart-line", items: [
        { label: "Dashboard tổng hợp", icon: "fa-gauge-high", type: "route", route: "/dashboard" },
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
