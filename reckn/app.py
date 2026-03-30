"""Textual UI for Reckn calculator notepad."""

from dataclasses import dataclass, field
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll, Center, Middle
from textual.widgets import Static, Button, Input, Label, ListItem, ListView, Checkbox
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from textual import events
from rich.text import Text

from .evaluator import LineEvaluator, format_config
from .pad import Pad, save_pad, load_pad, load_pad_from_path, list_pads
from .highlighter import highlight_line
from .settings import Settings, load_settings, save_settings
from . import clipboard
from . import pad as pad_module


class EditorLine(Static):
    """A single editable line in the editor."""

    DEFAULT_CSS = """
    EditorLine {
        height: auto;
        width: 2fr;
        padding: 0 1;
    }
    """

    class TextChanged(Message):
        """Message sent when line text changes."""
        def __init__(self, line_number: int, text: str) -> None:
            super().__init__()
            self.line_number = line_number
            self.text = text

    text = reactive("", init=False)
    cursor_pos = reactive(0)

    _SMART_SPACE_OPS = set("+-*/^=")

    def __init__(self, text: str = "", line_number: int = 0) -> None:
        super().__init__()
        self._text = text
        self.line_number = line_number
        self.cursor_pos = len(text)
        self.can_focus = True
        self._known_variables: set = set()
        self.smart_spaces: bool = False

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        if self._text != value:
            self._text = value
            self.refresh(layout=True)
            self.post_message(self.TextChanged(self.line_number, value))

    def set_text_no_notify(self, value: str) -> None:
        """Set text without triggering TextChanged message."""
        self._text = value
        self.cursor_pos = len(value)
        self.refresh(layout=True)

    def set_known_variables(self, variables: set) -> None:
        """Update known variable names for syntax highlighting."""
        if self._known_variables != variables:
            self._known_variables = variables
            self.refresh()

    def render(self) -> Text:
        """Render the line with syntax highlighting and cursor."""
        text = self._text

        if not text and not self.has_focus:
            return Text(" ")

        highlighted = highlight_line(text if text else "", self._known_variables)

        if self.has_focus:
            cursor_pos = self.cursor_pos
            result = Text()
            if cursor_pos > 0:
                result.append_text(highlighted[:cursor_pos])
            if cursor_pos < len(text):
                cursor_char = highlighted[cursor_pos:cursor_pos + 1]
                cursor_char.stylize("reverse", 0, 1)
                result.append_text(cursor_char)
                if cursor_pos + 1 < len(text):
                    result.append_text(highlighted[cursor_pos + 1:])
            else:
                result.append(" ", style="reverse")
            return result

        return highlighted

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for editing."""
        if event.key == "left":
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                self.refresh()
            event.stop()
        elif event.key == "right":
            if self.cursor_pos < len(self._text):
                self.cursor_pos += 1
                self.refresh()
            event.stop()
        elif event.key == "home":
            self.cursor_pos = 0
            self.refresh()
            event.stop()
        elif event.key == "end":
            self.cursor_pos = len(self._text)
            self.refresh()
            event.stop()
        elif event.key == "backspace":
            if self.cursor_pos > 0:
                self.text = self._text[:self.cursor_pos - 1] + self._text[self.cursor_pos:]
                self.cursor_pos -= 1
            elif self.line_number > 0:
                # Cursor at position 0 — merge with line above
                editor = self._get_editor()
                if editor:
                    idx = self.line_number
                    prev_line = editor.lines[idx - 1]
                    prev_len = len(prev_line._text)
                    prev_line.text = prev_line._text + self._text
                    editor.remove_line(idx)
                    editor.focus_line(idx - 1)
                    editor.lines[idx - 1].cursor_pos = prev_len
                    editor.lines[idx - 1].refresh()
            event.stop()
        elif event.key == "delete":
            if self.cursor_pos < len(self._text):
                self.text = self._text[:self.cursor_pos] + self._text[self.cursor_pos + 1:]
                event.stop()
        elif event.key == "ctrl+v":
            text = clipboard.paste()
            if text:
                first_line = text.split("\n")[0]
                self.insert_text(first_line)
            event.stop()
        elif event.character and event.character.isprintable() and not event.key.startswith("alt+"):
            ch = event.character
            if self.smart_spaces and ch in self._SMART_SPACE_OPS:
                before = self._text[:self.cursor_pos]
                after = self._text[self.cursor_pos:]
                stripped = before.rstrip()
                # Skip smart spacing for unary minus/plus (start of line or after operator/open paren)
                is_unary = ch in "+-" and (not stripped or stripped[-1] in "+-*/^=(")
                if is_unary:
                    self.text = before + ch + after
                    self.cursor_pos = len(before) + 1
                else:
                    # Add space before operator if not already there
                    if before and before[-1] != " ":
                        before += " "
                    # Add space after operator
                    insert = before + ch
                    if not after or after[0] != " ":
                        insert += " "
                    self.text = insert + after
                    self.cursor_pos = len(insert)
            else:
                self.text = self._text[:self.cursor_pos] + ch + self._text[self.cursor_pos:]
                self.cursor_pos += 1
            event.stop()

    def insert_text(self, text: str) -> None:
        """Insert text at the current cursor position."""
        self.text = self._text[:self.cursor_pos] + text + self._text[self.cursor_pos:]
        self.cursor_pos += len(text)

    def on_paste(self, event: events.Paste) -> None:
        """Handle paste from terminal (bracketed paste mode)."""
        if event.text:
            first_line = event.text.split("\n")[0]
            self.insert_text(first_line)
        event.stop()

    def on_click(self, event: events.Click) -> None:
        """Position cursor at the clicked column."""
        pos = max(0, min(event.x, len(self._text)))
        self.cursor_pos = pos
        self.refresh()

    def _get_editor(self):
        """Find the Editor ancestor."""
        node = self.parent
        while node and not isinstance(node, Editor):
            node = node.parent
        return node if isinstance(node, Editor) else None

    def on_focus(self, event: events.Focus) -> None:
        """Notify parent Editor when this line gets focus (e.g. via click)."""
        editor = self._get_editor()
        if editor:
            editor.current_line = self.line_number


class LineNumber(Static):
    """Line number gutter label."""

    DEFAULT_CSS = """
    LineNumber {
        width: 4;
        min-width: 4;
        height: auto;
        padding: 0 1 0 0;
        text-align: right;
        color: $text-disabled;
    }
    """

    def __init__(self, number: int) -> None:
        super().__init__(str(number + 1))
        self.number = number

    def update_number(self, number: int) -> None:
        self.number = number
        self.update(str(number + 1))


class LineRow(Horizontal):
    """A row containing an editor line and its result."""

    DEFAULT_CSS = """
    LineRow {
        height: auto;
        width: 100%;
    }
    """


class ResultLine(Static):
    """A single result line in the results panel."""

    DEFAULT_CSS = """
    ResultLine {
        height: auto;
        width: 1fr;
        min-width: 16;
        padding: 0 1;
        text-align: right;
        color: $text-muted;
        border-left: solid $secondary;
    }
    ResultLine:hover {
        background: $surface-lighten-1;
    }
    ResultLine.has-result {
        color: $success;
    }
    ResultLine.has-result:hover {
        background: $success 20%;
    }
    ResultLine.is-heading {
        color: $primary;
    }
    ResultLine.is-comment {
        color: $text-disabled;
    }
    ResultLine.is-subtotal {
        color: $warning;
        text-style: bold;
    }
    ResultLine.is-subtotal:hover {
        background: $warning 20%;
    }
    """

    class Clicked(Message):
        """Message sent when a result line is clicked."""
        def __init__(self, line_number: int) -> None:
            super().__init__()
            self.line_number = line_number

    def __init__(self, line_number: int = 0) -> None:
        super().__init__()
        self.line_number = line_number
        self._result = ""
        self._is_heading = False
        self._is_comment = False
        self._is_subtotal = False

    def on_click(self, event: events.Click) -> None:
        """Handle click on result line."""
        if self._result:
            self.post_message(self.Clicked(self.line_number))
            event.stop()

    def set_result(self, result: str, is_heading: bool = False,
                   is_comment: bool = False, is_subtotal: bool = False) -> None:
        """Set the result and styling."""
        self._result = result
        self._is_heading = is_heading
        self._is_comment = is_comment
        self._is_subtotal = is_subtotal
        self.set_class(bool(result), "has-result")
        self.set_class(is_heading, "is-heading")
        self.set_class(is_comment, "is-comment")
        self.set_class(is_subtotal, "is-subtotal")
        self.refresh()

    def render(self) -> Text:
        """Render the result."""
        if self._result:
            return Text(self._result, justify="right")
        return Text("")


class Editor(Vertical):
    """The left pane editor containing multiple lines."""

    DEFAULT_CSS = """
    Editor {
        width: 100%;
        height: 100%;
        border: solid $primary;
        background: $surface-darken-3;
        padding: 0;
        overflow-y: auto;
    }
    """

    MAX_LINES = 100
    current_line = reactive(0)

    class LineAdded(Message):
        """Message sent when a line is added."""
        pass

    class LineRemoved(Message):
        """Message sent when a line is removed."""
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    MAX_UNDO = 200
    UNDO_DEBOUNCE_SECONDS = 1.0  # Group typing bursts into one undo step

    def __init__(self, initial_lines: list[str] | None = None, show_line_numbers: bool = False, smart_spaces: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_lines = initial_lines or [""]
        self._show_line_numbers = show_line_numbers
        self._smart_spaces = smart_spaces
        self.lines: list[EditorLine] = []
        self.result_lines: list[ResultLine] = []
        self.line_numbers: list[LineNumber] = []
        # Undo/redo stacks: each entry is (lines_text, cursor_line, cursor_pos)
        self._undo_stack: list[tuple[list[str], int, int]] = []
        self._redo_stack: list[tuple[list[str], int, int]] = []
        self._restoring = False  # Flag to suppress snapshot during undo/redo restore
        self._undo_timer = None  # Debounce timer for text changes
        self._has_pending_changes = False  # Whether there are unsaved text changes

    def compose(self) -> ComposeResult:
        """Create initial line rows from initial_lines."""
        for i, text in enumerate(self._initial_lines):
            line_num = LineNumber(i)
            line_num.display = self._show_line_numbers
            editor_line = EditorLine(text, line_number=i)
            editor_line.smart_spaces = self._smart_spaces
            result_line = ResultLine(line_number=i)
            self.line_numbers.append(line_num)
            self.lines.append(editor_line)
            self.result_lines.append(result_line)
            yield LineRow(line_num, editor_line, result_line)

    def on_mount(self) -> None:
        """Focus the first line on mount."""
        if self.lines:
            self.lines[0].focus()
            self.current_line = 0
        # Save initial state
        self._push_snapshot()

    def _get_snapshot(self) -> tuple[list[str], int, int]:
        """Capture current editor state."""
        texts = [line._text for line in self.lines]
        cursor_line = self.current_line
        cursor_pos = self.lines[cursor_line].cursor_pos if 0 <= cursor_line < len(self.lines) else 0
        return (texts, cursor_line, cursor_pos)

    def _push_snapshot(self) -> None:
        """Push current state to undo stack unconditionally."""
        if self._restoring:
            return
        snapshot = self._get_snapshot()
        # Don't push if text is identical to top of stack
        if self._undo_stack and self._undo_stack[-1][0] == snapshot[0]:
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        # Any new change clears redo
        self._redo_stack.clear()
        self._has_pending_changes = False

    def _save_undo_snapshot_debounced(self) -> None:
        """Schedule a debounced undo snapshot for text typing.

        Typing creates many rapid changes. Instead of saving a snapshot per
        keystroke, we wait for a pause in typing (UNDO_DEBOUNCE_SECONDS).
        This groups typing bursts into one undo step.
        """
        if self._restoring:
            return
        self._has_pending_changes = True
        # Reset the debounce timer
        if self._undo_timer is not None:
            self._undo_timer.stop()
        self._undo_timer = self.set_timer(
            self.UNDO_DEBOUNCE_SECONDS, self._flush_undo_snapshot
        )

    def _flush_undo_snapshot(self) -> None:
        """Flush pending debounced snapshot to the undo stack."""
        self._undo_timer = None
        if self._has_pending_changes:
            self._push_snapshot()

    def _save_undo_snapshot_immediate(self) -> None:
        """Save an immediate undo snapshot for structural changes.

        Used for Enter (split line), Delete line, Backspace merge —
        actions that should each be one discrete undo step.
        Flushes any pending debounced snapshot first.
        """
        if self._restoring:
            return
        # Flush any pending typing snapshot before the structural change
        if self._has_pending_changes:
            if self._undo_timer is not None:
                self._undo_timer.stop()
                self._undo_timer = None
            self._push_snapshot()

    def undo(self) -> bool:
        """Undo the last change. Returns True if state was restored."""
        # Flush any pending typing changes so we capture the latest state
        if self._has_pending_changes:
            if self._undo_timer is not None:
                self._undo_timer.stop()
                self._undo_timer = None
            self._push_snapshot()
        if len(self._undo_stack) < 2:
            return False
        # Current state is top of undo stack; pop it to redo
        current = self._undo_stack.pop()
        self._redo_stack.append(current)
        # Restore previous state
        prev = self._undo_stack[-1]
        self._restore_snapshot(prev)
        return True

    def redo(self) -> bool:
        """Redo the last undone change. Returns True if state was restored."""
        if not self._redo_stack:
            return False
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(snapshot)
        self._restore_snapshot(snapshot)
        return True

    def _restore_snapshot(self, snapshot: tuple[list[str], int, int]) -> None:
        """Restore editor to a saved state."""
        texts, cursor_line, cursor_pos = snapshot
        self._restoring = True
        try:
            self.set_all_text(texts)
            cursor_line = min(cursor_line, len(self.lines) - 1)
            self.focus_line(cursor_line)
            self.lines[cursor_line].cursor_pos = min(cursor_pos, len(self.lines[cursor_line]._text))
            self.lines[cursor_line].refresh()
        finally:
            self._restoring = False

    def on_editor_line_text_changed(self, message: EditorLine.TextChanged) -> None:
        """Debounced undo snapshot for text typing."""
        self._save_undo_snapshot_debounced()

    def add_line(self, after_index: int = -1, text: str = "", notify: bool = True) -> bool:
        """Add a new line after the given index. Returns True if added."""
        self._save_undo_snapshot_immediate()
        if len(self.lines) >= self.MAX_LINES:
            return False
        if after_index < 0:
            after_index = len(self.lines) - 1
        line_num = LineNumber(after_index + 1)
        line_num.display = self._show_line_numbers
        editor_line = EditorLine(text, line_number=after_index + 1)
        editor_line.smart_spaces = self._smart_spaces
        result_line = ResultLine(line_number=after_index + 1)
        insert_pos = after_index + 1
        self.line_numbers.insert(insert_pos, line_num)
        self.lines.insert(insert_pos, editor_line)
        self.result_lines.insert(insert_pos, result_line)
        # Renumber lines after insertion
        for i in range(insert_pos, len(self.lines)):
            self.lines[i].line_number = i
            self.result_lines[i].line_number = i
            self.line_numbers[i].update_number(i)
        # Mount the row after the specified line's row
        row = LineRow(line_num, editor_line, result_line)
        after_row = self.lines[after_index].parent
        if after_index < len(self.lines) - 1 and after_row:
            self.mount(row, after=after_row)
        else:
            self.mount(row)
        if notify:
            self.post_message(self.LineAdded())
        self._push_snapshot()
        return True

    def remove_line(self, index: int, notify: bool = True) -> bool:
        """Remove the line at index. Returns True if removed."""
        self._save_undo_snapshot_immediate()
        if len(self.lines) <= 1 or index < 0 or index >= len(self.lines):
            return False
        editor_line = self.lines.pop(index)
        self.result_lines.pop(index)
        self.line_numbers.pop(index)
        # Remove the entire row (parent of editor_line)
        row = editor_line.parent
        if row:
            row.remove()
        else:
            editor_line.remove()
        # Renumber remaining lines
        for i in range(index, len(self.lines)):
            self.lines[i].line_number = i
            self.result_lines[i].line_number = i
            self.line_numbers[i].update_number(i)
        if notify:
            self.post_message(self.LineRemoved(index))
        self._push_snapshot()
        return True

    def focus_line(self, line_index: int) -> None:
        """Focus a specific line."""
        if 0 <= line_index < len(self.lines):
            self.lines[line_index].focus()
            self.current_line = line_index

    def on_key(self, event: events.Key) -> None:
        """Handle navigation keys."""
        if event.key == "up":
            if self.current_line > 0:
                self.focus_line(self.current_line - 1)
            event.stop()
        elif event.key == "down":
            if self.current_line < len(self.lines) - 1:
                self.focus_line(self.current_line + 1)
            event.stop()
        elif event.key == "enter":
            # Split the current line at cursor position
            current_widget = self.lines[self.current_line]
            text = current_widget._text
            cursor = current_widget.cursor_pos
            before = text[:cursor]
            after = text[cursor:]
            current_widget.text = before
            new_line_idx = self.current_line + 1
            if self.add_line(self.current_line, text=after):
                self.focus_line(new_line_idx)
                self.lines[new_line_idx].cursor_pos = 0
                self.lines[new_line_idx].refresh()
            event.stop()
        elif event.key == "delete":
            # Check if current line is empty - if so, delete it
            if self.current_line < len(self.lines):
                current = self.lines[self.current_line]
                if not current._text.strip():
                    if self.remove_line(self.current_line):
                        new_focus = max(0, self.current_line - 1)
                        self.focus_line(new_focus)
                        event.stop()
                        return
            # Let the event propagate to EditorLine for normal delete behavior

    def get_all_text(self) -> list[str]:
        """Get text from all lines."""
        return [line._text for line in self.lines]

    def update_known_variables(self, variables: set) -> None:
        """Update known variables on all lines for syntax highlighting."""
        for line in self.lines:
            line.set_known_variables(variables)

    def set_all_text(self, texts: list[str]) -> None:
        """Set text for all lines, growing/shrinking as needed."""
        was_restoring = self._restoring
        self._restoring = True
        try:
            # Ensure we have enough lines (don't notify - caller should sync)
            while len(self.lines) < len(texts) and len(self.lines) < self.MAX_LINES:
                self.add_line(notify=False)
            # Remove excess lines
            while len(self.lines) > max(len(texts), 1):
                self.remove_line(len(self.lines) - 1, notify=False)
            # Set the text
            for i, line in enumerate(self.lines):
                if i < len(texts):
                    line.set_text_no_notify(texts[i])
                else:
                    line.set_text_no_notify("")
        finally:
            self._restoring = was_restoring

    def set_result(self, line_index: int, result: str,
                   is_heading: bool = False, is_comment: bool = False,
                   is_subtotal: bool = False) -> None:
        """Set the result for a specific line."""
        if 0 <= line_index < len(self.result_lines):
            self.result_lines[line_index].set_result(result, is_heading, is_comment, is_subtotal)

    def reset_undo(self) -> None:
        """Reset undo/redo stacks (e.g. after loading a new pad)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._push_snapshot()

    def set_line_numbers_visible(self, visible: bool) -> None:
        """Show or hide line number gutter."""
        self._show_line_numbers = visible
        for ln in self.line_numbers:
            ln.display = visible

    def set_smart_spaces(self, enabled: bool) -> None:
        """Enable or disable smart spaces on all lines."""
        self._smart_spaces = enabled
        for line in self.lines:
            line.smart_spaces = enabled

    def clear(self) -> None:
        """Clear all lines (keep just one empty line)."""
        while len(self.lines) > 1:
            self.remove_line(len(self.lines) - 1, notify=False)
        if self.lines:
            self.lines[0].set_text_no_notify("")
        if self.result_lines:
            self.result_lines[0].set_result("")
        self.focus_line(0)


