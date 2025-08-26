# paper_sorter_gui.py (v2.7 — Configurable Paths)
# CHANGES IN THIS PATCH:
# - GUI now reads folder paths from config.json.
# - WATCH_FOLDER and SORTED_FOLDER are no longer hardcoded.
# - Minor adjustments to accommodate dynamic paths.

import os
import time
import shutil
import json
import logging
import re
from pathlib import Path
import sys
import threading
import webbrowser
from queue import Queue
from tkinter import filedialog

from tkinterdnd2 import DND_FILES, TkinterDnD
import customtkinter as ctk
from CTkMessagebox import CTkMessagebox
from customtkinter import CTkInputDialog
import google.generativeai as genai
from pypdf import PdfReader
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- NEW: DnD-enabled CTk root to keep CTk overlays/alpha in sync with main window ---
class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        ctk.CTk.__init__(self, *args, **kwargs)
        # Initialize TkDnD on this CTk window
        self.TkdndVersion = TkinterDnD._require(self)
        TkinterDnD.DnDWrapper.__init__(self)

# ======================================================================
# (All helper functions are unchanged and included below)
# ======================================================================
def get_paper_details(pdf_path: Path, api_key: str):
    # This function is unchanged.
    try:
        reader = PdfReader(pdf_path); text_content = ""
        for page in reader.pages[:5]:
            extracted = page.extract_text()
            if extracted: text_content += extracted + "\n\n"
        if not text_content.strip(): return None
        text_snippet = text_content[:8000]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={'temperature': 0.0})
        prompt = f"""
        Analyze text from a research paper and output ONLY a valid JSON object with these keys:
        1. "author": ONLY the last name of the VERY FIRST author listed.
        2. "year": the 4-digit publication year.
        3. "journal": official NLM/PubMed journal abbreviation if available; else the full journal name. Preprints => "Preprint".
        4. "title": the full official title of the paper.
        5. "is_multiple_authors": boolean true/false.
        Example: {{"author": "FitzGerald", "year": "2016", "journal": "Invest Radiol", "title": "A Proposed...", "is_multiple_authors": true}}
        Paper Text: ---
        {text_snippet}
        ---
        """
        response = model.generate_content(prompt)
        m = re.search(r"\{.*\}", (response.text or ""), re.DOTALL)
        if not m: return None
        details = json.loads(m.group(0))
        details.setdefault('author', 'Unknown'); details.setdefault('year', 'Unknown')
        details.setdefault('journal', 'Unknown'); details.setdefault('title', 'Unknown Title')
        details.setdefault('is_multiple_authors', True)
        return details
    except Exception as e:
        logging.error(f"AI processing error for {pdf_path.name}: {e}")
        return None

def sanitize_filename_part(part):
    return re.sub(r'[\\/*?:"<>|]', "", str(part).strip()).replace(' ', '_')

def cleanup_author_string(author: str) -> str:
    if not author:
        return ''
    if ';' in author:
        author = author.split(';')[0]
    if ',' in author:
        author = author.split(',')[0]
    return author.strip()

def safe_rename(src: Path, dst: Path) -> Path:
    if not dst.exists(): src.rename(dst); return dst
    stem, ext = dst.stem, dst.suffix; i = 1
    while True:
        candidate = dst.with_name(f"{stem}-{i}{ext}")
        if not candidate.exists(): src.rename(candidate); return candidate
        i += 1

def list_dirs(parent: Path) -> list[Path]:
    try: return sorted([p for p in parent.iterdir() if p.is_dir() and not p.name.startswith('.')])
    except Exception: return []

class TextboxRedirector:
    def __init__(self, textbox: ctk.CTkTextbox): self.textbox = textbox
    def write(self, text): self.textbox.after(0, self.textbox.insert, "end", text); self.textbox.after(0, self.textbox.see, "end")
    def flush(self): pass

