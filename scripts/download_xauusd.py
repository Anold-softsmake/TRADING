from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
YAHOO_SYMBOLS = ("XAUUSD=X", "GC=F")


def fetch_yahoo_ohlc(symbol: str, interval: str = "15m", range_value: str = "60d") -> pd.DataFrame:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={range_value}&includePrePost=false"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None),
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
        }
    ).dropna()
    return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    resampled = (
        df.set_index("timestamp")
        .resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
        .reset_index()
    )
    return resampled


def download_xauusd(data_dir: Path = DATA_DIR) -> dict[str, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    m15 = None
    used_symbol = None
    for symbol in YAHOO_SYMBOLS:
        try:
            m15 = fetch_yahoo_ohlc(symbol)
            if len(m15) >= 200:
                used_symbol = symbol
                break
        except Exception as exc:  # noqa: BLE001 - try the next public symbol
            last_error = exc
    if m15 is None or used_symbol is None:
        raise RuntimeError(f"Could not download XAUUSD history from Yahoo Finance: {last_error}")

    h1 = resample_ohlc(m15, "1h")
    h4 = resample_ohlc(m15, "4h")
    paths = {
        "m15": data_dir / "xauusd_m15.csv",
        "h1": data_dir / "xauusd_h1.csv",
        "h4": data_dir / "xauusd_h4.csv",
    }
    m15.to_csv(paths["m15"], index=False)
    h1.to_csv(paths["h1"], index=False)
    h4.to_csv(paths["h4"], index=False)
    print(f"source: {used_symbol}")
    print(f"m15 bars: {len(m15)}  {m15['timestamp'].min()} -> {m15['timestamp'].max()}")
    print(f"h1 bars: {len(h1)}")
    print(f"h4 bars: {len(h4)}")
    return paths


if __name__ == "__main__":
    download_xauusd()
