// =============================================================================
// Sales Invoice — Client Script (Desk)
// =============================================================================
// Bản này THAY THẾ toàn bộ Client Script cũ trên Sales Invoice.
//
// Khác bản cũ đúng một điểm về MISA: phần đẩy hóa đơn đã chuyển xuống server
// (ketoan/api/misa_push.py). Client Script không còn giữ username/mật khẩu,
// không còn dựng payload, không còn tự gọi api.meinvoice.vn.
//
// Toàn bộ nghiệp vụ còn lại — đọc số thành chữ, nạp giá, tính kiện/thể tích,
// ép conversion_factor — giữ NGUYÊN không đổi.
//
// Bản gốc của file này nằm trong git:
//   ketoan/misa_integration/client_script_sales_invoice.js
// Sửa ở đây thì nhớ sửa cả trong git, đừng để hai bên lệch nhau.
// =============================================================================

const numberToWords = (() => {
    const mangso = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín'];

    const dochangchuc = (so, daydu) => {
        let chuoi = "";
        const chuc = Math.floor(so / 10);
        const donvi = so % 10;

        if (chuc > 1) {
            chuoi = ` ${mangso[chuc]} mươi`;
            if (donvi === 1) chuoi += " mốt";
        } else if (chuc === 1) {
            chuoi = " mười";
            if (donvi === 1) chuoi += " một";
        } else if (daydu && donvi > 0) {
            chuoi = " lẻ";
        }

        if (donvi === 5 && chuc > 1) chuoi += " lăm";
        else if (donvi > 1 || (donvi === 1 && chuc === 0)) chuoi += ` ${mangso[donvi]}`;

        return chuoi;
    };

    const docblock = (so, daydu) => {
        let chuoi = "";
        const tram = Math.floor(so / 100);
        so = so % 100;
        if (daydu || tram > 0) {
            chuoi = ` ${mangso[tram]} trăm${dochangchuc(so, true)}`;
        } else {
            chuoi = dochangchuc(so, false);
        }
        return chuoi;
    };

    const dochangtrieu = (so, daydu) => {
        let chuoi = "";
        let trieu = Math.floor(so / 1000000);
        so = so % 1000000;
        if (trieu > 0) {
            chuoi = `${docblock(trieu, daydu)} triệu`;
            daydu = true;
        }
        const nghin = Math.floor(so / 1000);
        so = so % 1000;
        if (nghin > 0) {
            chuoi += `${docblock(nghin, daydu)} nghìn`;
            daydu = true;
        }
        if (so > 0) chuoi += docblock(so, daydu);
        return chuoi;
    };

    return (so) => {
        if (so === 0) return mangso[0];
        let chuoi = "", hauto = "";
        do {
            const ty = so % 1000000000;
            so = Math.floor(so / 1000000000);
            chuoi = (so > 0 ? dochangtrieu(ty, true) : dochangtrieu(ty, false)) + hauto + chuoi;
            hauto = " tỷ";
        } while (so > 0);
        return chuoi.trim();
    };
})();

const jsUcfirst = string => string.charAt(0).toUpperCase() + string.slice(1);


// -----------------------------------------------------------------------------
// Helper: batch fetch master data từ Item DocType
// -----------------------------------------------------------------------------
const fetchItemMasterData = async (items) => {
    const itemCodes = [...new Set(items.map(r => r.item_code).filter(Boolean))];
    if (itemCodes.length === 0) return {};

    const result = await frappe.db.get_list("Item", {
        filters: { name: ["in", itemCodes] },
        fields: ["name", "custom_quycach", "custom_thể_tích"],
        limit: itemCodes.length
    });

    const master = {};
    for (const item of result) {
        master[item.name] = {
            quycach: item.custom_quycach || 0,
            thetich: item.custom_thể_tích || 0
        };
    }
    return master;
};


