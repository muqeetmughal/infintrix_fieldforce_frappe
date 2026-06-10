import frappe
from frappe import _
import json


@frappe.whitelist(allow_guest=False)
def login():
    user = frappe.session.user
    if user and user != "Guest":
        user_doc = frappe.get_doc("User", user)
        return {
            "message": "Logged in",
            "full_name": user_doc.full_name,
            "username": user,
            "email": user_doc.email,
        }
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

    company = frappe.defaults.get_user_default("company")
    for c in customers:
        outstanding = 0
        credit_limit = 0
        if company:
            result = frappe.db.sql("""
                SELECT COALESCE(SUM(outstanding_amount), 0)
                FROM `tabSales Invoice`
                WHERE customer = %s AND docstatus = 1 AND company = %s AND outstanding_amount > 0
            """, (c["name"], company))
            outstanding = result[0][0] if result else 0

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

    return customers


@frappe.whitelist(allow_guest=False)
def get_customer_detail(customer):
    customer_doc = frappe.get_doc("Customer", customer)

    currency = frappe.defaults.get_user_default("currency") or "PKR"
    company = frappe.defaults.get_user_default("company") or frappe.get_list("Company", limit=1, pluck="name")[0] if frappe.get_list("Company", limit=1) else None

    outstanding = 0
    credit_limit = 0

    if company:
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0)
            FROM `tabSales Invoice`
            WHERE customer = %s AND docstatus = 1 AND company = %s AND outstanding_amount > 0
        """, (customer, company))
        outstanding = result[0][0] if result else 0

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
        fields=["name", "visit_type", "visit_date", "remarks", "gps_latitude", "gps_longitude"],
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
        "outstanding_amount": outstanding,
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

    today_visits = frappe.db.count("Field Visit", {"visited_by": user, "visit_date": today})
    today_orders = frappe.db.count("Sales Order", {"modified_by": user, "transaction_date": today, "docstatus": 1})

    today_collections = frappe.db.sql("""
        SELECT COALESCE(SUM(paid_amount), 0)
        FROM `tabPayment Entry`
        WHERE modified_by = %s AND posting_date = %s AND docstatus = 1 AND payment_type = 'Receive'
    """, (user, today))[0][0]

    total_outstanding = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
    """)[0][0]

    return {
        "today_visits_count": today_visits,
        "today_orders_count": today_orders,
        "today_collections_amount": today_collections,
        "total_outstanding_amount": total_outstanding,
    }


@frappe.whitelist(allow_guest=False)
def submit_field_visit():
    data = json.loads(frappe.request.data or "{}")

    visit = frappe.new_doc("Field Visit")
    visit.customer = data.get("customer")
    visit.visit_type = data.get("visit_type")
    visit.status = data.get("visit_status", "Checked In")
    visit.remarks = data.get("remarks", "")
    visit.gps_latitude = data.get("gps_latitude")
    visit.gps_longitude = data.get("gps_longitude")
    visit.next_followup_date = data.get("next_followup_date")
    visit.attachment = data.get("attachment")
    visit.visited_by = frappe.session.user

    visit.insert(ignore_permissions=False)

    return {"name": visit.name, "customer": visit.customer, "visit_type": visit.visit_type}


@frappe.whitelist(allow_guest=False)
def update_field_visit():
    data = json.loads(frappe.request.data or "{}")

    visit_name = data.get("visit_name")
    if not visit_name:
        frappe.throw(_("visit_name is required"))

    visit = frappe.get_doc("Field Visit", visit_name)
    visit.status = data.get("visit_status", "Completed")
    visit.remarks = data.get("remarks") or visit.remarks
    visit.next_followup_date = data.get("next_followup_date") or visit.next_followup_date
    if data.get("check_out_latitude"):
        visit.gps_latitude = data.get("check_out_latitude")
    if data.get("check_out_longitude"):
        visit.gps_longitude = data.get("check_out_longitude")

    visit.save(ignore_permissions=False)

    return {"name": visit.name, "customer": visit.customer, "status": visit.status}


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

    company = frappe.defaults.get_user_default("company")
    if not company:
        companies = frappe.get_list("Company", limit=1, pluck="name")
        company = companies[0] if companies else None
    if not company:
        frappe.throw(_("No Company found. Please set default company."))

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

    field_visit = data.get("field_visit")
    if field_visit:
        pe.custom_field_visit = field_visit

    pe.insert(ignore_permissions=False)

    return {"name": pe.name, "party": pe.party, "paid_amount": pe.paid_amount}


@frappe.whitelist(allow_guest=False)
def get_user_info():
    user = frappe.session.user
    user_doc = frappe.get_doc("User", user)
    return {
        "full_name": user_doc.full_name or user,
        "username": user,
        "email": user_doc.email or "",
        "mobile_no": user_doc.mobile_no or "",
    }


@frappe.whitelist(allow_guest=False)
def ping():
    return {"message": "pong", "user": frappe.session.user}
