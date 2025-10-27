import os
import tempfile
import aiofiles
import time
from typing import Optional, List, Dict, Any
import PyPDF2
import io
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .trace_handler import TraceHandler

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
        """Extract text from PDF with forensic tracing"""
        try:
            start_time = time.time()
            
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                # Extract text page by page
                page_texts = []
                raw_text = ""
                
                for page_num in range(total_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    page_texts.append(page_text)
                    raw_text += page_text + "\n"
                    
                    # Save raw text for each page
                    await self.trace_handler.save_raw_text_page(
                        trace_id, page_num + 1, page_text
                    )
                
                # Clean and normalize text
                clean_text = self._clean_text(raw_text.strip())
                
                # Save clean text
                await self.trace_handler.save_clean_text(trace_id, clean_text)
                
                # Create chunks
                chunks = self._create_chunks(clean_text)
                await self.trace_handler.save_chunks(trace_id, chunks)
                
                extraction_time = time.time() - start_time
                
                return {
                    "raw_text": raw_text.strip(),
                    "clean_text": clean_text,
                    "page_texts": page_texts,
                    "chunks": chunks,
                    "total_pages": total_pages,
                    "extraction_time": extraction_time
                }
                
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
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
