import time
import hashlib
import io
import pytesseract
from typing import List, Optional
from PIL import Image, UnidentifiedImageError
from pytesseract import Output
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ======= CONFIGURATION =======
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif"}

# ======= RESPONSE MODELS =======
class ImageMetadata(BaseModel):
    width: int = Field(..., example=1024)
    height: int = Field(..., example=768)
    format: str = Field(..., example="JPEG")

class OCRResponse(BaseModel):
    success: bool = Field(True, example=True)
    text: str = Field(..., example="Extracted text content from the image.")
    confidence: float = Field(..., example=0.95, description="Average confidence score (0.0 to 1.0)")
    metadata: ImageMetadata
    cached: bool = Field(False, example=False)
    processing_time_ms: int = Field(..., example=342)

class BatchResultItem(BaseModel):
    filename: str = Field(..., example="document.jpg")
    success: bool = Field(..., example=True)
    data: Optional[OCRResponse] = None
    error: Optional[str] = Field(None, example="File too large")

class BatchResponse(BaseModel):
    batch_results: List[BatchResultItem]

# ======= INIT =======
limiter = Limiter(key_func=get_remote_address)

tags_metadata = [
    {
        "name": "OCR",
        "description": "Optical Character Recognition operations.",
    },
    {
        "name": "System",
        "description": "Health checks and system status.",
    },
]

app = FastAPI(
    title="OCR API",
    description="""
    A serverless OCR API.
    
    ## Features
    * **Text Extraction**: Supports JPG, PNG, GIF, BMP etc. via Tesseract 4.0.
    * **Optimization**: In-memory caching for duplicate requests.
    * **Reliability**: Rate limiting and robust error handling.
    """,
    version="1.0.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "Satadip Dhar",
        "email": "dhar.satadip@gmail.com",
    },
)

# ======= GLOBAL EXCEPTION HANDLERS =======
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"success": False, "error": f"Validation Error: {exc.errors()}"}
    )

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ======= STORAGE =======
ocr_cache = {}

# ======= HELPER FUNCTIONS =======
def calculate_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split())

def process_image(content: bytes) -> dict:
    image_stream = io.BytesIO(content)
    pil_image = Image.open(image_stream)
    
    width, height = pil_image.size
    img_format = pil_image.format

    data = pytesseract.image_to_data(pil_image, output_type=Output.DICT, timeout=10)
    
    text_parts = []
    confidences = []

    for i, conf in enumerate(data['conf']):
        if int(conf) > -1:
            txt = data['text'][i].strip()
            if txt:
                text_parts.append(txt)
                confidences.append(int(conf))

    full_text = " ".join(text_parts)
    avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0

    return {
        "text": clean_text(full_text),
        "confidence": round(avg_confidence, 2),
        "metadata": {
            "width": width,
            "height": height,
            "format": img_format
        }
    }

# ======= ENDPOINTS =======
@app.get("/", tags=["System"], include_in_schema=False)
def root():
    return {"status": "online", "docs_url": "/docs"}

@app.post(
    "/extract-text", 
    response_model=OCRResponse, 
    tags=["OCR"],
    summary="Extract text from a single image",
    description="Upload an image of up to 10MB. Returns extracted text, confidence score, and metadata."
)
@limiter.limit("10/minute") 
async def extract_text(request: Request, image: UploadFile = File(..., description="Image file to process")):
    start_time = time.time()

    if image.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Invalid format. Allowed: {ALLOWED_MIME_TYPES}"
        )

    content = await image.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 
            detail="File size exceeds 10MB limit"
        )

    file_hash = calculate_hash(content)
    if file_hash in ocr_cache:
        response = ocr_cache[file_hash].copy()
        response.update({
            "cached": True,
            "processing_time_ms": int((time.time() - start_time) * 1000)
        })
        return JSONResponse(content=response)

    try:
        result = process_image(content)
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Corrupt or unreadable image file"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Internal Processing Error: {str(e)}"
        )

    response_payload = {
        "success": True,
        "text": result["text"],
        "confidence": result["confidence"],
        "metadata": result["metadata"],
        "cached": False,
        "processing_time_ms": int((time.time() - start_time) * 1000)
    }
    
    ocr_cache[file_hash] = response_payload

    return JSONResponse(content=response_payload)

@app.post(
    "/batch-extract", 
    response_model=BatchResponse, 
    tags=["OCR"],
    summary="Process multiple images in batch",
    description="Upload up to 10 images simultaneously. Processing is sequential for preserving memory."
)
@limiter.limit("10/minute")
async def batch_extract(request: Request, images: List[UploadFile] = File(..., description="List of image files")):
    if len(images) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Batch limit exceeded (Max 10 images)"
        )

    batch_results = []
    
    for img in images:
        try:
            content = await img.read()
            data = process_image(content)
            
            ocr_response_obj = {
                 "success": True,
                 "text": data["text"],
                 "confidence": data["confidence"],
                 "metadata": data["metadata"],
                 "cached": False,
                 "processing_time_ms": 0
            }
            
            batch_results.append({
                "filename": img.filename,
                "success": True,
                "data": ocr_response_obj,
                "error": None
            })
        except Exception as e:
            batch_results.append({
                "filename": img.filename,
                "success": False,
                "data": None,
                "error": str(e)
            })

    return JSONResponse(content={"batch_results": batch_results})