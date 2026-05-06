#!/usr/bin/env -S python3 -u
"""
KIT POS — Ingest a SINGLE .eml file into Supabase.
====================================================
Designed to be called once per email from a shell loop.
Process exits after one email → OS reclaims ALL memory.

Usage:
  python3 ingest_one_eml.py /tmp/emails_split/00042.eml
  python3 ingest_one_eml.py /tmp/emails_split/00042.eml --dry-run

Exit codes: 0=ok/skipped, 1=error, 2=inserted
"""

import os, sys, re, time, email, email.policy, email.header
import html.parser, ssl, json, urllib.request, urllib.error

# ── Config ────────────────────────────────────────────────────────────────────

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

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

EMBED_MODEL     = "openai/text-embedding-3-small"
CHUNK_CHARS     = 2000
CHUNK_OVERLAP   = 200
MAX_EMAIL_BYTES = 60_000
SKIP_DOMAINS    = {"amazon.com","business.amazon.com","shop.app",
                   "laireviews.io","accounts.google.com","google.com"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def decode_hdr(val):
    if not val: return ""
    try:
        parts = email.header.decode_header(str(val))
        return " ".join(
            p.decode(e or "utf-8", errors="replace") if isinstance(p, bytes) else str(p)
            for p, e in parts).strip()
    except: return str(val)

def strip_html(text):
    class P(html.parser.HTMLParser):
        SKIP = {"script","style","head","meta","link"}
        def __init__(self): super().__init__(); self.parts=[]; self._skip=0
        def handle_starttag(self,t,a):
            if t in self.SKIP: self._skip+=1
            if t in("br","p","div","tr","li","h1","h2","h3","h4","hr"): self.parts.append("\n")
        def handle_endtag(self,t):
            if t in self.SKIP: self._skip=max(0,self._skip-1)
        def handle_data(self,d):
            if not self._skip: self.parts.append(d)
    p=P(); p.feed(text)
    return re.sub(r"\n{3,}","\n\n",re.sub(r"[ \t]+"," ","".join(p.parts))).strip()

def get_body(msg):
    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type()!="text/plain": continue
        if "attachment" in str(part.get("Content-Disposition") or ""): continue
        raw=part.get_payload(decode=True)
        if not raw: continue
        cs=part.get_content_charset() or "utf-8"
        try: return raw.decode(cs,errors="replace")
        except: return raw.decode("latin-1",errors="replace")
    for part in parts:
        if part.get_content_type()!="text/html": continue
        if "attachment" in str(part.get("Content-Disposition") or ""): continue
        raw=part.get_payload(decode=True)
        if not raw: continue
        cs=part.get_content_charset() or "utf-8"
        try: text=raw.decode(cs,errors="replace")
        except: text=raw.decode("latin-1",errors="replace")
        return strip_html(text[:6000])
    return ""

def clean_body(text):
    if not text: return ""
    cleaned,gt=[],0
    for line in text.splitlines():
        s=line.strip()
        if s.startswith(">"): gt+=1
        else: gt=0
        if gt>2: continue
        if re.match(r"On .{10,100} wrote:$",s): break
        if re.search(r"(unsubscribe|click here to|view in browser|this email was sent|"
                     r"privacy policy|copyright \d{4}|all rights reserved)",s,re.I): continue
        if re.match(r"https?://\S+$",s): continue
        cleaned.append(line)
    return re.sub(r"\n{3,}","\n\n",re.sub(r"[ \t]+"," ","\n".join(cleaned))).strip()

def chunk_text(text):
    text=text.strip()
    if not text: return []
    if len(text)<=CHUNK_CHARS: return [text]
    chunks,start=[],0
    while start<len(text):
        end=min(start+CHUNK_CHARS,len(text))
        chunk=text[start:end]
        if end<len(text):
            for sep in["\n\n","\n",". "]:
                pos=chunk.rfind(sep,CHUNK_CHARS//2)
                if pos!=-1: chunk=chunk[:pos+len(sep)];end=start+pos+len(sep);break
        chunk=chunk.strip()
        if len(chunk)>=50: chunks.append(chunk)
        start=end-CHUNK_OVERLAP
    return chunks

def post_json(url,headers,data,timeout=30):
    req=urllib.request.Request(url,data=json.dumps(data).encode(),headers=headers,method="POST")
    with urllib.request.urlopen(req,context=_SSL,timeout=timeout) as r:
        return json.loads(r.read())

def get_embedding(text):
    r=post_json("https://openrouter.ai/api/v1/embeddings",
                {"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},
                {"model":EMBED_MODEL,"input":text[:8000]})
    return r["data"][0]["embedding"]

def already_exists(idx):
    """Return True if this email index is already in Supabase."""
    url=(f"{SUPABASE_URL}/rest/v1/documents"
         f"?source=eq.email%3AInbox%3A{idx}&source_type=eq.email&select=id&limit=1")
    req=urllib.request.Request(url,
        headers={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}",
                 "Accept":"application/json"},method="GET")
    try:
        with urllib.request.urlopen(req,context=_SSL,timeout=10) as r:
            return len(json.loads(r.read()))>0
    except: return False

def insert_doc(idx,title,content,meta,emb):
    req=urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/documents",
        data=json.dumps({"source":f"email:Inbox:{idx}","source_type":"email",
                         "title":title,"content":content,"metadata":meta,"embedding":emb}).encode(),
        headers={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}",
                 "Content-Type":"application/json","Prefer":"return=minimal"},method="POST")
    with urllib.request.urlopen(req,context=_SSL,timeout=15) as r:
        return r.status<300

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args=sys.argv[1:]
    if not args: print("Usage: ingest_one_eml.py <file.eml> [--dry-run]"); sys.exit(1)
    fpath=args[0]; dry_run="--dry-run" in args

    if not os.path.exists(fpath): print(f"not found: {fpath}"); sys.exit(1)

    fsize=os.path.getsize(fpath)
    if fsize>MAX_EMAIL_BYTES: sys.exit(0)   # skip large, exit 0 (normal skip)

    idx=int(os.path.basename(fpath).replace(".eml",""))

    if not dry_run and already_exists(idx): sys.exit(0)  # already ingested, skip

    raw=open(fpath,"rb").read()
    msg=email.message_from_bytes(raw,policy=email.policy.compat32)

    subject=decode_hdr(msg.get("Subject",""))
    frm=decode_hdr(msg.get("From",""))
    date=decode_hdr(msg.get("Date",""))
    labels=str(msg.get("X-Gmail-Labels",""))
    body=clean_body(get_body(msg))

    frm_addr=frm.split("<")[1].split(">")[0] if "<" in frm else frm
    domain=frm_addr.split("@")[-1].strip().lower() if "@" in frm_addr else ""
    if domain in SKIP_DOMAINS: sys.exit(0)
    if len(body)<60: sys.exit(0)

    full_text=f"From: {frm}\nDate: {date}\nSubject: {subject}\nLabels: {labels}\n\n{body}"
    chunks=chunk_text(full_text)
    if not chunks: sys.exit(0)

    title=f"{subject[:100]} — {frm[:60]}"
    meta={"from":frm[:200],"subject":subject[:200],"date":date[:50],
          "labels":labels[:100],"email_index":idx}

    if dry_run:
        print(f"[DRY {idx}] {subject[:60]} | {len(chunks)} chunk(s)")
        sys.exit(2)

    ok_total=0
    for j,chunk in enumerate(chunks):
        emb=get_embedding(chunk)
        ok=insert_doc(idx,title,chunk,{**meta,"chunk":j+1,"total_chunks":len(chunks)},emb)
        if ok: ok_total+=1
        time.sleep(0.05)

    if ok_total>0:
        print(f"✅ [{idx}] {subject[:55]} | {ok_total} chunks")
        sys.exit(2)   # exit 2 = inserted
    else:
        print(f"❌ [{idx}] {subject[:55]} | 0 chunks inserted")
        sys.exit(1)

if __name__=="__main__":
    main()
