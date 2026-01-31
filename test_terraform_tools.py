import unittest
import os
import shutil
from terraform_tools import TerraformTool

class TestTerraformTool(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_terraform"
        self.tf = TerraformTool(base_dir=self.test_dir)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_write_file(self):
        content = 'resource "aws_s3_bucket" "test" { bucket = "my-test-bucket" }'
        result = self.tf.write_file("main.tf", content, "subdir")
        self.assertIn("Successfully wrote main.tf", result)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "subdir", "main.tf")))

        with open(os.path.join(self.test_dir, "subdir", "main.tf"), "r") as f:
            self.assertEqual(f.read(), content)

    def test_init_fail(self):
        # This should fail or show error because there are no files
        result = self.tf.init("empty_dir")
        self.assertTrue(
            "Terraform initialized in an empty directory" in result or
            "No configuration files" in result
        )

if __name__ == "__main__":
    unittest.main()
