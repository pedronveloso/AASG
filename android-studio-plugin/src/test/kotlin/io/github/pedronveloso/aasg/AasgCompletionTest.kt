package io.github.pedronveloso.aasg

import com.intellij.codeInsight.lookup.Lookup
import com.intellij.testFramework.fixtures.LightJavaCodeInsightFixtureTestCase

class AasgCompletionTest : LightJavaCodeInsightFixtureTestCase() {
    private fun complete(value: String, choice: String, expected: String) {
        myFixture.configureByText("aasg.yaml", "captures:\n  home:\n    test: $value\n")
        val items = myFixture.completeBasic()
        if (items != null) {
            val item = items.firstOrNull { it.lookupString == choice }
            assertNotNull("Missing completion '$choice': ${items.map { it.lookupString }}", item)
            myFixture.lookup.currentItem = item
            myFixture.finishLookup(Lookup.NORMAL_SELECT_CHAR)
        }
        myFixture.checkResult("captures:\n  home:\n    test: $expected\n")
    }

    fun testClassCompletionPreservesQuotesSelectorAndSuffix() {
        myFixture.addClass("package example; public class Capture { public void capture() {} }")
        myFixture.addClass("package example; public class Other {}")
        complete(
            "'example.Cap<caret>ture#capture, example.Other'",
            "example.Capture",
            "'example.Capture<caret>#capture, example.Other'",
        )
    }

    fun testMethodCompletionReplacesRemainderAndPreservesSecondSelector() {
        myFixture.addClass("package example; public class Capture { public void capture() {} }")
        complete(
            "\"example.Capture#cap<caret>ture, example.Other\"",
            "capture",
            "\"example.Capture#capture<caret>, example.Other\"",
        )
    }

    fun testShortClassNameCompletionInEmptyValue() {
        myFixture.addClass("package example; public class Capture {}")
        complete("Cap<caret>", "example.Capture", "example.Capture<caret>")
    }

    fun testEscapedQuotedPrefixCompletion() {
        myFixture.addClass("package example; public class Capture {}")
        complete(
            "\"example.\\u0043ap<caret>ture\"",
            "example.Capture",
            "\"example.Capture<caret>\"",
        )
    }

    fun testNestedClassAndSecondSelectorCompletion() {
        myFixture.addClass("package example; public class Outer { public static class Nested {} }")
        complete(
            "'example.Other, example.Outer\$Nes<caret>ted'",
            "example.Outer\$Nested",
            "'example.Other, example.Outer\$Nested<caret>'",
        )
    }
}
