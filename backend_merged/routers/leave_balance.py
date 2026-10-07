from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import LeaveBalance, User
from schemas import LeaveBalanceResponse
from routers.users import get_current_user
from typing import List
from datetime import datetime

router = APIRouter(prefix="/leave-balance", tags=["leave-balance"])

@router.get("/", response_model=List[LeaveBalanceResponse])
def get_my_leave_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    balances = db.query(LeaveBalance).filter(
        LeaveBalance.user_id == current_user.id,
        LeaveBalance.year == datetime.now().year
    ).all()
    return balances

@router.post("/initialize")
def initialize_leave_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    leave_types = {
        "sick": 10,
        "casual": 10,
        "annual": 20,
        "maternity": 90,
        "paternity": 15,
        "unpaid": 30
    }

    created = []
    for leave_type, days in leave_types.items():
        existing = db.query(LeaveBalance).filter(
            LeaveBalance.user_id == current_user.id,
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == datetime.now().year
        ).first()

        if not existing:
            balance = LeaveBalance(
                user_id=current_user.id,
                leave_type=leave_type,
                total_days=days,
                used_days=0,
                remaining_days=days,
                year=datetime.now().year
            )
            db.add(balance)
            created.append(leave_type)

    db.commit()
    return {"message": "Leave balance initialized", "types": created}