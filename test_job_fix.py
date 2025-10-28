#!/usr/bin/env python3
"""
Test script to verify the job status fix
"""
import requests
import json
import time

API_BASE_URL = "https://dje-1-3.onrender.com"

def test_job_endpoints():
    """Test the job-related endpoints"""
    print("Testing job endpoints...")
    
    # Test 1: List all jobs
    print("\n1. Testing /api/jobs endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/api/jobs")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Total jobs: {data.get('total_jobs', 0)}")
            if data.get('jobs'):
                print("Available jobs:")
                for job_id, job in data['jobs'].items():
                    print(f"  - {job_id}: {job.get('status', 'unknown')} ({job.get('message', 'no message')})")
            else:
                print("No jobs found")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: Test health endpoint
    print("\n2. Testing /api/health endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/api/health")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Health: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 3: Test with a fake job ID
    print("\n3. Testing /api/jobs/{job_id}/status with fake ID...")
    fake_job_id = "test-job-123"
    try:
        response = requests.get(f"{API_BASE_URL}/api/jobs/{fake_job_id}/status")
        print(f"Status: {response.status_code}")
        if response.status_code == 404:
            print("✓ Correctly returns 404 for non-existent job")
        else:
            print(f"Unexpected response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_job_endpoints()
