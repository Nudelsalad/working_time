import frappe


def execute():
	for name in frappe.get_all(
		"Freelancer Time",
		filters={"total_duration": ("is", "not set"), "docstatus": 1},
		pluck="name",
	):
		doc = frappe.get_doc("Freelancer Time", name)
		doc.db_set("total_duration", sum(log.duration for log in doc.time_logs))
