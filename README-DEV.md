Developer notes

This fork focuses on safer, clearer OpenProject integration with ERPNext Projects, Tasks, and Timesheets.

Highlights in this branch:

- OpenProjectClient URL resolution honors scheme and uses site_url, with resilient retries on 429/5xx.
- Consistent work package URL building via OpenProjectClient to avoid hard-coded host issues.
- Timezone parsing for OpenProject timestamps uses System Settings time_zone when available.
- Activity Type from OpenProject time entries is mapped/created automatically.
- Project mapping accepts numeric id, identifier (slug), or a full project URL; the UI helper in Project form can search and set it.

Behavioral compatibility:

- No existing fields were removed or renamed; new helpers only enrich data.
- Verification remains disabled (verify=False) for API GET to keep compatibility with self-hosted OP using custom certs. Consider enabling verification and configuring CA trust in production.

Manual smoke checklist (bench console or UI):

- Create OpenProject Site (site_url can be with or without https://).
- On a Project: set openproject_site and openproject_project_id (id/identifier/URL), then click OpenProject → Validate mapping → should show id/name.
- Click Sync now and verify that Tasks are created/updated for work packages; Timesheets are created/updated for time entries.
- Check that Timesheet Detail shows Work Package URL and Time Entry URL, and that Activity Type is set to the OpenProject activity (auto-created if missing).

Notes:

- If your OpenProject instance requires integer project filter values, the sync now tries multiple strategies (project, project_id, href) to handle it.
- Phase restriction: set openproject_phase_work_package_id on the Project to restrict sync to that Phase and its descendants.
