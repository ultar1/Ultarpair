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

app.post('/pair', async (req, res) => {
    const phoneNumber = req.body.phoneNumber;
    if (!phoneNumber || !/^\+\d{10,}$/.test(phoneNumber)) {
        return res.status(400).send(getPage('<h1>Error</h1><p>Invalid phone number format. Please go back and try again.</p>'));
    }

    const sessionDir = path.join(__dirname, `session_${phoneNumber.replace('+', '')}`);
    if (fs.existsSync(sessionDir)) {
        fs.rmSync(sessionDir, { recursive: true, force: true });
    }

    try {
        const logger = pino({ level: 'trace' });
        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const bot = makeWASocket({
            logger,
            printQRInTerminal: false,
            auth: state,
            browser: ['Server Pairing', 'Chrome', '1.0.0']
        });

        // Add a delay to ensure the socket is ready before requesting the code
        await new Promise(resolve => setTimeout(resolve, 3000));
        const code = await bot.requestPairingCode(phoneNumber);
        
        res.send(getPage(`<h1>Pairing Code</h1><p>Your code for ${phoneNumber} is:</p><h2 class="message">${code}</h2><p>Enter this code in WhatsApp on your phone. The session will be sent to your WhatsApp chat after you connect.</p>`));

        bot.ev.on('creds.update', saveCreds);

        bot.ev.on('connection.update', async (update) => {
            if (update.connection === 'open') {
                console.log(chalk.green(`Paired successfully with ${phoneNumber}. Sending session...`));
                const zip = new JSZip();
                const files = fs.readdirSync(sessionDir);
                for (const file of files) {
                    zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                }
                const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                const sessionId = buffer.toString('base64');
                const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;

                await bot.sendMessage(bot.user.id, { text: message });
                console.log(chalk.cyan('Session ID sent.'));

                await bot.ws.close();
                fs.rmSync(sessionDir, { recursive: true, force: true });
                // Cleanly exit to allow server to restart if needed
                setTimeout(() => process.exit(0), 2000);
            }

            if (update.connection === 'close') {
                 if (fs.existsSync(sessionDir)) {
                    fs.rmSync(sessionDir, { recursive: true, force: true });
                }
            }
        });

    } catch (error) {
        console.error(chalk.red("Pairing process failed:"), error);
        res.status(500).send(getPage('<h1>Error</h1><p>Could not initiate pairing. The server might be blocked or the number is invalid.</p>'));
    }
});

app.listen(PORT, () => {
    console.log(chalk.green(`Server is running on port ${PORT}`));
});
