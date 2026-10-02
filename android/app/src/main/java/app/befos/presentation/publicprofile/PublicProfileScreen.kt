package app.befos.presentation.publicprofile

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Block
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.CompatibilityScore
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.SuccessGreen
import app.befos.core.designsystem.glassSurface
import app.befos.core.designsystem.photoScrim
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.PublicProfile
import app.befos.presentation.common.CategoryScoreList
import app.befos.presentation.common.goalLabel
import app.befos.presentation.compatibility.prettifySlug
import coil.compose.AsyncImage
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PublicProfileScreen(
    userId: String,
    onBack: () -> Unit,
    onOpenChat: (String) -> Unit,
) {
    val vm: PublicProfileViewModel = beFosViewModel {
        PublicProfileViewModel(it.profileRepository, it.discoveryRepository, it.safetyRepository, userId)
    }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.gone) { if (state.gone && state.match == null) onBack() }

    state.match?.let { outcome ->
        outcome.matchId?.let { matchId ->
            MutualMatchEvent(
                name = state.profile?.name,
                compatibility = outcome.compatibility,
                onOpenChat = {
                    vm.dismissMatch()
                    onOpenChat(matchId)
                },
                onDismiss = vm::dismissMatch,
            )
        }
    }

    if (state.reportDialog) {
        ReportDialog(
            reason = state.reportReason,
            details = state.reportDetails,
            onReason = vm::onReportReason,
            onDetails = vm::onReportDetails,
            onSubmit = vm::submitReport,
            onDismiss = vm::closeReport,
        )
    }

    Scaffold(
        topBar = {
            AppTopBar(
                title = "Анкета",
                onBack = onBack,
                actions = {
                    IconButton(onClick = vm::openReport) { Icon(Icons.Filled.Flag, contentDescription = "Пожаловаться") }
                    IconButton(onClick = vm::block) { Icon(Icons.Filled.Block, contentDescription = "Заблокировать") }
                },
            )
        },
    ) { padding ->
        when {
            state.loading -> LoadingState(Modifier.padding(padding))
            state.profile == null -> ErrorState(
                message = state.error ?: "Ошибка",
                title = "Профиль недоступен",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> {
                val p = state.profile!!
                Column(
                    modifier = Modifier
                        .padding(padding)
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
                ) {
                    ProfileHero(p)

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = Spacing.gutter),
                        verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
                    ) {
                        if (!p.about.isNullOrBlank()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader("О себе")
                                Text(p.about, style = MaterialTheme.typography.bodyLarge)
                            }
                        }

                        if (p.categories.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader("Совместимость по категориям")
                                AppCard(modifier = Modifier.fillMaxWidth()) {
                                    CategoryScoreList(p.categories)
                                }
                            }
                        }

                        if (p.sharedInterests.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader("Общие интересы")
                                FlowRow(
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                                ) {
                                    p.sharedInterests.forEach { slug -> InterestChip(label = prettifySlug(slug)) }
                                }
                            }
                        }

                        if (p.interests.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader("Интересы")
                                FlowRow(
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                                ) {
                                    p.interests.forEach { name -> InterestChip(label = name) }
                                }
                            }
                        }

                        state.notice?.let { notice ->
                            Text(
                                notice,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth().padding(bottom = Spacing.xxl),
                            horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
                        ) {
                            AppButton(
                                text = "Пропустить",
                                onClick = vm::pass,
                                enabled = !state.busy,
                                variant = AppButtonVariant.Tonal,
                                modifier = Modifier.weight(1f),
                            )
                            AppButton(
                                text = "Нравится",
                                onClick = vm::like,
                                enabled = !state.busy,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            }
        }
    }
}

