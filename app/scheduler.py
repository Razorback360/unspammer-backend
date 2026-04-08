import logging

from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()


def _refresh_tokens_job() -> None:
    db = SessionLocal()
    try:
        from app.services.subscription import auto_refresh_expiring_tokens

        auto_refresh_expiring_tokens(db)
    except Exception:
        logger.exception("Error in token refresh job.")
    finally:
        db.close()


def _renew_subscriptions_job() -> None:
    db = SessionLocal()
    try:
        from app.services.subscription import auto_renew_expiring_subscriptions

        auto_renew_expiring_subscriptions(db)
    except Exception:
        logger.exception("Error in subscription renewal job.")
    finally:
        db.close()


def start_scheduler() -> None:
    _scheduler.add_job(_refresh_tokens_job, "interval", minutes=15, id="refresh_tokens")
    _scheduler.add_job(_renew_subscriptions_job, "interval", hours=2, id="renew_subscriptions")
    _scheduler.start()
    logger.info(
        "APScheduler started — jobs: refresh_tokens (every 15 min), "
        "renew_subscriptions (every 2 hr)."
    )


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
