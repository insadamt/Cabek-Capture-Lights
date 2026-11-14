"""Launch the standalone lighting server on loopback port 8001.

Depends on Uvicorn and lighting_api.main; a single process owns the USB port.
"""
import argparse
import uvicorn
from lighting_api.main import create_app

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(create_app(), host='127.0.0.1', port=args.port)

if __name__ == '__main__':
    main()
