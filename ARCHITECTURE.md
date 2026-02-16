# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         User Browser                         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐   │
│  │ Chat     │  │ Chat     │  │ Workflow              │   │
│  │ List     │  │ Window   │  │ Visualization         │   │
│  │ (20%)    │  │ (30%)    │  │ (50%)                 │   │
│  │          │  │          │  │                        │   │
│  │ • Chats  │  │ • Msgs   │  │ • ReactFlow           │   │
│  │ • New    │  │ • Input  │  │ • Zoom/Pan            │   │
│  │ • Delete │  │ • Send   │  │ • Auto-layout         │   │
│  └──────────┘  └──────────┘  └────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                          │
                          │ HTTP/REST API
                          │ (JWT Auth)
                          │
┌──────────────────────────┴───────────────────────────────────┐
│                      FastAPI Backend                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Auth         │  │ Chat         │  │ OpenAI           │ │
│  │ Endpoints    │  │ Endpoints    │  │ Integration      │ │
│  │              │  │              │  │                  │ │
│  │ • Register   │  │ • Create     │  │ • GPT-3.5       │ │
│  │ • Login      │  │ • List       │  │ • Workflow Gen  │ │
│  │ • JWT Auth   │  │ • Messages   │  │ • JSON Format   │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
│                           │                                  │
│                           │ SQLAlchemy ORM                  │
│                           │                                  │
└───────────────────────────┴──────────────────────────────────┘
                           │
                           │
┌───────────────────────────┴──────────────────────────────────┐
│                      MySQL Database                          │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐ │
│  │ users    │  │ chats    │  │ messages                │ │
│  │          │  │          │  │                         │ │
│  │ • id     │  │ • id     │  │ • id                    │ │
│  │ • user   │  │ • title  │  │ • chat_id               │ │
│  │ • email  │  │ • user   │  │ • role (user/assistant) │ │
│  │ • pass   │  │ • dates  │  │ • content               │ │
│  │          │  │          │  │ • workflow_data (JSON)  │ │
│  └──────────┘  └──────────┘  └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## User Flow

### 1. Authentication
```
User → Register/Login → JWT Token → Authenticated Session
```

### 2. Chat Creation
```
User → Click "New" → Create Chat → Chat Added to List → Select Chat
```

### 3. Workflow Generation
```
User → Type Message → Send to Backend → OpenAI API → Generate Workflow
     ↓
Assistant Response + Workflow JSON → Display in Chat + Visualize
```

### 4. Workflow Visualization
```
Workflow JSON → Parse Nodes/Edges → ReactFlow → Interactive Diagram
                                                  ↓
                                             Zoom, Pan, Explore
```

## Technology Stack Details

### Frontend (Next.js 14)
- **Framework**: Next.js with App Router
- **Language**: TypeScript
- **Styling**: CSS Modules
- **State**: Zustand (lightweight state management)
- **HTTP Client**: Axios
- **Visualization**: ReactFlow (workflow diagrams)

### Backend (FastAPI)
- **Framework**: FastAPI (Python)
- **ORM**: SQLAlchemy 2.0
- **Authentication**: JWT with python-jose
- **Password**: Bcrypt hashing via passlib
- **AI**: OpenAI Python SDK
- **Validation**: Pydantic v2

### Database (MySQL 8.0)
- **Type**: Relational database
- **Connection**: PyMySQL driver
- **Migrations**: Manual (SQLAlchemy models)

### Deployment (Docker)
- **Backend**: Python 3.11 slim image
- **Frontend**: Node 18 Alpine image
- **Database**: MySQL 8.0 official image
- **Orchestration**: Docker Compose

## Data Flow

### Authentication Flow
```
1. User enters credentials
2. Frontend sends POST /auth/login
3. Backend validates against database
4. Backend generates JWT token
5. Frontend stores token in localStorage
6. Token included in all subsequent requests
```

### Message Flow
```
1. User types message in chat window
2. Frontend POST /chats/{id}/messages
3. Backend saves user message to DB
4. Backend calls OpenAI API with conversation history
5. OpenAI generates response + workflow data
6. Backend saves assistant message to DB
7. Frontend receives message + workflow
8. Chat window displays message
9. Workflow visualizer renders diagram
```

## Security Layers

1. **Transport**: HTTPS in production
2. **Authentication**: JWT tokens (HS256)
3. **Passwords**: Bcrypt hashing
4. **Database**: Parameterized queries (SQLAlchemy ORM)
5. **CORS**: Configured origins only
6. **Environment**: Secrets in .env files (not committed)

## Scalability Considerations

### Current Architecture (MVP)
- Single backend instance
- Single database instance
- Suitable for small to medium workloads

### Potential Improvements
1. **Horizontal Scaling**: Multiple backend instances with load balancer
2. **Database**: Read replicas for query scaling
3. **Caching**: Redis for session/response caching
4. **CDN**: Static asset delivery
5. **Queue**: Background job processing for AI calls
6. **WebSockets**: Real-time message updates

## Performance Characteristics

### Backend
- **Cold start**: ~1-2 seconds
- **API response**: <100ms (without OpenAI)
- **With OpenAI**: 2-5 seconds (depends on OpenAI)

### Frontend
- **Initial load**: ~200ms (after build)
- **Navigation**: Instant (client-side routing)
- **Re-renders**: Optimized with React best practices

### Database
- **Queries**: Indexed on foreign keys
- **Connections**: Pooled via SQLAlchemy
- **Transactions**: Atomic for consistency
