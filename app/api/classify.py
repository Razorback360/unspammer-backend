from fastapi import APIRouter, HTTPException

from app.schemas.ml import (
    EmailClassifyRequest,
    EmailClassifyResponse,
    EmailClassifyBatchRequest,
    EmailClassifyBatchResponse,
)
from app.services.classifier import classify_email

router = APIRouter()


@router.post("/", response_model=EmailClassifyResponse, summary="Classify a single email")
def classify_single(request: EmailClassifyRequest) -> EmailClassifyResponse:
    result = classify_email(
        sender=request.sender,
        subject=request.subject,
        body_preview=request.body_preview,
        recipient_name=request.recipient_name,
    )
    return EmailClassifyResponse(**result)


@router.post(
    "/batch",
    response_model=EmailClassifyBatchResponse,
    summary="Classify a batch of emails (max 50)",
)
def classify_batch(request: EmailClassifyBatchRequest) -> EmailClassifyBatchResponse:
    if len(request.emails) > 50:
        raise HTTPException(status_code=422, detail="Batch size must not exceed 50 emails.")

    results = [
        EmailClassifyResponse(
            **classify_email(
                sender=email.sender,
                subject=email.subject,
                body_preview=email.body_preview,
                recipient_name=email.recipient_name,
            )
        )
        for email in request.emails
    ]
    return EmailClassifyBatchResponse(results=results)
