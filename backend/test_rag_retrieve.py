#!/usr/bin/env python3
"""
Test script for RAG retrieval functionality
Demonstrates how to use the retrieve_rules function for decision items
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from services.rag_retrieve import retrieve_rules, retrieve_rules_batch, get_negation_chunks

def test_retrieve_rules():
    """Test basic retrieval functionality"""
    print("Testing RAG retrieval functionality...")
    
    # Example usage
    query = "Coal"
    doc_id = "trace_1761577414_da143344"  # Example trace ID
    k = 5
    vectordb_dir = "var/chroma"
    
    print(f"\n1. Retrieving rules for '{query}' in document '{doc_id}':")
    results = retrieve_rules(query, doc_id, k, vectordb_dir)
    
    if results:
        print(f"Found {len(results)} results:")
        for i, item in enumerate(results, 1):
            print(f"\n  Result {i}:")
            print(f"    ID: {item['id']}")
            print(f"    Text: {item['text'][:100]}...")
            print(f"    Has Negation: {item['meta'].get('has_negation', False)}")
            print(f"    Char Length: {item['meta'].get('char_len', 0)}")
    else:
        print("No results found.")
    
    return results

def test_batch_retrieval():
    """Test batch retrieval for multiple decision items"""
    print("\n" + "="*50)
    print("Testing batch retrieval...")
    
    queries = ["Coal", "Saudi Arabia", "Renewable Energy", "Oil"]
    doc_id = "trace_1761577414_da143344"
    k = 3
    vectordb_dir = "var/chroma"
    
    print(f"Retrieving rules for multiple queries: {queries}")
    batch_results = retrieve_rules_batch(queries, doc_id, k, vectordb_dir)
    
    for query, results in batch_results.items():
        print(f"\n{query}: {len(results)} results")
        for i, item in enumerate(results, 1):
            negation_status = "✓" if item['meta'].get('has_negation', False) else "✗"
            print(f"  {i}. {negation_status} {item['text'][:60]}...")

def test_negation_chunks():
    """Test retrieval of only negation-bearing chunks"""
    print("\n" + "="*50)
    print("Testing negation-only retrieval...")
    
    query = "Coal"
    doc_id = "trace_1761577414_da143344"
    k = 3
    vectordb_dir = "var/chroma"
    
    print(f"Retrieving only negation chunks for '{query}':")
    negation_results = get_negation_chunks(query, doc_id, k, vectordb_dir)
    
    if negation_results:
        print(f"Found {len(negation_results)} negation chunks:")
        for i, item in enumerate(negation_results, 1):
            print(f"\n  Negation Chunk {i}:")
            print(f"    ID: {item['id']}")
            print(f"    Text: {item['text'][:100]}...")
            print(f"    Char Length: {item['meta'].get('char_len', 0)}")
    else:
        print("No negation chunks found.")

def main():
    """Main test function"""
    print("RAG Retrieval Test Suite")
    print("=" * 50)
    
    try:
        # Test basic retrieval
        test_retrieve_rules()
        
        # Test batch retrieval
        test_batch_retrieval()
        
        # Test negation-only retrieval
        test_negation_chunks()
        
        print("\n" + "="*50)
        print("All tests completed!")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
