# Real-Time Multi-User Collaboration Features

This document covers all collaboration, real-time, and version control features implemented in the workflow builder.

---

## Table of Contents

1. [Chat Sharing & Access Control](#1-chat-sharing--access-control)
2. [Real-Time Communication (WebSockets)](#2-real-time-communication-websockets)
3. [Presence & Typing Indicators](#3-presence--typing-indicators)
4. [Concurrent Message Processing (Chat Locking)](#4-concurrent-message-processing-chat-locking)
5. [Workflow Conflict Resolution](#5-workflow-conflict-resolution)
6. [Version Control (Undo / Redo / Revert)](#6-version-control-undo--redo--revert)
7. [Database Models](#7-database-models)
8. [API Reference](#8-api-reference)
9. [Frontend Components](#9-frontend-components)
10. [Architecture Decisions](#10-architecture-decisions)

---

## 1. Chat Sharing & Access Control

Users can share their chats with other users, assigning them a role.

### Roles

| Role     | Can view messages | Can send messages | Can edit workflow | Can share with others |
|----------|:-:|:-:|:-:|:-:|
| **Owner**  | Yes | Yes | Yes | Yes |
| **Editor** | Yes | Yes | Yes | No  |
| **Viewer** | Yes | No  | No  | No  |

### How It Works

- The chat owner searches for users by username or email via the **ShareDialog** component.
- Adding a collaborator creates a `ChatCollaborator` record with the chosen role.
- All existing endpoints (`get_chats`, `get_chat`, `delete_chat`, `create_message`, etc.) check access via `get_chat_with_access()`, which allows both the owner and any collaborator.
- Shared chats appear in a separate "Shared with me" section in the sidebar, showing the owner's name and the user's role.

### Files

| File | What |
|------|------|
| `backend/database.py` | `ChatCollaborator` model, `CollaboratorRole` enum |
| `backend/schemas.py` | `CollaboratorAdd`, `CollaboratorResponse`, `SharedChatResponse`, `UserSearchResponse` |
| `backend/main.py` | `/users/search`, `/chats/shared`, `/chats/{id}/collaborators` CRUD endpoints |
| `frontend/components/ShareDialog.tsx` | Modal UI for searching users, adding/removing collaborators, changing roles |
| `frontend/components/ChatList.tsx` | Renders shared chats in sidebar with owner name and role badge |

---

## 2. Real-Time Communication (WebSockets)

A persistent WebSocket connection per chat enables instant updates between all connected users.

### Connection Flow

```
Client                          Server
  |                                |
  |-- WS /ws/{chat_id}?token=JWT -|
  |                                |-- Authenticate JWT
  |                                |-- Add to ConnectionManager
  |<-- { type: "presence" } -------|-- Broadcast join to others
  |                                |
  |-- { type: "typing" } -------->|-- Broadcast to others
  |<-- { type: "typing" } --------|
  |                                |
  |<-- { type: "new_message" } ---|-- After AI responds
  |<-- { type: "workflow_op" } ---|-- After workflow edit
  |<-- { type: "version_revert" }-|-- After undo/redo
  |                                |
  |-- ping ---------------------->|-- pong (keepalive)
  |                                |
  |-- disconnect ---------------->|-- Remove from manager
  |                                |-- Broadcast leave
```

### Event Types

| Event | Direction | Payload | Purpose |
|-------|-----------|---------|---------|
| `presence` | Server -> Client | `{ online_users, user_joined/left }` | User join/leave notifications |
| `typing` | Bidirectional | `{ user_id, username, is_typing }` | Typing indicator |
| `new_message` | Server -> Client | `{ messages, workflow_version }` | New chat messages (user + AI) |
| `workflow_op` | Server -> Client | `{ version, data, operations, status }` | Remote workflow edit applied |
| `version_revert` | Server -> Client | `{ current_version, max_version, data }` | Another user did undo/redo |
| `processing` | Server -> Client | `{ status: started/queued/done }` | Message processing status |

### Files

| File | What |
|------|------|
| `backend/main.py` | `ConnectionManager` class, `WS /ws/{chat_id}` endpoint |
| `frontend/lib/api.ts` | `ChatWebSocket` class with auto-reconnect, ping/pong, event emitter |

---

## 3. Presence & Typing Indicators

### Online Users

- When a user connects via WebSocket, they're added to the `ConnectionManager`'s `user_info` map.
- On connect/disconnect, a `presence` event is broadcast with the updated list of online users.
- The `OnlineIndicator` component renders an avatar stack of up to 5 online users.

### Typing Indicators

- On `input` change in the chat box, the client sends `{ type: "typing", is_typing: true }`.
- The server broadcasts it to other users in the chat.
- The `OnlineIndicator` component shows "{username} is typing..." with a dot animation.
- A debounce timer auto-clears the typing state after inactivity.

### Files

| File | What |
|------|------|
| `frontend/components/OnlineIndicator.tsx` | Avatar stack + typing indicator UI |
| `frontend/components/OnlineIndicator.module.css` | Styling for avatars, typing dots |
| `frontend/components/ChatWindow.tsx` | Sends typing events, listens for presence updates |

---

## 4. Concurrent Message Processing (Chat Locking)

### Problem

If User A and User B both send a message at the same time, two AI calls run in parallel. Both read the same conversation history, producing responses based on stale context. The second response overwrites the first workflow.

### Solution: Per-Chat `asyncio.Lock`

The `ChatLockManager` provides one `asyncio.Lock` per `chat_id`:

1. User A sends a message -> acquires lock -> AI processes -> releases lock.
2. User B sends a message concurrently -> waits for lock -> processes with updated history.

### User Experience

While a user's message is queued behind another:
- A **"Processing another request..."** banner appears in the chat window.
- WebSocket events notify all users of processing status (`started`, `queued`, `done`).
- The lock is automatically cleaned up when no longer referenced.

### Files

| File | What |
|------|------|
| `backend/main.py` | `ChatLockManager` class, used in `create_message` and `undo_workflow` endpoints |
| `frontend/components/ChatWindow.tsx` | `processingInfo` state, processing banner UI |

---

## 5. Workflow Conflict Resolution

### Problem

User A drags Node X to position (100, 200). At the same time, User B deletes Node X. Whose edit wins?

### Solution: Version-Based Optimistic Concurrency with Operation-Level Merging

Every workflow edit is sent as a list of **operations** (not the full JSON), along with the `base_version` the client last saw.

### Conflict Resolution Flow

```
Client sends:  { base_version: 5, operations: [move_node(X, 100, 200)] }

Server checks: current_version = 7 (two edits happened since v5)

Server logic:
  1. Get concurrent ops (v6, v7) from the operation log
  2. Check if incoming ops conflict with concurrent ops
  3. If no conflict → auto-merge (apply on top of v7)
  4. If conflict → reject with details + latest state
```

### Conflict Rules

| Incoming | Concurrent | Conflict? |
|----------|-----------|:-:|
| Move Node X | Move Node X | Yes |
| Move Node X | Delete Node X | Yes |
| Update Node X | Delete Node X | Yes |
| Move Node X | Move Node Y | No (auto-merge) |
| Add Edge A->B | Delete Node A | Yes |
| Add Node X | Add Node Y | No (auto-merge) |

### Operation Types

| Operation | Payload |
|-----------|---------|
| `move_node` | `{ node_id, x, y }` |
| `add_node` | `{ node: { id, label, type, ... } }` |
| `delete_node` | `{ node_id }` |
| `update_node` | `{ node_id, changes: { ... } }` |
| `add_edge` | `{ edge: { from, to } }` |
| `delete_edge` | `{ from, to }` |

### Frontend Handling

- On `conflict` response: a red banner appears showing which nodes/edges conflicted, and the local state is rebased to the server's latest version.
- On `merged` response: local state is silently updated to the server's merged result.

### Files

| File | What |
|------|------|
| `backend/conflict_resolver.py` | `Operation`, `ConflictResult`, `detect_conflicts()`, `apply_operations()`, `resolve()` |
| `backend/main.py` | `POST /chats/{id}/workflow/operations` endpoint |
| `frontend/components/WorkflowVisualization.tsx` | `flushOperations()` batches ops, handles conflict/merged responses |

---

## 6. Version Control (Undo / Redo / Revert)

### Design: Pointer-Based (Git-Style)

The version history uses an **immutable snapshot list** with a **movable pointer**:

```
Snapshots:  v1 ── v2 ── v3 ── v4 ── v5
                                 ^
                          current_version = 4  (user undid once)
```

- **Undo**: moves pointer backward (v4 -> v3). No new snapshot created.
- **Redo**: moves pointer forward (v3 -> v4). No new snapshot created.
- **New edit while pointer is in the middle**: truncates future snapshots (git-style), then creates a new one.

```
Before edit at v3:  v1 ── v2 ── v3 ── v4 ── v5
                                 ^
After new edit:     v1 ── v2 ── v3 ── v6    (v4, v5 discarded)
                                       ^
```

### Database Fields

| Field | Description |
|-------|-------------|
| `WorkflowState.version` | `max_version` — highest snapshot number, only incremented by real edits |
| `WorkflowState.current_version` | Pointer to the active snapshot |
| `WorkflowSnapshot.version` | Immutable snapshot number |
| `WorkflowSnapshot.data` | Full workflow JSON at that version |
| `WorkflowSnapshot.description` | Human-readable label (e.g., "AI-generated workflow", "alice: move_node") |

### Version Timeline UI

The `VersionTimeline` component provides:

- **Undo / Redo buttons** in a compact toolbar
- **Version label** showing the current version number
- **Expandable timeline** showing all versions with:
  - Version number and "current" badge
  - Description of what changed
  - Who made the change and when
  - **View** button to preview without reverting
  - **Accept** button to revert to that version
- **Preview mode** with a yellow banner ("Previewing v3 — Exit preview")

### Files

| File | What |
|------|------|
| `backend/database.py` | `WorkflowState` (with `current_version` pointer), `WorkflowSnapshot` |
| `backend/main.py` | `/workflow/versions`, `/workflow/revert`, `/workflow/versions/{version}` endpoints |
| `backend/schemas.py` | `VersionEntry`, `VersionTimelineResponse`, `RevertRequest`, `RevertResponse` |
| `frontend/components/VersionTimeline.tsx` | Timeline UI, undo/redo/preview/accept logic |
| `frontend/components/VersionTimeline.module.css` | Timeline styling |
| `frontend/components/WorkflowVisualization.tsx` | Integrates timeline, handles `handleVersionRevert` and `handleVersionPreview` |

---

## 7. Database Models

### Entity Relationship

```
User ──< Chat ──< Message
  |         |
  |         ├──< ChatCollaborator >── User
  |         |
  |         ├──── WorkflowState (1:1)
  |         |
  |         ├──< WorkflowSnapshot
  |         |
  |         └──< WorkflowOperation
  |
  └──< ChatCollaborator (via shared_chats)
```

### Models Summary

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | Registered users with hashed passwords |
| `Chat` | `chats` | Conversations owned by a user |
| `Message` | `messages` | Chat messages (user + assistant), optionally with `workflow_data` |
| `ChatCollaborator` | `chat_collaborators` | Sharing junction table with role (viewer/editor) |
| `WorkflowState` | `workflow_states` | Live workflow state per chat, version pointer |
| `WorkflowSnapshot` | `workflow_snapshots` | Immutable historical snapshots for undo/redo |
| `WorkflowOperation` | `workflow_operations` | Append-only operation log for auditing and conflict resolution |

---

## 8. API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login, returns JWT token |
| GET | `/auth/me` | Get current user profile |

### Chats

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/chats` | List user's own chats |
| GET | `/chats/shared` | List chats shared with the user |
| POST | `/chats` | Create a new chat |
| GET | `/chats/{id}` | Get chat with messages |
| DELETE | `/chats/{id}` | Delete a chat (owner only) |

### Messages

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chats/{id}/messages` | Send a message and get AI response |

### Collaboration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users/search?q=` | Search users by username/email |
| GET | `/chats/{id}/collaborators` | List collaborators on a chat |
| POST | `/chats/{id}/collaborators` | Add a collaborator |
| PATCH | `/chats/{id}/collaborators/{user_id}` | Update collaborator role |
| DELETE | `/chats/{id}/collaborators/{user_id}` | Remove a collaborator |
| GET | `/chats/{id}/online` | List currently online users |

### Workflow Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/chats/{id}/workflow/state` | Get current workflow state + version |
| POST | `/chats/{id}/workflow/operations` | Apply operations with conflict resolution |

### Version Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/chats/{id}/workflow/versions` | Get full version timeline |
| POST | `/chats/{id}/workflow/revert` | Move version pointer (undo/redo/accept) |
| GET | `/chats/{id}/workflow/versions/{v}` | Preview a specific version |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/{chat_id}?token=JWT` | Real-time updates for a chat |

---

## 9. Frontend Components

### New Components

| Component | File | Description |
|-----------|------|-------------|
| `ShareDialog` | `components/ShareDialog.tsx` | Modal for managing chat sharing — user search, add/remove collaborators, role management |
| `OnlineIndicator` | `components/OnlineIndicator.tsx` | Avatar stack of online users + typing indicator |
| `VersionTimeline` | `components/VersionTimeline.tsx` | Undo/redo toolbar + expandable version history with preview and accept |

### Modified Components

| Component | Key Changes |
|-----------|-------------|
| `ChatWindow` | WebSocket integration, typing events, processing banner, Share button, presence tracking |
| `ChatList` | "Shared with me" section, owner name + role badge display |
| `WorkflowVisualization` | Operation-based editing, conflict handling, version timeline integration, preview mode |
| `page.tsx` | `isOwnerOfSelected` state for correct ownership propagation |

### New Client Library

| Module | File | Description |
|--------|------|-------------|
| `ChatWebSocket` | `lib/api.ts` | WebSocket client with auto-reconnect, ping/pong keepalive, event emitter pattern |
| `workflowApi` | `lib/api.ts` | API methods for `getState`, `applyOperations`, `getVersionTimeline`, `revertToVersion`, `getVersionSnapshot` |
| `collaborationApi` | `lib/api.ts` | API methods for user search and collaborator CRUD |

---

## 10. Architecture Decisions

### Why WebSockets over SSE or polling?

- Bidirectional: clients need to send typing indicators and receive updates.
- Low latency: instant delivery of presence changes and workflow edits.
- Single connection per chat: efficient for multiple event types.

### Why per-chat locking instead of CRDT for messages?

- Chat messages are inherently sequential — the AI response depends on the full conversation history.
- CRDTs solve concurrent editing of the same document, but chat messages aren't edited, they're appended.
- A simple `asyncio.Lock` serializes processing cleanly while allowing concurrent reads.

### Why version-based conflict resolution instead of CRDT for workflows?

- Workflow graphs have structural constraints (e.g., no orphaned edges) that CRDTs don't enforce well.
- Operation-level merging gives precise conflict messages ("Node X was deleted by another user while you were moving it").
- The version-based model is simpler to debug and audit via the operation log.

### Why pointer-based version control instead of append-on-revert?

- Appending a new snapshot on every undo/redo bloats the timeline with redundant entries.
- A pointer model keeps the history clean: undo from v5 to v3 just moves the pointer, the timeline still shows [v1, v2, v3, v4, v5].
- New edits after undo truncate future snapshots (git-style), which is the behavior users expect.

### Why truncate future snapshots on new edit?

- This matches the mental model of every undo/redo system users are familiar with (text editors, git, Photoshop).
- If the user undoes to v3 and makes a new edit, versions v4 and v5 are no longer reachable — keeping them would confuse the timeline.
- The operation log (`WorkflowOperation`) still retains the full audit trail even after truncation.
