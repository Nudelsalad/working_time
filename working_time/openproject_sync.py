# Copyright (c) 2025, Contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, Optional, Tuple

import frappe
from frappe import _
from frappe.utils.data import get_datetime

from .openproject_client import OpenProjectClient
from .openproject_utils import get_openproject_work_package_url


def _parse_iso8601_duration_to_hours(value: str | float | int | None) -> float:
    """Convert OpenProject duration to hours.

    OpenProject returns ISO 8601 durations like "PT1H30M". Also handle numeric inputs.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).upper()
    if not s.startswith('P'):
        # Try numeric string
        try:
            return float(s)
        except Exception:
            return 0.0
    # Very small parser for PnDTnHnMnS
    days = hours = minutes = seconds = 0
    try:
        # Split date and time
        if 'T' in s:
            date_part, time_part = s[1:].split('T', 1)
        else:
            date_part, time_part = s[1:], ''
        # Days
        if 'D' in date_part:
            d_idx = date_part.index('D')
            days = int(date_part[:d_idx] or 0)
        # Time
        tmp = time_part
        # Hours
        if 'H' in tmp:
            h_idx = tmp.index('H')
            # find start of number
            start = 0
            for i in range(h_idx - 1, -1, -1):
                if not tmp[i].isdigit():
                    start = i + 1
                    break
            hours = int(tmp[start:h_idx] or 0)
        # Minutes
        if 'M' in tmp:
            m_idx = tmp.index('M')
            start = 0
            for i in range(m_idx - 1, -1, -1):
                if not tmp[i].isdigit():
                    start = i + 1
                    break
            minutes = int(tmp[start:m_idx] or 0)
        # Seconds
        if 'S' in tmp:
            s_idx = tmp.index('S')
            start = 0
            for i in range(s_idx - 1, -1, -1):
                if not tmp[i].isdigit():
                    start = i + 1
                    break
            seconds = int(tmp[start:s_idx] or 0)
    except Exception:
        return 0.0
    return days * 24.0 + hours + minutes / 60.0 + seconds / 3600.0


def _normalize_dt_value(value: Any) -> Optional[str]:
    """Return datetime as 'YYYY-MM-DD HH:MM:SS' string.

    Accepts:
    - None -> None
    - datetime -> formatted string
    - string -> trimmed to seconds if format contains fractional seconds
    - other -> str() best-effort
    """
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(value, str):
            s = value.strip()
            # Remove fractional seconds if present (e.g., '...:SS.ssssss')
            if '.' in s:
                s = s.split('.', 1)[0]
            return s
        # Fallback: try str then truncate fractional seconds if present
        s = str(value)
        if '.' in s:
            s = s.split('.', 1)[0]
        return s
    except Exception:
        return None


def _parse_op_datetime(value: str | None) -> Optional[str]:
    """Parse OpenProject ISO8601 datetime (with trailing Z) into string acceptable by ERPNext.

    Returns an ISO-like 'YYYY-MM-DD HH:MM:SS' in system time (assuming given value is UTC).
    If parsing fails returns None.
    Note: We treat the incoming timestamp as UTC and store naive server time; if you need
    timezone-accurate handling later, adjust to convert to user timezone.
    """
    if not value:
        return None
    try:
        # Replace Z with +00:00 for fromisoformat
        v = value.replace('Z', '+00:00')
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Try to convert to system/user timezone if available
        try:
            # Frappe exposes system time zone via System Settings; best-effort
            tz_name = frappe.db.get_single_value('System Settings', 'time_zone') or 'UTC'
            local_dt = dt.astimezone(ZoneInfo(tz_name))
        except Exception:
            # Fallback: assume Europe/Berlin if not configured (legacy behavior was +2h)
            try:
                local_dt = dt.astimezone(ZoneInfo('Europe/Berlin'))
            except Exception:
                # Last resort: keep UTC
                local_dt = dt.astimezone(timezone.utc)
        # Convert to naive string (ERPNext stores naive timestamps in many places)
        return local_dt.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def _project_settings(project: str) -> Tuple[str, str]:
    site, op_project_id = frappe.get_value(
        'Project', project, ['openproject_site', 'openproject_project_id']
    )
    if not site:
        frappe.throw(_('Please set OpenProject Site on Project'))
    if not op_project_id:
        frappe.throw(_('Please set OpenProject Project ID on Project'))
    return site, op_project_id


def _client(site: str) -> OpenProjectClient:
    return OpenProjectClient(site)


def _iter_paginated(client: OpenProjectClient, url: str, params: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Yield items across OpenProject paginated API.

    Expects HAL style: _embedded["elements"], with total, count, pageSize, offset.
    """
    page = 1
    page_size = params.get('pageSize', 100)
    while True:
        p = dict(params)
        p['pageSize'] = page_size
        # OpenProject expects offset as 1-based index of the first element
        p['offset'] = (page - 1) * page_size + 1
        data = client.get(url, params=p)
        elements = (data.get('_embedded') or {}).get('elements') or []
        for e in elements:
            yield e
        total = data.get('total', 0)
        count = len(elements)
        if page * page_size >= total or count == 0:
            break
        page += 1

