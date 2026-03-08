"""Repository locale per Dashboard Progetti."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class ProjectMeta:
    id: str
    name: str
    createdAt: str
    updatedAt: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectMeta":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Progetto")),
            createdAt=str(data.get("createdAt", _now_iso())),
            updatedAt=str(data.get("updatedAt", _now_iso())),
        )


class ProjectRepository:
    """Gestisce metadati progetti e file workspace per projectId."""

    def __init__(self, base_dir: str):
        self.base_path = Path(base_dir)
        self.projects_dir = self.base_path / "projects"
        self.index_file = self.base_path / "projects_index.json"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self._save_index([])

    def _load_index(self) -> List[ProjectMeta]:
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            items = payload.get("projects", [])
            return [ProjectMeta.from_dict(x) for x in items]
        except Exception:
            return []

    def _save_index(self, projects: List[ProjectMeta]):
        payload = {"projects": [p.to_dict() for p in projects]}
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def list_recent(self) -> List[ProjectMeta]:
        items = self._load_index()
        return sorted(items, key=lambda p: p.updatedAt, reverse=True)

    def get(self, project_id: str) -> Optional[ProjectMeta]:
        return next((p for p in self._load_index() if p.id == project_id), None)

    def get_project_file_path(self, project_id: str) -> str:
        return str((self.projects_dir / f"{project_id}.json").absolute())

    def create(self, name: str) -> ProjectMeta:
        now = _now_iso()
        project = ProjectMeta(
            id=str(uuid.uuid4()),
            name=(name or "Nuovo Progetto").strip() or "Nuovo Progetto",
            createdAt=now,
            updatedAt=now,
        )
        projects = self._load_index()
        projects.append(project)
        self._save_index(projects)

        # File progetto iniziale vuoto.
        project_file = Path(self.get_project_file_path(project.id))
        if not project_file.exists():
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "project": {}, "events": {}, "clips": []}, f, indent=2, ensure_ascii=False)
        return project

    def delete(self, project_id: str):
        projects = [p for p in self._load_index() if p.id != project_id]
        self._save_index(projects)
        file_path = Path(self.get_project_file_path(project_id))
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass

    def touch(self, project_id: str):
        projects = self._load_index()
        now = _now_iso()
        for p in projects:
            if p.id == project_id:
                p.updatedAt = now
                break
        self._save_index(projects)

    def rename(self, project_id: str, new_name: str) -> bool:
        cleaned = (new_name or "").strip()
        if not cleaned:
            return False
        projects = self._load_index()
        updated = False
        now = _now_iso()
        for p in projects:
            if p.id == project_id:
                p.name = cleaned
                p.updatedAt = now
                updated = True
                break
        if updated:
            self._save_index(projects)
        return updated
