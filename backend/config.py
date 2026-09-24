import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    savanna_host: str = os.getenv("SAVANNA_HOST", "https://localhost")
    savanna_username: str = os.getenv("SAVANNA_USERNAME", "tigergraph")
    savanna_password: str = os.getenv("SAVANNA_PASSWORD", "tigergraph")
    savanna_graph: str = os.getenv("SAVANNA_GRAPH", "FraudGraph")
    savanna_api_port: int = int(os.getenv("SAVANNA_API_PORT", "443"))
    llm_api_key: str = os.getenv("LLM_API_KEY", "sk-test")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"
    sqlite_log_path: str = os.getenv("SQLITE_LOG_PATH", "/tmp/fraud_investigation.db")
    temp_dir: str = os.getenv("TEMP_DIR", "/tmp/fraud_answers")
    batch_size: int = int(os.getenv("BATCH_SIZE", "50"))
    use_mock: bool = os.getenv("USE_MOCK", "false").lower() == "true"

    @property
    def is_dry_run(self) -> bool:
        return self.dry_run

    @property
    def answers_dir(self) -> Path:
        return Path(self.temp_dir) / "answers"

    @property
    def graph_url(self) -> str:
        return f"{self.savanna_host}:{self.savanna_api_port}"


config = Config()
