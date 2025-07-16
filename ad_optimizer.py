
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import openai
import os
from dotenv import load_dotenv
import uvicorn
import logging
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer
from faiss import IndexFlatL2
import numpy as np
import json
import asyncio
from threading import Lock
import time
import hashlib
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY environment variable not set")

# Initialize OpenAI client for OpenRouter
client = openai.OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="AI-Powered Marketing Agent",
    description="Enterprise-scale marketing automation with AI-powered ad optimization",
    version="1.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Simple in-memory cache
cache = {}
cache_lock = Lock()
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes default

# Define input schemas
class AdRewriteRequest(BaseModel):
    ad_text: str
    tone: str
    platforms: List[str]

class AdVariant(BaseModel):
    text: str
    score: float
    rank: int

class AdResponse(BaseModel):
    rewritten_ads: dict
    ad_variants: dict  # platform -> list of variants with scores
    request_id: str
    timestamp: str

class FeedbackRequest(BaseModel):
    request_id: str
    platform: str
    ad_text: str
    engagement_rate: float
    click_through_rate: float
    conversion_rate: Optional[float] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str

# Simulated knowledge graph (platform -> tone -> ad element relationships)
KNOWLEDGE_GRAPH = {
    "facebook": {
        "friendly": {"cta": "strong, early placement", "length": "medium", "style": "engaging, visual"},
        "professional": {"cta": "clear, value-driven", "length": "medium", "style": "polished"},
    },
    "instagram": {
        "friendly": {"cta": "subtle, hashtag-driven", "length": "short", "style": "visual, trendy"},
        "professional": {"cta": "value-focused", "length": "short", "style": "sleek"},
    },
    "linkedin": {
        "friendly": {"cta": "community-oriented", "length": "medium", "style": "approachable"},
        "professional": {"cta": "value-driven", "length": "long", "style": "formal"},
    },
    "twitter": {
        "friendly": {"cta": "witty, hashtag-driven", "length": "short", "style": "catchy"},
        "professional": {"cta": "direct", "length": "short", "style": "concise"},
    }
}

# Platform-specific guidelines
PLATFORM_GUIDELINES = {
    "facebook": "Make it engaging and image-focused, with a strong CTA early on.",
    "instagram": "Make it visual and concise with hashtags.",
    "linkedin": "Make it professional and value-driven.",
    "twitter": "Make it short, witty, and hashtag-friendly."
}

# Initialize vector store for Agentic RAG
model = SentenceTransformer('all-MiniLM-L6-v2')
example_ads = [
    "Shop now for our summer sale! #SummerVibes #Discounts",
    "Boost your career with our professional courses. Enroll today!",
    "Join our community! Discover amazing products now. #ShopSmart",
    "Limited offer: Get 20% off today! Click here to save. #Sale"
]
embeddings = model.encode(example_ads)
dimension = embeddings.shape[1]
index = IndexFlatL2(dimension)
index.add(embeddings)

# Memory store for feedback loop with thread safety
MEMORY_FILE = "memory.json"
MAX_MEMORY_ENTRIES = 1000
memory = {}
memory_lock = Lock()

def load_memory():
    global memory
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r') as f:
                memory = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load memory file: {e}")
            memory = {}

