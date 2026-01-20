# Sales Teaching Assistant

Real-Time AI Sales Role-Play Training Platform built with Python/FastAPI, Gemini Live API, and PostgreSQL (Neon).

## Features

- **Real-time voice conversations** with AI personas via Gemini Live API
- **Dynamic personas** that adapt mood, skepticism, and behavior based on rep performance
- **Live analytics** including talk ratio, sentiment timeline, and behavior markers
- **Scenario-based training** with cold calls, discovery calls, and coaching sessions
- **Manager assignments** for structured team training
- **Production-ready security** with rate limiting, CORS hardening, and JWT auth

---

## Architecture Overview

```mermaid
graph TB
    subgraph Frontend
        UI[React/Next.js App]
        WA[Web Audio API]
        WS[WebSocket Client]
    end
    
    subgraph Backend[FastAPI Backend]
        API[REST API]
        AUTH[Neon JWKS Auth]
        WSH[WebSocket Handler]
        SEC[Security Middleware]
        
        subgraph LLM[LLM Layer]
            ORCH[Orchestrator]
            PB[Prompt Builder]
            LIVE[Gemini Live API]
            ANALYSIS[Gemini Analysis]
        end
    end
    
    subgraph External
        NEON[(Neon PostgreSQL)]
        GEMINI[Gemini API]
        JWKS[Neon Auth JWKS]
    end
    
    UI --> API
    WA --> WS
    WS --> WSH
    API --> AUTH
    AUTH --> JWKS
    WSH --> ORCH
    ORCH --> PB
    ORCH --> LIVE
    ORCH --> ANALYSIS
    LIVE --> GEMINI
    ANALYSIS --> GEMINI
    API --> NEON
    WSH --> NEON
    SEC --> API
```

---

## System Flow

### Complete Call Session Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant WS as WebSocket
    participant O as Orchestrator
    participant LIVE as Gemini Live
    participant DB as Neon DB
    
    U->>FE: Select Scenario
    FE->>API: POST /api/sessions {scenario_id}
    API->>DB: Create session (status=pending)
    API-->>FE: session_id
    
    FE->>WS: Connect /ws/call/{session_id}
    WS->>DB: Load session + scenario + persona
    WS->>O: Initialize orchestrator
    O->>LIVE: Connect with system prompt
    WS-->>FE: CALL_STARTED {mood, rapport}
    
    loop Conversation Turns
        U->>FE: Speak (audio)
        FE->>WS: Audio stream
        WS->>LIVE: Stream audio
        LIVE-->>WS: AI audio response
        WS-->>FE: AI audio + transcript
        O->>O: Analyze turn, update state
        WS-->>FE: STATE_UPDATE {mood, rapport}
    end
    
    U->>FE: End Call
    FE->>WS: {type: "end_call"}
    WS->>O: Generate feedback
    WS->>DB: Save transcript, feedback, analytics
    WS-->>FE: CALL_ENDED + feedback
```

---

## Core Components

### Directory Structure

```
app/
├── main.py                 # FastAPI entry, security middleware, CORS
├── config.py               # Pydantic settings (env vars)
├── api/routes/
│   ├── auth.py             # JWKS validation, get_current_user
│   ├── sessions.py         # Session CRUD, lifecycle
│   ├── scenarios.py        # Scenario listing/filtering
│   ├── personas.py         # Persona management
│   ├── users.py            # User profile management
│   ├── assignments.py      # Manager training assignments
│   ├── analytics.py        # Performance metrics
│   └── websocket.py        # Real-time call handler
├── core/
│   ├── llm/
│   │   ├── prompt_builder.py   # Dynamic prompt construction
│   │   ├── gemini_client.py    # Gemini analysis API
│   │   └── orchestrator.py     # Turn management + state
│   ├── voice/
│   │   ├── tts_provider.py     # Text-to-Speech abstraction
│   │   └── stt_provider.py     # Speech-to-Text abstraction
│   └── analytics_service.py    # Analytics aggregation
├── db/
│   └── connection.py       # Async SQLAlchemy + Neon pooling
└── models/
    ├── database.py         # SQLAlchemy ORM models
    └── schemas.py          # Pydantic validation schemas

data/
├── prompts.json            # Persona & scenario definitions (gitignored)
├── prompts.example.json    # Template for prompts.json
├── system_prompts.json     # LLM behavior templates (gitignored)
└── system_prompts.example.json  # Template for system prompts
```

### Component Responsibilities

| Component | File | Purpose |
|-----------|------|---------|
| **Orchestrator** | `orchestrator.py` | Central brain - coordinates turn processing, state updates, analytics |
| **Prompt Builder** | `prompt_builder.py` | Constructs dynamic prompts from external JSON templates |
| **Gemini Client** | `gemini_client.py` | Handles analysis and feedback generation |
| **WebSocket Handler** | `websocket.py` | Real-time audio/message routing with Gemini Live |
| **Analytics Service** | `analytics_service.py` | Aggregates user and session performance metrics |

---

## Prompt Architecture

Prompts are externalized to `data/system_prompts.json` for security and customization:

```mermaid
graph TD
    subgraph "External Config (gitignored)"
        SP[system_prompts.json]
        PP[prompts.json]
    end
    
    subgraph "Database"
        PERSONA[Persona Table]
        SCENARIO[Scenario Table]
    end
    
    subgraph "Runtime"
        PB[Prompt Builder]
        GC[Gemini Client]
    end
    
    PP -->|seed script| PERSONA
    PP -->|seed script| SCENARIO
    PERSONA --> PB
    SCENARIO --> PB
    SP --> PB
    SP --> GC
    
    PB --> |System Prompt| LIVE[Gemini Live API]
    GC --> |Analysis Prompt| ANALYSIS[Gemini Analysis API]
