from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Any, Optional


class PredictionRequest(BaseModel):
    features: List[float]


class PredictionResponse(BaseModel):
    prediction: Any
    confidence: Optional[float] = None


class TrainingRequest(BaseModel):
    dataset_url: HttpUrl
    parameters: Dict[str, Any] = {}


class TrainingResponse(BaseModel):
    task_id: str
    message: str


# --- Email classification schemas ---

class EmailClassifyRequest(BaseModel):
    sender: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject line")
    body_preview: str = Field(..., description="Email body or preview text")
    recipient_name: Optional[str] = Field(None, description="Recipient's name for personalisation detection")


class EmailClassifyResponse(BaseModel):
    label: str = Field(..., description="Classification label: Important, Marketing, or Other")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")


class EmailClassifyBatchRequest(BaseModel):
    emails: List[EmailClassifyRequest] = Field(..., max_length=50, description="List of emails to classify (max 50)")


class EmailClassifyBatchResponse(BaseModel):
    results: List[EmailClassifyResponse]
