# App 7: Autonomous Medical Intake Nurse (Voice)

## Concept
A HIPAA-compliant voice agent that handles inbound patient triage and scheduling.

## Workflow
1.  **Inbound Call:** Receives call via Twilio/Vapi.
2.  **Screening:** Asks screening questions (symptoms, duration, urgency).
3.  **Triage:** Uses a medical RAG knowledge base to determine if the patient needs an ER, an urgent care visit, or a routine appointment.
4.  **Scheduling:** Autonomously checks the clinic's EHR (Electronic Health Record) calendar and books the slot.
5.  **Confirmation:** Sends a follow-up SMS with appointment details.

## Tech Stack
- **Language:** Python
- **Backend:** FastAPI (Async)
- **Voice Orchestration:** Vapi (Advanced Voice Engine)
- **STT:** Deepgram (Nova-2 Model)
- **TTS:** Cartesia (Sonic-1 for <100ms generation)
- **Database:** MongoDB Atlas (for flexible medical schemas)
