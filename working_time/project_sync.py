# Copyright (c) 2023, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, flt
from working_time.openproject_client import OpenProjectClient
from working_time.openproject_utils import get_description, get_openproject_work_package_url


@frappe.whitelist()
def fetch_and_create_timesheets(project_name):
	"""Fetch time entries from OpenProject and create timesheets in ERPNext."""
	# Check permissions - user should have read access to the project
	project = frappe.get_doc("Project", project_name)
	
	# Ensure user has permission to read this project
	project.check_permission("read")
	
	if not project.openproject_site:
		frappe.throw(_("OpenProject Site is not configured for this project"))
	
	if not project.openproject_id:
		frappe.throw(_("OpenProject Project ID is not configured for this project"))
	
	# Initialize OpenProject client
	client = OpenProjectClient(project.openproject_site)
	
	# Fetch time entries from OpenProject
	time_entries = client.fetch_time_entries(project.openproject_id)
	
	if not time_entries:
		frappe.msgprint(_("No time entries found for this project"))
		return
	
	created_timesheets = []
	
	for entry in time_entries:
		# Check if timesheet already exists for this time entry
		existing_timesheet = frappe.db.exists("Timesheet", {
			"openproject_time_entry_id": entry.get("id")
		})
		
		if existing_timesheet:
			continue
		
		# Extract data from time entry
		hours = flt(entry.get("hours", 0))
		spent_on = getdate(entry.get("spentOn"))
		comment = entry.get("comment", "")
		activity = entry.get("_links", {}).get("activity", {}).get("title", "Default")
		
		# Get work package info
		work_package_href = entry.get("_links", {}).get("workPackage", {}).get("href", "")
		work_package_id = work_package_href.split("/")[-1] if work_package_href else ""
		
		# Get user info
		user_href = entry.get("_links", {}).get("user", {}).get("href", "")
		user_id = user_href.split("/")[-1] if user_href else ""
		
		# Try to find corresponding employee in ERPNext
		employee = find_employee_by_openproject_user(user_id, project.openproject_site)
		
		if not employee:
			frappe.log_error(f"Could not find employee for OpenProject user {user_id}")
			continue
		
		# Get billing and costing rates
		billing_rate = project.billing_rate or 0
		
		# Get costing rate for employee (similar to existing pattern)
		costing_rate = 0
		try:
			from erpnext.projects.doctype.timesheet.timesheet import get_costing_rate
			costing_rate = get_costing_rate(employee)
		except ImportError:
			# Fallback if function not available
			costing_rate = billing_rate
		
		# Create timesheet
		timesheet = frappe.get_doc({
			"doctype": "Timesheet",
			"employee": employee,
			"customer": project.customer,
			"parent_project": project_name,
			"openproject_time_entry_id": entry.get("id"),
			"time_logs": [{
				"activity_type": activity,
				"project": project_name,
				"hours": hours,
				"from_time": spent_on,
				"is_billable": 1 if hours > 0 and billing_rate > 0 else 0,
				"billing_hours": hours if hours > 0 and billing_rate > 0 else 0,
				"billing_rate": billing_rate,
				"base_billing_rate": billing_rate,
				"costing_rate": costing_rate,
				"base_costing_rate": costing_rate,
				"description": get_description(project.openproject_site, work_package_id, comment),
				"openproject_work_package_url": get_openproject_work_package_url(project.openproject_site, work_package_id),
			}]
		})
		
		try:
			timesheet.insert()
			created_timesheets.append(timesheet.name)
		except Exception as e:
			frappe.log_error(f"Failed to create timesheet: {str(e)}")
			continue
	
	if created_timesheets:
		frappe.msgprint(_("Created {0} timesheets: {1}").format(
			len(created_timesheets), 
			", ".join(created_timesheets)
		))
	else:
		frappe.msgprint(_("No new timesheets were created"))
	
	return created_timesheets


def find_employee_by_openproject_user(openproject_user_id, openproject_site):
	"""Find ERPNext employee corresponding to OpenProject user."""
	# For now, we'll use a simple mapping based on user email or custom field
	# This could be enhanced with a mapping table
	
	# Try to get user details from OpenProject
	try:
		client = OpenProjectClient(openproject_site)
		user_url = f"{client.url}/api/v3/users/{openproject_user_id}"
		user_data = client.get(user_url)
		user_email = user_data.get("email")
		
		if user_email:
			# Find employee by email
			employee = frappe.db.get_value("Employee", {"user_id": user_email}, "name")
			if employee:
				return employee
				
			# Try by personal email
			employee = frappe.db.get_value("Employee", {"personal_email": user_email}, "name")
			if employee:
				return employee
				
		# If no email match, try by name (fallback)
		user_name = user_data.get("name")
		if user_name:
			employee = frappe.db.get_value("Employee", {"employee_name": user_name}, "name")
			if employee:
				return employee
				
	except Exception as e:
		frappe.log_error(f"Failed to fetch OpenProject user {openproject_user_id}: {str(e)}")
	
	return None