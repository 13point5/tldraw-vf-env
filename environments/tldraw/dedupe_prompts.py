import argparse
import asyncio
import ast
import csv
import json
import math
import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tqdm import tqdm

load_dotenv()


def normalize_prompt(text: str) -> str:
    """Normalize text for exact-match style dedupe."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text


def _extract_prompt_from_record(record: dict, prompt_field: str) -> str:
    value = record.get(prompt_field, "")
    if value is None:
        return ""
    return str(value).strip()


def load_prompts(path: str, prompt_field: str = "prompt") -> List[str]:
    """Load prompts from .jsonl, .json, .txt, or .csv."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".jsonl":
        prompts = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # Fallback for lines written as Python dict repr.
                    record = ast.literal_eval(line)
                if isinstance(record, dict):
                    prompt = _extract_prompt_from_record(record, prompt_field)
                    if prompt:
                        prompts.append(prompt)
                elif isinstance(record, str):
                    prompts.append(record.strip())
        return prompts

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            prompts = []
            for item in data:
                if isinstance(item, dict):
                    prompt = _extract_prompt_from_record(item, prompt_field)
                    if prompt:
                        prompts.append(prompt)
                elif isinstance(item, str):
                    prompts.append(item.strip())
            return prompts
        raise ValueError("JSON input must be a list of strings or objects")

    if ext == ".csv":
        prompts = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                prompt = _extract_prompt_from_record(row, prompt_field)
                if prompt:
                    prompts.append(prompt)
        return prompts

    # Default: plain text, one prompt per line.
    prompts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                prompts.append(text)
    return prompts