class StatusBar(Static):
    """Status bar at the bottom."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        width: 100%;
        color: $text-muted;
        padding: 0 1;
    }
    """

    pad_name = reactive("*new*")
    is_modified = reactive(False)
    is_offline = reactive(False)
    total_visible = reactive(True)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._totals: list = []

    @property
    def totals(self) -> list:
        return self._totals

    @totals.setter
    def totals(self, values: list) -> None:
        self._totals = values
        self.refresh()

    def render(self) -> Text:
        """Render the status bar with total right-aligned."""
        text = Text()

        if self.is_offline:
            text.append("[offline]", style="bold red")

        # Build total text on the right
        if self.total_visible and self._totals:
            from .evaluator import format_total_values
            total_str = f"Total: {format_total_values(self._totals)}"
            available = self.size.width - len(text.plain) - len(total_str)
            if available > 0:
                text.append(" " * available)
            else:
                text.append("  ")
            text.append(total_str, style="bold green")

        return text


@dataclass
class TabState:
    """State for a single tab."""
    tab_id: int
    editor: object  # Editor instance (forward reference)
    pad: Pad | None = None
    is_modified: bool = False
    display_name: str = ""


class TabBar(Static):
    """Tab bar showing open pads."""

    DEFAULT_CSS = """
    TabBar {
        height: 1;
        width: 100%;
        padding: 0 0 0 0;
    }
    """

    class TabClicked(Message):
        def __init__(self, tab_index: int) -> None:
            super().__init__()
            self.tab_index = tab_index

    def __init__(self) -> None:
        super().__init__()
        self._tabs: list[tuple[str, bool]] = []  # (name, is_modified)
        self._active: int = 0

    def set_tabs(self, tabs: list[tuple[str, bool]], active: int) -> None:
        self._tabs = tabs
        self._active = active
        self.refresh()

    def render(self) -> Text:
        text = Text()
        width = self.size.width - 1  # Available width (minus padding)

        # Build all labels to measure total length
        labels = []
        for i, (name, modified) in enumerate(self._tabs):
            mod = "*" if modified else ""
            label = f" {mod}{name} "
            sep = "│" if i < len(self._tabs) - 1 else ""
            labels.append((label, sep))

        # Calculate total length
        total_len = sum(len(l) + len(s) for l, s in labels)

        # If overflow, scroll to keep active tab visible
        start_idx = 0
        if total_len > width and len(labels) > 1:
            # Find the start index that keeps active tab visible
            # Show as many tabs as fit, centered on active
            start_idx = max(0, self._active - 1)
            while start_idx > 0:
                visible_len = sum(len(l) + len(s) for l, s in labels[start_idx:])
                if visible_len <= width:
                    break
                start_idx += 1
            if start_idx > 0:
                text.append("◂ ", style="dim")

        for i in range(start_idx, len(labels)):
            label, sep = labels[i]
            # Check if adding this label would overflow
            remaining = width - len(text.plain)
            if remaining < len(label) + 2 and i > self._active:
                text.append(" ▸", style="dim")
                break
            if i == self._active:
                # label is " name " or " *name " — strip spaces for underline
                inner = label.strip()
                text.append(" ", style="")
                text.append(inner, style="bold underline")
                text.append(" ", style="")
            else:
                text.append(label, style="dim")
            if sep:
                text.append(sep, style="dim")
        return text

    def on_click(self, event: events.Click) -> None:
        x = event.x
        pos = 0
        for i, (name, modified) in enumerate(self._tabs):
            mod = "*" if modified else ""
            label_len = len(f" {mod}{name} ")
            sep_len = 1 if i < len(self._tabs) - 1 else 0
            if x < pos + label_len + sep_len:
                self.post_message(self.TabClicked(i))
                return
            pos += label_len + sep_len


