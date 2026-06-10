import frappe
from frappe import _
from frappe.utils import flt
import json


def _resolve_image(file_url):
    """Convert a private file path to a data URI, or return public path as-is."""
    if not file_url:
        return ""
    if file_url.startswith("http") or file_url.startswith("data:"):
        return file_url
    if not file_url.startswith("/private"):
        return file_url
    try:
        file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if not file_name:
            file_name = frappe.db.get_value("File", {"file_url": file_url.lstrip("/")}, "name")
        if not file_name:
            frappe.log_error(f"File not found for URL: {file_url}", "mobile_api._resolve_image")
            return file_url
        file_doc = frappe.get_doc("File", file_name)
        raw = file_doc.get_content()
        import base64
        if isinstance(raw, str):
            encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        else:
            encoded = base64.b64encode(raw).decode("utf-8")
        content_type = file_doc.get("content_type") or "image/png"
        return f"data:{content_type};base64,{encoded}"
    except Exception as e:
        frappe.log_error(f"Failed to resolve image {file_url}: {e}", "mobile_api._resolve_image")
        return file_url


def _get_net_outstanding(customer, company):
    """Return net outstanding balance (invoice outstanding minus unallocated payments)."""
    invoice_outstanding = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND company = %s AND outstanding_amount > 0
    """, (customer, company))
    invoice_total = invoice_outstanding[0][0] if invoice_outstanding else 0

    payment_unallocated = frappe.db.sql("""
        SELECT COALESCE(SUM(unallocated_amount), 0)
        FROM `tabPayment Entry`
        WHERE party = %s AND party_type = 'Customer' AND docstatus = 1
          AND company = %s AND unallocated_amount > 0
    """, (customer, company))
    unallocated_total = payment_unallocated[0][0] if payment_unallocated else 0

    return flt(invoice_total - unallocated_total)


@frappe.whitelist(allow_guest=False)
def login():
    user = frappe.session.user
    if user and user != "Guest":
        info = _get_user_info_dict(user)
        info["message"] = "Logged in"
        return info
    frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)


@frappe.whitelist(allow_guest=False)
def get_visit_types():
    types = frappe.get_all("Visit Type", fields=["name"], order_by="name asc")
    return [t["name"] for t in types]


@frappe.whitelist(allow_guest=False)
def get_field_types():
    types = frappe.get_all("Visit Type", fields=["name"], order_by="name asc")
    return [{"name": t["name"], "field_type_name": t["name"]} for t in types]


@frappe.whitelist(allow_guest=False)
def get_customers(territory=None, customer_group=None, limit=100):
    filters = [["disabled", "=", 0]]
    if territory:
        filters.append(["territory", "=", territory])
    if customer_group:
        filters.append(["customer_group", "=", customer_group])

    customers = frappe.get_all(
        "Customer",
        filters=filters,
        fields=[
            "name",
            "customer_name",
            "territory",
            "customer_group",
            "mobile_no",
            "email_id",
            "image",
            "primary_address",
        ],
        limit_page_length=limit,
        order_by="customer_name asc",
    )

    company = frappe.defaults.get_user_default("company") or (
        frappe.get_list("Company", limit=1, pluck="name")[0]
        if frappe.get_list("Company", limit=1)
        else None
    )
    for c in customers:
        outstanding = 0
        credit_limit = 0
        if company:
            outstanding = _get_net_outstanding(c["name"], company)

            credit_limit = frappe.db.get_value(
                "Customer Credit Limit",
                {"parent": c["name"], "company": company},
                "credit_limit"
            ) or 0

        c["outstanding_amount"] = outstanding
        c["credit_limit"] = credit_limit

        last_visit = frappe.db.get_value(
            "Field Visit",
            {"customer": c["name"], "docstatus": 0},
            "creation",
            order_by="creation desc"
        )
        c["last_visit_date"] = str(last_visit.date()) if last_visit else None

        c["image"] = _resolve_image(c.get("image"))

    return customers


@frappe.whitelist(allow_guest=False)
def get_customer_detail(customer):
    customer_doc = frappe.get_doc("Customer", customer)

    currency = frappe.defaults.get_user_default("currency") or "PKR"
    company = frappe.defaults.get_user_default("company") or frappe.get_list("Company", limit=1, pluck="name")[0] if frappe.get_list("Company", limit=1) else None

    outstanding = 0
    credit_limit = 0

    if company:
        outstanding = _get_net_outstanding(customer, company)

        credit_limit = frappe.db.get_value(
            "Customer Credit Limit",
            {"parent": customer, "company": company},
            "credit_limit"
        ) or 0

    recent_orders = frappe.get_all(
        "Sales Order",
        filters={"customer": customer, "docstatus": 1},
        fields=["name", "grand_total", "delivery_date", "creation", "status"],
        limit_page_length=5,
        order_by="creation desc",
    )

    recent_payments = frappe.get_all(
        "Payment Entry",
        filters={"party": customer, "docstatus": 1, "payment_type": "Receive"},
        fields=["name", "paid_amount", "reference_no", "payment_type", "creation", "mode_of_payment"],
        limit_page_length=5,
        order_by="creation desc",
    )

    recent_visits = frappe.get_all(
        "Field Visit",
        filters={"customer": customer},
        fields=["name", "field_type", "check_in_time", "remarks", "check_in_latitude", "check_in_longitude", "visit_status", "visit_outcome"],
        limit_page_length=10,
        order_by="creation desc",
    )

    return {
        "name": customer_doc.name,
        "customer_name": customer_doc.customer_name,
        "customer_primary_contact": customer_doc.customer_primary_contact,
        "mobile_no": customer_doc.get("mobile_no") or "",
        "email_id": customer_doc.get("email_id") or "",
        "territory": customer_doc.get("territory") or "",
        "customer_group": customer_doc.get("customer_group") or "",
        "primary_address": customer_doc.get("primary_address") or "",
        "image": _resolve_image(customer_doc.get("image")),
        "outstanding_amount": outstanding,
        "credit_limit": credit_limit,
        "credit_limit": credit_limit,
        "currency": currency,
        "recent_orders": recent_orders,
        "recent_payments": recent_payments,
        "recent_visits": recent_visits,
    }


@frappe.whitelist(allow_guest=False)
def get_items(limit=100):
    items = frappe.get_all(
        "Item",
        filters=[["disabled", "=", 0], ["is_sales_item", "=", 1]],
        fields=["name", "item_name", "item_group", "standard_rate", "description", "stock_uom"],
        limit_page_length=limit,
        order_by="item_name asc",
    )

    for item in items:
        actual_qty = frappe.db.get_value(
            "Bin",
            {"item_code": item["name"]},
            "actual_qty"
        )
        item["actual_qty"] = actual_qty or 0

    return items


@frappe.whitelist(allow_guest=False)
def get_dashboard_metrics():
    user = frappe.session.user
    today = frappe.utils.today()

    today_visits = frappe.db.count("Field Visit", {"user": user, "creation": (">=", today)})
    today_orders = frappe.db.count("Sales Order", {"modified_by": user, "transaction_date": today, "docstatus": 1})

    company = frappe.defaults.get_user_default("company")
    if not company:
        company = frappe.get_list("Company", limit=1, pluck="name")
        company = company[0] if company else None

    today_collections = frappe.db.sql("""
        SELECT COALESCE(SUM(paid_amount), 0)
        FROM `tabPayment Entry`
        WHERE company = %s AND posting_date = %s AND docstatus = 1 AND payment_type = 'Receive'
    """, (company or "", today))[0][0]

    total_outstanding = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
    """)[0][0]

    total_unallocated = frappe.db.sql("""
        SELECT COALESCE(SUM(unallocated_amount), 0)
        FROM `tabPayment Entry`
        WHERE docstatus = 1 AND party_type = 'Customer' AND unallocated_amount > 0
    """)[0][0]

    return {
        "today_visits_count": today_visits,
        "today_orders_count": today_orders,
        "today_collections_amount": today_collections,
        "total_outstanding_amount": flt(total_outstanding - total_unallocated),
    }


