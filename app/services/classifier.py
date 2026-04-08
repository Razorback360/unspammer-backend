"""
Heuristic-based email classifier.
No ML libraries, no HTTP calls. Pure Python logic.

Signal model:
  Each of the three signals returns (important_score, marketing_score) in [0, 1].
  Neutral baseline is 0.5 for both categories when a signal has no evidence.
  Signals combine as a weighted average: sender 40%, subject 35%, body 25%.
  Label thresholds: Important or Marketing if score > 0.6, otherwise Other.
"""

from __future__ import annotations

import re

MASS_MAIL_KEYWORDS = {
    "mailchimp",
    "sendgrid",
    "constantcontact",
    "hubspot",
    "noreply",
    "no-reply",
    "donotreply",
    "marketing",
    "newsletter",
    "notifications",
    "mailer",
    "campaigns",
}

KFUPM_IMPORTANT_LOCAL = {
    "registrar",
    "academic",
    "provost",
    "dean",
    "admission",
    "finance",
    "noreply",
    "blackboard",
    "lms",
}

TRUSTED_ACADEMIC_PLATFORMS = {
    "blackboard.com",
    "blackboard.kfupm.edu.sa",
    "instructure.com",
    "canvas.com",
}

IMPORTANT_SUBJECT_KEYWORDS = [
    "deadline",
    "urgent",
    "required",
    "mandatory",
    "grade",
    "exam",
    "final",
    "result",
    "warning",
    "action required",
    "failure",
    "dismissed",
    "probation",
    "registration",
    "tuition",
    "transcript",
    "feedback",
    "quiz",
    "assignment",
    "course",
    "submission",
    "score",
]

MARKETING_SUBJECT_KEYWORDS = [
    "join us",
    "event",
    "invitation",
    "celebrate",
    "workshop",
    "seminar",
    "competition",
    "hackathon",
    "club",
    "fest",
    "ceremony",
    "cordially",
    "guest",
    "speaker",
    "register now",
    "limited seats",
    "opportunity",
]


def _is_mass_mail_domain(domain: str) -> bool:
    parts = domain.split(".")
    for part in parts:
        if part in MASS_MAIL_KEYWORDS:
            return True
    for keyword in MASS_MAIL_KEYWORDS:
        if domain.startswith(keyword + ".") or f".{keyword}." in domain:
            return True
    return False


def _sender_signal(sender: str) -> tuple[float, float]:
    """
    Returns (important_score, marketing_score).
    Neutral baseline is (0.5, 0.5) when no signal fires.
    """
    sender = sender.lower().strip()
    domain = sender.split("@", 1)[1] if "@" in sender else sender
    local = sender.split("@")[0] if "@" in sender else ""

    # Trusted academic platforms take priority
    for platform in TRUSTED_ACADEMIC_PLATFORMS:
        if domain == platform or domain.endswith("." + platform):
            return 0.85, 0.1

    if _is_mass_mail_domain(domain):
        return 0.1, 0.9

    if domain.endswith("kfupm.edu.sa"):
        if local in KFUPM_IMPORTANT_LOCAL:
            return 0.9, 0.1
        return 0.6, 0.1  # Other-ish from kfupm

    return 0.5, 0.5  # neutral


def _subject_signal(subject: str) -> tuple[float, float]:
    """
    Returns (important_score, marketing_score).
    Baseline is 0.5; each keyword hit adds 0.15, capped at 0.95.
    """
    lower = subject.lower()

    important_score = 0.5
    for kw in IMPORTANT_SUBJECT_KEYWORDS:
        if kw in lower:
            important_score = min(important_score + 0.15, 0.95)

    marketing_score = 0.5
    for kw in MARKETING_SUBJECT_KEYWORDS:
        if kw in lower:
            marketing_score = min(marketing_score + 0.15, 0.95)

    return important_score, marketing_score


