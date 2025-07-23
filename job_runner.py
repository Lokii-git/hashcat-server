import os
import json
import uuid
import time
import subprocess
import shlex
import threading
import platform
from typing import List, Dict, Optional, Any
from datetime import datetime

class HashcatJobRunner:
    """
    Class for managing hashcat jobs in a tmux/screen session
    """
    def __init__(self):
        self.jobs_file = "jobs.json"
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._load_jobs()
        
        # Create necessary directories
        os.makedirs("uploads", exist_ok=True)
        os.makedirs("hashes", exist_ok=True)
        os.makedirs("wordlists", exist_ok=True)
        os.makedirs("outputs", exist_ok=True)
    
    def _load_jobs(self):
        """Load jobs from file"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, "r") as f:
                    self.jobs = json.load(f)
            except json.JSONDecodeError:
                self.jobs = {}
        else:
            self.jobs = {}
    
    def _save_jobs(self):
        """Save jobs to file"""
        with open(self.jobs_file, "w") as f:
            json.dump(self.jobs, f, indent=2)
    
    def start_job(self, hash_mode: str, attack_mode: str, hash_file: str, wordlist: str, options: str = "") -> str:
        """Start a new hashcat job"""
        job_id = str(uuid.uuid4())
        output_file = os.path.join("outputs", f"hashcat_{job_id}.txt")
        
        # Create job record
        job = {
            "id": job_id,
            "status": "starting",
            "hash_file": os.path.basename(hash_file),
            "wordlist": os.path.basename(wordlist),
            "hash_mode": hash_mode,
            "attack_mode": attack_mode,
            "options": options,
            "output_file": output_file,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "cracked_count": 0,
            "total_hashes": 0
        }
        
        # Add job to record
        self.jobs[job_id] = job
        self._save_jobs()
        
        # Start job in a separate thread
        threading.Thread(
            target=self._run_job,
            args=(job_id, hash_mode, attack_mode, hash_file, wordlist, options, output_file),
            daemon=True
        ).start()
        
        return job_id
    
    def _run_job(self, job_id: str, hash_mode: str, attack_mode: str, hash_file: str, 
                 wordlist: str, options: str, output_file: str):
        """Run hashcat job in a background process"""
        # Detect platform for terminal command choice
        is_windows = platform.system().lower() == "windows"
        
        # Construct hashcat command
        base_cmd = "hashcat"
        if is_windows:
            # For Windows, use direct command
            cmd = f'{base_cmd} -m {hash_mode} -a {attack_mode} "{hash_file}" "{wordlist}" -o "{output_file}" {options}'
            shell = True
        else:
            # For Linux/Mac, use tmux
            session_name = f"hashcat_{job_id}"
            cmd_args = [
                "tmux", "new-session", "-d", "-s", session_name,
                f'{base_cmd} -m {hash_mode} -a {attack_mode} "{hash_file}" "{wordlist}" -o "{output_file}" {options}'
            ]
            cmd = " ".join(cmd_args)
            shell = True
        
        # Update job status
        self._update_job_status(job_id, "running")
        
        try:
            # Run the command
            if is_windows:
                process = subprocess.Popen(
                    cmd, 
                    shell=shell, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
                # Wait for completion
                stdout, stderr = process.communicate()
                
                # Write output to file
                with open(output_file, "w") as f:
                    f.write(stdout)
                    if stderr:
                        f.write("\n\nERRORS:\n")
                        f.write(stderr)
                
                exit_code = process.returncode
            else:
                # For Linux/Mac, execute the tmux command
                process = subprocess.run(cmd, shell=shell)
                exit_code = process.returncode
            
            # Update job status based on exit code
            if exit_code == 0:
                status = "completed"
            else:
                status = "failed"
                
            # Parse output to get cracked count (basic implementation)
            cracked_count = 0
            total_hashes = 0
            
            if os.path.exists(output_file):
                with open(output_file, "r") as f:
                    content = f.read()
                    # Very simple parsing - would need improvement for real-world use
                    if "Recovered" in content:
                        for line in content.split("\n"):
                            if "Recovered" in line:
                                parts = line.split()
                                if len(parts) >= 3:
                                    try:
                                        cracked = parts[1].split("/")[0]
                                        total = parts[1].split("/")[1]
                                        cracked_count = int(cracked)
                                        total_hashes = int(total)
                                    except (IndexError, ValueError):
                                        pass
            
            # Update job with results
            self._update_job_status(
                job_id, 
                status,
                completed_at=datetime.now().isoformat(),
                cracked_count=cracked_count,
                total_hashes=total_hashes
            )
            
        except Exception as e:
            # Update job status on error
            self._update_job_status(
                job_id, 
                "error",
                error_message=str(e),
                completed_at=datetime.now().isoformat()
            )
    
    def _update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status and additional fields"""
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            for key, value in kwargs.items():
                self.jobs[job_id][key] = value
            self._save_jobs()
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID"""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs"""
        return list(self.jobs.values())
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        if job_id not in self.jobs:
            return False
        
        # Remove output file if exists
        output_file = self.jobs[job_id].get("output_file")
        if output_file and os.path.exists(output_file):
            try:
                os.remove(output_file)
            except:
                pass
        
        # Remove job from records
        del self.jobs[job_id]
        self._save_jobs()
        
        # Try to kill the tmux session if on Linux/Mac
        if platform.system().lower() != "windows":
            session_name = f"hashcat_{job_id}"
            try:
                subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)
            except:
                pass
        
        return True
