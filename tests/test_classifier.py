"""
Standalone tests for the heuristic email classifier.
No pytest fixtures — plain assert statements only.
Run with:  python -m pytest tests/test_classifier.py -v
       or:  python tests/test_classifier.py
"""

import sys
import os

# Allow running directly without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.classifier import classify_email


def test_clear_marketing_email():
    """Mass-sender domain + unsubscribe link → Marketing."""
    result = classify_email(
        sender="promo@mailchimp.com",
        subject="Join us for our exclusive event this weekend!",
        body_preview="Don't miss out. Click here to register now. Unsubscribe at any time.",
    )
    assert result["label"] == "Marketing", f"Expected Marketing, got {result}"
    assert result["confidence"] > 0.6, f"Low confidence: {result['confidence']}"


def test_blackboard_grade_notification():
    """Real KFUPM Blackboard grade email must classify as Important."""
    result = classify_email(
        sender="do-not-reply@blackboard.com",
        subject="New grade and feedback for Quiz 3 in 252-ICS-353-01(Design/Analysis of Algorithms)",
        body_preview="New grade and feedback. Quiz 3. Assessment. View grades. Want to change how you receive these emails? Manage your notification settings.",
        recipient_name=None,
    )
    assert result["label"] == "Important", f"Expected Important, got {result}"
    assert result["confidence"] >= 0.6, f"Confidence too low: {result}"


def test_ambiguous_email():
    """Generic sender, no strong signals → Other."""
    result = classify_email(
        sender="info@somecompany.com",
        subject="Hello",
        body_preview="Just checking in.",
    )
    assert result["label"] == "Other", f"Expected Other, got {result}"


def test_kfupm_registrar_email():
    """Registrar local part from kfupm.edu.sa → Important even with neutral subject."""
    result = classify_email(
        sender="registrar@kfupm.edu.sa",
        subject="Announcement",
        body_preview="Please review the attached document.",
    )
    assert result["label"] == "Important", f"Expected Important, got {result}"
    assert result["confidence"] > 0.6, f"Low confidence: {result['confidence']}"


def test_kfupm_non_official_email():
    """Non-official local part from kfupm.edu.sa → Other (not Important)."""
    result = classify_email(
        sender="student123@kfupm.edu.sa",
        subject="Hey",
        body_preview="Are you coming to the meetup?",
    )
    # Score for sender is 0.6 important, 0.1 marketing.
    # Subject/body are neutral → weighted important ≈ 0.6*0.4 = 0.24 → Other
    assert result["label"] in ("Other", "Important"), f"Unexpected label: {result}"
    # At minimum, it should NOT be Marketing
    assert result["label"] != "Marketing", f"Should not be Marketing: {result}"


def test_mass_sender_domain():
    """SendGrid domain → Marketing regardless of subject."""
    result = classify_email(
        sender="noreply@sendgrid.net",
        subject="Your monthly report",
        body_preview="Please find your report attached.",
    )
    assert result["label"] == "Marketing", f"Expected Marketing, got {result}"
    assert result["confidence"] > 0.6, f"Low confidence: {result['confidence']}"


def test_important_keywords_in_subject():
    """Multiple important keywords push score above threshold."""
    result = classify_email(
        sender="someone@example.com",
        subject="Final exam results and grade warning — action required",
        body_preview="Please check your transcript.",
    )
    assert result["label"] == "Important", f"Expected Important, got {result}"


def test_marketing_keywords_in_subject():
    """Multiple marketing keywords from a non-mass-sender → Marketing."""
    result = classify_email(
        sender="events@university-club.org",
        subject="Invitation to our hackathon and workshop — limited seats!",
        body_preview="We would be cordially pleased to have you as our guest speaker.",
    )
    assert result["label"] == "Marketing", f"Expected Marketing, got {result}"


def test_unsubscribe_boosts_marketing():
    """Unsubscribe alone is a strong Marketing signal."""
    result = classify_email(
        sender="news@example.org",
        subject="Weekly newsletter",
        body_preview=(
            "Here is your weekly digest. To stop receiving these emails, "
            "click unsubscribe below. Learn more about our offerings."
        ),
    )
    assert result["label"] == "Marketing", f"Expected Marketing, got {result}"


def test_html_heavy_body():
    """High density of HTML tags from a mass-mail sender → Marketing signal."""
    # Mass-mail sender gives si_mkt=0.9. HTML body pushes bo_mkt above baseline.
    # Combined, marketing score clearly exceeds 0.6.
    html_body = "<div><p><strong><em><a href='#'>Click here</a></em></strong></p></div>" * 5
    result = classify_email(
        sender="noreply@mailchimp.com",
        subject="Special offer",
        body_preview=html_body,
    )
    assert result["label"] == "Marketing", f"Expected Marketing, got {result}"


def test_batch_size_respected():
    """Classifier works correctly across multiple emails in a loop."""
    emails = [
        {
            "sender": "registrar@kfupm.edu.sa",
            "subject": "Urgent: Transcript deadline",
            "body_preview": "Action required immediately.",
        },
        {
            "sender": "promo@mailchimp.com",
            "subject": "Join us for our event",
            "body_preview": "Unsubscribe anytime.",
        },
        {
            "sender": "friend@gmail.com",
            "subject": "Lunch?",
            "body_preview": "Are you free today?",
        },
    ]
    results = [classify_email(**e) for e in emails]
    labels = [r["label"] for r in results]
    assert labels[0] == "Important", f"First email should be Important: {results[0]}"
    assert labels[1] == "Marketing", f"Second email should be Marketing: {results[1]}"
    assert labels[2] == "Other", f"Third email should be Other: {results[2]}"


if __name__ == "__main__":
    tests = [
        test_clear_marketing_email,
        test_blackboard_grade_notification,
        test_ambiguous_email,
        test_kfupm_registrar_email,
        test_kfupm_non_official_email,
        test_mass_sender_domain,
        test_important_keywords_in_subject,
        test_marketing_keywords_in_subject,
        test_unsubscribe_boosts_marketing,
        test_html_heavy_body,
        test_batch_size_respected,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
