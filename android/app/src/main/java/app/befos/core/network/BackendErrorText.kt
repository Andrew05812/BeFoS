package app.befos.core.network

import java.util.Locale

/**
 * The API contract is English; the product is Russian. Showing the envelope message
 * verbatim puts the backend on screen — the classic student-project tell — so every
 * known message gets product copy here, and anything unknown falls back to Russian
 * status text rather than the raw English.
 */

/**
 * The one wording for a chat this person can no longer open. Three paths reach that fact — the
 * REST refusal of a dissolved pair, the websocket handshake the server will not grant, and the
 * screen that shows an empty thread — so it is stated once and shared rather than written three
 * times that can drift apart.
 */
const val CHAT_CLOSED = "Этот чат больше недоступен."

/**
 * The three formats the server's photo pipeline re-encodes, and the one wording that says so.
 *
 * The client needs both halves: the copy for the refusal the server sends, and the check a picked
 * file passes before its bytes are put on the uplink. A file the pipeline cannot read costs a
 * doomed upload otherwise. `backend/tests/test_a_release_checklist_demands_a_photo_no_screen_can_take.py`
 * pins this list against `photo_service.ALLOWED_CONTENT_TYPES`, because the two halves drift only
 * once the server starts taking a fourth format.
 */
const val PHOTO_TYPES_SUPPORTED = "Поддерживаются JPEG, PNG и WEBP."
val PHOTO_UPLOAD_CONTENT_TYPES = setOf("image/jpeg", "image/png", "image/webp")

/**
 * What a closed chat still offers its reader. The line under [CHAT_CLOSED] must not be the
 * localized refusal of the read that set the state: «Пара не найдена. Обновите список.» was
 * written for a list that can be pulled again, and on a terminal screen it is advice that cannot
 * be followed — the same class of promise the «Повторить» button belonged to.
 */
const val CHAT_CLOSED_DETAIL = "Пара распущена, и её строки не перечитываются: новое обращение " +
    "получит тот же отказ."

