# Common Outflows Added

This backend keeps the teammates' existing Leave Approval System and adds three reusable common outflows:

1. **Smart Notification** - reuses the existing Celery email task and records each queued notification in `notification_logs`.
2. **Audit Report / Workflow Record Logging** - generic `audit_logs` table and APIs for any workflow type.
3. **Document Generator** - generates a PDF completion report for any `COMPLETED` workflow event and stores its record in `documents`.

## Generic event contract

Authenticated clients can call `POST /outflows/events`:

```json
{
  "workflow_id": "LR-1001",
  "workflow_type": "leave_request",
  "event": "COMPLETED",
  "recipient_email": "employee@example.com",
  "notification_subject": "Workflow completed",
  "notification_body": "<p>Your workflow is complete.</p>",
  "data": {
    "request_id": "LR-1001",
    "status": "completed"
  },
  "previous_status": "approved",
  "new_status": "completed"
}
```

- Every event creates an audit record.
- If recipient + subject + body are supplied, a notification is queued through the existing Celery email task.
- `COMPLETED` also generates a PDF in `generated_documents/`.

## Leave workflow integration

Leave submission automatically creates a `SUBMITTED` audit event and the approval/rejection endpoint automatically creates an `APPROVED` or `REJECTED` audit event. Existing notification calls are preserved for compatibility.

## Useful endpoints

- `POST /outflows/events`
- `GET /outflows/audit/{workflow_id}`
- `GET /outflows/audit/{workflow_id}/report`
- `GET /outflows/notifications/{workflow_id}`
- `GET /outflows/documents/{document_id}`
- `GET /outflows/documents/{document_id}/download`

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Swagger: `http://127.0.0.1:8000/docs`

### Celery/Redis

The existing notification and escalation tasks still use Redis/Celery exactly as before. Start Redis and the Celery worker separately when testing actual asynchronous email delivery. Without SMTP credentials, the existing task prints an `[EMAIL MOCK]` message.
