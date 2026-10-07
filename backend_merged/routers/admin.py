from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import User
from po_models import PurchaseOrder
from routers.users import require_role
from schemas import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_role("hr_admin")
MANAGER_ROLES = ("manager_l1", "manager_l2", "hr_admin")
PO_STATUSES = ("DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CANCELLED")


class ManagerAssignment(BaseModel):
    manager_id: Optional[str] = None


def _get_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.put("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    user = _get_user(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    user = _get_user(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/manager", response_model=UserResponse)
def assign_manager(user_id: str, data: ManagerAssignment, db: Session = Depends(get_db),
                   current_user: User = Depends(admin_only)):
    """Set (or clear, with null) a user's manager."""
    user = _get_user(db, user_id)
    if data.manager_id:
        if data.manager_id == user.id:
            raise HTTPException(status_code=400, detail="A user cannot be their own manager.")
        manager = _get_user(db, data.manager_id)
        if manager.role not in MANAGER_ROLES:
            raise HTTPException(status_code=400, detail="That user is not a manager.")
    user.manager_id = data.manager_id
    db.commit()
    db.refresh(user)
    return user


@router.get("/purchase-orders/summary")
def purchase_order_summary(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    counts = {s: 0 for s in PO_STATUSES}
    rows = db.query(PurchaseOrder.status, func.count(PurchaseOrder.id)).group_by(PurchaseOrder.status).all()
    for status_value, count in rows:
        counts[status_value] = count
    return {"total": sum(counts.values()), **{k.lower(): v for k, v in counts.items()}}