import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    fields = {
        "Sales Invoice Timesheet": [
            {
                "fieldname": "technician_on_site",
                "label": "Technician on Site",
                "fieldtype": "Check",
                "insert_after": "billing_hours",
                "read_only": 1,
                "in_list_view": 1,
                "translatable": 0,
                "fetch_from": "time_sheet.technician_on_site",
            }
        ]
    }
    create_custom_fields(fields)
