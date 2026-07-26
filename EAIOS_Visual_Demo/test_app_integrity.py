"""The presentation layer is real code and nothing else executes it.

Every other module is covered by tests that call it. The Streamlit app is
only exercised by opening a browser, so a function deleted by a careless
edit stays green through the whole suite and fails in front of an audience.

These checks are static: they parse the app and confirm that everything it
calls exists and that every accessor it reaches for is really on the
repository. No Streamlit runtime is required.
"""

from pathlib import Path
import ast
import unittest

import eaios_story_data


ROOT = Path(__file__).resolve().parent
APP = ROOT / "eaios_story_app.py"


def app_tree() -> ast.Module:
    return ast.parse(APP.read_text(encoding="utf-8"))


def defined_functions(tree: ast.Module, *, top_level_only: bool = False) -> set[str]:
    nodes = tree.body if top_level_only else ast.walk(tree)
    return {
        node.name
        for node in nodes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def called_names(tree: ast.Module) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def repository_methods_called(tree: ast.Module) -> set[str]:
    """Attribute calls made on anything named `repo`."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "repo"
        ):
            names.add(func.attr)
    return names


class AppCallIntegrityTests(unittest.TestCase):
    def test_every_render_function_the_app_calls_is_defined(self):
        tree = app_tree()
        defined = defined_functions(tree)
        missing = sorted(
            name
            for name in called_names(tree)
            if name.startswith("render_") and name not in defined
        )
        self.assertEqual(
            missing,
            [],
            f"the app calls render functions that do not exist: {missing}",
        )

    def test_every_local_helper_the_app_calls_is_defined(self):
        tree = app_tree()
        defined = defined_functions(tree)
        imported = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        builtins_and_libs = {
            "print", "len", "int", "float", "str", "bool", "sorted", "set",
            "list", "dict", "min", "max", "sum", "any", "all", "zip",
            "enumerate", "range", "isinstance", "next", "tuple", "getattr",
        }
        allowed = defined | imported | builtins_and_libs
        missing = sorted(
            name for name in called_names(tree) if name not in allowed
        )
        self.assertEqual(missing, [], f"undefined names called: {missing}")

    def test_every_repository_accessor_the_app_uses_exists(self):
        """The app and the data layer must not drift apart."""
        missing = sorted(
            name
            for name in repository_methods_called(app_tree())
            if not hasattr(eaios_story_data.StoryRepository, name)
        )
        self.assertEqual(
            missing,
            [],
            f"the app calls repository methods that do not exist: {missing}",
        )

    def test_the_app_parses(self):
        self.assertIsInstance(app_tree(), ast.Module)


class RenderCoverageTests(unittest.TestCase):
    EXPECTED = {
        "render_fusion",
        "render_vendor_health",
        "render_control_plane",
        "render_adjudication",
        "render_comparison",
        "render_evidence",
        "render_readiness",
        "render_servicenow_boundary",
        "render_adaptive_story",
    }

    def test_the_concept_panels_are_all_present(self):
        defined = defined_functions(app_tree(), top_level_only=True)
        missing = sorted(self.EXPECTED - defined)
        self.assertEqual(missing, [], f"panels missing from the app: {missing}")

    def test_each_panel_is_reachable_from_a_tab(self):
        tree = app_tree()
        called = called_names(tree)
        for panel in ("render_fusion", "render_vendor_health", "render_control_plane"):
            with self.subTest(panel=panel):
                self.assertIn(panel, called)


if __name__ == "__main__":
    unittest.main()
