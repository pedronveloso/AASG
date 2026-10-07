package io.github.pedronveloso.aasg

import com.intellij.codeInsight.completion.CompletionContributor
import com.intellij.codeInsight.completion.CompletionParameters
import com.intellij.codeInsight.completion.CompletionProvider
import com.intellij.codeInsight.completion.CompletionResultSet
import com.intellij.codeInsight.completion.CompletionType
import com.intellij.codeInsight.completion.InsertionContext
import com.intellij.codeInsight.lookup.LookupElementBuilder
import com.intellij.openapi.editor.RangeMarker
import com.intellij.openapi.project.DumbService
import com.intellij.patterns.PlatformPatterns
import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiClass
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.PsiShortNamesCache
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.ProcessingContext
import org.jetbrains.yaml.psi.YAMLScalar

class AasgCompletionContributor : CompletionContributor() {
    init {
        extend(
            CompletionType.BASIC,
            PlatformPatterns.psiElement(),
            object : CompletionProvider<CompletionParameters>() {
                override fun addCompletions(
                    parameters: CompletionParameters,
                    context: ProcessingContext,
                    result: CompletionResultSet,
                ) {
                    if (DumbService.isDumb(parameters.position.project)) return
                    val scalar =
                        PsiTreeUtil.getParentOfType(
                            parameters.position,
                            YAMLScalar::class.java,
                            false,
                        ) ?: return
                    if (!AasgYaml.isReference(scalar)) return
                    val text = ScalarText(scalar)
                    val value = text.value ?: return
                    val offset =
                        text.decodedOffset(parameters.offset - scalar.textRange.startOffset)
                            ?: return
                    val segmentStart = value.lastIndexOf(',', offset - 1) + 1
                    val hash =
                        value.indexOf('#', segmentStart).takeIf { it in segmentStart until offset }
                    val start = if (hash == null) segmentStart else hash + 1
                    val prefix = value.substring(start, offset).trimStart()
                    val set = result.withPrefixMatcher(prefix)
                    val replacement = tokenRange(parameters, hash != null) ?: return
                    if (hash != null && !AasgYaml.isRunner(scalar)) {
                        val className = value.substring(segmentStart, hash).trim()
                        AndroidSymbols.classes(scalar.project, className)
                            .flatMap { it.allMethods.toList() }
                            .filter { !it.isConstructor }
                            .map { it.name }
                            .distinct()
                            .sorted()
                            .forEach {
                                set.addElement(
                                    LookupElementBuilder.create(it)
                                        .withTypeText(className)
                                        .withInsertHandler { insertion, item ->
                                            replaceToken(insertion, replacement, item.lookupString)
                                        }
                                )
                            }
                    } else if (hash == null) {
                        val scope = GlobalSearchScope.allScope(scalar.project)
                        val cache = PsiShortNamesCache.getInstance(scalar.project)
                        val seen = mutableSetOf<String>()
                        val packageName = prefix.substringBeforeLast('.', "")
                        if ('$' in prefix) {
                            AndroidSymbols.classes(scalar.project, prefix.substringBeforeLast('$'))
                                .flatMap { it.innerClasses.toList() }
                                .forEach { addClass(it, prefix, seen, set, replacement) }
                            return
                        }
                        if (packageName.isNotEmpty()) {
                            JavaPsiFacade.getInstance(scalar.project)
                                .findPackage(packageName)
                                ?.getClasses(scope)
                                ?.forEach { addClass(it, prefix, seen, set, replacement) }
                            return
                        }
                        // Filter the name index before resolving classes; never scan source files.
                        val shortPrefix = prefix.substringAfterLast('.').substringAfterLast('$')
                        val names = mutableSetOf<String>()
                        cache.processAllClassNames { name ->
                            com.intellij.openapi.progress.ProgressManager.checkCanceled()
                            if (name.startsWith(shortPrefix, ignoreCase = true)) names.add(name)
                            true
                        }
                        // Querying a second index inside the name processor can deadlock the IDE.
                        for (name in names.sorted()) {
                            com.intellij.openapi.progress.ProgressManager.checkCanceled()
                            cache.getClassesByName(name, scope).forEach {
                                addClass(it, prefix, seen, set, replacement)
                            }
                        }
                    }
                }
            },
        )
    }

    private fun addClass(
        clazz: PsiClass,
        prefix: String,
        seen: MutableSet<String>,
        result: CompletionResultSet,
        replacement: RangeMarker,
    ) {
        val name = AndroidSymbols.binaryName(clazz) ?: return
        if (!name.startsWith(prefix, true) && !clazz.name.orEmpty().startsWith(prefix, true)) return
        if (!seen.add(name)) return
        result.addElement(
            LookupElementBuilder.create(name)
                .withLookupString(clazz.name.orEmpty())
                .withIcon(clazz.getIcon(0))
                .withTypeText(clazz.containingFile?.name)
                .withInsertHandler { insertion, item ->
                    replaceToken(insertion, replacement, item.lookupString)
                }
        )
    }

    /** Track the original host token through the IDE's default prefix replacement. */
    private fun tokenRange(parameters: CompletionParameters, method: Boolean): RangeMarker? {
        val document = parameters.originalFile.viewProvider.document ?: return null
        val scalar =
            parameters.originalFile.findElementAt((parameters.offset - 1).coerceAtLeast(0))?.let {
                PsiTreeUtil.getParentOfType(it, YAMLScalar::class.java, false)
            }
        val range =
            if (scalar != null && AasgYaml.isReference(scalar)) {
                val text = ScalarText(scalar)
                val value = text.value ?: return null
                val offset =
                    text.decodedOffset(parameters.offset - scalar.textRange.startOffset)
                        ?: return null
                var start = value.lastIndexOf(',', offset - 1) + 1
                if (method) start = value.indexOf('#', start) + 1
                while (start < offset && value[start].isWhitespace()) start++
                var end = offset
                while (
                    end < value.length &&
                        (value[end].isLetterOrDigit() ||
                            value[end] == '_' ||
                            value[end] == '$' ||
                            (!method && value[end] == '.'))
                ) end++
                text.range(start, end)?.shiftRight(scalar.textRange.startOffset) ?: return null
            } else {
                com.intellij.openapi.util.TextRange(parameters.offset, parameters.offset)
            }
        return document.createRangeMarker(range).apply {
            isGreedyToLeft = true
            isGreedyToRight = true
        }
    }

    private fun replaceToken(insertion: InsertionContext, token: RangeMarker, name: String) {
        if (!token.isValid) return
        val start = token.startOffset
        insertion.document.replaceString(start, maxOf(token.endOffset, insertion.tailOffset), name)
        insertion.tailOffset = start + name.length
        insertion.editor.caretModel.moveToOffset(insertion.tailOffset)
        token.dispose()
    }
}
