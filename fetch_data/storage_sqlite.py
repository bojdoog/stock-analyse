"""Shared database storage; legacy module name retained for script compatibility."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flask_backend"))
from market_store import file_content, initialize, list_files, refresh_index, save_dataframe, save_frames


class CsvFrame:
    """把磁盘上的 CSV 当作待入库快照，批量入库时不必把全部股票读进内存。"""
    columns = ["date", "open", "close", "high", "low", "volume"]

    def __init__(self, path):
        self.path = Path(path)

    def to_csv(self, index=False):
        return self.path.read_text(encoding="utf-8-sig")


def save_csvs_batch(paths, category="stock", progress=None):
    """批量入库：整批共用一条数据库连接，最后统一同步一次 MySQL。"""
    return save_frames(((Path(path), CsvFrame(path)) for path in paths), category=category, progress=progress)


def read_frame(path):
    import pandas as pd
    content = file_content(f'{Path(path).parent.name}/{Path(path).name}')
    if content is None:
        raise FileNotFoundError(f'Not imported into database: {path}')
    return pd.read_csv(io.BytesIO(content))


def has_file(path, category=None):
    return file_content(f'{category or Path(path).parent.name}/{Path(path).name}') is not None
