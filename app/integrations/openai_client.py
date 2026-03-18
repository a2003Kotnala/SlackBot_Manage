import httpx
from app.config import settings
from app.domain.schemas.extraction import ExtractionResult

class OpenAIClient:
    def __init__(self):
        self.api_key = settings.openai_api_key
        self.base_url = "https://api.openai.com/v1"

    async def extract_meeting_data(self, raw_content: str) -> ExtractionResult:
        """Call OpenAI to extract structured data from meeting notes."""
        prompt = f"""
        Extract the following from the meeting notes:
        - Summary: A brief summary of the meeting.
        - Decisions: List of decisions made.
        - Action Items: List with content, owner (if stated), due_date (if stated), confidence (high/medium/low/needs_review).
        - Open Questions: List of unresolved questions.
        - Blockers: List of risks or blockers.
        - Overall Confidence: high/medium/low/needs_review.

        Do not invent owners or dates. If unclear, set to null and confidence to needs_review.

        Meeting notes:
        {raw_content}
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_schema", "json_schema": ExtractionResult.model_json_schema()}
                }
            )
            response.raise_for_status()
            data = response.json()
            # Parse the response into ExtractionResult
            return ExtractionResult.parse_raw(data["choices"][0]["message"]["content"])

openai_client = OpenAIClient()