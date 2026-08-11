#!/usr/bin/env python3
"""Render an mbox (e.g. from `b4 mbox`) as a threaded, readable digest.

Messages are ordered as a reply tree (In-Reply-To, falling back to the
last entry of References), children sorted by date. Useful to actually
read a lore.kernel.org discussion instead of scrolling a raw mbox.

Usage:
    mbox-thread.py THREAD.mbox                  # full, quotes kept
    mbox-thread.py --strip-quotes THREAD.mbox   # discussion only
    mbox-thread.py --list THREAD.mbox           # one line per message
"""

import argparse
import email.header
import email.utils
import mailbox
import re
import sys

QUOTE_RE = re.compile(r"^\s*>")


def _decode(value):
    if not value:
        return ""
    try:
        text = str(email.header.make_header(email.header.decode_header(value)))
    except Exception:
        text = value
    return " ".join(text.split())


def _body_of(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, "replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, "replace")


def _strip_quotes(text):
    out, dropped = [], 0
    for line in text.splitlines():
        if QUOTE_RE.match(line):
            dropped += 1
            continue
        if dropped and line.strip() == "":
            continue
        if dropped:
            out.append(f"[... {dropped} quoted line(s) removed ...]")
            dropped = 0
        out.append(line)
    if dropped:
        out.append(f"[... {dropped} quoted line(s) removed ...]")
    return "\n".join(out)


def _msgid(value):
    return (value or "").strip().strip("<>").strip()


def _parent_of(msg):
    parent = _msgid(msg.get("In-Reply-To"))
    if parent:
        return parent
    refs = (msg.get("References") or "").split()
    return _msgid(refs[-1]) if refs else ""


def _sort_key(msg):
    parsed = email.utils.parsedate_tz(msg.get("Date") or "")
    return email.utils.mktime_tz(parsed) if parsed else 0


def _main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mbox")
    ap.add_argument("--strip-quotes", action="store_true",
                    help="drop quoted lines (keeps a marker)")
    ap.add_argument("--list", action="store_true",
                    help="only print a one-line summary per message")
    args = ap.parse_args()

    messages = list(mailbox.mbox(args.mbox))
    if not messages:
        sys.exit(f"{args.mbox}: no messages")

    by_id = {_msgid(m.get("Message-Id")): m for m in messages}
    children, roots = {}, []
    for msg in messages:
        parent = _parent_of(msg)
        if parent and parent in by_id and parent != _msgid(msg.get("Message-Id")):
            children.setdefault(parent, []).append(msg)
        else:
            roots.append(msg)

    def walk(msg, depth):
        subject = _decode(msg.get("Subject"))
        sender = _decode(msg.get("From"))
        if args.list:
            print(f"{'  ' * depth}[{depth}] {msg.get('Date')} | {sender} | {subject}")
        else:
            print("=" * 100)
            print(f"[depth {depth}] FROM: {sender}")
            print(f"DATE: {msg.get('Date')}")
            print(f"SUBJ: {subject}")
            print(f"MSGID: <{_msgid(msg.get('Message-Id'))}>")
            print("-" * 100)
            text = _body_of(msg)
            print(_strip_quotes(text) if args.strip_quotes else text)
        for child in sorted(children.get(_msgid(msg.get("Message-Id")), []), key=_sort_key):
            walk(child, depth + 1)

    for root in sorted(roots, key=_sort_key):
        walk(root, 0)

    print(f"\n[{len(messages)} message(s) in {args.mbox}]", file=sys.stderr)


if __name__ == "__main__":
    _main()
