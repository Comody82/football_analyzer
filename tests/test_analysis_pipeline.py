"""
Test per pipeline analisi unificata: Analisi automatica, Ricalcola squadre, clustering globale.
Eseguibili senza GUI: python -m unittest tests.test_analysis_pipeline -v
"""
import json
import tempfile
import unittest
from pathlib import Path


class TestAnalysisPipeline(unittest.TestCase):
    """Test BackendBridge e global_team_clustering."""

    def test_backend_bridge_has_full_analysis_methods(self):
        """BackendBridge espone openFullAnalysis e openReclusterTeams; non crashano con parent=None."""
        from PyQt5.QtWidgets import QApplication
        from backend import BackendBridge

        app = QApplication.instance() or QApplication([])
        bridge = BackendBridge(None)
        self.assertTrue(hasattr(bridge, "openFullAnalysis") and callable(bridge.openFullAnalysis))
        self.assertTrue(hasattr(bridge, "openReclusterTeams") and callable(bridge.openReclusterTeams))
        bridge.openFullAnalysis()
        bridge.openReclusterTeams()

    def test_global_team_clustering_missing_dir(self):
        """run_global_team_clustering su percorso inesistente ritorna False."""
        from analysis.global_team_clustering import run_global_team_clustering

        ok = run_global_team_clustering(str(Path(tempfile.gettempdir()) / "nonexistent_analysis_dir_xyz"))
        self.assertFalse(ok)

    def test_global_team_clustering_missing_player_tracks(self):
        """run_global_team_clustering con cartella senza player_tracks.json ritorna False."""
        from analysis.config import get_analysis_output_path
        from analysis.global_team_clustering import run_global_team_clustering

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(get_analysis_output_path(tmp))
            out.mkdir(parents=True, exist_ok=True)
            (out / "detections").mkdir(exist_ok=True)
            ok = run_global_team_clustering(tmp)
        self.assertFalse(ok)

    def test_global_team_clustering_empty_frames_returns_true(self):
        """run_global_team_clustering con frames vuoti ritorna True (nessuna modifica)."""
        from analysis.config import get_analysis_output_path
        from analysis.global_team_clustering import run_global_team_clustering

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(get_analysis_output_path(tmp))
            out.mkdir(parents=True, exist_ok=True)
            det_dir = out / "detections"
            det_dir.mkdir(exist_ok=True)
            tracks_path = det_dir / "player_tracks.json"
            tracks_path.write_text(json.dumps({"frames": []}, indent=2), encoding="utf-8")
            ok = run_global_team_clustering(tmp)
        self.assertTrue(ok)

    def test_global_team_clustering_with_samples_updates_teams(self):
        """run_global_team_clustering con almeno 3 campioni jersey_hsv aggiorna il campo team."""
        from analysis.config import get_analysis_output_path
        from analysis.global_team_clustering import run_global_team_clustering

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(get_analysis_output_path(tmp))
            out.mkdir(parents=True, exist_ok=True)
            det_dir = out / "detections"
            det_dir.mkdir(exist_ok=True)
            data = {
                "frames": [
                    {
                        "detections": [
                            {"track_id": 1, "team": 0, "jersey_hsv": [0, 200, 200]},
                            {"track_id": 2, "team": 0, "jersey_hsv": [0, 0, 240]},
                            {"track_id": 3, "team": 0, "jersey_hsv": [45, 180, 200]},
                        ]
                    }
                ]
            }
            tracks_path = det_dir / "player_tracks.json"
            tracks_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            ok = run_global_team_clustering(tmp)
            self.assertTrue(ok)
            with open(tracks_path, "r", encoding="utf-8") as f:
                updated = json.load(f)
            teams = [d["team"] for d in updated["frames"][0]["detections"]]
            self.assertLessEqual(set(teams), {0, 1, -1})
            self.assertIn(-1, teams)
