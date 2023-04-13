import sys
import os
import argparse

# import httpx
# import lxml
# import html5_parser

# import parser2
# from parser2 import mimetype
from parser2.book import Book

# from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
# from urllib.parse import quote_plus, unquote_plus


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-j",
        "--threads",
        help="threads used for download (default: 8)",
        type=int,
        default=8,
    )
    parser.add_argument("book_url")

    return parser


def main():
    # init
    parser = init_argparse()
    args = parser.parse_args()

    # main
    book = Book(args.book_url)
    book.parse()
    book.parse_chapters()
    book.print_content()
    book.save_as_epub(f"{book.title}.epub")
    input("Enter to continue...")


if __name__ == "__main__":
    main()
