# Streaming Partial Updates — AI + Live UX

This document covers the streaming workflow generation feature: how the AI response is streamed token-by-token, how nodes appear one-by-one on the canvas in real time, and the architectural decisions behind it.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Backend: Incremental JSON Parser](#3-backend-incremental-json-parser)
4. [Backend: SSE Streaming Endpoint](#4-backend-sse-streaming-endpoint)
5. [Frontend: SSE Client](#5-frontend-sse-client)
6. [Frontend: Streaming State Management](#6-frontend-streaming-state-management)
7. [Frontend: Staggered Node Reveal](#7-frontend-staggered-node-reveal)
8. [Frontend: Animations & UX](#8-frontend-animations--ux)
9. [Data Flow (End-to-End)](#9-data-flow-end-to-end)
10. [SSE Event Reference](#10-sse-event-reference)
11. [Files Changed](#11-files-changed)
12. [Design Decisions & Trade-offs](#12-design-decisions--trade-offs)

---

## 1. Overview

### Problem

The original workflow builder waited for the full OpenAI response (3–5 seconds), then rendered the entire graph at once. This created a dead period where the user saw nothing but a loading spinner.

### Solution

The AI response is now **streamed** via Server-Sent Events (SSE). As OpenAI generates tokens:

- **Chat text** appears character-by-character (like ChatGPT)
- **Workflow nodes** drop onto the canvas **one by one** with a staggered delay
- **Edges** fade in the moment both their endpoints are visible
- The camera **auto-pans** to follow the growing graph

The builder feels alive — the user sees progress immediately instead of waiting.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser (Next.js)                                      │
│                                                         │
│  ChatWindow ──fetch POST──▶ /messages/stream            │
│       │                         │                       │
│       │  ◀── SSE: text_chunk ───┤                       │
│       │  ◀── SSE: node_add  ───┤  FastAPI async         │
│       │  ◀── SSE: edge_add  ───┤  generator             │
│       │  ◀── SSE: complete  ───┤                        │
│       ▼                         │                       │
│  page.tsx (state)               │  OpenAI streaming     │
│       │                         │  ──stream=True──▶     │
│       ▼                         │                       │
│  WorkflowVisualization          │  IncrementalWorkflow  │
│   ├─ revealedCount (stagger)    │  Parser detects       │
│   ├─ buildStreamingGraph()      │  nodes/edges as       │
│   └─ fitView() auto-pan        │  tokens arrive        │
│                                 │                       │
└─────────────────────────────────────────────────────────┘
```

**Key technologies:**
- **Server-Sent Events (SSE)** for streaming (via `StreamingResponse`)
- **AsyncOpenAI** client for non-blocking token streaming
- **Incremental JSON parser** for detecting nodes/edges mid-stream
- **React state + timer** for staggered one-by-one node reveal
- **CSS keyframe animations** for entrance effects

---

## 3. Backend: Incremental JSON Parser

**File:** `backend/stream_parser.py`

The `IncrementalWorkflowParser` is fed tokens one-by-one as they arrive from OpenAI. After each token, it scans the accumulated text for completed JSON objects that look like workflow nodes or edges.

### How It Works

1. Accumulates all streamed text in a buffer
2. Scans for "leaf-level" JSON objects (objects with no nested `{}`)
3. Checks each object against node signature (`id` + `label` + `type`) or edge signature (`from` + `to`)
4. Deduplicates — each node/edge is emitted exactly once

### Key Design Choices

- **Handles any key order:** `{"id":"1","label":"Start","type":"start"}` and `{"type":"start","id":"1","label":"Start"}` both work
- **String-aware brace counting:** Braces inside JSON string values (e.g., `"label": "Check {status}"`) don't break parsing
- **No regex dependency:** Uses a character-level state machine for reliability

### API

```python
parser = IncrementalWorkflowParser()

# Feed tokens as they arrive from OpenAI
new_nodes, new_edges = parser.feed("...token...")
# new_nodes: [{"id": "1", "label": "Start", "type": "start"}]
# new_edges: [{"from": "1", "to": "2"}]
```

---

## 4. Backend: SSE Streaming Endpoint

**File:** `backend/main.py`  
**Endpoint:** `POST /chats/{chat_id}/messages/stream`

### Request

Same as the non-streaming endpoint:

```json
{ "content": "Create a hiring workflow" }
```

### Response

`Content-Type: text/event-stream` — a stream of SSE events:

```
event: stream_start
data: {"user_message_id": 42}

event: text_chunk
data: {"content": "Here's a"}

event: text_chunk
data: {"content": " hiring workflow"}

event: node_add
data: {"node": {"id": "1", "label": "Start", "type": "start"}}

event: node_add
data: {"node": {"id": "2", "label": "Post Job", "type": "process"}}

event: edge_add
data: {"edge": {"from": "1", "to": "2"}}

event: workflow_complete
data: {"workflow_data": "{...full JSON...}", "display_content": "Here's a hiring workflow..."}

event: stream_end
data: {"message_id": 43, "workflow_version": 5}
```

### Implementation Details

1. **Saves user message** before entering the async generator (while the DI session is valid)
2. **Creates a fresh DB session** (`SessionLocal()`) inside the generator for post-stream persistence
3. Uses **`AsyncOpenAI`** with `stream=True` for non-blocking I/O
4. Feeds each token to `IncrementalWorkflowParser` and yields `node_add`/`edge_add` events
5. After streaming completes, runs the same JSON extraction + validation as the sync endpoint
6. **Persists** the assistant message + workflow state
7. **Broadcasts** to WebSocket collaborators
8. **Releases the per-chat lock** in a `finally` block (handles client disconnect)

### Shared Helpers

To avoid duplicating the 60-line system prompt and JSON extraction logic, three functions were extracted to module level:

| Function | Purpose |
|---|---|
| `extract_json_workflow(text)` | Extracts workflow JSON from AI response text |
| `_build_system_message(workflow_context)` | Builds the OpenAI system prompt |
| `_build_conversation_history(messages, last_workflow_msg)` | Builds the conversation array + workflow context |

Both the sync (`POST /messages`) and streaming (`POST /messages/stream`) endpoints use these.

---

## 5. Frontend: SSE Client

**File:** `frontend/lib/api.ts`

### Types

```typescript
interface StreamingNode { id: string; label: string; type: string; }
interface StreamingEdge { from: string; to: string; }

interface StreamCallbacks {
  onStreamStart?: (data: { user_message_id: number }) => void;
  onTextChunk?:   (data: { content: string }) => void;
  onNodeAdd?:     (data: { node: StreamingNode }) => void;
  onEdgeAdd?:     (data: { edge: StreamingEdge }) => void;
  onWorkflowComplete?: (data: { workflow_data: string | null; display_content: string }) => void;
  onStreamEnd?:   (data: { message_id: number; workflow_version: number | null }) => void;
  onError?:       (error: string) => void;
}
```

### Usage

```typescript
const controller = streamApi.streamMessage(chatId, content, {
  onTextChunk: (data) => { /* append to chat bubble */ },
  onNodeAdd:   (data) => { /* add node to streaming state */ },
  onStreamEnd: (data) => { /* cleanup, reload messages */ },
});

// Cancel mid-stream:
controller.abort();
```

### Implementation

Uses the browser's native `fetch` API with `ReadableStream` reader (not `EventSource`, which only supports GET). Parses SSE events by splitting on `\n\n` boundaries and dispatching based on the `event:` field.

---

## 6. Frontend: Streaming State Management

**File:** `frontend/app/page.tsx`

### State Shape

```typescript
interface StreamingData {
  nodes: StreamingNode[];   // All nodes received so far from SSE
  edges: StreamingEdge[];   // All edges received so far from SSE
  isStreaming: boolean;     // true while AI is still generating
}
```

### Event Handler

`handleStreamEvent` processes events from `ChatWindow` and updates `streamingData`:

| Event | Action |
|---|---|
| `start` | Initialize `{ nodes: [], edges: [], isStreaming: true }` |
| `node_add` | Append node to `streamingData.nodes` |
| `edge_add` | Append edge to `streamingData.edges` |
| `workflow_complete` | Set final `workflowData`, mark `isStreaming: false` |
| `end` | Clear `streamingData` to `null`, update `currentMessageId` |
| `error` | Clear `streamingData` to `null` |

### Data Flow

```
ChatWindow                    page.tsx                    WorkflowVisualization
   │                             │                               │
   │── onStreamEvent(node_add)──▶│                               │
   │                             │── streamingData ─────────────▶│
   │                             │                               │── revealedCount++
   │                             │                               │── buildStreamingGraph()
   │                             │                               │── fitView()
```

---

## 7. Frontend: Staggered Node Reveal

**File:** `frontend/components/WorkflowVisualization.tsx`

This is the key UX mechanism that makes nodes appear **one at a time like chat messages** rather than all at once.

### How It Works

```
streamingData.nodes: [A, B, C, D, E]     ← received from SSE (may arrive in bursts)
revealedCount:        0 → 1 → 2 → 3...   ← increments every 400ms
visible on canvas:    [] → [A] → [A,B] → [A,B,C]...
```

1. **`revealedCount`** (React state) starts at 0 when streaming begins
2. A `useEffect` watches `streamingData.nodes.length` and `revealedCount`
3. Whenever `revealedCount < nodes.length`, it schedules a `setTimeout` to increment by 1 after **400ms**
4. `buildStreamingGraph()` only includes `nodes.slice(0, revealedCount)`
5. Edges only appear when both their source and target nodes are revealed
6. After each increment, `reactFlowInstance.fitView()` smoothly pans the camera

### Why a Timer Instead of Direct Rendering

If nodes arrive in a burst (e.g., the AI generates several nodes in quick succession), showing them all instantly would lose the sequential effect. The 400ms timer **queues** them so each node gets its own moment — just like chat messages.

### Reset Logic

When `streamingData` becomes `null` (stream ended), `revealedCount` resets to 0 and the timer is cleared. The final workflow data then renders using the standard graph layout algorithm.

---

## 8. Frontend: Animations & UX

### Node Entrance Animation

**File:** `frontend/styles/globals.css`

Each node enters with a "drop and bounce" effect:

```css
@keyframes workflowNodeAppear {
  0%   { opacity: 0; filter: blur(6px); transform: translateY(-18px) scale(0.88); }
  50%  { opacity: 1; filter: blur(0);   transform: translateY(3px) scale(1.03); }
  75%  {                                 transform: translateY(-1px) scale(0.99); }
  100% { opacity: 1; filter: blur(0);   transform: translateY(0) scale(1); }
}
```

These are defined as global keyframes because React Flow applies node styles inline — CSS module names aren't reachable from inline `style` objects.

### Newest Node Glow

The most recently revealed node gets a pulsing pink glow ring:

```typescript
boxShadow: '0 0 0 4px rgba(252, 0, 92, 0.3), 0 0 20px rgba(252, 0, 92, 0.15)'
```

This highlights the "frontier" of the building workflow.

### Edge Entrance

Edges fade in smoothly when both their endpoints appear:

```css
@keyframes workflowEdgeAppear {
  from { opacity: 0; }
  to   { opacity: 1; }
}
```

### Streaming Banner

**File:** `frontend/components/WorkflowVisualization.module.css`

A pink shimmer banner shows at the top of the visualization:

```
◉ Building workflow...                    3 / 7 nodes
```

- Pulsing dot animation
- Shimmer gradient background
- Live counter showing revealed / total

### Chat Streaming Text

**File:** `frontend/components/ChatWindow.module.css`

The AI's text response appears character-by-character with a blinking cursor:

```
Here's a hiring workflow for your company|
                                         ^ blinking cursor
```

JSON code blocks are filtered out of the visible text (only the explanatory text is shown).

---

## 9. Data Flow (End-to-End)

```
1. User types "Create a hiring workflow" → clicks Send
2. ChatWindow calls streamApi.streamMessage()
3. POST /chats/{chat_id}/messages/stream
4. Backend saves user message, acquires per-chat lock
5. AsyncOpenAI.create(stream=True)
6. Tokens arrive one by one:

   Token: "Here"
     → SSE: text_chunk {"content": "Here"}
     → ChatWindow: streamingText += "Here"

   Token: '{"id":"1","label":"Start","type":"start"}'  (completed)
     → IncrementalWorkflowParser detects node
     → SSE: node_add {"node": {"id":"1","label":"Start","type":"start"}}
     → page.tsx: streamingData.nodes = [node1]
     → WorkflowVisualization: revealedCount=0, schedules reveal in 400ms

   ...400ms later...
     → revealedCount → 1
     → buildStreamingGraph shows [Start] node with drop-in animation
     → fitView() pans camera

   More tokens → more node_add events → more reveals every 400ms

7. OpenAI stream finishes
8. Backend: extract + validate final JSON, save message, create workflow state
9. SSE: workflow_complete {"workflow_data": "...", "display_content": "..."}
     → page.tsx: setWorkflowData(finalJSON), isStreaming=false
10. SSE: stream_end {"message_id": 43, "workflow_version": 5}
     → page.tsx: setStreamingData(null)
     → revealedCount resets to 0
     → WorkflowVisualization renders final graph with proper layout algorithm
     → ChatWindow reloads messages (clean content without JSON)
11. Backend broadcasts to WebSocket collaborators
12. Lock released
```

---

## 10. SSE Event Reference

| Event | Payload | When |
|---|---|---|
| `stream_start` | `{ user_message_id: number }` | Generation begins |
| `text_chunk` | `{ content: string }` | Each token from OpenAI |
| `node_add` | `{ node: { id, label, type } }` | Parser detects a completed node object |
| `edge_add` | `{ edge: { from, to } }` | Parser detects a completed edge object |
| `workflow_complete` | `{ workflow_data: string \| null, display_content: string }` | Final validated workflow JSON |
| `stream_end` | `{ message_id: number, workflow_version: number \| null }` | Message persisted, all done |
| `error` | `{ error: string }` | Something went wrong |

---

## 11. Files Changed

### New Files

| File | Purpose |
|---|---|
| `backend/stream_parser.py` | Incremental JSON parser for detecting nodes/edges mid-stream |

### Modified Files

| File | Changes |
|---|---|
| `backend/main.py` | Extracted shared helpers (`extract_json_workflow`, `_build_system_message`, `_build_conversation_history`); added `POST /messages/stream` SSE endpoint; added `StreamingResponse` and `AsyncOpenAI` imports |
| `frontend/lib/api.ts` | Added `StreamingNode`, `StreamingEdge`, `StreamCallbacks` types; added `streamApi.streamMessage()` SSE client |
| `frontend/app/page.tsx` | Added `StreamingData` and `StreamEvent` types; added `streamingData` state and `handleStreamEvent` callback; passes `onStreamEvent` to ChatWindow and `streamingData` to WorkflowVisualization |
| `frontend/components/ChatWindow.tsx` | Replaced `chatApi.sendMessage()` with `streamApi.streamMessage()`; added streaming text display with blinking cursor; filters JSON from visible text |
| `frontend/components/WorkflowVisualization.tsx` | Added `revealedCount` stagger mechanism; `buildStreamingGraph()` uses reveal count; auto-fit camera on each reveal; streaming banner with progress counter; `onInit` for ReactFlow instance |
| `frontend/components/ChatWindow.module.css` | Added `.streamCursor` blinking animation and `.streamingMessage` styles |
| `frontend/components/WorkflowVisualization.module.css` | Added `.streamingBanner`, `.streamingDot`, `.streamingCount` with shimmer and pulse animations |
| `frontend/styles/globals.css` | Added global `@keyframes workflowNodeAppear` (drop-bounce) and `@keyframes workflowEdgeAppear` (fade-in) |

---

## 12. Design Decisions & Trade-offs

### SSE over WebSocket for Streaming

The app already has WebSocket infrastructure for collaboration. However, SSE was chosen for the AI streaming because:

- **Request-response model:** SSE fits naturally — the client sends a message, the server streams back a response
- **Automatic reconnection:** Built into the SSE protocol
- **Simpler error handling:** HTTP status codes work normally
- **No bidirectional need:** The client doesn't need to send data mid-stream

WebSocket is still used to **broadcast** the final result to collaborators after the stream completes.

### Staggered Reveal (400ms Timer) over Instant Rendering

Nodes could be rendered the instant they're parsed, but this creates a jarring experience when multiple nodes arrive in a burst. The 400ms timer creates a deliberate, sequential "building" feel — like watching someone construct a diagram step by step.

### Incremental Parser over Waiting for Complete JSON

Waiting for the full JSON to be complete defeats the purpose of streaming. The incremental parser detects nodes as they're generated, even when the overall JSON is incomplete. This means the first node can appear on-screen while the AI is still generating the last node.

### Separate DB Session for Generator

The SSE generator runs after the FastAPI endpoint function returns. The dependency-injected DB session may be closed by then, so the generator creates its own `SessionLocal()` and closes it in `finally`. This ensures the session lifecycle is correct regardless of when the generator runs or how the client disconnects.

### AsyncOpenAI over Sync OpenAI

The streaming endpoint uses `AsyncOpenAI` (async HTTP client) instead of the sync `OpenAI` client. This is critical because the SSE generator is an async generator — using the sync client would block the event loop while waiting for each token, preventing other requests from being served.

### Backward Compatibility

The original `POST /chats/{chat_id}/messages` endpoint remains unchanged. The streaming endpoint is additive — if the frontend's SSE connection fails, it could fall back to the sync endpoint without data loss.
