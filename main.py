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
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import secrets
import uvicorn
from pydantic import BaseModel

from auth import get_current_username, initialize_credentials
from job_runner import HashcatJobRunner

# Initialize credentials on startup to ensure we have valid credentials
initialize_credentials()

# Custom middleware for handling proxy headers
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Handle X-Forwarded headers from reverse proxy
        if "x-forwarded-proto" in request.headers:
            request.scope["scheme"] = request.headers["x-forwarded-proto"]
        
        if "x-forwarded-host" in request.headers:
            request.scope["headers"].append(
                (b"host", request.headers["x-forwarded-host"].encode())
            )
            
        response = await call_next(request)
        return response

# Initialize FastAPI
app = FastAPI(
    title="Hashcat Server API", 
    description="Remote Hashcat execution server with web UI",
    # Ensure proper root path when behind a proxy
    root_path=os.getenv("ROOT_PATH", "")
)

# Add middlewares
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(ProxyHeadersMiddleware)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")

# Mount static files without authentication requirement
# This ensures static resources don't trigger authentication popups
app.mount("/static", StaticFiles(directory="static"), name="static")

# Define which routes should be public (not require authentication)
PUBLIC_ROUTES = [
    "/static", 
    "/favicon.ico",
    "/login",
    "/check-auth",  # Allow checking auth status without auth
    "/api/check-auth", # API version of auth check
    "/css/", # Any potential CSS files
    "/js/",  # Any potential JS files
    "/img/", # Any potential image files
    # Add any other routes that should be accessible without authentication
]

# Custom middleware to bypass authentication for public routes
class AuthenticationBypassMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Check if the path is a public route
        path = request.url.path
        for public_route in PUBLIC_ROUTES:
            if path.startswith(public_route):
                # For public routes, add a special marker to skip auth in dependencies
                request.state.skip_auth = True
                return await call_next(request)
        
        # Apply authentication for all other routes
        return await call_next(request)

# Add authentication bypass middleware
app.add_middleware(AuthenticationBypassMiddleware)

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
    # Set authentication bypass flag for this route
    request.state.skip_auth = True
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/check-auth")
async def check_auth(username: str = Depends(get_current_username)):
    """Check if authentication is valid"""
    return {"authenticated": True, "username": username}

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
    # Use a shorter ID instead of full UUID
    short_id = str(uuid.uuid4())[:8]  
    filename = f"{short_id}_{hashlist.filename}"
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
    # Use a shorter ID instead of full UUID
    short_id = str(uuid.uuid4())[:8]
    filename = f"{short_id}_{wordlist.filename}"
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
    queue_if_busy: bool = Form(False),
    username: str = Depends(get_current_username)
):
    """Launch a hashcat job"""
    hash_file_path = os.path.join("hashes", hash_file)
    wordlist_path = os.path.join("wordlists", wordlist)
    
    if not os.path.exists(hash_file_path):
        raise HTTPException(status_code=404, detail="Hash file not found")
    if not os.path.exists(wordlist_path):
        raise HTTPException(status_code=404, detail="Wordlist not found")
    
    result = job_runner.start_job(
        hash_mode, attack_mode, hash_file_path, wordlist_path, 
        options, auto_delete_hash, queue_if_busy
    )
    return result

@app.get("/api/jobs")
async def list_jobs(username: str = Depends(get_current_username)):
    """List all jobs with status"""
    return {"jobs": job_runner.list_jobs()}

@app.get("/api/jobs/status")
async def get_jobs_status(username: str = Depends(get_current_username)):
    """Get the overall status of jobs - if any are running"""
    return {
        "has_running_jobs": job_runner.has_running_jobs(),
        "total_jobs": len(job_runner.jobs),
        "running_jobs": sum(1 for job in job_runner.list_jobs() if job["status"] in ["running", "starting"]),
        "queued_jobs": sum(1 for job in job_runner.list_jobs() if job["status"] == "queued")
    }

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
    # First check if the job exists
    job = job_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    output_path = os.path.join("outputs", f"hashcat_{job_id}.txt")
    if not os.path.exists(output_path):
        # If the output file doesn't exist, create a simple one with job info
        try:
            with open(output_path, "w") as f:
                f.write("HASHCAT COMMAND:\n\n")
                f.write(f"Job ID: {job_id}\n")
                f.write(f"Status: {job.get('status', 'Unknown')}\n")
                f.write(f"Started: {job.get('started_at', 'Unknown')}\n")
                f.write(f"Completed: {job.get('completed_at', 'Not completed')}\n\n")
                f.write("No output available for this job.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating output file: {str(e)}")
    
    # For completed jobs with existing output, ensure we get any potential
    # last bit of output that might have been missed
    if job.get("status", "").startswith("completed") and os.path.exists(output_path):
        # Before returning the file, check if it's a completed job and refresh its output
        # This ensures we've captured all final output
        job_runner.refresh_job_output(job_id)
    
    return FileResponse(output_path, media_type="text/plain", filename=f"hashcat_{job_id}.txt")
    
