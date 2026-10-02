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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.CompatibilityScore
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Explanation
import app.befos.presentation.common.CategoryScoreList

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CompatibilityScreen(matchId: String, onBack: () -> Unit) {
    val vm: CompatibilityViewModel = beFosViewModel { CompatibilityViewModel(it.matchRepository, matchId) }
    val state by vm.uiState.collectAsState()

    Scaffold(
        topBar = { AppTopBar(title = "Совместимость", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> LoadingState(Modifier.padding(padding))
            state.data == null -> ErrorState(
                message = state.error ?: "Ошибка",
                title = "Не удалось рассчитать",
                onRetry = vm::load,
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
                        CompatibilityScore(percent = data.overall, size = 132.dp, label = "$animatedScore%")
                        Text(
                            verdictFor(data.overall),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = scoreColor(data.overall),
                        )
                    }

                    SectionHeader("По категориям")
                    CategoryScoreList(data.categories)

                    if (data.strengths.isNotEmpty()) {
                        SectionHeader("Почему вы подходите")
                        ExplanationList(data.strengths, positive = true)
                    }
                    if (data.differences.isNotEmpty()) {
                        SectionHeader("Что может отличаться")
                        ExplanationList(data.differences, positive = false)
                    }
                    if (data.sharedInterests.isNotEmpty()) {
                        SectionHeader("Общие интересы")
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            data.sharedInterests.forEach { slug ->
                                InterestChip(label = prettifySlug(slug))
                            }
                        }
                    }
                }
            }
        }
    }
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
