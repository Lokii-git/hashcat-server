/**
 * Hashcat Server - Common JavaScript
 * Enhanced with dark mode support and UI utilities
 */

// Global configuration
const HashcatUI = {
    animations: true,       // Enable/disable UI animations
    notifications: true,    // Enable/disable notifications
    autoRefresh: 10000,     // Auto-refresh interval in milliseconds (10 seconds)
    theme: 'dark',          // Default theme
    
    // Hash type definitions (mode to readable name)
    hashTypes: {
        '0': 'MD5',
        '100': 'SHA1',
        '1000': 'NTLM',
        '1400': 'SHA256',
        '1700': 'SHA512',
        '1800': 'SHA512crypt $6$ (Unix)',
        '2500': 'WPA/WPA2',
        '3000': 'LM',
        '3200': 'bcrypt $2*$ (Blowfish)',
        '5500': 'NetNTLMv1',
        '5600': 'NetNTLMv2',
        '7500': 'Kerberos 5 AS-REQ Pre-Auth',
        '13100': 'Kerberos 5 TGS-REP',
        '13400': 'KeePass 1 (AES/Twofish) and KeePass 2 (AES)',
        '16800': 'WPA-PMKID-PBKDF2',
        '22000': 'WPA-PBKDF2-PMKID+EAPOL'
    },
    
    // Attack mode definitions
    attackModes: {
        '0': 'Straight (Dictionary)',
        '1': 'Combination',
        '3': 'Brute Force',
        '6': 'Hybrid Wordlist + Mask',
        '7': 'Hybrid Mask + Wordlist',
        '9': 'Association'
    },
    
    // Status color mappings
    statusColors: {
        'starting': 'text-blue-400',
        'running': 'text-blue-400 pulse',
        'completed': 'text-green-400',
        'failed': 'text-red-400',
        'error': 'text-red-400'
    },
    
    // Initialize the UI
    init: function() {
        this.setupAuth();
        this.setupTheme();
        this.setupMobileMenu();
    },
    
    // Authentication setup
    setupAuth: function() {
        // Skip auth check on the login page and for static resources
        if (window.location.pathname === '/login') return;
        
        // Check for auth token in session storage
        const auth = sessionStorage.getItem('auth');
        if (!auth) {
            // Redirect to login page
            window.location.href = '/login';
            return;
        }
        
        // Add Authorization header to all future fetch requests
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            // Don't add auth headers for static resources
            if (url.toString().startsWith('/static/')) {
                return originalFetch(url, options);
            }
            
            options = options || {};
            options.headers = options.headers || {};
            
            // Only add Authorization if not already present
            if (!options.headers['Authorization']) {
                options.headers['Authorization'] = `Basic ${auth}`;
            }
            
            return originalFetch(url, options);
        };
        
        // Test if auth token is valid (use already patched fetch)
        fetch('/api/jobs')
        .then(response => {
            if (!response.ok) {
                // Auth failed, redirect to login
                sessionStorage.removeItem('auth');
                window.location.href = '/login';
            }
        })
        .catch(() => {
            // Error, redirect to login
            sessionStorage.removeItem('auth');
            window.location.href = '/login';
        });
        
        // Add logout button to navigation
        const nav = document.querySelector('nav');
        if (nav) {
            const logoutLink = document.createElement('a');
            logoutLink.href = '#';
            logoutLink.className = 'px-3 py-2 rounded hover:bg-gray-700 flex items-center space-x-1';
            logoutLink.innerHTML = `
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                    <path fill-rule="evenodd" d="M3 3a1 1 0 00-1 1v12a1 1 0 102 0V4a1 1 0 00-1-1zm10.293 9.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L14.586 9H7a1 1 0 100 2h7.586l-1.293 1.293z" clip-rule="evenodd"></path>
                </svg>
                <span>Logout</span>
            `;
            logoutLink.addEventListener('click', function(e) {
                e.preventDefault();
                sessionStorage.removeItem('auth');
                window.location.href = '/login';
            });
            nav.appendChild(logoutLink);
            
            // Also update mobile menu logout
            const mobileLogout = document.getElementById('mobile-logout');
            if (mobileLogout) {
                mobileLogout.classList.remove('hidden');
                mobileLogout.addEventListener('click', function(e) {
                    e.preventDefault();
                    sessionStorage.removeItem('auth');
                    window.location.href = '/login';
                });
            }
        }
    },
    
    // Theme setup
    setupTheme: function() {
        // Theme is already handled in layout.html, just saving the reference here
        this.theme = localStorage.getItem('theme') || 'dark';
        
        // Listen for theme changes
        document.addEventListener('themeChanged', (e) => {
            this.theme = e.detail.theme;
        });
    },
    
    // Mobile menu setup
    setupMobileMenu: function() {
        const mobileMenuButton = document.getElementById('mobile-menu-button');
        const mobileMenu = document.getElementById('mobile-menu');
        
        if (mobileMenuButton && mobileMenu) {
            mobileMenuButton.addEventListener('click', function() {
                mobileMenu.classList.toggle('hidden');
            });
        }
    },
    
    // Show a notification
    notify: function(message, type = 'info') {
        if (!this.notifications) return;
        
        // Check if window.showNotification is available (defined in layout.html)
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type);
        } else {
            console.log(`[${type}] ${message}`);
        }
    },
    
    // Format hash mode to readable name
    formatHashMode: function(mode) {
        return this.hashTypes[mode] || `Mode ${mode}`;
    },
    
    // Format attack mode to readable name
    formatAttackMode: function(mode) {
        return this.attackModes[mode] || `Mode ${mode}`;
    },
    
    // Format date
    formatDate: function(dateString) {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleString();
    },
    
    // Get status color class
    getStatusColorClass: function(status) {
        return this.statusColors[status] || 'text-gray-400';
    },
    
    // Generate a loading spinner
    spinner: function(size = 'md', color = 'text-green-400') {
        const sizes = {
            'sm': 'h-4 w-4',
            'md': 'h-5 w-5',
            'lg': 'h-8 w-8',
            'xl': 'h-12 w-12'
        };
        
        const spinnerSize = sizes[size] || sizes.md;
        
        return `<svg class="animate-spin ${spinnerSize} ${color}" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>`;
    },
    
    // Create a progress bar
    progressBar: function(current, total, showText = true) {
        if (!current || !total) return 'N/A';
        
        const percent = Math.round((current / total) * 100);
        
        return `
            <div class="w-full">
                ${showText ? `<div class="text-xs text-right mb-1">${current} / ${total} (${percent}%)</div>` : ''}
                <div class="progress-bar">
                    <div class="progress-bar-fill" style="width: ${percent}%"></div>
                </div>
            </div>
        `;
    },
    
    // Copy text to clipboard
    copyToClipboard: function(text) {
        navigator.clipboard.writeText(text).then(() => {
            this.notify('Copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Could not copy text: ', err);
            this.notify('Failed to copy to clipboard', 'error');
        });
    }
};

// Initialize UI on DOM load
document.addEventListener('DOMContentLoaded', function() {
    HashcatUI.init();
});

// Export formatters as standalone functions for backward compatibility
function formatHashMode(mode) {
    return HashcatUI.formatHashMode(mode);
}

function formatAttackMode(mode) {
    return HashcatUI.formatAttackMode(mode);
}

function formatDate(dateString) {
    return HashcatUI.formatDate(dateString);
}
