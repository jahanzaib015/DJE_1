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
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .trace_handler import TraceHandler
from ..services.rag_index import index_pdf
from .logger import setup_logger

logger = setup_logger(__name__)

# Try to import NLTK for sentence tokenization
try:
    import nltk
    from nltk.tokenize import sent_tokenize
    NLTK_AVAILABLE = True
    # Download required NLTK data
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
except ImportError:
    NLTK_AVAILABLE = False

# Try to import LangChain for improved chunking
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

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
    
    # Negation cues pattern for preserving exceptions and negations
    NEG_CUES = re.compile(r"\b(not|no|except|unless|excluded|exclusion|prohibit|forbidden|restricted|ban(ned)?|provided\s+that|excluding|not\s+permitted|not\s+allowed)\b", re.IGNORECASE)
    
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
            
            # Create chunks with improved LangChain-based chunking
            chunks = self.chunk_text(clean_text)
            await self.trace_handler.save_chunks(trace_id, chunks)
            
            # Save chunks in JSONL format for verification
            await self.save_chunks_jsonl(chunks, trace_id)
            
            # Index chunks for RAG retrieval
            trace_dir = self.trace_handler.get_trace_dir(trace_id)
            clean_text_path = os.path.join(trace_dir, "20_clean_text.txt")
            chunks_path = os.path.join(trace_dir, "30_chunks.jsonl")
            vectordb_dir = "var/chroma"
            
            # Perform RAG indexing
            rag_results = index_pdf(
                clean_text_path=clean_text_path,
                chunks_path=chunks_path,
                vectordb_dir=vectordb_dir,
                doc_id=trace_id
            )
            
            # Save RAG indexing results
            await self.trace_handler.save_rag_index(trace_id, rag_results)
            
            # Update final metadata
            meta.update({
                "clean_text_length": len(clean_text),
                "chunks_count": len(chunks),
                "extraction_time": time.time() - start_time,
                "rag_indexed": rag_results.get("success", False),
                "rag_chunks_indexed": rag_results.get("indexed", 0)
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
                    logger.info(f"Low text count ({char_count}), attempting OCR...")
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
            logger.warning(f"OCR failed: {e}")
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
        """Extract tables from PDF using Camelot with both lattice and stream flavors"""
        if not CAMELOT_AVAILABLE:
            return []
        
        table_data = []
        table_id = 1
        
        # Method 1: Try lattice first (line-drawn tables)
        try:
            logger.debug("Attempting table extraction with lattice flavor...")
            lattice_tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
            
            for table in lattice_tables:
                # Convert to markdown-like format for better LLM processing
                markdown_text = self._convert_table_to_markdown(table.df, table_id, table.page, "lattice")
                
                table_dict = {
                    "table_id": table_id,
                    "page": table.page,
                    "accuracy": table.accuracy,
                    "method": "lattice",
                    "data": table.df.to_dict('records'),
                    "text": table.df.to_string(index=False),
                    "markdown": markdown_text
                }
                table_data.append(table_dict)
                table_id += 1
                
            logger.info(f"Lattice extraction found {len(lattice_tables)} tables")
            
        except Exception as e:
            logger.warning(f"Lattice table extraction failed: {e}")
        
        # Method 2: Try stream (whitespace-separated tables)
        try:
            logger.debug("Attempting table extraction with stream flavor...")
            stream_tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
            
            for table in stream_tables:
                # Convert to markdown-like format for better LLM processing
                markdown_text = self._convert_table_to_markdown(table.df, table_id, table.page, "stream")
                
                table_dict = {
                    "table_id": table_id,
                    "page": table.page,
                    "accuracy": table.accuracy,
                    "method": "stream",
                    "data": table.df.to_dict('records'),
                    "text": table.df.to_string(index=False),
                    "markdown": markdown_text
                }
                table_data.append(table_dict)
                table_id += 1
                
            logger.info(f"Stream extraction found {len(stream_tables)} tables")
            
        except Exception as e:
            logger.warning(f"Stream table extraction failed: {e}")
        
        logger.info(f"Total tables extracted: {len(table_data)}")
        return table_data
    
    def _convert_table_to_markdown(self, df, table_id: int, page: int, method: str) -> str:
        """Convert table DataFrame to markdown-like format for better LLM processing"""
        try:
            # Create markdown table with proper formatting
            markdown_lines = []
            markdown_lines.append(f"=== TABLE {table_id} (page {page}) - {method.upper()} ===")
            
            # Convert DataFrame to markdown format
            if not df.empty:
                # Get column headers
                headers = df.columns.tolist()
                markdown_lines.append(" | ".join(str(col) for col in headers))
                markdown_lines.append(" | ".join("---" for _ in headers))
                
                # Add data rows
                for _, row in df.iterrows():
                    row_data = [str(cell) if pd.notna(cell) else "" for cell in row]
                    markdown_lines.append(" | ".join(row_data))
            
            markdown_lines.append(f"=== END TABLE {table_id} ===")
            return "\n".join(markdown_lines)
            
        except Exception as e:
            logger.error(f"Error converting table {table_id} to markdown: {e}", exc_info=True)
            # Fallback to simple text format
            return f"=== TABLE {table_id} (page {page}) - {method.upper()} ===\n{df.to_string(index=False)}\n=== END TABLE {table_id} ==="
    
    def _stitch_tables_into_text(self, text: str, tables: List[Dict]) -> str:
        """Stitch extracted tables back into text with clear markers"""
        if not tables:
            return text
        
        table_texts = []
        for table in tables:
            # Use the markdown format if available, otherwise fall back to text
            if 'markdown' in table:
                table_texts.append(f"\n\n{table['markdown']}\n")
            else:
                # Fallback to old format
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
    
    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """Create text chunks using LangChain's RecursiveCharacterTextSplitter for better granularity"""
        if not LANGCHAIN_AVAILABLE:
            # Fallback to existing chunking method
            return self._create_chunks(text, max_tokens=1000, overlap_tokens=150)
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,        # ~700–1 000 tokens per chunk
            chunk_overlap=150,      # 15% overlap keeps context
            separators=["\n\n", "\n", ". ", ";", " "]
        )
        chunks = splitter.split_text(text)
        
        # Convert to the expected format
        result = []
        char_position = 0
        
        for i, chunk_text in enumerate(chunks):
            chunk_length = len(chunk_text)
            result.append({
                "chunk_id": i + 1,
                "start_char": char_position,
                "end_char": char_position + chunk_length,
                "text": chunk_text,
                "length": chunk_length,
                "token_estimate": chunk_length // 4,
                "prev_chunk": i if i > 0 else None,
                "next_chunk": i + 2 if i < len(chunks) - 1 else None,
                "has_negations": bool(self.NEG_CUES.search(chunk_text)),
                "type": "text"
            })
            char_position += chunk_length
        
        return result
    
    def _create_chunks(self, text: str, max_tokens: int = 1200, overlap_tokens: int = 150) -> List[Dict[str, Any]]:
        """Create text chunks with negation-aware chunking that preserves exceptions and legal constructs"""
        
        # Fallback to simple chunking if NLTK is not available
        if not NLTK_AVAILABLE:
            return self._create_chunks_fallback(text, max_tokens * 4, overlap_tokens * 4)
        
        # Convert token estimates to character estimates (rough approximation: 1 token ≈ 4 characters)
        max_chars = max_tokens * 4
        overlap_chars = overlap_tokens * 4
        
        # Split text into sentences
        sentences = sent_tokenize(text)
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_id = 0
        char_position = 0
        
        i = 0
        while i < len(sentences):
            sentence = sentences[i].strip()
            if not sentence:
                i += 1
                continue
                
            # Check if sentence contains negation cues
            has_negation = bool(self.NEG_CUES.search(sentence))
            
            # Calculate length of current sentence plus potential neighbors
            sentence_length = len(sentence)
            extended_length = sentence_length
            
            # If sentence has negation cues, try to include neighbors
            if has_negation:
                # Add previous sentence if available
                if i > 0 and sentences[i-1].strip():
                    prev_sentence = sentences[i-1].strip()
                    extended_length += len(prev_sentence) + 1  # +1 for space
                
                # Add next sentence if available
                if i + 1 < len(sentences) and sentences[i+1].strip():
                    next_sentence = sentences[i+1].strip()
                    extended_length += len(next_sentence) + 1  # +1 for space
            
            # Check if adding this sentence (with potential neighbors) would exceed limit
            if current_length + extended_length > max_chars and current_chunk:
                # Save current chunk
                chunk_id += 1
                chunk_text = " ".join(current_chunk).strip()
                chunks.append({
                    "chunk_id": chunk_id,
                    "start_char": char_position - current_length,
                    "end_char": char_position,
                    "text": chunk_text,
                    "length": current_length,
                    "token_estimate": current_length // 4,
                    "prev_chunk": chunk_id - 1 if chunk_id > 1 else None,
                    "next_chunk": None,  # Will be updated
                    "has_negations": any(self.NEG_CUES.search(s) for s in current_chunk)
                })
                
                # Create overlap for next chunk
                overlap_text = chunk_text[-overlap_chars:] if len(chunk_text) > overlap_chars else chunk_text
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text)
            else:
                # Add sentence to current chunk
                if has_negation and i > 0 and sentences[i-1].strip() and not current_chunk:
                    # Include previous sentence for context
                    current_chunk.append(sentences[i-1].strip())
                    current_length += len(sentences[i-1].strip()) + 1
                
                current_chunk.append(sentence)
                current_length += sentence_length + (1 if current_chunk else 0)
                
                # If we included next sentence for negation context, skip it in next iteration
                if has_negation and i + 1 < len(sentences) and sentences[i+1].strip():
                    current_chunk.append(sentences[i+1].strip())
                    current_length += len(sentences[i+1].strip()) + 1
                    i += 1  # Skip next sentence as we already included it
            
            char_position += sentence_length + 1  # +1 for space
            i += 1
        
        # Add final chunk
        if current_chunk:
            chunk_id += 1
            chunk_text = " ".join(current_chunk).strip()
            chunks.append({
                "chunk_id": chunk_id,
                "start_char": char_position - current_length,
                "end_char": char_position,
                "text": chunk_text,
                "length": current_length,
                "token_estimate": current_length // 4,
                "prev_chunk": chunk_id - 1 if chunk_id > 1 else None,
                "next_chunk": None,
                "has_negations": any(self.NEG_CUES.search(s) for s in current_chunk)
            })
        
        # Update next_chunk references
        for i in range(len(chunks) - 1):
            chunks[i]["next_chunk"] = chunks[i + 1]["chunk_id"]
        
        return chunks
    
    def _create_chunks_fallback(self, text: str, chunk_size: int = 2000, overlap: int = 200) -> List[Dict[str, Any]]:
        """Fallback chunking method when NLTK is not available"""
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
                    "token_estimate": len(current_chunk) // 4,
                    "prev_chunk": chunk_id - 1 if chunk_id > 1 else None,
                    "next_chunk": None,  # Will be updated
                    "has_negations": bool(self.NEG_CUES.search(current_chunk))
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
                "token_estimate": len(current_chunk) // 4,
                "prev_chunk": chunk_id - 1 if chunk_id > 1 else None,
                "next_chunk": None,
                "has_negations": bool(self.NEG_CUES.search(current_chunk))
            })
        
        # Update next_chunk references
        for i in range(len(chunks) - 1):
            chunks[i]["next_chunk"] = chunks[i + 1]["chunk_id"]
        
        return chunks
    
    async def save_chunks_jsonl(self, chunks: List[Dict[str, Any]], trace_id: str) -> str:
        """Save chunks to JSONL format for verification and analysis"""
        try:
            jsonl_path = os.path.join(self.trace_handler.get_trace_dir(trace_id), "chunks.jsonl")
            
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for chunk in chunks:
                    # Create a clean JSONL entry
                    jsonl_entry = {
                        "chunk_id": chunk["chunk_id"],
                        "start_char": chunk["start_char"],
                        "end_char": chunk["end_char"],
                        "length": chunk["length"],
                        "token_estimate": chunk.get("token_estimate", chunk["length"] // 4),
                        "has_negations": chunk.get("has_negations", False),
                        "prev_chunk": chunk.get("prev_chunk"),
                        "next_chunk": chunk.get("next_chunk"),
                        "text": chunk["text"]
                    }
                    f.write(json.dumps(jsonl_entry, ensure_ascii=False) + '\n')
            
            return jsonl_path
            
        except Exception as e:
            logger.error(f"Failed to save chunks JSONL: {e}", exc_info=True)
            return None
    
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
