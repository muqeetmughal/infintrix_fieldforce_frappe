// Copyright (c) 2026, muqeetmughal786@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Field Visit Plan", {
	refresh(frm) {
		if (frm.doc.status === "In Progress" && frm.doc.actual_field_visit) {
			frm.add_custom_button(__("View Field Visit"), function () {
				frappe.set_route("Form", "Field Visit", frm.doc.actual_field_visit);
			});
		}
		toggle_party_fields(frm);
	},
	party_type(frm) {
		frm.set_value("party", "");
		frm.set_value("party_name", "");
		frm.set_value("customer", "");
		frm.set_value("lead", "");
		frm.set_value("opportunity", "");
		frm.set_value("supplier", "");
		frm.set_value("contact_mobile", "");
		frm.set_value("address", "");
		toggle_party_fields(frm);
	},
});

function toggle_party_fields(frm) {
	const party_type = frm.doc.party_type;
	const has_doctype = ["Customer", "Lead", "Opportunity", "Supplier"].includes(party_type);

	["customer", "lead", "opportunity", "supplier"].forEach((f) => frm.toggle_display(f, false));
	frm.toggle_display("party", has_doctype);
	frm.toggle_display("party_name", !has_doctype);
}
