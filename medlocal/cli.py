"""MedLocal CLI — offline clinical consultation & training."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="Offline clinical consultation & training for community health workers."
)
console = Console()


@app.command()
def ingest(
    source: str = typer.Argument(help="File path, URL, or directory to ingest"),
    profile: str = typer.Option("local", help="Knowledge base profile: core or local"),
    force: bool = typer.Option(False, "--force", help="Re-ingest even if already exists"),
) -> None:
    """Ingest clinical protocols into the knowledge base."""
    from .config import load_config
    from .knowledge import KnowledgeBase

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    console.print(f"[bold]Ingesting[/bold] {source} into [cyan]{profile}[/cyan] profile...")

    if profile == "core":
        chunks = kb.ingest_core(source, force=force)
    else:
        chunks = kb.ingest_local(source, force=force)

    if chunks == 0:
        console.print("[yellow]No content ingested.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]Ingested {chunks} chunks[/green] into {profile} profile")


@app.command()
def consult_cmd(
    question: str = typer.Argument(help="Clinical question"),
) -> None:
    """Ask a clinical question (one-shot)."""
    from rich.panel import Panel

    from .config import load_config
    from .consult import consult
    from .knowledge import KnowledgeBase

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    console.print("[dim]Searching protocols...[/dim]")
    answer, sources = consult(question, kb, cfg.llm)

    console.print(Panel(answer, title="Clinical Guidance", border_style="green"))
    if sources:
        console.print("[dim]Sources:[/dim]")
        for s in sources:
            console.print(f"  [dim]{s['title']} ({s['profile']}, score: {s['score']})[/dim]")


@app.command()
def chat() -> None:
    """Interactive clinical consultation (multi-turn)."""
    from rich.panel import Panel
    from rich.prompt import Prompt

    from .config import load_config
    from .consult import consult
    from .knowledge import KnowledgeBase

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    console.print("[bold]Clinical Consultation[/bold] [dim](type 'q' to quit)[/dim]\n")
    history: list[dict[str, str]] = []

    while True:
        question = Prompt.ask("[bold blue]Question[/bold blue]")
        if question.strip().lower() in ("q", "quit", "exit"):
            break

        console.print("[dim]Searching protocols...[/dim]")
        answer, sources = consult(question, kb, cfg.llm, history=history)

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

        console.print(Panel(answer, title="Clinical Guidance", border_style="green"))
        if sources:
            for s in sources:
                console.print(f"  [dim]{s['title']} ({s['profile']})[/dim]")
        console.print()


@app.command()
def train(
    topic: str = typer.Argument(help="Topic to generate training cards for"),
    max_chunks: int = typer.Option(10, help="Max protocol chunks to use"),
) -> None:
    """Generate training cards from clinical protocols."""
    from .config import load_config
    from .knowledge import KnowledgeBase
    from .store import TrainingStore
    from .training import generate_cards

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    console.print(f"[bold]Generating training cards[/bold] for: {topic}")
    cards = generate_cards(kb, topic, cfg.llm, max_chunks=max_chunks)

    if not cards:
        console.print("[yellow]No cards generated.[/yellow]")
        raise typer.Exit(1)

    with TrainingStore(cfg.recall_db) as store:
        saved = store.add_cards(cards)

    console.print(f"[green]Created {len(saved)} training cards[/green] for topic: {topic}")


@app.command()
def study(
    topic: str | None = typer.Option(None, help="Study a specific topic"),
    new: int = typer.Option(10, help="Max new cards"),
) -> None:
    """Interactive training session with spaced repetition."""
    from datetime import datetime, timezone

    from rich.panel import Panel
    from rich.prompt import Prompt

    from .config import load_config
    from .store import Rating, ReviewLog, TrainingStore
    from .training import evaluate, schedule

    cfg = load_config()

    with TrainingStore(cfg.recall_db) as store:
        due = store.get_due_cards(topic, limit=50)
        new_cards = store.get_new_cards(topic, limit=new)
        queue = due + new_cards

        if not queue:
            console.print("[green]Nothing to review! Come back later.[/green]")
            return

        level_labels = {0: "Concept", 1: "Clinical Recall", 2: "Scenario"}
        console.print(
            f"\n[bold]Training Session[/bold] — {len(due)} due, {len(new_cards)} new\n"
        )

        reviewed = 0
        correct = 0

        for i, card in enumerate(queue, 1):
            label = level_labels.get(card.level, "?")
            console.print(f"[dim]Card {i}/{len(queue)}[/dim] [{label}]")

            if card.level == 0:
                console.print(Panel(
                    f"[bold]{card.question}[/bold]\n\n{card.answer}",
                    title="Key Concept", border_style="magenta",
                ))
                Prompt.ask("[dim]Press Enter when ready[/dim]", default="")
                rating = Rating.GOOD
            else:
                console.print(Panel(card.question, title=label, border_style="blue"))
                answer = Prompt.ask("Answer (or 'q' to quit, 's' to skip)")

                if answer.strip().lower() == "q":
                    break
                if answer.strip().lower() == "s":
                    continue

                console.print("[dim]Evaluating...[/dim]")
                rating, feedback = evaluate(
                    card.question, card.answer, answer, cfg.llm,
                )
                console.print(Panel(card.answer, title="Correct Answer", border_style="green"))

                rating_styles = {
                    Rating.AGAIN: "[bold red]AGAIN[/bold red]",
                    Rating.HARD: "[bold yellow]HARD[/bold yellow]",
                    Rating.GOOD: "[bold green]GOOD[/bold green]",
                    Rating.EASY: "[bold cyan]EASY[/bold cyan]",
                }
                console.print(f"  {rating_styles[rating]}")
                if feedback:
                    console.print(f"  [dim]{feedback}[/dim]")

            now = datetime.now(timezone.utc)
            elapsed = 0.0
            if card.last_review:
                elapsed = (now - card.last_review).total_seconds() / 86400

            updated = schedule(card, rating, now)
            scheduled_days = (
                (updated.due - now).total_seconds() / 86400 if updated.due else 0.0
            )

            store.update_card(updated)
            store.log_review(ReviewLog(
                card_id=card.id, rating=rating,
                elapsed_days=elapsed, scheduled_days=scheduled_days, review_at=now,
            ))

            reviewed += 1
            if rating not in (Rating.AGAIN, Rating.HARD):
                correct += 1

            console.print(f"[dim]Next review in {scheduled_days:.1f} days[/dim]\n")

        # Summary
        table = Table(title="Training Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Reviewed", str(reviewed))
        table.add_row("Correct", f"{correct}/{reviewed}" if reviewed else "—")
        table.add_row("Accuracy", f"{correct / reviewed:.0%}" if reviewed else "—")
        console.print(table)


@app.command()
def search(
    query: str = typer.Argument(help="Search query"),
    top_k: int = typer.Option(5, help="Number of results"),
) -> None:
    """Search the knowledge base directly."""
    from .config import load_config
    from .knowledge import KnowledgeBase

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    results = kb.search(query, top_k=top_k)
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, r in enumerate(results, 1):
        console.print(
            f"\n[bold]{i}.[/bold] {r.title} "
            f"[dim]({r.profile}, score: {r.score:.3f})[/dim]"
        )
        console.print(f"  {r.text[:200]}...")


@app.command()
def serve(
    port: int = typer.Option(8765, help="Port for the API server"),
) -> None:
    """Start the MedLocal API server."""
    import uvicorn

    from .api import app as api_app

    console.print(f"[bold]MedLocal API[/bold] running on http://localhost:{port}")
    console.print(f"[dim]Docs at http://localhost:{port}/docs[/dim]")
    uvicorn.run(api_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    app()
