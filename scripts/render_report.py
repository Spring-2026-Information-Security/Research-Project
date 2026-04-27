"""Render the benchmark report: matplotlib PNG charts + an HTML summary.

Usage:

    python scripts/render_report.py login-lab/logs/benchmark/<stamp>/summary.json

Produces, alongside the JSON:
  * chart_verdict.png       - found-rate per config (across trials)
  * chart_elapsed.png       - median wall-clock time per attack with min/max range
  * chart_request_rate.png  - effective requests/second per attack (median)
  * chart_status_mix.png    - aggregate response status counts across trials
  * chart_first_hit.png     - median first-success attempt # per config that broke through
  * chart_position_vs_time.png - scatter of target wordlist position vs time-to-crack
  * report.html             - HTML overview embedding the charts
  * report.md               - markdown overview
"""

from __future__ import annotations

import html
import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


COLORS = {
    "found_full": "#d33636",     # 100% breached
    "found_partial": "#e8a13a",  # some trials breached
    "blocked": "#2d8f5a",        # 0% breached
    "elapsed": "#a657d8",
    "rate": "#3d7bd8",
    "401": "#bbbbbb",
    "423": "#d33636",
    "429": "#e8a13a",
    "403": "#7b2eb8",
    "pow": "#3d7bd8",
    "captcha": "#2dab8f",
    "200": "#111111",
}


def verdict_color(success_rate: float) -> str:
    if success_rate >= 0.999:
        return COLORS["found_full"]
    if success_rate <= 0.001:
        return COLORS["blocked"]
    return COLORS["found_partial"]


def short_label(r: dict) -> str:
    return r["name"]


# ── individual charts ──────────────────────────────────────────────────────


def chart_verdict(results: list[dict], out_path: Path) -> None:
    labels = [short_label(r) for r in results]
    rates = [r["success_rate"] * 100 for r in results]
    colors = [verdict_color(r["success_rate"]) for r in results]
    n_trials = max((len(r["trials"]) for r in results), default=1)

    fig, ax = plt.subplots(figsize=(11, max(4, 0.36 * len(results))))
    bars = ax.barh(labels, rates, color=colors, edgecolor="white")
    ax.set_xlim(0, 110)
    ax.set_xlabel(f"% of trials where the attacker found the password (n={n_trials} trials per config)")
    ax.set_title("Breach rate per config")
    ax.invert_yaxis()
    for bar, value in zip(bars, rates):
        ax.text(
            bar.get_width() + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.0f}%",
            va="center",
            fontsize=10,
            color="#222",
        )
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def chart_elapsed(results: list[dict], out_path: Path) -> None:
    labels = [short_label(r) for r in results]
    medians = [r["median_elapsed_seconds"] for r in results]
    mins = [r["min_elapsed_seconds"] for r in results]
    maxes = [r["max_elapsed_seconds"] for r in results]
    colors = [verdict_color(r["success_rate"]) for r in results]
    err_lo = [med - lo for med, lo in zip(medians, mins)]
    err_hi = [hi - med for hi, med in zip(maxes, medians)]

    fig, ax = plt.subplots(figsize=(11, max(4, 0.36 * len(results))))
    bars = ax.barh(labels, medians, color=colors, edgecolor="white")
    ax.errorbar(
        medians,
        labels,
        xerr=[err_lo, err_hi],
        fmt="none",
        ecolor="#333",
        elinewidth=1,
        capsize=4,
    )
    ax.invert_yaxis()
    ax.set_xlabel("seconds (bar = median, whiskers = min/max across trials)")
    ax.set_title("Wall-clock duration of attack")
    max_x = max(maxes) if maxes else 1.0
    for bar, med, lo, hi in zip(bars, medians, mins, maxes):
        ax.text(
            max(bar.get_width(), hi) + max_x * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{med:.1f}s",
            va="center",
            fontsize=9,
            color="#333",
        )
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def chart_request_rate(results: list[dict], out_path: Path) -> None:
    labels = [short_label(r) for r in results]
    rates = [r["median_requests_per_second"] for r in results]
    fig, ax = plt.subplots(figsize=(11, max(4, 0.36 * len(results))))
    bars = ax.barh(labels, rates, color=COLORS["rate"], edgecolor="white")
    ax.invert_yaxis()
    ax.set_xlabel("median requests / second (lower = defense throttled the attacker more)")
    ax.set_title("Effective attacker request rate")
    max_x = max(rates) if rates else 1.0
    for bar, value in zip(bars, rates):
        ax.text(
            bar.get_width() + max_x * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}",
            va="center",
            fontsize=9,
            color="#333",
        )
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def aggregate_status_counts(result: dict) -> dict[str, float]:
    """Mean per-trial counts for stacked-bar visualization."""
    fields = [
        "invalid_credentials",
        "blocked_423",
        "blocked_429",
        "pow_required",
        "captcha_required",
        "blocked_403",
        "successes",
    ]
    out = {f: 0.0 for f in fields}
    if not result["trials"]:
        return out
    n = len(result["trials"])
    for trial in result["trials"]:
        for f in fields:
            out[f] += trial[f]
    for f in fields:
        out[f] /= n
    return out


