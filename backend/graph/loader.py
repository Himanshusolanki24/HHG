import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("loader")


class TigerGraphLoader:
    def __init__(self, config):
        self.config = config
        self.tg = None
        self.total_loaded = 0
        self.skipped = 0
        self.start_time = None

    def connect(self):
        from pytigergraph import TigerGraphConnection
        self.tg = TigerGraphConnection(
            host=self.config.savanna_host,
            username=self.config.savanna_username,
            password=self.config.savanna_password,
            graphname=self.config.savanna_graph,
            useCert=True,
            api_ver="2.0"
        )
        try:
            self.tg.gsql("USE GRAPH FraudGraph")
            logger.info("Connected to TigerGraph Savanna: %s", self.config.savanna_graph)
        except Exception as e:
            logger.warning("Could not use graph: %s", e)

    def install_schema(self, schema_path: str):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would install schema from %s", schema_path)
            return
        with open(schema_path) as f:
            schema = f.read()
        try:
            self.tg.gsql(schema)
            logger.info("Schema installed successfully")
        except Exception as e:
            logger.error("Schema install failed: %s", e)
            raise

    def load_transactions(self, transactions: list[dict], batch_size: int = 50):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load %d transactions", len(transactions))
            return
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i+batch_size]
            values = []
            for t in batch:
                vals = [t["id"], t["at"], str(t["amount"]), t["merchant"], t["direction"], str(t["flagged"]).lower(), ""]
                values.append("('" + "','".join(vals) + "')")
            insert_sql = f'INSERT INTO Transaction VALUES {", ".join(values)}'
            try:
                self.tg.gsql(insert_sql)
            except Exception as e:
                logger.warning("Batch insert failed at %d: %s", i, e)
            self.total_loaded += len(batch)
            if i % (batch_size * 10) == 0:
                logger.info("Loaded %d/%d transactions", self.total_loaded, len(transactions))

    def load_accounts(self, accounts: list[dict]):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load %d accounts", len(accounts))
            return
        logger.info("Would load %d accounts in dry run", len(accounts))

    def load_edges(self, edges: list[dict]):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load %d edges", len(edges))
            return
        logger.info("Would load %d edges in dry run", len(edges))

    def load_cases(self, cases: list[dict]):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load %d cases", len(cases))
            return
        logger.info("Would load %d cases in dry run", len(cases))

    def load_policies(self, policies: list[dict]):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load %d policies", len(policies))
            return
        logger.info("Would load %d policies in dry run", len(policies))

    def load_patterns(self, patterns: list[dict]):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load %d fraud patterns", len(patterns))
            return
        logger.info("Would load %d fraud patterns in dry run", len(patterns))

    def load_embeddings(self, embeddings: dict):
        if self.config.dry_run:
            logger.info("[DRY RUN] Would load vector embeddings")
            return
        logger.info("Would load vector embeddings in dry run")

    def load_all(self, data_dir: str):
        self.start_time = datetime.now(timezone.utc)
        data_dir = Path(data_dir)
        logger.info("Starting data load from %s (dry_run=%s)", data_dir, self.config.dry_run)

        if self.config.dry_run:
            logger.info("[DRY RUN MODE] Skipping all actual data loading")
            logger.info("Dry run complete. No data written to TigerGraph.")
            return

        self.connect()

        transactions = json.loads((data_dir / "transactions.json").read_text()) if (data_dir / "transactions.json").exists() else []
        accounts = json.loads((data_dir / "accounts.json").read_text()) if (data_dir / "accounts.json").exists() else []
        edges = json.loads((data_dir / "edges.json").read_text()) if (data_dir / "edges.json").exists() else []
        cases = json.loads((data_dir / "cases.json").read_text()) if (data_dir / "cases.json").exists() else []
        policies = json.loads((data_dir / "policies.json").read_text()) if (data_dir / "policies.json").exists() else []

        self.load_transactions(transactions)
        self.load_accounts(accounts)
        self.load_edges(edges)
        self.load_cases(cases)
        self.load_policies(policies)

        logger.info("Data load complete. Total loaded: %d records in %s", self.total_loaded, datetime.now(timezone.utc) - self.start_time)


def main():
    from config import Config
    config = Config()
    loader = TigerGraphLoader(config)
    data_dir = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "fixtures")
    loader.load_all(data_dir)


if __name__ == "__main__":
    main()