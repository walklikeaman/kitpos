#!/usr/bin/env -S python3 -u
"""
KIT POS — Ingest pre-split .eml files into Supabase.
======================================================
Reads individual .eml files (already split from mbox) one at a time.
Each file is tiny (<60KB), no large memory alloc.

Usage:
  python3 ingest_eml_dir.py /tmp/emails_split
  python3 ingest_eml_dir.py /tmp/emails_split --start=10
  python3 ingest_eml_dir.py /tmp/emails_split --start=10 --limit=80
  python3 ingest_eml_dir.py /tmp/emails_split --dry-run
"""

import os, sys, re, time, gc, email, email.policy, email.header
import html.parser, ssl, json, urllib.request, urllib.error

# ── Config ───────────────────────────────────────────────────────────────────

SUPABASE_URL   = os.environ.get("SUPABASE_URL", "https://hoowbtzdzndvyihxhlpb.supabase.co")
SUPABASE_KEY   = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

if not SUPABASE_KEY or not OPENROUTER_KEY:
    _env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_env):
        for _line in open(_env):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
        SUPABASE_KEY   = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", SUPABASE_KEY)
        OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_KEY)

if not SUPABASE_KEY:  print("❌  SUPABASE_ANON_KEY not set"); sys.exit(1)
if not OPENROUTER_KEY: print("❌  OPENROUTER_API_KEY not set"); sys.exit(1)

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

EMBED_MODEL     = "openai/text-embedding-3-small"
CHUNK_CHARS     = 2000
CHUNK_OVERLAP   = 200
MAX_EMAIL_BYTES = 60_000

SKIP_DOMAINS = {
    "amazon.com", "business.amazon.com", "shop.app",
    "laireviews.io", "accounts.google.com", "google.com",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def decode_hdr(val) -> str:
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
        def handle_starttag(self, t, a):
            if t in self.SKIP: self._skip += 1
            if t in ("br","p","div","tr","li","h1","h2","h3","h4","hr"): self.parts.append("\n")
        def handle_endtag(self, t):
            if t in self.SKIP: self._skip = max(0, self._skip-1)
        def handle_data(self, d):
            if not self._skip: self.parts.append(d)
    p = P()
    try: p.feed(text)
    except: pass
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.parts))).strip()

def get_body(msg) -> str:
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
    cleaned, gt = [], 0
    for line in lines:
        s = line.strip()
        if s.startswith(">"): gt += 1;
        else: gt = 0
        if gt > 2: continue
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

def _post(url, headers, data, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, context=_SSL, timeout=timeout) as r:
        return json.loads(r.read())

def get_embedding(text: str):
    try:
        r = _post("https://openrouter.ai/api/v1/embeddings",
                  {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                  {"model": EMBED_MODEL, "input": text[:8000]})
        return r["data"][0]["embedding"]
    except Exception as e:
        print(f"    ❌  embed: {e}", flush=True); return None

def insert_doc(idx, title, content, meta, emb) -> bool:
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/documents",
            data=json.dumps({"source": f"email:Inbox:{idx}", "source_type": "email",
                             "title": title, "content": content,
                             "metadata": meta, "embedding": emb}).encode(),
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            method="POST")
        with urllib.request.urlopen(req, context=_SSL, timeout=15) as r:
            return r.status < 300
    except urllib.error.HTTPError as e:
        print(f"    ❌  insert {e.code}: {e.read()[:80]}", flush=True); return False
    except Exception as e:
        print(f"    ❌  insert: {e}", flush=True); return False

# ── Main ─────────────────────────────────────────────────────────────────────

