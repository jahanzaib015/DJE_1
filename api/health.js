module.exports = (req, res) => {
  res.status(200).json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    backend: process.env.PYTHON_BACKEND_URL || 'http://localhost:8000'
  });
};
