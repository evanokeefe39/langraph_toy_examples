import asyncio
import json
import os
from typing import Literal, List, TypedDict, Annotated, Optional, Tuple, Union, Protocol, Any
from uuid import uuid4
from dataclasses import dataclass, field

from dotenv import load_dotenv

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import ToolMessage, AIMessage, BaseMessage
from langchain_core.callbacks import dispatch_custom_event, adispatch_custom_event
import operator

# --- 0. Mocks & Setup ---
load_dotenv()

# --- 1. Repository & Data Models ---

class CanvasRepository(Protocol):
    def get_state(self) -> dict:
        ...
    
    def add_node(self, node: dict) -> None:
        ...
    
    def add_edge(self, edge: dict) -> None:
        ...

@dataclass
class InMemoryCanvas:
    nodes: List[dict] = field(default_factory=list)
    edges: List[dict] = field(default_factory=list)

    def get_state(self) -> dict:
        return {
            "nodes": self.nodes,
            "edges": self.edges
        }

    def add_node(self, node: dict) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: dict) -> None:
        self.edges.append(edge)

@dataclass
class AgentDeps:
    canvas: CanvasRepository

# --- 2. Shared Models ---

class Plan(BaseModel):
    """The plan of action."""
    steps: List[str] = Field(description="Sequential list of steps to follow.")

class Response(BaseModel):
    """Final response to the user."""
    response: str

class PlanExecuteState(TypedDict):
    input: str
    plan: list[str]
    past_steps: Annotated[list[tuple[str, str]], operator.add]
    response: Optional[str]
    # For the internal executor agent:
    executor_messages: Annotated[List[BaseMessage], add_messages] 
    # Logic: referencing an object ID or similar could be better, 
    # but for this toy example we will assume 'deps' are injected at runtime via config
    # or just accessible via scope if we keep it simple. 
    # BETTER: generic "deps" or "context" key isn't standard in typeddict unless we put it there.
    # We will pass the 'canvas' instance via the 'configurable' config in LangGraph.

class RePlan(BaseModel):
    """The updated plan or final response."""
    response: Optional[str] = Field(description="Final answer to user if done.")
    plan: Optional[List[str]] = Field(description="New sequential list of remaining steps.")


# --- 3. The Agents ---

# -- Planner Agent --
planner_agent = Agent(
    'openai:gpt-4o',
    deps_type=AgentDeps,
    output_type=Plan,
)

@planner_agent.system_prompt
def planner_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    canvas_state = json.dumps(ctx.deps.canvas.get_state())
    return (
        "You are a Graph Construction Planner."
        f"\nCurrent Canvas: {canvas_state}"
        "\nYour job is to break down the user's request into a strict sequence of steps."
        "\nThe available tools for execution are:"
        "\n- add_node(type, label)"
        "\n- connect_nodes(source_label, target_label)"
        "\nBe explicit about node labels and types."
        "\nIMPORTANT: Check the Current Canvas. If a requested node already exists, do not plan to add it."
    )

# -- Executor Agent --
executor_agent = Agent(
    'openai:gpt-4o',
    deps_type=AgentDeps,
)

@executor_agent.system_prompt
def executor_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    canvas_state = json.dumps(ctx.deps.canvas.get_state())
    return (
        "You are a Graph Tool Executor."
        f"\nCurrent Canvas: {canvas_state}" 
        "\nYour goal is to execute the given task using the available tools."
        "\nIf you cannot perform the action, explain why."
    )

@executor_agent.tool
def tool_add_node(ctx: RunContext[AgentDeps], type: str, label: str) -> str:
    """
    Add a new node to the graph.
    
    Args:
        type: The type of node (e.g., 'source', 'process', 'sink', 'database', 'twitter').
        label: A unique descriptive name for the node.
    """
    new_id = str(uuid4())
    node = {"id": new_id, "type": type, "label": label}
    ctx.deps.canvas.add_node(node)
    
    # Emit custom event for UI visibility
    dispatch_custom_event(
        "custom_tool_call",
        {
            "toolName": "add_node",
            "input": {"type": type, "label": label},
            "output": {"id": new_id, "status": "success"}
        }
    )
    
    return json.dumps({"status": "success", "msg": f"Added node '{label}'", "id": new_id})

@executor_agent.tool
def tool_connect_nodes(ctx: RunContext[AgentDeps], source_label: str, target_label: str) -> str:
    """
    Connect two existing nodes by their labels.
    
    Args:
        source_label: The label of the starting node.
        target_label: The label of the destination node.
    """
    state_snap = ctx.deps.canvas.get_state()
    nodes = state_snap["nodes"]
    
    # Helper to find IDs by label
    s_node = next((n for n in nodes if n['label'].lower() == source_label.lower()), None)
    t_node = next((n for n in nodes if n['label'].lower() == target_label.lower()), None)
    
    if not s_node:
        return f"Error: Source node '{source_label}' not found."
    if not t_node:
        return f"Error: Target node '{target_label}' not found."
    
    edge = {"source": s_node['id'], "target": t_node['id']}
    ctx.deps.canvas.add_edge(edge)
    
    # Emit custom event for UI visibility
    dispatch_custom_event(
        "custom_tool_call",
        {
            "toolName": "connect_nodes",
            "input": {"source_label": source_label, "target_label": target_label},
            "output": {"status": "success"}
        }
    )
    
    return json.dumps({"status": "success", "msg": f"Connected {source_label} to {target_label}"})

