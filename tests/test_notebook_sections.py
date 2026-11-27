import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'models'))
from notebook_sections import load_sections


class NotebookSectionsTest(unittest.TestCase):
    def test_reordered_and_inserted_cells(self):
        cells = [
            {'cell_type': 'code', 'source': ['other = 1\n']},
            {'cell_type': 'markdown', 'source': ['def features():\n']},
            {'cell_type': 'code', 'source': ['def features():\n', '    return 42\n']},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.ipynb'
            for order in (cells, list(reversed(cells))):
                path.write_text(json.dumps({'cells': order}), encoding='utf-8')
                self.assertEqual(load_sections(path, {'features': ('def features():',)})['features'],
                                 'def features():\n    return 42\n')

    def test_missing_or_ambiguous_section_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.ipynb'
            for count in (0, 2):
                path.write_text(json.dumps({'cells': [
                    {'cell_type': 'code', 'source': ['target = 1']} for _ in range(count)
                ]}), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, f'{count} เซลล์'):
                    load_sections(path, {'target': ('target =',)})

    def test_current_notebook_sections_match_adapters(self):
        # Extract the literal declarations without importing ML dependencies.
        import ast
        for model in ('mu', 'amzn'):
            tree = ast.parse((ROOT / 'models' / f'{model}.py').read_text(encoding='utf-8'))
            call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name) and node.func.id == 'load_sections')
            markers = ast.literal_eval(call.args[1])
            notebook = 'MU_Capstone_v5_WalkForward_Improved.ipynb' if model == 'mu' else 'AMZN_Prediction_V4.ipynb'
            sections = load_sections(ROOT / notebook, markers)
            for role, source in sections.items():
                compile(source, f'<{model}:{role}>', 'exec')


if __name__ == '__main__':
    unittest.main()
