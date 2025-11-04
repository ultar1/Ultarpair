import logging
import asyncio
import config
import database
from telegram import Bot
from telegram.error import Forbidden, BadRequest

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# How often the scheduler checks the DB (in seconds)
POLL_INTERVAL = 15

async def process_jobs():
    """
    Fetches and processes all due jobs from the database.
    This now ONLY handles 'unpin' jobs.
    """
    bot = Bot(config.TOKEN)
    
    try:
        # Get due jobs (database.py now only returns 'unpin' jobs)
        jobs_to_run = await asyncio.to_thread(database.get_due_jobs)
        if not jobs_to_run:
            # This is normal, just means no jobs are due
            logger.info("Scheduler: No due jobs found.")
            return

        logger.info(f"Scheduler: Found {len(jobs_to_run)} due jobs to process.")
        
        for job in jobs_to_run:
            job_id = job['id']
            job_type = job['job_type']
            chat_id = job['chat_id']
            target_id = job['target_id']

            try:
                # --- (THIS IS THE FIX) ---
                # We only check for 'unpin'. All 'unmute' logic is GONE.
                if job_type == 'unpin':
                    logger.info(f"Running 'unpin' job {job_id} for message {target_id} in chat {chat_id}")
                    await bot.unpin_chat_message(
                        chat_id=chat_id,
                        message_id=target_id
                    )
                else:
                    logger.warning(f"Scheduler: Found unknown job_type '{job_type}' (job_id: {job_id}). Deleting it.")
                
                # --- (END OF FIX) ---

                # If successful (or unknown), delete the job
                await asyncio.to_thread(database.delete_job, job_id)

            except (Forbidden, BadRequest) as e:
                # If we get a Forbidden/Bad Request error, the bot probably
                # lost admin rights or the message/user is gone.
                # Delete the job to stop retrying.
                logger.warning(f"Scheduler: Failed to run job {job_id} ({e}). Deleting job.")
                await asyncio.to_thread(database.delete_job, job_id)
            except Exception as e:
                # For other errors (e.g., network), log it but
                # DON'T delete the job, so it will be retried.
                logger.error(f"Scheduler: Network/unknown error on job {job_id}: {e}. Will retry.")

    except Exception as e:
        logger.error(f"Scheduler: Error in process_jobs loop: {e}")


async def main():
    """Main entry point for the scheduler worker."""
    logger.info("Scheduler worker starting...")
    if not all([config.TOKEN, config.DATABASE_URL]):
        logger.critical("Scheduler: TOKEN or DATABASE_URL not set. Exiting.")
        return
        
    while True:
        try:
            await process_jobs()
        except Exception as e:
            logger.error(f"Scheduler: Critical error in main loop: {e}")
        
        logger.info(f"Scheduler: Sleeping for {POLL_INTERVAL} seconds...")
        await asyncio.Esleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
