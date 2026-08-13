import tempfile
import unittest
from pathlib import Path

from bitrix_connector.r1_key_vault_protected_probe_dotenv_source import (
    ExactReviewTokenDotenvSource,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_owner import (
    REVIEW_TOKEN_NAME,
)


TOKEN = b"fixture-review-token-long-enough"


class R1KeyVaultProtectedProbeDotenvSourceTests(unittest.IsolatedAsyncioTestCase):
    async def source(self, content):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / ".env"
        path.write_bytes(content)
        return ExactReviewTokenDotenvSource(path, expected_path=path)

    async def test_extracts_only_exact_review_token_once(self):
        source = await self.source(
            b"OTHER_SECRET=decoy\n"
            + REVIEW_TOKEN_NAME.encode()
            + b"="
            + TOKEN
            + b"\nANOTHER=decoy\n"
        )
        await source.open()
        value = await source.read_exact(REVIEW_TOKEN_NAME)
        self.assertEqual(value, bytearray(TOKEN))
        value[:] = b"\x00" * len(value)
        value.clear()
        await source.close()
        with self.assertRaisesRegex(RuntimeError, "source_reused"):
            await source.open()

    async def test_missing_duplicate_quoted_or_short_value_fails_closed(self):
        cases = (
            b"OTHER=value\n",
            REVIEW_TOKEN_NAME.encode() + b"=" + TOKEN + b"\n" + REVIEW_TOKEN_NAME.encode() + b"=" + TOKEN,
            REVIEW_TOKEN_NAME.encode() + b"='" + TOKEN + b"'\n",
            REVIEW_TOKEN_NAME.encode() + b"=short\n",
        )
        for content in cases:
            with self.subTest(content_length=len(content)):
                source = await self.source(content)
                with self.assertRaises((RuntimeError, ValueError)):
                    await source.open()
                await source.close()

    async def test_wrong_name_or_path_is_blocked(self):
        source = await self.source(REVIEW_TOKEN_NAME.encode() + b"=" + TOKEN)
        with self.assertRaisesRegex(RuntimeError, "read_blocked"):
            await source.read_exact("OTHER")
        with tempfile.TemporaryDirectory() as other:
            wrong = ExactReviewTokenDotenvSource(
                Path(other) / ".env",
                expected_path=Path(other) / "expected.env",
            )
            with self.assertRaisesRegex(ValueError, "path_invalid"):
                await wrong.open()


if __name__ == "__main__":
    unittest.main()
