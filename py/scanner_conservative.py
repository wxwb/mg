#!/usr/bin/env python3
"""
CCTV端口扫描器 - 保守优化版
100%保持原版逻辑，仅提升并发
"""

import ipaddress
import socket
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import argparse
import sys

# ==================== 默认配置 ====================
IP_RANGES = [
    '60.162.0.0/16',
    '62.234.0.0/16',
    '109.244.144.0/21',
    '109.244.192.0/21',
    '114.225.0.0/16'
]

PORTS = [1234, 3000, 49155, 7788]
DEFAULT_WORKERS = 500
TIMEOUT = 3

# ==============================================

def check_target(ip, port):
    """与原版完全相同的检测逻辑"""
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
    
    # HTTP检测
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

def generate_targets():
    """生成扫描目标"""
    print("\n正在生成扫描目标...")
    targets = []
    total_ips = 0
    
    for ip_range in IP_RANGES:
        net = ipaddress.ip_network(ip_range, strict=False)
        ips = list(net.hosts())
        total_ips += len(ips)
        print(f"  {ip_range}: {len(ips):,} IP")
        for ip in ips:
            for port in PORTS:
                targets.append((str(ip), port))
    
    return targets, total_ips

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='CCTV端口扫描器 - 保守版')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS,
                       help=f'并发线程数 (默认: {DEFAULT_WORKERS})')
    args = parser.parse_args()
    
    print("=" * 60)
    print("  CCTV扫描器 (保守优化版)")
    print("  100%保持原版逻辑，仅提升并发")
    print("=" * 60)
    
    print(f"\n配置信息:")
    print(f"  并发线程: {args.workers}")
    print(f"  HTTP超时: {TIMEOUT}秒")
    print(f"  扫描端口: {PORTS}")
    
    targets, total_ips = generate_targets()
    total_targets = len(targets)
    
    print(f"\n总目标: {total_targets:,}")
    print(f"  (IP: {total_ips:,} × 端口: {len(PORTS)})")
    
    estimated_speed = args.workers * 0.3
    estimated_minutes = total_targets / estimated_speed / 60
    print(f"  预计耗时: {estimated_minutes:.0f}-{estimated_minutes*1.2:.0f} 分钟")
    
    print("\n开始扫描...")
    print("-" * 60)
    start_time = time.time()
    results = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(check_target, ip, port) for ip, port in targets]
        
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            
            if result:
                results.append(result)
                print(f"  ✓ {result}")
            
            if completed % 10000 == 0:
                elapsed = time.time() - start_time
                pct = completed * 100 // total_targets
                speed = completed / elapsed if elapsed > 0 else 0
                remaining = total_targets - completed
                eta = remaining / speed if speed > 0 else 0
                
                print(f"\n  📊 进度: {pct}% ({completed:,}/{total_targets:,})")
                print(f"     速度: {speed:.1f} 目标/秒")
                print(f"     已发现: {len(results)}")
                print(f"     预计剩余: {eta/60:.1f} 分钟\n")
    
    with open('migu.txt', 'w') as f:
        f.write('\n'.join(results))
    
    elapsed = time.time() - start_time
    print("=" * 60)
    print("扫描完成！")
    print(f"  ✅ 发现目标: {len(results)} 个")
    print(f"  ⏱️  总耗时: {elapsed/60:.1f} 分钟 ({elapsed:.0f} 秒)")
    print(f"  🚀 扫描速度: {total_targets/elapsed:.1f} 目标/秒")
    
    if len(results) > 0:
        print(f"\n结果列表:")
        for i, result in enumerate(results[:20], 1):
            print(f"  {i}. {result}")
        if len(results) > 20:
            print(f"  ... 还有 {len(results)-20} 个")
    
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  扫描被中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)