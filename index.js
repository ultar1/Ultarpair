const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState
} = require('baileys');
const pino = require('pino');
const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const chalk = require('chalk');
const qrcode = require('qrcode');

const PORT = process.env.PORT || 3000;
const app = express();
app.use(express.json());

// --- HTML Page Template ---
const getPage = (content) => `
<!DOCTYPE html>
<html>
<head>
    <title>Session Generator</title>
    <style>
        body { font-family: monospace; background-color: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background-color: #1e1e1e; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); text-align: center; width: 90%; max-width: 500px; }
        h1 { color: #ffffff; }
        p { color: #b0b0b0; }
        img { margin-top: 20px; border: 5px solid #fff; }
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
    generateSession(res);
});

app.listen(PORT, () => {
    console.log(chalk.green(`Server is running on port ${PORT}`));
    console.log(chalk.yellow(`Open your app's public URL in a browser to get the QR code.`));
});

// --- Baileys Connection Logic ---
async function generateSession(res) {
    const sessionDir = path.join(__dirname, 'session');
    if (fs.existsSync(sessionDir)) {
        fs.rmSync(sessionDir, { recursive: true, force: true });
    }

    try {
        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const bot = makeWASocket({
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            auth: state,
            browser: ['Web QR Gen', 'Chrome', '1.0.0']
        });

        bot.ev.on('creds.update', saveCreds);

        bot.ev.on('connection.update', async (update) => {
            const { connection, qr } = update;

            if (qr) {
                const qrImage = await qrcode.toDataURL(qr);
                const content = `
                    <h1>Scan this QR Code</h1>
                    <p>Scan the image below with your WhatsApp app.</p>
                    <img src="${qrImage}" alt="QR Code">
                `;
                if (!res.headersSent) {
                    res.send(getPage(content));
                }
            }

            if (connection === 'open') {
                const content = `<h1>Success!</h1><p>Connected successfully. Generating and sending session ID to your WhatsApp...</p>`;
                if (!res.headersSent) {
                    res.send(getPage(content));
                }
                
                const zip = new JSZip();
                const files = fs.readdirSync(sessionDir);
                for (const file of files) {
                    zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                }
                const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                const sessionId = buffer.toString('base64');
                const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;
                
                await bot.sendMessage(bot.user.id, { text: message });
                console.log(chalk.cyan('Session ID has been sent to your WhatsApp.'));
                
                await bot.ws.close();
                process.exit(0);
            }

            if (connection === 'close') {
                if (!res.headersSent) {
                    res.send(getPage('<h1>Connection Closed</h1><p>The connection was closed. Please try again.</p>'));
                }
                if (fs.existsSync(sessionDir)) {
                    fs.rmSync(sessionDir, { recursive: true, force: true });
                }
            }
        });

    } catch (error) {
        console.error(chalk.red("Session generation failed:"), error);
        if (!res.headersSent) {
            res.status(500).send(getPage('<h1>Error</h1><p>The session generator failed to start.</p>'));
        }
    }
}
