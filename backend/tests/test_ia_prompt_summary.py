"""The compacted start of a conversation must be presented as such: under a bare title, gemma4:e4b
answered "what do you remember?" from the last exchanges only (prod 2026-11-11; veille bench 5/10 -> 10/10)."""
from app.ia_prompt import summary_block


def test_summary_is_presented_as_the_start_of_this_conversation():
    block = summary_block("FAITS:\n* Le point d'accès Wi-Fi est entre la Table 2 et la Table 4.")
    assert block.startswith("=== EARLIER IN THIS CONVERSATION ===\n")
    assert "no longer shown to you" in block and "asks what you remember" in block
    assert block.endswith("* Le point d'accès Wi-Fi est entre la Table 2 et la Table 4.")
