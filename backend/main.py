import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from policy.engine import PolicyEngine
from graph.retrieval import GraphRAGRetriever
from api.main import app, _answer_files, _investigations, init_db
from graph.loader import TigerGraphLoader
from batch import run_batch

def main():
    config = Config()

    if config.dry_run:
        print("Running in DRY RUN mode")

    init_db()

    if "--batch" in sys.argv:
        output = sys.argv[sys.argv.index("--batch") + 1] if len(sys.argv) > sys.argv.index("--batch") + 1 else None
        run_batch(output)

    if "--load" in sys.argv:
        loader = TigerGraphLoader(config)
        data_dir = sys.argv[sys.argv.index("--load") + 1] if len(sys.argv) > sys.argv.index("--load") + 1 else None
        loader.load_all(data_dir or str(Path(__file__).parent / "fixtures"))

    if "--serve" in sys.argv or "--api" in sys.argv:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()