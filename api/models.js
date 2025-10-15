const axios = require('axios');

module.exports = async (req, res) => {
  try {
    const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || 'http://localhost:8000';
    const response = await axios.get(`${PYTHON_BACKEND_URL}/api/models`);
    res.json(response.data);
  } catch (error) {
    console.error('Error fetching models:', error.message);
    res.status(500).json({ error: 'Failed to fetch models' });
  }
};
