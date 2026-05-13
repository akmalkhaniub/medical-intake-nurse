# Medical Intake Nurse

A HIPAA-compliant voice agent that handles inbound patient calls, performs symptom-based triage using a medical knowledge base, and autonomously books appointments in the clinic's EHR system.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        INBOUND CALL                                      │
│              (Patient dials clinic phone number)                          │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │  SIP / PSTN via Twilio
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    VOICE ORCHESTRATION (Vapi)                             │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                │
│  │  Deepgram    │   │  LLM Agent   │   │  Cartesia    │                │
│  │  STT         │──▶│  (Screening) │──▶│  TTS         │                │
│  │  Nova-2      │   │              │   │  Sonic-1     │                │
│  │              │   │  Symptoms?   │   │  <100ms      │                │
│  │  Audio ▶ text│   │  Duration?   │   │  text ▶ audio│                │
│  └──────────────┘   │  Urgency?    │   └──────────────┘                │
│                     └──────┬───────┘                                     │
│                            │  structured screening data                  │
│                            ▼                                             │
└──────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                                      │
│                                                                          │
│  POST /vapi/webhook        — handle Vapi call events                     │
│  GET  /appointments        — list scheduled appointments                 │
│  GET  /patients/:id        — patient intake history                      │
│                                                                          │
│         ┌───────────────────────────────────────────┐                   │
│         │              TRIAGE AGENT                  │                   │
│         │                                            │                   │
│         │  Medical RAG ──▶ Knowledge Base lookup     │                   │
│         │                                            │                   │
│         │  Output:                                   │                   │
│         │    ER          (immediate danger)           │                   │
│         │    Urgent Care (same-day visit)             │                   │
│         │    Routine     (schedule appointment)       │                   │
│         └──────────────────┬─────────────────────────┘                  │
│                            │                                             │
│                 ┌──────────┼──────────┐                                  │
│                 ▼          ▼          ▼                                  │
│              ER         Urgent     Routine                               │
│           ┌────────┐  ┌────────┐  ┌──────────┐                          │
│           │Transfer│  │ Book   │  │ Book     │                          │
│           │to 911  │  │ today  │  │ next     │                          │
│           │hotline │  │ slot   │  │ available│                          │
│           └────────┘  └───┬────┘  └────┬─────┘                          │
│                           └──────┬─────┘                                 │
│                                  ▼                                       │
│                     ┌───────────────────┐      ┌───────────────────┐    │
│                     │  EHR Calendar     │      │  MongoDB Atlas    │    │
│                     │  Integration      │      │  Patient Records  │    │
│                     │  (book slot)      │      │  Intake Data      │    │
│                     └───────────────────┘      └───────────────────┘    │
│                                  │                                       │
│                                  ▼                                       │
│                     ┌───────────────────┐                               │
│                     │  SMS Confirmation │                               │
│                     │  (Twilio)         │                               │
│                     │  Date, time, doc  │                               │
│                     └───────────────────┘                               │
└──────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python | Async-first with rich ML/NLP ecosystem |
| Backend | FastAPI | Async webhook handling and REST API |
| Voice | Vapi | End-to-end voice orchestration engine |
| STT | Deepgram Nova-2 | Real-time speech-to-text transcription |
| TTS | Cartesia Sonic-1 | Sub-100ms text-to-speech generation |
| Database | MongoDB Atlas | Flexible schema for varied medical intake forms |
| Telephony | Twilio | Inbound call routing and SMS confirmations |

## Quick Start

```bash
cd medical-intake-nurse
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Configure via environment variables:

```bash
export VAPI_API_KEY=...
export TWILIO_ACCOUNT_SID=...
export TWILIO_AUTH_TOKEN=...
export MONGODB_URI=mongodb+srv://...
```

## API Examples

### Vapi webhook endpoint
```bash
curl -X POST http://localhost:8000/vapi/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "call.ended", "call_id": "call_abc123", "transcript": "..."}'
```

### List appointments
```bash
curl http://localhost:8000/appointments?date=2026-05-12
```

### Get patient intake record
```bash
curl http://localhost:8000/patients/pat_456
```

## Design Decisions

- **Vapi over raw Twilio**: Vapi handles the STT-LLM-TTS loop natively, eliminating custom WebSocket audio streaming code and reducing voice latency.
- **Cartesia for TTS**: Sub-100ms generation provides natural conversational pacing. Patients should not notice they are speaking to an AI.
- **MongoDB flexible schema**: Medical intake forms vary by specialty. A document store avoids rigid table migrations when adding new screening question sets.
- **Triage-first architecture**: The agent never books directly. It always classifies urgency first, ensuring ER-level symptoms trigger immediate human escalation rather than scheduling a routine visit.
