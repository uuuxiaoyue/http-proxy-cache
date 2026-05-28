# HTTP 代理缓存服务器

这是一个使用 Python 标准库实现的 HTTP/HTTPS 代理缓存服务器。它可以接收浏览器或 `curl` 发来的代理请求，转发到目标网站，并对可缓存的 HTTP GET 响应进行本地缓存。

## 功能

- HTTP 代理转发：解析请求、连接目标服务器、回传响应。
- GET 缓存：支持 TTL 过期、LRU 淘汰和缓存命中统计。
- HTTPS CONNECT：为 HTTPS 请求建立透明 TCP 隧道。
- 并发处理：使用线程池同时处理多个客户端连接。
- 访问控制：支持黑名单、白名单和关闭访问控制三种模式。
- 日志记录：记录时间、客户端 IP、请求方法、URL、状态码、缓存命中情况和响应大小。
- 管理功能：提供命令行管理控制台和 Web 管理后台。
- 请求头修改：支持在命令行和 Web 后台添加自定义请求头、覆盖请求头和模拟 User-Agent。

## 项目结构

```text
main.py                 # 程序入口和命令行参数
proxy/
  __init__.py
  access_control.py     # 黑名单 / 白名单
  cache.py              # TTL + LRU 缓存管理
  config.py             # 默认配置
  headers.py            # 请求头和响应头修改
  http_utils.py         # HTTP 报文解析与构造
  logging_utils.py      # 日志记录
  server.py             # 代理服务器主流程
  stats.py              # 访问统计
  web_admin.py          # Web 管理后台
```

## 环境要求

- Python 3.8 或更高版本
- 不需要安装第三方依赖

## 启动

```bash
python main.py
```

默认配置：

```text
代理端口：8888
Web 管理后台地址：127.0.0.1
Web 管理后台端口：8890
缓存 TTL：300 秒
最大缓存条目：200
最大工作线程：50
```

自定义启动示例：

```bash
python main.py -p 8080 --web-port 8081 --cache-ttl 600 --max-cache 500
python main.py --web-host 0.0.0.0 --web-port 8890
python main.py --no-admin
```

查看参数：

```bash
python main.py --help
```

## 使用 curl 测试

HTTP 代理：

```bash
curl -i --proxy http://localhost:8888 http://httpbin.org/get
```

缓存命中：

```bash
curl -i --proxy http://localhost:8888 http://httpbin.org/get
curl -i --proxy http://localhost:8888 http://httpbin.org/get
```

第二次响应头中应出现：

```http
X-Cache: HIT
```

HTTPS CONNECT：

```bash
curl -i --proxy http://localhost:8888 https://httpbin.org/get
```

## 浏览器配置

把浏览器或系统代理设置为：

```text
HTTP 代理：localhost:8888
HTTPS 代理：localhost:8888
```

HTTPS 请求只走 CONNECT 隧道，代理不会解密 HTTPS 内容，因此 HTTPS 页面内容不会被缓存。

## Web 管理后台

启动服务后打开：

```text
http://localhost:8890
```

后台可以查看：

- 总请求数
- 缓存命中率
- 缓存条目数
- 黑名单和白名单
- 请求头修改规则
- 热门 URL 和热门域名
- 最近访问日志

## 命令行管理

服务启动后，可在终端输入：

```text
help
stats
cache
cache list
cache clear
blacklist list
blacklist add example.com
blacklist del example.com
whitelist list
whitelist add example.com
whitelist del example.com
mode blacklist
mode whitelist
mode off
config
config ttl 600
config maxcache 500
header list
header add X-Demo value
header del X-Demo
header ua Mozilla/5.0
quit
```

## 访问控制说明

黑名单模式：

```text
默认允许所有网站，只拒绝黑名单里的域名。
```

白名单模式：

```text
默认拒绝所有网站，只允许白名单里的域名。
```

关闭模式：

```text
不做访问控制，全部允许。
```

域名规则支持简单通配：

```text
*.example.com
```

也支持直接填写 IP 或 CIDR 网段：

```text
93.184.216.34
93.184.216.0/24
```

如果名单中填写的是 IP 或网段，而用户访问的是域名，代理会解析域名对应的 IP 后再进行匹配。

## 缓存策略

当前只缓存 HTTP GET 响应。缓存会遵守这些规则：

- `Cache-Control: no-store` 不缓存
- `Cache-Control: no-cache` 不缓存
- `Cache-Control: private` 不缓存
- `Cache-Control: max-age=<秒>` 用作缓存 TTL
- `Expires` 可作为缓存过期时间
- 缓存满时优先清理过期条目，再淘汰低频或最久未使用条目

## 日志

日志格式示例：

```text
[2026-05-28 20:02:33] [127.0.0.1      ] [GET    ] [MISS] [200] [    11] http://127.0.0.1:65033/text [127.0.0.1]
[2026-05-28 20:02:33] [127.0.0.1      ] [GET    ] [HIT ] [200] [    11] http://127.0.0.1:65033/text 缓存命中 [127.0.0.1]
```

运行时会生成：

```text
proxy/proxy.log
proxy/blacklist.txt
proxy/whitelist.txt
```

## 自测

项目包含一个标准库 smoke test，用来快速验证代理转发、缓存、二进制响应、chunked 响应、POST body、请求头修改和 CIDR 黑名单：

```bash
python tests/smoke_test.py
```
