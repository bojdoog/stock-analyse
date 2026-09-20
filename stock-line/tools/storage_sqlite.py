"""Shared database storage; legacy module name retained for script compatibility."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'flask_backend'))
from market_store import file_content, initialize, list_files, refresh_index, save_dataframe


def read_frame(path):
    import pandas as pd
    content = file_content(f'{Path(path).parent.name}/{Path(path).name}')
    if content is None:
        raise FileNotFoundError(f'Not imported into database: {path}')
    return pd.read_csv(io.BytesIO(content))


def has_file(path, category=None):
    return file_content(f'{category or Path(path).parent.name}/{Path(path).name}') is not None
