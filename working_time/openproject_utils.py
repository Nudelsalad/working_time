"""Utility helpers for OpenProject integration."""

from working_time.openproject_client import OpenProjectClient


def get_openproject_work_package_url(openproject_site: str, key):
	"""Return the canonical UI URL for a work package.

	openproject_site is the name of the "OpenProject Site" document (Link value).
	We resolve it via OpenProjectClient to ensure we use the configured site_url.
	"""
	if not key:
		return None
	client = OpenProjectClient(openproject_site)
	return f"{client.url}/work_packages/{key}"


def get_description(openproject_site, key, note):
	if key:
		description = f"{OpenProjectClient(openproject_site).get_work_package_summary(key)} ({key})"
		if note:
			description += f":\n\n{note}"
		return description.strip()
	elif note:
		return note
	else:
		return "-"
