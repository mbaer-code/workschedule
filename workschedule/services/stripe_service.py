import logging
import os

import stripe

logger = logging.getLogger(__name__)

stripe.api_key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def create_checkout_session(price_id, customer_email=None, success_url=None,
                            cancel_url=None, metadata=None, coupon_code=None):
    """
    Creates a Stripe Checkout Session.
    customer_email is optional — if None, Stripe collects it on the checkout page
    or the session proceeds anonymously.
    """
    try:
        session_params = {
            "line_items": [{"price": price_id, "quantity": 1}],
            "mode": "payment",
            "customer_creation": "if_required",
            "payment_method_types": ["card"],
            "success_url": success_url or os.getenv("STRIPE_SUCCESS_URL"),
            "cancel_url": cancel_url or os.getenv("STRIPE_CANCEL_URL"),
            "metadata": metadata or {},
            "allow_promotion_codes": True,
        }

        if customer_email:
            session_params["customer_email"] = customer_email

        if coupon_code:
            logger.debug(f"Coupon code '{coupon_code}' — enter on Stripe checkout page.")

        logger.info(f"[stripe] Creating checkout session price_id={price_id}")
        session = stripe.checkout.Session.create(**session_params)
        logger.info(f"[stripe] Session created id={session.id} url={session.url!r}")
        return session

    except stripe.error.StripeError as e:
        logger.error(f"[stripe] StripeError: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"[stripe] Unexpected error: {e}", exc_info=True)
        return None
