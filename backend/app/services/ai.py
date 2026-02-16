"""OpenAI integration and workflow JSON extraction."""

import json
import re
from typing import List, Tuple, Optional

from sqlalchemy.orm import Session

from app.models import Message, WorkflowState
from app.services.workflow import ensure_workflow_state

# System prompt and conversation building are pure functions; no DB here.
# Callers pass in message lists and last workflow message.


def build_system_message(workflow_context: str) -> dict:
    """Build the system prompt for the OpenAI conversation."""
    return {
        "role": "system",
        "content": f"""You are a helpful assistant that helps companies design and visualize process workflows. You can communicate in English and Spanish.

    When the user requests a workflow:
    1. Provide a brief explanation of the workflow (1-3 sentences) in the user's language
    2. ALWAYS include the workflow as valid JSON in this exact format: {{"nodes": [{{"id": "1", "label": "Step name", "type": "start|process|decision|end"}}], "edges": [{{"from": "1", "to": "2"}}]}}
    3. NEVER return empty responses - always provide both explanation and JSON{workflow_context}

    Guidelines:
    - For NEW workflows: Create from scratch based on the user's description
    - For UPDATES/MODIFICATIONS:
    * CRITICAL: START WITH THE CURRENT WORKFLOW JSON PROVIDED ABOVE
    * ONLY modify the specific nodes/edges the user explicitly mentioned
    * Copy all other nodes and edges EXACTLY as they appear in the current workflow
    * Preserve all node IDs, labels, types, and edge connections that aren't being changed
    * If updating ONE node label, copy all other nodes with identical IDs and labels
    * If adding ONE node, copy the entire current workflow and append the new node with the next sequential ID
    * If removing ONE node:
      - Remove the node from the nodes array
      - Remove all edges that connect to/from that node
      - If removing a DECISION node that creates branches:
        a) Find all nodes that were AFTER the decision (nodes that the decision pointed to)
        b) Find what came BEFORE the decision (the parent node)
        c) Connect the parent node directly to the FIRST branch path (skip the decision)
        d) Merge the branches back into the main flow at their natural convergence point
        e) Example: A→Decision→[B,C]→D becomes A→B→D (selecting primary branch)
      - Ensure no orphaned nodes (nodes with no path from start)
    * Think of it as copy-paste with minimal edits, not reconstruction
    - Use sequential IDs starting from "1" for NEW workflows
    - MUST include exactly one "start" node and at least one "end" node
    - Use "decision" type for branching points (if/else scenarios)
    - Ensure all edges connect existing node IDs
    - Keep labels clear and concise (max 80 characters)
    - Node labels must be based on user's language: either English or Spanish

    IMPORTANT FOR MODIFICATIONS:
    - When user says "change/cambiar X", "update/actualizar X", "modify/modificar X" - ONLY change X
    - The current workflow is your STARTING POINT - copy it and make minimal edits
    - Do not reorganize, renumber, reorder, or restructure unchanged parts
    - Imagine you're using find-and-replace, not rewriting from scratch
    - Preserve the exact structure and IDs from the current workflow

    SPECIAL CASE - Removing Decision Nodes:
    - When removing a decision node, intelligently merge the branches (parent → primary branch; remove alternate branches if they don't rejoin).

    CRITICAL: EVERY workflow request MUST include valid JSON with at least:
    - One "start" node, one "end" node, at least one connecting edge, proper node IDs (no duplicates).

    Spanish keywords: flujo, diagrama, proceso, flujo de trabajo, flowchart
    English keywords: workflow, flowchart, process, flow

    ALWAYS provide both explanation AND valid JSON. Never provide responses without JSON when a workflow is requested.""",
    }


def build_conversation_history(messages, last_workflow_msg) -> Tuple[List[dict], str]:
    """Build conversation array and workflow context string from message history."""
    conversation = []
    for msg in messages:
        if msg.role == "assistant" and msg.workflow_data:
            content = f"{msg.content}\n\nCurrent workflow JSON:\n{msg.workflow_data}"
            conversation.append({"role": msg.role, "content": content})
        else:
            conversation.append({"role": msg.role, "content": msg.content})

    workflow_context = ""
    if last_workflow_msg and last_workflow_msg.workflow_data:
        workflow_context = (
            f"\n\nCURRENT WORKFLOW (use this as your baseline for any modifications):\n"
            f"{last_workflow_msg.workflow_data}\n\n"
            "When making changes, start with this exact workflow and ONLY modify what the user specifically requests."
        )

    return conversation, workflow_context


