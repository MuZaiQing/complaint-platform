#!/usr/bin/env python3
"""CFPB 投诉叙述数据采集（archive.html → 17 份 Export zip → 校验 + manifest）。

来源：https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/
产物：E:\\选拔赛\\data\\narratives\\*.zip + download_manifest.json
下游：解压出的 CSV 即项目 未清洗前的源数据/CCDB/CCDB_Export_*.csv（17 份，Export_5 ~ Export_21）

运行环境：Windows（依赖 curl.exe）；需先将 archive.html 存到工作目录的 work/ 下。

设计要点：
- 并发 3 线程下载，避免被源站限流
- 先用 HEAD 取 Content-Length，校验本地已存在文件与 .part 续传文件的大小
- curl -C - 断点续传 + 5 次重试 + 重试等待
- zipfile.testzip() 做 CRC 校验，防止半截文件
- 记录 sha256 与 zip 成员清单到 download_manifest.json，便于后续溯源
"""
import concurrent.futures
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

dest = Path(r'E:\选拔赛\data\narratives')
dest.mkdir(parents=True, exist_ok=True)
html = Path('work/archive.html').read_text(encoding='utf-8')
urls = list(dict.fromkeys(re.findall(r'`https://files\.consumerfinance\.gov/[^`"<> ]+\.zip', html)))
urls = [u for u in urls if 5 <= int(re.search(r'Export_(\d+)_', u).group(1)) <= 21]
assert len(urls) == 17, len(urls)


def download(url):
    name = url.rsplit('/', 1)[1]
    target = dest / name
    part = dest / (name + '.part')
    print('START ' + name, flush=True)
    headers = subprocess.run(['curl.exe', '-fILsS', '--retry', '3', '--max-time', '90', url],
                             capture_output=True, text=True, check=True).stdout
    sizes = re.findall(r'(?im)^content-length:\s*(\d+)', headers)
    expected = int(sizes[-1]) if sizes else None
    if not target.exists() or (expected and target.stat().st_size != expected):
        subprocess.run(['curl.exe', '-fLsS', '--retry', '5', '--retry-all-errors',
                        '--retry-delay', '2', '--connect-timeout', '30', '--max-time', '1800',
                        '-C', '-', '-o', str(part), url], check=True)
        if expected and part.stat().st_size != expected:
            raise RuntimeError('Size mismatch: ' + name)
        part.replace(target)
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError('CRC failure: ' + bad)
        members = [{'name': i.filename, 'bytes': i.file_size} for i in archive.infolist()]
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    print('OK ' + name + ' ' + str(target.stat().st_size), flush=True)
    return {'file': name, 'url': url, 'bytes': target.stat().st_size,
            'sha256': digest, 'zip_crc_valid': True, 'members': members}


results, errors = [], []
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    futures = {pool.submit(download, u): u for u in urls}
    for future in concurrent.futures.as_completed(futures):
        try:
            results.append(future.result())
        except Exception as exc:
            errors.append({'url': futures[future], 'error': str(exc)})
            print('ERROR ' + str(exc), flush=True)
results.sort(key=lambda r: int(re.search(r'Export_(\d+)_', r['file']).group(1)))
manifest = {
    'source': 'https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/',
    'files': results,
    'errors': errors,
}
(dest / 'download_manifest.json').write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print('SUMMARY ' + json.dumps({'files': len(results),
                               'bytes': sum(r['bytes'] for r in results),
                               'errors': errors}), flush=True)
if errors:
    raise SystemExit(1)
