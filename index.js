import express from 'express'
import http from 'http'
import { WebSocketServer } from 'ws'
import { makeWASocket, DisconnectReason } from 'baileys'
import { Boom } from '@hapi/boom'
import QRCode from 'qrcode'
import dotenv from 'dotenv'
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
    printQRInTerminal: false
  })

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update

    if (qr) {
      const qrImage = await QRCode.toDataURL(qr)
      broadcast({ type: 'qr', data: qrImage })
    }

    if (connection === 'close') {
      const shouldReconnect =
        (lastDisconnect?.error instanceof Boom) &&
        lastDisconnect.error.output?.statusCode === DisconnectReason.restartRequired

      if (shouldReconnect) {
        console.log('🔄 Restarting socket...')
        startSocket()
      } else {
        console.error('❌ Connection closed:', lastDisconnect?.error)
      }
    }

    if (connection === 'open') {
      console.log('✅ Connected to WhatsApp')
      broadcast({ type: 'status', data: 'Connected to WhatsApp' })
    }
  })

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async (update) => {
    const { connection, qr } = update
    if (connection === 'connecting' || !!qr) {
      const phoneNumber = '2348012345678'
      const code = await sock.requestPairingCode(phoneNumber)
      broadcast({ type: 'pairing', data: code })
    }
  })
}

startSocket()

const PORT = process.env.PORT || 3000
server.listen(PORT, () => {
  console.log(`🌐 Server running on http://localhost:${PORT}`)
})
