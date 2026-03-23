# DocMind — AI Document Intelligence Platform

> RAG-based document Q&A system using LangChain, OpenAI GPT-4o, FAISS, FastAPI, Node.js — deployed on GCP Cloud Run

## Live Demo
- API Gateway: https://rag-api-gateway-328140872450.us-central1.run.app
- Health Check: https://rag-api-gateway-328140872450.us-central1.run.app/health

## Tech Stack
| Layer | Technology |
|---|---|
| RAG Framework | LangChain — document loaders, text splitting, retrieval chains |
| LLM | GPT-4o-mini (OpenAI) |
| Embeddings | text-embedding-3-small (OpenAI) |
| Vector Store | FAISS — in-memory cosine similarity search |
| Python API | FastAPI + uvicorn |
| API Gateway | Node.js + Express |
| Cloud | GCP Cloud Run (auto-scaling 0→10 instances) |
| Containers | Docker (AMD64 cross-platform builds) |
| Secrets | GCP Secret Manager |
| Frontend | Single-file HTML/CSS/JS |

## Architecture
```
Client → Node.js Gateway (auth, rate limit) → Python RAG Service → OpenAI API
                                                      ↓
                                               FAISS Vector Index
```

## Quick Start
```bash
# Python server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
uvicorn main:app --port 8080

# Node.js gateway (new terminal)
npm install
echo "RAG_SERVICE_URL=http://localhost:8080" > .env
echo "API_GATEWAY_KEY=mydevkey123" >> .env
node gateway.js
```

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| POST | /api/upload | Upload PDF/DOCX/TXT document |
| POST | /api/query | Ask question about document |
| GET | /api/session/:id | Get session info |
| DELETE | /api/session/:id | Delete session |
| GET | /health | Health check |

## Resume Highlights
- Built RAG system using LangChain (FAISS, OpenAI embeddings, GPT-4o) for semantic document Q&A
- Implemented REST APIs with Node.js/Express gateway featuring auth, rate limiting, and file validation
- Deployed microservices on GCP Cloud Run with Docker, Secret Manager, and auto-scaling
