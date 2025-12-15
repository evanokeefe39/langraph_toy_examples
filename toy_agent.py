import asyncio
import json
import os
from typing import Literal, List, TypedDict, Annotated, Optional, Tuple, Union
from uuid import uuid4

from dotenv import load_dotenv

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import ToolMessage, AIMessage, BaseMessage

# --- 0. Mocks & Setup ---
load_dotenv()

# Mock Data Store (The "Canvas")
CANVAS_DB = {
    "nodes": [],
    "edges": []
}

def render_canvas():
    """Helper to visualize the graph in ASCII"""
    print("\n" + "="*40)
    print("      CURRENT CANVAS STATE      ")
    print("="*40)
    if not CANVAS_DB["nodes"]:
        print("(Empty)")
    else:
        print(f"Nodes ({len(CANVAS_DB['nodes'])}):")
        for n in CANVAS_DB["nodes"]:
            print(f"  [{n['type'].upper()}] {n['label']} (ID: {n['id'][:4]}..)")
        
        print(f"\nEdges ({len(CANVAS_DB['edges'])}):")
        for e in CANVAS_DB["edges"]:
            print(f"  {e['source'][:4]}.. --> {e['target'][:4]}..")
    print("="*40 + "\n")

# --- 1. Data Models ---

class Plan(BaseModel):
    """The plan of action."""
    steps: List[str] = Field(description="Sequential list of steps to follow.")

class Response(BaseModel):
    """Final response to the user."""
    response: str

class PlanExecuteState(TypedDict):
    input: str
    plan: list[str]
    past_steps: list[tuple[str, str]]
    response: Optional[str]
    # For the internal executor agent:
    executor_messages: Annotated[List[BaseMessage], add_messages] 

# --- 2. The Tools (Native PydanticAI) ---

# Define the Executor Agent globally so we can register tools
executor_agent = Agent(
    'openai:gpt-4o',
    deps_type=RunContext,
)

@executor_agent.system_prompt
def block_executor_system_prompt(ctx: RunContext) -> str:
    return (
        "You are a Graph Tool Executor."
        f"\nCurrent Canvas: {json.dumps(CANVAS_DB)}" 
        "\nYour goal is to execute the given task using the available tools."
        "\nIf you cannot perform the action, explain why."
    )

# We use the deps_type=None default for now, purely functional tools
@executor_agent.tool
def tool_add_node(ctx: RunContext, type: str, label: str) -> str:
    """
    Add a new node to the graph.
    
    Args:
        type: The type of node (e.g., 'source', 'process', 'sink', 'database', 'twitter').
        label: A unique descriptive name for the node.
    """
    new_id = str(uuid4())
    node = {"id": new_id, "type": type, "label": label}
    CANVAS_DB["nodes"].append(node)
    return json.dumps({"status": "success", "msg": f"Added node '{label}'", "id": new_id})

@executor_agent.tool
def tool_connect_nodes(ctx: RunContext, source_label: str, target_label: str) -> str:
    """
    Connect two existing nodes by their labels.
    
    Args:
        source_label: The label of the starting node.
        target_label: The label of the destination node.
    """
    # Helper to find IDs by label
    s_node = next((n for n in CANVAS_DB["nodes"] if n['label'].lower() == source_label.lower()), None)
    t_node = next((n for n in CANVAS_DB["nodes"] if n['label'].lower() == target_label.lower()), None)
    
    if not s_node:
        return f"Error: Source node '{source_label}' not found."
    if not t_node:
        return f"Error: Target node '{target_label}' not found."
    
    edge = {"source": s_node['id'], "target": t_node['id']}
    CANVAS_DB["edges"].append(edge)
    return json.dumps({"status": "success", "msg": f"Connected {source_label} to {target_label}"})


# --- 3. Node A: The Planner ---

async def planner_node(state: PlanExecuteState):
    print("  ... [Planner] Creating plan ...")
    agent = Agent(
        'openai:gpt-4o',
        output_type=Plan,
        system_prompt=(
            "You are a Graph Construction Planner."
            f"\nCurrent Canvas: {json.dumps(CANVAS_DB)}"
            "\nYour job is to break down the user's request into a strict sequence of steps."
            "\nThe available tools for execution are:"
            "\n- add_node(type, label)"
            "\n- connect_nodes(source_label, target_label)"
            "\nBe explicit about node labels and types."
            "\nIMPORTANT: Check the Current Canvas. If a requested node already exists, do not plan to add it."
        )
    )
    
    result = await agent.run(state['input'])
    print(f"  ... [Planner] Plan: {result.output.steps}")
    return {"plan": result.output.steps}

# --- 4. Node B: The Executor (Step Solver) ---

async def executor_step_node(state: PlanExecuteState):
    # This node executes the *first* step in the plan
    step_to_execute = state['plan'][0]
    print(f"  ... [Executor] Executing step: '{step_to_execute}' ...")
    
    # Run the native PydanticAI executor agent
    # The dynamic system prompt (registered below or above) will inject the current state.
    
    result = await executor_agent.run(step_to_execute)
    output = result.output # Expecting str by default if no output_type
    
    print(f"  ... [Executor] Result: {output}")
    
    return {
        "past_steps": [(step_to_execute, str(output))] # Cast to str just in case
    }

# --- 5. Node C: The Re-Planner ---

class RePlan(BaseModel):
    """The updated plan or final response."""
    response: Optional[str] = Field(description="Final answer to user if done.")
    plan: Optional[List[str]] = Field(description="New sequential list of remaining steps.")

async def replanner_node(state: PlanExecuteState):
    print("  ... [Replanner] Reviewing progress ...")
    
    agent = Agent(
        'openai:gpt-4o',
        output_type=RePlan,
        system_prompt=(
            "You are a Replanner."
            f"\nCurrent Canvas: {json.dumps(CANVAS_DB)}"
            "\nReview the original goal, the steps completed so far, and the result of the last step."
            "\nUpdate the plan if necessary. If the task is substantially complete, provide a final response."
            "\nIf more steps are needed, provide the *remaining* steps."
            "\nIMPORTANT: Do not plan to add nodes that are already present in the Current Canvas."
        )
    )
    
    prompt = f"""
    Original Input: {state['input']}
    Original Plan: {state['plan']}
    Past Steps and Results: {state['past_steps']}
    
    Update the plan or finish.
    """
    
    result = await agent.run(prompt)
    decision = result.output # Wait, user said .output?
    # I need to use .output based on visual evidence from previous turns.
    
    if decision.response:
        print(f"  ... [Replanner] Done! Response: {decision.response}")
        return {"response": decision.response, "plan": []}
    else:
        print(f"  ... [Replanner] New Plan: {decision.plan}")
        return {"plan": decision.plan}

# --- 6. Logic & Graph ---

def planner_edge(state: PlanExecuteState):
    if state.get("response"):
        return END
    return "executor" # execute first step

workflow = StateGraph(PlanExecuteState)
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_step_node)
workflow.add_node("re_planner", replanner_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "executor")
workflow.add_edge("executor", "re_planner")
workflow.add_conditional_edges("re_planner", planner_edge)

app = workflow.compile()

# --- 7. CLI Runner ---

async def main():
    print("Welcome to the Plan-and-Execute Toy Agent!")
    print("Try: 'Create a twitter source, filter it, and sink to database'")
    
    while True:
        render_canvas()
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