class FolderPicker(ctk.CTkToplevel):
    def __init__(self, master, root_path: Path):
        super().__init__(master)
        self.title("Choose Destination Folder"); self.geometry("520x360"); self.resizable(True, True)
        self.transient(master); self.grab_set()
        self.root_path = root_path; self.level_frames = []; self.selected_paths = []
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self); self.scroll.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.btn_row = ctk.CTkFrame(self); self.btn_row.grid(row=1, column=0, padx=10, pady=(0,10), sticky="ew")
        self.btn_row.columnconfigure((0,1,2), weight=1)
        self.btn_ok = ctk.CTkButton(self.btn_row, text="Confirm", command=self._confirm); self.btn_ok.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.btn_root = ctk.CTkButton(self.btn_row, text="Jump to Root", command=self._reset_to_root); self.btn_root.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.btn_cancel = ctk.CTkButton(self.btn_row, text="Cancel", command=self._cancel); self.btn_cancel.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        self._add_level(parent=self.root_path, label_text=str(self.root_path.name or self.root_path)); self.result = None
    def _reset_to_root(self):
        for f in self.level_frames: f.destroy()
        self.level_frames.clear(); self.selected_paths.clear()
        self._add_level(parent=self.root_path, label_text=str(self.root_path.name or self.root_path))
    def _add_level(self, parent: Path, label_text: str):
        frame = ctk.CTkFrame(self.scroll); frame.pack(fill="x", padx=5, pady=5)
        lbl = ctk.CTkLabel(frame, text=label_text); lbl.pack(side="left", padx=5)
        children = list_dirs(parent); options = [p.name for p in children]; options.append("New folder…"); options.append("<Select none>")
        var = ctk.StringVar(value="<Select none>"); om = ctk.CTkOptionMenu(frame, variable=var, values=options, command=lambda choice, parent=parent: self._on_select(choice, parent))
        om.pack(side="left", padx=5, fill="x", expand=True)
        self.level_frames.append(frame); self.selected_paths.append(parent)
    def _remove_levels_after(self, index: int):
        while len(self.level_frames) > index + 1:
            f = self.level_frames.pop(); f.destroy(); self.selected_paths.pop()
    def _on_select(self, choice: str, parent: Path):
        idx = self._find_level_index_for_parent(parent)
        if idx is None: return
        self._remove_levels_after(idx)
        if choice == "<Select none>": return
        if choice == "New folder…": self._create_new_folder(parent, idx); return
        selected = parent / choice; self.selected_paths.append(selected); self._add_level(parent=selected, label_text=f"↳ {selected.name}")
    def _create_new_folder(self, parent: Path, idx: int):
        dialog = CTkInputDialog(text="Enter new folder name:", title="New Folder"); name = dialog.get_input()
        if not name: return
        clean = re.sub(r'[\/*?:"<>|]', "", name).strip()
        if not clean: CTkMessagebox(master=self, title="Invalid Name", message="Folder name cannot be empty or only special characters."); return
        new_path = parent / clean
        try: new_path.mkdir(parents=True, exist_ok=False)
        except FileExistsError: CTkMessagebox(master=self, title="Exists", message="A folder with that name already exists.")
        except Exception as e: CTkMessagebox(master=self, title="Error", message=f"Failed to create folder: {e}")
        self._remove_levels_after(idx-1 if idx>0 else -1); self._add_level(parent=parent, label_text=str(parent.name))
    def _find_level_index_for_parent(self, parent: Path):
        for i, p in enumerate(self.selected_paths):
            if p == parent: return i
        return None
    def _final_path(self) -> Path:
        return self.selected_paths[-1] if self.selected_paths else self.root_path
    def _confirm(self): self.result = self._final_path(); self.destroy()
    def _cancel(self): self.result = None; self.destroy()

