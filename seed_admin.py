"""Create an admin account interactively:  python seed_admin.py"""

from app import create_app
from app.seed import create_admin_interactive

app = create_app()

with app.app_context():
    create_admin_interactive()
