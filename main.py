import argparse

from proxy.config import DEFAULT_CACHE_TTL, DEFAULT_MAX_CACHE, DEFAULT_MAX_WORKERS, DEFAULT_PORT
from proxy.server import ProxyServer


def main():
    parser = argparse.ArgumentParser(
        description='HTTP 代理缓存服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                           # 使用默认端口 8888
  python main.py -p 8080                   # 指定代理端口
  python main.py --cache-ttl 600           # 缓存 10 分钟
  python main.py --max-cache 500           # 最多缓存 500 条资源
  python main.py --no-admin                # 禁用命令行管理控制台
        """)
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT,
                        help=f'代理监听端口，默认 {DEFAULT_PORT}')
    parser.add_argument('--cache-ttl', type=int, default=DEFAULT_CACHE_TTL,
                        help=f'默认缓存过期时间，单位秒，默认 {DEFAULT_CACHE_TTL}')
    parser.add_argument('--max-cache', type=int, default=DEFAULT_MAX_CACHE,
                        help=f'最大缓存条目数，默认 {DEFAULT_MAX_CACHE}')
    parser.add_argument('--workers', type=int, default=DEFAULT_MAX_WORKERS,
                        help=f'最大工作线程数，默认 {DEFAULT_MAX_WORKERS}')
    parser.add_argument('--log-file', type=str, default='proxy.log',
                        help='日志文件名，默认 proxy.log')
    parser.add_argument('--no-admin', action='store_true',
                        help='禁用命令行管理控制台')
    parser.add_argument('--web-port', type=int, default=8890,
                        help='Web 管理后台端口，默认 8890')
    parser.add_argument('--web-host', type=str, default='127.0.0.1',
                        help='Web 管理后台监听地址，默认 127.0.0.1')

    args = parser.parse_args()

    proxy = ProxyServer(
        host='0.0.0.0',
        port=args.port,
        cache_ttl=args.cache_ttl,
        max_cache=args.max_cache,
        max_workers=args.workers,
        log_file=args.log_file,
        no_admin=args.no_admin,
        web_port=args.web_port,
        web_host=args.web_host,
    )

    try:
        proxy.run()
    except KeyboardInterrupt:
        proxy.stop()
        print('\n服务器已通过 Ctrl+C 停止。')


if __name__ == '__main__':
    main()
