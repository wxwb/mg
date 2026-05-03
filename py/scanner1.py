#!/usr/bin/env python3
"""
CCTV端口扫描器 - 精简高效版
只访问 IP:端口，检测CCTV关键字
"""

import ipaddress
import socket
import urllib.request
import urllib.error
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import sys

# ==================== 配置区域 ====================
IP_RANGES = [
    '60.162.0.0/16',
    '62.234.0.0/16',
    '109.244.144.0/21',
    '109.244.192.0/21',
    '114.225.0.0/16'
]

PORTS = [1234, 3000, 49155, 7788]

# 性能配置
MAX_WORKERS = 200      # 并发线程数
TCP_TIMEOUT = 2        # TCP连接超时(秒)
HTTP_TIMEOUT = 3       # HTTP请求超时(秒)
# =================================================

class CCTVScanner:
    def __init__(self):
        self.results = []
        self.targets = []
        self.scanned = 0
        self.start_time = None
        
    def print_banner(self):
        print("=" * 60)
        print("  CCTV端口扫描器 v3.0")
        print("  只检测 IP:端口 是否包含 CCTV")
        print("=" * 60)
    
    def generate_targets(self):
        """生成所有扫描目标"""
        print("\n[1/3] 生成扫描目标...")
        
        total_ips = 0
        for ip_range in IP_RANGES:
            network = ipaddress.ip_network(ip_range, strict=False)
            ips = list(network.hosts())
            total_ips += len(ips)
            print(f"  {ip_range}: {len(ips):,} 个IP")
            
            for ip in ips:
                ip_str = str(ip)
                for port in PORTS:
                    self.targets.append((ip_str, port))
        
        print(f"\n  总计: {len(self.targets):,} 个目标 (IP:{total_ips:,} × 端口:{len(PORTS)})")
        return len(self.targets)
    
    def check_target(self, ip, port):
        """检查单个目标"""
        # 1. TCP端口检测
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TCP_TIMEOUT)
        try:
            if sock.connect_ex((ip, port)) != 0:
                sock.close()
                return None
            sock.close()
        except:
            sock.close()
            return None
        
        # 2. HTTP请求 - 只访问根路径
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # 尝试 http 和 https
        for protocol in ['http', 'https']:
            url = f"{protocol}://{ip}:{port}"
            try:
                req = urllib.request.Request(url, headers=headers)
                response = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ssl_context)
                content = response.read(8192)
                response.close()
                
                if b'cctv' in content.lower():
                    return f"{ip}:{port}"
            except:
                continue
        
        return None
    
    def run(self):
        """执行扫描"""
        self.print_banner()
        
        # 生成目标
        if self.generate_targets() == 0:
            print("错误: 没有扫描目标")
            return
        
        # 开始扫描
        print(f"\n[2/3] 开始扫描 (线程数: {MAX_WORKERS})...")
        print("-" * 50)
        
        self.start_time = time.time()
        found = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self.check_target, ip, port): (ip, port) 
                      for ip, port in self.targets}
            
            for future in as_completed(futures):
                self.scanned += 1
                result = future.result()
                
                if result:
                    found.append(result)
                    self.results.append(result)
                    print(f"  ✓ {result}")
                
                # 定期显示进度
                if self.scanned % 10000 == 0 or self.scanned == len(self.targets):
                    elapsed = time.time() - self.start_time
                    percent = self.scanned * 100 // len(self.targets)
                    speed = self.scanned / elapsed if elapsed > 0 else 0
                    print(f"  📊 进度: {percent}% ({self.scanned:,}/{len(self.targets):,}) "
                          f"速度: {speed:.1f}/秒 发现: {len(found)}")
        
        # 保存结果
        print("\n[3/3] 保存结果...")
        print("-" * 50)
        
        if found:
            with open('migu.txt', 'w') as f:
                f.write('\n'.join(found))
            print(f"  ✅ 发现 {len(found)} 个有效目标")
            print("\n结果列表:")
            for r in found:
                print(f"    {r}")
        else:
            print("  ❌ 未发现包含 CCTV 关键字的服务")
            with open('migu.txt', 'w') as f:
                f.write("# 扫描完成，未发现CCTV目标\n")
        
        # 统计
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 60)
        print(f"  扫描完成!")
        print(f"  总目标: {len(self.targets):,}")
        print(f"  发现: {len(found)} 个")
        print(f"  耗时: {elapsed/60:.1f} 分钟")
        print(f"  速度: {len(self.targets)/elapsed:.1f} 目标/秒")
        print("=" * 60)

def main():
    try:
        scanner = CCTVScanner()
        scanner.run()
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)

if __name__ == "__main__":
    main()