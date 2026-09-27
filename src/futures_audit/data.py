from __future__ import annotations

import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import random
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


CFFEX_MONTH_URL = "http://www.cffex.com.cn/sj/historysj/{month}/zip/{month}.zip"
SHFE_DAY_URL = "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{date}.dat?params=1"
METADATA_URLS = {
    "CFFEX_IF_SPEC": "http://www.cffex.com.cn/cn/hs300.html",
    "CFFEX_TF_SPEC": "http://www.cffex.com.cn/cn/5tf.html",
    "CFFEX_T_SPEC": "http://www.cffex.com.cn/cn/10t.html",
}
METADATA_MARKERS = {
    "CFFEX_IF_SPEC": ("沪深300股指期货", "合约乘数", "IF"),
    "CFFEX_TF_SPEC": ("5年期国债期货", "100万元", "TF"),
    "CFFEX_T_SPEC": ("10年期国债期货", "100万元", "交易代码"),
}
USER_AGENT = "futures-strategy-audit/0.1 (+public research; no credentials)"


@dataclass(frozen=True)
class SourceRecord:
    provider: str
    requested_url: str
    retrieved_at_utc: str
    sha256: str
    byte_count: int
    status: str
    observation_date: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fetch(url: str, referer: str, attempts: int = 5, timeout: int = 90) -> tuple[bytes | None, str]:
    headers = {"User-Agent": USER_AGENT, "Referer": referer, "Accept": "*/*"}
    last_error = "unattempted"
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                return payload, "ok"
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, "http_404"
            last_error = f"http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            time.sleep(min(8.0, (2**attempt) + random.random()))
    return None, f"failed_{last_error}"


def _month_range(start: dt.date, end: dt.date) -> list[str]:
    cursor = start.replace(day=1)
    months: list[str] = []
    while cursor <= end:
        months.append(cursor.strftime("%Y%m"))
        cursor = (cursor.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return months


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    return [
        start + dt.timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + dt.timedelta(days=offset)).weekday() < 5
    ]


def _source_record(provider: str, url: str, observed: str, payload: bytes | None, status: str) -> SourceRecord:
    return SourceRecord(
        provider=provider,
        requested_url=url,
        retrieved_at_utc=dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        sha256=_sha256(payload) if payload is not None else "",
        byte_count=len(payload) if payload is not None else 0,
        status=status,
        observation_date=observed,
    )


def _parse_cffex_month(payload: bytes, requested_month: str) -> tuple[list[dict], set[str]]:
    rows: list[dict] = []
    dates: set[str] = set()
    contract_pattern = re.compile(r"^(IF|TF|T)(\d{4})$")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            match_date = re.fullmatch(r"(\d{8})_1\.csv", Path(info.filename).name)
            if not match_date:
                continue
            date_text = match_date.group(1)
            if not date_text.startswith(requested_month):
                raise ValueError(f"CFFEX archive contains out-of-month entry {info.filename}")
            text = archive.read(info).decode("gb18030")
            reader = csv.DictReader(io.StringIO(text))
            expected = {"合约代码", "今开盘", "最高价", "最低价", "成交量", "持仓量", "今收盘", "今结算", "前结算"}
            if not expected.issubset(set(reader.fieldnames or [])):
                raise ValueError(f"CFFEX schema mismatch in {info.filename}")
            day_has_target = False
            for raw in reader:
                code = (raw.get("合约代码") or "").strip()
                match = contract_pattern.fullmatch(code)
                if not match:
                    continue
                values = {key: raw.get(key, "") for key in expected}
                if any(values[key] in {"", "null", "--"} for key in ("今开盘", "最高价", "最低价", "今收盘", "今结算")):
                    continue
                rows.append(
                    {
                        "date": pd.Timestamp(date_text),
                        "exchange": "CFFEX",
                        "root": match.group(1),
                        "contract": code,
                        "delivery_month": match.group(2),
                        "open": float(values["今开盘"]),
                        "high": float(values["最高价"]),
                        "low": float(values["最低价"]),
                        "close": float(values["今收盘"]),
                        "settle": float(values["今结算"]),
                        "pre_settle": float(values["前结算"]),
                        "volume": int(float(values["成交量"])),
                        "open_interest": int(float(values["持仓量"])),
                    }
                )
                day_has_target = True
            if day_has_target:
                dates.add(pd.Timestamp(date_text).date().isoformat())
    if not rows:
        raise ValueError(f"No IF/TF/T delivery contracts in CFFEX {requested_month}")
    return rows, dates


