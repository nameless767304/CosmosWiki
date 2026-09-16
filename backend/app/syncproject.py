# 파일명: backend/app/syncproject.py
import ast
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import (
    DEFAULT_WORKSPACE_DIR,
    IGNORED_DIR_NAMES,
    SCANNABLE_EXTENSIONS,
    MAX_SYNC_FILE_BYTES
)
from app.database import (
    fetch_all_blueprints_basic,
    fetch_blueprint_id_by_path,
    delete_blueprint_cascade,
    upsert_project_blueprint,
    upsert_project_source_code,
    delete_blueprint_functions_by_file,
    insert_blueprint_function,
    delete_blueprint_relationships_by_source,
    insert_blueprint_relationship
)

logger = logging.getLogger("cosmos_wiki")

router = APIRouter()


class SyncLocalRequest(BaseModel):
    target_dir: str | None = None


def resolve_target_dir(target_dir: str | None) -> Path:
    """Resolve the directory to scan, creating the default workspace if missing."""
    if target_dir:
        path = Path(target_dir).expanduser().resolve()
        if not path.is_dir():
            raise HTTPException(status_code=404, detail=f"디렉터리를 찾을 수 없습니다: {path}")
        return path

    path = Path(DEFAULT_WORKSPACE_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def collect_source_files(root: Path) -> list[Path]:
    """Recursively collect scannable source files, skipping ignored directories."""
    collected = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES and not d.startswith(".")]
        for filename in filenames:
            if Path(filename).suffix.lower() not in SCANNABLE_EXTENSIONS:
                continue
            file_path = Path(dirpath) / filename
            try:
                if file_path.stat().st_size > MAX_SYNC_FILE_BYTES:
                    logger.warning(f"Skipping oversized file: {file_path}")
                    continue
            except OSError as e:
                logger.warning(f"Skipping unreadable file {file_path}: {e}")
                continue
            collected.append(file_path)
    return collected


def read_text_file(file_path: Path) -> str | None:
    try:
        return file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        logger.warning(f"Skipping unreadable file {file_path}: {e}")
        return None


def build_file_summary(rel_path: str, content: str, module_tree: ast.Module | None) -> str:
    if module_tree is not None:
        docstring = ast.get_docstring(module_tree)
        if docstring:
            return docstring.split("\n")[0]
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:200]
    return f"자동 스캔된 파일: {rel_path}"


def extract_functions(module_tree: ast.Module) -> list[dict]:
    functions = []
    for node in ast.walk(module_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in node.args.args]
            is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            signature = f"{is_async}def {node.name}({', '.join(args)})"
            docstring = ast.get_docstring(node)
            summary = docstring.split("\n")[0] if docstring else "정적 AST 인덱싱된 인터페이스"
            functions.append({
                "name": node.name,
                "signature": signature,
                "summary": summary
            })
    return functions


def resolve_relative_base(rel_path: str, level: int) -> str:
    """Compute the dotted package base for a relative import (ImportFrom.level)."""
    parts = Path(rel_path).parent.parts
    up = level - 1
    if up > 0:
        parts = parts[:-up] if len(parts) >= up else ()
    return ".".join(parts)


def extract_import_targets(module_tree: ast.Module, rel_path: str) -> list[str]:
    """Extract dotted module paths referenced by Import/ImportFrom statements."""
    targets = []
    for node in ast.walk(module_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = resolve_relative_base(rel_path, node.level)
                if node.module:
                    targets.append(f"{base}.{node.module}" if base else node.module)
                else:
                    for alias in node.names:
                        targets.append(f"{base}.{alias.name}" if base else alias.name)
            elif node.module:
                targets.append(node.module)
    return targets


@router.post("/api/project/sync-local")
async def sync_local_project(payload: SyncLocalRequest | None = None):
    target_dir = payload.target_dir if payload else None
    root = resolve_target_dir(target_dir)
    logger.info(f"Starting local sync for directory: {root}")

    try:
        files = collect_source_files(root)

        file_records = []  # (rel_path, blueprint_id, module_tree)
        scanned_paths = set()

        for file_path in files:
            content = read_text_file(file_path)
            if content is None:
                continue

            rel_path = file_path.relative_to(root).as_posix()
            scanned_paths.add(rel_path)

            existing_id = fetch_blueprint_id_by_path(rel_path)
            file_id = existing_id or str(uuid.uuid4())

            module_tree = None
            if file_path.suffix.lower() == ".py":
                try:
                    module_tree = ast.parse(content)
                except SyntaxError as e:
                    logger.warning(f"AST parse failed for {rel_path}: {e}")

            summary = build_file_summary(rel_path, content, module_tree)

            upsert_project_blueprint(blueprint_id=file_id, type="file", path=rel_path, summary=summary)
            upsert_project_source_code(file_id, content)

            file_records.append((rel_path, file_id, module_tree))

        # Second pass: functions and import relationships need the full path map,
        # which is only complete once every file has been upserted above.
        functions_indexed = 0
        relations_mapped = 0
        all_blueprints = fetch_all_blueprints_basic()

        for rel_path, file_id, module_tree in file_records:
            delete_blueprint_functions_by_file(file_id)
            delete_blueprint_relationships_by_source(file_id)

            if module_tree is None:
                continue

            for func in extract_functions(module_tree):
                insert_blueprint_function(
                    file_id=file_id,
                    function_name=func["name"],
                    signature=func["signature"],
                    summary=func["summary"]
                )
                functions_indexed += 1

            mapped_target_ids = set()
            for mod in extract_import_targets(module_tree, rel_path):
                expected_suffix = mod.replace(".", "/") + ".py"
                target = next(
                    (bp for bp in all_blueprints if bp["path"].replace("\\", "/").endswith(expected_suffix)),
                    None
                )
                if not target or str(target["id"]) == str(file_id) or target["id"] in mapped_target_ids:
                    continue

                mapped_target_ids.add(target["id"])
                insert_blueprint_relationship(
                    relation_type="imports",
                    source_id=file_id,
                    source_type="file",
                    target_id=target["id"],
                    target_type="file"
                )
                relations_mapped += 1

        # Remove blueprints for files that no longer exist under this root.
        removed_count = 0
        for bp in fetch_all_blueprints_basic():
            bp_path = bp["path"].replace("\\", "/")
            if bp_path in scanned_paths or ".." in Path(bp_path).parts:
                continue
            if not (root / bp_path).exists():
                delete_blueprint_cascade(bp["id"])
                removed_count += 1

        logger.info(
            f"Local sync completed: {len(file_records)} files, "
            f"{functions_indexed} functions, {relations_mapped} relations, {removed_count} removed"
        )

        return {
            "status": "success",
            "target_dir": str(root),
            "scanned_files": len(file_records),
            "functions_indexed": functions_indexed,
            "relations_mapped": relations_mapped,
            "removed_files": removed_count,
            "message": "로컬 코드 동기화가 완료되었습니다."
        }

    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Local sync failed: {err}")
        raise HTTPException(status_code=500, detail=f"로컬 동기화 중 오류가 발생했습니다: {str(err)}")
