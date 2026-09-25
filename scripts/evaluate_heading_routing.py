"""
Pozisyon yönlendirme (subtree routing) deneyi — LLM çağrısı yapmaz.

SORU
----
Mevcut hat her ürünü 97 faslın tamamını içeren bir CHAPTER seçimiyle başlatıyor.
Öneri: fasıl seçimini atlayıp aday 4 haneli pozisyonları arama ile bulmak ve
LLM'i doğrudan HEADING seviyesinden başlatmak. Bu ancak arama doğru pozisyonu
kısa listede yeterince sık yakalıyorsa işe yarar. Bu betik bunu ölçer.

YÖNTEMLER
---------
  btb     Ürünle eşleşen BTB emsallerinin pozisyonlarına oy verilir (üretimdeki
          `search_btb_precedents`, numunenin kendi kararı hariç).
  lexical Her pozisyon için bir belge kurulur (pozisyon metni + tüm alt pozisyon
          ve yaprak metinleri) ve BM25 ile sıralanır. Türkçe ekler için ilk 5
          karakter kökü kullanılır.
  dense   Aynı pozisyon belgeleri Vertex AI embedding ile vektörleştirilir;
          kosinüs benzerliğiyle sıralanır. Belge vektörleri önbelleğe yazılır.
  fused   Mevcut yöntemlerin Reciprocal Rank Fusion birleşimi (k=60).

METRİKLER
---------
  heading_recall@k   Doğru pozisyon ilk k aday arasında mı?
  chapter_recall@k   Doğru fasıl ilk k adayın fasılları arasında mı?
  coverage           Yöntem en az bir aday üretti mi?
  gate taraması      Kapı koşulunu sağlayan numunelerin oranı ve bunlar içinde
                     recall@3. Hibrit yapıda "aramaya güven / ağaca dön"
                     kararının eşiği buradan seçilir.
  traversal karşılaştırması  LLM ağaç dolaşımının fasılda yanıldığı numunelerde
                     yönlendirme doğru pozisyonu buluyor mu?

Holdout, bir benchmark raporundaki numunelerden (--from-report) alınır; böylece
sonuçlar aynı numuneler üzerinde LLM dolaşımıyla birebir karşılaştırılabilir.

Kullanım:
  python -m scripts.evaluate_heading_routing \\
      --from-report benchmark_results/benchmark-full-20260923T191133Z.json
  python -m scripts.evaluate_heading_routing --sample 120 --no-dense
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import logging
import math
import os
import re
import statistics
import sys
import time
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Üretimdeki yönlendirme (workflow) aynı oylamayı kullanır; deney onu ölçer.
from api.modules.rag_engine import aggregate_precedents_by_heading  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HeadingRouting")

CATALOG_PATH = os.path.join(root_dir, "2026 TGTC", "tgtc_2026_full_database.json")
RECALL_KS = (1, 3, 5, 10)
RRF_K = 60
# Embedding modeli belge başına ~2048 token kabul eder; pozisyon belgeleri
# (özellikle 84/85'te) bunu aşar. Kesme, pozisyon metnini ve ilk alt dalları korur.
DENSE_DOC_CHARS = 6000
DEFAULT_DENSE_MODEL = "text-multilingual-embedding-002"

Ranking = List[Tuple[str, float]]  # [(pozisyon kodu, skor)], skora göre azalan


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


# ──────────────────────────────────────────────────────────────────────────────
# Metin normalizasyonu ve pozisyon belgeleri
# ──────────────────────────────────────────────────────────────────────────────

# Tarife metninde her pozisyonda geçen, ayırt etmeyen sözcükler (5 karakter kökü).
_STOP_STEMS = {
    "ile", "veya", "icin", "bir", "gibi", "kadar", "ait", "gore",
    "olan", "olanl", "olsun", "olmas", "olara", "diger", "haric", "dahil",
    "turde", "turle", "kulla", "mahsu",
}


def fold(text: Any) -> str:
    """Türkçe karakter ve aksanları katlar, küçük harfe çevirir."""
    value = str(text or "").replace("ı", "i").replace("İ", "I")
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def tokenize(text: Any, stem_len: int = 5) -> List[str]:
    """Kelime → ilk `stem_len` karakter. Türkçe eklemeli yapıda basit ve etkili kök."""
    stems = []
    for word in re.findall(r"[a-z]+", fold(text)):
        if len(word) < 3:
            continue
        stem = word[:stem_len]
        if stem in _STOP_STEMS:
            continue
        stems.append(stem)
    return stems


def _clean_segment(text: str) -> str:
    return re.sub(r"^[\s\-–—:]+|[\s:;]+$", "", str(text or "")).strip()


def build_heading_documents(catalog: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Her 4 haneli pozisyon için pozisyon metni + alt dal metinlerinden belge kurar.

    Yaprak açıklamaları yeni katalogda kökten yaprağa yol taşır ("A > B > C");
    aynı segment birden çok yaprakta tekrarlanır. Segmentler tekilleştirilir,
    böylece belge uzunluğu tekrarla şişmez ve BM25 frekansları çarpılmaz.
    """
    titles: Dict[str, str] = {}
    segments: Dict[str, List[str]] = collections.defaultdict(list)
    seen: Dict[str, set] = collections.defaultdict(set)

    for item in catalog:
        code = _digits(item.get("gtip_code"))
        description = str(item.get("description") or "")
        if len(code) < 4 or not description.strip():
            continue
        heading = code[:4]
        if len(code) == 4:
            titles[heading] = _clean_segment(description)
            continue
        for part in description.split(" > "):
            segment = _clean_segment(part)
            key = fold(segment)
            if not segment or key in seen[heading] or key in {"digerleri", "diger"}:
                continue
            seen[heading].add(key)
            segments[heading].append(segment)

    documents: Dict[str, str] = {}
    for heading in sorted(set(titles) | set(segments)):
        parts = [titles.get(heading, "")] + segments.get(heading, [])
        documents[heading] = " ; ".join(part for part in parts if part)
    return documents


