package app.befos.presentation.universe

import android.provider.Settings
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.CompatibilityBadge
import app.befos.core.designsystem.CompatibilityScore
import app.befos.core.designsystem.CompatibilitySkeleton
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.core.share.shareText
import app.befos.domain.model.Connection
import app.befos.domain.model.Universe
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode

@Composable
fun UniverseScreen(matchId: String, onBack: () -> Unit) {
    val vm: UniverseViewModel = beFosViewModel {
        UniverseViewModel(it.matchRepository, it.profileRepository, matchId)
    }
    val state by vm.uiState.collectAsState()
    val context = LocalContext.current

    Scaffold(
        topBar = { AppTopBar(title = "Карта пары", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> CompatibilitySkeleton(Modifier.padding(padding))
            state.data == null && state.gone ->
                // A 404 is not a hiccup: the pair is gone, so «Повторить» here is a button that
                // cannot work — the same dead control defect 72-11 removed from the chat screen.
                EmptyState(
                    title = "Карты больше нет",
                    message = state.error ?: "Эта пара больше не существует.",
                    modifier = Modifier.padding(padding),
                    overline = "Пара",
                )
            state.data == null -> ErrorState(
                title = "Карта не загрузилась",
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> UniverseContent(
                state = state,
                modifier = Modifier.padding(padding),
                onSelect = vm::select,
                onFilter = vm::setFilter,
                onMode = vm::setMode,
                onShare = { text -> shareText(context, STORY_TITLE, text) },
            )
        }
    }
}

@Composable
private fun UniverseContent(
    state: UniverseUiState,
    modifier: Modifier,
    onSelect: (String?) -> Unit,
    onFilter: (Connection?) -> Unit,
    onMode: (UniverseMode) -> Unit,
    onShare: (String) -> Unit,
) {
    val universe = state.data
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(Spacing.section),
    ) {
        if (universe == null) return@Column
        if (universe.layers.flatMap { it.nodes }.isEmpty()) {
            EmptyState(
                title = "Строить карту не из чего",
                message = "Ни в одной из семи областей не нашлось ответа, который можно " +
                    "сравнить. Заполните анкету и пройдите тест — карта появится.",
                overline = "Пусто",
            )
            return@Column
        }

        UniverseModeSwitcher(mode = state.mode, onMode = onMode)

        // One document, three readings: switching never refetches and never recomputes, because all
        // three branches below read the same `universe` the map was drawn from.
        when (state.mode) {
            UniverseMode.Map -> UniverseMapView(state, onSelect, onFilter)
            UniverseMode.Analysis -> UniverseAnalysisView(state, onSelect)
            UniverseMode.Story -> UniverseStoryView(state, onShare)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun UniverseModeSwitcher(mode: UniverseMode, onMode: (UniverseMode) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        SectionHeader(
            title = "Как читать",
            subtitle = "Карта, разбор по полосам и история, которую можно отдать, — три взгляда " +
                "на один и тот же расчёт.",
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            UniverseMode.entries.forEach {
                InterestChip(label = modeWord(it), selected = mode == it, onClick = { onMode(it) })
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun UniverseMapView(
    state: UniverseUiState,
    onSelect: (String?) -> Unit,
    onFilter: (Connection?) -> Unit,
) {
    val universe = state.data ?: return
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.section)) {
        Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                Text(
                    "СОВМЕСТИМОСТЬ ПАРЫ",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                CompatibilityScore(percent = universe.overall, size = 132.dp, strokeWidth = 10.dp)
                Text(
                    "Эту цифру посчитал тот же движок, что и экран совместимости. Ниже не новые " +
                        "проценты, а те ответы, из которых она сложилась.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
            SectionHeader(
                title = "Два мира",
                subtitle = "Нажмите на точку — объяснение появится под картой.",
            )
            AppCard(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(Spacing.lg),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    UniverseMap(state = state, onSelect = onSelect)
                    UniverseLegend()
                    Text(
                        "Процент — итог слоя, «сверено N из M» — покрытие: сколько пунктов слоя " +
                            "действительно сравнили. Это разные числа, и покрытие не входит в процент.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        "Ряд из четырёх черт в раскрытом узле — насколько уверенно ответ сидит в " +
                            "своей полосе: пустой ряд значит «ещё шаг, и это читается другой " +
                            "связью», полный — «иначе этот ответ не читается». Это расстояние до " +
                            "границы полосы, а не вероятность того, как сложатся отношения.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        val selected = state.selected()
        val reducedMotion = rememberReducedMotion()
        // A panel that is animating away has already lost its node, so it keeps showing the node it
        // was opened for until it has finished shrinking.
        var revealed by remember { mutableStateOf(selected) }
        LaunchedEffect(state.selectedKey) { state.selected()?.let { revealed = it } }
        AnimatedVisibility(
            visible = selected != null,
            enter = revealIn(reducedMotion),
            exit = revealOut(reducedMotion),
        ) {
            revealed?.let { selection ->
                // Tapping a second node never closes the panel, so nothing above animates: the
                // content fades in on its own key instead.
                val appear = remember(selection.node.key, reducedMotion) {
                    Animatable(if (reducedMotion) 1f else 0f)
                }
                LaunchedEffect(selection.node.key, reducedMotion) {
                    if (!reducedMotion && appear.value < 1f) appear.animateTo(1f, tween(Motion.Base))
                }
                Column(
                    modifier = Modifier.alpha(appear.value),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    SectionHeader("Выбранный узел")
                    AppCard(modifier = Modifier.fillMaxWidth()) {
                        Column(
                            modifier = Modifier.padding(Spacing.xl),
                            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    selection.node.label,
                                    modifier = Modifier.weight(1f),
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                // The canvas has no back gesture of its own, so the panel a tap
                                // opened has to name the control that closes it.
                                TextButton(onClick = { onSelect(null) }) { Text("Свернуть") }
                            }
                            Text(
                                "${selection.layer.label} · ${connectionWord(selection.node.connection)}",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                sideLine(selection.node, selection.layer, state.aName, state.bName),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                            AssuranceRow(selection.node)
                            Text(
                                selection.node.evidence,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            if (selection.node.suggestion.isNotBlank()) {
                                Text(selection.node.suggestion, style = MaterialTheme.typography.bodyMedium)
                            }
                            if (selection.node.questions.isNotEmpty()) {
                                Text(
                                    "ЧЕМ ЭТО ИЗМЕРЕНО",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                selection.node.questions.forEach { question ->
                                    Text(
                                        question,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            SectionHeader("Показать")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                Connection.entries.forEach { kind ->
                    InterestChip(
                        label = "${connectionWord(kind)} · ${countOf(universe, kind)}",
                        selected = state.filter == kind,
                        onClick = { onFilter(if (state.filter == kind) null else kind) },
                    )
                }
            }
            if (state.filter != null) {
                InterestChip(label = "Сбросить фильтр", selected = false, onClick = { onFilter(null) })
            }
        }

        shownSections(state.filter).forEach { kind ->
            val groups = universe.layers.mapNotNull { layer ->
                val items = layer.nodes.filter { it.connection == kind }
                if (items.isEmpty()) null else layer to items
            }
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader(title = sectionTitle(kind), subtitle = sectionHint(kind))
                if (groups.isEmpty()) {
                    Text(
                        "Таких узлов в этой паре нет.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    AppCard(modifier = Modifier.fillMaxWidth()) {
                        Column(
                            modifier = Modifier.padding(Spacing.xl),
                            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
                        ) {
                            groups.forEach { (layer, items) ->
                                Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                                    Text(
                                        bandCaption(layer),
                                        style = MaterialTheme.typography.labelMedium,
                                        fontWeight = FontWeight.SemiBold,
                                    )
                                    items.forEach { node ->
                                        NodeRow(
                                            node = node,
                                            layer = layer,
                                            state = state,
                                            expanded = state.selectedKey == node.key,
                                            onClick = { onSelect(node.key) },
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Text(
            MAP_DISCLAIMER,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Deep Analysis: the same seven bands read one under another, heaviest first, each with every node
 * it owns. No new numbers appear here — the band line is the caption the canvas already prints, and
 * a node opens the same panel the map gives it.
 */
@Composable
private fun UniverseAnalysisView(state: UniverseUiState, onSelect: (String?) -> Unit) {
    val universe = state.data ?: return
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
        SectionHeader(
            title = "По полосам",
            subtitle = "Сверху те области, вес которых больше. Порядок — единственное, что здесь " +
                "считается на клиенте: проценты и покрытие пришли с сервера.",
        )
        AppCard(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(Spacing.xl),
                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
            ) {
                analysisOrder(universe.layers).forEach { layer ->
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                        // A band the engine could not score must not be shown with a badge: an empty
                        // category printing its neutral placeholder is defect 72-1.
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                        ) {
                            Text(
                                bandCaption(layer),
                                modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                            )
                            if (layer.hasData) {
                                CompatibilityBadge(percent = layer.score, compact = true)
                            }
                        }
                        AssuranceRow(
                            confidence = layer.confidence,
                            compared = layer.nodes.any { it.hasData },
                        )
                        layer.nodes.forEach { node ->
                            NodeRow(
                                node = node,
                                layer = layer,
                                state = state,
                                expanded = state.selectedKey == node.key,
                                onClick = { onSelect(node.key) },
                            )
                        }
                    }
                }
            }
        }
        Text(
            MAP_DISCLAIMER,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Our Story: the reading built to leave the phone. The sentences come from the engine, aggregates
 * only, so the client adds no number and no name of its own before handing them to another app.
 */
@Composable
private fun UniverseStoryView(state: UniverseUiState, onShare: (String) -> Unit) {
    val universe = state.data ?: return
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
        SectionHeader(
            title = "Наша история",
            subtitle = "В этом тексте только итоги полос: ни одного ответа отдельно взятого " +
                "человека, поэтому его не жалко отдать кому угодно.",
        )
        AppCard(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(Spacing.xl),
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                if (universe.story.isEmpty()) {
                    // An older server answers the map without a story. The share would then send an
                    // empty artefact, so the control says what is missing instead of opening a sheet.
                    Text(
                        "Карта есть, а слов к ней нет: этот ответ сервера историю ещё не приносит.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    universe.story.forEach { line ->
                        Text(line, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                AppButton(
                    text = "Поделиться",
                    onClick = { onShare(storyShareText(universe.story)) },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = universe.story.isNotEmpty(),
                )
            }
        }
        Text(
            MAP_DISCLAIMER,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

internal fun modeWord(mode: UniverseMode): String = when (mode) {
    UniverseMode.Map -> "Два мира"
    UniverseMode.Analysis -> "По полосам"
    UniverseMode.Story -> "Наша история"
}

@Composable
private fun UniverseMap(state: UniverseUiState, onSelect: (String?) -> Unit) {
    val universe = state.data ?: return
    val bands = remember(universe) { UniverseLayout.place(universe.layers) }
    val reducedMotion = rememberReducedMotion()
    val appear = remember(reducedMotion) { Animatable(if (reducedMotion) 1f else 0f) }
    LaunchedEffect(bands, reducedMotion) {
        if (!reducedMotion && appear.value < 1f) appear.animateTo(1f, tween(Motion.Slow))
    }
    val height: Dp = UniverseLayout.heightForDp(universe.layers).dp
    val textMeasurer = rememberTextMeasurer()
    val labelStyle = TextStyle(
        fontSize = 11.sp,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurface,
    )
    val nameStyle = TextStyle(
        fontSize = 12.sp,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurface,
    )
    val ink = MaterialTheme.colorScheme.onSurface
    val primary = MaterialTheme.colorScheme.primary
    val worldLine = MaterialTheme.colorScheme.secondary

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .semantics { contentDescription = universeDescription(state) },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(
            modifier = Modifier
                .widthIn(max = 420.dp)
                .height(height)
                .pointerInput(bands, height) {
                    detectTapGestures { offset ->
                        onSelect(
                            UniverseLayout.nodeAt(
                                bands = bands,
                                x = offset.x / size.width,
                                y = offset.y / size.height,
                                aspect = size.width.toFloat() / size.height,
                                toleranceDp = 26f,
                                heightDp = height.value,
                            )?.key,
                        )
                    }
                },
        ) {
            val width = size.width
            val canvasHeight = size.height
            val rx = UniverseLayout.WORLD_RADIUS * width
            val ry = UniverseLayout.WORLD_RADIUS * canvasHeight
            listOf(UniverseLayout.WORLD_A_CENTER_X to state.aName, UniverseLayout.WORLD_B_CENTER_X to state.bName)
                .forEach { (cx, name) ->
                    val topLeft = Offset((cx - UniverseLayout.WORLD_RADIUS) * width, (0.5f - UniverseLayout.WORLD_RADIUS) * canvasHeight)
                    val ovalSize = Size(rx * 2f, ry * 2f)
                    drawOval(
                        color = worldLine.copy(alpha = 0.05f),
                        topLeft = topLeft,
                        size = ovalSize,
                        alpha = appear.value,
                    )
                    drawOval(
                        color = worldLine.copy(alpha = 0.30f),
                        topLeft = topLeft,
                        size = ovalSize,
                        style = Stroke(width = 1.dp.toPx()),
                        alpha = appear.value,
                    )
                }

            drawWorldName(textMeasurer, state.aName ?: "Анкета слева", UniverseLayout.WORLD_A_CENTER_X, nameStyle, width, canvasHeight, appear.value)
            drawWorldName(textMeasurer, state.bName ?: "Анкета справа", UniverseLayout.WORLD_B_CENTER_X, nameStyle, width, canvasHeight, appear.value)

            bands.forEach { band ->
                val selectedPlacement = band.placements.firstOrNull { it.node.key == state.selectedKey }
                if (selectedPlacement != null) {
                    drawRect(
                        color = IrisSoft.copy(alpha = 0.75f),
                        topLeft = Offset(0f, selectedPlacement.y * canvasHeight - 13.dp.toPx()),
                        size = Size(width, 26.dp.toPx()),
                    )
                }
                val caption = textMeasurer.measure(bandCaption(band.layer), labelStyle)
                drawText(
                    textLayoutResult = caption,
                    topLeft = Offset(0f, band.labelY * canvasHeight - caption.size.height / 2f),
                    alpha = appear.value,
                )
                band.placements.forEach { placement ->
                    val selected = placement.node.key == state.selectedKey
                    drawLink(placement, ink, appear.value)
                    placement.marks.forEach { mark ->
                        drawMark(
                            x = mark.x * width,
                            y = mark.y * canvasHeight,
                            radius = if (selected) 7.5.dp.toPx() else 5.5.dp.toPx(),
                            shape = mark.shape,
                            color = if (selected) primary else ink,
                            alpha = appear.value,
                        )
                        if (selected) drawMarkPercent(textMeasurer, mark, labelStyle, appear.value)
                    }
                }
            }
        }
    }
}

@Composable
private fun UniverseLegend() {
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        Connection.entries.forEach { kind ->
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                ShapeKey(UniverseLayout.shapeOf(kind), UniverseLayout.linkOf(kind, true))
                Text(
                    "${connectionWord(kind)} — ${legendHint(kind)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ShapeKey(shape: UniverseLayout.MarkShape, link: UniverseLayout.LinkStyle) {
    val ink = MaterialTheme.colorScheme.onSurface
    Canvas(modifier = Modifier.size(width = 40.dp, height = 14.dp)) {
        drawLinkLine(
            x1 = 0.14f * size.width,
            x2 = 0.86f * size.width,
            y = size.height / 2f,
            link = link,
            color = ink,
            alpha = 1f,
        )
        listOf(0.14f, 0.86f).forEach { x ->
            drawMark(
                x = x * size.width,
                y = size.height / 2f,
                radius = 4.5.dp.toPx(),
                shape = shape,
                color = ink,
                alpha = 1f,
            )
        }
    }
}

@Composable
private fun NodeRow(
    node: UniverseNode,
    layer: UniverseLayer,
    state: UniverseUiState,
    expanded: Boolean,
    onClick: () -> Unit,
) {
    val reducedMotion = rememberReducedMotion()
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .semantics {
                contentDescription = "${node.label}. " +
                    "${sideLine(node, layer, state.aName, state.bName)}. " +
                    "${connectionWord(node.connection)}. ${node.evidence}. " +
                    "${assuranceWord(node.confidence, node.connection)}." +
                    node.suggestion.takeIf { it.isNotBlank() }?.let { " $it." }.orEmpty() +
                    node.questions.firstOrNull()?.let { " Измерено вопросом: $it." }.orEmpty()
            },
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            node.label,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
        )
        Text(
            sideLine(node, layer, state.aName, state.bName),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AnimatedVisibility(
            visible = expanded,
            enter = revealIn(reducedMotion),
            exit = revealOut(reducedMotion),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    node.evidence,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                AssuranceRow(node)
                if (node.suggestion.isNotBlank()) {
                    Text(
                        node.suggestion,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/**
 * The assurance a node or a whole band carries, drawn as four steps: each step is a quarter of the
 * width of the band that decided this connection, so a half-filled row says «half of this band's
 * width still separates the answer from the next band». Nothing here is a probability of the
 * relationship, and a band that compared nothing gets the same «сравнения не было» an unknown node
 * gets — its mean is a mean over an empty set.
 */
@Composable
private fun AssuranceRow(node: UniverseNode) {
    AssuranceRow(confidence = node.confidence, compared = node.connection != Connection.UNKNOWN)
}

@Composable
private fun AssuranceRow(confidence: Int, compared: Boolean) {
    val ink = MaterialTheme.colorScheme.onSurfaceVariant
    val filled = assuranceSteps(confidence)
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            repeat(ASSURANCE_STEPS) { step ->
                Box(
                    modifier = Modifier
                        .size(width = 10.dp, height = 4.dp)
                        .background(
                            if (step < filled) ink else ink.copy(alpha = 0.22f),
                            RoundedCornerShape(2.dp),
                        ),
                )
            }
        }
        Text(
            assuranceWord(confidence, compared),
            style = MaterialTheme.typography.labelSmall,
            color = ink,
        )
    }
}

// ---------------------------------------------------------------------------
// words, derived from the values each node already carries
// ---------------------------------------------------------------------------

internal fun connectionWord(connection: Connection): String = when (connection) {
    Connection.HARMONY -> "совпадение"
    Connection.COMPLEMENTARITY -> "дополнение"
    Connection.DISCUSSION -> "расхождение"
    Connection.UNKNOWN -> "нет данных"
}

/** How many quarters of its own band's width still separate this answer from the next band. */
internal const val ASSURANCE_STEPS = 4

/**
 * The node's assurance in words. `confidence` is a distance inside the band that decided this
 * connection, not a probability of anything, so the sentence names the distance and never a chance.
 * Terse on purpose: the same row carries four marks that say the same thing, and the sentence under
 * the map is where the scale gets explained — a per-node paragraph would put that essay on every
 * row the pair scrolls through.
 */
internal fun assuranceWord(confidence: Int, connection: Connection): String =
    assuranceWord(confidence, connection != Connection.UNKNOWN)

internal fun assuranceWord(confidence: Int, compared: Boolean): String = when {
    !compared -> "сравнения не было"
    confidence <= 0 -> "на границе полосы"
    confidence < 34 -> "ближе к краю"
    confidence < 67 -> "в середине полосы"
    confidence < 100 -> "у надёжного конца"
    else -> "иначе не читается"
}

/**
 * The same distance drawn as [ASSURANCE_STEPS] marks, one per quarter of the band's width, so the
 * row and the sentence say the same thing in two channels.
 */
internal fun assuranceSteps(confidence: Int): Int = when {
    confidence <= 0 -> 0
    confidence >= 100 -> ASSURANCE_STEPS
    else -> (confidence + 24) / 25
}

internal fun sectionTitle(connection: Connection): String = when (connection) {
    Connection.HARMONY -> "Что нас объединяет"
    Connection.COMPLEMENTARITY -> "В чём мы дополняем друг друга"
    Connection.DISCUSSION -> "Где ответы расходятся"
    Connection.UNKNOWN -> "Что нам ещё предстоит узнать"
}

internal fun sectionHint(connection: Connection): String = when (connection) {
    Connection.HARMONY -> "Оба ответили в одной полосе."
    Connection.COMPLEMENTARITY -> "Ответы разные, но не противоположные."
    Connection.DISCUSSION -> "Ответы из противоположных полос."
    Connection.UNKNOWN -> "Здесь сравнивать было не с чем: это не совпадение и не спор."
}

internal fun legendHint(connection: Connection): String = when (connection) {
    Connection.HARMONY -> "сплошная линия, полные точки"
    Connection.COMPLEMENTARITY -> "пунктир, пустые кольца"
    Connection.DISCUSSION -> "линия с разрывом, ромбы"
    Connection.UNKNOWN -> "без линии: одна точка и пустой квадрат"
}

/** The sections a filtered map shows: one kind when filtered, all four when not. */
internal fun shownSections(filter: Connection?): List<Connection> =
    if (filter == null) Connection.entries.toList() else listOf(filter)

internal fun countOf(universe: Universe, kind: Connection): Int =
    universe.layers.sumOf { layer -> layer.nodes.count { it.connection == kind } }

/**
 * Whose answer is what. Interests are either named or not named, so they get words instead of a
 * fake «100%»; the goal layer carries one shared matrix cell rather than two answers, so it says
 * so instead of printing the same number twice as if it were a pair of replies.
 */
internal fun sideLine(node: UniverseNode, layer: UniverseLayer, aName: String?, bName: String?): String {
    val a = aName ?: "Первый"
    val b = bName ?: "Второй"
    return when {
        layer.category == "goals" -> {
            val cell = UniverseLayout.percentOf(node.aValue?.toFloat() ?: node.bValue?.toFloat())
            if (cell == null) "$a или $b не назвали цель" else "Клетка матрицы целей: $cell%"
        }

        layer.category == "interests" ->
            "$a — ${named(node.aValue)} · $b — ${named(node.bValue)}"

        else -> "$a: ${percentText(node, left = true)} · $b: ${percentText(node, left = false)}"
    }
}

private fun named(value: Double?): String = if (value != null) "назвал(а)" else "не называл(а)"

private fun percentText(node: UniverseNode, left: Boolean): String {
    val percent = UniverseLayout.percentOf((if (left) node.aValue else node.bValue)?.toFloat())
        ?: return "нет ответа"
    return "$percent%"
}

/** Percent and coverage on one line, kept visibly apart. */
internal fun bandCaption(layer: UniverseLayer): String {
    val compared = layer.nodes.count { it.hasData }
    val total = layer.nodes.size
    val score = if (layer.hasData) "${layer.score}%" else "нет данных"
    return "${layer.label} · $score · сверено $compared из $total"
}

/** Spoken summary of the map, so nothing the canvas draws exists only on the canvas. */
internal fun universeDescription(state: UniverseUiState): String {
    val universe = state.data ?: return "Карта совместимости ещё не загружена"
    val nodes = universe.layers.flatMap { it.nodes }
    val names = listOfNotNull(state.aName, state.bName).joinToString(" и ")
    return buildString {
        append("Карта совместимости")
        if (names.isNotEmpty()) append(": $names")
        append(". Итог ${universe.overall}%.")
        append(" Слоёв ${universe.layers.size}, узлов ${nodes.size}.")
        Connection.entries.forEach { kind ->
            append(" ${connectionWord(kind)}: ${nodes.count { it.connection == kind }}.")
        }
        // The four marks are drawn per node; the spoken summary explains the scale once, so the
        // reader is not left with a row of dashes and no key.
        append(" Уверенность узла — четыре черты: пустой ряд значит «ещё шаг, и это читается")
        append(" другой связью», полный — «иначе этот ответ не читается».")
    }
}

// ---------------------------------------------------------------------------
// drawing
// ---------------------------------------------------------------------------

private fun DrawScope.drawMark(
    x: Float,
    y: Float,
    radius: Float,
    shape: UniverseLayout.MarkShape,
    color: Color,
    alpha: Float,
) {
    val border = Stroke(width = 1.6.dp.toPx())
    val center = Offset(x, y)
    val half = radius * 0.82f
    when (shape) {
        UniverseLayout.MarkShape.DOT ->
            drawCircle(color = color, radius = radius, center = center, alpha = alpha)

        UniverseLayout.MarkShape.RING ->
            drawCircle(color = color, radius = radius, center = center, style = border, alpha = alpha)

        UniverseLayout.MarkShape.DIAMOND -> rotate(degrees = 45f, pivot = center) {
            drawRect(
                color = color,
                topLeft = Offset(x - half, y - half),
                size = Size(half * 2f, half * 2f),
                alpha = alpha,
            )
        }

        UniverseLayout.MarkShape.ABSENCE -> drawRect(
            color = color,
            topLeft = Offset(x - half, y - half),
            size = Size(half * 2f, half * 2f),
            style = border,
            alpha = alpha,
        )
    }
}

private fun DrawScope.drawLink(
    placement: UniverseLayout.Placement,
    color: Color,
    alpha: Float,
) {
    if (placement.marks.size < 2) return
    val left = placement.marks.minBy { it.x }
    val right = placement.marks.maxBy { it.x }
    drawLinkLine(
        x1 = left.x * size.width,
        x2 = right.x * size.width,
        y = placement.y * size.height,
        link = placement.link,
        color = color,
        alpha = alpha,
    )
}

/**
 * The stroke between two marks. Its style is the second half of the connection's shape language:
 * a line that holds, a line that is stitched, a line that breaks in the middle, and for an unknown
 * node no line at all — the absence of a meeting is drawn, not described.
 */
private fun DrawScope.drawLinkLine(
    x1: Float,
    x2: Float,
    y: Float,
    link: UniverseLayout.LinkStyle,
    color: Color,
    alpha: Float,
) {
    if (link == UniverseLayout.LinkStyle.NONE) return
    val width = 2.dp.toPx()
    when (link) {
        UniverseLayout.LinkStyle.SOLID ->
            drawLine(color, Offset(x1, y), Offset(x2, y), width, cap = StrokeCap.Round, alpha = alpha)

        UniverseLayout.LinkStyle.DASHED -> drawLine(
            color = color,
            start = Offset(x1, y),
            end = Offset(x2, y),
            strokeWidth = width,
            cap = StrokeCap.Round,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 5.dp.toPx())),
            alpha = alpha,
        )

        UniverseLayout.LinkStyle.BROKEN -> {
            val gap = 7.dp.toPx()
            val middle = (x1 + x2) / 2f
            drawLine(color, Offset(x1, y), Offset(middle - gap, y), width, cap = StrokeCap.Round, alpha = alpha)
            drawLine(color, Offset(middle + gap, y), Offset(x2, y), width, cap = StrokeCap.Round, alpha = alpha)
        }

        UniverseLayout.LinkStyle.NONE -> Unit
    }
}

/**
 * Whether the device is told not to animate. The map's marks appear with one tween; on a phone with
 * the animator scale off they must simply be there, because motion the user refused is not a
 * decoration the app gets to keep.
 */
@Composable
private fun rememberReducedMotion(): Boolean {
    val context = LocalContext.current
    return remember(context) {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    }
}

/**
 * A panel opening and closing. Reduced motion keeps both halves instant: the content must arrive
 * and leave without animation, but it must still arrive and leave — the refusal is about motion,
 * not about the explanation.
 */
private fun revealIn(reduced: Boolean): EnterTransition =
    if (reduced) fadeIn(tween(0)) + expandVertically(tween(0))
    else fadeIn(tween(Motion.Base)) + expandVertically(tween(Motion.Base))

private fun revealOut(reduced: Boolean): ExitTransition =
    if (reduced) fadeOut(tween(0)) + shrinkVertically(tween(0))
    else fadeOut(tween(Motion.Fast)) + shrinkVertically(tween(Motion.Fast))

/** The expanded row names its own numbers: a mark without its percent is a shape, not evidence. */
private fun DrawScope.drawMarkPercent(
    textMeasurer: TextMeasurer,
    mark: UniverseLayout.Mark,
    style: TextStyle,
    alpha: Float,
) {
    val percent = mark.percent ?: return
    val layout = textMeasurer.measure("$percent%", style)
    // Outward from the middle, so the number never sits on top of the stroke it belongs to.
    val offset = if (mark.side == UniverseLayout.Side.A) -8.dp.toPx() - layout.size.width else 8.dp.toPx()
    drawText(
        textLayoutResult = layout,
        topLeft = Offset(mark.x * size.width + offset, mark.y * size.height - layout.size.height / 2f),
        alpha = alpha,
    )
}

private fun DrawScope.drawWorldName(
    textMeasurer: TextMeasurer,
    text: String,
    xFraction: Float,
    style: TextStyle,
    widthPx: Float,
    heightPx: Float,
    alpha: Float,
) {
    val layout = textMeasurer.measure(text, style)
    drawText(
        textLayoutResult = layout,
        topLeft = Offset(
            xFraction * widthPx - layout.size.width / 2f,
            UniverseLayout.NAMES_BOTTOM * 0.5f * heightPx - layout.size.height / 2f,
        ),
        alpha = alpha,
    )
}
