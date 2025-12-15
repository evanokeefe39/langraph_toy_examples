import asyncio
import json
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from toy_agent import create_graph, AgentDeps, InMemoryCanvas

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory session store
# In production, use Redis or a proper database
SESSIONS: Dict[str, AgentDeps] = {}

class Message(BaseModel):
    role: str
    content: str
    
class ChatRequest(BaseModel):
    messages: List[Message]
    id: str = "default" # Session ID

def get_or_create_session(session_id: str) -> AgentDeps:
    if session_id not in SESSIONS:
        canvas_repo = InMemoryCanvas()
        SESSIONS[session_id] = AgentDeps(canvas=canvas_repo)
    return SESSIONS[session_id]

@app.post("/api/chat")
async def chat(request: ChatRequest):
    async def event_generator():
        # Simulate thinking
        reasoning_steps = [
            "Analyzing user request...",
            "Checking knowledge base...",
            "Identifying relevant documentation...",
            "Formulating response..."
        ]
        
        for step in reasoning_steps:
            await asyncio.sleep(0.5)
            # Send reasoning chunk
            data = {"type": "reasoning_chunk", "text": f"{step}\n"}
            yield json.dumps(data) + "\n"

        # Simulate sources finding
        await asyncio.sleep(0.5)
        sources = [
            {"title": "FastAPI Documentation", "url": "https://fastapi.tiangolo.com/"},
            {"title": "React Docs", "url": "https://react.dev/"}
        ]
        yield json.dumps({"type": "sources", "data": sources}) + "\n"

        # Simulate content generation
        response_text = "I can help you with that! This response is streaming from the FastAPI backend. \n\nWe are mocking the connection to demonstrate: \n1. Reasoning states\n2. Real-time streaming\n3. Source citation"
        
        for char in response_text:
            await asyncio.sleep(0.02)
            yield json.dumps({"type": "content_chunk", "text": char}) + "\n"

        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
