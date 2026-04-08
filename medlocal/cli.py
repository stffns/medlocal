"""MedLocal CLI — offline clinical consultation & training."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="Offline clinical consultation & training for community health workers."
)
protocol_app = typer.Typer(
    help="Author, validate, and audit clinical protocols.",
    no_args_is_help=True,
)
app.add_typer(protocol_app, name="protocol")
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
    result = consult(question, kb, cfg.llm, language=cfg.language)

    # Safety indicators
    confidence = result["confidence"]
    safety_flags = result.get("safety_flags", [])
    emergency = result.get("emergency", False)

    border = "red" if emergency else ("yellow" if confidence.value <= 1 else "green")
    title = "⚠ EMERGENCY" if emergency else "Clinical Guidance"

    console.print(Panel(result["answer"], title=title, border_style=border))

    # Confidence badge
    conf_style = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}
    console.print(f"  Confidence: [{conf_style.get(confidence.name, 'white')}]{confidence.name}[/]")

    if safety_flags:
        from .safety import SafetyFlag
        for flag in safety_flags:
            console.print(f"  [bold red]⚠ {flag.name}[/bold red]")

    if result.get("sources"):
        console.print("[dim]Sources:[/dim]")
        for s in result["sources"]:
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
        result = consult(question, kb, cfg.llm, history=history, language=cfg.language)

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result["answer"]})

        emergency = result.get("emergency", False)
        border = "red" if emergency else "green"
        title = "⚠ EMERGENCY" if emergency else "Clinical Guidance"
        console.print(Panel(result["answer"], title=title, border_style=border))
        if result.get("sources"):
            for s in result["sources"]:
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
    cards = generate_cards(kb, topic, cfg.get_teacher_llm(), max_chunks=max_chunks)

    if not cards:
        console.print("[yellow]No cards generated.[/yellow]")
        raise typer.Exit(1)

    with TrainingStore(cfg.recall_db) as store:
        saved = store.add_cards(cards)

    console.print(f"[green]Created {len(saved)} training cards[/green] for topic: {topic}")


@app.command()
def index() -> None:
    """Generate consultation index from all protocols (uses teacher LLM)."""
    from .config import load_config
    from .indexer import index_all_protocols
    from .knowledge import KnowledgeBase

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    console.print("[bold]Generating consultation index[/bold] from all protocols...")
    console.print("[dim]Using teacher LLM — this may take several minutes[/dim]")
    total = index_all_protocols(kb, cfg)
    console.print(f"[green]Created {total} consultation pairs[/green]")


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
    from .knowledge import KnowledgeBase
    from .store import Rating, ReviewLog, TrainingStore
    from .training import evaluate, schedule

    cfg = load_config()
    kb = KnowledgeBase(cfg)

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

                # Retrieve source protocol for double grounding
                source_protocol = None
                if card.chunk_id:
                    source_protocol = kb.get_chunk(card.chunk_id, card.source_profile)

                console.print("[dim]Evaluating...[/dim]")
                rating, feedback = evaluate(
                    card.question, card.answer, answer, cfg.llm,
                    source_protocol=source_protocol,
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
    """Start the MedLocal web server with mobile UI."""
    import uvicorn

    from .web import app as web_app  # noqa: F811 — imports api.app + adds UI route

    console.print(f"[bold]MedLocal[/bold] running on http://localhost:{port}")
    console.print(f"[dim]API docs at http://localhost:{port}/docs[/dim]")
    uvicorn.run(web_app, host="0.0.0.0", port=port)


# --------------------------------------------------------------------------- #
# Protocol sub-commands — author, validate, audit                              #
# --------------------------------------------------------------------------- #


def _print_issues(issues: list, header: str | None = None) -> tuple[int, int]:
    """Print a list of ProtocolIssue objects. Returns (errors, warnings)."""
    if header:
        console.print(f"\n[bold]{header}[/bold]")
    errors = warns = 0
    for issue in issues:
        style = {"error": "red", "warn": "yellow", "info": "cyan"}[issue.severity]
        console.print(f"[{style}]{issue}[/{style}]")
        if issue.severity == "error":
            errors += 1
        elif issue.severity == "warn":
            warns += 1
    return errors, warns


@protocol_app.command("audit")
def protocol_audit(
    protocols_dir: str = typer.Option(
        "data/core/protocols",
        help="Directory containing protocol markdown files",
    ),
    profile: str = typer.Option("core", help="KB profile: core or local"),
    fix_hints: bool = typer.Option(
        True, "--hints/--no-hints", help="Show fix-hint details for each issue"
    ),
) -> None:
    """Audit the entire protocol corpus against authoring rules.

    Checks every .md file in <protocols_dir> for:
      • ≤2000 chars (warn) / ≤2048 chars (error)
      • H1 title present
      • Source attribution (WHO/MSF/Hesperian/IMCI/IMAI/CDC/NICE)
      • No YAML frontmatter
      • Exactly one vstash chunk per file (this is the critical one)
      • No stale orphans in the KB whose source file is gone
    """
    from .config import load_config
    from .knowledge import KnowledgeBase
    from .protocol import audit_corpus

    cfg = load_config()
    kb = KnowledgeBase(cfg)

    console.print(f"[bold]Auditing[/bold] {protocols_dir} against [cyan]{profile}[/cyan] KB...")
    issues = audit_corpus(kb, protocols_dir, profile=profile)

    if not issues:
        console.print("\n[green]✓ Corpus is clean — all rules pass.[/green]")
        return

    # Group by rule for a readable report
    by_rule: dict[str, list] = {}
    for issue in issues:
        by_rule.setdefault(issue.rule, []).append(issue)

    total_errors = total_warns = 0
    for rule, items in sorted(by_rule.items()):
        console.print(f"\n[bold]Rule: {rule}[/bold] ({len(items)} issue{'s' if len(items) > 1 else ''})")
        for issue in items:
            style = {"error": "red", "warn": "yellow", "info": "cyan"}[issue.severity]
            from pathlib import Path as _P
            name = _P(issue.path).name if issue.path else "(no path)"
            tag = {"error": "✗", "warn": "⚠", "info": "ℹ"}[issue.severity]
            console.print(f"  [{style}]{tag} {name}[/{style}]: {issue.message}")
            if fix_hints and issue.fix_hint:
                for line in issue.fix_hint.splitlines():
                    console.print(f"    [dim]{line}[/dim]")
            if issue.severity == "error":
                total_errors += 1
            elif issue.severity == "warn":
                total_warns += 1

    console.print(
        f"\n[bold]Summary:[/bold] "
        f"[red]{total_errors} error{'s' if total_errors != 1 else ''}[/red], "
        f"[yellow]{total_warns} warning{'s' if total_warns != 1 else ''}[/yellow]"
    )
    if total_errors:
        raise typer.Exit(1)


@protocol_app.command("validate")
def protocol_validate(
    path: str = typer.Argument(help="Path to a protocol .md file"),
    profile: str = typer.Option("core", help="KB profile: core or local"),
    ingest: bool = typer.Option(
        True, "--ingest/--no-ingest",
        help="Actually ingest into vstash to verify chunk count (default: yes)",
    ),
) -> None:
    """Validate a single protocol file against all authoring rules.

    With --ingest (the default) this also calls vstash to confirm the
    file produces exactly one chunk. Without --ingest only the text-level
    rules are checked.
    """
    from .config import load_config
    from .knowledge import KnowledgeBase
    from .protocol import ingest_and_verify, validate_file

    console.print(f"[bold]Validating[/bold] {path}")

    # Text-level rules first — cheap, no KB
    text_issues = validate_file(path)
    e1, w1 = _print_issues(text_issues, header="Text-level checks")
    if not text_issues:
        console.print("  [green]✓ text-level rules pass[/green]")

    errors = e1
    warns = w1

    if ingest:
        cfg = load_config()
        kb = KnowledgeBase(cfg)
        kb_issues = ingest_and_verify(kb, path, profile=profile)
        e2, w2 = _print_issues(kb_issues, header="KB chunk-count check")
        if not kb_issues:
            console.print("  [green]✓ produces exactly 1 chunk[/green]")
        errors += e2
        warns += w2

    console.print(
        f"\n[bold]Summary:[/bold] "
        f"[red]{errors} error{'s' if errors != 1 else ''}[/red], "
        f"[yellow]{warns} warning{'s' if warns != 1 else ''}[/yellow]"
    )
    if errors:
        raise typer.Exit(1)


@protocol_app.command("new")
def protocol_new(
    source: str = typer.Argument(help="Path to a markdown file (draft or final)"),
    dest_dir: str = typer.Option(
        "data/core/protocols", help="Destination directory"
    ),
    profile: str = typer.Option("core", help="KB profile to ingest into"),
    query: list[str] = typer.Option(
        None, "--query", "-q",
        help="Probe query for the retrieval dry-run. Repeatable. "
             "Write the query a CHW would actually type, in lay language.",
    ),
    title_fragment: str = typer.Option(
        None, "--title-fragment",
        help="Case-insensitive fragment the retrieved chunk title must match. "
             "Defaults to the Title-Cased filename stem.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate + probe without copying to dest_dir"
    ),
) -> None:
    """Ingest a new protocol file with full validation and a retrieval probe.

    Pipeline:
      1. Text-level validation (chars, title, source, frontmatter)
      2. Copy to dest_dir unless --dry-run
      3. Ingest into vstash (--force) and assert exactly 1 chunk
      4. Run each --query and report whether the new protocol surfaces
         in the top 6 (this is the check that would have caught the
         organophosphate embedder failure at authoring time)

    Example:
      medlocal protocol new drafts/new-cholera.md \\
        -q "Niño con diarrea acuosa profusa, deshidratado" \\
        -q "adult with rice water stools after flood"
    """
    import shutil

    from .config import load_config
    from .knowledge import KnowledgeBase
    from .protocol import (
        ingest_and_verify,
        retrieval_dry_run,
        validate_file,
    )

    src = Path(source)
    if not src.exists():
        console.print(f"[red]✗ {source} does not exist[/red]")
        raise typer.Exit(1)

    # 1. Text-level validation
    console.print(f"\n[bold]1/4 Text-level validation[/bold]")
    text_issues = validate_file(src)
    e1, w1 = _print_issues(text_issues)
    if not text_issues:
        console.print("  [green]✓ rules pass[/green]")
    if e1:
        console.print("[red]Aborting due to text-level errors.[/red]")
        raise typer.Exit(1)

    # 2. Copy to destination
    dest = Path(dest_dir) / src.name
    if dry_run:
        console.print(f"\n[bold]2/4 Copy to destination[/bold] [dim](skipped — --dry-run)[/dim]")
        working = src
    else:
        console.print(f"\n[bold]2/4 Copy to destination[/bold]")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        console.print(f"  [green]✓ copied[/green] → {dest}")
        working = dest

    # 3. Ingest + chunk count
    console.print(f"\n[bold]3/4 Ingest + chunk-count check[/bold]")
    cfg = load_config()
    kb = KnowledgeBase(cfg)
    kb_issues = ingest_and_verify(kb, working, profile=profile)
    e2, _ = _print_issues(kb_issues)
    if not kb_issues:
        console.print("  [green]✓ produces exactly 1 chunk[/green]")
    if e2:
        console.print("[red]Aborting — chunk count is not 1.[/red]")
        raise typer.Exit(1)

    # 4. Retrieval dry-run
    console.print(f"\n[bold]4/4 Retrieval dry-run[/bold]")
    if not query:
        console.print("  [dim]No --query probes given; skipping.[/dim]")
        console.print("  [dim]Re-run with -q '<CHW-style lay query>' to verify reachability.[/dim]")
    else:
        fragment = title_fragment or _title_from_stem(src.stem)
        reports = retrieval_dry_run(kb, fragment, list(query), top_k=6)
        failed = 0
        for r in reports:
            if r.passed:
                console.print(
                    f"  [green]✓[/green] rank {r.found_rank}/{r.top_k}  "
                    f"[dim]{r.query[:80]}[/dim]"
                )
            else:
                failed += 1
                console.print(
                    f"  [red]✗[/red] NOT in top {r.top_k}  [dim]{r.query[:80]}[/dim]"
                )
                console.print(
                    f"    [dim]Top titles: {', '.join(r.top_titles[:4])}...[/dim]"
                )
        if failed:
            console.print(
                f"\n[yellow]⚠ {failed}/{len(reports)} queries did not surface the new protocol.[/yellow]\n"
                f"  [dim]Consider enriching the file with lay-language synonyms "
                f"that appear in the failing queries.[/dim]"
            )

    console.print(f"\n[bold green]Done.[/bold green]")


def _title_from_stem(stem: str) -> str:
    """Convert a filename stem like 'poisoning-organophosphate-who' to a fragment."""
    parts = [p for p in stem.split("-") if p.lower() != "who"]
    return " ".join(parts).title()


if __name__ == "__main__":
    app()
