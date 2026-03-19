from fastapi import APIRouter, HTTPException, Request

from app.slack.bolt_app import handle_slack_request

router = APIRouter(tags=["slack"])


@router.post("/slack/commands")
async def slack_commands(request: Request):
    try:
        return await handle_slack_request(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
