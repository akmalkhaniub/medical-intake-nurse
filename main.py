from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

app = FastAPI(title="Medical Intake Voice Agent")


class TriageLevel(str, Enum):
    ER = "ER"
    URGENT = "urgent_care"
    ROUTINE = "routine"


class Symptom(BaseModel):
    name: str
    duration: str | None = None
    severity: int = Field(default=1, ge=1, le=10)


class Patient(BaseModel):
    id: str = Field(default_factory=lambda: f"pat_{uuid.uuid4().hex[:8]}")
    name: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TriageResult(BaseModel):
    level: TriageLevel
    urgency_score: int = Field(ge=1, le=5)
    reasoning: str
    recommended_action: str


class Appointment(BaseModel):
    id: str = Field(default_factory=lambda: f"apt_{uuid.uuid4().hex[:8]}")
    patient_id: str
    scheduled_at: datetime
    department: str
    reason: str
    status: str = "confirmed"


class IntakeSession(BaseModel):
    id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    call_id: str
    patient: Patient = Field(default_factory=Patient)
    symptoms: list[Symptom] = Field(default_factory=list)
    triage_result: TriageResult | None = None
    appointment: Appointment | None = None
    stage: str = "greeting"
    transcript: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None


sessions: dict[str, IntakeSession] = {}
sessions_by_call: dict[str, str] = {}
appointments: dict[str, Appointment] = {}

HIGH_URGENCY_KEYWORDS = {
    "chest pain": 5, "difficulty breathing": 5, "severe bleeding": 5,
    "unconscious": 5, "stroke": 5, "heart attack": 5, "seizure": 5,
    "choking": 5, "anaphylaxis": 5, "suicidal": 5,
}
MEDIUM_URGENCY_KEYWORDS = {
    "high fever": 4, "vomiting blood": 4, "broken bone": 4, "fracture": 4,
    "deep cut": 3, "persistent vomiting": 3, "severe headache": 3,
    "abdominal pain": 3, "dizziness": 3, "dehydration": 3,
}
LOW_URGENCY_KEYWORDS = {
    "cold": 1, "cough": 1, "sore throat": 1, "runny nose": 1,
    "mild headache": 2, "rash": 2, "back pain": 2, "earache": 2,
    "fatigue": 1, "allergies": 1, "mild fever": 2,
}

ALL_KEYWORDS = {**LOW_URGENCY_KEYWORDS, **MEDIUM_URGENCY_KEYWORDS, **HIGH_URGENCY_KEYWORDS}