def _body_signal(body: str, recipient_name: str | None) -> tuple[float, float]:
    """
    Returns (important_score, marketing_score).
    Baseline is 0.5 for both; signals shift the scores up or down.
    """
    lower = body.lower()
    important_score = 0.5
    marketing_score = 0.5

    if "unsubscribe" in lower:
        marketing_score += 0.4

    if "click here" in lower or "learn more" in lower:
        marketing_score += 0.2

    if recipient_name and recipient_name.lower() in lower:
        important_score += 0.2

    if "dear student" in lower or "dear all" in lower:
        # Generic address → push toward Other (less Important, slightly less Marketing)
        important_score -= 0.3
        marketing_score -= 0.15

    # HTML-heavy: high density of angle brackets signals templated/marketing content
    if len(body) > 0 and body.count("<") / len(body) > 0.02:
        marketing_score += 0.2

    important_score = max(0.0, min(1.0, important_score))
    marketing_score = max(0.0, min(1.0, marketing_score))

    return important_score, marketing_score

def extract_event_date(subject: str, body_preview: str) -> str:
    """Extract dates from subject and body. Handles various common formats."""
    text = f"{subject} {body_preview}"
    
    # 1. YYYY-MM-DD, YYYY/MM/DD
    pattern1 = r'\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\b'
    # 2. DD/MM/YYYY, DD-MM-YYYY, MM/DD/YYYY, with or without 4-digit year
    pattern2 = r'\b(\d{1,2}[-/.]\d{1,2}[-/.](?:20\d{2}|\d{2}))\b'
    # 3. Month DD, YYYY or Month DD
    pattern3 = r'\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*20\d{2})?)\b'
    # 4. DD Month YYYY
    pattern4 = r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?:,?\s*20\d{2})?)\b'
    
    for pattern in [pattern1, pattern2, pattern3, pattern4]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
    return ""

def classify_email(
    sender: str,
    subject: str,
    body_preview: str,
    recipient_name: str | None = None,
) -> dict:
    """
    Classify an email using heuristic signals.

    Returns:
        {"label": "Important" | "Marketing" | "Other", "confidence": float}
    """
    sender_lower = sender.lower()
    subject_lower = subject.lower()
    body_lower = body_preview.lower()

    # High-priority rules override
    important_keywords = ["exam", "project", "quiz", "assignment", "registration"]
    important_senders = [
        "blackboard", "registrar", "edesk", "gradescope", 
        "teams", "part-time-jobs", "evaluate", "amn", "registr"
    ]
    
    extracted_date = extract_event_date(subject, body_preview)

    if any(kw in sender_lower for kw in important_senders):
        return {"label": "Important", "confidence": 1.0, "event_date": extracted_date}

    if any(kw in subject_lower for kw in important_keywords) or "blackboard" in subject_lower:
        return {"label": "Important", "confidence": 1.0, "event_date": extracted_date}

    if any(kw in body_lower for kw in important_keywords) or "blackboard" in body_lower:
        return {"label": "Important", "confidence": 1.0, "event_date": extracted_date}

    si_imp, si_mkt = _sender_signal(sender)
    su_imp, su_mkt = _subject_signal(subject)
    bo_imp, bo_mkt = _body_signal(body_preview, recipient_name)

    # Weighted average — sender 40%, subject 35%, body 25%
    important_score = si_imp * 0.40 + su_imp * 0.35 + bo_imp * 0.25
    marketing_score = si_mkt * 0.40 + su_mkt * 0.35 + bo_mkt * 0.25

    important_above_threshold = important_score > 0.6
    marketing_above_threshold = marketing_score > 0.6

    if important_above_threshold and marketing_above_threshold:
        if important_score >= marketing_score:
            label = "Important"
            confidence = round(important_score, 4)
        else:
            label = "Unimportant"
            confidence = round(marketing_score, 4)
    elif important_above_threshold:
        label = "Important"
        confidence = round(important_score, 4)
    elif marketing_above_threshold:
        label = "Unimportant"
        confidence = round(marketing_score, 4)
    else:
        label = "Unimportant"
        confidence = round(1.0 - max(important_score, marketing_score), 4)

    return {"label": label, "confidence": confidence, "event_date": extracted_date}
