"""
Football Analyzer - Software per l'analisi video delle partite di calcio.

Funzionalità:
- Tagging eventi (Gol, Tiri, Calci d'angolo, custom)
- Disegno su video (cerchi, frecce, testo, coni, zoom)
- Creazione clip e assemblaggio highlights
- Statistiche partita
"""
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from ui.theme import apply_palette
from ui.main_window import MainWindow

# High DPI scaling - deve essere impostato PRIMA di creare QApplication
if hasattr(Qt, 'AA_UseHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_UseHighDpiScaling, True)
elif hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Football Analyzer")
    apply_palette(app)

    win = MainWindow()

    # Menu File
    menu = win.menuBar().addMenu("File")
    menu.addAction("📂 Apri Video", win.open_file)
    menu.addAction("Esci", app.quit)

    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
