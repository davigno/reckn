"""Textual UI for Reckn calculator notepad."""

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll, Center, Middle
from textual.widgets import Static, Button, Input, Label, ListItem, ListView
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from textual import events
from rich.text import Text

from .evaluator import LineEvaluator
from .pad import Pad, save_pad, load_pad, load_pad_from_path, list_pads
from .highlighter import highlight_line
from . import clipboard


class EditorLine(Static):
    """A single editable line in the editor."""

    DEFAULT_CSS = """
    EditorLine {
        height: auto;
        width: 2fr;
        padding: 0 1;
    }
    EditorLine:focus {
        background: $surface-lighten-1;
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

    def __init__(self, text: str = "", line_number: int = 0) -> None:
        super().__init__()
        self._text = text
        self.line_number = line_number
        self.cursor_pos = len(text)
        self.can_focus = True
        self._known_variables: set = set()

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
            # Segment before cursor
            if cursor_pos > 0:
                result.append_text(highlighted[:cursor_pos])
            # Cursor character with reverse style
            if cursor_pos < len(text):
                cursor_char = highlighted[cursor_pos:cursor_pos + 1]
                cursor_char.stylize("reverse", 0, 1)
                result.append_text(cursor_char)
                # Segment after cursor
                if cursor_pos + 1 < len(text):
                    result.append_text(highlighted[cursor_pos + 1:])
            else:
                # Cursor past end — show block cursor on empty space
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
                    # Append current line's text to previous line
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
            self.text = self._text[:self.cursor_pos] + event.character + self._text[self.cursor_pos:]
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

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[EditorLine] = []
        self.result_lines: list[ResultLine] = []

    def compose(self) -> ComposeResult:
        """Create initial single line row."""
        editor_line = EditorLine("", line_number=0)
        result_line = ResultLine(line_number=0)
        self.lines.append(editor_line)
        self.result_lines.append(result_line)
        yield LineRow(editor_line, result_line)

    def on_mount(self) -> None:
        """Focus the first line on mount."""
        if self.lines:
            self.lines[0].focus()
            self.current_line = 0

    def add_line(self, after_index: int = -1, text: str = "", notify: bool = True) -> bool:
        """Add a new line after the given index. Returns True if added."""
        if len(self.lines) >= self.MAX_LINES:
            return False
        if after_index < 0:
            after_index = len(self.lines) - 1
        editor_line = EditorLine(text, line_number=after_index + 1)
        result_line = ResultLine(line_number=after_index + 1)
        insert_pos = after_index + 1
        self.lines.insert(insert_pos, editor_line)
        self.result_lines.insert(insert_pos, result_line)
        # Renumber lines after insertion
        for i in range(insert_pos, len(self.lines)):
            self.lines[i].line_number = i
            self.result_lines[i].line_number = i
        # Mount the row after the specified line's row
        row = LineRow(editor_line, result_line)
        after_row = self.lines[after_index].parent
        if after_index < len(self.lines) - 1 and after_row:
            self.mount(row, after=after_row)
        else:
            self.mount(row)
        if notify:
            self.post_message(self.LineAdded())
        return True

    def remove_line(self, index: int, notify: bool = True) -> bool:
        """Remove the line at index. Returns True if removed."""
        if len(self.lines) <= 1 or index < 0 or index >= len(self.lines):
            return False
        editor_line = self.lines.pop(index)
        self.result_lines.pop(index)
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
        if notify:
            self.post_message(self.LineRemoved(index))
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

    def set_result(self, line_index: int, result: str,
                   is_heading: bool = False, is_comment: bool = False,
                   is_subtotal: bool = False) -> None:
        """Set the result for a specific line."""
        if 0 <= line_index < len(self.result_lines):
            self.result_lines[line_index].set_result(result, is_heading, is_comment, is_subtotal)

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
        background: $surface;
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
        """Render the status bar with pad name left-aligned and total right-aligned."""
        text = Text()
        pad_display = self.pad_name
        if self.is_modified:
            pad_display = f"*{pad_display}"
        text.append(f"Pad: {pad_display}", style="italic")

        if self.is_offline:
            text.append("  [offline]", style="bold red")

        # Build total text on the right
        if self.total_visible and self._totals:
            from .evaluator import format_total_values
            total_str = f"Total: {format_total_values(self._totals)}"
            # Pad with spaces to push total to the right
            available = self.size.width - len(text.plain) - len(total_str)
            if available > 0:
                text.append(" " * available)
            else:
                text.append("  ")
            text.append(total_str, style="bold green")

        return text


class MenuBar(Static):
    """Menu bar at the top of the application."""

    DEFAULT_CSS = """
    MenuBar {
        height: 1;
        width: 100%;
        background: $primary;
        padding: 0 1;
    }
    """

    class AboutClicked(Message):
        pass

    class FileClicked(Message):
        pass

    class HelpClicked(Message):
        pass

    def render(self) -> Text:
        text = Text()
        text.append("Reckn", style="bold")
        text.append(" \u2502 ", style="dim")
        text.append("F", style="underline bold")
        text.append("ile ", style="bold")
        text.append("F1", style="dim")
        text.append(" \u2502 ", style="dim")
        text.append("H", style="underline bold")
        text.append("elp ", style="bold")
        text.append("F2", style="dim")
        return text

    def on_click(self, event: events.Click) -> None:
        # Layout: " Reckn │ File F1 │ Help F2"
        # Reckn region: x < 7, File region: 7-17, Help region: >= 18
        if event.x < 7:
            self.post_message(self.AboutClicked())
        elif event.x < 18:
            self.post_message(self.FileClicked())
        else:
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
        margin: 1 0 0 8;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f1", "close", "Close"),
    ]

    def __init__(self, total_visible: bool = True) -> None:
        super().__init__()
        self._highlighted = 0
        total_label = "Hide Total" if total_visible else "Show Total"
        self._menu_items = [
            ("New", "Ctrl+N", "new_pad"),
            ("Open", "Ctrl+O", "open_pad"),
            ("Save", "Ctrl+S", "save"),
            ("Export", "Ctrl+E", "export"),
            (total_label, "Ctrl+T", "toggle_total"),
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
    """Help screen with keyboard shortcuts and syntax reference."""

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
        Binding("f2", "close", "Close"),
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

        heading("KEYBOARD SHORTCUTS")
        shortcut("Ctrl+N", "New pad")
        shortcut("Ctrl+O", "Open pad")
        shortcut("Ctrl+S", "Save pad")
        shortcut("Ctrl+E", "Export as markdown")
        shortcut("Ctrl+T", "Toggle floating total")
        shortcut("Ctrl+K", "Toggle comment")
        shortcut("Ctrl+X", "Delete line")
        shortcut("Ctrl+C", "Copy result to clipboard")
        shortcut("Ctrl+Shift+C", "Copy entire pad")
        shortcut("Ctrl+V", "Paste from clipboard")
        shortcut("Ctrl+Q", "Quit")
        shortcut("F1", "File menu")
        shortcut("F2", "This help screen")
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
        Binding("ctrl+n", "new_pad", "New"),
        Binding("ctrl+e", "export", "Export"),
        Binding("ctrl+t", "toggle_total", "Toggle Total"),
        Binding("ctrl+k", "toggle_comment", "Comment", show=False),
        Binding("ctrl+x", "delete_line", "Delete Line", show=False),
        Binding("ctrl+c", "copy_result", "Copy Result", show=False, priority=True),
        Binding("ctrl+shift+c", "copy_all", "Copy All", show=False),
        Binding("alt+f", "toggle_file_menu", "File Menu", show=False, priority=True),
        Binding("f1", "toggle_file_menu", "File Menu", show=False),
        Binding("f2", "toggle_help", "Help", show=False),
    ]

    def __init__(self, pad_name: str | None = None) -> None:
        super().__init__()
        self.evaluator = LineEvaluator()
        self._eval_pending = False
        self.current_pad: Pad | None = None
        self._initial_pad_name = pad_name
        self._clipboard_warned = False

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield MenuBar()
        with Vertical(id="main-container"):
            yield Editor()
        yield StatusBar()

    def on_mount(self) -> None:
        """Set up the app on mount."""
        self.title = "Reckn"
        self.sub_title = "Calculator Notepad"

        # Load initial pad if specified
        if self._initial_pad_name:
            self._load_pad_by_name(self._initial_pad_name)

        # Start background currency fetch
        self._start_currency_fetch()

    def _start_currency_fetch(self) -> None:
        """Kick off background currency rate fetch if no rates cached."""
        from .currencies import get_converter
        converter = get_converter()
        if not converter.rates:
            converter.fetch_rates_in_background(on_complete=self._on_currency_loaded)

    def _on_currency_loaded(self, success: bool) -> None:
        """Called from background thread when currency fetch completes."""
        self.call_from_thread(self._handle_currency_loaded, success)

    def _handle_currency_loaded(self, success: bool) -> None:
        """Handle currency load result on the main thread."""
        if not success:
            from .currencies import get_converter
            converter = get_converter()
            if not converter.rates:
                status_bar = self.query_one(StatusBar)
                status_bar.is_offline = True
        # Re-evaluate all lines with fresh/cached rates
        self._do_evaluation()

    def on_menu_bar_about_clicked(self, message: MenuBar.AboutClicked) -> None:
        """Handle click on Reckn in the menu bar."""
        self.push_screen(AboutScreen(), lambda _: None)

    def on_menu_bar_file_clicked(self, message: MenuBar.FileClicked) -> None:
        """Handle click on File in the menu bar."""
        self.action_toggle_file_menu()

    def on_menu_bar_help_clicked(self, message: MenuBar.HelpClicked) -> None:
        """Handle click on Help in the menu bar."""
        self.action_toggle_help()

    def action_toggle_help(self) -> None:
        """Toggle the help screen."""
        if isinstance(self.screen, HelpScreen):
            self.screen.dismiss("")
            return
        self.push_screen(HelpScreen(), lambda _: None)

    def action_toggle_file_menu(self) -> None:
        """Toggle the file menu dropdown open/closed."""
        if isinstance(self.screen, FileMenuScreen):
            self.screen.dismiss("")
            return
        try:
            status_bar = self.query_one(StatusBar)
            total_visible = status_bar.total_visible
        except Exception:
            total_visible = True
        self.push_screen(FileMenuScreen(total_visible), self._handle_file_menu)

    def _handle_file_menu(self, action: str) -> None:
        """Handle file menu selection."""
        if not action:
            return
        action_method = getattr(self, f"action_{action}", None)
        if action_method:
            action_method()

    def _load_pad_by_name(self, name: str) -> None:
        """Load a pad by name."""
        pad = load_pad(name)
        if pad:
            self.current_pad = pad
            editor = self.query_one(Editor)
            editor.set_all_text(pad.lines if pad.lines else [""])

            status_bar = self.query_one(StatusBar)
            status_bar.pad_name = pad.name
            status_bar.is_modified = False

            self._do_evaluation()
            editor.focus_line(0)
        else:
            # Pad doesn't exist - create new with this name
            status_bar = self.query_one(StatusBar)
            status_bar.pad_name = name
            status_bar.is_modified = False
            self.current_pad = Pad.new(name)

    def on_editor_line_text_changed(self, message: EditorLine.TextChanged) -> None:
        """Handle text changes in editor lines."""
        status_bar = self.query_one(StatusBar)
        status_bar.is_modified = True
        self._schedule_evaluation()

    def on_result_line_clicked(self, message: ResultLine.Clicked) -> None:
        """Handle click on a result line - insert line reference."""
        editor = self.query_one(Editor)
        current_line_idx = editor.current_line
        if 0 <= current_line_idx < len(editor.lines):
            current_line = editor.lines[current_line_idx]
            line_ref = f"line{message.line_number + 1}"
            current_line.insert_text(line_ref)
            self._schedule_evaluation()

    def on_editor_line_added(self, message: Editor.LineAdded) -> None:
        """Handle line added in editor."""
        self._schedule_evaluation()

    def on_editor_line_removed(self, message: Editor.LineRemoved) -> None:
        """Handle line removed in editor."""
        self._schedule_evaluation()

    def action_toggle_comment(self) -> None:
        """Toggle comment on current line."""
        editor = self.query_one(Editor)
        if editor.current_line < len(editor.lines):
            line = editor.lines[editor.current_line]
            text = line._text.strip()
            if text.startswith("// "):
                # Remove comment
                line.text = line._text.replace("// ", "", 1)
            elif text.startswith("//"):
                # Remove comment (no space)
                line.text = line._text.replace("//", "", 1)
            else:
                # Add comment
                line.text = "// " + line._text
            self._schedule_evaluation()

    def action_delete_line(self) -> None:
        """Delete the current line."""
        editor = self.query_one(Editor)
        current = editor.current_line
        if editor.remove_line(current):
            # Focus the previous line or stay at 0
            new_focus = max(0, current - 1) if current > 0 else 0
            editor.focus_line(new_focus)
        elif len(editor.lines) == 1:
            # Only one line left - clear it instead of removing
            editor.lines[0].text = ""
            editor.lines[0].cursor_pos = 0

    def _check_clipboard(self) -> bool:
        """Check clipboard availability, show one-time warning if missing."""
        if clipboard.is_available():
            return True
        if not self._clipboard_warned:
            self._clipboard_warned = True
            self.notify("Install xclip for clipboard support", severity="warning")
        return False

    def action_copy_result(self) -> None:
        """Copy the current line's result to the system clipboard."""
        if not self._check_clipboard():
            return
        editor = self.query_one(Editor)
        idx = editor.current_line
        if 0 <= idx < len(editor.result_lines):
            result = editor.result_lines[idx]._result
            if result:
                clipboard.copy(result)
                self.notify("Result copied")
            else:
                self.notify("No result to copy", severity="warning")

    def action_copy_all(self) -> None:
        """Copy the entire pad (expressions + results, tab-separated) to clipboard."""
        if not self._check_clipboard():
            return
        editor = self.query_one(Editor)
        lines = editor.get_all_text()
        output = []
        for i, line_text in enumerate(lines):
            result = editor.result_lines[i]._result if i < len(editor.result_lines) else ""
            if result:
                output.append(f"{line_text}\t{result}")
            else:
                output.append(line_text)
        clipboard.copy("\n".join(output))
        self.notify("Pad copied to clipboard")

    def _schedule_evaluation(self) -> None:
        """Schedule evaluation with debouncing."""
        if not self._eval_pending:
            self._eval_pending = True
            self.set_timer(0.1, self._do_evaluation)

    def _do_evaluation(self) -> None:
        """Perform evaluation of all lines."""
        self._eval_pending = False

        editor = self.query_one(Editor)

        lines = editor.get_all_text()
        self.evaluator = LineEvaluator()

        for i, line_text in enumerate(lines):
            stripped = line_text.strip()
            is_heading = stripped.startswith('#')
            is_comment = stripped.startswith('//')
            result = self.evaluator.evaluate_line(line_text, i + 1)
            is_subtotal = self.evaluator.is_subtotal_line(i + 1)
            editor.set_result(i, result, is_heading, is_comment, is_subtotal)

        # Update floating total in status bar
        try:
            status_bar = self.query_one(StatusBar)
            status_bar.totals = self.evaluator.get_floating_totals()
        except Exception:
            pass

        # Update syntax highlighting with known variables
        known_vars = set(self.evaluator.context.variables.keys())
        editor.update_known_variables(known_vars)

    def action_quit(self) -> None:
        """Quit the application."""
        status_bar = self.query_one(StatusBar)
        if status_bar.is_modified:
            self.push_screen(
                ConfirmScreen("You have unsaved changes. Quit anyway?"),
                self._handle_quit_confirm
            )
        else:
            self.exit()

    def _handle_quit_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self.exit()

    def action_save(self) -> None:
        """Save the current pad."""
        status_bar = self.query_one(StatusBar)
        current_name = status_bar.pad_name

        self.push_screen(SaveScreen(current_name), self._handle_save)

    def _handle_save(self, name: str) -> None:
        if not name:
            return

        editor = self.query_one(Editor)
        lines = editor.get_all_text()

        # Remove trailing empty lines for cleaner save
        while lines and not lines[-1].strip():
            lines.pop()

        if self.current_pad:
            self.current_pad.name = name
            self.current_pad.lines = lines
        else:
            self.current_pad = Pad.new(name)
            self.current_pad.lines = lines

        try:
            path = save_pad(self.current_pad)
            status_bar = self.query_one(StatusBar)
            status_bar.pad_name = name
            status_bar.is_modified = False
            self.notify(f"Saved to {path.name}")
        except Exception as e:
            self.notify(f"Error saving: {e}", severity="error")

    def action_open_pad(self) -> None:
        """Open a saved pad."""
        status_bar = self.query_one(StatusBar)

        if status_bar.is_modified:
            self.push_screen(
                ConfirmScreen("You have unsaved changes. Discard them?"),
                self._handle_open_confirm
            )
        else:
            self.push_screen(OpenScreen(), self._handle_open)

    def _handle_open_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self.push_screen(OpenScreen(), self._handle_open)

    def _handle_open(self, path_str: str) -> None:
        if not path_str:
            return

        from pathlib import Path
        path = Path(path_str)
        pad = load_pad_from_path(path)

        if pad:
            self.current_pad = pad
            editor = self.query_one(Editor)

            # Set text (this will grow/shrink the editor)
            editor.set_all_text(pad.lines if pad.lines else [""])

            status_bar = self.query_one(StatusBar)
            status_bar.pad_name = pad.name
            status_bar.is_modified = False

            self._do_evaluation()
            editor.focus_line(0)
            self.notify(f"Opened: {pad.name}")
        else:
            self.notify("Failed to open pad", severity="error")

    def action_new_pad(self) -> None:
        """Create a new empty pad."""
        status_bar = self.query_one(StatusBar)

        if status_bar.is_modified:
            self.push_screen(
                ConfirmScreen("You have unsaved changes. Discard them?"),
                self._handle_new_confirm
            )
        else:
            self._do_new_pad()

    def _handle_new_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self._do_new_pad()

    def _do_new_pad(self) -> None:
        """Actually create a new pad."""
        self.current_pad = None

        editor = self.query_one(Editor)
        editor.clear()

        status_bar = self.query_one(StatusBar)
        status_bar.pad_name = "*new*"
        status_bar.is_modified = False

        editor.focus_line(0)
        self.notify("New pad created")

    def action_toggle_total(self) -> None:
        """Toggle the floating total display."""
        try:
            status_bar = self.query_one(StatusBar)
            status_bar.total_visible = not status_bar.total_visible
            if status_bar.total_visible:
                self.notify("Floating total shown")
            else:
                self.notify("Floating total hidden")
        except Exception:
            pass

    def action_export(self) -> None:
        """Export the current pad as markdown."""
        status_bar = self.query_one(StatusBar)
        default_name = status_bar.pad_name
        if default_name == "*new*":
            default_name = "export"
        # Clean up name for filename
        default_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in default_name)

        self.push_screen(ExportScreen(default_name), self._handle_export)

    def _handle_export(self, path_str: str) -> None:
        if not path_str:
            return

        from pathlib import Path
        path = Path(path_str).expanduser()

        # Ensure .md extension
        if not path.suffix:
            path = path.with_suffix(".md")

        # Create parent directory if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            markdown = self._generate_export_markdown()
            path.write_text(markdown)
            self.notify(f"Exported to {path}")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    def _generate_export_markdown(self) -> str:
        """Generate markdown export of current pad."""
        editor = self.query_one(Editor)

        lines = editor.get_all_text()
        results = [rl._result for rl in editor.result_lines]

        output_parts: list[str] = []
        table_rows: list[tuple[str, str]] = []

        def flush_table() -> None:
            """Write accumulated table rows to output."""
            nonlocal table_rows
            if table_rows:
                output_parts.append("| Expression | Result |")
                output_parts.append("|---|---|")
                for expr, result in table_rows:
                    # Escape pipe characters in expressions and results
                    expr_escaped = expr.replace("|", "\\|")
                    result_escaped = result.replace("|", "\\|")
                    output_parts.append(f"| {expr_escaped} | {result_escaped} |")
                output_parts.append("")  # Blank line after table
                table_rows = []

        for i, line_text in enumerate(lines):
            stripped = line_text.strip()
            result = results[i] if i < len(results) else ""

            if not stripped:
                # Empty line - flush current table and add separator
                flush_table()
                continue

            if stripped.startswith("#"):
                # Heading - flush table, then output heading
                flush_table()
                output_parts.append(stripped)
                output_parts.append("")
                continue

            if stripped.startswith("//"):
                # Comment - flush table, output as paragraph
                flush_table()
                comment_text = stripped[2:].strip()
                if comment_text:
                    output_parts.append(comment_text)
                    output_parts.append("")
                continue

            # Regular expression line - add to table
            table_rows.append((stripped, result))

        # Flush any remaining table rows
        flush_table()

        # Remove trailing empty lines
        while output_parts and not output_parts[-1]:
            output_parts.pop()

        return "\n".join(output_parts) + "\n"


def main():
    """Run the Reckn app."""
    app = RecknApp()
    app.run()


if __name__ == "__main__":
    main()
