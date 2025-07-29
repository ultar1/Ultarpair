const TelegramBot = require('node-telegram-bot-api');
const {
    default: makeWASocket,
    useMultiFileAuthState
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const fs = require('fs');
const JSZip = require('jszip');
const chalk = require('chalk');

// --- CONFIGURATION ---
// Add your Telegram Bot Token here
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_TOKEN || '8029175609:AAFyEm6APB8giEJh7-nImaAaFRA0JP2caMY';

// --- TELEGRAM BOT SETUP ---
const bot = new TelegramBot(TELEGRAM_BOT_TOKEN, { polling: true });
console.log(chalk.green('Telegram Bot is running...'));

bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id, "Welcome! Use /reqpair <whatsapp_number_with_country_code> to get your session ID.");
});

bot.onText(/\/reqpair (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const phoneNumber = match[1];

    if (!phoneNumber || !/^\+\d+$/.test(phoneNumber)) {
        bot.sendMessage(chatId, "Please provide a valid WhatsApp number including the country code (e.g., /reqpair +1234567890).");
        return;
    }

    const sessionDir = `./temp_${phoneNumber}`;

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
        await bot.sendMessage(chatId, `Your pairing code is: *${pairingCode}*\n\nEnter this code on your WhatsApp device.`, { parse_mode: 'Markdown' });

        waBot.ev.on('creds.update', saveCreds);

        waBot.ev.on('connection.update', async (update) => {
            if (update.connection === 'open') {
                await bot.sendMessage(chatId, "Successfully paired! Generating your session string...");

                const zip = new JSZip();
                const files = fs.readdirSync(sessionDir);
                for (const file of files) {
                    const data = fs.readFileSync(`${sessionDir}/${file}`);
                    zip.file(file, data);
                }

                const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                const sessionId = buffer.toString('base64');
                
                const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\`\n\nCopy this and add it as an environment variable in your main bot's deployment.`;
                
                await waBot.sendMessage(`${phoneNumber}@s.whatsapp.net`, { text: message });
                await bot.sendMessage(chatId, "Your session ID has been sent to your WhatsApp personal chat. You can now close this bot.");
                
                // Clean up
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