// -----------------------------------------------------------------------------
// MISA meInvoice — ĐẨY HÓA ĐƠN
// -----------------------------------------------------------------------------
// Toàn bộ việc nặng nằm ở server: lấy token, dựng payload, tính thuế theo từng
// dòng, chặn đẩy trùng, chặn lệch tiền. Ở đây chỉ gọi và hiện kết quả.
//
// Server sẽ TỪ CHỐI nếu: chưa bật "Cho phép đẩy hóa đơn" trong MISA Settings,
// hóa đơn chưa ghi sổ, là hóa đơn trả hàng, đã đẩy trước đó, hoặc tổng tiền
// dựng ra lệch với sổ. Không cần kiểm lại ở client.
// -----------------------------------------------------------------------------
const pushToMisa = async (frm, { silent = false } = {}) => {
    try {
        const r = await frappe.call({
            method: "ketoan.api.misa_push.push_invoice",
            args: { sales_invoice: frm.doc.name },
            freeze: !silent,
            freeze_message: "Đang đẩy hóa đơn sang MISA..."
        });
        const res = r.message || {};

        if (res.already) {
            if (!silent) frappe.msgprint(res.message);
            return;
        }
        if (!res.ok) {
            frappe.msgprint({ title: "Đẩy hóa đơn thất bại", message: res.message, indicator: "red" });
            return;
        }

        let msg = res.message;
        if (res.vat_rates && res.vat_rates.length > 1) {
            msg += `<br><b>Hóa đơn có nhiều thuế suất: ${res.vat_rates.join("%, ")}%</b>`;
        }
        frappe.msgprint({ title: "Đã đẩy sang MISA", message: msg, indicator: "green" });
        frm.reload_doc();
    } catch (e) {
        // frappe.call đã hiện lỗi server. Ở đây chỉ ghi console để dò về sau.
        console.error("push_invoice:", e);
    }
};


// -----------------------------------------------------------------------------
// Sales Invoice Item — ép conversion_factor bám theo item_code
// -----------------------------------------------------------------------------
// ERPNext KHÔNG tự cập nhật conversion_factor khi đổi item_code trên dòng đã có
// giá trị: get_item_details.py:525 dùng `ctx.conversion_factor or get_conversion_factor(...)`
// mà client lại gửi giá trị cũ lên → toán tử `or` đoản mạch, trả về số cũ.
// Hệ quả: TX300 (30 hộp/thùng) sửa thành TX170 (48) vẫn giữ 30.
frappe.ui.form.on("Sales Invoice Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code || !row.uom) return;

        // after_ajax: đợi get_item_details của ERPNext hạ cánh rồi mới ghi đè.
        frappe.after_ajax(() => {
            frappe.call({
                method: "erpnext.stock.get_item_details.get_conversion_factor",
                args: { item_code: row.item_code, uom: row.uom },
                callback(r) {
                    if (!r.message) return;
                    const fresh = locals[cdt][cdn];
                    if (!fresh || fresh.item_code !== row.item_code) return;
                    frappe.model.set_value(cdt, cdn,
                        "conversion_factor", r.message.conversion_factor);
                }
            });
        });
    }
});


