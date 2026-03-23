# Football Analyzer – Guida all’analisi automatica

Questa guida spiega come usare Player detection, Ball detection e la gestione delle analisi lunghe.

---

## Tempi attesi

| Video | CPU tipica | Con GPU |
|-------|------------|---------|
| Partita 90 min | ~1.5–2 ore | ~30–45 min |
| 10 minuti | ~8–12 min | ~3–5 min |

L’analisi usa ~10 FPS (non tutti i frame) per velocizzare senza perdere qualità.

---

## Uso della CPU

- L’analisi gira a **priorità bassa** → il PC resta utilizzabile
- CPU al 100% è normale durante l’analisi
- Puoi navigare nell’app, aprire altri progetti, usare il browser

---

## Durante l’analisi

### Continuare a lavorare

- Il dialog di analisi **non blocca** l’app
- Puoi spostarti tra schermate, aprire altri progetti, ecc.
- Il video resta in pausa per evitare rallentamenti

### Chiudere l’app

Se chiudi l’app mentre l’analisi è in corso:

- **Ferma** – interrompe l’analisi e chiude (i progressi sono salvati nei checkpoint)
- **Continua** – chiude l’app ma l’analisi continua in background; al riavvio riceverai notifica al termine
- **Annulla** – annulla la chiusura

---

## Interruzione e ripresa

### Interrompere

- Clic **Interrompi** nel dialog di analisi
- I progressi sono salvati automaticamente ogni ~40 secondi

### Riprendere

Alla successiva analisi dello stesso progetto:

- Apparirà: **"Riprendere dall’ultimo punto salvato?"**
- **Riprendi** – continua da dove era rimasta (perdi al massimo ~40 sec)
- **Ricomincia da capo** – riparte dall’inizio
- **Annulla** – non fare nulla

---

## Requisiti di sistema

- **RAM:** 8 GB minimo, 16 GB consigliato
- **Spazio disco:** ~500 MB per modelli + output
- **Windows 10/11**

---

## Note tecniche

- **Checkpoint:** primo a ~20 secondi, poi ogni ~40 secondi
- **Output:** file JSON in `data/analysis/<project_id>/analysis_output/`
- Se l’eseguibile del motore non è disponibile, l’app usa lo script Python (richiede Python 3.10 installato)
