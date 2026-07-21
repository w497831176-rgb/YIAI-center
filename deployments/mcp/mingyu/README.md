# Mingyu MCP independent deployment

These files reproduce the independently deployed demo service. They are not part of the YIAI Center application image or Compose project.

- Upstream: `https://github.com/Brhiza/mingyu`
- Fixed upstream commit: `8e24d474d25d52d8b33533fe6e4dbc50aae6d9c8`
- Remote directory: `D:\Docker\yiai-mcp-mingyu`
- Compose project and container: `yiai-mcp-mingyu`
- Endpoint: `http://192.168.50.232:19120/mcp`
- Transport: Streamable HTTP
- Adapter scope: transport only. `http-server.ts` registers the upstream Tool implementations and does not copy or rewrite the calculation algorithms.
- Upstream server version: `0.1.0`; adapter-visible version: `0.1.0+8e24d47`
- Node runtime: `22.17.0`, downloaded with fixed SHA-256 `325c0f1261e0c61bcae369a1274028e9cfb7ab7949c05512c5b1e630f7e80e12`
- Package manager: `pnpm@11.9.0`

The deployed server exposes the upstream Tool list. YIAI Center separately enforces the Release-owned read-only allowlist, which contains only `ziwei_calculate` for the Mingyu acceptance Release.

Deployment outline:

1. Clone the upstream repository into its independent directory and check out the fixed commit in detached HEAD state.
2. Place these three files at the paths shown by the Compose and Dockerfile definitions; place `http-server.ts` at `mcp/src/http-server.ts`.
3. Build and start only the `yiai-mcp-mingyu` Compose project.
4. Verify `/health`, then use MCP `initialize`, `tools/list`, and a real `ziwei_calculate` call.

YIAI Center never performs these deployment steps. It stores and connects to the resulting remote Endpoint only.
