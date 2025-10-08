#!/bin/bash

echo "Testing MySchedule.cloud email functionality..."
echo

# Activate virtual environment (adjust path as needed)
source venv/bin/activate

# Run the email test
python -c "from workschedule.services.mailgun_service import test_email_locally; test_email_locally()"

echo
echo "Email test completed. Check your inbox!"
read -p "Press Enter to continue..."