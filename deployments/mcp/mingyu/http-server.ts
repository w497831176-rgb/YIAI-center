import { createServer as createHttpServer } from 'node:http';
import type { IncomingMessage } from 'node:http';
import { randomUUID } from 'node:crypto';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { registerBaziTool } from './tools/bazi.js';
import { registerZiweiTool } from './tools/ziwei.js';
import { registerBaziZiweiTool } from './tools/bazi-ziwei.js';
import { registerLiuyaoTool } from './tools/liuyao.js';
import { registerMeihuaTool } from './tools/meihua.js';
import { registerXiaoliurenTool } from './tools/xiaoliuren.js';
import { registerJinkoujueTool } from './tools/jinkoujue.js';
import { registerQimenTool } from './tools/qimen.js';
import { registerLiurenTool } from './tools/liuren.js';
import { registerTarotTool } from './tools/tarot.js';
import { registerSsgwTool } from './tools/ssgw.js';
import { registerAlmanacTool } from './tools/almanac.js';
import { registerLenormandTool } from './tools/lenormand.js';
import { registerAstrolabeTool } from './tools/astrolabe.js';
import { registerBaZhaiTool } from './tools/ba_zhai.js';
import { registerZodiacTool } from './tools/zodiac.js';
import { registerTaiyiTool } from './tools/taiyi.js';
import { registerQizhengTool } from './tools/qi_zheng.js';
import { registerXuanKongTool } from './tools/xuan_kong.js';
import { registerResidentialFengshuiTool } from './tools/residential_fengshui.js';
import { registerFoundationTools } from './tools/foundation.js';
import { registerCalendarTools } from './tools/calendar.js';

const MAX_BODY_BYTES = 1_000_000;
const PORT = Number(process.env.PORT || '3001');
type Session = { server: McpServer; transport: StreamableHTTPServerTransport };
const sessions = new Map<string, Session>();

function createMcpServer() {
  const server = new McpServer(
    { name: 'mingyu-mcp-server', version: '0.1.0+8e24d47' },
    {
      capabilities: { tools: {} },
      instructions: '命语 MCP 的远程 Streamable HTTP 适配。工具算法保持上游固定 commit 原样。',
    },
  );
  registerBaziTool(server);
  registerZiweiTool(server);
  registerBaziZiweiTool(server);
  registerLiuyaoTool(server);
  registerMeihuaTool(server);
  registerXiaoliurenTool(server);
  registerJinkoujueTool(server);
  registerQimenTool(server);
  registerLiurenTool(server);
  registerTarotTool(server);
  registerSsgwTool(server);
  registerAlmanacTool(server);
  registerLenormandTool(server);
  registerAstrolabeTool(server);
  registerBaZhaiTool(server);
  registerZodiacTool(server);
  registerTaiyiTool(server);
  registerQizhengTool(server);
  registerXuanKongTool(server);
  registerResidentialFengshuiTool(server);
  registerFoundationTools(server);
  registerCalendarTools(server);
  return server;
}

async function readJsonBody(request: IncomingMessage) {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > MAX_BODY_BYTES) throw new Error('request body too large');
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

const httpServer = createHttpServer(async (request, response) => {
  response.setHeader('Access-Control-Allow-Origin', '*');
  response.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version');
  response.setHeader('Access-Control-Expose-Headers', 'Mcp-Session-Id');
  if (request.method === 'OPTIONS') {
    response.writeHead(204).end();
    return;
  }
  if (request.url === '/health') {
    response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    response.end(JSON.stringify({ status: 'ok', commit: '8e24d474d25d52d8b33533fe6e4dbc50aae6d9c8' }));
    return;
  }
  if (request.url !== '/mcp' || !['POST', 'DELETE'].includes(request.method || '')) {
    response.writeHead(405, { 'Content-Type': 'application/json; charset=utf-8' });
    response.end(JSON.stringify({ error: 'Use POST /mcp' }));
    return;
  }
  try {
    const body = request.method === 'POST' ? await readJsonBody(request) : undefined;
    const sessionId = request.headers['mcp-session-id'];
    let session = typeof sessionId === 'string' ? sessions.get(sessionId) : undefined;
    if (!session) {
      if (request.method !== 'POST' || body?.method !== 'initialize') {
        response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        response.end(JSON.stringify({ error: 'Valid MCP session required; initialize first' }));
        return;
      }
      const mcpServer = createMcpServer();
      let transport!: StreamableHTTPServerTransport;
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        enableJsonResponse: true,
        onsessioninitialized: (id) => sessions.set(id, { server: mcpServer, transport }),
        onsessionclosed: (id) => sessions.delete(id),
      });
      transport.onclose = () => {
        for (const [id, value] of sessions) {
          if (value.transport === transport) sessions.delete(id);
        }
      };
      await mcpServer.connect(transport);
      session = { server: mcpServer, transport };
    }
    await session.transport.handleRequest(request, response, body);
  } catch (error) {
    if (!response.headersSent) {
      response.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify({ error: error instanceof Error ? error.message : 'invalid request' }));
    }
  }
});

httpServer.listen(PORT, '0.0.0.0', () => {
  console.log(`mingyu MCP Streamable HTTP listening on 0.0.0.0:${PORT}/mcp`);
});
