"""Reusable data-quality checks for pandas DataFrames.

Each check returns a ``CheckResult`` that records which data-quality dimension it
belongs to, how many rows were checked, and which rows failed. Results can then be
summarised into a scorecard or used to pull out the failing records.

Dimensions follow common data-governance practice:
completeness, uniqueness, validity, consistency and timeliness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

import pandas as pd


@dataclass
class CheckResult:
    dimension: str
    rule: str
    columns: str
    rows_checked: int
    failed_index: list = field(default_factory=list)

    @property
    def rows_failed(self) -> int:
        return len(self.failed_index)

    @property
    def pass_rate(self) -> float:
        if self.rows_checked == 0:
            return 1.0
        return 1 - self.rows_failed / self.rows_checked

    @property
    def passed(self) -> bool:
        return self.rows_failed == 0


def _result(dimension: str, rule: str, columns, mask: pd.Series) -> CheckResult:
    cols = ", ".join(columns) if isinstance(columns, (list, tuple)) else columns
    return CheckResult(dimension, rule, cols, int(mask.size), list(mask[mask].index))


# --- Completeness -----------------------------------------------------------

def not_null(df: pd.DataFrame, column: str) -> CheckResult:
    """Every row has a value in ``column``."""
    return _result("Completeness", f"{column} is not null", column, df[column].isna())


# --- Uniqueness -------------------------------------------------------------

def unique(df: pd.DataFrame, columns: list[str]) -> CheckResult:
    """The combination of ``columns`` identifies each record once (a business key)."""
    mask = df.duplicated(subset=columns, keep="first")
    return _result("Uniqueness", f"({', '.join(columns)}) is unique", columns, mask)


# --- Validity ---------------------------------------------------------------

def in_range(df: pd.DataFrame, column: str, min_value=None, max_value=None) -> CheckResult:
    """Non-null values fall within ``[min_value, max_value]``."""
    values = df[column]
    mask = pd.Series(False, index=df.index)
    if min_value is not None:
        mask |= values < min_value
    if max_value is not None:
        mask |= values > max_value
    if min_value is not None and max_value is not None:
        rule = f"{column} between {min_value} and {max_value}"
    elif min_value is not None:
        rule = f"{column} >= {min_value}"
    else:
        rule = f"{column} <= {max_value}"
    return _result("Validity", rule, column, mask & values.notna())


def allowed_values(df: pd.DataFrame, column: str, allowed: Iterable) -> CheckResult:
    """Non-null values belong to a reference list (e.g. ISO country codes)."""
    allowed = set(allowed)
    mask = df[column].notna() & ~df[column].isin(allowed)
    return _result("Validity", f"{column} in reference list", column, mask)


def matches_pattern(df: pd.DataFrame, column: str, pattern: str, description: str) -> CheckResult:
    """Non-null values match a regular expression."""
    regex = re.compile(pattern)
    values = df[column].astype("string")
    mask = values.notna() & ~values.fillna("").str.fullmatch(regex)
    return _result("Validity", f"{column} format is {description}", column, mask.astype(bool))


def parses_as_date(df: pd.DataFrame, column: str) -> CheckResult:
    """Non-null values can be read as a date."""
    parsed = pd.to_datetime(df[column], errors="coerce", format="%Y-%m-%d")
    mask = df[column].notna() & parsed.isna()
    return _result("Validity", f"{column} is a valid date", column, mask)


# --- Consistency ------------------------------------------------------------

def consistent(
    df: pd.DataFrame,
    rule: str,
    columns: list[str],
    predicate: Callable[[pd.DataFrame], pd.Series],
) -> CheckResult:
    """A cross-field rule holds. ``predicate`` returns True for rows that are consistent.

    Rows with nulls in any of ``columns`` are skipped (completeness checks cover them).
    """
    complete = df[columns].notna().all(axis=1)
    ok = predicate(df).fillna(False).astype(bool)
    return _result("Consistency", rule, columns, complete & ~ok)


# --- Timeliness -------------------------------------------------------------

def not_in_future(df: pd.DataFrame, column: str, as_of: str) -> CheckResult:
    """Dates are not later than the ``as_of`` date."""
    parsed = pd.to_datetime(df[column], errors="coerce", format="%Y-%m-%d")
    mask = parsed > pd.Timestamp(as_of)
    return _result("Timeliness", f"{column} not after {as_of}", column, mask.fillna(False))


# --- Reporting --------------------------------------------------------------

def scorecard(results: list[CheckResult]) -> pd.DataFrame:
    """One row per rule with counts and pass rate."""
    return pd.DataFrame(
        {
            "dimension": r.dimension,
            "rule": r.rule,
            "columns": r.columns,
            "rows_checked": r.rows_checked,
            "rows_failed": r.rows_failed,
            "pass_rate": round(r.pass_rate, 4),
            "status": "PASS" if r.passed else "FAIL",
        }
        for r in results
    )


def dimension_scores(results: list[CheckResult]) -> pd.DataFrame:
    """Average pass rate for each data-quality dimension."""
    card = scorecard(results)
    return (
        card.groupby("dimension", as_index=False)
        .agg(rules=("rule", "count"), rules_failed=("status", lambda s: (s == "FAIL").sum()), pass_rate=("pass_rate", "mean"))
        .sort_values("pass_rate")
        .reset_index(drop=True)
    )


def failing_rows(df: pd.DataFrame, results: list[CheckResult]) -> pd.DataFrame:
    """Every failing record, with the rules it broke listed in one column."""
    issues: dict = {}
    for r in results:
        for idx in r.failed_index:
            issues.setdefault(idx, []).append(r.rule)
    if not issues:
        return df.iloc[0:0].assign(issues="")
    out = df.loc[list(issues)].copy()
    out.insert(0, "issues", ["; ".join(issues[i]) for i in out.index])
    return out.sort_index()