class MenuBar(Static):
    """Menu bar at the top of the application."""

    DEFAULT_CSS = """
    MenuBar {
        height: 1;
        width: 100%;
        padding: 0 1;
    }
    """

    class AboutClicked(Message):
        pass

    class FileClicked(Message):
        pass

    class SettingsClicked(Message):
        pass

    class HelpClicked(Message):
        pass

    def render(self) -> Text:
        # Layout: " File │ Settings │ Help              Reckn"
        text = Text()
        text.append("File", style="bold")
        text.append(" \u2502 ", style="dim")
        text.append("Settings", style="bold")
        text.append(" \u2502 ", style="dim")
        text.append("Help", style="bold")
        left_len = len("File \u2502 Settings \u2502 Help")
        label = "Reckn"
        available = self.size.width - left_len - len(label) - 2
        if available > 0:
            text.append(" " * available)
        text.append(label, style="bold")
        return text

    def on_click(self, event: events.Click) -> None:
        # Layout: " File │ Settings │ Help              Reckn"
        # File: x < 6, Settings: 6-18, Help: 18-24, Reckn: far right
        x = event.x
        width = self.size.width
        if x >= width - 7:
            self.post_message(self.AboutClicked())
        elif x < 6:
            self.post_message(self.FileClicked())
        elif x < 18:
            self.post_message(self.SettingsClicked())
        elif x < 24:
            self.post_message(self.HelpClicked())


class FileMenuItem(Static):
    """A single item in the file menu."""

    DEFAULT_CSS = """
    FileMenuItem {
        height: 1;
        width: 100%;
        padding: 0 1;
    }
    FileMenuItem:hover {
        background: $primary 40%;
    }
    FileMenuItem.highlighted {
        background: $primary;
        color: auto;
        text-style: bold;
    }
    """

    class Clicked(Message):
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    def __init__(self, label: str, shortcut: str, action: str) -> None:
        super().__init__()
        self._label = label
        self._shortcut = shortcut
        self._action = action

    def render(self) -> Text:
        text = Text()
        text.append(f" {self._label:<12}")
        text.append(f" {self._shortcut:>8}", style="dim")
        return text

    def on_click(self, event: events.Click) -> None:
        self.post_message(self.Clicked(self._action))
        event.stop()