/** Lowercased backend message -> UI copy. Keys mirror the raise sites in the API. */
private val translated: Map<String, String> = mapOf(
    // auth
    "invalid email or password." to "Не совпали email или пароль. Попробуйте ещё раз.",
    "an account with this email already exists." to "Такой email уже занят. Войдите или попробуйте другой.",
    "passwords do not match." to "Пароли не совпадают.",
    "password must be at least 8 characters." to "Пароль должен быть не короче 8 символов.",
    "current password is incorrect." to "Текущий пароль указан неверно.",
    "account is disabled." to "Аккаунт отключён. Обратитесь в поддержку.",
    "account is deactivated." to "Аккаунт отключён. Обратитесь в поддержку.",
    "user no longer exists." to "Сессия истекла. Войдите снова.",
    "user no longer active." to "Сессия истекла. Войдите снова.",
    "missing authentication token." to "Сессия истекла. Войдите снова.",
    "token has expired." to "Сессия истекла. Войдите снова.",
    "invalid authentication token." to "Сессия истекла. Войдите снова.",
    "invalid token type." to "Сессия истекла. Войдите снова.",
    "invalid token subject." to "Сессия истекла. Войдите снова.",
    "invalid or expired refresh token." to "Сессия истекла. Войдите снова.",
    "refresh token has been revoked." to "Сессия истекла. Войдите снова.",
    "not authenticated." to "Сессия истекла. Войдите снова.",

    // profile + preferences
    "name is required." to "Укажите имя.",
    "name cannot be empty." to "Укажите имя.",
    "invalid gender." to "Выберите пол из списка.",
    "invalid birth date." to "Укажите корректную дату рождения.",
    "users must be 18 or older." to "BeFoS доступен с 18 лет.",
    "birth_date must be in yyyy-mm-dd format." to "Укажите корректную дату рождения.",
    "age_min cannot be greater than age_max." to "Максимальный возраст должен быть не меньше минимального.",
    "complete your profile before discovering people." to "Заполните анкету, чтобы увидеть людей.",
    "an interest name cannot be empty." to "Пустой интерес выбрать нельзя.",
    "a gender preference cannot be empty." to "Пустое предпочтение по полу выбрать нельзя.",

    // photos
    "unsupported image type. use jpeg, png or webp." to PHOTO_TYPES_SUPPORTED,
    "empty file." to "Файл пуст. Выберите другое фото.",
    "file is not a valid image." to "Не удалось прочитать фото. Выберите другое.",
    "image dimensions are too large." to "Фото слишком большое. Выберите снимок поменьше.",
    // The three refusals of the management writes. The row's number comes from the server, so a
    // number it does not accept is its own row having changed under the screen — the advice is to
    // read it again, never to name a stranger's photograph.
    "no photograph with this number is in your profile." to
        "Этого снимка в вашем профиле нет. Обновите экран.",
    "a photo order cannot name the same photograph twice." to
        "Один и тот же снимок в порядке встречается дважды. Обновите экран.",

    // chat
    "message cannot be empty." to "Напишите сообщение.",
    "message is too long." to "Сообщение слишком длинное — разбейте его на два.",
    "you are not a participant of this chat." to CHAT_CLOSED,
    "you are not a participant of this match." to CHAT_CLOSED,
    "match not found." to "Пара не найдена. Обновите список.",
    // Frames the live socket refuses. Reached only when this client sends something the
    // server cannot use; the wording stays advice-shaped, never the English contract text.
    "invalid frame." to "Сервер не понял это сообщение. Попробуйте ещё раз.",
    "invalid message body." to "Сообщение не принято. Проверьте текст и отправьте ещё раз.",

    // discovery + matches
    "you cannot act on your own profile." to "Это ваша анкета.",
    "profile not found." to "Анкета не найдена.",
    "user not found." to "Пользователь не найден.",

    // recommendations + meeting time. The pair's plan is arranged in minutes and hours, so an
    // refusal about a moment is answered with the moment's own words, not with «проверьте данные».
    "send this idea to the chat before arranging a time for it." to
        "Договариваться о времени можно для идеи, которая уже отправлена в чат.",
    "the other half has not named a time for this idea yet." to
        "Партнёр ещё не предложил время для этой идеи.",
    "that time is no longer the one being offered." to
        "Партнёр уже предложил другое время. Обновите карточку и согласуйте его заново.",
    "this moment has already passed." to "Это время уже прошло. Выберите час позже.",
    "a meeting is arranged within the next year, not beyond it." to
        "Договориться можно только о встрече в ближайший год.",

    // safety
    "you cannot block yourself." to "Нельзя применить это к себе.",
    "you cannot unblock yourself." to "Нельзя применить это к себе.",
    // A release tap on a row the server no longer holds — because the list went stale, or because
    // the account behind it is gone — has to say which of the two it is, not the bare «не найдено»
    // a stranger's profile number also earns.
    "you have not blocked this user." to "Вы этого человека не блокировали. Обновите список.",
    "you cannot report yourself." to "Нельзя применить это к себе.",
    "you have already reported this user for the same reason." to "Такая жалоба уже отправлена.",
    // The hourly budget counts complaints this account wrote, so the line says which of the
    // account's own actions is full. The status fallback would read as a general overload and send
    // the person to retry the tap that just worked for a different complaint.
    "too many complaints for now. try again later." to "Жалоб с вашего аккаунта уже много. Попробуйте позже.",

    // moderation. The queue is a screen a moderator opens, so all four speak to the hand that
    // decides rather than to a person who filed something.
    "moderator role is required." to "Очередь модерации доступна только модератору.",
    "report not found." to "Этой жалобы уже нет в очереди. Обновите список.",
    "report cursor not found." to "Очередь изменилась, пока вы читали. Загрузите её заново.",
    "this complaint already carries that status." to "Жалоба уже в этом статусе.",
    "a moderator cannot decide a complaint about their own account." to
        "Свою жалобу вы решить не можете — её должен рассмотреть другой модератор.",
    "a complaint that is being closed needs a comment saying why." to
        "Закрывая жалобу, надо записать причину. Без записи решение не сохраняется.",

    // test
    "no answers provided." to "Ответьте хотя бы на один вопрос.",
    "invalid input." to "Проверьте введённые данные.",
    "invalid request payload." to "Проверьте введённые данные.",

    // generic. The three that belong to a status family name it instead of repeating its
    // sentence, so a failure cannot grow two wordings.
    "something went wrong." to "Не удалось выполнить запрос. Попробуйте ещё раз.",
    "resource not found." to defaultHttpMessage(404),
    "resource already exists." to "Это уже добавлено.",
    "you do not have access to this resource." to defaultHttpMessage(403),
    "request failed." to "Не удалось выполнить запрос. Попробуйте ещё раз.",
    "internal server error." to defaultHttpMessage(500),
    "too many requests. please slow down." to "Слишком много запросов. Подождите немного.",
    // An outage is not a bug and not a logout: the only advice there is, is to wait.
    "befos is sorting itself out for a moment. try again in a few seconds." to
        "Сервис временно недоступен. Попробуйте ещё раз через несколько секунд.",
)

