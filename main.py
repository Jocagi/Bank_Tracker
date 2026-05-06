from app import create_app
import logging

app = create_app()

# Enable logging to see errors
logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    app.run(use_debugger=True)
