# Tutor Agent API Design

Date: 2026-06-30

## Overview

Tutor Agent API is a training-oriented backend project for learning backend development through building an AI learning tutor Agent.

The first version, `v0.1`, focuses on a FastAPI backend API that accepts learning questions, calls a replaceable LLM client, returns structured tutoring replies, and stores simple conversation history in SQLite.

This design intentionally avoids frontend, authentication, long-term memory, RAG, and complex Agent orchestration in the first version.

## Confirmed Decisions

- Project type: AI learning tutor Agent
- Learning path: mixed route, with backend as the main line and AI full-stack capabilities introduced gradually
- First interface shape: backend API version
- Tutor behavior: mixed tutor, returning explanation, next task, exercise, and checkpoints
- Model integration: replaceable `LLMClient`
- First model implementation: OpenAI-compatible client
- Storage: SQLite simple conversation history
- Multi-user strategy: lightweight `user_id` in requests, no login in v0.1
- Recommended approach: training-oriented backend API version

## Project Goals

Functional goal:

- Build a runnable FastAPI backend.
- Support `POST /chat`.
- Call a model through a replaceable LLM client.
- Return structured tutor replies.
- Store simple conversation history.
- Query recent conversation history by `user_id`.

Learning goal:

- Learn backend project structure.
- Learn HTTP APIs.
- Learn request and response schemas.
- Learn environment variable configuration.
- Learn LLM API integration.
- Learn basic SQLite persistence.
- Learn route, service, client, repository, and database boundaries.
- Learn basic error handling and tests.

## Architecture

Target structure:

```text
tutor-agent-api/
  app/
    main.py
    core/
      config.py
    api/
      routes/
        health.py
        chat.py
        conversations.py
    schemas/
      chat.py
      conversation.py
    services/
      tutor_agent.py
      llm_client.py
    repositories/
      conversation_repository.py
    db/
      database.py
      models.py
  tests/
    test_health.py
    test_chat.py
  docs/
    requirements.md
    main-quest-progress.md
    training-plan.md
    ai-collaboration-guide.md
    api-design.md
    data-design.md
    learning-journal.md
    v2-roadmap.md
  scripts/
    test_llm.py
  .env.example
  requirements.txt
  README.md
```

Main data flow:

```text
User requests POST /chat
  -> FastAPI route receives request
  -> Pydantic validates user_id and message
  -> TutorAgentService builds tutor prompt
  -> LLMClient calls model
  -> Service parses or falls back to structured reply
  -> Repository stores message and reply in SQLite
  -> API returns user_id, message, reply, conversation_id
```

## API Scope

`GET /health`

- Confirms service is running.

`POST /chat`

- Accepts `user_id` and `message`.
- Calls the tutor service.
- Returns structured reply.
- Saves conversation history.

`GET /conversations/{user_id}`

- Returns recent 20 conversations for a user.

## Structured Tutor Reply

The tutor reply shape:

```json
{
  "answer": "Explain the user's question",
  "next_task": "Suggest the next step",
  "exercise": "Give a small exercise",
  "checkpoints": [
    "What the learner should be able to do"
  ]
}
```

If the model fails to return valid JSON, v0.1 uses a simple fallback that places the model text into `answer` and fills the other fields with default learning prompts.

## Data Design

Database: SQLite

Table: `conversations`

```text
id          INTEGER PRIMARY KEY
user_id     TEXT NOT NULL
message     TEXT NOT NULL
reply_json  TEXT NOT NULL
created_at  DATETIME NOT NULL
```

v0.1 stores only simple raw conversation history. It does not implement long-term memory, learning profiles, vector search, or task status.

## Error Handling

v0.1 handles:

- Empty `user_id`
- Empty `message`
- Missing model API key
- Model call failure
- Invalid model JSON output
- Database write failure
- Database query failure

Error responses must not expose API keys or sensitive configuration.

## Documentation Set

Project documentation:

- `docs/requirements.md`
- `docs/main-quest-progress.md`
- `docs/training-plan.md`
- `docs/ai-collaboration-guide.md`
- `docs/api-design.md`
- `docs/data-design.md`
- `docs/learning-journal.md`
- `docs/v2-roadmap.md`

The main quest progress file is the operational checklist. The other documents explain why the project is designed this way and how to collaborate with AI while building it.

## v0.1 Exclusions

The first version does not include:

- Login or registration
- JWT
- Complex permissions
- Frontend UI
- Admin panel
- Long-term memory
- Vector database
- Learning profile
- Task completion status
- Knowledge graph
- Multi-Agent orchestration
- RAG document QA
- File upload
- Production deployment
- Payment system
- Message queue
- Microservices
- Docker

## Roadmap

`v0.2`: learning progress management

- Learning tasks
- Task completion state
- Current learning stage
- User learning plan

`v0.3`: tool calling

- Query progress
- Create tasks
- Mark tasks complete
- Generate exercises

`v0.4`: simple frontend

- Chat UI
- Message list
- Learning task panel
- User ID switcher

`v0.5`: long-term memory prototype

- Learning summaries
- Weak points
- Review suggestions

`v0.6`: RAG learning materials QA

- Upload or ingest learning docs
- Chunk documents
- Retrieve relevant snippets
- Answer with sources

`v0.7`: deployment and engineering

- Docker
- Cloud deployment
- Logs
- Environment management
- Database migration

## Acceptance Criteria

Functional:

- FastAPI service starts.
- `/health` works.
- `/docs` works.
- `/chat` accepts `user_id` and `message`.
- `/chat` calls replaceable LLM client.
- `/chat` returns structured tutor reply.
- `/chat` stores conversation history.
- `/conversations/{user_id}` returns recent history.
- Basic error handling exists.
- Basic tests exist.

Learning:

- Learner can explain project structure.
- Learner can explain the full `/chat` request flow.
- Learner can explain route, schema, service, client, repository, and database responsibilities.
- Learner can explain why v0.1 excludes auth, frontend, long-term memory, and RAG.
- Learner can use the docs to continue with AI-guided development.
