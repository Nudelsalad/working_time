// Copyright (c) 2023, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project", {
	refresh: function(frm) {
		// Add "Fetch Time Entries" button if OpenProject is configured
		if (frm.doc.openproject_site && frm.doc.openproject_id && !frm.is_new()) {
			frm.add_custom_button(__("Fetch Time Entries"), function() {
				fetch_time_entries_from_openproject(frm);
			}, __("OpenProject"));
		}
	}
});

function fetch_time_entries_from_openproject(frm) {
	frappe.confirm(
		__("This will fetch time entries from OpenProject and create timesheets. Continue?"),
		function() {
			frappe.call({
				method: "working_time.project_sync.fetch_and_create_timesheets",
				args: {
					project_name: frm.doc.name
				},
				callback: function(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("Time entries fetched successfully"),
							indicator: "green"
						});
						frm.reload_doc();
					}
				},
				freeze: true,
				freeze_message: __("Fetching time entries from OpenProject...")
			});
		}
	);
}