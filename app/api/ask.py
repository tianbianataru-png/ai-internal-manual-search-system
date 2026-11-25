from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.schemas.ask import AskIn, AskOut
from app.services import qa_service
from app.services.embedding import EmbeddingError

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("", response_model=AskOut)
def ask(body: AskIn, user: dict = Depends(get_current_user)):
    """質問に対して、登録済みマニュアルだけを根拠に回答し、出典を返す。"""
    try:
        return qa_service.ask(body.question, user["id"], body.manual_id, body.category)
    except qa_service.QuestionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (EmbeddingError, qa_service.ChatError) as e:
        raise HTTPException(status_code=502, detail=str(e))
