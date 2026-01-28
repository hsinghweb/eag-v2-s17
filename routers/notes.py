from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/notes", tags=["Notes"])

NOTES_ROOT = Path("data/Notes").resolve()


def _resolve_note_path(rel_path: str) -> Path:
    target = (NOTES_ROOT / rel_path).resolve()
    if NOTES_ROOT not in target.parents and target != NOTES_ROOT:
        raise HTTPException(status_code=400, detail="Invalid note path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Note not found")
    return target


@router.get("/list")
async def list_notes(limit: int = 100) -> List[Dict[str, Any]]:
    if not NOTES_ROOT.exists():
        return []
    notes = []
    for path in NOTES_ROOT.rglob("*.md"):
        stat = path.stat()
        notes.append(
            {
                "path": str(path.relative_to(NOTES_ROOT)),
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    notes.sort(key=lambda n: n["updated_at"], reverse=True)
    return notes[:limit]


@router.get("/read")
async def read_note(path: str = Query(..., description="Relative path under data/Notes")):
    note_path = _resolve_note_path(path)
    content = note_path.read_text(encoding="utf-8", errors="ignore")
    return {"path": str(note_path.relative_to(NOTES_ROOT)), "content": content}
