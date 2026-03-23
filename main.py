"""
AI-Powered Document Q&A System
RAG Backend: LangChain + OpenAI + FAISS + FastAPI
"""

import os
import uuid
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App Setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="RAG Document Q&A API",
    description="AI-powered document question answering using LangChain + FAISS",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-Memory Store (use Redis/Firestore in prod) ─────────────────────────────
sessions: dict = {}   # session_id -> {vectorstore, chain, doc_meta}

# ─── Models ───────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    session_id: str
    question: str
    chat_history: Optional[list] = []

class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str

class SessionInfo(BaseModel):
    session_id: str
    filename: str
    chunk_count: int
    status: str

# ─── Custom RAG Prompt ────────────────────────────────────────────────────────
CUSTOM_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are an expert document analyst. Use ONLY the provided context to answer questions.
If the answer is not in the context, say "I couldn't find that in the document."

Context:
{context}

Question: {question}

Answer (be precise, cite page numbers if available):"""
)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_loader(file_path: str, filename: str):
    """Select appropriate document loader based on file extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return PyPDFLoader(file_path)
    elif ext == ".txt":
        return TextLoader(file_path)
    elif ext in [".docx", ".doc"]:
        return Docx2txtLoader(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def build_rag_chain(file_path: str, filename: str) -> tuple:
    """
    Core RAG pipeline:
    1. Load document
    2. Split into chunks
    3. Embed with OpenAI
    4. Index with FAISS
    5. Build ConversationalRetrievalChain
    """
    # 1. Load
    loader = get_loader(file_path, filename)
    documents = loader.load()
    logger.info(f"Loaded {len(documents)} pages from {filename}")

    # 2. Split
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    logger.info(f"Split into {len(chunks)} chunks")

    # 3. Embed + Index
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    logger.info("FAISS index built successfully")

    # 4. Build chain with memory
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer",
    )
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectorstore.as_retriever(search_kwargs={"k": 4}),
        memory=memory,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": CUSTOM_PROMPT},
    )
    return vectorstore, chain, len(chunks)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "RAG Document Q&A API", "version": "1.0.0"}


@app.post("/upload", response_model=SessionInfo)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a document (PDF/TXT/DOCX).
    Returns a session_id to use for subsequent queries.
    """
    allowed_types = {".pdf", ".txt", ".docx", ".doc"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_types:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {allowed_types}")

    session_id = str(uuid.uuid4())

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        vectorstore, chain, chunk_count = build_rag_chain(tmp_path, file.filename)
        sessions[session_id] = {
            "vectorstore": vectorstore,
            "chain": chain,
            "filename": file.filename,
            "chunk_count": chunk_count,
        }
        logger.info(f"Session {session_id} created for {file.filename}")
    finally:
        os.unlink(tmp_path)

    return SessionInfo(
        session_id=session_id,
        filename=file.filename,
        chunk_count=chunk_count,
        status="ready",
    )


@app.post("/query", response_model=QueryResponse)
async def query_document(req: QueryRequest):
    """
    Ask a question about the uploaded document.
    Maintains conversational context within the session.
    """
    if req.session_id not in sessions:
        raise HTTPException(404, "Session not found. Please upload a document first.")

    session = sessions[req.session_id]
    chain = session["chain"]

    try:
        result = chain({"question": req.question})
        answer = result["answer"]
        sources = list({
            doc.metadata.get("source", "Document")
            for doc in result.get("source_documents", [])
        })
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(500, f"Query failed: {str(e)}")

    return QueryResponse(
        answer=answer,
        sources=sources,
        session_id=req.session_id,
    )


@app.get("/session/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Get info about an active session."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    s = sessions[session_id]
    return SessionInfo(
        session_id=session_id,
        filename=s["filename"],
        chunk_count=s["chunk_count"],
        status="ready",
    )


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Clean up a session and free memory."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    del sessions[session_id]
    return {"message": f"Session {session_id} deleted"}


@app.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    return {
        "sessions": [
            {"session_id": sid, "filename": s["filename"], "chunks": s["chunk_count"]}
            for sid, s in sessions.items()
        ]
    }
