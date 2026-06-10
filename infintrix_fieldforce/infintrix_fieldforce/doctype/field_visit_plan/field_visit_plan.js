// Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Field Visit Plan", {
	refresh(frm) {
		if (frm.doc.status === "In Progress" && frm.doc.actual_field_visit) {
			frm.add_custom_button(__("View Field Visit"), function () {
				frappe.set_route("Form", "Field Visit", frm.doc.actual_field_visit);
			});
		}
		if (frm.doc.party_type === "Customer" && frm.doc.party) {
			frm.add_custom_button(__("View Ledger"), function () {
				frappe.route_options = {
					party_type: "Customer",
					party: [frm.doc.party],
					from_date: frappe.datetime.month_start(),
					to_date: frappe.datetime.nowdate(),
				};
				frappe.set_route("query-report", "General Ledger");
			});
		}
		toggle_party_fields(frm);
	},
	party_type(frm) {
		frm.set_value("party", "");
		frm.set_value("party_name", "");
		frm.set_value("contact_mobile", "");
		frm.set_value("address", "");
		toggle_party_fields(frm);
	},
});

function toggle_party_fields(frm) {
	const has_doctype = ["Customer", "Lead", "Opportunity", "Supplier"].includes(frm.doc.party_type);
	frm.toggle_display("party", has_doctype);
	frm.toggle_display("party_name", !has_doctype);
}
