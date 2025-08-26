# OpenProject Time Entry Sync

This module provides functionality to automatically sync time entries from OpenProject to ERPNext timesheets.

## Setup

1. **Configure OpenProject Site**: Create an OpenProject Site record with your site URL, username, and API token.

2. **Configure Project**: 
   - Link your ERPNext Project to the OpenProject Site
   - Set the **OpenProject Project ID** field to the corresponding OpenProject project ID
   - Set the billing rate per hour if needed

3. **Employee Mapping**: Ensure that your ERPNext employees have email addresses that match the users in OpenProject. The sync will attempt to match employees by:
   - User ID (email)
   - Personal email
   - Employee name (fallback)

## Usage

### Manual Sync
1. Open the Project form in ERPNext
2. If the project has both OpenProject Site and OpenProject Project ID configured, you'll see a "Fetch Time Entries" button under the "OpenProject" menu
3. Click the button to fetch and create timesheets from OpenProject time entries

### What Gets Synced
- Time entries from the specified OpenProject project
- Hours logged and spent date
- Work package information (linked as OpenProject Work Package URL)
- Comments and descriptions
- User mapping to ERPNext employees

### Duplicate Prevention
The system tracks synced time entries using the `openproject_time_entry_id` field to prevent duplicate timesheet creation.

## API Endpoint Used
The sync uses the OpenProject REST API endpoint:
```
GET /api/v3/time_entries
```

With filters to get only time entries for the specific project:
```json
{
  "filters": [
    {
      "project": {
        "operator": "=",
        "values": ["PROJECT_ID"]
      }
    }
  ]
}
```

## Error Handling
- Missing OpenProject configuration will show appropriate error messages
- Failed employee mapping will log errors and skip those time entries
- API errors are logged for debugging

## Development
The main functionality is implemented in:
- `working_time/project_sync.py` - Core sync logic
- `working_time/openproject_client.py` - API client (extended)
- `working_time/public/js/project.js` - Frontend button and handling