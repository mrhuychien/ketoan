"""Whitelisted methods — Nhập sổ quỹ từ file sao kê ngân hàng (Excel).

- parse_statement: đọc file .xlsx (cột: Số tham chiếu / Ngày / Ghi nợ / Ghi có /
  Số dư / Nội dung), trả danh sách giao dịch + cờ trùng (đã nhập trước đó).
- import_transactions: tạo Journal Entry (Bank Entry) cho các dòng đã chọn —
  Ghi có (tiền vào) → Nợ TK ngân hàng / Có TK đối ứng; Ghi nợ (tiền ra) → ngược lại.
  DRAFT, chống trùng bằng marker [BANKIMP-<key>] ghi trong field remark.

TK ngân hàng (112) do người dùng chọn. Read trừ import (ghi DRAFT). Guard quỹ.
"""

import base64
import hashlib
import io
import json
import re
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt

from ketoan.api._guard import guard_cash, resolve_company
from ketoan.utils import je_remark_field

_MARK_RE = re.compile(r"\[BANKIMP-([0-9a-f]{16})\]")


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace(" ", "").strip()
    try:
        return float(s or 0)
    except ValueError:
        return 0.0


def _parse_date(v):
    """Trả (iso_date, raw_str). Hỗ trợ datetime hoặc 'dd/mm/yyyy[ HH:MM:SS]'."""
    if isinstance(v, datetime):
        return v.date().isoformat(), v.isoformat(sep=" ")
    s = str(v or "").strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat(), s
        except ValueError:
            continue
    return None, s


def _row_key(ref, date_iso, debit, credit, content) -> str:
    raw = f"{ref}|{date_iso}|{debit}|{credit}|{(content or '')[:60]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _suggest_bank_account(company: str) -> str | None:
    """Đoán TK ngân hàng 112 (account_number/name bắt đầu 112)."""
    rows = frappe.get_all(
        "Account",
        filters={"company": company, "account_type": "Bank", "is_group": 0, "disabled": 0},
        fields=["name", "account_number"],
        order_by="account_number, name",
    )
    for a in rows:
        if (a.account_number or "").startswith("112") or a.name.startswith("112"):
            return a.name
    return rows[0].name if rows else None


@frappe.whitelist()
def get_import_options(company: str | None = None) -> dict:
    """TK ngân hàng (Bank) + TK đối ứng gợi ý + TK ngân hàng đề xuất (112)."""
    guard_cash()
    company = resolve_company(company)
    bank_accounts = frappe.get_all(
        "Account",
        filters={"company": company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0, "disabled": 0},
        fields=["name", "account_name", "account_type"],
        order_by="account_type, name",
    )
    counter_accounts = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "disabled": 0},
        fields=["name", "account_name", "root_type", "account_type"],
        order_by="root_type, name",
        limit=1000,
    )
    return {
        "company": company,
        "bank_accounts": bank_accounts,
        "counter_accounts": counter_accounts,
        "suggested_bank": _suggest_bank_account(company),
    }


@frappe.whitelist()
def parse_statement(content: str, company: str | None = None) -> dict:
    """Đọc file sao kê .xlsx (base64) → danh sách giao dịch + cờ trùng."""
    guard_cash()
    company = resolve_company(company)

    raw = base64.b64decode((content or "").split(",")[-1])
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        frappe.throw(_("Không đọc được file Excel. Hãy xuất đúng định dạng .xlsx"))

    ws = wb.active
    txns = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # bỏ header
        if not row or len(row) < 6:
            continue
        ref = str(row[0] or "").strip()
        date_iso, date_raw = _parse_date(row[1])
        debit = _num(row[2])   # Ghi nợ = tiền RA khỏi ngân hàng
        credit = _num(row[3])  # Ghi có = tiền VÀO ngân hàng
        content_txt = str(row[5] or "").strip()
        if not date_iso or (debit == 0 and credit == 0):
            continue
        key = _row_key(ref, date_iso, debit, credit, content_txt)
        txns.append({
            "key": key,
            "ref": ref,
            "date": date_iso,
            "datetime": date_raw,
            "debit": debit,
            "credit": credit,
            "direction": "in" if credit > 0 else "out",
            "content": content_txt,
        })

    if not txns:
        return {"company": company, "transactions": [], "duplicates": 0}

    # Lọc trùng: dò marker [BANKIMP-key] trong JE đã có (theo khoảng ngày của file).
    dates = [t["date"] for t in txns]
    field = je_remark_field()
    existing = set()
    cands = frappe.get_all(
        "Journal Entry",
        filters={field: ["like", "%[BANKIMP-%"], "docstatus": ["<", 2],
                 "company": company, "posting_date": ["between", [min(dates), max(dates)]]},
        fields=["name", field],
        limit=5000,
    )
    for c in cands:
        for m in _MARK_RE.findall(c.get(field) or ""):
            existing.add(m)

    dup_count = 0
    for t in txns:
        t["duplicate"] = t["key"] in existing
        if t["duplicate"]:
            dup_count += 1

    return {"company": company, "transactions": txns, "duplicates": dup_count, "total": len(txns)}


