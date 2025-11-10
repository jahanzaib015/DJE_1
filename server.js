const express = require('express');
const cors = require('cors');
const multer = require('multer');
const axios = require('axios');
const WebSocket = require('ws');
const helmet = require('helmet');
const compression = require('compression');
const path = require('path');
const FormData = require('form-data');
const fs = require('fs');
const morgan = require('morgan');
const logger = require('./logger');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;
// Use localhost for local development, or Render URL for production
const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || (process.env.NODE_ENV === 'production' ? 'https://dje-1-3.onrender.com' : 'http://localhost:8000');

// Middleware
app.use(helmet());
app.use(compression());

// Enhanced logging middleware
app.use(morgan('combined', {
    skip: (req, res) => res.statusCode < 400,
    stream: {
        write: (message) => {
            logger.info(`[HTTP] ${message.trim()}`);
        }
    }
}));

// Request logging middleware
app.use((req, res, next) => {
    const requestId = req.headers['x-request-id'] || `req_${Date.now()}`;
    req.requestId = requestId;
    res.setHeader('X-Request-ID', requestId);
    
    const startTime = Date.now();
    
    // Log incoming request
    const logData = {
        requestId,
        method: req.method,
        path: req.path,
        query: req.query,
        headers: {
            'content-type': req.headers['content-type'],
            'user-agent': req.headers['user-agent'],
            'origin': req.headers['origin']
        },
        ip: req.ip || req.connection.remoteAddress
    };
    
    logger.info(`📥 INCOMING ${req.method} ${req.path}`, JSON.stringify(logData, null, 2), requestId);
    
    // Log response
    res.on('finish', () => {
        const duration = Date.now() - startTime;
        if (res.statusCode >= 400) {
            logger.error(`OUTGOING ${req.method} ${req.path} | Status: ${res.statusCode} | Duration: ${duration}ms`, null, requestId);
        } else {
            logger.info(`✅ OUTGOING ${req.method} ${req.path} | Status: ${res.statusCode} | Duration: ${duration}ms`, null, requestId);
        }
    });
    
    next();
});

const allowedOrigins = [
  "https://dje-1-4.onrender.com",
  "http://localhost:3000"
];

app.use(cors({
  origin: function (origin, callback) {
    if (!origin || allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      logger.warn("Blocked by CORS", { origin });
      callback(new Error("Not allowed by CORS"));
    }
  },
  methods: ["GET", "POST", "OPTIONS"],
  credentials: true,
  allowedHeaders: ["Content-Type", "Authorization"]
}));

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Serve static files from React build
app.use(express.static(path.join(__dirname, 'frontend/build')));

// Ensure uploads directory exists
if (!fs.existsSync('uploads')) {
  fs.mkdirSync('uploads');
}

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, 'uploads/'),
  filename: (req, file, cb) => cb(null, Date.now() + '-' + file.originalname)
});

const upload = multer({
  storage,
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') cb(null, true);
    else cb(new Error('Only PDF files are allowed'), false);
  },
  limits: { fileSize: 50 * 1024 * 1024 }
});

// Health check
app.get('/api/health', (req, res) => {
  logger.info('Health check requested', null, req.requestId);
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    backend: PYTHON_BACKEND_URL
  });
});

// Test Python backend health
app.get('/api/health/backend', async (req, res) => {
  logger.info(`🔍 Checking backend health at ${PYTHON_BACKEND_URL}...`, null, req.requestId);
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/health`, {
      timeout: 5000,
      headers: {
        'X-Request-ID': req.requestId
      }
    });
    logger.info('✅ Backend healthy', response.data, req.requestId);
    res.json(response.data);
  } catch (error) {
    logger.error('❌ Backend health check failed', { message: error.message }, req.requestId);
    if (error.response) {
      logger.error('Backend response', { status: error.response.status, data: error.response.data }, req.requestId);
    }
    res.status(500).json({
      error: 'Backend health check failed',
      backend: PYTHON_BACKEND_URL,
      details: error.message
    });
  }
});

// Get available models
app.get('/api/models', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/models`);
    res.json(response.data);
  } catch (error) {
    logger.error('Error fetching models', { message: error.message });
    res.status(500).json({ error: 'Failed to fetch models' });
  }
});

