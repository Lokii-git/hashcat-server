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
        # Get the directory where the script is located
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.jobs_file = os.path.join(self.base_dir, "jobs.json")
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._load_jobs()
        
        # Create necessary directories with absolute paths
        for dir_name in ["uploads", "hashes", "wordlists", "outputs"]:
            dir_path = os.path.join(self.base_dir, dir_name)
            try:
                os.makedirs(dir_path, exist_ok=True)
            except PermissionError:
                print(f"WARNING: Permission denied creating directory: {dir_path}")
                print(f"The application may not function correctly without write permissions.")
    
    def _load_jobs(self):
        """Load jobs from file"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, "r") as f:
                    self.jobs = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Error parsing jobs file. Using empty jobs list.")
                self.jobs = {}
            except PermissionError:
                print(f"Warning: Permission denied reading jobs file: {self.jobs_file}")
                self.jobs = {}
        else:
            self.jobs = {}
    
    def _save_jobs(self):
        """Save jobs to file"""
        try:
            with open(self.jobs_file, "w") as f:
                json.dump(self.jobs, f, indent=2)
        except PermissionError:
            print(f"Error: Permission denied writing to jobs file: {self.jobs_file}")
            print(f"Job status will not be persisted. Check file permissions.")
    
    def start_job(self, hash_mode: str, attack_mode: str, hash_file: str, wordlist: str, options: str = "", auto_delete_hash: bool = False) -> str:
        """Start a new hashcat job"""
        job_id = str(uuid.uuid4())
        
        # Ensure we're using absolute paths
        output_dir = os.path.join(self.base_dir, "outputs")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"hashcat_{job_id}.txt")
        
        # Store the full paths in variables for the run_job function
        hash_file_abs = os.path.abspath(hash_file)
        wordlist_abs = os.path.abspath(wordlist)
        
        # Create job record
        job = {
            "id": job_id,
            "status": "starting",
            "hash_file": os.path.basename(hash_file),
            "hash_file_path": hash_file_abs,  # Store full path for easier reference
            "wordlist": os.path.basename(wordlist),
            "wordlist_path": wordlist_abs,    # Store full path for easier reference
            "hash_mode": hash_mode,
            "attack_mode": attack_mode,
            "options": options,
            "output_file": output_file,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "cracked_count": 0,
            "total_hashes": 0,
            "auto_delete_hash": auto_delete_hash
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
        
        # Use absolute paths for files
        hash_file_abs = os.path.abspath(hash_file)
        wordlist_abs = os.path.abspath(wordlist)
        output_file_abs = os.path.abspath(output_file)
        
        # Construct hashcat command
        base_cmd = "hashcat"
        # Add status output to ensure we get more info about progress
        hashcat_options = f"-m {hash_mode} -a {attack_mode} --status --status-timer=1 --potfile-disable"
        
        if is_windows:
            # For Windows, use direct command with better output
            cmd = f'{base_cmd} {hashcat_options} "{hash_file_abs}" "{wordlist_abs}" -o "{output_file_abs}" {options}'
            shell = True
        else:
            # For Linux/Mac, try different approaches
            session_name = f"hashcat_{job_id}"
            hashcat_cmd = f'{base_cmd} {hashcat_options} "{hash_file_abs}" "{wordlist_abs}" -o "{output_file_abs}" {options}'
            
            # Try multiple background execution methods in order of preference
            # First check if tmux is available
            tmux_available = False
            screen_available = False
            
            try:
                # Check for tmux
                tmux_check = subprocess.run(["which", "tmux"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                tmux_available = tmux_check.returncode == 0
                
                # Check for screen if tmux is not available
                if not tmux_available:
                    screen_check = subprocess.run(["which", "screen"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    screen_available = screen_check.returncode == 0
            except Exception as e:
                print(f"Error checking for tmux/screen: {str(e)}")
                tmux_available = False
                screen_available = False
            
            # Choose execution method based on availability
            if tmux_available:
                # Use tmux if available
                cmd = f"tmux new-session -d -s {session_name} '{hashcat_cmd}'"
                print(f"Using tmux for background execution: {cmd}")
            elif screen_available:
                # Use screen as fallback
                cmd = f"screen -dm -S {session_name} bash -c '{hashcat_cmd}'"
                print(f"Using screen for background execution: {cmd}")
            else:
                # Last resort: use background execution with nohup
                cmd = f"nohup {hashcat_cmd} > {output_file_abs}.log 2>&1 &"
                print(f"Using nohup for background execution: {cmd}")
            
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
                
                # Write output to file - always keep output regardless of success/failure
                with open(output_file, "w") as f:
                    f.write("HASHCAT COMMAND:\n")
                    f.write(f"{cmd}\n\n")
                    f.write("STANDARD OUTPUT:\n")
                    f.write(stdout)
                    if stderr:
                        f.write("\n\nSTANDARD ERROR:\n")
                        f.write(stderr)
                
                exit_code = process.returncode
            else:
                # For Linux/Mac, execute the command (tmux, screen, or nohup)
                try:
                    print(f"Executing command: {cmd}")
                    process = subprocess.run(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    exit_code = process.returncode
                    
                    # Capture any immediate output
                    cmd_output = f"STDOUT: {process.stdout}\n\nSTDERR: {process.stderr}"
                    print(f"Command execution result: code={exit_code}, output_length={len(cmd_output)}")
                    
                    # Wait for hashcat to start
                    time.sleep(3)
                    
                    # Try different methods to capture output based on what method was used
                    if tmux_available and "tmux" in cmd:
                        try:
                            # Try to capture output from tmux session
                            print(f"Attempting to capture output from tmux session: {session_name}")
                            tmux_output = subprocess.run(
                                ["tmux", "capture-pane", "-p", "-t", session_name],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                            )
                            if tmux_output.returncode == 0 and tmux_output.stdout:
                                existing_content = tmux_output.stdout
                            else:
                                existing_content = f"Tmux session started but output capture failed.\n{cmd_output}"
                        except Exception as e:
                            print(f"Error capturing tmux output: {str(e)}")
                            existing_content = f"Error capturing tmux output: {str(e)}\n{cmd_output}"
                    elif screen_available and "screen" in cmd:
                        existing_content = f"Screen session started with ID: {session_name}.\n{cmd_output}"
                    else:
                        # For nohup, check if the log file exists
                        log_file = f"{output_file}.log"
                        if os.path.exists(log_file):
                            try:
                                with open(log_file, "r") as f:
                                    log_content = f.read()
                                existing_content = f"Background process started. Current log:\n{log_content}"
                            except Exception as e:
                                existing_content = f"Background process started but couldn't read log: {str(e)}\n{cmd_output}"
                        else:
                            existing_content = f"Background process started. No log file available yet.\n{cmd_output}"
                except Exception as e:
                    print(f"Error executing command: {str(e)}")
                    exit_code = 1
                    existing_content = f"Error executing command: {str(e)}"
                
                # Record the command that was run
                with open(output_file, "w") as f:
                    f.write("HASHCAT COMMAND:\n")
                    f.write(f"{cmd}\n\n")
                    f.write("OUTPUT:\n")
                    f.write(existing_content)
            
            # Parse output to get cracked count (improved implementation)
            cracked_count = 0
            total_hashes = 0
            exhaust_check = False
            progress_info = ""
            
            if os.path.exists(output_file):
                with open(output_file, "r") as f:
                    content = f.read()
                    # Check if the wordlist was exhausted
                    if "Exhausted" in content or "Approaching final keyspace" in content:
                        exhaust_check = True
                    
                    # Parse recovered hashes info
                    for line in content.split("\n"):
                        if "Recovered" in line:
                            progress_info = line.strip()
                            parts = line.split()
                            if len(parts) >= 3:
                                try:
                                    cracked = parts[1].split("/")[0]
                                    total = parts[1].split("/")[1]
                                    cracked_count = int(cracked)
                                    total_hashes = int(total)
                                except (IndexError, ValueError):
                                    pass
            
            # Set status based on cracking results and exit code
            if cracked_count > 0:
                status = "completed_success"
            elif exhaust_check:
                status = "completed_exhausted"
            elif exit_code == 0:
                status = "completed"
            else:
                status = "failed"
            
            # Update job with results
            self._update_job_status(
                job_id, 
                status,
                completed_at=datetime.now().isoformat(),
                cracked_count=cracked_count,
                total_hashes=total_hashes
            )
            
            # Auto-delete hash file if enabled
            if self.jobs[job_id].get("auto_delete_hash", False) and hash_file and os.path.exists(hash_file):
                try:
                    os.remove(hash_file)
                    print(f"Auto-deleted hash file: {hash_file}")
                    self._update_job_status(job_id, status, hash_file_deleted=True)
                except Exception as e:
                    print(f"Failed to auto-delete hash file: {str(e)}")
            
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
        
        # Try to kill the background process if on Linux/Mac
        if platform.system().lower() != "windows":
            session_name = f"hashcat_{job_id}"
            
            try:
                # Try multiple methods to kill the process
                print(f"Attempting to terminate job {job_id}")
                
                # Try tmux
                try:
                    tmux_check = subprocess.run(["which", "tmux"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if tmux_check.returncode == 0:
                        print(f"Trying to kill tmux session: {session_name}")
                        subprocess.run(["tmux", "kill-session", "-t", session_name], 
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                except Exception as e:
                    print(f"Error killing tmux session: {str(e)}")
                
                # Try screen
                try:
                    screen_check = subprocess.run(["which", "screen"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if screen_check.returncode == 0:
                        print(f"Trying to kill screen session: {session_name}")
                        subprocess.run(["screen", "-X", "-S", session_name, "quit"], 
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                except Exception as e:
                    print(f"Error killing screen session: {str(e)}")
                
                # Kill by process name/pattern as last resort
                try:
                    print(f"Trying to kill process by pattern: hashcat.*{job_id}")
                    subprocess.run(f"pkill -f 'hashcat.*{job_id}'", shell=True, 
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                except Exception as e:
                    print(f"Error killing process by pattern: {str(e)}")
                    
            except Exception as e:
                print(f"Failed to kill session/process for job {job_id}: {str(e)}")
        
        return True