def run(eml_dir: str, dry_run=False, start_idx=0, limit=0):
    files = sorted(f for f in os.listdir(eml_dir) if f.endswith(".eml"))
    total_files = len(files)
    print(f"📂  {total_files} .eml files in {eml_dir}", flush=True)

    total = skipped = processed = errors = chunks_total = 0
    t0 = time.time()

    for fname in files:
        idx = int(fname.replace(".eml",""))
        total += 1

        if idx < start_idx:
            continue
        if limit and processed >= limit:
            print(f"  ⏹  Limit {limit} reached", flush=True)
            break

        fpath = os.path.join(eml_dir, fname)
        fsize = os.path.getsize(fpath)

        if fsize > MAX_EMAIL_BYTES:
            skipped += 1; continue

        try:
            raw = open(fpath, "rb").read()
            msg = email.message_from_bytes(raw, policy=email.policy.compat32)
            subject = decode_hdr(msg.get("Subject", ""))
            frm     = decode_hdr(msg.get("From", ""))
            date    = decode_hdr(msg.get("Date", ""))
            labels  = str(msg.get("X-Gmail-Labels", ""))
            body    = clean_body(get_body(msg))
            del msg, raw
        except Exception as e:
            print(f"  ❌  [{idx}] parse error: {e}", flush=True)
            errors += 1; gc.collect(); continue

        frm_addr = frm.split("<")[1].split(">")[0] if "<" in frm else frm
        domain   = frm_addr.split("@")[-1].strip().lower() if "@" in frm_addr else ""
        if domain in SKIP_DOMAINS:
            skipped += 1; gc.collect(); continue

        if len(body) < 60:
            skipped += 1; gc.collect(); continue

        full_text = f"From: {frm}\nDate: {date}\nSubject: {subject}\nLabels: {labels}\n\n{body}"
        del body
        chunks = chunk_text(full_text); del full_text

        if not chunks:
            skipped += 1; gc.collect(); continue

        title = f"{subject[:100]} — {frm[:60]}"
        meta  = {"from": frm[:200], "subject": subject[:200],
                  "date": date[:50], "labels": labels[:100], "email_index": idx}

        if dry_run:
            print(f"  [DRY {idx}] {subject[:55]} | {len(chunks)} chunk(s)", flush=True)
            processed += 1
        else:
            ok_count = 0
            for j, chunk in enumerate(chunks):
                emb = get_embedding(chunk)
                if emb is None: errors += 1; continue
                ok = insert_doc(idx, title, chunk,
                                {**meta, "chunk": j+1, "total_chunks": len(chunks)}, emb)
                del emb
                if ok: chunks_total += 1; ok_count += 1
                else:  errors += 1
                time.sleep(0.05)
            del chunks, meta
            if ok_count > 0:
                processed += 1

        if processed <= 20 or processed % 50 == 0:
            elapsed = time.time() - t0
            rate = processed / elapsed * 60 if elapsed > 0 else 0
            remaining = total_files - start_idx - total
            eta = remaining / (processed/elapsed) / 60 if processed > 0 and elapsed > 0 else 0
            print(f"  ✅ [{idx}] {subject[:50]} | done:{processed} chunks:{chunks_total} "
                  f"({rate:.1f}/min ETA:{eta:.0f}min)", flush=True)

        gc.collect()

    elapsed = time.time() - t0
    print(f"\n{'═'*55}", flush=True)
    print(f"Files:     {total}", flush=True)
    print(f"Skipped:   {skipped}", flush=True)
    print(f"Processed: {processed}", flush=True)
    print(f"Chunks:    {chunks_total}", flush=True)
    print(f"Errors:    {errors}", flush=True)
    if elapsed > 0:
        print(f"Time:      {elapsed:.0f}s ({processed/elapsed*60:.1f} emails/min)", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h","--help"):
        print(__doc__); sys.exit(0)
    eml_dir   = args[0]
    dry_run   = "--dry-run" in args
    start_arg = [a for a in args if a.startswith("--start=")]
    limit_arg = [a for a in args if a.startswith("--limit=")]
    start_idx = int(start_arg[0].split("=")[1]) if start_arg else 0
    limit     = int(limit_arg[0].split("=")[1]) if limit_arg else 0
    run(eml_dir, dry_run=dry_run, start_idx=start_idx, limit=limit)