def find_exact_match_groups(
    prompts: Sequence[str], *, normalized: bool = False
) -> Dict[str, List[int]]:
    """Group duplicate prompts by exact or normalized exact key."""
    groups: Dict[str, List[int]] = defaultdict(list)
    for idx, prompt in enumerate(prompts):
        key = normalize_prompt(prompt) if normalized else prompt
        groups[key].append(idx)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _l2_normalize(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [x / norm for x in vector]


async def _embed_batch(
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    *,
    model: str,
    batch_index: int,
    prompts_batch: Sequence[str],
) -> Tuple[int, List[List[float]]]:
    async with semaphore:
        response = await client.embeddings.create(model=model, input=list(prompts_batch))
    vectors = [_l2_normalize(item.embedding) for item in response.data]
    return batch_index, vectors


async def get_openai_embeddings(
    prompts: Sequence[str],
    *,
    model: str,
    batch_size: int = 128,
    concurrency: int = 8,
) -> List[List[float]]:
    """Fetch embeddings from OpenAI in parallel batches."""
    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(concurrency)

    batches: List[Tuple[int, Sequence[str]]] = []
    for i in range(0, len(prompts), batch_size):
        batch_index = i // batch_size
        batches.append((batch_index, prompts[i : i + batch_size]))

    tasks = [
        asyncio.create_task(
            _embed_batch(
                client,
                semaphore,
                model=model,
                batch_index=batch_index,
                prompts_batch=prompts_batch,
            )
        )
        for batch_index, prompts_batch in batches
    ]

    ordered: List[Optional[List[List[float]]]] = [None] * len(batches)
    try:
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Embedding batches"):
            batch_index, batch_vectors = await coro
            ordered[batch_index] = batch_vectors
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.close()

    vectors: List[List[float]] = []
    for batch_vectors in ordered:
        if batch_vectors is None:
            raise RuntimeError("Missing embedding batch result")
        vectors.extend(batch_vectors)
    return vectors


def find_cosine_duplicates_bruteforce(
    prompts: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    *,
    threshold: float,
) -> List[Tuple[float, int, int]]:
    """Brute-force all pairs and keep those above threshold."""
    if len(prompts) != len(embeddings):
        raise ValueError("prompts and embeddings length mismatch")

    pairs: List[Tuple[float, int, int]] = []
    total = len(prompts)
    for i in tqdm(range(total), desc="Pairwise cosine"):
        vi = embeddings[i]
        for j in range(i + 1, total):
            vj = embeddings[j]
            score = sum(a * b for a, b in zip(vi, vj))
            if score >= threshold:
                pairs.append((score, i, j))
    pairs.sort(key=lambda x: x[0], reverse=True)
    return pairs


def write_exact_report_md(
    path: str,
    title: str,
    groups: Dict[str, List[int]],
    prompts: Sequence[str],
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"Duplicate groups: {len(groups)}\n\n")
        group_items = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
        for gid, (_, indices) in enumerate(group_items, start=1):
            f.write(f"## Group {gid} (count={len(indices)})\n")
            for idx in indices:
                f.write(f"- idx {idx}: {prompts[idx]}\n")
            f.write("\n")


def write_exact_report_csv(
    path: str,
    groups: Dict[str, List[int]],
    prompts: Sequence[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["group_id", "idx", "prompt"])
        group_items = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
        for gid, (_, indices) in enumerate(group_items, start=1):
            for idx in indices:
                writer.writerow([gid, idx, prompts[idx]])


def write_cosine_report_md(
    path: str,
    pairs: Sequence[Tuple[float, int, int]],
    prompts: Sequence[str],
    *,
    threshold: float,
    max_pairs: int,
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Semantic Near-Duplicate Report (Cosine)\n\n")
        f.write(f"Threshold: {threshold}\n\n")
        f.write(f"Pairs found: {len(pairs)}\n\n")
        shown = pairs[:max_pairs]
        f.write(f"Showing top {len(shown)} pairs by similarity.\n\n")
        for k, (score, i, j) in enumerate(shown, start=1):
            f.write(f"## Pair {k} (score={score:.4f})\n")
            f.write(f"- idx {i}: {prompts[i]}\n")
            f.write(f"- idx {j}: {prompts[j]}\n\n")


def write_cosine_report_csv(
    path: str,
    pairs: Sequence[Tuple[float, int, int]],
    prompts: Sequence[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["score", "idx_a", "idx_b", "prompt_a", "prompt_b"])
        for score, i, j in pairs:
            writer.writerow([f"{score:.6f}", i, j, prompts[i], prompts[j]])


async def run(
    input_path: str,
    output_dir: str,
    prompt_field: str,
    embedding_model: str,
    threshold: float,
    batch_size: int,
    embedding_concurrency: int,
    max_pairs_in_md: int,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    prompts = load_prompts(input_path, prompt_field=prompt_field)
    if not prompts:
        raise ValueError(f"No prompts found in {input_path}")

    raw_exact_task = asyncio.to_thread(find_exact_match_groups, prompts, normalized=False)
    norm_exact_task = asyncio.to_thread(find_exact_match_groups, prompts, normalized=True)
    raw_exact, norm_exact = await asyncio.gather(raw_exact_task, norm_exact_task)

    write_exact_report_md(
        os.path.join(output_dir, "exact_duplicates_raw.md"),
        "Exact Duplicate Report (Raw String)",
        raw_exact,
        prompts,
    )
    write_exact_report_csv(
        os.path.join(output_dir, "exact_duplicates_raw.csv"),
        raw_exact,
        prompts,
    )

    write_exact_report_md(
        os.path.join(output_dir, "exact_duplicates_normalized.md"),
        "Exact Duplicate Report (Normalized String)",
        norm_exact,
        prompts,
    )
    write_exact_report_csv(
        os.path.join(output_dir, "exact_duplicates_normalized.csv"),
        norm_exact,
        prompts,
    )

    embeddings = await get_openai_embeddings(
        prompts,
        model=embedding_model,
        batch_size=batch_size,
        concurrency=embedding_concurrency,
    )
    semantic_pairs = await asyncio.to_thread(
        find_cosine_duplicates_bruteforce,
        prompts,
        embeddings,
        threshold=threshold,
    )

    write_cosine_report_md(
        os.path.join(output_dir, "semantic_duplicates.md"),
        semantic_pairs,
        prompts,
        threshold=threshold,
        max_pairs=max_pairs_in_md,
    )
    write_cosine_report_csv(
        os.path.join(output_dir, "semantic_duplicates.csv"),
        semantic_pairs,
        prompts,
    )

    with open(os.path.join(output_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(f"Input prompts: {len(prompts)}\n")
        f.write(f"Raw exact duplicate groups: {len(raw_exact)}\n")
        f.write(f"Normalized exact duplicate groups: {len(norm_exact)}\n")
        f.write(f"Cosine threshold: {threshold}\n")
        f.write(f"Semantic duplicate pairs: {len(semantic_pairs)}\n")
        f.write(f"Embedding model: {embedding_model}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find duplicate prompts via exact match and cosine similarity."
    )
    parser.add_argument("--input", default="prompts.jsonl", help="Input file path")
    parser.add_argument("--output-dir", default="duplicate_reports", help="Output dir")
    parser.add_argument("--prompt-field", default="prompt", help="Prompt field name")
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.92,
        help="Cosine similarity threshold",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Embedding batch size",
    )
    parser.add_argument(
        "--embedding-concurrency",
        type=int,
        default=8,
        help="Number of concurrent embedding requests",
    )
    parser.add_argument(
        "--max-pairs-in-md",
        type=int,
        default=200,
        help="Max number of semantic pairs to include in markdown report",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run(
            input_path=args.input,
            output_dir=args.output_dir,
            prompt_field=args.prompt_field,
            embedding_model=args.embedding_model,
            threshold=args.threshold,
            batch_size=args.batch_size,
            embedding_concurrency=args.embedding_concurrency,
            max_pairs_in_md=args.max_pairs_in_md,
        )
    )
