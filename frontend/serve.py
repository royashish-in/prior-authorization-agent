#!/usr/bin/env python3
"""
Simple HTTP server to serve the Prior Authorization Agent frontend.
This avoids CORS issues when opening HTML files directly in the browser.
"""

import http.server
import socketserver
import webbrowser
import os
import sys

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

def main():
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"🚀 Frontend server starting on http://localhost:{PORT}")
            print(f"📁 Serving files from: {DIRECTORY}")
            print(f"🌐 Dashboard URL: http://localhost:{PORT}/simple-dashboard.html")
            print(f"🛑 Press Ctrl+C to stop the server")
            print()
            
            # Try to open browser automatically
            try:
                webbrowser.open(f'http://localhost:{PORT}/simple-dashboard.html')
                print("✅ Browser opened automatically")
            except:
                print("⚠️  Could not open browser automatically")
                print(f"   Please open: http://localhost:{PORT}/simple-dashboard.html")
            
            print()
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"❌ Port {PORT} is already in use")
            print(f"   Try: lsof -i :{PORT}")
            print(f"   Or use a different port")
        else:
            print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()