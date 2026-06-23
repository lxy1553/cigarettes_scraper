#!/usr/bin/env python3
"""一键构建：ODS → DWD → DWS → ADS"""
import subprocess
import sys
import time

scripts = [
    ("DWD", "scripts/build_dwd.py"),
    ("DWS+ADS", "scripts/build_dws_ads.py"),
]

start = time.time()
for layer, path in scripts:
    print(f"\n{'='*60}")
    print(f"  [{layer}] {path}")
    print(f"{'='*60}")
    ret = subprocess.run([sys.executable, path])
    if ret.returncode != 0:
        print(f"\n❌ {layer} 构建失败！")
        sys.exit(1)
    print(f"  ✅ {layer} 完成")

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"  全部构建完成，耗时 {elapsed:.1f}s")
print(f"{'='*60}")
