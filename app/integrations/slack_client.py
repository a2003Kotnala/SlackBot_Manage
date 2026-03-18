from slack_sdk import WebClient
from app.config import settings

class SlackClient:
    def __init__(self):
        self.client = WebClient(token=settings.slack_bot_token)

    async def get_channel_history(self, channel_id: str, thread_ts: str = None, limit: int = 100):
        """Fetch channel history, optionally for a thread."""
        response = self.client.conversations_history(
            channel=channel_id,
            latest=thread_ts,
            limit=limit,
            inclusive=True
        )
        return response["messages"]

    async def list_files(self, channel_id: str, ts_from: str = None, types: str = "canvases"):
        """List files in a channel, filtered by type."""
        response = self.client.files_list(
            channel=channel_id,
            ts_from=ts_from,
            types=types
        )
        return response["files"]

    async def get_file_content(self, file_id: str):
        """Get file content (for canvases)."""
        response = self.client.files_info(file=file_id)
        return response["file"]

    async def upload_canvas(self, channels: str, content: str, title: str):
        """Upload a canvas file."""
        response = self.client.files_upload(
            channels=channels,
            content=content,
            title=title,
            filetype="canvas"
        )
        return response["file"]

slack_client = SlackClient()