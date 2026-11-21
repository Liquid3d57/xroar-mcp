#!/usr/bin/env python3
"""MCP Server for xroar emulator testing.

Provides an HTTP-based interface for agents to interact with the xroar emulator,
including building, running, and testing capabilities.
"""

import argparse
import configparser
import http.server
import json
import os
import shlex
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
XROAR_DIR = os.path.join(PROJECT_ROOT, "xroar")
BINARY_PATH = os.path.join(PROJECT_ROOT, "bin", "xroar-dev.exe") if sys.platform.startswith("win") else os.path.join(XROAR_DIR, "xroar")


def load_config():
    """Load server settings from config.ini, with process environment overrides."""
    config = configparser.ConfigParser()
    config.read(os.path.join(PROJECT_ROOT, "config.ini"), encoding="utf-8")
    section = config["server"] if config.has_section("server") else {}
    host = os.environ.get("MCP_HOST", section.get("host", "127.0.0.1"))
    port = int(os.environ.get("MCP_PORT", section.get("port", "8000")))
    return host, port


def windows_bash_path(path):
    """Convert a native Windows absolute path to the MSYS/Git Bash form."""
    if sys.platform.startswith("win") and len(path) >= 3 and path[1] == ":":
        return "/" + path[0].lower() + path[2:].replace("\\", "/")
    return path

# Global state
emulator_process = None
server_running = True


def find_binary():
    """Find the emulator binary."""
    candidates = [
        os.path.join(PROJECT_ROOT, "bin", "xroar-dev.exe"),
        os.path.join(PROJECT_ROOT, "bin", "xroar.exe"),
        os.path.join(XROAR_DIR, "xroar.exe" if sys.platform.startswith("win") else "xroar"),
        os.path.join(PROJECT_ROOT, "xroar.exe" if sys.platform.startswith("win") else "xroar"),
        os.path.join(BUILD_DIR, "xroar.exe" if sys.platform.startswith("win") else "xroar"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def build_emulator():
    """Build the xroar emulator."""
    try:
        if sys.platform.startswith("win"):
            build_script = os.path.join(BUILD_DIR, "build-windows.sh")
        elif sys.platform.startswith("darwin"):
            build_script = os.path.join(BUILD_DIR, "build-macos.sh")
        else:
            build_script = os.path.join(BUILD_DIR, "build-linux.sh")
        
        if os.path.exists(build_script):
            bash_script = os.path.relpath(build_script, PROJECT_ROOT).replace("\\", "/")
            result = subprocess.run(["bash", bash_script], check=False, cwd=PROJECT_ROOT,
                                    capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                binary = find_binary()
                return {"status": "success", "returncode": 0, "binary": binary,
                        "stdout": result.stdout, "stderr": result.stderr,
                        "message": "Build completed successfully"}
            else:
                return {"status": "error", "returncode": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr,
                        "message": "Build failed"}
        else:
            return {"status": "error", "returncode": 2,
                    "message": f"No build script found at {build_script}"}
    except (OSError, subprocess.SubprocessError) as e:
        return {"status": "error", "returncode": 1, "message": str(e)}


def compile_minimal():
    """Attempt minimal compilation of xroar."""
    try:
        # Check if there's a configure script or makefile
        configure_script = os.path.join(XROAR_DIR, "configure")
        makefile = os.path.join(XROAR_DIR, "makefile" if sys.platform.startswith("win") else "Makefile")
        
        if os.path.exists(configure_script):
            result = subprocess.run(
                ["bash", configure_script, "--without-opengl"],
                check=False,
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
                check=False,
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
    except (OSError, subprocess.SubprocessError) as e:
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
        if isinstance(commands, str):
            commands = shlex.split(commands)
        for cmd_opt in commands:
            cmd.append(str(cmd_opt))
    
    try:
        emulator_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True
        )
        return {
            "status": "started",
            "pid": emulator_process.pid,
            "command": " ".join(cmd),
            "message": f"Emulator started with PID {emulator_process.pid}"
        }
    except OSError as e:
        return {"status": "error", "message": str(e)}


def stop_emulator():
    """Stop the emulator process."""
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
        except OSError as e:
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
    
    acceptance_script = os.path.relpath(os.path.join(BUILD_DIR, "acceptance.sh"), PROJECT_ROOT).replace("\\", "/")
    binary_arg = os.path.relpath(binary, PROJECT_ROOT).replace("\\", "/")
    cmd = ["bash", acceptance_script, binary_arg]
    if tolerated:
        cmd.extend(tolerated.split())
    
    try:
        result = subprocess.run(
            cmd,
            check=False,
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
    except OSError as e:
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
            check=False,
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
    except OSError as e:
        return {"status": "error", "message": str(e)}


def handle_request(handler_method):
    """Decorator to standardize API responses."""
    def wrapper(*args, **kwargs):
        try:
            result = handler_method(*args, **kwargs)
            return {"status": "success", "data": result}
        except (OSError, ValueError, TypeError) as e:
            return {"status": "error", "message": str(e)}
    return wrapper


class MCPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the MCP server."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
    
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
                            emulator_process.stdin.write(cmd + "\n")
                            emulator_process.stdin.flush()
                        response = {"status": "command_sent", "command": cmd}
                    except (OSError, BrokenPipeError) as e:
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
                argv = shlex.split(cmd, posix=(os.name != "nt"))
                if not argv:
                    raise ValueError("Command is empty")
                result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=30)
                response = {
                    "status": "completed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            except subprocess.TimeoutExpired:
                response = {"status": "timeout", "message": "Command timed out"}
            except (OSError, ValueError) as e:
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
        except OSError:
            break
    
    httpd.server_close()
    print("MCP Server stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XRoar MCP HTTP server")
    parser.add_argument("command", nargs="?", choices=["build", "test", "status"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    configured_host, configured_port = load_config()
    port = args.port or configured_port
    host = args.host or configured_host

    if args.command == "build":
        print(json.dumps(build_emulator(), indent=2))
    elif args.command == "test":
        print(json.dumps(run_acceptance_tests(), indent=2))
    elif args.command == "status":
        binary = find_binary()
        print(json.dumps({"binary_available": binary is not None,
                          "binary": binary,
                          "emulator_running": emulator_process is not None and emulator_process.poll() is None},
                         indent=2))
    else:
        binary = find_binary()
        if binary:
            print(f"Found emulator binary: {binary}", file=sys.stderr)
        else:
            print("No emulator binary found. Use /build endpoint to compile.", file=sys.stderr)
        run_server(port, host)