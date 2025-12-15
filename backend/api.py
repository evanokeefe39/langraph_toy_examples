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

from uuid import uuid4

@app.post("/api/chat")
async def chat(request: ChatRequest):
    async def event_generator():
        deps = get_or_create_session(request.id)
        agent_app = create_graph(deps)
        
        inputs = {
            "input": request.messages[-1].content,
            "plan": [],
            "past_steps": []
        }
        
        all_past_steps = []
        current_remaining_plan = []
        
        # Use v2 for custom events support
        async for event in agent_app.astream_events(inputs, version="v2"):
            kind = event["event"]
            name = event.get("name")
            data = event.get("data", {})
            
            # --- Custom Events (Reasoning & Tools) ---
            if kind == "on_custom_event":
                if name == "custom_reasoning":
                    text = data.get("text")
                    if text:
                        yield json.dumps({"type": "reasoning_chunk", "text": text + "\n"}) + "\n"
                        
                elif name == "custom_tool_call":
                    # We get the full tool execution info at once
                    tool_name = data.get("toolName")
                    tool_input = data.get("input")
                    tool_output = data.get("output")
                    
                    # Generate a unique ID for the UI
                    tool_call_id = f"call_{uuid4().hex[:8]}"
                    
                    # 1. Emit Input
                    yield json.dumps({
                        "type": "tool_call",
                        "tool": {
                            "type": "tool-call",
                            "toolCallId": tool_call_id,
                            "toolName": tool_name,
                            "input": tool_input,
                            "state": "input-available"
                        }
                    }) + "\n"
                    
                    # 2. Emit Output
                    yield json.dumps({
                        "type": "tool_call",
                        "tool": {
                            "type": "tool-result",
                            "toolCallId": tool_call_id,
                            "toolName": tool_name,
                            "input": tool_input,
                            "result": json.dumps(tool_output),
                            "state": "output-available"
                        }
                    }) + "\n"

            # --- State Updates (Plan Tracking) ---
            if kind == "on_chain_end":
                output = data.get("output")
                
                if name == "planner" and output and "plan" in output:
                    current_remaining_plan = output["plan"]
                    # Initial Plan
                    yield json.dumps({
                        "type": "tasks", 
                        "data": [{"title": "Execution Plan", "items": current_remaining_plan}]
                    }) + "\n"

                elif name == "executor" and output and "past_steps" in output:
                    # Capture completed steps
                    # output['past_steps'] is a list of tuples (step, result)
                    # Since it's a delta update, we typically see just the executed step
                    new_steps = output["past_steps"]
                    if isinstance(new_steps, list):
                        all_past_steps.extend(new_steps)

                elif name == "re_planner" and output:
                    if "plan" in output:
                        current_remaining_plan = output["plan"]
                        
                        # Reconstruct Full Plan View
                        # Completed steps (checked) + Remaining steps (unchecked)
                        # Extract just the step text from past_steps tuple (step, result)
                        completed_items = [f"✅ {s[0]}" for s in all_past_steps]
                        
                        full_plan = completed_items + current_remaining_plan
                        
                        yield json.dumps({
                            "type": "tasks", 
                            "data": [{"title": "Execution Plan", "items": full_plan}]
                        }) + "\n"

        # --- Final Response & Graph State ---
        canvas_state = deps.canvas.get_state()
        final_msg = "\n\n**Execution Complete.**\n\nFinal Graph State:\n"
        final_msg += f"```json\n{json.dumps(canvas_state, indent=2)}\n```"
        
        yield json.dumps({"type": "content_chunk", "text": final_msg}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
    
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
