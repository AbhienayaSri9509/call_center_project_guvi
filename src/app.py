import os
import base64
import tempfile
import json

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from openai import OpenAI
from dotenv import load_dotenv

# Load env
load_dotenv()

# Keys
API_KEY = os.getenv("API_KEY", "sk_track3_987654321")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# App
app = FastAPI(title="Call Center Compliance API")


# Request Schema
class CallAnalyticsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    language: str
    audioFormat: str
    audioBase64: str


# 🎙️ TRANSCRIPTION USING OPENAI (NO WHISPER)
def transcribe_audio(file_path):
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file
        )
    return transcript.text


# 🤖 GPT Analysis
def analyze_with_gpt(transcript: str) -> dict:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict call center compliance AI."
                },
                {
                    "role": "user",
                    "content": f"""
Analyze the following call center transcript and extract business intelligence.

Transcript:
{transcript}

Return JSON with:
summary, sop_validation, analytics, keywords
"""
                }
            ],
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print("OpenAI Error:", e)
        return {}


# 🚀 API
@app.post("/api/call-analytics")
def analyze_call(req_body: CallAnalyticsRequest, x_api_key: str = Header(None)):

    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if req_body.audioFormat.lower() != "mp3":
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": "audioFormat must be mp3"
        })

    temp_audio_path = None

    try:
        # decode audio
        audio_data = base64.b64decode(req_body.audioBase64)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            temp_audio.write(audio_data)
            temp_audio_path = temp_audio.name

        # 🎙️ TRANSCRIBE (API)
        transcript = transcribe_audio(temp_audio_path)

        if not transcript:
            raise Exception("Transcript empty")

        # 🤖 ANALYSIS
        analysis = analyze_with_gpt(transcript)

        return {
            "status": "success",
            "language": req_body.language,
            "transcript": transcript,
            "summary": analysis.get("summary", ""),
            "sop_validation": analysis.get("sop_validation", {}),
            "analytics": analysis.get("analytics", {}),
            "keywords": analysis.get("keywords", ["Agent", "Customer"])
        }

    except Exception as e:
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(e)
        })

    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)