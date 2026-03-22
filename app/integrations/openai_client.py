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
            "meeting_title: string\n"
            "summary: string\n"
            "what_happened: string\n"
            "status_summary: string\n"
            "priority_focus: string\n"
            "next_review_date: ISO date or null\n"
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

        content = self._request_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured project execution "
                        "data from meeting notes."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return ExtractionResult.model_validate(json.loads(content))

    def generate_followthru_reply(
        self,
        messages: list[dict[str, str]],
        user_input: str,
    ) -> str:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY or OPENAI_API_KEY is not configured.")

        conversation = [
            {
                "role": "system",
                "content": (
                    "You are FollowThru, a concise delivery execution assistant. "
                    "Help users turn notes into action canvases, "
                    "summarize execution status, and explain how to preview, "
                    "draft, or publish workflow output. "
                    "Do not pretend actions were published unless the tool path "
                    "already did it."
                ),
            },
            *messages[-10:],
            {"role": "user", "content": user_input},
        ]
        return self._request_chat_completion(
            messages=conversation,
            temperature=0.2,
        )

    def _request_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict | None = None,
    ) -> str:
        payload = {
            "model": settings.resolved_llm_model,
            "temperature": temperature,
            "messages": messages,
        }
        if response_format:
            payload["response_format"] = response_format

        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            payload = response.json()

        return self._extract_message_content(payload)

    def _extract_message_content(self, payload: dict) -> str:
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        return content


openai_client = OpenAIClient()
