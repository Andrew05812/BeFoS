"""The text a person accepts when an account is made, and the version of it they accepted.

A consent is not a checkbox. It is a document with a name, a version and a date, and a product only
knows what somebody agreed to while it can still say which of those three it was. So the text lives
here, in the tree, and travels to the client from `GET /auth/consent` — not baked into an app build,
which would make every installed version vouch for whatever its author remembered at that time.

The version is a short product string, not a hash: the database stores which text was accepted
(`users.consent_version`), and a hash would turn «what did this person agree to» into a question
answered by a repository archaeology session. It changes when the words below change in a way a
person would care about — a new purpose, a new category of data, a new right — and then every account
that accepted an older version is asked again before it continues (`GET /users/me` reports
`consent_up_to_date`, and `RootViewModel` sends it to the consent screen).

`CONSENT_TEXT` is what the product says today. It is not a substitute for the operator's own privacy
policy: a service that takes real people's data publishes that document under its own name, and
`docs/RELEASE.md` names it as the owner's outstanding item. What this file can do is make the claim
the app itself makes accurate — every sentence below is something the code in this repository
actually does.
"""

from __future__ import annotations

CONSENT_VERSION = "1"

# The date the words of this version took effect. It travels beside the text so a person reading a
# copy of it later can tell which draft they read without diffing the repository.
CONSENT_EFFECTIVE_DATE = "2026-11-09"

CONSENT_TEXT = """\
BeFoS — приложение для знакомств по совместимости. Чтобы сервис работал, он хранит то, что вы \
сами о себе рассказали, и то, что возникает из ваших действий. Этот текст говорит, что именно.

Что хранится

- Адрес электронной почты и пароль. Пароль хранится как необратимый хэш, а не открытым текстом, и \
сервис не может его прочитать.
- Анкета: имя, дата рождения, город, пол, цель знакомства, интересы, образ жизни и фотографии.
- Ответы тестов и профиль совместимости, посчитанный по ним.
- Симпатии, пропуски, совпадения, переписка, прочитанные сообщения и совместные планы.
- Отметка о согласии: версия этого текста и время, когда вы её приняли.

Зачем

- Чтобы показывать вашу анкету другим людям в подборе и в паре и считать совместимость.
- Чтобы отправлять письма с кодом: подтверждение адреса и возврат доступа к аккаунту.
- Чтобы разбирать жалобы и защищать людей от злоупотреблений.

Чего сервис не делает

- Не продаёт данные и не передаёт их рекламным сетям.
- Не создаёт анкет за вас и не подставляет людей в подбор: в колоде только настоящие \
зарегистрированные аккаунты.

Ваши права

- Выгрузить всё, что о вас хранится, одним файлом: «Настройки» → «Выгрузка данных».
- Удалить аккаунт: «Настройки» → «Удаление аккаунта». Удаление стирает анкету, фотографии, \
ответы тестов, симпатии, совпадения, планы и переписку; адрес освобождается. Вернуть удалённое \
нельзя.
- Отказаться от обработки. Без этих данных сервису нечем вас знакомить, поэтому отказ означает \
удаление аккаунта.

Возраст

BeFoS — только для людей 18 лет и старше. Регистрируясь, вы подтверждаете, что вам есть 18. Дата \
рождения, указанная в анкете, проверяется на сервере, и аккаунт младше 18 не может попасть в подбор.

Версия и дата

Версия этого текста — {version}, дата вступления в силу — {date}. Если текст изменится, сервис \
попросит принять новую версию до того, как вы продолжите пользоваться аккаунтом.
"""


def consent_document(version: str | None = None, effective_date: str | None = None,
                     text: str | None = None) -> dict[str, str]:
    """The document as the door answers it: version, date, text — and nothing about a person."""
    version = version or CONSENT_VERSION
    effective_date = effective_date or CONSENT_EFFECTIVE_DATE
    body = text if text is not None else CONSENT_TEXT
    return {
        "version": version,
        "effective_date": effective_date,
        "text": body.format(version=version, date=effective_date),
    }


def is_current(version: str | None) -> bool:
    """Whether this account accepted the text the product is asking for now.

    `None` is not «current»: every account made before the consent existed has no version on its row,
    and a truthy answer for silence is exactly how a product ends up claiming agreement nobody gave.
    """
    return version == CONSENT_VERSION
