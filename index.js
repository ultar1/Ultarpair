import express from 'express';
import { makeWASocket, DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs/promises'; // Import fs for potential session cleanup

// --- Setup for ES Modules __dirname ---
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- Persistent Storage Path ---
// This path corresponds to the Render Persistent Disk mount path you configured.
const SESSION_PATH = process.env.WA_SESSION_PATH || path.resolve(__dirname, 'baileys_auth_info');

// --- Express Server Setup ---
const app = express();
const port = process.env.PORT || 3000; // Render sets PORT automatically

// --- Baileys Global Variables ---
let sock = null; // Stores the Baileys socket instance
let qrCodeData = null; // Stores the QR/pairing code string
let linkingInProgress = false; // Flag to manage the linking process state

// --- Baileys Connection Function ---
async function startBaileys() {
    if (linkingInProgress && sock) {
        console.log("Linking process already in progress or bot is running.");
        // If already connected, no need to re-initiate linking unless explicitly logged out
        if (sock.ws.readyState === sock.ws.OPEN) return;
    }

    linkingInProgress = true;
    qrCodeData = null; // Clear any old code when starting a new linking attempt

    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

    sock = makeWASocket({
        auth: state,
        // printQRInTerminal is deprecated and removed here
        browser: ['My Baileys Bot', 'Chrome', '1.0'] // Custom browser name
    });

    // --- Event Listeners for Baileys ---
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error instanceof Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Connection closed. Reconnecting:', shouldReconnect);
            sock = null; // Clear socket instance
            if (shouldReconnect) {
                // If it's a transient disconnect, retry connection
                console.log('Attempting to reconnect Baileys...');
                startBaileys();
            } else {
                // If logged out, clear session and indicate need for new link
                console.log('Logged out. Please link again via /link.');
                linkingInProgress = false; // Allow new linking attempt
                qrCodeData = null; // Clear any old QR/pairing code
                // Optionally, delete auth info on full logout to force a fresh start
                try {
                    await fs.rm(SESSION_PATH, { recursive: true, force: true });
                    console.log('Deleted old session data.');
                } catch (err) {
                    console.error('Error deleting session data:', err);
                }
            }
        } else if (connection === 'open') {
            console.log('WhatsApp connection opened!');
            linkingInProgress = false; // Linking complete
            qrCodeData = null; // Clear QR data once connected
        }

        // The 'qr' property in connection.update will contain the QR code string OR the pairing code string
        if (qr) {
            console.log('QR/Pairing Code received:', qr);
            qrCodeData = qr; // Store the code for web display
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // --- Message Handling Logic (from previous discussion) ---
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        for (const msg of messages) {
            // Ignore messages from yourself (the bot's session)
            if (!msg.key.fromMe) {
                console.log(`Message received from another source (not this bot): ${msg.message?.conversation || msg.message?.extendedTextMessage?.text || JSON.stringify(msg.message)}`);

                // Check if the message is deletable and if remoteJid and id exist
                if (msg.key.remoteJid && msg.key.id) {
                    try {
                        // Delete the message for everyone
                        await sock.sendMessage(msg.key.remoteJid, {
                            delete: msg.key // Pass the message key to delete it
                        });
                        console.log(`Successfully deleted message with ID: ${msg.key.id} in chat: ${msg.key.remoteJid}`);
                    } catch (error) {
                        console.error(`Failed to delete message with ID: ${msg.key.id}:`, error);
                    }
                }
            }
        }
    });

    console.log("Baileys connection attempt initiated.");
}

// --- Express Routes ---

// Basic homepage
app.get('/', (req, res) => {
    res.send('<h1>WhatsApp Bot Running</h1><p>Visit <a href="/link">/link</a> to connect your WhatsApp account.</p>');
});

// Linking interface route
app.get('/link', async (req, res) => {
    // If bot is already connected
    if (sock && sock.ws.readyState === sock.ws.OPEN) {
        return res.send('<h1>WhatsApp Bot Connected!</h1><p>Your bot is already active and linked.</p>');
    }

    // If linking is in progress and a code is available
    if (linkingInProgress && qrCodeData) {
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Link WhatsApp Account</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 20px; }
                    pre { font-size: 2em; font-weight: bold; background-color: #f0f0f0; padding: 10px; border-radius: 5px; display: inline-block; }
                    .note { color: gray; font-size: 0.9em; margin-top: 20px; }
                    .status { margin-top: 20px; font-weight: bold; }
                </style>
            </head>
            <body>
                <h1>Link WhatsApp Account (Pairing Code)</h1>
                <p>Open WhatsApp on your phone, go to:</p>
                <p><strong>Settings / Linked Devices → Link a Device → Link with phone number</strong></p>
                <p>Then, enter this **Pairing Code**:</p>
                <pre>${qrCodeData}</pre>
                <p class="note">This code will expire soon.</p>
                <p class="note">If it expires or the bot restarts, simply refresh this page to get a new code.</p>
                <p class="status">Status: Connecting...</p>
            </body>
            </html>
        `);
    } else if (!linkingInProgress) {
        // If not connected and not currently trying to link, start the process
        await startBaileys();
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
                <p>Initiating linking process. Please wait a few moments and **refresh this page** to see the pairing code.</p>
                <p class="status">Status: Initializing...</p>
            </body>
            </html>
        `);
    } else {
        // linkingInProgress is true but qrCodeData is not yet available (e.g., waiting for Baileys to generate it)
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
                <p>Generating pairing code. Please wait and **refresh this page** in a few moments.</p>
                <p class="status">Status: Generating code...</p>
            </body>
            </html>
        `);
    }
});

// --- Start the Express Server and Baileys Connection ---
app.listen(port, () => {
    console.log(`Server listening on port ${port}`);
    // Start Baileys connection when the Express server starts
    startBaileys();
});
