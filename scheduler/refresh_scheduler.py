# =============================================================================
# scheduler/refresh_scheduler.py
# Scheduled data refresh + notification checks
# =============================================================================

import logging
import threading
import time

import schedule

from notifications.rules_engine import run_all_checks
from notifications.teams_notify import send_daily_summary

logger = logging.getLogger("claims.scheduler")


class ClaimsScheduler:
    """
    Runs periodic data refresh and notification checks using the
    ``schedule`` library in a background daemon thread.
    """

    def __init__(self, pipeline, config):
        """
        Args:
            pipeline: Initialised RAGPipeline instance (must expose
                      .rebuild(), .loader, and .loader.df attributes).
            config: Full application config dict.
        """
        self.pipeline = pipeline
        self.config = config
        self._thread = None
        self._stop_event = threading.Event()
        self._already_alerted = set()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start(self):
        """Schedule jobs and start the background loop."""
        sched_cfg = self.config.get("scheduler", {})
        refresh_time = sched_cfg.get("refresh_time", "06:45")
        summary_time = sched_cfg.get("daily_summary_time", "07:00")

        schedule.every().day.at(refresh_time).do(self._run_refresh)
        schedule.every().day.at(summary_time).do(self._run_daily_summary)

        logger.info(
            f"Scheduler started -- refresh at {refresh_time}, "
            f"summary at {summary_time}"
        )

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the background loop to stop."""
        self._stop_event.set()
        schedule.clear()
        logger.info("Scheduler stopped.")

    # ------------------------------------------------------------------ #
    # Scheduled jobs
    # ------------------------------------------------------------------ #

    def _run_refresh(self):
        """Rebuild pipeline data and run notification rule checks."""
        try:
            logger.info("Scheduled data refresh starting...")
            self.pipeline.rebuild()
            logger.info("Data refresh complete.")

            # Run notification checks on the refreshed data
            df = getattr(self.pipeline.loader, "df", None)
            if df is not None:
                col_map = self.config.get("columns", {})
                self._already_alerted = run_all_checks(
                    df, col_map, self.config, self._already_alerted
                )
        except Exception as e:
            logger.error(f"Scheduled refresh failed: {e}")

    def _run_daily_summary(self):
        """Build and send the daily summary card."""
        try:
            webhook = self.config.get("notifications", {}).get("teams_webhook_url", "")
            df = getattr(self.pipeline.loader, "df", None)
            if df is None:
                logger.warning("No DataFrame available for daily summary.")
                return

            col = self.config.get("columns", {})
            status_col = col.get("status", col.get("claim_status_derived", "Claim Status Derived"))
            amount_col = col.get("claim_amount", col.get("incurred_usd", "Incurred USD"))

            total = len(df)
            open_claims = 0
            if status_col in df.columns:
                open_claims = df[df[status_col].str.lower().str.contains("open", na=False)].shape[0]

            total_incurred = 0
            if amount_col in df.columns:
                total_incurred = df[amount_col].sum()

            hv_thresh = self.config.get("notifications", {}).get("high_value_claim_threshold", 100000)
            hv_count = 0
            if amount_col in df.columns:
                hv_count = int((df[amount_col] > hv_thresh).sum())

            summary = {
                "total_claims": total,
                "open_claims": open_claims,
                "closed_today": "N/A",
                "high_value_count": hv_count,
                "total_incurred": total_incurred,
            }

            send_daily_summary(webhook, summary)
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")

    # ------------------------------------------------------------------ #
    # Background loop
    # ------------------------------------------------------------------ #

    def _loop(self):
        """Check for pending jobs every 30 seconds."""
        while not self._stop_event.is_set():
            schedule.run_pending()
            self._stop_event.wait(30)
