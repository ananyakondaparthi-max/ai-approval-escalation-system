"""Common outflow services shared by all workflow types."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import AuditLog, DocumentRecord, NotificationLog
from tasks.notifications import send_email


def utcnow():
    return datetime.now(timezone.utc)


def log_audit(db: Session, *, workflow_id: str, workflow_type: str, event: str,
              actor_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
              previous_status: Optional[str] = None, new_status: Optional[str] = None):
    row = AuditLog(workflow_id=workflow_id, workflow_type=workflow_type, event=event,
                   actor_id=actor_id, previous_status=previous_status,
                   new_status=new_status, details=json.dumps(details or {}, default=str),
                   created_at=utcnow())
    db.add(row)
    return row


def queue_notification(db: Session, *, workflow_id: str, workflow_type: str,
                       event: str, to_email: str, subject: str, body: str):
    row = NotificationLog(workflow_id=workflow_id, workflow_type=workflow_type,
                          event=event, recipient=to_email, subject=subject,
                          body=body, status="queued", created_at=utcnow())
    db.add(row)
    db.flush()
    row.status = send_email(to_email, subject, body)
    return row


def generate_completion_document(db: Session, *, workflow_id: str, workflow_type: str,
                                 event: str, data: Dict[str, Any]):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    out_dir = Path("generated_documents")
    out_dir.mkdir(exist_ok=True)
    safe_id = "".join(c for c in workflow_id if c.isalnum() or c in "-_") or "workflow"
    filename = f"{safe_id}_{event.lower()}_report.pdf"
    path = out_dir / filename

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 60
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, "Workflow Completion Report")
    y -= 35
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Workflow ID: {workflow_id}")
    y -= 18
    c.drawString(50, y, f"Workflow Type: {workflow_type}")
    y -= 18
    c.drawString(50, y, f"Event: {event}")
    y -= 18
    c.drawString(50, y, f"Generated: {utcnow().isoformat()}")
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Workflow Data")
    y -= 20
    c.setFont("Helvetica", 10)
    for key, value in data.items():
        text = f"{key}: {value}"
        for chunk in [text[i:i + 95] for i in range(0, len(text), 95)]:
            if y < 55:
                c.showPage()
                y = height - 55
                c.setFont("Helvetica", 10)
            c.drawString(55, y, chunk)
            y -= 16
    c.save()

    row = DocumentRecord(workflow_id=workflow_id, workflow_type=workflow_type,
                         event=event, filename=filename, path=str(path),
                         created_at=utcnow())
    db.add(row)
    return row


def process_event(db: Session, *, workflow_id: str, workflow_type: str, event: str,
                  actor_id: Optional[str] = None, recipient_email: Optional[str] = None,
                  notification_subject: Optional[str] = None,
                  notification_body: Optional[str] = None,
                  data: Optional[Dict[str, Any]] = None,
                  previous_status: Optional[str] = None,
                  new_status: Optional[str] = None):
    data = data or {}
    audit = log_audit(db, workflow_id=workflow_id, workflow_type=workflow_type,
                      event=event, actor_id=actor_id, details=data,
                      previous_status=previous_status, new_status=new_status)

    notification = None
    if recipient_email and notification_subject and notification_body:
        notification = queue_notification(db, workflow_id=workflow_id,
                                          workflow_type=workflow_type, event=event,
                                          to_email=recipient_email,
                                          subject=notification_subject,
                                          body=notification_body)

    document = None
    if event.upper() == "COMPLETED":
        document = generate_completion_document(db, workflow_id=workflow_id,
                                                workflow_type=workflow_type,
                                                event=event, data=data)
    return audit, notification, document