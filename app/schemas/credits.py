from pydantic import BaseModel, Field

class CreditReservationRequest(BaseModel):
    request_id: str = Field(min_length=3, max_length=120)
    workload: str = Field(min_length=2, max_length=80)
    estimate: int | None = Field(default=None, ge=0)

class CreditSettlementRequest(BaseModel):
    request_id: str
    actual: int = Field(ge=0)
    meaningful_output: bool = True

class ReferralApplyRequest(BaseModel):
    code: str = Field(min_length=4, max_length=40)

class PurchaseOrderRequest(BaseModel):
    product_id: str

class PurchaseVerifyRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str