def _parse_shfe_day(payload: bytes, requested_date: dt.date) -> tuple[list[dict], str]:
    document = json.loads(payload.decode("utf-8"))
    trade_day = str(
        document.get("report_date")
        or f"{document.get('o_year', '')}{document.get('o_month', '')}{document.get('o_day', '')}"
        or document.get("o_trade_day")
        or ""
    ).replace("-", "")
    expected = requested_date.strftime("%Y%m%d")
    if trade_day and trade_day != expected:
        raise ValueError(f"SHFE trade day {trade_day} does not match request {expected}")
    raw_rows = document.get("o_curinstrument")
    if not isinstance(raw_rows, list):
        raise ValueError("SHFE schema missing o_curinstrument")
    rows: list[dict] = []
    for raw in raw_rows:
        root = str(raw.get("PRODUCTGROUPID", "")).upper()
        month = str(raw.get("DELIVERYMONTH", ""))
        if root not in {"CU", "RB"} or not re.fullmatch(r"\d{4}", month):
            continue
        required = ["OPENPRICE", "HIGHESTPRICE", "LOWESTPRICE", "CLOSEPRICE", "SETTLEMENTPRICE"]
        if any(raw.get(key) in {"", None} for key in required):
            continue
        rows.append(
            {
                "date": pd.Timestamp(requested_date),
                "exchange": "SHFE",
                "root": root,
                "contract": f"{root}{month}",
                "delivery_month": month,
                "open": float(raw["OPENPRICE"]),
                "high": float(raw["HIGHESTPRICE"]),
                "low": float(raw["LOWESTPRICE"]),
                "close": float(raw["CLOSEPRICE"]),
                "settle": float(raw["SETTLEMENTPRICE"]),
                "pre_settle": float(raw["PRESETTLEMENTPRICE"]),
                "volume": int(float(raw["VOLUME"])),
                "open_interest": int(float(raw["OPENINTEREST"])),
            }
        )
    if not rows:
        raise ValueError(f"No CU/RB delivery contracts in SHFE {expected}")
    return rows, requested_date.isoformat()


