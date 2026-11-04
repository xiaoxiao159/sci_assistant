"""MCP Server 入口:python -m app.mcp.server [--transport stdio|http]。

与主后端同代码库、独立进程运行(规范 §4.2/§9):外部 MCP Client → 本 Server
→ app.mcp.tools → RAG 内部接口/服务层 → 同一 RAG Core,不复制逻辑。

Transport:
  - stdio(默认):本地客户端(Claude Desktop / Claude Code 等)以子进程拉起;
    API Key 通过 MCP_API_KEY 环境变量或 --api-key 参数注入。
  - http(streamable-http):uvicorn 监听 MCP_HOST:MCP_PORT;
    每次调用带 X-API-Key 请求头(工具内读取,经 ctx.headers)。

SDK:mcp==2.3.0(v2:FastMCP 更名 MCPServer;锁定版本,不自行实现协议)。
"""
import argparse
import os
import sys

from mcp.server import MCPServer

from app.core.config import settings
from app.mcp import tools

INSTRUCTIONS = """科研问答与写作系统的受控 RAG 工具集。

- search_knowledge_base / query_knowledge_base:知识库语义检索与带引用问答
- get_document_info / get_document_content:授权文档元数据与全文(限长)
- index_document:重新索引(写操作,服务端默认关闭)

所有调用需 API Key 认证;只能访问该 Key 绑定用户名下的资源。证据不足时
query 会明确说明,不会伪造引用。"""


def build_server() -> MCPServer:
    """构建 MCPServer 并注册工具(供测试与外部嵌入复用)。"""
    server = MCPServer(
        name="sci_assistant",
        title="sci_assistant RAG Tools",
        version="1.0.0",
        instructions=INSTRUCTIONS,
    )
    tools.register_tools(server)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.mcp.server", description="sci_assistant MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default=settings.MCP_TRANSPORT,
                        help=f"传输方式(默认 {settings.MCP_TRANSPORT};http=streamable-http)")
    parser.add_argument("--host", default=settings.MCP_HOST, help="http 模式监听地址")
    parser.add_argument("--port", type=int, default=settings.MCP_PORT, help="http 模式监听端口")
    parser.add_argument("--api-key", default=None, help="stdio 模式的 API Key(也可用环境变量 MCP_API_KEY)")
    args = parser.parse_args(argv)

    if not settings.MCP_API_KEYS:
        print("[MCP] 警告: 未配置 MCP_API_KEYS,所有外部调用将被拒绝", file=sys.stderr)

    server = build_server()
    if args.transport == "stdio":
        # stdio 无请求头:Key 由环境变量或命令行注入,进程生命周期内固定
        if args.api_key:
            os.environ["MCP_API_KEY"] = args.api_key
        server.run(transport="stdio")
    else:
        # streamable-http:客户端每次调用带 X-API-Key 头(工具内经 ctx.headers 读取)
        print(f"[MCP] streamable-http 监听 http://{args.host}:{args.port}/mcp", file=sys.stderr)
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
