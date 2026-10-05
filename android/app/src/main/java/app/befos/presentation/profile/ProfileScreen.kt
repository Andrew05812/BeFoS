package app.befos.presentation.profile

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.Avatar
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.ProfileSkeleton
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.goalLabel

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProfileScreen(
    onEdit: () -> Unit,
    onSettings: () -> Unit,
    onTest: () -> Unit,
    onLoggedOut: () -> Unit,
) {
    val vm: ProfileViewModel = beFosViewModel {
        ProfileViewModel(it.profileRepository, it.testRepository, it.authRepository)
    }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.loggedOut) { if (state.loggedOut) onLoggedOut() }

    LifecycleResumeEffect(Unit) {
        vm.refreshSilently()
        onPauseOrDispose { }
    }

    when {
        state.loading -> ProfileSkeleton()
        state.profile == null -> ErrorState(
            message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
            title = "Не удалось загрузить профиль",
            onRetry = vm::load,
        )
        else -> {
            val profile = state.profile!!
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(start = Spacing.gutter, top = Spacing.xl, end = Spacing.gutter, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
            ) {
                state.refreshError?.let {
                    InlineNotice(it, actionLabel = "Повторить", onAction = vm::refreshSilently)
                }
                ProfileHero(profile.primaryPhoto, "${profile.name}, ${profile.age}", profile.city, goalLabel(profile.datingGoal))

                if (!profile.about.isNullOrBlank()) {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        SectionHeader("О себе")
                        Text(profile.about, style = MaterialTheme.typography.bodyLarge)
                    }
                }

                TestProgressCard(
                    percent = state.testProgress?.percent ?: 0,
                    completed = state.testProgress?.completed ?: false,
                    failed = state.testProgress == null && state.testProgressFailed,
                    onTest = onTest,
                )

                if (profile.interests.isNotEmpty()) {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        SectionHeader("Интересы")
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                        ) {
                            profile.interests.forEach { interest ->
                                InterestChip(label = interest.name)
                            }
                        }
                    }
                }

                // Full width: side by side "Редактировать" broke mid-word on a 320dp
                // screen, and the two actions are not a pair the user compares.
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    AppButton(
                        text = "Редактировать анкету",
                        onClick = onEdit,
                        leadingIcon = Icons.Filled.Edit,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    AppButton(
                        text = "Настройки",
                        onClick = onSettings,
                        variant = AppButtonVariant.Tonal,
                        leadingIcon = Icons.Outlined.Settings,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

/** Branded identity panel: photo/initial on a warm gradient, name front and center. */
@Composable
private fun ProfileHero(photoUrl: String?, title: String, city: String, goal: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .background(Brush.verticalGradient(listOf(IrisSoft, MaterialTheme.colorScheme.surface)))
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, MaterialTheme.shapes.large),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.xxl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Text(
                "МОЙ ПРОФИЛЬ",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
            ) {
                Avatar(photoUrl, size = 76.dp, initials = title, contentDescription = title)
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(city, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    // The hero panel fades from iris-soft, which is lighter than paper, so
                    // the fill ember here would read below 4.5:1 at labelLarge.
                    Text(goal, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
                }
            }
        }
    }
}

@Composable
private fun TestProgressCard(percent: Int, completed: Boolean, failed: Boolean, onTest: () -> Unit) {
    var visible by remember { androidx.compose.runtime.mutableStateOf(false) }
    LaunchedEffect(Unit) { visible = true }
    val fill by animateFloatAsState(
        targetValue = if (visible && !failed) percent / 100f else 0f,
        animationSpec = tween(Motion.Slow, easing = androidx.compose.animation.core.FastOutSlowInEasing),
        label = "testProgressFill",
    )
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text("ТЕСТ СОВМЕСТИМОСТИ", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        when {
                            failed -> "Прогресс теста не загрузился"
                            completed -> "Тест пройден"
                            else -> "Тест не пройден"
                        },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                // The bare number used to sit under "Профиль совместимости" and read as a
                // compatibility score of 100%. It is answer coverage — so it says so.
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        if (failed) "—" else "$percent%",
                        style = MaterialTheme.typography.headlineSmall.tabularDigits(),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        "отвечено",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(10.dp)
                    .clip(RoundedCornerShape(5.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(fill)
                        .height(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(EmberGradient),
                )
            }
            Text(
                when {
                    failed -> "Данные теста не загрузились — попробуйте обновить."
                    completed -> "Вы можете пройти тест заново, чтобы уточнить ответы."
                    else -> "Пройдите тест — без него совместимость считается неточно."
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            AppButton(
                text = if (completed) "Пройти заново" else "Пройти тест",
                onClick = onTest,
                variant = if (completed) AppButtonVariant.Tonal else AppButtonVariant.Filled,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
