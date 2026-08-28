import sys
import time
import asyncio
import traceback
import uvicorn

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

def start_server():
    print("[Server Supervisor] Starting FastAPI backend supervisor on http://127.0.0.1:8000 ...")
    while True:
        try:
            uvicorn.run(
                "app.main:app",
                host="127.0.0.1",
                port=8000,
                log_level="info",
                access_log=False
            )
        except (KeyboardInterrupt, SystemExit):
            print("[Server Supervisor] Exiting server gracefully.")
            break
        except Exception as e:
            print(f"[Server Supervisor] Server crashed with: {e}. Auto-restarting in 1s...")
            traceback.print_exc()
            time.sleep(1.0)

if __name__ == "__main__":
    start_server()
