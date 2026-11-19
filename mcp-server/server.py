#!/usr/bin/env python3
"""MCP Server for xroar emulator testing.

Provides an HTTP-based interface for agents to interact with the xroar emulator,
including building, running, and testing capabilities.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
XROAR_DIR = os.path.join(PROJECT_ROOT, "xroar")
BINARY_PATH = os.path.join(XROAR_DIR, "xroar.exe") if sys.platform.startswith("win") else os.path.join(XROAR_DIR, "xroar")

# Global state
emulator_process = None
server_running = True


def find_binary():
    """Find the emulator binary."""
    # Check common locations
    candidates = [
        os.path.join(XROAR_DIR, "xroar.exe" if sys.platform.startswith("win") else "xroar"),
        os.path.join(PROJECT_ROOT, "xroar.exe" if sys.platform.startswith("win") else "xroar"),
        os.path.join(BUILD_DIR, "xroar.exe" if sys.platform.startswith("win") else "xroar"),
    ]
    
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    
    # Try to build first
    if not os.path.exists(candidates[0]):
        print(f"Binary not found at {candidates[0]}, attempting build...")
        if build_emulator():
            return candidates[0]
    
    return None


def build_emulator():
    """Build the xroar emulator."""
    try:
        # Try the appropriate build script for the platform
        if sys.platform.startswith("win"):
            build_script = os.path.join(BUILD_DIR, "build-windows.sh")
        elif sys.platform.startswith("darwin"):
            build_script = os.path.join(BUILD_DIR, "build-macos.sh")
        else:
            build_script = os.path.join(BUILD_DIR, "build-linux.sh")
        
        if os.path.exists(build_script):
            result = subprocess.run(
                ["bash", build_script],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                print("Build completed successfully")
                return True
            else:
                print(f"Build failed: {result.stderr}")
                return False
        else:
            print(f"No build script found at {build_script}")
            # Try minimal compilation
            return compile_minimal()
    except Exception as e:
        print(f"Error during build: {e}")
        return False


def compile_minimal():
    """Attempt minimal compilation of xroar."""
    try:
        # Check if there's a configure script or makefile
        configure_script = os.path.join(XROAR_DIR, "configure")
        makefile = os.path.join(XROAR_DIR, "makefile" if sys.platform.startswith("win") else "Makefile")
        
        if os.path.exists(configure_script):
            result = subprocess.run(
                ["bash", configure_script, "--without-opengl"],
                cwd=XROAR_DIR,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                print(f"Configure failed: {result.stderr}")
                return False
        
        if os.path.exists(makefile):
            result = subprocess.run(
                ["make"],
                cwd=XROAR_DIR,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                print("Minimal build completed successfully")
                return True
            else:
                print(f"Make failed: {result.stderr}")
                return False
        
        return False
    except Exception as e:
        print(f"Error during minimal compile: {e}")
        return False


def start_emulator(headless=True, rom_path=None, commands=None):
    """Start the xroar emulator process."""
    global emulator_process
    
    binary = find_binary()
    if not binary:
        return {"status": "error", "message": "Emulator binary not found. Please build first."}
    
    cmd = [binary]
    
    if headless:
        cmd.append("-headless")
    
    if rom_path:
        cmd.extend(["-cart", rom_path])
    
    # Add any additional commands
    if commands:
        for cmd_opt in commands:
            cmd.append(cmd_opt)
    
    try:
        emulator_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return {
            "status": "started",
            "pid": emulator_process.pid,
            "command": " ".join(cmd),
            "message": f"Emulator started with PID {emulator_process.pid}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def stop_emulator():
    """Stop the emulator process."""
    global emulator_process
    
    if emulator_process and emulator_process.poll() is None:
        try:
            emulator_process.terminate()
            # Wait a bit for graceful shutdown
            try:
                emulator_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                emulator_process.kill()
                emulator_process.wait()
            return {"status": "stopped", "message": "Emulator stopped successfully"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    elif emulator_process:
        return {"status": "already_stopped", "message": "Emulator already stopped"}
    else:
        return {"status": "not_running", "message": "No emulator process running"}


def run_acceptance_tests(tolerated=None):
    """Run the acceptance tests."""
    binary = find_binary()
    if not binary:
        return {"status": "error", "message": "Emulator binary not found. Please build first."}
    
    cmd = ["bash", os.path.join(BUILD_DIR, "acceptance.sh"), binary]
    if tolerated:
        cmd.extend(tolerated.split())
    
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            "status": "completed",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "message": f"Acceptance tests completed with code {result.returncode}"
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Acceptance tests timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_symbol_info(symbol_name):
    """Get symbol information from the emulator binary."""
    binary = find_binary()
    if not binary:
        return {"status": "error", "message": "Emulator binary not found."}
    
    try:
        # Use strings to extract symbols
        result = subprocess.run(
            ["strings", binary],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Search for the symbol
        symbols = result.stdout.split('\n')
        for sym in symbols:
            if symbol_name in sym:
                return {
                    "status": "found",
                    "symbol": sym.strip(),
                    "message": f"Found symbol: {sym.strip()}"
                }
        
        return {
            "status": "not_found",
            "message": f"Symbol '{symbol_name}' not found in binary"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def handle_request(handler_method):
    """Decorator to standardize API responses."""
    def wrapper(*args, **kwargs):
        try:
            result = handler_method(*args, **kwargs)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return wrapper


class MCPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the MCP server."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "server": "xroar-mcp",
                "version": "1.0.0",
                "endpoints": {
                    "status": "/status",
                    "build": "/build",
                    "test": "/test",
                    "emulator": "/emulator",
                    "symbols": "/symbols",
                    "health": "/health"
                }
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            binary = find_binary()
            response = {
                "emulator_running": emulator_process is not None and emulator_process.poll() is None,
                "binary_available": binary is not None,
                "project_root": PROJECT_ROOT,
                "message": "MCP Server is operational"
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "ok", "message": "MCP Server healthy"}
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/build":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            result = build_emulator()
            response = {"status": result.get("status", "error"), "data": result}
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/test":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Get tolerated parameters from query
            qs = parse_qs(parsed.query)
            tolerated = qs.get("tolerated", [None])[0]
            result = run_acceptance_tests(tolerated)
            response = {"status": result.get("status", "error"), "data": result}
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/emulator":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            qs = parse_qs(parsed.query)
            action = qs.get("action", [None])[0]
            
            if action == "start":
                rom = qs.get("rom", [None])[0]
                commands = qs.get("cmd", [None])[0]
                result = start_emulator(headless=True, rom_path=rom, commands=commands)
                response = {"status": result.get("status", "error"), "data": result}
            elif action == "stop":
                result = stop_emulator()
                response = {"status": result.get("status", "error"), "data": result}
            elif action == "status":
                result = {
                    "running": emulator_process is not None and emulator_process.poll() is None,
                    "pid": emulator_process.pid if emulator_process else None
                }
                response = {"status": "success", "data": result}
            else:
                response = {"status": "error", "message": "Unknown action. Use: start, stop, or status"}
            
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/symbols":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            qs = parse_qs(parsed.query)
            symbol = qs.get("name", [None])[0]
            
            if symbol:
                result = get_symbol_info(symbol)
                response = {"status": result.get("status", "error"), "data": result}
            else:
                # Return available symbols
                result = get_symbol_info("")
                response = {"status": result.get("status", "error"), "data": result}
            
            self.wfile.write(json.dumps(response).encode())
        
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "not_found", "message": "Endpoint not found"}
            self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b""
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        
        if parsed.path == "/emulator":
            action = data.get("action", "")
            
            if action == "start":
                rom = data.get("rom", None)
                commands = data.get("cmd", None)
                headless = data.get("headless", True)
                result = start_emulator(headless=headless, rom_path=rom, commands=commands)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": result.get("status", "error"), "data": result}).encode())
            elif action == "stop":
                result = stop_emulator()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": result.get("status", "error"), "data": result}).encode())
            elif action == "command":
                cmd = data.get("command", "")
                # Execute a command against the emulator
                if emulator_process and emulator_process.poll() is None:
                    # Send input to the process if it's interactive
                    try:
                        if emulator_process.stdin:
                            emulator_process.stdin.write((cmd + "\n").encode())
                            emulator_process.stdin.flush()
                        response = {"status": "command_sent", "command": cmd}
                    except Exception as e:
                        response = {"status": "error", "message": str(e)}
                else:
                    response = {"status": "not_running", "message": "Emulator not running"}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": response.get("status", "error"), "data": response}).encode())
            else:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Unknown action"}).encode())
        
        elif parsed.path == "/command":
            cmd = data.get("command", "")
            # Generic command execution
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                response = {
                    "status": "completed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            except subprocess.TimeoutExpired:
                response = {"status": "timeout", "message": "Command timed out"}
            except Exception as e:
                response = {"status": "error", "message": str(e)}
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": response.get("status", "error"), "data": response}).encode())
        
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "not_found", "message": "Endpoint not found"}).encode())
    
    def do_HEAD(self):
        """Handle HEAD requests."""
        self.send_response(200)
        self.end_headers()


def run_server(port=8000, host="0.0.0.0"):
    """Run the MCP server."""
    global server_running
    
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, MCPHandler)
    
    # Set timeout so we can check server_running periodically
    httpd.timeout = 1
    
    print(f"MCP Server starting on {host}:{port}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Binary path: {BINARY_PATH}")
    
    while server_running:
        try:
            httpd.handle_request()
        except Exception:
            break
    
    httpd.server_close()
    print("MCP Server stopped")


if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", 8000))
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    
    # Print available information
    binary = find_binary()
    if binary:
        print(f"Found emulator binary: {binary}")
    else:
        print("No emulator binary found. Use /build endpoint to compile.")
    
    run_server(port, host)