import express from 'express';
import { makeWASocket, DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs/promises'; // For file system operations, like deleting session data

// --- Setup for ES Modules __dirname and __filename ---
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- Persistent Storage Path ---
const SESSION_PATH = process.env.WA_SESSION_PATH || path.resolve(__dirname, 'baileys_auth_info');

// --- Express Server Setup ---
const app = express();
const port = process.env.PORT || 3000;

// Middleware to parse URL-encoded bodies (for form submissions)
app.use(express.urlencoded({ extended: true }));

// --- Baileys Global State Variables ---
let sock = null; // Holds the Baileys socket instance
let qrCodeData = null; // Stores the QR code string or pairing code string for display
let linkingInProgress = false; // Flag to manage the linking process state
let currentPhoneNumber = null; // Stores the phone number entered by the user for pairing

// --- Function to Start/Manage Baileys Connection ---
async function startBaileys(phoneNumber = null) {
    // Prevent multiple linking attempts if one is already in progress
    if (linkingInProgress && sock) {
        if (sock.ws.readyState === sock.ws.OPEN) {
            console.log("Bot already connected and active.");
            return;
        }
        console.log("Linking process already in progress. Waiting for previous attempt to resolve.");
        return; // Don't start a new process if one is ongoing
    }

    linkingInProgress = true;
    qrCodeData = null; // Clear any old code when starting a new linking attempt
    currentPhoneNumber = phoneNumber; // Store the number for potential re-use

    // Load or create authentication state for Baileys
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

    // Create a new Baileys WhatsApp Socket instance
    sock = makeWASocket({
        auth: state,
        browser: ['My Baileys Bot', 'Chrome', '1.0'] // Custom browser identifier
    });

    // --- Baileys Event Listeners (Set up immediately) ---

    // Listen for connection updates (open, close, QR/pairing code)
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error instanceof Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Connection closed. Reconnecting:', shouldReconnect);
            sock = null; // Clear the socket instance on close

            if (shouldReconnect) {
                console.log('Attempting to reconnect Baileys...');
                // Recursively call startBaileys for reconnection
                startBaileys(currentPhoneNumber); // Attempt to reconnect with the last used number
            } else {
                console.log('Logged out. Please link again via /link.');
                linkingInProgress = false; // Allow a new linking attempt
                qrCodeData = null; // Clear any old QR/pairing code
                currentPhoneNumber = null; // Clear the phone number on full logout

                // Attempt to delete old session data to force a fresh start
                try {
                    await fs.rm(SESSION_PATH, { recursive: true, force: true });
                    console.log('Deleted old session data.');
                } catch (err) {
                    console.error('Error deleting session data:', err);
                }
            }
        } else if (connection === 'open') {
            // Connection successfully opened
            console.log('WhatsApp connection opened!');
            linkingInProgress = false; // Linking complete
            qrCodeData = null; // Clear QR data once connected
            currentPhoneNumber = null; // Clear phone number once successfully linked
        }

        // The 'qr' property in connection.update will contain the linking data.
        // For phone number pairing, this often is the 8-digit code string.
        // We set it here as a fallback/initial display, but pairPhone() should return the definitive 8-digit code.
        if (qr && !qrCodeData) { // Only set if qrCodeData hasn't been explicitly set by pairPhone() yet
             console.log('Raw QR/Pairing Code received from connection.update event:', qr);
             qrCodeData = qr; // Fallback: set qrCodeData to the raw `qr` string from the event
        }
    });

    // Save credentials when they are updated (essential for session persistence)
    sock.ev.on('creds.update', saveCreds);

    // --- Message Handling Logic (Automatic Deletion) ---
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        for (const msg of messages) {
            // Ignore messages from yourself (the bot's session)
            if (!msg.key.fromMe) {
                const messageText = msg.message?.conversation || msg.message?.extendedTextMessage?.text || JSON.stringify(msg.message);
                console.log(`Message received from another source (not this bot): ${messageText}`);

                // Check if the message is deletable (i.e., has a remoteJid and a message ID)
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

    console.log("Baileys socket instance created. Now attempting pairing/connection.");

    // --- Execute pairPhone if a phone number is provided ---
    // This needs to be called AFTER sock is initialized and event listeners are set up.
    if (phoneNumber) {
        console.log(`Attempting to explicitly pair with phone number: ${phoneNumber}`);
        try {
            // Explicitly check if sock.pairPhone is a function before calling
            if (sock && typeof sock.pairPhone === 'function') {
                const code = await sock.pairPhone(phoneNumber); // This should return the 8-digit code
                console.log("Successfully generated 8-digit pairing code:", code);
                qrCodeData = code; // Set the human-readable code for display
            } else {
                console.error("Error: sock.pairPhone is not a function. This might indicate a Baileys version issue.");
                // Fallback: If pairPhone is not available, we rely solely on the `qr` event from connection.update.
                // The `qrCodeData` would then contain the raw string from that event.
                qrCodeData = "Could not generate 8-digit code. Please use the full code if displayed or check logs.";
            }
        } catch (e) {
            console.error("Error during sock.pairPhone execution:", e);
            linkingInProgress = false;
            qrCodeData = "Error generating pairing code. Please try again or check logs. (Execution failed)";
        }
    }
}

// --- Express Routes ---

// Route for the basic homepage
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
                a { color: #007bff; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>WhatsApp Bot Running</h1>
            <p>This is your Baileys bot service.</p>
            <p>Visit <a href="/link">/link</a> to connect your WhatsApp account.</p>
        </body>
        </html>
    `);
});

// GET /link: Displays the form to ask for number, or shows the pairing code, or displays connected status.
app.get('/link', (req, res) => {
    // If the bot is already connected to WhatsApp
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

    // If linking is in progress and a pairing code is available
    if (linkingInProgress && qrCodeData) {
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Link WhatsApp Account</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 20px; }
                    pre { font-size: 2em; font-weight: bold; background-color: #f0f0f0; padding: 10px; border-radius: 5px; display: inline-block; word-break: break-all; white-space: normal; }
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
    } else if (linkingInProgress && !qrCodeData) {
        // Linking is in progress, but the code isn't generated yet
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
                <p>Generating pairing code. Please wait a few moments and **refresh this page**.</p>
                <p class="status">Status: Generating code...</p>
            </body>
            </html>
        `);
    } else {
        // Not connected, not linking, show the form to get the phone number
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Link WhatsApp Account</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 20px; }
                    form { margin-top: 30px; }
                    input[type="text"] { padding: 10px; width: 300px; border: 1px solid #ccc; border-radius: 5px; }
                    button { padding: 10px 20px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; }
                    button:hover { background-color: #218838; }
                    .note { color: gray; font-size: 0.9em; margin-top: 20px; }
                </style>
            </head>
            <body>
                <h1>Link WhatsApp Account</h1>
                <p>Please enter your WhatsApp phone number to generate a pairing code.</p>
                <p class="note">Include your country code (e.g., 2348012345678 for Nigeria).</p>
                <form action="/link" method="POST">
                    <input type="text" name="phoneNumber" placeholder="e.g., 2348012345678" required>
                    <button type="submit">Get Pairing Code</button>
                </form>
            </body>
            </html>
        `);
    }
});

// POST /link: Handles the form submission for the phone number
app.post('/link', async (req, res) => {
    const { phoneNumber } = req.body;

    if (!phoneNumber) {
        return res.status(400).send('Phone number is required.');
    }

    // Clean the phone number (remove non-digits)
    currentPhoneNumber = phoneNumber.replace(/[^0-9]/g, '');

    // Start the Baileys connection with the provided phone number
    await startBaileys(currentPhoneNumber);

    // Redirect to the GET /link page to display the code.
    res.send(`
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="refresh" content="5;url=/link">
            <title>Generating Code...</title>
            <style>
                body { font-family: sans-serif; text-align: center; padding: 20px; }
            </style>
        </head>
        <body>
            <h1>Generating Pairing Code...</h1>
            <p>Please wait while the pairing code is generated for ${currentPhoneNumber}.</p>
            <p>You will be redirected in 5 seconds. If not, <a href="/link">click here</a>.</p>
        </body>
        </html>
    `);
});


// --- Start the Express Server ---
app.listen(port, () => {
    console.log(`Server listening on port ${port}`);
    // IMPORTANT: Baileys connection is NOT started immediately here.
    // It will only start when a user visits and submits the form on the /link route.
    // However, if an existing session already exists from a previous successful link,
    // you might want to load it on startup to avoid re-linking.
    // For now, it will solely rely on the web interface for initial linking.
});
