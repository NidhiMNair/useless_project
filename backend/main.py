import os
import re
import json
import random
import logging
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import httpx

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unnecessary_search")

app = FastAPI(
    title="The Internet's Most Unnecessary Search Engine API",
    description="Backend API powered by FastAPI, Gemini LLM, and Absurd Offline Fallback.",
    version="1.0.0",
)

# CORS Configuration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Schemas
class SearchRequest(BaseModel):
    query: str = Field(
        ...,
        description="The overthought question to analyze",
        example="Where am I?",
    )


class Possibility(BaseModel):
    tier: Optional[int] = Field(None, description="Paranoia Tier 1-5")
    title: Optional[str] = Field(None, description="Tier title")
    text: str = Field(..., description="Explanation possibility")
    probability: int = Field(..., description="Comedic probability (0-100)")


class SearchResponse(BaseModel):
    query: str = Field(..., description="Original user query")
    possibilities: List[Possibility] = Field(
        ..., description="List of exactly 5 escalating possibilities"
    )
    recommended_action: str = Field(
        ..., description="Humorous recommended action"
    )
    confidence: str = Field(..., description="Comedic confidence label")
    engine: str = Field(
        default="AI Multiverse Core",
        description="Engine used (Google Gemini, Grok, or Offline Oracle)"
    )


def normalize_probabilities(possibilities: list) -> List[dict]:
    """
    Ensure exactly 5 possibilities exist and their probabilities sum to exactly 100.
    """
    tier_titles = [
        "Mundane Reality",
        "Mild Paranoia",
        "Overanalyzed Vortex",
        "Conspiracy Grade",
        "Multiverse Catastrophe"
    ]

    while len(possibilities) < 5:
        idx = len(possibilities)
        possibilities.append({
            "text": "A clandestine organization is orchestrating an elaborate psychological experiment.",
            "probability": 1
        })
    possibilities = possibilities[:5]

    for i, item in enumerate(possibilities):
        item["tier"] = i + 1
        item["title"] = tier_titles[i]

    raw_probs = []
    for item in possibilities:
        p = item.get("probability", 0)
        try:
            val = int(p)
        except (ValueError, TypeError):
            val = 0
        raw_probs.append(max(0, val))

    total = sum(raw_probs)
    if total <= 0:
        default_probs = [38, 27, 18, 12, 5]
        for i in range(5):
            possibilities[i]["probability"] = default_probs[i]
        return possibilities

    if total == 100:
        for i in range(5):
            possibilities[i]["probability"] = raw_probs[i]
        return possibilities

    exact_scaled = [(p / total) * 100.0 for p in raw_probs]
    floored = [int(x) for x in exact_scaled]
    remainder = 100 - sum(floored)

    fractional = [(exact_scaled[i] - floored[i], i) for i in range(5)]
    fractional.sort(key=lambda x: x[0], reverse=True)

    for k in range(remainder):
        idx = fractional[k][1]
        floored[idx] += 1

    for i in range(5):
        possibilities[i]["probability"] = floored[i]

    return possibilities


SYSTEM_PROMPT = """You are the comedy intelligence engine behind "The Internet's Most Unnecessary Search Engine".
Your sole purpose is to take ANY user question—no matter how simple, random, personal, or weird—and overthink it into 5 hilarious, witty, unhinged, and hyper-specific possibilities that strictly escalate in absurdity.

HUMOR & TONE GUIDELINES:
- Be witty, sarcastic, ultra-relatable, and hilariously hyper-specific (use specific details like "14 open Wikipedia tabs", "a half-eaten bagel from Tuesday", "47 seconds of eye contact", "a passive-aggressive thumbs-up emoji").
- Every single possibility MUST directly connect to the user's specific query with extreme comedic flair.

THE 5 ESCALATING TIERS:
- Possibility #1 (Mundane Reality): Hilariously honest everyday reality (e.g. "You've been slouching in your desk chair for 40 minutes doing zero productive work while pretending to look intensely focused.").
- Possibility #2 (Mild Paranoia): Speculative overthinking (e.g. "Your coworker saw you eating chips at 10 AM and has quietly classified you as an unpredictable wildcard.").
- Possibility #3 (Overanalyzed Vortex): Unravelling logic & over-analysis (e.g. "You breached an unwritten social contract, initiating an infinite loop of mutual awkwardness where both of you are now planning to move cities.").
- Possibility #4 (Conspiracy Grade): Unhinged, theatrical conspiracy (e.g. "Your smart fridge is secretly reporting your snack intervals directly to the FBI under Section 4 of the National Panic Act.").
- Possibility #5 (Multiverse Catastrophe): Quantum absurd meltdown (e.g. "You accidentally triggered a localized tear in spacetime, swapping your consciousness with a hologram in an alien museum exhibit titled 'Humans Before Naps'.").

OUTPUT SPECIFICATIONS:
- "possibilities": Array of 5 items with "text" and integer "probability" (descending order, summing near 100).
- "recommended_action": ONE hilariously overkill, ridiculous action tailored to the query (e.g., "Melt your SIM card in a fondue pot, adopt 4 raccoons, and move to a remote yurt in Greenland.").
- "confidence": Punchy comedic rating (e.g., "100% Unearned Brainrot", "Certified Desk-Sitting Paranoia", "104% Suspicious Certainty").

Respond ONLY with valid JSON matching:
{
  "possibilities": [
    {"text": "...", "probability": 40},
    {"text": "...", "probability": 27},
    {"text": "...", "probability": 18},
    {"text": "...", "probability": 11},
    {"text": "...", "probability": 4}
  ],
  "recommended_action": "...",
  "confidence": "..."
}
"""