def load_catalog(path: str = CATALOG_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def subheading_counts(catalog: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Pozisyon başına 6 haneli alt pozisyon sayısı (HEADING sonrası seçenek boyutu)."""
    subs: Dict[str, set] = collections.defaultdict(set)
    for item in catalog:
        code = _digits(item.get("gtip_code"))
        if len(code) >= 6:
            subs[code[:4]].add(code[:6])
    return {heading: len(values) for heading, values in subs.items()}


# ──────────────────────────────────────────────────────────────────────────────
# Sıralayıcılar
# ──────────────────────────────────────────────────────────────────────────────

class BM25Index:
    """Küçük, bağımlılıksız BM25 (Okapi). 964 belge için yeterince hızlı."""

    def __init__(self, documents: Dict[str, str], k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.keys = list(documents)
        self.term_freqs: List[collections.Counter] = []
        self.lengths: List[int] = []
        df: collections.Counter = collections.Counter()
        for key in self.keys:
            tokens = tokenize(documents[key])
            counts = collections.Counter(tokens)
            self.term_freqs.append(counts)
            self.lengths.append(len(tokens))
            df.update(counts.keys())
        self.avg_len = statistics.fmean(self.lengths) if self.lengths else 0.0
        total = len(self.keys)
        self.idf = {
            term: math.log(1.0 + (total - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def rank(self, query: str, top_k: int = 20) -> Ranking:
        query_terms = set(tokenize(query))
        if not query_terms or not self.keys:
            return []
        scores: List[Tuple[str, float]] = []
        for key, counts, length in zip(self.keys, self.term_freqs, self.lengths):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1.0))
            for term in query_terms:
                tf = counts.get(term)
                if tf:
                    score += self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
            if score > 0:
                scores.append((key, score))
        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores[:top_k]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def dense_rank(query_vector: Sequence[float], doc_vectors: Dict[str, Sequence[float]], top_k: int = 20) -> Ranking:
    if not query_vector or not any(query_vector):
        return []
    scores = [(key, cosine(query_vector, vector)) for key, vector in doc_vectors.items()]
    scores.sort(key=lambda pair: pair[1], reverse=True)
    return scores[:top_k]


def rrf_fuse(rankings: Sequence[Ranking], k: int = RRF_K, top_k: int = 20) -> Ranking:
    """Reciprocal Rank Fusion: skor ölçekleri farklı sıralamaları sıra üzerinden birleştirir."""
    fused: Dict[str, float] = collections.defaultdict(float)
    for ranking in rankings:
        for position, (key, _) in enumerate(ranking, 1):
            fused[key] += 1.0 / (k + position)
    ordered = sorted(fused.items(), key=lambda pair: pair[1], reverse=True)
    return ordered[:top_k]


# ──────────────────────────────────────────────────────────────────────────────
# Embedding (Vertex AI) — önbellekli
# ──────────────────────────────────────────────────────────────────────────────

def _embed_batch(texts: List[str], model: str, task_type: str) -> List[List[float]]:
    from google import genai
    from google.genai import types

    from api.config import settings

    client = genai.Client(vertexai=True, project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
    for attempt in range(1, 5):
        try:
            response = client.models.embed_content(
                model=model,
                contents=texts,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            return [list(item.values) for item in response.embeddings]
        except Exception as exc:
            if attempt == 4:
                raise
            wait = 2.0 * attempt
            logger.warning("Embedding çağrısı başarısız (%s); %.0f sn sonra yeniden.", exc, wait)
            time.sleep(wait)
    return []


def embed_documents(
    documents: Dict[str, str],
    model: str,
    cache_path: str,
    batch_size: int = 8,
) -> Dict[str, List[float]]:
    """Pozisyon belgelerini vektörleştirir. Önbellek belge metninin özetiyle doğrulanır."""
    import hashlib

    signature = hashlib.sha256(
        json.dumps([model, DENSE_DOC_CHARS, sorted(documents.items())], ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
        if cached.get("signature") == signature:
            logger.info("Pozisyon vektörleri önbellekten okundu: %s", cache_path)
            return cached["vectors"]
        logger.info("Önbellek eski (katalog veya model değişmiş); yeniden hesaplanıyor.")

    keys = list(documents)
    vectors: Dict[str, List[float]] = {}
    for start in range(0, len(keys), batch_size):
        chunk = keys[start:start + batch_size]
        texts = [documents[key][:DENSE_DOC_CHARS] for key in chunk]
        for key, vector in zip(chunk, _embed_batch(texts, model, "RETRIEVAL_DOCUMENT")):
            vectors[key] = vector
        if (start // batch_size) % 20 == 0:
            logger.info("Pozisyon vektörleri: %d/%d", min(start + batch_size, len(keys)), len(keys))

    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump({"signature": signature, "model": model, "vectors": vectors}, handle)
    return vectors


# ──────────────────────────────────────────────────────────────────────────────
# Metrikler
# ──────────────────────────────────────────────────────────────────────────────

def rank_of(ranking: Ranking, expected: str, width: int = 4) -> Optional[int]:
    """Beklenen kodun (ilk `width` hane) sıralamadaki 1-tabanlı yeri; yoksa None.

    Fasıl için (width=2) aynı faslın ilk görüldüğü sıra kullanılır.
    """
    target = expected[:width]
    seen: List[str] = []
    for key, _ in ranking:
        prefix = key[:width]
        if prefix in seen:
            continue
        seen.append(prefix)
        if prefix == target:
            return len(seen)
    return None


def recall_at(ranks: Sequence[Optional[int]], k: int) -> float:
    if not ranks:
        return 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank <= k)
    return round(100.0 * hits / len(ranks), 2)


def gate_features(ranking: Ranking) -> Dict[str, float]:
    """Kapı için kullanılabilecek güven özellikleri: en iyi skor ve 1.–2. farkı."""
    if not ranking:
        return {"top1": 0.0, "margin": 0.0}
    top1 = ranking[0][1]
    top2 = ranking[1][1] if len(ranking) > 1 else 0.0
    return {"top1": round(top1, 6), "margin": round(top1 - top2, 6)}


def sweep_gate(
    rows: Sequence[Dict[str, Any]],
    feature: str,
    thresholds: Sequence[float],
    k: int = 3,
) -> List[Dict[str, Any]]:
    """Her eşik için: kapıdan geçen oran ve geçenler içinde recall@k.

    Hibrit yapıda kapıyı geçenler doğrudan HEADING'den başlar, geçmeyenler
    mevcut fasıl seçimine döner. İyi bir eşik yüksek recall'u yeterli oranla verir.
    """
    table = []
    for threshold in thresholds:
        passed = [row for row in rows if row["gate"][feature] >= threshold]
        ranks = [row["heading_rank"] for row in passed]
        table.append({
            "threshold": threshold,
            "pass_rate": round(100.0 * len(passed) / len(rows), 2) if rows else 0.0,
            "passed": len(passed),
            f"recall@{k}_of_passed": recall_at(ranks, k) if passed else None,
        })
    return table


def summarize(method: str, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    heading_ranks = [row["heading_rank"] for row in rows]
    chapter_ranks = [row["chapter_rank"] for row in rows]
    return {
        "method": method,
        "n": len(rows),
        "coverage": round(100.0 * sum(1 for row in rows if row["candidates"]) / len(rows), 2) if rows else 0.0,
        **{f"heading_recall@{k}": recall_at(heading_ranks, k) for k in RECALL_KS},
        **{f"chapter_recall@{k}": recall_at(chapter_ranks, k) for k in (1, 3)},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Veri
# ──────────────────────────────────────────────────────────────────────────────

def load_dataset_from_report(report_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Benchmark raporundaki numuneleri Cloud SQL'den açıklamalarıyla yeniden kurar."""
    from api.db.database import GumrukEmsalKararModel, SessionLocal
    from scripts.evaluate_gtip_benchmark import load_report

    report = load_report(report_path)
    traversal = {sample["reference_no"]: sample for sample in report.get("samples", [])}
    if not traversal:
        raise SystemExit("Raporda 'samples' yok; numune bazlı karşılaştırma yapılamaz.")

    with SessionLocal() as session:
        rows = session.query(
            GumrukEmsalKararModel.referans_no,
            GumrukEmsalKararModel.gtip_kodu,
            GumrukEmsalKararModel.esya_tanimi,
        ).filter(
            GumrukEmsalKararModel.karar_tipi == "BTB",
            GumrukEmsalKararModel.referans_no.in_(list(traversal)),
        ).all()

    dataset: List[Dict[str, Any]] = []
    found = set()
    for ref_no, gtip, description in rows:
        ref = str(ref_no)
        expected = traversal[ref]["expected_gtip"]
        # Aynı referansın birden çok kalemi olabilir; raporda ölçülen kodla eşleşeni al.
        if ref in found or _digits(gtip) != expected:
            continue
        found.add(ref)
        dataset.append({
            "reference_no": ref,
            "expected_gtip": expected,
            "description": str(description or "").strip(),
        })
    missing = set(traversal) - found
    if missing:
        logger.warning("%d numune veritabanında bulunamadı: %s", len(missing), sorted(missing)[:5])
    return dataset, traversal


# ──────────────────────────────────────────────────────────────────────────────
# Deney
# ──────────────────────────────────────────────────────────────────────────────

def evaluate(
    dataset: Sequence[Dict[str, Any]],
    retrievers: Dict[str, Callable[[Dict[str, Any]], Ranking]],
    traversal: Optional[Dict[str, Dict[str, Any]]] = None,
    sub_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    # BTB emsali numunelerin çoğunda boş döner; emsalden bağımsız metin
    # yönlendirmesinin gücü ayrıca görülmeli.
    text_methods = [name for name in ("lexical", "dense") if name in retrievers]
    per_method: Dict[str, List[Dict[str, Any]]] = {name: [] for name in retrievers}
    per_method["fused"] = []
    if len(text_methods) == 2:
        per_method["fused_text"] = []
    samples: List[Dict[str, Any]] = []

    for index, sample in enumerate(dataset, 1):
        expected = sample["expected_gtip"]
        rankings = {name: retriever(sample) for name, retriever in retrievers.items()}
        base = dict(rankings)
        rankings["fused"] = rrf_fuse([ranking for ranking in base.values() if ranking])
        if "fused_text" in per_method:
            rankings["fused_text"] = rrf_fuse([base[name] for name in text_methods if base[name]])

        record = {"reference_no": sample["reference_no"], "expected_heading": expected[:4]}
        for name, ranking in rankings.items():
            row = {
                "candidates": len(ranking),
                "heading_rank": rank_of(ranking, expected, 4),
                "chapter_rank": rank_of(ranking, expected, 2),
                "gate": gate_features(ranking),
                "top3": [key for key, _ in ranking[:3]],
            }
            per_method[name].append({**row, "reference_no": sample["reference_no"]})
            record[name] = row
        samples.append(record)
        if index % 20 == 0:
            logger.info("[%d/%d] işlendi", index, len(dataset))

    report: Dict[str, Any] = {
        "summary": [summarize(name, rows) for name, rows in per_method.items()],
        "gates": {},
        "samples": samples,
    }

    # Kapı taraması: BTB için en iyi benzerlik, dense/fused için 1.–2. farkı.
    if "btb" in per_method:
        report["gates"]["btb_top1"] = sweep_gate(per_method["btb"], "top1", [0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.96])
    if "dense" in per_method:
        report["gates"]["dense_margin"] = sweep_gate(per_method["dense"], "margin", [0.0, 0.01, 0.02, 0.03, 0.05, 0.08])
    if "lexical" in per_method:
        report["gates"]["lexical_margin"] = sweep_gate(per_method["lexical"], "margin", [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    # RRF skorları küçüktür: tek başına 1. sıra 1/61 ≈ 0.0164 katkı verir.
    for name in ("fused", "fused_text"):
        if name in per_method:
            report["gates"][f"{name}_margin"] = sweep_gate(
                per_method[name], "margin", [0.0, 0.001, 0.002, 0.004, 0.008, 0.016]
            )

    # Seçenek boyutu: ilk 3 pozisyonun alt pozisyon sayısı toplamı. Öneri alt
    # pozisyon seviyesini atlayıp yaprakları birleştirecekse bu sayı büyür.
    if sub_counts:
        sizes = [
            sum(sub_counts.get(key, 0) for key in row["top3"])
            for row in per_method["fused"] if row["top3"]
        ]
        if sizes:
            ordered = sorted(sizes)
            report["fused_top3_subheading_options"] = {
                "median": ordered[len(ordered) // 2],
                "p90": ordered[int(len(ordered) * 0.9)],
                "max": ordered[-1],
            }

    # LLM ağaç dolaşımıyla numune bazlı karşılaştırma.
    if traversal:
        fused_by_ref = {row["reference_no"]: row for row in per_method["fused"]}
        groups: Dict[str, List[Optional[int]]] = collections.defaultdict(list)
        for ref, sample in traversal.items():
            row = fused_by_ref.get(ref)
            if row is None:
                continue
            predicted = _digits(sample.get("predicted_gtip"))
            expected = sample["expected_gtip"]
            if not predicted:
                group = f"traversal_no_code_{sample.get('status')}"
            elif predicted[:2] != expected[:2]:
                group = "traversal_wrong_chapter"
            elif predicted[:4] != expected[:4]:
                group = "traversal_right_chapter_wrong_heading"
            else:
                group = "traversal_right_heading"
            groups[group].append(row["heading_rank"])
        report["vs_traversal"] = {
            group: {"n": len(ranks), "fused_recall@3": recall_at(ranks, 3), "fused_recall@5": recall_at(ranks, 5)}
            for group, ranks in sorted(groups.items())
        }
    return report


def _log_report(report: Dict[str, Any]) -> None:
    logger.info("=== ÖZET ===")
    for item in report["summary"]:
        logger.info(
            "%-8s n=%d kapsam=%%%s  H@1=%s H@3=%s H@5=%s H@10=%s  F@1=%s F@3=%s",
            item["method"], item["n"], item["coverage"],
            item["heading_recall@1"], item["heading_recall@3"], item["heading_recall@5"],
            item["heading_recall@10"], item["chapter_recall@1"], item["chapter_recall@3"],
        )
    for name, table in report.get("gates", {}).items():
        logger.info("--- kapı: %s ---", name)
        for row in table:
            logger.info("  eşik=%-6s geçen=%%%-6s (%d) recall@3=%s",
                        row["threshold"], row["pass_rate"], row["passed"], row.get("recall@3_of_passed"))
    if "fused_top3_subheading_options" in report:
        logger.info("fused ilk 3 pozisyonun alt pozisyon sayısı: %s", report["fused_top3_subheading_options"])
    for group, values in report.get("vs_traversal", {}).items():
        logger.info("dolaşım=%-42s n=%-3d fused R@3=%s R@5=%s",
                    group, values["n"], values["fused_recall@3"], values["fused_recall@5"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Pozisyon yönlendirme deneyi (LLM çağrısı yok)")
    parser.add_argument("--from-report", default=None, help="Numuneleri bu benchmark raporundan al")
    parser.add_argument("--sample", type=int, default=120, help="--from-report yoksa holdout boyutu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dense-model", default=DEFAULT_DENSE_MODEL)
    parser.add_argument("--no-dense", action="store_true", help="Vertex embedding kullanma")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    from scripts.evaluate_gtip_benchmark import RESULTS_DIR, build_holdout, upload_to_gcs

    if args.from_report:
        dataset, traversal = load_dataset_from_report(args.from_report)
    else:
        dataset, traversal = build_holdout(args.sample, args.seed), None
    logger.info("Numune: %d", len(dataset))

    catalog = load_catalog()
    documents = build_heading_documents(catalog)
    logger.info("Pozisyon belgesi: %d", len(documents))

    from api.modules.rag_engine import rag_engine

    bm25 = BM25Index(documents)
    retrievers: Dict[str, Callable[[Dict[str, Any]], Ranking]] = {
        "btb": lambda s: aggregate_precedents_by_heading(
            rag_engine.search_btb_precedents(s["description"], top_k=20, exclude_refs={s["reference_no"]})
        ),
        "lexical": lambda s: bm25.rank(s["description"]),
    }

    if not args.no_dense:
        cache = os.path.join(RESULTS_DIR, "cache", f"heading_vectors-{args.dense_model}.json")
        doc_vectors = embed_documents(documents, args.dense_model, cache)
        query_vectors: Dict[str, List[float]] = {}
        texts = [sample["description"][:DENSE_DOC_CHARS] for sample in dataset]
        for start in range(0, len(texts), 8):
            chunk = dataset[start:start + 8]
            for sample, vector in zip(chunk, _embed_batch(texts[start:start + 8], args.dense_model, "RETRIEVAL_QUERY")):
                query_vectors[sample["reference_no"]] = vector
        retrievers["dense"] = lambda s: dense_rank(query_vectors.get(s["reference_no"], []), doc_vectors)

    started = time.perf_counter()
    report = evaluate(dataset, retrievers, traversal, subheading_counts(catalog))
    report.update({
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_report": args.from_report,
        "dense_model": None if args.no_dense else args.dense_model,
        "elapsed_s": round(time.perf_counter() - started, 1),
    })
    _log_report(report)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or os.path.join(RESULTS_DIR, f"routing-{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    logger.info("Rapor yazıldı: %s", out_path)
    gcs_uri = upload_to_gcs(out_path)
    if gcs_uri:
        logger.info("Rapor GCS'e yüklendi: %s", gcs_uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
