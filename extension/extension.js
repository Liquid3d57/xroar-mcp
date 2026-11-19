const vscode = require('vscode');
const { spawn } = require('child_process');
const http = require('http');

let serverProcess = null;
let outputChannel = vscode.window.createOutputChannel('xroar MCP Server');

/**
 * Starts the MCP server as a subprocess
 */
function startServer() {
    const config = vscode.workspace.getConfiguration('mcp');
    const host = config.get('host', 'localhost');
    const port = config.get('port', 3000);
    const serverPath = config.get('serverPath', '${workspaceFolder}/mcp-server/server.py');
    
    // Kill existing server if running
    if (serverProcess) {
        serverProcess.kill();
    }
    
    outputChannel.appendLine(`Starting MCP server at http://${host}:${port}`);
    outputChannel.appendLine(`Using server: ${serverPath}`);
    
    serverProcess = spawn('python3', [serverPath], {
        cwd: vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[1].uri.fsPath : undefined,
        env: {
            ...process.env,
            MCP_HOST: host,
            MCP_PORT: port.toString()
        },
        detached: false
    });
    
    serverProcess.stdout.on('data', (data) => {
        outputChannel.append(`[stdout] ${data}`);
    });
    
    serverProcess.stderr.on('data', (data) => {
        outputChannel.append(`[stderr] ${data}`);
    });
    
    serverProcess.on('close', (code) => {
        outputChannel.appendLine(`[MCP Server] Process exited with code ${code}`);
        serverProcess = null;
    });
    
    // Wait a moment for server to start, then test connection
    setTimeout(testConnection, 2000);
}

/**
 * Stops the MCP server subprocess
 */
function stopServer() {
    if (serverProcess) {
        outputChannel.appendLine('Stopping MCP server...');
        serverProcess.kill();
        serverProcess = null;
        outputChannel.appendLine('MCP server stopped.');
    } else {
        outputChannel.appendLine('No MCP server process running.');
    }
}

/**
 * Checks the MCP server status
 */
function checkStatus() {
    const config = vscode.workspace.getConfiguration('mcp');
    const host = config.get('host', 'localhost');
    const port = config.get('port', 3000);
    
    http.get(`http://${host}:${port}/status`, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => {
            try {
                const status = JSON.parse(data);
                outputChannel.appendLine(`MCP Server Status: ${JSON.stringify(status, null, 2)}`);
                
                // Show helpful message
                if (status.emulator_running) {
                    vscode.window.showInformationMessage('MCP server is running and emulator is active');
                } else {
                    vscode.window.showInformationMessage('MCP server is running but emulator is not active');
                }
            } catch (e) {
                outputChannel.appendLine(`Failed to parse status: ${data}`);
                vscode.window.showErrorMessage('Failed to parse MCP server status');
            }
        });
    }).on('error', (e) => {
        outputChannel.appendLine(`Connection error: ${e.message}`);
        vscode.window.showErrorMessage(`Cannot connect to MCP server at http://${host}:${port}. Is the server running?`);
    });
}

/**
 * Runs the test client
 */
function testClient() {
    const pythonPath = require('python3') ? 'python3' : 'python';
    const scriptPath = vscode.workspace.getConfiguration('mcp').get('serverPath', '${workspaceFolder}/mcp-server/test_client.py');
    
    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        cancellable: false
    }, async () => {
        const exec = require('child_process').exec;
        exec(`${pythonPath} "${scriptPath}"`, (error, stdout, stderr) => {
            outputChannel.appendLine(`[Test Client] stdout: ${stdout}`);
            outputChannel.appendLine(`[Test Client] stderr: ${stderr}`);
            if (error) {
                outputChannel.appendLine(`[Test Client] error: ${error.message}`);
            }
            vscode.window.showInformationMessage('Test client output sent to "xroar MCP Server" output channel');
        });
    });
}

/**
 * Builds the emulator via the MCP server
 */
function buildEmulator() {
    const config = vscode.workspace.getConfiguration('mcp');
    const host = config.get('host', 'localhost');
    const port = config.get('port', 3000);
    
    http.get(`http://${host}:${port}/build`, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => {
            try {
                const result = JSON.parse(data);
                outputChannel.appendLine(`[Build] ${JSON.stringify(result, null, 2)}`);
            } catch (e) {
                outputChannel.appendLine(`[Build] Raw response: ${data}`);
            }
        });
    }).on('error', (e) => {
        outputChannel.appendLine(`[Build] Connection error: ${e.message}`);
    });
}

/**
 * Runs acceptance tests via the MCP server
 */
function runTests() {
    const config = vscode.workspace.getConfiguration('mcp');
    const host = config.get('host', 'localhost');
    const port = config.get('port', 3000);
    
    http.get(`http://${host}:${port}/test`, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => {
            try {
                const result = JSON.parse(data);
                outputChannel.appendLine(`[Tests] ${JSON.stringify(result, null, 2)}`);
            } catch (e) {
                outputChannel.appendLine(`[Tests] Raw response: ${data}`);
            }
        });
    }).on('error', (e) => {
        outputChannel.appendLine(`[Tests] Connection error: ${e.message}`);
    });
}

// Activate the extension
function activate(context) {
    // Register all commands
    let startDisposable = vscode.commands.registerCommand('mcp.startServer', startServer);
    let stopDisposable = vscode.commands.registerCommand('mcp.stopServer', stopServer);
    let statusDisposable = vscode.commands.registerCommand('mcp.status', checkStatus);
    let testDisposable = vscode.commands.registerCommand('mcp.testClient', testClient);
    let buildDisposable = vscode.commands.registerCommand('mcp.buildEmulator', buildEmulator);
    let testsDisposable = vscode.commands.registerCommand('mcp.runTests', runTests);
    
    context.subscriptions.push(startDisposable);
    context.subscriptions.push(stopDisposable);
    context.subscriptions.push(statusDisposable);
    context.subscriptions.push(testDisposable);
    context.subscriptions.push(buildDisposable);
    context.subscriptions.push(testsDisposable);
    
    // Add output channel to sidebar
    context.subscriptions.push(outputChannel);
    
    outputChannel.appendLine('xroar MCP Server extension activated');
    outputChannel.appendLine('Use "MCP: Start Server" command to begin');
}

// This method is called when your extension is deactivated
function deactivate() {
    if (serverProcess) {
        serverProcess.kill();
    }
}

module.exports = { activate, deactivate };