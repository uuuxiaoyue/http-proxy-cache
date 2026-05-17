# HTTP 代理缓存服务器

Python 实现的 HTTP/HTTPS 代理缓存服务器，支持 HTTP 代理转发、智能缓存加速、黑白名单访问控制、Web 管理面板、HTTPS CONNECT 隧道等完整功能。仅使用 Python 标准库，无需安装第三方依赖。

## 功能清单

### 基础功能

| 功能 | 说明 |
|------|------|
| HTTP 代理转发 | 接收客户端 HTTP 请求，解析后转发至目标服务器，将响应回传客户端 |
| 资源缓存 | 对 GET/HEAD 请求结果缓存，重复访问命中时直接返回，避免重复网络请求 |
| 并发连接 | 基于 `ThreadPoolExecutor` 线程池同时处理多个客户端请求 |
| 日志记录 | 记录每次请求的时间、客户端 IP、方法、目标 URL、状态码、缓存命中、响应大小 |

### 拓展功能

| 功能 | 说明 |
|------|------|
| 智能缓存策略 | 基于时间过期 (TTL) + LRU 淘汰 + 访问频率优先级；支持解析 `Cache-Control` / `Expires` 响应头 |
| 黑白名单访问控制 | 支持黑名单模式、白名单模式、关闭三种状态，运行时动态管理，支持通配符匹配 (`*.example.com`) |
| Web 管理面板 | 实时统计仪表盘、热门资源排行、黑/白名单可视化管理、访问控制模式切换、实时日志查看、缓存清空 |
| CLI 管理控制台 | `stats` / `cache` / `blacklist` / `whitelist` / `mode` / `config` / `header` 等交互命令 |
| HTTPS CONNECT 隧道 | 支持 HTTPS 流量的透明转发（双向 TCP 中继），基于 `select` 多路复用 |
| 请求头修改 | 支持添加、覆盖、删除请求头，模拟不同 User-Agent |

## 快速开始

### 环境要求

- Python 3.8+
- 无需安装第三方依赖

### 启动服务器

```bash
# 默认配置（代理端口 8888，Web 面板端口 8890）
python proxy_server.py

# 自定义端口和缓存参数
python proxy_server.py -p 8080 --web-port 8081 --cache-ttl 600 --max-cache 500

# 后台运行（无交互控制台）
python proxy_server.py --no-admin
```

### 配置浏览器

1. 打开系统代理设置
2. HTTP 代理：`localhost:8888`，HTTPS 代理：`localhost:8888`
3. 正常浏览网页，代理自动工作

### 使用 curl 测试

```bash
# HTTP 请求
curl --proxy http://localhost:8888 http://httpbin.org/get

# HTTPS 请求（CONNECT 隧道）
curl --proxy http://localhost:8888 https://httpbin.org/get

# 验证缓存命中（第二次请求应显示 X-Cache: HIT）
curl -I --proxy http://localhost:8888 http://httpbin.org/get
```

## Web 管理面板

启动后浏览器打开 `http://localhost:8890`：

- **实时仪表盘** — 总请求数、缓存命中率、缓存条目、已拦截数、访问控制模式
- **黑/白名单管理** — 可视化添加/删除域名
- **访问控制切换** — 一键切换关闭/黑名单/白名单模式
- **热门资源排行** — URL 和域名访问次数 Top10，含进度条可视化
- **实时日志** — 最近 40 条代理日志，颜色区分缓存命中/拦截/错误
- **缓存清空** — 一键清空所有缓存

页面每 2 秒自动刷新。

## CLI 管理控制台

服务器启动后在终端直接输入命令：

### 统计与监控
| 命令 | 说明 |
|------|------|
| `stats` | 显示请求总数、命中率、热门域名/URL Top10、状态码分布 |
| `cache` | 查看缓存条目数、总大小、命中率 |
| `cache list` | 列出热门缓存资源及访问次数 |
| `clear cache` | 清空所有缓存 |

### 访问控制
| 命令 | 说明 |
|------|------|
| `blacklist list` | 显示黑名单 |
| `blacklist add <域名>` | 添加域名到黑名单 |
| `blacklist del <域名>` | 从黑名单移除域名 |
| `whitelist list` | 显示白名单 |
| `whitelist add <域名>` | 添加域名到白名单 |
| `whitelist del <域名>` | 从白名单移除域名 |
| `mode blacklist` | 切换为黑名单模式 |
| `mode whitelist` | 切换为白名单模式 |
| `mode off` | 关闭访问控制 |

