# =============================================================================
# data/qvd_loader.py
# Phase 1 - Step 1: QVD Reader and DataFrame Loader
# =============================================================================
# Responsibilities:
#   - Load configuration from config.yaml
#   - Generate dummy claims data (when no QVD files available)
#   - Read real QVD files via pyqvd (when available)
#   - Apply smart loading strategy (recent data, chunking, aggregates)
#   - Expose a clean DataFrame to the rest of the app
# =============================================================================

import os
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Logging setup - all modules use the same logger name "claims"
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("claims.data")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config/config.yaml") -> dict:
    """
    Load the central YAML configuration file.

    Args:
        config_path: Relative or absolute path to config.yaml

    Returns:
        Dictionary of all configuration values.

    Raises:
        FileNotFoundError: If the config file cannot be found.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at: {path.resolve()}")

    with open(path, "r") as f:
        config = yaml.safe_load(f)

    logger.info(f"Config loaded from {path.resolve()}")
    return config


# ---------------------------------------------------------------------------
# Dummy data generator
# ---------------------------------------------------------------------------

def generate_dummy_data(n_rows: int, col_map: dict) -> pd.DataFrame:
    """
    Generate realistic-looking dummy insurance claims data for development
    and testing. No real data required.

    Args:
        n_rows:   Number of rows to generate.
        col_map:  Column name mapping from config (so column names match config).

    Returns:
        A Pandas DataFrame with dummy claims data.
    """
    logger.info(f"Generating {n_rows:,} rows of dummy claims data...")

    random.seed(42)
    np.random.seed(42)

    # --- Reference data pools ---
    statuses      = ["Open", "Closed", "Pending", "Rejected", "Under Review"]
    status_weights = [0.35, 0.40, 0.12, 0.08, 0.05]   # realistic distribution

    claim_types   = ["Medical", "Property", "Liability", "Motor", "Life", "Travel"]
    type_weights  = [0.30, 0.25, 0.20, 0.15, 0.06, 0.04]

    regions       = ["London", "North West", "South East", "Midlands",
                     "Scotland", "Wales"]

    first_names   = ["James", "Sarah", "Mohammed", "Emily", "David",
                     "Priya", "John", "Laura", "Ahmed", "Claire"]
    last_names    = ["Smith", "Jones", "Patel", "Williams", "Brown",
                     "Taylor", "Davies", "Wilson", "Evans", "Thomas"]

    # --- Date range: last 3 years ---
    end_date   = datetime.today()
    start_date = end_date - timedelta(days=3 * 365)

    def rand_date(start, end):
        delta = (end - start).days
        return start + timedelta(days=random.randint(0, delta))

    submitted_dates = [rand_date(start_date, end_date) for _ in range(n_rows)]

    # Closed date: only for Closed/Rejected rows, otherwise NaT
    statuses_col = random.choices(statuses, weights=status_weights, k=n_rows)
    closed_dates = [
        (sd + timedelta(days=random.randint(1, 365)))
        if s in ("Closed", "Rejected") else pd.NaT
        for sd, s in zip(submitted_dates, statuses_col)
    ]

    # Days open
    today = datetime.today()
    days_open = [
        (cd - sd).days if pd.notna(cd) else (today - sd).days
        for sd, cd in zip(submitted_dates, closed_dates)
    ]

    # Financial figures - lognormal gives realistic skew (lots of small, few huge)
    claim_amounts   = np.round(np.random.lognormal(mean=10.5, sigma=1.2, size=n_rows), 2)
    paid_amounts    = np.where(
        np.array(statuses_col) == "Closed",
        np.round(claim_amounts * np.random.uniform(0.5, 1.0, n_rows), 2),
        0.0,
    )
    reserve_amounts = np.where(
        np.array(statuses_col) == "Open",
        np.round(claim_amounts * np.random.uniform(0.6, 1.0, n_rows), 2),
        0.0,
    )

    # --- Build DataFrame with config-defined column names ---
    df = pd.DataFrame({
        col_map["claim_id"]:       [f"CLM{str(i+1).zfill(7)}" for i in range(n_rows)],
        col_map["status"]:         statuses_col,
        col_map["claim_type"]:     random.choices(claim_types, weights=type_weights, k=n_rows),
        col_map["submitted_date"]: submitted_dates,
        col_map["closed_date"]:    closed_dates,
        col_map["region"]:         random.choices(regions, k=n_rows),
        col_map["claimant_name"]:  [
            f"{random.choice(first_names)} {random.choice(last_names)}"
            for _ in range(n_rows)
        ],
        col_map["claim_amount"]:   claim_amounts,
        col_map["paid_amount"]:    paid_amounts,
        col_map["reserve_amount"]: reserve_amounts,
        col_map["days_open"]:      days_open,
    })

    # Ensure date columns are proper datetime dtype
    df[col_map["submitted_date"]] = pd.to_datetime(df[col_map["submitted_date"]])
    df[col_map["closed_date"]]    = pd.to_datetime(df[col_map["closed_date"]])

    logger.info(f"Dummy data generated. Shape: {df.shape}")
    return df


# ---------------------------------------------------------------------------
# Real QVD loader
# ---------------------------------------------------------------------------

def load_qvd_file(file_path: str, col_map: dict, recent_months: int) -> pd.DataFrame:
    """
    Load a single QVD file using pyqvd and apply date filtering to avoid
    loading all 20M rows at once.

    Args:
        file_path:     Full path to the .qvd file.
        col_map:       Column name mapping from config.
        recent_months: Only load rows from the last N months.

    Returns:
        A filtered Pandas DataFrame.

    Raises:
        ImportError:  If pyqvd is not installed.
        FileNotFoundError: If the QVD file doesn't exist.
    """
    try:
        from pyqvd import QvdDataFrame          # only imported when needed
    except ImportError:
        raise ImportError(
            "pyqvd is not installed. Run: pip install pyqvd\n"
            "Or set dummy_mode: true in config.yaml to use generated data."
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"QVD file not found: {path.resolve()}")

    logger.info(f"Reading QVD file: {path.name}")
    qvd = QvdDataFrame.from_qvd(str(path))
    df  = qvd.to_pandas()
    logger.info(f"QVD loaded raw shape: {df.shape}")

    # Apply date filter to keep memory usage down
    df = apply_date_filter(df, col_map, recent_months)
    return df


def load_all_qvd_files(qvd_folder: str, col_map: dict, recent_months: int) -> pd.DataFrame:
    """
    Load and combine all .qvd files found in the specified folder.

    Args:
        qvd_folder:    Path to the folder containing QVD files.
        col_map:       Column name mapping from config.
        recent_months: Date window filter to apply to each file.

    Returns:
        A single combined DataFrame from all QVD files.
    """
    folder = Path(qvd_folder)
    qvd_files = list(folder.glob("*.qvd"))

    if not qvd_files:
        raise FileNotFoundError(f"No .qvd files found in: {folder.resolve()}")

    logger.info(f"Found {len(qvd_files)} QVD file(s) in {qvd_folder}")

    frames = []
    for qvd_file in qvd_files:
        try:
            df = load_qvd_file(str(qvd_file), col_map, recent_months)
            frames.append(df)
        except Exception as e:
            logger.error(f"Failed to load {qvd_file.name}: {e}")

    if not frames:
        raise RuntimeError("No QVD files could be loaded successfully.")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"All QVD files combined. Total shape: {combined.shape}")
    return combined


# ---------------------------------------------------------------------------
# Smart loading helpers
# ---------------------------------------------------------------------------

def apply_date_filter(df: pd.DataFrame, col_map: dict, recent_months: int) -> pd.DataFrame:
    """
    Filter the DataFrame to only include claims submitted within the last
    N months. This is the primary memory-saving strategy.

    Args:
        df:            Input DataFrame.
        col_map:       Column name mapping from config.
        recent_months: Number of months to look back.

    Returns:
        Date-filtered DataFrame.
    """
    date_col = col_map["submitted_date"]

    if date_col not in df.columns:
        logger.warning(f"Date column '{date_col}' not found. Skipping date filter.")
        return df

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    cutoff = datetime.today() - timedelta(days=recent_months * 30)
    filtered = df[df[date_col] >= cutoff].copy()

    logger.info(
        f"Date filter applied (last {recent_months} months). "
        f"Rows before: {len(df):,}  After: {len(filtered):,}"
    )
    return filtered


def build_aggregated_summary(df: pd.DataFrame, col_map: dict) -> dict:
    """
    Compute high-level summary statistics that are always kept in memory.
    These power quick answers without scanning the full DataFrame.

    Args:
        df:      The loaded claims DataFrame.
        col_map: Column name mapping from config.

    Returns:
        Dictionary of summary metrics.
    """
    c = col_map   # shorthand

    summary = {
        "total_claims":          len(df),
        "status_counts":         df[c["status"]].value_counts().to_dict(),
        "type_counts":           df[c["claim_type"]].value_counts().to_dict(),
        "region_counts":         df[c["region"]].value_counts().to_dict(),
        "total_claim_amount":    round(df[c["claim_amount"]].sum(), 2),
        "total_paid_amount":     round(df[c["paid_amount"]].sum(), 2),
        "total_reserve_amount":  round(df[c["reserve_amount"]].sum(), 2),
        "avg_claim_amount":      round(df[c["claim_amount"]].mean(), 2),
        "avg_days_open":         round(df[c["days_open"]].mean(), 1),
        "max_claim_amount":      round(df[c["claim_amount"]].max(), 2),
        "oldest_open_days":      int(df[df[c["status"]] == "Open"][c["days_open"]].max())
                                 if "Open" in df[c["status"]].values else 0,
        "data_loaded_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_range_start":      str(df[c["submitted_date"]].min().date()),
        "date_range_end":        str(df[c["submitted_date"]].max().date()),
    }

    logger.info(
        f"Summary built: {summary['total_claims']:,} claims, "
        f"£{summary['total_claim_amount']:,.0f} total value"
    )
    return summary


# ---------------------------------------------------------------------------
# Main ClaimsDataLoader class
# ---------------------------------------------------------------------------

class ClaimsDataLoader:
    """
    Central data access object for the Claims ChatGPT system.

    Usage:
        loader = ClaimsDataLoader()
        loader.load()

        df      = loader.df           # Full working DataFrame
        summary = loader.summary      # Pre-computed summary stats
        col     = loader.col          # Column name mapping shorthand
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialise the loader by reading configuration.

        Args:
            config_path: Path to the YAML config file.
        """
        self.config     = load_config(config_path)
        self.col        = self.config["columns"]          # column name map
        self.data_cfg   = self.config["data"]             # data settings
        self.df = None               # type: pd.DataFrame
        self.summary = None          # type: dict
        self._loaded_at = None       # type: datetime

    # ------------------------------------------------------------------
    def load(self) -> pd.DataFrame:
        """
        Main entry point. Loads data from either dummy generator or QVD files
        depending on config setting, then builds the summary.

        Returns:
            The loaded DataFrame (also stored as self.df).
        """
        if self.data_cfg.get("dummy_mode", True):
            logger.info("dummy_mode is ON — generating synthetic data")
            self.df = generate_dummy_data(
                n_rows  = self.data_cfg["dummy_row_count"],
                col_map = self.col,
            )
        else:
            logger.info("dummy_mode is OFF — reading QVD files")
            self.df = load_all_qvd_files(
                qvd_folder    = self.data_cfg["qvd_folder"],
                col_map       = self.col,
                recent_months = self.data_cfg["recent_months"],
            )

        # Enforce hard row cap for safety
        max_rows = self.data_cfg.get("max_rows_in_memory", 500_000)
        if len(self.df) > max_rows:
            logger.warning(
                f"DataFrame has {len(self.df):,} rows — capping at {max_rows:,} "
                f"to protect memory. Adjust max_rows_in_memory in config if needed."
            )
            self.df = self.df.tail(max_rows).reset_index(drop=True)

        self.summary    = build_aggregated_summary(self.df, self.col)
        self._loaded_at = datetime.now()

        logger.info("Data load complete ✓")
        return self.df

    # ------------------------------------------------------------------
    def reload(self) -> pd.DataFrame:
        """
        Force a full reload of the data. Useful for manual refresh commands
        or the scheduled nightly refresh.

        Returns:
            Freshly loaded DataFrame.
        """
        logger.info("Reload triggered — clearing existing data")
        self.df      = None
        self.summary = None
        return self.load()

    # ------------------------------------------------------------------
    def get_subset(self, status=None, region=None, claim_type=None):
        """
        Return a filtered subset of the DataFrame on demand.
        Used by the RAG pipeline to narrow context for specific questions.

        Args:
            status:     Filter by claim status (e.g. "Open").
            region:     Filter by region (e.g. "London").
            claim_type: Filter by claim type (e.g. "Medical").

        Returns:
            Filtered DataFrame (does not modify self.df).

        Raises:
            RuntimeError: If data hasn't been loaded yet.
        """
        if self.df is None:
            raise RuntimeError("Data not loaded. Call loader.load() first.")

        subset = self.df.copy()

        if status:
            subset = subset[subset[self.col["status"]].str.lower() == status.lower()]
        if region:
            subset = subset[subset[self.col["region"]].str.lower() == region.lower()]
        if claim_type:
            subset = subset[subset[self.col["claim_type"]].str.lower() == claim_type.lower()]

        logger.debug(
            f"Subset returned: status={status}, region={region}, "
            f"type={claim_type}. Rows: {len(subset):,}"
        )
        return subset

    # ------------------------------------------------------------------
    @property
    def last_loaded(self) -> str:
        """Human-readable timestamp of when data was last loaded."""
        if self._loaded_at is None:
            return "Not loaded yet"
        return self._loaded_at.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        rows = len(self.df) if self.df is not None else 0
        return f"<ClaimsDataLoader rows={rows:,} loaded_at='{self.last_loaded}'>"
