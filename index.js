import makeWASocket, { DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import path from 'path'; // Import path module
import { fileURLToPath } from 'url'; // If using ES modules

// If using ES Modules (type: "module" in package.json)
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Define the path for session data to be stored on Render's persistent disk
// This path will be where your Render Persistent Disk is mounted
// We'll define this as an environment variable in Render later (e.g., WA_SESSION_PATH)
const SESSION_PATH = process.env.WA_SESSION_PATH || path.resolve(__dirname, 'baileys_auth_info');


async function connectToWhatsApp() {
    // Use the defined SESSION_PATH for storing auth credentials
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: true, // Crucial for initial setup (QR code in logs)
        browser: ['My Baileys Bot', 'Chrome', '1.0'] // Custom browser name
    });

    // ... (rest of your bot code, connection.update, messages.upsert, creds.update events)

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error instanceof Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Connection closed. Reconnecting:', shouldReconnect);
            if (shouldReconnect) {
                connectToWhatsApp();
            } else {
                console.log('Logged out. Please re-run the bot and scan QR again.');
                // Handle a full logout scenario, maybe exit process or reset session
            }
        } else if (connection === 'open') {
            console.log('WhatsApp connection opened!');
        }
    });

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        // Your message handling logic here
        // ...
    });

    sock.ev.on('creds.update', saveCreds);
}

connectToWhatsApp();
