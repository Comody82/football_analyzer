# Fase 6: Distribuzione e test

> 2025-02-25

---

## 6.1 Includere analysis_engine.exe nel pacchetto

### Struttura attuale

- **Build:** `pyinstaller build_engine.spec --noconfirm`
- **Output:** `dist/analysis_engine/` (cartella con exe + DLL + moduli)
- **Uso da main_web:** cerca `project_root/dist/analysis_engine/analysis_engine.exe`; se manca, usa `python analysis_engine.py`

### Per distribuzione

1. **Build dell'engine:**
   ```bash
   cd c:\football_analyzer
   pyinstaller build_engine.spec --noconfirm
   ```

2. **Copiare la cartella completa** `dist/analysis_engine/` nel pacchetto/installer.

3. **Layout consigliato per utente finale:**
   ```
   FootballAnalyzer/
   ├── main_web.py           # oppure .exe se anche la UI è packaged
   ├── analysis_engine.py    # fallback se exe non disponibile
   ├── dist/
   │   └── analysis_engine/
   │       ├── analysis_engine.exe
   │       ├── (DLL, _internal/, ecc.)
   │       └── models/       # yolox_s.pth (opzionale, scaricato al primo avvio)
   └── ...
   ```

4. **Nota:** Se l'exe YOLOX dà problemi (vedi FASE4), l’app usa automaticamente `python analysis_engine.py` come fallback.

---

## 6.2 Test su diversi PC

### Checklist

| Ambiente | Azione | Esito |
|----------|--------|-------|
| PC con GPU (CUDA) | Avviare analisi, verificare velocità | |
| PC senza GPU (solo CPU) | Avviare analisi, verificare tempi | |
| PC senza Python | Se distribuito con exe UI + exe engine | |
| PC con solo Python (no exe) | Verificare fallback a `python analysis_engine.py` | |
| Prima esecuzione | Scaricamento yolox_s.pth in models/ | |

### Comandi test rapido

```bash
# Test engine da solo
cd dist\analysis_engine
.\analysis_engine.exe --video path\to\video.mp4 --output path\to\output --mode player --no-priority

# Test via UI
python main_web.py
# Apri progetto → Player detection / Ball detection
```

---

## 6.3 Test con video lunghi (90 min)

| Cosa verificare | Come |
|-----------------|------|
| **Checkpoint** | Interrompere a ~20–30%, riavviare, verificare "Riprendere dall'ultimo punto salvato?" |
| **Memoria** | Monitorare RAM durante analisi (Task Manager) |
| **Stabilità** | Lasciare completare analisi full (90 min) senza crash |
| **Uso disco** | Verificare spazio per checkpoint e output JSON |
| **CPU** | Priorità bassa attiva → PC utilizzabile durante analisi |

### Tempi indicativi (25 fps, 10 target fps)

- **90 min** ≈ 135.000 frame → ~13.500 frame da analizzare
- **Player detection:** ~0.2 s/frame → ~45 min
- **Ball detection:** simile
- **Full:** ~1.5–2 h (CPU), meno con GPU

---

## 6.4 Documentazione per l'utente

### Contenuti da includere (manuale / README utente)

1. **Tempi attesi**
   - Partita 90 min, 25 fps: analisi completa ~1.5–2 h su CPU
   - Con GPU: 2–4× più veloce

2. **Uso CPU**
   - L’analisi gira a priorità bassa → puoi usare il PC per altre attività
   - CPU al 100% è normale; il PC resta utilizzabile

3. **Continuare a lavorare**
   - Il dialog di analisi non è modale: puoi navigare, aprire altri progetti, ecc.
   - Puoi chiudere l’app: scegli **Continua** per lasciare l’analisi in background e ricevere notifica al termine

4. **Interruzione e ripresa**
   - **Interrompi** → salvataggio checkpoint (~ ogni 40 sec)
   - Alla prossima analisi: "Riprendere dall'ultimo punto salvato?" → **Riprendi**

5. **Requisiti**
   - Windows 10/11
   - RAM: 8 GB minimo, 16 GB consigliato
   - Spazio disco: ~500 MB per modelli + output
   - Python 3.10 (se si usa lo script, non l’exe)
