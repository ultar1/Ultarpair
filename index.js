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
app.use(express.urlencoded({ extended: true }));

// --- HTML Page Template ---
const getPage = (content) => `
<!DOCTYPE html><html><head><title>Session Generator</title><style>body{font-family:monospace;background-color:#121212;color:#e0e0e0;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.container{background-color:#1e1e1e;padding:40px;border-radius:8px;text-align:center;width:90%;max-width:500px}h1{color:#fff}p{color:#b0b0b0}img{margin-top:20px;border:5px solid #fff}input{width:calc(100%-20px);padding:10px;margin-top:20px;border-radius:4px;border:1px solid #333;background-color:#2c2c2c;color:#e0e0e0}button,a{display:block;width:100%;box-sizing:border-box;padding:10px;margin-top:20px;border-radius:4px;border:none;background-color:#007bff;color:#fff;font-size:16px;cursor:pointer;text-decoration:none}.message{margin-top:20px;color:#00ff7f;word-wrap:break-word}</style></head><body><div class="container">${content}</div></body></html>`;

// --- Routes ---
app.get('/', (req, res) => {
    const content = `
        <h1>Session Generator</h1>
        <p>Choose your preferred connection method.</p>
        <a href="/qr">Get QR Code</a>
        <form action="/pair" method="post">
            <input type="text" name="phoneNumber" placeholder="Enter number for Pairing Code, e.g., +1234567890" required>
            <button type="submit">Get Pairing Code</button>
        </form>
    `;
    res.send(getPage(content));
});

app.get('/qr', (req, res) => {
    generateSession(res, 'qr');
});

app.post('/pair', (req, res) => {
    const phoneNumber = req.body.phoneNumber;
    if (!phoneNumber || !/^\+\d{10,}$/.test(phoneNumber)) {
        return res.status(400).send(getPage('<h1>Error</h1><p>Invalid phone number. Please go back.</p>'));
    }
    generateSession(res, 'pair', phoneNumber);
});

app.listen(PORT, () => {
    console.log(chalk.green(`✅ Server running on port ${PORT}`));
});

// --- Baileys Logic ---
async function generateSession(res, method, phoneNumber = null) {
    const sessionDir = path.join(__dirname, `session_${Date.now()}`);
    let bot, timeout;

    const cleanup = () => {
        if (bot) bot.ws.close();
        if (fs.existsSync(sessionDir)) fs.rmSync(sessionDir, { recursive: true, force: true });
        if (timeout) clearTimeout(timeout);
    };

    try {
        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        bot = makeWASocket({
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            auth: state,
            browser: ['Web Gen', 'Chrome', '1.0.0']
        });

        bot.ev.on('creds.update', saveCreds);

        timeout = setTimeout(() => {
            if (!res.headersSent) res.status(500).send(getPage('<h1>Error</h1><p>Connection timed out. WhatsApp may be blocking the server.</p>'));
            cleanup();
        }, 60000);

        bot.ev.on('connection.update', async (update) => {
            const { connection, qr } = update;
            console.log(chalk.yellow('🔄 Connection Update:'), update);

            if (method === 'qr' && qr) {
                const qrImage = await qrcode.toDataURL(qr);
                if (!res.headersSent) res.send(getPage(`<h1>Scan QR Code</h1><img src="${qrImage}" alt="QR Code">`));
            }

            if (connection === 'open') {
                clearTimeout(timeout);

                if (method === 'pair') {
                    try {
                        const code = await bot.requestPairingCode(phoneNumber);
                        if (!res.headersSent) {
                            res.send(getPage(`<h1>Pairing Code</h1><p>Your code is:</p><h2 class="message">${code}</h2><p>Enter this in WhatsApp. Session will be sent after you connect.</p>`));
                        }
                    } catch (err) {
                        console.error(chalk.red('❌ Failed to get pairing code:'), err);
                        if (!res.headersSent) res.status(500).send(getPage('<h1>Error</h1><p>Could not generate pairing code.</p>'));
                        cleanup();
                        return;
                    }
                }

                // Wait for final confirmation
                bot.ev.on('connection.update', async (finalUpdate) => {
                    if (finalUpdate.connection === 'open') {
                        const zip = new JSZip();
                        const files = fs.readdirSync(sessionDir);
                        for (const file of files) {
                            zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                        }
                        const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                        const sessionId = buffer.toString('base64');

                        const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;
                        try {
                            await bot.sendMessage(bot.user.id, { text: message });
                            if (!res.headersSent) {
                                res.send(getPage(`<h1>Done!</h1><p>Session ID has been sent to your WhatsApp.</p>`));
                            }
                        } catch (err) {
                            console.error(chalk.red('❌ Failed to send message:'), err);
                            if (!res.headersSent) res.status(500).send(getPage('<h1>Error</h1><p>Could not send session ID to WhatsApp.</p>'));
                        }
                        cleanup();
                        setTimeout(() => process.exit(0), 2000);
                    }
                });
            }

            if (connection === 'close') {
                console.warn(chalk.red('⚠️ Connection closed.'));
                if (!res.headersSent) res.status(500).send(getPage('<h1>Connection Closed</h1><p>Connection closed unexpectedly. Please try again.</p>'));
                cleanup();
            }
        });

    } catch (error) {
        console.error(chalk.red("❌ Session generation failed:"), error);
        if (!res.headersSent) res.status(500).send(getPage('<h1>Error</h1><p>The generator failed to start.</p>'));
        cleanup();
    }
}