// -----------------------------------------------------------------------------
// Sales Invoice — main handlers
// -----------------------------------------------------------------------------
frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        // Nút đẩy tay — dùng khi đẩy tự động lỗi, hoặc khi kế toán muốn chủ động.
        if (frm.doc.docstatus === 1 && !frm.doc.is_return
            && !frm.doc.custom_misa_pushed_at && !frm.doc.vn_einvoice_lookup_code) {
            frm.add_custom_button("Đẩy hóa đơn sang MISA", () => pushToMisa(frm), "MISA");
        }
        if (frm.doc.docstatus === 1 && frm.doc.custom_misa_ref_id) {
            frm.add_custom_button("Xem trước dữ liệu gửi MISA", () => {
                frappe.call({
                    method: "ketoan.api.misa_push.preview_payload",
                    args: { sales_invoice: frm.doc.name }
                }).then(r => {
                    frappe.msgprint({
                        title: "Dữ liệu sẽ gửi sang MISA",
                        message: `<pre style="max-height:60vh;overflow:auto">${
                            frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`,
                        wide: true
                    });
                });
            }, "MISA");
        }
    },

    validate: async (frm) => {
        const {
            items,
            custom_po_: so_po,
            custom_cod: số_tiền_cod,
            is_return,
            customer_group,
            custom_hàng_dùng_thử: hangdungthu,
            grand_total,
            total
        } = frm.doc;

        // 1. Auto-load Item Price khi rate trống
        for (let row of items) {
            if ((!row.rate || row.rate === 0) && frm.doc.selling_price_list) {
                try {
                    const result = await frappe.call({
                        method: "frappe.client.get_list",
                        args: {
                            doctype: "Item Price",
                            filters: {
                                item_code: row.item_code,
                                price_list: frm.doc.selling_price_list,
                                selling: 1
                            },
                            fields: ["price_list_rate", "uom"],
                            limit: 1,
                            order_by: "valid_from desc"
                        }
                    });

                    if (result.message && result.message.length > 0) {
                        row.rate = result.message[0].price_list_rate;
                        row.price_list_rate = result.message[0].price_list_rate;

                        frappe.show_alert({
                            message: `Đã load giá cho ${row.item_name}: ${frappe.format(row.rate, { fieldtype: 'Currency' })}`,
                            indicator: 'green'
                        });
                    } else {
                        frappe.show_alert({
                            message: `Không tìm thấy giá cho ${row.item_name} trong bảng giá ${frm.doc.selling_price_list}`,
                            indicator: 'orange'
                        });
                    }
                } catch (error) {
                    console.error(`Lỗi khi load giá cho ${row.item_code}:`, error);
                }
            }
        }

        // 2. Batch fetch master data (custom_quycach, custom_thể_tích) từ Item
        const itemMaster = await fetchItemMasterData(items);

        // 3. Tính tổng (KHÔNG persist xuống row — dùng standard fields)
        let total_amount = 0, total_volume = 0, full_boxes = 0, rem_pieces = 0;

        items.forEach(row => {
            const m = itemMaster[row.item_code] || { quycach: 0, thetich: 0 };
            const stockQty = row.stock_qty || (row.qty * (row.conversion_factor || 1));

            total_amount += (row.qty || 0) * (row.price_list_rate || 0);

            if (m.quycach > 0) {
                full_boxes += Math.floor(stockQty / m.quycach);
                rem_pieces += stockQty % m.quycach;
            }
            total_volume += m.thetich * stockQty;

            if (frm.doc.set_warehouse) row.warehouse = frm.doc.set_warehouse;
            if (is_return) row.income_account = "5213 - Hàng bán bị trả lại - HGC";
        });

        // 4. Set parent fields
        await frm.set_value({
            po_no: so_po,
            custom_tổng_cộng: total_amount,
            custom_thể_tích_lô: total_volume,
            custom_tổng_kiện: full_boxes,
            custom_hộp_lẻ: rem_pieces,
            custom_tiền_chiết_khấu: total_amount - total,
            custom_ghi_bằng_chữ: jsUcfirst(numberToWords(Math.round(grand_total)) + " đồng"),
            remarks: is_return ? "Trả hàng" : "Nhập hàng",
            update_stock: !is_return
        });

        // 5. COD handling
        if (số_tiền_cod > 0) {
            await frm.set_value({
                po_no: "THU HỘ COD",
                remarks: `Thu hộ COD. Số tiền: ${số_tiền_cod}`
            });
        }

        // 6. Auto-load taxes nếu chưa có
        if (frm.doc.taxes_and_charges && (!frm.doc.taxes || frm.doc.taxes.length === 0)) {
            const result = await frappe.call({
                method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
                args: {
                    doctype: frm.doc.doctype,
                    master_name: frm.doc.taxes_and_charges,
                    master_doctype: "Sales Taxes and Charges Template"
                }
            });
            if (result.message) {
                frm.clear_table("taxes");
                result.message.forEach(d => {
                    let row = frm.add_child("taxes");
                    Object.assign(row, d);
                });
                frm.refresh_field("taxes");
            }
        }

        // 7. Cảnh báo hàng dùng thử cho khách Du lịch
        if (hangdungthu && customer_group === "Du lịch") {
            frappe.msgprint(`Lưu ý hàng dùng thử ${hangdungthu}`, __('Chú ý'));
        }
    },

    after_save(frm) {
        // Đẩy tự động khi kế toán đã tick cờ xuất hóa đơn.
        //
        // Điều kiện chặn đẩy trùng giữ CẢ HAI vế:
        //   custom_misa_pushed_at    — hóa đơn đẩy bằng luồng mới
        //   vn_einvoice_lookup_code  — hóa đơn đẩy bằng luồng CŨ (không có
        //                              pushed_at). Bỏ vế này là chúng bị phát
        //                              hành lần thứ hai.
        // Server còn chặn lần nữa; đây chỉ để đỡ gọi thừa.
        if (
            frm.doc.docstatus === 1 &&
            !frm.doc.is_return &&
            (frm.doc.custom_xuất_hoá_đơn === 1 || frm.doc.custom_xuất_theo_hộp_ === 1) &&
            !frm.doc.custom_misa_pushed_at &&
            !frm.doc.vn_einvoice_lookup_code
        ) {
            pushToMisa(frm, { silent: true });
        }
    }
});
