#!/usr/bin/env python3
"""
CCTV端口扫描器 - 极限优化版
使用异步IO + 连接池 + 智能超时
"""

import ipaddress
import asyncio
import aiohttp
import aiohttp.client_exceptions
from concurrent.futures import ThreadPoolExecutor
import time
from collections import deque
import socket

# ==================== 优化配置 ====================
IP_RANGES = [
    '60.162.0.0/16',
    '62.234.0.0/16',
    '109.244.144.0/21',
    '109.244.192.0/21',
    '114.225.0.0/16'
]

# 按速度排序的端口（快的放前面）
PORTS = [1234, 7788, 3000, 49155]  # 1234最快

# 极限并发配置
MAX_CONCURRENT_TCP = 2000      # TCP并发连接数
MAX_CONCURRENT_HTTP = 500       # HTTP并发请求数
TCP_TIMEOUT = 1.0              # TCP超时降低到1秒
HTTP_TIMEOUT = 2.0             # HTTP超时2秒
TCP_RETRY = 0                  # 不重试，加快速度

# 连接复用
TCP_KEEPALIVE = False          # 关闭keepalive
NAGLE_ALGO = False             # 禁用Nagle算法

# 缓冲优化
WRITE_BUFFER = 8192            # 增大写缓冲
READ_BUFFER = 16384            # 增大读缓冲

# ==============================================

# 预解析IP为字节格式（加速socket操作）
async def check_target_tcp(ip: str, port: int, semaphore: asyncio.Semaphore):
    """异步TCP端口检测"""
    async with semaphore:
        try:
            # 使用asyncio的open_connection，比socket更高效
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=TCP_TIMEOUT
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False

async def check_target_http(ip: str, port: int, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
    """异步HTTP检测"""
    async with semaphore:
        url = f"http://{ip}:{port}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as resp:
                # 只读取前2KB，足够判断
                content = await resp.content.read(2048)
                if b'cctv' in content.lower():
                    return f"{ip}:{port}"
        except:
            pass
        return None

async def scan_worker(ip: str, port: int, 
                      tcp_sem: asyncio.Semaphore,
                      http_sem: asyncio.Semaphore,
                      session: aiohttp.ClientSession,
                      results: list,
                      stats: dict):
    """单个目标的扫描工作器"""
    # 先快速TCP检测
    if not await check_target_tcp(ip, port, tcp_sem):
        return
    
    stats['tcp_open'] += 1
    
    # TCP通，再HTTP检测
    result = await check_target_http(ip, port, http_sem, session)
    if result:
        results.append(result)
        stats['found'] += 1
        print(f"  ✓ {result}")

async def main_async():
    print("=" * 60)
    print("  CCTV快速扫描器 (异步极限版)")
    print("=" * 60)
    
    # 预生成所有目标
    print("\n生成目标...")
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
    
    total_targets = len(targets)
    print(f"\n总目标: {total_targets:,}")
    print(f"   IP总数: {total_ips:,}")
    print(f"   端口数: {len(PORTS)}")
    print(f"TCP并发: {MAX_CONCURRENT_TCP}")
    print(f"HTTP并发: {MAX_CONCURRENT_HTTP}")
    
    # 初始化统计
    stats = {'tcp_open': 0, 'found': 0}
    results = []
    
    # 创建信号量控制并发
    tcp_sem = asyncio.Semaphore(MAX_CONCURRENT_TCP)
    http_sem = asyncio.Semaphore(MAX_CONCURRENT_HTTP)
    
    # 创建HTTP会话，配置连接池优化
    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT_HTTP,
        limit_per_host=MAX_CONCURRENT_HTTP,
        ttl_dns_cache=300,           # DNS缓存5分钟
        enable_cleanup_closed=True,
        force_close=True,             # 强制关闭连接，不复用
        keepalive_timeout=0,          # 不保持连接
    )
    
    # 设置更激进的超时
    timeout = aiohttp.ClientTimeout(
        total=HTTP_TIMEOUT,
        connect=1,
        sock_read=2
    )
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={'User-Agent': 'Mozilla/5.0', 'Connection': 'close'}  # 强制关闭
    ) as session:
        
        print("\n开始扫描...")
        start = time.time()
        
        # 创建所有任务
        tasks = []
        for ip, port in targets:
            task = asyncio.create_task(
                scan_worker(ip, port, tcp_sem, http_sem, session, results, stats)
            )
            tasks.append(task)
            
            # 分批显示进度
            if len(tasks) % 10000 == 0:
                await asyncio.sleep(0)  # 让出控制权
        
        # 使用as_completed监控进度
        completed = 0
        last_log_time = time.time()
        
        for coro in asyncio.as_completed(tasks):
            completed += 1
            await coro  # 等待完成
            
            # 每5秒或每10000个任务显示进度
            now = time.time()
            if now - last_log_time >= 5 or completed % 10000 == 0:
                pct = completed * 100 // total_targets
                elapsed = now - start
                speed = completed / elapsed if elapsed > 0 else 0
                print(f"  📊 进度: {pct}% ({completed:,}/{total_targets:,}) "
                      f"速度: {speed:.0f}/s "
                      f"TCP通:{stats['tcp_open']:,} "
                      f"发现:{len(results)}")
                last_log_time = now
    
    # 保存结果
    with open('migu.txt', 'w') as f:
        f.write('\n'.join(results))
    
    # 统计
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"完成！发现 {len(results)} 个目标")
    print(f"   TCP开放: {stats['tcp_open']:,} ({stats['tcp_open']/total_targets*100:.2f}%)")
    print(f"   扫描速度: {total_targets/elapsed:.1f} 目标/秒")
    print(f"   总耗时: {elapsed/60:.1f} 分钟")
    print("=" * 60)

def main():
    """入口函数"""
    # 设置事件循环策略（Linux下使用更高效的uvloop）
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        print("✓ 使用uvloop加速")
    except ImportError:
        print("⚠ 使用标准asyncio（安装uvloop可提速30%）")
    
    # 运行主函数
    asyncio.run(main_async())

if __name__ == "__main__":
    main()