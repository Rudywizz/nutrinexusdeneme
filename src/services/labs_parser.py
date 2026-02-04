from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import re
from datetime import datetime

# Referans parser: "0 - 5", "<126", ">50"
_RE_RANGE = re.compile(r'(?P<low>-?\d+(?:[.,]\d+)?)\s*-\s*(?P<high>-?\d+(?:[.,]\d+)?)')
_RE_LT = re.compile(r'<\s*(?P<lim>-?\d+(?:[.,]\d+)?)')
_RE_GT = re.compile(r'>\s*(?P<lim>-?\d+(?:[.,]\d+)?)')

_RE_NUM = re.compile(r'[-+]?\d+(?:[.,]\d+)?')

def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(',', '.'))
    except Exception:
        return None

@dataclass
class RefRange:
    mode: str                 # range/lt/gt/unknown
    low: Optional[float] = None
    high: Optional[float] = None
    text: str = ""

def parse_ref(ref_text: str) -> RefRange:
    t = (ref_text or "").strip()
    m = _RE_RANGE.search(t)
    if m:
        return RefRange(mode="range", low=_to_float(m.group("low")), high=_to_float(m.group("high")), text=t)
    m = _RE_LT.search(t)
    if m:
        lim = _to_float(m.group("lim"))
        return RefRange(mode="lt", low=None, high=lim, text=t)
    m = _RE_GT.search(t)
    if m:
        lim = _to_float(m.group("lim"))
        return RefRange(mode="gt", low=lim, high=None, text=t)
    return RefRange(mode="unknown", text=t)

def classify_value(value: Optional[float], ref: RefRange, borderline_ratio: float = 0.05) -> str:
    """
    borderline_ratio: sınır bandı (örn %5).
    """
    if value is None:
        return "unknown"
    if ref.mode == "range" and ref.low is not None and ref.high is not None:
        if value < ref.low:
            return "low"
        if value > ref.high:
            return "high"
        span = max(ref.high - ref.low, 0.000001)
        if value <= ref.low + span * borderline_ratio or value >= ref.high - span * borderline_ratio:
            return "borderline"
        return "normal"
    if ref.mode == "lt" and ref.high is not None:
        if value > ref.high:
            return "high"
        if value >= ref.high * (1 - borderline_ratio):
            return "borderline"
        return "normal"
    if ref.mode == "gt" and ref.low is not None:
        if value < ref.low:
            return "low"
        if value <= ref.low * (1 + borderline_ratio):
            return "borderline"
        return "normal"
    return "unknown"

@dataclass
class LabRow:
    test_name: str
    result_text: str
    result_value: Optional[float]
    unit: str
    ref_text: str
    ref: RefRange
    status: str

def _extract_row_from_line(line: str) -> Optional[LabRow]:
    """
    Heuristik: satırın sonunda referans var; referansın solunda sonuç ve birim var.
    """
    raw = re.sub(r'\s+', ' ', (line or "").strip())
    if len(raw) < 8:
        return None

    # referans kısmını satırın sonundan yakalamaya çalış
    # range / < / >
    ref_match = None
    for rx in (_RE_RANGE, _RE_LT, _RE_GT):
        for m in rx.finditer(raw):
            ref_match = m  # last match wins
    if not ref_match:
        return None

    ref_text = raw[ref_match.start():].strip()
    left = raw[:ref_match.start()].strip()
    tokens = left.split(" ")

    # soldan sağa değil, sağdan sola: önce numeric sonucu bul
    # ör: "... Glukoz 148 mg/dL" veya "... HDL 28 mg/dL"
    val_idx = None
    for i in range(len(tokens)-1, -1, -1):
        if _RE_NUM.fullmatch(tokens[i]):
            val_idx = i
            break
    if val_idx is None:
        return None

    result_text = tokens[val_idx]
    value = _to_float(result_text)

    unit = ""
    if val_idx + 1 < len(tokens):
        unit = " ".join(tokens[val_idx+1:]).strip()

    name = " ".join(tokens[:val_idx]).strip()
    # bazı satırlarda isim boş kalabiliyor; güvenlik
    if len(name) < 2:
        return None

    ref = parse_ref(ref_text)
    status = classify_value(value, ref)
    return LabRow(
        test_name=name,
        result_text=result_text,
        result_value=value,
        unit=unit,
        ref_text=ref_text,
        ref=ref,
        status=status
    )

def parse_enabiz_text(text: str) -> List[LabRow]:
    """
    PDF'den çıkarılan düz metinden satırları parse eder.
    """
    rows: List[LabRow] = []
    for line in (text or "").splitlines():
        r = _extract_row_from_line(line)
        if r:
            rows.append(r)

    # aynı test birden fazla kez gelebilir; burada tümünü bırakıyoruz.
    # UI tarafında en günceli seçme / filtreleme yapılabilir.
    return rows
