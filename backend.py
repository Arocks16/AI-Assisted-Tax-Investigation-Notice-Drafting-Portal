# LangGraph workflow for Phase 1 (Investigation) + Phase 2 (Notice Drafting & Refinement)
# Flow:
#   Phase 1: load_documents → investigate → generate_report → ao_review (interrupt)
#       → template_drafting (if AO approves) | close_case (if AO rejects)
#   Phase 2: template_drafting → ao_review_notice (interrupt)
#       → refine_notice ←→ template_drafting (loop)  |  apply_dsc → END (on approval)

import os
import uuid
from typing import TypedDict
import pandas as pd
from langgraph.types import interrupt
from prompts import investigation_prompt, drafting_prompt, refinement_prompt
from llm import llm
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

_DIR = os.path.dirname(os.path.abspath(__file__))


class State(TypedDict):
    """Shared state passed between graph nodes."""
    itr_text: str
    form16_text: str
    ais_text: str
    investigation: str
    report: str
    ao_decision: str
    # Phase 2 fields
    draft_notice_text: str
    ao_feedback: str
    din: str


def load_documents(state):
    """Read ITR, Form 16, and AIS from Excel files. Convert to markdown."""
    itr = pd.read_excel(os.path.join(_DIR, "ITR.xlsx"), sheet_name=None)
    state["itr_text"] = "\n\n".join(f"## {n}\n{d.to_markdown(index=False)}" for n, d in itr.items())
    f16 = pd.read_excel(os.path.join(_DIR, "Form16.xlsx"))
    state["form16_text"] = f16.to_markdown(index=False)
    ais = pd.read_excel(os.path.join(_DIR, "AIS.xlsx"), sheet_name=None)
    state["ais_text"] = "\n\n".join(f"## {n}\n{d.to_markdown(index=False)}" for n, d in ais.items())
    return state


def investigate(state):
    """Call LLM to identify discrepancies between ITR, Form 16, and AIS."""
    state["investigation"] = llm.invoke(
        investigation_prompt.format(
            itr=state["itr_text"], form16=state["form16_text"], ais=state["ais_text"]
        )
    )
    return state


def generate_report(state):
    """Call LLM to format the investigation into a structured report."""
    state["report"] = llm.invoke(f"""
    Based on the investigation findings below, generate a structured markdown
    Tax Investigation Report.

    Include:
    # Taxpayer Details - Name, PAN, Assessment Year
    # Executive Summary
    # Critical Issues - markdown table: Issue ID | Discrepancy Type | Description | Source Documents | Severity
    # Detailed Findings - For each issue: Description, Values observed, Source documents, Reason for flagging

    Investigation Findings:
    {state["investigation"]}
    """)
    return state


def ao_review(state):
    """Phase 1 interrupt — pause for AO decision on investigation report."""
    response = interrupt({"report": state["report"], "question": "Initiate Draft Notice?"})
    return {"ao_decision": response["answer"]}


def route(state):
    """Phase 1 conditional: yes → Phase 2 entry, no → close case."""
    return "template_drafting" if state["ao_decision"] == "yes" else "close_case"


def template_drafting(state):
    """Phase 2 — LLM drafts Section 142(1) scrutiny notice from the report."""
    state["draft_notice_text"] = llm.invoke(
        drafting_prompt.format(report=state["report"])
    )
    return state


def ao_review_notice(state):
    """Phase 2 interrupt — pause for AO feedback on the draft notice."""
    response = interrupt({
        "draft_notice": state["draft_notice_text"],
        "question": "Provide feedback or leave blank to approve."
    })
    return {"ao_feedback": response.get("feedback", "")}


def route_notice(state):
    """Phase 2 conditional: empty feedback → approve, non-empty → refine."""
    return "apply_dsc" if state["ao_feedback"] == "" else "refine_notice"


def refine_notice(state):
    """LLM revises the notice based on AO's feedback."""
    state["draft_notice_text"] = llm.invoke(
        refinement_prompt.format(notice=state["draft_notice_text"], feedback=state["ao_feedback"])
    )
    return state


def apply_dsc(state):
    """Generate dummy DIN and finalise the case."""
    state["din"] = f"DIN-ITBA-2025-{uuid.uuid4().hex[:6].upper()}"
    print(f"AO Action: Notice Approved — DIN {state['din']}")
    return state


def close_case(state):
    """Terminal — AO rejected issues, case closed."""
    print("Case has been closed.")
    return state


# ── Build the graph ──────────────────────────────────────

builder = StateGraph(State)

builder.add_node("load_documents", load_documents)
builder.add_node("investigate", investigate)
builder.add_node("generate_report", generate_report)
builder.add_node("ao_review", ao_review)
builder.add_node("template_drafting", template_drafting)
builder.add_node("ao_review_notice", ao_review_notice)
builder.add_node("refine_notice", refine_notice)
builder.add_node("apply_dsc", apply_dsc)
builder.add_node("close_case", close_case)

builder.set_entry_point("load_documents")

builder.add_edge("load_documents", "investigate")
builder.add_edge("investigate", "generate_report")
builder.add_edge("generate_report", "ao_review")

builder.add_conditional_edges("ao_review", route, {
    "template_drafting": "template_drafting",
    "close_case": "close_case",
})

builder.add_edge("template_drafting", "ao_review_notice")

builder.add_conditional_edges("ao_review_notice", route_notice, {
    "apply_dsc": "apply_dsc",
    "refine_notice": "refine_notice",
})

builder.add_edge("refine_notice", "template_drafting")
builder.add_edge("apply_dsc", END)
builder.add_edge("close_case", END)

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)