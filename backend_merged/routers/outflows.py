from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models import AuditLog, NotificationLog, DocumentRecord
from routers.users import get_current_user
from models import User
from services.outflow_service import process_event

router = APIRouter(prefix="/outflows", tags=["common outflows"])

class WorkflowEvent(BaseModel):
    workflow_id: str
    workflow_type: str
    event: str
    actor_id: Optional[str] = None
    recipient_email: Optional[str] = None
    notification_subject: Optional[str] = None
    notification_body: Optional[str] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

@router.post("/events")
def create_workflow_event(payload: WorkflowEvent, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    actor = payload.actor_id or current_user.id
    audit, notification, document = process_event(
        db, workflow_id=payload.workflow_id, workflow_type=payload.workflow_type,
        event=payload.event.upper(), actor_id=actor,
        recipient_email=payload.recipient_email,
        notification_subject=payload.notification_subject,
        notification_body=payload.notification_body,
        data=payload.data, previous_status=payload.previous_status,
        new_status=payload.new_status)
    db.commit()
    return {"event": payload.event.upper(), "workflow_id": payload.workflow_id,
            "audit_id": audit.id, "notification_id": notification.id if notification else None,
            "document_id": document.id if document else None}

@router.get("/audit/{workflow_id}")
def get_audit(workflow_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(AuditLog).filter(AuditLog.workflow_id == workflow_id).order_by(AuditLog.created_at.desc()).all()

@router.get("/audit/{workflow_id}/report")
def audit_report(workflow_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    rows = db.query(AuditLog).filter(AuditLog.workflow_id == workflow_id).order_by(AuditLog.created_at.asc()).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No audit records found")
    out_dir = Path("generated_documents"); out_dir.mkdir(exist_ok=True)
    safe_id = "".join(c for c in workflow_id if c.isalnum() or c in "-_") or "workflow"
    path = out_dir / f"{safe_id}_audit_report.pdf"
    c = canvas.Canvas(str(path), pagesize=A4); width, height = A4
    y = height - 55
    c.setFont("Helvetica-Bold", 17); c.drawString(45, y, "Workflow Audit Report")
    y -= 25; c.setFont("Helvetica", 10); c.drawString(45, y, f"Workflow ID: {workflow_id}")
    y -= 30
    for row in rows:
        lines = [f"Event: {row.event}", f"Workflow Type: {row.workflow_type}", f"Actor: {row.actor_id or 'system'}", f"Status: {row.previous_status or '-'} -> {row.new_status or '-'}", f"Time: {row.created_at}", f"Details: {row.details or '{}'}"]
        for line in lines:
            if y < 60:
                c.showPage(); y = height - 55; c.setFont("Helvetica", 10)
            for chunk in [line[i:i+100] for i in range(0, len(line), 100)]:
                c.drawString(50, y, chunk); y -= 14
        y -= 8
    c.save()
    return FileResponse(path, media_type="application/pdf", filename=path.name)

@router.get("/notifications/{workflow_id}")
def get_notifications(workflow_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(NotificationLog).filter(NotificationLog.workflow_id == workflow_id).order_by(NotificationLog.created_at.desc()).all()

@router.get("/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(DocumentRecord).filter(DocumentRecord.id == document_id).first()
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.get("/documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(DocumentRecord).filter(DocumentRecord.id == document_id).first()
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    path = Path(doc.path)
    if not path.exists(): raise HTTPException(status_code=404, detail="Generated file not found")
    return FileResponse(path, media_type="application/pdf", filename=doc.filename)
