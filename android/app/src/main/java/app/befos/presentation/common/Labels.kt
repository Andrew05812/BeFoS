package app.befos.presentation.common

val GenderLabels = linkedMapOf(
    "male" to "Мужской",
    "female" to "Женский",
    "nonbinary" to "Небинарный",
    "other" to "Другое",
)

val DatingGoalLabels = linkedMapOf(
    "relationship" to "Отношения",
    "marriage" to "Брак",
    "friendship" to "Дружба",
    "casual" to "Лёгкое общение",
    "networking" to "Нетворкинг",
)

fun genderLabel(code: String): String = GenderLabels[code] ?: code
fun goalLabel(code: String): String = DatingGoalLabels[code] ?: code

/**
 * The identity line under a name — "Москва · Отношения". A separator only joins two
 * things that were both answered: a profile that has no city says its goal alone instead
 * of opening with a dangling " · ", and one with neither says nothing at all.
 */
fun identityLine(city: String, goalCode: String): String =
    listOf(city.trim(), goalLabel(goalCode)).filter { it.isNotBlank() }.joinToString(" · ")

// Mirrors backend VALID_REASONS in safety_service.py: the API accepts only these slugs.
val ReportReasonLabels = linkedMapOf(
    "spam" to "Спам",
    "harassment" to "Оскорбления",
    "inappropriate" to "Неподходящие фото",
    "fake" to "Ненастоящая анкета",
    "minor" to "Анкета несовершеннолетнего",
    "other" to "Другое",
)
