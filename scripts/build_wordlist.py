"""Build a benchmark wordlist by sampling from a real corpus and injecting the
target password at a random position.

Example:

    python scripts/build_wordlist.py \
        --source passwords/raw/SecLists/Common-Credentials/10k-most-common.txt \
        --size 200 --target password123 --seed 7 \
        --output login-lab/wordlists/trial_007.txt

Behaviour:
* Reads the source wordlist line-by-line, ignoring blanks and comments.
* If `--size` is smaller than the source, samples without replacement.
* Drops the target password if it appears in the sample (so the only hit is the
  one we inject).
* Inserts the target at a uniformly-random position in the sampled list.
* Writes the result and a sidecar `<output>.meta.json` describing the seed,
  source, target, and target position.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def read_corpus(path: Path) -> list[str]:
    out: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            word = line.strip()
            if not word or word.startswith("#"):
                continue
            out.append(word)
    return out


def build(source: Path, size: int, target: str, seed: int, output: Path) -> dict:
    rng = random.Random(seed)
    corpus = read_corpus(source)
    if not corpus:
        raise SystemExit(f"empty corpus: {source}")

    pool = [w for w in corpus if w != target]
    sample_size = min(size - 1, len(pool))  # leave a slot for the injected target
    sample = rng.sample(pool, sample_size)

    insert_at = rng.randint(0, sample_size)  # 0..sample_size inclusive
    sample.insert(insert_at, target)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        for word in sample:
            f.write(word + "\n")

    meta = {
        "source": str(source),
        "size": len(sample),
        "target": target,
        "target_position_1based": insert_at + 1,
        "seed": seed,
        "output": str(output),
    }
    meta_path = output.with_suffix(output.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--size", type=int, default=200)
    ap.add_argument("--target", type=str, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    meta = build(args.source, args.size, args.target, args.seed, args.output)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
