from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

# Reuse the REAL source classes and filters so results match the live pipeline.
from bot.sources.base import Job
from bot.sources.greenhouse import GreenhouseSource
from bot.sources.lever import LeverSource
from bot.sources.ashby import AshbySource


# Default location filter mirrors bot/pipeline.py's LOCATION_KEYWORD.
DEFAULT_LOCATION = "singapore"


@dataclass
class SlugResult:
    ats: str
    slug: str
    resolved: bool
    intern_count: int          # roles kept after the source's intern filter
    location_count: int        # of those, how many match the location filter
    error: str = ""            # populated when resolved is False


def _location_ok(job: Job, location_keyword: str) -> bool:
    """Same test pipeline._fetch_all applies: keep roles whose location contains
    the keyword. Empty keyword disables the filter (keep everything)."""
    if not location_keyword:
        return True
    return location_keyword in (job.location or "").lower()


def _verify_one(ats: str, slug: str, location_keyword: str) -> SlugResult:
    """Fetch a single slug through its real Source class and tally the results.

    Each Source is constructed with a one-element list so its own per-board
    try/except still applies — a dead slug returns [] rather than raising, which
    we detect separately below by probing once with isolation turned off.
    """
    source_map = {
        "greenhouse": GreenhouseSource,
        "lever": LeverSource,
        "ashby": AshbySource,
    }
    SourceCls = source_map[ats]

    # The Source classes swallow per-board exceptions and return [], so a clean
    # [] is ambiguous: "resolved but no intern roles" vs "slug is dead". To tell
    # them apart we call the source's private single-board fetch directly, which
    # DOES raise, and treat a raise as "did not resolve".
    single = SourceCls([slug])
    fetch_one = getattr(single, "_fetch_board", None) or getattr(single, "_fetch_company", None)

    try:
        if fetch_one is not None:
            jobs = fetch_one(slug)          # raises on a dead slug -> caught below
        else:
            jobs = single.fetch()           # fallback: never raises
        resolved = True
        error = ""
    except Exception as e:
        return SlugResult(ats, slug, resolved=False, intern_count=0,
                          location_count=0, error=f"{type(e).__name__}: {e}")

    intern_count = len(jobs)
    location_count = sum(1 for j in jobs if _location_ok(j, location_keyword))
    return SlugResult(ats, slug, resolved, intern_count, location_count, error)


def _parse_slugs(inline: str | None, file_path: str | None) -> list[str]:
    """Collect slugs from a comma-separated --x value and/or a --x-file."""
    slugs: list[str] = []
    if inline:
        slugs += [s.strip() for s in inline.split(",") if s.strip()]
    if file_path:
        with open(file_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()   # allow '# comments'
                if line:
                    slugs.append(line)
    # de-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _print_table(results: list[SlugResult], location_keyword: str) -> None:
    loc_label = location_keyword or "(no filter)"
    header = f"{'ATS':<11}{'SLUG':<24}{'RESOLVES':<10}{'INTERN':<8}{'SG/' + loc_label:<14}NOTE"
    print(header)
    print("-" * len(header))
    for r in results:
        if not r.resolved:
            print(f"{r.ats:<11}{r.slug:<24}{'NO':<10}{'-':<8}{'-':<14}{r.error}")
            continue
        note = ""
        if r.intern_count == 0:
            note = "resolves, but no intern roles right now"
        elif r.location_count == 0:
            note = f"intern roles exist, but none in '{loc_label}'"
        print(f"{r.ats:<11}{r.slug:<24}{'yes':<10}{r.intern_count:<8}{r.location_count:<14}{note}")


def _print_env_lines(results: list[SlugResult]) -> None:
    """Emit .env-ready lines containing only slugs that actually surface roles in
    the target location — the ones genuinely worth adding."""
    keep = {"greenhouse": [], "lever": [], "ashby": []}
    for r in results:
        if r.resolved and r.location_count > 0:
            keep[r.ats].append(r.slug)

    print("\n# --- slugs that currently surface roles in your target location ---")
    print("# (paste into .env; these are the ones worth adding)")
    env_var = {"greenhouse": "GREENHOUSE_BOARDS",
               "lever": "LEVER_COMPANIES",
               "ashby": "ASHBY_BOARDS"}
    any_kept = False
    for ats, slugs in keep.items():
        if slugs:
            any_kept = True
            print(f"{env_var[ats]}={','.join(slugs)}")
    if not any_kept:
        print("# (none — no candidate currently has a role in the target location)")

    # Also surface the "resolves but nothing in-location" set: worth keeping on a
    # watchlist, since they may post SG roles later.
    watch = [r for r in results if r.resolved and r.location_count == 0]
    if watch:
        print("\n# resolves but no in-location roles *right now* — watchlist candidates:")
        for r in watch:
            print(f"#   {r.ats}: {r.slug}  ({r.intern_count} intern roles elsewhere)")


def main() -> int:
    p = argparse.ArgumentParser(description="Verify candidate ATS board slugs.")
    p.add_argument("--greenhouse", help="comma-separated Greenhouse slugs")
    p.add_argument("--lever", help="comma-separated Lever slugs")
    p.add_argument("--ashby", help="comma-separated Ashby slugs")
    p.add_argument("--greenhouse-file", help="file of Greenhouse slugs (one per line)")
    p.add_argument("--lever-file", help="file of Lever slugs (one per line)")
    p.add_argument("--ashby-file", help="file of Ashby slugs (one per line)")
    p.add_argument("--location", default=DEFAULT_LOCATION,
                   help=f"location keyword filter (default: {DEFAULT_LOCATION!r}; "
                        f"pass empty string to disable)")
    args = p.parse_args()

    candidates: list[tuple[str, str]] = []
    for ats, inline, fpath in [
        ("greenhouse", args.greenhouse, args.greenhouse_file),
        ("lever", args.lever, args.lever_file),
        ("ashby", args.ashby, args.ashby_file),
    ]:
        for slug in _parse_slugs(inline, fpath):
            candidates.append((ats, slug))

    if not candidates:
        p.print_help()
        print("\nNo slugs given. Pass --greenhouse/--lever/--ashby or their --*-file forms.")
        return 1

    location_keyword = args.location.strip().lower()

    print(f"Verifying {len(candidates)} candidate slug(s); "
          f"location filter = {location_keyword or '(disabled)'}\n")

    results: list[SlugResult] = []
    for ats, slug in candidates:
        print(f"  checking {ats}:{slug} ...", file=sys.stderr)
        results.append(_verify_one(ats, slug, location_keyword))

    print()
    _print_table(results, location_keyword)
    _print_env_lines(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
