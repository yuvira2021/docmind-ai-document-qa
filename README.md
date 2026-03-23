# 🤖 AI-Powered Document Q&A System
### RAG Architecture · LangChain + OpenAI + FAISS · REST APIs · GCP Cloud Run

> **Resume bullet points:**
> - Built RAG-based document Q&A system using LangChain, FAISS vector store, and GPT-4o
> - Implemented REST APIs for LLM interaction with Node.js API Gateway and rate limiting
> - Deployed scalable microservices on GCP Cloud Run with CI/CD via GitHub Actions

---

## 🏗️ Architecture

```
User → Node.js API Gateway (Auth + Rate Limit)
           ↓
    Python FastAPI (LangChain RAG)
           ↓
    ┌──────────────────────────────┐
    │  Document Loader             │  PDF / TXT / DOCX
    │  Text Splitter               │  RecursiveCharacter (1000 tokens)
    │  OpenAI Embeddings           │  text-embedding-3-small
    │  FAISS Vector Store          │  Similarity Search (k=4)
    │  GPT-4o-mini                 │  Answer Generation
    │  ConversationalChain         │  Memory + Context
    └──────────────────────────────┘
           ↓
       GCP Cloud Run (auto-scaling, 0→10 instances)
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+
- OpenAI API key

### 1. Clone & Setup

```bash
git clone https://github.com/yourname/rag-document-qa
cd rag-document-qa
```

### 2. Python RAG Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Set env vars
export OPENAI_API_KEY="sk-..."

# Run
uvicorn main:app --reload --port 8080
# API docs: http://localhost:8080/docs
```

### 3. Node.js API Gateway

```bash
cd backend
npm install

# .env file
echo "RAG_SERVICE_URL=http://localhost:8080" > .env
echo "API_GATEWAY_KEY=my-secret-key" >> .env

npm start
# Gateway: http://localhost:3000
```

---

## 📡 API Reference

### Upload Document
```bash
curl -X POST http://localhost:3000/api/upload \
  -H "x-api-key: my-secret-key" \
  -F "file=@document.pdf"

# Response:
# { "session_id": "abc-123", "filename": "document.pdf", "chunk_count": 42 }
```

### Query Document
```bash
curl -X POST http://localhost:3000/api/query \
  -H "x-api-key: my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc-123", "question": "What is the main topic?"}'

# Response:
# { "answer": "The document discusses...", "sources": ["document.pdf"] }
```

### Delete Session
```bash
curl -X DELETE http://localhost:3000/api/session/abc-123 \
  -H "x-api-key: my-secret-key"
```

---

## ☁️ GCP Deployment

### Prerequisites
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### Deploy with Terraform

```bash
cd infra
terraform init
terraform plan -var="project_id=YOUR_PROJECT" -var="openai_api_key=sk-..."
terraform apply
```

### Deploy with Cloud Run (manual)

```bash
# Build & push images
gcloud builds submit --tag gcr.io/PROJECT_ID/rag-backend ./backend

# Deploy RAG Backend (internal)
gcloud run deploy rag-backend \
  --image gcr.io/PROJECT_ID/rag-backend \
  --region us-central1 \
  --memory 4Gi \
  --cpu 2 \
  --no-allow-unauthenticated \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest

# Deploy API Gateway (public)
gcloud run deploy rag-api-gateway \
  --image gcr.io/PROJECT_ID/api-gateway \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars RAG_SERVICE_URL=https://rag-backend-xxx.run.app
```

---

## 🔑 Key Technical Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Vector DB | FAISS | Zero infra, perfect for < 1M docs per session |
| Embeddings | text-embedding-3-small | Best cost/quality ratio |
| LLM | GPT-4o-mini | Fast, cheap, 128K context |
| Chunking | Recursive (1000 tokens, 200 overlap) | Preserves semantic boundaries |
| Memory | ConversationBufferMemory | Multi-turn Q&A |
| Deployment | Cloud Run | Serverless, scales to zero, pay-per-use |

---

## 📁 Project Structure

```
rag-system/
├── backend/
│   ├── main.py              # Python RAG service (FastAPI + LangChain)
│   ├── gateway.js           # Node.js API Gateway (Express)
│   ├── requirements.txt     # Python deps
│   ├── package.json         # Node deps
│   └── Dockerfile           # Container for RAG service
├── infra/
│   └── main.tf              # Terraform: GCP Cloud Run + Secrets
├── .github/
│   └── workflows/
│       └── deploy.yml       # CI/CD: test → build → deploy
└── README.md
```

---

## 💡 Resume Summary

```
• Built production RAG system using LangChain (FAISS vector store, OpenAI embeddings,
  GPT-4o) enabling semantic Q&A over uploaded PDF/DOCX/TXT documents
• Engineered REST API layer with Node.js/Express gateway featuring API key auth,
  rate limiting (100 req/15min), and multer-based file validation
• Deployed microservices on GCP Cloud Run with Terraform IaC, auto-scaling (0→10
  instances), Secret Manager integration, and GitHub Actions CI/CD pipeline
```
