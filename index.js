const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const JSZip = require('jszip');
const chalk = require('chalk');

// --- CONFIGURATION ---
const TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN_HERE';
const APP_URL = process.env.APP_URL;
const PORT = process.env.PORT || 3000;

if (!TELEGRAM_TOKEN || !APP_URL) {
    console.error(chalk.red('Error: TELEGRAM_TOKEN (in code) and APP_URL (in environment variables) must be set.'));
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

    const sessionDir = `./temp_session_${phoneNumber.replace('+', '')}`;
    if (fs.existsSync(sessionDir)) {
        fs.rmSync(sessionDir, { recursive: true, force: true });
    }

    try {
        await bot.sendMessage(chatId, "Request received. Initializing connection...");

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const waBot = makeWASocket({
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            auth: state,
            browser: ['Session Generator', 'Chrome', '1.0.0']
        });

        // We use a flag to ensure we only request the code once.
        let codeRequested = false;

        waBot.ev.on('creds.update', saveCreds);

        waBot.ev.on('connection.update', async (update) => {
            const { connection } = update;

            // This block runs when the connection is fully established.
            if (connection === 'open') {
                // Check if we have already requested the code.
                // This 'open' event can fire multiple times.
                if (!codeRequested) {
                    codeRequested = true;
                    // Now that the connection is ready, we request the code.
                    const pairingCode = await waBot.requestPairingCode(phoneNumber);
                    await bot.sendMessage(chatId, `Connection ready. Your pairing code is: *${pairingCode}*\n\nEnter this on your device.`, { parse_mode: 'Markdown' });
                } else {
                    // This 'open' event happens AFTER the user pairs successfully.
                    await bot.sendMessage(chatId, "Successfully paired! Generating session string...");

                    const zip = new JSZip();
                    const files = fs.readdirSync(sessionDir);
                    for (const file of files) {
                        const data = fs.readFileSync(`${sessionDir}/${file}`);
                        zip.file(file, data);
                    }

                    const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                    const sessionId = buffer.toString('base64');
                    const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;

                    await waBot.sendMessage(`${phoneNumber}@s.whatsapp.net`, { text: message });
                    await bot.sendMessage(chatId, "Session ID has been sent to your WhatsApp. You can now close this bot.");

                    // Clean up
                    await waBot.ws.close();
                    fs.rmSync(sessionDir, { recursive: true, force: true });
                }
            }

            if (connection === 'close') {
                 // You can add logic here if the connection closes unexpectedly
            }
        });

    } catch (error) {
        console.error("Pairing Error:", error);
        bot.sendMessage(chatId, "An error occurred during the pairing process. Please check the logs.");
        if (fs.existsSync(sessionDir)) {
            fs.rmSync(sessionDir, { recursive: true, force: true });
        }
    }
});
