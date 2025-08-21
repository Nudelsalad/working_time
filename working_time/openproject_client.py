# Copyright (c) 2023, ALYF GmbH and contributors
# For license information, please see license.txt


import json

import frappe
import requests
from frappe import _
from requests.auth import HTTPBasicAuth


class OpenProjectClient:
	def __init__(self, openproject_site: str) -> None:
		openproject_site = frappe.get_doc("OpenProject Site", openproject_site)

		self.url = f"https://{openproject_site.name}"
		self.session = requests.Session()
		self.session.auth = HTTPBasicAuth(
			openproject_site.username, openproject_site.get_password(fieldname="api_token")
		)
		self.session.headers = {"Accept": "application/json"}

	def get(self, url: str, params=None):
		response = self.session.get(url, params=params, verify=False)

		try:
			response.raise_for_status()
		except requests.HTTPError:
			try:
				error_text = json.loads(response.text)
				# OpenProject API error format
				error_message = (
					error_text.get("message")
					or error_text.get("errorMessage")
					or (error_text.get("errorMessages") or [None])[0]
					or "Something went wrong."
				)
			except (json.JSONDecodeError, KeyError):
				error_message = f"HTTP {response.status_code}: {response.reason}"

			frappe.throw(f"{url}: {_(error_message)}")

		return response.json()

	def get_work_package_summary(self, key: str) -> str:
		"""Get the subject/title of an OpenProject work package by its ID."""
		url = f"{self.url}/api/v3/work_packages/{key}"
		params = {}

		try:
			response = self.get(url, params=params)
			return response.get("subject", "")
		except Exception:
			# If we can't fetch the work package, just return empty string
			return ""
