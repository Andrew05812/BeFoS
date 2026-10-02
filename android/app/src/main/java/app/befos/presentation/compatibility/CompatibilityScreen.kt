package app.befos.presentation.compatibility

import androidx.compose.animation.core.animateIntAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import app.befos.core.designsystem.ScoreRing
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Explanation
import app.befos.presentation.common.CategoryScoreList

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun CompatibilityScreen(matchId: String, onBack: () -> Unit) {
    val vm: CompatibilityViewModel = beFosViewModel { CompatibilityViewModel(it.matchRepository, matchId) }
    val state by vm.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Совместимость", fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад") }
                },
            )
        },
    ) { padding ->
        when {
            state.loading -> LoadingBox(Modifier.padding(padding))
            state.data == null -> MessagePane(
                text = state.error ?: "Ошибка",
                title = "Не удалось рассчитать",
                actionLabel = "Повторить",
                onAction = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> {
                val data = state.data!!
                val animatedScore by animateIntAsState(targetValue = data.overall, label = "score")
                Column(
                    modifier = Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(20.dp),
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        ScoreRing(percent = data.overall, size = 132.dp, label = "$animatedScore%")
                        Text(
                            verdictFor(data.overall),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = scoreColor(data.overall),
                        )
                    }

                    Section("По категориям")
                    CategoryScoreList(data.categories)

                    if (data.strengths.isNotEmpty()) {
                        Section("Почему вы подходите")
                        ExplanationList(data.strengths, positive = true)
                    }
                    if (data.differences.isNotEmpty()) {
                        Section("Что может отличаться")
                        ExplanationList(data.differences, positive = false)
                    }
                    if (data.sharedInterests.isNotEmpty()) {
                        Section("Общие интересы")
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            data.sharedInterests.forEach { slug ->
                                AssistChip(onClick = {}, label = { Text(prettifySlug(slug)) })
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Section(title: String) {
    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
}

@Composable
private fun ExplanationList(items: List<Explanation>, positive: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items.forEach { item ->
            Column {
                Text(item.label, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                Text(
                    item.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

internal fun prettifySlug(slug: String): String =
    slug.replace('_', ' ').replace('-', ' ').replaceFirstChar { it.uppercase() }

/** Human verdict for the overall compatibility percentage. */
internal fun verdictFor(overall: Int): String = when {
    overall >= 85 -> "Вы очень хорошо подходите"
    overall >= 70 -> "Вы хорошо подходите"
    overall >= 55 -> "Есть перспектива"
    overall >= 40 -> "Стоит узнать друг друга"
    else -> "Вы довольно разные"
}
