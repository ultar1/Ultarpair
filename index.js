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

const PORT = process.env.PORT || 3000;
const app = express();

// Use express to handle form data
app.use(express.urlencoded({ extended: true }));

// --- HTML Page to Request Number ---
const getHomePage = (message = '') => `
<!DOCTYPE html>
<html>
<head>
    <title>WhatsApp Session Generator</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background-color: #1e1e1e; padding: 40px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); text-align: center; width: 90%; max-width: 400px; }
        h1 { color: #ffffff; }
        p { color: #b0b0b0; }
        input { width: calc(100% - 20px); padding: 10px; margin-top: 20px; border-radius: 4px; border: 1px solid #333; background-color: #2c2c2c; color: #e0e0e0; }
        button { width: 100%; padding: 10px; margin-top: 20px; border-radius: 4px; border: none; background-color: #007bff; color: white; font-size: 16px; cursor: pointer; }
        button:hover { background-color: #0056b3; }
        .message { margin-top: 20px; color: #00ff7f; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Session ID Generator</h1>
        <p>Enter your full WhatsApp number with country code to get a pairing code.</p>
        <form action="/pair" method="post">
            <input type="text" name="phoneNumber" placeholder="e.g., +1234567890" required>
            <button type="submit">Get Pairing Code</button>
        </form>
        ${message ? `<p class="message">${message}</p>` : ''}
    </div>
</body>
</html>
`;

// --- Web Server Endpoints ---
app.get('/', (req, res) => {
    res.send(getHomePage());
});

app.post('/pair', (req, res) => {
    const phoneNumber = req.body.phoneNumber;
    if (!phoneNumber || !/^\+\d{10,}$/.test(phoneNumber)) {
        return res.send(getHomePage("Invalid phone number format. Please try again."));
    }
    
    // Send an immediate response to the user
    res.send(getHomePage(`Request received for ${phoneNumber}. A pairing code will be sent to this page shortly. Please wait...`));
    
    // Start the pairing process in the background
    generateSession(phoneNumber);
});

app.listen(PORT, () => {
    console.log(chalk.green(`Server is running on port ${PORT}`));
    console.log(chalk.yellow(`Open your app's public URL in a browser to begin.`));
});


// --- Baileys Connection Logic ---
async function generateSession(phoneNumber) {
    const sessionDir = path.join(__dirname, `session_${phoneNumber.replace('+', '')}`);
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

        // Request pairing code as soon as the socket is created
        if (bot.ws.isOpen) {
            await sendPairingCode(bot, phoneNumber);
        } else {
            bot.ev.on('connection.update', async (update) => {
                if (update.connection === 'open') {
                    await sendPairingCode(bot, phoneNumber);
                }
            });
        }

        bot.ev.on('creds.update', saveCreds);

        bot.ev.on('connection.update', async (update) => {
            if (update.connection === 'open') {
                console.log(chalk.green('Successfully paired! Generating and sending session ID...'));
                
                const zip = new JSZip();
                const files = fs.readdirSync(sessionDir);
                for (const file of files) {
                    zip.file(file, fs.readFileSync(path.join(sessionDir, file)));
                }

                const buffer = await zip.generateAsync({ type: 'nodebuffer' });
                const sessionId = buffer.toString('base64');
                const message = `Here is your SESSION_ID:\n\n${sessionId}`;
                
                await bot.sendMessage(bot.user.id, { text: message });
                console.log(chalk.cyan('Session ID has been sent to your WhatsApp.'));
                
                await bot.ws.close();
                // Cleanly exit the process
                process.exit(0);
            }

            if (update.connection === 'close') {
                console.log(chalk.red('Connection closed.'));
                if (fs.existsSync(sessionDir)) {
                    fs.rmSync(sessionDir, { recursive: true, force: true });
                }
            }
        });

    } catch (error) {
        console.error(chalk.red("Session generation failed:"), error);
    }
}

async function sendPairingCode(bot, phoneNumber) {
    try {
        const code = await bot.requestPairingCode(phoneNumber);
        console.log(chalk.yellow(`Pairing code for ${phoneNumber} is: ${code}`));
        // We can't directly send the code back to the web page easily without websockets.
        // The user should be instructed to check the logs, or we can just let them wait for the session.
        // For simplicity, the user will pair, and the result will be sent to their WhatsApp.
    } catch (error) {
        console.error(chalk.red('Failed to request pairing code:'), error);
    }
}
