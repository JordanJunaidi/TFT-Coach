"""CLI: ask the coach one question.

Usage: python -m tftcoach.agent "What should I watch out for this patch?" [--riot-id Name#TAG]
"""

import argparse
import logging

from tftcoach.agent.loop import tool_result_preview
from tftcoach.agent.session import open_session


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ask the TFT coach a question")
    parser.add_argument("question")
    parser.add_argument("--riot-id", help="defaults to TFT_RIOT_ID in .env")
    parser.add_argument("--show-tools", action="store_true", help="print tool calls and results")
    parser.add_argument("-v", "--verbose", action="store_true", help="log each round as it runs")
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%X")

    session = open_session(args.riot_id)
    try:
        result = session.ask(args.question)
    finally:
        session.close()

    if args.show_tools:
        for call in result.tool_calls:
            print(f"--> {call.name}({call.arguments})\n{tool_result_preview(call)}\n")
    print(result.answer)
    print()
    print(f"Tool calls: {', '.join(c.name for c in result.tool_calls) or 'none'}")
    print(f"Citations: {', '.join(result.citations) or 'none'}")
    if result.unknown_citations:
        print(f"WARNING: cited chunks that were never retrieved: {result.unknown_citations}")
    if result.grounding.ok:
        print(f"Grounding: all {result.grounding.numbers_checked} numbers found in tool output")
    else:
        print(f"WARNING: numbers not found in tool output: {result.grounding.unsupported}")


if __name__ == "__main__":
    main()