@frappe.whitelist(allow_guest=False)
def submit_field_visit():
    data = json.loads(frappe.request.data or "{}")

    offline_id = data.get("offline_record_id", "")
    if offline_id:
        existing = frappe.db.get_value("Field Visit", {"offline_record_id": offline_id}, "name")
        if existing:
            return {"name": existing, "party_type": data.get("party_type"), "party": data.get("party"), "party_name": data.get("party_name"), "duplicate": True}

    visit = frappe.new_doc("Field Visit")
    visit.party_type = data.get("party_type", "Customer")
    visit.party = data.get("party") or data.get("customer")
    visit.party_name = data.get("party_name", "")
    visit.field_type = data.get("visit_type") or data.get("field_type")
    visit.visit_status = data.get("visit_status", "Checked In")
    visit.visit_purpose = data.get("visit_purpose", "")
    visit.remarks = data.get("remarks", "")
    visit.check_in_latitude = data.get("gps_latitude") or data.get("check_in_latitude")
    visit.check_in_longitude = data.get("gps_longitude") or data.get("check_in_longitude")
    visit.check_in_time = data.get("check_in_time") or frappe.utils.now()
    visit.check_in_address = data.get("check_in_address", "")
    visit.next_follow_up_date = data.get("next_follow_up_date") or data.get("next_followup_date")
    visit.sales_person = data.get("sales_person", "")
    visit.employee = data.get("employee", "")
    visit.created_from_mobile = 1
    visit.offline_record_id = data.get("offline_record_id", "")
    visit.sync_status = "Synced"

    visit.insert(ignore_permissions=False)

    return {"name": visit.name, "party_type": visit.party_type, "party": visit.party, "party_name": visit.party_name}


