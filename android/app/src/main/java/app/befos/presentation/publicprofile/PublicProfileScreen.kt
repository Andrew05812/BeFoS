package app.befos.presentation.publicprofile

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.GlassScoreBadge
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.PublicProfileSkeleton
import app.befos.core.designsystem.MatchMoment
import app.befos.core.designsystem.MonogramFallback
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.RemotePhoto
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.SuccessGreen
import app.befos.core.designsystem.photoScrim
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.PublicProfile
import app.befos.presentation.common.CategoryScoreList
import app.befos.presentation.common.ReportReasonLabels
import app.befos.presentation.common.goalLabel
import app.befos.presentation.compatibility.prettifySlug

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
    val haptics = rememberHaptics()

    LaunchedEffect(state.gone) { if (state.gone && state.match == null) onBack() }

    state.match?.let { outcome ->
        outcome.matchId?.let { matchId ->
            MatchMoment(
                name = state.profile?.name,
                photoUrl = state.profile?.photoUrls?.firstOrNull(),
                compatibility = outcome.compatibility,
                onOpenChat = {
                    vm.openChat()
                    onOpenChat(matchId)
                },
                onDismiss = vm::dismissMatch,
                secondaryLabel = "Позже",
            )
        }
    }

    if (state.reportDialog) {
        ReportDialog(
            reason = state.reportReason,
            details = state.reportDetails,
            error = state.reportError,
            sending = state.busy,
            onReason = vm::setReportReason,
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
            state.loading -> PublicProfileSkeleton(Modifier.padding(padding))
            state.profile == null -> ErrorState(
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
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
                        // Reading order follows the product's own logic: why you fit,
                        // what you share, then the person's words.
                        if (p.categories.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader("Совместимость по категориям")
                                AppCard(modifier = Modifier.fillMaxWidth()) {
                                    Column(modifier = Modifier.padding(Spacing.xl)) {
                                        CategoryScoreList(p.categories)
                                    }
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
                                    // Same ember accent the Discovery card puts on the
                                    // shared-interests pill: what connects the pair is not
                                    // just another item in her list.
                                    p.sharedInterests.forEach { slug ->
                                        InterestChip(
                                            label = prettifySlug(slug),
                                            containerColor = MaterialTheme.colorScheme.primaryContainer,
                                            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
                                        )
                                    }
                                }
                            }
                        }

                        // The shared ones already had their moment above; repeating them
                        // under a second heading reads as a bug, not as a fuller picture.
                        val rest = p.interests.filter { name ->
                            p.sharedInterests.none { prettifySlug(it).equals(name, ignoreCase = true) }
                        }
                        if (rest.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader(if (p.sharedInterests.isNotEmpty()) "Другие интересы" else "Интересы")
                                FlowRow(
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                                ) {
                                    rest.forEach { name -> InterestChip(label = name) }
                                }
                            }
                        }

                        if (!p.about.isNullOrBlank()) {
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                                SectionHeader("О себе")
                                Text(p.about, style = MaterialTheme.typography.bodyLarge)
                            }
                        }

                        state.error?.let { message ->
                            InlineNotice(message)
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth().padding(bottom = Spacing.xxl),
                            horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
                        ) {
                            AppButton(
                                text = "Пропустить",
                                onClick = {
                                    haptics.medium()
                                    vm.pass()
                                },
                                enabled = !state.busy,
                                variant = AppButtonVariant.Tonal,
                                modifier = Modifier.weight(1f),
                            )
                            AppButton(
                                text = "Нравится",
                                onClick = {
                                    haptics.medium()
                                    vm.like()
                                },
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
            MonogramFallback(
                name = p.name,
                modifier = Modifier.fillMaxSize(),
                badgeSize = 96.dp,
                contentPadding = PaddingValues(start = Spacing.lg, top = Spacing.lg, end = Spacing.lg, bottom = 132.dp),
            )
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

        // Compatibility on frosted glass, top-right: the number plus what it claims.
        GlassScoreBadge(
            percent = p.compatibility,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(Spacing.lg),
        )

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

/** Single hero photo page; the branded gradient underneath is both loader and fallback. */
@Composable
private fun HeroPhoto(url: String, description: String, name: String) {
    var failed by remember(url) { mutableStateOf(false) }
    // The pager page is not a Box: without an explicit container the photo and its
    // fallback become two stacked-less siblings and the image never gets drawn.
    Box(modifier = Modifier.fillMaxSize()) {
        MonogramFallback(
            name = name,
            modifier = Modifier.fillMaxSize(),
            badgeSize = 84.dp,
            contentPadding = PaddingValues(bottom = 96.dp),
        )
        if (!failed) {
            RemotePhoto(
                url = url,
                contentDescription = description,
                modifier = Modifier.fillMaxSize(),
                onError = { failed = true },
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ReportDialog(
    reason: String,
    details: String,
    error: String?,
    sending: Boolean,
    onReason: (String) -> Unit,
    onDetails: (String) -> Unit,
    onSubmit: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Пожаловаться") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.md),
            ) {
                Text(
                    "Что не так с анкетой?",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    ReportReasonLabels.forEach { (slug, label) ->
                        InterestChip(
                            label = label,
                            selected = reason == slug,
                            onClick = { onReason(slug) },
                        )
                    }
                }
                AppTextField(
                    value = details,
                    onValueChange = onDetails,
                    label = "Подробности (необязательно)",
                    error = error,
                    singleLine = false,
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onSubmit, enabled = !sending) {
                Text(if (sending) "Отправляем…" else "Отправить")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !sending) { Text("Отмена") } },
    )
}

private val EmberTint: Color get() = Color(0xFFF0544F)
private val IrisTint: Color get() = Color(0xFF6C4CF1)
