import os
import base64
import tempfile
import json
import whisper   # ✅ correct import

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from openai import OpenAI
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# API Keys
API_KEY = os.getenv("API_KEY", "sk_track3_987654321")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ✅ Load lightweight Whisper model (important for Render memory)
print("Loading Whisper model...")
model = whisper.load_model("tiny")
print("Whisper model loaded.")

# FastAPI app
app = FastAPI(title="Call Center Compliance API")


# Request Schema
class CallAnalyticsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    language: str
    audioFormat: str
    audioBase64: str


# GPT Analysis
def analyze_with_gpt(transcript: str) -> dict:
    if not client:
        return {}

    prompt = f"""
    Analyze the following call center transcript and extract business intelligence and compliance metrics.

    Transcript:
    "{transcript}"

    Return ONLY a valid JSON object matching EXACTLY this structure:
    {{
      "summary": "",
      "sop_validation": {{
        "greeting": false,
        "identification": false,
        "problemStatement": false,
        "solutionOffering": false,
        "closing": false,
        "complianceScore": 0.0,
        "adherenceStatus": "",
        "explanation": ""
      }},
      "analytics": {{
        "paymentPreference": "",
        "rejectionReason": "",
        "sentiment": ""
      }},
      "keywords": []
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a strict call center compliance AI."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print("OpenAI Error:", e)
        return {}


# API Endpoint
@app.post("/api/call-analytics")
def analyze_call(req_body: CallAnalyticsRequest, x_api_key: str = Header(None)):

    # Auth check
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Validate format
    if req_body.audioFormat.lower() != "mp3":
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": "audioFormat must be mp3"
        })

    temp_audio_path = None

    try:
        # Decode base64
        audio_data = base64.b64decode(req_body.audioBase64)

        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            temp_audio.write(audio_data)
            temp_audio_path = temp_audio.name

        # 🎙️ Transcribe
        result = model.transcribe(temp_audio_path)
        transcript = result["text"].strip()

        if not transcript:
            raise Exception("Transcript empty")

        # 🤖 AI Analysis
        analysis = analyze_with_gpt(transcript)

        # Final response
        final_response = {
            "status": "success",
            "language": req_body.language,
            "transcript": transcript,
            "summary": analysis.get("summary", "AI skipped"),
            "sop_validation": analysis.get("sop_validation", {
                "greeting": False,
                "identification": False,
                "problemStatement": False,
                "solutionOffering": False,
                "closing": False,
                "complianceScore": 0.0,
                "adherenceStatus": "NOT_FOLLOWED",
                "explanation": "Fallback response"
            }),
            "analytics": analysis.get("analytics", {
                "paymentPreference": "DOWN_PAYMENT",
                "rejectionReason": "NONE",
                "sentiment": "Neutral"
            }),
            "keywords": analysis.get("keywords", ["Agent", "Customer"])
        }

        return final_response

    except Exception as e:
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(e)
        })

    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)