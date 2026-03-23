"""
Registry delle calibrazioni campo.
Ogni calibrazione = nome + homography_matrix + dimensioni campo.
Riutilizzabile su più progetti (stessa camera, stesso campo).
"""
import json
import uuid
from datetime import datetime
from pathlib import Path


class CalibrationRegistry:
    def __init__(self, base_path: str):
        self._path = Path(base_path) / 'data' / 'calibrations.json'
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {'calibrations': []}

    def _save(self):
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def list_calibrations(self) -> list:
        return list(self._data.get('calibrations', []))

    def get(self, cal_id: str) -> dict | None:
        for c in self._data.get('calibrations', []):
            if c['id'] == cal_id:
                return c
        return None

    def save(self, name: str, matrix: list, src_points: list,
             dst_points: list, field_w: float = 105.0, field_h: float = 68.0) -> str:
        """Salva una nuova calibrazione e ritorna il suo ID."""
        cal_id = str(uuid.uuid4())[:8]
        entry = {
            'id': cal_id,
            'name': name,
            'matrix': matrix,          # 3x3 homography come lista nested
            'src_points': src_points,  # punti pixel cliccati sul video
            'dst_points': dst_points,  # coordinate reali corrispondenti (metri)
            'field_w': field_w,
            'field_h': field_h,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        }
        self._data.setdefault('calibrations', []).append(entry)
        self._save()
        return cal_id

    def rename(self, cal_id: str, new_name: str) -> bool:
        for c in self._data.get('calibrations', []):
            if c['id'] == cal_id:
                c['name'] = new_name
                self._save()
                return True
        return False

    def delete(self, cal_id: str) -> bool:
        before = len(self._data.get('calibrations', []))
        self._data['calibrations'] = [
            c for c in self._data.get('calibrations', []) if c['id'] != cal_id
        ]
        if len(self._data['calibrations']) < before:
            self._save()
            return True
        return False
