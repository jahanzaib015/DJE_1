#!/usr/bin/env python3
"""
Example integration of RAG retrieval with analysis service
Shows how to use retrieve_rules for decision items like sectors and countries
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from services.rag_retrieve import retrieve_rules, retrieve_rules_batch, get_negation_chunks
from services.analysis_service import AnalysisService
from models.analysis_models import AnalysisMethod, LLMProvider

def example_sector_analysis():
    """Example: Analyze specific sectors using RAG retrieval"""
    print("=== Sector Analysis with RAG Retrieval ===")
    
    # Example sectors to analyze
    sectors = ["Coal", "Oil", "Renewable Energy", "Nuclear", "Natural Gas"]
    doc_id = "trace_1761577414_da143344"  # Example trace ID
    k = 3  # Top 3 results per sector
    
    print(f"Analyzing sectors: {sectors}")
    print(f"Document ID: {doc_id}")
    print(f"Retrieving top {k} chunks per sector\n")
    
    # Retrieve rules for each sector
    sector_results = retrieve_rules_batch(sectors, doc_id, k)
    
    for sector, chunks in sector_results.items():
        print(f"--- {sector} ---")
        if chunks:
            for i, chunk in enumerate(chunks, 1):
                negation_indicator = "🚫" if chunk['meta'].get('has_negation', False) else "✅"
                print(f"  {i}. {negation_indicator} {chunk['text'][:80]}...")
                print(f"     Length: {chunk['meta'].get('char_len', 0)} chars")
        else:
            print("  No relevant chunks found")
        print()

def example_country_analysis():
    """Example: Analyze specific countries using RAG retrieval"""
    print("=== Country Analysis with RAG Retrieval ===")
    
    # Example countries to analyze
    countries = ["Saudi Arabia", "Russia", "China", "United States", "Germany"]
    doc_id = "trace_1761577414_da143344"
    k = 2  # Top 2 results per country
    
    print(f"Analyzing countries: {countries}")
    print(f"Document ID: {doc_id}")
    print(f"Retrieving top {k} chunks per country\n")
    
    # Retrieve rules for each country
    country_results = retrieve_rules_batch(countries, doc_id, k)
    
    for country, chunks in country_results.items():
        print(f"--- {country} ---")
        if chunks:
            for i, chunk in enumerate(chunks, 1):
                negation_indicator = "🚫" if chunk['meta'].get('has_negation', False) else "✅"
                print(f"  {i}. {negation_indicator} {chunk['text'][:80]}...")
                print(f"     Page: {chunk['meta'].get('page', 'N/A')}")
        else:
            print("  No relevant chunks found")
        print()

def example_negation_focused_analysis():
    """Example: Focus on negation-bearing chunks for compliance analysis"""
    print("=== Negation-Focused Analysis ===")
    
    # Focus on sectors that might have restrictions
    restricted_sectors = ["Coal", "Fossil Fuels", "Tobacco", "Weapons"]
    doc_id = "trace_1761577414_da143344"
    
    print("Looking for restriction patterns (negation chunks)...")
    print(f"Sectors: {restricted_sectors}\n")
    
    for sector in restricted_sectors:
        print(f"--- {sector} Restrictions ---")
        
        # Get only negation chunks
        negation_chunks = get_negation_chunks(sector, doc_id, k=3)
        
        if negation_chunks:
            print(f"Found {len(negation_chunks)} restriction-related chunks:")
            for i, chunk in enumerate(negation_chunks, 1):
                print(f"  {i}. {chunk['text'][:100]}...")
                print(f"     Chunk ID: {chunk['id']}")
        else:
            print("  No restriction patterns found")
        print()

def example_integration_with_analysis_service():
    """Example: How to integrate RAG retrieval with existing analysis service"""
    print("=== Integration with Analysis Service ===")
    
    # Initialize analysis service
    analysis_service = AnalysisService()
    
    # Example: Use RAG to pre-filter content before LLM analysis
    doc_id = "trace_1761577414_da143344"
    
    # Get relevant chunks for specific decision items
    decision_items = ["Coal", "Saudi Arabia", "Renewable Energy"]
    
    print("Pre-filtering content using RAG retrieval...")
    print(f"Decision items: {decision_items}")
    
    # Retrieve relevant chunks
    relevant_chunks = []
    for item in decision_items:
        chunks = retrieve_rules(item, doc_id, k=2)
        relevant_chunks.extend(chunks)
    
    # Combine chunk texts for analysis
    if relevant_chunks:
        combined_text = "\n\n".join([chunk['text'] for chunk in relevant_chunks])
        print(f"\nRetrieved {len(relevant_chunks)} relevant chunks")
        print(f"Combined text length: {len(combined_text)} characters")
        
        # You could now pass this filtered text to the analysis service
        # result = await analysis_service.analyze_document(
        #     text=combined_text,
        #     analysis_method=AnalysisMethod.LLM,
        #     llm_provider=LLMProvider.OPENAI,
        #     model="gpt-4",
        #     fund_id="example_fund"
        # )
        
        print("(Analysis service call would go here)")
    else:
        print("No relevant chunks found for analysis")

def example_decision_item_workflow():
    """Example: Complete workflow for decision item analysis"""
    print("=== Complete Decision Item Workflow ===")
    
    # Define decision items to analyze
    decision_items = {
        "sectors": ["Coal", "Oil", "Renewable Energy", "Nuclear"],
        "countries": ["Saudi Arabia", "Russia", "China", "United States"],
        "instruments": ["Bonds", "Stocks", "Derivatives", "Funds"]
    }
    
    doc_id = "trace_1761577414_da143344"
    k = 2
    
    print("Analyzing decision items across categories...")
    print(f"Document ID: {doc_id}")
    print(f"Retrieving top {k} chunks per item\n")
    
    all_results = {}
    
    for category, items in decision_items.items():
        print(f"--- {category.upper()} ---")
        category_results = {}
        
        for item in items:
            chunks = retrieve_rules(item, doc_id, k)
            category_results[item] = chunks
            
            if chunks:
                negation_count = sum(1 for chunk in chunks if chunk['meta'].get('has_negation', False))
                print(f"  {item}: {len(chunks)} chunks ({negation_count} with negations)")
            else:
                print(f"  {item}: No chunks found")
        
        all_results[category] = category_results
        print()
    
    # Summary
    print("=== SUMMARY ===")
    total_items = sum(len(items) for items in decision_items.values())
    total_chunks = sum(
        len(chunks) 
        for category_results in all_results.values() 
        for chunks in category_results.values()
    )
    total_negations = sum(
        sum(1 for chunk in chunks if chunk['meta'].get('has_negation', False))
        for category_results in all_results.values()
        for chunks in category_results.values()
    )
    
    print(f"Total decision items analyzed: {total_items}")
    print(f"Total chunks retrieved: {total_chunks}")
    print(f"Chunks with negations: {total_negations}")
    print(f"Negation rate: {total_negations/total_chunks*100:.1f}%" if total_chunks > 0 else "N/A")

def main():
    """Run all examples"""
    print("RAG Retrieval Integration Examples")
    print("=" * 50)
    
    try:
        # Run examples
        example_sector_analysis()
        print("\n" + "="*50 + "\n")
        
        example_country_analysis()
        print("\n" + "="*50 + "\n")
        
        example_negation_focused_analysis()
        print("\n" + "="*50 + "\n")
        
        example_integration_with_analysis_service()
        print("\n" + "="*50 + "\n")
        
        example_decision_item_workflow()
        
        print("\n" + "="*50)
        print("All examples completed!")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
