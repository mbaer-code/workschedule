import stripe
import os

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


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

        # Only pass customer_email if provided — omitting it means Stripe
        # won't pre-fill or require it, keeping the flow anonymous.
        if customer_email:
            session_params["customer_email"] = customer_email

        if coupon_code:
            print(f"[DEBUG] Coupon code '{coupon_code}' — enter on Stripe checkout page.")

        print(f"[DEBUG] Creating Stripe session with params: {session_params}")
        session = stripe.checkout.Session.create(**session_params)
        print(f"[DEBUG] Stripe session created: {session.id}")
        return session

    except stripe.error.StripeError as e:
        print(f"Stripe error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None
