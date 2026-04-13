#!/usr/bin/env python3
from __future__ import annotations

import traceback
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from build_filtered_a2l import build_summary, run_filter_job


@dataclass
class BatchJob:
    job_id: str
    input_a2l: Path
    input_csv: Path
    output_a2l: Path


class BatchJobDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        input_a2l: str = "",
        input_csv: str = "",
        output_a2l: str = "",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(True, False)
        self.transient(parent)
        self.grab_set()

        self.input_a2l_var = tk.StringVar(value=input_a2l)
        self.input_csv_var = tk.StringVar(value=input_csv)
        self.output_a2l_var = tk.StringVar(value=output_a2l)
        self.result: tuple[Path, Path, Path] | None = None

        self.columnconfigure(0, weight=1)

        frame = ttk.Frame(self, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="A2L input").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.input_a2l_var).grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.choose_input_a2l).grid(row=0, column=2, pady=(0, 8))

        ttk.Label(frame, text="CSV input").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.input_csv_var).grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.choose_input_csv).grid(row=1, column=2, pady=(0, 8))

        ttk.Label(frame, text="Output A2L").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.output_a2l_var).grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Save as...", command=self.choose_output_a2l).grid(row=2, column=2, pady=(0, 8))

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        button_row.columnconfigure(0, weight=1)

        ttk.Button(button_row, text="Föreslå output", command=self.suggest_output_name).grid(row=0, column=0, sticky="w")
        ttk.Button(button_row, text="Avbryt", command=self.on_cancel).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(button_row, text="OK", command=self.on_ok).grid(row=0, column=2, padx=(8, 0))

        self.bind("<Return>", lambda _event: self.on_ok())
        self.bind("<Escape>", lambda _event: self.on_cancel())
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        self.after(10, self._focus_first)

    def _focus_first(self) -> None:
        self.focus_force()

    def choose_input_a2l(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Välj A2L-fil",
            initialdir=str(Path(self.input_a2l_var.get()).parent) if self.input_a2l_var.get() else str(Path.cwd()),
            filetypes=[("A2L files", "*.a2l"), ("All files", "*.*")],
        )
        if filename:
            self.input_a2l_var.set(filename)
            if not self.output_a2l_var.get().strip():
                self.suggest_output_name()

    def choose_input_csv(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Välj CSV-fil",
            initialdir=str(Path(self.input_csv_var.get()).parent) if self.input_csv_var.get() else str(Path.cwd()),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            self.input_csv_var.set(filename)
            if not self.output_a2l_var.get().strip():
                self.suggest_output_name()

    def choose_output_a2l(self) -> None:
        suggestion = self._build_suggested_output_path()
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Spara filtrerad A2L som",
            defaultextension=".a2l",
            initialdir=str(suggestion.parent),
            initialfile=suggestion.name,
            filetypes=[("A2L files", "*.a2l"), ("All files", "*.*")],
        )
        if filename:
            self.output_a2l_var.set(filename)

    def suggest_output_name(self) -> None:
        self.output_a2l_var.set(str(self._build_suggested_output_path()))

    def _build_suggested_output_path(self) -> Path:
        a2l = Path(self.input_a2l_var.get()) if self.input_a2l_var.get().strip() else Path.cwd() / "input.a2l"
        csv_file = Path(self.input_csv_var.get()) if self.input_csv_var.get().strip() else Path("signals.csv")
        csv_stem = csv_file.stem if csv_file.suffix else "signals"
        safe_csv_stem = csv_stem.replace(" ", "_")
        return a2l.with_name(f"{a2l.stem}_{safe_csv_stem}_filtered.a2l")

    def on_ok(self) -> None:
        input_a2l = self.input_a2l_var.get().strip()
        input_csv = self.input_csv_var.get().strip()
        output_a2l = self.output_a2l_var.get().strip()
        if not input_a2l or not input_csv or not output_a2l:
            messagebox.showerror("Saknar filer", "Välj A2L, CSV och output-fil först.", parent=self)
            return
        self.result = (Path(input_a2l), Path(input_csv), Path(output_a2l))
        self.destroy()

    def on_cancel(self) -> None:
        self.result = None
        self.destroy()


