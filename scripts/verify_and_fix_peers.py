#!/usr/bin/env python3
import sqlite3
import subprocess
import tempfile
import fcntl
import os
import time

DB = 'wg_bot.db'
LOCK_PATH = '/var/lock/wg_manager.lock'


def with_lock(fn):
    def wrapped(*a, **k):
        fd = open(LOCK_PATH, 'w')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            return fn(*a, **k)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
            fd.close()
    return wrapped


def get_awg_allowed_ips():
    proc = subprocess.run(['sudo','awg','show','wg0','allowed-ips'], capture_output=True, text=True)
    if proc.returncode != 0:
        return ''
    return proc.stdout


@with_lock
def add_peer(public_key, preshared_key, address):
    # write psk
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.psk') as f:
        f.write(preshared_key)
        psk_path = f.name
    cmd = ['sudo','awg','set','wg0','peer',public_key,'preshared-key',psk_path,'allowed-ips',f'{address}/32']
    proc = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(psk_path)
    return proc.returncode == 0


def main():
    if not os.path.exists(DB):
        print('Database not found:', DB)
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT public_key, preshared_key, address, config_name FROM configs WHERE is_active = 1")
    rows = cur.fetchall()
    allowed = get_awg_allowed_ips()
    print('awg allowed-ips length:', len(allowed))
    missing = []
    for pub, psk, addr, cfg in rows:
        if not pub or not addr:
            continue
        if (pub in allowed) or (f"{addr}/32" in allowed):
            print(f'{cfg} OK')
        else:
            print(f'{cfg} MISSING -> will try to add')
            ok = add_peer(pub, psk, addr)
            time.sleep(0.5)
            allowed = get_awg_allowed_ips()
            if ok and (pub in allowed or f"{addr}/32" in allowed):
                print(f'{cfg} added and verified')
            else:
                print(f'{cfg} add failed; appending to server config as fallback')
                # fallback: append via sudo tee
                peer_block = f"\n[Peer]\nPublicKey = {pub}\nPresharedKey = {psk}\nAllowedIPs = {addr}/32\n"
                p = subprocess.run(['sudo','tee','-a','/etc/amnezia/amneziawg/wg0.conf'], input=peer_block, text=True, capture_output=True)
                if p.returncode == 0:
                    print(f'{cfg} appended to server config')
                else:
                    print(f'{cfg} fallback append failed: ', p.stderr)

    conn.close()

if __name__ == '__main__':
    main()
