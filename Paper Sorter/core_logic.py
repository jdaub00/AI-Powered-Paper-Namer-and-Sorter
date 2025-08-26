# core_logic.py

import json
import logging
import re
from pathlib import Path

import google.generativeai as genai
from pypdf import PdfReader

def get_paper_details(pdf_path: Path, api_key: str):
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
    if ';' in author: author = author.split(';')[0]
    if ',' in author: author = author.split(',')[0]
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