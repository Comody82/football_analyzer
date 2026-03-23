"""
Dialog per la calibrazione del campo.
L'utente clicca punti noti sul frame video → sistema calcola homography_matrix.
"""
import cv2
import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRectF
from PyQt5.QtGui import (QPixmap, QImage, QPainter, QPen, QBrush,
                          QColor, QFont)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QWidget, QSplitter,
    QMessageBox, QSizePolicy,
)


# ── Punti standard del campo (x_m, y_m) con campo 105×68 ──────────────────
FIELD_POINTS = [
    {"id": "tl",    "label": "Angolo sup. sinistro",        "x_m": 0.0,   "y_m": 0.0},
    {"id": "tr",    "label": "Angolo sup. destro",          "x_m": 105.0, "y_m": 0.0},
    {"id": "br",    "label": "Angolo inf. destro",          "x_m": 105.0, "y_m": 68.0},
    {"id": "bl",    "label": "Angolo inf. sinistro",        "x_m": 0.0,   "y_m": 68.0},
    {"id": "c",     "label": "Centro campo",                "x_m": 52.5,  "y_m": 34.0},
    {"id": "pen_l", "label": "Dischetto rig. sinistro",     "x_m": 11.0,  "y_m": 34.0},
    {"id": "pen_r", "label": "Dischetto rig. destro",       "x_m": 94.0,  "y_m": 34.0},
    {"id": "ga_tl", "label": "Area grande sx – ang. sup.",  "x_m": 16.5,  "y_m": 13.84},
    {"id": "ga_bl", "label": "Area grande sx – ang. inf.",  "x_m": 16.5,  "y_m": 54.16},
    {"id": "ga_tr", "label": "Area grande dx – ang. sup.",  "x_m": 88.5,  "y_m": 13.84},
    {"id": "ga_br", "label": "Area grande dx – ang. inf.",  "x_m": 88.5,  "y_m": 54.16},
    {"id": "pa_tl", "label": "Area piccola sx – ang. sup.", "x_m": 5.5,   "y_m": 24.84},
    {"id": "pa_bl", "label": "Area piccola sx – ang. inf.", "x_m": 5.5,   "y_m": 43.16},
    {"id": "pa_tr", "label": "Area piccola dx – ang. sup.", "x_m": 99.5,  "y_m": 24.84},
    {"id": "pa_br", "label": "Area piccola dx – ang. inf.", "x_m": 99.5,  "y_m": 43.16},
]

FIELD_W, FIELD_H = 105.0, 68.0


# ── Widget video cliccabile ────────────────────────────────────────────────
class ClickableFrameWidget(QLabel):
    point_clicked = pyqtSignal(float, float)   # x_norm, y_norm [0-1]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #0a1220; border-radius: 6px;")
        self.setCursor(Qt.CrossCursor)
        self._placed = []        # [(x_norm, y_norm, number)]
        self._base_pixmap = None

    def set_frame(self, pixmap):
        self._base_pixmap = pixmap
        self._redraw()

    def add_point(self, x_norm, y_norm, number):
        self._placed.append((x_norm, y_norm, number))
        self._redraw()

    def remove_last_point(self):
        if self._placed:
            self._placed.pop()
            self._redraw()

    def clear_points(self):
        self._placed.clear()
        self._redraw()

    def _redraw(self):
        if self._base_pixmap is None:
            return
        canvas = self._base_pixmap.copy()
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = canvas.width(), canvas.height()
        for x_n, y_n, num in self._placed:
            px, py = int(x_n * w), int(y_n * h)
            painter.setPen(QPen(Qt.white, 2))
            painter.setBrush(QBrush(QColor("#22c55e")))
            painter.drawEllipse(QPoint(px, py), 10, 10)
            painter.setPen(QPen(Qt.white))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(px - 4, py + 4, str(num))
        painter.end()
        self.setPixmap(canvas.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._base_pixmap is None:
            return
        pw = self._base_pixmap.width()
        ph = self._base_pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph)
        disp_w = pw * scale
        disp_h = ph * scale
        off_x = (ww - disp_w) / 2
        off_y = (wh - disp_h) / 2
        lx = event.x() - off_x
        ly = event.y() - off_y
        if lx < 0 or ly < 0 or lx > disp_w or ly > disp_h:
            return
        self.point_clicked.emit(lx / disp_w, ly / disp_h)


