import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json
import os
from ad_optimizer import app, memory, cache, get_cache_key, AdRewriteRequest

client = TestClient(app)

@pytest.fixture
def sample_request():
    return {
        "ad_text": "Buy our amazing product now!",
        "tone": "friendly",
        "platforms": ["facebook", "instagram"]
    }

@pytest.fixture
def mock_openai_response():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Rewritten ad copy here!"
    return mock_response

class TestHealthEndpoints:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "1.0.0"

    def test_metrics(self):
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "memory_entries" in data
        assert "cache_entries" in data
        assert "total_requests" in data

class TestValidation:
    def test_invalid_platform(self, sample_request):
        sample_request["platforms"] = ["invalid_platform"]
        response = client.post("/run-agent", json=sample_request)
        assert response.status_code == 400
        assert "Invalid platforms" in response.json()["detail"]

    def test_invalid_tone(self, sample_request):
        sample_request["tone"] = "invalid_tone"
        response = client.post("/run-agent", json=sample_request)
        assert response.status_code == 400
        assert "Invalid tone" in response.json()["detail"]

    def test_empty_ad_text(self, sample_request):
        sample_request["ad_text"] = ""
        response = client.post("/run-agent", json=sample_request)
        assert response.status_code == 400
        assert "Ad text cannot be empty" in response.json()["detail"]

class TestCaching:
    def test_cache_key_generation(self):
        request = AdRewriteRequest(
            ad_text="Test ad",
            tone="friendly",
            platforms=["facebook", "instagram"]
        )
        key1 = get_cache_key(request)
        key2 = get_cache_key(request)
        assert key1 == key2
        
        # Different order should produce same key
        request2 = AdRewriteRequest(
            ad_text="Test ad",
            tone="friendly",
            platforms=["instagram", "facebook"]
        )
        key3 = get_cache_key(request2)
        assert key1 == key3

    @patch('ad_optimizer.openai.chat.completions.create')
    def test_caching_works(self, mock_openai, sample_request, mock_openai_response):
        mock_openai.return_value = mock_openai_response
        
        # Clear cache
        cache.clear()
        
        # First request
        response1 = client.post("/run-agent", json=sample_request)
        assert response1.status_code == 200
        
        # Second identical request should hit cache
        response2 = client.post("/run-agent", json=sample_request)
        assert response2.status_code == 200
        
        # Should have same request_id (from cache)
        assert response1.json()["request_id"] == response2.json()["request_id"]

class TestAdGeneration:
    @patch('ad_optimizer.openai.chat.completions.create')
    def test_successful_ad_generation(self, mock_openai, sample_request, mock_openai_response):
        mock_openai.return_value = mock_openai_response
        
        response = client.post("/run-agent", json=sample_request)
        assert response.status_code == 200
        
        data = response.json()
        assert "rewritten_ads" in data
        assert "request_id" in data
        assert "timestamp" in data
        assert len(data["rewritten_ads"]) == 2  # facebook and instagram

    def test_openrouter_configuration(self):
        """Test that OpenRouter configuration is properly set"""
        import ad_optimizer
        import openai
        
        # Verify OpenRouter base URL is set
        assert openai.base_url == "https://openrouter.ai/api/v1"
        
        # Verify environment variable is expected
        assert os.getenv("OPENROUTER_API_KEY") is not None or os.getenv("OPENROUTER_API_KEY") == "your_openrouter_api_key_here"

class TestMemoryManagement:
    def test_memory_rotation(self):
        # This would require more complex setup to test properly
        # For now, just verify the function exists and can be called
        from ad_optimizer import save_memory, load_memory
        save_memory()
        load_memory()

if __name__ == "__main__":
    pytest.main([__file__])