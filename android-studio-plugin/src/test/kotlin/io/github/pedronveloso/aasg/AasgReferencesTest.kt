package io.github.pedronveloso.aasg

import com.intellij.psi.PsiPolyVariantReference
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.DumbModeTestUtils
import com.intellij.testFramework.fixtures.LightJavaCodeInsightFixtureTestCase
import org.jetbrains.kotlin.psi.KtClass
import org.jetbrains.kotlin.psi.KtNamedFunction
import org.jetbrains.yaml.psi.YAMLScalar

class AasgReferencesTest : LightJavaCodeInsightFixtureTestCase() {
    private fun configure(value: String, filename: String = "aasg.yaml"): List<AndroidReference> {
        val file =
            myFixture.configureByText(filename, "schema: 9\ncaptures:\n  home:\n    test: $value\n")
        return PsiTreeUtil.findChildrenOfType(file, YAMLScalar::class.java).flatMap {
            it.references.filterIsInstance<AndroidReference>()
        }
    }

    fun testJavaClassAndMethodWithPreciseQuotedRanges() {
        val clazz =
            myFixture.addClass("package example; public class Capture { public void capture() {} }")
        for (quote in listOf("", "'", "\"")) {
            val refs = configure("${quote}example.Capture#capture$quote")
            assertEquals(2, refs.size)
            assertEquals("example.Capture", refs[0].rangeInElement.substring(refs[0].element.text))
            assertEquals("capture", refs[1].rangeInElement.substring(refs[1].element.text))
            assertEquals(clazz, refs[0].resolve())
            assertEquals(clazz.methods.single(), refs[1].resolve())
        }
    }

    fun testKotlinNavigationUsesSourceDeclarations() {
        myFixture.addFileToProject(
            "example/Capture.kt",
            "package example\nclass Capture { fun capture() {} }",
        )
        val refs = configure("example.Capture#capture")
        assertEquals(2, refs.size)
        assertInstanceOf(refs[0].resolve(), KtClass::class.java)
        assertInstanceOf(refs[1].resolve(), KtNamedFunction::class.java)
    }

    fun testNestedJvmClassAndCommaSeparatedSelectors() {
        myFixture.addClass(
            "package example; public class Outer { public static class Nested { public void capture() {} } }"
        )
        myFixture.addClass("package example; public class Other {}")
        val refs = configure("'example.Outer\$Nested#capture, example.Other'")
        assertEquals(3, refs.size)
        assertTrue(refs.all { it.multiResolve(false).isNotEmpty() })
        assertEquals(
            "example.Outer\$Nested",
            refs[0].rangeInElement.substring(refs[0].element.text),
        )
    }

    fun testOverloadsReturnEveryTarget() {
        myFixture.addClass(
            "package example; public class Capture { public void capture() {} public void capture(int n) {} }"
        )
        val reference = configure("example.Capture#capture")[1] as PsiPolyVariantReference
        assertEquals(2, reference.multiResolve(false).size)
    }

    fun testRunnerAndUnrelatedKeys() {
        val clazz = myFixture.addClass("package example; public class Runner {}")
        val file =
            myFixture.configureByText(
                "aasg.yml",
                """
                android:
                  direct_instrumentation:
                    runner: example.Runner
                unrelated:
                  runner: example.Runner
                  test: example.Runner
                captures:
                  home:
                    arguments:
                      test: example.Runner
                """
                    .trimIndent(),
            )
        val refs =
            PsiTreeUtil.findChildrenOfType(file, YAMLScalar::class.java).flatMap {
                it.references.filterIsInstance<AndroidReference>()
            }
        assertEquals(1, refs.size)
        assertEquals(clazz, refs.single().resolve())
        assertEmpty(configure("example.Runner", "application.yaml"))
    }

    fun testUnresolvedWarningsAndMissingClassDoesNotDuplicateMethodWarning() {
        myFixture.enableInspections(AasgUnresolvedReferenceInspection())
        configure("example.Missing#capture")
        val warnings =
            myFixture.doHighlighting().filter {
                it.description?.startsWith("Cannot resolve") == true
            }
        assertEquals(1, warnings.size)
        myFixture.addClass("package example; public class Capture {}")
        configure("example.Capture#missing")
        assertEquals(
            1,
            myFixture.doHighlighting().count {
                it.description?.startsWith("Cannot resolve method") == true
            },
        )
    }

    fun testIndexingSuppressesReferencesAndInspection() {
        myFixture.addClass("package example; public class Capture {}")
        configure("example.Capture")
        DumbModeTestUtils.runInDumbModeSynchronously(project) {
            val scalar =
                PsiTreeUtil.findChildrenOfType(myFixture.file, YAMLScalar::class.java).first {
                    AasgYaml.isReference(it)
                }
            assertEmpty(AasgReferenceContributor.references(scalar))
            assertEmpty(AndroidSymbols.classes(project, "example.Capture"))
        }
        assertNotNull(configure("example.Capture").single().resolve())
    }

    fun testOldSchemaStillNavigatesAndMalformedSelectorsAreIgnored() {
        val clazz = myFixture.addClass("package example; public class Capture {}")
        val file =
            myFixture.configureByText(
                "aasg.yaml",
                "schema: 4\ncaptures:\n  home:\n    test: example.Capture\n",
            )
        val scalar =
            PsiTreeUtil.findChildrenOfType(file, YAMLScalar::class.java).first {
                AasgYaml.isReference(it)
            }
        assertEquals(
            clazz,
            scalar.references.filterIsInstance<AndroidReference>().single().resolve(),
        )
        for (value in
            listOf(
                "''",
                "example.",
                "'#capture'",
                "example.Capture#",
                "|\n      example.Capture",
            )) {
            assertEmpty(configure(value))
        }
    }

    fun testEscapedQuotedClassHasCorrectHostRange() {
        myFixture.addClass("package example; public class Capture {}")
        val refs = configure("\"example.\\u0043apture\"")
        assertEquals(1, refs.size)
        assertNotNull(refs.single().resolve())
        assertEquals(
            "example.\\u0043apture",
            refs.single().rangeInElement.substring(refs.single().element.text),
        )
    }
}
