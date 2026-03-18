# Extraction service
from app.integrations.openai_client import openai_client
from app.domain.schemas.extraction import ExtractionResult

async def extract_structured_meeting_data(raw_content: str) -> ExtractionResult:
    """Extract structured data from raw meeting content using OpenAI."""
    return await openai_client.extract_meeting_data(raw_content)