def _build_project_filter(op_project_id: str, use_href: bool = True, field: str = 'project', numeric_value: bool = False) -> Dict[str, Any]:
    """Build OpenProject API filter for a project.

    - field: either 'project' (expects href) or 'project_id' (expects numeric string)
    - use_href: when True, build '/api/v3/projects/<id>'
    Some OP installations require href values, others accept numeric IDs under 'project_id'.
    """
    if use_href:
        value: Any = f"/api/v3/projects/{op_project_id}"
    else:
        # Allow sending a true integer in JSON when required by some servers
        if numeric_value and str(op_project_id).isdigit():
            value = int(op_project_id)
        else:
            value = str(op_project_id)
    return {
        'filters': json.dumps([
            {
                field: {
                    'operator': '=',
                    'values': [value]
                }
            }
        ])
    }


def _extract_id_from_href(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    parts = href.rstrip('/').split('/')
    return parts[-1] if parts else None


def _extract_identifier_from_url(text: str) -> Optional[str]:
    """Extract OpenProject project identifier from a URL like https://host/projects/<identifier>.

    Returns None if not matched.
    """
    try:
        s = (text or '').strip()
        if not s:
            return None
        # ensure we only look at path
        # find '/projects/' and take the following segment
        marker = '/projects/'
        if marker not in s:
            return None
        after = s.split(marker, 1)[1]
        ident = after.split('/', 1)[0]
        return ident or None
    except Exception:
        return None


def _resolve_project_ref(client: OpenProjectClient, op_project_id: str) -> Tuple[str, str]:
    """Resolve the given project reference (id/identifier/url/href) to (numeric_id, href).

    Tries to GET /api/v3/projects/{key} where key can be numeric id or identifier.
    Falls back to returning the original string as both id and href suffix if resolution fails.
    """
    raw = (op_project_id or '').strip()
    key = raw
    # Accept full UI URL or API href
    try:
        if raw.startswith('http'):
            ident = _extract_identifier_from_url(raw)
            if ident:
                key = ident
            else:
                # try API path
                if '/api/v3/projects/' in raw:
                    key = raw.rstrip('/').split('/')[-1]
        elif raw.startswith('/'):
            if '/api/v3/projects/' in raw:
                key = raw.rstrip('/').split('/')[-1]
            elif '/projects/' in raw:
                key = raw.rstrip('/').split('/')[-1]
        # Now fetch project to canonicalize to numeric id
        data = client.get(f"{client.url}/api/v3/projects/{key}")
        pid = str(data.get('id')) if data and data.get('id') is not None else key
        href = f"/api/v3/projects/{pid}"
        return pid, href
    except Exception:
        # Fallback: best-effort
        pid = key
        href = f"/api/v3/projects/{key}"
        return pid, href


def _map_priority(op_title: Optional[str]) -> str:
    """Map OpenProject priority title to ERPNext Task.priority options.

    Defaults to 'Medium' when unknown. Handles common English and German labels.
    """
    t = (op_title or '').strip().lower()
    if not t:
        return 'Medium'
    mapping = {
        'low': 'Low',
        'lowest': 'Low',
        'niedrig': 'Low',
        'medium': 'Medium',
        'mittel': 'Medium',
        'normal': 'Medium',
        'high': 'High',
        'highest': 'High',
        'urgent': 'High',
        'dringend': 'High',
    }
    return mapping.get(t, 'Medium')


def _ensure_activity_type(name: str):
    """Create Activity Type if missing (minimal, to avoid insertion errors)."""
    if not frappe.db.exists('Activity Type', name):
        doc = frappe.get_doc({
            'doctype': 'Activity Type',
            'activity_type': name,
            'is_billable': 1,
        })
        doc.flags.ignore_permissions = True
        doc.insert()


def _get_activity_from_te(te: Dict[str, Any]) -> str:
    """Extract activity type title from time entry, fallback to 'Default'."""
    title = None
    # Newer OP returns activity under _links.activity.title
    title = (((te.get('_links') or {}).get('activity') or {}).get('title'))
    if not title:
        # Sometimes in _embedded.activity.name
        title = (((te.get('_embedded') or {}).get('activity') or {}).get('name'))
    if not title:
        title = 'Default'
    # Ensure Activity Type exists in ERPNext
    _ensure_activity_type(title)
    return title


def _get_employee_for_op_user(client: OpenProjectClient, te: Dict[str, Any]) -> Optional[str]:
    """Resolve ERPNext Employee by OpenProject user email/login from a time entry."""
    user = (te.get('_embedded') or {}).get('user')
    user_id: Optional[str] = None
    if user:
        user_id = str(user.get('id')) if user.get('id') is not None else None
    if not user_id:
        user_href = ((te.get('_links') or {}).get('user') or {}).get('href')
        user_id = _extract_id_from_href(user_href)
    if not user_id:
        return None

    # Ensure we have email/login; fetch if needed
    if not user or ('mail' not in user and 'login' not in user):
        try:
            user = client.get(f"{client.url}/api/v3/users/{user_id}")
        except Exception:
            user = user or {}

    email = user.get('mail') or user.get('email') or user.get('login') or None
    if not email:
        return None
    # Try company_email then personal_email then via linked User
    employee = frappe.db.get_value('Employee', {'company_email': email}, 'name')
    if not employee:
        employee = frappe.db.get_value('Employee', {'personal_email': email}, 'name')
    if not employee:
        user_name = frappe.db.get_value('User', {'email': email}, 'name')
        if user_name:
            employee = frappe.db.get_value('Employee', {'user_id': user_name}, 'name')
    return employee


def _work_package_to_task_fields(project: str, site: str, wp: Dict[str, Any]) -> Dict[str, Any]:
    subject = wp.get('subject')
    wp_id = wp.get('id')
    status = (
        ((wp.get('_embedded') or {}).get('status') or {}).get('name')
        or (((wp.get('_links') or {}).get('status') or {}).get('title'))
    )
    description = (wp.get('description') or {}).get('raw', '')
    start_date = wp.get('startDate')
    due_date = wp.get('dueDate')
    priority_title = (((wp.get('_links') or {}).get('priority') or {}).get('title'))
    url = get_openproject_work_package_url(site, wp_id)
    # Map OP -> ERPNext Task status
    erp_status = 'Open'
    s = (status or '').lower()
    if s in {'closed', 'done', 'resolved'}:
        erp_status = 'Completed'
    elif s in {'in progress', 'doing', 'active', 'working'}:
        erp_status = 'Working'
    elif s in {'rejected', 'cancelled', 'canceled'}:
        erp_status = 'Cancelled'
    elif s in {'on hold', 'blocked', 'review', 'in testing', 'tested', 'developed'}:
        erp_status = 'Pending Review'
    elif s in {'test failed'}:
        erp_status = 'Working'
    # 'new' and 'in specification' remain 'Open'
    return {
        'doctype': 'Task',
        'project': project,
        'subject': subject or f'OP #{wp_id}',
        'status': erp_status,
        'priority': _map_priority(priority_title),
        'description': description,
        'exp_start_date': start_date,
        'exp_end_date': due_date,
        'openproject_work_package_id': str(wp_id),
        'openproject_work_package_url_task': url,
    }


def _find_existing_task(project: str, wp_id: int | str) -> Optional[str]:
    return frappe.db.get_value('Task', {
        'project': project,
        'openproject_work_package_id': str(wp_id),
    }, 'name')


@frappe.whitelist()
def search_openproject_projects(site: str, q: str | None = None, limit: int = 100) -> Dict[str, Any]:
    """Search or resolve OpenProject Projects.

    Accepts:
    - full project URL (extracts identifier)
    - identifier (slug)
    - numeric id
    - free text (matches name/identifier contains, client-side on first page)

    Returns: { results: [ { id, name, identifier, label } ] }
    """
    client = _client(site)
    q = (q or '').strip()

    # 1) Try resolve by URL identifier
    identifier = _extract_identifier_from_url(q) if q else None
    if identifier:
        try:
            data = client.get(f"{client.url}/api/v3/projects/{identifier}")
            if data:
                return {
                    'results': [{
                        'id': str(data.get('id')),
                        'name': data.get('name'),
                        'identifier': data.get('identifier'),
                        'label': f"{data.get('name')} ({data.get('identifier')}) [#" + str(data.get('id')) + "]",
                    }]
                }
        except Exception:
            pass

    # 2) Try resolve by numeric id directly
    if q and q.isdigit():
        try:
            data = client.get(f"{client.url}/api/v3/projects/{q}")
            if data:
                return {
                    'results': [{
                        'id': str(data.get('id')),
                        'name': data.get('name'),
                        'identifier': data.get('identifier'),
                        'label': f"{data.get('name')} ({data.get('identifier')}) [#" + str(data.get('id')) + "]",
                    }]
                }
        except Exception:
            pass

    # 3) Fallback: fetch first page and filter client-side by substring
    try:
        url = f"{client.url}/api/v3/projects"
        params = { 'pageSize': max(1, min(int(limit or 50), 200)) }
        data = client.get(url, params=params)
        elements = ((data.get('_embedded') or {}).get('elements')) or []
        results = []
        ql = q.lower() if q else ''
        for p in elements:
            pid = str(p.get('id')) if p.get('id') is not None else None
            name = p.get('name')
            ident = p.get('identifier') or (
                ((p.get('_links') or {}).get('self') or {}).get('href') or ''
            ).rstrip('/').split('/')[-1]
            if ql:
                text = f"{name} {ident} {pid}".lower()
                if ql not in text:
                    continue
            if pid:
                results.append({
                    'id': pid,
                    'name': name,
                    'identifier': ident,
                    'label': f"{name} ({ident}) [#" + pid + "]",
                })
            if len(results) >= params['pageSize']:
                break
        return { 'results': results }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'OpenProject project search failed')
        return { 'results': [] }


