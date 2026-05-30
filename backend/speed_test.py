"""Speed test: 4x LOCAL file upload to SharePoint. Outputs to speed_test.log."""
from __future__ import annotations

import asyncio
import os
import sys
import time
import urllib.parse

import httpx

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speed_test.log")

TENANT_ID = "6c57e51c-678e-48ec-afdf-bcf6026f4208"
CLIENT_ID = "4493df60-6976-4787-8e2f-0bdde31b1499"
CLIENT_SECRET = os.environ.get("SJHL_CLIENT_SECRET", "")
GRAPH_BASE = "https://microsoftgraph.chinacloudapi.cn/v1.0"
AUTH_BASE = "https://login.partner.microsoftonline.cn"
DRIVE_ID = "b!83oe-lVRoEORAp8tCyfBnV4wIAmsFEhGpUswAl_4KgP9zOA9v4c2RJaigMYiSyI2"
BASE_REMOTE = "媒体库/Media/电视剧/综艺/最强大脑 (2014)/Season 1/_speedtest"

FILE_SIZE = 600 * 1024 * 1024  # 600 MB each
CHUNK_SIZE = 40 * 1024 * 1024   # 40 MiB
CONCURRENT = 4

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_testdata")


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fmt_speed(b: int, sec: float) -> str:
    return f"{b / sec / 1024 / 1024:.1f} MiB/s" if sec > 0 else "N/A"


def fmt_b(b: int) -> str:
    return f"{b / 1024 / 1024:.1f} MiB"


async def get_graph_token(client: httpx.AsyncClient) -> str:
    url = f"{AUTH_BASE}/{TENANT_ID}/oauth2/v2.0/token"
    resp = await client.post(url, data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "scope": f"{GRAPH_BASE.split('/v1.0')[0]}/.default", "grant_type": "client_credentials",
    })
    d = resp.json()
    if resp.status_code >= 400:
        raise RuntimeError(f"Auth failed: {d}")
    return d["access_token"]


async def create_session(client: httpx.AsyncClient, token: str, remote_path: str) -> str:
    encoded = urllib.parse.quote(remote_path.lstrip("/"), safe="")
    url = f"{GRAPH_BASE}/drives/{urllib.parse.quote(DRIVE_ID, safe='')}/root:/{encoded}:/createUploadSession"
    resp = await client.post(url, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    }, json={"item": {"@microsoft.graph.conflictBehavior": "replace", "name": remote_path.split("/")[-1]}})
    d = resp.json()
    if resp.status_code >= 400:
        raise RuntimeError(f"Session failed {resp.status_code}: {d}")
    return d["uploadUrl"]


async def upload_file(client: httpx.AsyncClient, session_url: str, file_path: str, total: int, task_id: int) -> dict:
    chunk_times = []
    uploaded = 0
    started = time.perf_counter()

    with open(file_path, "rb") as fh:
        while uploaded < total:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            end = uploaded + len(chunk) - 1
            t0 = time.perf_counter()
            for attempt in range(4):
                try:
                    r = await client.put(session_url, headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {uploaded}-{end}/{total}",
                    }, content=chunk)
                    if r.status_code in (200, 201, 202):
                        break
                    if r.status_code not in (409, 423, 429, 500, 502, 503, 504) or attempt == 3:
                        raise RuntimeError(f"Chunk fail {r.status_code}: {r.text[:200]}")
                    await asyncio.sleep((attempt + 1) * 1.5)
                except (httpx.RemoteProtocolError, httpx.ConnectError):
                    if attempt == 3:
                        raise
                    await asyncio.sleep((attempt + 1) * 0.5)
            elapsed = time.perf_counter() - t0
            chunk_times.append(elapsed)
            uploaded += len(chunk)
            # Log every chunk
            n = len(chunk_times)
            total_chunks = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
            log(f"  #{task_id} chunk {n}/{total_chunks}  {fmt_b(uploaded)}/{fmt_b(total)}  "
                f"{elapsed:.1f}s  {fmt_speed(len(chunk), elapsed)}")

    total_sec = time.perf_counter() - started
    avg_speed = fmt_speed(total, total_sec)
    min_spd = fmt_speed(CHUNK_SIZE, max(chunk_times)) if chunk_times else "N/A"
    max_spd = fmt_speed(CHUNK_SIZE, min(chunk_times)) if chunk_times else "N/A"
    return {"name": os.path.basename(file_path), "size": total, "sec": total_sec, "speed": avg_speed,
            "min_speed": min_spd, "max_speed": max_spd, "chunks": len(chunk_times)}