def extract_json_workflow(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Try multiple methods to extract a workflow JSON object from AI response text.
    Returns (json_string, full_match_string) or (None, None).
    """
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1))
            if "nodes" in data and "edges" in data:
                return code_block_match.group(1), code_block_match.group(0)
        except (json.JSONDecodeError, ValueError):
            pass

    json_pattern = r"\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}"
    json_matches = list(re.finditer(json_pattern, text, re.DOTALL))
    json_matches.sort(key=lambda m: len(m.group(0)), reverse=True)

    for match in json_matches:
        try:
            data = json.loads(match.group(0))
            if "nodes" in data and "edges" in data:
                if isinstance(data["nodes"], list) and isinstance(data["edges"], list):
                    if len(data["nodes"]) > 0:
                        return match.group(0), match.group(0)
        except (json.JSONDecodeError, ValueError):
            continue

    return None, None


# Fallback workflow when parsing fails or API errors
FALLBACK_WORKFLOW = json.dumps({
    "nodes": [
        {"id": "1", "label": "Start", "type": "start"},
        {"id": "2", "label": "Process Request", "type": "process"},
        {"id": "3", "label": "Decision Point", "type": "decision"},
        {"id": "4", "label": "Complete", "type": "end"},
    ],
    "edges": [
        {"from": "1", "to": "2"},
        {"from": "2", "to": "3"},
        {"from": "3", "to": "4"},
    ],
})

WORKFLOW_KEYWORDS = ["workflow", "flowchart", "process", "flujo", "diagrama"]


def generate_ai_response(
    chat_id: int,
    message_content: str,
    user_message: Message,
    user_id: int,
    username: str,
    db: Session,
) -> Message:
    """
    Call OpenAI, parse workflow JSON, persist assistant message and workflow state.
    Returns the created assistant Message. On API/parse errors, returns a fallback message.
    """
    from openai import OpenAI

    from app.core.config import settings

    client = OpenAI(api_key=settings.openai_api_key, timeout=120.0)

    messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at).all()
    last_workflow_msg = (
        db.query(Message)
        .filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .first()
    )

    conversation, workflow_context = build_conversation_history(messages, last_workflow_msg)
    system_message = build_system_message(workflow_context)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[system_message] + conversation,
            max_completion_tokens=5000,
        )
        ai_content = response.choices[0].message.content
    except Exception as e:
        return _create_fallback_message(chat_id, db, user_id, str(e))

    if not ai_content or not ai_content.strip():
        prev = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        if prev and prev.workflow_data:
            ai_message = Message(
                chat_id=chat_id,
                role="assistant",
                content="I apologize, I encountered an issue generating a response. I've kept your previous workflow intact. Please try rephrasing your request or ask me to create a new workflow.",
                workflow_data=prev.workflow_data,
            )
            db.add(ai_message)
            db.commit()
            db.refresh(ai_message)
            if ai_message.workflow_data:
                ensure_workflow_state(chat_id, ai_message.workflow_data, user_id, db)
            return ai_message
        return _create_fallback_message(chat_id, db, user_id, "Empty AI response")

    workflow_data = None
    display_content = ai_content

    try:
        extracted_json, full_match = extract_json_workflow(ai_content)
        if extracted_json:
            workflow_data = extracted_json
            parsed = json.loads(workflow_data)
            if "nodes" not in parsed or "edges" not in parsed or len(parsed["nodes"]) == 0:
                raise ValueError("Invalid workflow structure")
            display_content = ai_content.replace(full_match, "").strip()
            display_content = re.sub(r"```\s*```", "", display_content).strip()
            display_content = re.sub(r"\n\s*\n\s*\n+", "\n\n", display_content)
            if not display_content or len(display_content) < 10:
                display_content = "I've created a workflow visualization for you based on your requirements. You can see it in the visualization panel on the right."
        else:
            if any(kw in message_content.lower() for kw in WORKFLOW_KEYWORDS):
                workflow_data = json.dumps({
                    "nodes": [
                        {"id": "1", "label": "Start", "type": "start"},
                        {"id": "2", "label": "Process request", "type": "process"},
                        {"id": "3", "label": "Complete", "type": "end"},
                    ],
                    "edges": [{"from": "1", "to": "2"}, {"from": "2", "to": "3"}],
                })
                display_content = ai_content or "I've created a basic workflow structure for you."
    except Exception:
        workflow_data = None

    ai_message = Message(
        chat_id=chat_id,
        role="assistant",
        content=display_content,
        workflow_data=workflow_data,
    )
    db.add(ai_message)
    db.commit()
    db.refresh(ai_message)
    if ai_message.workflow_data:
        ensure_workflow_state(chat_id, ai_message.workflow_data, user_id, db)
    return ai_message


def _create_fallback_message(chat_id: int, db: Session, user_id: int, error_detail: str) -> Message:
    ai_message = Message(
        chat_id=chat_id,
        role="assistant",
        content=f"I can help you design a workflow. Here's a sample process visualization. (Note: OpenAI API is not configured - {error_detail})",
        workflow_data=FALLBACK_WORKFLOW,
    )
    db.add(ai_message)
    db.commit()
    db.refresh(ai_message)
    ensure_workflow_state(chat_id, ai_message.workflow_data, user_id, db)
    return ai_message