/** Hero photo pager with identity composed over the scrim; branded fallback without photos. */
@Composable
private fun ProfileHero(p: PublicProfile) {
    val shape = MaterialTheme.shapes.extraLarge
    val photos = p.photoUrls.filter { it.isNotBlank() }
    val pagerState = rememberPagerState(pageCount = { photos.size })
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.gutter)
            .aspectRatio(0.82f)
            .clip(shape),
    ) {
        if (photos.isNotEmpty()) {
            HorizontalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { page ->
                HeroPhoto(photos[page], "Фото ${page + 1} из ${photos.size}", p.name)
            }
        } else {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Brush.linearGradient(listOf(IrisTint, EmberTint, Peach))),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    p.name.trim().firstOrNull()?.uppercase().toString(),
                    style = MaterialTheme.typography.displayLarge,
                    color = Color.White.copy(alpha = 0.9f),
                )
            }
        }

        // Identity block over the scrim.
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .background(photoScrim())
                .padding(start = Spacing.xl, end = Spacing.xl, top = Spacing.huge, bottom = if (photos.size > 1) Spacing.huge else Spacing.xxl),
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    p.name,
                    color = Color.White,
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                    maxLines = 2,
                )
                Text(", ${p.age}", color = Color.White.copy(alpha = 0.7f), style = MaterialTheme.typography.displaySmall)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                Box(Modifier.size(7.dp).clip(CircleShape).background(SuccessGreen))
                Text(
                    "${p.city} · ${goalLabel(p.datingGoal)}",
                    color = Color.White.copy(alpha = 0.85f),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }

        // Compatibility on frosted glass, top-right.
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(Spacing.lg)
                .glassSurface(CircleShape),
        ) {
            CompatibilityScore(percent = p.compatibility, size = 66.dp, strokeWidth = 6.dp)
        }

        // Page dots.
        if (photos.size > 1) {
            Row(
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = Spacing.lg),
                horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                repeat(photos.size) { i ->
                    Box(
                        Modifier
                            .size(if (pagerState.currentPage == i) 8.dp else 6.dp)
                            .clip(CircleShape)
                            .background(Color.White.copy(alpha = if (pagerState.currentPage == i) 1f else 0.4f)),
                    )
                }
            }
        }

        Box(Modifier.fillMaxSize().border(Elev.hairlineWidth, Color.White.copy(alpha = 0.14f), shape))
    }
}

/** Single hero photo page; falls back to the branded gradient when the image can't load. */
@Composable
private fun HeroPhoto(url: String, description: String, name: String) {
    var failed by remember(url) { mutableStateOf(false) }
    if (!failed) {
        AsyncImage(
            model = url,
            contentDescription = description,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
            onError = { failed = true },
        )
    } else {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Brush.linearGradient(listOf(IrisTint, EmberTint, Peach))),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                name.trim().firstOrNull()?.uppercase().toString(),
                style = MaterialTheme.typography.displayLarge,
                color = Color.White.copy(alpha = 0.9f),
            )
        }
    }
}

/** Mutual-like moment — same event treatment as discovery, no confetti. */
@Composable
private fun MutualMatchEvent(name: String?, compatibility: Int?, onOpenChat: () -> Unit, onDismiss: () -> Unit) {
    val scale = remember { Animatable(0.86f) }
    val fade = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        launch { scale.animateTo(1f, spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow)) }
        launch { fade.animateTo(1f, tween(Motion.Base)) }
    }
    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .graphicsLayer {
                    scaleX = scale.value
                    scaleY = scale.value
                    alpha = fade.value
                }
                .clip(MaterialTheme.shapes.extraLarge)
                .background(Brush.verticalGradient(listOf(Color(0xFF241B2E), Color(0xFF171222))))
                .border(1.dp, Color.White.copy(alpha = 0.10f), MaterialTheme.shapes.extraLarge)
                .padding(Spacing.huge),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            Text(
                "ВЗАИМНЫЙ ЛАЙК",
                style = MaterialTheme.typography.labelSmall,
                color = Color.White.copy(alpha = 0.6f),
            )
            Text(
                if (name != null) "Это взаимно — вы и $name" else "Это взаимно!",
                style = MaterialTheme.typography.headlineMedium,
                color = Color.White,
            )
            if (compatibility != null) {
                CompatibilityScore(percent = compatibility, size = 120.dp, strokeWidth = 10.dp)
                Text(
                    "Ваша совместимость $compatibility%",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color.White.copy(alpha = 0.72f),
                )
            }
            AppButton(
                text = if (name != null) "Написать $name" else "Открыть чат",
                onClick = onOpenChat,
                modifier = Modifier.fillMaxWidth(),
            )
            AppButton(
                text = "Позже",
                onClick = onDismiss,
                variant = AppButtonVariant.Ghost,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ReportDialog(
    reason: String,
    details: String,
    onReason: (String) -> Unit,
    onDetails: (String) -> Unit,
    onSubmit: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Пожаловаться") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                AppTextField(reason, onReason, label = "Причина", modifier = Modifier.fillMaxWidth())
                AppTextField(
                    details,
                    onDetails,
                    label = "Подробности (необязательно)",
                    singleLine = false,
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { TextButton(onClick = onSubmit) { Text("Отправить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
    )
}

private val EmberTint: Color get() = Color(0xFFF0544F)
private val IrisTint: Color get() = Color(0xFF6C4CF1)
