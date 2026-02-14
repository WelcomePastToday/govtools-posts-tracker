#!/usr/bin/env python3
import csv
import os
import re
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Set

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Configuration
CSV_PATH = "USSTATE.csv"
BASE_URL = "https://x.com/"
OUT_ROOT = "data"  # New root for daily folders
INTERVAL_SECONDS = 120

# Conservative behavior
HEADLESS = True
NAV_TIMEOUT_MS = 30000
POST_NAV_WAIT_MS = 3500

# Only top portion (header + maybe 1-2 posts)
VIEWPORT_W = 1280
VIEWPORT_H = 1400

SUMMARY_FIELDS = [
    "timestamp_utc",
    "handle",
    "url",
    "status",
    "posts_count",
    "has_visible_posts",
    "bio",
    "screenshot",
    "error",
]

def normalize_handle(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if s.startswith("@"):
        s = s[1:]
    s = s.replace("https://x.com/", "").replace("http://x.com/", "")
    s = s.replace("https://twitter.com/", "").replace("http://twitter.com/", "")
    s = s.strip().strip("/")
    if "/" in s:
        s = s.split("/", 1)[0]
    return s

def read_handles(csv_path: str) -> list[str]:
    p = Path(csv_path)
    if not p.exists():
        return []

    raw = p.read_bytes().replace(b"\x00", b"")
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]

    def parse_with_delim(delim: str) -> list[str]:
        out = []
        for row in csv.reader(lines, delimiter=delim):
            if not row:
                continue
            cell = ""
            for c in row:
                if c and c.strip():
                    cell = c
                    break
            h = normalize_handle(cell)
            if h:
                out.append(h)
        return out

    # Try common delimiters and choose the one yielding most handles
    candidates = []
    for d in [",", ";", "\t", "|"]:
        hs = parse_with_delim(d)
        candidates.append((len(hs), hs))
    candidates.sort(reverse=True, key=lambda x: x[0])
    handles = candidates[0][1] if candidates else []

    if not handles:
        handles = [normalize_handle(ln) for ln in lines]
        handles = [h for h in handles if h]

    # Drop obvious header
    if handles and handles[0].lower() in {"id", "ids", "handle", "handles", "username", "user", "screen_name"}:
        handles = handles[1:]

    # Dedupe preserve order
    seen = set()
    out = []
    for h in handles:
        k = h.lower()
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out

def load_already_done(summary_path: Path) -> Dict[str, datetime]:
    """
    Reads summary.csv and returns map of {handle: last_timestamp} for today.
    """
    done: Dict[str, datetime] = {}
    if not summary_path.exists():
        return done

    with open(summary_path, "r", encoding="utf-8", newline="") as f:
        # summary is ;;; separated
        for line in f:
            line = line.strip()
            if not line or line.startswith("timestamp_utc;;;"):
                continue
            parts = line.split(";;;")
            if len(parts) >= 2:
                ts_str = parts[0].strip()
                handle = parts[1].strip().lower()
                
                # Try parsing timestamp
                dt = None
                # Support both new microsecond format and old format
                for fmt in ("%Y%m%dT%H%M%S.%fZ", "%Y%m%dT%H%M%SZ"):
                    try:
                        dt = datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                
                if dt:
                    if handle not in done or dt > done[handle]:
                        done[handle] = dt
    return done

def classify_account(page) -> str:
    checks = [
        ("suspended", [
            "Account suspended",
            "This account is suspended",
            "has been suspended",
        ]),
        ("does_not_exist", [
            "This account doesn’t exist",
            "This account doesn't exist",
            "Try searching for another",
        ]),
        ("protected", [
            "These posts are protected",
            "Only approved followers can see",
        ]),
        ("restricted", [
            "temporarily restricted",
            "limited",
            "Caution:",
        ]),
    ]

    try:
        body_text = page.inner_text("body")
    except Exception:
        return "unknown"

    lower = body_text.lower()
    for label, phrases in checks:
        for p in phrases:
            if p.lower() in lower:
                return label
    return "active_or_visible"

def is_login_screen(page) -> bool:
    try:
        # Check for common login prompts/buttons
        if page.locator('[data-testid="loginButton"]').count() > 0 or \
           "Sign in to X" in page.title() or \
           "Log in" in page.title():
            return True
        # Check specifically for "Sign in to subscribe" or similar overlays that block content
        if page.get_by_text("Sign in to X").count() > 0:
            return True
    except:
        pass
    return False

