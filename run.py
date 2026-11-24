import os

from app import create_app
from app.core.utils import is_truthy

app = create_app()

if __name__ == '__main__':
    from upgrade_db import upgrade_database
    upgrade_database(app)
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))
    debug = is_truthy(os.environ.get('FLASK_DEBUG', '0'))
    app.run(host=host, port=port, debug=debug)
