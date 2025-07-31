import express from 'express';
import { makeWASocket, DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs/promises';
import qrcode from 'qrcode';

// --- Setup for ES Modules __dirname and __filename ---
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- Persistent Storage Path ---
const SESSION_PATH = process.env.WA_SESSION_PATH || path.resolve(__dirname, 'baileys_auth_info');

// --- Express Server Setup ---
const app = express();
const port = process.env.PORT || 3000;

app.use(express.urlencoded({ extended: true }));

// --- Baileys Global State Variables ---
let sock = null;
let qrCodeData = null;
let linkingInProgress = false;

// --- Function to Start/Manage Baileys Connection ---
async function startBaileys() {
    if (linkingInProgress && sock) {
        if (sock.ws.readyState === sock.ws.OPEN) {
            console.log("Bot already connected and active.");
            return;
        }
        console.log("Linking process already in progress.");
        return;
    }

    linkingInProgress = true;
    qrCodeData = null;

    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

    // --- CRITICAL FIX: Updated the version string for compatibility ---
    const version = [2, 3000, 1023223821];

    sock = makeWASocket({
        auth: state,
        // The version string is now explicitly set for stability
        version: version, 
        // The browser option can be omitted or updated if needed, but this version property is more direct
        browser: ['My Baileys Bot', 'Chrome', '1.0'] 
    });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error instanceof Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Connection closed. Reconnecting:', shouldReconnect);
            sock = null;

            if (shouldReconnect) {
                console.log('Attempting to reconnect Baileys in 30 seconds...');
                setTimeout(() => startBaileys(), 30000);
            } else {
                console.log('Logged out. Please link again via /link.');
                linkingInProgress = false;
                qrCodeData = null;
                try {
                    await fs.rm(SESSION_PATH, { recursive: true, force: true });
                    console.log('Deleted old session data.');
                } catch (err) {
                    console.error('Error deleting session data:', err);
                }
            }
        } else if (connection === 'open') {
            console.log('WhatsApp connection opened!');
            linkingInProgress = false;
            qrCodeData = null;
        }

        if (qr) {
            console.log('QR Code received from connection.update event.');
            try {
                const qrImage = await qrcode.toDataURL(qr, { type: 'image/png' });
                qrCodeData = qrImage;
                console.log('Generated QR code image for display.');
            } catch (e) {
                console.error("Error generating QR code:", e);
                qrCodeData = "Error generating QR code. Check logs.";
            }
        }
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        for (const msg of messages) {
            if (!msg.key.fromMe) {
                const messageText = msg.message?.conversation || msg.message?.extendedTextMessage?.text || JSON.stringify(msg.message);
                console.log(`Message received from another source (not this bot): ${messageText}`);

                if (msg.key.remoteJid && msg.key.id) {
                    try {
                        await sock.sendMessage(msg.key.remoteJid, {
                            delete: msg.key
                        });
                        console.log(`Successfully deleted message with ID: ${msg.key.id}`);
                    } catch (error) {
                        console.error(`Failed to delete message with ID: ${msg.key.id}:`, error);
                    }
                }
            }
        }
    });

    console.log("Baileys socket instance created. Event listeners set up.");
}

// --- Express Routes ---

app.get('/', (req, res) => {
    res.send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>WhatsApp Bot</title>
            <style>
                body { font-family: sans-serif; text-align: center; padding: 50px; }
                h1 { color: #333; }
                p { color: #666; }
                a.button {
                    display: inline-block;
                    background-color: #28a745;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-size: 1.2em;
                    margin-top: 20px;
                }
                a.button:hover { background-color: #218838; }
            </style>
        </head>
        <body>
            <h1>WhatsApp Bot Running</h1>
            <p>Your bot is active, but not yet linked to an account.</p>
            <a class="button" href="/link">Tap to Generate QR Code</a>
        </body>
        </html>
    `);
});

app.get('/link', (req, res) => {
    if (!linkingInProgress && !sock) {
        startBaileys();
    }

    if (sock && sock.ws.readyState === sock.ws.OPEN) {
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Bot Connected</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 50px; }
                    h1 { color: #28a745; }
                    p { color: #666; }
                </style>
            </head>
            <body>
                <h1>WhatsApp Bot Connected!</h1>
                <p>Your bot is already active and linked to your WhatsApp account.</p>
            </body>
            </html>
        `);
    }

    if (linkingInProgress && qrCodeData) {
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Link WhatsApp Account</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 20px; }
                    .qr-container { margin: 20px auto; padding: 10px; border: 1px solid #ccc; width: 300px; }
                    .note { color: gray; font-size: 0.9em; margin-top: 20px; }
                </style>
            </head>
            <body>
                <h1>Scan to Link WhatsApp Account</h1>
                <p>Open WhatsApp on your phone, go to **Settings / Linked Devices**, then tap **Link a Device** and scan this QR code.</p>
                <div class="qr-container">
                    <img src="${qrCodeData}" alt="QR Code" />
                </div>
                <p class="note">This code will expire. If it does, simply refresh this page for a new one.</p>
            </body>
            </html>
        `);
    } else {
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Link WhatsApp Account</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 20px; }
                    .status { margin-top: 20px; font-weight: bold; }
                </style>
            </head>
            <body>
                <h1>Linking WhatsApp Account</h1>
                <p>Generating QR code. Please wait a few moments and **refresh this page** to see the QR code.</p>
                <p class="status">Status: Initializing...</p>
            </body>
            </html>
        `);
    }
});


app.listen(port, () => {
    console.log(`Server listening on port ${port}`);
    startBaileys();
});
