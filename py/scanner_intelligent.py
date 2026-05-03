#!/usr/bin/env python3
"""
CCTV端口扫描器 - 智能优化版
基于M3U8内容特征进行极限优化
"""

import ipaddress
import socket
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
import json
import argparse
import sys
from datetime import datetime
from collections import defaultdict
import threading

# ==================== 默认配置 ====================
IP_RANGES = [
    '60.162.0.0/16',
    '62.234.0.0/16',
    '109.244.144.0/21',
    '109.244.192.0/21',
    '114.225.0.0/16'
]

# 按活跃度排序的端口（活跃的放前面）
PORTS = [3000, 1234, 7788, 49155]

# CCTV响应特征（基于实际M3U8内容）- 使用字符串而非bytes
CCTV_SIGNATURES = [
    '#EXTM3U',
    'x-tvg-url',
    'group-title="央视"',
    'CCTV1综合',
    'CCTV2财经',
    'CCTV',
    'playback.xml',
    'catchup="append"'
]

# 预编译正则表达式（匹配bytes）
CCTV_PATTERN = re.compile(rb'#EXTM3U.*?(?:CCTV|[\xe5\xa4\xae\xe8\xa7\x86])', re.DOTALL)

# ==============================================

class ProgressTracker:
    """进度跟踪器"""
    def __init__(self, total_targets):
        self.total_targets = total_targets
        self.completed = 0
        self.found = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.last_log_time = 0
        
    def update(self, found=False):
        with self.lock:
            self.completed += 1
            if found:
                self.found += 1
                
    def log_progress(self, force=False):
        current_time = time.time()
        with self.lock:
            if force or current_time - self.last_log_time >= 5:
                elapsed = current_time - self.start_time
                speed = self.completed / elapsed if elapsed > 0 else 0
                pct = self.completed * 100 // self.total_targets
                eta = (self.total_targets - self.completed) / speed if speed > 0 else 0
                
                print(f"  📊 进度: {pct}% ({self.completed:,}/{self.total_targets:,}) "
                      f"速度: {speed:.0f}/s 发现: {self.found} "
                      f"ETA: {eta/60:.1f}分钟")
                
                self.last_log_time = current_time
                return True
        return False

class FastCCTVScanner:
    """快速CCTV扫描器"""
    
    def __init__(self, max_workers=800, timeout_tcp=1.5, timeout_http=2.0, verify=False):
        self.max_workers = max_workers
        self.timeout_tcp = timeout_tcp
        self.timeout_http = timeout_http
        self.verify = verify
        self.results = []
        self.stats = defaultdict(int)
        
    def tcp_check(self, ip, port):
        """快速TCP端口检测"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_tcp)
            result = sock.connect_ex((ip, port))
            sock.close()
            self.stats['tcp_checks'] += 1
            return result == 0
        except:
            self.stats['tcp_errors'] += 1
            return False
    
    def http_check(self, ip, port):
        """智能HTTP检测"""
        url = f"http://{ip}:{port}"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Connection': 'close'
                }
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout_http) as response:
                # 只读取必要的数据量
                content = response.read(1024)
                
                # 转换为字符串进行匹配（处理中文）
                content_str = content.decode('utf-8', errors='ignore')
                
                # 快速特征匹配
                if 'group-title="央视"' in content_str:
                    self.stats['http_matches'] += 1
                    return True
                if '#EXTM3U' in content_str and 'CCTV' in content_str:
                    self.stats['http_matches'] += 1
                    return True
                if 'CCTV1综合' in content_str or 'CCTV2财经' in content_str:
                    self.stats['http_matches'] += 1
                    return True
                
                # 逐个特征匹配
                for sig in CCTV_SIGNATURES:
                    if sig in content_str:
                        self.stats['http_matches'] += 1
                        return True
                        
            self.stats['http_checks'] += 1
            return False
        except urllib.error.HTTPError as e:
            self.stats['http_errors'] += 1
            return False
        except (urllib.error.URLError, socket.timeout, socket.error):
            self.stats['http_errors'] += 1
            return False
        except Exception:
            self.stats['http_errors'] += 1
            return False
    
    def ultra_quick_check(self, ip, port):
        """极限快速检测"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_tcp)
            sock.connect((ip, port))
            
            # 发送简化的HTTP请求
            request = f"GET / HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n\r\n"
            sock.send(request.encode())
            
            # 只读取前512字节
            data = sock.recv(512)
            sock.close()
            
            # 检查特征（转为字符串）
            data_str = data.decode('utf-8', errors='ignore')
            if '#EXTM3U' in data_str or ('CCTV' in data_str and 'http' in data_str):
                self.stats['ultra_matches'] += 1
                return True
        except:
            self.stats['ultra_errors'] += 1
        return False
    
    def verify_target(self, ip, port):
        """验证目标并获取频道信息"""
        url = f"http://{ip}:{port}"
        channels = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                content = resp.read(8192).decode('utf-8', errors='ignore')
                
                # 提取频道信息
                for line in content.split('\n'):
                    if 'CCTV' in line and 'tvg-name' in line:
                        match = re.search(r'tvg-name="([^"]+)"', line)
                        if match:
                            channels.append(match.group(1))
                    
                    if len(channels) >= 10:
                        break
                        
            return channels
        except:
            return []
    
    def check_target(self, ip, port, mode='smart', progress=None):
        """检测单个目标"""
        # TCP快速检测
        if not self.tcp_check(ip, port):
            if progress:
                progress.update(False)
            return None
        
        # HTTP检测
        if mode == 'ultra':
            result = self.ultra_quick_check(ip, port)
        else:  # smart mode
            result = self.http_check(ip, port)
        
        if result:
            target = f"{ip}:{port}"
            
            # 可选验证
            if self.verify:
                channels = self.verify_target(ip, port)
                if channels:
                    self.stats['verified'] += 1
                    print(f"  ✓ {target} - 频道: {', '.join(channels[:3])}")
                else:
                    print(f"  ✓ {target}")
            else:
                print(f"  ✓ {target}")
            
            if progress:
                progress.update(True)
            return target
        
        if progress:
            progress.update(False)
        return None
    
    def scan(self, targets, mode='smart'):
        """批量扫描"""
        self.results = []
        progress = ProgressTracker(len(targets))
        
        print(f"\n开始扫描 ({mode}模式)...")
        print(f"并发线程: {self.max_workers}")
        print("-" * 60)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            futures = {
                executor.submit(self.check_target, ip, port, mode, progress): (ip, port)
                for ip, port in targets
            }
            
            # 收集结果
            for future in as_completed(futures):
                result = future.result()
                if result:
                    self.results.append(result)
                
                # 定期显示进度
                progress.log_progress()
        
        elapsed = time.time() - start_time
        self.stats['total_time'] = elapsed
        self.stats['total_targets'] = len(targets)
        self.stats['found'] = len(self.results)
        
        return self.results

