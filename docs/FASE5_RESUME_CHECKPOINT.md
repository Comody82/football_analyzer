# Fase 5: Ripresa da checkpoint

> 2025-02-25

---

## Modifiche

- **analysis_engine.py:** flag `--resume` per riprendere dall’ultimo checkpoint
- **analysis/player_detection.py:** parametri `start_frame`, `initial_results` per ripresa
- **analysis/ball_detection.py:** parametri `start_frame`, `initial_results` per ripresa
- **ui/analysis_process_dialog.py:** parametro `resume`, funzione `has_checkpoint()`
- **main_web.py:** prompt "Analisi interrotta. Riprendere da dove era rimasta?" se esiste checkpoint

---

## Comportamento

1. L’utente avvia Player detection / Ball detection
2. Se esiste un checkpoint (es. analisi interrotta precedentemente):
   - Mostra dialog: "Analisi interrotta. Riprendere da dove era rimasta?"
   - **Riprendi** → avvia con `--resume` (continua dal frame successivo all’ultimo checkpoint)
   - **Ricomincia da capo** → avvia senza `--resume` (sovrascrive)
   - **Annulla** → nessuna azione
3. Se non esiste checkpoint: avvio normale (nessun prompt)

---

## Dettagli tecnici

- Checkpoint: `*_checkpoint_{frame_idx}.json` (es. `player_detections_checkpoint_4000.json`)
- `_find_latest_checkpoint()` cerca il file con frame index più alto
- Ripresa: seek video a `start_frame`, carica risultati parziali, continua il loop
- **Checkpoint adattivo:** primo a 500 frame (~20 sec), poi ogni 1000 frame (~40 sec)
- `--checkpoint-first 500` e `--checkpoint-interval 1000` (default)

---

## Uso CLI

```bash
# Riprendi analisi interrotta
python analysis_engine.py --video video.mp4 --output ./out --mode player --resume
```
