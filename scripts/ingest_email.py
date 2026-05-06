#!/usr/bin/env -S python3 -u
"""
KIT POS — Email (mbox) Ingestion  (mmap-based, no streaming)
=============================================================
Uses mmap to slice emails by byte offset — avoids all buffering/OOM issues.

Usage:
  python3 -u ingest_email.py <Inbox.mbox>
  python3 -u ingest_email.py <Inbox.mbox> --start=500       # resume from index
  python3 -u ingest_email.py <Inbox.mbox> --start=500 --limit=100  # batch mode
  python3 -u ingest_email.py <Inbox.mbox> --dry-run

Batch runner (runs in chunks, fresh process each time):
  ./ingest_email_batch.sh <Inbox.mbox>
"""

import os, sys, re, time, gc, mmap
import email, email.policy, email.header
import html.parser

try:
    import requests
except ImportError:
    print("❌  pip install requests"); sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "https://hoowbtzdzndvyihxhlpb.supabase.co")
SUPABASE_KEY  = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

if not SUPABASE_KEY or not OPENROUTER_KEY:
    # Load from .env in repo root if env vars not set
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_env_path):
        for _line in open(_env_path):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
        SUPABASE_KEY   = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", SUPABASE_KEY)
        OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_KEY)

if not SUPABASE_KEY:
    print("❌  SUPABASE_ANON_KEY not set. Add to .env or export env var."); sys.exit(1)
if not OPENROUTER_KEY:
    print("❌  OPENROUTER_API_KEY not set. Add to .env or export env var."); sys.exit(1)

EMBED_MODEL      = "openai/text-embedding-3-small"
CHUNK_CHARS      = 2000
CHUNK_OVERLAP    = 200
MAX_EMAIL_BYTES  = 60_000   # skip emails >60KB (likely has embedded images)

SKIP_DOMAINS = {
    "amazon.com", "business.amazon.com", "shop.app",
    "laireviews.io", "accounts.google.com", "google.com",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def decode_header(val) -> str:
    if not val: return ""
    try:
        parts = email.header.decode_header(str(val))
        return " ".join(
            p.decode(e or "utf-8", errors="replace") if isinstance(p, bytes) else str(p)
            for p, e in parts
        ).strip()
    except: return str(val)


def strip_html(text: str) -> str:
    class P(html.parser.HTMLParser):
        SKIP = {"script","style","head","meta","link"}
        def __init__(self): super().__init__(); self.parts=[]; self._skip=0
        def handle_starttag(self, tag, attrs):
            if tag in self.SKIP: self._skip += 1
            if tag in ("br","p","div","tr","li","h1","h2","h3","h4","hr"):
                self.parts.append("\n")
        def handle_endtag(self, tag):
            if tag in self.SKIP: self._skip = max(0, self._skip-1)
        def handle_data(self, d):
            if not self._skip: self.parts.append(d)
    p = P()
    try: p.feed(text)
    except: pass
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.parts))).strip()


def get_body(email_bytes: bytes) -> str:
    """Extract plain text. Prefer text/plain; HTML fallback capped at 6KB."""
    try:
        msg = email.message_from_bytes(email_bytes, policy=email.policy.compat32)
    except Exception:
        return ""
    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() != "text/plain": continue
        if "attachment" in str(part.get("Content-Disposition") or ""): continue
        payload = part.get_payload(decode=True)
        if not payload: continue
        cs = part.get_content_charset() or "utf-8"
        try: return payload.decode(cs, errors="replace")
        except: return payload.decode("latin-1", errors="replace")
    for part in parts:
        if part.get_content_type() != "text/html": continue
        if "attachment" in str(part.get("Content-Disposition") or ""): continue
        payload = part.get_payload(decode=True)
        if not payload: continue
        cs = part.get_content_charset() or "utf-8"
        try: text = payload.decode(cs, errors="replace")
        except: text = payload.decode("latin-1", errors="replace")
        return strip_html(text[:6000])
    return ""


def clean_body(text: str) -> str:
    if not text: return ""
    lines = text.splitlines()
    cleaned = []
    gt_streak = 0
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            gt_streak += 1
            if gt_streak > 2: continue
        else:
            gt_streak = 0
        if re.match(r"On .{10,100} wrote:$", s): break
        if re.search(r"(unsubscribe|click here to|view in browser|this email was sent|"
                     r"privacy policy|copyright \d{4}|all rights reserved)", s, re.I): continue
        if re.match(r"https?://\S+$", s): continue
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", "\n".join(cleaned))).strip()


def chunk_text(text: str) -> list:
    text = text.strip()
    if not text: return []
    if len(text) <= CHUNK_CHARS: return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        chunk = text[start:end]
        if end < len(text):
            for sep in ["\n\n", "\n", ". "]:
                pos = chunk.rfind(sep, CHUNK_CHARS // 2)
                if pos != -1:
                    chunk = chunk[:pos+len(sep)]; end = start+pos+len(sep); break
        chunk = chunk.strip()
        if len(chunk) >= 50: chunks.append(chunk)
        start = end - CHUNK_OVERLAP
    return chunks


def get_embedding(text: str, session):
    try:
        r = session.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                     "Content-Type": "application/json"},
            json={"model": EMBED_MODEL, "input": text[:8000]},
            timeout=30,
        )
        r.raise_for_status()
        result = r.json()["data"][0]["embedding"]
        r.close()
        return result
    except Exception as e:
        print(f"    ❌  embed error: {e}", flush=True)
        return None


