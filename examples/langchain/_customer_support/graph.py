from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import tools_condition

from .agent import Assistant
from .state import State
from .utilities import create_tool_node_with_fallback


def make_graph():
    # Import at call time so we see values set by make_chat_model(db)
    from .agent import part_1_assistant_runnable, part_1_tools

    builder = StateGraph(State)

    # Define nodes: these do the work
    builder.add_node("assistant", Assistant(part_1_assistant_runnable))
    builder.add_node("tools", create_tool_node_with_fallback(part_1_tools))
    # Define edges: these determine how the control flow moves
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges(
        "assistant",
        tools_condition,
    )
    builder.add_edge("tools", "assistant")

    # The checkpointer lets the graph persist its state
    # this is a complete memory for the entire graph.
    memory = InMemorySaver()
    part_1_graph = builder.compile(checkpointer=memory)
    return part_1_graph
