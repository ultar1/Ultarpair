// index.js
import express from 'express'
import http from 'http'
import { WebSocketServer } from 'ws'
import { makeWASocket, DisconnectReason } from 'baileys'
import { Boom } from '@hapi/boom'
import QRCode from 'qrcode'
import dotenv from 'dotenv'
import logger from './logger.js'
import { getSession, saveSession } from './db.js'

dotenv.config()

const SESSION_ID = 'default'
const app = express()
const server = http.createServer(app)
const wss = new WebSocketServer({ server })

let clients = []

wss.on('connection', (ws) => {
  clients.push(ws)
  ws.on('close', () => {
    clients = clients.filter(c => c !== ws)
  })
})

function broadcast(data) {
  clients.forEach(ws => {
    if (ws.readyState === ws.OPEN) {
      ws.send(JSON.stringify(data))
    }
  })
}

app.use(express.static('public'))

async function usePostgresAuthState() {
  const session = await getSession(SESSION_ID)
  const creds = session?.creds || {}
  const keys = session?.keys || {}

  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          return (keys[type] || {}) || {}
        },
        set: async (data) => {
          for (const key in data) {
            keys[key] = {
              ...(keys[key] || {}),
              ...data[key]
            }
          }
        }
      }
    },
    saveCreds: async () => {
      await saveSession(SESSION_ID, creds, keys)
    }
  }
}

async function startSocket() {
  const { state, saveCreds } = await usePostgresAuthState()

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    logger: logger.child({ module: 'baileys' }),
    browser: ['CustomBot', 'Chrome', '1.0.0']
  })

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update

    if (qr) {
      try {
        const qrImage = await QRCode.toDataURL(qr)
        broadcast({ type: 'qr', data: qrImage })
        logger.info('📡 QR code generated and sent to clients')
      } catch (err) {
        logger.error('❌ Failed to generate QR code:', err)
      }
    }

    if (connection === 'open') {
      logger.info('✅ WhatsApp connection established')
      broadcast({ type: 'status', data: 'Connected to WhatsApp' })

      // Pairing code logic after connection opens
      const phoneNumber = '2348012345678'
      try {
        const code = await sock.requestPairingCode(phoneNumber)
        broadcast({ type: 'pairing', data: code })
        logger.info(`🔐 Pairing code generated: ${code}`)
      } catch (err) {
        logger.error('❌ Failed to generate pairing code:', err)
      }
    }

    if (connection === 'close') {
      const shouldReconnect =
        (lastDisconnect?.error instanceof Boom) &&
        lastDisconnect.error.output?.statusCode === DisconnectReason.restartRequired

      if (shouldReconnect) {
        logger.warn('🔄 Restart required. Reconnecting...')
        startSocket()
      } else {
        logger.error('❌ Connection closed:', lastDisconnect?.error)
      }
    }
  })
}

startSocket()

const PORT = process.env.PORT || 3000
server.listen(PORT, () => {
  logger.info(`🌐 Server running at http://localhost:${PORT}`)
})
