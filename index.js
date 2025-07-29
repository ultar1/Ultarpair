const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion
} = require('baileys');
const pino = require('pino');
const { Boom } = require('@hapi/boom');
const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const chalk = require('chalk');
const qrcode = require('qrcode-terminal');

const sessionDir = path.join(__dirname, 'session');

async function connectToWhatsApp() {
    console.log(chalk.yellow('Starting session generator...'));

    if (fs.existsSync(sessionDir)) {
        fs.rmSync(sessionDir, { recursive: true, force: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version, isLatest } = await fetchLatestBaileysVersion();
    console.log(chalk.blue(`Using Baileys version ${version.join('.')}, isLatest: ${isLatest}`));

    const bot = makeWASocket({
        version,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: true, // This will be handled manually
        auth: state,
        browser: ['Ultar-MD (Gen)', 'Chrome', '1.0.0']
    });

    bot.ev.on('creds.update', saveCreds);

    bot.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log(chalk.yellow('\nScan the QR code below using your WhatsApp app:'));
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
            const message = `Here is your SESSION_ID:\n\n\`\`\`${sessionId}\`\`\``;
            
            await bot.sendMessage(bot.user.id, { text: message });
            console.log(chalk.cyan('Session ID has been sent to your WhatsApp. The process will now exit.'));
            
            // Clean shutdown
            await bot.ws.close();
            process.exit(0);
        }

        if (connection === 'close') {
            const reason = new Boom(lastDisconnect?.error)?.output.statusCode;
            if (reason === DisconnectReason.loggedOut) {
                console.log(chalk.red('Device logged out. Please delete the session and try again.'));
            } else {
                console.log(chalk.red('Connection closed. Restarting...'));
                connectToWhatsApp();
            }
        }
    });
}

connectToWhatsApp();
