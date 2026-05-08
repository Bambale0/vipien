#!/usr/bin/env python3
import glob
import re
import sqlite3
import subprocess
import time
from collections import defaultdict

DB = "wg_bot.db"
PCAP_PATH = "/tmp/wg_traffic.pcap"
CAPTURE_SECONDS = 20


def db_duplicates():
    out = []
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute(
            "SELECT public_key, COUNT(*), GROUP_CONCAT(config_name) FROM configs WHERE public_key IS NOT NULL AND public_key!='' GROUP BY public_key HAVING COUNT(*)>1"
        )
        rows = cur.fetchall()
        out.append(("public_key_duplicates", rows))
        cur.execute(
            "SELECT preshared_key, COUNT(*), GROUP_CONCAT(config_name) FROM configs WHERE preshared_key IS NOT NULL AND preshared_key!='' GROUP BY preshared_key HAVING COUNT(*)>1"
        )
        rows2 = cur.fetchall()
        out.append(("preshared_key_duplicates", rows2))
        conn.close()
    except Exception as e:
        out.append(("db_error", str(e)))
    return out


def awg_duplicates():
    # parse allowed-ips output
    mapping = defaultdict(list)  # ip -> [pubkeys]
    try:
        proc = subprocess.run(
            ["sudo", "awg", "show", "wg0", "allowed-ips"],
            capture_output=True,
            text=True,
        )
        txt = proc.stdout or ""
        for line in txt.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                pub = parts[0].strip()
                ipraw = parts[1].strip()
                if ipraw and ipraw != "(none)":
                    ip = ipraw.split("/")[0]
                    mapping[ip].append(pub)
    except Exception as e:
        return ("awg_error", str(e))
    duplicates = [
        (ip, len(pubs), pubs) for ip, pubs in mapping.items() if len(pubs) > 1
    ]
    return duplicates


def list_config_addresses():
    out = []
    for path in sorted(glob.glob("wg_configs/*.conf")):
        try:
            with open(path) as f:
                for ln in f:
                    if ln.strip().startswith("Address"):
                        addr = ln.split("=", 1)[1].strip()
                        out.append((path, addr))
                        break
        except Exception as e:
            out.append((path, "error", str(e)))
    return out


def run_capture():
    # capture UDP port 51820 for CAPTURE_SECONDS using timeout
    try:
        subprocess.run(
            [
                "sudo",
                "timeout",
                str(CAPTURE_SECONDS),
                "tcpdump",
                "-i",
                "any",
                "-n",
                "udp",
                "port",
                "51820",
                "-w",
                PCAP_PATH,
            ],
            check=False,
        )
        return ("ok", PCAP_PATH)
    except Exception as e:
        return ("capture_error", str(e))


def analyze_pcap():
    # read pcap and extract source IP counts
    counts = defaultdict(int)
    samples = []
    try:
        proc = subprocess.run(
            ["sudo", "tcpdump", "-nn", "-r", PCAP_PATH], capture_output=True, text=True
        )
        txt = proc.stdout or ""
        # lines like: IP 10.8.1.5.51820 > 89.125.51.145.51820: UDP, length 64
        for line in txt.splitlines():
            m = re.search(r"IP (\S+) >", line)
            if m:
                src = m.group(1)
                # strip trailing .port for IPv4 dotted-quad
                parts = src.split(".")
                if len(parts) > 4 and parts[-1].isdigit():
                    ip = ".".join(parts[:-1])
                else:
                    ip = src
                counts[ip] += 1
                if len(samples) < 20:
                    samples.append(line)
        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        return (sorted_counts, samples)
    except Exception as e:
        return ("analyze_error", str(e))


def main():
    print("=== DB duplicates ===")
    for item in db_duplicates():
        print(item[0])
        print(item[1])

    print("\n=== AWG runtime duplicates ===")
    awg_dup = awg_duplicates()
    print(awg_dup)

    print("\n=== Config file addresses ===")
    for p in list_config_addresses():
        print(p)

    print(f"\n=== Running tcpdump capture for {CAPTURE_SECONDS}s to {PCAP_PATH} ===")
    cap = run_capture()
    print("capture result:", cap)
    if cap[0] == "ok":
        print("\n=== Analyzing pcap ===")
        analysis = analyze_pcap()
        print("top src IPs and counts:")
        print(analysis[0])
        print("\nsample tcpdump lines:")
        for s in analysis[1]:
            print(s)
        print(f"pcap saved at {PCAP_PATH}")


if __name__ == "__main__":
    main()
