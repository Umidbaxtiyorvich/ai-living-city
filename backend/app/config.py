from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    world_seed: int = 20260831
    map_size: int = int(os.environ.get("MAP_SIZE", "80"))
    founding_population: int = int(os.environ.get("FOUNDING_POPULATION", "25"))
    starting_budget: float = 8_000_000.0
    #: Default watch speed — 1× is real-time (1 sim-minute per real second).
    default_speed: int = int(os.environ.get("DEFAULT_SPEED", "1"))
    host: str = "0.0.0.0"
    port: int = 8000

    #: SQLite by default so the simulator runs with no server to install.
    #: Point this at postgresql+psycopg://... for a shared deployment.
    database_url: str = "sqlite:///./city.db"
    #: Name the running city is saved under, and reloaded from.
    world_name: str = "AI Living City"
    president_name: str = "Umid Ravshanov"
    #: Simulated days between automatic saves. 0 disables autosaving.
    autosave_days: int = 1
    #: Snapshots kept per world; older ones are pruned after each save.
    snapshot_history: int = 12


settings = Settings()
