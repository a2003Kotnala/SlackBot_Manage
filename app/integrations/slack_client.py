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
        self, channel_id: str, ts_from: str | None = None, types: str = "canvases"
    ):
        response = self.client.files_list(
            channel=channel_id,
            ts_from=ts_from,
            types=types,
        )
        return response["files"]

    def get_file_content(self, file_id: str):
        response = self.client.files_info(file=file_id)
        return response["file"]

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
