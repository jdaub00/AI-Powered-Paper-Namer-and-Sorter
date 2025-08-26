# AI Paper Sorter

AI Paper Sorter is a desktop utility for organizing research papers (PDFs) using **AI-assisted metadata extraction** and a simple drag-and-drop interface. It automatically analyzes papers, proposes filenames (based on author, journal, and year), and helps you sort them into structured folders. The project includes a GUI application and an optional background watcher that launches the sorter whenever new PDFs appear.

---

## Features
- **Drag-and-drop** or browse to add papers.  
- **AI-powered metadata extraction** (title, author, year, journal) using Google Gemini.  
- **Filename proposal & editing dialog** before saving.  
- **Interactive folder picker** for choosing destinations.  
- **Duplicate detection** with user confirmation.  
- **Rename existing PDFs** in bulk with AI-suggested names.  
- **Background watcher** (`watch_and_launch.py`) that starts the GUI automatically when new papers arrive in the `ToSort` folder.  
- **Dark mode interface** powered by [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter).  

---

## Project Structure
- `paper_sorter_gui.py` — Main GUI application:contentReference[oaicite:0]{index=0}  
- `core_logic.py` — Core functions for AI metadata extraction & safe renaming:contentReference[oaicite:1]{index=1}  
- `gui_components.py` — Custom GUI dialogs and folder picker:contentReference[oaicite:2]{index=2}  
- `watch_and_launch.py` — Background watcher to auto-launch the sorter:contentReference[oaicite:3]{index=3}  
- `config.json` — Configuration file for watch/sorted folder paths:contentReference[oaicite:4]{index=4}  
- `Icon.ico` / `Icon.png` — Application icon files  

---

## Requirements

Main dependencies:

customtkinter — modern Tkinter UI

tkinterdnd2 — drag & drop support

CTkMessagebox — message dialogs

pypdf — PDF text extraction

google-generativeai — AI paper metadata parsing

watchdog — folder monitoring

Configuration
Edit config.json to define your folders:

json
Copy
Edit
{
  "watch_folder": "C:\\Users\\<username>\\Documents\\ToSort",
  "sorted_folder": "C:\\Users\\<username>\\Documents\\Sorted"
}
watch_folder: new papers dropped here are processed

sorted_folder: destination root for organized papers

Usage
1. Run the GUI
bash
Copy
Edit
python paper_sorter_gui.py
Drag & drop PDFs into the window, or use the browse option.

Approve/edit AI-suggested filenames.

Select a folder for the paper.

Confirm and move the file.

2. Rename Existing Papers
Click "Name Paper(s)" in the GUI to batch-rename PDFs in a folder.

3. Background Watcher
Run:

bash
Copy
Edit
python watch_and_launch.py
Continuously watches the ToSort folder.

Automatically launches the GUI when new PDFs are detected.

Environment Variables
Set your Gemini API key:

bash
Copy
Edit
export GEMINI_API_KEY="your_api_key_here"   # Linux/macOS
setx GEMINI_API_KEY "your_api_key_here"     # Windows
Building Executables
You can build standalone executables with PyInstaller:

bash
Copy
Edit
pyinstaller --noconfirm --onefile --windowed --icon=Icon.ico paper_sorter_gui.py
pyinstaller --noconfirm --onefile --icon=Icon.ico watch_and_launch.py
Logging
Logs are saved to paper_sorter_log.txt inside the sorted_folder.

Shows file moves, renames, skips, and errors.

License
This project is distributed for academic and personal research use.
