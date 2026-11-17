"""Load demo users, suppliers and products:  python seed_demo.py"""

from app import create_app
from app.seed import seed_demo_data

app = create_app()

with app.app_context():
    print(seed_demo_data())
