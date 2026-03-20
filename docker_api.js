const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = 8002;

// Execute commands and return promises
const runCommand = (cmd) => new Promise((resolve, reject) => {
    exec(cmd, (error, stdout, stderr) => {
        if (error) {
            reject({ error, stdout, stderr });
        } else {
            resolve({ stdout, stderr });
        }
    });
});

app.post('/start-project', async (req, res) => {
    const { userId, projectId, pythonVersion, projectPath } = req.body;

    if (!userId || !projectId || !pythonVersion || !projectPath) {
        return res.status(400).json({ error: 'Missing required fields: userId, projectId, pythonVersion, projectPath' });
    }

    const containerName = `${userId}_${projectId}`;
    const image = `python:${pythonVersion}-slim`;

    // 1. Check if Docker is running
    try {
        await runCommand('docker info');
    } catch (e) {
        return res.status(500).json({ error: 'Docker is not running or not accessible. Please start Docker Desktop.' });
    }

    // 2. Check if container already exists
    try {
        const { stdout } = await runCommand('docker ps -a --format "{{.Names}}"');
        if (stdout.includes(containerName)) {
            // Container exists, if it's running we return success, if stopped we start it
            const running = await runCommand('docker ps --format "{{.Names}}"');
            if (running.stdout.includes(containerName)) {
                return res.json({ status: 'success', message: 'Container already running', containerName });
            } else {
                await runCommand(`docker start ${containerName}`);
                return res.json({ status: 'success', message: 'Container restarted', containerName });
            }
        }
    } catch (e) {
        console.error("Error checking existing containers:", e);
    }

    // 3. Normalize path for Docker volume mounting and escape quotes
    const normalizedPath = projectPath.replace(/\\/g, '/');

    // 4. Run the container with strict constraints
    // cpu 0.5, memory 512m, pids 100, detached, tail -f /dev/null keeps it alive
    const runCmd = `docker run -itd --name ${containerName} --cpus="0.5" -m 512m --pids-limit 100 -v "${normalizedPath}:/app" -w /app ${image} tail -f /dev/null`;

    try {
        await runCommand(runCmd);
        res.json({ status: 'success', message: 'Container created and started successfully', containerName });
    } catch (e) {
        const errText = (e.stderr || e.error.message || '').toLowerCase();
        if (errText.includes('not found') || errText.includes('manifest unknown') || errText.includes('pull access denied')) {
            // Provide a better error message if the image needs to be pulled but fails
            return res.status(404).json({ error: `Image ${image} not found. Docker might need to pull it first, or it doesn't exist.` });
        }
        res.status(500).json({ error: 'Failed to start container', details: e.stderr || e.error.message });
    }
});

app.post('/execute-command', async (req, res) => {
    const { userId, projectId, command, workingDir } = req.body;

    if (!userId || !projectId || !command) {
        return res.status(400).json({ error: 'Missing required fields' });
    }

    const containerName = `${userId}_${projectId}`;

    // 1. Check if container is running
    try {
        const { stdout } = await runCommand('docker ps --format "{{.Names}}"');
        if (!stdout.includes(containerName)) {
            return res.status(404).json({ error: 'Container is not running. Please start the project first.' });
        }
    } catch (e) {
        return res.status(500).json({ error: 'Failed to check container status', details: e.stderr });
    }

    // 2. Execute command inside container
    let commandWithCwd = command;
    if (workingDir && typeof workingDir === 'string' && workingDir.trim()) {
        const escapedDir = workingDir.trim().replace(/"/g, '\\"');
        commandWithCwd = `cd "${escapedDir}" && ${command}`;
    }

    // Escape double quotes inside the command to ensure bash -c gets the full string securely
    const escapedCommand = commandWithCwd.replace(/"/g, '\\"');
    const execCmd = `docker exec ${containerName} bash -c "${escapedCommand}"`;

    try {
        const { stdout, stderr } = await runCommand(execCmd);
        res.json({ status: 'success', stdout, stderr });
    } catch (e) {
        // e.error.code won't necessarily be 0, meaning the command errored out
        // We still want to return the stdout and stderr from the command execution to the user
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

    const containerName = `${userId}_${projectId}`;

    try {
        await runCommand(`docker stop ${containerName}`);
        await runCommand(`docker rm ${containerName}`);
        res.json({ status: 'success', message: 'Container stopped and removed successfully' });
    } catch (e) {
        const errText = (e.stderr || '').toLowerCase();
        if (errText.includes('no such container')) {
            return res.json({ status: 'success', message: 'Container already stopped and removed' });
        }
        res.status(500).json({ error: 'Failed to stop/remove container', details: e.stderr || e.error.message });
    }
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`Docker Isolation API running on http://127.0.0.1:${PORT}`);
});
