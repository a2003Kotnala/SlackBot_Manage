import json

import httpx

from app.config import settings
from app.domain.schemas.extraction import ExtractionResult


class OpenAIClient:
    def __init__(self) -> None:
        self.base_url = settings.resolved_llm_base_url

    def is_configured(self) -> bool:
        return bool(settings.llm_api_key)

    def extract_meeting_data(self, raw_content: str) -> ExtractionResult:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY or OPENAI_API_KEY is not configured.")

        prompt = (
            "Extract structured meeting data from the notes below.\n"
            "Return valid JSON with these keys:\n"
            "summary: string\n"
            "what_happened: string\n"
            "decisions: array of {content, confidence}\n"
            "action_items: array of {content, owner, due_date, confidence}\n"
            "owners: array of strings\n"
            "due_dates: array of ISO dates\n"
            "open_questions: array of {content, confidence}\n"
            "risks: array of {content, confidence}\n"
            "confidence_overall: high|medium|low|needs_review\n"
            "Do not invent owners or dates. Use null when not stated.\n\n"
            f"Meeting notes:\n{raw_content}"
        )

        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.resolved_llm_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You extract structured project execution "
                                "data from meeting notes."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()

        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )

        return ExtractionResult.model_validate(json.loads(content))


openai_client = OpenAIClient()