class FileMenuScreen(ModalScreen[str]):
    """Dropdown file menu overlay."""

    DEFAULT_CSS = """
    FileMenuScreen {
        align: left top;
        background: transparent;
    }
    #file-menu-box {
        width: 28;
        height: auto;
        background: $surface;
        border: solid $primary;
        margin: 1 0 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f1", "close", "Close"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._highlighted = 0
        self._menu_items = [
            ("New Tab", "Ctrl+N", "new_pad"),
            ("Open", "Ctrl+O", "open_pad"),
            ("Close Tab", "Ctrl+W", "close_tab"),
            ("Save", "Ctrl+S", "save"),
            ("Export", "Ctrl+E", "export"),
            ("Quit", "Ctrl+Q", "quit"),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="file-menu-box"):
            for label, shortcut, action in self._menu_items:
                yield FileMenuItem(label, shortcut, action)

    def on_mount(self) -> None:
        self._update_highlight()

    def _update_highlight(self) -> None:
        for i, item in enumerate(self.query(FileMenuItem)):
            item.set_class(i == self._highlighted, "highlighted")

    def on_key(self, event: events.Key) -> None:
        if event.key == "up":
            self._highlighted = (self._highlighted - 1) % len(self._menu_items)
            self._update_highlight()
            event.stop()
        elif event.key == "down":
            self._highlighted = (self._highlighted + 1) % len(self._menu_items)
            self._update_highlight()
            event.stop()
        elif event.key == "enter":
            action = self._menu_items[self._highlighted][2]
            self.dismiss(action)
            event.stop()

    def action_close(self) -> None:
        self.dismiss("")

    def on_file_menu_item_clicked(self, message: FileMenuItem.Clicked) -> None:
        self.dismiss(message.action)

    def on_click(self, event: events.Click) -> None:
        """Click on transparent background closes menu."""
        self.dismiss("")


# Modal Screens


class AboutScreen(ModalScreen[str]):
    """About dialog showing version info."""

    DEFAULT_CSS = """
    AboutScreen {
        align: center middle;
    }
    #about-dialog {
        width: 44;
        height: 14;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #about-text {
        text-align: center;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        from . import __version__
        about = Text(justify="center")
        about.append("\n")
        about.append("Reckn\n", style="bold")
        about.append(f"v{__version__}\n\n", style="")
        about.append("Calculator notepad\n", style="dim")
        about.append("for the terminal\n\n", style="dim")
        about.append("MIT License\n\n", style="dim")
        about.append("Press Escape to close", style="dim italic")
        with Vertical(id="about-dialog"):
            yield Static(about, id="about-text")

    def action_close(self) -> None:
        self.dismiss("")

    def on_click(self, event: events.Click) -> None:
        self.dismiss("")


class HelpScreen(ModalScreen[str]):
    """Help screen with keyboard shortcuts and syntax reference (F3)."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: $surface 90%;
    }
    #help-container {
        width: 66;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #help-content {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f3", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-container"):
            yield Static(self._build_help(), id="help-content")

    def _build_help(self) -> Text:
        t = Text()

        def heading(s: str) -> None:
            t.append(f"\n {s}\n", style="bold underline")

        def shortcut(key: str, desc: str) -> None:
            t.append(f"  {key:<18}", style="bold")
            t.append(f"{desc}\n", style="")

        def example(expr: str, result: str) -> None:
            t.append(f"  {expr:<28}", style="")
            t.append(f"{result}\n", style="dim")

        def note(s: str) -> None:
            t.append(f"  {s}\n", style="dim italic")

        heading("TABS")
        shortcut("Ctrl+N", "New tab")
        shortcut("Ctrl+O", "Open pad in new tab")
        shortcut("Ctrl+W", "Close current tab")
        shortcut("Tab", "Next tab")
        shortcut("Click tab", "Switch to tab")

        heading("KEYBOARD SHORTCUTS")
        shortcut("Ctrl+S", "Save current tab")
        shortcut("Ctrl+E", "Export as markdown")
        shortcut("Ctrl+T", "Toggle floating total")
        shortcut("Ctrl+Z", "Undo")
        shortcut("Ctrl+Y", "Redo")
        shortcut("Ctrl+K", "Toggle comment")
        shortcut("Ctrl+X", "Delete line")
        shortcut("Ctrl+C", "Copy result to clipboard")
        shortcut("Ctrl+V", "Paste from clipboard")
        shortcut("Ctrl+Q", "Quit")
        shortcut("F1", "File menu")
        shortcut("F2", "Settings")
        shortcut("F3", "This help screen")
        shortcut("Click result", "Insert line reference")

        heading("STRUCTURE")
        example("# Monthly Budget", "Heading (not evaluated)")
        example("// a note", "Comment (not evaluated)")
        example("rent: 1200", "Label (display only)")
        example("rent = 1200", "Variable assignment")
        example("line1 + line2", "Reference previous results")
        example("--- or ===", "Subtotal")

        heading("ARITHMETIC & SI NOTATION")
        example("2 + 3 * (10 - 4)", "Standard precedence")
        example("2 ^ 10", "1,024")
        example("100k", "100,000  (k M B G)")
        example("salary = 60k", "Variable with SI")

        heading("UNITS & CONVERSIONS")
        example("10 inches in cm", "25.4 cm")
        example("5 km in miles", "3.11 mi")
        example("100 degC in degF", "212 \u00b0F")
        example("1000 MB in GB", "1 GB")
        example("100 km/h in mph", "62.14 mph")
        example("1 km + 500 m", "1,500 m")
        example("500 km / 2 hours", "250 km/h")
        note("Length, weight, time, data, speed, temperature")

        heading("CURRENCIES")
        example("$100 in EUR", "\u20ac84.79")
        example("100 GBP to USD", "$135.89")
        example("rent = 100 USD", "$100 (unit preserved)")
        note("Live rates from frankfurter.app, cached locally")

        heading("PERCENTAGES")
        example("25% of 1000", "250")
        example("10% off 200", "180")
        example("200 + 10%", "220")
        example("50 as % of 200", "25%")

        heading("DATES & CALENDAR")
        example("today", "25 March 2026")
        example("today + 3 weeks", "15 April 2026")
        example("June 12 + 3 months", "12 September 2026")
        example("from March 1 to April 1", "1 month")
        example("4 days from now", "29 March 2026")

        heading("CLOCK TIME")
        example("7:45am", "7:45 am")
        example("now + 2 hours", "(2 hours from now)")
        example("3:35pm - 11:00am", "4 hr 35 min")
        example("5.5 hours as timespan", "5 hr 30 min")

        heading("TIMEZONES")
        example("now in Tokyo", "(current time in Tokyo)")
        example("3:30pm CET in PST", "6:30 am PST")
        example("meeting = 2pm EST", "2:00 pm EST")
        example("meeting in CET", "8:00 pm CET")
        example("time difference between CET and PST", "9 hr")
        example("Tokyo vs New_York", "13 hr")
        note("City names or abbreviations, case-insensitive")

        heading("PROPORTIONS")
        example("3 is to 6 as what is to 10", "5")
        example("3 is to 6 as 9 is to what", "18")
        example("10 kg is to 20 kg as ? is to 50 kg", "25 kg")
        note("Use what, x, or ? for the unknown")

        heading("MATH FUNCTIONS")
        example("sqrt(144)", "12")
        example("abs(-42)", "42")
        example("round(3.7)", "4")
        example("round(3.14159, 2)", "3.14")
        example("floor(3.9) / ceil(3.1)", "3 / 4")
        example("min(10, 20, 5)", "5")
        example("max(line1, line2)", "(largest)")
        example("log(100) / log10(100)", "4.61 / 2")
        example("sin(0) / cos(0)", "0 / 1")
        note("abs, round, floor, ceil preserve units")

        t.append("\n")
        note("Press Escape or F2 to close")

        return t

    def action_close(self) -> None:
        self.dismiss("")

    def on_click(self, event: events.Click) -> None:
        # Only close if clicking outside the help container
        pass


class ThemePickerScreen(ModalScreen[str]):
    """Theme selection screen."""

    DEFAULT_CSS = """
    ThemePickerScreen { align: center middle; }
    #theme-dialog {
        width: 40;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #theme-dialog Label { width: 100%; padding-bottom: 1; }
    #theme-list { height: 1fr; }
    #theme-buttons { width: 100%; height: auto; align: center middle; padding-top: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current_theme: str) -> None:
        super().__init__()
        self._current = current_theme

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-dialog"):
            yield Label("Select Theme")
            with ListView(id="theme-list"):
                for name in sorted(self.app.available_themes):
                    marker = " \u2713" if name == self._current else ""
                    yield ListItem(Static(f"{name}{marker}"), id=f"theme-{name}")
            with Horizontal(id="theme-buttons"):
                yield Button("Cancel", id="cancel-btn")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            theme_name = event.item.id.replace("theme-", "", 1)
            self.app.theme = theme_name
            self._current = theme_name

    def action_cancel(self) -> None:
        self.dismiss(self._current)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._current)


