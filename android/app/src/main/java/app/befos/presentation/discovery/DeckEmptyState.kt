package app.befos.presentation.discovery

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.EmberSoft
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Iris
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.Spacing

/**
 * One empty deck, seven different sentences.
 *
 * The server decides **why** the page carried no cards (`DiscoveryEmpty.reason`); this file only
 * chooses the words and the one or two doors that answer that reason. It never counts people, names
 * anybody, or upgrades a bucket: «рядом уже есть люди» may be drawn from `audience == "some"`, but
 * «рядом 37 человек» may not, because the second sentence is a fact about thirty-seven accounts that
 * never agreed to be a number on somebody's screen.
 *
 * The priorities are deliberate. A gate on the reader's own account (mail, questionnaire) is the
 * primary action and outranks every invitation. When the product itself is simply young, the only
 * action that changes the world is another person, so «Пригласить друга» is primary. A waitlist mark
 * never pretends to be a subscription: it stores a city, and the copy says that letters do not exist
 * yet.
 */
@Composable
fun DeckEmptyState(
    state: DiscoveryUiState,
    onRefresh: () -> Unit,
    onOpenFilters: () -> Unit,
    onOpenReferrals: () -> Unit,
    onConfirmEmail: () -> Unit,
    onFinishOnboarding: () -> Unit,
    onJoinWaitlist: () -> Unit,
    onLeaveWaitlist: () -> Unit,
    onDismissWaitlistError: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val why = state.empty
    val copy = deckCopy(
        reason = why?.reason,
        someonePreparingHere = why?.someonePreparingHere == true,
        canWidenFilters = why?.canWidenFilters == true,
        reviewedThisVisit = state.reviewedAllLoaded,
        onRefresh = onRefresh,
        onOpenFilters = onOpenFilters,
        onOpenReferrals = onOpenReferrals,
        onConfirmEmail = onConfirmEmail,
        onFinishOnboarding = onFinishOnboarding,
    )
    val joined = state.waitlist?.joined == true
    val waitingCity = state.waitlist?.city

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.huge)
            .padding(top = Spacing.hero, bottom = Spacing.xxl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Box(
            Modifier
                .size(72.dp)
                .background(
                    Brush.linearGradient(listOf(EmberSoft, IrisSoft)),
                    CircleShape,
                )
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier
                    .size(40.dp)
                    .background(
                        Brush.linearGradient(listOf(Peach, MaterialTheme.colorScheme.primary, Iris)),
                        CircleShape,
                    ),
            )
        }

        Text(
            copy.overline.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            copy.title,
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
        )
        Text(
            copy.message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )

        copy.primary?.let { (label, action) ->
            AppButton(
                text = label,
                onClick = action,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        copy.secondary?.let { (label, action) ->
            AppButton(
                text = label,
                onClick = action,
                variant = AppButtonVariant.Tonal,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        copy.tertiary?.let { (label, action) ->
            AppButton(
                text = label,
                onClick = action,
                variant = AppButtonVariant.Ghost,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        if (copy.offerWaitlist) {
            WaitlistSection(
                joined = joined,
                city = waitingCity,
                busy = state.waitlistBusy,
                error = state.waitlistError,
                onJoin = onJoinWaitlist,
                onLeave = onLeaveWaitlist,
                onRetry = { onDismissWaitlistError(); if (joined) onLeaveWaitlist() else onJoinWaitlist() },
            )
        }
    }
}

/**
 * The waiting mark is a row, not a subscription. Its copy says where the city came from and that
 * no letter is sent today, because `WaitlistService` has no product-notice channel in this build —
 * promising one would turn a stored request into a message the system cannot keep.
 */
@Composable
private fun WaitlistSection(
    joined: Boolean,
    city: String?,
    busy: Boolean,
    error: String?,
    onJoin: () -> Unit,
    onLeave: () -> Unit,
    onRetry: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = Spacing.sm),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text(
            if (joined) {
                "Вы в листе ожидания${city?.let { ": $it" }.orEmpty()}. " +
                    "Отметка добровольная и её можно убрать в любой момент. " +
                    "Писем об этом пока не присылаем — канала для уведомления ещё нет."
            } else {
                "Можно отметить, что вы ждёте людей рядом. Мы сохраним город из вашего профиля, если он указан. " +
                    "Это не подписка на уведомления: писем пока не будет."
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        AppButton(
            text = if (joined) "Убрать отметку" else "Записаться в лист ожидания",
            onClick = if (joined) onLeave else onJoin,
            variant = AppButtonVariant.Ghost,
            loading = busy,
            modifier = Modifier.fillMaxWidth(),
        )
        if (error != null) {
            InlineNotice(
                text = error,
                actionLabel = "Повторить",
                onAction = onRetry,
            )
        }
    }
}

/** Everything the screen needs to say and every door it can offer, for one reason. */
private data class DeckCopy(
    val title: String,
    val message: String,
    val overline: String = "Подбор",
    val primary: Pair<String, () -> Unit>? = null,
    val secondary: Pair<String, () -> Unit>? = null,
    val tertiary: Pair<String, () -> Unit>? = null,
    val offerWaitlist: Boolean = false,
)

private fun deckCopy(
    reason: String?,
    someonePreparingHere: Boolean,
    canWidenFilters: Boolean,
    reviewedThisVisit: Boolean,
    onRefresh: () -> Unit,
    onOpenFilters: () -> Unit,
    onOpenReferrals: () -> Unit,
    onConfirmEmail: () -> Unit,
    onFinishOnboarding: () -> Unit,
): DeckCopy = when (reason) {
    "email_unconfirmed" -> DeckCopy(
        title = "Подтвердите почту",
        message = "Пока адрес не подтверждён, вашу анкету не показывают другим — значит, " +
            "взаимной симпатии не случится. Письмо с кодом приходит при регистрации; если его " +
            "нет, экран подтверждения отправит новое. Это занимает минуту.",
        primary = "Подтвердить почту" to onConfirmEmail,
        secondary = "Я уже подтвердил — проверить" to onRefresh,
    )
    "onboarding_incomplete" -> DeckCopy(
        title = "Заполните профиль",
        message = "Короткая анкета о ценностях и образе жизни нужна, чтобы подбор было с чем " +
            "сравнивать. Пока она не заполнена, вас не показывают другим и совпадений не будет.",
        primary = "Заполнить анкету" to onFinishOnboarding,
        secondary = "Проверить снова" to onRefresh,
    )
    "filters_too_narrow" -> DeckCopy(
        title = "Под фильтры никто не подходит",
        message = "Анкеты есть, но выбранные пол и возраст не оставляют ни одной. Ослабьте одну " +
            "границу — и подбор снова наполнится.",
        primary = "Изменить фильтры" to onOpenFilters,
        secondary = "Проверить снова" to onRefresh,
        tertiary = "Пригласить друга" to onOpenReferrals,
    )
    "city_filter_empty" -> DeckCopy(
        title = "В выбранном городе пока никого",
        message = "Пол и возраст подходят людям в других городах, а выбранный город поиска " +
            "оставляет подбор пустым. Город можно изменить в фильтрах.",
        primary = "Изменить город поиска" to onOpenFilters,
        secondary = "Проверить снова" to onRefresh,
        tertiary = "Пригласить друга" to onOpenReferrals,
    )
    "audience_preparing" -> DeckCopy(
        title = "Люди уже регистрируются",
        message = if (someonePreparingHere) {
            "Кто-то в вашем городе уже заполняет профиль или подтверждает почту. Анкеты " +
                "показываются только после проверки — загляните чуть позже или позовите друга."
        } else {
            "Анкеты в BeFoS уже появляются, но пока не готовы к показу: адрес не подтверждён " +
                "или анкета не заполнена. Это временно. Можно позвать друга или отметить, " +
                "что вы ждёте людей рядом."
        },
        primary = "Пригласить друга" to onOpenReferrals,
        secondary = "Проверить снова" to onRefresh,
        offerWaitlist = true,
    )
    "no_one_yet" -> DeckCopy(
        title = "Пока здесь никого",
        message = "Сейчас в BeFoS нет ни одной анкеты, которую можно показать вам, — это не " +
            "ошибка. Пригласите человека, которому доверяете, или отметьтесь в листе ожидания, " +
            "чтобы мы видели, где людей ждут.",
        primary = "Пригласить друга" to onOpenReferrals,
        secondary = "Проверить снова" to onRefresh,
        offerWaitlist = true,
    )
    "exhausted" -> DeckCopy(
        title = "Анкеты на сейчас закончились",
        message = "На этот момент новых карточек нет. Люди появляются, когда регистрируются, " +
            "поэтому стоит заглянуть позже." + if (canWidenFilters) {
            " В других городах подбор ещё не пуст — город поиска можно расширить."
        } else {
            ""
        },
        primary = "Проверить снова" to onRefresh,
        secondary = "Пригласить друга" to onOpenReferrals,
        tertiary = if (canWidenFilters) "Изменить город поиска" to onOpenFilters else null,
    )
    else -> if (reviewedThisVisit) {
        // A client fact, not a server reason: every card this session received was answered, and
        // the last page said there was no more. It does not claim the world is empty — only this
        // visit's deck — so «проверить снова» stays the honest first door.
        DeckCopy(
            title = "Вы посмотрели все анкеты",
            message = "Это все карточки, которые пришли в подбор в этот раз. Новые люди появятся, " +
                "когда зарегистрируются, — можно проверить снова или позвать друга.",
            primary = "Проверить снова" to onRefresh,
            secondary = "Пригласить друга" to onOpenReferrals,
        )
    } else {
        DeckCopy(
            title = "Анкеты закончились",
            message = "Сейчас новых анкет нет — это не ошибка. Загляните чуть позже или пригласите " +
                "человека, которому доверяете.",
            primary = "Обновить подбор" to onRefresh,
            secondary = "Пригласить друга" to onOpenReferrals,
        )
    }
}
