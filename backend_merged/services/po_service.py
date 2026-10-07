"""Purchase order logic and approval workflow."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from models import User
from po_models import PurchaseOrder, PurchaseOrderItem
from services.outflow_service import process_event

WORKFLOW_TYPE = "purchase_order"
APPROVER_ROLES = ("manager_l1", "manager_l2", "hr_admin")
VIEW_ALL_ROLES = ("manager_l2", "hr_admin")
EDITABLE_STATUSES = ("DRAFT", "REJECTED")
CANCELLABLE_STATUSES = ("DRAFT", "PENDING_APPROVAL")


def utcnow():
    return datetime.now(timezone.utc)


def generate_po_number() -> str:
    return f"PO-{datetime.now().year}-{uuid4().hex[:8].upper()}"


def _build_items(items_data):
    items, total = [], 0.0
    for d in items_data:
        line_total = round(d.quantity * d.unit_price, 2)
        items.append(PurchaseOrderItem(
            item_name=d.item_name,
            item_description=d.item_description,
            quantity=d.quantity,
            unit_price=d.unit_price,
            total_price=line_total,
        ))
        total += line_total
    return items, round(total, 2)


def find_approver(db: Session, user: User):
    """The user's own manager, otherwise the first available approver."""
    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id, User.is_active == True).first()
        if manager and manager.role in APPROVER_ROLES and manager.id != user.id:
            return manager
    for role in APPROVER_ROLES:
        approver = db.query(User).filter(
            User.role == role, User.is_active == True, User.id != user.id
        ).first()
        if approver:
            return approver
    return None


def can_view(po: PurchaseOrder, user: User) -> bool:
    return (
        po.requester_id == user.id
        or po.approver_id == user.id
        or user.role in VIEW_ALL_ROLES
    )


def can_decide(po: PurchaseOrder, user: User) -> bool:
    if po.requester_id == user.id:
        return False
    if user.role in VIEW_ALL_ROLES:
        return True
    return user.role in APPROVER_ROLES and po.approver_id == user.id


def _po_html(po: PurchaseOrder, heading: str) -> str:
    return (
        f"<p>{heading}</p>"
        f"<p><b>PO Number:</b> {po.po_number}</p>"
        f"<p><b>Department:</b> {po.department}</p>"
        f"<p><b>Vendor:</b> {po.vendor_name}</p>"
        f"<p><b>Purpose:</b> {po.purpose}</p>"
        f"<p><b>Total:</b> {po.total_amount}</p>"
    )


def _record(db: Session, po: PurchaseOrder, event: str, actor_id: str,
            old_status, new_status, recipient=None, subject=None, body=None, extra=None):
    data = {
        "po_number": po.po_number,
        "department": po.department,
        "vendor_name": po.vendor_name,
        "purpose": po.purpose,
        "total_amount": po.total_amount,
        "items": [f"{i.item_name} x{i.quantity} @ {i.unit_price}" for i in po.items],
    }
    if extra:
        data.update(extra)
    process_event(
        db,
        workflow_id=str(po.id),
        workflow_type=WORKFLOW_TYPE,
        event=event,
        actor_id=actor_id,
        recipient_email=recipient,
        notification_subject=subject if recipient else None,
        notification_body=body if recipient else None,
        data=data,
        previous_status=old_status,
        new_status=new_status,
    )


# ---------------- CRUD ----------------

def create_purchase_order(db: Session, user: User, data):
    items, total = _build_items(data.items)
    po = PurchaseOrder(
        po_number=generate_po_number(),
        requester_id=user.id,
        department=data.department,
        vendor_name=data.vendor_name,
        vendor_email=data.vendor_email,
        vendor_phone=data.vendor_phone,
        purpose=data.purpose,
        description=data.description,
        status="DRAFT",
        total_amount=total,
        items=items,
    )
    db.add(po)
    db.flush()
    _record(db, po, "CREATED", user.id, None, "DRAFT")
    db.commit()
    db.refresh(po)
    return po


def get_purchase_order(db: Session, po_id: str):
    return db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()


def list_purchase_orders(db: Session, *, requester_id=None, approver_id=None, status=None):
    query = db.query(PurchaseOrder)
    if requester_id:
        query = query.filter(PurchaseOrder.requester_id == requester_id)
    if approver_id:
        query = query.filter(PurchaseOrder.approver_id == approver_id)
    if status:
        query = query.filter(PurchaseOrder.status == status)
    return query.order_by(PurchaseOrder.created_at.desc()).all()


def update_purchase_order(db: Session, po: PurchaseOrder, user: User, data):
    if po.status not in EDITABLE_STATUSES:
        raise ValueError("Only DRAFT or REJECTED Purchase Orders can be edited.")
    if po.requester_id != user.id and user.role != "hr_admin":
        raise PermissionError("You can only edit your own Purchase Order.")

    for field in ("department", "vendor_name", "vendor_email", "vendor_phone", "purpose", "description"):
        value = getattr(data, field)
        if value is not None:
            setattr(po, field, value)

    if data.items is not None:
        if not data.items:
            raise ValueError("A Purchase Order needs at least one item.")
        items, total = _build_items(data.items)
        po.items.clear()
        po.items.extend(items)
        po.total_amount = total

    po.updated_at = utcnow()
    db.commit()
    db.refresh(po)
    return po