@frappe.whitelist(allow_guest=False)
def update_field_visit():
    data = json.loads(frappe.request.data or "{}")

    visit_name = data.get("visit_name")
    if not visit_name:
        frappe.throw(_("visit_name is required"))

    visit = frappe.get_doc("Field Visit", visit_name)
    visit.visit_status = data.get("visit_status", "Completed")
    visit.remarks = data.get("remarks") or visit.remarks
    visit.visit_outcome = data.get("visit_outcome") or visit.visit_outcome
    visit.next_follow_up_date = data.get("next_follow_up_date") or data.get("next_followup_date") or visit.next_follow_up_date
    if data.get("check_out_latitude"):
        visit.check_out_latitude = data.get("check_out_latitude")
    if data.get("check_out_longitude"):
        visit.check_out_longitude = data.get("check_out_longitude")
    if data.get("check_out_time"):
        visit.check_out_time = data.get("check_out_time")
    else:
        visit.check_out_time = frappe.utils.now()
    visit.check_out_address = data.get("check_out_address", "")

    visit.save(ignore_permissions=False)

    return {"name": visit.name, "party_type": visit.party_type, "party": visit.party, "visit_status": visit.visit_status}


@frappe.whitelist(allow_guest=False)
def submit_sales_order():
    data = json.loads(frappe.request.data or "{}")

    items_data = data.get("items", [])

    so = frappe.new_doc("Sales Order")
    so.customer = data.get("customer")
    so.delivery_date = data.get("delivery_date")
    so.remarks = data.get("remarks", "")
    so.transaction_date = data.get("transaction_date") or frappe.utils.today()

    for item in items_data:
        so.append("items", {
            "item_code": item.get("item_code"),
            "qty": item.get("qty", 1),
            "rate": item.get("rate", 0),
            "delivery_date": data.get("delivery_date"),
        })

    field_visit = data.get("field_visit")
    if field_visit:
        so.custom_field_visit = field_visit

    so.insert(ignore_permissions=False)

    return {"name": so.name, "customer": so.customer, "grand_total": so.grand_total}


