from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from models import DocumentRecord, User
from po_schemas import (
    PurchaseOrderApproval,
    PurchaseOrderCreate,
    PurchaseOrderRejection,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
)
from routers.users import get_current_user, require_role
from services import po_service

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])


def _handle(db: Session, action):
    """Turn service errors into clear HTTP errors."""
    try:
        return action()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


def _get_po(db: Session, po_id: str):
    po = po_service.get_purchase_order(db, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found.")
    return po


def _get_visible_po(db: Session, po_id: str, user: User):
    po = _get_po(db, po_id)
    if not po_service.can_view(po, user):
        raise HTTPException(status_code=403, detail="You do not have permission to view this Purchase Order.")
    return po


@router.post("/", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
def create_po(data: PurchaseOrderCreate, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    """Create a Purchase Order in DRAFT status."""
    return _handle(db, lambda: po_service.create_purchase_order(db, current_user, data))


@router.get("/my", response_model=List[PurchaseOrderResponse])
def my_pos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Purchase Orders created by the logged-in user."""
    return po_service.list_purchase_orders(db, requester_id=current_user.id)


@router.get("/", response_model=List[PurchaseOrderResponse])
def list_pos(status_filter: Optional[str] = None, db: Session = Depends(get_db),
             current_user: User = Depends(require_role(*po_service.APPROVER_ROLES))):
    """For approvers. manager_l1 sees POs assigned to them, manager_l2 and hr_admin see all."""
    status_value = status_filter.upper() if status_filter else None
    if current_user.role == "manager_l1":
        return po_service.list_purchase_orders(db, approver_id=current_user.id, status=status_value)
    return po_service.list_purchase_orders(db, status=status_value)


@router.get("/{po_id}", response_model=PurchaseOrderResponse)
def get_po(po_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_visible_po(db, po_id, current_user)


@router.put("/{po_id}", response_model=PurchaseOrderResponse)
def update_po(po_id: str, data: PurchaseOrderUpdate, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    """Edit a DRAFT or REJECTED Purchase Order."""
    po = _get_po(db, po_id)
    return _handle(db, lambda: po_service.update_purchase_order(db, po, current_user, data))


@router.post("/{po_id}/submit", response_model=PurchaseOrderResponse)
def submit_po(po_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    po = _get_po(db, po_id)
    return _handle(db, lambda: po_service.submit_purchase_order(db, po, current_user))


@router.post("/{po_id}/approve", response_model=PurchaseOrderResponse)
def approve_po(po_id: str, data: PurchaseOrderApproval, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    po = _get_po(db, po_id)
    return _handle(db, lambda: po_service.approve_purchase_order(db, po, current_user, data.remarks))


@router.post("/{po_id}/reject", response_model=PurchaseOrderResponse)
def reject_po(po_id: str, data: PurchaseOrderRejection, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    po = _get_po(db, po_id)
    return _handle(db, lambda: po_service.reject_purchase_order(db, po, current_user, data.reason))


@router.post("/{po_id}/resubmit", response_model=PurchaseOrderResponse)
def resubmit_po(po_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    po = _get_po(db, po_id)
    return _handle(db, lambda: po_service.resubmit_purchase_order(db, po, current_user))


@router.post("/{po_id}/cancel", response_model=PurchaseOrderResponse)
def cancel_po(po_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    po = _get_po(db, po_id)
    return _handle(db, lambda: po_service.cancel_purchase_order(db, po, current_user))


@router.get("/{po_id}/status")
def po_status(po_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    po = _get_visible_po(db, po_id, current_user)
    return {
        "purchase_order_id": po.id,
        "po_number": po.po_number,
        "status": po.status,
        "approver_id": po.approver_id,
        "submitted_at": po.submitted_at,
        "approved_at": po.approved_at,
        "rejected_at": po.rejected_at,
        "rejection_reason": po.rejection_reason,
    }


@router.get("/{po_id}/document")
def po_document(po_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download the PDF created when the Purchase Order was approved."""
    po = _get_visible_po(db, po_id, current_user)
    doc = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.workflow_id == po.id)
        .order_by(DocumentRecord.created_at.desc())
        .first()
    )
    if not doc or not Path(doc.path).exists():
        raise HTTPException(status_code=404, detail="No document yet. A PDF is created when the PO is approved.")
    return FileResponse(doc.path, media_type="application/pdf", filename=doc.filename)