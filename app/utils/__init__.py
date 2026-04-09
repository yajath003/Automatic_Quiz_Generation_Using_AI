import os
import PyPDF2
import docx
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_storage):
    filename = secure_filename(file_storage.filename)
    file_ext = filename.rsplit('.', 1)[1].lower()
    text = ""

    try:
        if file_ext == 'txt':
            text = file_storage.read().decode('utf-8', errors='ignore')
        
        elif file_ext == 'pdf':
            pdf_reader = PyPDF2.PdfReader(file_storage)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        
        elif file_ext == 'docx':
            doc = docx.Document(file_storage)
            for para in doc.paragraphs:
                text += para.text + "\n"
                
    except Exception as e:
        print(f"Error extracting text from {filename}: {e}")
        return None

    return text.strip()
