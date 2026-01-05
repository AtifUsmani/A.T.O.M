# cli.py

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from datetime import datetime
from core.config import cfg as config

console = Console()

user_id = config["USER_ID"]
class CLIStreamer:
    def __init__(self, llm):
        self.llm = llm
        self.console = Console()
        self.history = []

    def stream_to_console(self, user_input):
        self.console.rule(f"[bold green]User[/]  •  {datetime.now().strftime('%H:%M:%S')}")

        self.console.print(Panel.fit(user_input, style="bold cyan"))
        self.history.append(("user", user_input))

        last_text = ""
        generated = ""

        with Live(refresh_per_second=40) as live:
            for chunk in self.llm.generate_chunks(user_input, user_id):
                if not chunk:
                    continue

                # delta logic
                # if chunk.startswith(last_text):
                #     delta = chunk[len(last_text):]
                # else:
                #     delta = chunk

                # last_text = chunk
                # generated += delta

                generated += chunk

                # Render assistant response live
                md = Markdown(generated)
                live.update(
                    Panel(
                        md,
                        border_style="bright_magenta",
                        title="🤖 Assistant",
                        padding=(1, 2)
                    )
                )

        # Save to history
        self.history.append(("assistant", generated))
        self.console.print()  # newline

        yield generated

    def stream_to_console_basic(self, user_input):
        # print(user_input)

        self.history.append(("user", user_input))

        last_text = ""
        generated = ""

        for chunk in self.llm.generate_chunks(user_input, user_id):
            if not chunk:
                continue

            # compute delta
            if chunk.startswith(last_text):
                delta = chunk[len(last_text):]
            else:
                delta = chunk

            last_text = chunk
            generated += delta

            # PRINT NEW DELTA
            # print(delta, end="", flush=True)

            # YIELD CHUNK TO MAIN + TTS
            yield delta

        print("\n")
        self.history.append(("assistant", generated))

    def stream_to_console_basic_md(self, user_input):
        self.history.append(("user", user_input))

        previous = ""      # last full chunk
        generated = ""     # final output buffer
        partial = ""       # used for markdown blocks

        for chunk in self.llm.generate_chunks(user_input, user_id):
            if not chunk:
                continue

            i = 0
            max_len = min(len(previous), len(chunk))
            while i < max_len and previous[i] == chunk[i]:
                i += 1
            delta = chunk[i:]

            previous = chunk
            generated += delta
            partial += delta

            # detect complete markdown
            should_render = False
            if partial.count("**") % 2 == 0 and "**" in partial:
                should_render = True
            if partial.count("```") % 2 == 0 and "```" in partial:
                should_render = True
            if partial.count("`") % 2 == 0 and "`" in partial:
                should_render = True

            if should_render:
                console.print(Markdown(partial), end="")
                partial = ""
            else:
                console.print(delta, end="")

            # yield if needed
            # yield delta

        # leftover
        if partial.strip():
            console.print(partial, end="")

        console.print("\n")
        self.history.append(("assistant", generated))