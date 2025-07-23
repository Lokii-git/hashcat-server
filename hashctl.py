#!/usr/bin/env python3
import os
import sys
import json
import argparse
import requests
from typing import Dict, Any, Optional, List

class HashcatClient:
    """
    Command-line client for the Hashcat Server API
    """
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.auth = (username, password)
    
    def upload_hashlist(self, file_path: str) -> Dict[str, Any]:
        """Upload a hash file"""
        url = f"{self.base_url}/api/upload/hashlist"
        with open(file_path, "rb") as f:
            files = {"hashlist": (os.path.basename(file_path), f)}
            response = requests.post(url, files=files, auth=self.auth)
            response.raise_for_status()
            return response.json()
    
    def upload_wordlist(self, file_path: str) -> Dict[str, Any]:
        """Upload a wordlist file"""
        url = f"{self.base_url}/api/upload/wordlist"
        with open(file_path, "rb") as f:
            files = {"wordlist": (os.path.basename(file_path), f)}
            response = requests.post(url, files=files, auth=self.auth)
            response.raise_for_status()
            return response.json()
    
    def run_hashcat(self, hash_mode: str, attack_mode: str, hash_file: str, 
                   wordlist: str, options: str = "") -> Dict[str, Any]:
        """Start a hashcat job"""
        url = f"{self.base_url}/api/run/hashcat"
        data = {
            "hash_mode": hash_mode,
            "attack_mode": attack_mode,
            "hash_file": hash_file,
            "wordlist": wordlist,
            "options": options
        }
        response = requests.post(url, data=data, auth=self.auth)
        response.raise_for_status()
        return response.json()
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs"""
        url = f"{self.base_url}/api/jobs"
        response = requests.get(url, auth=self.auth)
        response.raise_for_status()
        return response.json()["jobs"]
    
    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get job details"""
        url = f"{self.base_url}/api/jobs/{job_id}"
        response = requests.get(url, auth=self.auth)
        response.raise_for_status()
        return response.json()["job"]
    
    def get_job_output(self, job_id: str, output_file: Optional[str] = None) -> str:
        """Get job output and optionally save to file"""
        url = f"{self.base_url}/api/jobs/{job_id}/output"
        response = requests.get(url, auth=self.auth)
        response.raise_for_status()
        
        if output_file:
            with open(output_file, "wb") as f:
                f.write(response.content)
            return f"Output saved to {output_file}"
        else:
            return response.text
    
    def delete_job(self, job_id: str) -> Dict[str, Any]:
        """Delete a job"""
        url = f"{self.base_url}/api/jobs/{job_id}"
        response = requests.delete(url, auth=self.auth)
        response.raise_for_status()
        return response.json()


def main():
    """Main CLI entry point"""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Hashcat Server API Client")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--username", default="admin", help="Auth username")
    parser.add_argument("--password", default="password", help="Auth password")
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Upload hashlist command
    upload_hash_parser = subparsers.add_parser("upload-hash", help="Upload a hash file")
    upload_hash_parser.add_argument("file", help="Path to hash file")
    
    # Upload wordlist command
    upload_wordlist_parser = subparsers.add_parser("upload-wordlist", help="Upload a wordlist file")
    upload_wordlist_parser.add_argument("file", help="Path to wordlist file")
    
    # Run hashcat command
    run_parser = subparsers.add_parser("run", help="Run a hashcat job")
    run_parser.add_argument("--hash-mode", "-m", required=True, help="Hash mode")
    run_parser.add_argument("--attack-mode", "-a", required=True, help="Attack mode")
    run_parser.add_argument("--hash-file", required=True, help="Hash file name (already uploaded)")
    run_parser.add_argument("--wordlist", required=True, help="Wordlist file name (already uploaded)")
    run_parser.add_argument("--options", default="", help="Additional hashcat options")
    
    # List jobs command
    list_parser = subparsers.add_parser("list", help="List all jobs")
    
    # Get job command
    get_parser = subparsers.add_parser("get", help="Get job details")
    get_parser.add_argument("job_id", help="Job ID")
    
    # Get output command
    output_parser = subparsers.add_parser("output", help="Get job output")
    output_parser.add_argument("job_id", help="Job ID")
    output_parser.add_argument("--output", "-o", help="Output file path")
    
    # Delete job command
    delete_parser = subparsers.add_parser("delete", help="Delete a job")
    delete_parser.add_argument("job_id", help="Job ID")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create client
    client = HashcatClient(args.url, args.username, args.password)
    
    try:
        # Execute command
        if args.command == "upload-hash":
            result = client.upload_hashlist(args.file)
            print(f"Uploaded hash file as: {result['filename']}")
        
        elif args.command == "upload-wordlist":
            result = client.upload_wordlist(args.file)
            print(f"Uploaded wordlist as: {result['filename']}")
        
        elif args.command == "run":
            result = client.run_hashcat(
                args.hash_mode, 
                args.attack_mode, 
                args.hash_file, 
                args.wordlist, 
                args.options
            )
            print(f"Started job {result['job_id']} with status: {result['status']}")
        
        elif args.command == "list":
            jobs = client.list_jobs()
            print(f"Found {len(jobs)} job(s):")
            for job in jobs:
                print(f"ID: {job['id']}")
                print(f"  Status: {job['status']}")
                print(f"  Hash file: {job['hash_file']}")
                print(f"  Wordlist: {job['wordlist']}")
                print(f"  Started: {job['started_at']}")
                if job['completed_at']:
                    print(f"  Completed: {job['completed_at']}")
                if 'cracked_count' in job and job['cracked_count'] is not None:
                    print(f"  Cracked: {job['cracked_count']} / {job['total_hashes'] or '?'}")
                print("")
        
        elif args.command == "get":
            job = client.get_job(args.job_id)
            print(f"Job ID: {job['id']}")
            print(f"Status: {job['status']}")
            print(f"Hash file: {job['hash_file']}")
            print(f"Wordlist: {job['wordlist']}")
            print(f"Hash mode: {job['hash_mode']}")
            print(f"Attack mode: {job['attack_mode']}")
            print(f"Started at: {job['started_at']}")
            if job['completed_at']:
                print(f"Completed at: {job['completed_at']}")
            if 'cracked_count' in job and job['cracked_count'] is not None:
                print(f"Cracked: {job['cracked_count']} / {job['total_hashes'] or '?'}")
        
        elif args.command == "output":
            output = client.get_job_output(args.job_id, args.output)
            if not args.output:
                print(output)
            else:
                print(output)  # This will be the success message
        
        elif args.command == "delete":
            result = client.delete_job(args.job_id)
            print(f"Deleted job {args.job_id}")
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
