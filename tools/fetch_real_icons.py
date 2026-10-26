import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lgtv
import urllib.request
import ssl
import os
import re

ctx = ssl._create_unverified_context()
session = lgtv.session('192.168.1.68')
res = lgtv.call(session, 'ssap://com.webos.applicationManager/listLaunchPoints')
session.close()

apps = res.get('launchPoints', [])
os.makedirs('app/icons', exist_ok=True)
downloaded = 0

for a in apps:
    aid = a.get('id', '')
    url = a.get('largeIcon') or a.get('icon')
    if not aid or not url:
        continue
    clean_id = re.sub(r'[<>:"/\\|?*]', '_', aid)
    dest = os.path.join('app', 'icons', f'{clean_id}.png')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            data = r.read()
            if len(data) > 500:
                with open(dest, 'wb') as f:
                    f.write(data)
                downloaded += 1
                print(f"[OK] {aid} -> {len(data)} bytes ({dest})")
            else:
                print(f"[WARN] {aid} data too small ({len(data)} bytes)")
    except Exception as e:
        print(f"[ERR] {aid} ({url}): {e}")

print(f"Done! Downloaded {downloaded}/{len(apps)} real icons.")
