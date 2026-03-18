from fastapi import APIRouter, HTTPException, Request

from app.slack.bolt_app import get_bolt_app

router = APIRouter()

@router.post("/slack/commands")
async def slack_commands(request: Request):
    try:
        bolt_app = get_bolt_app()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await bolt_app.process(request)
