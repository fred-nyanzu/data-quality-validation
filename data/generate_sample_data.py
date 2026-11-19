"""Generate a synthetic quarterly economic-indicators dataset with known data-quality issues.

All values are synthetic and for demonstration only. Issues are injected on purpose
so the validation notebook has something realistic to find.

Usage:
    python data/generate_sample_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
OUTPUT = Path(__file__).parent / "economic_indicators.csv"

COUNTRIES = {
    "GHA": ("Ghana", 33.5, 76.0),
    "NGA": ("Nigeria", 223.0, 470.0),
    "KEN": ("Kenya", 55.0, 110.0),
    "ZAF": ("South Africa", 60.0, 380.0),
    "USA": ("United States", 335.0, 27000.0),
    "GBR": ("United Kingdom", 68.0, 3300.0),
    "DEU": ("Germany", 84.0, 4400.0),
    "IND": ("India", 1430.0, 3700.0),
    "BRA": ("Brazil", 216.0, 2200.0),
    "CAN": ("Canada", 40.0, 2100.0),
}
QUARTERS = [f"{year}-Q{q}" for year in range(2020, 2026) for q in range(1, 5)]


def build_clean(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for code, (name, pop_m, gdp_bn) in COUNTRIES.items():
        for i, quarter in enumerate(QUARTERS):
            growth = 1 + 0.006 * i + rng.normal(0, 0.01)
            gdp = round(gdp_bn / 4 * growth, 2)  # quarterly GDP, USD billions
            pop = round(pop_m * (1 + 0.003 * i), 2)
            year, q = int(quarter[:4]), int(quarter[-1])
            quarter_end = pd.Timestamp(year=year, month=q * 3, day=1) + pd.offsets.MonthEnd(0)
            rows.append(
                {
                    "country_code": code,
                    "country_name": name,
                    "quarter": quarter,
                    "gdp_usd_bn": gdp,
                    "population_m": pop,
                    "gdp_per_capita_usd": round(gdp * 1e9 / (pop * 1e6), 2),
                    "inflation_rate_pct": round(rng.normal(6, 4), 2),
                    "unemployment_rate_pct": round(abs(rng.normal(7, 3)), 2),
                    "last_updated": (quarter_end + pd.Timedelta(days=int(rng.integers(30, 60)))).date(),
                    "source": rng.choice(["National Statistics Office", "Central Bank"]),
                }
            )
    return pd.DataFrame(rows)


def inject_issues(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    pick = lambda k: rng.choice(n, size=k, replace=False)  # noqa: E731

    df["last_updated"] = df["last_updated"].astype(str)
    df.loc[pick(8), "gdp_usd_bn"] = np.nan                   # completeness
    df.loc[pick(6), "unemployment_rate_pct"] = np.nan        # completeness
    df.loc[pick(3), "source"] = None                         # completeness
    df.loc[pick(4), "gdp_usd_bn"] *= -1                      # validity: negative GDP
    df.loc[pick(3), "unemployment_rate_pct"] = 120.0         # validity: impossible rate
    df.loc[pick(3), "country_code"] = "XXX"                  # validity: unknown code
    df.loc[pick(4), "quarter"] = "2023Q5"                    # validity: bad format
    bad_ratio = pick(5)
    df.loc[bad_ratio, "gdp_per_capita_usd"] *= 10           # consistency: wrong derived value
    df.loc[pick(3), "last_updated"] = "2031-01-01"           # timeliness: date in the future
    df.loc[pick(4), "last_updated"] = "not available"        # validity: unparseable date

    duplicates = df.sample(5, random_state=SEED)             # uniqueness: repeated records
    return pd.concat([df, duplicates], ignore_index=True)


def main() -> None:
    rng = np.random.default_rng(SEED)
    df = inject_issues(build_clean(rng), rng)
    df.insert(0, "record_id", range(1, len(df) + 1))
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
