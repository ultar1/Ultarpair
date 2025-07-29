const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const chalk = require('chalk');
const qrcode = require('qrcode-terminal');

const PORT = process.env.PORT || 3000;
const app = express();
app.use(express.json());

// Main endpoint to start the session generation
app.get('/', (req, res) => {
    res.send('Session Generator is running. Check logs for QR code.');
    generateSession(res);
});

app.listen(PORT, () => {
    console.log(chalk.green(`Server is running on port ${PORT}`));
    console.log(chalk.yellow(`Open your app's public URL in a browser to start the session generation.`));
});

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
            browser: ['Session Generator', 'Chrome', '1.0.0']
        });

        bot.ev.on('creds.update', saveCreds);

        bot.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                console.log(chalk.yellow('Scan the QR code below:'));
                qrcode.generate(qr, { small: true });
            }

            if (connection === 'open') {
                console.log(chalk.green('Successfully connected! Generating session ID...'));
                
                const zip = new JSZip();
                const files = fs.readdirSync(sessionDir);
                for (const file of files) {
                    zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                }

                const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                const sessionId = buffer.toString('base64');
                
                const message = `Here is your SESSION_ID:\n\n${sessionId}\n\nCopy this and add it to your main bot's environment variables.`;
                
                await bot.sendMessage(bot.user.id, { text: message });
                console.log(chalk.cyan('Session ID has been sent to your WhatsApp.'));
                
                await bot.ws.close();
                // Clean shutdown
                process.exit(0);
            }

            if (connection === 'close') {
                console.log(chalk.red('Connection closed.'));
                if (fs.existsSync(sessionDir)) {
                    fs.rmSync(sessionDir, { recursive: true, force: true });
                }
                 process.exit(1);
            }
        });

    } catch (error) {
        console.error(chalk.red("Session generation failed:"), error);
        process.exit(1);
    }
}
