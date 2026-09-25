import random
import string
import time
import threading
import json
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

stats = {"checked": 0, "found": 0, "taken": 0, "errors": 0}

GQL_URL = "https://gql.twitch.tv/gql"
PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

QUERY = """
query($login: String!) {
  user(login: $login) {
    id
    login
  }
}
"""

RATE_LIMIT = 90
RATE_WINDOW = 60
rate_lock = threading.Lock()
request_times = []

def wait_for_rate_limit():
    global request_times
    while True:
        with rate_lock:
            now = time.time()
            request_times = [t for t in request_times if now - t < RATE_WINDOW]
            if len(request_times) < RATE_LIMIT:
                request_times.append(now)
                return
            oldest = request_times[0]
            sleep_time = RATE_WINDOW - (now - oldest) + 0.05
        time.sleep(sleep_time)

def check(username, debug=False):
    wait_for_rate_limit()

    headers = {
        "Client-ID": PUBLIC_CLIENT_ID,
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    payload = {"query": QUERY, "variables": {"login": username}}

    try:
        r = requests.post(GQL_URL, headers=headers, json=payload, timeout=10)

        if debug:
            print(f"\n--- DEBUG for {username} ---")
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:600]}")
            print("--- END DEBUG ---\n")

        if r.status_code == 429:
            time.sleep(5 + random.random() * 5)
            return check(username, debug)

        if r.status_code != 200:
            return username, "error"

        data = r.json()
        if "errors" in data:
            return username, "error"

        user = data.get("data", {}).get("user")
        if user is None:
            return username, "available"
        else:
            return username, "taken"

    except requests.exceptions.Timeout:
        return username, "error"
    except requests.exceptions.ConnectionError:
        return username, "error"
    except json.JSONDecodeError:
        return username, "error"
    except Exception:
        return username, "error"

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

def run():
    print(C + B + BANNER + R)
    print()

    print(C + "  [*] self-test on 'twitch' ..." + R, end="", flush=True)
    u, status = check("twitch", debug=False)
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
        workers = int(ask(D + "    workers (5-50): " + R, "20"))
    except ValueError:
        workers = 20
    workers = max(5, min(50, workers))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    avail_file = f"twitch_available_{length}{mode}_{ts}.txt"
    open(avail_file, "w").close()

    print()
    print(f"    length:   {B}{length}{R}")
    print(f"    mode:     {B}{mode}{R}")
    print(f"    target:   {B}{target}{R}")
    print(f"    workers:  {B}{workers}{R}")
    print(f"    output:   {B}{avail_file}{R}")
    print()

    start = time.time()
    seen = set()
    af = open(avail_file, "a")
    last_report = 0

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = set()
            max_in_flight = workers * 3
            while stats["found"] < target:
                while len(futures) < max_in_flight:
                    u = gen(mode, length)
                    if u in seen:
                        continue
                    seen.add(u)
                    futures.add(ex.submit(check, u))

                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for f in done:
                    username, status = f.result()
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

                if stats["checked"] - last_report >= 25:
                    last_report = stats["checked"]
                    el = time.time() - start
                    rate = stats["checked"] / el if el else 0
                    err_pct = stats["errors"] / max(1, stats["checked"]) * 100
                    hit_pct = stats["found"] / max(1, stats["checked"]) * 100
                    print(Y + "    [~] " + R + D
                          + f"checked={stats['checked']} " + R + G
                          + f"found={stats['found']} " + R + RD
                          + f"taken={stats['taken']} " + R + Y
                          + f"err={stats['errors']} ({err_pct:.0f}%) " + R + D
                          + f"hit={hit_pct:.1f}% {rate:.1f}/s" + R)
    except KeyboardInterrupt:
        print(Y + B + "\n    [!] interrupted" + R)
    finally:
        af.close()

    el = time.time() - start
    print()
    print(f"    {G}available:{R} {B}{stats['found']}{R}")
    print(f"    {RD}taken:    {R} {B}{stats['taken']}{R}")
    print(f"    {Y}errors:   {R} {B}{stats['errors']}{R}")
    print(f"    {D}time:     {R} {B}{el:.1f}s{R}")
    print(f"    {C}saved:    {R} {B}{avail_file}{R}")
    print()

if __name__ == "__main__":
    run()