@frappe.whitelist(allow_guest=False)
def submit_payment_entry():
    data = json.loads(frappe.request.data or "{}")

    company = data.get("company") or ""
    if not company:
        try:
            settings = frappe.get_single("FieldForce Settings")
            company = settings.get("mobile_company") or ""
        except Exception:
            pass
    if not company:
        company = frappe.defaults.get_user_default("company")
    if not company:
        companies = frappe.get_list("Company", limit=1, pluck="name")
        company = companies[0] if companies else None
    if not company:
        frappe.throw(_("No Company found. Please set default company."))

    company_doc = frappe.get_cached_doc("Company", company)
    currency = company_doc.default_currency

    paid_from = company_doc.default_receivable_account
    if not paid_from:
        frappe.throw(_("Default Receivable Account not set for Company {0}").format(company))

    paid_to = data.get("paid_to")
    if not paid_to:
        mode_of_payment = data.get("mode_of_payment", "Cash")
        mode_doc = frappe.get_doc("Mode of Payment", mode_of_payment) if frappe.db.exists("Mode of Payment", mode_of_payment) else None
        if mode_doc:
            for acc in mode_doc.accounts:
                if acc.company == company and acc.default_account:
                    paid_to = acc.default_account
                    break
    if not paid_to:
        paid_to = company_doc.default_cash_account
    if not paid_to:
        frappe.throw(_("No Cash/Bank account found. Set Mode of Payment account or default Cash Account for Company {0}").format(company))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = data.get("party")
    pe.paid_amount = data.get("paid_amount")
    pe.received_amount = data.get("paid_amount")
    pe.company = company
    pe.mode_of_payment = data.get("mode_of_payment", "Cash")
    pe.reference_no = data.get("reference_no")
    pe.reference_date = data.get("reference_date") or frappe.utils.today()
    pe.posting_date = frappe.utils.today()
    pe.remarks = data.get("remarks", "")

    pe.paid_from = paid_from
    pe.paid_from_account_currency = currency
    pe.paid_to = paid_to
    pe.paid_to_account_currency = currency
    pe.source_exchange_rate = 1.0
    pe.target_exchange_rate = 1.0

    field_visit = data.get("field_visit")
    if field_visit:
        pe.custom_field_visit = field_visit

    selected_invoices = data.get("invoices", [])

    if selected_invoices:
        for inv_data in selected_invoices:
            pe.append("references", {
                "reference_doctype": "Sales Invoice",
                "reference_name": inv_data.get("name"),
                "total_amount": inv_data.get("outstanding_amount", 0),
                "outstanding_amount": inv_data.get("outstanding_amount", 0),
                "allocated_amount": inv_data.get("allocated_amount", 0),
            })
    else:
        invoices = frappe.db.sql("""
            SELECT name, COALESCE(outstanding_amount, 0) AS outstanding
            FROM `tabSales Invoice`
            WHERE customer = %s AND company = %s AND docstatus = 1 AND outstanding_amount > 0
            ORDER BY posting_date ASC, name ASC
        """, (pe.party, company), as_dict=True)

        remaining = flt(pe.paid_amount)
        for inv in invoices:
            alloc = min(remaining, inv.outstanding)
            if alloc <= 0:
                continue
            pe.append("references", {
                "reference_doctype": "Sales Invoice",
                "reference_name": inv.name,
                "total_amount": alloc,
                "outstanding_amount": inv.outstanding,
                "allocated_amount": alloc,
            })
            remaining -= alloc
            if remaining <= 0:
                break

    has_refs = len(pe.get("references", [])) > 0

    pe.save(ignore_permissions=False)
    if has_refs:
        pe.submit()

    return {"name": pe.name, "party": pe.party, "paid_amount": pe.paid_amount, "submitted": has_refs}


@frappe.whitelist(allow_guest=False)
def get_scheduled_visits():
    """Fetch Field Visit Plans assigned to the logged-in user (via sales_person or employee)."""
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else ""
    
    filters = [["status", "not in", ["Cancelled"]]]
    if employee:
        filters.append(["employee", "=", employee])
    if sales_person:
        filters.append(["sales_person", "=", sales_person])
    if not employee and not sales_person:
        filters.append(["assigned_by", "=", user])
    
    plans = frappe.get_all(
        "Field Visit Plan",
        filters=filters,
        fields=[
            "name", "plan_date", "company", "sales_person", "employee",
            "party_type", "party", "party_name",
            "customer", "lead", "opportunity", "supplier",
            "contact_mobile", "address",
            "territory", "route", "field_type",
            "priority", "planned_start_time", "planned_end_time",
            "visit_purpose", "status", "actual_field_visit",
            "assigned_by", "assigned_on", "remarks",
        ],
        order_by="planned_start_time asc",
    )
    return plans


