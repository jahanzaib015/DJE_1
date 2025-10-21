const express = require('express');
const cors = require('cors');
const multer = require('multer');
const axios = require('axios');
const WebSocket = require('ws');
const helmet = require('helmet');
const compression = require('compression');
const path = require('path');
const FormData = require('form-data');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || 'https://dje-1-3.onrender.com';

// Middleware
app.use(helmet());
app.use(compression());
const allowedOrigins = [
  "https://dje-1-4.onrender.com",
  "http://localhost:3000"
];

app.use(cors({
  origin: function (origin, callback) {
    if (!origin || allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      console.log("Blocked by CORS:", origin);
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

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, 'uploads/');
  },
  filename: (req, file, cb) => {
    cb(null, Date.now() + '-' + file.originalname);
  }
});

const upload = multer({ 
  storage: storage,
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') {
      cb(null, true);
    } else {
      cb(new Error('Only PDF files are allowed'), false);
    }
  },
  limits: {
    fileSize: 50 * 1024 * 1024 // 50MB limit
  }
});

// Ensure uploads directory exists
const fs = require('fs');
if (!fs.existsSync('uploads')) {
  fs.mkdirSync('uploads');
}

// Health check
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    timestamp: new Date().toISOString(),
    backend: PYTHON_BACKEND_URL
  });
});

// Test Python backend health
app.get('/api/health/backend', async (req, res) => {
  console.log('Backend health check requested');
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/health`);
    console.log('Backend health response:', response.data);
    res.json(response.data);
  } catch (error) {
    console.error('Backend health check failed:', error.message);
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
    console.error('Error fetching models:', error.message);
    res.status(500).json({ error: 'Failed to fetch models' });
  }
});

// File upload endpoint
app.post('/api/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' });
    }

    // Forward to Python backend
    const formData = new FormData();
    formData.append('file', fs.createReadStream(req.file.path), {
      filename: req.file.originalname,
      contentType: req.file.mimetype
    });

    const response = await axios.post(`${PYTHON_BACKEND_URL}/api/upload`, formData, {
      headers: {
        ...formData.getHeaders()
      }
    });

    // Clean up local file
    fs.unlinkSync(req.file.path);

    res.json(response.data);
  } catch (error) {
    console.error('Upload error:', error.message);
    res.status(500).json({ error: 'Upload failed' });
  }
});

// Analysis endpoint
app.post('/api/analyze', async (req, res) => {
  try {
    const response = await axios.post(`${PYTHON_BACKEND_URL}/api/analyze`, req.body);
    res.json(response.data);
  } catch (error) {
    console.error('Analysis error:', error.message);
    res.status(500).json({ error: 'Analysis failed' });
  }
});

// Job status endpoint
app.get('/api/jobs/:jobId/status', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${req.params.jobId}/status`);
    res.json(response.data);
  } catch (error) {
    console.error('Status error:', error.message);
    res.status(500).json({ error: 'Failed to get job status' });
  }
});

// Job results endpoint
app.get('/api/jobs/:jobId/results', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${req.params.jobId}/results`);
    res.json(response.data);
  } catch (error) {
    console.error('Results error:', error.message);
    res.status(500).json({ error: 'Failed to get results' });
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
    console.error('Export error:', error.message);
    res.status(500).json({ error: 'Export failed' });
  }
});

// Export JSON endpoint
app.get('/api/jobs/:jobId/export/json', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/jobs/${req.params.jobId}/export/json`);
    res.json(response.data);
  } catch (error) {
    console.error('Export error:', error.message);
    res.status(500).json({ error: 'Export failed' });
  }
});

// WebSocket proxy for real-time updates
const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', (ws, req) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const jobId = url.pathname.split('/').pop();
  
  // Connect to Python backend WebSocket
  const backendWs = new WebSocket(
    `${PYTHON_BACKEND_URL.replace('http', 'ws')}/ws/jobs/${jobId}`
  );
  
  
  backendWs.on('message', (data) => {
    ws.send(data);
  });
  
  backendWs.on('close', () => {
    ws.close();
  });
  
  ws.on('close', () => {
    backendWs.close();
  });
});

// Error handling middleware
app.use((error, req, res, next) => {
  console.error('Server error:', error);
  res.status(500).json({ error: 'Internal server error' });
});

// Serve React app for all other routes (but not API routes)
app.get('*', (req, res) => {
  console.log('Catch-all route hit:', req.path, req.method);
  // Don't serve React app for API routes
  if (req.path.startsWith('/api/')) {
    console.log('API route not found:', req.path);
    return res.status(404).json({ error: 'API endpoint not found' });
  }
  console.log('Serving React app for:', req.path);
  res.sendFile(path.join(__dirname, 'frontend/build', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`🚀 Node.js server running on port ${PORT}`);
  console.log(`📡 Python backend: ${PYTHON_BACKEND_URL}`);
  console.log(`🌐 WebSocket server on port 8080`);
});
