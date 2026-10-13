"""A dissolved pair leaves a chat whose only offer is a retry that cannot succeed.

Stage 72 §2 walked the navigation map and §5 the social mechanics on the live stand. The two meet in
one state that nobody had drawn: the card of a partner (``Routes.PARTNER``, added at stage 72-10)
returns the person who blocks from it straight back to ``Routes.CHAT`` of the pair that the block
just dissolved — ``PublicProfileScreen.kt`` calls ``onBack()`` when ``state.gone`` lands and its
``match`` is null. What that screen then shows was measured, not imagined
(``s72_d11_block_pair.txt``, прогон 03:17:13…03:17:16 UTC): after ``A blocks B`` both sides read
their own pair back as 404 ``not_found`` with ``Match not found.`` — the list, the detail, the
history page, the compatibility, the recommendations — and ``B`` liking ``A`` again is refused the
same way, so the rows behind that thread are gone for good.

The client had already been given the status for exactly this case: ``ApiResult.Error`` carries it
(``SafeApiCall.kt``), ``BackendErrorText`` knows the sentence for a closed chat, and
``ChatRepositoryImpl`` stops redialling a handshake answered 403 because that answer is the pair's
state and not the network's. ``ChatViewModel.loadHistory()`` was the one place that dropped the
status: it kept ``result.message`` and threw ``result.code`` away, so a thread that will never be
read again was drawn as a page that merely failed to arrive — «Не удалось загрузить переписку» above
a «Повторить» that pays for the same 404, and a composer that accepts a message the server will
refuse on every tap. The same class of control was removed for an expired session
(``BeFosNavHost.kt:34-45``) and for the gestures of a formed pair
(``test_the_card_of_a_partner_has_no_way_to_be_opened_by_the_pair.py``).

The checks below read the Kotlin sources and require the end of a thread to be a state of its own,
decided by the status the API actually answers with, and drawn without the promises that state
cannot keep.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
CLIENT = ROOT / "android/app/src/main/java/app/befos"
CHAT_VM = CLIENT / "presentation/chat/ChatViewModel.kt"
CHAT_SCREEN = CLIENT / "presentation/chat/ChatScreen.kt"
ERROR_TEXT = CLIENT / "core/network/BackendErrorText.kt"
CHAT_REPO = CLIENT / "data/repository/ChatRepositoryImpl.kt"
CHAT_SERVICE = ROOT / "backend/app/services/chat_service.py"

CLOSED_SENTENCE = "Этот чат больше недоступен."


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_view_model_keeps_the_status_that_ends_a_thread() -> None:
    """A refusal that names the pair as gone has to survive longer than the string it carries."""
    vm = _read(CHAT_VM)
    assert re.search(r"val gone: Boolean = false", vm) is not None, (
        "ChatUiState publishes no state of its own for a thread the server refuses"
    )
    assert re.search(r"isEndOfThread\w*\(result\.code\)", vm) is not None, (
        "the refused read never looks at the status, so a gone pair and a dropped network "
        "stay one state on screen"
    )
    assert re.search(r"code == 404", vm) is not None, (
        "the end of a thread is not keyed on the status the pair actually answers with"
    )


def test_a_thread_that_was_read_again_is_not_left_ended() -> None:
    """A page that arrives is the pair answering for itself; the ended state cannot outlive it."""
    vm = _read(CHAT_VM)
    reads = re.findall(r"is ApiResult\.Success -> .*?\n(?:.*?\n){0,12}?\s{16}\}", vm)
    clearing = [block for block in reads if "gone = false" in block]
    assert len(clearing) >= 2, (
        "only one of the two thread reads takes the ended state back: a gap page that arrives "
        "after a refusal would leave a live thread drawn as a closed one"
    )


def test_a_closed_thread_is_drawn_without_a_retry_that_cannot_work() -> None:
    """The screen names the end instead of paying for the same refusal a second time."""
    screen = _read(CHAT_SCREEN)
    assert re.search(r"state\.messages\.isEmpty\(\) && state\.gone ->", screen) is not None, (
        "ChatScreen.kt has no branch that draws a thread the server refuses as gone"
    )
    assert re.search(r"actionLabel = if \(state\.gone\) null else \"Повторить\"", screen) is not None, (
        "the notice over an open thread still offers a retry once the pair is gone"
    )
    gone_branch = screen[screen.index("state.gone ->") :]
    assert "onRetry" not in gone_branch[: gone_branch.index("state.messages.isEmpty() && state.historyError")], (
        "the gone branch hands out a retry button"
    )


def test_a_thread_that_cannot_receive_a_message_holds_the_composer_back() -> None:
    """An input that fails on every tap is the dead end the map was walked to find."""
    screen = _read(CHAT_SCREEN)
    bottom = re.search(r"bottomBar = \{\s*(?P<body>.*?)(?:\n        \},)", screen, re.S)
    assert bottom is not None, "ChatScreen.kt no longer builds its bottom bar where it can be read"
    assert "if (!state.gone)" in bottom["body"], (
        "the composer is drawn for a pair the server refuses, so every send answers 404"
    )
    # The status pill promises a recovery; a gone thread has stopped dialling, so it says nothing.
    pill = re.search(
        r"if \(!state\.loading && !state\.connected(?P<rest> && !state\.gone)?\)", screen
    )
    assert pill is not None and pill["rest"] is not None, (
        "the reconnecting pill is drawn over a thread that will never reconnect"
    )


def test_the_sentence_for_a_closed_chat_is_written_once() -> None:
    """Three paths reach this fact — the REST refusal, the refused handshake, the empty screen."""
    text = _read(ERROR_TEXT)
    assert re.search(rf'const val CHAT_CLOSED = "{re.escape(CLOSED_SENTENCE)}"', text) is not None, (
        "core/network declares no shared wording for a chat that closed"
    )
    repo = _read(CHAT_REPO)
    assert "import app.befos.core.network.CHAT_CLOSED" in repo, (
        "the socket answers with its own copy of the sentence instead of the shared one"
    )
    screen = _read(CHAT_SCREEN)
    assert "title = CHAT_CLOSED" in screen, (
        "the screen that shows the closed chat writes the sentence again"
    )
    written = [
        path for path in CLIENT.rglob("*.kt")
        if CLOSED_SENTENCE in path.read_text(encoding="utf-8")
    ]
    assert [path.name for path in written] == ["BackendErrorText.kt"], (
        f"the sentence is spelled out in {len(written)} files, which can drift apart"
    )


def test_the_closed_screen_says_what_is_left_instead_of_repeating_the_refusal() -> None:
    """The line under the title cannot be the advice carried by the read that ended the thread.

    ``Пара не найдена. Обновите список.`` is the localized answer of the refused history page, and
    a person who follows it — pulls the list again — returns to the same screen, so the terminal
    state has to say what is still true of it instead. The check reads both files: the wording is
    declared once beside the shared sentence, and the gone branch quotes it rather than
    ``state.historyError``.
    """
    text = _read(ERROR_TEXT)
    assert re.search(r'const val CHAT_CLOSED_DETAIL = "Пара распущена', text) is not None, (
        "core/network declares no terminal wording for a closed chat"
    )
    screen = _read(CHAT_SCREEN)
    gone_branch = screen[screen.index("state.gone ->") :]
    gone_branch = gone_branch[: gone_branch.index("state.messages.isEmpty() && state.historyError")]
    assert "message = CHAT_CLOSED_DETAIL" in gone_branch, (
        "the closed screen shows the refused read's advice again"
    )
    assert "state.historyError" not in gone_branch, (
        "whatever the API answered next becomes the terminal copy on screen"
    )


def test_the_pair_answers_with_the_status_the_client_keys_on() -> None:
    """The client's rule is only honest while the API keeps answering a dissolved pair with 404."""
    service = _read(CHAT_SERVICE)
    membership = re.search(
        r"async def _require_membership\(.*?(?=\n    async def |\nclass )", service, re.S
    )
    assert membership is not None, "chat_service.py no longer has the membership check to read"
    assert 'NotFoundError("Match not found.")' in membership.group(0), (
        "a pair that is not there answers with something other than 404, and the client's rule "
        "ends threads it should only pause"
    )
