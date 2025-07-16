#!/usr/bin/env python3
"""
Simple test for OpenAI client
"""
import openai
import os
from dotenv import load_dotenv

load_dotenv()

# Test the exact same setup as in ad_optimizer.py
api_key = os.getenv("OPENROUTER_API_KEY")
print(f"API Key present: {'Yes' if api_key else 'No'}")

if api_key:
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )
    
    try:
        response = client.chat.completions.create(
            model="anthropic/claude-3.5-sonnet",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in 5 words"}
            ],
            max_tokens=20,
            temperature=0.7
        )
        
        print("✅ Success!")
        print(f"Response type: {type(response)}")
        print(f"Response: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"Error type: {type(e)}")
else:
    print("❌ No API key found")