"""回答の評価の集計(管理者のみ)。"""
from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.schemas.history import FeedbackSummary, Unanswered, Usage
from app.services import history_service

router = APIRouter(prefix="/api/feedback", tags=["feedback"], dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=FeedbackSummary)
def summary():
    return history_service.feedback_summary()


@router.get("/unanswered", response_model=Unanswered)
def unanswered():
    """資料が見つからず回答できなかった質問の一覧(マニュアルの不足を見つける手がかり)。"""
    return history_service.unanswered()


@router.get("/usage", response_model=Usage)
def usage():
    """利用状況(質問数・日別の推移・よく使う人)。"""
    return history_service.usage()
