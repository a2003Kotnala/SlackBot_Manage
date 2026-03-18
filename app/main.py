from fastapi import FastAPI
from app.api.routes import health, slack_commands, slack_interactions
from app.config import settings
from app.logger import logger

app = FastAPI(title="ZManage", version="1.0.0")

# Include routes
app.include_router(health.router)
app.include_router(slack_commands.router)
app.include_router(slack_interactions.router)

# Mount Slack Bolt app (for Slack events)
# Note: Bolt handles its own routing; integrate as needed

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
