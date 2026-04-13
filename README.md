# A2L Filter Tool

Ett Python-verktyg för att filtrera A2L-filer baserat på en lista med signaler i CSV-format.

## Vad verktyget gör

- behåller endast valda `MEASUREMENT`
- kan ta bort `GROUP`, `FUNCTION`, `CHARACTERISTIC` och `AXIS_PTS`
- behåller endast använda `COMPU_METHOD` och `COMPU_VTAB`
- kan verifiera att `MEASUREMENT`, `COMPU_METHOD` och `COMPU_VTAB` är identiska med originalet
- har både CLI och GUI
- GUI har både enkel körning och batchläge

## Krav

- Python 3.10+
- inga externa paket behövs

## CLI

Grundkommando:

```bash
python build_filtered_a2l.py input.a2l signals.csv output_filtered.a2l \
  --ignore-case \
  --drop-structure \
  --drop-characteristics \
  --drop-axis-pts \
  --prune-support \
  --missing-report missing.txt \
  --verify
```

## GUI

Starta GUI:

```bash
python a2l_filter_gui.py
```

På Windows kan du också dubbelklicka på:

```text
Start_A2L_Filter_GUI.bat
```

## Enkel körning i GUI

1. välj input A2L
2. välj input CSV
3. välj output A2L
4. klicka på `Kör jobb`

## Batchläge i GUI

Batchläget används när du vill köra flera jobb i samma fönster.

1. öppna fliken `Batchläge`
2. klicka på `Lägg till jobb`
3. välj A2L, CSV och output-fil för varje jobb
4. klicka på `Kör alla jobb`

Du kan också:

- lägga till nuvarande enkel-körning i batch med `Lägg till i batch`
- redigera markerat jobb
- ta bort markerat jobb
- rensa hela batchlistan
- auto-generera output-namn med `Föreslå outputs`

## Rekommenderade inställningar för CCP / IPEmotion

- `Ignore case`
- `Drop GROUP/FUNCTION`
- `Drop CHARACTERISTIC`
- `Drop AXIS_PTS`
- `Prune COMPU_METHOD / COMPU_VTAB`
- `Verify output`
- `Create missing report next to output`

## Verify

När `verify` är aktivt kontrolleras att det som påverkar mätdata inte har ändrats:

- `MEASUREMENT`
- `COMPU_METHOD`
- `COMPU_VTAB`

Om verify misslyckas ska output-filen inte användas.