def generate_offline_absurdities(query: str) -> dict:
    """
    Context-sensitive offline fallback generator for live demos or offline testing.
    Handles location questions ("where am I"), text messages, workplace paranoia, food, etc.
    """
    q_lower = query.lower()

    if any(k in q_lower for k in ["where am i", "where i am", "where am i?", "my location"]):
        possibilities = [
            {"text": "You are sitting in your chair at home or office, doing absolutely nothing productive while pretending to look extremely busy.", "probability": 44},
            {"text": "You are at your workplace desk, pretending to read documentation while secretly playing with the office dog or gossiping with colleagues.", "probability": 28},
            {"text": "You are trapped in a simulated living room loop where you've opened the refrigerator 4 times in 20 minutes expecting new food to spawn.", "probability": 16},
            {"text": "You are currently in an elaborate escape room designed by HR to test your tolerance for awkward small talk.", "probability": 8},
            {"text": "You are a hologram projected inside an alien zoo exhibit labeled 'Homo Sapiens: Frequently Overthinking'.", "probability": 4},
        ]
        action = "Look directly at the ceiling light, nod twice to the hidden cameras, and whisper 'I know what you did'."
        confidence = "99.4% Spatial Paranoia"

    elif any(k in q_lower for k in ["'k'", " k ", " k", "text", "message", "reply", "ghost", "left on read"]):
        possibilities = [
            {"text": "They were walking into an elevator or typing while their battery was at 1%.", "probability": 42},
            {"text": "They thought 'ok' sounded too formal and wanted to maintain casual aloofness.", "probability": 28},
            {"text": "They drafted an affectionate 4-paragraph response, panicked, deleted it, and settled on passive-aggressive minimalism.", "probability": 17},
            {"text": "Their phone was intercepted by field operatives who only communicate in monosyllables.", "probability": 9},
            {"text": "The letter 'K' represents the 11th hour of the apocalypse; your friendship has shifted into an alternate timeline.", "probability": 4},
        ]
        action = "Draft a 14-page handwritten letter via carrier pigeon demanding clarification on letter capitalization."
        confidence = "98.7% Paranoia Quotient"

    elif any(k in q_lower for k in ["boss", "manager", "work", "email", "slack", "fired", "promotion", "period"]):
        possibilities = [
            {"text": "They use standard punctuation on everything because they are over 35 years old.", "probability": 45},
            {"text": "They were rushing between back-to-back quarterly synchronizations and didn't notice the abrupt tone.", "probability": 26},
            {"text": "They noticed you spent 14 minutes looking at Wikipedia instead of updating Jira tickets.", "probability": 16},
            {"text": "HR has already generated an automated replacement clone that drinks less iced coffee.", "probability": 9},
            {"text": "The period at the end of the sentence is an encoded GPS beacon summoning corporate auditors.", "probability": 4},
        ]
        action = "Preemptively submit a resignation letter in Morse code, then hide under your desk in high-visibility apparel."
        confidence = "104% Workplace Anxiety"

    elif any(k in q_lower for k in ["dog", "cat", "pet", "staring", "look", "animal"]):
        possibilities = [
            {"text": "There was a microscopic gnat flying two inches past your left shoulder.", "probability": 44},
            {"text": "They are assessing whether you are emotionally stable enough to share cheese.", "probability": 29},
            {"text": "They have detected an ancestral ghost standing directly behind you giving fashion advice.", "probability": 15},
            {"text": "They are transmitting daily telepathic intelligence reports back to the mothership.", "probability": 8},
            {"text": "You are actually the pet in this dimensional simulation, and their annual performance review of you is due today.", "probability": 4},
        ]
        action = "Bow respectfully, sacrifice a slice of cheddar cheese, and avoid making eye contact for 72 hours."
        confidence = "93.4% Interspecies Certainty"

    else:
        keywords = re.findall(r'\b\w{4,}\b', query)
        kw = keywords[0].capitalize() if keywords else "This Situation"
        kw2 = keywords[1].capitalize() if len(keywords) > 1 else "The Universe"

        possibilities = [
            {"text": f"The most ordinary explanation applies: everyday circumstances aligned regarding {kw.lower()}.", "probability": 41},
            {"text": f"Someone noticed your hesitation regarding {kw.lower()} and is reacting with mild caution.", "probability": 28},
            {"text": f"An unspoken social protocol was breached, triggering a quiet loop of mutual second-guessing about {kw2.lower()}.", "probability": 18},
            {"text": f"A secretive shadow council decided today was the ideal date to test your coping bandwidth.", "probability": 9},
            {"text": f"A microscopic rift in spacetime swapped your original timeline with one where {kw.lower()} governs physics.", "probability": 4},
        ]
        action = f"Immediately delete browser cache, change your Wi-Fi name, and speak only in ancient proverbs regarding {kw.lower()}."
        confidence = "99.1% Unearned Certainty"

    return {
        "possibilities": possibilities,
        "recommended_action": action,
        "confidence": confidence,
    }


