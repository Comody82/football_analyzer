"""
Generazione report (Fase 8): JSON completo, CSV, PDF.
Assembla tracking, eventi, metriche, calibrazione in un unico export conforme allo schema Step 0.1.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_analysis_output_path, get_calibration_path
from .player_tracking import get_tracks_path
from .ball_tracking import get_ball_tracks_path


def build_full_result(
    project_analysis_dir: str,
    source: str = "local",
    project_id: Optional[str] = None,
    parameters_used: Optional[Dict] = None,
    manual_events: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Assembla il risultato completo analisi (schema Step 0.1) da cartella progetto.
    Carica tracking, events_engine.json, metrics.json, calibrazione.
    """
    base = Path(project_analysis_dir)
    analysis_output = get_analysis_output_path(project_analysis_dir)
    detections_dir = analysis_output / "detections"

    result = {
        "version": "1.0",
        "source": source,
        "project_id": project_id,
        "calibration": None,
        "parameters_used": parameters_used or {},
        "tracking": {},
        "events": {"manual": manual_events or [], "automatic": []},
        "metrics": {"players": [], "teams": []},
        "clips": [],
        "heatmaps": {},
    }

    # Calibrazione
    cal_path = get_calibration_path(project_analysis_dir)
    if cal_path.exists():
        try:
            with open(cal_path, "r", encoding="utf-8") as f:
                result["calibration"] = json.load(f)
        except Exception:
            pass

    # Tracking
    pt_path = get_tracks_path(project_analysis_dir)
    bt_path = get_ball_tracks_path(project_analysis_dir)
    if pt_path.exists():
        with open(pt_path, "r", encoding="utf-8") as f:
            result["tracking"]["player_tracks"] = json.load(f)
    if bt_path.exists():
        with open(bt_path, "r", encoding="utf-8") as f:
            result["tracking"]["ball_tracks"] = json.load(f)

    # Eventi automatici
    events_path = detections_dir / "events_engine.json"
    if events_path.exists():
        with open(events_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            result["events"]["automatic"] = data.get("automatic", [])

    # Metriche
    metrics_path = analysis_output / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            result["metrics"]["players"] = data.get("players", [])
            result["metrics"]["teams"] = data.get("teams", [])

    return result


def export_json(project_analysis_dir: str, output_path: str, **kwargs) -> bool:
    """Esporta il risultato completo in un unico JSON (schema Step 0.1)."""
    try:
        data = build_full_result(project_analysis_dir, **kwargs)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def export_csv(
    project_analysis_dir: str,
    output_dir_or_file: str,
    include_events: bool = True,
    **kwargs,
) -> bool:
    """
    Esporta tabelle CSV: metriche giocatori, metriche squadre, opzionale eventi.
    Se output_dir_or_file è una cartella, crea players.csv, teams.csv, events.csv.
    Se è un file, usa il path come prefisso (es. report -> report_players.csv, ...).
    """
    try:
        data = build_full_result(project_analysis_dir, **kwargs)
        out = Path(output_dir_or_file)
        if out.suffix.lower() == ".csv":
            base_dir = out.parent
            prefix = out.stem + "_"
        else:
            base_dir = out
            base_dir.mkdir(parents=True, exist_ok=True)
            prefix = ""

        # Metriche giocatori
        players = data.get("metrics", {}).get("players", [])
        if players:
            p_path = base_dir / f"{prefix}players.csv"
            with open(p_path, "w", newline="", encoding="utf-8") as f:
                keys = ["track_id", "team", "distance_m", "passes", "passes_success", "touches"]
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                for row in players:
                    w.writerow({k: row.get(k) for k in keys})

        # Metriche squadre
        teams = data.get("metrics", {}).get("teams", [])
        if teams:
            t_path = base_dir / f"{prefix}teams.csv"
            with open(t_path, "w", newline="", encoding="utf-8") as f:
                keys = ["team_id", "possession_pct", "passes_total"]
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                for row in teams:
                    w.writerow({k: row.get(k) for k in keys})

        # Eventi (automatici)
        if include_events:
            events = data.get("events", {}).get("automatic", [])
            if events:
                e_path = base_dir / f"{prefix}events.csv"
                with open(e_path, "w", newline="", encoding="utf-8") as f:
                    keys = ["type", "timestamp_ms", "team", "track_id", "track_id_to", "zone"]
                    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                    w.writeheader()
                    for row in events:
                        w.writerow({k: row.get(k) for k in keys})

        return True
    except Exception:
        return False


def export_pdf(project_analysis_dir: str, output_path: str, **kwargs) -> bool:
    """
    Genera report PDF tecnico: riepilogo, metriche, eventi, grafici testuali.
    Richiede reportlab: pip install reportlab
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except ImportError:
        raise ImportError("Per l'export PDF installa reportlab: pip install reportlab")

    data = build_full_result(project_analysis_dir, **kwargs)
    teams = data.get("metrics", {}).get("teams", [])
    players = data.get("metrics", {}).get("players", [])
    events = data.get("events", {}).get("automatic", [])

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Report analisi partita", styles["Title"]))
    story.append(Spacer(1, 12))

    # Riepilogo squadre
    story.append(Paragraph("Riepilogo squadre", styles["Heading2"]))
    if teams:
        t_data = [["Squadra", "Possesso %", "Passaggi totali"]]
        for t in teams:
            t_data.append([str(t.get("team_id", "")), str(t.get("possession_pct", "")), str(t.get("passes_total", ""))])
        table = Table(t_data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Nessuna metrica squadra disponibile.", styles["Normal"]))
    story.append(Spacer(1, 16))

    # Metriche giocatori (sintesi)
    story.append(Paragraph("Metriche giocatori (sintesi)", styles["Heading2"]))
    if players:
        p_data = [["track_id", "team", "distanza_m", "passaggi", "tocchi"]]
        for p in players[:30]:  # primi 30
            p_data.append([
                str(p.get("track_id", "")),
                str(p.get("team", "")),
                str(p.get("distance_m", "")),
                str(p.get("passes", "")),
                str(p.get("touches", "")),
            ])
        if len(players) > 30:
            p_data.append(["...", "", "", "", f"(altri {len(players)-30} giocatori)"])
        table = Table(p_data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Nessuna metrica giocatore disponibile.", styles["Normal"]))
    story.append(Spacer(1, 16))

    # Timeline eventi
    story.append(Paragraph("Eventi automatici (timeline)", styles["Heading2"]))
    if events:
        e_data = [["Tipo", "Timestamp (ms)", "Team", "Zona"]]
        for e in events[:50]:
            e_data.append([
                str(e.get("type", "")),
                str(e.get("timestamp_ms", "")),
                str(e.get("team", "")),
                str(e.get("zone", "")),
            ])
        if len(events) > 50:
            e_data.append(["...", "", "", f"(altri {len(events)-50} eventi)"])
        table = Table(e_data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Nessun evento automatico.", styles["Normal"]))

    doc.build(story)
    return True
