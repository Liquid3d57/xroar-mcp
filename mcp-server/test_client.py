#!/usr/bin/env python3
"""Test client for the xroar MCP server."""

import http.client
import json
import sys
import time


def MCP_HOST = "localhost"
MCP_PORT = 8000


def call_endpoint(path, method="GET", body=None, params=None):
    """Call an MCP server endpoint."""
    if params:
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        path = f"{path}?{query}"
    
    conn = http.client.HTTPConnection(MCP_HOST, MCP_PORT, timeout=10)
    
    if method == "GET":
        conn.request("GET", path)
    elif method == "POST":
        headers = {"Content-Type": "application/json"}
        conn.request("POST", path, body=body, headers=headers)
    
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()
    
    try:
        return response.status, json.loads(data)
    except json.JSONDecodeError:
        return response.status, {"raw": data}


def test_all():
    """Test all MCP server endpoints."""
    print("=" * 60)
    print("MCP Server Test Client")
    print("=" * 60)
    
    # Test 1: Root endpoint
    print("\n1. Testing root endpoint (/)...")
    status, data = call_endpoint("/")
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
    else:
        print(f"   Error: {data}")
    
    # Test 2: Health endpoint
    print("\n2. Testing health endpoint (/health)...")
    status, data = call_endpoint("/health")
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)}")
    else:
        print(f"   Error: {data}")
    
    # Test 3: Status endpoint
    print("\n3. Testing status endpoint (/status)...")
    status, data = call_endpoint("/status")
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)}")
    else:
        print(f"   Error: {data}")
    
    # Test 4: Build endpoint
    print("\n4. Testing build endpoint (/build)...")
    status, data = call_endpoint("/build")
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)[:300]}...")
    else:
        print(f"   Error: {data}")
    
    # Test 5: Symbols endpoint (without specific symbol)
    print("\n5. Testing symbols endpoint (/symbols)...")
    status, data = call_endpoint("/symbols")
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)[:300]}...")
    else:
        print(f"   Error: {data}")
    
    # Test 6: Symbols endpoint (with specific symbol - may not find any)
    print("\n6. Testing symbols endpoint with specific symbol (/symbols?name=MainLoop)...")
    status, data = call_endpoint("/symbols", params={"name": "MainLoop"})
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)}")
    else:
        print(f"   Error: {data}")
    
    # Test 7: Test endpoint
    print("\n7. Testing test endpoint (/test)...")
    status, data = call_endpoint("/test")
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)[:300]}...")
    else:
        print(f"   Error: {data}")
    
    # Test 8: Emulator status endpoint
    print("\n8. Testing emulator status endpoint (/emulator?action=status)...")
    status, data = call_endpoint("/emulator", params={"action": "status"})
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Response: {json.dumps(data, indent=2)}")
    else:
        print(f"   Error: {data}")
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_all()