@frappe.whitelist()
def sync_project_from_openproject(project_name: str) -> Dict[str, Any]:
    """Fetch work packages and time entries for a Project from OpenProject and upsert in ERPNext.

    - Creates/updates Tasks mapped from work packages.
    - Creates Timesheets from time entries (if not already mirrored), linked to Task when possible.
    """
    site, op_project_id = _project_settings(project_name)
    # Work Package Type: "Project" root work package id (legacy name: phase)
    # Backward compatibility: keep reading legacy field if new one not yet migrated.
    project_wp_id = (
        frappe.db.get_value('Project', project_name, 'openproject_project_work_package_id')
        or frappe.db.get_value('Project', project_name, 'openproject_phase_work_package_id')
    )
    client = _client(site)
    # Normalize project reference to numeric id and href
    numeric_pid, project_href = _resolve_project_ref(client, str(op_project_id))

    # 1) Work packages -> Tasks
    wp_url = f"{client.url}/api/v3/work_packages"
    created_tasks = 0
    updated_tasks = 0
    task_map: Dict[str, str] = {}

    # 2) Time entries -> Timesheet rows
    te_url = f"{client.url}/api/v3/time_entries"
    # Prefer integer-valued 'project' for time entries on servers that require it,
    # then try 'project_id', and finally project href.
    te_filter_strategies = [
        {
            'sortBy': json.dumps([["spent_on", "asc"]]),
            'pageSize': 100,
            **_build_project_filter(numeric_pid, use_href=False, field='project', numeric_value=True),
        },
        {
            'sortBy': json.dumps([["spent_on", "asc"]]),
            'pageSize': 100,
            **_build_project_filter(numeric_pid, use_href=False, field='project_id', numeric_value=True),
        },
        {
            'sortBy': json.dumps([["spent_on", "asc"]]),
            'pageSize': 100,
            **_build_project_filter(numeric_pid, use_href=True, field='project'),
        },
    ]
    project_descendant_ids: set[str] | None = None
    project_wp_id_str = str(project_wp_id).strip() if project_wp_id else None

    def _collect_project_descendants(all_wps: Dict[str, Dict[str, Any]]):
        """Build set of descendant WP IDs (strings) of the given root project work package id.

    NOTE: We EXCLUDE the project root itself; only descendants
        should be created as Tasks/Timesheet entries mapping.
        We rely on each WP's ancestor chain via _embedded.ancestors or _links.parent.
        """
        nonlocal project_descendant_ids
        if not project_wp_id_str:
            return
        project_descendant_ids = set()
        # Collect any WP that has project_wp_id_str in its ancestor chain.
        for wp_id, wp in all_wps.items():
            if wp_id == project_wp_id_str:
                # Explicitly skip adding root project WP itself
                continue
            ancestors: list[str] = []
            embedded = (wp.get('_embedded') or {})
            anc_list = embedded.get('ancestors') or []
            for anc in anc_list:
                a_id = str(anc.get('id')) if anc.get('id') is not None else None
                if a_id:
                    ancestors.append(a_id)
            # Fallback: follow parent chain if no explicit ancestors provided
            if not ancestors:
                current = wp
                safeguard = 0
                while safeguard < 10:
                    parent_link = ((current.get('_links') or {}).get('parent') or {}).get('href')
                    if not parent_link:
                        break
                    p_id = _extract_id_from_href(parent_link)
                    if not p_id:
                        break
                    ancestors.append(p_id)
                    if p_id in all_wps:
                        current = all_wps[p_id]
                    else:
                        break
                    safeguard += 1
                    # If we already encountered root id we can stop early
                    if project_wp_id_str in ancestors:
                        break
            if project_wp_id_str in ancestors:
                project_descendant_ids.add(wp_id)

    # Temp storage to possibly post-filter for project-root descendant restriction
    collected_wps: Dict[str, Dict[str, Any]] = {}

    def _sync_wps(filters: Dict[str, Any]):
        nonlocal created_tasks, updated_tasks, task_map
        for wp in _iter_paginated(client, wp_url, filters):
            wp_id = wp.get('id')
            if wp_id is None:
                continue
            wp_id_str = str(wp_id)
            collected_wps[wp_id_str] = wp
    # If a root project work package is specified, build descendant set after first successful fetch
        if project_wp_id_str and project_descendant_ids is None:
            _collect_project_descendants(collected_wps)
        # Now iterate over (possibly filtered) WPs for task sync
        for wp_id_str, wp in list(collected_wps.items()):
            if project_wp_id_str and project_descendant_ids is not None:
                # Skip root itself (not in descendants set) and anything not descendant
                if wp_id_str not in project_descendant_ids:
                    continue
            wp_id = wp.get('id')
            existing = _find_existing_task(project_name, wp_id)
            fields = _work_package_to_task_fields(project_name, site, wp)
            if existing:
                # Update selected fields only (guard optional custom fields)
                values = {
                    'subject': fields['subject'],
                    'status': fields['status'],
                    'priority': fields['priority'],
                    'description': fields['description'],
                    'exp_start_date': fields['exp_start_date'],
                    'exp_end_date': fields['exp_end_date'],
                    'openproject_work_package_url_task': fields['openproject_work_package_url_task'],
                }
                try:
                    values['openproject_last_synced_at'] = get_datetime()
                except Exception:
                    pass
                try:
                    frappe.db.set_value('Task', existing, values)
                except Exception:
                    # Retry without optional fields in case of missing columns
                    values.pop('openproject_work_package_url_task', None)
                    values.pop('openproject_last_synced_at', None)
                    frappe.db.set_value('Task', existing, values)
                updated_tasks += 1
                task_map[str(wp_id)] = existing
            else:
                doc = frappe.get_doc(fields)
                doc.flags.ignore_permissions = True
                doc.insert()
                try:
                    frappe.db.set_value('Task', doc.name, 'openproject_last_synced_at', get_datetime())
                except Exception:
                    pass
                created_tasks += 1
                task_map[str(wp_id)] = doc.name

    # Try multiple filter strategies
    # Prefer integer-valued filters for servers enforcing integer types
    wp_filter_strategies = [
        _build_project_filter(numeric_pid, use_href=False, field='project', numeric_value=True),
        _build_project_filter(numeric_pid, use_href=False, field='project_id', numeric_value=True),
        _build_project_filter(numeric_pid, use_href=True, field='project'),
        _build_project_filter(numeric_pid, use_href=False, field='project'),
    ]
    last_wp_error = None
    for filt in wp_filter_strategies:
        try:
            _sync_wps(filt)
            last_wp_error = None
            break
        except Exception as e:
            last_wp_error = e
            msg = str(e)
            if (
                'Project filter has invalid values' in msg
                or 'Invalid query' in msg
                or 'is not an integer' in msg
                or 'not an integer' in msg
            ):
                continue
            raise
    if last_wp_error:
        raise last_wp_error

    created_ts_details = 0
    updated_ts_details = 0
    # No cache: do direct lookup for simplicity
    def _sync_tes(filters: Dict[str, Any]):
        nonlocal created_ts_details, updated_ts_details, task_map
        for te in _iter_paginated(client, te_url, filters):
            te_id = te.get('id')
            # If already imported, update the row if changed
            existing_ts_detail_name = frappe.db.exists('Timesheet Detail', {
                'openproject_time_entry_id': str(te_id)
            })

            spent_on = te.get('spentOn')  # yyyy-mm-dd
            hours = _parse_iso8601_duration_to_hours(te.get('hours'))
            comments = (te.get('comment') or {}).get('raw', '')
            activity = _get_activity_from_te(te)
            # On-site flag from OpenProject custom field; don't change Activity Type, only store flags
            on_site_flag = bool(te.get('customField1'))
            start_time_raw = te.get('startTime')
            end_time_raw = te.get('endTime')
            start_time = _parse_op_datetime(start_time_raw)
            end_time = _parse_op_datetime(end_time_raw)
            # Fallback compute end_time from hours if start only
            if start_time and not end_time and hours:
                try:
                    dt_start = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                    delta_seconds = int(hours * 3600)
                    dt_end = dt_start + frappe.utils.time_delta(seconds=delta_seconds)
                    end_time = dt_end.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            wp_link = ((te.get('_links') or {}).get('workPackage') or {}).get('href')
            wp_id = None
            if wp_link and wp_link.rstrip('/').split('/')[-2] == 'work_packages':
                wp_id = wp_link.rstrip('/').split('/')[-1]
            task_name = task_map.get(str(wp_id)) if wp_id else None

            # If restricted to project root descendants ensure WP belongs
            if project_wp_id_str and project_descendant_ids is not None:
                if wp_id and str(wp_id) not in project_descendant_ids:
                    continue
            if existing_ts_detail_name:
                ts_detail = frappe.get_doc('Timesheet Detail', existing_ts_detail_name)
                changed = False
                if abs((ts_detail.hours or 0) - hours) > 1e-6:
                    ts_detail.hours = hours
                    changed = True
                if (ts_detail.description or '') != (comments or ''):
                    ts_detail.description = comments
                    changed = True
                if (ts_detail.activity_type or '') != activity:
                    ts_detail.activity_type = activity
                    changed = True
                if (ts_detail.task or '') != (task_name or ''):
                    ts_detail.task = task_name
                    changed = True
                new_wp_url = get_openproject_work_package_url(site, wp_id) if wp_id else None
                if (ts_detail.openproject_work_package_url or '') != (new_wp_url or ''):
                    ts_detail.openproject_work_package_url = new_wp_url
                    changed = True
                # Update on-site flag from OP customField1
                if int(ts_detail.get('technician_on_site') or 0) != int(on_site_flag):
                    ts_detail.technician_on_site = on_site_flag
                    changed = True
                # Start / end time updates
                # Only update if OpenProject provides them
                if start_time:
                    current_from = _normalize_dt_value(ts_detail.from_time)
                    if current_from != start_time:
                        ts_detail.from_time = start_time
                        changed = True
                if end_time:
                    # Ensure to_time exists; compute if not provided
                    current_to = _normalize_dt_value(ts_detail.to_time)
                    if current_to != end_time:
                        ts_detail.to_time = end_time
                        # Recalculate hours if both times available
                        try:
                            dt_from = datetime.strptime(_normalize_dt_value(ts_detail.from_time) or '', '%Y-%m-%d %H:%M:%S') if ts_detail.from_time else None
                            dt_to = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
                            if dt_from:
                                diff_hours = (dt_to - dt_from).total_seconds() / 3600.0
                                if abs(diff_hours - ts_detail.hours) > 1e-4:
                                    ts_detail.hours = diff_hours
                        except Exception:
                            pass
                if changed:
                    # Save through parent to recalc
                    parent = frappe.get_doc('Timesheet', ts_detail.parent)
                    # Set parent checkbox based on entry
                    try:
                        parent.technician_on_site = on_site_flag
                    except Exception:
                        pass
                    parent.flags.ignore_permissions = True
                    parent.save()
                    updated_ts_details += 1
                continue

            # Determine employee for new entries: map OP user -> Employee by email/login
            employee = _get_employee_for_op_user(client, te)
            if not employee:
                # Skip creating without an employee mapping
                continue

            from_time = start_time or f"{spent_on} 00:00:00"
            to_time = end_time
            # If both present and mismatch with provided hours, prefer explicit hours for now
            if start_time and end_time:
                try:
                    dt_s = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                    dt_e = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
                    computed = (dt_e - dt_s).total_seconds() / 3600.0
                    if computed > 0 and abs(computed - hours) > 1e-4:
                        # Keep hours but accept times; optionally could align hours=computed
                        pass
                except Exception:
                    pass
            elif start_time and not end_time and hours:
                try:
                    dt_s = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                    dt_e = dt_s + frappe.utils.time_delta(hours=hours)
                    to_time = dt_e.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass

            time_log = {
                'activity_type': activity,
                'from_time': from_time,
                'hours': hours,
                'task': task_name,
                'description': comments,
                'openproject_time_entry_id': str(te_id),
                'openproject_time_entry_url': f"{client.url}/time_entries/{te_id}",
                'openproject_work_package_url': get_openproject_work_package_url(site, wp_id) if wp_id else None,
                'technician_on_site': on_site_flag,
            }
            if to_time:
                time_log['to_time'] = to_time
            ts = frappe.get_doc({
                'doctype': 'Timesheet',
                'employee': employee,
                'project': project_name,
                'technician_on_site': on_site_flag,
                'time_logs': [time_log]
            })
            ts.flags.ignore_permissions = True
            ts.insert()
            created_ts_details += 1

    last_te_error = None
    for te_filters in te_filter_strategies:
        try:
            _sync_tes(te_filters)
            last_te_error = None
            break
        except Exception as e:
            last_te_error = e
            # Broaden fallback patterns for server-specific validation messages
            msg = str(e)
            if (
                'Project filter has invalid values' in msg
                or 'Invalid query' in msg
                or 'is not an integer' in msg
                or 'not an integer' in msg
            ):
                continue
            raise
    if last_te_error:
        raise last_te_error

    try:
        frappe.db.set_value('Project', project_name, 'openproject_last_synced_at', get_datetime())
    except Exception:
        pass

    return {
        'created_tasks': created_tasks,
        'updated_tasks': updated_tasks,
        'created_timesheet_rows': created_ts_details,
        'updated_timesheet_rows': updated_ts_details,
    }


