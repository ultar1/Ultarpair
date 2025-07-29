const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const chalk = require('chalk');

// --- CONFIGURATION ---
const TELEGRAM_TOKEN = '8029175609:AAFyEm6APB8giEJh7-nImaAaFRA0JP2caMY';
const APP_URL = process.env.APP_URL;
const PORT = process.env.PORT || 3000;

if (!APP_URL) {
    console.error(chalk.red('Error: APP_URL environment variable must be set.'));
    process.exit(1);
}

// --- TELEGRAM BOT SETUP (WEBHOOK MODE) ---
const bot = new TelegramBot(TELEGRAM_TOKEN);
const cleanAppUrl = APP_URL.replace(/\/$/, '');
const webhookUrl = `${cleanAppUrl}/bot${TELEGRAM_TOKEN}`;
bot.setWebHook(webhookUrl);

const app = express();
app.use(express.json());
app.post(`/bot${TELEGRAM_TOKEN}`, (req, res) => {
    bot.processUpdate(req.body);
    res.sendStatus(200);
});
app.listen(PORT, () => {
    console.log(chalk.green(`Server is running on port ${PORT}`));
    console.log(chalk.blue(`Webhook is set to ${webhookUrl}`));
});

// --- COMMAND HANDLERS ---
bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id, "Welcome! Use /reqpair <whatsapp_number_with_country_code> to get your session ID.");
});

bot.onText(/\/reqpair(.*)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const phoneNumber = match[1] ? match[1].trim() : '';

    if (!phoneNumber || !/^\+\d{10,}$/.test(phoneNumber)) {
        bot.sendMessage(chatId, "Please provide a valid WhatsApp number including the country code.\n\nExample: `/reqpair +1234567890`", { parse_mode: 'Markdown' });
        return;
    }

    const sessionDir = path.join(__dirname, `temp_session_${phoneNumber.replace('+', '')}`);

    try {
        if (fs.existsSync(sessionDir)) {
            fs.rmSync(sessionDir, { recursive: true, force: true });
        }
        // Ensure the directory exists before using it
        fs.mkdirSync(sessionDir, { recursive: true });

        await bot.sendMessage(chatId, "Request received. Initializing connection...");

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const waBot = makeWASocket({
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            auth: state,
            browser: ['Session Generator', 'Chrome', '1.0.0']
        });

        let codeRequested = false;

        waBot.ev.on('creds.update', saveCreds);

        waBot.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect } = update;

            if (connection === 'open') {
                if (!codeRequested) {
                    codeRequested = true;
                    try {
                        const pairingCode = await waBot.requestPairingCode(phoneNumber);
                        await bot.sendMessage(chatId, `Connection ready. Your pairing code is: *${pairingCode}*\n\nEnter this on your device.`, { parse_mode: 'Markdown' });
                    } catch (error) {
                         console.error("Error requesting pairing code:", error);
                         await bot.sendMessage(chatId, "Failed to request pairing code. The WhatsApp connection may have been blocked. Please try again later.");
                    }
                } else {
                    await bot.sendMessage(chatId, "Successfully paired! Generating and sending session string to your WhatsApp...");

                    const zip = new JSZip();
                    const files = fs.readdirSync(sessionDir);
                    for (const file of files) {
                        const data = fs.readFileSync(path.join(sessionDir, file));
                        zip.file(file, data);
                    }

                    const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                    const sessionId = buffer.toString('base64');
                    const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;
                    
                    await waBot.sendMessage(`${phoneNumber}@s.whatsapp.net`, { text: message });
                    await bot.sendMessage(chatId, "Session ID has been sent to your WhatsApp.");
                    
                    await waBot.ws.close();
                }
            }

            if (connection === 'close') {
                console.log('Connection closed.', lastDisconnect?.error);
                if (fs.existsSync(sessionDir)) {
                    fs.rmSync(sessionDir, { recursive: true, force: true });
                }
            }
        });

    } catch (error) {
        console.error("Pairing Error:", error);
        bot.sendMessage(chatId, "A critical error occurred. Please check the logs.");
        if (fs.existsSync(sessionDir)) {
            fs.rmSync(sessionDir, { recursive: true, force: true });
        }
    }
});
