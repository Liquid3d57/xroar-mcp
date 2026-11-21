const vscode = require('vscode');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

let serverProcess = null;
let outputChannel = vscode.window.createOutputChannel('xroar MCP Server');

function readServerIni(workspaceFolder) {
    const iniPath = path.join(workspaceFolder || '', 'config.ini');
    const result = {host: '127.0.0.1', port: 8000};
    if (!workspaceFolder || !fs.existsSync(iniPath)) return result;
    for (const line of fs.readFileSync(iniPath, 'utf8').split(/\r?\n/)) {
        const match = /^\s*([a-zA-Z]+)\s*=\s*(.*?)\s*$/.exec(line);
        if (!match) continue;
        if (match[1].toLowerCase() === 'host') result.host = match[2];
        if (match[1].toLowerCase() === 'port') result.port = parseInt(match[2], 10) || result.port;
    }
    return result;
}

function getServerSettings(config, workspaceFolder) {
    const ini = readServerIni(workspaceFolder);
    const hostSetting = config.inspect('host');
    const portSetting = config.inspect('port');
    const configuredHost = hostSetting && (hostSetting.workspaceFolderValue ?? hostSetting.workspaceValue ?? hostSetting.globalValue);
    const configuredPort = portSetting && (portSetting.workspaceFolderValue ?? portSetting.workspaceValue ?? portSetting.globalValue);
    return {
        host: configuredHost && configuredHost !== '127.0.0.1' ? configuredHost : ini.host,
        port: configuredPort && configuredPort !== 8000 ? configuredPort : ini.port
    };
}

/**
 * Starts the MCP server as a subprocess
 */
function startServer() {
    const config = vscode.workspace.getConfiguration('mcp');
    const configuredPath = config.get('serverPath', '');
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const settings = getServerSettings(config, workspaceFolder);
    const host = settings.host;
    const port = settings.port;
    const serverPath = (configuredPath && configuredPath !== '${workspaceFolder}/mcp-server/server.py'
        ? configuredPath
        : workspaceFolder ? `${workspaceFolder}/mcp-server/server.py` : undefined);

    if (!serverPath || !workspaceFolder) {
        vscode.window.showErrorMessage('Open an xroar-mcp workspace before starting the MCP server');
        return;
    }
    
    // Kill existing server if running
    if (serverProcess) {
        serverProcess.kill();
    }
    
    outputChannel.appendLine(`Starting MCP server at http://${host}:${port}`);
    outputChannel.appendLine(`Using server: ${serverPath}`);
    
    serverProcess = spawn('python', [serverPath], {
        cwd: workspaceFolder,
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

function testConnection() {
    if (!serverProcess) return;
    const config = vscode.workspace.getConfiguration('mcp');
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const settings = getServerSettings(config, workspaceFolder);
    const host = settings.host;
    const port = settings.port;
    http.get(`http://${host}:${port}/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
            outputChannel.appendLine('MCP server health check passed');
        }
    }).on('error', (error) => {
        outputChannel.appendLine(`MCP server health check failed: ${error.message}`);
    });
}

/**
 * Checks the MCP server status
 */
function checkStatus() {
    const config = vscode.workspace.getConfiguration('mcp');
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const settings = getServerSettings(config, workspaceFolder);
    const host = settings.host;
    const port = settings.port;
    
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
    const config = vscode.workspace.getConfiguration('mcp');
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const settings = getServerSettings(config, workspaceFolder);
    const host = settings.host;
    const port = settings.port;
    if (!workspaceFolder) {
        vscode.window.showErrorMessage('Open an xroar-mcp workspace before running the test client');
        return;
    }
    const scriptPath = `${workspaceFolder}/mcp-server/test_client.py`;
    
    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        cancellable: false
    }, async () => {
        const spawn = require('child_process').spawn;
        const child = spawn('python', [scriptPath], {
            cwd: workspaceFolder,
            env: {...process.env, MCP_HOST: host, MCP_PORT: port.toString()}
        });
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (data) => stdout += data);
        child.stderr.on('data', (data) => stderr += data);
        child.on('close', (code) => {
            outputChannel.appendLine(`[Test Client] stdout: ${stdout}`);
            outputChannel.appendLine(`[Test Client] stderr: ${stderr}`);
            if (code !== 0) outputChannel.appendLine(`[Test Client] exit code: ${code}`);
            vscode.window.showInformationMessage('Test client output sent to "xroar MCP Server" output channel');
        });
    });
}

/**
 * Builds the emulator via the MCP server
 */
function buildEmulator() {
    const config = vscode.workspace.getConfiguration('mcp');
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const settings = getServerSettings(config, workspaceFolder);
    const host = settings.host;
    const port = settings.port;
    
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
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const settings = getServerSettings(config, workspaceFolder);
    const host = settings.host;
    const port = settings.port;
    
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

/**
 * Installs native or Docker dependencies and configures the MCP server.
 */
function installMcp() {
    const config = vscode.workspace.getConfiguration('mcp');
    const mode = config.get('installMode', 'native');
    const port = config.get('port', 8000);
    const workspaceFolder = vscode.workspace.workspaceFolders ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined;
    const workspaceInstaller = workspaceFolder ? `${workspaceFolder}/install.ps1` : undefined;
    const bundledInstaller = `${__dirname}/resources/install.ps1`;
    const installer = workspaceInstaller && fs.existsSync(workspaceInstaller) ? workspaceInstaller : bundledInstaller;

    if (!fs.existsSync(installer)) {
        vscode.window.showErrorMessage('MCP installer was not found in the workspace or extension package');
        return;
    }

    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `Installing xroar MCP (${mode})`,
        cancellable: false
    }, async () => {
        await new Promise((resolve) => {
            const args = [
                '-NoProfile',
                '-ExecutionPolicy', 'Bypass',
                '-File', installer,
                '-Mode', mode,
                '-Port', port.toString()
            ];
            if (workspaceFolder) args.push('-SourceRoot', workspaceFolder);
            const child = spawn('pwsh', args, {cwd: workspaceFolder || __dirname});
            let stdout = '';
            let stderr = '';
            child.stdout.on('data', (data) => {
                stdout += data;
                outputChannel.append(`[Installer] ${data}`);
            });
            child.stderr.on('data', (data) => {
                stderr += data;
                outputChannel.append(`[Installer stderr] ${data}`);
            });
            child.on('close', (code) => {
                if (code === 0) {
                    vscode.window.showInformationMessage(`xroar MCP installed and configured on port ${port}`);
                } else {
                    vscode.window.showErrorMessage(`MCP installation failed with exit code ${code}`);
                }
                resolve();
            });
        });
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
    let installDisposable = vscode.commands.registerCommand('mcp.install', installMcp);
    
    context.subscriptions.push(startDisposable);
    context.subscriptions.push(stopDisposable);
    context.subscriptions.push(statusDisposable);
    context.subscriptions.push(testDisposable);
    context.subscriptions.push(buildDisposable);
    context.subscriptions.push(testsDisposable);
    context.subscriptions.push(installDisposable);
    
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