# ── Widget diagramma campo 2D ──────────────────────────────────────────────
class FieldDiagramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._active_idx = None
        self._placed_indices = set()

    def set_active(self, idx):
        self._active_idx = idx
        self.update()

    def mark_placed(self, idx):
        self._placed_indices.add(idx)
        self.update()

    def unmark_last(self, idx):
        self._placed_indices.discard(idx)
        self.update()

    def reset(self):
        self._active_idx = None
        self._placed_indices.clear()
        self.update()

    def _field_rect(self):
        m = 18
        w, h = self.width(), self.height()
        scale = min((w - 2*m) / FIELD_W, (h - 2*m) / FIELD_H)
        fw, fh = FIELD_W * scale, FIELD_H * scale
        return (w - fw) / 2, (h - fh) / 2, fw, fh

    def _pt_px(self, x_m, y_m):
        x0, y0, fw, fh = self._field_rect()
        return x0 + x_m / FIELD_W * fw, y0 + y_m / FIELD_H * fh

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x0, y0, fw, fh = self._field_rect()

        p.fillRect(self.rect(), QColor("#0d1b2e"))
        p.setBrush(QBrush(QColor("#16532d")))
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.drawRect(int(x0), int(y0), int(fw), int(fh))

        # Linea centrocampo
        cx = x0 + fw / 2
        p.drawLine(int(cx), int(y0), int(cx), int(y0 + fh))
        # Cerchio
        rc = fw / FIELD_W * 9.15
        cy = y0 + fh / 2
        p.drawEllipse(QRectF(cx - rc, cy - rc, rc * 2, rc * 2))
        # Aree grandi
        gaw = fw / FIELD_W * 16.5
        gah = fh / FIELD_H * 40.32
        p.drawRect(int(x0), int(cy - gah/2), int(gaw), int(gah))
        p.drawRect(int(x0 + fw - gaw), int(cy - gah/2), int(gaw), int(gah))
        # Aree piccole
        paw = fw / FIELD_W * 5.5
        pah = fh / FIELD_H * 18.32
        p.drawRect(int(x0), int(cy - pah/2), int(paw), int(pah))
        p.drawRect(int(x0 + fw - paw), int(cy - pah/2), int(paw), int(pah))

        # Punti
        p.setFont(QFont("Arial", 7, QFont.Bold))
        for i, pt in enumerate(FIELD_POINTS):
            px, py = self._pt_px(pt['x_m'], pt['y_m'])
            if i in self._placed_indices:
                color = QColor("#22c55e")
            elif i == self._active_idx:
                color = QColor("#facc15")
            else:
                color = QColor("#64748b")
            r = 9 if i >= 9 else 6   # 2 cifre (10-15) → cerchio più grande
            ox = -5 if i >= 9 else -3  # offset testo centrato
            p.setPen(QPen(Qt.white, 1))
            p.setBrush(QBrush(color))
            p.drawEllipse(QPoint(int(px), int(py)), r, r)
            p.setPen(QPen(QColor("#ffffff")))
            p.drawText(int(px) + ox, int(py) + 4, str(i + 1))
        p.end()


