# Investment Classification System

A chatbot system that reads customer documents, matches them against your investment catalog using embeddings, checks business constraints, and returns YES/NO decisions with reasoning.

## Features

- **Embedding-based matching**: Uses sentence transformers to match customer documents to your investment catalog, even with different wording
- **Synonym support**: Handles variations in terminology (e.g., "gold" → "precious metals")
- **Constraint checking**: Validates business rules (min ticket size, investor types, regions, etc.)
- **Fuzzy matching**: Combines embedding similarity with fuzzy string matching for robustness
- **Ambiguity detection**: Identifies when multiple matches are close and requests clarification

## Installation

1. Install the new dependencies:
```bash
pip install sentence-transformers rapidfuzz spacy
python -m spacy download en_core_web_sm
```

2. The system will automatically create a default catalog on first run at `backend/data/investment_catalog.json`

## API Endpoints

### Classify a Document

**POST** `/api/classify`

Classify a customer document against your investment catalog.

**Request Body:**
```json
{
  "document_text": "Client proposal: Gold investment for professional investors in the EU. Indicative ticket €50,000 via ETF structure.",
  "similarity_threshold": 0.68,
  "require_constraints": true,
  "document_metadata": {}
}
```

**Response:**
```json
{
  "decision": "YES",
  "reason": "Matches 'Precious metals' via phrase 'Gold investment'. Supported instrument types and regions.",
  "matched_offering": {
    "id": "precious_metals",
    "label": "Precious metals",
    "synonyms": ["gold", "silver", "platinum", "palladium", "bullion", "commodity metals"],
    "description": "Direct exposure or ETFs tracking precious metals.",
    "constraints": {
      "instrument_types": ["physical", "etf", "cfds"],
      "regions": ["EU", "US"],
      "min_ticket_eur": 10000
    },
    "active": true
  },
  "similarity_score": 0.85,
  "constraint_violations": [],
  "candidate_phrases": ["Gold investment"]
}
```

**Possible decisions:**
- `YES`: Document matches a catalog item and passes all constraints
- `NO`: No match found, or constraints violated
- `NEEDS_CLARIFICATION`: Multiple close matches found

### Catalog Management

#### Get All Offerings

**GET** `/api/catalog?active_only=true`

Returns all catalog offerings.

#### Get Specific Offering

**GET** `/api/catalog/{offering_id}`

Get a specific offering by ID.

#### Create Offering

**POST** `/api/catalog`

Create a new investment offering.

**Request Body:**
```json
{
  "id": "real_estate",
  "label": "Real Estate Investment",
  "synonyms": ["property", "real estate", "REIT", "real estate investment trust"],
  "description": "Commercial and residential real estate investment opportunities.",
  "constraints": {
    "instrument_types": ["fund", "reit"],
    "regions": ["EU", "US", "UK"],
    "investor_types": ["professional", "institutional"],
    "min_ticket_eur": 50000
  },
  "active": true
}
```

#### Update Offering

**PUT** `/api/catalog/{offering_id}`

Update an existing offering.

#### Delete Offering

**DELETE** `/api/catalog/{offering_id}`

Delete an offering from the catalog.

## Catalog Structure

Each investment offering in the catalog has:

- **id**: Unique identifier (e.g., "precious_metals")
- **label**: Canonical name (e.g., "Precious metals")
- **synonyms**: List of alternative names/terms
- **description**: Detailed description
- **constraints**: Business rules
  - `instrument_types`: Allowed instrument types
  - `regions`: Allowed regions
  - `investor_types`: Allowed investor types
  - `min_ticket_eur`: Minimum ticket size
  - `max_ticket_eur`: Maximum ticket size (optional)
  - `regulatory_tags`: Regulatory classifications (optional)
- **active**: Whether the offering is currently active

## How It Works

1. **Document Processing**: Extracts candidate phrases from the document using spaCy NLP
2. **Embedding Matching**: Computes similarity between document phrases and catalog items using sentence transformers
3. **Fuzzy Matching**: Combines embedding similarity with fuzzy string matching for robustness
4. **Constraint Evaluation**: Checks business rules (ticket size, investor type, regions, etc.)
5. **Decision Making**: Returns YES/NO/NEEDS_CLARIFICATION with reasoning

## Example Usage

### Python Example

```python
import requests

# Classify a document
response = requests.post("http://localhost:8000/api/classify", json={
    "document_text": """
    Client proposal: Gold investment for professional investors in the EU.
    Indicative ticket €50,000 via ETF structure.
    """,
    "similarity_threshold": 0.68,
    "require_constraints": True
})

result = response.json()
print(f"Decision: {result['decision']}")
print(f"Reason: {result['reason']}")
if result['matched_offering']:
    print(f"Matched: {result['matched_offering']['label']}")
```

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/classify" \
  -H "Content-Type: application/json" \
  -d '{
    "document_text": "Gold investment for professional investors. Ticket size €50,000.",
    "similarity_threshold": 0.68
  }'
```

## Configuration

### Similarity Threshold

The `similarity_threshold` parameter (default: 0.68) controls how strict the matching is:
- **Lower (0.5-0.6)**: More permissive, may match loosely related items
- **Higher (0.7-0.8)**: More strict, requires closer matches

### Constraint Checking

Set `require_constraints: false` to skip constraint validation and only do matching.

## Troubleshooting

### "Classification service not available"

- Check that `sentence-transformers` is installed: `pip install sentence-transformers`
- Check server logs for initialization errors
- Ensure the catalog file exists at `backend/data/investment_catalog.json`

### Low similarity scores

- Add more synonyms to your catalog items
- Lower the `similarity_threshold`
- Check that document text contains relevant investment terms

### Constraint violations

- Review the `constraint_violations` field in the response
- Update catalog constraints or document requirements

## Extending the System

### Adding Custom Constraints

Edit `classification_service.py` in the `_evaluate_constraints` method to add custom constraint checks.

### Using Different Embedding Models

Change the model in `embedding_service.py`:
```python
embedding_service = EmbeddingService(model_name="sentence-transformers/all-mpnet-base-v2")
```

### Multilingual Support

Use a multilingual embedding model:
```python
embedding_service = EmbeddingService(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
```

## Default Catalog

The system comes with two example offerings:
1. **Precious metals**: Gold, silver, platinum, etc. (min €10k, EU/US)
2. **Private Credit**: Direct lending, mezzanine debt, etc. (professional/institutional only)

You can customize these or add your own via the API.

