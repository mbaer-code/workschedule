import stripe
import os

# Set your Stripe API key from environment variables
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def create_checkout_session(price_id, customer_email):
    """
    Creates a Stripe Checkout Session for a single product.

    Args:
        price_id (str): The ID of the price in Stripe for the product.
        customer_email (str): The email of the customer.

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
            success_url=os.getenv("STRIPE_SUCCESS_URL"),
            cancel_url=os.getenv("STRIPE_CANCEL_URL"),
            customer_email=customer_email,
        )
        return session
    except stripe.error.StripeError as e:
        print(f"A Stripe error occurred: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

