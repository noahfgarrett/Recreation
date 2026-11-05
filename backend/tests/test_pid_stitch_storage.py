import tempfile
import unittest
from copy import deepcopy

from recreation_extractor.models import Project, to_dict
from recreation_extractor.pid_stitch.layout import generate_layout_options
from recreation_extractor.storage import ProjectStore


class PidStitchStorageTests(unittest.TestCase):
    def test_replace_and_list_stores_options_and_documents_and_removes_old_project_drawings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            first_options = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])
            store.replace_drawing_options("project_a", first_options)
            first_drawing_id = first_options[0][1].id

            listed = store.list_layout_options("project_a")
            self.assertEqual(
                [option["name"] for option in listed],
                ["Semantic Drawing", "Semantic Overlay", "Clean overview", "Recommended", "Source-driven Combined P&ID", "Source-faithful"],
            )
            self.assertEqual(listed[0]["drawingId"], first_drawing_id)
            self.assertIn("drawingDocument", listed[0])
            self.assertEqual(listed[0]["drawingDocument"]["id"], first_drawing_id)

            replacement_options = generate_layout_options("project_a", [self._page("src_b_p1", "src_b")], [], [])
            replacement_drawing_id = replacement_options[0][1].id
            replacement_options[0][1].id = "drawing_project_a_replacement"
            replacement_options[0][0].drawingId = replacement_options[0][1].id
            store.replace_drawing_options("project_a", replacement_options)

            listed = store.list_layout_options("project_a")
            self.assertEqual(len(listed), 6)
            self.assertEqual(listed[0]["drawingId"], "drawing_project_a_replacement")
            self.assertNotEqual(replacement_drawing_id, "drawing_project_a_replacement")
            with self.assertRaises(KeyError):
                store.get_drawing_document("project_a", first_drawing_id)

    def test_get_drawing_document_enforces_project_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            self._project(store, "project_b")
            options = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])
            store.replace_drawing_options("project_a", options)
            drawing_id = options[0][1].id

            self.assertEqual(store.get_drawing_document("project_a", drawing_id)["id"], drawing_id)
            with self.assertRaises(KeyError):
                store.get_drawing_document("project_b", drawing_id)
            with self.assertRaises(KeyError):
                store.get_drawing_document("project_a", "missing")

    def test_update_drawing_document_persists_edits_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            options = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])
            store.replace_drawing_options("project_a", options)
            drawing_id = options[0][1].id

            document = store.get_drawing_document("project_a", drawing_id)
            document["id"] = "wrong_id"
            document["projectId"] = "wrong_project"
            document["objects"][0]["label"] = "Edited source page"
            document["objects"].append({**document["objects"][0], "id": "user_added_object", "label": "Added object"})
            document["visualQa"]["labelOverlaps"] = 7

            updated = store.update_drawing_document("project_a", drawing_id, document)

            self.assertEqual(updated["id"], drawing_id)
            self.assertEqual(updated["projectId"], "project_a")
            self.assertEqual(updated["objects"][0]["label"], "Edited source page")
            self.assertTrue(any(obj["id"] == "user_added_object" for obj in updated["objects"]))
            self.assertEqual(updated["visualQa"]["labelOverlaps"], 7)
            self.assertEqual(store.get_drawing_document("project_a", drawing_id), updated)

    def test_replace_drawing_options_does_not_delete_unrelated_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            self._project(store, "project_b")
            project_a_options = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])
            project_b_options = generate_layout_options("project_b", [self._page("src_b_p1", "src_b")], [], [])
            store.replace_drawing_options("project_a", project_a_options)
            store.replace_drawing_options("project_b", project_b_options)

            replacement_options = generate_layout_options("project_a", [self._page("src_c_p1", "src_c")], [], [])
            store.replace_drawing_options("project_a", replacement_options)

            self.assertEqual(len(store.list_layout_options("project_a")), 6)
            self.assertEqual(len(store.list_layout_options("project_b")), 6)
            self.assertEqual(
                store.get_drawing_document("project_b", project_b_options[0][1].id)["projectId"],
                "project_b",
            )

    def test_mismatched_option_project_id_raises_and_leaves_existing_project_data_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            self._project(store, "project_b")
            project_b_options = generate_layout_options("project_b", [self._page("src_b_p1", "src_b")], [], [])
            store.replace_drawing_options("project_b", project_b_options)
            existing = store.list_layout_options("project_b")

            project_a_options = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])
            with self.assertRaises(ValueError):
                store.replace_drawing_options("project_b", project_a_options)

            self.assertEqual(store.list_layout_options("project_b"), existing)

    def test_mismatched_nested_drawing_document_project_id_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            option, document = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])[0]
            payload = to_dict(option)
            payload["drawingDocument"] = {**to_dict(document), "projectId": "project_b"}

            with self.assertRaises(ValueError):
                store.replace_drawing_options("project_a", [payload])

    def test_dict_nested_drawing_document_input_does_not_mutate_caller_owned_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(tmp)
            self._project(store, "project_a")
            option, document = generate_layout_options("project_a", [self._page("src_a_p1", "src_a")], [], [])[0]
            payload = to_dict(option)
            payload["drawingDocument"] = to_dict(document)
            original = deepcopy(payload)

            store.replace_drawing_options("project_a", [payload])

            self.assertEqual(payload, original)

    def _project(self, store, project_id):
        store.upsert_project(Project(project_id, project_id, "2026-05-08T00:00:00Z", "2026-05-08T00:00:00Z"))

    def _page(self, page_id, source_id):
        from recreation_extractor.pid_stitch.models import PageEvidence

        return PageEvidence(
            page_id,
            source_id,
            1,
            3024.0,
            2160.0,
            270,
            {"x": 0, "y": 0, "width": 2800, "height": 1900},
            [],
            50,
        )


if __name__ == "__main__":
    unittest.main()
