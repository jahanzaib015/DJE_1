# OCRD Extractor - Render Deployment Guide

This guide will help you deploy both the frontend and backend of the OCRD Extractor application to Render.

## Prerequisites

1. A Render account (sign up at [render.com](https://render.com))
2. Your OpenAI API key
3. A GitHub repository with your code

## Deployment Steps

### Step 1: Deploy the Backend

1. **Connect your GitHub repository to Render:**
   - Go to your Render dashboard
   - Click "New +" → "Web Service"
   - Connect your GitHub account and select your repository

2. **Configure the Backend Service:**
   - **Name**: `ocrd-extractor-backend`
   - **Environment**: `Python 3`
   - **Build Command**: 
     ```bash
     pip install --upgrade pip
     pip install -r backend/requirements.txt
     ```
   - **Start Command**: 
     ```bash
     cd backend && python run.py
     ```
   - **Python Version**: `3.11.0`

3. **Set Environment Variables:**
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `HOST`: `0.0.0.0`
   - `PORT`: `8000`
   - `DEBUG`: `False`
   - `MAX_FILE_SIZE`: `50MB`
   - `UPLOAD_DIR`: `uploads`
   - `EXPORT_DIR`: `exports`
   - `DEFAULT_LLM_PROVIDER`: `openai`
   - `DEFAULT_MODEL`: `gpt-4`
   - `DEFAULT_ANALYSIS_METHOD`: `llm_with_fallback`

4. **Deploy the Backend:**
   - Click "Create Web Service"
   - Wait for the deployment to complete
   - Note down the backend URL (e.g., `https://ocrd-extractor-backend.onrender.com`)

### Step 2: Deploy the Frontend

1. **Create a new Static Site:**
   - Go to your Render dashboard
   - Click "New +" → "Static Site"
   - Connect your GitHub repository

2. **Configure the Frontend Service:**
   - **Name**: `ocrd-extractor-frontend`
   - **Build Command**: 
     ```bash
     cd frontend
     npm install
     npm run build
     ```
   - **Publish Directory**: `frontend/build`

3. **Set Environment Variables:**
   - `REACT_APP_API_URL`: Your backend URL from Step 1 (e.g., `https://ocrd-extractor-backend.onrender.com`)

4. **Deploy the Frontend:**
   - Click "Create Static Site"
   - Wait for the deployment to complete
   - Note down the frontend URL (e.g., `https://ocrd-extractor-frontend.onrender.com`)

### Step 3: Update Backend CORS Settings

After deploying both services, you need to update the backend CORS settings to allow your frontend domain:

1. Go to your backend service on Render
2. Add a new environment variable:
   - `FRONTEND_URL`: Your frontend URL from Step 2
3. Redeploy the backend service

### Step 4: Test the Deployment

1. Visit your frontend URL
2. Try uploading a PDF file
3. Check if the analysis works correctly
4. Monitor the backend logs for any errors

## Configuration Files Created

### Backend Configuration
- `backend/render.yaml` - Render service configuration
- `backend/requirements_render.txt` - Production requirements
- `backend/Procfile` - Process file for deployment
- `backend/runtime.txt` - Python version specification

### Frontend Configuration
- `frontend/render.yaml` - Render static site configuration
- Updated `frontend/package.json` with homepage setting
- Updated `frontend/src/services/AnalysisService.ts` with correct API URL

## Environment Variables Summary

### Backend Environment Variables
```
OPENAI_API_KEY=your_openai_api_key_here
HOST=0.0.0.0
PORT=8000
DEBUG=False
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4
DEFAULT_ANALYSIS_METHOD=llm_with_fallback
FRONTEND_URL=https://your-frontend-url.onrender.com
```

### Frontend Environment Variables
```
REACT_APP_API_URL=https://your-backend-url.onrender.com
```

## Troubleshooting

### Common Issues

1. **CORS Errors:**
   - Make sure `FRONTEND_URL` is set in backend environment variables
   - Check that the frontend URL is correct

2. **API Connection Issues:**
   - Verify `REACT_APP_API_URL` is set correctly in frontend
   - Check that the backend is running and accessible

3. **Build Failures:**
   - Check the build logs in Render dashboard
   - Ensure all dependencies are properly specified
   - Verify Python/Node.js versions are correct

4. **File Upload Issues:**
   - Check that `UPLOAD_DIR` and `EXPORT_DIR` are writable
   - Verify file size limits are appropriate

### Monitoring

- Check Render dashboard for service status
- Monitor logs for errors
- Use Render's built-in monitoring tools
- Set up alerts for service downtime

## Cost Considerations

- Render's free tier has limitations:
  - Services may sleep after 15 minutes of inactivity
  - Limited build minutes per month
  - Consider upgrading to paid plans for production use

## Security Notes

- Never commit API keys to your repository
- Use Render's environment variable system for sensitive data
- Consider using Render's database services for production data storage
- Implement proper authentication for production use

## Next Steps

1. Set up custom domains (if needed)
2. Configure SSL certificates
3. Set up monitoring and alerting
4. Implement database storage for job persistence
5. Add authentication and user management
6. Set up CI/CD pipelines for automatic deployments
