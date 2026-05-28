#!/usr/bin/env python3
"""
Production-Ready Wallet Database Converter.

Converts EVM wallet data from SQLite databases into multiple industry-standard
export formats while preserving sequential wallet ordering and integrity.

Supported Export Formats:
- TXT: Simple pipe-separated format (id|address|private_key)
- JSON: Structured JSON array format
- CSV: Comma-separated values with headers
- SQL: SQL INSERT statements for direct database import
- NDJSON: Newline-delimited JSON (one object per line)
- TSV: Tab-separated values with headers

Features:
- Automatic database detection and selection
- Memory-efficient streaming exports (supports 1M+ wallets)
- Rich console UI with progress tracking
- Comprehensive logging without exposing private keys
- Read-only database access (never modifies original DB)
- Interactive database selection menu
- Database validation before export
- CLI support with flexible arguments
- Professional error handling
- Fully offline operation (no telemetry/network)
"""

import argparse
import csv
import json
import logging
import logging.handlers
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text


# Constants
BATCH_SIZE = 5000
EXPORT_DIR = Path("exports")
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "converter.log"
REQUIRED_COLUMNS = {"id", "address", "private_key"}
DEFAULT_CHUNK_SIZE = 10000


class DatabaseConverter:
    """Production-grade wallet database converter with streaming export capabilities."""

    def __init__(self, quiet: bool = False):
        """
        Initialize converter with console and logging setup.

        Args:
            quiet: Suppress console output if True.
        """
        self.quiet = quiet
        self.console = Console()
        self.logger = self._setup_logging()
        self.selected_db: Optional[Path] = None
        self.connection: Optional[sqlite3.Connection] = None
        self._databases_cache: Optional[List[Path]] = None

    def _setup_logging(self) -> logging.Logger:
        """
        Set up logging with rotating file handler.

        Returns:
            Configured logger instance.
        """
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("converter")
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Create rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        handler.setLevel(logging.DEBUG)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger

    def find_databases(self) -> List[Path]:
        """
        Scan project directory for SQLite database files.

        Results are cached to avoid redundant filesystem scans.

        Returns:
            List of Path objects for found .db files.
        """
        if self._databases_cache is not None:
            return self._databases_cache

        cwd = Path.cwd()
        databases = sorted(cwd.glob("*.db"))

        self._databases_cache = databases
        self.logger.info(f"Database scan: found {len(databases)} databases")
        return databases

    def select_database(self, databases: List[Path], db_arg: Optional[str] = None) -> Optional[Path]:
        """
        Present database selection menu or use provided database argument.

        Args:
            databases: List of available database paths.
            db_arg: Optional database name from CLI argument.

        Returns:
            Selected database Path or None if user cancels.
        """
        if db_arg:
            # Use provided database argument
            db_path = Path(db_arg)
            if db_path.exists() and db_path.suffix == ".db":
                self.logger.info(f"Using specified database: {db_arg}")
                return db_path
            else:
                self.console.print(f"[red]Error: Database not found: {db_arg}[/red]")
                self.logger.error(f"Specified database not found: {db_arg}")
                return None

        if not databases:
            self.console.print("[red]No SQLite databases found in current directory[/red]")
            self.logger.warning("No databases found during selection")
            return None

        if len(databases) == 1:
            self.logger.info(f"Single database found: {databases[0].name}")
            return databases[0]

        # Multiple databases - show selection menu
        if not self.quiet:
            self.console.print("\n[bold cyan]Detected Databases:[/bold cyan]")
            table = Table(show_header=False, box=None)
            for idx, db in enumerate(databases, 1):
                size_mb = db.stat().st_size / (1024 * 1024)
                table.add_row(f"[{idx}]", db.name, f"({size_mb:.2f} MB)")
            self.console.print(table)

        while True:
            try:
                selection = input("\nSelect Database (number): ").strip()
                idx = int(selection) - 1
                
                if 0 <= idx < len(databases):
                    selected = databases[idx]
                    self.logger.info(f"User selected database: {selected.name}")
                    return selected
                else:
                    self.console.print("[red]Invalid selection. Please try again.[/red]")
            except ValueError:
                self.console.print("[red]Invalid input. Please enter a number.[/red]")
            except KeyboardInterrupt:
                self.logger.warning("Database selection cancelled by user")
                return None

    def connect_database(self, db_path: Path) -> bool:
        """
        Establish read-only connection to SQLite database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            # Open in read-only mode using URI
            # Note: check_same_thread=False is safe here as this is a single-threaded CLI tool
            uri = f"file:{db_path}?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self.selected_db = db_path
            self.logger.info(f"Connected to database: {db_path.name}")
            return True
        except sqlite3.DatabaseError as e:
            self.logger.error(f"Database connection failed: {e}")
            self.console.print(f"[red]Error: Invalid or corrupted database: {e}[/red]")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to database: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return False

    def validate_database(self) -> bool:
        """
        Validate that database has required wallets table and columns.

        Returns:
            True if database is valid, False otherwise.
        """
        if not self.connection:
            self.logger.error("No active database connection")
            return False

        try:
            cursor = self.connection.cursor()

            # Check if wallets table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='wallets'"
            )
            if not cursor.fetchone():
                self.logger.error("Wallets table not found in database")
                self.console.print("[red]Error: 'wallets' table not found[/red]")
                return False

            # Check required columns
            cursor.execute("PRAGMA table_info(wallets)")
            columns = {row[1] for row in cursor.fetchall()}

            missing = REQUIRED_COLUMNS - columns
            if missing:
                self.logger.error(f"Missing required columns: {missing}")
                self.console.print(f"[red]Error: Missing columns: {', '.join(missing)}[/red]")
                return False

            # Count total wallets
            cursor.execute("SELECT COUNT(*) FROM wallets")
            count = cursor.fetchone()[0]
            self.logger.info(f"Database validation successful. Total wallets: {count}")
            return True

        except sqlite3.Error as e:
            self.logger.error(f"Database validation failed: {e}")
            self.console.print(f"[red]Error validating database: {e}[/red]")
            return False

    def get_wallet_count(self) -> int:
        """
        Get total wallet count from database.

        Returns:
            Number of wallets in database.
        """
        if not self.connection:
            return 0

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM wallets")
            count = cursor.fetchone()[0]
            return count
        except Exception as e:
            self.logger.error(f"Error getting wallet count: {e}")
            return 0

    def fetch_wallets(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        batch_size: int = BATCH_SIZE
    ) -> Generator[List[Tuple], None, None]:
        """
        Fetch wallets from database in streaming batches.

        Uses memory-efficient chunked processing to support large databases.
        Note: This tool requires SQLite for database access.

        Args:
            limit: Maximum number of wallets to fetch (None for all).
            offset: Number of wallets to skip.
            batch_size: Number of rows to fetch per query batch.

        Yields:
            Lists of wallet tuples (id, address, private_key).
        """
        if not self.connection:
            return

        try:
            cursor = self.connection.cursor()

            # Build query - SQLite requires LIMIT before OFFSET
            if limit:
                query = "SELECT id, address, private_key FROM wallets ORDER BY id ASC LIMIT ? OFFSET ?"
                cursor.execute(query, (limit, offset))
            elif offset:
                # When only offset is specified without limit, use a large number
                query = "SELECT id, address, private_key FROM wallets ORDER BY id ASC LIMIT 9223372036854775807 OFFSET ?"
                cursor.execute(query, (offset,))
            else:
                # No limit or offset - fetch all results
                query = "SELECT id, address, private_key FROM wallets ORDER BY id ASC"
                cursor.execute(query)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield rows

            self.logger.debug(f"Wallet fetch completed (limit={limit}, offset={offset})")

        except Exception as e:
            self.logger.error(f"Error fetching wallets: {e}")
            raise

    def _create_export_dir(self) -> bool:
        """
        Create exports directory if it doesn't exist.

        Returns:
            True if successful, False otherwise.
        """
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to create export directory: {e}")
            return False

    def export_txt(
        self,
        output_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[str]:
        """
        Export wallets to TXT format: id|address|private_key.

        Args:
            output_path: Custom output filename.
            limit: Maximum number of wallets to export.
            offset: Number of wallets to skip.

        Returns:
            Path to exported file or None on error.
        """
        if not self._create_export_dir():
            return None

        try:
            filename = output_path or f"wallets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = EXPORT_DIR / filename

            with open(filepath, "w") as f:
                row_count = 0
                for batch in self.fetch_wallets(limit, offset):
                    for wallet_id, address, private_key in batch:
                        f.write(f"{wallet_id}|{address}|{private_key}\n")
                        row_count += 1

            self.logger.info(f"Exported {row_count} wallets to TXT: {filepath}")
            return str(filepath)

        except IOError as e:
            self.logger.error(f"TXT export failed: {e}")
            self.console.print(f"[red]Error writing TXT file: {e}[/red]")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in TXT export: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return None

    def export_json(
        self,
        output_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[str]:
        """
        Export wallets to JSON format using streaming approach.

        Writes JSON array incrementally without loading entire database into RAM.

        Args:
            output_path: Custom output filename.
            limit: Maximum number of wallets to export.
            offset: Number of wallets to skip.

        Returns:
            Path to exported file or None on error.
        """
        if not self._create_export_dir():
            return None

        try:
            filename = output_path or f"wallets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = EXPORT_DIR / filename

            with open(filepath, "w") as f:
                f.write("[\n")
                row_count = 0
                first_item = True

                for batch in self.fetch_wallets(limit, offset):
                    for wallet_id, address, private_key in batch:
                        if not first_item:
                            f.write(",\n")
                        
                        obj = {
                            "id": wallet_id,
                            "address": address,
                            "private_key": private_key
                        }
                        f.write("  " + json.dumps(obj))
                        row_count += 1
                        first_item = False

                f.write("\n]\n")

            self.logger.info(f"Exported {row_count} wallets to JSON: {filepath}")
            return str(filepath)

        except IOError as e:
            self.logger.error(f"JSON export failed: {e}")
            self.console.print(f"[red]Error writing JSON file: {e}[/red]")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in JSON export: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return None

    def export_csv(
        self,
        output_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[str]:
        """
        Export wallets to CSV format.

        Args:
            output_path: Custom output filename.
            limit: Maximum number of wallets to export.
            offset: Number of wallets to skip.

        Returns:
            Path to exported file or None on error.
        """
        if not self._create_export_dir():
            return None

        try:
            filename = output_path or f"wallets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = EXPORT_DIR / filename

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "address", "private_key"])

                row_count = 0
                for batch in self.fetch_wallets(limit, offset):
                    for wallet_id, address, private_key in batch:
                        writer.writerow([wallet_id, address, private_key])
                        row_count += 1

            self.logger.info(f"Exported {row_count} wallets to CSV: {filepath}")
            return str(filepath)

        except IOError as e:
            self.logger.error(f"CSV export failed: {e}")
            self.console.print(f"[red]Error writing CSV file: {e}[/red]")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in CSV export: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return None

    def export_sql(
        self,
        output_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[str]:
        """
        Export wallets to SQL INSERT statements.

        Args:
            output_path: Custom output filename.
            limit: Maximum number of wallets to export.
            offset: Number of wallets to skip.

        Returns:
            Path to exported file or None on error.
        """
        if not self._create_export_dir():
            return None

        if not self.selected_db:
            self.logger.error("No database selected for SQL export")
            self.console.print("[red]Error: No database selected[/red]")
            return None

        try:
            filename = output_path or f"wallets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            filepath = EXPORT_DIR / filename

            with open(filepath, "w") as f:
                f.write("-- Wallet Database Export\n")
                f.write(f"-- Source Database: {self.selected_db.name}\n")
                f.write(f"-- Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("CREATE TABLE IF NOT EXISTS wallets (\n")
                f.write("    id INTEGER PRIMARY KEY,\n")
                f.write("    address TEXT NOT NULL,\n")
                f.write("    private_key TEXT NOT NULL\n")
                f.write(");\n\n")

                row_count = 0
                for batch in self.fetch_wallets(limit, offset):
                    for wallet_id, address, private_key in batch:
                        # Escape single quotes in values
                        addr_escaped = address.replace("'", "''")
                        key_escaped = private_key.replace("'", "''")
                        f.write(
                            f"INSERT INTO wallets (id, address, private_key) "
                            f"VALUES ({wallet_id}, '{addr_escaped}', '{key_escaped}');\n"
                        )
                        row_count += 1

            self.logger.info(f"Exported {row_count} wallets to SQL: {filepath}")
            return str(filepath)

        except IOError as e:
            self.logger.error(f"SQL export failed: {e}")
            self.console.print(f"[red]Error writing SQL file: {e}[/red]")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in SQL export: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return None

    def export_ndjson(
        self,
        output_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[str]:
        """
        Export wallets to NDJSON format (newline-delimited JSON).

        Args:
            output_path: Custom output filename.
            limit: Maximum number of wallets to export.
            offset: Number of wallets to skip.

        Returns:
            Path to exported file or None on error.
        """
        if not self._create_export_dir():
            return None

        try:
            filename = output_path or f"wallets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ndjson"
            filepath = EXPORT_DIR / filename

            with open(filepath, "w") as f:
                row_count = 0
                for batch in self.fetch_wallets(limit, offset):
                    for wallet_id, address, private_key in batch:
                        obj = {
                            "id": wallet_id,
                            "address": address,
                            "private_key": private_key
                        }
                        f.write(json.dumps(obj) + "\n")
                        row_count += 1

            self.logger.info(f"Exported {row_count} wallets to NDJSON: {filepath}")
            return str(filepath)

        except IOError as e:
            self.logger.error(f"NDJSON export failed: {e}")
            self.console.print(f"[red]Error writing NDJSON file: {e}[/red]")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in NDJSON export: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return None

    def export_tsv(
        self,
        output_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Optional[str]:
        """
        Export wallets to TSV format (tab-separated values).

        Args:
            output_path: Custom output filename.
            limit: Maximum number of wallets to export.
            offset: Number of wallets to skip.

        Returns:
            Path to exported file or None on error.
        """
        if not self._create_export_dir():
            return None

        try:
            filename = output_path or f"wallets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tsv"
            filepath = EXPORT_DIR / filename

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["id", "address", "private_key"])

                row_count = 0
                for batch in self.fetch_wallets(limit, offset):
                    for wallet_id, address, private_key in batch:
                        writer.writerow([wallet_id, address, private_key])
                        row_count += 1

            self.logger.info(f"Exported {row_count} wallets to TSV: {filepath}")
            return str(filepath)

        except IOError as e:
            self.logger.error(f"TSV export failed: {e}")
            self.console.print(f"[red]Error writing TSV file: {e}[/red]")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in TSV export: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
            return None

    def display_startup_dashboard(
        self,
        db_name: str,
        export_format: str,
        total_wallets: int
    ) -> None:
        """
        Display startup dashboard with export configuration.

        Args:
            db_name: Name of selected database.
            export_format: Export format being used.
            total_wallets: Total number of wallets in database.
        """
        if self.quiet:
            return

        dashboard = Table(show_header=False, box=None)
        dashboard.add_row("Detected Databases", str(len(self.find_databases())))
        dashboard.add_row("Selected Database", f"[bold cyan]{db_name}[/bold cyan]")
        dashboard.add_row("Total Wallets", f"[bold green]{total_wallets:,}[/bold green]")
        dashboard.add_row("Export Format", f"[bold yellow]{export_format.upper()}[/bold yellow]")

        panel = Panel(
            dashboard,
            title="[bold]Export Configuration[/bold]",
            border_style="blue",
            padding=(1, 2)
        )
        self.console.print(panel)

    def display_completion_dashboard(
        self,
        rows_exported: int,
        export_format: str,
        output_file: str,
        runtime_seconds: float
    ) -> None:
        """
        Display completion dashboard with export statistics.

        Args:
            rows_exported: Number of rows exported.
            export_format: Format used for export.
            output_file: Path to output file.
            runtime_seconds: Total runtime in seconds.
        """
        if self.quiet:
            return

        speed = rows_exported / runtime_seconds if runtime_seconds > 0 else 0

        summary = Table(show_header=False, box=None)
        summary.add_row("Rows Exported", f"[bold green]{rows_exported:,}[/bold green]")
        summary.add_row("Format", f"[bold yellow]{export_format.upper()}[/bold yellow]")
        summary.add_row("Output File", f"[cyan]{output_file}[/cyan]")
        summary.add_row("Runtime", f"{runtime_seconds:.2f}s")
        summary.add_row("Speed", f"[bold cyan]{speed:,.0f} rows/sec[/bold cyan]")

        panel = Panel(
            summary,
            title="[bold green]Export Complete[/bold green]",
            border_style="green",
            padding=(1, 2)
        )
        self.console.print(panel)

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            try:
                self.connection.close()
                self.logger.info("Database connection closed")
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")


def parse_arguments() -> argparse.Namespace:
    """
    Parse and validate command-line arguments.

    Returns:
        Parsed arguments.

    Raises:
        SystemExit: On invalid arguments.
    """
    parser = argparse.ArgumentParser(
        description="Production-ready wallet database converter with streaming exports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python converter.py
  python converter.py --format json
  python converter.py --db wallets.db --format csv --output custom.csv
  python converter.py --format txt --limit 1000
  python converter.py --format json --offset 5000 --limit 1000
  python converter.py --quiet
        """
    )

    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Database filename (auto-detected if not specified)"
    )

    parser.add_argument(
        "--format",
        type=str,
        choices=["txt", "json", "csv", "sql", "ndjson", "tsv"],
        default="json",
        help="Export format (default: json)"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output filename (auto-generated if not specified)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of wallets to export (None for all)"
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Number of wallets to skip (default: 0)"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than 0")

    if args.offset < 0:
        parser.error("--offset must be non-negative")

    return args