def extract_posts_count(page) -> str:
    try:
        txt = page.inner_text("body")
    except Exception:
        return ""
    m = re.search(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s+posts\b", txt, flags=re.IGNORECASE)
    return m.group(1) if m else ""

def extract_bio(page) -> str:
    selectors = [
        '[data-testid="UserDescription"]',
        'div[data-testid="UserDescription"]',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                t = loc.first.inner_text().strip()
                if t:
                    return t
        except Exception:
            pass
    return ""

def has_any_visible_posts(page) -> bool:
    try:
        arts = page.locator('article[role="article"]')
        return arts.count() > 0
    except Exception:
        return False

def screenshot_top(page, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(out_path),
        full_page=False,
        clip={"x": 0, "y": 0, "width": VIEWPORT_W, "height": VIEWPORT_H},
    )

def ensure_summary_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(";;;".join(SUMMARY_FIELDS) + "\n")

def append_summary_row(path: Path, row: Dict[str, str]) -> None:
    ensure_summary_header(path)
    clean = []
    for k in SUMMARY_FIELDS:
        v = row.get(k, "") or ""
        if k == "bio":
            v = v.replace("\n", " ").strip()
        clean.append(v)
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(";;;".join(clean) + "\n")

def run_one(p, handle: str, out_dir: Path) -> Dict[str, str]:
    url = BASE_URL + handle
    # Timestamp down to microseconds
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    result: Dict[str, str] = {
        "timestamp_utc": ts,
        "handle": handle,
        "url": url,
        "status": "",
        "posts_count": "",
        "has_visible_posts": "",
        "bio": "",
        "screenshot": "",
        "error": "",
    }

    browser = None
    try:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=1,
        )
        page = context.new_page()
        page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(POST_NAV_WAIT_MS)

        if is_login_screen(page):
            result["status"] = "login_required"
            result["error"] = "login_wall"
        else:
            result["status"] = classify_account(page)
            result["posts_count"] = extract_posts_count(page)
            result["bio"] = extract_bio(page)
            result["has_visible_posts"] = "yes" if has_any_visible_posts(page) else "no"

            screenshots_dir = out_dir / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            out_path = screenshots_dir / f"{handle}_{ts}.png"
            screenshot_top(page, out_path)
            result["screenshot"] = str(out_path)

        context.close()
        browser.close()
        return result

    except PlaywrightTimeoutError:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    return result

def main():
    handles = read_handles(CSV_PATH)
    if not handles:
        print(f"No handles found in {CSV_PATH} or file is empty.")
        # Create dummy file if not exists
        if not Path(CSV_PATH).exists():
            with open(CSV_PATH, "w") as f:
                f.write("handle\n@StateDept\n")
            print(f"Created dummy {CSV_PATH}. Please populate.")
            return

    # Create daily output directory
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(OUT_ROOT) / today_str
    out_dir.mkdir(parents=True, exist_ok=True)
    
    summary_path = out_dir / "summary.csv"

    # Load done strictly for today to allow daily runs
    done = load_already_done(summary_path)

    print(f"Loaded {len(handles)} handles from {CSV_PATH}")
    print(f"Already processed today ({today_str}): {len(done)}")
    print("No scrolling. Top-only clip. Ctrl+C to stop. Intelligent backoff enabled.")

    consecutive_login_errors = 0
    MAX_CONSECUTIVE_LOGIN_ERRORS = 5
    
    # Timing configuration
    MIN_SLEEP = 33.0
    MAX_SLEEP = 67.0
    
    # Backoff multiplier
    backoff_multiplier = 1.0

    with sync_playwright() as p:
        for handle in handles:
            handle_key = handle.lower()

            # Check for skip based on 12h rule
            should_skip = False
            skip_reason = ""
            REPROCESS_INTERVAL = 12 * 3600  # 12 hours

            if handle_key in done:
                last_ts = done[handle_key]
                now = datetime.now(timezone.utc)
                age_seconds = (now - last_ts).total_seconds()
                
                if age_seconds < REPROCESS_INTERVAL:
                    should_skip = True
                    skip_reason = f"(done {age_seconds/3600:.1f}h ago)"
            
            if should_skip:
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                print(f"{ts}\t{handle}\tskipped\t{skip_reason}")
                continue

            started = time.time()
            row = run_one(p, handle, out_dir)
            append_summary_row(summary_path, row)

            print(
                f'{row["timestamp_utc"]}\t{row["handle"]}\t{row["status"]}\t'
                f'posts={row["posts_count"] or "?"}\tvisible_posts={row["has_visible_posts"] or "?"}\t'
                f'err={row["error"] or "-"}'
            )

            is_error = False
            if row["status"] == "login_required" or row["error"] == "login_wall":
                is_error = True
                consecutive_login_errors += 1
            else:
                consecutive_login_errors = 0
            
            # Intelligent Backoff Logic
            if is_error:
                # Exponential backoff: 2x, 4x, 8x...
                # But limited to reasonable bounds?
                # User said "back off intelligently".
                # Let's double the multiplier on error.
                backoff_multiplier = min(backoff_multiplier * 2.0, 16.0) # Cap at 16x (~10-20 mins)
            else:
                # Reset on success
                backoff_multiplier = 1.0

            if consecutive_login_errors >= MAX_CONSECUTIVE_LOGIN_ERRORS:
                print(f"\n[!] Process aborted: Encountered {MAX_CONSECUTIVE_LOGIN_ERRORS} consecutive login walls/errors.")
                print("    This likely means Twitter is blocking the requests or requiring authentication.")
                break

            elapsed = time.time() - started
            
            # Random sleep with microsecond precision logic
            base_sleep = random.uniform(MIN_SLEEP, MAX_SLEEP)
            target_sleep = base_sleep * backoff_multiplier
            
            # Deduct elapsed time
            actual_sleep = max(0.000001, target_sleep - elapsed)
            
            # Print with high precision
            print(f"    Sleeping {actual_sleep:.6f}s (Multiplier: {backoff_multiplier}x)")
            time.sleep(actual_sleep)

if __name__ == "__main__":
    main()
