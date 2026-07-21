import dataclasses
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import db, mcp_runtime
from app.mcp_client import StreamableHttpMcpClient, test_connection as check_connection


READ_TOOL = {
    "name": "read_record",
    "description": "Return a record without side effects",
    "inputSchema": {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True},
}


class FakeMcpHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        method = request.get("method")
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    READ_TOOL,
                    {
                        "name": "delete_record",
                        "description": "Mutates data",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                ]
            }
        elif method == "tools/call":
            result = {
                "content": [
                    {"type": "text", "text": json.dumps({"record": request["params"]["arguments"]})}
                ]
            }
        else:
            result = {}
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Mcp-Session-Id", "session-test")
        event_body = b"event: message\ndata: " + payload + b"\n\n"
        self.send_header("Content-Length", str(len(event_body)))
        self.end_headers()
        self.wfile.write(event_body)


class McpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcpHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}/mcp"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_settings = db.settings
        db.settings = dataclasses.replace(
            self.original_settings, db_path=f"{self.directory.name}/test.sqlite"
        )
        db.init_db()

    def tearDown(self):
        db.settings = self.original_settings
        self.directory.cleanup()

    def payload(self, agent_ids=None):
        return {
            "name": "Fake read-only MCP",
            "git_url": "https://github.com/example/fake-mcp",
            "version_ref": "commit-123",
            "endpoint": self.endpoint,
            "transport": "STREAMABLE_HTTP",
            "auth_type": "NONE",
            "allowed_tools": ["read_record"],
            "declared_read_only_tools": ["read_record"],
            "agent_ids": ["general-service"] if agent_ids is None else agent_ids,
            "runtime_config": {
                "activation_keywords": ["record"],
                "default_arguments": {},
                "result_paths": ["record"],
            },
        }

    def test_streamable_http_session_list_and_call(self):
        client = StreamableHttpMcpClient(self.endpoint)
        initialized = client.initialize()
        self.assertEqual(initialized["serverInfo"]["name"], "fake-mcp")
        self.assertEqual(client.session_id, "session-test")
        self.assertEqual(len(client.list_tools()), 2)
        response = client.call_tool("read_record", {"id": "42"})
        summary = mcp_runtime.summarize_result(response.payload, ["record"])
        self.assertEqual(summary["selected_data"]["record"]["id"], "42")

    def test_connection_enforces_read_only_allowlist(self):
        result = check_connection(
            self.endpoint, ["read_record"], ["read_record"], "NONE", ""
        )
        self.assertTrue(result["initialize_success"])
        self.assertTrue(result["tools_list_success"])
        self.assertEqual(result["tool_count"], 2)
        self.assertEqual(result["allowed_read_only_tools"], ["read_record"])
        self.assertEqual(result["rejected_tools"][0]["name"], "delete_record")
        self.assertEqual(result["rejected_tools"][0]["reason"], "not in Release read-only Tool allowlist")

    def test_release_hot_swap_preserves_old_mcp_snapshot(self):
        server = db.save_mcp_server(self.payload())
        connected = db.record_mcp_test(
            server["id"], check_connection(self.endpoint, ["read_record"], ["read_record"])
        )
        self.assertEqual(connected["status"], "CONNECTED")
        release_a = db.create_candidate("V0.5.9-mcp-a", "bind remote read-only MCP")
        db.activate_release(release_a["id"])
        old_run = db.prepare_run(None, "read record 42")
        self.assertEqual(old_run["release_config"]["mcp"][0]["server_id"], server["id"])
        db.save_mcp_call_snap(
            old_run["run_id"], old_run["release_id"],
            {
                "server_id": server["id"], "server_name": connected["name"],
                "git_url": connected["git_url"], "version_ref": connected["version_ref"],
                "endpoint": connected["endpoint"], "transport": connected["transport"],
                "tool_name": "read_record", "request_args": {"id": "42"},
                "result_summary": {"record": {"id": "42"}}, "result_length": 42,
                "started_at": "2026-07-21T00:00:00+00:00",
                "finished_at": "2026-07-21T00:00:01+00:00", "latency_ms": 1000,
                "status": "SUCCESS", "error_message": None, "model_api_cost": 0,
            },
        )
        unbound = db.save_mcp_server(self.payload(agent_ids=[]), server["id"])
        self.assertEqual(unbound["status"], "CONNECTED")
        release_b = db.create_candidate("V0.5.9-mcp-b", "unbind remote MCP")
        self.assertEqual(db.get_release_detail(release_b["id"])["diff"]["mcp_removed"], [server["id"]])
        db.activate_release(release_b["id"])
        new_run = db.prepare_run(old_run["conversation_id"], "read record 43")
        self.assertEqual(new_run["release_config"]["mcp"], [])
        self.assertEqual(db.get_run_detail(old_run["run_id"])["mcp_call_snaps"][0]["tool_name"], "read_record")
        self.assertNotEqual(old_run["release_id"], new_run["release_id"])

    def test_preflight_is_schema_checked_and_defaults_are_release_data(self):
        server = {
            "server_id": "mcp_1", "allowed_tools": ["read_record"],
            "tools": [{
                "name": "read_record", "allowed": True,
                "input_schema": READ_TOOL["inputSchema"],
            }],
            "runtime_config": {"default_arguments": {"id": "default"}},
        }
        parsed = mcp_runtime.parse_preflight(
            json.dumps({
                "matched": True, "server_id": "mcp_1", "tool_name": "read_record",
                "arguments": {"id": "explicit"}, "raw_extracted": {"id": "explicit"},
                "missing_fields": [],
            }),
            [server],
        )
        self.assertEqual(parsed["arguments"]["id"], "explicit")
        self.assertEqual(mcp_runtime.validate_arguments(server["tools"][0], parsed["arguments"]), [])
        with self.assertRaises(ValueError):
            mcp_runtime.parse_preflight(
                json.dumps({
                    "matched": True, "server_id": "mcp_1", "tool_name": "delete_record",
                    "arguments": {}, "raw_extracted": {}, "missing_fields": [],
                }),
                [server],
            )

    def test_declarative_extraction_enriches_model_arguments(self):
        server = {
            "server_id": "mcp_2", "allowed_tools": ["read_record"],
            "runtime_config": {
                "default_tool": "read_record",
                "default_arguments": {},
                "argument_extractors": [
                    {"target": "id", "pattern": r"record (?P<value>\d+)", "type": "string"},
                    {"target": "hour", "pattern": r"at (?P<value>\d+)", "type": "integer"},
                ],
                "range_lookups": [{
                    "source": "hour", "target": "period", "ranges": [
                        {"min": 7, "max": 8, "value": 4}
                    ],
                }],
                "required_arguments": ["id", "hour"],
            },
        }
        enriched = mcp_runtime.enrich_preflight(
            {
                "matched": True, "server": server, "server_id": "mcp_2",
                "tool_name": "read_record", "arguments": {"id": "model"},
                "raw_extracted": {}, "missing_fields": ["hour"],
            },
            "read record 42 at 7",
        )
        self.assertEqual(enriched["arguments"], {"id": "42", "hour": 7, "period": 4})
        self.assertEqual(enriched["missing_fields"], [])


if __name__ == "__main__":
    unittest.main()
