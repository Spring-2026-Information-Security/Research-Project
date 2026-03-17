#!/usr/bin/env python3
"""Download SecLists GitHub repo zip and extract the 'Passwords' folder to ./passwords/raw/SecLists/"""
import os
import tempfile
import shutil
import requests
import zipfile

ZIP_URL = "https://github.com/danielmiessler/SecLists/archive/refs/heads/master.zip"
OUT_DIR = os.path.join(os.getcwd(), "passwords", "raw", "SecLists")
os.makedirs(OUT_DIR, exist_ok=True)

def download(url, dst):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

def main():
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tf:
            tmp = tf.name
        print("Downloading SecLists zip...")
        download(ZIP_URL, tmp)
        with zipfile.ZipFile(tmp, 'r') as z:
            # detect top-level prefix (e.g., SecLists-master/)
            names = z.namelist()
            prefix = None
            for n in names:
                if n.endswith('/'):
                    prefix = n.split('/')[0] + '/'
                    break
            if not prefix:
                prefix = 'SecLists-master/'
            target_prefix = prefix + 'Passwords/'
            members = [m for m in names if m.startswith(target_prefix)]
            if not members:
                print("No 'Passwords' folder found in archive.")
                return
            for m in members:
                rel = m[len(target_prefix):]
                if not rel:
                    continue
                dest = os.path.join(OUT_DIR, rel)
                if m.endswith('/'):
                    os.makedirs(dest, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(m) as src, open(dest, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
        print("Extracted 'Passwords' to:", OUT_DIR)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

if __name__ == '__main__':
    main()