# -- Replanner Agent --
replanner_agent = Agent(
    'openai:gpt-4o',
    deps_type=AgentDeps,
    output_type=RePlan,
)

@replanner_agent.system_prompt
def replanner_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    canvas_state = json.dumps(ctx.deps.canvas.get_state())
    return (
        "You are a Replanner."
        f"\nCurrent Canvas: {canvas_state}"
        "\nReview the original goal, the steps completed so far, and the result of the last step."
        "\nCheck if the goal is FULLY satisfied. Do not stop if there are missing connections or nodes."
        "\nIf steps remain, provide them in the 'plan' field and leave 'response' empty."
        "\nOnly provide a 'response' when the task is 100% complete and verified against the canvas state."
        "\nIMPORTANT: Do not plan to add nodes that are already present in the Current Canvas."
    )


# --- 4. Logic & Graph Construction ---

def create_graph(deps: AgentDeps):
    
    # -- Node Implementations (closing over deps) --
    
    async def planner_node(state: PlanExecuteState):
        print("  ... [Planner] Creating plan ...")
        await adispatch_custom_event("custom_reasoning", {"text": "[Planner] Creating plan based on request..."})
        result = await planner_agent.run(state['input'], deps=deps)
        print(f"  ... [Planner] Plan: {result.output.steps}")
        await adispatch_custom_event("custom_reasoning", {"text": f"[Planner] Plan created with {len(result.output.steps)} steps."})
        return {"plan": result.output.steps}

    async def executor_step_node(state: PlanExecuteState):
        if not state['plan']:
            print("  ... [Executor] No steps left in plan.")
            return {"past_steps": []}
            
        step_to_execute = state['plan'][0]
        print(f"  ... [Executor] Executing step: '{step_to_execute}' ...")
        await adispatch_custom_event("custom_reasoning", {"text": f"[Executor] Executing step: '{step_to_execute}'"})
        
        result = await executor_agent.run(step_to_execute, deps=deps)
        output = result.output 
        
        print(f"  ... [Executor] Result: {output}")
        return {
            "past_steps": [(step_to_execute, str(output))] 
        }

    async def replanner_node(state: PlanExecuteState):
        print("  ... [Replanner] Reviewing progress ...")
        await adispatch_custom_event("custom_reasoning", {"text": "[Replanner] Reviewing progress..."})
        prompt = f"""
        Original Input: {state['input']}
        Original Plan: {state['plan']}
        Past Steps and Results: {state['past_steps']}
        
        Update the plan or finish.
        """
        
        result = await replanner_agent.run(prompt, deps=deps)
        decision = result.output
        
        if decision.response:
            print(f"  ... [Replanner] Done! Response: {decision.response}")
            return {"response": decision.response, "plan": []}
        else:
            print(f"  ... [Replanner] New Plan: {decision.plan}")
            return {"plan": decision.plan}

    def planner_edge(state: PlanExecuteState):
        if state.get("response"):
            return END
        return "executor" 

    # -- Graph Definition --
    
    workflow = StateGraph(PlanExecuteState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_step_node)
    workflow.add_node("re_planner", replanner_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "re_planner")
    workflow.add_conditional_edges("re_planner", planner_edge)

    return workflow.compile()

# --- 5. CLI Runner ---

def render_canvas(canvas: CanvasRepository):
    """Helper to visualize the graph in ASCII"""
    state = canvas.get_state()
    nodes = state["nodes"]
    edges = state["edges"]
    
    print("\n" + "="*40)
    print("      CURRENT CANVAS STATE      ")
    print("="*40)
    if not nodes:
        print("(Empty)")
    else:
        print(f"Nodes ({len(nodes)}):")
        for n in nodes:
            print(f"  [{n['type'].upper()}] {n['label']} (ID: {n['id'][:4]}..)")
        
        print(f"\nEdges ({len(edges)}):")
        for e in edges:
            print(f"  {e['source'][:4]}.. --> {e['target'][:4]}..")
    print("="*40 + "\n")

async def main():
    print("Welcome to the Plan-and-Execute Toy Agent!")
    print("Try: 'Create a twitter source, filter it, and sink to database'")
    
    # Initialize State
    canvas_repo = InMemoryCanvas()
    deps = AgentDeps(canvas=canvas_repo)
    
    # Build Graph with Deps
    app = create_graph(deps)
    
    while True:
        render_canvas(canvas_repo)
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]:
            break
            
        print("\n--- Agent Loop Started ---")
        
        # Prepare Input
        inputs = {
            "input": user_input,
            "plan": [],
            "past_steps": []
        }
        
        # Run Graph
        async for event in app.astream(inputs):
            pass
            
        print("--- Agent Loop Finished ---\n")
        print("(Type 'exit' to quit)")

if __name__ == "__main__":
    asyncio.run(main())