@frappe.whitelist()
def import_transactions(rows, bank_account: str, company: str | None = None) -> dict:
    """Tạo Journal Entry (Bank Entry) DRAFT cho các giao dịch đã chọn.

    rows: JSON list {key, date, debit, credit, content, counter_account, party?}.
    """
    guard_cash()
    company = resolve_company(company)
    if isinstance(rows, str):
        rows = json.loads(rows)
    if not rows:
        frappe.throw(_("Chưa chọn giao dịch nào"))
    if not bank_account:
        frappe.throw(_("Chưa chọn tài khoản ngân hàng"))

    bank = frappe.db.get_value("Account", bank_account, ["company", "is_group", "disabled"], as_dict=True)
    if not bank or bank.company != company or bank.is_group or bank.disabled:
        frappe.throw(_("Tài khoản ngân hàng không hợp lệ"))
    if len(rows) > 500:
        frappe.throw(_("Tối đa 500 giao dịch mỗi lần nhập"))

    field = je_remark_field()
    # Khóa trùng hiện có trong khoảng ngày.
    dates = [r.get("date") for r in rows if r.get("date")]
    existing = set()
    if dates:
        for c in frappe.get_all(
            "Journal Entry",
            filters={field: ["like", "%[BANKIMP-%"], "docstatus": ["<", 2],
                     "company": company, "posting_date": ["between", [min(dates), max(dates)]]},
            fields=[field], limit=5000,
        ):
            existing.update(_MARK_RE.findall(c.get(field) or ""))

    created, skipped = [], []
    for r in rows:
        key = r.get("key") or _row_key(r.get("ref", ""), r.get("date"), r.get("debit"), r.get("credit"), r.get("content"))
        if key in existing:
            skipped.append({"key": key, "reason": "Đã nhập trước đó"})
            continue
        counter = r.get("counter_account")
        if not counter:
            skipped.append({"key": key, "reason": "Chưa chọn TK đối ứng"})
            continue
        debit = _num(r.get("debit"))
        credit = _num(r.get("credit"))
        amount = credit if credit > 0 else debit
        if amount <= 0:
            skipped.append({"key": key, "reason": "Số tiền = 0"})
            continue

        cacc = frappe.db.get_value("Account", counter, ["company", "is_group", "account_type"], as_dict=True)
        if not cacc or cacc.company != company or cacc.is_group:
            skipped.append({"key": key, "reason": "TK đối ứng không hợp lệ"})
            continue
        party = (r.get("party") or "").strip() or None
        if cacc.account_type in ("Receivable", "Payable") and not party:
            skipped.append({"key": key, "reason": "TK đối ứng cần đối tượng (KH/NCC)"})
            continue
        party_type = None
        if party:
            party_type = "Customer" if cacc.account_type == "Receivable" else "Supplier"

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Bank Entry"
        je.posting_date = r.get("date")
        je.company = company
        je.set(field, f"[BANKIMP-{key}] {(r.get('content') or '')[:240]}")

        bank_line = {"account": bank_account}
        counter_line = {"account": counter}
        if party:
            counter_line["party_type"] = party_type
            counter_line["party"] = party
        if credit > 0:
            # Tiền VÀO ngân hàng: Nợ ngân hàng / Có đối ứng
            bank_line["debit_in_account_currency"] = amount
            counter_line["credit_in_account_currency"] = amount
        else:
            # Tiền RA khỏi ngân hàng: Nợ đối ứng / Có ngân hàng
            counter_line["debit_in_account_currency"] = amount
            bank_line["credit_in_account_currency"] = amount
        je.append("accounts", counter_line if credit <= 0 else bank_line)
        je.append("accounts", bank_line if credit <= 0 else counter_line)

        try:
            je.insert()
            existing.add(key)
            created.append({"key": key, "name": je.name, "route": f"/app/journal-entry/{je.name}"})
        except Exception as e:
            skipped.append({"key": key, "reason": str(e)[:120]})

    return {"created": created, "skipped": skipped, "count": len(created)}
