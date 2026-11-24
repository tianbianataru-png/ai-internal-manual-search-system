from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.schemas.history import HistoryDetail, HistorySummary, RatingIn
from app.services import history_service
from app.services.history_service import HistoryError

router = APIRouter(prefix="/api/history", tags=["history"])


def _http(e: HistoryError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


@router.get("", response_model=list[HistorySummary])
def list_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 user: dict = Depends(get_current_user)):
    """質問履歴の一覧(新しい順)。"""
    return history_service.list_history(user["id"], limit, offset)


@router.get("/{history_id}", response_model=HistoryDetail)
def get_history(history_id: int, user: dict = Depends(get_current_user)):
    """質問・回答・出典の詳細。"""
    try:
        return history_service.get_history(history_id, user["id"])
    except HistoryError as e:
        raise _http(e)


@router.delete("/{history_id}", status_code=204)
def delete_history(history_id: int, user: dict = Depends(get_current_user)):
    try:
        history_service.delete_history(history_id, user["id"])
    except HistoryError as e:
        raise _http(e)


@router.put("/{history_id}/rating", status_code=204)
def set_rating(history_id: int, body: RatingIn, user: dict = Depends(get_current_user)):
    """回答に「役に立った / 役に立たなかった」の評価をつける(null で取り消し)。"""
    try:
        history_service.set_rating(history_id, user["id"], body.rating)
    except HistoryError as e:
        raise _http(e)