# ── Dialog principale ──────────────────────────────────────────────────────
class FieldCalibrationDialog(QDialog):
    calibration_saved = pyqtSignal(str)    # cal_id → registry (camera fissa)
    calibration_applied = pyqtSignal(list) # H.tolist() diretto (camera mobile/VEO)

    def __init__(self, video_path, video_pos_ms, registry, parent=None):
        super().__init__(parent)
        self._video_path = video_path
        self._video_pos_ms = video_pos_ms
        self._registry = registry
        self._placed = []            # [{point_idx, x_norm, y_norm}]
        self._active_point_idx = None

        self.setWindowTitle("Calibrazione Campo")
        self.setMinimumSize(1050, 640)
        self.setStyleSheet("""
            QDialog { background: #0d1b2e; color: #e8f0fa; }
            QLabel { color: #c8d8ec; font-size: 12px; }
            QLabel#title { font-size: 18px; font-weight: 700; color: #f1f6ff; }
            QLabel#sub   { font-size: 11px; color: #6a8aaa; }
            QPushButton {
                background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px; color: #e8f4ff; font-size: 12px; font-weight: 600;
                padding: 6px 14px; min-height: 28px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.13); }
            QPushButton#btnApply {
                background: #17806a; border: none; color: #eafff8; font-weight: 700;
            }
            QPushButton#btnApply:hover { background: #1e947c; }
            QPushButton#btnApply:disabled { background: rgba(23,128,106,0.3); color: #5a8a7a; }
            QPushButton#btnSaveApply {
                background: rgba(59,130,246,0.18); border: 1px solid #3b82f6;
                color: #93c5fd; font-weight: 600;
            }
            QPushButton#btnSaveApply:hover { background: rgba(59,130,246,0.28); }
            QPushButton#btnSaveApply:disabled { background: rgba(59,130,246,0.06); color: #4a6a8a; border-color: #2a4a6a; }
            QPushButton#btnUndo { background: rgba(239,68,68,0.12); border-color: #ef4444; color: #fca5a5; }
            QListWidget {
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px; color: #c8d8ec; font-size: 11px;
            }
            QListWidget::item:selected { background: rgba(34,197,94,0.25); color: #86efac; }
            QLineEdit {
                background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px; color: #e8f4ff; padding: 5px 10px; font-size: 12px;
            }
            QFrame#saveSeparator { background: rgba(255,255,255,0.08); }
        """)
        self._build_ui()
        self._load_frame()
        self._refresh_point_list()

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel("Calibrazione Campo")
        title.setObjectName("title")
        sub = QLabel("Seleziona un punto dalla lista → clicca la posizione corrispondente sul frame video.")
        sub.setObjectName("sub")
        hdr.addWidget(title)
        hdr.addSpacing(12)
        hdr.addWidget(sub, 1)
        root.addLayout(hdr)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        # Sinistra: frame video cliccabile
        self._frame_widget = ClickableFrameWidget()
        self._frame_widget.point_clicked.connect(self._on_video_click)
        splitter.addWidget(self._frame_widget)

        # Destra: controlli
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 0, 0, 0)
        rv.setSpacing(8)

        rv.addWidget(QLabel("Mappa campo (giallo = attivo, verde = piazzato):"))
        self._diagram = FieldDiagramWidget()
        self._diagram.setFixedHeight(185)
        rv.addWidget(self._diagram)

        rv.addWidget(QLabel("Punti calibrazione (clicca per selezionare):"))
        self._list_points = QListWidget()
        self._list_points.setMaximumHeight(200)
        self._list_points.currentRowChanged.connect(self._on_point_selected)
        rv.addWidget(self._list_points)

        self._lbl_status = QLabel("Seleziona almeno 4 punti non collineari.")
        self._lbl_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        self._lbl_status.setWordWrap(True)
        rv.addWidget(self._lbl_status)

        self._btn_undo = QPushButton("↩  Annulla ultimo punto")
        self._btn_undo.setObjectName("btnUndo")
        self._btn_undo.clicked.connect(self._undo_last)
        self._btn_undo.setEnabled(False)
        rv.addWidget(self._btn_undo)

        rv.addStretch()

        # ── Azione primaria: Applica senza salvare (camera mobile/VEO) ──
        btn_row_main = QHBoxLayout()
        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        self._btn_apply = QPushButton("Applica senza salvare")
        self._btn_apply.setObjectName("btnApply")
        self._btn_apply.setEnabled(False)
        self._btn_apply.setToolTip("Applica solo a questo progetto (camera mobile/VEO)")
        self._btn_apply.clicked.connect(self._apply_without_saving)
        btn_row_main.addWidget(btn_cancel)
        btn_row_main.addStretch()
        btn_row_main.addWidget(self._btn_apply)
        rv.addLayout(btn_row_main)

        # ── Separatore + sezione salvataggio (camera fissa) ──────────────
        from PyQt5.QtWidgets import QFrame
        sep = QFrame()
        sep.setObjectName("saveSeparator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        rv.addWidget(sep)

        lbl_save_hint = QLabel("Camera fissa? Salva per riutilizzarla su altri progetti:")
        lbl_save_hint.setStyleSheet("color: #4a6a8a; font-size: 10px;")
        rv.addWidget(lbl_save_hint)

        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("Nome calibrazione (es. Campo Centrale – Camera Nord)")
        rv.addWidget(self._edit_name)

        self._btn_save_apply = QPushButton("💾  Salva e applica")
        self._btn_save_apply.setObjectName("btnSaveApply")
        self._btn_save_apply.setEnabled(False)
        self._btn_save_apply.setToolTip("Salva nel registry e applica (camera fissa, stessa postazione)")
        self._btn_save_apply.clicked.connect(self._save_and_apply)
        rv.addWidget(self._btn_save_apply)

        splitter.addWidget(right)
        splitter.setSizes([630, 380])
        root.addWidget(splitter, 1)

    # ── Carica frame ───────────────────────────────────────────────────────
    def _load_frame(self):
        try:
            cap = cv2.VideoCapture(self._video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_idx = int(self._video_pos_ms / 1000.0 * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                cap2 = cv2.VideoCapture(self._video_path)
                ret, frame = cap2.read()
                cap2.release()
            if ret:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self._frame_widget.set_frame(QPixmap.fromImage(img))
            else:
                self._frame_widget.setText("Impossibile caricare il frame video.")
        except Exception as e:
            self._frame_widget.setText(f"Errore caricamento frame: {e}")

    # ── Lista punti ────────────────────────────────────────────────────────
    def _refresh_point_list(self):
        placed_ids = {p['point_idx'] for p in self._placed}
        self._list_points.blockSignals(True)
        self._list_points.clear()
        for i, pt in enumerate(FIELD_POINTS):
            done = i in placed_ids
            prefix = "✅" if done else f"{i+1:2d}."
            label = f"{prefix}  {pt['label']}  ({pt['x_m']:.1f}, {pt['y_m']:.1f} m)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, i)
            if done:
                item.setForeground(QColor("#22c55e"))
            self._list_points.addItem(item)
        self._list_points.blockSignals(False)

    # ── Selezione punto ────────────────────────────────────────────────────
    def _on_point_selected(self, row):
        if row < 0:
            return
        item = self._list_points.item(row)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        placed_ids = {p['point_idx'] for p in self._placed}
        if idx in placed_ids:
            self._active_point_idx = None
            self._diagram.set_active(None)
            self._lbl_status.setText("Punto già piazzato. Scegline un altro.")
            self._lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
            return
        self._active_point_idx = idx
        self._diagram.set_active(idx)
        pt = FIELD_POINTS[idx]
        n = len(self._placed)
        progress = f"  [{n} piazzati]" if n > 0 else ""
        self._lbl_status.setText(
            f"→ Clicca sul video dove vedi: {pt['label']}  ({pt['x_m']:.1f}, {pt['y_m']:.1f} m){progress}")
        self._lbl_status.setStyleSheet("color: #facc15; font-size: 11px;")

    # ── Auto-selezione prossimo punto disponibile ───────────────────────────
    def _auto_select_next(self, after_idx: int):
        """Seleziona automaticamente il prossimo punto non piazzato dopo after_idx."""
        placed_ids = {p['point_idx'] for p in self._placed}
        total = len(FIELD_POINTS)
        # cerca in ordine circolare partendo da after_idx+1
        for offset in range(1, total + 1):
            candidate = (after_idx + offset) % total
            if candidate not in placed_ids:
                self._list_points.setCurrentRow(candidate)
                return

    # ── Click sul video ────────────────────────────────────────────────────
    def _on_video_click(self, x_norm, y_norm):
        if self._active_point_idx is None:
            self._lbl_status.setText("Seleziona prima un punto dalla lista.")
            self._lbl_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
            return
        idx = self._active_point_idx
        number = len(self._placed) + 1
        self._placed.append({'point_idx': idx, 'x_norm': x_norm, 'y_norm': y_norm})
        self._frame_widget.add_point(x_norm, y_norm, number)
        self._diagram.mark_placed(idx)
        self._active_point_idx = None
        self._diagram.set_active(None)
        self._refresh_point_list()
        self._btn_undo.setEnabled(True)
        n = len(self._placed)
        if n >= 4:
            self._btn_apply.setEnabled(True)
            self._btn_save_apply.setEnabled(True)
        if n < len(FIELD_POINTS):
            # Auto-seleziona il prossimo punto non piazzato
            self._auto_select_next(idx)
        elif n >= 4:
            self._lbl_status.setText(f"Tutti i {n} punti piazzati. Puoi applicare.")
            self._lbl_status.setStyleSheet("color: #22c55e; font-size: 11px;")

    # ── Undo ───────────────────────────────────────────────────────────────
    def _undo_last(self):
        if not self._placed:
            return
        last = self._placed.pop()
        self._frame_widget.remove_last_point()
        self._diagram.unmark_last(last['point_idx'])
        self._refresh_point_list()
        n = len(self._placed)
        self._btn_undo.setEnabled(bool(self._placed))
        self._btn_apply.setEnabled(n >= 4)
        self._btn_save_apply.setEnabled(n >= 4)
        self._lbl_status.setText(
            f"{n} punti piazzati." if n else "Seleziona almeno 4 punti.")
        self._lbl_status.setStyleSheet(
            "color: #22c55e;" if n >= 4 else "color: #f59e0b; font-size: 11px;")

    # ── Helper: calcola homography ──────────────────────────────────────────
    def _compute_homography(self):
        """Ritorna (H, inliers) oppure (None, 0)."""
        src = np.array([[p['x_norm'], p['y_norm']] for p in self._placed],
                       dtype=np.float32)
        dst = np.array(
            [[FIELD_POINTS[p['point_idx']]['x_m'],
              FIELD_POINTS[p['point_idx']]['y_m']] for p in self._placed],
            dtype=np.float32)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            return None, 0
        return H, int(mask.sum()) if mask is not None else len(src)

    # ── Applica senza salvare (camera mobile/VEO) ──────────────────────────
    def _apply_without_saving(self):
        if len(self._placed) < 4:
            return
        H, inliers = self._compute_homography()
        if H is None:
            QMessageBox.critical(self, "Errore calibrazione",
                                 "Impossibile calcolare la homography.\n"
                                 "Assicurati che i punti non siano collineari.")
            return
        if inliers < 4:
            QMessageBox.warning(self, "Calibrazione imprecisa",
                                f"Solo {inliers}/{len(self._placed)} punti accettati da RANSAC.\n"
                                "Riposiziona i punti con più precisione.")
            return
        self.calibration_applied.emit(H.tolist())
        self.accept()

    # ── Salva nel registry e applica (camera fissa) ────────────────────────
    def _save_and_apply(self):
        name = self._edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Nome mancante",
                                "Inserisci un nome per salvare la calibrazione nel registry.")
            self._edit_name.setFocus()
            return
        if len(self._placed) < 4:
            return
        H, inliers = self._compute_homography()
        if H is None:
            QMessageBox.critical(self, "Errore calibrazione",
                                 "Impossibile calcolare la homography.\n"
                                 "Assicurati che i punti non siano collineari.")
            return
        if inliers < 4:
            QMessageBox.warning(self, "Calibrazione imprecisa",
                                f"Solo {inliers}/{len(self._placed)} punti accettati da RANSAC.\n"
                                "Riposiziona i punti con più precisione.")
            return
        cal_id = self._registry.save(
            name=name,
            matrix=H.tolist(),
            src_points=[[p['x_norm'], p['y_norm']] for p in self._placed],
            dst_points=[[FIELD_POINTS[p['point_idx']]['x_m'],
                         FIELD_POINTS[p['point_idx']]['y_m']] for p in self._placed],
        )
        self.calibration_saved.emit(cal_id)
        QMessageBox.information(
            self, "Calibrazione salvata",
            f'Calibrazione "{name}" salvata nel registry.\n{inliers}/{len(self._placed)} punti accettati.')
        self.accept()