@frappe.whitelist(allow_guest=False)
def get_today_scheduled_visits():
    """Fetch today's Field Visit Plans assigned to the logged-in user."""
    user = frappe.session.user
    today = frappe.utils.today()
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    sales_person = ""
    if employee:
        sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
    
    plans = frappe.get_all(
        "Field Visit Plan",
        filters=[
            ["plan_date", "=", today],
            ["status", "not in", ["Cancelled", "Completed"]],
        ],
        fields=[
            "name", "plan_date", "company", "sales_person", "employee",
            "party_type", "party", "party_name",
            "customer", "lead", "opportunity", "supplier",
            "contact_mobile", "address",
            "territory", "route", "field_type",
            "priority", "planned_start_time", "planned_end_time",
            "visit_purpose", "status", "actual_field_visit",
            "assigned_by", "assigned_on", "remarks",
        ],
        order_by="planned_start_time asc",
        limit_page_length=100,
    )

    # Post-filter: plan belongs to user if employee matches, sales_person matches, or assigned_by matches
    def _is_assigned(plan):
        if employee and plan.get("employee") == employee:
            return True
        if sales_person and plan.get("sales_person") == sales_person:
            return True
        if plan.get("assigned_by") == user:
            return True
        return False

    return [p for p in plans if _is_assigned(p)]


@frappe.whitelist(allow_guest=False)
def create_field_visit_from_plan():
    """Create a Field Visit from a Field Visit Plan, then update the plan status."""
    data = json.loads(frappe.request.data or "{}")
    plan_name = data.get("plan_name")
    if not plan_name:
        frappe.throw(_("plan_name is required"))
    
    plan = frappe.get_doc("Field Visit Plan", plan_name)
    
    visit = frappe.new_doc("Field Visit")
    visit.party_type = plan.party_type
    visit.party = plan.party
    visit.party_name = plan.party_name
    visit.customer = plan.customer
    visit.lead = plan.lead
    visit.opportunity = plan.opportunity
    visit.supplier = plan.supplier
    visit.contact_mobile = plan.contact_mobile
    visit.address = plan.address
    visit.territory = plan.territory
    visit.field_type = plan.field_type or data.get("visit_type", "Scheduled Visit")
    visit.sales_person = plan.sales_person
    visit.employee = plan.employee
    visit.visit_status = "Checked In"
    visit.visit_purpose = plan.visit_purpose
    visit.remarks = data.get("remarks", "")
    visit.check_in_latitude = data.get("gps_latitude") or data.get("check_in_latitude")
    visit.check_in_longitude = data.get("gps_longitude") or data.get("check_in_longitude")
    visit.check_in_time = data.get("check_in_time") or frappe.utils.now()
    visit.check_in_address = data.get("check_in_address", "")
    visit.field_visit_plan = plan_name
    visit.created_from_mobile = 1
    visit.offline_record_id = data.get("offline_record_id", "")
    visit.sync_status = "Synced"
    
    visit.insert(ignore_permissions=False)
    
    plan.db_set("status", "In Progress")
    plan.db_set("actual_field_visit", visit.name)
    
    return {"name": visit.name, "plan_name": plan_name, "party_type": visit.party_type, "party": visit.party, "party_name": visit.party_name}


@frappe.whitelist(allow_guest=False)
def update_field_visit_plan_status():
    """Update status of a Field Visit Plan."""
    data = json.loads(frappe.request.data or "{}")
    plan_name = data.get("plan_name")
    if not plan_name:
        frappe.throw(_("plan_name is required"))
    new_status = data.get("status", "Completed")
    actual_visit = data.get("actual_field_visit")
    
    plan = frappe.get_doc("Field Visit Plan", plan_name)
    plan.db_set("status", new_status)
    if actual_visit:
        plan.db_set("actual_field_visit", actual_visit)
    
    return {"name": plan_name, "status": new_status}


@frappe.whitelist(allow_guest=False)
def reschedule_field_visit_plan():
    """Reschedule a Field Visit Plan to a new date."""
    data = json.loads(frappe.request.data or "{}")
    plan_name = data.get("plan_name")
    if not plan_name:
        frappe.throw(_("plan_name is required"))
    new_date = data.get("new_date")
    new_start_time = data.get("new_start_time")
    new_end_time = data.get("new_end_time")
    
    plan = frappe.get_doc("Field Visit Plan", plan_name)
    if new_date:
        plan.db_set("plan_date", new_date)
    if new_start_time:
        plan.db_set("planned_start_time", new_start_time)
    if new_end_time:
        plan.db_set("planned_end_time", new_end_time)
    plan.db_set("status", "Rescheduled")
    
    return {"name": plan_name, "plan_date": new_date or plan.plan_date}


