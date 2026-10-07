from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Enum, Float
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone
import uuid
import enum

def generate_uuid():
    return str(uuid.uuid4())

class RoleEnum(str, enum.Enum):
    employee = "employee"
    manager_l1 = "manager_l1"
    manager_l2 = "manager_l2"
    hr_admin = "hr_admin"

class StatusEnum(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    escalated = "escalated"

class LeaveTypeEnum(str, enum.Enum):
    sick = "sick"
    casual = "casual"
    annual = "annual"
    maternity = "maternity"
    paternity = "paternity"
    unpaid = "unpaid"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    employee_id = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default=RoleEnum.employee)
    department_id = Column(String, nullable=True)
    manager_id = Column(String, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    leave_balances = relationship("LeaveBalance", back_populates="user")
    requests = relationship("LeaveRequest", back_populates="requester", foreign_keys="LeaveRequest.requester_id")

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    leave_type = Column(String, nullable=False)
    total_days = Column(Float, default=0)
    used_days = Column(Float, default=0)
    remaining_days = Column(Float, default=0)
    year = Column(Integer, default=lambda: datetime.now().year)

    user = relationship("User", back_populates="leave_balances")

class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(String, primary_key=True, default=generate_uuid)
    requester_id = Column(String, ForeignKey("users.id"), nullable=False)
    leave_type = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    number_of_days = Column(Float, nullable=False)
    reason = Column(String, nullable=False)
    status = Column(String, default=StatusEnum.pending)
    escalation_level = Column(String, default="manager_l1")
    current_approver_id = Column(String, ForeignKey("users.id"), nullable=True)
    comments = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True)
    escalated_at = Column(DateTime, nullable=True)

    requester = relationship("User", back_populates="requests", foreign_keys=[requester_id])
    history = relationship("ApprovalHistory", back_populates="leave_request")

class ApprovalHistory(Base):
    __tablename__ = "approval_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    request_id = Column(String, ForeignKey("leave_requests.id"), nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    comments = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    leave_request = relationship("LeaveRequest", back_populates="history")
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    workflow_id = Column(String, nullable=False, index=True)
    workflow_type = Column(String, nullable=False, index=True)
    event = Column(String, nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    details = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    workflow_id = Column(String, nullable=False, index=True)
    workflow_type = Column(String, nullable=False)
    event = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(String, nullable=False)
    status = Column(String, default="queued")
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    workflow_id = Column(String, nullable=False, index=True)
    workflow_type = Column(String, nullable=False)
    event = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    path = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