// ✅ FIXED FILE UPLOAD ENDPOINT — works on Render reliably
app.post('/api/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      logger.error('No file uploaded', null, req.requestId);
      return res.status(400).json({ error: 'No file uploaded' });
    }

    logger.info(`📤 Upload received: ${req.file.originalname} (${req.file.size} bytes, ${req.file.mimetype})`, null, req.requestId);
    logger.info(`📡 Forwarding to backend: ${PYTHON_BACKEND_URL}/api/upload`, null, req.requestId);

    // 💤 Wake backend before upload (Render free-tier workaround)
    try {
      await axios.get(`${PYTHON_BACKEND_URL}/api/health`, { 
        timeout: 5000,
        headers: { 'X-Request-ID': req.requestId }
      });
      logger.info('✅ Python backend is awake', null, req.requestId);
    } catch (err) {
      logger.warn(`⚠️ Python backend unreachable before upload: ${err.message}`, null, req.requestId);
      logger.warn('⚠️ Continuing with upload anyway - backend may wake up during processing', null, req.requestId);
      // Don't return error - let the upload proceed and let the backend wake up naturally
    }

    // ✅ Read file into buffer instead of stream
    const fileBuffer = fs.readFileSync(req.file.path);

    const formData = new FormData();
    formData.append('file', fileBuffer, {
      filename: req.file.originalname,
      contentType: req.file.mimetype,
    });

    // Perform upload
    logger.info('📤 Sending file to Python backend...', null, req.requestId);
    const response = await axios.post(`${PYTHON_BACKEND_URL}/api/upload`, formData, {
      headers: {
        ...formData.getHeaders(),
        'X-Request-ID': req.requestId
      },
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
      timeout: 90000,
    });

    fs.unlinkSync(req.file.path); // clean temp

    logger.info('✅ Upload success', response.data, req.requestId);
    res.json(response.data);
  } catch (error) {
    logger.error('❌ Upload proxy error', { message: error.message }, req.requestId);

    if (error.response) {
      logger.error('Backend returned', { status: error.response.status, data: error.response.data }, req.requestId);
      res.status(error.response.status).json({
        error: error.response.data?.detail || error.response.data || 'Backend error',
      });
    } else if (error.request) {
      logger.error('❌ No response from backend', { message: error.message }, req.requestId);
      res.status(503).json({ error: 'Backend unavailable: ' + error.message });
    } else {
      logger.error('❌ Upload error', { message: error.message }, req.requestId);
      res.status(500).json({ error: 'Upload failed: ' + error.message });
    }
  }
});

// Analysis endpoint
app.post('/api/analyze', async (req, res) => {
  try {
    logger.info('🚀 Starting analysis', req.body, req.requestId);
    const response = await axios.post(`${PYTHON_BACKEND_URL}/api/analyze`, req.body, {
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': req.requestId
      },
      timeout: 30000
    });
    logger.info('✅ Analysis started', response.data, req.requestId);
    res.json(response.data);
  } catch (error) {
    logger.error('❌ Analysis error', { message: error.message }, req.requestId);
    if (error.response) {
      logger.error('Backend response', { status: error.response.status, data: error.response.data }, req.requestId);
      res.status(error.response.status).json(error.response.data);
    } else {
      res.status(500).json({ error: 'Analysis failed: ' + error.message });
    }
  }
});

// Job status endpoint
app.get('/api/jobs/:jobId/status', async (req, res) => {
  try {
    const jobId = req.params.jobId;
    logger.info(`📊 Getting status for job: ${jobId}`, null, req.requestId);
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${jobId}/status`, {
      headers: { 'X-Request-ID': req.requestId },
      timeout: 10000
    });
    logger.info('✅ Job status', { status: response.data.status }, req.requestId);
    res.json(response.data);
  } catch (error) {
    logger.error('❌ Status error', { message: error.message }, req.requestId);
    if (error.response) {
      res.status(error.response.status).json(error.response.data);
    } else {
      res.status(500).json({ error: 'Failed to get job status: ' + error.message });
    }
  }
});

// Job results endpoint
app.get('/api/jobs/:jobId/results', async (req, res) => {
  try {
    const jobId = req.params.jobId;
    logger.info(`📋 Getting results for job: ${jobId}`, null, req.requestId);
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${jobId}/results`, {
      headers: { 'X-Request-ID': req.requestId },
      timeout: 30000
    });
    logger.info(`✅ Results retrieved for job: ${jobId}`, null, req.requestId);
    res.json(response.data);
  } catch (error) {
    logger.error('❌ Results error', { message: error.message }, req.requestId);
    if (error.response) {
      res.status(error.response.status).json(error.response.data);
    } else {
      res.status(500).json({ error: 'Failed to get results: ' + error.message });
    }
  }
});

// Export Excel endpoint
app.get('/api/jobs/:jobId/export/excel', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${req.params.jobId}/export/excel`, {
      responseType: 'stream'
    });
    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    res.setHeader('Content-Disposition', 'attachment; filename=ocrd_results.xlsx');
    response.data.pipe(res);
  } catch (error) {
    logger.error('Export Excel error', { message: error.message });
    res.status(500).json({ error: 'Export failed' });
  }
});

// Export JSON endpoint
app.get('/api/jobs/:jobId/export/json', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${req.params.jobId}/export/json`);
    res.json(response.data);
  } catch (error) {
    logger.error('Export JSON error', { message: error.message });
    res.status(500).json({ error: 'Export failed' });
  }
});

// WebSocket proxy for real-time updates
const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', (ws, req) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const jobId = url.pathname.split('/').pop();

  const backendWs = new WebSocket(
    `${PYTHON_BACKEND_URL.replace('http', 'ws')}/ws/jobs/${jobId}`
  );

  backendWs.on('message', (data) => ws.send(data));
  backendWs.on('close', () => ws.close());
  ws.on('close', () => backendWs.close());
});

// Error handling middleware
app.use((error, req, res, next) => {
  logger.error('Server error', { error: error.message, stack: error.stack });
  res.status(500).json({ error: 'Internal server error' });
});

// Serve React app for all non-API routes
app.get('*', (req, res) => {
  logger.debug('Serving React app', { path: req.path });
  if (req.path.startsWith('/api/')) {
    return res.status(404).json({ error: 'API endpoint not found' });
  }
  res.sendFile(path.join(__dirname, 'frontend/build', 'index.html'));
});

app.listen(PORT, () => {
  logger.info(`🚀 Node.js server running on port ${PORT}`);
  logger.info(`📡 Python backend: ${PYTHON_BACKEND_URL}`);
  logger.info(`🌐 WebSocket server on port 8080`);
});
