from working_time.openproject_client import OpenProjectClient


def get_openproject_work_package_url(openproject_site, key):
    return f"https://{openproject_site}/work_packages/{key}" if key else None


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
