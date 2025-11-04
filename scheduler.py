import logging
import asyncio
import config
import database
from telegram import Bot, ChatPermissions
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
    """
    bot = Bot(config.TOKEN)
    
    try:
        # Get due jobs
        jobs_to_run = await asyncio.to_thread(database.get_due_jobs)
        if not jobs_to_run:
            return # Nothing to do

        logger.info(f"Found {len(jobs_to_run)} due jobs to process.")
        
        for job in jobs_to_run:
            job_id = job['id']
            job_type = job['job_type']
            chat_id = job['chat_id']
            target_id = job['target_id']

            try:
                if job_type == 'unmute':
                    logger.info(f"Running 'unmute' job {job_id} for user {target_id} in chat {chat_id}")
                    # Restore default permissions
                    await bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=target_id,
                        permissions=ChatPermissions(
                            can_send_messages=True,
                            can_send_media_messages=True,
                            can_send_polls=True,
                            can_send_other_messages=True,
                            can_add_web_page_previews=True,
                            can_invite_users=True
                        )
                    )
                
                elif job_type == 'unpin':
                    logger.info(f"Running 'unpin' job {job_id} for message {target_id} in chat {chat_id}")
                    await bot.unpin_chat_message(
                        chat_id=chat_id,
                        message_id=target_id
                    )
                
                # If successful, delete the job
                await asyncio.to_thread(database.delete_job, job_id)

            except (Forbidden, BadRequest) as e:
                # If we get a Forbidden/Bad Request error, the bot probably
                # lost admin rights or the message/user is gone.
                # Delete the job to stop retrying.
                logger.warning(f"Failed to run job {job_id} ({e}). Deleting job.")
                await asyncio.to_thread(database.delete_job, job_id)
            except Exception as e:
                # For other errors (e.g., network), log it but
                # DON'T delete the job, so it will be retried.
                logger.error(f"Network/unknown error on job {job_id}: {e}. Will retry.")

    except Exception as e:
        logger.error(f"Error in process_jobs loop: {e}")


async def main():
    """Main entry point for the scheduler worker."""
    logger.info("Scheduler worker starting...")
    if not all([config.TOKEN, config.DATABASE_URL]):
        logger.critical("TOKEN or DATABASE_URL not set. Exiting.")
        return
        
    while True:
        try:
            await process_jobs()
        except Exception as e:
            logger.error(f"Critical error in scheduler main loop: {e}")
        
        await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
