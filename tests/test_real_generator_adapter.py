from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.generators.real_generator_adapter import RealGeneratorAdapter


class RealGeneratorAdapterTest(unittest.TestCase):
    def test_gpt_image_backend_posts_to_images_generation_and_saves_b64(self) -> None:
        captured: dict[str, object] = {}
        image_bytes = b"fake image bytes"

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "created": 123,
                        "data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}],
                    }
                ).encode("utf-8")

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured["url"] = getattr(request, "full_url")
            captured["timeout"] = timeout
            captured["payload"] = json.loads(getattr(request, "data").decode("utf-8"))
            captured["auth"] = request.get_header("Authorization")
            return FakeResponse()

        env = {
            "GEN_RETRY_IMAGE_BASE_URL": "https://skyapi.duckdns.org/v1",
            "GEN_RETRY_IMAGE_API_KEY": "test-key",
            "GEN_RETRY_IMAGE_MODEL": "gpt-image-2",
            "GEN_RETRY_IMAGE_SIZE": "1024x1024",
            "GEN_RETRY_IMAGE_EXTRA_JSON": '{"quality":"high"}',
        }
        with TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False), patch(
            "gen_retry.generators.real_generator_adapter.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            output = Path(tmp) / "image.png"
            result = RealGeneratorAdapter("gpt_image").generate("a red cube", str(output))
            self.assertEqual(result, str(output))
            self.assertEqual(output.read_bytes(), image_bytes)
            self.assertTrue(output.with_suffix(".png.json").exists())
        self.assertEqual(captured["url"], "https://skyapi.duckdns.org/v1/images/generations")
        self.assertEqual(captured["auth"], "Bearer test-key")
        self.assertEqual(captured["payload"]["model"], "gpt-image-2")
        self.assertEqual(captured["payload"]["prompt"], "a red cube")
        self.assertEqual(captured["payload"]["quality"], "high")

    def test_gpt_image_backend_requires_image_api_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEN_RETRY_IMAGE_BASE_URL"):
                RealGeneratorAdapter("gpt_image").generate("prompt", "out.png")


if __name__ == "__main__":
    unittest.main()
