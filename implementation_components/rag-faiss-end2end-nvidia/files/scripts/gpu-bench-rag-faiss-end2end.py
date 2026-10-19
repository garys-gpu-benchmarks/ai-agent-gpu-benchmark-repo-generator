#!/usr/bin/env python3
"""End-to-end squad_v2 + FAISS retrieve + BGE rerank + Mistral-7B RAG."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from threading import Thread

import numpy as np
import torch
from transformers import AutoModel, AutoModelForCausalLM, AutoModelForSequenceClassification, AutoTokenizer, TextIteratorStreamer

from prefetch_rag_models import ensure_mistral
from rag_model_paths import find_local_causal_lm, reject_missing_causal_weights


DEFAULTS = {
    "corpus_dataset": "rajpurkar/squad_v2",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "vector_db": "faiss",
    "llm_model": "mistralai/Mistral-7B-v0.3",
    "reranker_model": "BAAI/bge-reranker-base",
    "retrieval_strategy": "dense",
}
PLACEHOLDERS = {"", "true", "false", "none", "yes", "1", "local"}


def first_int(value: object, default: int) -> int:
    text = str(value).split(",")[0].strip()
    try:
        if text.lower() in {"", "true", "yes", "none"}:
            return default
        return max(1, int(float(text)))
    except (TypeError, ValueError):
        return default


def resolve_name(value: object, key: str) -> str:
    text = str(value or "").strip()
    if text.lower() in PLACEHOLDERS:
        return DEFAULTS[key]
    return text


def mean_pool(last_hidden: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.unsqueeze(-1).to(last_hidden.dtype)
    summed = (last_hidden * weights).sum(dim=1)
    denom = weights.sum(dim=1).clamp(min=1e-6)
    return torch.nn.functional.normalize(summed / denom, p=2, dim=1)


def _use_private_nltk_data() -> None:
    """Select a single-link copy of LlamaIndex's bundled NLTK stopwords.

    SentenceSplitter refuses a stopword file whose link count is greater than
    one. A hard-linked install then falls back to word chunks, and the numeric
    chunk_backend value 0 fails validation.
    """
    import importlib.util
    import os
    import shutil

    spec = importlib.util.find_spec("llama_index.core")
    if spec is None or not spec.submodule_search_locations:
        return
    bundled = Path(next(iter(spec.submodule_search_locations))) / "_static" / "nltk_cache"
    if not bundled.is_dir():
        return
    dest = Path.cwd() / ".cache" / "nltk_data"
    english = dest / "corpora" / "stopwords" / "english"
    if (not english.is_file()) or english.stat().st_nlink > 1:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled, dest)
    os.environ["NLTK_DATA"] = str(dest.resolve())


def chunk_with_llamaindex(texts: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    _use_private_nltk_data()
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = splitter.get_nodes_from_documents([Document(text=text) for text in texts if text.strip()])
    chunks = [node.get_content().strip() for node in nodes if node.get_content().strip()]
    if not chunks:
        raise RuntimeError("LlamaIndex produced no chunks")
    return chunks


def chunk_by_words(texts: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    step = max(1, chunk_size - chunk_overlap)
    chunks: list[str] = []
    for text in texts:
        words = text.split()
        if not words:
            continue
        for start in range(0, len(words), step):
            piece = words[start : start + chunk_size]
            if piece:
                chunks.append(" ".join(piece))
            if start + chunk_size >= len(words):
                break
    return chunks


def load_squad(dataset_id: str, query_count: int) -> tuple[list[str], list[str]]:
    from datasets import load_dataset

    aliases = (dataset_id, "rajpurkar/squad_v2", "squad_v2")
    last_error: Exception | None = None
    dataset = None
    for name in dict.fromkeys(aliases):
        try:
            dataset = load_dataset(name, split="validation")
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if dataset is None:
        raise RuntimeError(f"Failed to load squad_v2 ({dataset_id}): {last_error}")

    contexts: list[str] = []
    seen: set[str] = set()
    questions: list[str] = []
    corpus_target = 64 if query_count <= 2 else 400 if query_count <= 100 else 800
    for row in dataset:
        context = str(row.get("context") or "").strip()
        question = str(row.get("question") or "").strip()
        if context and context not in seen and len(contexts) < corpus_target:
            seen.add(context)
            contexts.append(context)
        if question and len(questions) < query_count:
            questions.append(question)
        if len(contexts) >= corpus_target and len(questions) >= query_count:
            break
    if not contexts or not questions:
        raise RuntimeError("squad_v2 did not yield contexts and questions")
    while len(questions) < query_count:
        questions.append(questions[len(questions) % len(questions)])
    return contexts, questions[:query_count]


def encode_texts(model, tokenizer, texts: list[str], device: torch.device, batch_size: int, max_length: int) -> np.ndarray:
    vectors: list[np.ndarray] = []
    model.eval()
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        encoded = tokenizer(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            hidden = model(**encoded).last_hidden_state
            pooled = mean_pool(hidden, encoded["attention_mask"])
        vectors.append(pooled.detach().float().cpu().numpy())
    return np.vstack(vectors).astype("float32")


def rerank(model, tokenizer, query: str, passages: list[str], device: torch.device, keep: int) -> list[str]:
    if not passages:
        return []
    encoded = tokenizer(
        [query] * len(passages),
        passages,
        padding=True,
        truncation=True,
        max_length=256,
        return_tensors="pt",
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.no_grad():
        scores = model(**encoded).logits.view(-1)
    order = torch.argsort(scores, descending=True).tolist()
    return [passages[index] for index in order[:keep]]


def generate_answer(
    model,
    tokenizer,
    prompt: str,
    device: torch.device,
    max_new_tokens: int,
) -> tuple[float, float, int]:
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1536)
    inputs = {key: value.to(device) for key, value in inputs.items()}
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    generated: dict[str, torch.Tensor] = {}

    def _run() -> None:
        generated["sequences"] = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            streamer=streamer,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    start = time.perf_counter()
    thread = Thread(target=_run, daemon=True)
    thread.start()
    first_token_at: float | None = None
    for piece in streamer:
        if first_token_at is None and str(piece).strip():
            first_token_at = time.perf_counter()
    thread.join()
    torch.cuda.synchronize()
    stop = time.perf_counter()
    sequences = generated["sequences"]
    new_tokens = int(sequences.shape[-1] - inputs["input_ids"].shape[-1])
    ttft_ms = ((first_token_at or stop) - start) * 1000.0
    gen_ms = (stop - start) * 1000.0
    return ttft_ms, gen_ms, max(new_tokens, 0)


def build_prompt(query: str, passages: list[str], query_length: int) -> str:
    clipped = " ".join(query.split()[:query_length])
    context = "\n\n".join(passages)
    return (
        "Use the context to answer the question with a short factual reply.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {clipped}\n"
        "Answer:"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--corpus-dataset", dest="corpus_dataset", default=DEFAULTS["corpus_dataset"])
    parser.add_argument("--chunk-size", dest="chunk_size", default="256")
    parser.add_argument("--chunk-overlap", dest="chunk_overlap", default="32")
    parser.add_argument("--embedding-model", dest="embedding_model", default=DEFAULTS["embedding_model"])
    parser.add_argument("--vector-db", dest="vector_db", default=DEFAULTS["vector_db"])
    parser.add_argument("--llm-model", dest="llm_model", default=DEFAULTS["llm_model"])
    parser.add_argument("--reranker-model", dest="reranker_model", default=DEFAULTS["reranker_model"])
    parser.add_argument("--retrieval-strategy", dest="retrieval_strategy", default=DEFAULTS["retrieval_strategy"])
    parser.add_argument("--top-k", dest="top_k", default="5")
    parser.add_argument("--query-length", dest="query_length", default="32")
    parser.add_argument("--batch-size", dest="batch_size", default="8")
    parser.add_argument("--query-count", dest="query_count", default="100")
    parser.add_argument("--max-new-tokens", dest="max_new_tokens", default="")
    parser.add_argument("--output-format", default="")
    args, _unknown = parser.parse_known_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = resolve_name(args.corpus_dataset, "corpus_dataset")
    embedding_id = resolve_name(args.embedding_model, "embedding_model")
    llm_id = resolve_name(args.llm_model, "llm_model")
    reranker_id = resolve_name(args.reranker_model, "reranker_model")
    vector_db = resolve_name(args.vector_db, "vector_db")
    strategy = resolve_name(args.retrieval_strategy, "retrieval_strategy")
    chunk_size = first_int(args.chunk_size, 256)
    chunk_overlap = first_int(args.chunk_overlap, 32)
    top_k = first_int(args.top_k, 5)
    query_length = first_int(args.query_length, 32)
    batch_size = first_int(args.batch_size, 8)
    query_count = first_int(args.query_count, 2)
    max_new_tokens = first_int(args.max_new_tokens, 16 if query_count <= 2 else 64)
    retrieve_k = max(top_k * 4, top_k)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise SystemExit("[FAIL] CUDA is required for this RAG benchmark")

    print(f"[INFO] corpus={dataset_id} embed={embedding_id} llm={llm_id} rerank={reranker_id}", flush=True)
    print(f"[INFO] vector_db={vector_db} strategy={strategy} queries={query_count} top_k={top_k}", flush=True)

    contexts, questions = load_squad(dataset_id, query_count)
    try:
        chunks = chunk_with_llamaindex(contexts, chunk_size, chunk_overlap)
        chunk_backend = "llamaindex"
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] LlamaIndex chunking fallback: {exc}", flush=True)
        chunks = chunk_by_words(contexts, chunk_size, chunk_overlap)
        chunk_backend = "words"
    if not chunks:
        raise RuntimeError("no document chunks")

    embed_tok = AutoTokenizer.from_pretrained(embedding_id)
    embed_model = AutoModel.from_pretrained(embedding_id).to(device)
    embed_start = time.perf_counter()
    doc_vectors = encode_texts(embed_model, embed_tok, chunks, device, batch_size=min(32, max(batch_size, 8)), max_length=512)
    torch.cuda.synchronize()
    embed_s = time.perf_counter() - embed_start
    embedding_throughput = len(chunks) / max(embed_s, 1e-9)

    try:
        import faiss
    except ImportError as exc:
        raise SystemExit("[FAIL] faiss is not installed") from exc
    if "faiss" not in vector_db.lower() and vector_db.lower() not in PLACEHOLDERS:
        print(f"[WARN] vector_db={vector_db} requested; using FAISS IndexFlatIP", flush=True)
    index = faiss.IndexFlatIP(int(doc_vectors.shape[1]))
    index.add(doc_vectors)
    index_ntotal = int(index.ntotal)

    rerank_tok = AutoTokenizer.from_pretrained(reranker_id)
    rerank_model = AutoModelForSequenceClassification.from_pretrained(reranker_id).to(device).eval()
    # consolidated.safetensors is not loadable. Download the Hugging Face shards
    # before local_files_only can pin a snapshot that only has the original file.
    ensure_mistral(llm_id)
    local_llm = find_local_causal_lm(llm_id)
    llm_source = str(local_llm or llm_id)
    local_only = local_llm is not None
    print(f"[INFO] llm_source={llm_source} local_only={local_only}", flush=True)
    llm_tok = AutoTokenizer.from_pretrained(llm_source, local_files_only=local_only)
    if llm_tok.pad_token_id is None:
        llm_tok.pad_token = llm_tok.eos_token
    llm, loading_info = AutoModelForCausalLM.from_pretrained(
        llm_source,
        torch_dtype=torch.bfloat16,
        local_files_only=local_only,
        output_loading_info=True,
    )
    reject_missing_causal_weights(loading_info)
    llm = llm.to(device).eval()

    warmup_n = 1 if query_count > 1 else 0
    e2e_acc = retrieve_acc = ttft_acc = gen_ms_acc = 0.0
    tokens_acc = 0
    measured = 0
    query_rows: list[dict[str, object]] = []

    for index_q, question in enumerate(questions):
        query_text = " ".join(question.split()[:query_length])
        q_start = time.perf_counter()
        q_vec = encode_texts(embed_model, embed_tok, [query_text], device, batch_size=1, max_length=64)
        retrieve_start = time.perf_counter()
        _scores, ids = index.search(q_vec, min(retrieve_k, len(chunks)))
        retrieved = [chunks[int(item)] for item in ids[0] if int(item) >= 0]
        retrieve_ms = (time.perf_counter() - retrieve_start) * 1000.0
        passages = rerank(rerank_model, rerank_tok, query_text, retrieved, device, top_k)
        prompt = build_prompt(query_text, passages, query_length)
        ttft_ms, gen_ms, n_tokens = generate_answer(llm, llm_tok, prompt, device, max_new_tokens)
        torch.cuda.synchronize()
        e2e_ms = (time.perf_counter() - q_start) * 1000.0
        row = {
            "query_index": index_q,
            "end_to_end_query_latency_retrieval_generation_ms": e2e_ms,
            "generation_phase_time_to_first_token_ms": ttft_ms,
            "retrieval_latency_vector_search_ms": retrieve_ms,
            "generation_tokens": n_tokens,
            "generation_ms": gen_ms,
        }
        query_rows.append(row)
        print(
            f"[INFO] q{index_q} e2e={e2e_ms:.1f}ms ttft={ttft_ms:.1f}ms retrieve={retrieve_ms:.1f}ms tokens={n_tokens}",
            flush=True,
        )
        if index_q < warmup_n:
            continue
        e2e_acc += e2e_ms
        retrieve_acc += retrieve_ms
        ttft_acc += ttft_ms
        gen_ms_acc += gen_ms
        tokens_acc += n_tokens
        measured += 1

    measured = max(measured, 1)
    e2e_values = [
        float(row["end_to_end_query_latency_retrieval_generation_ms"])
        for row in query_rows
        if int(row["query_index"]) >= warmup_n
    ] or [float(row["end_to_end_query_latency_retrieval_generation_ms"]) for row in query_rows]
    ordered_e2e = sorted(e2e_values)

    def _pct(q: float) -> float:
        pos = (len(ordered_e2e) - 1) * q
        low = int(pos)
        high = min(low + 1, len(ordered_e2e) - 1)
        return ordered_e2e[low] + (ordered_e2e[high] - ordered_e2e[low]) * (pos - low)

    latest = {
        "end_to_end_query_latency_retrieval_generation_ms": e2e_acc / measured,
        "end_to_end_query_latency_p50_ms": _pct(0.50),
        "end_to_end_query_latency_p95_ms": (
            _pct(0.95) if len(e2e_values) >= 20
            else f"na (p95 requires at least 20 samples; n={len(e2e_values)})"
        ),
        "query_sample_count": float(len(e2e_values)),
        "headline_rule": "mean_over_queries",
        "headline_point": f"mean_over_queries n={len(e2e_values)}",
        "generation_phase_time_to_first_token_ms": ttft_acc / measured,
        "retrieval_latency_vector_search_ms": retrieve_acc / measured,
        "faiss_index_ntotal": float(index_ntotal),
        "generation_throughput_output_tokens_s": tokens_acc / max(gen_ms_acc / 1000.0, 1e-9),
        "embedding_throughput_docs_s": embedding_throughput,
        "index_backend": 1.0,
        "corpus_docs": float(len(contexts)),
        "chunk_count": float(len(chunks)),
        "query_count": float(query_count),
        "chunk_overlap": float(chunk_overlap),
    }
    rows = [{"check_name": "pass1", **latest}, {"check_name": "pass2", **latest}, {"check_name": "summary", **latest}]
    with (run_dir / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check_name", *latest.keys()])
        writer.writeheader()
        writer.writerows(rows)
    with (run_dir / "queries.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(query_rows[0].keys()))
        writer.writeheader()
        writer.writerows(query_rows)
    summary = {
        "check_name": "summary",
        **latest,
        "embedding_model": embedding_id,
        "llm_model": llm_id,
        "reranker_model": reranker_id,
        "corpus_dataset": dataset_id,
        "vector_db": "faiss",
        "retrieval_strategy": strategy,
        "chunk_backend": chunk_backend,
    }
    (run_dir / "raw_output.txt").write_text("SUMMARY " + json.dumps(summary) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
