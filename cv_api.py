"""
CV API - Computer Vision Service
Sistem Inspeksi Dimensi Part Manufaktur (Mode Online)
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
from io import BytesIO
import json

# Import existing modules
from modules.detection import preprocess, get_binary, find_objects, DetectedObject
from modules.reference import ReferenceManager
from modules.utils import now_iso

app = FastAPI(
    title="EPSight CV API",
    description="Computer Vision API for Online Inspection Mode",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize reference manager
ref_manager = ReferenceManager("referensi.json")

# Store latest frame and detection results for realtime access
latest_frame = None
latest_detections = {"objects": [], "results": []}
frame_lock = __import__('threading').Lock()

@app.get("/")
async def root():
    return {
        "service": "EPSight CV API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "references_loaded": len(ref_manager.refs),
        "timestamp": now_iso()
    }

@app.post("/save-reference-from-stream")
async def save_reference_from_stream(
    name: str = Form(...),
    ppm: float = Form(...),
    tolerance_mm: float = Form(...),
    contour_thresh: int = Form(150),
    min_area: float = Form(1500),
    min_feature_mm: float = Form(5.0)
):
    """
    Save reference from current video stream frame
    """
    try:
        with frame_lock:
            if latest_frame is None:
                return {
                    "success": False,
                    "error": "No frame available from stream",
                    "timestamp": now_iso()
                }
            
            image = latest_frame.copy()
        
        # Process image
        gray, blurred, enhanced = preprocess(image)
        binary = get_binary(enhanced, contour_thresh)
        objects = find_objects(binary, min_area, ppm, min_feature_mm)
        
        if not objects:
            return {
                "success": False,
                "error": "No objects detected in current frame",
                "timestamp": now_iso()
            }
        
        if len(objects) > 1:
            return {
                "success": False,
                "error": f"Multiple objects detected ({len(objects)}). Please ensure only one object is in frame.",
                "timestamp": now_iso()
            }
        
        obj = objects[0]
        ref_data = ref_manager.save_reference(obj, name, tolerance_mm)
        
        return {
            "success": True,
            "reference": ref_data,
            "message": f"Reference '{name}' saved from stream",
            "timestamp": now_iso()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": now_iso()
        }

@app.post("/save-reference")
async def save_reference(
    file: UploadFile = File(...),
    name: str = Form(...),
    ppm: float = Form(...),
    tolerance_mm: float = Form(...),
    contour_thresh: int = Form(150),
    min_area: float = Form(1500),
    min_feature_mm: float = Form(5.0)
):
    """
    Save a new reference profile from uploaded image
    
    Parameters:
    - file: Image file (JPEG/PNG)
    - name: Reference name
    - ppm: Pixel per millimeter calibration value
    - tolerance_mm: Tolerance in millimeters
    - contour_thresh: Contour detection threshold
    - min_area: Minimum contour area in pixels
    - min_feature_mm: Minimum feature size in mm
    """
    try:
        # 1. Decode image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # 2. Preprocess image
        gray, blurred, enhanced = preprocess(image)
        
        # 3. Get binary image
        binary = get_binary(enhanced, contour_thresh)
        
        # 4. Find objects
        objects = find_objects(binary, min_area, ppm, min_feature_mm)
        
        if not objects:
            return {
                "success": False,
                "error": "No objects detected in image",
                "timestamp": now_iso()
            }
        
        if len(objects) > 1:
            return {
                "success": False,
                "error": f"Multiple objects detected ({len(objects)}). Please ensure only one object is in frame.",
                "timestamp": now_iso()
            }
        
        # 5. Get the object
        obj = objects[0]
        
        # 6. Save reference
        ref_data = ref_manager.save_reference(obj, name, tolerance_mm)
        
        return {
            "success": True,
            "reference": ref_data,
            "message": f"Reference '{name}' saved successfully",
            "timestamp": now_iso()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": now_iso()
        }

@app.get("/references")
async def list_references():
    """List all available references"""
    return {
        "references": ref_manager.refs,
        "count": len(ref_manager.refs)
    }

@app.post("/update-frame")
async def update_frame(file: UploadFile = File(...)):
    """
    Update latest frame for stream-based operations
    Called by Main-ProgramV7.py to keep frame in sync
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image")
        
        with frame_lock:
            global latest_frame
            latest_frame = image
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/update-detections")
async def update_detections(
    objects: list = [],
    results: list = []
):
    """
    Update latest detection results for realtime display
    """
    try:
        with frame_lock:
            global latest_detections
            latest_detections = {
                "objects": objects,
                "results": results,
                "timestamp": now_iso()
            }
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/detections")
async def get_detections():
    """
    Get latest detection results for dashboard overlay
    """
    with frame_lock:
        return latest_detections

