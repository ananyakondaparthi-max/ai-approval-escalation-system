from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    employee_id: str
    full_name: str
    email: str
    password: str
    role: str
    department_id: Optional[str] = None
    manager_id: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    employee_id: str
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class LeaveRequestCreate(BaseModel):
    leave_type: str  # sick, casual, annual, maternity, paternity, unpaid
    start_date: datetime
    end_date: datetime
    reason: str

class LeaveRequestResponse(BaseModel):
    id: str
    requester_id: str
    leave_type: str
    start_date: datetime
    end_date: datetime
    number_of_days: float
    reason: str
    status: str
    escalation_level: str
    current_approver_id: Optional[str]
    comments: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class ApprovalAction(BaseModel):
    action: str  # approve or reject
    comments: Optional[str] = None

class LeaveBalanceResponse(BaseModel):
    id: str
    user_id: str
    leave_type: str
    total_days: float
    used_days: float
    remaining_days: float
    year: int

    class Config:
        from_attributes = True
        # Add this line at the bottom of schemas.py
Token = TokenResponse