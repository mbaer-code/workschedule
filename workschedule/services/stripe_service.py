import stripe
import os

# Set your Stripe API key from environment variables
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def create_checkout_session(price_id, customer_email, success_url=None, cancel_url=None, metadata=None):
    """
    Creates a Stripe Checkout Session for a single product.

    Args:
        price_id (str): The ID of the price in Stripe for the product.
        customer_email (str): The email of the customer.
        success_url (str): The URL to redirect to after successful payment.
        cancel_url (str): The URL to redirect to after cancellation.
        metadata (dict): Metadata to attach to the session.

    Returns:
        stripe.checkout.Session: The created session object.
    """
    try:
        session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            mode="payment",
            success_url=success_url or os.getenv("STRIPE_SUCCESS_URL"),
            cancel_url=cancel_url or os.getenv("STRIPE_CANCEL_URL"),
            customer_email=customer_email,
            metadata=metadata or {}
        )
        return session
    except stripe.error.StripeError as e:
        print(f"A Stripe error occurred: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

