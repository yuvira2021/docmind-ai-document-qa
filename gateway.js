/**
 * Node.js API Gateway — Document Q&A System
 * Acts as a BFF (Backend for Frontend) layer:
 *  - Auth middleware (API key validation)
 *  - Rate limiting
 *  - Request logging
 *  - Proxies to Python RAG service
 */

const express = require("express");
const multer = require("multer");
const axios = require("axios");
const FormData = require("form-data");
const rateLimit = require("express-rate-limit");
const morgan = require("morgan");
const cors = require("cors");
require("dotenv").config();

const app = express();
const PORT = process.env.PORT || 3000;
const RAG_SERVICE_URL = process.env.RAG_SERVICE_URL || "http://localhost:8080";
const API_KEY = process.env.API_GATEWAY_KEY || "dev-key-change-in-prod";

// ─── Middleware ────────────────────────────────────────────────────────────────
app.use(cors({ origin: "*" }));
app.use(express.json());
app.use(morgan("combined"));

// Rate limiting: 100 req/15min per IP
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: { error: "Too many requests, please try again later." },
});
app.use("/api/", limiter);

// Stricter limit for uploads
const uploadLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, // 1 hour
  max: 20,
  message: { error: "Upload limit reached. Max 20 uploads per hour." },
});

// ─── Auth Middleware ───────────────────────────────────────────────────────────
const authenticate = (req, res, next) => {
  const key = req.headers["x-api-key"];
  if (!key || key !== API_KEY) {
    return res.status(401).json({ error: "Invalid or missing API key" });
  }
  next();
};

// ─── File Upload Config ────────────────────────────────────────────────────────
const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: 50 * 1024 * 1024 }, // 50MB max
  fileFilter: (req, file, cb) => {
    const allowed = [".pdf", ".txt", ".docx", ".doc"];
    const ext = "." + file.originalname.split(".").pop().toLowerCase();
    if (allowed.includes(ext)) {
      cb(null, true);
    } else {
      cb(new Error(`Unsupported file type: ${ext}`));
    }
  },
});

// ─── Routes ───────────────────────────────────────────────────────────────────

// Health check (public)
app.get("/health", async (req, res) => {
  try {
    const { data } = await axios.get(`${RAG_SERVICE_URL}/health`, { timeout: 5000 });
    res.json({ gateway: "healthy", ragService: data });
  } catch {
    res.status(503).json({ gateway: "healthy", ragService: "unreachable" });
  }
});

// Upload document
app.post(
  "/api/upload",
  authenticate,
  uploadLimiter,
  upload.single("file"),
  async (req, res) => {
    if (!req.file) {
      return res.status(400).json({ error: "No file provided" });
    }

    try {
      const form = new FormData();
      form.append("file", req.file.buffer, {
        filename: req.file.originalname,
        contentType: req.file.mimetype,
      });

      const { data } = await axios.post(`${RAG_SERVICE_URL}/upload`, form, {
        headers: form.getHeaders(),
        timeout: 120_000, // 2 min for large docs
      });

      console.log(`[UPLOAD] session=${data.session_id} file=${data.filename} chunks=${data.chunk_count}`);
      res.json(data);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      res.status(err.response?.status || 500).json({ error: msg });
    }
  }
);

// Query document
app.post("/api/query", authenticate, async (req, res) => {
  const { session_id, question, chat_history } = req.body;

  if (!session_id || !question) {
    return res.status(400).json({ error: "session_id and question are required" });
  }
  if (question.length > 2000) {
    return res.status(400).json({ error: "Question too long (max 2000 chars)" });
  }

  try {
    const { data } = await axios.post(
      `${RAG_SERVICE_URL}/query`,
      { session_id, question, chat_history: chat_history || [] },
      { timeout: 60_000 }
    );
    console.log(`[QUERY] session=${session_id} q="${question.slice(0, 60)}..."`);
    res.json(data);
  } catch (err) {
    const msg = err.response?.data?.detail || err.message;
    res.status(err.response?.status || 500).json({ error: msg });
  }
});

// Get session info
app.get("/api/session/:id", authenticate, async (req, res) => {
  try {
    const { data } = await axios.get(`${RAG_SERVICE_URL}/session/${req.params.id}`);
    res.json(data);
  } catch (err) {
    res.status(err.response?.status || 404).json({ error: "Session not found" });
  }
});

// Delete session
app.delete("/api/session/:id", authenticate, async (req, res) => {
  try {
    const { data } = await axios.delete(`${RAG_SERVICE_URL}/session/${req.params.id}`);
    res.json(data);
  } catch (err) {
    res.status(err.response?.status || 404).json({ error: "Session not found" });
  }
});

// List sessions
app.get("/api/sessions", authenticate, async (req, res) => {
  try {
    const { data } = await axios.get(`${RAG_SERVICE_URL}/sessions`);
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: "Failed to list sessions" });
  }
});

// ─── Error Handler ─────────────────────────────────────────────────────────────
app.use((err, req, res, next) => {
  console.error("[ERROR]", err.message);
  if (err instanceof multer.MulterError) {
    return res.status(400).json({ error: `Upload error: ${err.message}` });
  }
  res.status(500).json({ error: err.message || "Internal server error" });
});

// ─── Start ─────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🚀 API Gateway running on http://localhost:${PORT}`);
  console.log(`📡 Proxying to RAG service: ${RAG_SERVICE_URL}`);
  console.log(`🔑 API Key auth: enabled\n`);
});

module.exports = app;
