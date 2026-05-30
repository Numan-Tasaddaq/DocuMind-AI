# DocuMind AI

DocuMind AI is a full-stack document intelligence assistant that lets users upload documents and ask natural-language questions grounded in their own files.

It combines secure authentication, user-isolated chat history, document parsing, RAG retrieval, and Gemini-powered responses in a Dockerized workflow with CI/CD support.

## Features

- Email/password authentication with secure password hashing
- OAuth sign-in and sign-up with Google and GitHub
- User profile and password update flow
- Chat workspace with per-user conversations
- Conversation rename and delete actions
- File upload with validation
- Document parsing for PDF, DOCX, XLS, XLSX
- RAG retrieval using embeddings + vector database
- One-click quick action: summarize latest uploaded document
- Docker-based local stack (frontend, backend, PostgreSQL)
- GitHub Actions CI and local CD (self-hosted runner)

## Problem It Solves

Teams and individuals often keep important information buried in resumes, reports, handbooks, spreadsheets, and certificates.

DocuMind AI turns those static files into an interactive assistant:

- Upload documents once
- Ask questions in plain language
- Retrieve relevant context quickly
- Keep conversations and documents isolated per user

## Tech Stack

### Backend

- FastAPI
- SQLAlchemy
- PostgreSQL
- JWT auth + bcrypt hashing

### AI / RAG

- Google Gemini API for generation
- LangChain for chunking/retrieval pipeline
- Gemini embeddings (`langchain-google-genai`)
- ChromaDB vector store (`langchain-chroma`)
- Document loaders and parsers:
  - PyPDFLoader
  - Docx2txt loader
  - XLS/XLSX parsing pipeline

### Frontend

- HTML, CSS, JavaScript
- Responsive dashboard UI
- Conversation and file-management UX

### DevOps

- Docker and Docker Compose
- GitHub Actions CI
- GitHub Actions local CD via self-hosted runner

## Project Structure

```text
DocuMind AI/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── core/
│   │   ├── database/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── utils/
│   ├── database/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   ├── dashboard.html
│   ├── profile.html
│   ├── app.js
│   ├── dashboard.js
│   └── Dockerfile
├── .github/workflows/
│   ├── ci.yml
│   └── deploy-local.yml
├── docker-compose.yml
└── README.md
```

## Authentication and Security

- Passwords are hashed with bcrypt
- JWT bearer authentication for protected endpoints
- Account lock controls for repeated failed logins
- OAuth state checks for provider callbacks
- Sensitive values are loaded from environment variables
- Runtime storage is excluded from git (`backend/storage/`)

## Document Upload Rules

- Allowed extensions: PDF, DOC, DOCX, XLS, XLSX
- Max file size: 10 MB per file
- Max selected/uploaded files: 5
- Encrypted/password-protected PDF upload is blocked

## RAG Flow

1. User uploads a document.
2. Backend parses text.
3. Content is chunked with LangChain.
4. Chunks are embedded using Gemini embeddings.
5. Embeddings are stored in Chroma.
6. At chat time, relevant chunks are retrieved.
7. Retrieved context is appended to prompt for grounded answers.

## Quick Actions

- `Summarize Latest`: summarizes the most recently uploaded document in one click.

## API Overview

### Auth

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/change-password`
- `GET /api/auth/oauth/{provider}/start`
- `GET /api/auth/oauth/{provider}/callback`

### Chats

- `GET /api/chats`
- `POST /api/chats`
- `GET /api/chats/{conversation_id}`
- `PATCH /api/chats/{conversation_id}`
- `DELETE /api/chats/{conversation_id}`
- `POST /api/chats/{conversation_id}/messages`

### Documents

- `POST /api/documents/upload`
- `GET /api/documents`
- `DELETE /api/documents/{document_id}`

### Health

- `GET /health`

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and provide real values.

Important keys:

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DATABASE_URL`
- `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRES_MINUTES`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`
- `FRONTEND_AUTH_CALLBACK_URL`
- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`
- `CHROMA_PERSIST_DIRECTORY`, `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_TOP_K`

## Local Development (Without Docker)

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd ..
python -m http.server 5500
```

Open:

- Frontend: `http://127.0.0.1:5500/frontend/index.html`
- Backend health: `http://127.0.0.1:8000/health`

## Docker Setup

```bash
docker compose up --build
```

Open:

- Frontend: `http://127.0.0.1:8080`
- Backend health: `http://127.0.0.1:8000/health`

Stop:

```bash
docker compose down
```

## CI/CD

### CI (`.github/workflows/ci.yml`)

- Runs on push and pull request to `main`
- Backend compile/syntax check
- Frontend JavaScript syntax check
- Docker build validation for frontend and backend images

### CD (`.github/workflows/deploy-local.yml`)

- Runs on push to `main` and manual dispatch
- Executes on self-hosted Windows runner
- Rebuilds and restarts Docker services locally
- Verifies backend health after deployment

## Self-Hosted Runner Notes

- For public repositories, use self-hosted runners carefully
- Restrict deployment workflows to trusted events
- Avoid running untrusted pull-request code on local infrastructure

## Troubleshooting

### Google/GitHub OAuth keeps spinning

- Check callback URLs in provider console match backend config exactly
- Confirm `FRONTEND_AUTH_CALLBACK_URL` points to current frontend URL
- Clear browser cache/local storage and retry

### `backend/.env` not found in CD

- CD workflow auto-generates `backend/.env` from `.env.example` if missing
- For production secrets, use GitHub Secrets injection

### Gemini quota or model errors

- Verify billing/quota for your Gemini project
- Use supported models for generation and embeddings

### Docker build fails with I/O errors

- Ensure sufficient disk space
- Move Docker disk image to larger drive
- Prune old build cache and retry

## Security Best Practices

- Never commit real `.env` files
- Rotate API keys and OAuth secrets periodically
- Keep least-privilege DB and service accounts
- Enable GitHub secret scanning and branch protection rules

## Roadmap

- Add automated tests (unit + integration)
- Add staging environment
- Add cloud deployment target
- Add observability and structured logging
- Add document-level access controls and audit logs

## License

Add your preferred license file (`MIT`, `Apache-2.0`, etc.) and reference it here.
