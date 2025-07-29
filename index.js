const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    makeCacheableSignalKeyStore
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
    let waBot;
    let connectionTimeout;

    const cleanup = () => {
        if (waBot) {
            waBot.ws.close();
        }
        if (fs.existsSync(sessionDir)) {
            fs.rmSync(sessionDir, { recursive: true, force: true });
        }
        if (connectionTimeout) {
            clearTimeout(connectionTimeout);
        }
    };

    try {
        if (fs.existsSync(sessionDir)) {
            fs.rmSync(sessionDir, { recursive: true, force: true });
        }
        fs.mkdirSync(sessionDir, { recursive: true });

        await bot.sendMessage(chatId, "Request received. Initializing connection... This may take up to 30 seconds.");
        
        const logger = pino({ level: 'silent' });
        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        
        waBot = makeWASocket({
            logger,
            printQRInTerminal: false,
            auth: {
                creds: state.creds,
                keys: makeCacheableSignalKeyStore(state.keys, logger),
            },
            browser: ['Session Generator', 'Chrome', '1.0.0']
        });

        // --- Timeout Logic ---
        connectionTimeout = setTimeout(() => {
            bot.sendMessage(chatId, "Connection timed out. The server is likely blocked by WhatsApp. Please try again later or use a different deployment method.");
            cleanup();
        }, 30000); // 30 second timeout

        waBot.ev.on('creds.update', saveCreds);

        waBot.ev.on('connection.update', async (update) => {
            const { connection } = update;

            if (connection === 'open') {
                clearTimeout(connectionTimeout); // Success, clear the timeout
                
                try {
                    const pairingCode = await waBot.requestPairingCode(phoneNumber);
                    await bot.sendMessage(chatId, `Connection ready. Your pairing code is: *${pairingCode}*\n\nEnter this on your device.`, { parse_mode: 'Markdown' });

                    // This second 'open' event happens AFTER the user pairs successfully.
                    waBot.ev.once('connection.update', async (finalUpdate) => {
                         if (finalUpdate.connection === 'open') {
                            await bot.sendMessage(chatId, "Successfully paired! Generating session string...");
                            const zip = new JSZip();
                            const files = fs.readdirSync(sessionDir);
                            for (const file of files) {
                                zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                            }
                            const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                            const sessionId = buffer.toString('base64');
                            const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;
                            await waBot.sendMessage(`${phoneNumber}@s.whatsapp.net`, { text: message });
                            await bot.sendMessage(chatId, "Session ID has been sent to your WhatsApp.");
                            cleanup();
                         }
                    });
                } catch (error) {
                     await bot.sendMessage(chatId, "Failed to request pairing code. The connection may have been blocked.");
                     cleanup();
                }
            }

            if (connection === 'close') {
                clearTimeout(connectionTimeout);
                cleanup();
            }
        });

    } catch (error) {
        console.error("Pairing Error:", error);
        bot.sendMessage(chatId, "A critical error occurred. Please check the logs.");
        cleanup();
    }
});