def generate_targets(ip_ranges=None, ports=None):
    """生成扫描目标列表"""
    if ip_ranges is None:
        ip_ranges = IP_RANGES
    if ports is None:
        ports = PORTS
    
    print("\n正在生成扫描目标...")
    targets = []
    total_ips = 0
    
    for ip_range in ip_ranges:
        try:
            net = ipaddress.ip_network(ip_range, strict=False)
            ips = list(net.hosts())
            total_ips += len(ips)
            print(f"  {ip_range}: {len(ips):,} IP")
            
            for ip in ips:
                for port in ports:
                    targets.append((str(ip), port))
        except Exception as e:
            print(f"  ✗ 解析失败 {ip_range}: {e}")
    
    return targets, total_ips

def save_results(results, filename='migu.txt'):
    """保存扫描结果"""
    with open(filename, 'w') as f:
        f.write('\n'.join(results))
    print(f"\n结果已保存到: {filename}")

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='CCTV端口扫描器')
    parser.add_argument('--mode', type=str, default='smart', 
                       choices=['smart', 'ultra'],
                       help='扫描模式: smart(智能), ultra(极限)')
    parser.add_argument('--workers', type=int, default=800,
                       help='并发线程数 (默认: 800)')
    parser.add_argument('--timeout-tcp', type=float, default=1.5,
                       help='TCP超时时间 (默认: 1.5秒)')
    parser.add_argument('--timeout-http', type=float, default=2.0,
                       help='HTTP超时时间 (默认: 2.0秒)')
    parser.add_argument('--verify', type=str, default='false',
                       help='是否验证结果 (true/false)')
    parser.add_argument('--output', type=str, default='migu.txt',
                       help='输出文件名 (默认: migu.txt)')
    
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    
    print("=" * 70)
    print("  CCTV端口扫描器 - 智能优化版 v2.0")
    print("  基于M3U8内容特征优化")
    print("=" * 70)
    
    # 显示配置
    print(f"\n配置信息:")
    print(f"  扫描模式: {args.mode}")
    print(f"  并发线程: {args.workers}")
    print(f"  TCP超时: {args.timeout_tcp}秒")
    print(f"  HTTP超时: {args.timeout_http}秒")
    print(f"  结果验证: {args.verify}")
    print(f"  输出文件: {args.output}")
    
    # 生成目标
    targets, total_ips = generate_targets()
    total_targets = len(targets)
    
    print(f"\n扫描统计:")
    print(f"  IP总数: {total_ips:,}")
    print(f"  端口数: {len(PORTS)}")
    print(f"  总目标: {total_targets:,}")
    
    # 估算时间
    estimated_speed = args.workers * 0.5
    estimated_minutes = total_targets / estimated_speed / 60
    print(f"  预计耗时: {estimated_minutes:.0f}-{estimated_minutes*1.2:.0f} 分钟")
    
    # 创建扫描器
    verify = args.verify.lower() == 'true'
    scanner = FastCCTVScanner(
        max_workers=args.workers,
        timeout_tcp=args.timeout_tcp,
        timeout_http=args.timeout_http,
        verify=verify
    )
    
    # 开始扫描
    scan_start = time.time()
    results = scanner.scan(targets, mode=args.mode)
    scan_elapsed = time.time() - scan_start
    
    # 保存结果
    save_results(results, args.output)
    
    # 最终统计
    print("\n" + "=" * 70)
    print("扫描完成！")
    print(f"  ✅ 发现目标: {len(results)} 个")
    print(f"  ⏱️  总耗时: {scan_elapsed/60:.1f} 分钟 ({scan_elapsed:.0f} 秒)")
    print(f"  🚀 平均速度: {total_targets/scan_elapsed:.1f} 目标/秒")
    
    if len(results) > 0:
        print(f"\n发现的目标:")
        for i, target in enumerate(results[:20], 1):
            print(f"  {i:2}. {target}")
        if len(results) > 20:
            print(f"  ... 还有 {len(results)-20} 个")
    
    print("=" * 70)
    
    # 生成统计报告
    stats_file = f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(stats_file, 'w') as f:
        json.dump({
            'scan_time': datetime.now().isoformat(),
            'mode': args.mode,
            'workers': args.workers,
            'total_targets': total_targets,
            'found': len(results),
            'elapsed_seconds': scan_elapsed,
            'speed': total_targets/scan_elapsed,
            'results': results
        }, f, indent=2)
    
    return results

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  扫描被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 扫描出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)