```

### Prompt Layers

| Layer | Source | Purpose |
|-------|--------|---------|
| **Identity** | `persona.system_prompt_template` (DB) | Who the AI is |
| **Scenario** | `scenario.scenario_rules` (DB) | Situation and rules |
| **Behavior** | `system_prompts.json` | Skepticism, patience, interrupts |
| **State** | Runtime | Current mood, rapport, turn count |
| **Hidden** | `system_prompts.json` | Adaptive instructions |

---

## Security Features

```mermaid
flowchart LR
    REQ[Incoming Request] --> RL[Rate Limiter]
    RL -->|100/min| SIZE[Size Limiter]
    SIZE -->|10MB max| CORS[CORS Validation]
    CORS --> ORIGIN[Origin Validator]
    ORIGIN --> SEC[Security Headers]
    SEC --> AUTH[JWT Auth]
    AUTH --> ROUTE[Route Handler]
```

| Feature | Implementation | Config |
|---------|---------------|--------|
| **Rate Limiting** | `slowapi` - 100 req/min per IP | `main.py` |
| **Request Size** | 10MB max body size | `main.py` |
| **CORS** | Explicit origin allowlist | `ALLOWED_ORIGINS` env |
| **Origin Validation** | Server-side origin check | `main.py` middleware |
| **Security Headers** | X-Frame-Options, CSP, HSTS | `main.py` middleware |
| **JWT Auth** | Neon JWKS validation | `auth.py` |
| **Prompt Protection** | External JSON, gitignored | `data/*.json` |

---

## Database Models

```mermaid
erDiagram
    COMPANY ||--o{ USER : has
    USER ||--o{ SESSION : completes
    PERSONA ||--o{ SCENARIO : defines
    SCENARIO ||--o{ SESSION : uses
    SESSION ||--o| TRANSCRIPT : has
    SESSION ||--o| FEEDBACK : has
    SESSION ||--o| SESSION_ANALYTICS : has
    SESSION ||--o{ CONVERSATION_STATE : tracks
    USER ||--o{ TRAINING_ASSIGNMENT : receives
    USER ||--o{ TRAINING_ASSIGNMENT : creates
    
    PERSONA {
        uuid id
        string name
        string title
        string[] traits
        string default_mood
        text system_prompt_template
        jsonb behavior_config
    }
    
    SCENARIO {
        uuid id
        uuid persona_id
        string type
        string difficulty
        text instructions
        text scenario_rules
        jsonb success_criteria
        decimal book_rate
    }
    
    SESSION {
        uuid id
        uuid user_id
        uuid scenario_id
        string status
        datetime start_time
        datetime end_time
        int duration_seconds
        decimal overall_score
    }
```

---

## Quick Start

### 1. Environment Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
GEMINI_API_KEY=your_key
NEON_JWKS_URL=https://your-project.auth.neon.tech/.well-known/jwks.json
ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
LIVE_API_MODEL=gemini-2.0-flash-live-001
ANALYSIS_API_MODEL=gemini-2.0-flash
```

### 3. Configure Prompts

Copy example files and customize:

```bash
cp data/prompts.example.json data/prompts.json
cp data/system_prompts.example.json data/system_prompts.json
```

### 4. Initialize Database

```bash
alembic upgrade head
python -m scripts.seed
```

### 5. Run Server

```bash
# Development
uvicorn app.main:app --reload

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/me` | GET | Current user info |
| `/api/scenarios` | GET | List scenarios |
| `/api/scenarios/{id}` | GET | Scenario details |
| `/api/personas` | GET | List personas |
| `/api/sessions` | POST | Create session |
| `/api/sessions/{id}` | GET | Session with results |
| `/api/sessions/{id}/start` | PATCH | Mark started |
| `/api/sessions/{id}/end` | PATCH | Mark ended |
| `/api/assignments` | GET/POST | Training assignments |
| `/api/analytics/sessions/{id}` | GET | Session analytics |
| `/api/analytics/user/{id}/summary` | GET | User performance |
| `/ws/call/{session_id}` | WS | Real-time call |

---

## WebSocket Messages

**Client → Server:**
```json
{"type": "audio", "data": "<base64>"}
{"type": "end_call"}
```

**Server → Client:**
```json
{"type": "call_started", "session_id": "...", "mood": "annoyed", "rapport": 0.3}
{"type": "transcript", "speaker": "rep|ai", "text": "..."}
{"type": "audio", "data": "<base64>"}
{"type": "state_update", "mood": "interested", "rapport": 0.6}
{"type": "call_ended", "feedback": {...}}
```

---

## Configuration Files

| File | Purpose | Tracked |
|------|---------|---------|
| `.env` | Environment variables | ❌ |
| `data/prompts.json` | Persona/scenario content | ❌ |
| `data/system_prompts.json` | LLM behavior templates | ❌ |
| `data/*.example.json` | Templates for above | ✅ |
| `requirements.txt` | Python dependencies | ✅ |
| `Dockerfile` | Container build | ✅ |