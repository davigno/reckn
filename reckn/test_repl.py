#!/usr/bin/env python3
"""Simple test REPL for the Reckn parser and evaluator."""

import sys
from evaluator import LineEvaluator


def run_repl():
    """Run an interactive REPL."""
    print("Reckn Test REPL")
    print("Enter expressions (one per line). Type 'quit' or Ctrl+D to exit.")
    print("Type 'reset' to clear variables and line history.")
    print("-" * 50)

    evaluator = LineEvaluator()
    line_num = 0

    while True:
        try:
            line = input(f"[{line_num + 1}] > ")
        except EOFError:
            print("\nBye!")
            break

        if line.strip().lower() == 'quit':
            print("Bye!")
            break

        if line.strip().lower() == 'reset':
            evaluator = LineEvaluator()
            line_num = 0
            print("Reset complete.")
            continue

        line_num += 1
        result = evaluator.evaluate_line(line, line_num)

        if result:
            print(f"      = {result}")
        else:
            print()


def run_batch(lines: list[str]):
    """Evaluate a batch of lines and print results."""
    evaluator = LineEvaluator()
    max_line_len = max(len(line) for line in lines) if lines else 20
    max_line_len = max(max_line_len, 20)

    print("-" * (max_line_len + 20))

    for i, line in enumerate(lines, start=1):
        result = evaluator.evaluate_line(line, i)
        padding = " " * (max_line_len - len(line) + 2)
        result_str = f"→ {result}" if result else ""
        print(f"{line}{padding}{result_str}")

    print("-" * (max_line_len + 20))


def main():
    if len(sys.argv) > 1:
        # Read from file
        filename = sys.argv[1]
        try:
            with open(filename, 'r') as f:
                lines = [line.rstrip('\n') for line in f]
            run_batch(lines)
        except FileNotFoundError:
            print(f"Error: File not found: {filename}")
            sys.exit(1)
    else:
        # Interactive mode
        run_repl()


if __name__ == "__main__":
    main()
