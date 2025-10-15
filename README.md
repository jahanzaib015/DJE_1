# OCRD Extractor - Modern API

A modern, fast, and flexible document analysis system with multiple LLM providers.

## 🚀 Features

- **Multiple LLM Providers**: OpenAI (ChatGPT), Ollama, and more
- **Smart Analysis**: Fast keyword analysis with LLM fallback
- **Modern UI**: Clean, responsive web interface
- **Real-time Updates**: WebSocket-powered progress tracking
- **Export Options**: Excel and JSON export
- **API-First**: RESTful API for easy integration

## 📦 Installation

### Prerequisites
- Python 3.8+
- OpenAI API key (optional, for ChatGPT integration)

### 🚀 Quick Start (Recommended)

**For Windows users:**
```bash
# Run the automated installer
install_windows.bat
```

**For all platforms:**
```bash
# Run the Python installer
python install.py
```

### 🔧 Manual Installation

If the automated installer doesn't work, try manual installation:

1. **Create virtual environment**:
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

2. **Install dependencies** (choose one method):

**Method 1 - Minimal (recommended for Windows):**
```bash
pip install -r requirements_minimal.txt
```

**Method 2 - Full backend:**
```bash
cd backend
pip install -r requirements_simple.txt
cd ..
pip install -r requirements.txt
```

**Method 3 - If compilation fails:**
```bash
pip install --only-binary=all -r backend/requirements_simple.txt
pip install --only-binary=all -r requirements.txt
```

3. **Set up environment** (optional):
```bash
cp backend/env.example backend/.env
# Edit backend/.env and add your OpenAI API key
```

4. **Run the server**:
```bash
cd backend
python run.py
```

5. **Open your browser**:
- Main app: http://localhost:8000
- API docs: http://localhost:8000/docs

### 🛠️ Troubleshooting

**If you get Rust compilation errors:**
- Use `requirements_minimal.txt` instead
- Or install with `--only-binary=all` flag

**If you get "ModuleNotFoundError":**
- Make sure virtual environment is activated
- Try: `pip install --upgrade pip`
- Reinstall dependencies

**For Windows users having issues:**
- Install Visual Studio Build Tools
- Or use the `install_windows.bat` script

## 🎯 Usage

### Web Interface
1. Open http://localhost:8000
2. Choose analysis method:
   - **Fast Keywords**: Instant results using keyword matching
   - **LLM Only**: AI analysis (slower but more accurate)
   - **LLM with Fallback**: Best of both worlds (recommended)
3. Select LLM provider (OpenAI or Ollama)
4. Upload your PDF document
5. View results and export

### API Usage

#### Upload File
```bash
curl -X POST "http://localhost:8000/api/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

#### Start Analysis
```bash
curl -X POST "http://localhost:8000/api/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "uploads/document.pdf",
    "analysis_method": "llm_with_fallback",
    "llm_provider": "openai",
    "model": "gpt-4",
    "fund_id": "5800"
  }'
```

#### Get Results
```bash
curl "http://localhost:8000/api/jobs/{job_id}/results"
```

## 🔧 Configuration

### Environment Variables
- `OPENAI_API_KEY`: Your OpenAI API key for ChatGPT integration
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)

### Analysis Methods
- `keywords`: Fast keyword-based analysis
- `llm`: AI-powered analysis only
- `llm_with_fallback`: Try LLM first, fallback to keywords

### LLM Providers
- `openai`: ChatGPT (requires API key)
- `ollama`: Local Ollama installation

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main web interface |
| `/api/upload` | POST | Upload PDF file |
| `/api/analyze` | POST | Start document analysis |
| `/api/jobs/{job_id}/status` | GET | Get job status |
| `/api/jobs/{job_id}/results` | GET | Get analysis results |
| `/api/jobs/{job_id}/export/excel` | GET | Export to Excel |
| `/api/jobs/{job_id}/export/json` | GET | Export to JSON |
| `/ws/jobs/{job_id}` | WebSocket | Real-time updates |

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │    │   FastAPI       │    │   LLM Providers │
│   (HTML/JS)     │◄──►│   Backend       │◄──►│   (OpenAI/Ollama)│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   File Storage  │
                       │   (Uploads/Exports)│
                       └─────────────────┘
```

## 🔄 Migration from Streamlit

This modern API replaces the Streamlit version with:
- ✅ **Better Performance**: Async processing and real-time updates
- ✅ **More Flexible**: Multiple LLM providers and analysis methods
- ✅ **API-First**: Easy to integrate with other systems
- ✅ **Modern UI**: Clean, responsive interface
- ✅ **Cost Optimized**: Smart fallback to reduce API costs

## 🚀 Deployment

### Local Development
```bash
python run.py
```

### Production
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker (Coming Soon)
```bash
docker-compose up
```

## 📝 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

For issues and questions:
- Create an issue on GitHub
- Check the API documentation at `/docs`
- Review the logs for error details