def chart_status_mix(results: list[dict], out_path: Path) -> None:
    labels = [short_label(r) for r in results]
    series = [
        ("401 invalid", "invalid_credentials", COLORS["401"]),
        ("423 account locked", "blocked_423", COLORS["423"]),
        ("429 rate limited", "blocked_429", COLORS["429"]),
        ("429 PoW required", "pow_required", COLORS["pow"]),
        ("429 CAPTCHA", "captcha_required", COLORS["captcha"]),
        ("403 banned/anomaly", "blocked_403", COLORS["403"]),
        ("200 success", "successes", COLORS["200"]),
    ]
    aggregated = [aggregate_status_counts(r) for r in results]
    fig, ax = plt.subplots(figsize=(11, max(4, 0.36 * len(results))))
    left = [0.0] * len(results)
    for name, field, color in series:
        widths = [agg[field] for agg in aggregated]
        ax.barh(labels, widths, left=left, color=color, label=name, edgecolor="white", linewidth=0.5)
        left = [a + b for a, b in zip(left, widths)]
    ax.invert_yaxis()
    ax.set_xlabel("response count (mean per trial)")
    ax.set_title("Response status mix per config")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def chart_first_hit(results: list[dict], wordlist_size: int, out_path: Path) -> None:
    """Per-trial strip plot: every successful trial gets its own dot.

    For each config that breached at least once, plot each trial's first-success
    position as a colored dot. Trials that didn't break through are shown as a
    grey 'X' at the trial's target position (so you can see WHERE it was when
    the defense stopped the attacker). A small median tick marks the centre.
    """
    rows = [r for r in results if any(t["successes"] for t in r["trials"]) or r["trials"]]
    # We want every config that has trials, even if none breached, so the chart
    # is comparable. But we need to render successes vs failures differently.
    rows = [r for r in results if r["trials"]]
    if not rows:
        return
    labels = [short_label(r) for r in rows]
    fig, ax = plt.subplots(figsize=(11, max(3.5, 0.45 * len(rows))))

    rng = __import__("random").Random(0)  # deterministic jitter
    plotted_breach = False
    plotted_block = False

    for y, r in enumerate(rows):
        success_positions = []
        fail_positions = []
        for t in r["trials"]:
            if t["successes"] and t["first_success_attempt"] is not None:
                success_positions.append(t["first_success_attempt"])
            else:
                fail_positions.append(t["target_position"])
        sx = success_positions
        sy = [y + rng.uniform(-0.12, 0.12) for _ in sx]
        fx = fail_positions
        fy = [y + rng.uniform(-0.12, 0.12) for _ in fx]
        if sx:
            ax.scatter(
                sx, sy,
                color=COLORS["found_full"], s=70, edgecolor="white", zorder=3,
                label="breached (attacker found pwd)" if not plotted_breach else None,
            )
            plotted_breach = True
        if fx:
            ax.scatter(
                fx, fy,
                color="#888", s=70, marker="x", linewidths=2, zorder=3,
                label="blocked (pwd was here, defense stopped it)" if not plotted_block else None,
            )
            plotted_block = True
        if success_positions:
            med = sorted(success_positions)[len(success_positions) // 2]
            ax.plot([med, med], [y - 0.32, y + 0.32], color="#111", linewidth=2.5, zorder=4)

    ax.set_yticks(range(len(rows)), labels=labels)
    ax.invert_yaxis()
    ax.set_xlim(0, wordlist_size + 2)
    ax.set_xlabel(f"attempt # in the wordlist (size {wordlist_size})  -  one dot per trial")
    ax.set_title("Per-trial outcome by wordlist position\nred = attacker found pwd here · grey X = pwd was here but defense blocked · black tick = median")
    ax.grid(True, axis="x", linestyle="--", alpha=0.4)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def chart_position_vs_time(results: list[dict], out_path: Path) -> None:
    """Scatter: wordlist position of target vs time to crack, per trial.

    Shows how the time-to-crack scales with target depth across trials.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    drew = False
    cmap = plt.colormaps["tab20"]
    for i, r in enumerate(results):
        positions = [t["target_position"] for t in r["trials"] if t["successes"]]
        elapsed = [t["elapsed_seconds"] for t in r["trials"] if t["successes"]]
        if not positions:
            continue
        drew = True
        ax.scatter(
            positions,
            elapsed,
            label=r["name"],
            color=cmap(i % 20),
            s=50,
            edgecolor="white",
        )
    if not drew:
        plt.close(fig)
        return
    ax.set_xlabel("target password position in wordlist")
    ax.set_ylabel("time to crack (seconds)")
    ax.set_title("Target position vs time to crack (one dot per successful trial)")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="best", fontsize=8, ncol=2, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ── HTML/MD report ──────────────────────────────────────────────────────────


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def suite_total(payload: dict) -> tuple[float, int, str]:
    """Return (total_seconds, total_trials, source) — falls back to summing
    trial elapsed_seconds when the runner did not record total wall-clock.
    """
    if "suite_total_seconds" in payload:
        total = payload["suite_total_seconds"]
        n = payload.get("total_trials") or sum(len(r["trials"]) for r in payload["results"])
        return float(total), int(n), "wall-clock"
    total = 0.0
    n = 0
    for r in payload["results"]:
        for t in r["trials"]:
            total += t.get("elapsed_seconds", 0.0)
            n += 1
    return total, n, "sum-of-trials (no wall-clock recorded)"


def write_html(payload: dict, run_dir: Path, charts: dict[str, Path]) -> Path:
    results = payload["results"]
    n_trials = payload.get("trials_per_config", 1)
    suite_seconds, total_trials, source = suite_total(payload)
    rows_html = []
    for r in results:
        success_pct = r["success_rate"] * 100
        if success_pct >= 99.9:
            verdict = f"<span class='bad'>compromised ({success_pct:.0f}%)</span>"
        elif success_pct <= 0.1:
            verdict = f"<span class='good'>blocked ({success_pct:.0f}%)</span>"
        else:
            verdict = f"<span class='warn'>partial ({success_pct:.0f}%)</span>"
        med_pos = (
            f"{r['median_first_success']:.0f}" if r["median_first_success"] else "-"
        )
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(r['name'])}</td>"
            f"<td>{html.escape(r['category'])}</td>"
            f"<td>{html.escape(r['description'])}</td>"
            f"<td>{verdict}</td>"
            f"<td>{r['median_elapsed_seconds']:.2f}s</td>"
            f"<td>{r['min_elapsed_seconds']:.1f} .. {r['max_elapsed_seconds']:.1f}</td>"
            f"<td>{r['median_requests_per_second']:.2f}</td>"
            f"<td>{med_pos}</td>"
            f"<td>{len(r['trials'])}</td>"
            "</tr>"
        )

    css = """
    body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 24px auto; padding: 0 20px; color: #222; }
    h1 { font-size: 28px; margin-bottom: 4px; }
    h2 { font-size: 20px; margin-top: 36px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
    h3 { font-size: 17px; margin-top: 24px; }
    .meta { color: #666; font-size: 14px; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px; }
    th, td { padding: 6px 10px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
    th { background: #f5f5f5; }
    .good { color: #2d8f5a; font-weight: 600; }
    .bad  { color: #d33636; font-weight: 600; }
    .warn { color: #c87a00; font-weight: 600; }
    img.chart { max-width: 100%; margin: 12px 0 28px 0; border: 1px solid #eee; border-radius: 4px; }
    code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
    """

    parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>Login lab defense benchmark - {html.escape(payload['timestamp_utc'])}</title>",
        f"<style>{css}</style>",
        "</head><body>",
        "<h1>Login Lab Defense Benchmark</h1>",
        "<p class='meta'>"
        f"Run timestamp (UTC): <code>{html.escape(payload['timestamp_utc'])}</code><br>"
        f"Wordlist source: <code>{html.escape(payload.get('wordlist_source','?'))}</code> "
        f"({payload.get('wordlist_size','?')} entries per generated wordlist)<br>"
        f"Trials per config: <b>{n_trials}</b> (target inserted at random position each trial)<br>"
        f"Base RNG seed: <code>{payload.get('base_seed','?')}</code><br>"
        f"Total suite runtime: <b>{format_duration(suite_seconds)}</b> "
        f"across {total_trials} trials "
        f"(avg {suite_seconds / total_trials:.1f}s/trial; <i>{source}</i>)"
        "</p>",

        "<h2>Verdict matrix</h2>",
        "<table><thead><tr><th>config</th><th>category</th><th>description</th>"
        "<th>verdict (% breached)</th><th>median elapsed</th><th>min..max</th>"
        "<th>median req/s</th><th>median pos</th><th>trials</th></tr></thead><tbody>",
        "\n".join(rows_html),
        "</tbody></table>",

        "<h2>Charts</h2>",
        "<h3>Did the attacker break in? (% of trials breached)</h3>",
        f'<img class="chart" src="{charts["verdict"].name}" alt="verdict chart" />',
    ]
    if "first_hit" in charts:
        parts += [
            "<h3>Where in the wordlist did the password land?</h3>",
            f'<img class="chart" src="{charts["first_hit"].name}" alt="first hit chart" />',
        ]
    parts += [
        "<h3>How long did each attack take? (median, with min/max range)</h3>",
        f'<img class="chart" src="{charts["elapsed"].name}" alt="elapsed chart" />',
        "<h3>How fast could the attacker hit the server?</h3>",
        f'<img class="chart" src="{charts["rate"].name}" alt="rate chart" />',
        "<h3>Where did each request end up? (mean per trial)</h3>",
        f'<img class="chart" src="{charts["mix"].name}" alt="status mix chart" />',
    ]
    if "scatter" in charts:
        parts += [
            "<h3>How does target depth affect time-to-crack?</h3>",
            f'<img class="chart" src="{charts["scatter"].name}" alt="position vs time chart" />',
        ]
    parts += [
        "<h2>Mechanisms in the lab</h2>",
        "<ul>"
        "<li><b>Account lockout</b> - after N consecutive failures, the account is frozen.</li>"
        "<li><b>IP rate limit</b> - caps attempts per IP in a sliding window.</li>"
        "<li><b>Tarpit</b> - artificial server-side sleep on every failed response.</li>"
        "<li><b>IP exponential backoff</b> - per-IP cooldown that doubles with each failure.</li>"
        "<li><b>Proof-of-Work</b> - server demands a SHA-256 puzzle after N failures.</li>"
        "<li><b>Permanent IP ban</b> - blacklist after K failures within a window.</li>"
        "<li><b>CAPTCHA</b> - server demands a human-solvable token after N failures.</li>"
        "<li><b>Slow password hash</b> - pbkdf2 / scrypt to inflate per-attempt CPU cost.</li>"
        "<li><b>Honeypot usernames</b> - contact with watched usernames triggers an instant ban.</li>"
        "<li><b>Anomaly detection</b> - block requests missing typical browser headers.</li>"
        "</ul>",
        "</body></html>",
    ]
    out = run_dir / "report.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


def write_markdown(payload: dict, run_dir: Path, charts: dict[str, Path]) -> Path:
    results = payload["results"]
    n_trials = payload.get("trials_per_config", 1)
    suite_seconds, total_trials, source = suite_total(payload)
    lines = [
        f"# Login Lab Defense Benchmark - {payload['timestamp_utc']}",
        "",
        f"- Wordlist source: `{payload.get('wordlist_source','?')}` "
        f"({payload.get('wordlist_size','?')} entries per generated wordlist)",
        f"- Trials per config: **{n_trials}** (target inserted at random position each trial)",
        f"- Base RNG seed: `{payload.get('base_seed','?')}`",
        f"- Total suite runtime: **{format_duration(suite_seconds)}** "
        f"across {total_trials} trials "
        f"(avg {suite_seconds / total_trials:.1f}s/trial; _{source}_)",
        "",
        "## Verdict matrix",
        "",
        "| config | category | breach % | med elapsed | min..max | med req/s | med pos | trials | description |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        breach = f"{r['success_rate']*100:.0f}%"
        verdict_label = "**COMPROMISED**" if r["success_rate"] >= 0.999 else (
            "**partial**" if r["success_rate"] > 0 else "blocked"
        )
        med_pos = f"{r['median_first_success']:.0f}" if r["median_first_success"] else "-"
        lines.append(
            f"| `{r['name']}` | {r['category']} | {breach} {verdict_label} "
            f"| {r['median_elapsed_seconds']:.2f}s "
            f"| {r['min_elapsed_seconds']:.1f}..{r['max_elapsed_seconds']:.1f} "
            f"| {r['median_requests_per_second']:.2f} | {med_pos} | {len(r['trials'])} "
            f"| {r['description']} |"
        )

    lines += ["", "## Charts", "", f"![verdict]({charts['verdict'].name})", ""]
    if "first_hit" in charts:
        lines += [f"![first hit]({charts['first_hit'].name})", ""]
    lines += [
        f"![elapsed]({charts['elapsed'].name})",
        "",
        f"![request rate]({charts['rate'].name})",
        "",
        f"![status mix]({charts['mix'].name})",
        "",
    ]
    if "scatter" in charts:
        lines += [f"![position vs time]({charts['scatter'].name})", ""]
    lines += [
        "## Mechanisms in the lab",
        "",
        "- **Account lockout** - after N consecutive failures, the account is frozen.",
        "- **IP rate limit** - caps attempts per IP in a sliding window.",
        "- **Tarpit** - artificial server-side sleep on every failed response.",
        "- **IP exponential backoff** - per-IP cooldown that doubles with each failure.",
        "- **Proof-of-Work** - server demands a SHA-256 puzzle after N failures.",
        "- **Permanent IP ban** - blacklist after K failures within a window.",
        "- **CAPTCHA** - server demands a human-solvable token after N failures.",
        "- **Slow password hash** - pbkdf2 / scrypt to inflate per-attempt CPU cost.",
        "- **Honeypot usernames** - contact with watched usernames triggers an instant ban.",
        "- **Anomaly detection** - block requests missing typical browser headers.",
    ]
    out = run_dir / "report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/render_report.py <summary.json>")
    json_path = Path(sys.argv[1]).resolve()
    if not json_path.exists():
        sys.exit(f"file not found: {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    results = payload["results"]
    run_dir = json_path.parent

    charts: dict[str, Path] = {
        "verdict": run_dir / "chart_verdict.png",
        "elapsed": run_dir / "chart_elapsed.png",
        "rate": run_dir / "chart_request_rate.png",
        "mix": run_dir / "chart_status_mix.png",
    }

    chart_verdict(results, charts["verdict"])
    chart_elapsed(results, charts["elapsed"])
    chart_request_rate(results, charts["rate"])
    chart_status_mix(results, charts["mix"])

    if any(r["trials"] for r in results):
        charts["first_hit"] = run_dir / "chart_first_hit.png"
        chart_first_hit(results, payload.get("wordlist_size", 0), charts["first_hit"])

    if any(t["successes"] for r in results for t in r["trials"]):
        scatter_path = run_dir / "chart_position_vs_time.png"
        chart_position_vs_time(results, scatter_path)
        if scatter_path.exists():
            charts["scatter"] = scatter_path

    html_path = write_html(payload, run_dir, charts)
    md_path = write_markdown(payload, run_dir, charts)

    print("Report written:")
    print(f"  HTML : {html_path}")
    print(f"  MD   : {md_path}")
    for name, path in charts.items():
        print(f"  PNG  : {path}  ({name})")


if __name__ == "__main__":
    main()
