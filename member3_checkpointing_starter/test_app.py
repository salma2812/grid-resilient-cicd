import os
import tempfile
import unittest

import app as checkpoint_app


class CheckpointServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_checkpoint_path = checkpoint_app.CHECKPOINT_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        checkpoint_app.CHECKPOINT_PATH = os.path.join(self.temp_dir.name, "checkpoint.pt")
        if os.path.exists(checkpoint_app.CHECKPOINT_PATH):
            os.remove(checkpoint_app.CHECKPOINT_PATH)

    def tearDown(self):
        checkpoint_app.CHECKPOINT_PATH = self.original_checkpoint_path
        self.temp_dir.cleanup()

    def test_checkpoint_and_resume_round_trip(self):
        checkpoint_response = checkpoint_app.checkpoint()
        self.assertTrue(checkpoint_response["done"])
        self.assertTrue(os.path.exists(checkpoint_app.CHECKPOINT_PATH))
        self.assertIn("work_saved_seconds", checkpoint_response)
        self.assertGreaterEqual(checkpoint_response["work_saved_seconds"], 0.0)

        resume_response = checkpoint_app.resume()
        self.assertTrue(resume_response["done"])
        self.assertIn("work_saved_seconds", resume_response)
        self.assertEqual(resume_response["work_saved_seconds"], checkpoint_response["work_saved_seconds"])


if __name__ == "__main__":
    unittest.main()
