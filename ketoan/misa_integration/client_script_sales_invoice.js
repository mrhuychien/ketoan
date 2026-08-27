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

        // chuc >= 1 chứ không phải > 1: thiếu vế chuc === 1 thì 15 đọc thành
        // "mười năm". Sai ở ô "số tiền bằng chữ" của hóa đơn là sai chứng từ.
        if (donvi === 5 && chuc >= 1) chuoi += " lăm";
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

    return function docso(so) {
        so = Math.round(Number(so) || 0);
        if (so === 0) return mangso[0];
        // Hóa đơn trả hàng mang số âm; vòng do/while dưới dừng ngay ở số âm và
        // trả chuỗi rỗng, làm ô "bằng chữ" trống trên chứng từ.
        if (so < 0) return "âm " + docso(-so);
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
const _pushing = new Set();   // tên hóa đơn đang có request đẩy bay trên đường

// Khóa/mở nút đẩy. Nút nằm TRONG nhóm "MISA" nên Frappe render nó thành
// `<a class="dropdown-item">`, không phải `<button>` — gán `.disabled` lên thẻ
// `<a>` là câu lệnh chạy được nhưng KHÔNG có tác dụng gì, bấm vẫn ăn. Phải chặn
// bằng lớp `disabled` + `pointer-events`.
//
// Đây không phải chốt chặn chính: `_pushing` và khóa hàng ở server mới là chốt.
// Nhưng một nút trông vẫn bấm được trong lúc đang đẩy thì kế toán sẽ bấm lại.
const _setPushDisabled = (on) => {
    $('[data-misa-push]')
        .prop("disabled", on)
        .toggleClass("disabled", on)
        .css("pointer-events", on ? "none" : "");
};

const pushToMisa = async (frm, { silent = false } = {}) => {
    // Server còn khóa lần nữa; đây chỉ để tránh auto-push (không freeze màn hình)
    // và nút bấm tay cùng gửi hai request tạo hai hóa đơn cho một chứng từ.
    if (_pushing.has(frm.doc.name)) return;
    _pushing.add(frm.doc.name);
    _setPushDisabled(true);
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
    } finally {
        _pushing.delete(frm.doc.name);
        _setPushDisabled(false);
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
// Nút của nhóm "MISA" trên thanh công cụ
// -----------------------------------------------------------------------------
// Tách khỏi handler `refresh` để chỗ gọi bọc được try/catch — xem chú thích dài
// ở `refresh` bên dưới.
//
// `frm.add_custom_button` trả về **đối tượng jQuery**, KHÔNG phải DOM element.
// Mọi thao tác lên nó phải dùng API của jQuery (`.attr`, `.prop`, `.addClass`).
// Gọi `.setAttribute` / `.disabled` lên nó là ném TypeError, và ở đây một
// TypeError không chỉ mất một nút — nó làm gãy cả chuỗi refresh của form.
const misaButtons = (frm) => {
    // Mở hóa đơn bên MISA. Mẫu URL khai trong MISA Settings nên sửa được
    // mà không phải đụng code.
    if (frm.doc.custom_misa_transaction_id || frm.doc.custom_misa_link) {
        frm.add_custom_button("Mở hóa đơn trên MISA", async () => {
            const r = await frappe.call({
                method: "ketoan.api.misa_desk.get_invoice_links",
                args: { sales_invoice: frm.doc.name }
            });
            const link = (r.message || {}).misa;
            if (link) window.open(link, "_blank", "noopener");
            else frappe.msgprint("Chưa khai mẫu link trong MISA Settings.");
        }, "MISA");

        frm.add_custom_button("Tra cứu công khai", async () => {
            const r = await frappe.call({
                method: "ketoan.api.misa_desk.get_invoice_links",
                args: { sales_invoice: frm.doc.name }
            });
            const res = r.message || {};
            if (res.lookup) window.open(res.lookup, "_blank", "noopener");
            if (res.transaction_id) {
                frappe.show_alert({
                    message: `Mã tra cứu: <b>${frappe.utils.escape_html(res.transaction_id)}</b>`,
                    indicator: "blue"
                }, 15);
            }
        }, "MISA");
    }

    // Nút đẩy tay — dùng khi đẩy tự động lỗi, hoặc khi kế toán muốn chủ động.
    if (frm.doc.docstatus === 1 && !frm.doc.is_return
        && !frm.doc.custom_misa_pushed_at && !frm.doc.vn_einvoice_lookup_code) {
        frm.add_custom_button("Đẩy hóa đơn sang MISA", () => pushToMisa(frm), "MISA")
            .attr("data-misa-push", "1");
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
};


// -----------------------------------------------------------------------------
// Phần tính tự động khi lưu hóa đơn
// -----------------------------------------------------------------------------
// Tách khỏi handler `validate` để chỗ gọi bọc được lỗi.
//
// `validate` là `async`, và Frappe chạy validate -> before_save -> save NỐI TIẾP
// NHAU. Một promise reject ở đây làm lệnh lưu không bao giờ chạy — form đứng im
// ở "Not Saved" mà không hiện lỗi nào. Đó là kiểu hỏng tệ nhất cho người dùng:
// bấm Lưu, không có gì xảy ra, bấm lại vẫn không có gì xảy ra.
//
// Hàm này KHÔNG chặn lưu bằng nghiệp vụ: nó chỉ tính và điền. Mọi lời `throw`
// thoát ra khỏi đây đều là SỰ CỐ, không phải luật kiểm — và được xử ở chỗ gọi.
const enrichInvoice = async (frm) => {
        const {
            items,
            custom_po_: so_po,
            custom_cod: số_tiền_cod,
            is_return,
            customer_group,
            custom_hàng_dùng_thử: hangdungthu,
        } = frm.doc;   // KHÔNG lấy grand_total/total ở đây — chúng còn đổi bên dưới

        // 1. Auto-load Item Price khi rate trống.
        //
        // BẮT BUỘC lọc theo ĐƠN VỊ TÍNH của dòng và theo hiệu lực. Bản cũ chỉ lọc
        // item_code + price_list rồi lấy bản valid_from mới nhất, nên mặt hàng có
        // cả giá /Thùng lẫn giá /Hộp sẽ nhận nhầm giá của đơn vị kia — sai đơn giá
        // trên hóa đơn thật. Bản cũ cũng ghi đè price_list_rate làm báo cáo soát
        // giá mất mốc so sánh, nên ở đây chỉ đặt rate.
        const postingDate = frm.doc.posting_date || frappe.datetime.get_today();
        for (let row of items) {
            if ((row.rate && row.rate !== 0) || !frm.doc.selling_price_list || !row.item_code) continue;
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
                        fields: ["price_list_rate", "uom", "valid_from", "valid_upto"],
                        limit: 50,
                        order_by: "valid_from desc"
                    }
                });
                const all = (result.message || []).filter((p) => {
                    if (p.valid_from && p.valid_from > postingDate) return false;
                    if (p.valid_upto && p.valid_upto < postingDate) return false;
                    return true;
                });
                // Ưu tiên giá đúng đơn vị tính của dòng; giá không khai đơn vị mới
                // dùng làm dự phòng. Giá của đơn vị KHÁC thì tuyệt đối không lấy.
                const exact = all.find((p) => p.uom && row.uom && p.uom === row.uom);
                const generic = all.find((p) => !p.uom);
                const picked = exact || generic;

                if (picked) {
                    row.rate = picked.price_list_rate;
                    frappe.show_alert({
                        message: `Đã load giá cho ${row.item_name}: ${frappe.format(picked.price_list_rate, { fieldtype: 'Currency' })}`
                            + (picked.uom ? ` / ${picked.uom}` : ""),
                        indicator: 'green'
                    });
                } else if (all.length) {
                    frappe.show_alert({
                        message: `Bảng giá ${frm.doc.selling_price_list} có giá cho ${row.item_name}`
                            + ` nhưng KHÔNG phải đơn vị ${row.uom} — nhập đơn giá tay`,
                        indicator: 'red'
                    }, 10);
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

        // 2. Nạp bảng thuế nếu chưa có — PHẢI chạy trước bước tính tổng, vì
        // "số tiền bằng chữ" dựng từ grand_total. Bản cũ để bước này ở cuối nên
        // chứng từ in ra có số bằng chữ chưa gồm thuế, lệch số bằng số.
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

        // Ép ERPNext tính lại tổng sau khi đã đổi đơn giá và bảng thuế, để các
        // bước sau đọc được grand_total ĐÚNG chứ không phải số chụp lúc đầu hàm.
        try { frm.cscript.calculate_taxes_and_totals(); } catch (_) {}

        // 3. Batch fetch master data (custom_quycach, custom_thể_tích) từ Item
        //
        // ⚠ HAI FIELD NÀY KHÔNG DO APP TẠO. Không một dòng nào trong `install.py`
        // hay patch nào sinh ra chúng — chúng tồn tại vì có người khai tay trên
        // site production. Site mới, site clone để thử, hay site vừa restore mà
        // chưa khai lại thì truy vấn này hỏi cột không tồn tại và server trả lỗi.
        //
        // Không bọc thì hậu quả KHÔNG dừng ở mất mấy con số phụ: `validate` là
        // `async`, Frappe chạy validate → before_save → save nối tiếp nhau, một
        // rejection ở đây làm LỆNH LƯU KHÔNG BAO GIỜ CHẠY. Kế toán bấm Lưu, không
        // hộp thoại nào hiện, form đứng "Not Saved", bấm lại vẫn thế.
        //
        // Số kiện và thể tích là thông tin phụ trợ. Mất nó thì phải NÓI ra, chứ
        // không được chặn kế toán lưu hóa đơn.
        let itemMaster = {};
        try {
            itemMaster = await fetchItemMasterData(items);
        } catch (e) {
            console.error("ketoan: đọc quy cách/thể tích của Item thất bại —", e);
            frappe.show_alert({
                message: "Không đọc được quy cách/thể tích mặt hàng — số kiện và thể "
                    + "tích lô sẽ bằng 0. Hóa đơn vẫn lưu bình thường.",
                indicator: "orange"
            }, 10);
        }

        // 4. Tính tổng (KHÔNG persist xuống row — dùng standard fields)
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

        // 5. Set parent fields
        await frm.set_value({
            po_no: so_po,
            custom_tổng_cộng: total_amount,
            custom_thể_tích_lô: total_volume,
            custom_tổng_kiện: full_boxes,
            custom_hộp_lẻ: rem_pieces,
            custom_tiền_chiết_khấu: total_amount - (frm.doc.total || 0),
            custom_ghi_bằng_chữ: jsUcfirst(numberToWords(frm.doc.grand_total) + " đồng"),
            remarks: is_return ? "Trả hàng" : "Nhập hàng",
            update_stock: !is_return
        });

        // 6. COD handling
        if (số_tiền_cod > 0) {
            await frm.set_value({
                po_no: "THU HỘ COD",
                remarks: `Thu hộ COD. Số tiền: ${số_tiền_cod}`
            });
        }

        // 7. Cảnh báo hàng dùng thử cho khách Du lịch
        if (hangdungthu && customer_group === "Du lịch") {
            frappe.msgprint(`Lưu ý hàng dùng thử ${hangdungthu}`, __('Chú ý'));
        }
    
};


// -----------------------------------------------------------------------------
// Sales Invoice — main handlers
// -----------------------------------------------------------------------------
frappe.ui.form.on("Sales Invoice", {
    // ═════════════════════════════════════════════════════════════════════════
    // BẤT DI BẤT DỊCH: tích hợp MISA hỏng KHÔNG được làm hỏng form của kế toán.
    //
    // Đây là bản sao ở tầng client của đúng ràng buộc đã áp cho `ensure_ref_id`
    // bên server. Lý do ở client còn nặng hơn:
    //
    //   Frappe nối các handler `refresh` NỐI TIẾP BẰNG PROMISE (script_manager).
    //   MỘT ngoại lệ thoát ra là promise reject, và mọi thứ đứng sau trong chuỗi
    //   không chạy — kể cả phần dựng thanh công cụ. Người dùng mất hẳn nhóm nút
    //   "Create" của ERPNext (Payment · Return/Credit Note · Payment Request…)
    //   mà KHÔNG có thông báo nào; lỗi chỉ nằm trong Console.
    //
    // Đã xảy ra thật: `add_custom_button` trả về đối tượng jQuery, code cũ gọi
    // `.setAttribute()` của DOM lên nó -> TypeError -> mất nút Create trên đúng
    // những hóa đơn CHƯA đẩy MISA (điều kiện hiện nút đẩy tay). Hóa đơn đã đẩy
    // rồi thì không dựng nút đó nên không nổ — vì vậy lỗi trông như "chỉ một số
    // hóa đơn bị", loại triệu chứng khó lần nhất.
    //
    // Bọc try/catch ở đây không phải để giấu lỗi: lỗi vẫn in ra Console. Nó để
    // bảo đảm cái hỏng chỉ là mấy nút MISA, không kéo theo cả form.
    // ═════════════════════════════════════════════════════════════════════════
    refresh(frm) {
        try {
            misaButtons(frm);
        } catch (e) {
            console.error("ketoan/MISA: dựng nút trên Sales Invoice thất bại —", e);
        }
    },

    // Phần tính tự động nằm ở `enrichInvoice`; ở đây chỉ bọc lỗi. Xem chú thích
    // dài ngay trên hàm đó về việc VÌ SAO không được để lỗi trôi ra.
    validate: async (frm) => {
        try {
            await enrichInvoice(frm);
        } catch (e) {
            console.error("ketoan: phần tính tự động của Sales Invoice thất bại —", e);
            // KHÔNG nuốt lỗi, và cũng KHÔNG để nó trôi ra trần.
            //
            // Trôi ra trần: chuỗi lưu của Frappe reject, form đứng im ở "Not Saved",
            // không một dòng giải thích — kế toán bấm Lưu mãi không hiểu vì sao.
            // Nuốt đi: hóa đơn LƯU ĐƯỢC nhưng mang số liệu tính dở — trong đó có
            // `custom_ghi_bằng_chữ`, thứ IN LÊN CHỨNG TỪ. Số bằng chữ lệch số bằng
            // số là sai chứng từ, tệ hơn hẳn không lưu được.
            //
            // Nên: vẫn chặn lưu, nhưng chặn có nói lý do.
            frappe.throw({
                title: "Chưa lưu được — phần tính tự động lỗi",
                message: `Hóa đơn <b>CHƯA</b> được lưu.<br><br>Lỗi: <code>${
                    frappe.utils.escape_html(String((e && e.message) || e))}</code>`
                    + "<br><br>Hay gặp nhất: Item thiếu field <code>custom_quycach</code> / "
                    + "<code>custom_thể_tích</code>, hoặc tài khoản không có quyền đọc Item.",
            });
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
            // CHỈ cờ xuất hóa đơn. custom_xuất_theo_hộp_ thuần túy là cờ trình bày
            // (quy đổi số lượng/đơn giá về Hộp) — để nó ở đây thì tick nhầm một ô
            // định dạng là PHÁT HÀNH hóa đơn điện tử có giá trị pháp lý.
            frm.doc.custom_xuất_hoá_đơn === 1 &&
            !frm.doc.custom_misa_pushed_at &&
            !frm.doc.vn_einvoice_lookup_code
        ) {
            pushToMisa(frm, { silent: true });
        }
    }
});
