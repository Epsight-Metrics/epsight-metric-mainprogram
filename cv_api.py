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
import os

# Import existing modules
from modules.detection import preprocess, get_binary, find_objects, DetectedObject
from modules.reference import ReferenceManager
from modules.utils import now_iso

# Load config.json untuk default parameter deteksi
def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

_config = load_config()
DEFAULT_PPM            = _config.get("pixel_per_mm", 7.86)
DEFAULT_CONTOUR_THRESH = _config.get("contour_thresh", 150)
DEFAULT_MIN_AREA       = _config.get("contour_min_area", 1500)
DEFAULT_MIN_FEATURE_MM = _config.get("min_feature_mm", 5.0)
DEFAULT_TOLERANCE_MM   = _config.get("tolerance_mm", 1.0)

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
async def update_frame(
    file: UploadFile = File(...),
    ppm: float = Form(None),
    contour_thresh: int = Form(None),
    min_area: float = Form(None),
    min_feature_mm: float = Form(None),
    tolerance_mm: float = Form(None),
):
    """
    Update latest frame dan jalankan deteksi real-time.
    Dipanggil oleh browser (mode online) setiap ~500ms untuk bounding box overlay.
    Juga dipanggil oleh Main-ProgramV7.py untuk sinkronisasi frame.
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
        
        # Gunakan parameter yang dikirim atau fallback ke config.json default
        _ppm            = ppm            if ppm            is not None else DEFAULT_PPM
        _contour_thresh = contour_thresh if contour_thresh is not None else DEFAULT_CONTOUR_THRESH
        _min_area       = min_area       if min_area       is not None else DEFAULT_MIN_AREA
        _min_feature_mm = min_feature_mm if min_feature_mm is not None else DEFAULT_MIN_FEATURE_MM
        _tolerance_mm   = tolerance_mm   if tolerance_mm   is not None else DEFAULT_TOLERANCE_MM
        
        # Jalankan deteksi real-time
        obj_list    = []
        result_list = []
        try:
            gray, blurred, enhanced = preprocess(image)
            binary  = get_binary(enhanced, _contour_thresh)
            objects = find_objects(binary, _min_area, _ppm, _min_feature_mm)
            
            for obj in objects:
                # Serialisasi data objek untuk SVG overlay di frontend
                obj_data = {
                    "shape":       obj.shape,
                    "bbox":        list(obj.bbox),
                    "center":      list(obj.center),
                    "radius_px":   float(obj.radius_px),
                    "diameter_mm": round(obj.diameter_mm, 2),
                    "width_mm":    round(obj.width_mm,    2),
                    "height_mm":   round(obj.height_mm,   2),
                    "rot_box":     obj.rot_box.tolist() if hasattr(obj.rot_box, 'tolist') else obj.rot_box,
                    "contour":     obj.contour.tolist() if hasattr(obj.contour, 'tolist') else []
                }
                obj_list.append(obj_data)
                
                # Bandingkan dengan referensi untuk status GOOD/NO GOOD/NO REF
                status, matched_ref, detail = ref_manager.compare(obj, _tolerance_mm)
                result_list.append({
                    "status":      status,
                    "matched_ref": matched_ref,
                    "detail":      detail
                })
            
            # Update latest_detections agar frontend bisa polling via /detections
            with frame_lock:
                global latest_detections
                latest_detections = {
                    "objects":   obj_list,
                    "results":   result_list,
                    "timestamp": now_iso()
                }
        except Exception as detect_err:
            # Jika deteksi gagal, tetap return success agar stream tidak putus
            print(f"[update-frame] Deteksi error: {detect_err}")
        
        # Kembalikan data deteksi langsung di response (stateless - cocok untuk cloud/Railway)
        # Browser tidak perlu polling /detections terpisah, setiap request self-contained
        return {
            "success":   True,
            "detected":  len(obj_list),
            "objects":   obj_list,
            "results":   result_list,
            "timestamp": now_iso()
        }
    except Exception as e:
        return {"success": False, "error": str(e), "objects": [], "results": [], "detected": 0}

@app.post("/update-detections")
async def update_detections(
    data: dict
):
    """
    Update latest detection results for realtime display
    """
    try:
        with frame_lock:
            global latest_detections
            latest_detections = {
                "objects": data.get("objects", []),
                "results": data.get("results", []),
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
