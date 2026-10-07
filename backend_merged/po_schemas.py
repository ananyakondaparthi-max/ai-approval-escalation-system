from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrderItemCreate(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=200)
    item_description: Optional[str] = None
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)


class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    item_name: str
    item_description: Optional[str] = None
    quantity: int
    unit_price: float
    total_price: float


class PurchaseOrderCreate(BaseModel):
    department: str = Field(..., min_length=1, max_length=100)
    vendor_name: str = Field(..., min_length=1, max_length=150)
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    purpose: str = Field(..., min_length=1)
    description: Optional[str] = None
    items: List[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderUpdate(BaseModel):
    department: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    purpose: Optional[str] = None
    description: Optional[str] = None
    items: Optional[List[PurchaseOrderItemCreate]] = None


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    po_number: str
    requester_id: str
    department: str
    vendor_name: str
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    purpose: str
    description: Optional[str] = None
    total_amount: float
    status: str
    approver_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    items: List[PurchaseOrderItemResponse] = []


class PurchaseOrderApproval(BaseModel):
    remarks: Optional[str] = None


class PurchaseOrderRejection(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)