class A2LFilterGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("A2L Filter")
        self.geometry("1100x760")
        self.minsize(900, 640)

        self.input_a2l_var = tk.StringVar()
        self.input_csv_var = tk.StringVar()
        self.output_a2l_var = tk.StringVar()
        self.csv_column_var = tk.StringVar()

        self.ignore_case_var = tk.BooleanVar(value=True)
        self.drop_structure_var = tk.BooleanVar(value=True)
        self.drop_characteristics_var = tk.BooleanVar(value=True)
        self.drop_axis_pts_var = tk.BooleanVar(value=True)
        self.prune_support_var = tk.BooleanVar(value=True)
        self.verify_var = tk.BooleanVar(value=True)
        self.create_missing_report_var = tk.BooleanVar(value=True)

        self.single_run_button: ttk.Button | None = None
        self.batch_run_button: ttk.Button | None = None
        self.batch_edit_button: ttk.Button | None = None
        self.batch_remove_button: ttk.Button | None = None
        self.batch_clear_button: ttk.Button | None = None
        self.batch_add_button: ttk.Button | None = None
        self.batch_add_current_button: ttk.Button | None = None
        self.batch_suggest_button: ttk.Button | None = None

        self.batch_jobs: dict[str, BatchJob] = {}
        self._job_counter = 0

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 8))

        self.single_tab = ttk.Frame(self.notebook, padding=14)
        self.single_tab.columnconfigure(1, weight=1)
        self.notebook.add(self.single_tab, text="Enkel körning")
        self._build_single_tab()

        self.batch_tab = ttk.Frame(self.notebook, padding=14)
        self.batch_tab.columnconfigure(0, weight=1)
        self.batch_tab.rowconfigure(1, weight=1)
        self.notebook.add(self.batch_tab, text="Batchläge")
        self._build_batch_tab()

        options = ttk.LabelFrame(self, text="Gemensamma inställningar", padding=14)
        options.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        for col in range(3):
            options.columnconfigure(col, weight=1)

        ttk.Checkbutton(options, text="Ignore case", variable=self.ignore_case_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="Drop GROUP/FUNCTION", variable=self.drop_structure_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(options, text="Drop CHARACTERISTIC", variable=self.drop_characteristics_var).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(options, text="Drop AXIS_PTS", variable=self.drop_axis_pts_var).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Prune COMPU_METHOD / COMPU_VTAB", variable=self.prune_support_var).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Verify output", variable=self.verify_var).grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Create missing report next to output", variable=self.create_missing_report_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(options, text="CSV column (optional)").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(options, textvariable=self.csv_column_var).grid(row=3, column=2, sticky="ew", pady=(4, 0))

        log_frame = ttk.LabelFrame(self, text="Resultat", padding=10)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_widget = ScrolledText(log_frame, wrap=tk.WORD, height=14)
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        self.log_widget.configure(state="disabled")

        self._append_log("Klar. Välj enkel körning eller bygg en batchlista.\n")

    def _build_single_tab(self) -> None:
        ttk.Label(self.single_tab, text="A2L input").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(self.single_tab, textvariable=self.input_a2l_var).grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(self.single_tab, text="Browse...", command=self.choose_input_a2l).grid(row=0, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(self.single_tab, text="CSV input").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(self.single_tab, textvariable=self.input_csv_var).grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(self.single_tab, text="Browse...", command=self.choose_input_csv).grid(row=1, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(self.single_tab, text="Output A2L").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(self.single_tab, textvariable=self.output_a2l_var).grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(self.single_tab, text="Save as...", command=self.choose_output_a2l).grid(row=2, column=2, sticky="ew", pady=(0, 8))

        hint = ttk.Label(
            self.single_tab,
            text="Tips: använd 'Lägg till i batch' när du vill köra flera jobb i samma fönster.",
        )
        hint.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))

        bottom = ttk.Frame(self.single_tab)
        bottom.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        bottom.columnconfigure(0, weight=1)

        ttk.Button(bottom, text="Föreslå output-namn", command=self.suggest_output_name).grid(row=0, column=0, sticky="w")
        self.batch_add_current_button = ttk.Button(bottom, text="Lägg till i batch", command=self.add_current_to_batch)
        self.batch_add_current_button.grid(row=0, column=1, sticky="e", padx=(8, 8))
        self.single_run_button = ttk.Button(bottom, text="Kör jobb", command=self.start_single_run)
        self.single_run_button.grid(row=0, column=2, sticky="e")

    def _build_batch_tab(self) -> None:
        top = ttk.Frame(self.batch_tab)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(0, weight=1)

        ttk.Label(
            top,
            text="Batchläge: bygg en lista med A2L + CSV + output och kör allt i samma fönster.",
        ).grid(row=0, column=0, sticky="w")

        tree_frame = ttk.Frame(self.batch_tab)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        columns = ("a2l", "csv", "output", "status")
        self.batch_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.batch_tree.heading("a2l", text="A2L input")
        self.batch_tree.heading("csv", text="CSV input")
        self.batch_tree.heading("output", text="Output A2L")
        self.batch_tree.heading("status", text="Status")
        self.batch_tree.column("a2l", width=260, anchor="w")
        self.batch_tree.column("csv", width=220, anchor="w")
        self.batch_tree.column("output", width=320, anchor="w")
        self.batch_tree.column("status", width=100, anchor="center")
        self.batch_tree.grid(row=0, column=0, sticky="nsew")
        self.batch_tree.bind("<Double-1>", lambda _event: self.edit_selected_batch_job())
        self.batch_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_batch_button_state())

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.batch_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.batch_tree.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self.batch_tab)
        button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for col in range(7):
            button_row.columnconfigure(col, weight=1 if col == 0 else 0)

        self.batch_add_button = ttk.Button(button_row, text="Lägg till jobb", command=self.add_batch_job)
        self.batch_add_button.grid(row=0, column=0, sticky="w")
        self.batch_edit_button = ttk.Button(button_row, text="Redigera markerat", command=self.edit_selected_batch_job)
        self.batch_edit_button.grid(row=0, column=1, padx=(8, 0))
        self.batch_remove_button = ttk.Button(button_row, text="Ta bort markerat", command=self.remove_selected_batch_job)
        self.batch_remove_button.grid(row=0, column=2, padx=(8, 0))
        self.batch_clear_button = ttk.Button(button_row, text="Rensa lista", command=self.clear_batch_jobs)
        self.batch_clear_button.grid(row=0, column=3, padx=(8, 0))
        self.batch_suggest_button = ttk.Button(button_row, text="Föreslå outputs", command=self.suggest_batch_output_names)
        self.batch_suggest_button.grid(row=0, column=4, padx=(8, 0))
        self.batch_run_button = ttk.Button(button_row, text="Kör alla jobb", command=self.start_batch_run)
        self.batch_run_button.grid(row=0, column=5, padx=(8, 0))

        self._update_batch_button_state()

    def choose_input_a2l(self) -> None:
        filename = filedialog.askopenfilename(
            title="Välj A2L-fil",
            filetypes=[("A2L files", "*.a2l"), ("All files", "*.*")],
        )
        if filename:
            self.input_a2l_var.set(filename)
            if not self.output_a2l_var.get().strip():
                self.suggest_output_name()

    def choose_input_csv(self) -> None:
        filename = filedialog.askopenfilename(
            title="Välj CSV-fil",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            self.input_csv_var.set(filename)
            if not self.output_a2l_var.get().strip():
                self.suggest_output_name()

    def choose_output_a2l(self) -> None:
        suggestion = self._build_suggested_output_path()
        filename = filedialog.asksaveasfilename(
            title="Spara filtrerad A2L som",
            defaultextension=".a2l",
            initialdir=str(suggestion.parent),
            initialfile=suggestion.name,
            filetypes=[("A2L files", "*.a2l"), ("All files", "*.*")],
        )
        if filename:
            self.output_a2l_var.set(filename)

    def suggest_output_name(self) -> None:
        self.output_a2l_var.set(str(self._build_suggested_output_path()))

    def _build_suggested_output_path(self) -> Path:
        a2l = Path(self.input_a2l_var.get()) if self.input_a2l_var.get().strip() else Path.cwd() / "input.a2l"
        csv_file = Path(self.input_csv_var.get()) if self.input_csv_var.get().strip() else Path("signals.csv")
        return self._suggest_output_path(a2l, csv_file)

    def _suggest_output_path(self, input_a2l: Path, input_csv: Path) -> Path:
        csv_stem = input_csv.stem if input_csv.suffix else "signals"
        safe_csv_stem = csv_stem.replace(" ", "_")
        return input_a2l.with_name(f"{input_a2l.stem}_{safe_csv_stem}_filtered.a2l")

    def _append_log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert(tk.END, text)
        self.log_widget.see(tk.END)
        self.log_widget.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        widgets = [
            self.single_run_button,
            self.batch_run_button,
            self.batch_add_button,
            self.batch_add_current_button,
            self.batch_edit_button,
            self.batch_remove_button,
            self.batch_clear_button,
            self.batch_suggest_button,
        ]
        for widget in widgets:
            if widget is not None:
                widget.configure(state="disabled" if running else "normal")
        if not running:
            self._update_batch_button_state()
        self.configure(cursor="watch" if running else "")
        self.update_idletasks()

    def _collect_options(self) -> dict[str, object]:
        return {
            "csv_column": self.csv_column_var.get().strip() or None,
            "ignore_case": self.ignore_case_var.get(),
            "drop_structure": self.drop_structure_var.get(),
            "drop_characteristics": self.drop_characteristics_var.get(),
            "drop_axis_pts": self.drop_axis_pts_var.get(),
            "prune_support": self.prune_support_var.get(),
            "verify": self.verify_var.get(),
            "create_missing_report": self.create_missing_report_var.get(),
        }

    def _validate_job_paths(self, input_a2l: Path, input_csv: Path, output_a2l: Path) -> None:
        if not input_a2l.exists():
            raise FileNotFoundError(f"A2L-filen finns inte: {input_a2l}")
        if not input_csv.exists():
            raise FileNotFoundError(f"CSV-filen finns inte: {input_csv}")
        if input_a2l.is_dir():
            raise ValueError(f"A2L-input måste vara en fil: {input_a2l}")
        if input_csv.is_dir():
            raise ValueError(f"CSV-input måste vara en fil: {input_csv}")
        if output_a2l.is_dir():
            raise ValueError(f"Output måste vara en fil, inte en mapp: {output_a2l}")

    def start_single_run(self) -> None:
        input_a2l = Path(self.input_a2l_var.get().strip()) if self.input_a2l_var.get().strip() else None
        input_csv = Path(self.input_csv_var.get().strip()) if self.input_csv_var.get().strip() else None
        output_a2l = Path(self.output_a2l_var.get().strip()) if self.output_a2l_var.get().strip() else None

        if input_a2l is None or input_csv is None or output_a2l is None:
            messagebox.showerror("Saknar filer", "Välj input A2L, CSV och output-fil först.")
            return

        try:
            self._validate_job_paths(input_a2l, input_csv, output_a2l)
        except Exception as exc:
            messagebox.showerror("Fel i filer", str(exc))
            return

        options = self._collect_options()
        self._append_log("\nKör enkel filtrering...\n")
        self._set_running(True)
        threading.Thread(
            target=self._run_single_job,
            args=(input_a2l, input_csv, output_a2l, options),
            daemon=True,
        ).start()

    def _run_single_job(self, input_a2l: Path, input_csv: Path, output_a2l: Path, options: dict[str, object]) -> None:
        try:
            missing_report = None
            if bool(options["create_missing_report"]):
                missing_report = output_a2l.with_name(f"{output_a2l.stem}_missing.txt")
            result = run_filter_job(
                input_a2l,
                input_csv,
                output_a2l,
                csv_column=options["csv_column"],
                ignore_case=bool(options["ignore_case"]),
                drop_structure=bool(options["drop_structure"]),
                drop_characteristics=bool(options["drop_characteristics"]),
                drop_axis_pts=bool(options["drop_axis_pts"]),
                prune_support=bool(options["prune_support"]),
                missing_report=missing_report,
                verify=bool(options["verify"]),
            )
            summary = build_summary(result, drop_structure=bool(options["drop_structure"]))
            self.after(0, lambda: self._on_single_success(summary, result.output_path, result.missing_report_path))
        except Exception as exc:
            details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.after(0, lambda: self._on_single_error(details))

    def _on_single_success(self, summary: str, output_path: Path, missing_report_path: Path | None) -> None:
        self._set_running(False)
        self._append_log(summary + "\n")
        if missing_report_path is not None:
            self._append_log(f"Missing report skapad: {missing_report_path}\n")
        messagebox.showinfo("Klart", f"Filtrerad A2L skapad:\n{output_path}")

    def _on_single_error(self, message: str) -> None:
        self._set_running(False)
        self._append_log(f"FEL: {message}\n")
        messagebox.showerror("Körningen misslyckades", message)

    def _open_job_dialog(self, *, title: str, job: BatchJob | None = None) -> tuple[Path, Path, Path] | None:
        dialog = BatchJobDialog(
            self,
            title=title,
            input_a2l=str(job.input_a2l) if job else self.input_a2l_var.get().strip(),
            input_csv=str(job.input_csv) if job else self.input_csv_var.get().strip(),
            output_a2l=str(job.output_a2l) if job else self.output_a2l_var.get().strip(),
        )
        self.wait_window(dialog)
        return dialog.result

    def add_batch_job(self) -> None:
        result = self._open_job_dialog(title="Lägg till batchjobb")
        if result is None:
            return
        input_a2l, input_csv, output_a2l = result
        try:
            self._validate_job_paths(input_a2l, input_csv, output_a2l)
        except Exception as exc:
            messagebox.showerror("Fel i filer", str(exc))
            return
        self._add_batch_job(input_a2l, input_csv, output_a2l)

    def add_current_to_batch(self) -> None:
        input_a2l = Path(self.input_a2l_var.get().strip()) if self.input_a2l_var.get().strip() else None
        input_csv = Path(self.input_csv_var.get().strip()) if self.input_csv_var.get().strip() else None
        output_a2l = Path(self.output_a2l_var.get().strip()) if self.output_a2l_var.get().strip() else None

        if input_a2l is None or input_csv is None or output_a2l is None:
            messagebox.showerror("Saknar filer", "Fyll i A2L, CSV och output i enkel körning först.")
            return
        try:
            self._validate_job_paths(input_a2l, input_csv, output_a2l)
        except Exception as exc:
            messagebox.showerror("Fel i filer", str(exc))
            return
        self._add_batch_job(input_a2l, input_csv, output_a2l)
        self.notebook.select(self.batch_tab)

    def _add_batch_job(self, input_a2l: Path, input_csv: Path, output_a2l: Path) -> None:
        self._job_counter += 1
        job_id = f"job_{self._job_counter}"
        job = BatchJob(job_id=job_id, input_a2l=input_a2l, input_csv=input_csv, output_a2l=output_a2l)
        self.batch_jobs[job_id] = job
        self.batch_tree.insert(
            "",
            tk.END,
            iid=job_id,
            values=(str(job.input_a2l), str(job.input_csv), str(job.output_a2l), "Köad"),
        )
        self._append_log(f"Batchjobb tillagt: {job.output_a2l.name}\n")
        self._update_batch_button_state()

    def _selected_job_id(self) -> str | None:
        selection = self.batch_tree.selection()
        return selection[0] if selection else None

    def edit_selected_batch_job(self) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            return
        existing = self.batch_jobs[job_id]
        result = self._open_job_dialog(title="Redigera batchjobb", job=existing)
        if result is None:
            return
        input_a2l, input_csv, output_a2l = result
        try:
            self._validate_job_paths(input_a2l, input_csv, output_a2l)
        except Exception as exc:
            messagebox.showerror("Fel i filer", str(exc))
            return
        updated = BatchJob(job_id=job_id, input_a2l=input_a2l, input_csv=input_csv, output_a2l=output_a2l)
        self.batch_jobs[job_id] = updated
        self.batch_tree.item(job_id, values=(str(input_a2l), str(input_csv), str(output_a2l), "Köad"))
        self._append_log(f"Batchjobb uppdaterat: {output_a2l.name}\n")

    def remove_selected_batch_job(self) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            return
        job = self.batch_jobs.pop(job_id, None)
        self.batch_tree.delete(job_id)
        if job is not None:
            self._append_log(f"Batchjobb borttaget: {job.output_a2l.name}\n")
        self._update_batch_button_state()

    def clear_batch_jobs(self) -> None:
        if not self.batch_jobs:
            return
        if not messagebox.askyesno("Rensa lista", "Vill du ta bort alla batchjobb?"):
            return
        self.batch_jobs.clear()
        for item_id in self.batch_tree.get_children():
            self.batch_tree.delete(item_id)
        self._append_log("Batchlistan rensades.\n")
        self._update_batch_button_state()

    def suggest_batch_output_names(self) -> None:
        if not self.batch_jobs:
            messagebox.showinfo("Tom batchlista", "Lägg till minst ett batchjobb först.")
            return
        for job_id, job in list(self.batch_jobs.items()):
            suggested = self._suggest_output_path(job.input_a2l, job.input_csv)
            updated = BatchJob(job_id=job_id, input_a2l=job.input_a2l, input_csv=job.input_csv, output_a2l=suggested)
            self.batch_jobs[job_id] = updated
            self.batch_tree.item(job_id, values=(str(updated.input_a2l), str(updated.input_csv), str(updated.output_a2l), "Köad"))
        self._append_log("Output-namn uppdaterade för batchlistan.\n")

    def _update_batch_button_state(self) -> None:
        has_jobs = bool(self.batch_jobs)
        has_selection = self._selected_job_id() is not None
        if self.batch_edit_button is not None:
            self.batch_edit_button.configure(state="normal" if has_selection else "disabled")
        if self.batch_remove_button is not None:
            self.batch_remove_button.configure(state="normal" if has_selection else "disabled")
        if self.batch_clear_button is not None:
            self.batch_clear_button.configure(state="normal" if has_jobs else "disabled")
        if self.batch_run_button is not None:
            self.batch_run_button.configure(state="normal" if has_jobs else "disabled")
        if self.batch_suggest_button is not None:
            self.batch_suggest_button.configure(state="normal" if has_jobs else "disabled")

    def _set_batch_status(self, job_id: str, status: str) -> None:
        if job_id in self.batch_jobs:
            job = self.batch_jobs[job_id]
            self.batch_tree.item(job_id, values=(str(job.input_a2l), str(job.input_csv), str(job.output_a2l), status))

    def start_batch_run(self) -> None:
        if not self.batch_jobs:
            messagebox.showerror("Tom batchlista", "Lägg till minst ett jobb först.")
            return
        jobs_in_order = [self.batch_jobs[item_id] for item_id in self.batch_tree.get_children() if item_id in self.batch_jobs]
        try:
            for job in jobs_in_order:
                self._validate_job_paths(job.input_a2l, job.input_csv, job.output_a2l)
        except Exception as exc:
            messagebox.showerror("Fel i batchlista", str(exc))
            return
        options = self._collect_options()
        self._append_log(f"\nStartar batchkörning med {len(jobs_in_order)} jobb...\n")
        self._set_running(True)
        threading.Thread(
            target=self._run_batch_jobs,
            args=(jobs_in_order, options),
            daemon=True,
        ).start()

    def _run_batch_jobs(self, jobs: list[BatchJob], options: dict[str, object]) -> None:
        ok_count = 0
        fail_count = 0
        for job in jobs:
            self.after(0, lambda job_id=job.job_id: self._set_batch_status(job_id, "Kör..."))
            try:
                missing_report = None
                if bool(options["create_missing_report"]):
                    missing_report = job.output_a2l.with_name(f"{job.output_a2l.stem}_missing.txt")
                result = run_filter_job(
                    job.input_a2l,
                    job.input_csv,
                    job.output_a2l,
                    csv_column=options["csv_column"],
                    ignore_case=bool(options["ignore_case"]),
                    drop_structure=bool(options["drop_structure"]),
                    drop_characteristics=bool(options["drop_characteristics"]),
                    drop_axis_pts=bool(options["drop_axis_pts"]),
                    prune_support=bool(options["prune_support"]),
                    missing_report=missing_report,
                    verify=bool(options["verify"]),
                )
                summary = build_summary(result, drop_structure=bool(options["drop_structure"]))
                ok_count += 1
                self.after(
                    0,
                    lambda job_id=job.job_id, job_name=job.output_a2l.name, summary_text=summary: self._on_batch_job_success(
                        job_id,
                        job_name,
                        summary_text,
                    ),
                )
            except Exception as exc:
                fail_count += 1
                details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                self.after(
                    0,
                    lambda job_id=job.job_id, job_name=job.output_a2l.name, message=details: self._on_batch_job_error(
                        job_id,
                        job_name,
                        message,
                    ),
                )
        self.after(0, lambda: self._on_batch_finished(len(jobs), ok_count, fail_count))

    def _on_batch_job_success(self, job_id: str, job_name: str, summary: str) -> None:
        self._set_batch_status(job_id, "OK")
        self._append_log(f"\n=== Batchjobb klart: {job_name} ===\n{summary}\n")

    def _on_batch_job_error(self, job_id: str, job_name: str, message: str) -> None:
        self._set_batch_status(job_id, "FEL")
        self._append_log(f"\n=== Batchjobb fel: {job_name} ===\n{message}\n")

    def _on_batch_finished(self, total: int, ok_count: int, fail_count: int) -> None:
        self._set_running(False)
        self._append_log(
            f"\nBatchkörning klar. Totalt: {total}, OK: {ok_count}, FEL: {fail_count}\n"
        )
        messagebox.showinfo(
            "Batchkörning klar",
            f"Totalt jobb: {total}\nOK: {ok_count}\nFEL: {fail_count}",
        )


if __name__ == "__main__":
    app = A2LFilterGUI()
    app.mainloop()
