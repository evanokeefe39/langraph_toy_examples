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
    allow_origins=["http://localhost:3000"],
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
    # Dummy Endpoint for UI Verification
    async def event_generator():
        # Simulate Planning (Thinking/Reasoning)
        await asyncio.sleep(0.5)
        yield "\n[Reasoning]: I need to create a source and sink as requested.\n"
        
        await asyncio.sleep(1)
        yield "\n[Plan]: ['Add Twitter Source', 'Add Database Sink', 'Connect them']\n"
        
        # Simulate Execution
        await asyncio.sleep(1)
        yield "\n[Tool Call]: add_node(type='source', label='Twitter')\n"
        await asyncio.sleep(0.5)
        yield "\n[Result]: Node 'Twitter' added (ID: 1234)\n"
        
        await asyncio.sleep(1)
        yield "\n[Tool Call]: add_node(type='sink', label='Postgres')\n"
        await asyncio.sleep(0.5)
        yield "\n[Result]: Node 'Postgres' added (ID: 5678)\n"
        
        # Final Response
        await asyncio.sleep(1)
        yield "\n[Final]: I have created the Twitter source and Postgres sink and connected them.\n"

    return StreamingResponse(event_generator(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