def insert_doc(idx, title, content, meta, embedding, session) -> bool:
    try:
        r = session.post(
            f"{SUPABASE_URL}/rest/v1/documents",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"source": f"email:Inbox:{idx}", "source_type": "email",
                  "title": title, "content": content, "metadata": meta,
                  "embedding": embedding},
            timeout=15,
        )
        r.close()
        return r.status_code < 300
    except Exception as e:
        print(f"    ❌  insert error: {e}", flush=True)
        return False


def find_offsets(mbox_path: str) -> list:
    """Return byte offsets of each email in the mbox using mmap. Fast, no buffering."""
    offsets = [0]
    with open(mbox_path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        pos = 0
        size = len(mm)
        while pos < size:
            nl = mm.find(b"\nFrom ", pos)
            if nl == -1:
                break
            offsets.append(nl + 1)
            pos = nl + 1
        mm.close()
    return offsets


# ── Main ─────────────────────────────────────────────────────────────────────

def run(mbox_path: str, dry_run=False, start_idx=0, limit=0):
    """limit=0 means no limit (process all emails)."""
    print(f"📬  Indexing {mbox_path} ...", flush=True)

    print("  🔍  Scanning email boundaries ...", end="", flush=True)
    offsets = find_offsets(mbox_path)
    print(f" {len(offsets)} emails found", flush=True)

    total = skipped = processed = errors = chunks_total = 0
    t0 = time.time()
    session = requests.Session()
    file_size = os.path.getsize(mbox_path)

    with open(mbox_path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        for idx in range(len(offsets)):
            total += 1

            if idx < start_idx:
                skipped += 1
                continue

            start_byte = offsets[idx]
            end_byte   = offsets[idx + 1] if idx + 1 < len(offsets) else file_size
            email_size = end_byte - start_byte

            if email_size > MAX_EMAIL_BYTES:
                skipped += 1
                continue

            # Extract email bytes directly from mmap slice
            email_raw = bytes(mm[start_byte:end_byte])

            # Strip mbox "From " separator line
            nl = email_raw.find(b"\n")
            if nl != -1 and email_raw[:5] == b"From ":
                email_raw = email_raw[nl + 1:]

            # Parse headers
            try:
                msg = email.message_from_bytes(email_raw, policy=email.policy.compat32)
                subject = decode_header(msg.get("Subject", ""))
                frm     = decode_header(msg.get("From", ""))
                date    = decode_header(msg.get("Date", ""))
                labels  = msg.get("X-Gmail-Labels", "")
                del msg
            except Exception as e:
                print(f"  ❌  [{idx}] header error: {e}", flush=True)
                del email_raw; errors += 1; continue

            # Domain filter
            frm_addr = frm.split("<")[1].split(">")[0] if "<" in frm else frm
            domain   = frm_addr.split("@")[-1].strip().lower() if "@" in frm_addr else ""
            if domain in SKIP_DOMAINS:
                del email_raw; skipped += 1; continue

            # Body
            body = clean_body(get_body(email_raw))
            del email_raw

            if len(body) < 60:
                skipped += 1; continue

            full_text = (
                f"From: {frm}\nDate: {date}\nSubject: {subject}\n"
                f"Labels: {labels}\n\n{body}"
            )
            del body

            chunks = chunk_text(full_text)
            del full_text

            if not chunks:
                skipped += 1; continue

            title = f"{subject[:100]} — {frm[:60]}"
            meta  = {"from": frm[:200], "subject": subject[:200],
                      "date": date[:50], "labels": labels[:100], "email_index": idx}

            if dry_run:
                print(f"  [DRY {idx}] {subject[:55]} | {len(chunks)} chunk(s)", flush=True)
                del chunks
                processed += 1
            else:
                for j, chunk in enumerate(chunks):
                    emb = get_embedding(chunk, session)
                    if emb is None:
                        errors += 1; continue
                    ok = insert_doc(idx, title, chunk,
                                    {**meta, "chunk": j+1, "total_chunks": len(chunks)},
                                    emb, session)
                    del emb
                    if ok: chunks_total += 1
                    else: errors += 1
                    time.sleep(0.05)
                del chunks, meta
                processed += 1

                # Recycle session every 5 emails to prevent SSL state buildup
                if processed % 5 == 0:
                    session.close()
                    session = requests.Session()
                    gc.collect()

            # Progress
            if processed <= 20 or processed % 50 == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = len(offsets) - start_idx - processed - skipped
                eta = remaining / rate / 60 if rate > 0 else 0
                print(f"  ✅ [{idx}] {subject[:50]} | done:{processed} chunks:{chunks_total} "
                      f"({rate:.1f}/min ETA:{eta:.0f}min)", flush=True)

            # Limit check
            if limit and processed >= limit:
                print(f"  ⏹  Limit {limit} reached at email_idx={idx}", flush=True)
                break

        mm.close()

    session.close()
    elapsed = time.time() - t0
    print(f"\n{'═'*55}", flush=True)
    print(f"Total:     {total}", flush=True)
    print(f"Skipped:   {skipped}", flush=True)
    print(f"Processed: {processed}", flush=True)
    print(f"Chunks:    {chunks_total}", flush=True)
    print(f"Errors:    {errors}", flush=True)
    if elapsed > 0:
        print(f"Time:      {elapsed:.0f}s ({processed/elapsed*60:.1f} emails/min)", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)

    mbox_path  = args[0]
    dry_run    = "--dry-run" in args
    start_arg  = [a for a in args if a.startswith("--start=")]
    limit_arg  = [a for a in args if a.startswith("--limit=")]
    start_idx  = int(start_arg[0].split("=")[1]) if start_arg else 0
    limit      = int(limit_arg[0].split("=")[1]) if limit_arg else 0

    run(mbox_path, dry_run=dry_run, start_idx=start_idx, limit=limit)
