from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db, mcp_runtime, rag
from .config import PRODUCT_VERSION, settings
from .git_skill_import import GitSkillImportError, import_public_github_skill
from .mcp_client import StreamableHttpMcpClient, test_connection
from .runtime import execute_chat, sse


STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


class YIAIHandler(BaseHTTPRequestHandler):
    server_version = "YIAI-Center/0.5.9"

    def log_message(self, format_string: str, *args) -> None:
        print(
            f'{self.address_string()} - [{self.log_date_time_string()}] '
            f'{format_string % args}',
            flush=True,
        )

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("Invalid request body length")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")
        return payload

    def _serve_static(self, path: str) -> None:
        mapping = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/styles.css": "styles.css",
        }
        filename = mapping.get(path)
        if filename is None:
            self._send_json({"detail": "Not found"}, 404)
            return
        target = STATIC_ROOT / filename
        if not target.is_file():
            self._send_json({"detail": "Static file missing"}, 500)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/health":
                database = "ok"
                try:
                    with db.connection() as conn:
                        conn.execute("SELECT 1").fetchone()
                except Exception:
                    database = "error"
                self._send_json(
                    {
                        "status": "ok" if database == "ok" else "degraded",
                        "version": PRODUCT_VERSION,
                        "database": database,
                        "deepseek_configured": bool(settings.deepseek_api_key),
                        "default_model": settings.default_model,
                        "thinking": {
                            "type": "enabled",
                            "reasoning_effort": settings.thinking_effort,
                        },
                        "expert_model_enabled_workflows": [],
                    }
                )
            elif path == "/api/workspace":
                self._send_json(db.get_workspace())
            elif path == "/api/releases":
                self._send_json(db.list_releases())
            elif path == "/api/skills":
                self._send_json(db.list_skills())
            elif path == "/api/skill-imports":
                self._send_json(db.list_skill_import_attempts())
            elif path == "/api/rag/documents":
                self._send_json(rag.list_documents())
            elif path == "/api/mcp/servers":
                self._send_json(db.list_mcp_servers())
            elif path == "/api/runs":
                query = parse_qs(parsed.query)
                limit = max(1, min(200, int(query.get("limit", ["50"])[0])))
                self._send_json(db.list_runs(limit))
            elif path == "/api/conversations":
                query = parse_qs(parsed.query)
                limit = max(1, min(200, int(query.get("limit", ["100"])[0])))
                self._send_json(db.list_conversations(limit))
            elif path.startswith("/api/runs/"):
                run_id = path.removeprefix("/api/runs/")
                try:
                    self._send_json(db.get_run_detail(run_id))
                except KeyError:
                    self._send_json({"detail": "Run not found"}, 404)
            elif re.fullmatch(r"/api/skills/[^/]+", path):
                skill_id = path.removeprefix("/api/skills/")
                try:
                    self._send_json(db.get_skill(skill_id))
                except KeyError:
                    self._send_json({"detail": "Skill not found"}, 404)
            elif re.fullmatch(r"/api/rag/documents/[^/]+", path):
                document_id = path.removeprefix("/api/rag/documents/")
                try:
                    self._send_json(rag.get_document(document_id))
                except KeyError:
                    self._send_json({"detail": "RAG document not found"}, 404)
            elif re.fullmatch(r"/api/mcp/servers/[^/]+", path):
                server_id = path.removeprefix("/api/mcp/servers/")
                try:
                    self._send_json(db.get_mcp_server(server_id))
                except KeyError:
                    self._send_json({"detail": "MCP Server not found"}, 404)
            elif re.fullmatch(r"/api/releases/[^/]+", path):
                release_id = path.removeprefix("/api/releases/")
                try:
                    self._send_json(db.get_release_detail(release_id))
                except KeyError:
                    self._send_json({"detail": "Release not found"}, 404)
            elif path.startswith("/api/conversations/") and path.endswith("/messages"):
                conversation_id = path.removeprefix("/api/conversations/").removesuffix(
                    "/messages"
                )
                self._send_json(db.get_messages(conversation_id))
            elif not path.startswith("/api/"):
                self._serve_static(path)
            else:
                self._send_json({"detail": "Not found"}, 404)
        except (ValueError, json.JSONDecodeError):
            self._send_json({"detail": "Invalid request"}, 400)
        except Exception as exc:
            print(f"GET {path} failed: {type(exc).__name__}", flush=True)
            self._send_json({"detail": "Internal error"}, 500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/chat/stream":
            self._chat_stream()
            return
        try:
            if path == "/api/skills":
                self._send_json(db.save_skill(self._read_json()), 201)
                return
            if path == "/api/rag/preview":
                payload = self._read_json()
                content = str(payload.get("content", ""))
                if not content or len(content) > 100_000:
                    raise ValueError("Invalid RAG content")
                self._send_json(rag.preview_document(content))
                return
            if path == "/api/rag/documents":
                self._send_json(rag.save_document(self._read_json()), 201)
                return
            if path == "/api/mcp/servers":
                self._send_json(db.save_mcp_server(self._read_json()), 201)
                return
            if path == "/api/rag/retrieve":
                payload = self._read_json()
                version_id = str(payload.get("rag_version_id", "")).strip()
                query = str(payload.get("query", "")).strip()
                limit = max(1, min(20, int(payload.get("limit", 5))))
                if not version_id or not query or len(query) > 2000:
                    raise ValueError("Invalid retrieval test")
                try:
                    self._send_json(rag.retrieve(version_id, query, limit))
                except KeyError:
                    self._send_json({"detail": "RAG version not found"}, 404)
                return
            if path == "/api/skill-imports":
                payload = self._read_json()
                url = str(payload.get("url", "")).strip()
                if not url or len(url) > 500:
                    raise ValueError("Invalid Git URL")
                try:
                    imported = import_public_github_skill(url)
                    source = {
                        key: value
                        for key, value in imported.items()
                        if key not in {"skill_payload", "status", "reason"}
                    }
                    skill = db.save_skill(
                        imported["skill_payload"], source_type="GIT", source=source
                    )
                    attempt = db.save_skill_import_attempt(
                        repo_url=imported["repo_url"],
                        commit_sha=imported["commit_sha"],
                        skill_path=imported["skill_path"],
                        status="IMPORTED",
                        file_list=imported["file_list"],
                        findings=imported["findings"],
                        reason=None,
                        skill_id=skill["id"],
                    )
                    self._send_json({"attempt": attempt, "skill": skill}, 201)
                except GitSkillImportError as exc:
                    result = exc.result
                    attempt = db.save_skill_import_attempt(
                        repo_url=result["repo_url"] or url,
                        commit_sha=result["commit_sha"],
                        skill_path=result["skill_path"],
                        status=result["status"],
                        file_list=result["file_list"],
                        findings=result["findings"],
                        reason=result["reason"],
                    )
                    self._send_json(
                        attempt, 422 if result["status"] == "REJECTED" else 502
                    )
                return
            skill_action = re.fullmatch(r"/api/skills/([^/]+)/(validate|disable)", path)
            if skill_action:
                skill_id, action = skill_action.groups()
                try:
                    result = (
                        db.validate_skill(skill_id)
                        if action == "validate"
                        else db.disable_skill(skill_id)
                    )
                    self._send_json(result)
                except KeyError:
                    self._send_json({"detail": "Skill not found"}, 404)
                return
            rag_action = re.fullmatch(r"/api/rag/documents/([^/]+)/(validate|disable)", path)
            if rag_action:
                document_id, action = rag_action.groups()
                try:
                    result = (
                        rag.validate_document(document_id)
                        if action == "validate"
                        else rag.disable_document(document_id)
                    )
                    self._send_json(result)
                except KeyError:
                    self._send_json({"detail": "RAG document not found"}, 404)
                return
            mcp_action = re.fullmatch(r"/api/mcp/servers/([^/]+)/(test|disable|tool-test)", path)
            if mcp_action:
                server_id, action = mcp_action.groups()
                try:
                    if action == "disable":
                        self._send_json(db.disable_mcp_server(server_id))
                        return
                    connection = db.get_mcp_connection_config(server_id)
                    if action == "test":
                        result = test_connection(
                            connection["endpoint"], connection["allowed_tools"],
                            connection["declared_read_only_tools"], connection["auth_type"],
                            connection["auth_value"],
                        )
                        self._send_json(db.record_mcp_test(server_id, result))
                        return
                    payload = self._read_json()
                    tool_name = str(payload.get("tool_name", "")).strip()
                    arguments = payload.get("arguments")
                    if tool_name not in connection["allowed_tools"] or not isinstance(arguments, dict):
                        raise ValueError("Tool is outside the allowlist or arguments are invalid")
                    client = StreamableHttpMcpClient(
                        connection["endpoint"], connection["auth_type"], connection["auth_value"]
                    )
                    client.initialize()
                    response = client.call_tool(tool_name, arguments)
                    self._send_json(
                        {
                            "tool_name": tool_name,
                            "result_length": response.length,
                            "result_summary": mcp_runtime.summarize_result(
                                response.payload,
                                connection["runtime_config"].get("result_paths") or [],
                            ),
                        }
                    )
                except KeyError:
                    self._send_json({"detail": "MCP Server not found"}, 404)
                return
            if path == "/api/releases/candidates":
                payload = self._read_json()
                version = str(payload.get("version", "")).strip()
                summary = str(payload.get("change_summary", "")).strip()
                if not version or len(version) > 80 or not summary or len(summary) > 300:
                    raise ValueError("Invalid candidate")
                try:
                    self._send_json(db.create_candidate(version, summary), 201)
                except sqlite3.IntegrityError:
                    self._send_json({"detail": "Release version already exists"}, 409)
                return

            match = re.fullmatch(r"/api/releases/([^/]+)/(publish|rollback)", path)
            if match:
                release_id, _action = match.groups()
                try:
                    self._send_json(db.activate_release(release_id))
                except KeyError:
                    self._send_json({"detail": "Release not found"}, 404)
                return
            self._send_json({"detail": "Not found"}, 404)
        except (ValueError, json.JSONDecodeError):
            self._send_json({"detail": "Invalid request"}, 400)
        except Exception as exc:
            print(f"POST {path} failed: {type(exc).__name__}", flush=True)
            self._send_json({"detail": "Internal error"}, 500)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        mcp_match = re.fullmatch(r"/api/mcp/servers/([^/]+)", path)
        if mcp_match:
            try:
                self._send_json(db.save_mcp_server(self._read_json(), mcp_match.group(1)))
            except KeyError:
                self._send_json({"detail": "MCP Server not found"}, 404)
            except (ValueError, json.JSONDecodeError):
                self._send_json({"detail": "Invalid request"}, 400)
            except Exception as exc:
                print(f"PUT {path} failed: {type(exc).__name__}", flush=True)
                self._send_json({"detail": "Internal error"}, 500)
            return
        rag_match = re.fullmatch(r"/api/rag/documents/([^/]+)", path)
        if rag_match:
            try:
                self._send_json(rag.save_document(self._read_json(), rag_match.group(1)))
            except KeyError:
                self._send_json({"detail": "RAG document not found"}, 404)
            except (ValueError, json.JSONDecodeError):
                self._send_json({"detail": "Invalid request"}, 400)
            except Exception as exc:
                print(f"PUT {path} failed: {type(exc).__name__}", flush=True)
                self._send_json({"detail": "Internal error"}, 500)
            return
        match = re.fullmatch(r"/api/skills/([^/]+)", path)
        if not match:
            self._send_json({"detail": "Not found"}, 404)
            return
        try:
            self._send_json(db.save_skill(self._read_json(), match.group(1)))
        except KeyError:
            self._send_json({"detail": "Skill not found"}, 404)
        except (ValueError, json.JSONDecodeError):
            self._send_json({"detail": "Invalid request"}, 400)
        except Exception as exc:
            print(f"PUT {path} failed: {type(exc).__name__}", flush=True)
            self._send_json({"detail": "Internal error"}, 500)

    def _chat_stream(self) -> None:
        try:
            payload = self._read_json()
            content = str(payload.get("content", "")).strip()
            conversation_id = payload.get("conversation_id")
            if conversation_id is not None:
                conversation_id = str(conversation_id)
            if not content or len(content) > 8000:
                raise ValueError("Invalid content")
        except (ValueError, json.JSONDecodeError):
            self._send_json({"detail": "Invalid request"}, 400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        connected = True
        try:
            for chunk in execute_chat(conversation_id, content):
                if not connected:
                    continue
                try:
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    connected = False
        except Exception as exc:
            print(f"chat stream failed: {type(exc).__name__}", flush=True)
            if connected:
                try:
                    self.wfile.write(
                        sse(
                            "error",
                            {
                                "status": "ERROR",
                                "error_code": type(exc).__name__,
                                "message": "本轮运行失败，请在平台管理中查看证据。",
                            },
                        ).encode("utf-8")
                    )
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
        finally:
            self.close_connection = True


def run() -> None:
    settings.validate_model_policy()
    db.init_db()
    server = ThreadingHTTPServer(("0.0.0.0", 8000), YIAIHandler)
    print(f"YIAI Center {PRODUCT_VERSION} listening on 0.0.0.0:8000", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
