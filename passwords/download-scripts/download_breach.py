#!/usr/bin/env python3
"""Download breach.txt.7z from weakpass and extract breach.txt to ./passwords/raw/breach/"""
import os
import tempfile
import shutil
import requests
import py7zr

URL = "https://weakpass.com/download/2126/breach.txt.7z"
OUT_DIR = os.path.join(os.getcwd(),"passwords", "raw", "breach")
os.makedirs(OUT_DIR, exist_ok=True)

def download(url, dst):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

def main():
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tmp = tf.name
        print("Downloading:", URL)
        download(URL, tmp)
        print("Extracting 7z archive...")
        with py7zr.SevenZipFile(tmp, mode='r') as archive:
            names = archive.getnames()
            target = None
            for n in names:
                if os.path.basename(n).lower() == "breach.txt":
                    target = n
                    break
            if target:
                archive.extract(targets=[target], path=OUT_DIR)
                extracted = os.path.join(OUT_DIR, os.path.basename(target))
                final = os.path.join(OUT_DIR, "breach.txt")
                if os.path.exists(extracted) and extracted != final:
                    shutil.move(extracted, final)
            else:
                archive.extractall(path=OUT_DIR)
                txts = [p for p in os.listdir(OUT_DIR) if p.lower().endswith('.txt')]
                if len(txts) == 1:
                    src = os.path.join(OUT_DIR, txts[0])
                    dst = os.path.join(OUT_DIR, 'breach.txt')
                    if src != dst:
                        shutil.move(src, dst)
        print("Extraction complete:", os.path.join(OUT_DIR, "breach.txt"))
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

if __name__ == '__main__':
    main()
