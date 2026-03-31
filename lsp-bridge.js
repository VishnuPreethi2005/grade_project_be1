/**
 * lsp-bridge.js
 * â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
 * Spawns the pyright-langserver and bridges it to Monaco via WebSocket.
 * Run with: node lsp-bridge.js
 */

const { WebSocketServer } = require('ws');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const LSP_PORT = 8080;
const PYRIGHT_BIN = path.join(__dirname, 'node_modules', '.bin', 'pyright-langserver');

function getWorkspaceRoot(reqUrl) {
    const fallbackRoot = process.cwd();

    try {
        const requestUrl = new URL(reqUrl, `http://localhost:${LSP_PORT}`);
        const rootParam = requestUrl.searchParams.get('root');
        return rootParam ? decodeURIComponent(rootParam) : fallbackRoot;
    } catch (error) {
        console.error('[LSP Bridge] Failed to parse workspace root from URL:', error.message);
        return fallbackRoot;
    }
}

function getPyrightLaunchConfig() {
    const pyrightArgs = ['--stdio'];

    if (process.platform === 'win32') {
        return {
            command: `${PYRIGHT_BIN}.cmd`,
            args: pyrightArgs,
            options: {
                shell: true
            }
        };
    }

    return {
        command: PYRIGHT_BIN,
        args: pyrightArgs,
        options: {}
    };
}

const wss = new WebSocketServer({ port: LSP_PORT });
console.log(`[LSP Bridge] WebSocket server started on ws://localhost:${LSP_PORT}`);

wss.on('connection', (ws, req) => {
    const workspaceRoot = getWorkspaceRoot(req.url);
    console.log(`[LSP Bridge] Client connected. Workspace: ${workspaceRoot}`);

    // Spawn Pyright language server
    const launchConfig = getPyrightLaunchConfig();
    console.log(`[LSP Bridge] Starting pyright with command: ${launchConfig.command} ${launchConfig.args.join(' ')}`);
    const pyright = spawn(launchConfig.command, launchConfig.args, {
        cwd: workspaceRoot,
        windowsHide: true,
        ...launchConfig.options
    });

    pyright.on('error', (err) => {
        console.error('[LSP Bridge] Failed to start pyright:', err.message);
        ws.close();
    });

    pyright.stdout.once('data', () => {
        console.log('[LSP Bridge] Pyright started successfully.');
    });

    pyright.on('exit', (code) => {
        console.log(`[LSP Bridge] Pyright exited with code ${code}`);
        ws.close();
    });

    // --- LSP uses Content-Length framing ---
    let buffer = Buffer.alloc(0);

    pyright.stdout.on('data', (data) => {
        buffer = Buffer.concat([buffer, data]);
        while (true) {
            const str = buffer.toString('utf8');
            const headerEnd = str.indexOf('\r\n\r\n');
            if (headerEnd === -1) break;

            const header = str.substring(0, headerEnd);
            const lenMatch = header.match(/Content-Length:\s*(\d+)/i);
            if (!lenMatch) break;

            const contentLength = parseInt(lenMatch[1], 10);
            const bodyStart = headerEnd + 4;
            if (buffer.length < bodyStart + contentLength) break;

            const body = buffer.slice(bodyStart, bodyStart + contentLength).toString('utf8');
            buffer = buffer.slice(bodyStart + contentLength);

            try {
                if (ws.readyState === ws.OPEN) {
                    ws.send(body);
                }
            } catch (e) {
                console.error('[LSP Bridge] Error sending to client:', e.message);
            }
        }
    });

    pyright.stderr.on('data', (data) => {
        console.error('[LSP Bridge] pyright stderr:', data.toString());
    });

    // Monaco â†’ Pyright
    ws.on('message', (rawMsg) => {
        try {
            const msg = rawMsg.toString('utf8');
            const encoded = Buffer.from(msg, 'utf8');
            const header = `Content-Length: ${encoded.length}\r\n\r\n`;
            pyright.stdin.write(header + msg);
        } catch (e) {
            console.error('[LSP Bridge] Error sending to pyright:', e.message);
        }
    });

    ws.on('close', () => {
        console.log('[LSP Bridge] Client disconnected, killing pyright.');
        pyright.kill();
    });
});