@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    ppm: float = Form(...),
    tolerance_mm: float = Form(...),
    contour_thresh: int = Form(150),
    min_area: float = Form(1500),
    min_feature_mm: float = Form(5.0),
    reference_name: str = Form(...)
):
    """
    Process uploaded image and detect object dimensions
    
    Parameters:
    - file: Image file (JPEG/PNG)
    - ppm: Pixel per millimeter calibration value
    - tolerance_mm: Tolerance in millimeters
    - contour_thresh: Contour detection threshold
    - min_area: Minimum contour area in pixels
    - min_feature_mm: Minimum feature size in mm
    - reference_name: Name of reference profile to compare
    """
    try:
        # 1. Decode image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # 2. Preprocess image
        gray, blurred, enhanced = preprocess(image)
        
        # 3. Get binary image
        binary = get_binary(enhanced, contour_thresh)
        
        # 4. Find objects
        objects = find_objects(binary, min_area, ppm, min_feature_mm)
        
        if not objects:
            return {
                "success": False,
                "error": "No objects detected in image",
                "status": "NO OBJECT",
                "measurements": {},
                "deviations": {},
                "timestamp": now_iso()
            }
        
        # 5. Get the largest object (assume it's the part to inspect)
        obj = max(objects, key=lambda o: o.area_px)
        
        # 6. Compare with reference
        status, matched_ref, detail = ref_manager.compare(obj, tolerance_mm)
        
        # 7. Calculate deviations
        deviations = {}
        if matched_ref and matched_ref in ref_manager.refs:
            ref = ref_manager.refs[matched_ref]
            if obj.shape == "circle":
                deviations["diameter_mm"] = round(obj.diameter_mm - ref["diameter_mm"], 2)
            else:
                deviations["width_mm"] = round(obj.width_mm - ref["width_mm"], 2)
                deviations["height_mm"] = round(obj.height_mm - ref["height_mm"], 2)
        
        # 8. Prepare measurements
        measurements = {
            "shape": obj.shape,
            "diameter_mm": round(obj.diameter_mm, 2),
            "width_mm": round(obj.width_mm, 2),
            "height_mm": round(obj.height_mm, 2),
            "vertices": obj.vertices,
            "circularity": round(obj.circularity, 3),
            "bbox": obj.bbox,
            "center": obj.center,
            "radius_px": obj.radius_px,
            "rot_box": obj.rot_box.tolist() if hasattr(obj.rot_box, 'tolist') else obj.rot_box,
            "contour": obj.contour.tolist() if hasattr(obj.contour, 'tolist') else obj.contour
        }
        
        # 9. Map status
        status_map = {
            "GOOD": "OK",
            "NO GOOD": "NG",
            "NO REF": "NO REF"
        }
        
        return {
            "success": True,
            "status": status_map.get(status, status),
            "measurements": measurements,
            "deviations": deviations,
            "reference_matched": matched_ref,
            "detail": detail,
            "timestamp": now_iso()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "ERROR",
            "measurements": {},
            "deviations": {},
            "timestamp": now_iso()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
