# workschedule-cloud/wsgi.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

from src import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
