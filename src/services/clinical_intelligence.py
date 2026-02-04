from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from src.services.labs_service import LabsService
from src.services.measurements_service import MeasurementsService, Measurement
from src.services.settings_service import SettingsService

# ---------------------------
# Helpers
# ---------------------------

def norm_key(name: str) -> str:
    """Normalize lab test names for matching / rule lookup."""
    import re
    s = (name or "").strip().casefold()
    tr_map = str.maketrans({"ı":"i","İ":"i","ş":"s","Ş":"s","ğ":"g","Ğ":"g","ü":"u","Ü":"u","ö":"o","Ö":"o","ç":"c","Ç":"c"})
    s = s.translate(tr_map)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    synonyms = {
        "c reaktif protein": "crp",
        "c reaktif protein crp": "crp",
        "crp turbidimetrik": "crp",
        "hs crp": "hs crp",
        "aclik kan sekeri": "glukoz aclik",
        "glukoz aclik kan sekeri": "glukoz aclik",
        "glukoz": "glukoz",
        "hba1c": "hba1c",
        "hb a1c": "hba1c",
        "vitamin d": "25 oh vitamin d",
        "25 oh vitamin d": "25 oh vitamin d",
        "b12": "vitamin b12",
        "vitamin b12": "vitamin b12",
        "total kolesterol": "kolesterol total",
        "kolesterol": "kolesterol total",
        "ldl kolesterol": "ldl",
        "hdl kolesterol": "hdl",
        "trigliserid": "trigliserid",
        "trigliserit": "trigliserid",
        "alt": "alt",
        "ast": "ast",
        "ggt": "ggt",
        "tsh": "tsh",
        "ferritin": "ferritin",
        "demir": "demir",
        "ure": "ure",
        "kreatinin": "kreatinin",
        "egfr": "egfr",
        "uric acid": "urik asit",
        "urik asit": "urik asit",
        "hemoglobin": "hemoglobin",
        "hb": "hemoglobin",
    }
    return synonyms.get(s, s)


@dataclass
class Insight:
    severity: str   # info / warn / critical
    title: str
    detail: str = ""