@frappe.whitelist(allow_guest=False)
def mark_visit_plan_missed():
    """Mark a Field Visit Plan as Missed."""
    data = json.loads(frappe.request.data or "{}")
    plan_name = data.get("plan_name")
    if not plan_name:
        frappe.throw(_("plan_name is required"))
    remarks = data.get("remarks", "")
    
    plan = frappe.get_doc("Field Visit Plan", plan_name)
    plan.db_set("status", "Missed")
    if remarks:
        plan.db_set("remarks", remarks)
    
    return {"name": plan_name, "status": "Missed"}


@frappe.whitelist(allow_guest=False)
def get_territories():
    territories = frappe.get_all(
        "Territory",
        filters=[["is_group", "=", 0]],
        fields=["name", "territory_name"],
        order_by="name asc",
    )
    return territories


@frappe.whitelist(allow_guest=False)
def get_customer_groups():
    groups = frappe.get_all(
        "Customer Group",
        filters=[["is_group", "=", 0]],
        fields=["name", "customer_group_name"],
        order_by="name asc",
    )
    return groups


@frappe.whitelist(allow_guest=False)
def _get_user_info_dict(user):
    """Return enriched user info dict used by login() and get_user_info()."""
    user_doc = frappe.get_doc("User", user)
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    company = ""
    default_currency = ""
    try:
        settings = frappe.get_single("FieldForce Settings")
        company = settings.get("mobile_company") or ""
        default_currency = settings.get("mobile_currency") or ""
    except Exception:
        pass

    if not company and employee:
        company = frappe.db.get_value("Employee", employee, "company") or ""
    if not company:
        company = frappe.defaults.get_user_default("company") or ""
    if not company:
        company = (
            frappe.get_list("Company", limit=1, pluck="name")[0]
            if frappe.get_list("Company", limit=1)
            else ""
        )
    if not default_currency and company:
        default_currency = frappe.db.get_value("Company", company, "default_currency") or ""
    if not default_currency:
        default_currency = frappe.defaults.get_user_default("currency") or ""

    return {
        "full_name": user_doc.full_name or user,
        "username": user,
        "email": user_doc.email or "",
        "mobile_no": user_doc.mobile_no or "",
        "employee": employee or "",
        "company": company,
        "default_currency": default_currency or "USD",
        "user_image": _resolve_image(user_doc.user_image or ""),
    }


@frappe.whitelist(allow_guest=False)
def get_doctype_schema():
    """Return field definitions (fieldname, label, reqd, fieldtype, options) for any DocType."""
    data = json.loads(frappe.request.data or "{}")
    doctype = data.get("doctype")
    if not doctype:
        frappe.throw(_("doctype parameter is required"))
    meta = frappe.get_meta(doctype)
    fields = []
    for df in meta.fields:
        fields.append({
            "fieldname": df.fieldname,
            "label": df.label,
            "reqd": df.reqd or 0,
            "fieldtype": df.fieldtype,
            "options": df.options or "",
        })
    return {
        "doctype": doctype,
        "fields": fields,
    }


@frappe.whitelist(allow_guest=False)
def get_mobile_config():
    """Return mobile configuration from FieldForce Settings."""
    try:
        settings = frappe.get_single("FieldForce Settings")
        return {
            "mobile_company": settings.mobile_company or "",
            "mobile_currency": settings.mobile_currency or "USD",
            "allow_offline_mode": settings.allow_offline_mode or 1,
            "enable_gps_tracking": settings.enable_gps_tracking or 1,
            "sync_interval_minutes": settings.sync_interval_minutes or 15,
            "max_image_size_mb": settings.max_image_size_mb or 5,
        }
    except Exception:
        return {
            "mobile_company": "",
            "mobile_currency": "USD",
            "allow_offline_mode": 1,
            "enable_gps_tracking": 1,
            "sync_interval_minutes": 15,
            "max_image_size_mb": 5,
        }


@frappe.whitelist(allow_guest=False)
def get_user_info():
    return _get_user_info_dict(frappe.session.user)


def _get_sales_person_for_user(user=None):
    """Map user -> Employee -> Sales Person using standard DocTypes."""
    user = user or frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    sales_person = ""
    if employee:
        sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
    return sales_person or ""


@frappe.whitelist(allow_guest=False)
def get_sales_person_mapping():
    user = frappe.session.user
    sales_person = _get_sales_person_for_user(user)
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    return {
        "user": user,
        "employee": employee or "",
        "sales_person": sales_person or "",
    }


