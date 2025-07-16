#!/usr/bin/env python3
"""
Simple test script to verify API endpoints work correctly
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health_endpoint():
    """Test the health check endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Start with: python ad_optimizer.py")

def test_metrics_endpoint():
    """Test the metrics endpoint"""
    print("\nTesting metrics endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/metrics")
        if response.status_code == 200:
            print("✅ Metrics endpoint passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Metrics endpoint failed: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Server not running")

def test_ad_generation_validation():
    """Test ad generation with invalid inputs"""
    print("\nTesting validation...")
    
    # Test invalid platform
    invalid_platform_data = {
        "ad_text": "Buy our amazing product now!",
        "tone": "friendly",
        "platforms": ["invalid_platform"]
    }
    
    try:
        response = requests.post(f"{BASE_URL}/run-agent", json=invalid_platform_data)
        if response.status_code == 400:
            print("✅ Invalid platform validation passed")
        else:
            print(f"❌ Invalid platform validation failed: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Server not running")

def test_ad_generation_with_mock():
    """Test ad generation (will fail without valid API key, but tests the flow)"""
    print("\nTesting ad generation flow...")
    
    valid_data = {
        "ad_text": "Buy our amazing product now!",
        "tone": "friendly",
        "platforms": ["facebook", "instagram"]
    }
    
    try:
        response = requests.post(f"{BASE_URL}/run-agent", json=valid_data)
        print(f"   Status code: {response.status_code}")
        if response.status_code == 200:
            print("✅ Ad generation successful")
            result = response.json()
            print(f"   Request ID: {result.get('request_id')}")
            print(f"   Platforms: {list(result.get('rewritten_ads', {}).keys())}")
        elif response.status_code == 500:
            print("⚠️  Expected failure (no valid API key)")
            print(f"   Error: {response.json().get('detail')}")
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            print(f"   Response: {response.json()}")
    except requests.exceptions.ConnectionError:
        print("❌ Server not running")

if __name__ == "__main__":
    print("🚀 Testing OpenRouter API Integration")
    print("=" * 50)
    
    test_health_endpoint()
    test_metrics_endpoint()
    test_ad_generation_validation()
    test_ad_generation_with_mock()
    
    print("\n" + "=" * 50)
    print("📝 Next steps:")
    print("1. Get your OpenRouter API key from: https://openrouter.ai/keys")
    print("2. Update your .env file with: OPENROUTER_API_KEY=your_actual_key")
    print("3. Start the server with: python ad_optimizer.py")
    print("4. Run this test again to verify full functionality")