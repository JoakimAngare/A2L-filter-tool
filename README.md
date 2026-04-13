# A2L Filter Tool

A Python tool for filtering A2L files based on a list of signals in CSV format.

## What the tool does

* keeps only selected `MEASUREMENT`
* can remove `GROUP`, `FUNCTION`, `CHARACTERISTIC`, and `AXIS_PTS`
* keeps only used `COMPU_METHOD` and `COMPU_VTAB`
* can verify that `MEASUREMENT`, `COMPU_METHOD`, and `COMPU_VTAB` are identical to the original
* includes both CLI and GUI
* GUI supports both single run and batch mode

## Requirements

* Python 3.10+
* no external packages required

## CLI

Basic command:

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

Start the GUI:

```bash
python a2l_filter_gui.py
```

On Windows, you can also double-click:

```text
Start_A2L_Filter_GUI.bat
```

## Single run in GUI

1. select input A2L
2. select input CSV
3. select output A2L
4. click `Run job`

## Batch mode in GUI

Batch mode is used when you want to run multiple jobs in the same window.

1. open the `Batch mode` tab
2. click `Add job`
3. select A2L, CSV, and output file for each job
4. click `Run all jobs`

You can also:

* add the current single run to batch with `Add to batch`
* edit selected job
* remove selected job
* clear the entire batch list
* auto-generate output names with `Suggest outputs`

## Recommended settings for CCP / IPEmotion

* `Ignore case`
* `Drop GROUP/FUNCTION`
* `Drop CHARACTERISTIC`
* `Drop AXIS_PTS`
* `Prune COMPU_METHOD / COMPU_VTAB`
* `Verify output`
* `Create missing report next to output`

## Verify

When `verify` is enabled, it checks that elements affecting measurement data have not changed:

* `MEASUREMENT`
* `COMPU_METHOD`
* `COMPU_VTAB`

If verification fails, the output file should not be used.

