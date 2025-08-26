# Copyright (c) 2025, Contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


def _project_settings(project: str) -> Tuple[str, str, Optional[str]]:
    site, op_project_id, default_employee = frappe.get_value(
        'Project', project, ['openproject_site', 'openproject_project_id', 'openproject_default_employee']
    )
    if not site:
        frappe.throw(_('Please set OpenProject Site on Project'))
    if not op_project_id:
        frappe.throw(_('Please set OpenProject Project ID on Project'))
    return site, op_project_id, default_employee


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
        p['offset'] = page
        data = client.get(url, params=p)
        elements = (data.get('_embedded') or {}).get('elements') or []
        for e in elements:
            yield e
        total = data.get('total', 0)
        count = len(elements)
        if page * page_size >= total or count == 0:
            break
        page += 1


def _work_package_to_task_fields(project: str, site: str, wp: Dict[str, Any]) -> Dict[str, Any]:
    subject = wp.get('subject')
    wp_id = wp.get('id')
    status = ((wp.get('_embedded') or {}).get('status') or {}).get('name')
    description = (wp.get('description') or {}).get('raw', '')
    start_date = wp.get('startDate')
    due_date = wp.get('dueDate')
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
    elif s in {'on hold', 'blocked', 'review'}:
        erp_status = 'Pending Review'
    return {
        'doctype': 'Task',
        'project': project,
        'subject': subject or f'OP #{wp_id}',
        'status': erp_status,
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
def sync_project_from_openproject(project_name: str) -> Dict[str, Any]:
    """Fetch work packages and time entries for a Project from OpenProject and upsert in ERPNext.

    - Creates/updates Tasks mapped from work packages.
    - Creates Timesheets from time entries (if not already mirrored), linked to Task when possible.
    """
    site, op_project_id, default_employee = _project_settings(project_name)
    client = _client(site)

    # 1) Work packages -> Tasks
    wp_url = f"{client.url}/api/v3/work_packages"
    wp_filters = {
        'filters': json.dumps([
            { 'project': { 'operator': '=', 'values': [str(op_project_id)] } }
        ])
    }

    created_tasks = 0
    updated_tasks = 0
    task_map: Dict[str, str] = {}

    for wp in _iter_paginated(client, wp_url, wp_filters):
        wp_id = wp.get('id')
        existing = _find_existing_task(project_name, wp_id)
        fields = _work_package_to_task_fields(project_name, site, wp)
        if existing:
            # Update selected fields only
            frappe.db.set_value('Task', existing, {
                'subject': fields['subject'],
                'status': fields['status'],
                'description': fields['description'],
                'exp_start_date': fields['exp_start_date'],
                'exp_end_date': fields['exp_end_date'],
                'openproject_work_package_url_task': fields['openproject_work_package_url_task'],
            })
            updated_tasks += 1
            task_map[str(wp_id)] = existing
        else:
            doc = frappe.get_doc(fields)
            doc.flags.ignore_permissions = True
            doc.insert()
            created_tasks += 1
            task_map[str(wp_id)] = doc.name

    # 2) Time entries -> Timesheet rows
    te_url = f"{client.url}/api/v3/time_entries"
    te_filters = {
        'sortBy': json.dumps([["spent_on", "asc"]]),
        'pageSize': 100,
        'filters': json.dumps([
            { 'project': { 'operator': '=', 'values': [str(op_project_id)] } }
        ])
    }

    created_ts_details = 0
    updated_ts_details = 0

    for te in _iter_paginated(client, te_url, te_filters):
        te_id = te.get('id')
        # If already imported, update the row if changed
        existing_ts_detail_name = frappe.db.exists('Timesheet Detail', {
            'openproject_time_entry_id': str(te_id)
        })

        spent_on = te.get('spentOn')  # yyyy-mm-dd
        hours = _parse_iso8601_duration_to_hours(te.get('hours'))
        comments = (te.get('comment') or {}).get('raw', '')
        activity = ((te.get('_embedded') or {}).get('activity') or {}).get('name') or 'Default'
        wp_link = ((te.get('_links') or {}).get('workPackage') or {}).get('href')
        wp_id = None
        if wp_link and wp_link.rstrip('/').split('/')[-2] == 'work_packages':
            wp_id = wp_link.rstrip('/').split('/')[-1]
        task_name = task_map.get(str(wp_id)) if wp_id else None

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
            if changed:
                # Save through parent to recalc
                parent = frappe.get_doc('Timesheet', ts_detail.parent)
                parent.flags.ignore_permissions = True
                parent.save()
                updated_ts_details += 1
            continue

        # Determine employee for new entries
        employee = default_employee
        # If no default employee, we could map OP user -> Employee via email here (future work)
        if not employee:
            # Skip creating without an employee mapping
            continue

        ts = frappe.get_doc({
            'doctype': 'Timesheet',
            'employee': employee,
            'project': project_name,
            'time_logs': [
                {
                    'activity_type': activity,
                    'from_time': f"{spent_on} 00:00:00",
                    'hours': hours,
                    'task': task_name,
                    'description': comments,
                    'openproject_time_entry_id': str(te_id),
                    'openproject_time_entry_url': f"{client.url}/time_entries/{te_id}",
                    'openproject_work_package_url': get_openproject_work_package_url(site, wp_id) if wp_id else None,
                }
            ]
        })
        ts.flags.ignore_permissions = True
        ts.insert()
        created_ts_details += 1

    frappe.db.set_value('Project', project_name, 'openproject_last_synced_at', get_datetime())

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