def save_memory():
    try:
        # Rotate memory if too large
        if len(memory) > MAX_MEMORY_ENTRIES:
            # Keep only the most recent entries
            sorted_entries = sorted(memory.items(), 
                                  key=lambda x: x[1].get('timestamp', ''), 
                                  reverse=True)
            memory.clear()
            memory.update(dict(sorted_entries[:MAX_MEMORY_ENTRIES//2]))
        
        with open(MEMORY_FILE, 'w') as f:
            json.dump(memory, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save memory: {e}")

def validate_tone_and_platform(tone: str, platforms: List[str]) -> tuple:
    """Validate tone and platforms against knowledge graph"""
    valid_tones = set()
    for platform_data in KNOWLEDGE_GRAPH.values():
        valid_tones.update(platform_data.keys())
    
    invalid_platforms = [p for p in platforms if p.lower() not in PLATFORM_GUIDELINES]
    invalid_tone = tone.lower() not in valid_tones
    
    return invalid_platforms, invalid_tone, list(valid_tones)

# Load memory on startup
load_memory()

def score_ad_quality(ad_text: str, platform: str, tone: str) -> float:
    """Score ad based on various quality metrics"""
    score = 0.0
    
    # Length scoring based on platform optimal ranges
    optimal_lengths = {
        "facebook": (50, 150), 
        "instagram": (30, 100), 
        "linkedin": (100, 200),
        "twitter": (20, 280)
    }
    length = len(ad_text)
    if platform in optimal_lengths:
        min_len, max_len = optimal_lengths[platform]
        if min_len <= length <= max_len:
            score += 0.3
        else:
            # Penalty for being too short or too long
            deviation = min(abs(length - min_len), abs(length - max_len))
            score += max(0, 0.3 - (deviation / max_len))
    
    # CTA presence and strength
    strong_ctas = ["shop now", "buy now", "get started", "learn more", "sign up", "download"]
    medium_ctas = ["shop", "buy", "click", "discover", "try", "join"]
    
    ad_lower = ad_text.lower()
    if any(cta in ad_lower for cta in strong_ctas):
        score += 0.25
    elif any(cta in ad_lower for cta in medium_ctas):
        score += 0.15
    
    # Emoji usage for friendly tone (but not excessive)
    emoji_count = sum(1 for char in ad_text if ord(char) > 127 and ord(char) < 65536)
    if tone == "friendly":
        if 1 <= emoji_count <= 3:
            score += 0.15
        elif emoji_count > 3:
            score += 0.05  # Too many emojis
    elif tone == "professional" and emoji_count == 0:
        score += 0.1
    
    # Hashtag usage for social platforms
    hashtag_count = ad_text.count('#')
    if platform in ["instagram", "twitter"]:
        if 1 <= hashtag_count <= 5:
            score += 0.1
        elif hashtag_count > 5:
            score += 0.05  # Too many hashtags
    elif platform == "linkedin" and hashtag_count <= 2:
        score += 0.05
    
    # Urgency words for conversion
    urgency_words = ["limited", "now", "today", "hurry", "exclusive", "sale", "offer"]
    if any(word in ad_lower for word in urgency_words):
        score += 0.1
    
    # Question engagement for social platforms
    if platform in ["facebook", "instagram"] and '?' in ad_text:
        score += 0.05
    
    return min(score, 1.0)

def get_performance_insights(request_id: str) -> dict:
    """Get performance insights for a specific request"""
    with memory_lock:
        if request_id in memory:
            entry = memory[request_id]
            feedback_data = entry.get('feedback', {})
            
            if feedback_data:
                avg_engagement = np.mean([f.get('engagement_rate', 0) for f in feedback_data.values()])
                avg_ctr = np.mean([f.get('click_through_rate', 0) for f in feedback_data.values()])
                best_platform = max(feedback_data.keys(), 
                                  key=lambda k: feedback_data[k].get('engagement_rate', 0))
                
                return {
                    "avg_engagement_rate": avg_engagement,
                    "avg_click_through_rate": avg_ctr,
                    "best_performing_platform": best_platform,
                    "total_platforms_tested": len(feedback_data)
                }
    
    return {"message": "No performance data available yet"}

def get_cache_key(request: AdRewriteRequest) -> str:
    """Generate cache key from request"""
    content = f"{request.ad_text}_{request.tone}_{'_'.join(sorted(request.platforms))}"
    return hashlib.md5(content.encode()).hexdigest()

def get_from_cache(cache_key: str) -> Optional[dict]:
    """Get cached response if valid"""
    with cache_lock:
        if cache_key in cache:
            cached_data, timestamp = cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=CACHE_TTL):
                logger.info(f"Cache hit for key: {cache_key}")
                return cached_data
            else:
                # Remove expired entry
                del cache[cache_key]
    return None

def set_cache(cache_key: str, data: dict):
    """Store data in cache"""
    with cache_lock:
        cache[cache_key] = (data, datetime.now())
        # Simple cache cleanup - remove oldest entries if cache gets too large
        if len(cache) > 100:
            oldest_key = min(cache.keys(), key=lambda k: cache[k][1])
            del cache[oldest_key]

@app.get("/")
async def root():
    """Root endpoint with simple web interface"""
    return {
        "message": "AI-Powered Marketing Agent v2.0 - Enhanced with Scoring & Feedback",
        "version": "2.0.0",
        "new_features": [
            "🎯 Multiple ad variants with quality scoring",
            "📊 Performance feedback collection",
            "📈 Analytics and insights"
        ],
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics", 
            "run_agent": "/run-agent (POST) - Generate scored ad variants",
            "feedback": "/feedback (POST) - Submit performance data",
            "insights": "/insights/{request_id} (GET) - Get performance insights",
            "top_performers": "/top-performers (GET) - View best performing ads",
            "docs": "/docs"
        },
        "usage": {
            "generate_ads": "POST /run-agent with {\"ad_text\": \"your ad\", \"tone\": \"friendly|professional\", \"platforms\": [\"facebook\", \"instagram\"]}",
            "submit_feedback": "POST /feedback with {\"request_id\": \"uuid\", \"platform\": \"facebook\", \"ad_text\": \"ad\", \"engagement_rate\": 0.05, \"click_through_rate\": 0.02}"
        }
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for monitoring"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )

@app.get("/metrics")
async def get_metrics():
    """Basic metrics endpoint for monitoring"""
    return {
        "memory_entries": len(memory),
        "cache_entries": len(cache),
        "uptime": "N/A",  # Could track actual uptime
        "total_requests": len(memory)
    }

@app.post("/feedback")
async def collect_feedback(feedback: FeedbackRequest):
    """Collect performance feedback for continuous learning"""
    try:
        with memory_lock:
            if feedback.request_id in memory:
                # Initialize feedback dict if it doesn't exist
                if 'feedback' not in memory[feedback.request_id]:
                    memory[feedback.request_id]['feedback'] = {}
                
                # Store feedback data
                memory[feedback.request_id]['feedback'][feedback.platform] = {
                    "ad_text": feedback.ad_text,
                    "engagement_rate": feedback.engagement_rate,
                    "click_through_rate": feedback.click_through_rate,
                    "conversion_rate": feedback.conversion_rate,
                    "feedback_timestamp": datetime.now().isoformat()
                }
                
                save_memory()
                
                return {
                    "message": "Feedback recorded successfully",
                    "request_id": feedback.request_id,
                    "platform": feedback.platform
                }
            else:
                raise HTTPException(status_code=404, detail="Request ID not found")
                
    except Exception as e:
        logger.error(f"Error recording feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")

@app.get("/insights/{request_id}")
async def get_insights(request_id: str):
    """Get performance insights for a specific request"""
    try:
        insights = get_performance_insights(request_id)
        return {
            "request_id": request_id,
            "insights": insights,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting insights: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get insights")

@app.get("/top-performers")
async def get_top_performers():
    """Get top performing ads across all requests"""
    try:
        with memory_lock:
            top_ads = []
            
            for request_id, data in memory.items():
                feedback = data.get('feedback', {})
                for platform, fb_data in feedback.items():
                    top_ads.append({
                        "request_id": request_id,
                        "platform": platform,
                        "ad_text": fb_data.get("ad_text", ""),
                        "engagement_rate": fb_data.get("engagement_rate", 0),
                        "click_through_rate": fb_data.get("click_through_rate", 0),
                        "conversion_rate": fb_data.get("conversion_rate", 0)
                    })
            
            # Sort by engagement rate
            top_ads.sort(key=lambda x: x["engagement_rate"], reverse=True)
            
            return {
                "top_performers": top_ads[:10],  # Top 10
                "total_ads_with_feedback": len(top_ads),
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error getting top performers: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get top performers")

@app.post("/run-agent", response_model=AdResponse)
@limiter.limit("60/minute")
async def run_agent(request: Request, ad_request: AdRewriteRequest):
    try:
        # Check cache first
        cache_key = get_cache_key(ad_request)
        cached_response = get_from_cache(cache_key)
        if cached_response:
            return AdResponse(**cached_response)
        
        # Enhanced validation
        invalid_platforms, invalid_tone, valid_tones = validate_tone_and_platform(
            ad_request.tone, ad_request.platforms
        )
        
        if invalid_platforms:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid platforms: {invalid_platforms}. Valid platforms: {list(PLATFORM_GUIDELINES.keys())}"
            )
        
        if invalid_tone:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid tone: '{ad_request.tone}'. Valid tones: {valid_tones}"
            )
        
        if not ad_request.ad_text.strip():
            raise HTTPException(status_code=400, detail="Ad text cannot be empty")

        # Retrieve relevant ad examples using Agentic RAG
        query_embedding = model.encode([ad_request.ad_text])[0]
        _, indices = index.search(np.array([query_embedding]), k=2)
        context_ads = [example_ads[i] for i in indices[0]]

        # Generate unique request ID
        request_id = str(uuid4())
        timestamp = datetime.now().isoformat()
        
        # Process platforms concurrently with multiple variants
        async def process_platform(platform: str) -> tuple:
            platform = platform.lower()
            # Use knowledge graph for structured guidance
            kg_guidance = KNOWLEDGE_GRAPH.get(platform, {}).get(ad_request.tone.lower(), {})
            base_prompt = (
                f"Rewrite the ad copy in a {ad_request.tone} tone, optimized for {platform}. "
                f"{PLATFORM_GUIDELINES[platform]}\n"
                f"Knowledge Graph Guidance: CTA: {kg_guidance.get('cta', 'clear')}, "
                f"Length: {kg_guidance.get('length', 'medium')}, Style: {kg_guidance.get('style', 'engaging')}\n"
                f"Context Ads: {context_ads}\n\nAd Text: {ad_request.ad_text}"
            )

            logger.info(f"Generating 3 ad variants for platform: {platform}")
            
            # Generate 3 variants with different temperatures for diversity
            variants = []
            temperatures = [0.6, 0.8, 1.0]
            
            for i, temp in enumerate(temperatures):
                prompt = base_prompt + f"\n\nCreate a unique, creative variation (variant {i+1}):"
                
                response = client.chat.completions.create(
                    model="anthropic/claude-3.5-sonnet",
                    messages=[
                        {"role": "system", "content": "You are a marketing copy expert. Create diverse, high-quality ad variations."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=150,
                    temperature=temp
                )
                
                ad_text = response.choices[0].message.content.strip()
                score = score_ad_quality(ad_text, platform, ad_request.tone)
                
                variants.append({
                    "text": ad_text,
                    "score": round(score, 3),
                    "rank": 0  # Will be set after sorting
                })
            
            # Sort variants by score and assign ranks
            variants.sort(key=lambda x: x["score"], reverse=True)
            for i, variant in enumerate(variants):
                variant["rank"] = i + 1
            
            # Return best variant as main ad, plus all variants with scores
            best_ad = variants[0]["text"]
            return platform, best_ad, variants
        
        # Process all platforms concurrently
        tasks = [process_platform(platform) for platform in ad_request.platforms]
        results = await asyncio.gather(*tasks)
        
        # Extract results properly (platform, best_ad, variants)
        rewritten_ads = {}
        ad_variants = {}
        
        for platform, best_ad, variants in results:
            rewritten_ads[platform] = best_ad
            ad_variants[platform] = variants
        
        # Create response
        response_data = {
            "rewritten_ads": rewritten_ads,
            "ad_variants": ad_variants,
            "request_id": request_id,
            "timestamp": timestamp
        }
        
        # Store in cache
        set_cache(cache_key, response_data)
        
        # Store in memory with thread safety
        with memory_lock:
            memory[request_id] = {
                "input": ad_request.model_dump(),
                "output": rewritten_ads,
                "timestamp": timestamp,
                "request_id": request_id
            }
            save_memory()

        return AdResponse(**response_data)

    except openai.OpenAIError as e:
        logger.error(f"OpenRouter API error: {str(e)}")
        raise HTTPException(status_code=500, detail="OpenRouter service temporarily unavailable")
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