# ---------------- Workflow ----------------

def submit_purchase_order(db: Session, po: PurchaseOrder, user: User):
    if po.status != "DRAFT":
        raise ValueError("Only DRAFT Purchase Orders can be submitted.")
    if po.requester_id != user.id:
        raise PermissionError("You can only submit your own Purchase Order.")
    if not po.items or po.total_amount <= 0:
        raise ValueError("Purchase Order must have at least one item and a total above zero.")

    approver = find_approver(db, user)
    if not approver:
        raise ValueError("No approver available. Register a manager_l1 user first.")

    old = po.status
    po.status = "PENDING_APPROVAL"
    po.approver_id = approver.id
    po.submitted_at = utcnow()
    po.updated_at = utcnow()

    _record(db, po, "SUBMITTED", user.id, old, po.status,
            recipient=approver.email,
            subject=f"Purchase Order {po.po_number} needs your approval",
            body=_po_html(po, f"A Purchase Order from {user.full_name} needs your approval."))
    db.commit()
    db.refresh(po)
    return po


def approve_purchase_order(db: Session, po: PurchaseOrder, user: User, remarks=None):
    if po.status != "PENDING_APPROVAL":
        raise ValueError("Only Purchase Orders pending approval can be approved.")
    if not can_decide(po, user):
        raise PermissionError("You are not allowed to approve this Purchase Order.")

    old = po.status
    po.status = "APPROVED"
    po.approver_id = user.id
    po.approved_at = utcnow()
    po.updated_at = utcnow()

    requester = db.query(User).filter(User.id == po.requester_id).first()
    _record(db, po, "APPROVED", user.id, old, po.status,
            recipient=requester.email if requester else None,
            subject=f"Your Purchase Order {po.po_number} has been approved",
            body=_po_html(po, f"Your Purchase Order was approved by {user.full_name}.")
                 + f"<p><b>Remarks:</b> {remarks or 'None'}</p>",
            extra={"remarks": remarks})

    # COMPLETED makes the shared document generator create a PDF.
    _record(db, po, "COMPLETED", user.id, po.status, po.status,
            extra={"approved_by": user.full_name, "remarks": remarks})

    db.commit()
    db.refresh(po)
    return po


def reject_purchase_order(db: Session, po: PurchaseOrder, user: User, reason: str):
    if po.status != "PENDING_APPROVAL":
        raise ValueError("Only Purchase Orders pending approval can be rejected.")
    if not can_decide(po, user):
        raise PermissionError("You are not allowed to reject this Purchase Order.")
    if not reason or not reason.strip():
        raise ValueError("A rejection reason is required.")

    old = po.status
    po.status = "REJECTED"
    po.approver_id = user.id
    po.rejection_reason = reason.strip()
    po.rejected_at = utcnow()
    po.updated_at = utcnow()

    requester = db.query(User).filter(User.id == po.requester_id).first()
    _record(db, po, "REJECTED", user.id, old, po.status,
            recipient=requester.email if requester else None,
            subject=f"Your Purchase Order {po.po_number} has been rejected",
            body=_po_html(po, f"Your Purchase Order was rejected by {user.full_name}.")
                 + f"<p><b>Reason:</b> {po.rejection_reason}</p>",
            extra={"reason": po.rejection_reason})
    db.commit()
    db.refresh(po)
    return po


def resubmit_purchase_order(db: Session, po: PurchaseOrder, user: User):
    if po.status != "REJECTED":
        raise ValueError("Only REJECTED Purchase Orders can be resubmitted.")
    if po.requester_id != user.id:
        raise PermissionError("You can only resubmit your own Purchase Order.")

    approver = find_approver(db, user)
    if not approver:
        raise ValueError("No approver available.")

    old = po.status
    po.status = "PENDING_APPROVAL"
    po.approver_id = approver.id
    po.submitted_at = utcnow()
    po.rejected_at = None
    po.rejection_reason = None
    po.updated_at = utcnow()

    _record(db, po, "RESUBMITTED", user.id, old, po.status,
            recipient=approver.email,
            subject=f"Purchase Order {po.po_number} was resubmitted",
            body=_po_html(po, f"{user.full_name} corrected and resubmitted this Purchase Order."))
    db.commit()
    db.refresh(po)
    return po


def cancel_purchase_order(db: Session, po: PurchaseOrder, user: User):
    if po.requester_id != user.id and user.role != "hr_admin":
        raise PermissionError("You can only cancel your own Purchase Order.")
    if po.status not in CANCELLABLE_STATUSES:
        raise ValueError("This Purchase Order cannot be cancelled.")

    old = po.status
    po.status = "CANCELLED"
    po.updated_at = utcnow()
    _record(db, po, "CANCELLED", user.id, old, po.status)
    db.commit()
    db.refresh(po)
    return po