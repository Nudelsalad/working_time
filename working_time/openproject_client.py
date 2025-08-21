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
			error_text = json.loads(response.text)
			error_message = (
				error_text.get("errorMessage")
				or (error_text.get("errorMessages") or [None])[0]
				or error_text.get("message")
				or "Something went wrong."
			)

			frappe.throw(f"{url}: {_(error_message)}")

		return response.json()

	def get_work_package_summary(self, key: str) -> str:
		url = f"{self.url}/api/v3/work_packages/{key}"
		params = {}

		response = self.get(url, params=params)
		return response.get("subject", "")
