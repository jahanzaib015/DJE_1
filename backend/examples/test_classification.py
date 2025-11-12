"""
Example script to test the investment classification system
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_classification():
    """Test document classification"""
    print("=" * 60)
    print("Testing Document Classification")
    print("=" * 60)
    
    # Test case 1: Gold investment that should match
    print("\n📄 Test 1: Gold investment (should match)")
    response = requests.post(
        f"{BASE_URL}/api/classify",
        json={
            "document_text": """
            Client proposal: Gold investment for professional investors in the EU.
            Indicative ticket €50,000 via ETF structure.
            """,
            "similarity_threshold": 0.68,
            "require_constraints": True
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Decision: {result['decision']}")
        print(f"📝 Reason: {result['reason']}")
        if result.get('matched_offering'):
            print(f"🎯 Matched: {result['matched_offering']['label']}")
        if result.get('similarity_score'):
            print(f"📊 Similarity: {result['similarity_score']:.2f}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
    
    # Test case 2: Investment below minimum ticket
    print("\n📄 Test 2: Gold investment below minimum (should fail constraints)")
    response = requests.post(
        f"{BASE_URL}/api/classify",
        json={
            "document_text": """
            Client proposal: Gold investment for retail investors.
            Ticket size €5,000.
            """,
            "similarity_threshold": 0.68,
            "require_constraints": True
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Decision: {result['decision']}")
        print(f"📝 Reason: {result['reason']}")
        if result.get('constraint_violations'):
            print(f"⚠️ Violations: {', '.join(result['constraint_violations'])}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
    
    # Test case 3: Private credit
    print("\n📄 Test 3: Private credit (should match)")
    response = requests.post(
        f"{BASE_URL}/api/classify",
        json={
            "document_text": """
            Investment opportunity: Direct lending strategy for institutional investors.
            Unitranche facility with minimum commitment of €1,000,000.
            """,
            "similarity_threshold": 0.68,
            "require_constraints": True
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Decision: {result['decision']}")
        print(f"📝 Reason: {result['reason']}")
        if result.get('matched_offering'):
            print(f"🎯 Matched: {result['matched_offering']['label']}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
    
    # Test case 4: Unrelated document
    print("\n📄 Test 4: Unrelated document (should not match)")
    response = requests.post(
        f"{BASE_URL}/api/classify",
        json={
            "document_text": """
            This is a document about cooking recipes and food preparation.
            It has nothing to do with investments.
            """,
            "similarity_threshold": 0.68,
            "require_constraints": True
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Decision: {result['decision']}")
        print(f"📝 Reason: {result['reason']}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")


def test_catalog_management():
    """Test catalog management endpoints"""
    print("\n" + "=" * 60)
    print("Testing Catalog Management")
    print("=" * 60)
    
    # Get all offerings
    print("\n📋 Getting all catalog offerings...")
    response = requests.get(f"{BASE_URL}/api/catalog")
    
    if response.status_code == 200:
        items = response.json()
        print(f"✅ Found {len(items)} offerings:")
        for item in items:
            print(f"  - {item['id']}: {item['label']}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
    
    # Get specific offering
    print("\n🔍 Getting specific offering...")
    response = requests.get(f"{BASE_URL}/api/catalog/precious_metals")
    
    if response.status_code == 200:
        item = response.json()
        print(f"✅ Found: {item['label']}")
        print(f"   Description: {item['description']}")
        print(f"   Synonyms: {', '.join(item['synonyms'][:3])}...")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")


if __name__ == "__main__":
    print("\n🚀 Investment Classification System - Test Script\n")
    
    try:
        # Test classification
        test_classification()
        
        # Test catalog management
        test_catalog_management()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to server.")
        print("   Make sure the server is running on http://localhost:8000")
        print("   Start it with: uvicorn backend.app.main:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {e}")