@app.post("/api/jobs/{job_id}/refresh")
async def refresh_job(job_id: str, username: str = Depends(get_current_username)):
    """Force refresh of job output and status"""
    job = job_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Before refreshing, ensure any output file exists
    output_path = os.path.join("outputs", f"hashcat_{job_id}.txt")
    if not os.path.exists(output_path):
        # If the output file doesn't exist, create an empty one
        try:
            with open(output_path, "w") as f:
                f.write("HASHCAT COMMAND:\n\nInitializing...\n")
        except Exception as e:
            print(f"Error creating output file: {str(e)}")
            # Continue anyway, the refresh may still work
    
    success = job_runner.refresh_job_output(job_id)
    
    # Get the updated job information
    updated_job = job_runner.get_job(job_id)
    
    # Check if the job is actually complete but not marked as such
    if updated_job and not updated_job.get('status').startswith('completed'):
        # Make sure the job is still running
        is_job_running = job_runner.is_job_running(job_id)
        output_path = os.path.join("outputs", f"hashcat_{job_id}.txt")
        
        # Only process if the output file exists
        if os.path.exists(output_path):
            try:
                with open(output_path, "r") as f:
                    content = f.read().lower()
                    
                    # Check hashcat status lines
                    status_found = False
                    
                    # First, look for explicit status messages from hashcat
                    for line in content.split("\n"):
                        line_lower = line.lower().strip()
                        if line_lower.startswith("status") and ":" in line_lower:
                            if "cracked" in line_lower:
                                # If hashcat explicitly reports "Cracked", mark as success
                                job_runner.update_job_status(job_id, "completed_success")
                                updated_job = job_runner.get_job(job_id)
                                status_found = True
                                break
                            elif "exhausted" in line_lower:
                                # If hashcat explicitly reports "Exhausted", mark as exhausted
                                job_runner.update_job_status(job_id, "completed_exhausted")
                                updated_job = job_runner.get_job(job_id)
                                status_found = True
                                break
                    
                    # If we didn't find an explicit status line, use backup methods
                    if not status_found:
                        # Check if the job is explicitly exhausted
                        if "exhausted" in content or "keyspace exhausted" in content or "approaching final keyspace" in content:
                            if not is_job_running:
                                # If job is not running and has exhaustion marker, mark as exhausted
                                job_runner.update_job_status(job_id, "completed_exhausted")
                                # Get the updated job info again
                                updated_job = job_runner.get_job(job_id)
                        
                        # Check for 100% progress as an additional completion indicator
                        elif not is_job_running:
                            progress_complete = False
                            for line in content.split("\n"):
                                line_lower = line.lower().strip()
                                if line_lower.startswith("progress") and "100.00%" in line_lower:
                                    progress_complete = True
                                    break
                            
                            if progress_complete:
                                # If job shows 100% progress and is not running, mark as completed
                                if "recovered.....: 0/" not in content.lower():  # Some hashes recovered
                                    job_runner.update_job_status(job_id, "completed_success")
                                else:  # No hashes recovered - exhausted
                                    job_runner.update_job_status(job_id, "completed_exhausted")
                                # Get the updated job info again
                                updated_job = job_runner.get_job(job_id)
                    
                    # Check for cracked hashes
                    elif any(marker in content for marker in ["all hashes have been recovered", "all hashes found"]):
                        if not is_job_running:
                            # If job is not running and all hashes found, mark as success
                            job_runner.update_job_status(job_id, "completed_success")
                            # Get the updated job info again
                            updated_job = job_runner.get_job(job_id)
                    
                    # Check for 100% progress indicator (usually means job is complete)
                    elif not status_found:
                        for line in content.split("\n"):
                            line_lower = line.lower().strip()
                            # Look for progress: 100% lines
                            if line_lower.startswith("progress") and "100.00%" in line_lower:
                                # If we see 100% progress but hashcat is not running anymore
                                if not is_job_running:
                                    # Check if we see recovered lines that indicate success
                                    if "recovered.....: 0/" not in content.lower():  # Some hashes recovered
                                        job_runner.update_job_status(job_id, "completed_success")
                                    else:  # No hashes recovered - exhausted
                                        job_runner.update_job_status(job_id, "completed_exhausted")
                                    # Get the updated job info again
                                    updated_job = job_runner.get_job(job_id)
                                    status_found = True
                                    break
                    
                    # Check for other completion markers, but only if the job is not running anymore
                    elif not status_found and not is_job_running and any(marker in content for marker in [
                        "session completed", 
                        "session stopped", 
                        "finished",
                        "hashcat stopped!",
                        "[Job Complete]",  # Our custom completion marker
                        "Waiting 10 seconds to capture final status"  # Our custom delay message
                    ]):
                        # Update job status to completed
                        job_runner.update_job_status(job_id, "completed")
                        # Get the updated job info again
                        updated_job = job_runner.get_job(job_id)
            except Exception as e:
                print(f"Error reading output file during refresh: {str(e)}")
    
    if success or updated_job:
        return {
            "status": "refreshed", 
            "job_id": job_id,
            "job": updated_job
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to refresh job output")
    
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
