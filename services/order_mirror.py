import asyncio
import threading
import logging

logger = logging.getLogger(__name__)

# _sender can be either a sync callable or async coroutine function with signature
# (order_id: int, event: str = "order_updated", payment_status: str = "")
_sender = None


def register_sender(sender):
    global _sender
    _sender = sender


def notify(order_id: int, event: str = "order_updated", payment_status: str = ""):
    """Notify the registered sender about an order event.

    This is safe to call from synchronous code paths. If the registered
    sender is async, we attempt to schedule it on the running event loop;
    otherwise we execute it on a background thread.
    """
    if _sender is None:
        logger.debug("order_mirror: no sender registered, skipping notify for order %s", order_id)
        return

    try:
        if asyncio.iscoroutinefunction(_sender):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop in this thread; run in a background thread
                logger.debug("order_mirror: scheduling async sender in background thread for order %s", order_id)
                threading.Thread(
                    target=lambda: asyncio.run(_sender(order_id, event, payment_status)),
                    daemon=True,
                ).start()
            else:
                # Schedule safely on the running loop
                logger.debug("order_mirror: scheduling async sender on running loop for order %s", order_id)
                asyncio.run_coroutine_threadsafe(_sender(order_id, event, payment_status), loop)
        else:
            # Sync sender: run on background thread to avoid blocking callers
            logger.debug("order_mirror: running sync sender on background thread for order %s", order_id)
            threading.Thread(target=lambda: _sender(order_id, event, payment_status), daemon=True).start()
    except Exception:
        logger.exception("order_mirror: failed to notify sender for order %s", order_id)
