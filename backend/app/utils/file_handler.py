import os
import tempfile
import aiofiles
import time
import subprocess
import json
import re
import unicodedata
from typing import Optional, List, Dict, Any
from pathlib import Path
from uuid import uuid4
import PyPDF2
import io
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .trace_handler import TraceHandler

# Try to import optional dependencies
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False

class FileHandler:
    """Handle file operations for the OCRD extractor"""
    
    def __init__(self):
        self.upload_dir = "uploads"
        self.export_dir = "exports"
        self.trace_handler = TraceHandler()
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.export_dir, exist_ok=True)
    
    async def save_uploaded_file(self, file) -> str:
        """Save uploaded file and return file path"""
        # Generate unique filename
        filename = f"{file.filename}_{int(time.time())}"
        file_path = os.path.join(self.upload_dir, filename)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        return file_path
    
    async def extract_pdf_text(self, file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n"
                
                return text.strip()
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
    async def extract_pdf_text_with_tracing(self, file_path: str, trace_id: str) -> Dict[str, Any]:
        """Extract text from PDF with robust fallback chain and forensic tracing"""
        try:
            start_time = time.time()
            trace_dir = Path(self.trace_handler.get_trace_dir(trace_id))
            
            # Initialize metadata
            meta = {
                "pdf_path": str(file_path),
                "trace_id": trace_id,
                "extraction_methods": [],
                "total_pages": 0,
                "char_count": 0,
                "tables_found": 0,
                "ocr_used": False
            }
            
            # Extract text using robust fallback chain
            page_texts, extraction_methods = await self._extract_text_robust(file_path, trace_dir)
            
            # Update metadata
            meta.update({
                "extraction_methods": extraction_methods,
                "total_pages": len(page_texts),
                "char_count": sum(len(t) for t in page_texts),
                "ocr_used": any(method.get("method") == "ocr" for method in extraction_methods)
            })
            
            # Save raw text for each page
            for i, page_text in enumerate(page_texts):
                await self.trace_handler.save_raw_text_page(
                    trace_id, i + 1, page_text
                )
            
            # Clean and normalize text
            clean_text = self._clean_text_robust(page_texts)
            
            # Save clean text
            await self.trace_handler.save_clean_text(trace_id, clean_text)
            
            # Extract tables if available
            tables = await self._extract_tables(file_path, trace_dir)
            if tables:
                # Stitch tables back into text with clear markers
                clean_text = self._stitch_tables_into_text(clean_text, tables)
                meta["tables_found"] = len(tables)
                # Save tables separately
                await self.trace_handler.save_tables(trace_id, tables)
            
            # Create chunks
            chunks = self._create_chunks(clean_text)
            await self.trace_handler.save_chunks(trace_id, chunks)
            
            # Update final metadata
            meta.update({
                "clean_text_length": len(clean_text),
                "chunks_count": len(chunks),
                "extraction_time": time.time() - start_time
            })
            
            # Save metadata
            await self.trace_handler.save_meta(trace_id, meta)
            
            extraction_time = time.time() - start_time
            
            return {
                "raw_text": "\n".join(page_texts),
                "clean_text": clean_text,
                "page_texts": page_texts,
                "chunks": chunks,
                "total_pages": len(page_texts),
                "extraction_time": extraction_time,
                "extraction_methods": extraction_methods,
                "ocr_used": meta["ocr_used"]
            }
                
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
    async def _extract_text_robust(self, file_path: str, trace_dir: Path) -> tuple[List[str], List[Dict]]:
        """Robust text extraction with fallback chain"""
        methods_used = []
        page_texts = []
        
        # Method 1: Try PyMuPDF (best for most PDFs)
        if PYMUPDF_AVAILABLE:
            try:
                page_texts, char_count = self._extract_with_pymupdf(file_path)
                methods_used.append({"method": "pymupdf", "char_count": char_count, "success": True})
                
                # Heuristic: if too little text, try OCR
                if char_count < 2000:
                    print(f"Low text count ({char_count}), attempting OCR...")
                    ocr_texts = await self._extract_with_ocr(file_path, trace_dir)
                    if ocr_texts and sum(len(t) for t in ocr_texts) > char_count:
                        page_texts = ocr_texts
                        methods_used.append({"method": "ocr", "char_count": sum(len(t) for t in ocr_texts), "success": True})
                
                return page_texts, methods_used
            except Exception as e:
                methods_used.append({"method": "pymupdf", "error": str(e), "success": False})
        
        # Method 2: Try pdfminer
        if PDFMINER_AVAILABLE:
            try:
                page_texts, char_count = self._extract_with_pdfminer(file_path)
                methods_used.append({"method": "pdfminer", "char_count": char_count, "success": True})
                return page_texts, methods_used
            except Exception as e:
                methods_used.append({"method": "pdfminer", "error": str(e), "success": False})
        
        # Method 3: Fallback to PyPDF2
        try:
            page_texts, char_count = self._extract_with_pypdf2(file_path)
            methods_used.append({"method": "pypdf2", "char_count": char_count, "success": True})
            return page_texts, methods_used
        except Exception as e:
            methods_used.append({"method": "pypdf2", "error": str(e), "success": False})
            raise Exception("All text extraction methods failed")
    
    def _extract_with_pymupdf(self, file_path: str) -> tuple[List[str], int]:
        """Extract text using PyMuPDF"""
        doc = fitz.open(file_path)
        page_texts = []
        
        for page in doc:
            txt = page.get_text("text")
            page_texts.append(txt)
        
        doc.close()
        char_count = sum(len(t) for t in page_texts)
        return page_texts, char_count
    
    def _extract_with_pdfminer(self, file_path: str) -> tuple[List[str], int]:
        """Extract text using pdfminer"""
        text = pdfminer_extract(file_path)
        # Split by pages (rough approximation)
        page_texts = text.split('\f')  # Form feed character
        char_count = len(text)
        return page_texts, char_count
    
    def _extract_with_pypdf2(self, file_path: str) -> tuple[List[str], int]:
        """Extract text using PyPDF2 (fallback)"""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            page_texts = []
            
            for page in pdf_reader.pages:
                txt = page.extract_text()
                page_texts.append(txt)
        
        char_count = sum(len(t) for t in page_texts)
        return page_texts, char_count
    
    async def _extract_with_ocr(self, file_path: str, trace_dir: Path) -> List[str]:
        """Extract text using OCR (Tesseract)"""
        try:
            # Check if tesseract is available
            subprocess.run(['tesseract', '--version'], capture_output=True, check=True)
            
            # Convert PDF to images
            images_dir = trace_dir / "ocr_images"
            images_dir.mkdir(exist_ok=True)
            
            # Use pdftoppm to convert PDF to images
            subprocess.run([
                'pdftoppm', '-png', '-r', '300', file_path, str(images_dir / "page")
            ], check=True)
            
            # OCR each image
            page_texts = []
            image_files = sorted(images_dir.glob("page-*.png"))
            
            for img_file in image_files:
                result = subprocess.run([
                    'tesseract', str(img_file), 'stdout', '-l', 'eng'
                ], capture_output=True, text=True, check=True)
                page_texts.append(result.stdout)
            
            return page_texts
            
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"OCR failed: {e}")
            return []
    
    def _clean_text_robust(self, page_texts: List[str]) -> str:
        """Robust text cleaning that preserves meaning"""
        # Join all pages
        text = "\n".join(page_texts)
        
        # Fix hyphenation across line breaks: "prohibi-\nted" → "prohibited"
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        
        # Normalize unicode (fi/ff ligatures, etc.)
        text = unicodedata.normalize("NFKC", text)
        
        # Fix common OCR errors
        text = re.sub(r"(\w)\s+(\w)", r"\1 \2", text)  # Fix word spacing
        text = re.sub(r"(\w)([A-Z])", r"\1 \2", text)  # Fix missing spaces before capitals
        
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page numbers and headers/footers (basic patterns)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'Page \d+ of \d+', '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    async def _extract_tables(self, file_path: str, trace_dir: Path) -> List[Dict]:
        """Extract tables from PDF using Camelot"""
        if not CAMELOT_AVAILABLE:
            return []
        
        try:
            tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
            table_data = []
            
            for i, table in enumerate(tables):
                # Convert to dictionary format
                table_dict = {
                    "table_id": i + 1,
                    "page": table.page,
                    "accuracy": table.accuracy,
                    "data": table.df.to_dict('records'),
                    "text": table.df.to_string(index=False)
                }
                table_data.append(table_dict)
            
            return table_data
            
        except Exception as e:
            print(f"Table extraction failed: {e}")
            return []
    
    def _stitch_tables_into_text(self, text: str, tables: List[Dict]) -> str:
        """Stitch extracted tables back into text with clear markers"""
        if not tables:
            return text
        
        table_texts = []
        for table in tables:
            table_marker = f"\n\n[TABLE {table['table_id']} - Page {table['page']}]\n"
            table_content = table['text']
            table_marker += table_content
            table_marker += f"\n[END TABLE {table['table_id']}]\n\n"
            table_texts.append(table_marker)
        
        # Insert tables at the end of the document
        return text + "\n\n" + "\n".join(table_texts)
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        import re
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page numbers and headers/footers (basic patterns)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'Page \d+ of \d+', '', text, flags=re.IGNORECASE)
        
        # Normalize line breaks
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    def _create_chunks(self, text: str, chunk_size: int = 2000, overlap: int = 200) -> List[Dict[str, Any]]:
        """Create text chunks with metadata"""
        import re
        
        # Split by paragraphs first
        paragraphs = re.split(r'\n\s*\n', text)
        
        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_id = 0
        
        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                # Save current chunk
                chunk_id += 1
                chunks.append({
                    "chunk_id": chunk_id,
                    "start_char": current_start,
                    "end_char": current_start + len(current_chunk),
                    "text": current_chunk.strip(),
                    "length": len(current_chunk),
                    "prev_chunk": chunk_id - 1 if chunk_id > 1 else None,
                    "next_chunk": None  # Will be updated
                })
                
                # Start new chunk with overlap
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + " " + para
                current_start = current_start + len(current_chunk) - len(overlap_text) - len(para) - 1
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        # Add final chunk
        if current_chunk.strip():
            chunk_id += 1
            chunks.append({
                "chunk_id": chunk_id,
                "start_char": current_start,
                "end_char": current_start + len(current_chunk),
                "text": current_chunk.strip(),
                "length": len(current_chunk),
                "prev_chunk": chunk_id - 1 if chunk_id > 1 else None,
                "next_chunk": None
            })
        
        # Update next_chunk references
        for i in range(len(chunks) - 1):
            chunks[i]["next_chunk"] = chunks[i + 1]["chunk_id"]
        
        return chunks
    
    async def create_excel_export(self, data: dict) -> str:
        """Create Excel export from analysis results"""
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "OCRD Results"
            
            # Define styles
            header_fill = PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid")
            white_font = Font(color="FFFFFF", bold=True)
            center_alignment = Alignment(horizontal="center", vertical="center")
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            # Add headers
            headers = ["Section", "Instrument", "Allowed", "Note", "Evidence"]
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.fill = header_fill
                cell.font = white_font
                cell.alignment = center_alignment
                cell.border = thin_border
            
            # Add data
            row = 2
            for section, items in data.get("sections", {}).items():
                for key, value in items.items():
                    if isinstance(value, dict) and "allowed" in value:
                        ws.cell(row=row, column=1, value=section)
                        ws.cell(row=row, column=2, value=key)
                        ws.cell(row=row, column=3, value="✓" if value.get("allowed") else "")
                        ws.cell(row=row, column=4, value=value.get("note", ""))
                        # Only show evidence for allowed items
                        evidence_text = ""
                        if value.get("allowed"):
                            evidence_text = value.get("evidence", {}).get("text", "")
                        ws.cell(row=row, column=5, value=evidence_text)
                        
                        # Add borders
                        for col in range(1, 6):
                            ws.cell(row=row, column=col).border = thin_border
                        
                        row += 1
            
            # Auto-adjust column widths
            for column in ws.columns:
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            # Save file
            filename = f"ocrd_export_{int(time.time())}.xlsx"
            file_path = os.path.join(self.export_dir, filename)
            wb.save(file_path)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to create Excel export: {str(e)}")
    
    def cleanup_file(self, file_path: str):
        """Clean up temporary file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
