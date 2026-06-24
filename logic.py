import json
import re
import unicodedata
from pathlib import Path

DATA_PATH = Path(__file__).parent / "estudios.json"


def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    if s is None:
        return ""
    s = strip_accents(str(s)).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


STOPWORDS = {
    "QUE", "CUAL", "CUALES", "CUANTO", "CUANTOS", "CUANTA", "CUANTAS", "DIAS", "DIA",
    "DEMORA", "TARDA", "TARDAN", "MUESTRA", "METODO", "VALOR", "VALORES", "REFERENCIA",
    "NORMAL", "NORMALES", "DEBO", "USAR", "PARA", "UN", "UNA", "EL", "LA", "LOS", "LAS",
    "DE", "DEL", "EN", "ES", "SE", "ME", "MI", "POR", "CON", "Y", "O", "A", "AL", "COMO",
    "HACE", "HACEN", "NECESITO", "NECESITA", "ESTUDIO", "ANALISIS", "TIENE", "TIENEN",
    "CODIGO", "INDICACION", "INDICACIONES", "OBSERVACION", "OBSERVACIONES", "LABORATORIO",
    "DERIVA", "DERIVADO", "DERIVADOS", "PIDO", "PEDIR", "SACAR", "RESULTADO", "RESULTADOS",
    "TIPO", "TENGO", "TENES", "TIENES", "QUIERO", "PUEDO", "SIRVE", "HAY", "FAVOR",
    "DECIME", "DECIR", "AVISA", "PEDIDO", "PODES", "PODRIAS", "PODRIA", "SABES", "SABE",
}

INTENTS = {
    "demora": ["demora", "tarda", "dias", "dia", "habiles", "espera", "cuanto tiempo"],
    "muestra": ["muestra", "tubo", "sangre", "extraccion", "recolectar", "recipiente"],
    "metodo": ["metodo", "tecnica", "como se procesa", "que tecnica"],
    "valores_referencia": ["valor de referencia", "valores de referencia", "valor normal", "valores normales", "rango"],
    "indicaciones": ["indicacion", "indicaciones", "ayuno", "preparacion", "antes de"],
    "laboratorio": ["donde se procesa", "que laboratorio", "a donde deriva", "se deriva"],
    "observaciones": ["observacion", "observaciones", "comentario", "nota"],
}


def detect_intent(query_norm: str):
    for intent, keywords in INTENTS.items():
        for kw in keywords:
            if normalize(kw) in query_norm:
                return intent
    return None


def extract_search_terms(query_norm: str):
    return [w for w in query_norm.split() if w not in STOPWORDS and len(w) > 1]


def score_record(record, terms, query_norm):
    estudio_norm = normalize(record.get("estudio", ""))
    nemonico_norm = normalize(record.get("nemonico_datatech", ""))
    codigo_norm = normalize(record.get("codigo_hexalis", ""))

    score = 0
    if codigo_norm and codigo_norm == query_norm.replace(" ", ""):
        score += 100

    # how many distinct query terms actually appear in the study name —
    # this is the main driver of relevance, since a short generic code
    # (e.g. nemonico "PCR") shouldn't outrank a study that matches every
    # word of a longer, more specific query.
    estudio_words = set(estudio_norm.split())
    matched_terms = {t for t in terms if t in estudio_words or t in estudio_norm}
    term_match_count = len(matched_terms)
    score += term_match_count * 18
    if terms and term_match_count == len(terms):
        score += 25  # full coverage of every query term

    if nemonico_norm and len(nemonico_norm) >= 3 and nemonico_norm in terms:
        score += 20

    if terms:
        joined = " ".join(terms)
        if joined and joined in estudio_norm:
            score += 40
    return score


def record_key(rec):
    return rec.get("codigo_hexalis") or rec.get("estudio")


def search(data, query):
    query_norm = normalize(query)
    terms = extract_search_terms(query_norm)
    if not terms:
        return [], None

    scored = []
    for rec in data:
        s = score_record(rec, terms, query_norm)
        if s > 0:
            scored.append((s, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score = scored[0][0] if scored else 0
    if top_score == 0:
        return [], terms

    # identify the keys (study identity) that achieved the top score band
    threshold = top_score * 0.6
    top_keys = {record_key(r) for s, r in scored if s >= threshold}

    # pull in ALL records sharing those keys, even ones that scored lower
    # (e.g. the GENERAL row may score lower than a derived-lab row that has
    # an extra nemonico match, but it should still be included in the group)
    candidates = [r for r in data if record_key(r) in top_keys]
    return candidates, terms


def group_by_study(records):
    groups = {}
    order = []
    for r in records:
        key = r.get("codigo_hexalis") or r.get("estudio")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    return [(k, groups[k]) for k in order]


FIELD_LABELS = {
    "metodo": "Método",
    "muestra": "Muestra",
    "valores_referencia": "Valores de referencia",
    "demora": "Demora (días hábiles)",
    "indicaciones": "Indicaciones",
    "observaciones": "Observaciones",
    "resultado_preanalitico": "Resultado preanalítico",
    "modelo_informe": "Modelo de informe",
    "status": "Estado de paridad",
}


def format_demora(val):
    try:
        f = float(val)
        if f == int(f):
            return f"{int(f)} días hábiles"
        return f"{f} días hábiles"
    except (TypeError, ValueError):
        return str(val)


def answer_for_record(rec, intent):
    lab = rec.get("laboratorio", "")
    estudio = rec.get("estudio", "")
    if intent and rec.get(intent) not in (None, ""):
        val = rec[intent]
        if intent == "demora":
            val = format_demora(val)
        label = FIELD_LABELS.get(intent, intent)
        return f"**{estudio}** ({lab}) — {label}: {val}"
    parts = [f"**{estudio}** ({lab})"]
    for field in ["metodo", "muestra", "valores_referencia", "demora", "indicaciones"]:
        v = rec.get(field)
        if v not in (None, ""):
            if field == "demora":
                v = format_demora(v)
            parts.append(f"- {FIELD_LABELS[field]}: {v}")
    return "\n".join(parts)


def answer_query(data, query):
    """Pure function: query in, answer text out. Used by app.py and tests."""
    intent = detect_intent(normalize(query))
    candidates, terms = search(data, query)

    if not terms:
        return "No entendí la consulta. Probá nombrando el estudio o el código (ej: \"demora de ACTH\")."
    if not candidates:
        return f"No encontré ningún estudio que coincida con \"{query}\"."

    groups = group_by_study(candidates)
    if len(groups) == 1:
        key, recs = groups[0]
        general = next((r for r in recs if r["laboratorio"] == "GENERAL"), recs[0])
        response = answer_for_record(general, intent)
        other_labs = [r for r in recs if r is not general]
        if other_labs:
            lab_names = ", ".join(sorted({r["laboratorio"] for r in other_labs}))
            response += f"\n\n_También figura derivado en: {lab_names}._"
        return response

    response = f"Encontré {len(groups)} estudios que coinciden con \"{query}\":\n\n"
    for key, recs in groups[:8]:
        general = next((r for r in recs if r["laboratorio"] == "GENERAL"), recs[0])
        response += f"- {answer_for_record(general, intent)}\n"
    if len(groups) > 8:
        response += f"\n_y {len(groups) - 8} más. Probá ser más específico._"
    return response
