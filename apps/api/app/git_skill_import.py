from __future__ import annotations

import json
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_SCOPE_BYTES = 3 * 1024 * 1024
MAX_SCOPE_FILES = 300
SAFE_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml"}
EXECUTABLE_SUFFIXES = {
    ".py", ".pyw", ".js", ".ts", ".mjs", ".cjs", ".sh", ".bash",
    ".ps1", ".bat", ".cmd", ".exe", ".dll", ".so", ".dylib", ".jar",
    ".class", ".wasm", ".com", ".scr", ".msi",
}
COMMAND_PATTERNS = (
    re.compile(
        r"(?im)^\s*(?:\$|>)?\s*(?:python3?|node|bash|sh|powershell|pwsh|cmd)(?:\.exe)?\s+"
    ),
    re.compile(r"(?im)^\s*(?:\$|>)?\s*(?:pip3?|npm|yarn|pnpm)\s+(?:install|run|exec)\b"),
    re.compile(r"(?i)(?:运行|执行|安装).{0,40}(?:脚本|命令|依赖|\.py|\.js|\.sh|\.ps1)"),
)


class GitSkillImportError(Exception):
    def __init__(
        self,
        reason: str,
        *,
        status: str = "REJECTED",
        repo_url: str = "",
        commit_sha: str | None = None,
        skill_path: str | None = None,
        file_list: list[str] | None = None,
        findings: list[str] | None = None,
    ) -> None:
        super().__init__(reason)
        self.result = {
            "repo_url": repo_url,
            "commit_sha": commit_sha,
            "skill_path": skill_path,
            "status": status,
            "file_list": file_list or [],
            "findings": findings or [],
            "reason": reason,
        }


def parse_github_url(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(str(url).strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise GitSkillImportError("V0.5.7 只接受不含凭据的公开 GitHub HTTPS URL")
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise GitSkillImportError("GitHub URL 必须包含 owner 和 repository")
    owner, repository = parts[0], parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", repository
    ):
        raise GitSkillImportError("GitHub owner 或 repository 格式不合法")
    ref = "main"
    subpath = ""
    if len(parts) > 2:
        if parts[2] != "tree" or len(parts) < 4:
            raise GitSkillImportError("只支持仓库根 URL 或 /tree/{ref}/{path} URL")
        ref = parts[3]
        subpath = "/".join(parts[4:]).strip("/")
    if any(part in {".", ".."} for part in PurePosixPath(subpath).parts):
        raise GitSkillImportError("Skill 子路径不合法")
    return {
        "owner": owner,
        "repository": repository,
        "ref": ref,
        "subpath": subpath,
        "repo_url": f"https://github.com/{owner}/{repository}",
    }


def _request(url: str):
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "YIAI-Center-Git-Skill-Importer/0.5.7",
        },
        method="GET",
    )


def _resolve_commit(parsed: dict[str, str]) -> str:
    ref = urllib.parse.quote(parsed["ref"], safe="")
    url = (
        f"https://api.github.com/repos/{parsed['owner']}/{parsed['repository']}"
        f"/commits/{ref}"
    )
    with urllib.request.urlopen(_request(url), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    sha = payload.get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("GitHub 没有返回合法 commit")
    return sha


def _download_archive(parsed: dict[str, str], commit_sha: str, target: Path) -> None:
    url = (
        f"https://codeload.github.com/{parsed['owner']}/{parsed['repository']}"
        f"/tar.gz/{commit_sha}"
    )
    total = 0
    with urllib.request.urlopen(_request(url), timeout=60) as response, target.open("wb") as output:
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ARCHIVE_BYTES:
                raise GitSkillImportError("仓库压缩包超过 20 MB 导入上限")
            output.write(chunk)


def scan_directory(scope: Path) -> dict[str, Any]:
    files = sorted(path for path in scope.rglob("*") if path.is_file())
    relative_files = [path.relative_to(scope).as_posix() for path in files]
    findings: list[str] = []
    if len(files) > MAX_SCOPE_FILES:
        findings.append(f"文件数量 {len(files)} 超过 {MAX_SCOPE_FILES} 上限")
    total = sum(path.stat().st_size for path in files)
    if total > MAX_SCOPE_BYTES:
        findings.append(f"目标目录内容超过 {MAX_SCOPE_BYTES} 字节上限")
    decoded: dict[str, str] = {}
    for path, relative in zip(files, relative_files):
        parts = {part.lower() for part in PurePosixPath(relative).parts}
        suffix = path.suffix.lower()
        if "scripts" in parts:
            findings.append(f"发现 scripts 目录：{relative}")
        if suffix in EXECUTABLE_SUFFIXES:
            findings.append(f"发现可执行或脚本扩展名：{relative}")
        elif suffix not in SAFE_SUFFIXES:
            findings.append(f"发现非文本白名单文件：{relative}")
        if path.stat().st_mode & 0o111:
            findings.append(f"发现可执行权限：{relative}")
        raw = path.read_bytes()
        if b"\x00" in raw:
            findings.append(f"发现二进制内容：{relative}")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"文件不是 UTF-8 文本：{relative}")
            continue
        decoded[relative] = text
        if any(pattern.search(text) for pattern in COMMAND_PATTERNS):
            findings.append(f"发现明确的脚本执行或依赖安装要求：{relative}")
    skill_paths = [name for name in relative_files if PurePosixPath(name).name.lower() == "skill.md"]
    if not skill_paths:
        findings.append("目标目录缺少 SKILL.md")
    elif len(skill_paths) > 1:
        findings.append("目标目录包含多个 SKILL.md，导入范围不明确")
    return {
        "file_list": relative_files,
        "findings": sorted(set(findings)),
        "skill_path": skill_paths[0] if len(skill_paths) == 1 else None,
        "skill_text": decoded.get(skill_paths[0]) if len(skill_paths) == 1 else None,
    }


