# Draft service
from app.db.models.draft import Draft, DraftStatus
from app.db.models.extracted_item import ExtractedItem
from app.db.session import SessionLocal
from app.domain.schemas.extraction import ExtractionResult
from app.integrations.slack_client import slack_client
from app.domain.services.canvas_composer import create_draft_canvas
from datetime import datetime

async def create_draft(owner_user_id: str, source_id: str, extraction: ExtractionResult) -> Draft:
    """Create a draft from extraction."""
    canvas_content = create_draft_canvas(extraction)
    
    # Upload to Slack as private canvas
    file = await slack_client.upload_canvas(
        channels="",  # Private
        content=canvas_content,
        title=f"Action Canvas Draft — {datetime.now().strftime('%Y-%m-%d')}"
    )
    
    db = SessionLocal()
    try:
        draft = Draft(
            owner_user_id=owner_user_id,
            source_id=source_id,
            slack_canvas_id=file["id"],
            title=file["title"],
            status=DraftStatus.draft,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        # Save extracted items
        for item in extraction.action_items + extraction.decisions + extraction.open_questions + extraction.risks:
            extracted_item = ExtractedItem(
                draft_id=draft.id,
                item_type=item.__class__.__name__.lower(),  # e.g., action_item
                content=item.content if hasattr(item, 'content') else str(item),
                confidence=getattr(item, 'confidence', 'high'),
                assignee=getattr(item, 'owner', None),
                due_date=getattr(item, 'due_date', None),
                created_at=datetime.utcnow()
            )
            db.add(extracted_item)
        db.commit()
        
        return draft
    finally:
        db.close()