def sync_all_projects_from_openproject():
    """Scheduled job: iterate over projects with OpenProject mapping and sync."""
    projects = frappe.get_all('Project', fields=['name'], filters={
        'openproject_site': ('is', 'set'),
        'openproject_project_id': ('is', 'set')
    })
    for p in projects:
        try:
            sync_project_from_openproject(p.name)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"OpenProject sync failed for Project {p.name}")


@frappe.whitelist()
def enqueue_sync_project_from_openproject(project_name: str) -> Dict[str, Any]:
    """Enqueue the project sync to avoid blocking the UI."""
    frappe.enqueue(
        'working_time.working_time.openproject_sync.sync_project_from_openproject',
        project_name=project_name,
        queue='long'
    )
    return { 'queued': True }


@frappe.whitelist()
def sync_task_from_openproject(task_name: str) -> Dict[str, Any]:
    """Refresh a single Task from its OpenProject work package."""
    task = frappe.get_doc('Task', task_name)
    project_name = task.project
    wp_id = task.get('openproject_work_package_id')
    if not project_name or not wp_id:
        frappe.throw(_('Task must have Project and OpenProject Work Package ID'))
    site, _ = _project_settings(project_name)
    client = _client(site)
    wp = client.get(f"{client.url}/api/v3/work_packages/{wp_id}")
    fields = _work_package_to_task_fields(project_name, site, wp)
    # Update selective fields
    values = {
        'subject': fields['subject'],
        'status': fields['status'],
        'priority': fields['priority'],
        'description': fields['description'],
        'exp_start_date': fields['exp_start_date'],
        'exp_end_date': fields['exp_end_date'],
        'openproject_work_package_url_task': fields['openproject_work_package_url_task'],
    }
    try:
        values['openproject_last_synced_at'] = get_datetime()
    except Exception:
        pass
    try:
        frappe.db.set_value('Task', task.name, values)
    except Exception:
        values.pop('openproject_work_package_url_task', None)
        values.pop('openproject_last_synced_at', None)
        frappe.db.set_value('Task', task.name, values)
    return { 'updated': True }


@frappe.whitelist()
def validate_openproject_mapping(project_name: str) -> Dict[str, Any]:
    """Quick check that site/token and project mapping work."""
    site, op_project_id = _project_settings(project_name)
    client = _client(site)
    # Resolve identifier/url to numeric id to confirm mapping
    pid, _ = _resolve_project_ref(client, str(op_project_id))
    data = client.get(f"{client.url}/api/v3/projects/{pid}")
    return {
        'id': data.get('id'),
        'name': data.get('name'),
        'identifier': data.get('identifier'),
    }
