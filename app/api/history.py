import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import get_current_user
from app.schemas.history import HistoryDetail, HistorySummary, RatingIn
from app.services import history_service
from app.services.history_service import HistoryError

router = APIRouter(prefix="/api/history", tags=["history"])


def _http(e: HistoryError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


@router.get("", response_model=list[HistorySummary])
def list_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 q: str | None = Query(None, max_length=100), rating: str | None = None,
                 user: dict = Depends(get_current_user)):
    """質問履歴の一覧(新しい順)。q: 質問・回答の部分一致、rating: good / bad / none(未評価)。"""
    try:
        return history_service.list_history(user["id"], limit, offset, q, rating)
    except HistoryError as e:
        raise _http(e)


def _cell(v) -> str:
    """CSVの数式インジェクション対策: 先頭が = + - @ などなら ' を付けて文字列として扱わせる。"""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@router.get("/export.csv")
def export_history(q: str | None = Query(None, max_length=100), rating: str | None = None,
                   user: dict = Depends(get_current_user)):
    """自分の質問履歴をCSVでダウンロード(一覧と同じ q / rating の絞り込みが使える。最大5000件)。"""
    try:
        rows = history_service.list_history(user["id"], 5000, 0, q, rating)
    except HistoryError as e:
        raise _http(e)
    labels = {"good": "役に立った", "bad": "役に立たなかった", None: ""}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日時", "質問", "回答", "出典数", "評価"])
    for h in rows:
        w.writerow([h["created_at"], _cell(h["question"]), _cell(h["answer"]), h["source_count"], labels[h["rating"]]])
    # BOM付きUTF-8(Excelで文字化けしない)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=history.csv"})


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
