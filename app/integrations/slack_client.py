import httpx
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.config import settings


class SlackClient:
    def __init__(self) -> None:
        self.client = WebClient(token=settings.slack_bot_token)

    def is_configured(self) -> bool:
        return bool(settings.slack_bot_token)

    def get_channel_history(
        self, channel_id: str, thread_ts: str | None = None, limit: int = 100
    ):
        response = self.client.conversations_history(
            channel=channel_id,
            latest=thread_ts,
            limit=limit,
            inclusive=True,
        )
        return response["messages"]

    def list_files(
        self,
        channel_id: str,
        ts_from: str | None = None,
        types: str | None = None,
    ):
        request = {
            "channel": channel_id,
            "ts_from": ts_from,
        }
        if types:
            request["types"] = types

        response = self.client.files_list(**request)
        return response["files"]

    def get_file_content(self, file_id: str):
        response = self.client.files_info(file=file_id)
        return response["file"]

    def download_text_file(self, file_url: str) -> str:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                file_url,
                headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            )
            response.raise_for_status()
            return response.text

    def update_message(self, channel_id: str, message_ts: str, text: str):
        response = self.client.chat_update(channel=channel_id, ts=message_ts, text=text)
        return {"channel": response["channel"], "ts": response["ts"], "text": text}

    def upload_canvas(self, channel_id: str, content: str, title: str):
        document_content = {"type": "markdown", "markdown": content}

        try:
            response = self.client.conversations_canvases_create(
                channel_id=channel_id,
                title=title,
                document_content=document_content,
            )
            return {"id": response["canvas_id"], "title": title}
        except SlackApiError as exc:
            if exc.response.get("error") != "channel_canvas_already_exists":
                raise

            channel = self.client.conversations_info(channel=channel_id)["channel"]
            canvas = channel.get("properties", {}).get("canvas")
            if not canvas or not canvas.get("canvas_id"):
                raise

            self.client.canvases_edit(
                canvas_id=canvas["canvas_id"],
                changes=[
                    {
                        "operation": "replace",
                        "document_content": document_content,
                    }
                ],
            )
            return {"id": canvas["canvas_id"], "title": title}


slack_client = SlackClient()
