from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ApprovalHistory, LeaveBalance, LeaveRequest, User
from routers.users import get_current_user
from schemas import ApprovalAction, LeaveRequestCreate, LeaveRequestResponse
from services.outflow_service import process_event

router = APIRouter(prefix="/requests", tags=["requests"])

OPEN_STATUSES = ("pending", "escalated")
VIEW_ALL_ROLES = ("manager_l2", "hr_admin")


def calculate_working_days(start_date: datetime, end_date: datetime) -> float:
    days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # Monday to Friday
            days += 1
        current += timedelta(days=1)
    return days


def find_approver(db: Session, user: User):
    """The user's own manager, or the first active manager_l1 as a fallback."""
    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id, User.is_active == True).first()
        if manager:
            return manager
    return db.query(User).filter(
        User.role == "manager_l1", User.is_active == True, User.id != user.id
    ).first()


@router.post("/", response_model=LeaveRequestResponse)
def create_leave_request(
    data: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.start_date > data.end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")

    number_of_days = calculate_working_days(data.start_date, data.end_date)
    if number_of_days == 0:
        raise HTTPException(status_code=400, detail="The selected dates have no working days")

    balance = db.query(LeaveBalance).filter(
        LeaveBalance.user_id == current_user.id,
        LeaveBalance.leave_type == data.leave_type,
        LeaveBalance.year == datetime.now().year,
    ).first()
    if balance and balance.remaining_days < number_of_days:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient leave balance. Available: {balance.remaining_days} days",
        )

    approver = find_approver(db, current_user)

    new_request = LeaveRequest(
        requester_id=current_user.id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        number_of_days=number_of_days,
        reason=data.reason,
        current_approver_id=approver.id if approver else None,
        status="pending",
        escalation_level="manager_l1",
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    process_event(
        db,
        workflow_id=str(new_request.id),
        workflow_type="leave_request",
        event="SUBMITTED",
        actor_id=current_user.id,
        recipient_email=approver.email if approver else None,
        notification_subject=f"New Leave Request: {data.leave_type}",
        notification_body=(
            f"<p>A new leave request needs your approval.</p>"
            f"<p><b>Employee:</b> {current_user.full_name}</p>"
            f"<p><b>Leave Type:</b> {data.leave_type}</p>"
            f"<p><b>From:</b> {data.start_date.date()}</p>"
            f"<p><b>To:</b> {data.end_date.date()}</p>"
            f"<p><b>Days:</b> {number_of_days}</p>"
            f"<p><b>Reason:</b> {data.reason}</p>"
        ),
        data={
            "leave_type": data.leave_type,
            "start_date": data.start_date,
            "end_date": data.end_date,
            "number_of_days": number_of_days,
            "reason": data.reason,
        },
        previous_status=None,
        new_status="pending",
    )
    db.commit()
    return new_request


@router.get("/", response_model=List[LeaveRequestResponse])
def get_leave_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "employee":
        return db.query(LeaveRequest).filter(LeaveRequest.requester_id == current_user.id).all()
    if current_user.role in ("manager_l1", "manager_l2"):
        return db.query(LeaveRequest).filter(LeaveRequest.current_approver_id == current_user.id).all()
    return db.query(LeaveRequest).all()


@router.get("/{request_id}", response_model=LeaveRequestResponse)
def get_leave_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    allowed = (
        request.requester_id == current_user.id
        or request.current_approver_id == current_user.id
        or current_user.role in VIEW_ALL_ROLES
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized to view this request")
    return request


@router.post("/{request_id}/action")
def action_leave_request(
    request_id: str,
    action: ApprovalAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    action_name = action.action.lower()
    if action_name not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be approve or reject")

    if request.status not in OPEN_STATUSES:
        raise HTTPException(status_code=400, detail=f"This request is already {request.status}")

    if str(request.current_approver_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    previous_status = request.status
    request.status = "approved" if action_name == "approve" else "rejected"
    request.comments = action.comments
    request.updated_at = datetime.now(timezone.utc)

    if action_name == "approve":
        balance = db.query(LeaveBalance).filter(
            LeaveBalance.user_id == request.requester_id,
            LeaveBalance.leave_type == request.leave_type,
            LeaveBalance.year == datetime.now().year,
        ).first()
        if balance:
            balance.used_days += request.number_of_days
            balance.remaining_days -= request.number_of_days

    db.add(ApprovalHistory(
        request_id=request.id,
        actor_id=current_user.id,
        action=action_name,
        comments=action.comments,
    ))
    db.commit()

    requester = db.query(User).filter(User.id == request.requester_id).first()
    process_event(
        db,
        workflow_id=str(request.id),
        workflow_type="leave_request",
        event="APPROVED" if action_name == "approve" else "REJECTED",
        actor_id=current_user.id,
        recipient_email=requester.email if requester else None,
        notification_subject=f"Your Leave Request has been {request.status}",
        notification_body=(
            f"<p>Your leave request has been <b>{request.status}</b>.</p>"
            f"<p><b>Leave Type:</b> {request.leave_type}</p>"
            f"<p><b>From:</b> {request.start_date.date()}</p>"
            f"<p><b>To:</b> {request.end_date.date()}</p>"
            f"<p><b>Days:</b> {request.number_of_days}</p>"
            f"<p><b>Comments:</b> {action.comments or 'None'}</p>"
        ),
        data={
            "leave_type": request.leave_type,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "number_of_days": request.number_of_days,
            "reason": request.reason,
            "comments": action.comments,
        },
        previous_status=previous_status,
        new_status=request.status,
    )
    db.commit()

    return {"status": request.status, "request_id": request_id}