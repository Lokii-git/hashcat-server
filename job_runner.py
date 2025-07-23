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
        for dir_name in ["uploads", "hashes", "wordlists", "outputs", "potfiles"]:
            dir_path = os.path.join(self.base_dir, dir_name)
            try:
                os.makedirs(dir_path, exist_ok=True)
            except PermissionError:
                print(f"WARNING: Permission denied creating directory: {dir_path}")
                print(f"The application may not function correctly without write permissions.")
        
        # Use current user's home directory for hashcat cache
        try:
            # Get current user's home directory
            home_dir = os.path.expanduser('~')
            hashcat_cache_dir = os.path.join(home_dir, '.cache', 'hashcat')
            
            if not os.path.exists(hashcat_cache_dir):
                try:
                    os.makedirs(hashcat_cache_dir, exist_ok=True)
                    print(f"Created hashcat cache directory: {hashcat_cache_dir}")
                except PermissionError:
                    print(f"WARNING: Permission denied creating directory: {hashcat_cache_dir}")
                    print(f"Dictionary cache may not work correctly. Consider running with appropriate permissions.")
                except Exception as e:
                    print(f"Error creating hashcat cache directory: {str(e)}")
        except Exception as e:
            print(f"Error setting up hashcat cache directories: {str(e)}")
            print("Dictionary cache may not work correctly.")
    
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
    
    def has_running_jobs(self) -> bool:
        """Check if there are any running jobs"""
        for job in self.jobs.values():
            if job["status"] == "starting" or job["status"] == "running":
                return True
        return False
        
    def start_job(self, hash_mode: str, attack_mode: str, hash_file: str, wordlist: str, 
                  options: str = "", auto_delete_hash: bool = False, queue_if_busy: bool = False) -> Dict[str, Any]:
        """Start a new hashcat job or queue it if requested and another job is running"""
        job_id = str(uuid.uuid4())
        
        # Ensure we're using absolute paths
        output_dir = os.path.join(self.base_dir, "outputs")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"hashcat_{job_id}.txt")
        
        # Store the full paths in variables for the run_job function
        hash_file_abs = os.path.abspath(hash_file)
        wordlist_abs = os.path.abspath(wordlist)
        
        # Check if any jobs are currently running
        jobs_running = self.has_running_jobs()
        
        # Create job record
        job = {
            "id": job_id,
            "status": "queued" if (jobs_running and queue_if_busy) else "starting",
            "hash_file": os.path.basename(hash_file),
            "hash_file_path": hash_file_abs,  # Store full path for easier reference
            "wordlist": os.path.basename(wordlist),
            "wordlist_path": wordlist_abs,    # Store full path for easier reference
            "hash_mode": hash_mode,
            "attack_mode": attack_mode,
            "options": options,
            "output_file": output_file,
            "started_at": datetime.now().isoformat() if not (jobs_running and queue_if_busy) else None,
            "queued_at": datetime.now().isoformat() if (jobs_running and queue_if_busy) else None,
            "completed_at": None,
            "cracked_count": 0,
            "total_hashes": 0,
            "auto_delete_hash": auto_delete_hash
        }
        
        # Add job to record
        self.jobs[job_id] = job
        self._save_jobs()
        
        # If we're not queueing or no jobs are running, start immediately
        if not jobs_running or not queue_if_busy:
            # Start job in a separate thread
            threading.Thread(
                target=self._run_job,
                args=(job_id, hash_mode, attack_mode, hash_file, wordlist, options, output_file),
                daemon=True
            ).start()
            return {"job_id": job_id, "status": "started"}
        else:
            # Job is queued for later execution
            return {"job_id": job_id, "status": "queued"}
            
    def _check_queue(self) -> None:
        """Check if there are any queued jobs that can be started"""
        # If there are any running jobs, don't start new ones
        if self.has_running_jobs():
            return
            
        # Find the oldest queued job
        queued_jobs = [job for job in self.jobs.values() if job["status"] == "queued"]
        if not queued_jobs:
            return
            
        # Sort by queued_at time
        queued_jobs.sort(key=lambda j: j.get("queued_at") or "")
        next_job = queued_jobs[0]
        
        # Update job status
        job_id = next_job["id"]
        hash_mode = next_job["hash_mode"]
        attack_mode = next_job["attack_mode"]
        hash_file = next_job["hash_file_path"]
        wordlist = next_job["wordlist_path"]
        options = next_job["options"]
        output_file = next_job["output_file"]
        
        # Update job status
        self.jobs[job_id]["status"] = "starting"
        self.jobs[job_id]["started_at"] = datetime.now().isoformat()
        self._save_jobs()
        
        # Start job in a separate thread
        threading.Thread(
            target=self._run_job,
            args=(job_id, hash_mode, attack_mode, hash_file, wordlist, options, output_file),
            daemon=True
        ).start()
    
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
        # Use potfile for better cache efficiency and configure status output
        potfile_dir = os.path.join(self.base_dir, "potfiles")
        potfile_path = os.path.join(potfile_dir, "hashcat.pot")
        
        # Ensure potfile directory exists and has proper permissions
        try:
            os.makedirs(potfile_dir, exist_ok=True)
            # Create empty potfile if it doesn't exist
            if not os.path.exists(potfile_path):
                with open(potfile_path, 'a'):  # 'a' mode creates file if it doesn't exist
                    pass
            # Make sure file is readable and writable
            os.chmod(potfile_path, 0o666)  # rw-rw-rw- permission
        except Exception as e:
            print(f"Warning: Could not prepare potfile: {str(e)}")
            # Fall back to potfile-disable if we can't manage the potfile
            hashcat_options = f"-m {hash_mode} -a {attack_mode} --status --status-timer=1 --potfile-disable"
        else:
            hashcat_options = f"-m {hash_mode} -a {attack_mode} --status --status-timer=1 --potfile-path=\"{potfile_path}\""
        
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
            
            # Get current user's home directory for cache
            home_dir = os.path.expanduser('~')
            cache_dir = os.path.join(home_dir, '.cache')
            env_vars = f"env XDG_CACHE_HOME={cache_dir}"
            
            # Choose execution method based on availability
            if tmux_available:
                # Use tmux if available
                cmd = f"tmux new-session -d -s {session_name} '{env_vars} {hashcat_cmd}'"
                print(f"Using tmux for background execution: {cmd}")
            elif screen_available:
                # Use screen as fallback
                cmd = f"screen -dm -S {session_name} bash -c '{env_vars} {hashcat_cmd}'"
                print(f"Using screen for background execution: {cmd}")
            else:
                # Last resort: use background execution with nohup
                cmd = f"nohup {env_vars} {hashcat_cmd} > {output_file_abs}.log 2>&1 &"
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
                # For Linux/Mac, execute the command (tmux, screen, or nohup) but DON'T wait for completion
                try:
                    print(f"Executing command: {cmd}")
                    process = subprocess.run(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    exit_code = process.returncode
                    
                    # Capture any immediate output
                    cmd_output = f"STDOUT: {process.stdout}\n\nSTDERR: {process.stderr}"
                    print(f"Command execution result: code={exit_code}, output_length={len(cmd_output)}")
                    
                    # Wait for hashcat to start
                    time.sleep(3)
                    
                    # Store session information in job data for later monitoring
                    self._update_job_status(job_id, "running", 
                                           session_name=session_name,
                                           session_type="tmux" if (tmux_available and "tmux" in cmd) else 
                                                        "screen" if (screen_available and "screen" in cmd) else "nohup",
                                           pid_file=f"{output_file}.pid")
                    
                    # Create initial output content to show job is running in background
                    initial_content = [
                        "HASHCAT COMMAND:",
                        cmd,
                        "",
                        "JOB STARTED IN BACKGROUND MODE",
                        f"Job ID: {job_id}",
                        "Status: Running",
                        "",
                        "Initial output:",
                    ]
                    
                    # Try different methods to capture initial output based on what method was used
                    if tmux_available and "tmux" in cmd:
                        try:
                            # Try to capture initial output from tmux session
                            print(f"Attempting to capture output from tmux session: {session_name}")
                            tmux_output = subprocess.run(
                                ["tmux", "capture-pane", "-p", "-t", session_name],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                            )
                            if tmux_output.returncode == 0 and tmux_output.stdout:
                                initial_content.append(tmux_output.stdout)
                                
                                # Save PID for monitoring if we can find it
                                try:
                                    pid_cmd = f"tmux list-panes -a -F '#{{pane_pid}} #{{session_name}}' | grep {session_name} | awk '{{print $1}}'"
                                    pid_result = subprocess.run(pid_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                                    if pid_result.stdout.strip():
                                        with open(f"{output_file}.pid", "w") as pid_file:
                                            pid_file.write(pid_result.stdout.strip())
                                except:
                                    pass
                            else:
                                initial_content.append(f"Tmux session started but output capture failed.\n{cmd_output}")
                        except Exception as e:
                            print(f"Error capturing tmux output: {str(e)}")
                            initial_content.append(f"Error capturing tmux output: {str(e)}\n{cmd_output}")
                    elif screen_available and "screen" in cmd:
                        initial_content.append(f"Screen session started with ID: {session_name}.\n{cmd_output}")
                        try:
                            # Try to get PID of screen session
                            pid_cmd = f"screen -ls | grep {session_name} | awk '{{print $1}}' | cut -d. -f1"
                            pid_result = subprocess.run(pid_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            if pid_result.stdout.strip():
                                with open(f"{output_file}.pid", "w") as pid_file:
                                    pid_file.write(pid_result.stdout.strip())
                        except:
                            pass
                    else:
                        # For nohup, check if the log file exists
                        log_file = f"{output_file}.log"
                        if os.path.exists(log_file):
                            try:
                                with open(log_file, "r") as f:
                                    log_content = f.read()
                                initial_content.append(f"Background process started. Current log:\n{log_content}")
                            except Exception as e:
                                initial_content.append(f"Background process started but couldn't read log: {str(e)}\n{cmd_output}")
                        else:
                            initial_content.append(f"Background process started. No log file available yet.\n{cmd_output}")
                            
                        # Try to find PID for background process
                        try:
                            pid_cmd = f"pgrep -f 'hashcat.*{job_id}'"
                            pid_result = subprocess.run(pid_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            if pid_result.stdout.strip():
                                with open(f"{output_file}.pid", "w") as pid_file:
                                    pid_file.write(pid_result.stdout.strip())
                        except:
                            pass
                    
                    # Join initial content into a string
                    existing_content = "\n".join(initial_content)
                    
                except Exception as e:
                    print(f"Error executing command: {str(e)}")
                    exit_code = 1
                    existing_content = f"Error executing command: {str(e)}"
                    
                # Since this is a background job on Linux, we're returning immediately
                # and will update the job status through a monitoring mechanism
                # DON'T mark the job as complete here
                
                # Record the command that was run
                with open(output_file, "w") as f:
                    f.write("HASHCAT COMMAND:\n")
                    f.write(f"{cmd}\n\n")
                    f.write("OUTPUT:\n")
                    f.write(existing_content)
            
            # For Windows, we can process the output now since the job is completed
            # For Linux, we only create an initial output file, the actual completion will be handled by monitoring
            if is_windows:
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
            else:
                # For Linux, we just create the initial output file and register a background monitor
                # The job status will be updated asynchronously by the monitor_linux_job method
                
                # Write initial output to file
                with open(output_file, "w") as f:
                    f.write(existing_content)
                
                # Start the monitoring thread for this job
                threading.Thread(
                    target=self._monitor_linux_job,
                    args=(job_id, output_file),
                    daemon=True
                ).start()
            
            # For Windows jobs, handle auto-delete here
            # For Linux jobs, this is handled in the _process_job_completion method
            if is_windows and self.jobs[job_id].get("auto_delete_hash", False) and hash_file and os.path.exists(hash_file):
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
    
    def _monitor_linux_job(self, job_id: str, output_file: str):
        """
        Monitor a running hashcat job on Linux systems.
        This method runs in a separate thread and periodically checks the job status,
        updates the output file with the latest information, and updates job status.
        """
        if job_id not in self.jobs:
            return
        
        job = self.jobs[job_id]
        session_name = job.get("session_name")
        session_type = job.get("session_type", "unknown")
        pid_file = job.get("pid_file")
        
        # Get the PID if available
        pid = None
        if pid_file and os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = f.read().strip()
            except:
                pass
        
        # Initialize monitoring variables
        check_interval = 5  # seconds between checks
        max_idle_time = 90  # seconds with no output change before checking if process ended
        final_check_delay = 10  # seconds to wait after detecting near completion before final check
        last_output_size = -1
        last_output_change = time.time()
        start_time = time.time()
        last_output_content = ""
        near_completion = False
        near_completion_time = None
        highest_progress = 0.0
        
        print(f"Starting monitoring for job {job_id} ({session_type})")
        
        try:
            # Main monitoring loop
            while True:
                # Check if job has been marked as completed by another process
                if job_id in self.jobs:
                    current_status = self.jobs[job_id]["status"]
                    if current_status not in ["starting", "running"]:
                        print(f"Job {job_id} already marked as {current_status}, stopping monitor")
                        break
                else:
                    print(f"Job {job_id} no longer exists, stopping monitor")
                    break
                
                # Check if output file exists
                current_output = ""
                if os.path.exists(output_file):
                    try:
                        with open(output_file, "r") as f:
                            current_output = f.read()
                    except Exception as e:
                        print(f"Error reading output file: {str(e)}")
                
                # Get latest output based on session type
                latest_output = []
                
                if session_type == "tmux" and session_name:
                    # Get output from tmux session
                    try:
                        tmux_output = subprocess.run(
                            ["tmux", "capture-pane", "-p", "-t", session_name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                        )
                        if tmux_output.returncode == 0 and tmux_output.stdout:
                            latest_output = tmux_output.stdout.splitlines()
                    except Exception as e:
                        print(f"Error capturing tmux output: {str(e)}")
                
                elif session_type == "screen" and session_name:
                    # Try to get screen session output (more limited)
                    try:
                        # screen -S session_name -X hardcopy /tmp/screen_output
                        screen_file = f"/tmp/screen_{job_id}.txt"
                        subprocess.run(
                            ["screen", "-S", session_name, "-X", "hardcopy", screen_file],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                        )
                        if os.path.exists(screen_file):
                            with open(screen_file, "r") as f:
                                latest_output = f.read().splitlines()
                            # Clean up temp file
                            os.remove(screen_file)
                    except Exception as e:
                        print(f"Error capturing screen output: {str(e)}")
                
                elif session_type == "nohup":
                    # For nohup, check the log file
                    log_file = f"{output_file}.log"
                    if os.path.exists(log_file):
                        try:
                            with open(log_file, "r") as f:
                                latest_output = f.read().splitlines()
                        except Exception as e:
                            print(f"Error reading nohup log: {str(e)}")
                
                # Check if process is still running
                process_running = False
                
                if pid:
                    # Check by PID
                    try:
                        os.kill(int(pid), 0)  # Does not kill the process, just checks if it exists
                        process_running = True
                    except (ProcessLookupError, PermissionError, ValueError):
                        process_running = False
                elif session_name:
                    # Check by session name
                    if session_type == "tmux":
                        try:
                            tmux_check = subprocess.run(
                                ["tmux", "has-session", "-t", session_name],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                            )
                            process_running = tmux_check.returncode == 0
                        except:
                            process_running = False
                    elif session_type == "screen":
                        try:
                            screen_check = subprocess.run(
                                ["screen", "-list", session_name],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                            )
                            process_running = session_name in screen_check.stdout
                        except:
                            process_running = False
                else:
                    # Last resort: check by pattern in process list
                    try:
                        ps_check = subprocess.run(
                            ["pgrep", "-f", f"hashcat.*{job_id}"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                        )
                        process_running = ps_check.returncode == 0
                    except:
                        process_running = False
                
                # Update output file if we have new data
                if latest_output:
                    # Keep the original command and initial info
                    if current_output:
                        # Extract the command part from existing output
                        cmd_part = ""
                        for line in current_output.splitlines():
                            cmd_part += line + "\n"
                            if line == "":  # Find the first empty line after "HASHCAT COMMAND:"
                                break
                            
                        # Build new output with command part and latest output
                        new_output = cmd_part + "\n".join(latest_output)
                        
                        # Write updated output
                        if new_output != last_output_content:
                            with open(output_file, "w") as f:
                                f.write(new_output)
                            last_output_content = new_output
                            last_output_change = time.time()
                            last_output_size = len(new_output)
                
                # Check for completion conditions
                if not process_running:
                    # Double check that the process is really not running
                    # Sometimes there can be temporary glitches in process detection
                    time.sleep(1)  # Wait a moment before second check
                    
                    # Try all three methods to detect the process
                    second_check = False
                    
                    # Check by PID again
                    if pid:
                        try:
                            os.kill(int(pid), 0)
                            second_check = True  # Process exists
                        except:
                            pass
                            
                    # Check by session name again
                    if not second_check and session_name:
                        if session_type == "tmux":
                            try:
                                tmux_check = subprocess.run(
                                    ["tmux", "has-session", "-t", session_name],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                                )
                                second_check = tmux_check.returncode == 0
                            except:
                                pass
                                
                    # Last resort check by pattern again
                    if not second_check:
                        try:
                            ps_check = subprocess.run(
                                ["pgrep", "-f", f"hashcat.*{job_id}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                            )
                            second_check = ps_check.returncode == 0
                        except:
                            pass
                    
                    if not second_check:
                        # Process is definitely not running, mark job as completed
                        print(f"Process for job {job_id} is confirmed not running, marking as completed")
                        self._process_job_completion(job_id, output_file)
                        break
                    else:
                        print(f"Process for job {job_id} was detected on second check, continuing monitoring")
                
                # Check for job progress indicators in output
                if latest_output:
                    # Parse the output for progress information
                    cracked_count = 0
                    total_hashes = 0
                    progress_info = ""
                    exhaust_check = False
                    current_progress = 0.0
                    
                    for line in latest_output:
                        # Look for recovered hash information
                        if "Recovered" in line:
                            progress_info = line.strip()
                            parts = line.split()
                            if len(parts) >= 3:
                                try:
                                    cracked = parts[1].split("/")[0]
                                    total = parts[1].split("/")[1]
                                    cracked_count = int(cracked)
                                    total_hashes = int(total)
                                    
                                    # Update job with progress information
                                    self._update_job_status(
                                        job_id,
                                        "running",
                                        cracked_count=cracked_count,
                                        total_hashes=total_hashes,
                                        progress_info=progress_info
                                    )
                                except (IndexError, ValueError):
                                    pass
                        
                        # Check for progress percentage
                        if "Progress" in line:
                            try:
                                # Extract percentage like "1234567/7654321 (45.67%)"
                                progress_match = line.split("(")[1].split(")")[0].replace("%", "")
                                current_progress = float(progress_match)
                                
                                # Skip updating progress if this is just the dictionary cache building
                                # Dictionary cache usually shows as bytes (X.XX%)
                                if "Dictionary cache building" in line or "bytes" in line:
                                    print(f"Detected dictionary cache building for job {job_id}, not updating progress")
                                else:
                                    if current_progress > highest_progress:
                                        highest_progress = current_progress
                                        
                                    # Detect near completion to capture final output
                                    if current_progress >= 99.9 and not near_completion:
                                        print(f"Job {job_id} is at {current_progress}% - preparing for final capture")
                                        near_completion = True
                                        near_completion_time = time.time()
                            except (IndexError, ValueError) as e:
                                print(f"Error parsing progress: {str(e)}")
                        
                        # Check for exhausted wordlist
                        if "Exhausted" in line or "Approaching final keyspace" in line:
                            exhaust_check = True
                            # Only consider as completion when progress is high
                            if highest_progress > 99.0:
                                # Force final output capture, but wait a few seconds to capture any last output
                                print(f"Detected exhausted keyspace for job {job_id}")
                                time.sleep(3)  # Wait a bit to capture any final output
                                self._process_job_completion(job_id, output_file)
                                break
                        
                        # Check for finished indicators
                        if "Stopped" in line or "Quit" in line or "Finished" in line or "All hashes" in line:
                            print(f"Detected completion message in output for job {job_id}")
                            time.sleep(3)  # Wait a bit to capture any final output
                            self._process_job_completion(job_id, output_file)
                            break
                        
                        # Check for cracked hash indicators - common pattern for cracked hash output
                        if ":" in line and (line.strip().count(":") >= 3) and not line.startswith("#"):
                            print(f"Detected potential cracked hash for job {job_id}")
                            # Give it a little more time to finish output
                            time.sleep(2)
                            self._process_job_completion(job_id, output_file)
                            break
                
                # Check if we've had no output changes for a while and process isn't running
                if last_output_size > 0 and (time.time() - last_output_change) > max_idle_time:
                    # Double check if process is running
                    if not process_running:
                        print(f"No output changes for {max_idle_time}s and process not running, marking job {job_id} as completed")
                        self._process_job_completion(job_id, output_file)
                        break
                
                # If near completion, wait for the final output
                if near_completion and (time.time() - near_completion_time) > final_check_delay:
                    print(f"Job {job_id} is at {highest_progress}% and {time.time() - near_completion_time:.1f}s has passed since near completion")
                    print(f"Capturing final output for job {job_id}")
                    time.sleep(1)  # Give a bit more time for final output
                    self._process_job_completion(job_id, output_file)
                    break
                
                # Sleep before next check
                time.sleep(check_interval)
                
        except Exception as e:
            print(f"Error in job monitor for {job_id}: {str(e)}")
            # Mark job as failed if there was an error in monitoring
            if job_id in self.jobs and self.jobs[job_id]["status"] in ["starting", "running"]:
                self._update_job_status(
                    job_id,
                    "error",
                    error_message=f"Error monitoring job: {str(e)}",
                    completed_at=datetime.now().isoformat()
                )
    
    def _process_job_completion(self, job_id: str, output_file: str):
        """Process job completion based on output file contents"""
        if not os.path.exists(output_file) or job_id not in self.jobs:
            return
        
        try:
            # Wait a moment for any final output to be written
            time.sleep(2)
            
            with open(output_file, "r") as f:
                content = f.read()
            
            # Parse output to determine completion status
            cracked_count = 0
            total_hashes = 0
            exhaust_check = False
            cracked_found = False
            status = "completed"
            
            # First, look for specific Status line from hashcat
            status_cracked = False
            status_exhausted = False
            
            # Check for explicit status messages from hashcat
            for line in content.split("\n"):
                line_lower = line.lower().strip()
                if line_lower.startswith("status"):
                    if "cracked" in line_lower:
                        status_cracked = True
                        cracked_found = True
                        break
                    elif "exhausted" in line_lower:
                        status_exhausted = True
                        exhaust_check = True
                        break
            
            # Backup check if we didn't find explicit status lines
            if not status_cracked and not status_exhausted:
                # Check if the wordlist was exhausted - use more specific detection
                exhaust_phrases = [
                    "exhausted", 
                    "keyspace exhausted", 
                    "approaching final keyspace", 
                    "dictionary exhausted",
                    "dictionaries exhausted"
                ]
                for phrase in exhaust_phrases:
                    if phrase in content.lower():
                        exhaust_check = True
                        break
            
            # Check for actual cracked hashes in the output (they typically contain ":" character)
            if not status_cracked:  # Only do this if we didn't already find "Status: Cracked"
                for line in content.split("\n"):
                    # More strict checking for cracked hashes
                    # Lines with cracked passwords typically look like "hash:password"
                    # We'll check for lines with at least one colon that aren't comments or headers
                    if (":" in line and 
                        not line.startswith("#") and 
                        not line.startswith("Session") and 
                        not line.startswith("Status") and
                        not line.startswith("Recovered") and
                        not "Progress" in line and
                        not "Time" in line and
                        not "Speed" in line):
                            
                        # Additional check to avoid counting system messages
                        if line.strip().count(":") >= 1 and len(line.strip()) > 10:
                            cracked_found = True
                            cracked_count += 1
            
            # Parse recovered hashes info from status lines
            for line in content.split("\n"):
                if "Recovered" in line and ":" in line:  # Make sure it's the right format
                    parts = line.split(":")
                    if len(parts) >= 2:
                        value_part = parts[1].strip()
                        if "/" in value_part:
                            try:
                                fraction_part = value_part.split()[0]  # Get the first part which should be like "1/1"
                                cracked = fraction_part.split("/")[0]
                                total = fraction_part.split("/")[1]
                                parsed_cracked = int(cracked)
                                total_hashes = int(total)
                                
                                # Only update if we haven't found actual cracked hashes
                                # or if the parsed count is higher
                                if not cracked_found or parsed_cracked > cracked_count:
                                    cracked_count = parsed_cracked
                                    cracked_found = True
                                    
                                # If all hashes are cracked, set status_cracked
                                if parsed_cracked == total_hashes and total_hashes > 0:
                                    status_cracked = True
                            except (IndexError, ValueError):
                                pass
            
            # Set status based on cracking results
            if status_cracked or (cracked_count > 0 and cracked_count == total_hashes and total_hashes > 0):
                status = "completed_success"
            elif exhaust_check:
                status = "completed_exhausted"
            elif "error" in content.lower() or "failed" in content.lower():
                status = "failed"
            else:
                status = "completed"
            
            # Update job with results
            self._update_job_status(
                job_id, 
                status,
                completed_at=datetime.now().isoformat(),
                cracked_count=cracked_count,
                total_hashes=total_hashes
            )
            
            # Auto-delete hash file if enabled
            job = self.jobs[job_id]
            if job.get("auto_delete_hash", False):
                hash_file = job.get("hash_file_path", "")
                if hash_file and os.path.exists(hash_file):
                    try:
                        os.remove(hash_file)
                        print(f"Auto-deleted hash file: {hash_file}")
                        self._update_job_status(job_id, status, hash_file_deleted=True)
                    except Exception as e:
                        print(f"Failed to auto-delete hash file: {str(e)}")
                        
            # Check if there are any queued jobs that can now be started
            threading.Thread(target=self._check_queue, daemon=True).start()
                        
        except Exception as e:
            print(f"Error processing job completion for {job_id}: {str(e)}")
            # Mark as error if we can't process the completion
            self._update_job_status(
                job_id,
                "error",
                error_message=f"Error processing job completion: {str(e)}",
                completed_at=datetime.now().isoformat()
            )
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID"""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs"""
        return list(self.jobs.values())
    
    def update_job_status(self, job_id: str, status: str) -> bool:
        """Update the status of a job"""
        if job_id not in self.jobs:
            return False
            
        job = self.jobs[job_id]
        
        # Update status
        job["status"] = status
        
        # If status starts with 'completed' and no completed_at time, set it
        if status.startswith("completed") and not job.get("completed_at"):
            job["completed_at"] = datetime.datetime.now().isoformat()
            
        # Save jobs
        self._save_jobs()
        return True
    
    def is_job_running(self, job_id: str) -> bool:
        """Check if a job is still running"""
        if job_id not in self.jobs:
            return False
            
        job = self.jobs[job_id]
        session_name = job.get("session_name")
        session_type = job.get("session_type", "unknown")
        
        # If job status is already completed, return False
        if job.get("status", "").startswith("completed") or job.get("status") == "failed" or job.get("status") == "error":
            return False
        
        # Check using various methods
        process_running = False
        
        if session_name:
            if session_type == "tmux":
                try:
                    tmux_check = subprocess.run(
                        ["tmux", "has-session", "-t", session_name],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                    )
                    process_running = tmux_check.returncode == 0
                except Exception:
                    process_running = False
            elif session_type == "screen":
                try:
                    screen_check = subprocess.run(
                        ["screen", "-list", session_name],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                    )
                    process_running = session_name in screen_check.stdout
                except Exception:
                    process_running = False
        
        # Last resort check by pattern
        if not process_running:
            try:
                ps_check = subprocess.run(
                    ["pgrep", "-f", f"hashcat.*{job_id}"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                )
                process_running = ps_check.returncode == 0
            except Exception:
                process_running = False
        
        return process_running
    
    def refresh_job_output(self, job_id: str) -> bool:
        """Force refresh of job output and status check"""
        if job_id not in self.jobs:
            return False
            
        job = self.jobs[job_id]
        output_file = job.get("output_file")
        session_name = job.get("session_name")
        session_type = job.get("session_type", "unknown")
        
        # First, check if the job is still running
        process_running = False
        
        # Check using various methods
        if session_name:
            if session_type == "tmux":
                try:
                    tmux_check = subprocess.run(
                        ["tmux", "has-session", "-t", session_name],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                    )
                    process_running = tmux_check.returncode == 0
                except Exception:
                    process_running = False
            elif session_type == "screen":
                try:
                    screen_check = subprocess.run(
                        ["screen", "-list", session_name],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                    )
                    process_running = session_name in screen_check.stdout
                except Exception:
                    process_running = False
                    
        # Last resort check by pattern
        if not process_running:
            try:
                ps_check = subprocess.run(
                    ["pgrep", "-f", f"hashcat.*{job_id}"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                )
                process_running = ps_check.returncode == 0
            except Exception:
                process_running = False
                
        # If job is still running and we're in tmux or screen, fetch latest output
        if process_running and session_name and (session_type == "tmux" or session_type == "screen"):
            try:
                latest_output = []
                
                if session_type == "tmux":
                    tmux_output = subprocess.run(
                        ["tmux", "capture-pane", "-p", "-t", session_name],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                    )
                    if tmux_output.returncode == 0 and tmux_output.stdout:
                        latest_output = tmux_output.stdout.splitlines()
                elif session_type == "screen":
                    screen_file = f"/tmp/screen_{job_id}.txt"
                    subprocess.run(
                        ["screen", "-S", session_name, "-X", "hardcopy", screen_file],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                    )
                    if os.path.exists(screen_file):
                        with open(screen_file, "r") as f:
                            latest_output = f.read().splitlines()
                        # Clean up temp file
                        os.remove(screen_file)
                
                if latest_output and output_file:
                    # Get the current output content
                    current_output = ""
                    if os.path.exists(output_file):
                        with open(output_file, "r") as f:
                            current_output = f.read()
                            
                    # Extract the command part from existing output
                    cmd_part = ""
                    for line in current_output.splitlines():
                        cmd_part += line + "\n"
                        if line == "":  # Find the first empty line after "HASHCAT COMMAND:"
                            break
                            
                    # Build new output with command part and latest output
                    new_output = cmd_part + "\n".join(latest_output)
                    
                    # Write updated output
                    with open(output_file, "w") as f:
                        f.write(new_output)
            except Exception as e:
                print(f"Error updating output during refresh: {str(e)}")
        
        # For completed jobs, we still want to process the output to ensure status is correct
        # This is important for jobs that were running and have completed
        if output_file and os.path.exists(output_file):
            try:
                # For jobs that are already marked as completed, we'll still
                # process the completion to ensure the status is accurate,
                # but we won't overwrite the completed status
                if job.get("status", "").startswith("completed") or job.get("status") == "failed" or job.get("status") == "error":
                    # Just return True, we don't need to process completion again
                    # but this counts as a successful refresh
                    return True
                
                # Force update of job status and output for non-completed jobs
                self._process_job_completion(job_id, output_file)
                return True
            except Exception as e:
                print(f"Error refreshing job output: {str(e)}")
                return False
        return False
        
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
