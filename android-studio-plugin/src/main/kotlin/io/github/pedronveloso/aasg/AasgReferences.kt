package io.github.pedronveloso.aasg

import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.patterns.PlatformPatterns
import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementResolveResult
import com.intellij.psi.PsiPolyVariantReferenceBase
import com.intellij.psi.PsiReference
import com.intellij.psi.PsiReferenceContributor
import com.intellij.psi.PsiReferenceProvider
import com.intellij.psi.PsiReferenceRegistrar
import com.intellij.psi.ResolveResult
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.util.ProcessingContext
import org.jetbrains.yaml.psi.YAMLScalar

internal object AndroidSymbols {
    fun classes(project: Project, name: String): List<PsiClass> {
        if (DumbService.isDumb(project)) return emptyList()
        val facade = JavaPsiFacade.getInstance(project)
        val qualifiedName = name.replace('$', '.')
        val sources = facade.findClasses(qualifiedName, GlobalSearchScope.projectScope(project))
        val classes =
            if (sources.isNotEmpty()) sources
            else facade.findClasses(qualifiedName, GlobalSearchScope.allScope(project))
        return classes.distinctBy { it.navigationElement }
    }

    fun binaryName(clazz: PsiClass): String? {
        val parent = clazz.containingClass ?: return clazz.qualifiedName
        return binaryName(parent)?.let { "$it\$${clazz.name ?: return null}" }
    }
}

internal class AndroidReference(
    scalar: YAMLScalar,
    range: TextRange,
    val className: String,
    val methodName: String? = null,
) : PsiPolyVariantReferenceBase<YAMLScalar>(scalar, range, true) {
    override fun multiResolve(incompleteCode: Boolean): Array<ResolveResult> {
        if (DumbService.isDumb(element.project)) return ResolveResult.EMPTY_ARRAY
        val classes = AndroidSymbols.classes(element.project, className)
        val targets =
            if (methodName == null) {
                classes.map { it.navigationElement }
            } else {
                classes
                    .flatMap { it.findMethodsByName(methodName, true).toList() }
                    .map { it.navigationElement }
            }
        return targets.distinct().map { PsiElementResolveResult(it) }.toTypedArray()
    }

    override fun getVariants(): Array<Any> = emptyArray()
}

class AasgReferenceContributor : PsiReferenceContributor() {
    override fun registerReferenceProviders(registrar: PsiReferenceRegistrar) {
        registrar.registerReferenceProvider(
            PlatformPatterns.psiElement(YAMLScalar::class.java),
            object : PsiReferenceProvider() {
                override fun getReferencesByElement(
                    element: PsiElement,
                    context: ProcessingContext,
                ): Array<PsiReference> = references(element as YAMLScalar)
            },
        )
    }

    companion object {
        internal fun references(scalar: YAMLScalar): Array<PsiReference> {
            if (!AasgYaml.isReference(scalar) || DumbService.isDumb(scalar.project))
                return emptyArray()
            val text = ScalarText(scalar)
            val value = text.value ?: return emptyArray()
            return Selectors.parse(value, AasgYaml.isRunner(scalar))
                .flatMap { part ->
                    buildList {
                        text.range(part.classStart, part.classEnd)?.let {
                            add(AndroidReference(scalar, it, part.className))
                        }
                        if (
                            part.methodName != null &&
                                part.methodStart != null &&
                                part.methodEnd != null
                        ) {
                            text.range(part.methodStart, part.methodEnd)?.let {
                                add(AndroidReference(scalar, it, part.className, part.methodName))
                            }
                        }
                    }
                }
                .toTypedArray()
        }
    }
}
