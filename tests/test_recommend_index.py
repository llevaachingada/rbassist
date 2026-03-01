import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np

from rbassist import recommend


class _FakeIndex:
    def __init__(self, space=None, dim=None):
        self.space = space
        self.dim = dim
        self._max_elements = 2
        self._current_count = 2
        self.add_calls = []
        self.resize_calls = []
        self.saved_path = None
        self.loaded_path = None
        self.ef = None

    def init_index(self, max_elements, ef_construction=None, M=None):
        self._max_elements = max_elements
        self._current_count = 0

    def load_index(self, path):
        self.loaded_path = path

    def set_ef(self, value):
        self.ef = value

    def get_ids_list(self):
        return [0]

    def get_items(self, ids):
        return np.ones((len(ids), recommend.DIM), dtype=np.float32)

    def get_current_count(self):
        return self._current_count

    def get_max_elements(self):
        return self._max_elements

    def resize_index(self, new_size):
        self.resize_calls.append(new_size)
        self._max_elements = new_size

    def add_items(self, arr, ids):
        if arr.shape[0] > 2:
            raise RuntimeError('too many items in one add_items call')
        self.add_calls.append((arr.shape[0], ids.tolist()))
        self._current_count += arr.shape[0]

    def save_index(self, path):
        self.saved_path = path


class RecommendIndexTests(unittest.TestCase):
    def test_build_index_incremental_resizes_and_chunks_adds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            idx_dir = base / 'index'
            idx_dir.mkdir(parents=True)
            idxfile = idx_dir / 'hnsw.idx'
            idxfile.write_text('idx', encoding='utf-8')
            mapfile = idx_dir / 'paths.json'
            existing_paths = ['existing-0', 'existing-1']
            mapfile.write_text(json.dumps(existing_paths), encoding='utf-8')

            embed_dir = base / 'embeddings'
            embed_dir.mkdir()
            tracks = {}
            for i in range(5):
                emb_path = embed_dir / f'track-{i}.npy'
                np.save(emb_path, np.ones(recommend.DIM, dtype=np.float32) * (i + 1))
                tracks[f'new-{i}'] = {'embedding': str(emb_path)}

            fake_index = _FakeIndex(space='cosine', dim=recommend.DIM)

            with mock.patch.object(recommend, 'IDX', idx_dir),                 mock.patch.object(recommend, 'load_meta', return_value={'tracks': tracks}),                 mock.patch.object(recommend.hnswlib, 'Index', side_effect=lambda *args, **kwargs: fake_index):
                recommend.build_index(incremental=True, add_chunk_size=2)

            self.assertTrue(fake_index.resize_calls)
            self.assertEqual([call[0] for call in fake_index.add_calls], [2, 2, 1])
            updated_paths = json.loads(mapfile.read_text(encoding='utf-8'))
            self.assertEqual(len(updated_paths), 7)
            self.assertEqual(updated_paths[:2], existing_paths)


if __name__ == '__main__':
    unittest.main()