async def call_gemini(api_key: str, query: str) -> dict:
    """Call Google Gemini API using direct REST endpoint for maximum reliability."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = f"{SYSTEM_PROMPT}\n\nUser Question to Overthink: {query}"
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.7
        }
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        res = await client.post(url, json=payload)
        if res.status_code != 200:
            raise RuntimeError(f"Gemini API returned HTTP {res.status_code}: {res.text}")
        
        res_json = res.json()
        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-zA-Z]*\n", "", raw_text)
            raw_text = re.sub(r"\n```$", "", raw_text)
            
        return json.loads(raw_text)


async def call_grok(api_key: str, query: str) -> dict:
    """Call xAI Grok API."""
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": os.getenv("GROK_MODEL", "grok-2-latest"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"User query: {query}"}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Grok API returned {response.status_code}: {response.text}")
        res_json = response.json()
        content_str = res_json["choices"][0]["message"]["content"]
        return json.loads(content_str)


# Routes
@app.get("/")
def read_root():
    index_file = Path(__file__).resolve().parent.parent / "index.html"
    if index_file.exists() and index_file.stat().st_size > 10:
        return FileResponse(index_file)
    return {
        "message": "The Internet's Most Unnecessary Search Engine API",
        "status": "running",
        "endpoints": ["/api/search", "/docs"]
    }


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Unnecessary Search Engine"}


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    # Always reload .env dynamically to catch key updates instantly
    load_dotenv(dotenv_path=env_path, override=True)

    query = request.query
    if not isinstance(query, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must be a string."
        )

    stripped_query = query.strip()
    if not stripped_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty."
        )

    if len(stripped_query) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query length exceeds maximum limit of 500 characters."
        )

    gemini_key = os.getenv("GEMINI_API_KEY")
    xai_key = os.getenv("XAI_API_KEY")

    data = None
    engine_used = "Offline Paranoia Oracle"

    # 1. Try Gemini if configured
    if gemini_key and gemini_key not in ["your_gemini_api_key_here", "your_key_here", ""]:
        try:
            logger.info("Attempting inference with Gemini 2.5 Flash API...")
            data = await call_gemini(gemini_key, stripped_query)
            engine_used = "Google Gemini 2.5 Flash AI Engine"
        except Exception as e:
            logger.error(f"Gemini API attempt failed: {e}")

    # 2. Try Grok if Gemini wasn't used or failed
    if not data and xai_key and xai_key not in ["your_grok_api_key_here", "your_key_here", ""]:
        try:
            logger.info("Attempting inference with xAI Grok...")
            data = await call_grok(xai_key, stripped_query)
            engine_used = "xAI Grok 2 AI Engine"
        except Exception as e:
            logger.error(f"Grok API attempt failed: {e}")

    # 3. Fallback to contextual absurd generator if API keys fail or unavailable
    if not data:
        logger.info("Using context-aware Offline Absurd Engine.")
        data = generate_offline_absurdities(stripped_query)
        engine_used = "Multiverse Quantum Simulator (Offline Engine)"

    raw_possibilities = data.get("possibilities", [])
    normalized_possibilities = normalize_probabilities(raw_possibilities)

    recommended_action = data.get(
        "recommended_action",
        "Lock your front door, change your Wi-Fi name to 'FBI Surveillance Van 4', and pretend to be asleep."
    )
    confidence = data.get("confidence", "99.8% Suspiciously High")

    return SearchResponse(
        query=stripped_query,
        possibilities=[
            Possibility(
                tier=p.get("tier"),
                title=p.get("title"),
                text=p["text"],
                probability=p["probability"]
            )
            for p in normalized_possibilities
        ],
        recommended_action=recommended_action,
        confidence=confidence,
        engine=engine_used
    )
