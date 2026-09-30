import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

from brokenvault.common.constants import DEFAULT_CHUNK_SIZE
from brokenvault.client.api_client import BrokenVaultAPIClient
from brokenvault.client.uploader import execute_backup
from brokenvault.client.restorer import execute_restore

app = typer.Typer(help="BrokenVault CLI")
console = Console()

@app.command()
def backup(
    folder: str = typer.Argument(..., help="Path to directory to back up"),
    server: str = typer.Option("http://127.0.0.1:8000", "--server", "-s", help="Server URL"),
    chunk_size: int = typer.Option(DEFAULT_CHUNK_SIZE, "--chunk-size", "-c", help="Chunk size in bytes"),
    upload_id: Optional[str] = typer.Option(None, "--upload-id", "-u", help="Specific upload ID to resume")
):
    try:
        def on_prog(curr, total, cid):
            console.print(f"[green]Uploading chunk {curr}/{total}:[/green] {cid[:16]}...")

        res = execute_backup(
            source_dir=folder,
            server_url=server,
            chunk_size=chunk_size,
            upload_id=upload_id,
            progress_callback=on_prog
        )

        table = Table(title="Backup Complete")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Version ID", res.version_id)
        table.add_row("Status", res.status)
        table.add_row("Total Logical Bytes", f"{res.total_logical_bytes:,} bytes")
        table.add_row("Uploaded Chunk Bytes", f"{res.uploaded_bytes:,} bytes")
        table.add_row("Reused Chunk Bytes", f"{res.reused_bytes:,} bytes")
        table.add_row("Created At", res.created_at)
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Backup error:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command(name="list")
def list_versions(
    server: str = typer.Option("http://127.0.0.1:8000", "--server", "-s", help="Server URL")
):
    try:
        with BrokenVaultAPIClient(base_url=server) as client:
            res = client.list_versions()

        if not res.versions:
            console.print("[yellow]No completed versions found.[/yellow]")
            return

        table = Table(title="Saved Completed Versions")
        table.add_column("Version ID", style="cyan")
        table.add_column("Source Label", style="magenta")
        table.add_column("Total Bytes", justify="right")
        table.add_column("Uploaded Bytes", justify="right")
        table.add_column("Reused Bytes", justify="right")
        table.add_column("Created At", style="dim")

        for v in res.versions:
            table.add_row(
                v.version_id,
                v.source_label or "-",
                f"{v.total_logical_bytes:,}",
                f"{v.uploaded_bytes:,}",
                f"{v.reused_bytes:,}",
                v.created_at
            )
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]List error:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command()
def restore(
    version_id: str = typer.Argument(..., help="Version ID to restore"),
    dest: str = typer.Argument(..., help="Target directory for restored files"),
    server: str = typer.Option("http://127.0.0.1:8000", "--server", "-s", help="Server URL")
):
    try:
        def on_prog(curr, total, path):
            console.print(f"[blue]Restoring {curr}/{total}:[/blue] {path}")

        manifest = execute_restore(
            version_id=version_id,
            destination_dir=dest,
            server_url=server,
            progress_callback=on_prog
        )

        console.print(f"[bold green]Successfully restored {len(manifest.entries)} items for version {version_id} into {dest}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Restore error:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command()
def verify(
    server: str = typer.Option("http://127.0.0.1:8000", "--server", "-s", help="Server URL")
):
    try:
        with BrokenVaultAPIClient(base_url=server) as client:
            res = client.verify_storage()

        if res.corrupted_chunks_count == 0:
            console.print(f"[bold green]Integrity Verified:[/bold green] All {res.total_chunks_checked} stored chunks are healthy.")
            return

        console.print(f"[bold red]Integrity Alert:[/bold red] Found {res.corrupted_chunks_count} corrupted/missing chunks out of {res.total_chunks_checked} checked.")
        
        table = Table(title="Corrupted Chunks Impact Report")
        table.add_column("Chunk ID", style="red")
        table.add_column("Status", style="yellow")
        table.add_column("Affected Versions", style="cyan")
        table.add_column("Affected Files", style="magenta")

        for d in res.corrupted_chunks:
            file_summaries = ", ".join([f"{f.version_id}:{f.path}" for f in d.affected_files])
            table.add_row(
                d.chunk_id[:16] + "...",
                d.status,
                ", ".join(d.affected_versions),
                file_summaries
            )
        console.print(table)
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Verify error:[/bold red] {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
