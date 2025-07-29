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

export async function getSession(id) {
  try {
    const res = await pool.query('SELECT * FROM sessions WHERE id = $1', [id])
    return res.rows[0]
  } catch (err) {
    logger.error('Failed to fetch session:', err)
    return null
  }
}

export async function saveSession(id, creds, keys) {
  try {
    await pool.query(
      `INSERT INTO sessions (id, creds, keys) 
       VALUES ($1, $2, $3) 
       ON CONFLICT (id) DO UPDATE SET creds = $2, keys = $3`,
      [id, creds, keys]
    )
    logger.info(`Session ${id} saved`)
  } catch (err) {
    logger.error('Failed to save session:', err)
  }
}
