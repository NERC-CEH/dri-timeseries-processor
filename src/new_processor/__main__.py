import logging
import sys

from new_processor.app.run import build_processor
from new_processor.cli.cli import parse_args

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def main(argv: list[str]) -> None:
    run_config = parse_args(argv)
    processor = build_processor(run_config)
    processor.run()


if __name__ == "__main__":
    main(sys.argv[1:])
