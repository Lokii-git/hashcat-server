import os
import uuid
import json
import shutil
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import uvicorn
from pydantic import BaseModel

from auth import get_current_username
from job_runner import HashcatJobRunner

# Initialize FastAPI
app = FastAPI(title="Hashcat Server API", description="Remote Hashcat execution server with web UI")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")

# Mount static files without authentication requirement
# This ensures static resources don't trigger authentication popups
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize job runner
job_runner = HashcatJobRunner()

# Ensure directories exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("hashes", exist_ok=True)
os.makedirs("wordlists", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# Models
class JobStatus(BaseModel):
    id: str
    status: str
    hash_file: str
    wordlist: str
    hash_mode: str
    attack_mode: str
    started_at: str
    completed_at: Optional[str] = None
    cracked_count: Optional[int] = None
    total_hashes: Optional[int] = None

# Routes for Web UI
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, username: str = Depends(get_current_username)):
    """Render the main dashboard page"""
    return templates.TemplateResponse("index.html", {"request": request, "username": username})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, username: str = Depends(get_current_username)):
    """Render the upload page"""
    return templates.TemplateResponse("upload.html", {"request": request, "username": username})

@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, username: str = Depends(get_current_username)):
    """Render the jobs page"""
    return templates.TemplateResponse("jobs.html", {"request": request, "username": username})

@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail_page(request: Request, job_id: str, username: str = Depends(get_current_username)):
    """Render the job detail page"""
    job = job_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("job_detail.html", {"request": request, "job": job, "username": username})

# API Routes
@app.post("/api/upload/hashlist")
async def upload_hashlist(hashlist: UploadFile = File(...), username: str = Depends(get_current_username)):
    """Upload a hash file"""
    filename = f"{uuid.uuid4()}_{hashlist.filename}"
    file_path = os.path.join("hashes", filename)
    
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(hashlist.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not upload file: {str(e)}")
    
    return {"filename": filename, "path": file_path}

@app.post("/api/upload/wordlist")
async def upload_wordlist(wordlist: UploadFile = File(...), username: str = Depends(get_current_username)):
    """Upload a wordlist file"""
    filename = f"{uuid.uuid4()}_{wordlist.filename}"
    file_path = os.path.join("wordlists", filename)
    
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(wordlist.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not upload file: {str(e)}")
    
    return {"filename": filename, "path": file_path}

@app.post("/api/run/hashcat")
async def run_hashcat(
    hash_mode: str = Form(...),
    attack_mode: str = Form(...),
    hash_file: str = Form(...),
    wordlist: str = Form(...),
    options: str = Form(""),
    auto_delete_hash: bool = Form(False),
    username: str = Depends(get_current_username)
):
    """Launch a hashcat job"""
    hash_file_path = os.path.join("hashes", hash_file)
    wordlist_path = os.path.join("wordlists", wordlist)
    
    if not os.path.exists(hash_file_path):
        raise HTTPException(status_code=404, detail="Hash file not found")
    if not os.path.exists(wordlist_path):
        raise HTTPException(status_code=404, detail="Wordlist not found")
    
    job_id = job_runner.start_job(hash_mode, attack_mode, hash_file_path, wordlist_path, options, auto_delete_hash)
    return {"job_id": job_id, "status": "started"}

@app.get("/api/jobs")
async def list_jobs(username: str = Depends(get_current_username)):
    """List all jobs with status"""
    return {"jobs": job_runner.list_jobs()}

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, username: str = Depends(get_current_username)):
    """Get job status and details"""
    job = job_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}

@app.get("/api/jobs/{job_id}/output")
async def get_job_output(job_id: str, username: str = Depends(get_current_username)):
    """Get job output file"""
    output_path = os.path.join("outputs", f"hashcat_{job_id}.txt")
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(output_path, media_type="text/plain", filename=f"hashcat_{job_id}.txt")
    
@app.get("/api/files")
async def list_uploaded_files(username: str = Depends(get_current_username)):
    """List all files in the hashes and wordlists directories"""
    files = []
    
    # List hash files
    if os.path.exists("hashes"):
        for file in os.listdir("hashes"):
            files.append({
                "filename": file,
                "path": os.path.join("hashes", file),
                "type": "hashlist"
            })
    
    # List wordlist files
    if os.path.exists("wordlists"):
        for file in os.listdir("wordlists"):
            files.append({
                "filename": file,
                "path": os.path.join("wordlists", file),
                "type": "wordlist"
            })
    
    # For backward compatibility - check uploads directory too
    if os.path.exists("uploads"):
        for file in os.listdir("uploads"):
            files.append({
                "filename": file,
                "path": os.path.join("uploads", file),
                "type": "wordlist" if file.endswith((".txt", ".dict", ".wordlist")) else "hashlist"
            })
            
    return {"files": files}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, username: str = Depends(get_current_username)):
    """Delete a job"""
    success = job_runner.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted"}

@app.delete("/api/jobs/{job_id}/hash_file")
async def delete_hash_file(job_id: str, username: str = Depends(get_current_username)):
    """Delete the hash file associated with a job but keep the job record"""
    job = job_runner.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get hash file path
    hash_file_name = job.get("hash_file")
    if not hash_file_name:
        raise HTTPException(status_code=404, detail="Hash file not found in job record")
    
    hash_file_path = os.path.join("hashes", hash_file_name)
    
    # Check if file exists
    if not os.path.exists(hash_file_path):
        raise HTTPException(status_code=404, detail="Hash file does not exist on disk")
    
    # Delete the file
    try:
        os.remove(hash_file_path)
        return {"status": "deleted", "file": hash_file_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete hash file: {str(e)}")

# Main entry point
if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Hashcat Server - Web interface for hashcat password cracking")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    
    args = parser.parse_args()
    
    print(f"Starting Hashcat Server on {args.host}:{args.port}")
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
