"""回答の評価の集計(管理者のみ)。"""
from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.schemas.history import FeedbackSummary
from app.services import history_service

router = APIRouter(prefix="/api/feedback", tags=["feedback"], dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=FeedbackSummary)
def summary():
    return history_service.feedback_summary()
