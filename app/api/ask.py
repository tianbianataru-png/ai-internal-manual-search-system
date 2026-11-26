import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

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


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def ask_stream(body: AskIn, user: dict = Depends(get_current_user)):
    """回答を少しずつ送る版(Server-Sent Events)。
    event: delta(回答の断片)→ event: done(最終結果。/api/ask と同じ形)。失敗時は event: error。"""
    # 質問の不正は、ストリーム開始前に通常のエラーとして返す
    gen = qa_service.ask_stream(body.question, user["id"], body.manual_id, body.category)
    try:
        first = next(gen)
    except qa_service.QuestionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (EmbeddingError, qa_service.ChatError) as e:
        raise HTTPException(status_code=502, detail=str(e))

    def events():
        try:
            yield _sse(*first)
            for kind, data in gen:
                yield _sse(kind, data)
        except (EmbeddingError, qa_service.ChatError) as e:
            yield _sse("error", {"detail": str(e)})
        except Exception:
            yield _sse("error", {"detail": "回答の生成中にエラーが発生しました。"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
