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
        # Setup the plan
        plan_steps = [
            "Add a node with type 'twitter' and label 'Twitter'",
            "Add a node with type 'process' and label 'Filter'",
            "Add a node with type 'sink' and label 'Database'",
            "Connect the 'Twitter' node to the 'Filter' node",
            "Connect the 'Filter' node to the 'Database' node"
        ]
        
        # 1. Planner Phase
        await asyncio.sleep(0.5)
        yield json.dumps({"type": "reasoning_chunk", "text": "[Planner] Creating plan based on request...\n"}) + "\n"
        await asyncio.sleep(0.4)
        yield json.dumps({"type": "reasoning_chunk", "text": f"[Planner] Plan: {json.dumps(plan_steps)}\n"}) + "\n"
        
        # Send Initial Plan
        yield json.dumps({
            "type": "tasks", 
            "data": [{"title": "Execution Plan", "items": plan_steps}]
        }) + "\n"

        # 2. Execution Loop
        for i, step in enumerate(plan_steps):
            await asyncio.sleep(0.5)
            yield json.dumps({"type": "reasoning_chunk", "text": f"[Executor] Executing step: '{step}' ...\n"}) + "\n"
            
            # Simulate Tool Call
            tool_name = "connect_nodes" if "Connect" in step else "add_node"
            tool_id = f"call_{i}"
            
            # Construct args based on step text (mock parsing)
            if "Twitter" in step:
                args = {"type": "source", "label": "Twitter"}
            elif "Filter" in step:
                args = {"type": "process", "label": "Filter"}
            elif "Database" in step:
                args = {"type": "sink", "label": "Database"}
            elif "Twitter" in step and "Filter" in step:
                args = {"source_label": "Twitter", "target_label": "Filter"}
            elif "Filter" in step and "Database" in step:
                args = {"source_label": "Filter", "target_label": "Database"}
            else:
                args = {}

            # Emit Tool Call (Running)
            yield json.dumps({
                "type": "tool_call",
                "tool": {
                    "type": "tool-call",
                    "toolCallId": tool_id,
                    "toolName": tool_name,
                    "args": args,
                    "state": "input-available"
                }
            }) + "\n"
            
            await asyncio.sleep(1.0)
            
            # Emit Tool Result (Completed)
            result_data = {"status": "success", "id": f"node-{i}"} if tool_name == "add_node" else {"status": "success", "msg": "Connected"}
            yield json.dumps({
                "type": "tool_call",
                "tool": {
                    "type": "tool-result",
                    "toolCallId": tool_id,
                    "toolName": tool_name,
                    "args": args,
                    "result": json.dumps(result_data),
                    "state": "output-available"
                }
            }) + "\n"

            # Update Plan (Mark current as done)
            await asyncio.sleep(0.2)
            updated_items = []
            for j, s in enumerate(plan_steps):
                if j <= i:
                    updated_items.append(f"✅ {s}")
                else:
                    updated_items.append(s)
            
            yield json.dumps({
                "type": "tasks", 
                "data": [{"title": "Execution Plan", "items": updated_items}]
            }) + "\n"

            yield json.dumps({"type": "reasoning_chunk", "text": "[Replanner] Reviewing progress ...\n"}) + "\n"
        
        # 3. Final Response
        await asyncio.sleep(0.5)
        response_text = "The task is complete. The Twitter data source has been added, filtered, and connected to the database as outlined in the original input."
        
        for char in response_text:
            await asyncio.sleep(0.01)
            yield json.dumps({"type": "content_chunk", "text": char}) + "\n"

        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
