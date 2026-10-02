package app.befos.presentation.publicprofile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.ProfileCard
import app.befos.core.designsystem.SectionHeader
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.CategoryScoreList
import app.befos.presentation.common.goalLabel
import app.befos.presentation.compatibility.prettifySlug
import coil.compose.AsyncImage

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
            AlertDialog(
                onDismissRequest = vm::dismissMatch,
                title = { Text("Это взаимно!") },
                text = {
                    Text(
                        if (outcome.compatibility != null) "Ваша совместимость ${outcome.compatibility}%. Откройте чат, чтобы начать общение."
                        else "Откройте чат, чтобы начать общение.",
                    )
                },
                confirmButton = {
                    TextButton(onClick = {
                        vm.dismissMatch()
                        onOpenChat(matchId)
                    }) { Text("Открыть чат") }
                },
                dismissButton = { TextButton(onClick = vm::dismissMatch) { Text("Позже") } },
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
                    modifier = Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    PhotoPager(p.photoUrls)

                    ProfileCard(
                        name = p.name,
                        age = p.age,
                        city = p.city,
                        goal = goalLabel(p.datingGoal),
                        compatibility = p.compatibility,
                    )

                    if (!p.about.isNullOrBlank()) {
                        Text(p.about, style = MaterialTheme.typography.bodyLarge)
                    }

                    if (p.categories.isNotEmpty()) {
                        SectionHeader("Совместимость по категориям")
                        CategoryScoreList(p.categories)
                    }

                    if (p.sharedInterests.isNotEmpty()) {
                        SectionHeader("Общие интересы")
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            p.sharedInterests.forEach { slug -> InterestChip(label = prettifySlug(slug)) }
                        }
                    }

                    if (p.interests.isNotEmpty()) {
                        SectionHeader("Интересы")
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            p.interests.forEach { name -> InterestChip(label = name) }
                        }
                    }

                    if (state.notice != null) {
                        Text(state.notice!!, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                        AppButton(
                            text = "Пропустить",
                            onClick = vm::pass,
                            enabled = !state.busy,
                            secondary = true,
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

@Composable
private fun PhotoPager(photos: List<String>) {
    val visible = photos.filter { it.isNotBlank() }
    if (visible.isEmpty()) {
        Box(
            Modifier.fillMaxWidth().height(320.dp)
                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(20.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text("Нет фото", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        return
    }
    val pagerState = rememberPagerState(pageCount = { visible.size })
    HorizontalPager(state = pagerState, modifier = Modifier.fillMaxWidth().height(420.dp)) { page ->
        AsyncImage(
            model = visible[page],
            contentDescription = "Фото ${page + 1} анкет ${visible.size}",
            modifier = Modifier.fillMaxSize().clip(RoundedCornerShape(20.dp)),
            contentScale = ContentScale.Crop,
        )
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
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
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