/** Backend builds some messages from data, so they are matched by their constant prefix. */
private val translatedPrefixes: List<Pair<String, String>> = listOf(
    "Image exceeds " to "Фото слишком большое. Выберите файл меньшего размера.",
    "Invalid report reason" to "Выберите причину жалобы из списка.",
    "Question " to "Тест обновился. Перезагрузите страницу.",
    "Option " to "Тест обновился. Перезагрузите страницу.",
    "Test is not finished yet" to "Пройдите тест до конца, чтобы увидеть результат.",
    "client_msg_id" to "Сообщение не отправлено. Попробуйте ещё раз.",
    "Unknown message type" to "Сообщение не отправлено. Попробуйте ещё раз.",
    // Both interest refusals name data the backend counted, so neither is a fixed sentence.
    "A profile can hold at most " to "Интересов можно выбрать не больше 30.",
    "Interests the catalogue does not know" to "Таких интересов в списке нет. Обновите экран и выберите заново.",
    // The gender pair is the same shape: one names the ceiling the server counted, the other
    // names the values it refused. Both are stated as the screen's own limit, not the server's.
    "A profile can prefer at most " to "Предпочтений по полу можно выбрать не больше четырёх.",
    "Genders the server does not know" to "Таких вариантов пола в списке нет. Обновите экран и выберите заново.",
    // The goal refusal names the value it refused and lists the goals the server actually scores,
    // so its constant part is only the opening; the screen keeps its own advice-shaped copy.
    "Invalid dating goal" to "Выберите цель знакомства.",
    // The server names the whole rule in one sentence about two cities; the screen says what to do.
    "Meeting time must carry a UTC offset" to "Не удалось понять, в каком поясе этот час.",
    // A refused order names how many photographs the screen left out, so its constant part is the
    // opening. What the person can do is re-read the row, which is what the copy says.
    "A photo order must name every photograph the profile holds" to
        "Список снимков изменился. Обновите экран и переставьте заново.",
    // A refused transition names the two statuses the row actually holds and was asked to take. The
    // screen cannot repair that pair — the queue moved under the reader — so the copy sends them back
    // to the row rather than repeating the server's own sentence about it.
    "A complaint cannot move from " to "Жалоба уже не переходит в этот статус. Обновите очередь.",
    "Invalid report status. Allowed:" to "Такого статуса жалоба не принимает.",
    "That comment is longer than " to "Запись слишком длинная. Сократите её.",
)

/** Second layer: the envelope's machine code covers messages this file has never seen. */
private fun fallback(code: String, status: Int): String = when (code) {
    "unauthorized" -> "Сессия истекла. Войдите снова."
    "validation_error" -> "Проверьте введённые данные."
    // These three are the status families themselves; naming the status keeps one failure
    // from having two wordings that drift apart.
    "forbidden" -> defaultHttpMessage(403)
    "not_found" -> defaultHttpMessage(404)
    "internal_error" -> defaultHttpMessage(500)
    "conflict" -> "Это уже сделано."
    "rate_limited" -> "Слишком много запросов. Подождите немного."
    "database_unavailable" -> "Сервис временно недоступен. Попробуйте ещё раз через несколько секунд."
    else -> defaultHttpMessage(status)
}

fun localizeBackendError(rawMessage: String, code: String, status: Int): String {
    val message = rawMessage.trim()
    if (message.isEmpty()) return fallback(code, status)
    translated[message.lowercase(Locale.ROOT)]?.let { return it }
    translatedPrefixes.firstOrNull { message.startsWith(it.first) }?.let { return it.second }
    return fallback(code, status)
}
