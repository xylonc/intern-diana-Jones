from bot.pipeline import run , seed , register
import sys

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command == "seed":
        seed()
    elif command == "register":
        register()
    else:
        run()