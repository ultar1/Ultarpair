const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    makeCacheableSignalKeyStore
} = require('baileys');
const pino = require('pino');
const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const chalk = chalk;

const PORT = process.env.PORT || 3000;
const app = express();

app.use(express.urlencoded({ extended: true }));

// --- Web Page HTML ---
const getPage = (content) => `
<!DOCTYPE html>
<html>
<head>
    <title>Session Generator</title>
    <style>
        body { font-family: monospace; background-color: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background-color: #1e1e1e; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); text-align: center; width: 90%; max-width: 500px; }
        h1 { color: #ffffff; }
        p, label { color: #b0b0b0; }
        input { width: calc(100% - 20px); padding: 10px; margin-top: 20px; border-radius: 4px; border: 1px solid #333; background-color: #2c2c2c; color: #e0e0e0; }
        button { width: 100%; padding: 10px; margin-top: 20px; border-radius: 4px; border: none; background-color: #007bff; color: white; font-size: 16px; cursor: pointer; }
        .message { margin-top: 20px; color: #00ff7f; word-wrap: break-word; }
    </style>
</head>
<body>
    <div class="container">${content}</div>
</body>
</html>
`;

// --- Web Server Endpoints ---
app.get('/', (req, res) => {
    const form = `
        <h1>Session ID Generator</h1>
        <p>Enter your full WhatsApp number with country code.</p>
        <form action="/pair" method="post">
            <input type="text" name="phoneNumber" placeholder="e.g., +1234567890" required>
            <button type="submit">Get Pairing Code</button>
        </form>
    `;
    res.send(getPage(form));
});

let pairingProcess = {};

app.post('/pair', async (req, res) => {
    const phoneNumber = req.body.phoneNumber;
    if (!phoneNumber || !/^\+\d{10,}$/.test(phoneNumber)) {
        return res.status(400).send(getPage('<h1>Error</h1><p>Invalid phone number format. Please go back and try again.</p>'));
    }

    const processId = Date.now();
    pairingProcess[processId] = { res };
    res.setHeader('Content-Type', 'text/html');
    res.write(getPage(`<h1>Connecting...</h1><p>Attempting to connect to WhatsApp for ${phoneNumber}. This may take up to 45 seconds. Do not close this page.</p>`));

    generateSession(phoneNumber, processId);
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});

// --- Baileys Connection Logic ---
async function generateSession(phoneNumber, processId) {
    const { res } = pairingProcess[processId];
    const sessionDir = path.join(__dirname, `session_${phoneNumber.replace('+', '')}`);
    let bot;
    let timeout;

    const cleanup = () => {
        if (bot) bot.ws.close();
        if (fs.existsSync(sessionDir)) fs.rmSync(sessionDir, { recursive: true, force: true });
        if (timeout) clearTimeout(timeout);
        delete pairingProcess[processId];
    };

    try {
        if (fs.existsSync(sessionDir)) fs.rmSync(sessionDir, { recursive: true, force: true });
        
        const logger = pino({ level: 'silent' });
        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        
        bot = makeWASocket({
            logger,
            printQRInTerminal: false,
            auth: {
                creds: state.creds,
                keys: makeCacheableSignalKeyStore(state.keys, logger),
            },
            browser: ['Server Pairing', 'Chrome', '1.0.0']
        });

        timeout = setTimeout(() => {
            res.end(getPage('<h1>Error</h1><p>Connection timed out. The server is likely blocked by WhatsApp.</p>'));
            cleanup();
        }, 45000); // 45-second timeout

        bot.ev.on('creds.update', saveCreds);

        bot.ev.on('connection.update', async (update) => {
            const { connection } = update;

            if (connection === 'open') {
                clearTimeout(timeout);
                try {
                    const code = await bot.requestPairingCode(phoneNumber);
                    res.write(getPage(`<h1>Pairing Code</h1><p>Your code for ${phoneNumber} is:</p><h2 class="message">${code}</h2><p>Enter this in WhatsApp. The page will update after you connect.</p>`));
                    
                    bot.ev.once('connection.update', async (finalUpdate) => {
                        if (finalUpdate.connection === 'open') {
                            res.write(getPage(`<h1>Success!</h1><p>Paired successfully. Generating and sending session ID to your WhatsApp...</p>`));
                            const zip = new JSZip();
                            const files = fs.readdirSync(sessionDir);
                            for (const file of files) zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                            const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                            const sessionId = buffer.toString('base64');
                            const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;
                            await bot.sendMessage(bot.user.id, { text: message });
                            res.end(getPage(`<h1>Done!</h1><p>Session ID has been sent to your WhatsApp.</p>`));
                            cleanup();
                        }
                    });
                } catch (error) {
                    res.end(getPage('<h1>Error</h1><p>Failed to request pairing code.</p>'));
                    cleanup();
                }
            }

            if (connection === 'close') {
                clearTimeout(timeout);
                if (pairingProcess[processId]) { // Check if response is still open
                    res.end(getPage('<h1>Connection Closed</h1><p>The connection to WhatsApp was closed unexpectedly.</p>'));
                }
                cleanup();
            }
        });

    } catch (error) {
        if (pairingProcess[processId]) {
            res.end(getPage('<h1>Critical Error</h1><p>An unexpected error occurred.</p>'));
        }
        cleanup();
    }
}
