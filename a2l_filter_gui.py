#!/usr/bin/env python3
from __future__ import annotations
import traceback
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    import sv_ttk  # type: ignore
except Exception:
    sv_ttk = None

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
        self.rowconfigure(0, weight=1)

        card = ttk.Frame(self, padding=18, style="Card.TFrame")
        card.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Add or edit batch job", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )

        ttk.Label(card, text="A2L input").grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(card, textvariable=self.input_a2l_var).grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(0, 10))
        ttk.Button(card, text="Browse...", command=self.choose_input_a2l, style="Accent.TButton").grid(row=1, column=2, pady=(0, 10))

        ttk.Label(card, text="CSV input").grid(row=2, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(card, textvariable=self.input_csv_var).grid(row=2, column=1, sticky="ew", padx=(10, 10), pady=(0, 10))
        ttk.Button(card, text="Browse...", command=self.choose_input_csv).grid(row=2, column=2, pady=(0, 10))

        ttk.Label(card, text="Output A2L").grid(row=3, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(card, textvariable=self.output_a2l_var).grid(row=3, column=1, sticky="ew", padx=(10, 10), pady=(0, 10))
        ttk.Button(card, text="Save as...", command=self.choose_output_a2l).grid(row=3, column=2, pady=(0, 10))

        button_row = ttk.Frame(card)
        button_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        button_row.columnconfigure(0, weight=1)

        ttk.Button(button_row, text="Föreslå output", command=self.suggest_output_name).grid(row=0, column=0, sticky="w")
        ttk.Button(button_row, text="Avbryt", command=self.on_cancel).grid(row=0, column=1, padx=(10, 0))
        ttk.Button(button_row, text="OK", command=self.on_ok, style="Accent.TButton").grid(row=0, column=2, padx=(10, 0))

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
            title="Save filtered A2L as",
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

        icon_path = Path(__file__).parent / "a2l_icon.ico"
        if icon_path.exists():
            self.iconbitmap(icon_path)

        self.title("A2L Filter")
        self.geometry("1180x820")
        self.minsize(980, 700)

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
        self.theme_mode_var = tk.StringVar(value="dark")

        self.single_run_button: ttk.Button | None = None
        self.batch_run_button: ttk.Button | None = None
        self.batch_edit_button: ttk.Button | None = None
        self.batch_remove_button: ttk.Button | None = None
        self.batch_clear_button: ttk.Button | None = None
        self.batch_add_button: ttk.Button | None = None
        self.batch_add_current_button: ttk.Button | None = None
        self.batch_suggest_button: ttk.Button | None = None
        self.theme_toggle_button: ttk.Button | None = None

        self.batch_jobs: dict[str, BatchJob] = {}
        self._job_counter = 0

        self._apply_theme()
        self._configure_styles()
        self._build_ui()

    def _apply_theme(self) -> None:
        if sv_ttk is not None:
            try:
                sv_ttk.set_theme(self.theme_mode_var.get())
            except Exception:
                pass
        else:
            fallback = "vista" if "vista" in ttk.Style().theme_names() else ttk.Style().theme_use()
            ttk.Style().theme_use(fallback)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        base_font = ("Segoe UI", 10)
        heading_font = ("Segoe UI Semibold", 18)
        section_font = ("Segoe UI Semibold", 11)
        mono_font = ("Cascadia Mono", 10)

        self.option_add("*Font", base_font)
        style.configure("TLabel", font=base_font)
        style.configure("TButton", padding=(12, 8))
        style.configure("TEntry", padding=(8, 6))
        style.configure("TCheckbutton", padding=(2, 4))
        style.configure("TNotebook.Tab", padding=(16, 8))
        style.configure("Card.TFrame", padding=18)
        style.configure("Hero.TFrame", padding=18)
        style.configure("Title.TLabel", font=heading_font)
        style.configure("Subtitle.TLabel", font=base_font)
        style.configure("SectionTitle.TLabel", font=section_font)
        style.configure("Status.TLabel", font=("Segoe UI", 9))
        style.configure("Batch.Treeview", rowheight=28)
        style.configure("Batch.Treeview.Heading", font=("Segoe UI Semibold", 10))

        bg = self.cget("bg")
        self.log_text_bg = "#1c1c1c" if self.theme_mode_var.get() == "dark" else "#ffffff"
        self.log_text_fg = "#f2f2f2" if self.theme_mode_var.get() == "dark" else "#1f1f1f"
        self.log_insert_bg = self.log_text_fg
        self.hero_hint_fg = "#9aa0a6" if self.theme_mode_var.get() == "dark" else "#5f6368"
        self.card_border = "#2f2f2f" if self.theme_mode_var.get() == "dark" else "#d9d9d9"
        self.surface = bg

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        hero = ttk.Frame(self, style="Hero.TFrame")
        hero.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        hero.columnconfigure(0, weight=1)

        ttk.Label(hero, text="A2L Filter", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="Filter single files or run multiple jobs in batch mode in the same window.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        toolbar = ttk.Frame(hero)
        toolbar.grid(row=0, column=1, rowspan=2, sticky="e")
        self.theme_toggle_button = ttk.Button(toolbar, text=self._theme_button_text(), command=self.toggle_theme)
        self.theme_toggle_button.grid(row=0, column=0, sticky="e")

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))

        self.single_tab = ttk.Frame(self.notebook, padding=18)
        self.single_tab.columnconfigure(1, weight=1)
        self.notebook.add(self.single_tab, text="Single run")
        self._build_single_tab()

        self.batch_tab = ttk.Frame(self.notebook, padding=18)
        self.batch_tab.columnconfigure(0, weight=1)
        self.batch_tab.rowconfigure(1, weight=1)
        self.notebook.add(self.batch_tab, text="Batch mode")
        self._build_batch_tab()

        options = ttk.LabelFrame(self, text="Common settings", padding=16)
        options.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        for col in range(3):
            options.columnconfigure(col, weight=1)

        ttk.Checkbutton(options, text="Ignore case", variable=self.ignore_case_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="Drop GROUP/FUNCTION", variable=self.drop_structure_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(options, text="Drop CHARACTERISTIC", variable=self.drop_characteristics_var).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(options, text="Drop AXIS_PTS", variable=self.drop_axis_pts_var).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Prune COMPU_METHOD / COMPU_VTAB", variable=self.prune_support_var).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Verify output", variable=self.verify_var).grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Create missing report next to output", variable=self.create_missing_report_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        
        log_frame = ttk.LabelFrame(self, text="Resultat", padding=12)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_widget = ScrolledText(log_frame, wrap=tk.WORD, height=14, relief="flat", borderwidth=0, font=("Cascadia Mono", 10))
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        self.log_widget.configure(
            state="disabled",
            bg=self.log_text_bg,
            fg=self.log_text_fg,
            insertbackground=self.log_insert_bg,
            padx=12,
            pady=12,
        )

        self._append_log("Ready. Choose single run or build a batch list.\n")

    def _build_single_tab(self) -> None:
        card = ttk.Frame(self.single_tab, style="Card.TFrame")
        card.grid(row=0, column=0, columnspan=3, sticky="nsew")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Single run", style="SectionTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(card, text="A2L input").grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(card, textvariable=self.input_a2l_var).grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(0, 10))
        ttk.Button(card, text="Browse...", command=self.choose_input_a2l, style="Accent.TButton").grid(row=1, column=2, sticky="ew", pady=(0, 10))

        ttk.Label(card, text="CSV input").grid(row=2, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(card, textvariable=self.input_csv_var).grid(row=2, column=1, sticky="ew", padx=(10, 10), pady=(0, 10))
        ttk.Button(card, text="Browse...", command=self.choose_input_csv).grid(row=2, column=2, sticky="ew", pady=(0, 10))

        ttk.Label(card, text="Output A2L").grid(row=3, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(card, textvariable=self.output_a2l_var).grid(row=3, column=1, sticky="ew", padx=(10, 10), pady=(0, 10))
        ttk.Button(card, text="Save as...", command=self.choose_output_a2l).grid(row=3, column=2, sticky="ew", pady=(0, 10))

        ttk.Label(
            card,
            text="Tip: add the same settings to the batch list when you want to run multiple jobs in sequence.",
            style="Status.TLabel",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 14))

        bottom = ttk.Frame(card)
        bottom.grid(row=5, column=0, columnspan=3, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        ttk.Button(bottom, text="Suggest output name", command=self.suggest_output_name).grid(row=0, column=0, sticky="w")
        self.batch_add_current_button = ttk.Button(bottom, text="Add to batch", command=self.add_current_to_batch)
        self.batch_add_current_button.grid(row=0, column=1, sticky="e", padx=(10, 10))
        self.single_run_button = ttk.Button(bottom, text="Run job", command=self.start_single_run, style="Accent.TButton")
        self.single_run_button.grid(row=0, column=2, sticky="e")

    def _build_batch_tab(self) -> None:
        header_card = ttk.Frame(self.batch_tab, style="Card.TFrame")
        header_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_card.columnconfigure(0, weight=1)

        ttk.Label(header_card, text="Batch mode", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header_card,
            text="Build a list with A2L + CSV + output and run all in the same window.",
            style="Status.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        tree_frame = ttk.Frame(self.batch_tab, style="Card.TFrame")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        columns = ("a2l", "csv", "output", "status")
        self.batch_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse", style="Batch.Treeview")
        self.batch_tree.heading("a2l", text="A2L input")
        self.batch_tree.heading("csv", text="CSV input")
        self.batch_tree.heading("output", text="Output A2L")
        self.batch_tree.heading("status", text="Status")
        self.batch_tree.column("a2l", width=260, anchor="w")
        self.batch_tree.column("csv", width=220, anchor="w")
        self.batch_tree.column("output", width=360, anchor="w")
        self.batch_tree.column("status", width=100, anchor="center")
        self.batch_tree.grid(row=0, column=0, sticky="nsew")
        self.batch_tree.bind("<Double-1>", lambda _event: self.edit_selected_batch_job())
        self.batch_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_batch_button_state())

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.batch_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.batch_tree.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self.batch_tab)
        button_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        button_row.columnconfigure(0, weight=1)

        self.batch_add_button = ttk.Button(button_row, text="Add job", command=self.add_batch_job, style="Accent.TButton")
        self.batch_add_button.grid(row=0, column=0, sticky="w")
        self.batch_edit_button = ttk.Button(button_row, text="Edit selected", command=self.edit_selected_batch_job)
        self.batch_edit_button.grid(row=0, column=1, padx=(10, 0))
        self.batch_remove_button = ttk.Button(button_row, text="Remove selected", command=self.remove_selected_batch_job)
        self.batch_remove_button.grid(row=0, column=2, padx=(10, 0))
        self.batch_clear_button = ttk.Button(button_row, text="Clear list", command=self.clear_batch_jobs)
        self.batch_clear_button.grid(row=0, column=3, padx=(10, 0))
        self.batch_suggest_button = ttk.Button(button_row, text="Suggest outputs", command=self.suggest_batch_output_names)
        self.batch_suggest_button.grid(row=0, column=4, padx=(10, 0))
        self.batch_run_button = ttk.Button(button_row, text="Run all jobs", command=self.start_batch_run, style="Accent.TButton")
        self.batch_run_button.grid(row=0, column=5, padx=(10, 0))

        self._update_batch_button_state()

    def _theme_button_text(self) -> str:
        return "Change to light mode" if self.theme_mode_var.get() == "dark" else "Change to dark mode"

    def toggle_theme(self) -> None:
        self.theme_mode_var.set("light" if self.theme_mode_var.get() == "dark" else "dark")
        self._apply_theme()
        self._configure_styles()
        if self.theme_toggle_button is not None:
            self.theme_toggle_button.configure(text=self._theme_button_text())
        if hasattr(self, "log_widget"):
            self.log_widget.configure(
                bg=self.log_text_bg,
                fg=self.log_text_fg,
                insertbackground=self.log_insert_bg,
            )

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
            title="Save filtered A2L as",
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
            self.theme_toggle_button,
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
            messagebox.showerror("Missing files", "Choose input A2L, CSV and output file first.")
            return

        try:
            self._validate_job_paths(input_a2l, input_csv, output_a2l)
        except Exception as exc:
            messagebox.showerror("Fel i filer", str(exc))
            return

        options = self._collect_options()
        self._append_log("\nStarting single filtering...\n")
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
            self._append_log(f"Missing report created: {missing_report_path}\n")
        messagebox.showinfo("Done", f"Filtered A2L created:\n{output_path}")

    def _on_single_error(self, message: str) -> None:
        self._set_running(False)
        self._append_log(f"ERROR: {message}\n")
        messagebox.showerror("Job failed", message)

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
            messagebox.showerror("Missing files", "Choose input A2L, CSV and output file first.")
            return
        try:
            self._validate_job_paths(input_a2l, input_csv, output_a2l)
        except Exception as exc:
            messagebox.showerror("File error", str(exc))
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
        if not messagebox.askyesno("Clear list", "Do you want to remove all batch jobs?"):
            return
        self.batch_jobs.clear()
        for item_id in self.batch_tree.get_children():
            self.batch_tree.delete(item_id)
        self._append_log("Batchlistan rensades.\n")
        self._update_batch_button_state()

    def suggest_batch_output_names(self) -> None:
        if not self.batch_jobs:
            messagebox.showinfo("Empty batch list", "Add at least one batch job first.")
            return
        for job_id, job in list(self.batch_jobs.items()):
            suggested = self._suggest_output_path(job.input_a2l, job.input_csv)
            updated = BatchJob(job_id=job_id, input_a2l=job.input_a2l, input_csv=job.input_csv, output_a2l=suggested)
            self.batch_jobs[job_id] = updated
            self.batch_tree.item(job_id, values=(str(updated.input_a2l), str(updated.input_csv), str(updated.output_a2l), "Köad"))
        self._append_log("Output-names updated for batch list.\n")

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
            messagebox.showerror("Empty batch list", "Add at least one job first.")
            return
        jobs_in_order = [self.batch_jobs[item_id] for item_id in self.batch_tree.get_children() if item_id in self.batch_jobs]
        try:
            for job in jobs_in_order:
                self._validate_job_paths(job.input_a2l, job.input_csv, job.output_a2l)
        except Exception as exc:
            messagebox.showerror("Error in batch list", str(exc))
            return
        options = self._collect_options()
        self._append_log(f"\nStarting batch run with {len(jobs_in_order)} jobs...\n")
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