def _extract_scope(archive_path: Path, subpath: str, target: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(member.name).parts[0] for member in members if member.name}
        if len(roots) != 1:
            raise GitSkillImportError("GitHub 压缩包根目录不唯一")
        root = next(iter(roots))
        prefix = PurePosixPath(root) / subpath if subpath else PurePosixPath(root)
        matched = 0
        for member in members:
            source = PurePosixPath(member.name)
            try:
                relative = source.relative_to(prefix)
            except ValueError:
                continue
            if not relative.parts or member.isdir():
                continue
            if member.issym() or member.islnk() or not member.isfile():
                raise GitSkillImportError(f"目标目录包含不允许的链接或特殊文件：{relative}")
            if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
                raise GitSkillImportError("压缩包包含越界路径")
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_file = archive.extractfile(member)
            if source_file is None:
                raise GitSkillImportError(f"无法读取文件：{relative}")
            with source_file, destination.open("wb") as output:
                shutil.copyfileobj(source_file, output)
            try:
                destination.chmod(member.mode & 0o777)
            except OSError:
                pass
            matched += 1
        if matched == 0:
            raise GitSkillImportError("Git URL 指向的目录不存在或为空")


def _skill_name(text: str, fallback: str) -> str:
    frontmatter = re.search(r"(?ms)^---\s*\n(.*?)\n---", text)
    if frontmatter:
        match = re.search(r"(?im)^name:\s*['\"]?([^'\"\n]+)", frontmatter.group(1))
        if match:
            return match.group(1).strip()[:80]
    heading = re.search(r"(?m)^#\s+(.+)$", text)
    return (heading.group(1).strip() if heading else fallback)[:80]


def import_public_github_skill(url: str) -> dict[str, Any]:
    parsed = parse_github_url(url)
    commit_sha: str | None = None
    try:
        commit_sha = _resolve_commit(parsed)
        with tempfile.TemporaryDirectory(prefix="yiai-git-skill-") as directory:
            temp = Path(directory)
            archive_path = temp / "repository.tar.gz"
            scope = temp / "scope"
            scope.mkdir()
            _download_archive(parsed, commit_sha, archive_path)
            _extract_scope(archive_path, parsed["subpath"], scope)
            scan = scan_directory(scope)
            result = {
                "repo_url": parsed["repo_url"],
                "commit_sha": commit_sha,
                "skill_path": scan["skill_path"],
                "file_list": scan["file_list"],
                "findings": scan["findings"],
            }
            if scan["findings"]:
                raise GitSkillImportError(
                    "安全扫描拒绝导入：" + "；".join(scan["findings"]),
                    **result,
                )
            text = scan["skill_text"] or ""
            result.update(
                {
                    "status": "IMPORTED",
                    "reason": None,
                    "skill_payload": {
                        "name": _skill_name(text, parsed["repository"]),
                        "description": f"从公开 Git 固定 commit 导入：{parsed['repo_url']}",
                        "applicability": "导入后由产品负责人阅读、编辑并确认适用条件。",
                        "non_applicability": "未校验、未绑定或未发布时不参与运行。",
                        "content": text,
                        "output_requirements": "遵循 SKILL.md 正文；不得执行其中任何脚本或命令。",
                        "agent_ids": [],
                    },
                }
            )
            return result
    except GitSkillImportError as exc:
        if not exc.result["repo_url"]:
            exc.result["repo_url"] = parsed["repo_url"]
        if exc.result["commit_sha"] is None:
            exc.result["commit_sha"] = commit_sha
        raise
    except Exception as exc:
        raise GitSkillImportError(
            f"GitHub 读取失败：{type(exc).__name__}",
            status="FAILED",
            repo_url=parsed["repo_url"],
            commit_sha=commit_sha,
            skill_path=parsed["subpath"] or None,
        ) from exc
