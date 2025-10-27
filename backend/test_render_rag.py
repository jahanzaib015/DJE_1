#!/usr/bin/env python3
"""
Test script for RAG retrieval on Render deployment
Tests the API endpoints directly
"""

import requests
import json
import sys

# Render deployment URL (update this with your actual Render URL)
RENDER_URL = "https://dje-1-3.onrender.com"

def test_rag_endpoints():
    """Test RAG retrieval endpoints on Render"""
    print("Testing RAG Retrieval on Render Deployment")
    print("=" * 50)
    
    # Test data
    test_doc_id = "trace_1761577414_da143344"
    test_queries = ["Coal", "Saudi Arabia", "Renewable Energy"]
    
    print(f"Render URL: {RENDER_URL}")
    print(f"Test Document ID: {test_doc_id}")
    print(f"Test Queries: {test_queries}")
    print()
    
    # Test 1: Single query retrieval
    print("1. Testing single query retrieval...")
    try:
        response = requests.post(
            f"{RENDER_URL}/api/rag/retrieve",
            params={
                "query": "Coal",
                "doc_id": test_doc_id,
                "k": 3
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Success: {data['count']} results found")
            for i, result in enumerate(data['results'][:2], 1):
                negation = "🚫" if result['meta'].get('has_negation', False) else "✅"
                print(f"     {i}. {negation} {result['text'][:60]}...")
        else:
            print(f"   ✗ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print()
    
    # Test 2: Batch retrieval
    print("2. Testing batch retrieval...")
    try:
        response = requests.post(
            f"{RENDER_URL}/api/rag/retrieve/batch",
            params={
                "queries": json.dumps(test_queries),
                "doc_id": test_doc_id,
                "k": 2
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Success: {data['total_queries']} queries processed")
            for query, results in data['results'].items():
                print(f"     {query}: {len(results)} chunks")
        else:
            print(f"   ✗ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print()
    
    # Test 3: Negation-only retrieval
    print("3. Testing negation-only retrieval...")
    try:
        response = requests.post(
            f"{RENDER_URL}/api/rag/negations",
            params={
                "query": "Fossil Fuels",
                "doc_id": test_doc_id,
                "k": 3
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Success: {data['count']} negation chunks found")
            for i, chunk in enumerate(data['negation_chunks'][:2], 1):
                print(f"     {i}. {chunk['text'][:60]}...")
        else:
            print(f"   ✗ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print()
    
    # Test 4: RAG stats
    print("4. Testing RAG stats...")
    try:
        response = requests.get(f"{RENDER_URL}/api/rag/stats")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Success: {data['total_chunks']} total chunks")
            print(f"     Documents: {data['unique_documents']}")
            print(f"     Mode: {data['mode']}")
        else:
            print(f"   ✗ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print()
    
    # Test 5: Health check
    print("5. Testing health check...")
    try:
        response = requests.get(f"{RENDER_URL}/health")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Success: {data['status']}")
        else:
            print(f"   ✗ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

def test_with_curl_commands():
    """Generate curl commands for testing"""
    print("\n" + "=" * 50)
    print("CURL Commands for Testing")
    print("=" * 50)
    
    test_doc_id = "trace_1761577414_da143344"
    
    print("1. Single query retrieval:")
    print(f'curl -X POST "{RENDER_URL}/api/rag/retrieve?query=Coal&doc_id={test_doc_id}&k=3"')
    print()
    
    print("2. Batch retrieval:")
    print(f'curl -X POST "{RENDER_URL}/api/rag/retrieve/batch?queries=[\"Coal\",\"Saudi Arabia\"]&doc_id={test_doc_id}&k=2"')
    print()
    
    print("3. Negation-only retrieval:")
    print(f'curl -X POST "{RENDER_URL}/api/rag/negations?query=Fossil%20Fuels&doc_id={test_doc_id}&k=3"')
    print()
    
    print("4. RAG stats:")
    print(f'curl -X GET "{RENDER_URL}/api/rag/stats"')
    print()
    
    print("5. Health check:")
    print(f'curl -X GET "{RENDER_URL}/health"')

def main():
    """Main test function"""
    print("RAG Retrieval Render Deployment Test")
    print("=" * 50)
    
    # Check if requests is available
    try:
        import requests
    except ImportError:
        print("Error: requests library not found. Install with: pip install requests")
        return
    
    # Run tests
    test_rag_endpoints()
    test_with_curl_commands()
    
    print("\n" + "=" * 50)
    print("Test completed!")
    print("Note: Update RENDER_URL variable with your actual Render deployment URL")

if __name__ == "__main__":
    main()