def _iso_to_date(iso_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None


class ClinicalIntelligence:
    """
    Offline, rule-based 'Klinik Zeka'.

    Not a medical device. It generates *suggestions* based on common reference patterns.
    The clinician/diyetisyen must always validate.
    """
    def __init__(self, conn):
        self.conn = conn
        self.labs = LabsService(conn)
        self.meas = MeasurementsService(conn)
        self.settings = SettingsService(conn)
        self.th = self.settings.get_clinical_thresholds()

    # ---------------------------
    # Labs
    # ---------------------------
    def latest_labs(self, client_id: str) -> Tuple[Optional[dict], List[dict]]:
        """Return (import_row, result_rows_as_dict)."""
        import_id = self.labs.latest_import_id(client_id)
        if not import_id:
            return None, []
        # pull import row
        imp = self.conn.execute("SELECT * FROM lab_imports WHERE id=?", (import_id,)).fetchone()
        imp_dict = dict(imp) if imp else None
        rows = self.labs.list_results_for_import(import_id)
        return imp_dict, [dict(r) for r in rows]

    def lab_insights(self, lab_rows: List[dict]) -> List[Insight]:
        """
        Generate interpretation suggestions for common nutrition/clinic context.

        Uses:
        - status (low/high/borderline/normal/unknown)
        - normalized test_name
        - result_value, unit, ref_low/ref_high when available
        """
        # Build a map for fast lookup
        by_key: Dict[str, dict] = {}
        for r in lab_rows:
            k = norm_key(r.get("test_name",""))
            # prefer numeric rows (result_value not None) if duplicates exist
            if k not in by_key:
                by_key[k] = r
            else:
                cur = by_key[k]
                if cur.get("result_value") is None and r.get("result_value") is not None:
                    by_key[k] = r

        out: List[Insight] = []

        def add(sev: str, title: str, detail: str=""):
            out.append(Insight(severity=sev, title=title, detail=detail))

        def getv(key: str) -> Optional[float]:
            r = by_key.get(key)
            if not r:
                return None
            return r.get("result_value")

        def status(key: str) -> str:
            r = by_key.get(key)
            return (r.get("status") or "unknown") if r else "unknown"

        # --- Glycemic ---
        g = getv("glukoz aclik") or getv("glukoz")
        a1c = getv("hba1c")
        if a1c is not None:
            if a1c >= float(self.th.get('hba1c_critical', 6.5)):
                add("critical", f"HbA1c yüksek ({a1c:.2f}).", "Diyabet aralığı olabilir. Klinik doğrulama ve hekim değerlendirmesi önerilir.")
            elif a1c >= float(self.th.get('hba1c_warn', 5.7)):
                add("warn", f"HbA1c sınırda/yüksek ({a1c:.2f}).", "Prediyabet/insülin direnci açısından yaşam tarzı (lif, protein dengesi, aktivite, uyku) gözden geçirilebilir.")
            else:
                add("info", f"HbA1c normal ({a1c:.2f}).", "Glikoz kontrolü iyi görünüyor; sürdürülebilir beslenme alışkanlığıyla devam.")
        elif g is not None:
            # if only glucose exists, use common fasting ranges in mg/dL
            # NOTE: units might differ; we only act on plausible mg/dL values
            if 60 <= g <= 200:
                if g >= 126:
                    add("critical", f"Açlık glukozu yüksek ({g:.0f}).", "Diyabet aralığı olabilir. Klinik doğrulama ve hekim değerlendirmesi önerilir.")
                elif g >= 100:
                    add("warn", f"Açlık glukozu sınırda/yüksek ({g:.0f}).", "Prediyabet/insülin direnci açısından beslenme ve aktivite düzeni planlanabilir.")
                else:
                    add("info", f"Açlık glukozu normal ({g:.0f}).", "Glikoz kontrolü iyi görünüyor.")

        # --- Lipids ---
        ldl = getv("ldl")
        hdl = getv("hdl")
        tg = getv("trigliserid")
        total = getv("kolesterol total")
        if ldl is not None and 40 <= ldl <= 250:
            if ldl >= float(self.th.get('ldl_critical', 190.0)):
                add("critical", f"LDL çok yüksek ({ldl:.0f}).", "Ailevi hiperkolesterolemi dahil riskler için hekim değerlendirmesi gerekir.")
            elif ldl >= float(self.th.get('ldl_warn', 160.0)):
                add("warn", f"LDL yüksek ({ldl:.0f}).", "Doymuş yağ/ultra-işlenmiş gıda azaltımı, lif artırımı ve kilo/aktivite planı düşünülebilir.")
            elif ldl >= 130:
                add("warn", f"LDL sınırda ({ldl:.0f}).", "Kalp-damar riski profiline göre hedefler belirlenebilir.")
        if hdl is not None and 10 <= hdl <= 120:
            if hdl < 40:
                add("warn", f"HDL düşük ({hdl:.0f}).", "Düzenli aerobik aktivite, kilo yönetimi ve sigara varsa bırakma desteği yararlı olabilir.")
        if tg is not None and 30 <= tg <= 800:
            if tg >= 500:
                add("critical", f"Trigliserid çok yüksek ({tg:.0f}).", "Pankreatit riski açısından acil hekim değerlendirmesi gerekebilir.")
            elif tg >= 200:
                add("warn", f"Trigliserid yüksek ({tg:.0f}).", "Şeker/rafine karbonhidrat azaltımı, alkol varsa kısıtlama, omega-3 kaynakları ve aktivite planı düşünülebilir.")
            elif tg >= 150:
                add("warn", f"Trigliserid sınırda ({tg:.0f}).", "Karbonhidrat kalitesi ve total enerji dengesi gözden geçirilebilir.")
        if total is not None and 80 <= total <= 400:
            if total >= 240:
                add("warn", f"Total kolesterol yüksek ({total:.0f}).", "LDL/HDL/TG ile birlikte değerlendirilmelidir.")

        # --- Liver ---
        alt = getv("alt")
        ast = getv("ast")
        ggt = getv("ggt")
        # Use status if available; numeric thresholds vary by lab. We'll prefer status.
        for key, label in [("alt","ALT"),("ast","AST"),("ggt","GGT")]:
            st = status(key)
            v = getv(key)
            if st == "high":
                add("warn", f"{label} yüksek ({'' if v is None else f'{v:.0f}'}).", "Karaciğer yağlanması/alkol/ilaç etkisi gibi nedenler için klinik değerlendirme gerekir.")
        # --- Thyroid ---
        tsh = getv("tsh")
        if tsh is not None:
            # wide heuristic range
            if tsh >= 10:
                add("critical", f"TSH yüksek ({tsh:.2f}).", "Hipotiroidi olasılığı için hekim değerlendirmesi önerilir.")
            elif tsh > 4.5:
                add("warn", f"TSH yüksek ({tsh:.2f}).", "Tiroid fonksiyonları için klinik doğrulama önerilir.")
            elif tsh < 0.1:
                add("critical", f"TSH çok düşük ({tsh:.2f}).", "Hipertiroidi olasılığı için hekim değerlendirmesi önerilir.")
            elif tsh < 0.4:
                add("warn", f"TSH düşük ({tsh:.2f}).", "Tiroid fonksiyonları için klinik doğrulama önerilir.")

        # --- Iron / Vitamins ---
        ferr = getv("ferritin")
        if ferr is not None:
            if ferr < 15:
                add("warn", f"Ferritin düşük ({ferr:.1f}).", "Demir depoları düşük olabilir. Diyet (heme/non-heme demir), C vitamini eşleştirme ve hekim değerlendirmesi düşünülür.")
        vitd = getv("25 oh vitamin d")
        if vitd is not None:
            if vitd < 10:
                add("warn", f"Vitamin D çok düşük ({vitd:.1f}).", "Güneşlenme ve hekim kontrolünde destek planı değerlendirilebilir.")
            elif vitd < 20:
                add("warn", f"Vitamin D düşük ({vitd:.1f}).", "Yeterli güneşlenme ve hekim kontrolünde destek değerlendirilebilir.")
            elif vitd < 30:
                add("info", f"Vitamin D sınırda ({vitd:.1f}).", "Sürdürülebilir düzey için yaşam tarzı destekleri planlanabilir.")
        b12 = getv("vitamin b12")
        if b12 is not None and b12 < 200:
            add("warn", f"B12 düşük ({b12:.0f}).", "Hayvansal kaynak alımı, emilim sorunları ve hekim kontrolünde destek planı değerlendirilebilir.")

        # --- Inflammation ---
        crp = getv("crp") or getv("hs crp")
        if crp is not None:
            st = status("crp")
            if st == "high" or crp > float(self.th.get('crp_warn', 10.0)):
                add("warn", f"CRP yüksek ({crp:.1f}).", "Akut enfeksiyon/iltihap olabilir. Klinik tablo ile birlikte değerlendirilmelidir.")

        # --- Kidney ---
        kreat = getv("kreatinin")
        egfr = getv("egfr")
        if egfr is not None and egfr < 60:
            add("warn", f"eGFR düşük ({egfr:.0f}).", "Böbrek fonksiyonu için hekim değerlendirmesi gerekir (protein/ilaç/hipertansiyon vb.).")
        if kreat is not None and status("kreatinin") == "high":
            add("warn", f"Kreatinin yüksek ({kreat:.2f}).", "Böbrek fonksiyonu/hidrasyon/ilaçlar ile birlikte değerlendirme önerilir.")

        # If nothing triggered, still provide a gentle note if there are rows
        if not out and lab_rows:
            add("info", "Belirgin bir otomatik uyarı bulunamadı.", "Değerleri klinik bağlam ve danışan öyküsüyle birlikte yorumlayın.")

        # Sort by severity
        sev_order = {"critical": 0, "warn": 1, "info": 2}
        out.sort(key=lambda i: sev_order.get(i.severity, 9))
        return out

    # ---------------------------
    # Measurement trend alerts
    # ---------------------------
    def measurement_alerts(self, client_id: str) -> List[Insight]:
        ms = self.meas.list_for_client(client_id)
        ms = [m for m in ms if (m.weight_kg or 0) > 0]
        if len(ms) < 2:
            return [Insight("info", "Trend analizi için en az 2 ölçüm gerekir.", "Yeni ölçüm girildikçe trend uyarıları otomatik oluşur.")]

        # sort ascending by date
        def to_dt(m: Measurement) -> datetime:
            return datetime.strptime(m.measured_at, "%Y-%m-%d")
        ms_sorted = sorted(ms, key=to_dt)

        latest = ms_sorted[-1]
        prev = ms_sorted[-2]

        out: List[Insight] = []

        def add(sev: str, title: str, detail: str=""):
            out.append(Insight(sev, title, detail))

        # Weight change
        if latest.weight_kg and prev.weight_kg:
            dw = latest.weight_kg - prev.weight_kg
            days = (to_dt(latest) - to_dt(prev)).days or 1
            rate_week = dw / days * 7.0
            if abs(rate_week) >= float(self.th.get('weight_rate_warn', 2.0)):
                add("warn", f"Kilo değişimi hızlı ({dw:+.1f} kg / {days}g).", "Hızlı değişimler sıvı/ödem, uyum veya ölçüm koşulları kaynaklı olabilir; plan ve takip sıklığı gözden geçirilebilir.")
            elif abs(rate_week) >= float(self.th.get('weight_rate_info', 1.0)):
                add("info", f"Kilo değişimi belirgin ({dw:+.1f} kg / {days}g).", "Hedefe göre sürdürülebilir hız değerlendirmesi yapılabilir.")

        # BMI category (if height available)
        bmi = latest.bmi()
        if bmi is not None:
            if bmi >= 35:
                add("warn", f"BMI yüksek ({bmi:.1f}).", "Kardiyometabolik risk profiline göre planlama ve hekim iş birliği gerekebilir.")
            elif bmi >= 30:
                add("warn", f"Obezite aralığı BMI ({bmi:.1f}).", "Yaşam tarzı, uyku, stres ve aktivite ile birlikte sürdürülebilir kilo yönetimi planı önerilir.")
            elif bmi >= 25:
                add("info", f"Fazla kilo aralığı BMI ({bmi:.1f}).", "Hedefler danışan beklentisi ve klinik duruma göre netleştirilebilir.")

        # Waist alerts (common cutoffs: men>102, women>88) - gender not available here
        if latest.waist_cm:
            if latest.waist_cm >= float(self.th.get('waist_warn', 110.0)):
                add("warn", f"Bel çevresi yüksek ({latest.waist_cm:.0f} cm).", "Santral obezite açısından risk artabilir; beslenme + aktivite planı ve takip önerilir.")
            elif latest.waist_cm >= float(self.th.get('waist_info', 95.0)):
                add("info", f"Bel çevresi izlenmeli ({latest.waist_cm:.0f} cm).", "Kilo/yağ dağılımı hedefleri ile birlikte takip edilebilir.")

        # Trend direction over last 3 points (if available)
        if len(ms_sorted) >= 3:
            w3 = [m.weight_kg for m in ms_sorted[-3:] if m.weight_kg]
            if len(w3) == 3:
                if w3[2] > w3[1] > w3[0]:
                    add("warn", "Son 3 ölçümde kilo artış trendi var.", "Uygunluk, toplam enerji dengesi ve aktivite planı gözden geçirilebilir.")
                elif w3[2] < w3[1] < w3[0]:
                    add("info", "Son 3 ölçümde kilo düşüş trendi var.", "Hız ve sürdürülebilirlik hedefe göre değerlendirilebilir.")

        if not out:
            out.append(Insight("info", "Ölçüm trendinde belirgin risk/uyarı bulunamadı.", "Düzenli ölçüm ve notlarla takip sürdürülebilir hale gelir."))

        sev_order = {"critical": 0, "warn": 1, "info": 2}
        out.sort(key=lambda i: sev_order.get(i.severity, 9))
        return out

    # ---------------------------
    # One-glance summary
    # ---------------------------
    def one_glance_summary(self, client_id: str) -> Dict[str, object]:
        latest_meas = self.meas.latest_for_client(client_id)
        imp, labs = self.latest_labs(client_id)
        lab_ins = self.lab_insights(labs) if labs else []
        meas_ins = self.measurement_alerts(client_id)

        return {
            "latest_measurement": latest_meas,
            "latest_labs_import": imp,
            "lab_insights": lab_ins,
            "measurement_alerts": meas_ins,
        }