def create_test_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    files = []
    for i in range(CONCURRENT):
        fpath = os.path.join(DATA_DIR, f"testfile_{i}.bin")
        if not os.path.exists(fpath) or os.path.getsize(fpath) != FILE_SIZE:
            log(f"Creating test file #{i+1} ({fmt_b(FILE_SIZE)}) ...")
            with open(fpath, "wb") as f:
                # Write in 64MB blocks for speed
                block = os.urandom(64 * 1024 * 1024)
                written = 0
                while written < FILE_SIZE:
                    w = min(len(block), FILE_SIZE - written)
                    f.write(block[:w])
                    written += w
        files.append((fpath, FILE_SIZE))
    log(f"Test files ready: {len(files)} x {fmt_b(FILE_SIZE)} in {DATA_DIR}")
    return files


async def main():
    # Clear log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    log("=" * 60)
    log(f"  SPEED TEST: {CONCURRENT}x LOCAL upload ({fmt_b(FILE_SIZE)} each)")
    log(f"  Chunk: {CHUNK_SIZE // 1024 // 1024} MiB  |  Target: SharePoint 世纪互联")
    log("=" * 60)

    # Create test files
    test_files = create_test_files()

    # Auth
    async with httpx.AsyncClient(timeout=None) as ac:
        log("Auth...")
        token = await get_graph_token(ac)
        log("Token OK")

    # Create upload sessions
    async with httpx.AsyncClient(timeout=None) as client:
        sessions = []
        for i, (fpath, fsize) in enumerate(test_files):
            rpath = f"{BASE_REMOTE}/test_{i}.bin"
            sess_url = await create_session(client, token, rpath)
            sessions.append(sess_url)
            log(f"Session #{i+1} created: {rpath}")

        # Upload all concurrently
        log(f"\nStarting {CONCURRENT} concurrent uploads...\n")
        t0 = time.perf_counter()
        tasks = [upload_file(client, sessions[i], test_files[i][0], test_files[i][1], i + 1) for i in range(CONCURRENT)]
        results = await asyncio.gather(*tasks)
        wall = time.perf_counter() - t0

    # Report
    log("\n" + "=" * 60)
    log("  RESULTS")
    log("=" * 60)
    total_bytes = sum(r["size"] for r in results)
    for r in results:
        log(f"  {r['name']:<20} {fmt_b(r['size']):>8}  avg:{r['speed']:>10}  min:{r['min_speed']:>10}  max:{r['max_speed']:>10}  ({r['chunks']} chunks)")

    log(f"\n  Concurrent uploads:  {CONCURRENT}")
    log(f"  File size (each):    {fmt_b(FILE_SIZE)}")
    log(f"  Chunk size:          {fmt_b(CHUNK_SIZE)}")
    log(f"  Total uploaded:      {fmt_b(total_bytes)}")
    log(f"  Wall time:           {wall:.1f}s")
    log(f"  Combined throughput:  {fmt_speed(total_bytes, wall)}")
    log(f"  Per-file speed range: {min(r['speed'] for r in results)} ~ {max(r['speed'] for r in results)}")
    log("")


if __name__ == "__main__":
    if not CLIENT_SECRET:
        print("Set $env:SJHL_CLIENT_SECRET")
        sys.exit(1)
    try:
        asyncio.run(main())
    except Exception as e:
        import traceback
        log(f"FATAL: {e}")
        log(traceback.format_exc())
        sys.exit(1)