class SettingsMenuScreen(ModalScreen[str]):
    """Dropdown settings menu, same style as FileMenuScreen."""

    DEFAULT_CSS = """
    SettingsMenuScreen {
        align: left top;
        background: transparent;
    }
    #settings-menu-box {
        width: 36;
        height: auto;
        background: $surface;
        border: solid $primary;
        margin: 1 0 0 8;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Close"),
    ]

    def __init__(self, current_theme: str, settings: Settings) -> None:
        super().__init__()
        self._highlighted = 0
        total_label = "Hide Total" if settings.show_totals else "Show Total"
        ln_label = "Hide Line Numbers" if settings.show_line_numbers else "Show Line Numbers"
        sep_label = "Disable Thousands Separator" if settings.thousands_separator else "Enable Thousands Separator"
        fmt_label = f"Large Numbers: {'SI (100k)' if settings.large_number_format == 'si' else 'Scientific (1e5)'}"
        smart_label = "Disable Smart Spaces" if settings.smart_spaces else "Enable Smart Spaces"
        self._menu_items = [
            (f"Theme: {current_theme}", "", "pick_theme"),
            ("Pads directory", "", "pick_pads_dir"),
            (total_label, "Ctrl+T", "toggle_total"),
            (ln_label, "", "toggle_line_numbers"),
            (sep_label, "", "toggle_thousands_sep"),
            (fmt_label, "", "toggle_large_number_fmt"),
            (smart_label, "", "toggle_smart_spaces"),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-menu-box"):
            for label, shortcut, action in self._menu_items:
                yield FileMenuItem(label, shortcut, action)

    def on_mount(self) -> None:
        self._update_highlight()

    def _update_highlight(self) -> None:
        for i, item in enumerate(self.query(FileMenuItem)):
            item.set_class(i == self._highlighted, "highlighted")

    def on_key(self, event: events.Key) -> None:
        if event.key == "up":
            self._highlighted = (self._highlighted - 1) % len(self._menu_items)
            self._update_highlight()
            event.stop()
        elif event.key == "down":
            self._highlighted = (self._highlighted + 1) % len(self._menu_items)
            self._update_highlight()
            event.stop()
        elif event.key == "enter":
            action = self._menu_items[self._highlighted][2]
            self.dismiss(action)
            event.stop()

    def action_close(self) -> None:
        self.dismiss("")

    def on_file_menu_item_clicked(self, message: FileMenuItem.Clicked) -> None:
        self.dismiss(message.action)

    def on_click(self, event: events.Click) -> None:
        self.dismiss("")


class PadsDirectoryScreen(ModalScreen[str]):
    """Screen to change pads directory."""

    DEFAULT_CSS = """
    PadsDirectoryScreen { align: center middle; }
    #pads-dir-dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #pads-dir-dialog Label { width: 100%; padding-bottom: 1; }
    #pads-dir-buttons { width: 100%; height: auto; align: center middle; padding-top: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current_dir: str) -> None:
        super().__init__()
        self._current_dir = current_dir

    def compose(self) -> ComposeResult:
        with Vertical(id="pads-dir-dialog"):
            yield Label("Pads Directory")
            yield Input(
                value=self._current_dir,
                placeholder="Enter directory path...",
                id="pads-dir-input"
            )
            with Horizontal(id="pads-dir-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#pads-dir-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            path = self.query_one("#pads-dir-input", Input).value.strip()
            if path:
                self.dismiss(path)
            else:
                self.dismiss("")
        elif event.button.id == "cancel-btn":
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        self.dismiss(path if path else "")

    def action_cancel(self) -> None:
        self.dismiss("")


class SaveScreen(ModalScreen[str]):
    """Modal screen for saving a pad."""

    DEFAULT_CSS = """
    SaveScreen {
        align: center middle;
    }

    #save-dialog {
        width: 50;
        height: 14;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #save-dialog Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    #save-dialog Input {
        width: 100%;
        margin-bottom: 1;
    }

    #save-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #save-buttons Button {
        margin: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_name: str = "") -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical(id="save-dialog"):
            yield Label("Save Pad")
            yield Input(
                value=self.current_name if self.current_name != "*new*" else "",
                placeholder="Enter pad name...",
                id="pad-name-input"
            )
            with Horizontal(id="save-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#pad-name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            name = self.query_one("#pad-name-input", Input).value.strip()
            if name:
                self.dismiss(name)
            else:
                self.notify("Please enter a name", severity="error")
        elif event.button.id == "cancel-btn":
            self.dismiss("")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Replace spaces with underscores as the user types."""
        if " " in event.value:
            inp = self.query_one("#pad-name-input", Input)
            new_value = event.value.replace(" ", "_")
            cursor = inp.cursor_position
            inp.value = new_value
            inp.cursor_position = cursor

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name:
            self.dismiss(name)

    def action_cancel(self) -> None:
        self.dismiss("")


class OpenScreen(ModalScreen[str]):
    """Modal screen for opening a pad."""

    DEFAULT_CSS = """
    OpenScreen {
        align: center middle;
    }

    #open-dialog {
        width: 60;
        height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #open-dialog Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    #pad-list {
        height: 1fr;
        border: solid $secondary;
        margin-bottom: 1;
    }

    #open-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #open-buttons Button {
        margin: 0 2;
    }

    .pad-item {
        padding: 0 1;
    }

    .pad-item:hover {
        background: $primary 20%;
    }

    .no-pads {
        padding: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.pads = list_pads()
        self.selected_path = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="open-dialog"):
            yield Label("Open Pad")
            if self.pads:
                with ListView(id="pad-list"):
                    for pad_info in self.pads:
                        yield ListItem(
                            Static(pad_info["name"], classes="pad-item"),
                            id=f"pad-{pad_info['name']}"
                        )
                        # Store path in a way we can retrieve
            else:
                yield Static("No saved pads found", classes="no-pads")
            with Horizontal(id="open-buttons"):
                yield Button("Open", variant="primary", id="open-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        list_view = self.query_one("#pad-list", ListView) if self.pads else None
        if list_view:
            list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection (double-click or enter)."""
        if event.item and event.item.id:
            # Extract pad name from id
            pad_name = event.item.id.replace("pad-", "")
            for pad_info in self.pads:
                if pad_info["name"] == pad_name:
                    self.dismiss(str(pad_info["path"]))
                    return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "open-btn":
            list_view = self.query_one("#pad-list", ListView) if self.pads else None
            if list_view and list_view.highlighted_child:
                item = list_view.highlighted_child
                if item and item.id:
                    pad_name = item.id.replace("pad-", "")
                    for pad_info in self.pads:
                        if pad_info["name"] == pad_name:
                            self.dismiss(str(pad_info["path"]))
                            return
            self.notify("Please select a pad", severity="warning")
        elif event.button.id == "cancel-btn":
            self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")


class ConfirmScreen(ModalScreen[bool]):
    """Modal screen for confirmation dialogs."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 50;
        height: 12;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }

    #confirm-dialog Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    #confirm-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #confirm-buttons Button {
        margin: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self.message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", variant="warning", id="yes-btn")
                yield Button("No", variant="primary", id="no-btn")

    def on_mount(self) -> None:
        self.query_one("#yes-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes-btn")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ExportScreen(ModalScreen[str]):
    """Modal screen for exporting pad as markdown."""

    DEFAULT_CSS = """
    ExportScreen {
        align: center middle;
    }

    #export-dialog {
        width: 70;
        height: 14;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #export-dialog Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    #export-dialog Input {
        width: 100%;
        margin-bottom: 1;
    }

    #export-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #export-buttons Button {
        margin: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, default_name: str = "export") -> None:
        super().__init__()
        from pathlib import Path
        self.default_path = Path.home() / "Documents" / f"{default_name}.md"

    def compose(self) -> ComposeResult:
        with Vertical(id="export-dialog"):
            yield Label("Export as Markdown")
            yield Input(
                value=str(self.default_path),
                placeholder="Enter file path...",
                id="export-path-input"
            )
            with Horizontal(id="export-buttons"):
                yield Button("Export", variant="primary", id="export-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        input_widget = self.query_one("#export-path-input", Input)
        input_widget.focus()
        # Select just the filename part for easy editing
        input_widget.cursor_position = len(str(self.default_path))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export-btn":
            path = self.query_one("#export-path-input", Input).value.strip()
            if path:
                self.dismiss(path)
            else:
                self.notify("Please enter a file path", severity="error")
        elif event.button.id == "cancel-btn":
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        if path:
            self.dismiss(path)

    def action_cancel(self) -> None:
        self.dismiss("")


class QuitScreen(ModalScreen[list[int] | None]):
    """Quit dialog with checklist of unsaved tabs to save."""

    DEFAULT_CSS = """
    QuitScreen { align: center middle; }
    #quit-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #quit-dialog Label { width: 100%; padding-bottom: 1; }
    .quit-checkbox { padding: 0 2; }
    #quit-buttons { width: 100%; height: auto; align: center middle; padding-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, unsaved_tabs: list[tuple[int, str]]) -> None:
        super().__init__()
        self._unsaved_tabs = unsaved_tabs

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-dialog"):
            yield Label("Unsaved Changes")
            for idx, name in self._unsaved_tabs:
                yield Checkbox(name, value=True, id=f"quit-cb-{idx}", classes="quit-checkbox")
            with Horizontal(id="quit-buttons"):
                yield Button("[u]S[/u]ave & Quit", variant="primary", id="save-quit-btn")
                yield Button("[u]Q[/u]uit", variant="warning", id="quit-btn")
                yield Button("[u]C[/u]ancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#save-quit-btn", Button).focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "s":
            event.stop()
            event.prevent_default()
            self._do_save_quit()
        elif event.key == "q":
            event.stop()
            event.prevent_default()
            self.dismiss([])
        elif event.key == "c":
            event.stop()
            event.prevent_default()
            self.dismiss(None)
        elif event.key in ("tab", "down", "right"):
            event.stop()
            event.prevent_default()
            self.focus_next()
        elif event.key in ("shift+tab", "up", "left"):
            event.stop()
            event.prevent_default()
            self.focus_previous()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-quit-btn":
            self._do_save_quit()
        elif event.button.id == "quit-btn":
            self.dismiss([])
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def _do_save_quit(self) -> None:
        to_save = []
        for idx, name in self._unsaved_tabs:
            cb = self.query_one(f"#quit-cb-{idx}", Checkbox)
            if cb.value:
                to_save.append(idx)
        self.dismiss(to_save)

    def action_cancel(self) -> None:
        self.dismiss(None)


class RecknApp(App):
    """The main Reckn application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+o", "open_pad", "Open"),
        Binding("ctrl+n", "new_pad", "New Tab"),
        Binding("ctrl+e", "export", "Export"),
        Binding("ctrl+t", "toggle_total", "Toggle Total"),
        Binding("ctrl+k", "toggle_comment", "Comment", show=False),
        Binding("ctrl+x", "delete_line", "Delete Line", show=False),
        Binding("ctrl+c", "copy", "Copy", show=False, priority=True),
        Binding("ctrl+w", "close_tab", "Close Tab", show=False),
        Binding("tab", "next_tab", "Next Tab", show=False, priority=True),
        Binding("alt+f", "toggle_file_menu", "File Menu", show=False, priority=True),
        Binding("f1", "toggle_file_menu", "File Menu", show=False),
        Binding("f2", "toggle_settings", "Settings", show=False),
        Binding("f3", "toggle_help", "Help", show=False),
        Binding("f10", "show_about", show=False),
        Binding("ctrl+z", "undo", "Undo", show=False),
        Binding("ctrl+shift+z", "redo", "Redo", show=False),
        Binding("ctrl+y", "redo", "Redo", show=False),
    ]

    _MODAL_BLOCKED_ACTIONS = frozenset({
        "quit", "next_tab", "close_tab", "save", "open_pad", "new_pad",
        "export", "toggle_total", "toggle_comment", "delete_line", "copy",
        "undo", "redo", "toggle_file_menu", "toggle_settings",
        "toggle_help", "show_about",
    })

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self.screen.is_modal and action in self._MODAL_BLOCKED_ACTIONS:
            return False
        return True

    def __init__(self, pad_name: str | None = None) -> None:
        super().__init__()
        self.evaluator = LineEvaluator()
        self._eval_pending = False
        self._initial_pad_name = pad_name
        self._clipboard_warned = False
        self._settings = load_settings()
        # Tab state
        self.tabs: list[TabState] = []
        self._active_tab_index: int = 0
        self._next_tab_id: int = 1
        self._new_pad_counter: int = 1
        self._quit_save_queue: list[int] = []

    @property
    def active_tab(self) -> TabState:
        return self.tabs[self._active_tab_index]

    @property
    def active_editor(self) -> Editor:
        return self.active_tab.editor

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        initial_editor = Editor(show_line_numbers=self._settings.show_line_numbers, smart_spaces=self._settings.smart_spaces, id="editor-1")
        yield MenuBar()
        with Vertical(id="main-container"):
            yield initial_editor
        yield StatusBar()
        yield TabBar()

    def on_mount(self) -> None:
        """Set up the app on mount."""
        self.title = "Reckn"
        self.sub_title = "Calculator Notepad"

        # Create initial tab from the editor created in compose
        editor = self.query_one("#editor-1", Editor)
        tab = TabState(
            tab_id=1,
            editor=editor,
            display_name=f"new pad {self._new_pad_counter}",
        )
        self.tabs.append(tab)
        self._next_tab_id = 2
        self._new_pad_counter = 2

        # Register custom themes
        self._register_custom_themes()

        # Apply settings
        self._apply_settings()

        # Load initial pad if specified
        if self._initial_pad_name:
            self._load_pad_by_name(self._initial_pad_name)

        self._refresh_tab_bar()
        self._refresh_status_bar()
        self._start_currency_fetch()

    def _register_custom_themes(self) -> None:
        """Register custom themes not included in Textual."""
        from textual.theme import Theme
        self.register_theme(Theme(
            name="ubuntu",
            primary="#E95420",      # Ubuntu orange
            secondary="#772953",    # Aubergine
            accent="#77216F",       # Purple
            warning="#F99B11",      # Warm yellow
            error="#DF382C",        # Red
            success="#38B44A",      # Green
            surface="#2C001E",      # Dark aubergine
            panel="#3C0028",
            dark=True,
        ))

    def _apply_settings(self) -> None:
        """Apply loaded settings."""
        s = self._settings
        if s.theme and s.theme in self.available_themes:
            self.theme = s.theme
        if s.pads_directory:
            from pathlib import Path
            pad_module.PADS_DIR = Path(s.pads_directory)
        try:
            self.query_one(StatusBar).total_visible = s.show_totals
        except Exception:
            pass

    # --- Tab management ---

    def _refresh_tab_bar(self) -> None:
        try:
            tab_bar = self.query_one(TabBar)
            tab_data = [(t.display_name, t.is_modified) for t in self.tabs]
            tab_bar.set_tabs(tab_data, self._active_tab_index)
        except Exception:
            pass

    def _refresh_status_bar(self) -> None:
        try:
            status_bar = self.query_one(StatusBar)
            tab = self.active_tab
            status_bar.pad_name = tab.display_name
            status_bar.is_modified = tab.is_modified
        except Exception:
            pass

    def _switch_to_tab(self, index: int) -> None:
        if index < 0 or index >= len(self.tabs) or index == self._active_tab_index:
            return
        self.active_tab.editor.display = False
        self._active_tab_index = index
        self.active_tab.editor.display = True
        self.active_tab.editor.focus_line(self.active_tab.editor.current_line)
        self._refresh_tab_bar()
        self._refresh_status_bar()
        self._do_evaluation()

    def _create_tab(self, pad: Pad | None = None) -> TabState:
        tab_id = self._next_tab_id
        self._next_tab_id += 1

        lines = pad.lines if pad and pad.lines else None
        editor = Editor(initial_lines=lines, show_line_numbers=self._settings.show_line_numbers, smart_spaces=self._settings.smart_spaces, id=f"editor-{tab_id}")

        container = self.query_one("#main-container", Vertical)
        container.mount(editor)
        editor.display = False

        if pad:
            display_name = pad.name
        else:
            display_name = f"new pad {self._new_pad_counter}"
            self._new_pad_counter += 1

        tab = TabState(
            tab_id=tab_id,
            editor=editor,
            pad=pad,
            is_modified=False,
            display_name=display_name,
        )
        self.tabs.append(tab)
        self._switch_to_tab(len(self.tabs) - 1)

        if pad:
            def _init():
                editor.reset_undo()
                self._do_evaluation()
            self.set_timer(0.05, _init)

        return tab

    def _close_tab(self, index: int) -> None:
        if len(self.tabs) <= 1:
            # Last tab — just clear it, keep same name
            tab = self.tabs[0]
            tab.editor.clear()
            tab.pad = None
            tab.is_modified = False
            if not tab.display_name.startswith("new pad"):
                tab.display_name = f"new pad {self._new_pad_counter}"
                self._new_pad_counter += 1
            tab.editor.reset_undo()
            self._refresh_tab_bar()
            self._refresh_status_bar()
            self._do_evaluation()
            return

        tab = self.tabs[index]
        tab.editor.remove()
        self.tabs.pop(index)

        if self._active_tab_index >= len(self.tabs):
            self._active_tab_index = len(self.tabs) - 1
        elif self._active_tab_index > index:
            self._active_tab_index -= 1

        self.active_tab.editor.display = True
        self._refresh_tab_bar()
        self._refresh_status_bar()
        self._do_evaluation()
        self.active_editor.focus_line(self.active_editor.current_line)

    def _find_editor_ancestor(self, widget) -> Editor | None:
        """Walk up the widget tree to find the Editor ancestor."""
        node = widget.parent if hasattr(widget, 'parent') else None
        while node and not isinstance(node, Editor):
            node = node.parent
        return node if isinstance(node, Editor) else None

    def _is_from_active_editor(self, message) -> bool:
        """Check if a message originates from the active editor."""
        # For messages from EditorLine or ResultLine, walk up to find Editor
        sender = getattr(message, '_sender', None)
        if sender is None:
            return True  # Can't determine, assume active
        editor = self._find_editor_ancestor(sender)
        return editor is self.active_editor

    # --- Currency ---

    def _start_currency_fetch(self) -> None:
        from .currencies import get_converter
        converter = get_converter()
        if not converter.rates:
            converter.fetch_rates_in_background(on_complete=self._on_currency_loaded)

    def _on_currency_loaded(self, success: bool) -> None:
        self.call_from_thread(self._handle_currency_loaded, success)

    def _handle_currency_loaded(self, success: bool) -> None:
        if not success:
            from .currencies import get_converter
            converter = get_converter()
            if not converter.rates:
                try:
                    self.query_one(StatusBar).is_offline = True
                except Exception:
                    pass
        self._do_evaluation()

    # --- Menu bar handlers ---

    def on_menu_bar_about_clicked(self, message: MenuBar.AboutClicked) -> None:
        self.action_show_about()

    def on_menu_bar_file_clicked(self, message: MenuBar.FileClicked) -> None:
        self.action_toggle_file_menu()

    def on_menu_bar_settings_clicked(self, message: MenuBar.SettingsClicked) -> None:
        self.action_toggle_settings()

    def on_menu_bar_help_clicked(self, message: MenuBar.HelpClicked) -> None:
        self.action_toggle_help()

    def on_tab_bar_tab_clicked(self, message: TabBar.TabClicked) -> None:
        self._switch_to_tab(message.tab_index)

    def action_show_about(self) -> None:
        self.push_screen(AboutScreen(), lambda _: None)

    def action_toggle_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.screen.dismiss("")
            return
        self.push_screen(HelpScreen(), lambda _: None)

    def action_toggle_settings(self) -> None:
        if isinstance(self.screen, SettingsMenuScreen):
            self.screen.dismiss("")
            return
        try:
            self._settings.show_totals = self.query_one(StatusBar).total_visible
        except Exception:
            pass
        self.push_screen(
            SettingsMenuScreen(self.theme or "textual-dark", self._settings),
            self._handle_settings_menu
        )

    def _handle_settings_menu(self, action: str) -> None:
        if not action:
            return
        if action == "pick_theme":
            self.push_screen(
                ThemePickerScreen(self.theme or "textual-dark"),
                self._handle_theme_picked
            )
        elif action == "pick_pads_dir":
            pads_dir = self._settings.pads_directory or str(pad_module.PADS_DIR)
            self.push_screen(
                PadsDirectoryScreen(pads_dir),
                self._handle_pads_dir_picked
            )
        elif action == "toggle_total":
            self.action_toggle_total()
        elif action == "toggle_line_numbers":
            self._toggle_line_numbers()
        elif action == "toggle_thousands_sep":
            self._toggle_thousands_separator()
        elif action == "toggle_large_number_fmt":
            self._toggle_large_number_format()
        elif action == "toggle_smart_spaces":
            self._toggle_smart_spaces()

    def _toggle_line_numbers(self) -> None:
        self._settings.show_line_numbers = not self._settings.show_line_numbers
        for tab in self.tabs:
            if tab.editor:
                tab.editor.set_line_numbers_visible(self._settings.show_line_numbers)
        save_settings(self._settings)
        label = "on" if self._settings.show_line_numbers else "off"
        self.notify(f"Line numbers {label}")

    def _toggle_thousands_separator(self) -> None:
        self._settings.thousands_separator = not self._settings.thousands_separator
        save_settings(self._settings)
        label = "on" if self._settings.thousands_separator else "off"
        self.notify(f"Thousands separator {label}")
        self._schedule_evaluation()

    def _toggle_large_number_format(self) -> None:
        if self._settings.large_number_format == "si":
            self._settings.large_number_format = "scientific"
        else:
            self._settings.large_number_format = "si"
        save_settings(self._settings)
        self.notify(f"Large numbers: {self._settings.large_number_format.upper()}")
        self._schedule_evaluation()

    def _toggle_smart_spaces(self) -> None:
        self._settings.smart_spaces = not self._settings.smart_spaces
        for tab in self.tabs:
            if tab.editor:
                tab.editor.set_smart_spaces(self._settings.smart_spaces)
        save_settings(self._settings)
        label = "on" if self._settings.smart_spaces else "off"
        self.notify(f"Smart spaces {label}")

    def _handle_theme_picked(self, theme_name: str) -> None:
        if not theme_name:
            return
        if theme_name in self.available_themes:
            self.theme = theme_name
            self._settings.theme = theme_name
            save_settings(self._settings)

    def _handle_pads_dir_picked(self, new_dir: str) -> None:
        if not new_dir:
            return
        from pathlib import Path
        import shutil
        path = Path(new_dir).expanduser()
        old_path = pad_module.PADS_DIR

        # Validate: can't be a file
        if path.exists() and not path.is_dir():
            self.notify(f"Not a directory: {path}", severity="error")
            return

        # Create if needed
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.notify(f"Cannot create directory: {e}", severity="error")
            return

        # Move existing pads if old dir has files
        if old_path.exists() and old_path != path:
            pad_files = list(old_path.glob("*.json"))
            if pad_files:
                for f in pad_files:
                    dest = path / f.name
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
                self.notify(f"Moved {len(pad_files)} pad(s) to {path}")

        pad_module.PADS_DIR = path
        default_dir = str(Path.home() / ".config" / "reckn" / "pads")
        self._settings.pads_directory = str(path) if str(path) != default_dir else ""
        save_settings(self._settings)
        self.notify(f"Pads directory: {path}")

    def action_toggle_file_menu(self) -> None:
        if isinstance(self.screen, FileMenuScreen):
            self.screen.dismiss("")
            return
        self.push_screen(FileMenuScreen(), self._handle_file_menu)

    def _handle_file_menu(self, action: str) -> None:
        if not action:
            return
        action_method = getattr(self, f"action_{action}", None)
        if action_method:
            action_method()

    # --- Editor event handlers (with message origin filtering) ---

    def on_editor_line_text_changed(self, message: EditorLine.TextChanged) -> None:
        if not self._is_from_active_editor(message):
            return
        self.active_tab.is_modified = True
        self._refresh_tab_bar()
        self._refresh_status_bar()
        self._schedule_evaluation()

    def on_result_line_clicked(self, message: ResultLine.Clicked) -> None:
        if not self._is_from_active_editor(message):
            return
        editor = self.active_editor
        current_line_idx = editor.current_line
        if 0 <= current_line_idx < len(editor.lines):
            current_line = editor.lines[current_line_idx]
            line_ref = f"line{message.line_number + 1}"
            current_line.insert_text(line_ref)
            self._schedule_evaluation()

    def on_editor_line_added(self, message: Editor.LineAdded) -> None:
        if not self._is_from_active_editor(message):
            return
        self._schedule_evaluation()

    def on_editor_line_removed(self, message: Editor.LineRemoved) -> None:
        if not self._is_from_active_editor(message):
            return
        self._schedule_evaluation()

    # --- Editor actions ---

    def action_toggle_comment(self) -> None:
        editor = self.active_editor
        if editor.current_line < len(editor.lines):
            line = editor.lines[editor.current_line]
            text = line._text.strip()
            if text.startswith("// "):
                line.text = line._text.replace("// ", "", 1)
            elif text.startswith("//"):
                line.text = line._text.replace("//", "", 1)
            else:
                line.text = "// " + line._text
            self._schedule_evaluation()

    def action_undo(self) -> None:
        if self.active_editor.undo():
            self._schedule_evaluation()

    def action_redo(self) -> None:
        if self.active_editor.redo():
            self._schedule_evaluation()

    def action_delete_line(self) -> None:
        editor = self.active_editor
        current = editor.current_line
        if editor.remove_line(current):
            new_focus = max(0, current - 1) if current > 0 else 0
            editor.focus_line(new_focus)
        elif len(editor.lines) == 1:
            editor.lines[0].text = ""
            editor.lines[0].cursor_pos = 0

    def _check_clipboard(self) -> bool:
        if clipboard.is_available():
            return True
        if not self._clipboard_warned:
            self._clipboard_warned = True
            self.notify("Install xclip for clipboard support", severity="warning")
        return False

    def action_copy(self) -> None:
        if not self._check_clipboard():
            return
        editor = self.active_editor
        idx = editor.current_line
        if 0 <= idx < len(editor.result_lines):
            result = editor.result_lines[idx]._result
            if result:
                clipboard.copy(result)
                self.notify("Result copied")
            else:
                self.notify("No result to copy", severity="warning")

    # --- Evaluation ---

    def _schedule_evaluation(self) -> None:
        if not self._eval_pending:
            self._eval_pending = True
            self.set_timer(0.1, self._do_evaluation)

    def _do_evaluation(self) -> None:
        self._eval_pending = False
        editor = self.active_editor

        # Sync formatting settings
        format_config["thousands_separator"] = self._settings.thousands_separator
        format_config["large_number_format"] = self._settings.large_number_format

        lines = editor.get_all_text()
        self.evaluator = LineEvaluator()

        for i, line_text in enumerate(lines):
            stripped = line_text.strip()
            is_heading = stripped.startswith('#')
            is_comment = stripped.startswith('//')
            result = self.evaluator.evaluate_line(line_text, i + 1)
            is_subtotal = self.evaluator.is_subtotal_line(i + 1)
            editor.set_result(i, result, is_heading, is_comment, is_subtotal)

        try:
            self.query_one(StatusBar).totals = self.evaluator.get_floating_totals()
        except Exception:
            pass

        known_vars = set(self.evaluator.context.variables.keys())
        editor.update_known_variables(known_vars)

    # --- Tab navigation ---

    def action_next_tab(self) -> None:
        if len(self.tabs) > 1:
            next_idx = (self._active_tab_index + 1) % len(self.tabs)
            self._switch_to_tab(next_idx)

    def action_close_tab(self) -> None:
        tab = self.active_tab
        if tab.is_modified:
            self.push_screen(
                ConfirmScreen(f"'{tab.display_name}' has unsaved changes. Close anyway?"),
                self._handle_close_tab_confirm
            )
        else:
            self._close_tab(self._active_tab_index)

    def _handle_close_tab_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self._close_tab(self._active_tab_index)

    # --- Quit ---

    def action_quit(self) -> None:
        unsaved = [(i, t.display_name) for i, t in enumerate(self.tabs) if t.is_modified]
        if not unsaved:
            self.exit()
            return
        self.push_screen(QuitScreen(unsaved), self._handle_quit)

    def _handle_quit(self, result: list[int] | None) -> None:
        if result is None:
            return
        if not result:
            self.exit()
            return
        self._quit_save_queue = list(result)
        self._process_quit_save_queue()

    def _process_quit_save_queue(self) -> None:
        if not self._quit_save_queue:
            self.exit()
            return
        idx = self._quit_save_queue.pop(0)
        if idx >= len(self.tabs):
            self._process_quit_save_queue()
            return
        tab = self.tabs[idx]
        if tab.pad and tab.pad.name:
            tab.pad.lines = tab.editor.get_all_text()
            try:
                save_pad(tab.pad)
            except Exception:
                pass
            self._process_quit_save_queue()
        else:
            self._switch_to_tab(idx)
            self.push_screen(SaveScreen(tab.display_name), self._handle_quit_save_name)

    def _handle_quit_save_name(self, name: str) -> None:
        if name:
            tab = self.active_tab
            lines = tab.editor.get_all_text()
            while lines and not lines[-1].strip():
                lines.pop()
            tab.pad = Pad.new(name)
            tab.pad.lines = lines
            try:
                save_pad(tab.pad)
            except Exception:
                pass
        self._process_quit_save_queue()

    # --- Save ---

    def action_save(self) -> None:
        tab = self.active_tab
        self.push_screen(SaveScreen(tab.display_name), self._handle_save)

    def _handle_save(self, name: str) -> None:
        if not name:
            return
        tab = self.active_tab
        lines = tab.editor.get_all_text()
        while lines and not lines[-1].strip():
            lines.pop()

        if tab.pad:
            tab.pad.name = name
            tab.pad.lines = lines
        else:
            tab.pad = Pad.new(name)
            tab.pad.lines = lines

        try:
            path = save_pad(tab.pad)
            tab.display_name = name
            tab.is_modified = False
            self._refresh_tab_bar()
            self._refresh_status_bar()
            self.notify(f"Saved to {path.name}")
        except Exception as e:
            self.notify(f"Error saving: {e}", severity="error")

    # --- Open ---

    def action_open_pad(self) -> None:
        if len(self.tabs) >= 9:
            self.notify("Maximum 9 tabs", severity="warning")
            return
        self.push_screen(OpenScreen(), self._handle_open)

    def _handle_open(self, path_str: str) -> None:
        if not path_str:
            return
        from pathlib import Path
        pad = load_pad_from_path(Path(path_str))
        if pad:
            # Check if already open
            for i, tab in enumerate(self.tabs):
                if tab.pad and tab.pad.name == pad.name:
                    self._switch_to_tab(i)
                    self.notify(f"Switched to: {pad.name}")
                    return
            self._create_tab(pad=pad)
            self.notify(f"Opened: {pad.name}")
        else:
            self.notify("Failed to open pad", severity="error")

    # --- New tab ---

    def action_new_pad(self) -> None:
        if len(self.tabs) >= 9:
            self.notify("Maximum 9 tabs", severity="warning")
            return
        self._create_tab()

    # --- Load pad by name (CLI argument) ---

    def _load_pad_by_name(self, name: str) -> None:
        pad = load_pad(name)
        if pad:
            tab = self.active_tab
            tab.pad = pad
            tab.display_name = pad.name
            tab.editor.set_all_text(pad.lines if pad.lines else [""])
            tab.is_modified = False
            tab.editor.reset_undo()
            self._do_evaluation()
            tab.editor.focus_line(0)
        else:
            tab = self.active_tab
            tab.display_name = name
            tab.pad = Pad.new(name)

    # --- Toggle total ---

    def action_toggle_total(self) -> None:
        try:
            status_bar = self.query_one(StatusBar)
            status_bar.total_visible = not status_bar.total_visible
            self._settings.show_totals = status_bar.total_visible
            save_settings(self._settings)
            if status_bar.total_visible:
                self.notify("Floating total shown")
            else:
                self.notify("Floating total hidden")
        except Exception:
            pass

    # --- Export ---

    def action_export(self) -> None:
        tab = self.active_tab
        default_name = tab.display_name
        if default_name.startswith("new pad"):
            default_name = "export"
        default_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in default_name)
        self.push_screen(ExportScreen(default_name), self._handle_export)

    def _handle_export(self, path_str: str) -> None:
        if not path_str:
            return
        from pathlib import Path
        path = Path(path_str).expanduser()
        if not path.suffix:
            path = path.with_suffix(".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            markdown = self._generate_export_markdown()
            path.write_text(markdown)
            self.notify(f"Exported to {path}")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    def _generate_export_markdown(self) -> str:
        editor = self.active_editor
        lines = editor.get_all_text()
        results = [rl._result for rl in editor.result_lines]
        output_parts: list[str] = []
        table_rows: list[tuple[str, str]] = []

        def flush_table() -> None:
            nonlocal table_rows
            if table_rows:
                output_parts.append("| Expression | Result |")
                output_parts.append("|---|---|")
                for expr, result in table_rows:
                    expr_escaped = expr.replace("|", "\\|")
                    result_escaped = result.replace("|", "\\|")
                    output_parts.append(f"| {expr_escaped} | {result_escaped} |")
                output_parts.append("")
                table_rows = []

        for i, line_text in enumerate(lines):
            stripped = line_text.strip()
            result = results[i] if i < len(results) else ""
            if not stripped:
                flush_table()
                continue
            if stripped.startswith("#"):
                flush_table()
                output_parts.append(stripped)
                output_parts.append("")
                continue
            if stripped.startswith("//"):
                flush_table()
                comment_text = stripped[2:].strip()
                if comment_text:
                    output_parts.append(comment_text)
                    output_parts.append("")
                continue
            table_rows.append((stripped, result))

        flush_table()
        while output_parts and not output_parts[-1]:
            output_parts.pop()
        return "\n".join(output_parts) + "\n"


def main():
    """Run the Reckn app."""
    app = RecknApp()
    app.run()


if __name__ == "__main__":
    main()
