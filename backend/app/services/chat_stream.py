"""Incremental stream parsers for grounded-question answers.

The QA provider contract returns one JSON object ``{"answer": ..., "citations":
...}``. Real streaming cannot display that envelope directly, so these helpers
reconstruct only the human-facing answer text from the raw token flow:

- :class:`ThinkSuppressor` drops ``<think>...</think>`` sections (reasoning
  models often emit them inline) without waiting for the closing tag.
- :class:`JsonAnswerValueStream` locates the opening quote of the ``"answer"``
  string value and emits its decoded characters until the value closes,
  ignoring everything before it (chatter, markdown fences) and after it
  (the citations array). It is a display heuristic: the authoritative
  answer/citations still come from parsing the full accumulated output, so a
  pathologically crafted fake ``"answer":"`` marker could pollute the live
  view only.

Both are push-style: ``feed(chunk) -> str`` handles arbitrarily small
fragments and never emits a partial tag or escape.
"""

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"

_KEY = '"answer"'
_COLON_WS = " \t\r\n"

# decode states
_HUNT, _WANT_COLON, _WANT_QUOTE, _STRING, _ESC, _UNI, _DONE = range(7)


class ThinkSuppressor:
    """Filter out ``<think>...</think>`` regions from an incremental stream."""

    def __init__(self) -> None:
        self._inside = False
        self._pending = ""

    @staticmethod
    def _tail_hold(text: str, tag: str) -> int:
        """Earliest index whose suffix could become ``tag`` with more input.

        Only genuine tag-prefix suffixes are withheld, so ordinary text flows
        through with zero added latency.
        """
        for start in range(max(0, len(text) - len(tag) + 1), len(text)):
            if tag.startswith(text[start:]):
                return start
        return len(text)

    def feed(self, chunk: str) -> str:
        self._pending += chunk
        out: list[str] = []
        while True:
            if self._inside:
                end = self._pending.find(_THINK_CLOSE)
                if end != -1:
                    self._pending = self._pending[end + len(_THINK_CLOSE) :]
                    self._inside = False
                    continue
                hold = self._tail_hold(self._pending, _THINK_CLOSE)
                self._pending = self._pending[hold:]
                return "".join(out)
            start = self._pending.find(_THINK_OPEN)
            if start == -1:
                hold = self._tail_hold(self._pending, _THINK_OPEN)
                out.append(self._pending[:hold])
                self._pending = self._pending[hold:]
                return "".join(out)
            out.append(self._pending[:start])
            self._pending = self._pending[start + len(_THINK_OPEN) :]
            self._inside = True

    def flush(self) -> str:
        """Emit whatever is still buffered; call once at end of stream."""
        tail, self._pending = self._pending, ""
        return tail


class JsonAnswerValueStream:
    """Emit only the decoded text of the top-level ``"answer"`` JSON string."""

    def __init__(self) -> None:
        self._state = _HUNT
        self._buffer = ""  # unconsumed raw input (small: trimmed eagerly)
        self._search_from = 0  # HUNT resumes here; past known-false hits
        self._digits = ""  # collected hex digits while in _UNI

    @property
    def closed(self) -> bool:
        """True once the answer value has been seen to its closing quote."""
        return self._state == _DONE

    def feed(self, chunk: str) -> str:
        if self._state == _DONE or not chunk:
            return ""
        self._buffer += chunk
        out: list[str] = []
        while True:
            if self._state == _DONE:
                self._buffer = ""
                break
            if self._state == _HUNT:
                self._buffer = self._buffer[self._search_from :]
                self._search_from = 0
                idx = self._buffer.find(_KEY)
                if idx == -1:
                    self._search_from = max(0, len(self._buffer) - len(_KEY) + 1)
                    break  # keep possible partial key, await more input
                after = idx + len(_KEY)
                nxt = self._buffer[after] if after < len(self._buffer) else ""
                if nxt.isalnum() or nxt == "_":
                    # A lookalike identifier ("answers") — skip past it.
                    self._search_from = after
                    continue
                self._buffer = self._buffer[after:]
                self._state = _WANT_COLON
            elif self._state == _WANT_COLON:
                stripped = self._buffer.lstrip(_COLON_WS)
                if not stripped:
                    self._buffer = ""
                    break  # whitespace only; await the colon
                if stripped[0] != ":":
                    # Not followed by ':' — cancel this hit, resume hunting.
                    self._buffer = stripped
                    self._state = _HUNT
                    continue
                self._buffer = stripped[1:]
                self._state = _WANT_QUOTE
            elif self._state == _WANT_QUOTE:
                stripped = self._buffer.lstrip(_COLON_WS)
                if not stripped:
                    self._buffer = ""
                    break  # await the opening quote
                if stripped[0] != '"':
                    self._buffer = stripped
                    self._state = _HUNT  # false hit, resume hunting
                    continue
                self._buffer = stripped[1:]
                self._state = _STRING
            else:  # _STRING / _ESC / _UNI — decode until the closing quote
                emitted, state, remainder = self._decode()
                out.append(emitted)
                self._buffer = remainder
                self._state = state
                if state in (_STRING, _ESC, _UNI):
                    break  # ran out of input mid-string
        return "".join(out)

    def _decode(self) -> tuple[str, int, str]:
        """Consume ``self._buffer`` from its start inside the string value.

        Returns ``(emitted_text, next_state, unconsumed_input)``. Whichever of
        _STRING/_ESC/_UNI we land on means the buffer was exhausted and the
        remainder must come from a future feed().
        """
        out: list[str] = []
        data = self._buffer
        n = len(data)
        i = 0
        state = self._state
        digits = self._digits
        while i < n:
            if state == _ESC:
                char = data[i]
                if char == "u":
                    digits = ""
                    state = _UNI
                    i += 1
                else:
                    mapped = {
                        '"': '"',
                        "\\": "\\",
                        "/": "/",
                        "b": "\b",
                        "f": "\f",
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                    }.get(char)
                    if mapped is None:
                        # Unknown escape — surface it literally instead of eating it.
                        out.append("\\" + char)
                    else:
                        out.append(mapped)
                    state = _STRING
                    i += 1
            elif state == _UNI:
                while i < n and len(digits) < 4 and data[i] in "0123456789abcdefABCDEF":
                    digits += data[i]
                    i += 1
                if len(digits) < 4:
                    if i >= n:
                        self._digits = digits
                        return "".join(out), _UNI, ""
                    # Invalid escape sequence — show it raw, carry on.
                    out.append("\\u" + digits)
                    digits = ""
                    state = _STRING
                else:
                    try:
                        out.append(chr(int(digits, 16)))
                    except ValueError:  # pragma: no cover — 4 hex cannot fail
                        pass
                    digits = ""
                    state = _STRING
            else:  # _STRING
                char = data[i]
                if char == "\\":
                    if i + 1 >= n:
                        return "".join(out), _ESC, ""
                    state = _ESC
                    i += 1  # consume the backslash; next pass reads the escapee
                elif char == '"':
                    return "".join(out), _DONE, data[i + 1 :]
                else:
                    out.append(char)
                    i += 1
        self._digits = digits
        return "".join(out), state, ""
