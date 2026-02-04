"""Azure Functions App Host Configuration."""
import azure.functions as func
import logging
import os

app = func.FunctionApp()

CRON_SCHEDULE = os.getenv("CRON_SCHEDULE", "0 0 0 * * *")

@app.timer_trigger(
    schedule=CRON_SCHEDULE,
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=True
)
def crypto_signal_timer(myTimer: func.TimerRequest) -> None:
    """
    Timer-triggered function for crypto signal bot.
    
    Schedule: Configurable via CRON_SCHEDULE environment variable
    Default CRON: "0 0 0 * * *" (once a day at midnight)
    
    To configure in Azure Functions:
    - Azure Portal > Function App > Configuration > Application Settings
    - Add: CRON_SCHEDULE = "0 0 0 * * *"
    """
    logger = logging.getLogger(__name__)
    
    if myTimer.past_due:
        logger.warning('The timer is past due!')
    
    logger.info('=' * 60)
    logger.info('Crypto Signal Bot Timer Trigger executed')
    logger.info('=' * 60)
    
    try:
        # Import and run the bot main function
        # With flat structure, scripts/ is in the same directory
        from scripts.main import main as bot_main
        
        # Run the bot main function
        exit_code = bot_main()
        
        if exit_code == 0:
            logger.info('Bot execution completed successfully')
        else:
            error_msg = f'✗ Bot execution failed with exit code: {exit_code}'
            logger.error(error_msg)
            # Raise exception to mark function execution as failed in Azure
            raise RuntimeError(error_msg)
    except ImportError as e:
        logger.error(f'Import error - check deployment structure: {e}', exc_info=True)
        raise        
    except Exception as e:
        logger.error(f'Function execution failed: {e}', exc_info=True)
        raise

@app.function_name(name="HealthCheck")
@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Simple health check endpoint."""
    return func.HttpResponse(
        body='{"status": "healthy", "service": "crypto-signal-bot"}',
        mimetype="application/json",
        status_code=200
    )