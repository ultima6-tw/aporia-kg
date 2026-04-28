"""
Aporia KG CLI
Usage:
  python -m ragraphe.client.aporia_cli plan "write a machine learning paper"
  python -m ragraphe.client.aporia_cli nodes <session_id>
  python -m ragraphe.client.aporia_cli done  <session_id> <node_id>
  python -m ragraphe.client.aporia_cli chat  <session_id> "I want to focus on NLP"
  python -m ragraphe.client.aporia_cli export <session_id>
  python -m ragraphe.client.aporia_cli sessions
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from ragraphe.client.aporia_client import AporiaClient, Node

app = typer.Typer(help="Aporia KG — goal decomposition & task tracking CLI")
console = Console()

STATUS_COLOR = {
    "done":     "green",
    "todo":     "cyan",
    "unknown":  "yellow",
    "skip":     "dim",
    "deferred": "magenta",
}


def _client() -> AporiaClient:
    return AporiaClient()


def _node_table(nodes: list[Node], title: str = "Nodes") -> Table:
    t = Table(title=title, show_lines=False)
    t.add_column("ID",     style="dim", width=10)
    t.add_column("Name",   min_width=24)
    t.add_column("Status", width=10)
    t.add_column("Source", width=12, style="dim")
    t.add_column("Description", min_width=30, style="dim")
    for n in sorted(nodes, key=lambda x: (x.status, x.name)):
        color = STATUS_COLOR.get(n.status, "white")
        t.add_row(
            n.id[:8],
            f"[{color}]{n.name}[/{color}]",
            f"[{color}]{n.status}[/{color}]",
            n.source,
            n.description[:60] + ("…" if len(n.description) > 60 else ""),
        )
    return t


# ── Commands ─────────────────────────────────────────────────────────────────

@app.command()
def plan(
    goal: str = typer.Argument(..., help="The goal to decompose"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language: en / zh-TW / ja"),
):
    """Start a new session and decompose a goal into tasks."""
    client = _client()
    with console.status(f"[bold cyan]Planning: {goal!r}…"):
        result = client.plan_goal(goal, lang=lang)

    rprint(f"\n[bold green]Session:[/bold green] {result.session_id}")
    rprint(f"\n[bold]AI:[/bold] {result.reply}\n")
    console.print(_node_table(result.nodes, title=f"Initial nodes for: {goal}"))

    stats = client.summary(result.session_id)
    rprint(f"\n[dim]todo: {stats['todo']+stats['unknown']}  done: {stats['done']}  skip: {stats['skip']}[/dim]")
    rprint(f"\n[bold yellow]Session ID:[/bold yellow] {result.session_id}")


@app.command()
def nodes(
    session_id: str = typer.Argument(..., help="Session ID"),
    status: str = typer.Option("", "--status", "-s", help="Filter by status (todo/done/skip/unknown)"),
):
    """List all nodes in a session."""
    client = _client()
    all_nodes = client.get_nodes(session_id)
    if status:
        all_nodes = [n for n in all_nodes if n.status == status]
    console.print(_node_table(all_nodes))
    stats = client.summary(session_id)
    rprint(f"[dim]todo: {stats['todo']+stats['unknown']}  done: {stats['done']}  skip: {stats['skip']}  deferred: {stats['deferred']}[/dim]")


@app.command()
def done(
    session_id: str = typer.Argument(...),
    node_id: str = typer.Argument(..., help="Node ID (first 8 chars ok)"),
):
    """Mark a node as done."""
    client = _client()
    # allow short IDs — find full match
    all_nodes = client.get_nodes(session_id)
    matched = [n for n in all_nodes if n.id.startswith(node_id)]
    if not matched:
        rprint(f"[red]No node found matching '{node_id}'[/red]")
        raise typer.Exit(1)
    node = client.mark_done(session_id, matched[0].id)
    rprint(f"[green]✓ Done:[/green] {node.name}")


@app.command()
def skip(
    session_id: str = typer.Argument(...),
    node_id: str = typer.Argument(...),
):
    """Skip a node."""
    client = _client()
    all_nodes = client.get_nodes(session_id)
    matched = [n for n in all_nodes if n.id.startswith(node_id)]
    if not matched:
        rprint(f"[red]No node found matching '{node_id}'[/red]")
        raise typer.Exit(1)
    node = client.mark_skip(session_id, matched[0].id)
    rprint(f"[dim]↷ Skipped:[/dim] {node.name}")


@app.command()
def add(
    session_id: str = typer.Argument(...),
    name: str = typer.Argument(..., help="Node name"),
    description: str = typer.Option("", "--desc", "-d"),
):
    """Manually add a node to the graph."""
    client = _client()
    node = client.add_node(session_id, name, description)
    rprint(f"[cyan]＋ Added:[/cyan] {node.name} [{node.id[:8]}]")


@app.command()
def chat(
    session_id: str = typer.Argument(...),
    message: str = typer.Argument(..., help="Message to send"),
    lang: str = typer.Option("en", "--lang", "-l"),
):
    """Send a message to continue planning."""
    client = _client()
    with console.status("[bold cyan]Thinking…"):
        result = client.send_message(session_id, message, lang=lang)
    rprint(f"\n[bold]AI:[/bold] {result.reply}\n")
    if result.new_nodes:
        console.print(_node_table(result.new_nodes, title="New nodes"))
    if result.ready:
        rprint("[bold green]✅ All nodes filled — planning complete![/bold green]")


@app.command()
def export(
    session_id: str = typer.Argument(...),
    output: str = typer.Option("", "--out", "-o", help="Save to file"),
):
    """Export the graph as a Markdown checklist."""
    client = _client()
    md = client.export_markdown(session_id)
    if output:
        with open(output, "w") as f:
            f.write(md)
        rprint(f"[green]Saved to {output}[/green]")
    else:
        console.print(md)


@app.command()
def sessions():
    """List all sessions."""
    client = _client()
    rows = client.list_sessions()
    t = Table(title="Sessions")
    t.add_column("ID",      width=10)
    t.add_column("Goal",    min_width=30)
    t.add_column("Nodes",   width=7)
    t.add_column("Created", width=18)
    for s in rows:
        t.add_row(
            s["id"][:8],
            s.get("goal", "")[:50],
            str(s.get("node_count", "?")),
            s.get("created_at", "")[:16],
        )
    console.print(t)


if __name__ == "__main__":
    app()