# --- NEW: Custom Dialog for Editing Filenames ---
class FilenameEditorDialog(ctk.CTkToplevel):
    def __init__(self, master, original_name: str, ai_title: str, proposed_name: str):
        super().__init__(master)
        self.title("Propose & Edit Filename")
        self.geometry("600x250")
        self.transient(master)
        self.grab_set()

        self.result = None  # This will store the final filename or None if skipped

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Info Frame
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(info_frame, text="Original File:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(info_frame, text=original_name, wraplength=450).grid(row=0, column=1, sticky="w", padx=5)
        
        ctk.CTkLabel(info_frame, text="AI-Detected Title:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, sticky="w", pady=(5,0))
        ctk.CTkLabel(info_frame, text=ai_title, wraplength=450).grid(row=1, column=1, sticky="w", padx=5, pady=(5,0))

        # Entry Frame
        entry_frame = ctk.CTkFrame(self)
        entry_frame.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        entry_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(entry_frame, text="Proposed Filename (Editable):").pack(side="top", anchor="w", padx=10, pady=(5,2))
        self.filename_entry = ctk.CTkEntry(entry_frame, width=550)
        self.filename_entry.pack(side="top", fill="x", expand=True, padx=10, pady=(0,10))
        self.filename_entry.insert(0, proposed_name)

        # Button Frame
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=2, column=0, padx=15, pady=15, sticky="sew")
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.continue_button = ctk.CTkButton(button_frame, text="Continue", command=self._on_continue)
        self.continue_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.skip_button = ctk.CTkButton(button_frame, text="Skip File", command=self._on_skip)
        self.skip_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    def _on_continue(self):
        self.result = self.filename_entry.get().strip()
        if not self.result.lower().endswith('.pdf'):
            self.result += ".pdf"
        self.destroy()

    def _on_skip(self):
        self.result = None
        self.destroy()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Paper Sorter"); self.root.geometry("900x640")
        ctk.set_appearance_mode("dark")
        self.root.grid_columnconfigure(0, weight=1); self.root.grid_rowconfigure(0, weight=1)

        if getattr(sys, 'frozen', False): self.SCRIPT_DIRECTORY = Path(sys.executable).parent
        else: self.SCRIPT_DIRECTORY = Path(__file__).parent
        self.API_KEY = os.getenv('GEMINI_API_KEY')
        
        # --- NEW: Load configuration from config.json ---
        try:
            CONFIG_PATH = self.SCRIPT_DIRECTORY / "config.json"
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)
            self.WATCH_FOLDER = Path(config["watch_folder"])
            self.SORTED_FOLDER = Path(config["sorted_folder"])
        except Exception as e:
            CTkMessagebox(master=self.root, title="Configuration Error", message=f"Failed to load config.json:\n{e}", icon="error")
            self.root.destroy()
            return
        
        # Unified log for both sorting and naming
        self.LOG_FILE = self.SORTED_FOLDER / 'paper_sorter_log.txt'
        self.WATCH_FOLDER.mkdir(exist_ok=True)
        self.SORTED_FOLDER.mkdir(exist_ok=True)
        
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1); self.main_frame.grid_rowconfigure(0, weight=1); self.main_frame.grid_rowconfigure(1, weight=3)

        self.top_frame = ctk.CTkFrame(self.main_frame, fg_color="#18191a")  # Match log frame color
        self.top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.top_frame.grid_columnconfigure(0, weight=1); self.top_frame.grid_rowconfigure((0, 2), weight=1)
        # DnD registration on a CTk frame still works because root is DnD-enabled (DnDCTk)
        self.top_frame.drop_target_register(DND_FILES); self.top_frame.dnd_bind('<<Drop>>', self.handle_drop)
        self.plus_label = ctk.CTkLabel(self.top_frame, text="+", font=ctk.CTkFont(size=50)); self.plus_label.grid(row=0, column=0, pady=(20, 0))
        self.browse_text_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent"); self.browse_text_frame.grid(row=1, column=0, pady=(10, 20))
        self.drag_label = ctk.CTkLabel(self.browse_text_frame, text="To sort papers, drag them here, or ", font=ctk.CTkFont(size=14)); self.drag_label.pack(side="left")
        self.browse_label = ctk.CTkLabel(self.browse_text_frame, text="browse", font=ctk.CTkFont(size=14, underline=True), text_color=("blue", "cyan"), cursor="hand2")
        self.browse_label.pack(side="left"); self.browse_label.bind("<Button-1>", lambda e: self.select_and_add_papers())
        self.after_browse_label = ctk.CTkLabel(self.browse_text_frame, text=" your computer...", font=ctk.CTkFont(size=14)); self.after_browse_label.pack(side="left")
        
        self.bottom_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.bottom_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.bottom_frame.grid_columnconfigure(0, weight=1); self.bottom_frame.grid_rowconfigure(1, weight=1)
        self.button_frame = ctk.CTkFrame(self.bottom_frame)
        self.button_frame.grid(row=0, column=0, padx=0, pady=10, sticky="ew")
        self.functions_label = ctk.CTkLabel(self.button_frame, text="Additional functions:")
        self.functions_label.pack(side="left", padx=(10, 15), pady=5)
        self.btn_name_papers = ctk.CTkButton(self.button_frame, text="Name Paper(s)", command=self.rename_papers_flow); self.btn_name_papers.pack(side="left", padx=5, pady=5)
        self.btn_view_sorted = ctk.CTkButton(self.button_frame, text="View Sorted", command=self.open_sorted_folder); self.btn_view_sorted.pack(side="left", padx=5, pady=5)
        self.btn_view_log = ctk.CTkButton(self.button_frame, text="View Log", command=self.open_log_file); self.btn_view_log.pack(side="left", padx=5, pady=5)
        
        self.log_textbox = ctk.CTkTextbox(self.bottom_frame, activate_scrollbars=True); self.log_textbox.grid(row=1, column=0, padx=0, pady=(0, 10), sticky="nsew")
        self.redirector = TextboxRedirector(self.log_textbox)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', handlers=[
            logging.FileHandler(self.LOG_FILE, encoding='utf-8'), logging.StreamHandler(self.redirector)])
        self.file_queue = Queue(); self.rename_queue = Queue(); self.gui_queue = Queue()
        self.root.after(100, self.start_app)
        # One-time safety on startup
        self.root.after(0, self._normalize_root)

    # --- NEW: normalize helper to fix any leaked alpha/disabled state from modals ---
    def _normalize_root(self):
        try:
            self.root.attributes("-alpha", 1.0)
            self.root.attributes("-disabled", False)
            self.root.update_idletasks()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def start_app(self):
        if not self.API_KEY: logging.error("FATAL: GEMINI_API_KEY not set."); return
        self.worker_thread = threading.Thread(target=self.processing_loop, daemon=True); self.worker_thread.start()
        self.rename_worker_thread = threading.Thread(target=self.rename_processing_loop, daemon=True); self.rename_worker_thread.start()
        self.start_watcher(); self.process_gui_queue(); self.process_existing_files()
    def on_closing(self):
        logging.info("--- Shutting down... ---")
        try: self.observer.stop(); self.observer.join(timeout=3)
        except Exception: pass
        self.root.destroy()
    def start_watcher(self):
        event_handler = self.create_watchdog_handler(); self.observer = Observer()
        self.observer.schedule(event_handler, str(self.WATCH_FOLDER), recursive=False); self.observer.start()
        logging.info(f"Watching for new files in: {self.WATCH_FOLDER}"); self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    def create_watchdog_handler(self):
        class MyHandler(FileSystemEventHandler):
            def __init__(self, queue): self.queue = queue
            def on_created(self, event):
                if not event.is_directory and event.src_path.lower().endswith('.pdf'):
                    time.sleep(2); self.queue.put(Path(event.src_path))
        return MyHandler(self.file_queue)
    def processing_loop(self):
        while True:
            pdf_path = self.file_queue.get()
            logging.info(f"--- Processing (sort): {pdf_path.name} ---")
            details = get_paper_details(pdf_path, self.API_KEY)
            if details: self.gui_queue.put(("sort", pdf_path, details))
            else: logging.error(f"Could not get details for {pdf_path.name}.")
    def rename_processing_loop(self):
        while True:
            pdf_path = self.rename_queue.get()
            logging.info(f"--- Processing (rename): {pdf_path.name} ---")
            details = get_paper_details(pdf_path, self.API_KEY)
            if details: self.gui_queue.put(("rename", pdf_path, details))
            else: logging.error(f"Could not get details for {pdf_path.name}.")
    def process_gui_queue(self):
        try:
            while not self.gui_queue.empty():
                mode, pdf_path, details = self.gui_queue.get()
                if mode == "sort": self.handle_user_confirmation_sort(pdf_path, details)
                elif mode == "rename": self.handle_rename_confirmation(pdf_path, details)
        finally:
            self.root.after(200, self.process_gui_queue)

    # --- FIXED: Reworked function + normalization after every modal ---
    def handle_user_confirmation_sort(self, pdf_path: Path, details: dict):
        details['author'] = cleanup_author_string(details.get('author', 'Unknown'))
        author = details.get('author', 'Unknown'); year = details.get('year', 'Unknown')
        journal = details.get('journal', 'Unknown'); is_multiple = bool(details.get('is_multiple_authors', True))
        author_string = f"{author} et al" if is_multiple else author
        new_filename_base = f"{sanitize_filename_part(author_string)}_{sanitize_filename_part(journal)}_{year}"
        new_filename_ext = f"{new_filename_base}.pdf"; title = details.get('title', 'Unknown Title')
        
        # --- STEP 1: Propose and Edit Name ---
        name_dialog = FilenameEditorDialog(self.root, original_name=pdf_path.name, ai_title=title, proposed_name=new_filename_ext)
        self.root.wait_window(name_dialog)
        self._normalize_root()  # <-- normalize after modal
        final_filename = name_dialog.result

        if not final_filename:
            logging.info(f"User skipped '{pdf_path.name}' at name proposal stage."); return

        # --- STEP 2: Check for Duplicates (based on the user-approved name) ---
        final_filename_base = Path(final_filename).stem
        if list(self.SORTED_FOLDER.rglob(f"{final_filename_base}*.pdf")):
            msg_text = (f"A potential duplicate exists for:'{final_filename}'\n\nAdd anyway?")
            msg = CTkMessagebox(master=self.root, title="Suspected Duplicate", message=msg_text, icon="question", option_1="Add Anyway", option_2="Skip")
            choice = msg.get()
            self._normalize_root()  # <-- normalize after modal
            if choice == "Skip":
                logging.warning(f"DUPLICATE: User chose to skip '{pdf_path.name}'.")
                return
        
        # --- STEP 3: Choose the destination folder ---
        picker = FolderPicker(self.root, self.SORTED_FOLDER)
        self.root.wait_window(picker)
        self._normalize_root()  # <-- normalize after modal
        dest_folder = picker.result
        
        if not dest_folder: 
            logging.info(f"User canceled destination selection for '{pdf_path.name}'."); return

        final_destination_path = dest_folder / final_filename
        
        # --- STEP 4: Final Confirmation (No Edit button needed anymore) ---
        try:
            rel_folder = final_destination_path.parent.relative_to(self.SCRIPT_DIRECTORY)
            folder_display = f"...\\{rel_folder}"
        except ValueError:
            folder_display = str(final_destination_path.parent)
        confirm_text = (f"Destination Folder:\n{folder_display}\n\nFilename:\n{final_destination_path.name}")
        confirm_msg = CTkMessagebox(master=self.root, title="Confirm Move", message=confirm_text, icon="question", option_1="Confirm", option_2="Cancel")
        confirm_choice = confirm_msg.get()
        self._normalize_root()  # <-- normalize after modal
        
        if confirm_choice == "Cancel":
            logging.info(f"User canceled final move for '{pdf_path.name}'."); return
        
        # --- STEP 5: Move the file ---
        try:
            final_destination_path.parent.mkdir(parents=True, exist_ok=True)
            if final_destination_path.exists():
                final_destination_path = final_destination_path.with_name(f"{final_destination_path.stem}-1{final_destination_path.suffix}"); n = 1
                while final_destination_path.exists():
                    n += 1
                    base_stem = final_destination_path.stem.rsplit('-',1)[0]
                    final_destination_path = final_destination_path.with_name(f"{base_stem}-{n}{final_destination_path.suffix}")
            shutil.move(str(pdf_path), str(final_destination_path))
            try:
                rel_path = final_destination_path.relative_to(self.SCRIPT_DIRECTORY)
                logging.info(f"MOVED: '{pdf_path.name}' -> '{rel_path}'")
            except ValueError:
                logging.info(f"MOVED: '{pdf_path.name}' -> '{final_destination_path}'")
        except Exception as e:
            logging.error(f"Failed to move file: {e}")
        finally:
            self._normalize_root()  # extra safety

    # (The rename flow can also be updated to use the new dialog if desired)
    def rename_papers_flow(self):
        # Prompt user to select a folder or files
        choice = CTkMessagebox(master=self.root, title="Rename Papers", message="Would you like to select a folder or individual PDF files?", icon="question", option_1="Folder", option_2="Files", option_3="Cancel").get()
        if choice == "Cancel":
            logging.info("User canceled the rename papers operation.")
            return
        pdf_files = []
        if choice == "Folder":
            folder = filedialog.askdirectory(title="Select Folder Containing PDFs")
            if not folder:
                logging.info("No folder selected for renaming papers.")
                return
            folder_path = Path(folder)
            pdf_files = list(folder_path.glob('*.pdf'))
        elif choice == "Files":
            selected_files = filedialog.askopenfilenames(title="Select PDF files to rename", filetypes=[("PDF Documents", "*.pdf")])
            if not selected_files:
                logging.info("No files selected for renaming.")
                return
            pdf_files = [Path(f) for f in selected_files]
        if not pdf_files:
            logging.info("No PDF files found for renaming.")
            CTkMessagebox(master=self.root, title="No PDFs", message="No PDF files found.")
            return
        total = len(pdf_files)
        renamed = 0
        skipped = 0
        for pdf_path in pdf_files:
            details = get_paper_details(pdf_path, self.API_KEY)
            if not details:
                logging.info(f"Could not extract details for {pdf_path.name}. Skipping.")
                skipped += 1
                continue
            details['author'] = cleanup_author_string(details.get('author', 'Unknown'))
            author = details.get('author', 'Unknown')
            year = details.get('year', 'Unknown')
            journal = details.get('journal', 'Unknown')
            is_multiple = bool(details.get('is_multiple_authors', True))
            author_string = f"{author} et al" if is_multiple else author
            new_filename_base = f"{sanitize_filename_part(author_string)}_{sanitize_filename_part(journal)}_{year}"
            new_filename_ext = f"{new_filename_base}.pdf"
            title = details.get('title', 'Unknown Title')
            # Show dialog for user to edit/approve
            name_dialog = FilenameEditorDialog(self.root, original_name=pdf_path.name, ai_title=title, proposed_name=new_filename_ext)
            self.root.wait_window(name_dialog)
            self._normalize_root()
            final_filename = name_dialog.result
            if not final_filename:
                logging.info(f"User skipped '{pdf_path.name}' at name proposal stage.")
                skipped += 1
                continue
            final_path = pdf_path.parent / final_filename
            if final_path.exists():
                exists_box = CTkMessagebox(master=self.root, title="File Exists", message=f"A file named {final_filename} already exists. Skipping.")
                self.root.wait_window(exists_box)
                self._normalize_root()
                logging.info(f"Skipped renaming '{pdf_path.name}' because '{final_filename}' already exists.")
                skipped += 1
                continue
            try:
                pdf_path.rename(final_path)
                log_msg = f"Renamed (AI Naming): {pdf_path.name} -> {final_filename}"
                logging.info(log_msg)
                renamed += 1
            except Exception as e:
                logging.error(f"Failed to rename {pdf_path.name}: {e}")
                error_box = CTkMessagebox(master=self.root, title="Rename Error", message=f"Failed to rename {pdf_path.name}: {e}")
                self.root.wait_window(error_box)
                self._normalize_root()
                skipped += 1
        logging.info(f"Rename process finished. {renamed} renamed, {skipped} skipped, {total} total.")
        CTkMessagebox(master=self.root, title="Rename Complete", message=f"Renaming complete.\nRenamed: {renamed}\nSkipped: {skipped}\nTotal: {total}")
    def handle_rename_confirmation(self, pdf_path: Path, details: dict):
        # ... (unchanged placeholder) ...
        pass
        
    def process_existing_files(self):
        logging.info(f"Scanning for existing files in {self.WATCH_FOLDER}...")
        pdf_files = list(self.WATCH_FOLDER.glob('*.pdf'))
        if pdf_files:
            logging.info(f"Found {len(pdf_files)} PDF(s) to queue for processing.")
            for pdf_path in pdf_files:
                self.file_queue.put(pdf_path)
        else:
            logging.info("No PDF files found; ToSort folder is empty.")

    def select_and_add_papers(self):
        selected_files = filedialog.askopenfilenames(title="Select PDF files to add", filetypes=[("PDF Documents", "*.pdf")])
        if not selected_files: logging.info("No files selected."); return
        added = 0
        for file_path_str in selected_files:
            try:
                source_path = Path(file_path_str); destination_path = self.WATCH_FOLDER / source_path.name
                shutil.copy2(source_path, destination_path); added += 1
            except Exception as e: logging.error(f"Failed to copy '{source_path.name}': {e}")
        logging.info(f"User added {added} paper(s) to the ToSort folder.")
        
    def handle_drop(self, event):
        file_paths_str = self.root.tk.splitlist(event.data); added_count = 0
        for path_str in file_paths_str:
            if Path(path_str).suffix.lower() == '.pdf':
                try:
                    source_path = Path(path_str); destination_path = self.WATCH_FOLDER / source_path.name
                    shutil.copy2(source_path, destination_path); added_count += 1
                except Exception as e: logging.error(f"Failed to copy '{source_path.name}': {e}")
        if added_count > 0: logging.info(f"User dropped {added_count} paper(s) to the ToSort folder.")
        
    def open_watch_folder(self): webbrowser.open(self.WATCH_FOLDER)
    def open_sorted_folder(self): webbrowser.open(self.SORTED_FOLDER)
    def open_log_file(self):
        # Open the unified log file in the default text editor
        import os
        os.startfile(self.LOG_FILE)

if __name__ == "__main__":
    root = DnDCTk()
    app = App(root)
    root.mainloop()