def acquire_exchange_data(start: dt.date, end: dt.date, raw_dir: Path, workers: int) -> tuple[pd.DataFrame, dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    cffex_dir = raw_dir / "cffex"
    shfe_dir = raw_dir / "shfe"
    cffex_dir.mkdir(exist_ok=True)
    shfe_dir.mkdir(exist_ok=True)
    records: list[SourceRecord] = []
    all_rows: list[dict] = []
    cffex_dates: set[str] = set()
    shfe_dates: set[str] = set()

    def fetch_cffex(month: str) -> tuple[str, bytes | None, str, str]:
        url = CFFEX_MONTH_URL.format(month=month)
        cache = cffex_dir / f"{month}.zip"
        if cache.exists():
            return month, cache.read_bytes(), "cache", url
        payload, status = _fetch(url, "http://www.cffex.com.cn/cn/lssjxz.html")
        if payload is not None:
            cache.write_bytes(payload)
        return month, payload, status, url

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, 4)) as pool:
        futures = [pool.submit(fetch_cffex, month) for month in _month_range(start, end)]
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            month, payload, status, url = future.result()
            records.append(_source_record("CFFEX", url, month, payload, status))
            if payload is None:
                raise RuntimeError(f"CFFEX required month unavailable: {month} ({status})")
            rows, dates = _parse_cffex_month(payload, month)
            all_rows.extend(rows)
            cffex_dates.update(dates)
            print(f"CFFEX month {month}: {status}, {len(rows)} target rows ({completed}/{len(futures)})", flush=True)

    def fetch_shfe(day: dt.date) -> tuple[dt.date, bytes | None, str, str]:
        date_text = day.strftime("%Y%m%d")
        url = SHFE_DAY_URL.format(date=date_text)
        cache = shfe_dir / f"{date_text}.json"
        missing = shfe_dir / f"{date_text}.missing"
        if cache.exists():
            return day, cache.read_bytes(), "cache", url
        if missing.exists():
            return day, None, "http_404", url
        payload, status = _fetch(url, "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/")
        if payload is not None:
            cache.write_bytes(payload)
        elif status == "http_404":
            missing.write_text("official HTTP 404\n", encoding="utf-8")
        return day, payload, status, url

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_shfe, day) for day in _weekdays(start, end)]
        successful_shfe = 0
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            day, payload, status, url = future.result()
            records.append(_source_record("SHFE", url, day.isoformat(), payload, status))
            if payload is None:
                continue
            rows, observed = _parse_shfe_day(payload, day)
            all_rows.extend(rows)
            shfe_dates.add(observed)
            successful_shfe += 1
            if completed % 25 == 0 or completed == len(futures):
                print(
                    f"SHFE weekdays checked {completed}/{len(futures)}; successful trading days {successful_shfe}",
                    flush=True,
                )

    frame = pd.DataFrame(all_rows)
    frame = frame[(frame["date"].dt.date >= start) & (frame["date"].dt.date <= end)].copy()
    frame.sort_values(["date", "root", "contract"], inplace=True)
    duplicates = int(frame.duplicated(["date", "contract"]).sum())
    if duplicates:
        raise ValueError(f"Duplicate normalized contract rows: {duplicates}")

    common_dates = cffex_dates & shfe_dates
    only_cffex = sorted(cffex_dates - shfe_dates)
    only_shfe = sorted(shfe_dates - cffex_dates)
    if not common_dates:
        raise RuntimeError("CFFEX and SHFE have no common observed trading dates")
    interior_end = min(max(cffex_dates), max(shfe_dates))
    unexplained_cffex = [value for value in only_cffex if start.isoformat() <= value <= interior_end]
    unexplained_shfe = [value for value in only_shfe if start.isoformat() <= value <= interior_end]
    if unexplained_cffex or unexplained_shfe:
        raise RuntimeError(
            "Exchange calendar mismatch inside shared coverage: "
            f"CFFEX-only={unexplained_cffex[:10]}, SHFE-only={unexplained_shfe[:10]}"
        )
    metadata_summary: dict[str, object] = {}
    metadata_dir = raw_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)
    for name, url in METADATA_URLS.items():
        cache = metadata_dir / f"{name}.html"
        if cache.exists():
            payload, status = cache.read_bytes(), "cache"
        else:
            payload, status = _fetch(url, "http://www.cffex.com.cn/cp/")
            if payload is not None:
                cache.write_bytes(payload)
        records.append(_source_record(name, url, max(common_dates), payload, status))
        if payload is None or len(payload) < 10000:
            raise RuntimeError(f"Required CFFEX contract specification unavailable: {name} ({status})")
        decoded = payload.decode("utf-8")
        missing_markers = [marker for marker in METADATA_MARKERS[name] if marker not in decoded]
        if missing_markers:
            raise ValueError(f"CFFEX contract specification {name} missing expected fields: {missing_markers}")
        metadata_summary[name] = {"byte_count": len(payload), "sha256": _sha256(payload)}

    latest_text = max(common_dates).replace("-", "")
    shfe_metadata_urls = {
        "SHFE_CONTRACT_BASE": f"https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo{latest_text}.dat?params=1",
        "SHFE_TRADING_ARGUMENTS": f"https://www.shfe.com.cn/data/busiparamdata/future/ContractDailyTradeArgument{latest_text}.dat?params=1",
    }
    parsed_metadata: dict[str, dict] = {}
    for name, url in shfe_metadata_urls.items():
        cache = metadata_dir / f"{name}-{latest_text}.json"
        if cache.exists():
            payload, status = cache.read_bytes(), "cache"
        else:
            payload, status = _fetch(url, "https://www.shfe.com.cn/reports/businessdata/prmsummary/")
            if payload is not None:
                cache.write_bytes(payload)
        records.append(_source_record(name, url, max(common_dates), payload, status))
        if payload is None:
            raise RuntimeError(f"Required SHFE contract metadata unavailable: {name} ({status})")
        document = json.loads(payload.decode("utf-8"))
        array_key = "ContractBaseInfo" if name == "SHFE_CONTRACT_BASE" else "ContractDailyTradeArgument"
        entries = document.get(array_key)
        if not isinstance(entries, list):
            raise ValueError(f"SHFE metadata schema missing {array_key}")
        selected = [
            row for row in entries
            if str(row.get("INSTRUMENTID", "")).lower().startswith(("cu", "rb"))
        ]
        if not selected:
            raise ValueError(f"SHFE metadata has no CU/RB rows in {array_key}")
        parsed_metadata[name] = {
            "row_count": len(entries),
            "cu_rb_row_count": len(selected),
            "report_date": str(document.get("report_date", "")),
            "sha256": _sha256(payload),
        }
    metadata_summary.update(parsed_metadata)
    manifest = {
        "generated_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "normalized_rows": int(len(frame)),
        "contract_count": int(frame["contract"].nunique()),
        "coverage": {
            "CFFEX": {"start": min(cffex_dates), "end": max(cffex_dates), "trading_days": len(cffex_dates)},
            "SHFE": {"start": min(shfe_dates), "end": max(shfe_dates), "trading_days": len(shfe_dates)},
            "common": {"start": min(common_dates), "end": max(common_dates), "trading_days": len(common_dates)},
        },
        "calendar_gaps": {"CFFEX_only": only_cffex, "SHFE_only": only_shfe},
        "contract_metadata": metadata_summary,
        "sources": [asdict(record) for record in sorted(records, key=lambda item: (item.provider, item.observation_date))],
    }
    return frame, manifest


def write_normalized(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")


def write_json(document: dict | list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
