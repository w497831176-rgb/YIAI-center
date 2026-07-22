from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import action_gateway, codrive, db, mcp_runtime, rag, work_orders
from .config import PRODUCT_VERSION, settings
from .git_skill_import import GitSkillImportError, import_public_github_skill
from .mcp_client import StreamableHttpMcpClient, test_connection
from .runtime import execute_chat, sse


STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


class YIAIHandler(BaseHTTPRequestHandler):
    server_version = "YIAI-Center/0.5.13"

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
            elif path == "/api/agents":
                self._send_json(db.list_agent_configs())
            elif path == "/api/skills":
                self._send_json(db.list_skills())
            elif path == "/api/skill-imports":
                self._send_json(db.list_skill_import_attempts())
            elif path == "/api/rag/documents":
                self._send_json(rag.list_documents())
            elif path == "/api/mcp/servers":
                self._send_json(db.list_mcp_servers())
            elif path == "/api/work-orders":
                query = parse_qs(parsed.query)
                scope = str(query.get("scope", ["USER"])[0]).upper()
                status = query.get("status", [None])[0]
                self._send_json(work_orders.list_orders(scope=scope, status=status))
            elif path == "/api/actions":
                query = parse_qs(parsed.query)
                conversation_id = query.get("conversation_id", [None])[0]
                pending_only = str(query.get("pending_only", ["false"])[0]).lower() == "true"
                self._send_json(
                    action_gateway.list_actions(
                        conversation_id=conversation_id, pending_only=pending_only
                    )
                )
            elif path == "/api/codrive/sessions":
                query = parse_qs(parsed.query)
                include_ai_active = str(
                    query.get("include_ai_active", ["true"])[0]
                ).lower() == "true"
                self._send_json(
                    codrive.list_sessions(include_ai_active=include_ai_active)
                )
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
            elif re.fullmatch(r"/api/agents/[^/]+", path):
                agent_id = path.removeprefix("/api/agents/")
                try:
                    self._send_json(db.get_agent_config(agent_id))
                except KeyError:
                    self._send_json({"detail": "Agent not found"}, 404)
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
            elif re.fullmatch(r"/api/work-orders/[^/]+", path):
                work_order_id = path.removeprefix("/api/work-orders/")
                try:
                    self._send_json(work_orders.get_order(work_order_id))
                except KeyError:
                    self._send_json({"detail": "Work order not found"}, 404)
            elif re.fullmatch(r"/api/actions/[^/]+", path):
                action_id = path.removeprefix("/api/actions/")
                try:
                    self._send_json(action_gateway.get_action(action_id))
                except KeyError:
                    self._send_json({"detail": "Action not found"}, 404)
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
            elif path.startswith("/api/conversations/") and path.endswith("/codrive"):
                conversation_id = path.removeprefix("/api/conversations/").removesuffix(
                    "/codrive"
                )
                try:
                    self._send_json(codrive.get_session(conversation_id))
                except KeyError:
                    self._send_json({"detail": "Conversation not found"}, 404)
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
        if re.fullmatch(r"/api/conversations/[^/]+/codrive/return-ai/stream", path):
            self._codrive_return_stream(path)
            return
        try:
            if path == "/api/actions/drafts":
                payload = self._read_json()
                release_id = str(payload.get("release_id", "")).strip()
                if not release_id:
                    release_id = db.get_workspace()["active_release_id"]
                self._send_json(
                    action_gateway.create_draft(
                        tool_name=str(payload.get("tool_name", "")).strip(),
                        payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
                        release_id=release_id,
                        idempotency_key=str(payload.get("idempotency_key", "")).strip(),
                        conversation_id=str(payload.get("conversation_id", "")).strip() or None,
                        actor=str(payload.get("actor", "USER")),
                    ),
                    201,
                )
                return
            action_match = re.fullmatch(r"/api/actions/([^/]+)/(confirm|cancel)", path)
            if action_match:
                action_id, operation = action_match.groups()
                payload = self._read_json()
                try:
                    self._send_json(self._run_action_operation(action_id, operation, payload))
                except KeyError:
                    self._send_json({"detail": "Action not found"}, 404)
                except PermissionError as exc:
                    self._send_json({"detail": str(exc)}, 403)
                except RuntimeError as exc:
                    self._send_json({"detail": str(exc)}, 409)
                except ValueError as exc:
                    self._send_json({"detail": str(exc)}, 409)
                return
            codrive_match = re.fullmatch(
                r"/api/conversations/([^/]+)/codrive/(request|accept|messages)", path
            )
            if codrive_match:
                conversation_id, operation = codrive_match.groups()
                payload = self._read_json()
                try:
                    if operation == "request":
                        result = codrive.request_human(
                            conversation_id,
                            actor=str(payload.get("actor", "USER")),
                            reason=str(payload.get("reason", "")),
                            summary=str(payload.get("summary", "")),
                            expected_version=payload.get("expected_version"),
                        )
                    elif operation == "accept":
                        result = codrive.accept_handoff(
                            conversation_id,
                            expected_version=payload.get("expected_version"),
                        )
                    else:
                        result = codrive.add_staff_message(
                            conversation_id,
                            str(payload.get("content", "")),
                            expected_version=int(payload.get("expected_version", 0)),
                        )
                    self._send_json(result)
                except KeyError:
                    self._send_json({"detail": "Conversation not found"}, 404)
                except RuntimeError as exc:
                    self._send_json({"detail": str(exc)}, 409)
                except ValueError as exc:
                    self._send_json({"detail": str(exc)}, 409)
                return
            if path == "/api/agents":
                try:
                    self._send_json(db.create_agent_config(self._read_json()), 201)
                except ValueError as exc:
                    self._send_json({"detail": str(exc) or "Invalid Agent config"}, 400)
                return
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

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        agent_match = re.fullmatch(r"/api/agents/([^/]+)", path)
        if not agent_match:
            self._send_json({"detail": "Not found"}, 404)
            return
        try:
            self._send_json(db.delete_agent_config(agent_match.group(1)))
        except KeyError:
            self._send_json({"detail": "Agent not found"}, 404)
        except ValueError as exc:
            self._send_json({"detail": str(exc)}, 409)
        except Exception as exc:
            print(f"DELETE {path} failed: {type(exc).__name__}", flush=True)
            self._send_json({"detail": "Internal error"}, 500)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        agent_match = re.fullmatch(r"/api/agents/([^/]+)", path)
        if agent_match:
            try:
                self._send_json(
                    db.save_agent_config(agent_match.group(1), self._read_json())
                )
            except KeyError:
                self._send_json({"detail": "Agent not found"}, 404)
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json({"detail": str(exc) or "Invalid Agent config"}, 400)
            except Exception as exc:
                print(f"PUT {path} failed: {type(exc).__name__}", flush=True)
                self._send_json({"detail": "Internal error"}, 500)
            return
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

    def _run_action_operation(
        self, action_id: str, operation: str, payload: dict
    ) -> dict:
        action_before = action_gateway.get_action(action_id, include_audit=False)
        description = (
            f"确认执行 {action_before['tool_name']}"
            if operation == "confirm"
            else f"取消 {action_before['tool_name']}"
        )
        run = db.prepare_run(
            action_before.get("conversation_id"),
            f"【工单操作】{description}，操作编号 {action_id}",
            release_id_override=action_before["release_id"],
        )
        if not action_before.get("conversation_id"):
            with db.connection() as conn:
                conn.execute(
                    "UPDATE action_requests SET conversation_id=? WHERE id=?",
                    (run["conversation_id"], action_id),
                )
        started = time.perf_counter()
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "run_started",
            {"conversation_id": run["conversation_id"], "source": "action_gateway"},
        )
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "user_message_received",
            {
                "message_id": run["user_message_id"],
                "role": "user",
                "content": run["content"],
            },
        )
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "release_pinned",
            {"release_id": run["release_id"], "release_version": run["release_version"]},
        )
        released_tool = next(
            (
                item
                for item in run["release_config"].get("tools", [])
                if item.get("tool_id") == action_before["tool_name"]
            ),
            None,
        )
        if released_tool is None or not released_tool.get("agent_ids"):
            db.fail_run(run["run_id"], "TOOL_NOT_IN_RELEASE")
            db.append_trace(
                run["run_id"],
                run["release_id"],
                "error",
                {"error_code": "TOOL_NOT_IN_RELEASE", "action_id": action_id},
            )
            raise ValueError("该操作的 Release 快照中没有绑定此 Tool")
        agent_id = str(released_tool["agent_ids"][0])
        agent = next(
            item
            for item in run["release_config"]["agents"]
            if item["id"] == agent_id
        )
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "agent_selected",
            {"agent_id": agent_id, "agent_name": agent["name"], "source": "action_release_binding"},
        )
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "action_confirmation_received" if operation == "confirm" else "action_cancel_received",
            {
                "action_id": action_id,
                "tool_name": action_before["tool_name"],
                "action_version": action_before["version"],
                "confirmation_step": action_before["confirmation_step"],
                "required_confirmations": action_before["required_confirmations"],
            },
        )
        if operation == "confirm":
            action = action_gateway.confirm_action(
                action_id,
                confirmation_token=str(payload.get("confirmation_token", "")),
                expected_version=payload.get("expected_version"),
                confirmation_run_id=run["run_id"],
                actor="USER",
            )
        else:
            action = action_gateway.cancel_action(
                action_id,
                expected_version=payload.get("expected_version"),
                actor="USER",
            )
        if action["status"] == "SUCCEEDED":
            receipt = action.get("receipt") or {}
            answer = (
                f"{receipt.get('message', '操作已成功执行。')}"
                f"工单编号：{receipt.get('work_order_id', '—')}。"
            )
        elif action["status"] == "AWAITING_CONFIRMATION":
            answer = (
                f"第 {action['confirmation_step']} 次确认已记录；"
                f"还需要 {action['remaining_confirmations']} 次确认，当前仍未执行写操作。"
            )
        elif action["status"] == "CANCELLED":
            answer = "操作已取消，工单数据没有发生变化。"
        else:
            answer = (action.get("receipt") or {}).get("message") or "操作未成功执行。"
        latency_ms = round((time.perf_counter() - started) * 1000)
        result = db.finish_run(
            run["run_id"],
            run["release_id"],
            run["conversation_id"],
            agent_id,
            answer,
            latency_ms,
        )
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "action_gateway_completed",
            {
                "action_id": action_id,
                "tool_name": action["tool_name"],
                "status": action["status"],
                "payload": action["payload"],
                "before": action["before"],
                "result": action["result"],
                "receipt": action["receipt"],
                "model_api_cost": 0,
            },
        )
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "assistant_response_completed",
            {
                "message_id": result["message_id"],
                "role": "assistant",
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "content": answer,
            },
        )
        evaluation = db.save_run_evaluation(run["run_id"])
        db.append_trace(
            run["run_id"],
            run["release_id"],
            "evaluation_completed",
            {
                "evaluation_id": evaluation["id"],
                "status": evaluation["status"],
                "score": evaluation["score"],
                "checks": evaluation["checks"],
                "badcase_codes": evaluation["badcase_codes"],
                "scope": "CURRENT_RUN_ONLY",
            },
        )
        done = {
            "run_id": run["run_id"],
            "status": "DONE",
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "release_id": run["release_id"],
            "release_version": run["release_version"],
            "latency_ms": latency_ms,
            "estimated_cost": result["estimated_cost"],
            "estimated_cost_cny": result["estimated_cost_cny"],
            "display_currency": "CNY",
            "action_id": action_id,
            "action_status": action["status"],
            "evaluation": {
                "status": evaluation["status"],
                "score": evaluation["score"],
                "badcase_codes": evaluation["badcase_codes"],
            },
        }
        db.append_trace(run["run_id"], run["release_id"], "done", done)
        return {"action": action, "run": done, "message": answer}

    def _codrive_return_stream(self, path: str) -> None:
        conversation_id = path.removeprefix("/api/conversations/").removesuffix(
            "/codrive/return-ai/stream"
        )
        try:
            payload = self._read_json()
            session = codrive.begin_return_to_ai(
                conversation_id,
                summary=str(payload.get("summary", "")),
                expected_version=int(payload.get("expected_version", 0)),
            )
        except KeyError:
            self._send_json({"detail": "Conversation not found"}, 404)
            return
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._send_json({"detail": str(exc) or "Invalid request"}, 409)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        connected = True
        run_id = None
        success = False
        continuation = (
            "【人机共驾交还】员工已完成当前人工处置并将对话交还 AI。"
            "请读取最近的员工回复、用户消息和处置摘要，继续承接；这不是会话完结，"
            "回答后继续保持待命。"
        )
        if session.get("handoff_summary"):
            continuation += f"\n处置摘要：{session['handoff_summary']}"
        try:
            for chunk in execute_chat(
                conversation_id, continuation, resume_from_human=True
            ):
                lines = chunk.splitlines()
                event_name = next(
                    (line[7:] for line in lines if line.startswith("event: ")), ""
                )
                data_line = next(
                    (line[6:] for line in lines if line.startswith("data: ")), ""
                )
                if data_line:
                    data = json.loads(data_line)
                    if event_name == "run_started":
                        run_id = data.get("run_id")
                    elif event_name == "done":
                        success = True
                    elif event_name == "error":
                        success = False
                if connected:
                    try:
                        self.wfile.write(chunk.encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        connected = False
        except Exception as exc:
            print(f"codrive return stream failed: {type(exc).__name__}", flush=True)
        finally:
            restored = codrive.complete_return_to_ai(
                conversation_id, run_id=run_id, success=success
            )
            if connected:
                try:
                    self.wfile.write(sse("codrive", restored).encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            self.close_connection = True

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
