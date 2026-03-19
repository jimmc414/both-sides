"""Game session logger — captures all display output and player input to a file."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


# Regex to strip Rich markup tags like [bold red], [/bold], [dim], [#6B8EAF], etc.
_MARKUP_RE = re.compile(r"\[/?[^\]]*\]")


def strip_markup(text: str) -> str:
    """Remove Rich markup tags, leaving plain text."""
    return _MARKUP_RE.sub("", text)


class GameLogger:
    """Writes a plain-text transcript of the game session to a log file.

    Attach to GameDisplay via display.set_logger(logger). All render calls
    and player input are automatically mirrored to the log.
    """

    def __init__(self, log_dir: str | Path = "logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = self._log_dir / f"session_{timestamp}.log"
        self._file = open(self._path, "w", encoding="utf-8")
        self._write_header()

    def _write_header(self) -> None:
        self._file.write("=" * 72 + "\n")
        self._file.write("  BOTH SIDES — Game Session Log\n")
        self._file.write(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._file.write("=" * 72 + "\n\n")

    @property
    def path(self) -> Path:
        return self._path

    def log(self, text: str) -> None:
        """Write a line of plain text to the log."""
        clean = strip_markup(text)
        self._file.write(clean + "\n")
        self._file.flush()

    def log_raw(self, text: str) -> None:
        """Write text without adding a newline."""
        clean = strip_markup(text)
        self._file.write(clean)
        self._file.flush()

    def section(self, title: str) -> None:
        """Write a section divider."""
        self._file.write("\n" + "-" * 72 + "\n")
        self._file.write(f"  {title}\n")
        self._file.write("-" * 72 + "\n\n")
        self._file.flush()

    def subsection(self, title: str) -> None:
        """Write a minor divider."""
        self._file.write(f"\n--- {title} ---\n\n")
        self._file.flush()

    def blank(self) -> None:
        """Write a blank line."""
        self._file.write("\n")
        self._file.flush()

    def log_player_input(self, prompt: str, response: str) -> None:
        """Log a player input exchange."""
        self._file.write(f"  [{strip_markup(prompt)}] > {response}\n")
        self._file.flush()

    def log_state(
        self,
        chapter: int,
        phase: str,
        war_tension: int,
        iv_trust: int,
        iv_susp: int,
        ec_trust: int,
        ec_susp: int,
    ) -> None:
        """Log a game state snapshot."""
        self._file.write(
            f"  State: Ch{chapter} {phase} | "
            f"Tension {war_tension}% | "
            f"IV trust={iv_trust} susp={iv_susp} | "
            f"EC trust={ec_trust} susp={ec_susp}\n"
        )
        self._file.flush()

    def log_report_action(
        self, intel_id: str, action: str, target_faction: str,
        player_version: str | None = None,
    ) -> None:
        """Log a single report action."""
        line = f"  {intel_id} -> {target_faction}: {action.upper()}"
        if player_version:
            line += f' "{player_version[:80]}"'
        self._file.write(line + "\n")
        self._file.flush()

    def log_consequence(self, text: str) -> None:
        """Log a consequence line."""
        self._file.write(f"  - {strip_markup(text)}\n")
        self._file.flush()

    def close(self) -> None:
        """Write footer and close the log file."""
        self._file.write("\n" + "=" * 72 + "\n")
        self._file.write(f"  Session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._file.write("=" * 72 + "\n")
        self._file.close()

    def __del__(self) -> None:
        try:
            if not self._file.closed:
                self.close()
        except Exception:
            pass
