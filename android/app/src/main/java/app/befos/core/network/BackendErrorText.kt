package app.befos.core.network

import java.util.Locale

/**
 * The API contract is English; the product is Russian. Showing the envelope message
 * verbatim puts the backend on screen — the classic student-project tell — so every
 * known message gets product copy here, and anything unknown falls back to Russian
 * status text rather than the raw English.
 */

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
    "invalid dating goal." to "Выберите цель знакомства.",
    "invalid birth date." to "Укажите корректную дату рождения.",
    "users must be 18 or older." to "BeFoS доступен с 18 лет.",
    "birth_date must be in yyyy-mm-dd format." to "Укажите корректную дату рождения.",
    "age_min cannot be greater than age_max." to "Максимальный возраст должен быть не меньше минимального.",
    "complete your profile before discovering people." to "Заполните анкету, чтобы увидеть людей.",

    // photos
    "unsupported image type. use jpeg, png or webp." to "Поддерживаются JPEG, PNG и WEBP.",
    "empty file." to "Файл пуст. Выберите другое фото.",
    "file is not a valid image." to "Не удалось прочитать фото. Выберите другое.",
    "image dimensions are too large." to "Фото слишком большое. Выберите снимок поменьше.",

    // chat
    "message cannot be empty." to "Напишите сообщение.",
    "message is too long." to "Сообщение слишком длинное — разбейте его на два.",
    "you are not a participant of this chat." to "Этот чат больше недоступен.",
    "you are not a participant of this match." to "Этот чат больше недоступен.",
    "match not found." to "Пара не найдена. Обновите список.",

    // discovery + matches
    "you cannot act on your own profile." to "Это ваша анкета.",
    "profile not found." to "Анкета не найдена.",
    "user not found." to "Пользователь не найден.",

    // safety
    "you cannot block yourself." to "Нельзя применить это к себе.",
    "you cannot report yourself." to "Нельзя применить это к себе.",
    "you have already reported this user for the same reason." to "Такая жалоба уже отправлена.",

    // test
    "no answers provided." to "Ответьте хотя бы на один вопрос.",
    "invalid input." to "Проверьте введённые данные.",
    "invalid request payload." to "Проверьте введённые данные.",

    // generic
    "something went wrong." to "Не удалось выполнить запрос. Попробуйте ещё раз.",
    "resource not found." to "Не найдено.",
    "resource already exists." to "Это уже добавлено.",
    "you do not have access to this resource." to "Нет доступа.",
    "request failed." to "Не удалось выполнить запрос. Попробуйте ещё раз.",
    "internal server error." to "Ошибка сервера. Попробуйте позже.",
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
)

/** Second layer: the envelope's machine code covers messages this file has never seen. */
private fun fallback(code: String, status: Int): String = when (code) {
    "unauthorized" -> "Сессия истекла. Войдите снова."
    "validation_error" -> "Проверьте введённые данные."
    "forbidden" -> "Нет доступа."
    "not_found" -> "Не найдено."
    "conflict" -> "Это уже сделано."
    "rate_limited" -> "Слишком много запросов. Подождите немного."
    "internal_error" -> "Ошибка сервера. Попробуйте позже."
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
