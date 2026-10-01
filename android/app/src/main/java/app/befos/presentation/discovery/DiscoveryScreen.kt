package app.befos.presentation.discovery

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import coil.compose.AsyncImage
import app.befos.core.designsystem.AsyncAvatar
import app.befos.core.designsystem.LoadingBox
import app.befos.core.designsystem.MessagePane
import app.befos.core.designsystem.ScoreRing
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.DiscoveryCard
import app.befos.presentation.common.goalLabel
import kotlin.math.roundToInt

@Composable
fun DiscoveryScreen(onOpenMatch: (String) -> Unit, onOpenProfile: (String) -> Unit) {
    val vm: DiscoveryViewModel = beFosViewModel { DiscoveryViewModel(it.discoveryRepository) }
    val state by vm.uiState.collectAsState()

    state.match?.let { outcome ->
        outcome.matchId?.let { matchId ->
            MatchDialog(compatibility = outcome.compatibility, onOpen = {
                vm.dismissMatch()
                onOpenMatch(matchId)
            }, onDismiss = vm::dismissMatch)
        }
    }

    when {
        state.loading -> LoadingBox()
        state.error != null && state.cards.isEmpty() -> MessagePane(
            text = state.error ?: "Ошибка",
            title = "Не удалось загрузить анкеты",
            actionLabel = "Повторить",
            onAction = vm::load,
        )
        state.isEmpty || state.current == null -> MessagePane(
            text = "Новые анкеты закончились. Загляните позже — или расширите параметры поиска в профиле.",
            title = "Пока никого нет",
            actionLabel = "Обновить",
            onAction = vm::load,
        )
        else -> DiscoveryContent(state, vm, onOpenProfile)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DiscoveryContent(state: DiscoveryUiState, vm: DiscoveryViewModel, onOpenProfile: (String) -> Unit) {
    val card = state.current ?: return
    var dragX by remember(card.userId) { mutableFloatStateOf(0f) }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .offset { IntOffset(dragX.roundToInt(), 0) }
                .graphicsLayer { rotationZ = dragX / 40f }
                .clickable { onOpenProfile(card.userId) }
                .pointerInput(card.userId) {
                    detectHorizontalDragGestures(
                        onDragEnd = {
                            when {
                                dragX > 300f -> { dragX = 0f; vm.like() }
                                dragX < -300f -> { dragX = 0f; vm.pass() }
                                else -> dragX = 0f
                            }
                        },
                        onDragCancel = { dragX = 0f },
                    ) { change, amount ->
                        change.consume()
                        dragX += amount
                    }
                },
        ) {
            ProfileCard(card)
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FloatingActionButton(
                onClick = vm::pass,
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
                contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
            ) { Icon(Icons.Filled.Close, contentDescription = "Пропустить") }
            FloatingActionButton(
                onClick = vm::like,
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
            ) { Icon(Icons.Filled.Favorite, contentDescription = "Нравится") }
        }
        if (state.error != null) {
            Text(state.error!!, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileCard(card: DiscoveryCard) {
    Card(
        modifier = Modifier.fillMaxSize(),
        shape = RoundedCornerShape(28.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Box(Modifier.fillMaxSize()) {
            if (!card.photoUrl.isNullOrBlank()) {
                AsyncImage(
                    model = card.photoUrl,
                    contentDescription = card.name,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop,
                )
            } else {
                Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceVariant))
            }

            Box(
                Modifier.fillMaxWidth().align(Alignment.TopEnd).padding(16.dp),
            ) {
                ScoreRing(percent = card.compatibility, size = 72.dp, strokeWidth = 6.dp)
            }

            Column(
                modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth()
                    .background(
                        brush = androidx.compose.ui.graphics.Brush.verticalGradient(
                            listOf(androidx.compose.ui.graphics.Color.Transparent, androidx.compose.ui.graphics.Color(0xCC000000)),
                        ),
                    )
                    .padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    "${card.name}, ${card.age}",
                    color = androidx.compose.ui.graphics.Color.White,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "${card.city} · ${goalLabel(card.datingGoal)}",
                    color = androidx.compose.ui.graphics.Color(0xDDFFFFFF),
                    style = MaterialTheme.typography.bodyMedium,
                )
                if (card.sharedInterestsCount > 0) {
                    Text(
                        "${card.sharedInterestsCount} общих интересов",
                        color = scoreColor(card.compatibility),
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                if (card.interests.isNotEmpty()) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        card.interests.take(5).forEach { name ->
                            AssistChip(
                                onClick = {},
                                label = { Text(name, style = MaterialTheme.typography.labelSmall) },
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MatchDialog(compatibility: Int?, onOpen: () -> Unit, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(28.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Text("Это взаимно!", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                if (compatibility != null) {
                    ScoreRing(percent = compatibility, size = 120.dp)
                    Text(
                        "Ваша совместимость $compatibility%",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Button(onClick = onOpen, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                    Text("Открыть чат", fontWeight = FontWeight.SemiBold)
                }
                Button(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    colors = androidx.compose.material3.ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                        contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    ),
                ) { Text("Продолжить просмотр") }
            }
        }
    }
}
