#!/usr/bin/env python3
"""
Debug script to test individual components
"""
import os
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

def test_openai_connection():
    """Test OpenRouter API connection"""
    try:
        openai.api_key = os.getenv("OPENROUTER_API_KEY")
        openai.base_url = "https://openrouter.ai/api/v1"
        
        print(f"API Key present: {'Yes' if openai.api_key else 'No'}")
        print(f"API Key starts with: {openai.api_key[:10] if openai.api_key else 'None'}...")
        
        response = openai.chat.completions.create(
            model="anthropic/claude-3.5-sonnet",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello"}
            ],
            max_tokens=10
        )
        
        print("✅ OpenRouter API connection successful!")
        print(f"Response: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ OpenRouter API error: {e}")
        return False

def test_sentence_transformers():
    """Test sentence transformers model"""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        test_text = ["This is a test sentence"]
        embeddings = model.encode(test_text)
        
        print("✅ Sentence Transformers working!")
        print(f"Embedding shape: {embeddings.shape}")
        return True
        
    except Exception as e:
        print(f"❌ Sentence Transformers error: {e}")
        return False

def test_faiss():
    """Test FAISS vector store"""
    try:
        from faiss import IndexFlatL2
        import numpy as np
        
        # Create a simple index
        dimension = 384  # all-MiniLM-L6-v2 dimension
        index = IndexFlatL2(dimension)
        
        # Add some dummy vectors
        vectors = np.random.random((5, dimension)).astype('float32')
        index.add(vectors)
        
        # Search
        query = np.random.random((1, dimension)).astype('float32')
        _, indices = index.search(query, k=2)
        
        print("✅ FAISS working!")
        print(f"Search results: {indices}")
        return True
        
    except Exception as e:
        print(f"❌ FAISS error: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Running debug tests...\n")
    
    print("1. Testing OpenRouter API connection:")
    test_openai_connection()
    
    print("\n2. Testing Sentence Transformers:")
    test_sentence_transformers()
    
    print("\n3. Testing FAISS:")
    test_faiss()
    
    print("\n✅ Debug tests complete!")