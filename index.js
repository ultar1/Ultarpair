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
const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN;
const APP_URL = process.env.APP_URL; // Your app's public URL (e.g., https://your-app.onrender.com)
const PORT = process.env.PORT || 3000;

if (!TELEGRAM_TOKEN || !APP_URL) {
    console.error(chalk.red('Error: TELEGRAM_TOKEN and APP_URL environment variables must be set.'));
    process.exit(1);
}

// --- TELEGRAM BOT SETUP (WEBHOOK MODE) ---
const bot = new TelegramBot(TELEGRAM_TOKEN);
const webhookUrl = `${APP_URL}/bot${TELEGRAM_TOKEN}`;
bot.setWebHook(webhookUrl);

const app = express();
app.use(express.json());

// This is the endpoint Telegram will send updates to
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

// This is the fixed /reqpair command
bot.onText(/\/reqpair(.*)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const phoneNumber = match[1] ? match[1].trim() : '';

    if (!phoneNumber || !/^\+\d{10,}$/.test(phoneNumber)) {
        bot.sendMessage(chatId, "Please provide a valid WhatsApp number including the country code.\n\nExample: `/reqpair +1234567890`", { parse_mode: 'Markdown'});
        return;
    }

    const sessionDir = `./temp_session_${phoneNumber.replace('+', '')}`;

    try {
        if (fs.existsSync(sessionDir)) {
            fs.rmSync(sessionDir, { recursive: true, force: true });
        }

        await bot.sendMessage(chatId, "Request received. Generating pairing code...");

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const waBot = makeWASocket({
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            auth: state,
            browser: ['Session Generator', 'Chrome', '1.0.0']
        });

        const pairingCode = await waBot.requestPairingCode(phoneNumber);
        await bot.sendMessage(chatId, `Your pairing code is: *${pairingCode}*\n\nEnter this code on your WhatsApp device. The session ID will be sent to your WhatsApp chat upon connection.`, { parse_mode: 'Markdown' });

        waBot.ev.on('creds.update', saveCreds);

        waBot.ev.on('connection.update', async (update) => {
            if (update.connection === 'open') {
                await bot.sendMessage(chatId, "Successfully paired! Generating and sending session string to your WhatsApp...");

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
                await bot.sendMessage(chatId, "Your session ID has been sent to your WhatsApp. You can now use it in your main bot's deployment.");
                
                await waBot.ws.close();
                fs.rmSync(sessionDir, { recursive: true, force: true });
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
