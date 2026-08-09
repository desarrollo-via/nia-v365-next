import unittest

from bitrix_connector.internal_identity_names import (
    BOT_HUMAN_NAMES,
    CHAT_HUMAN_NAMES,
    bot_identity_label,
    chat_identity_label,
    human_bot_name,
    human_chat_name,
)


class InternalIdentityNamesTests(unittest.TestCase):
    def test_known_bots_have_stable_human_names(self):
        self.assertEqual(BOT_HUMAN_NAMES[245339], "Bot NIA")
        self.assertEqual(BOT_HUMAN_NAMES[373259], "Bot Next")
        self.assertEqual(
            bot_identity_label(373259),
            "Bot Next (bot_id=373259)",
        )

    def test_known_chat_keeps_both_technical_identifiers(self):
        self.assertEqual(
            CHAT_HUMAN_NAMES[78733],
            "Chat Test",
        )
        self.assertEqual(
            chat_identity_label(78733),
            "Chat Test (chat_id=78733, dialog_id=chat78733)",
        )

    def test_unknown_identities_are_visibly_uncatalogued(self):
        self.assertEqual(human_bot_name(999), "Bot no catalogado 999")
        self.assertEqual(human_chat_name(888), "Chat no catalogado 888")

    def test_invalid_identifiers_are_rejected(self):
        for value in (0, -1, True, "78733"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    human_bot_name(value)
                with self.assertRaises(ValueError):
                    human_chat_name(value)


if __name__ == "__main__":
    unittest.main()