@frappe.whitelist(allow_guest=False)
def get_leads(limit=100):
    leads = frappe.get_all(
        "Lead",
        filters=[["status", "!=", "Converted"]],
        fields=[
            "name", "lead_name", "company_name", "status",
            "mobile_no", "email_id", "territory", "source",
            "website", "industry", "address", "city", "state",
        ],
        limit_page_length=limit,
        order_by="lead_name asc",
    )
    return leads


@frappe.whitelist(allow_guest=False)
def get_opportunities(limit=100):
    opportunities = frappe.get_all(
        "Opportunity",
        filters=[["status", "not in", ["Lost", "Closed"]]],
        fields=[
            "name", "opportunity_from", "party_name", "customer_name",
            "status", "opportunity_type", "amount", "probability",
            "expected_closing", "territory", "source", "contact_email", "contact_mobile",
        ],
        limit_page_length=limit,
        order_by="creation desc",
    )
    return opportunities


@frappe.whitelist(allow_guest=False)
def get_suppliers(limit=100):
    suppliers = frappe.get_all(
        "Supplier",
        filters=[["disabled", "=", 0]],
        fields=[
            "name", "supplier_name", "supplier_group",
            "mobile_no", "email_id", "territory",
        ],
        limit_page_length=limit,
        order_by="supplier_name asc",
    )
    return suppliers


@frappe.whitelist(allow_guest=False)
def get_visit_targets(limit=100):
    """Fetch all possible visit targets: Customers, Leads, Opportunities, Prospects, Suppliers."""
    customers = frappe.get_all(
        "Customer",
        filters=[["disabled", "=", 0]],
        fields=["name", "customer_name", "territory", "mobile_no", "email_id"],
        limit_page_length=limit,
    )
    leads = frappe.get_all(
        "Lead",
        filters=[["status", "!=", "Converted"]],
        fields=["name", "lead_name", "territory", "mobile_no", "email_id"],
        limit_page_length=limit,
    )
    opportunities = frappe.get_all(
        "Opportunity",
        filters=[["status", "not in", ["Lost", "Closed"]]],
        fields=["name", "party_name", "territory", "contact_mobile", "contact_email"],
        limit_page_length=limit,
    )
    suppliers = frappe.get_all(
        "Supplier",
        filters=[["disabled", "=", 0]],
        fields=["name", "supplier_name", "territory", "mobile_no", "email_id"],
        limit_page_length=limit,
    )
    return {
        "customers": [
            {
                "party_type": "Customer",
                "party": c["name"],
                "party_name": c.get("customer_name") or c["name"],
                "territory": c.get("territory", ""),
                "mobile_no": c.get("mobile_no", ""),
                "email_id": c.get("email_id", ""),
            }
            for c in customers
        ],
        "leads": [
            {
                "party_type": "Lead",
                "party": l["name"],
                "party_name": l.get("lead_name") or l["name"],
                "territory": l.get("territory", ""),
                "mobile_no": l.get("mobile_no", ""),
                "email_id": l.get("email_id", ""),
            }
            for l in leads
        ],
        "opportunities": [
            {
                "party_type": "Opportunity",
                "party": o["name"],
                "party_name": o.get("party_name") or o["name"],
                "territory": o.get("territory", ""),
                "mobile_no": o.get("contact_mobile", ""),
                "email_id": o.get("contact_email", ""),
            }
            for o in opportunities
        ],
        "suppliers": [
            {
                "party_type": "Supplier",
                "party": s["name"],
                "party_name": s.get("supplier_name") or s["name"],
                "territory": s.get("territory", ""),
                "mobile_no": s.get("mobile_no", ""),
                "email_id": s.get("email_id", ""),
            }
            for s in suppliers
        ],
        "prospects": [],
    }


@frappe.whitelist(allow_guest=False)
def get_outstanding_amount(customer, company=None):
    if not company:
        company = frappe.defaults.get_user_default("company")
    if not company:
        company = (
            frappe.get_list("Company", limit=1, pluck="name")[0]
            if frappe.get_list("Company", limit=1)
            else None
        )
    if not company:
        return {"outstanding_amount": 0, "credit_limit": 0}
    outstanding = _get_net_outstanding(customer, company)
    credit_limit = frappe.db.get_value(
        "Customer Credit Limit",
        {"parent": customer, "company": company},
        "credit_limit"
    ) or 0
    return {"outstanding_amount": outstanding, "credit_limit": credit_limit}


