package app.befos.presentation.recommendations

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.LoadingBox
import app.befos.core.designsystem.MessagePane
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Recommendation

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecommendationsScreen(matchId: String, onBack: () -> Unit) {
    val vm: RecommendationsViewModel = beFosViewModel { RecommendationsViewModel(it.matchRepository, matchId) }
    val state by vm.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Идеи для встречи", fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад") }
                },
            )
        },
    ) { padding ->
        when {
            state.loading -> LoadingBox(Modifier.padding(padding))
            state.items.isEmpty() -> MessagePane(
                text = state.error ?: "Пока нет идей для этой пары.",
                title = "Нет рекомендаций",
                actionLabel = "Обновить",
                onAction = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> LazyColumn(
                modifier = Modifier.padding(padding).fillMaxSize().padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 16.dp),
            ) {
                items(state.items, key = { it.activity.id }) { rec ->
                    RecommendationCard(
                        rec = rec,
                        selected = state.selected.contains(rec.activity.id),
                        onSelect = { vm.select(rec.activity.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun RecommendationCard(rec: Recommendation, selected: Boolean, onSelect: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(rec.activity.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(
                    "${rec.score}",
                    color = scoreColor(rec.score),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
            }
            if (!rec.activity.description.isNullOrBlank()) {
                Text(rec.activity.description, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (rec.reasons.isNotEmpty()) {
                Text("Почему подойдёт:", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
                rec.reasons.forEach { reason ->
                    Text("• $reason", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (selected) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Text("Выбрано", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
                }
            } else {
                OutlinedButton(onClick = onSelect, modifier = Modifier.fillMaxWidth()) {
                    Text("Предложить это")
                }
            }
        }
    }
}
