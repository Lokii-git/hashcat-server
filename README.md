# Hashcat Server

![Version](https://img.shields.io/badge/version-1.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A secure, web-based interface for running and managing hashcat password cracking jobs remotely. This project provides a modern UI and API for managing hashcat jobs, uploading hash files and wordlists, and retrieving results.

## Features

- **Secure Web Interface**: Access hashcat from any device with a browser
- **Authentication**: Protect your cracking server with username/password (improved login flow)
- **User Management**: Admin panel with user creation and role-based access control
- **Job Management**: Launch, monitor, and retrieve results from hashcat jobs
- **File Upload**: Easily upload hash files and wordlists
- **Security Features**: Automatic or manual hash file deletion after job completion
- **Performance Optimization**: Persistent potfile caching for faster cracking of previously seen hashes
- **Mobile Friendly**: Responsive design works on desktop and mobile
- **Organized Storage**: Separate directories for hashes, wordlists, and potfiles
- **Linux Service Integration**: Run as a systemd service on Linux systems
- **Reverse Proxy Support**: Easily deploy behind Nginx or Apache with HTTPS
- **Admin Dashboard**: System overview, user management and global settings
- **Role-Based Access Control**: Regular and admin user roles with appropriate permissions

## Requirements

- Python 3.7+
- Hashcat installed and accessible in PATH
- For Linux/Mac: tmux installed (for background job management)
- Additional packages for admin panel:
  - SQLAlchemy (database ORM)
  - Passlib[bcrypt] (password hashing)
  - Psutil (system information for admin dashboard)

## Directory Structure

The application organizes files into specific directories:

- `/hashes`: Stores uploaded hash files
- `/wordlists`: Stores uploaded wordlist files
- `/outputs`: Stores hashcat job output files
- `/potfiles`: Stores hashcat potfiles for caching cracked passwords (ignored by git)
- `/uploads`: Legacy directory (for backward compatibility)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/hashcat-server.git
   cd hashcat-server
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Configure credentials:
   Edit the `.env` file to set your username and password:
   ```
   HASHCAT_USERNAME=admin
   HASHCAT_PASSWORD=your_secure_password
   ```

## Running the Server

### Quick Start

Run the server with:

```
python main.py
```

The server will start at http://localhost:8000 by default.

You can specify a custom host and port:

```
python main.py --host 127.0.0.1 --port 9000
```

### Linux Scripts

We provide several scripts to make running the server on Linux easier:

1. **Basic Start Script**:
   ```bash
   chmod +x start_server.sh
   ./start_server.sh
   ```

2. **Advanced Control Script**:
   ```bash
   chmod +x hashcat_server.sh
   
   # Start server in foreground
   ./hashcat_server.sh start
   
   # Start as daemon
   ./hashcat_server.sh -d start
   
   # Change port
   ./hashcat_server.sh -p 9000 start
   
   # Stop the server
   ./hashcat_server.sh stop
   
   # Check status
   ./hashcat_server.sh status
   
   # Restart
   ./hashcat_server.sh restart
   ```

3. **System Installation**:
   ```bash
   sudo chmod +x install_linux.sh
   
   # Standard installation (creates 'hashcat' user)
   sudo ./install_linux.sh
   
   # Use current user for running the service (preserves Git functionality)
   sudo ./install_linux.sh --use-current-user
   
   # Specify a custom user and install directory
   sudo ./install_linux.sh --user myuser --group mygroup --install-dir /path/to/install
   ```
   
   After installation, control the service with:
   ```bash
   sudo systemctl start hashcat-server
   sudo systemctl stop hashcat-server
   sudo systemctl status hashcat-server
   ```
   
   **Git Compatibility**: If you install in a Git repository directory and plan to use git commands like `git pull` afterwards, use the `--use-current-user` flag to prevent permission issues.
   
   **Reinstallation After Updates**: The installer is designed to handle reinstallation intelligently:
   ```bash
   # After git pull, simply run the installer again
   cd /opt/hashcat-server
   git pull
   sudo ./install_linux.sh --use-current-user
   ```
   
   The installer will:
   - Detect it's a reinstallation
   - Preserve existing files appropriately
   - Update Python dependencies
   - Update the service configuration
   - Restart the service if it was running before
   - Preserve Git repository permissions

### Production Deployment

For production use, consider running with a proper WSGI server like Gunicorn:

```
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## CLI Usage

The `hashctl.py` script provides CLI access to the server:

```
# Upload a hash file
python hashctl.py --url http://localhost:8000 --username admin --password password upload-hash path/to/hashes.txt

# Upload a wordlist
python hashctl.py --url http://localhost:8000 --username admin --password password upload-wordlist path/to/wordlist.txt

# Run a hashcat job
python hashctl.py --url http://localhost:8000 --username admin --password password run --hash-mode 0 --attack-mode 0 --hash-file your_hash_file.txt --wordlist your_wordlist.txt

# List jobs
python hashctl.py --url http://localhost:8000 --username admin --password password list

# Get job output
python hashctl.py --url http://localhost:8000 --username admin --password password output JOB_ID --output result.txt
```

## Securing for Production

For production use:

1. Use HTTPS with a valid certificate
2. Run behind a reverse proxy like Nginx
3. Use strong passwords
4. Consider adding IP restrictions
5. Set appropriate file upload limits
6. Consider changing default credentials

## Security Features

### Hash File Management

The server includes features to securely handle sensitive hash files:

1. **Automatic Hash Deletion**: When creating a job, you can enable the "Auto-Delete Hash File" option to automatically remove the hash file once the job completes (whether successful or not).

2. **Manual Hash Deletion**: You can delete a hash file associated with a job at any time through the job detail page or via API.

3. **Data Segregation**: Hash files are stored separately from wordlists in dedicated directories.

#### Using Hash File Deletion

**Through the Web UI:**
1. When creating a new job, check the "Auto-Delete Hash File After Completion" option to automatically delete the hash file when the job finishes.
2. On the job status page, use the "Delete Hash File" button to manually delete the hash file while keeping the job record and results.

**Through the API:**
1. When creating a job, include `"auto_delete_hash": true` in the request:
   ```
   POST /api/run/hashcat
   {
     "hash_mode": "0",
     "attack_mode": "0",
     "hash_file": "example.txt",
     "wordlist": "rockyou.txt",
     "auto_delete_hash": true
   }
   ```

2. To manually delete a hash file:
   ```
   DELETE /api/jobs/{job_id}/hash_file
   ```

### Authentication Improvements

- **Streamlined Login Flow**: The authentication system has been improved to eliminate redundant login prompts.
- **Protected Static Resources**: Static files (CSS, JS) are properly excluded from authentication checks to prevent multiple login prompts.

#### Authentication System

The authentication system now follows these principles:

1. Single login required - no more multiple login prompts when accessing the application
2. Proper session handling through browser storage
3. Automatic redirection to the login page when session expires
4. Static resources (CSS, JS, images) are accessible without authentication to improve user experience
5. All API endpoints and sensitive routes remain fully protected

## File Management

The server now organizes files into separate directories:

- **Hash Files**: Stored in the `/hashes` directory
- **Wordlists**: Stored in the `/wordlists` directory

When uploading files through the web UI:
1. Hash files will automatically be stored in the `/hashes` directory
2. Wordlists will automatically be stored in the `/wordlists` directory

The `/api/files` endpoint provides a comprehensive list of all available files, categorized by type. This makes it easy to select the appropriate files when configuring a new hashcat job.

## Linux Integration

The Hashcat Server can be installed as a system service on Linux systems using the provided scripts:

### Available Scripts

- `start_server.sh`: Basic script to check dependencies and start the server
- `hashcat_server.sh`: Advanced control script with start/stop/status/restart commands
- `install_linux.sh`: Full installation script that sets up the server as a systemd service
- `hashcat-server.service`: Systemd service definition file

### Installation as a Service

Running the `install_linux.sh` script as root will:

1. Create a dedicated user for the service
2. Install dependencies
3. Set up the directory structure
4. Install the systemd service
5. Configure permissions
6. Start the service (optional)

After installation, the service can be controlled using standard systemd commands:

```bash
sudo systemctl start hashcat-server
sudo systemctl stop hashcat-server
sudo systemctl restart hashcat-server
sudo systemctl status hashcat-server
sudo journalctl -u hashcat-server  # View logs
```

## API Endpoints

The server provides the following API endpoints:

### Web UI Routes
- `GET /`: Main dashboard page
- `GET /login`: Login page
- `GET /upload`: File upload page
- `GET /jobs`: Job listing page
- `GET /job/{job_id}`: Job detail page

### API Routes
- `POST /api/upload/hashlist`: Upload a hash file
- `POST /api/upload/wordlist`: Upload a wordlist file
- `POST /api/run/hashcat`: Launch a hashcat job (includes auto_delete_hash option)
- `GET /api/jobs`: List all jobs
- `GET /api/jobs/{job_id}`: Get job details
- `GET /api/jobs/{job_id}/output`: Get job output file
- `GET /check-auth`: Validate authentication credentials

## Reverse Proxy Setup

You can securely expose Hashcat Server to the internet using a reverse proxy with HTTPS. Example configurations for Nginx and Apache are provided in the `proxy_examples` directory.

### Nginx Configuration

See `proxy_examples/nginx.conf` for a complete example. Key points:

1. Redirect HTTP to HTTPS
2. Set proper security headers
3. Forward appropriate proxy headers
4. Cache static resources

### Apache Configuration

See `proxy_examples/apache.conf` for a complete example. Key points:

1. Enable required Apache modules
2. Configure SSL certificates
3. Set up WebSocket support (if needed)
4. Add security headers

### Common Issues

If you experience authentication issues behind a reverse proxy:

1. Ensure proxy headers are properly forwarded (X-Forwarded-Proto, X-Forwarded-Host)
2. Set `ROOT_PATH` environment variable if hosting under a subpath
3. Check for multiple authentication popups (should be fixed in latest version)
4. Verify default credentials (username: admin, password: password)
- `DELETE /api/jobs/{job_id}`: Delete a job
- `DELETE /api/jobs/{job_id}/hash_file`: Delete only the hash file associated with a job
- `GET /api/files`: List all available hash files and wordlists

## Troubleshooting

### Permission Issues

If you encounter permission issues after installation:

1. **Git Operations Failing**: If `git pull` or other Git commands fail with permission errors:
   ```bash
   # Fix Git directory permissions
   sudo chown -R your_username:your_group .git/
   sudo chmod -R 755 .git/
   
   # Or reinstall with your current user
   sudo ./install_linux.sh --use-current-user
   ```

2. **Job Execution Errors**: If jobs fail to run due to permission issues:
   ```bash
   # Make sure data directories are writable
   sudo chmod -R 775 /opt/hashcat-server/{uploads,hashes,wordlists,outputs,logs}
   sudo chmod 664 /opt/hashcat-server/jobs.json
   ```

3. **Service User Can't Write Files**: Ensure the service user has write access:
   ```bash
   # Add your user to the hashcat group
   sudo usermod -a -G hashcat your_username
   
   # Or change directory permissions to be more permissive
   sudo chmod -R 777 /opt/hashcat-server/{uploads,hashes,wordlists,outputs,logs}
   ```

## Admin Panel

The hashcat server now includes a comprehensive admin panel with the following features:

### User Management
- **Multiple User Support**: Create and manage multiple users with different permission levels
- **Role-Based Access**: Admin and regular user roles with different privileges
- **User Actions**: Admins can create, edit, disable, and delete users
- **Password Management**: Secure password storage with bcrypt hashing

### Admin Dashboard
- **System Overview**: View server statistics, system information, and user metrics
- **Job Management**: View and manage all users' hashcat jobs
- **User Management**: Manage user accounts from a central interface

### Settings Management
- **General Settings**: Configure server name, job limits, and defaults
- **Email Settings**: Set up email notifications for job completion
- **Security Settings**: Configure login attempt limits and password policies

### Security Enhancements
- **Login Attempt Tracking**: Prevents brute force attacks with account lockout
- **Password Policies**: Optional password expiration and complexity requirements
- **Role-Based Authorization**: API endpoints and pages secured by user role

### Accessing the Admin Panel
1. Log in with an admin account
2. Navigate to the admin dashboard at `/admin`
3. Default admin credentials:
   - Username: admin
   - Password: hashcat-admin (change this immediately after first login)

## Version History

### v1.3.0 (Current)
- Added admin panel with user management and system settings
- Implemented role-based access control with admin and regular user roles
- Added database authentication with bcrypt password hashing
- Added login attempt tracking and account lockout for security
- Created settings management system with general, email, and security settings
- Backward compatibility with existing user authentication

### v1.2.0 
- Improved job output monitoring with better completion detection
- Added support for capturing final output when jobs complete
- Added force refresh functionality to ensure complete job results
- Enhanced potfile integration and caching of cracked passwords
- Fixed bug with missing output at job completion (99.5%+ progress)
- Better handling of exhausted keyspace detection
- Added API endpoint to force refresh job output and status

### v1.1.0
- Added hash file security features:
  - Option to automatically delete hash files after job completion
  - Manual deletion of hash files via UI and API
- Improved authentication flow to prevent multiple login prompts
- Fixed issues with hashcat output display
- Enhanced job status tracking
- Added continuous monitoring for background jobs on Linux
- Improved Linux service installation options to preserve Git functionality

### v1.0.0 (Initial Release)
- Basic functionality for running hashcat jobs
- Web interface for job management
- File upload capabilities
- Authentication system
- Linux service integration

## License

MIT License