@frappe.whitelist(allow_guest=False)
def get_outstanding_invoices(customer, company=None):
    if not company:
        company = frappe.defaults.get_user_default("company")
    if not company:
        company = (
            frappe.get_list("Company", limit=1, pluck="name")[0]
            if frappe.get_list("Company", limit=1)
            else None
        )
    if not company:
        return []
    invoices = frappe.db.sql("""
        SELECT
            name,
            posting_date,
            COALESCE(outstanding_amount, 0) AS outstanding_amount,
            COALESCE(grand_total, 0) AS grand_total
        FROM `tabSales Invoice`
        WHERE customer = %s AND company = %s AND docstatus = 1 AND outstanding_amount > 0
        ORDER BY posting_date ASC, name ASC
    """, (customer, company), as_dict=True)
    return invoices


@frappe.whitelist(allow_guest=False)
def get_sync_updates():
    """Pull changes from server since last_sync timestamp for two-way sync."""
    data = json.loads(frappe.request.data or "{}")
    since = data.get("since") or frappe.utils.add_days(frappe.utils.now(), -7)
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else ""

    sync_filters = [["modified", ">=", since]]
    plan_filters = [["modified", ">=", since]]
    if employee:
        sync_filters.append(["employee", "=", employee])
        plan_filters.append(["employee", "=", employee])
    if sales_person:
        sync_filters.append(["sales_person", "=", sales_person])
        plan_filters.append(["sales_person", "=", sales_person])

    visits = frappe.get_all(
        "Field Visit",
        filters=sync_filters,
        fields=[
            "name", "party_type", "party", "party_name",
            "customer", "lead", "opportunity", "supplier",
            "contact_person", "contact_mobile", "address", "territory",
            "field_type", "sales_person", "employee", "user",
            "field_visit_plan", "visit_status", "visit_purpose",
            "visit_outcome", "remarks", "next_follow_up_date",
            "check_in_latitude", "check_in_longitude", "check_in_time", "check_in_address",
            "check_out_latitude", "check_out_longitude", "check_out_time", "check_out_address",
            "created_from_mobile", "offline_record_id", "sync_status",
            "creation", "modified",
        ],
        order_by="modified desc",
        limit_page_length=100,
    )

    plans = frappe.get_all(
        "Field Visit Plan",
        filters=plan_filters + [["status", "not in", ["Cancelled"]]],
        fields=[
            "name", "plan_date", "company", "sales_person", "employee",
            "party_type", "party", "party_name",
            "customer", "lead", "opportunity", "supplier",
            "contact_mobile", "address", "territory", "route",
            "field_type", "priority", "planned_start_time", "planned_end_time",
            "visit_purpose", "status", "actual_field_visit",
            "assigned_by", "assigned_on", "remarks",
            "creation", "modified",
        ],
        order_by="modified desc",
        limit_page_length=100,
    )

    return {
        "visits": visits,
        "plans": plans,
        "server_time": frappe.utils.now(),
    }


@frappe.whitelist(allow_guest=False)
def get_private_file():
    """Return private file content as a data URI for mobile consumption."""
    data = json.loads(frappe.request.data or "{}")
    file_url = data.get("file_url")
    if not file_url:
        frappe.throw(_("file_url is required"))
    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not file_name:
        file_name = frappe.db.get_value("File", {"file_url": file_url.lstrip("/")}, "name")
    if not file_name:
        frappe.throw(_("File not found for URL: {0}").format(file_url))
    file_doc = frappe.get_doc("File", file_name)
    raw = file_doc.get_content()
    import base64
    if isinstance(raw, str):
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    else:
        encoded = base64.b64encode(raw).decode("utf-8")
    content_type = file_doc.get("content_type") or "image/png"
    return {
        "data_uri": f"data:{content_type};base64,{encoded}",
        "file_name": file_doc.file_name,
    }


@frappe.whitelist(allow_guest=False)
def get_modes_of_payment():
    modes = frappe.get_all("Mode of Payment", fields=["name"], order_by="name asc")
    return [m["name"] for m in modes]


@frappe.whitelist(allow_guest=False)
def ping():
    return {"message": "pong", "user": frappe.session.user}
