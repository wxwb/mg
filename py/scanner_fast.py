#!/usr/bin/env python3
"""
CCTV端口扫描器 - 最快版本
只尝试HTTP，不尝试HTTPS，加快速度
"""

import ipaddress
import socket
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ==================== 配置 ====================
IP_RANGES = [
    '60.162.0.0/16',
    '62.234.0.0/16',
    '109.244.144.0/21',
    '109.244.192.0/21',
    '114.225.0.0/16'
]

PORTS = [1234, 3000, 49155, 7788]
MAX_WORKERS = 300
TIMEOUT = 3
# ==============================================

def check_target(ip, port):
    """快速检测"""
    # TCP检测
    try:
        sock = socket.socket()
        sock.settimeout(2)
        if sock.connect_ex((ip, port)) != 0:
            sock.close()
            return None
        sock.close()
    except:
        return None
    
    # HTTP检测 - 只尝试http
    url = f"http://{ip}:{port}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=TIMEOUT)
        content = response.read(4096)
        response.close()
        
        if b'cctv' in content.lower():
            return f"{ip}:{port}"
    except:
        pass
    
    return None

def main():
    print("=" * 60)
    print("  CCTV快速扫描器 (仅HTTP)")
    print("=" * 60)
    
    # 生成目标
    print("\n生成目标...")
    targets = []
    for ip_range in IP_RANGES:
        net = ipaddress.ip_network(ip_range, strict=False)
        ips = list(net.hosts())
        print(f"  {ip_range}: {len(ips):,} IP")
        for ip in ips:
            for port in PORTS:
                targets.append((str(ip), port))
    
    print(f"\n总目标: {len(targets):,}")
    print(f"线程数: {MAX_WORKERS}")
    print("\n开始扫描...\n")
    
    # 扫描
    start = time.time()
    results = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_target, ip, port) for ip, port in targets]
        
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            
            if result:
                results.append(result)
                print(f"  ✓ {result}")
            
            if completed % 10000 == 0:
                pct = completed * 100 // len(targets)
                print(f"  📊 进度: {pct}% ({completed:,}/{len(targets):,}) 发现: {len(results)}")
    
    # 保存结果
    with open('migu.txt', 'w') as f:
        f.write('\n'.join(results))
    
    # 统计
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"完成! 发现 {len(results)} 个目标")
    print(f"耗时: {elapsed/60:.1f} 分钟")
    print(f"速度: {len(targets)/elapsed:.1f} 目标/秒")
    print("=" * 60)

if __name__ == "__main__":
    main()