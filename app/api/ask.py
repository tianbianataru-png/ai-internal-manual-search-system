from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.ask import AskIn, AskOut
from app.services import qa_service
from app.services.embedding import EmbeddingError

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("", response_model=AskOut)
def ask(body: AskIn):
    """質問に対して、登録済みマニュアルだけを根拠に回答し、出典を返す。"""
    try:
        return qa_service.ask(body.question, get_settings().default_user_id)
    except qa_service.QuestionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (EmbeddingError, qa_service.ChatError) as e:
        raise HTTPException(status_code=502, detail=str(e))
