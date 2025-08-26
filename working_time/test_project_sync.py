# Copyright (c) 2023, ALYF GmbH and Contributors
# See license.txt

import unittest
import frappe
from unittest.mock import patch, MagicMock
from working_time.project_sync import fetch_and_create_timesheets, find_employee_by_openproject_user


class TestProjectSync(unittest.TestCase):
	def setUp(self):
		# Create test data
		self.test_project = frappe.get_doc({
			"doctype": "Project",
			"project_name": "Test OpenProject Sync",
			"openproject_site": "test.openproject.com",
			"openproject_id": "123"
		})
		
		# Mock OpenProject Site
		if not frappe.db.exists("OpenProject Site", "test.openproject.com"):
			openproject_site = frappe.get_doc({
				"doctype": "OpenProject Site",
				"site_name": "test.openproject.com",
				"username": "test_user",
				"api_token": "test_token"
			})
			openproject_site.insert(ignore_permissions=True)
	
	def tearDown(self):
		# Clean up test data
		frappe.db.rollback()
	
	@patch('working_time.openproject_client.OpenProjectClient.fetch_time_entries')
	@patch('working_time.project_sync.find_employee_by_openproject_user')
	def test_fetch_and_create_timesheets_success(self, mock_find_employee, mock_fetch_entries):
		"""Test successful fetching and creation of timesheets."""
		
		# Mock the API response
		mock_fetch_entries.return_value = [
			{
				"id": "1001",
				"hours": "2.5",
				"spentOn": "2023-12-01",
				"comment": "Test work",
				"_links": {
					"workPackage": {"href": "/api/v3/work_packages/456"},
					"user": {"href": "/api/v3/users/789"},
					"activity": {"title": "Development"}
				}
			}
		]
		
		# Mock employee lookup
		mock_find_employee.return_value = "TEST-EMP-001"
		
		# Create test project
		self.test_project.insert(ignore_permissions=True)
		
		# Test the function
		result = fetch_and_create_timesheets(self.test_project.name)
		
		# Assertions
		self.assertIsInstance(result, list)
		mock_fetch_entries.assert_called_once_with("123")
		mock_find_employee.assert_called_once_with("789", "test.openproject.com")
	
	@patch('working_time.openproject_client.OpenProjectClient.get')
	def test_find_employee_by_openproject_user(self, mock_get):
		"""Test finding employee by OpenProject user."""
		
		# Mock API response
		mock_get.return_value = {
			"email": "test@example.com",
			"name": "Test User"
		}
		
		# Create test employee
		if not frappe.db.exists("Employee", {"user_id": "test@example.com"}):
			employee = frappe.get_doc({
				"doctype": "Employee",
				"employee_name": "Test Employee",
				"user_id": "test@example.com"
			})
			employee.insert(ignore_permissions=True)
		
		# Test the function
		result = find_employee_by_openproject_user("789", "test.openproject.com")
		
		# The function should find the employee
		self.assertIsNotNone(result)
	
	def test_fetch_without_openproject_site(self):
		"""Test error when OpenProject site is not configured."""
		
		# Create project without OpenProject site
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": "Test Project No Site"
		})
		project.insert(ignore_permissions=True)
		
		# Should raise an error
		with self.assertRaises(frappe.exceptions.ValidationError):
			fetch_and_create_timesheets(project.name)
	
	def test_fetch_without_openproject_id(self):
		"""Test error when OpenProject ID is not configured."""
		
		# Create project without OpenProject ID
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": "Test Project No ID",
			"openproject_site": "test.openproject.com"
		})
		project.insert(ignore_permissions=True)
		
		# Should raise an error
		with self.assertRaises(frappe.exceptions.ValidationError):
			fetch_and_create_timesheets(project.name)