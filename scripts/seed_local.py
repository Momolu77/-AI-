import argparse

from common import ROOT, load_core


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args()
    for seat, token in load_core(args.env_file).seed().items():
        print(f"座位 {seat}: http://127.0.0.1:{args.port}/enter?seat={seat}&token={token}")


if __name__ == "__main__":
    main()
