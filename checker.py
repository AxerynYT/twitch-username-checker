import random
import string
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime

R = "\033[0m"; G = "\033[92m"; RD = "\033[91m"; Y = "\033[93m"
C = "\033[96m"; B = "\033[1m"; D = "\033[2m"

BANNER = r"""
 _______ _       _ _       _
|__   __| |     (_) |     | |
   | |  | |_ __ _| |_ ___| |__
   | |  | __/ _` | __/ __| '_ \
   | |  | || (_| | || (__| | | |
   |_|   \__\__,_|\__\___|_| |_|
"""

CLIENT_IDS = [
    "kimne78kx3ncx6brgo4mv6wki5h1ko",
    "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
    "ue6666qo983tsx6so1t0vnawi233wa",
    "7ue4gb2s1hup4tp0k7r2sj4e2d69bt",
]

GQL_URL = "https://gql.twitch.tv/gql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    id
    login
  }
}
"""

RATE_LIMIT = 60
RATE_WINDOW = 60

stats = {"checked": 0, "found": 0, "taken": 0, "errors": 0, "requests": 0}
stats_lock = threading.Lock()

rate_lock = threading.Lock()
request_times = []

local = threading.local()

def get_session():
    if not hasattr(local, "session"):
        s = requests.Session()
        s.headers.update({
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=2, max_retries=0)
        s.mount("https://", adapter)
        local.session = s
    return local.session

def wait_for_rate_limit():
    global request_times
    while True:
        with rate_lock:
            now = time.time()
            request_times = [t for t in request_times if now - t < RATE_WINDOW]
            if len(request_times) < RATE_LIMIT:
                request_times.append(now)
                return
            sleep_time = RATE_WINDOW - (now - request_times[0]) + 0.01
        time.sleep(sleep_time)

def check_batch(usernames, retries=2):
    wait_for_rate_limit()
    session = get_session()
    client_id = random.choice(CLIENT_IDS)
    payload = [{"query": QUERY, "variables": {"login": u}} for u in usernames]
    try:
        r = session.post(GQL_URL, headers={"Client-ID": client_id}, json=payload, timeout=15)
        with stats_lock:
            stats["requests"] += 1
        if r.status_code == 429 and retries > 0:
            time.sleep(2 + random.random() * 3)
            return check_batch(usernames, retries - 1)
        if r.status_code != 200:
            if retries > 0:
                time.sleep(1)
                return check_batch(usernames, retries - 1)
            return [(u, "error") for u in usernames]
        data = r.json()
        if not isinstance(data, list):
            data = [data]
        if len(data) != len(usernames):
            if retries > 0:
                return check_batch(usernames, retries - 1)
            return [(u, "error") for u in usernames]
        results = []
        for u, item in zip(usernames, data):
            if not isinstance(item, dict) or "errors" in item:
                results.append((u, "error"))
                continue
            user = item.get("data", {}).get("user") if item.get("data") else None
            results.append((u, "taken" if user else "available"))
        return results
    except Exception:
        if retries > 0:
            time.sleep(1)
            return check_batch(usernames, retries - 1)
        return [(u, "error") for u in usernames]

LETTERS = string.ascii_lowercase
ALNUM = string.ascii_lowercase + string.digits + "_"

def gen(mode, length):
    pool = LETTERS if mode == "l" else ALNUM
    first = random.choice(string.ascii_lowercase + string.digits)
    rest = "".join(random.choices(pool, k=length - 1))
    return first + rest

def ask(prompt, default=None):
    try:
        v = input(prompt).strip()
    except EOFError:
        return default if default is not None else ""
    return v if v else (default if default is not None else "")

def fmt_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}m"
    return f"{seconds/3600:.1f}h"

def run():
    print(C + B + BANNER + R)
    print()

    print(C + "  [*] self-test on 'twitch' ..." + R, end="", flush=True)
    res = check_batch(["twitch"])
    status = res[0][1] if res else "error"
    if status == "taken":
        print(G + " PASS" + R)
    elif status == "available":
        print(RD + " FAIL (twitch reported as available)" + R)
        return
    else:
        print(RD + " ERROR" + R)
        print(Y + "  check your network or IP" + R)
        return

    print()
    spec = ask(D + "    length+mode (e.g. 5c, 6l, 7c): " + R, "5c")
    try:
        length, mode = int(spec[:-1]), spec[-1].lower()
        if mode not in ("l", "c"):
            mode = "c"
        length = max(4, min(25, length))
    except Exception:
        length, mode = 5, "c"

    try:
        target = int(ask(D + "    how many available to find: " + R, "100"))
    except ValueError:
        target = 100

    try:
        workers = int(ask(D + "    workers (2-20): " + R, "8"))
    except ValueError:
        workers = 8
    workers = max(2, min(20, workers))

    try:
        batch_size = int(ask(D + "    batch size (5-50): " + R, "20"))
    except ValueError:
        batch_size = 20
    batch_size = max(5, min(50, batch_size))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    avail_file = f"twitch_available_{length}{mode}_{ts}.txt"
    open(avail_file, "w").close()

    print()
    print(f"    length:      {B}{length}{R}")
    print(f"    mode:        {B}{mode}{R}")
    print(f"    target:      {B}{target}{R}")
    print(f"    workers:     {B}{workers}{R}")
    print(f"    batch size:  {B}{batch_size}{R}")
    print(f"    output:      {B}{avail_file}{R}")
    print()

    start = time.time()
    seen = set()
    af = open(avail_file, "a")
    last_report = 0

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = set()
            max_in_flight = workers * 2
            while stats["found"] < target:
                while len(futures) < max_in_flight:
                    batch = []
                    attempts = 0
                    while len(batch) < batch_size and attempts < batch_size * 10:
                        attempts += 1
                        u = gen(mode, length)
                        if u in seen:
                            continue
                        seen.add(u)
                        batch.append(u)
                    if not batch:
                        break
                    futures.add(ex.submit(check_batch, batch))

                if not futures:
                    break

                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for f in done:
                    try:
                        results = f.result()
                    except Exception:
                        continue
                    for username, status in results:
                        stats["checked"] += 1
                        if status == "available":
                            stats["found"] += 1
                            print(G + B + f"    [+] {username}" + R + D + f"  ({stats['found']}/{target})" + R)
                            af.write(username + "\n")
                            af.flush()
                            if stats["found"] >= target:
                                break
                        elif status == "taken":
                            stats["taken"] += 1
                        else:
                            stats["errors"] += 1

                if stats["checked"] - last_report >= 50:
                    last_report = stats["checked"]
                    el = time.time() - start
                    rate = stats["checked"] / el if el else 0
                    err_pct = stats["errors"] / max(1, stats["checked"]) * 100
                    hit_pct = stats["found"] / max(1, stats["checked"]) * 100
                    if stats["found"] > 0:
                        eta = (target - stats["found"]) * el / stats["found"]
                        eta_str = fmt_time(eta)
                    else:
                        eta_str = "?"
                    print(Y + "    [~] " + R + D
                          + f"checked={stats['checked']} " + R + G
                          + f"found={stats['found']} " + R + RD
                          + f"taken={stats['taken']} " + R + Y
                          + f"err={stats['errors']} ({err_pct:.0f}%) " + R + D
                          + f"hit={hit_pct:.1f}% {rate:.0f}/s eta={eta_str}" + R)
    except KeyboardInterrupt:
        print(Y + B + "\n    [!] interrupted" + R)
    finally:
        af.close()

    el = time.time() - start
    print()
    print(f"    {G}available:{R} {B}{stats['found']}{R}")
    print(f"    {RD}taken:    {R} {B}{stats['taken']}{R}")
    print(f"    {Y}errors:   {R} {B}{stats['errors']}{R}")
    print(f"    {D}requests: {R} {B}{stats['requests']}{R}")
    print(f"    {D}time:     {R} {B}{el:.1f}s{R}")
    print(f"    {C}saved:    {R} {B}{avail_file}{R}")
    print()

if __name__ == "__main__":
    run()