def main() -> None:
    """
    Main entry point for wallet database converter CLI.

    Handles database selection, validation, export, and error handling.
    """
    converter = None

    try:
        args = parse_arguments()

        # Initialize converter
        converter = DatabaseConverter(quiet=args.quiet)

        # Find available databases
        databases = converter.find_databases()

        if not databases and not args.db:
            converter.console.print(
                "[yellow]No SQLite databases found in current directory[/yellow]"
            )
            converter.logger.warning("No databases found")
            return

        # Select database
        selected_db = converter.select_database(databases, args.db)
        if not selected_db:
            converter.logger.info("Database selection cancelled")
            return

        # Connect to database
        if not converter.connect_database(selected_db):
            return

        # Validate database
        if not converter.validate_database():
            return

        # Get total wallets
        total_wallets = converter.get_wallet_count()

        # Display startup dashboard
        converter.display_startup_dashboard(
            selected_db.name,
            args.format,
            total_wallets
        )

        # Perform export with timing
        start_time = time.time()

        # Initialize output_file
        output_file: Optional[str] = None

        if args.format == "txt":
            output_file = converter.export_txt(args.output, args.limit, args.offset)
        elif args.format == "json":
            output_file = converter.export_json(args.output, args.limit, args.offset)
        elif args.format == "csv":
            output_file = converter.export_csv(args.output, args.limit, args.offset)
        elif args.format == "sql":
            output_file = converter.export_sql(args.output, args.limit, args.offset)
        elif args.format == "ndjson":
            output_file = converter.export_ndjson(args.output, args.limit, args.offset)
        elif args.format == "tsv":
            output_file = converter.export_tsv(args.output, args.limit, args.offset)

        if output_file:
            runtime = time.time() - start_time

            # Calculate rows exported
            if args.limit:
                rows_exported = min(args.limit, total_wallets - args.offset)
            else:
                rows_exported = max(0, total_wallets - args.offset)

            # Display completion dashboard
            converter.display_completion_dashboard(
                rows_exported,
                args.format,
                output_file,
                runtime
            )

            converter.logger.info(
                f"Export completed successfully in {runtime:.2f}s - "
                f"{rows_exported} rows exported"
            )

            if not args.quiet:
                converter.console.print(
                    f"\n✓ Logs saved to: [bold green]logs/converter.log[/bold green]"
                )
        else:
            converter.logger.error("Export failed")

    except KeyboardInterrupt:
        if converter:
            converter.logger.warning("Export interrupted by user")
            converter.console.print("\n[yellow]Export interrupted by user[/yellow]")
        sys.exit(130)

    except Exception as e:
        if converter:
            converter.logger.exception(f"Unexpected error: {e}")
            converter.console.print(f"[red]Error: {e}[/red]")
        else:
            print(f"Error: {e}")
        sys.exit(1)

    finally:
        if converter:
            converter.close()


if __name__ == "__main__":
    main()