### 配置管理
| 命令 | 说明 |
|------|------|
| `config` | 查看当前配置（端口、TTL、最大缓存等） |
| `config ttl <秒>` | 修改缓存过期时间 |
| `config maxcache <数量>` | 修改最大缓存条目数 |
| `header list` | 显示请求头修改规则 |
| `header add <键> <值>` | 添加自定义请求头 |
| `header del <键>` | 删除自定义请求头 |
| `header ua <User-Agent>` | 修改模拟 User-Agent |
| `help` | 显示帮助信息 |
| `quit` | 停止服务器并退出 |

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-p`, `--port` | 8888 | 代理监听端口 |
| `--web-port` | 8890 | Web 管理面板端口 |
| `--cache-ttl` | 300 | 缓存过期时间（秒） |
| `--max-cache` | 200 | 最大缓存条目数 |
| `--workers` | 50 | 最大并发线程数 |
| `--log-file` | proxy.log | 日志文件路径 |
| `--no-admin` | false | 禁用 CLI 交互控制台 |

## 架构概览

```
proxy_server.py
├── CacheEntry          — 缓存条目（TTL、访问计数、数据存储）
├── CacheManager        — 缓存管理器（LRU + TTL 过期 + 频率淘汰）
├── AccessController    — 黑白名单访问控制（通配符匹配）
├── StatsCollector      — 统计数据收集（请求数、命中率、热门资源）
├── HeaderModifier      — 请求/响应头修改
├── Logger              — 日志记录（分级、格式、文件输出）
├── WebAdmin            — Web 管理面板（仪表盘 HTML + REST API）
├── WebAdminHandler     — HTTP API 请求处理
└── ProxyServer         — 主代理服务器（整合所有模块）
```

### 请求处理流程

```
┌─────────┐     ┌─────────────────────┐     ┌──────────────┐
│  浏览器  │ ──► │   代理服务器 (8888)   │ ──► │  目标服务器    │
└─────────┘     │                     │     └──────────────┘
                │  1. 解析 HTTP 请求    │
                │  2. 访问控制检查       │
                │  3. 缓存查询 ─ HIT → 直接返回
                │  4. 转发目标服务器      │
                │  5. 缓存响应           │
                │  6. 日志记录           │
                │  7. 返回响应           │
                └─────────────────────┘
```

## 测试验证

### 1. 代理访问与缓存对比

```bash
# 第一次访问：X-Cache: MISS（日志显示"代理转发"）
curl -I --proxy http://localhost:8888 http://httpbin.org/get

# 第二次访问：X-Cache: HIT（日志显示"缓存命中"，响应时间明显缩短）
curl -I --proxy http://localhost:8888 http://httpbin.org/get
```

### 2. 日志示例

```
[2026-05-17 20:13:00] [127.0.0.1      ] [GET    ] [MISS] [200] [   276] http://httpbin.org/get [httpbin.org]
[2026-05-17 20:13:03] [127.0.0.1      ] [GET    ] [HIT ] [200] [   276] http://httpbin.org/get 缓存命中 [httpbin.org]
```

### 3. 黑名单拦截演示

```bash
# 在管理控制台执行
blacklist add httpbin.org
mode blacklist

# 访问被拦截 → 403 Forbidden
curl --proxy http://localhost:8888 http://httpbin.org/get
```

### 4. HTTPS 隧道验证

```bash
curl --proxy http://localhost:8888 https://httpbin.org/get
# 日志显示：CONNECT https://httpbin.org:443 隧道建立
```

## 项目结构

```
├── proxy_server.py                           # 全部代码（~1580 行）
├── README.md                                 # 本文件
├── 实验报告.md                                # 实验报告
├── HTTP代理缓存服务器开发实验要求报告书.docx     # 实验要求
├── blacklist.txt / whitelist.txt             # 名单配置（运行时自动创建）
└── proxy.log                                 # 日志文件（运行时自动生成）
```

## 技术要点

- **HTTP 协议解析**：手动实现 HTTP/1.1 请求/响应的解析与构建，正确处理请求行、头部字段和消息体
- **HTTPS 隧道**：收到 CONNECT 请求后建立 TCP 隧道，使用 `select.select()` 双向中继加密流量，代理不接触明文数据
- **缓存一致性**：尊重源服务器的 `Cache-Control: no-store/no-cache/private` 指令，解析 `max-age` 和 `Expires` 计算缓存 TTL
- **线程安全**：缓存操作使用 `threading.Lock` 保护，每个缓存条目独立存储 TTL 避免竞态条件
- **LRU + 频率淘汰**：优先淘汰过期条目，其次淘汰低频访问条目（access_count ≤ 5），最后淘汰最久未使用条目
