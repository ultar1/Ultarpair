// db.js
import pkg from 'pg'
const { Pool } = pkg
import dotenv from 'dotenv'
import logger from './logger.js'

dotenv.config()

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
})

// Helper: safely encode Buffers to base64
function encodeBuffers(obj) {
  const encoded = {}
  for (const key in obj) {
    const value = obj[key]
    if (Buffer.isBuffer(value)) {
      encoded[key] = { __type: 'Buffer', data: value.toString('base64') }
    } else if (typeof value === 'object' && value !== null) {
      encoded[key] = encodeBuffers(value)
    } else {
      encoded[key] = value
    }
  }
  return encoded
}

// Helper: decode base64 back to Buffers
function decodeBuffers(obj) {
  const decoded = {}
  for (const key in obj) {
    const value = obj[key]
    if (value && value.__type === 'Buffer') {
      decoded[key] = Buffer.from(value.data, 'base64')
    } else if (typeof value === 'object' && value !== null) {
      decoded[key] = decodeBuffers(value)
    } else {
      decoded[key] = value
    }
  }
  return decoded
}

export async function getSession(id) {
  try {
    const res = await pool.query('SELECT * FROM sessions WHERE id = $1', [id])
    if (!res.rows[0]) return null

    const creds = decodeBuffers(res.rows[0].creds)
    const keys = decodeBuffers(res.rows[0].keys)

    return { creds, keys }
  } catch (err) {
    logger.error('❌ Failed to fetch session:', err)
    return null
  }
}

export async function saveSession(id, creds, keys) {
  try {
    const encodedCreds = encodeBuffers(creds)
    const encodedKeys = encodeBuffers(keys)

    await pool.query(
      `INSERT INTO sessions (id, creds, keys) 
       VALUES ($1, $2, $3) 
       ON CONFLICT (id) DO UPDATE SET creds = $2, keys = $3`,
      [id, encodedCreds, encodedKeys]
    )
    logger.info(`✅ Session ${id} saved`)
  } catch (err) {
    logger.error('❌ Failed to save session:', err)
  }
}