def compute_urgency(symptoms: list[Symptom]) -> int:
    if not symptoms:
        return 1
    max_score = 1
    for symptom in symptoms:
        symptom_lower = symptom.name.lower()
        for keyword, score in ALL_KEYWORDS.items():
            if keyword in symptom_lower:
                max_score = max(max_score, score)
        max_score = max(max_score, min(symptom.severity // 2, 5))
    return min(max_score, 5)


def triage(symptoms: list[Symptom]) -> TriageResult:
    urgency = compute_urgency(symptoms)
    if urgency >= 5:
        return TriageResult(
            level=TriageLevel.ER,
            urgency_score=5,
            reasoning="Patient reports symptoms indicating a potential emergency.",
            recommended_action="Transfer to 911 or nearest emergency room immediately.",
        )
    if urgency >= 3:
        return TriageResult(
            level=TriageLevel.URGENT,
            urgency_score=urgency,
            reasoning="Symptoms require same-day medical attention.",
            recommended_action="Book urgent care appointment for today.",
        )
    return TriageResult(
        level=TriageLevel.ROUTINE,
        urgency_score=urgency,
        reasoning="Symptoms are manageable and non-urgent.",
        recommended_action="Schedule routine appointment at next available slot.",
    )


def book_appointment_for_session(session: IntakeSession) -> Appointment:
    if session.triage_result is None:
        session.triage_result = triage(session.symptoms)

    level = session.triage_result.level
    now = datetime.utcnow()

    if level == TriageLevel.ER:
        scheduled = now
        dept = "Emergency"
    elif level == TriageLevel.URGENT:
        scheduled = now + timedelta(hours=2)
        dept = "Urgent Care"
    else:
        scheduled = now + timedelta(days=3)
        dept = "General Practice"

    symptom_names = ", ".join(s.name for s in session.symptoms) or "General checkup"
    appt = Appointment(
        patient_id=session.patient.id,
        scheduled_at=scheduled,
        department=dept,
        reason=symptom_names,
    )
    session.appointment = appt
    appointments[appt.id] = appt
    return appt


def get_or_create_session(call_id: str) -> IntakeSession:
    if call_id in sessions_by_call:
        return sessions[sessions_by_call[call_id]]
    session = IntakeSession(call_id=call_id)
    sessions[session.id] = session
    sessions_by_call[call_id] = session.id
    return session


# --- Vapi function-call handlers ---

def handle_collect_symptoms(session: IntakeSession, args: dict[str, Any]) -> dict:
    raw_symptoms = args.get("symptoms", [])
    for item in raw_symptoms:
        if isinstance(item, str):
            session.symptoms.append(Symptom(name=item))
        elif isinstance(item, dict):
            session.symptoms.append(Symptom(**item))
    session.stage = "severity_assessment"
    return {
        "message": f"Recorded {len(raw_symptoms)} symptom(s). Proceeding to severity assessment.",
        "symptoms": [s.model_dump() for s in session.symptoms],
    }


def handle_assess_severity(session: IntakeSession, args: dict[str, Any]) -> dict:
    for symptom in session.symptoms:
        name_lower = symptom.name.lower()
        for keyword, score in ALL_KEYWORDS.items():
            if keyword in name_lower:
                symptom.severity = max(symptom.severity, score * 2)
                break
    if "severity_override" in args:
        override = int(args["severity_override"])
        for symptom in session.symptoms:
            symptom.severity = max(symptom.severity, override)

    session.triage_result = triage(session.symptoms)
    session.stage = "triage_complete"
    return {
        "triage": session.triage_result.model_dump(),
        "message": f"Triage complete. Level: {session.triage_result.level.value}, Urgency: {session.triage_result.urgency_score}/5.",
    }


def handle_book_appointment(session: IntakeSession, args: dict[str, Any]) -> dict:
    if args.get("patient_name"):
        session.patient.name = args["patient_name"]
    if args.get("patient_phone"):
        session.patient.phone = args["patient_phone"]

    appt = book_appointment_for_session(session)
    session.stage = "booked"
    return {
        "appointment": appt.model_dump(mode="json"),
        "message": f"Appointment booked at {appt.department} for {appt.scheduled_at.isoformat()}.",
    }


def handle_escalate_to_nurse(session: IntakeSession, args: dict[str, Any]) -> dict:
    session.stage = "escalated"
    return {
        "escalated": True,
        "reason": args.get("reason", "Patient requires immediate human attention."),
        "message": "Transferring to a nurse now. Please hold.",
    }


FUNCTION_HANDLERS = {
    "collect_symptoms": handle_collect_symptoms,
    "assess_severity": handle_assess_severity,
    "book_appointment": handle_book_appointment,
    "escalate_to_nurse": handle_escalate_to_nurse,
}


@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    data = await request.json()
    event_type = data.get("type", "")
    call_id = data.get("call_id", data.get("call", {}).get("id", "unknown"))

    if event_type == "call.started":
        session = get_or_create_session(call_id)
        session.stage = "greeting"
        return {
            "message": "Hello, thank you for calling. I'm the automated intake assistant. Can you describe your symptoms?",
            "session_id": session.id,
        }

    if event_type == "call.ended":
        if call_id in sessions_by_call:
            session = sessions[sessions_by_call[call_id]]
            session.ended_at = datetime.utcnow()
            session.stage = "completed"
        return {"status": "call_ended"}

    if event_type == "speech":
        session = get_or_create_session(call_id)
        text = data.get("text", data.get("transcript", ""))
        if text:
            session.transcript.append(text)
        return {"status": "speech_received"}

    if event_type == "function_call":
        session = get_or_create_session(call_id)
        fn_name = data.get("function", data.get("name", ""))
        fn_args = data.get("arguments", data.get("args", {}))
        if isinstance(fn_args, str):
            import json
            fn_args = json.loads(fn_args)

        handler = FUNCTION_HANDLERS.get(fn_name)
        if not handler:
            raise HTTPException(status_code=400, detail=f"Unknown function: {fn_name}")
        result = handler(session, fn_args)
        return {"result": result}

    return {"status": "unhandled_event", "type": event_type}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump(mode="json")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len([s for s in sessions.values() if s.ended_at is None]),
        "total_sessions": len(sessions),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
