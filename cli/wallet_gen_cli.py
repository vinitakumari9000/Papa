#!/usr/bin/env python3
"""
Production-grade EVM Wallet Generator with SQLite Storage.

Generates EVM-compatible wallets for Ethereum and EVM-compatible chains:
- Ethereum, Polygon, Arbitrum, Optimism, BNB Chain
- Avalanche C-Chain, Linea, Scroll, zkSync Era, Blast, Mantle
- Direct SQLite database storage (no file exports)
- Memory-efficient streaming generation
- Suitable for massive wallet generation (1K to 1M+)

Features:
- Secure cryptographic randomness via eth_account
- Immediate database insertion (memory efficient)
- Batch transaction processing
- Rich console UI with progress bars
- Comprehensive logging
- Production-ready error handling
- Offline operation (no network requests)
"""

import argparse
import logging
import logging.handlers
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

import secrets
from eth_account import Account
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table
from rich.text import Text


@dataclass
class WalletGenerationStats:
    """Statistics for wallet generation session."""

    wallets_generated: int = 0
    wallets_inserted: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def speed(self) -> float:
        """Get generation speed (wallets/second)."""
        elapsed = self.elapsed_time
        if elapsed > 0:
            return self.wallets_generated / elapsed
        return 0.0


class WalletGenerator:
    """Production-grade EVM wallet generator with SQLite storage."""

    DB_SCHEMA = """
    CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT NOT NULL UNIQUE,
        private_key TEXT NOT NULL
    )
    """

    def __init__(self, db_path: str = "wallets.db", log_dir: str = "logs", quiet: bool = False):
        """
        Initialize wallet generator with database and logging.

        Args:
            db_path: Path to SQLite database file.
            log_dir: Directory for log files.
            quiet: Suppress console output.
        """
        self.db_path = db_path
        self.log_dir = Path(log_dir)
        self.console = Console() if not quiet else None
        self.logger = self._setup_logging()
        self.connection: Optional[sqlite3.Connection] = None
        self.stats = WalletGenerationStats()

    def _setup_logging(self) -> logging.Logger:
        """
        Set up logging with rotating file handler.

        Returns:
            Configured logger instance.
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("wallet_gen")
        
        # Clear existing handlers only if they exist (avoid unnecessary clearing)
        if logger.handlers:
            logger.handlers.clear()
        
        logger.setLevel(logging.DEBUG)

        # Create rotating file handler
        log_file = self.log_dir / "wallet_gen.log"
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        handler.setLevel(logging.DEBUG)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger

    def _print(self, message: str) -> None:
        """Print to console if not in quiet mode."""
        if self.console:
            self.console.print(message)

    def create_connection(self) -> sqlite3.Connection:
        """
        Create or reuse database connection.

        Returns:
            SQLite connection object.

        Raises:
            sqlite3.Error: If connection fails.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            self.logger.info(f"Connected to database: {self.db_path}")
            return conn
        except sqlite3.Error as e:
            self.logger.error(f"Database connection error: {e}")
            raise

    def create_table(self) -> None:
        """
        Create wallets table if it doesn't exist.

        Raises:
            sqlite3.Error: If table creation fails.
        """
        try:
            if self.connection is None:
                raise RuntimeError("No database connection")

            cursor = self.connection.cursor()
            cursor.execute(self.DB_SCHEMA)
            self.connection.commit()
            self.logger.info("Wallets table created or verified")
        except sqlite3.Error as e:
            self.logger.error(f"Table creation error: {e}")
            raise

    def generate_wallet(self) -> Tuple[str, str]:
        """
        Generate a single EVM wallet with secure randomness.

        Uses eth_account.Account to create secp256k1 wallets compatible
        with all standard EVM chains.

        Returns:
            Tuple of (address, private_key).

        Raises:
            Exception: If wallet generation fails.
        """
        try:
            # Generate 32 bytes of cryptographically secure random data
            random_bytes = secrets.token_bytes(32)

            # Create account from random bytes
            account = Account.from_key(random_bytes)

            address = account.address
            private_key = account.key.hex()

            self.logger.debug(f"Generated wallet: {address}")
            return address, private_key

        except Exception as e:
            self.logger.error(f"Wallet generation error: {e}")
            raise

    def insert_wallet(self, address: str, private_key: str) -> bool:
        """
        Insert a single wallet into the database.

        Args:
            address: Wallet address (0x...).
            private_key: Wallet private key (0x...).

        Returns:
            True if insert successful, False otherwise.
        """
        try:
            if self.connection is None:
                raise RuntimeError("No database connection")

            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO wallets (address, private_key) VALUES (?, ?)",
                (address, private_key),
            )
            self.connection.commit()
            self.stats.wallets_inserted += 1
            return True

        except sqlite3.IntegrityError as e:
            self.logger.warning(f"Duplicate wallet ignored: {address}")
            return False
        except sqlite3.Error as e:
            self.logger.error(f"Insert error: {e}")
            raise

    def insert_wallet_batch(
        self, wallets: List[Tuple[str, str]], commit_interval: int = 100
    ) -> int:
        """
        Insert multiple wallets in a batch transaction.

        Args:
            wallets: List of (address, private_key) tuples.
            commit_interval: Commit every N inserts.

        Returns:
            Number of wallets successfully inserted.
        """
        try:
            if self.connection is None:
                raise RuntimeError("No database connection")

            cursor = self.connection.cursor()
            inserted = 0

            for i, (address, private_key) in enumerate(wallets):
                try:
                    cursor.execute(
                        "INSERT INTO wallets (address, private_key) VALUES (?, ?)",
                        (address, private_key),
                    )
                    inserted += 1
                    self.stats.wallets_inserted += 1

                    # Commit periodically
                    if (i + 1) % commit_interval == 0:
                        self.connection.commit()

                except sqlite3.IntegrityError:
                    # Skip duplicates silently
                    pass

            # Final commit
            self.connection.commit()
            return inserted

        except sqlite3.Error as e:
            self.logger.error(f"Batch insert error: {e}")
            raise

    def count_wallets(self) -> int:
        """
        Count total wallets in database.

        Returns:
            Total wallet count.
        """
        try:
            if self.connection is None:
                raise RuntimeError("No database connection")

            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM wallets")
            count = cursor.fetchone()[0]
            return count

        except sqlite3.Error as e:
            self.logger.error(f"Count query error: {e}")
            return 0

    def generate_and_insert(self, count: int, batch_size: int = 0) -> None:
        """
        Generate wallets and insert them directly into database (streaming).

        This is the core memory-efficient function. Each wallet is generated
        and inserted immediately, not stored in RAM.

        Args:
            count: Number of wallets to generate.
            batch_size: If > 0, batch inserts for better performance.

        Raises:
            ValueError: If count is invalid.
        """
        if not isinstance(count, int) or count <= 0:
            raise ValueError("Count must be a positive integer")

        self.stats.start_time = time.time()
        use_batch = batch_size > 0

        try:
            with Progress(console=self.console) as progress:
                task = progress.add_task(
                    "[cyan]Generating and inserting wallets...",
                    total=count,
                )

                if use_batch:
                    # Batch mode: accumulate wallets, insert periodically
                    batch = []
                    for _ in range(count):
                        try:
                            wallet = self.generate_wallet()
                            batch.append(wallet)
                            self.stats.wallets_generated += 1

                            if len(batch) >= batch_size:
                                self.insert_wallet_batch(batch, batch_size)
                                batch = []

                            progress.update(task, advance=1)

                        except Exception as e:
                            self.logger.error(f"Generation error: {e}")
                            progress.stop()
                            raise

                    # Insert remaining wallets
                    if batch:
                        self.insert_wallet_batch(batch, batch_size)

                else:
                    # Streaming mode: insert immediately
                    for _ in range(count):
                        try:
                            wallet = self.generate_wallet()
                            self.stats.wallets_generated += 1
                            self.insert_wallet(wallet[0], wallet[1])
                            progress.update(task, advance=1)

                        except Exception as e:
                            self.logger.error(f"Generation or insert error: {e}")
                            progress.stop()
                            raise

        except KeyboardInterrupt:
            self.logger.warning("Generation interrupted by user")
            raise

        finally:
            self.stats.end_time = time.time()

    def display_startup_dashboard(self) -> None:
        """Display startup dashboard showing existing wallets."""
        existing_count = self.count_wallets()

        table = Table(title="Wallet Generation Startup", show_header=True)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Existing Wallets", str(existing_count))
        table.add_row("Database", self.db_path)
        table.add_row("Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        panel = Panel(table, title="[bold]Starting Generation[/bold]", border_style="blue")
        self._print(panel)

    def display_completion_dashboard(self, generation_count: int) -> None:
        """
        Display completion dashboard with statistics.

        Args:
            generation_count: Number of wallets generated in this session.
        """
        total_wallets = self.count_wallets()
        elapsed = self.stats.elapsed_time
        speed = self.stats.speed

        table = Table(title="Wallet Generation Summary", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Generated Wallets", str(self.stats.wallets_generated))
        table.add_row("Inserted Into DB", str(self.stats.wallets_inserted))
        table.add_row("Total Wallets", str(total_wallets))
        table.add_row("Database File", self.db_path)
        table.add_row("Runtime", f"{elapsed:.2f}s")
        table.add_row("Speed", f"{speed:.0f} wallets/sec")

        panel = Panel(
            table, title="[bold green]Generation Complete[/bold green]", border_style="green"
        )
        self._print(panel)

    def close_connection(self) -> None:
        """Close database connection."""
        try:
            if self.connection:
                self.connection.close()
                self.logger.info("Database connection closed")
        except sqlite3.Error as e:
            self.logger.error(f"Error closing connection: {e}")

    def main_flow(self, count: int, batch_size: int = 0) -> None:
        """
        Main workflow: initialize, generate, display results.

        Args:
            count: Number of wallets to generate.
            batch_size: Batch size for inserts (0 for streaming).
        """
        try:
            # Connect and setup
            self.connection = self.create_connection()
            self.create_table()

            # Display startup info
            self.display_startup_dashboard()

            # Generate and insert
            self.generate_and_insert(count, batch_size)

            # Display completion info
            self.display_completion_dashboard(count)

            self.logger.info(f"Generation completed: {count} wallets generated")

        except KeyboardInterrupt:
            self._print("\n[yellow]Generation interrupted by user[/yellow]")
            self.logger.warning("Generation interrupted by user")

        except Exception as e:
            self._print(f"[red]Error: {e}[/red]")
            self.logger.exception(f"Unexpected error: {e}")

        finally:
            self.close_connection()


def parse_arguments() -> argparse.Namespace:
    """
    Parse and validate command-line arguments.

    Returns:
        Parsed arguments.

    Raises:
        SystemExit: On invalid arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Production-grade EVM wallet generator with direct SQLite storage. "
            "Generates wallets compatible with Ethereum and all EVM chains."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python wallet_gen.py --count 1000
  python wallet_gen.py --count 50000 --batch-size 1000
  python wallet_gen.py --count 100000 --db custom_wallets.db
  python wallet_gen.py --count 10 --quiet
        """,
    )

    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Number of wallets to generate (default: 1000, max: 1,000,000)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help=(
            "Batch size for database inserts. "
            "0 (default) = streaming (insert immediately). "
            ">0 = batch mode (better for 100K+ wallets)"
        ),
    )

    parser.add_argument(
        "--db",
        type=str,
        default="wallets.db",
        help="SQLite database file path (default: wallets.db)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (logging still active)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.count < 1:
        parser.error("--count must be at least 1")

    if args.count > 1000000:
        parser.error("--count cannot exceed 1,000,000")

    if args.batch_size < 0:
        parser.error("--batch-size must be >= 0")

    if args.batch_size > 0 and args.batch_size < 10:
        parser.error("--batch-size must be 0 or >= 10")

    return args


def main() -> None:
    """
    Main entry point for wallet generator CLI.

    Handles argument parsing, initialization, and error handling.
    """
    try:
        args = parse_arguments()

        # Initialize generator
        generator = WalletGenerator(db_path=args.db, quiet=args.quiet)

        # Display banner
        if not args.quiet:
            banner = Text("EVM Wallet Generator - SQLite Storage", style="bold cyan")
            generator._print(
                Panel(
                    banner,
                    border_style="green",
                    padding=(1, 2),
                )
            )

        generator.logger.info(
            f"Starting generation: count={args.count}, "
            f"batch_size={args.batch_size}, db={args.db}"
        )

        # Run main workflow
        generator.main_flow(args.count, args.batch_size)

    except KeyboardInterrupt:
        print("\n[yellow]Wallet generation interrupted[/yellow]")

    except ValueError as e:
        print(f"[red]Validation Error: {e}[/red]")

    except sqlite3.Error as e:
        print(f"[red]Database Error: {e}[/red]")

    except ImportError as e:
        print(f"[red]Missing dependency: {e}[/red]")
        print("[yellow]Run: pip install -r requirements.txt[/yellow]")

    except Exception as e:
        print(f"[red]Unexpected Error: {e}[/red]")


if __name__ == "__main__":
    main()
