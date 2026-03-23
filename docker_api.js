const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = 8002;

// Execute commands and return promises
const runCommand = (cmd) => new Promise((resolve, reject) => {
    exec(cmd, { windowsHide: true }, (error, stdout, stderr) => {
        if (error) {
            reject({ error, stdout, stderr });
        } else {
            resolve({ stdout, stderr });
        }
    });
});

const sanitizeName = (value) =>
    String(value).trim().replace(/[^a-zA-Z0-9_.-]/g, '_');

app.post('/start-project', async (req, res) => {
    const { userId, projectId, pythonVersion, projectPath } = req.body;

    if (!userId || !projectId || !pythonVersion || !projectPath) {
        return res.status(400).json({
            error: 'Missing required fields: userId, projectId, pythonVersion, projectPath'
        });
    }

    const containerName = `${sanitizeName(userId)}_${sanitizeName(projectId)}`;

    // IMPORTANT: use your custom built IDE image, not plain python slim
    const image = `ide-python-${pythonVersion}`;

    // 1. Check if Docker is running
    try {
        await runCommand('docker info');
    } catch (e) {
        return res.status(500).json({
            error: 'Docker is not running or not accessible. Please start Docker Desktop.'
        });
    }

    // 2. Check if container already exists
    try {
        const { stdout } = await runCommand('docker ps -a --format "{{.Names}}"');
        const existing = stdout.split(/\r?\n/).map(x => x.trim()).filter(Boolean);

        if (existing.includes(containerName)) {
            const running = await runCommand('docker ps --format "{{.Names}}"');
            const runningList = running.stdout.split(/\r?\n/).map(x => x.trim()).filter(Boolean);

            if (runningList.includes(containerName)) {
                return res.json({
                    status: 'success',
                    message: 'Container already running',
                    containerName,
                    image
                });
            } else {
                await runCommand(`docker start ${containerName}`);
                return res.json({
                    status: 'success',
                    message: 'Container restarted',
                    containerName,
                    image
                });
            }
        }
    } catch (e) {
        console.error('Error checking existing containers:', e);
    }

    // 3. Normalize path for Docker volume mounting
    const normalizedPath = projectPath.replace(/\\/g, '/');

    // 4. Run the container
    const runCmd =
        `docker run -itd ` +
        `--name ${containerName} ` +
        `--cpus="0.5" -m 512m --pids-limit 100 ` +
        `-v "${normalizedPath}:/app" ` +
        `-w /app ` +
        `${image} tail -f /dev/null`;

    try {
        await runCommand(runCmd);
        res.json({
            status: 'success',
            message: 'Container created and started successfully',
            containerName,
            image
        });
    } catch (e) {
        const errText = (e.stderr || e.error.message || '').toLowerCase();

        if (
            errText.includes('not found') ||
            errText.includes('manifest unknown') ||
            errText.includes('pull access denied')
        ) {
            return res.status(404).json({
                error: `Image ${image} not found. Build ide-python-${pythonVersion} first.`
            });
        }

        res.status(500).json({
            error: 'Failed to start container',
            details: e.stderr || e.error.message
        });
    }
});

app.post('/execute-command', async (req, res) => {
    const { userId, projectId, command, workingDir } = req.body;

    if (!userId || !projectId || !command) {
        return res.status(400).json({ error: 'Missing required fields' });
    }

    const containerName = `${sanitizeName(userId)}_${sanitizeName(projectId)}`;

    // 1. Check if container is running
    try {
        const { stdout } = await runCommand('docker ps --format "{{.Names}}"');
        const running = stdout.split(/\r?\n/).map(x => x.trim()).filter(Boolean);

        if (!running.includes(containerName)) {
            return res.status(404).json({
                error: 'Container is not running. Please start the project first.'
            });
        }
    } catch (e) {
        return res.status(500).json({
            error: 'Failed to check container status',
            details: e.stderr
        });
    }

    // 2. Execute command inside container
    let commandWithCwd = command;
    if (workingDir && typeof workingDir === 'string' && workingDir.trim()) {
        const escapedDir = workingDir.trim().replace(/"/g, '\\"');
        commandWithCwd = `cd "${escapedDir}" && ${command}`;
    }

    const escapedCommand = commandWithCwd.replace(/"/g, '\\"');

    // use sh for better compatibility with slim images
    const execCmd = `docker exec ${containerName} sh -c "${escapedCommand}"`;

    try {
        const { stdout, stderr } = await runCommand(execCmd);
        res.json({ status: 'success', stdout, stderr });
    } catch (e) {
        res.status(500).json({
            error: 'Command execution failed or returned error exit code',
            stdout: e.stdout || '',
            stderr: e.stderr || e.error.message
        });
    }
});

app.post('/stop-project', async (req, res) => {
    const { userId, projectId } = req.body;

    if (!userId || !projectId) {
        return res.status(400).json({ error: 'Missing required fields' });
    }

    const containerName = `${sanitizeName(userId)}_${sanitizeName(projectId)}`;

    try {
        await runCommand(`docker stop ${containerName}`);
    } catch (e) {
        const errText = (e.stderr || '').toLowerCase();
        if (!errText.includes('no such container')) {
            return res.status(500).json({
                error: 'Failed to stop container',
                details: e.stderr || e.error.message
            });
        }
    }

    try {
        await runCommand(`docker rm ${containerName}`);
        res.json({
            status: 'success',
            message: 'Container stopped and removed successfully'
        });
    } catch (e) {
        const errText = (e.stderr || '').toLowerCase();
        if (errText.includes('no such container')) {
            return res.json({
                status: 'success',
                message: 'Container already stopped and removed'
            });
        }

        res.status(500).json({
            error: 'Failed to remove container',
            details: e.stderr || e.error.message
        });
    }
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`Docker Isolation API running on http://127.0.0.1:${PORT}`);
});