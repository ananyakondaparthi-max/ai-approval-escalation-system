from datetime import datetime, timezone

from celery_app import celery_app
from database import SessionLocal
from models import ApprovalHistory, LeaveRequest, StatusEnum, User
from tasks.notifications import send_email


@celery_app.task
def check_and_escalate():
    db = SessionLocal()
    try:
        open_requests = db.query(LeaveRequest).filter(
            LeaveRequest.status.in_(["pending", "escalated"])
        ).all()

        for request in open_requests:
            hours_pending = (
                datetime.now(timezone.utc) - request.created_at.replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600

            if hours_pending >= 2/60 and request.escalation_level == "manager_l1":
                escalate_request.delay(str(request.id), "manager_l2")
            elif hours_pending >=4/60 and request.escalation_level == "manager_l2":
                escalate_request.delay(str(request.id), "hr_admin")
    finally:
        db.close()


@celery_app.task
def escalate_request(request_id: str, escalate_to: str):
    db = SessionLocal()
    try:
        request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
        if not request:
            return {"error": "Request not found"}

        new_approver = db.query(User).filter(
            User.role == escalate_to,
            User.is_active == True,
        ).first()
        if not new_approver:
            return {"error": f"No approver found for role {escalate_to}"}

        request.escalation_level = escalate_to
        request.current_approver_id = new_approver.id
        request.status = StatusEnum.escalated
        request.escalated_at = datetime.now(timezone.utc)

        db.add(ApprovalHistory(
            request_id=request.id,
            actor_id=new_approver.id,
            action="escalated",
            comments=f"Auto-escalated to {escalate_to}",
        ))
        db.commit()

        send_email(
            new_approver.email,
            f"Escalated Leave Request: {request.leave_type}",
            f"<p>A request has been escalated to you.</p>"
            f"<p><b>Leave Type:</b> {request.leave_type}</p>"
            f"<p><b>Reason:</b> {request.reason}</p>",
        )
        return {"status": "escalated", "request_id": request_id}
    finally:
        db.close()